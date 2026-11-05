from sqlalchemy import select
from app.domain.models import CalendarioAcademico
import json
import logging
import re
from datetime import date
from typing import Any, Dict, List, Optional
from cachetools import TTLCache
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.chat_schemas import ChatRequest
from app.services.attendance_service import AttendanceService
from app.services.vehicle_service import VehicleService
from app.services.prediction_service import get_prophet_forecast, get_gbr_forecast_14days, get_visit_profiles
from app.services.chat.fechas_chat import (
    extraer_o_normalizar_fechas,
    obtener_anio_activo_espacio,
    obtener_contexto_calendario_rango,
    obtener_resumen_hechos_institucionales,
)

logger = logging.getLogger(__name__)

_cache_resultados_herramientas: TTLCache = TTLCache(maxsize=300, ttl=600)
_cache_graficos_contexto: TTLCache = TTLCache(maxsize=300, ttl=600)

async def _resolver_datos_grafico_contexto_interno(
    grafico_id: str,
    espacio_id: int,
    fecha_inicio: Optional[str],
    fecha_fin: Optional[str],
    db: AsyncSession,
    filtros: Optional[Dict[str, Any]] = None,
) -> tuple[Optional[str], Any, str, Optional[Dict[str, Any]], Optional[List[Dict[str, Any]]]]:
    """
    Enrutador determinista de gráficos: mapea directamente el slug enfocado hacia el servicio
    correspondiente y calcula un resumen estadístico estructurado para alimentar al LLM.
    """
    from datetime import date
    d_ini = None
    d_fin = None
    if fecha_inicio:
        try:
            d_ini = date.fromisoformat(str(fecha_inicio)[:10])
        except Exception:
            pass
    if fecha_fin:
        try:
            d_fin = date.fromisoformat(str(fecha_fin)[:10])
        except Exception:
            pass

    slug = re.sub(r'[^a-z0-9_]', '_', (grafico_id or '').lower().strip()).strip('_')
    filtros = filtros or {}
    alcance = filtros.get("alcance") or filtros.get("calidad") or "conformes"
    sala = filtros.get("sala")
    facultad = filtros.get("facultad")
    carrera = filtros.get("carrera")
    cohorte = filtros.get("cohorte")
    regimen_horario = filtros.get("regimen_horario") or filtros.get("rango_horario") or "todos"
    direccion = filtros.get("direccion") or filtros.get("sentido") or "todos"
    dias_semana = filtros.get("dias_semana") or filtros.get("tipo_dia")
    door = filtros.get("torniquetes") or filtros.get("door") or filtros.get("puerta")
    perfil_visita = filtros.get("perfil_visita") or filtros.get("perfil") or "todos"
    marcajes = filtros.get("marcajes") or "todos"
    sector = filtros.get("sector")
    tipo_vehiculo = filtros.get("tipo_vehiculo")
    nombre_espacio = "Estacionamiento CSF" if espacio_id == 2 else "Biblioteca CSF"

    # Capacidades físicas y calibradas oficiales Campus San Francisco
    CAP_SALA_1 = 150  # CSF02 2° Piso (Estudio y Biblioteca con Locker)
    CAP_SALA_2 = 126  # CSF04 1° Piso (Pecera de Estudio 24h régimen habitual)
    CAP_SALA_2_NOCTURNA = 226  # CSF04 1° Piso durante régimen de exámenes nocturnos
    CAP_CAMPUS_CALIBRADA = 276  # Suma calibrada 150 + 126
    CAP_CAMPUS_REFERENCIA = 350  # Capacidad máxima histórica de referencia

    if sala and ("1" in str(sala) or "csf02" in str(sala).lower()):
        cap_activa = CAP_SALA_1
        sala_desc = "Sala 1 — CSF02 (2° Piso, Estudio y Biblioteca con Locker: 150 asientos calibrados)"
    elif sala and ("2" in str(sala) or "csf04" in str(sala).lower() or "pecera" in str(sala).lower()):
        cap_activa = CAP_SALA_2_NOCTURNA if regimen_horario == "24h_delta" else CAP_SALA_2
        sala_desc = f"Sala 2 — CSF04 Pecera (1° Piso, Estudio 24h: {cap_activa} asientos calibrados)"
    else:
        cap_activa = CAP_CAMPUS_CALIBRADA
        sala_desc = "Campus San Francisco Completo (Sala 1: 150 as. + Sala 2: 126 as. = 276 asientos calibrados)"

    regimen_desc = ""
    if regimen_horario == "24h_delta":
        regimen_desc = "Régimen Horario Activo: Turno Nocturno Delta 24h (L-J 23:00-07:00 h | Vie 22:00-06:00 h en Sala 2 Pecera, 226 asientos)."
    elif regimen_horario == "examenes":
        regimen_desc = "Régimen Horario Activo: Extensión Horaria Especial Exámenes."
    elif regimen_horario == "diurno":
        regimen_desc = "Régimen Horario Activo: Diurno Habitual (07:00 a 20:30 h)."
    else:
        regimen_desc = "Régimen Horario Activo: Ciclo Continuo 24 Horas."

    detalle_hardware_torniquetes = (
        "Puntos de Control Físico (4 canales activos CSF):\n"
        "- CSF02 Torniquete Principal: Canal 2202/2184 (CSF02_320 CTRA IN 02 / OUT 02)\n"
        "- CSF02 Acceso Universal Prioritario: Canal 2177/2170 (CSF02_320 CTRA IN 01 / OUT 01)\n"
        "- CSF04 Torniquete Principal Pecera: Canal 2592/2587 (CSF04_110 IN 01 / OUT)\n"
        "- CSF04 Acceso Universal Prioritario Pecera: Canal 3411/3416 (CSF04_110 IN 02_Door_1 / OUT 02_Door_1)"
    )

    hitos_calendario = await obtener_contexto_calendario_rango(db, d_ini, d_fin, espacio_id=espacio_id)
    resumen_hechos = await obtener_resumen_hechos_institucionales(db, d_ini, d_fin, espacio_id=espacio_id)
    contexto_hitos = resumen_hechos

    component = None
    payload = None
    resumen_metricas = ""
    fig_data = None
    table_data = None

    SLUGS_EXCLUSIVOS_BIBLIOTECA = [
        "distribucion_curricular", "torniquetes", "comparativa_salas",
        "distribucion_marcajes", "checkins", "promedio_dias_semana", "volumen_mensual",
        "evolucion_semanal", "impacto_examenes", "perfiles_visita", "pronostico_14d", "permanencia_salas",
        "campana_24h", "analisis_24h", "flujo_nocturno", "justificacion_24h"
    ]
    SLUGS_EXCLUSIVOS_ESTACIONAMIENTO = [
        "composicion_flota", "flota_vehicular", "camaras_anpr", "movilidad_intercampus", "kmeans_clusters"
    ]
    if espacio_id == 1 and any(s in slug for s in SLUGS_EXCLUSIVOS_ESTACIONAMIENTO):
        return None, None, "El gráfico seleccionado pertenece al módulo de Estacionamiento CSF. Para consultarlo, cambie al módulo Estacionamiento en el selector superior.", None, None
    if espacio_id == 2 and any(s in slug for s in SLUGS_EXCLUSIVOS_BIBLIOTECA):
        return None, None, "El gráfico seleccionado pertenece al módulo de Biblioteca CSF. Para consultarlo, cambie al módulo Biblioteca en el selector superior.", None, None

    try:
        # 1. Curva de Aforo / Ocupación
        if any(k in slug for k in ["aforo_curva", "curva_ocupacion", "curva_de_aforo", "curva_de_ocupacion"]):
            if espacio_id == 2:
                data = await VehicleService.get_hourly_flow(
                    session=db,
                    fecha_inicio=d_ini,
                    fecha_fin=d_fin,
                    espacio_id=2,
                    alcance=alcance,
                    regimen_horario=regimen_horario,
                    direccion=direccion,
                    dias_semana=dias_semana,
                    door=door,
                    sector=sector,
                    tipo_vehiculo=tipo_vehiculo,
                )
                component = "OccupancyAreaChart"
                payload = data
                cap = 180
                max_val = 0
                max_time = "N/D"
                tot_in = 0
                tot_out = 0
                for r in (data or []):
                    tot_in += r.get("entradas", 0) or r.get("ingresos", 0) or 0
                    tot_out += r.get("salidas", 0) or 0
                    val = r.get("ocupacion_promedio") or r.get("entradas") or r.get("ingresos") or 0
                    if val > max_val:
                        max_val = val
                        max_time = r.get("bucket", "N/D")
                pct_cap = (max_val / cap * 100) if cap else 0
                resumen_metricas = (
                    f"Gráfico enfocado: Curva de Ocupación Vehicular ({nombre_espacio}).\n"
                    f"- Capacidad total instalada: {cap} plazas.\n"
                    f"- Pico máximo de aforo/ocupación: {max_val} vehículos ({pct_cap:.1f}% de capacidad) en fecha/hora {max_time}.\n"
                    f"- Total de entradas acumuladas en el período: {tot_in:,} vehículos.\n"
                    f"- Total de salidas acumuladas en el período: {tot_out:,} vehículos.\n"
                    f"- Cantidad de intervalos temporales evaluados: {len(data or [])} registros.\n"
                    f"{contexto_hitos}"
                )
                table_data = data[:50] if isinstance(data, list) else None
            else:
                data = await AttendanceService.get_hourly_flow(
                    session=db,
                    fecha_inicio=d_ini,
                    fecha_fin=d_fin,
                    espacio_id=1,
                    alcance=alcance,
                    regimen_horario=regimen_horario,
                    direccion=direccion,
                    dias_semana=dias_semana,
                    door=door,
                    perfil_visita=perfil_visita,
                    marcajes=marcajes,
                    sala=sala,
                    carrera=carrera,
                    facultad=facultad,
                    cohorte=cohorte,
                )
                component = "OccupancyAreaChart"
                payload = data
                cap = cap_activa
                max_val = 0
                max_time = "N/D"
                tot_in = 0
                tot_out = 0
                for r in (data or []):
                    tot_in += r.get("ingresos", 0) or r.get("entradas", 0) or 0
                    tot_out += r.get("salidas", 0) or 0
                    val = r.get("ocupacion_promedio") or r.get("ingresos") or 0
                    if val > max_val:
                        max_val = val
                        max_time = r.get("bucket", "N/D")
                pct_cap = (max_val / cap * 100) if cap else 0
                resumen_metricas = (
                    f"Gráfico enfocado: Curva de Aforo Concurrente ({nombre_espacio}).\n"
                    f"- Entorno y Capacidad Calibrada: {sala_desc}.\n"
                    f"- {regimen_desc}\n"
                    f"- Pico máximo registrado en el período: {max_val} personas ({pct_cap:.1f}% sobre capacidad calibrada de {cap} asientos) el {max_time}.\n"
                    f"- Total de ingresos acumulados con filtros activos: {tot_in:,}.\n"
                    f"- Total de salidas registradas: {tot_out:,}.\n"
                    f"- Intervalos horarios evaluados: {len(data or [])} registros.\n"
                    f"{contexto_hitos}"
                )
                table_data = data[:50] if isinstance(data, list) else None

        # 2. Pronóstico Prophet
        elif any(k in slug for k in ["prophet", "pronostico_prophet", "prediccion_prophet"]):
            data = await get_prophet_forecast(db, recinto="vehicular" if espacio_id == 2 else "biblioteca")
            component = "ForecastLineChart"
            payload = data
            pron = data.get("pronostico_7d") or data.get("forecast") or []
            max_p = 0
            max_t = "N/D"
            sum_p = 0
            for pt in pron:
                v = pt.get("aforo_proyectado", 0) or pt.get("yhat", 0) or 0
                sum_p += v
                if v > max_p:
                    max_p = v
                    max_t = pt.get("bucket", pt.get("ds", "N/D"))
            avg_p = (sum_p / len(pron)) if pron else 0
            m_stat = data.get("model_status", {})
            resumen_metricas = (
                f"Gráfico enfocado: Pronóstico Continuo Prophet ({nombre_espacio}).\n"
                f"- Alcance: 7 días de serie histórica y 7 días de proyección futura continua.\n"
                f"- Capacidad institucional calibrada de referencia: {cap_activa} asientos ({sala_desc}).\n"
                f"- Pico proyectado más elevado: {max_p:.0f} ocupantes proyectados en fecha/hora {max_t}.\n"
                f"- Demanda promedio estimada en el horizonte: {avg_p:.0f} ocupantes.\n"
                f"- Estado del modelo: {m_stat.get('status', 'ok')} (Entrenado el {m_stat.get('model_date', 'reciente')}).\n"
                f"{contexto_hitos}"
            )
            table_data = pron[:40] if pron else None

        # 3. Flujo Horario
        elif any(k in slug for k in ["flujo_horario", "flujo_horario_de"]):
            if espacio_id == 2:
                data = await VehicleService.get_hourly_flow(
                    session=db,
                    fecha_inicio=d_ini,
                    fecha_fin=d_fin,
                    espacio_id=2,
                    alcance=alcance,
                    regimen_horario=regimen_horario,
                    direccion=direccion,
                    dias_semana=dias_semana,
                    door=door,
                    sector=sector,
                    tipo_vehiculo=tipo_vehiculo,
                )
            else:
                data = await AttendanceService.get_hourly_flow(
                    session=db,
                    fecha_inicio=d_ini,
                    fecha_fin=d_fin,
                    espacio_id=1,
                    alcance=alcance,
                    regimen_horario=regimen_horario,
                    direccion=direccion,
                    dias_semana=dias_semana,
                    door=door,
                    perfil_visita=perfil_visita,
                    marcajes=marcajes,
                    sala=sala,
                    carrera=carrera,
                    facultad=facultad,
                    cohorte=cohorte,
                )
            component = "HourlyBarChart"
            payload = data
            max_h = 0
            top_hour = "N/D"
            min_h = 999999
            low_hour = "N/D"
            tot_in = 0
            tot_out = 0
            for r in (data or []):
                ent = r.get("entradas", 0) or r.get("ingresos", 0) or 0
                sal = r.get("salidas", 0) or 0
                tot_in += ent
                tot_out += sal
                if ent > max_h:
                    max_h = ent
                    top_hour = r.get("hora", r.get("bucket", "N/D"))
                if 0 < ent < min_h:
                    min_h = ent
                    low_hour = r.get("hora", r.get("bucket", "N/D"))
            resumen_metricas = (
                f"Gráfico enfocado: Flujo Horario de Accesos ({nombre_espacio}).\n"
                f"- Contexto operativo: {sala_desc}.\n"
                f"- {regimen_desc}\n"
                f"- Franja horaria pico con mayor volumen: {top_hour} con {max_h:,} entradas/ingresos.\n"
                f"- Franja valle con menor afluencia: {low_hour if min_h != 999999 else 'N/D'} con {min_h if min_h != 999999 else 0:,} accesos.\n"
                f"- Total acumulado: {tot_in:,} entradas y {tot_out:,} salidas.\n"
                f"{contexto_hitos}"
            )
            table_data = data[:40] if isinstance(data, list) else None

        # 4. Mapa de Calor
        elif any(k in slug for k in ["mapa_calor", "heatmap", "mapa_de_calor"]):
            data = await AttendanceService.get_heatmap(
                session=db,
                espacio_id=espacio_id,
                fecha_inicio=d_ini,
                fecha_fin=d_fin,
                alcance=alcance,
                regimen_horario=regimen_horario,
                direccion=direccion,
                dias_semana=dias_semana,
                door=door,
                perfil_visita=perfil_visita,
                marcajes=marcajes,
                sala=sala,
                carrera=carrera,
                facultad=facultad,
                cohorte=cohorte,
            )
            component = "HeatmapChart"
            payload = data
            top_spot = {}
            max_occ = 0
            for c in (data or []):
                val = c.get("ocupacion_media", 0) or c.get("aforo", 0) or c.get("valor", 0) or 0
                if val > max_occ:
                    max_occ = val
                    top_spot = c
            resumen_metricas = (
                f"Gráfico enfocado: Mapa de Calor de Ocupación Día × Hora ({nombre_espacio}).\n"
                f"- Configuración: {sala_desc}.\n"
                f"- {regimen_desc}\n"
                f"- Momento de mayor saturación: Día {top_spot.get('dia_semana', 'N/D')} a las {top_spot.get('hora', 'N/D')} hrs con aforo promedio de {max_occ:.0f} ocupantes.\n"
                f"- Total de combinaciones día-hora evaluadas: {len(data or [])} bloques.\n"
                f"{contexto_hitos}"
            )
            table_data = data[:35] if isinstance(data, list) else None

        # 5. Comparativa de Salas
        elif any(k in slug for k in ["comparativa_salas", "comparativa_de_salas", "comparativa_de_afluencia"]):
            data = await AttendanceService.get_rooms_comparison(
                session=db,
                espacio_id=1,
                fecha_inicio=d_ini,
                fecha_fin=d_fin,
                alcance=alcance,
                regimen_horario=regimen_horario,
                direccion=direccion,
                dias_semana=dias_semana,
                door=door,
                marcajes=marcajes,
                carrera=carrera,
                facultad=facultad,
            )
            component = "RoomComparisonPlotlyChart"
            payload = data
            resumen_salas = data.get("resumen_salas", []) if isinstance(data, dict) else []
            res_s1 = next((s for s in resumen_salas if "CSF02" in s.get("sala", "") or "1" in s.get("sala", "")), {})
            res_s2 = next((s for s in resumen_salas if "CSF04" in s.get("sala", "") or "2" in s.get("sala", "")), {})
            tot_s1 = res_s1.get("entradas", 0) or res_s1.get("total_marcajes", 0)
            tot_s2 = res_s2.get("entradas", 0) or res_s2.get("total_marcajes", 0)
            u_s1 = res_s1.get("usuarios_unicos", 0)
            u_s2 = res_s2.get("usuarios_unicos", 0)
            pct_s1 = res_s1.get("porcentaje_afluencia", 0)
            pct_s2 = res_s2.get("porcentaje_afluencia", 0)
            predom = "Sala 1 (CSF02 2° Piso)" if tot_s1 >= tot_s2 else "Sala 2 (CSF04 Pecera 1° Piso)"
            cap_s2_efectiva = CAP_SALA_2_NOCTURNA if regimen_horario == "24h_delta" else CAP_SALA_2
            resumen_metricas = (
                f"Gráfico enfocado: Comparativa de Afluencia entre Salas (Sala 1 vs Sala 2).\n"
                f"- Sala 1 (CSF02 2° Piso, Estudio y Biblioteca con Locker): {tot_s1:,} accesos ({u_s1:,} alumnos únicos, {pct_s1:.1f}% de afluencia, capacidad calibrada: {CAP_SALA_1} asientos).\n"
                f"- Sala 2 (CSF04 Pecera 1° Piso, Estudio 24h): {tot_s2:,} accesos ({u_s2:,} alumnos únicos, {pct_s2:.1f}% de afluencia, capacidad calibrada: {cap_s2_efectiva} asientos).\n"
                f"- Capacidad combinada calibrada: {CAP_CAMPUS_CALIBRADA} asientos (referencia histórica agregada: {CAP_CAMPUS_REFERENCIA} asientos).\n"
                f"- Sala predominante en el período: {predom}.\n"
                f"- {detalle_hardware_torniquetes}\n"
                f"{contexto_hitos}"
            )
            table_data = resumen_salas if resumen_salas else None

        # 6. Torniquetes y Accesos Universales
        elif any(k in slug for k in ["torniquetes", "uso_de_torniquetes", "doors_usage"]):
            data = await AttendanceService.get_door_usage(
                session=db,
                espacio_id=1,
                fecha_inicio=d_ini,
                fecha_fin=d_fin,
                alcance=alcance,
                regimen_horario=regimen_horario,
                direccion=direccion,
                dias_semana=dias_semana,
                door=door,
                perfil_visita=perfil_visita,
                marcajes=marcajes,
                sala=sala,
                carrera=carrera,
                facultad=facultad,
            )
            component = "DoorUsagePlotlyChart"
            payload = data
            top_door = max(data, key=lambda x: x.get("total", 0)) if data else {}
            tot_doors = sum(x.get("total", 0) for x in (data or []))
            top_pct = ((top_door.get("total", 0) / tot_doors) * 100) if tot_doors else 0
            nombre_puerta = top_door.get("puerta", top_door.get("door", "N/D"))
            resumen_metricas = (
                f"Gráfico enfocado: Uso de Torniquetes y Accesos Universales (Biblioteca CSF).\n"
                f"- Desglose físico de infraestructura de hardware (4 canales):\n"
                f"{detalle_hardware_torniquetes}\n"
                f"- Acceso o torniquete más transitado: '{nombre_puerta}' con {top_door.get('total', 0):,} usos "
                f"({top_door.get('entradas', 0):,} entradas, {top_door.get('salidas', 0):,} salidas, {top_pct:.1f}% del volumen total).\n"
                f"- Total de tránsitos registrados: {tot_doors:,} registros en {len(data or [])} accesos físicos.\n"
                f"{contexto_hitos}"
            )
            table_data = data if isinstance(data, list) else None

        # 7. Distribución de Marcajes
        elif any(k in slug for k in ["distribucion_marcajes", "distribucion_de_marcajes", "checkins"]):
            data = await AttendanceService.get_checkin_distribution(
                session=db,
                espacio_id=1,
                fecha_inicio=d_ini,
                fecha_fin=d_fin,
                alcance=alcance,
                regimen_horario=regimen_horario,
                direccion=direccion,
                dias_semana=dias_semana,
                door=door,
                perfil_visita=perfil_visita,
                marcajes=marcajes,
                sala=sala,
                carrera=carrera,
                facultad=facultad,
            )
            component = "CheckinDistributionPlotlyChart"
            payload = data
            tot_p = sum(x.get("total_personas", 0) for x in (data or [])) or 1
            res_items = []
            for item in (data or []):
                pct = (item.get("total_personas", 0) / tot_p) * 100
                res_items.append(f"{item.get('rango_marcajes', item.get('marcajes', 'N/D'))}: {item.get('total_personas', 0):,} personas ({pct:.1f}%)")
            resumen_metricas = (
                f"Gráfico enfocado: Distribución de Marcajes por Registro Diario (Biblioteca CSF).\n"
                f"- Entorno: {sala_desc}.\n"
                f"- Total de personas evaluadas: {tot_p:,}.\n"
                f"- Desglose por número de marcajes: {'; '.join(res_items)}.\n"
                f"{contexto_hitos}"
            )
            table_data = data if isinstance(data, list) else None

        # 8. Promedio de Asistencia por Día de la Semana
        elif any(k in slug for k in ["promedio_dias_semana", "promedio_diario_de_ingresos", "daily_average"]):
            data = await AttendanceService.get_daily_average_attendance(
                session=db,
                espacio_id=1,
                fecha_inicio=d_ini,
                fecha_fin=d_fin,
                alcance=alcance,
                regimen_horario=regimen_horario,
                direccion=direccion,
                dias_semana=dias_semana,
                door=door,
                marcajes=marcajes,
                carrera=carrera,
                facultad=facultad,
            )
            component = "DailyAverageAttendancePlotlyChart"
            payload = data
            if isinstance(data, dict):
                dias_list = data.get("dias", [])
            elif isinstance(data, list):
                dias_list = data
            else:
                dias_list = []
            top_dia = max(dias_list, key=lambda x: x.get("promedio_ingresos", 0) or x.get("total", 0)) if dias_list else {}
            low_dia = min(dias_list, key=lambda x: x.get("promedio_ingresos", 0) or x.get("total", 0)) if dias_list else {}
            resumen_metricas = (
                f"Gráfico enfocado: Promedio Diario de Asistencia por Día de la Semana.\n"
                f"- Configuración: {sala_desc}.\n"
                f"- Día con mayor asistencia promedio: {top_dia.get('dia_semana', 'N/D')} con promedio de {top_dia.get('promedio_ingresos', 0):,.0f} personas/día.\n"
                f"- Día con menor asistencia promedio: {low_dia.get('dia_semana', 'N/D')} con promedio de {low_dia.get('promedio_ingresos', 0):,.0f} personas/día.\n"
                f"{contexto_hitos}"
            )
            table_data = dias_list if dias_list else None

        # 9. Volumen Mensual
        elif any(k in slug for k in ["volumen_mensual", "monthly_volume"]):
            data = await AttendanceService.get_monthly_volume(session=db, espacio_id=1, fecha_inicio=d_ini, fecha_fin=d_fin)
            component = "MonthlyVolumePlotlyChart"
            payload = data
            top_mes = max(data, key=lambda x: x.get("total_ingresos", 0) or x.get("ingresos", 0)) if data else {}
            resumen_metricas = (
                f"Gráfico enfocado: Volumen Mensual de Asistencia.\n"
                f"- Mes de mayor afluencia: {top_mes.get('mes_nombre', top_mes.get('mes', 'N/D'))} con {top_mes.get('total_ingresos', 0):,} ingresos totales y promedio diario de {top_mes.get('promedio_diario', 0):,.0f} personas.\n"
                f"- Total meses comparados: {len(data or [])} meses.\n"
                f"{contexto_hitos}"
            )
            table_data = data if isinstance(data, list) else None

        # 10. Evolución Semanal
        elif any(k in slug for k in ["evolucion_semanal", "weekly_evolution"]):
            data = await AttendanceService.get_weekly_evolution(
                session=db,
                espacio_id=1,
                fecha_inicio=d_ini,
                fecha_fin=d_fin,
                alcance=alcance,
                regimen_horario=regimen_horario,
                direccion=direccion,
                dias_semana=dias_semana,
                door=door,
                perfil_visita=perfil_visita,
                marcajes=marcajes,
                sala=sala,
                carrera=carrera,
                facultad=facultad,
            )
            component = "WeeklyEvolutionPlotlyChart"
            payload = data
            top_sem = max(data, key=lambda x: x.get("total_ingresos", 0) or x.get("usuarios_unicos", 0)) if data else {}
            resumen_metricas = (
                f"Gráfico enfocado: Evolución Semanal de Usuarios (Semanas ISO).\n"
                f"- Configuración: {sala_desc}.\n"
                f"- Semana con mayor afluencia: {top_sem.get('semana_label', top_sem.get('semana', 'N/D'))} con {top_sem.get('total_ingresos', 0):,} accesos y {top_sem.get('usuarios_unicos', 0):,} usuarios únicos.\n"
                f"- Total semanas registradas: {len(data or [])} semanas.\n"
                f"{contexto_hitos}"
            )
            table_data = data[:30] if isinstance(data, list) else None

        # 11. Hitos Académicos / Impacto Calendario
        elif any(k in slug for k in ["hitos_academicos", "impacto_calendario", "academic_milestones"]):
            if espacio_id == 2:
                data = await VehicleService.get_academic_milestones_comparison(db, espacio_id=2)
                component = "VehicleMilestonesPlotlyChart"
            else:
                data = await AttendanceService.get_academic_milestones_comparison(session=db, espacio_id=1)
                component = "AcademicMilestonesPlotlyChart"
            payload = data
            top_hito = max(data, key=lambda x: x.get("promedio_diario", 0) or x.get("total", 0)) if data else {}
            resumen_metricas = (
                f"Gráfico enfocado: Comparativa por Hito del Calendario Académico ({nombre_espacio}).\n"
                f"- Hito con mayor demanda promedio: '{top_hito.get('hito', top_hito.get('categoria', 'N/D'))}' con promedio de {top_hito.get('promedio_diario', 0):,.0f} accesos diarios.\n"
                f"- Períodos evaluados: {', '.join([h.get('hito', h.get('categoria', '')) for h in (data or [])])}.\n"
                f"{contexto_hitos}"
            )
            table_data = data if isinstance(data, list) else None

        # 12. Distribución Curricular
        elif any(k in slug for k in ["distribucion_curricular", "poblacion_academica", "curricular"]):
            data = await AttendanceService.get_curricular_distribution(
                session=db,
                espacio_id=1,
                fecha_inicio=d_ini,
                fecha_fin=d_fin,
                alcance=alcance,
                regimen_horario=regimen_horario,
                direccion=direccion,
                dias_semana=dias_semana,
                door=door,
                perfil_visita=perfil_visita,
                marcajes=marcajes,
                sala=sala,
                carrera=carrera,
                facultad=facultad,
                cohorte=cohorte,
            )
            component = "CurricularDistributionPlotlyChart"
            payload = data
            if isinstance(data, dict):
                carreras = data.get("carreras", [])
            elif isinstance(data, list):
                carreras = data
            else:
                carreras = []
            facultades = data.get("facultades", []) if isinstance(data, dict) else []
            tot_eventos = data.get("total_eventos_asistencia", 0) if isinstance(data, dict) else 0
            tot_asistentes = data.get("total_estudiantes_asistentes", 0) if isinstance(data, dict) else 0
            tot_padron = data.get("total_estudiantes_catalogados", 0) if isinstance(data, dict) else 0

            carreras_ordenadas = sorted(
                carreras,
                key=lambda x: (x.get("eventos_asistencia", 0) or 0, x.get("estudiantes_asistentes", 0) or 0),
                reverse=True
            )
            top5_carreras = [
                f"{c.get('carrera', 'N/D')}: {c.get('eventos_asistencia', 0):,} asistencias ({c.get('estudiantes_asistentes', 0):,} alumnos únicos, {c.get('porcentaje_eventos', 0):.1f}% del total)"
                for c in carreras_ordenadas[:5]
            ]

            facs_ordenadas = sorted(
                facultades,
                key=lambda x: (x.get("eventos_asistencia", 0) or 0),
                reverse=True
            )
            top3_facs = [
                f"{f.get('facultad', 'N/D')}: {f.get('eventos_asistencia', 0):,} asistencias ({f.get('porcentaje_eventos', 0):.1f}%)"
                for f in facs_ordenadas[:3]
            ]

            resumen_metricas = (
                f"Gráfico enfocado: Demografía Institucional y Distribución Curricular (Biblioteca CSF - Ley 21.719).\n"
                f"- Contexto: {sala_desc}.\n"
                f"- {regimen_desc}\n"
                f"- Total de eventos de asistencia registrados en el período: {tot_eventos:,} asistencias.\n"
                f"- Estudiantes asistentes únicos en el período: {tot_asistentes:,} alumnos (de un padrón catalogado de {tot_padron:,} estudiantes).\n"
                f"- Carreras líderes en concurrencia:\n"
                f"  * " + "\n  * ".join(top5_carreras if top5_carreras else ["Sin registros en el rango seleccionado"]) + "\n"
                f"- Facultades principales: {'; '.join(top3_facs) if top3_facs else 'Sin registros'}.\n"
                f"- Total de carreras analizadas: {len(carreras)} carreras universitarias.\n"
                f"{contexto_hitos}"
            )
            table_data = [
                {
                    "carrera": c.get("carrera"),
                    "facultad": c.get("facultad"),
                    "asistencias": c.get("eventos_asistencia", 0),
                    "alumnos_unicos": c.get("estudiantes_asistentes", 0),
                    "padron_total": c.get("total_estudiantes", 0),
                    "porcentaje_eventos": c.get("porcentaje_eventos", 0),
                }
                for c in carreras_ordenadas[:30]
            ] if carreras_ordenadas else None

        # 13. Pronóstico 14 Días GBR
        elif any(k in slug for k in ["pronostico_14d", "proyeccion_de_demanda", "gbr"]):
            data = await get_gbr_forecast_14days(db, espacio_id=1)
            component = "Forecast14DaysPlotlyChart"
            payload = data.get("predicciones", data)
            preds = data.get("predicciones", [])
            max_dia = max(preds, key=lambda x: x.get("aforo_proyectado", 0)) if preds else {}
            sum_14 = sum(x.get("aforo_proyectado", 0) for x in preds)
            avg_14 = (sum_14 / len(preds)) if preds else 0
            resumen_metricas = (
                f"Gráfico enfocado: Proyección de Demanda Futura a 14 Días (HistGradientBoosting + Calendario).\n"
                f"- Día con mayor afluencia proyectada: {max_dia.get('fecha', 'N/D')} ({max_dia.get('dia_semana', '')}) con {max_dia.get('aforo_proyectado', 0):,.0f} usuarios proyectados.\n"
                f"- Demanda media diaria proyectada: {avg_14:,.0f} usuarios/día.\n"
                f"- Horizonte evaluado: 14 días calendario.\n"
                f"{contexto_hitos}"
            )
            table_data = preds if preds else None

        # 14. Perfiles de Visita
        elif any(k in slug for k in ["perfiles_visita", "perfiles_de_visita", "visit_profiles"]):
            data = await AttendanceService.get_visit_profiles_donut(
                session=db,
                espacio_id=1,
                fecha_inicio=d_ini,
                fecha_fin=d_fin,
                alcance=alcance,
                regimen_horario=regimen_horario,
                direccion=direccion,
                dias_semana=dias_semana,
                door=door,
                perfil_visita=perfil_visita,
                marcajes=marcajes,
                sala=sala,
                carrera=carrera,
                facultad=facultad,
            )
            component = "VisitProfilesPlotlyChart"
            payload = data
            if isinstance(data, dict):
                items = data.get("items", [])
            elif isinstance(data, list):
                items = data
            else:
                items = []
            tasa_reb = data.get("tasa_rebote_pct", 0) if isinstance(data, dict) else 0
            tot_vis = data.get("total_visitas_analizadas", 0) if isinstance(data, dict) else sum(x.get("total", 0) for x in items)
            lista_items = [
                f"{it.get('perfil', 'N/D')}: {it.get('porcentaje', 0)}%, prom: {it.get('promedio_min', 0)} min"
                for it in items
            ]
            resumen_metricas = (
                f"Gráfico enfocado: Perfiles de Visita y Tasa de Rebote (Cálculo Determinista Base de Datos).\n"
                f"- Configuración: {sala_desc}.\n"
                f"- Tasa de rebote (< 15 minutos): {tasa_reb:.1f}%.\n"
                f"- Total de visitas analizadas con entrada y salida: {tot_vis:,}.\n"
                f"- Distribución: {'; '.join(lista_items)}.\n"
                f"{contexto_hitos}"
            )
            table_data = items if items else None

        # 15. Composición de Flota
        elif any(k in slug for k in ["composicion_flota", "composicion_de_la_flota", "fleet_composition"]):
            data = await VehicleService.get_fleet_composition(db, espacio_id=2, fecha_inicio=d_ini, fecha_fin=d_fin, sector=sector)
            component = "FleetDonutChart"
            payload = data.get("por_tipo", data)
            tipos = data.get("por_tipo", [])
            top_t = max(tipos, key=lambda x: x.get("total", 0)) if tipos else {}
            tot_v = sum(x.get("total", 0) for x in tipos)
            top_pct = (top_t.get("total", 0) / tot_v * 100) if tot_v else 0
            resumen_metricas = (
                f"Gráfico enfocado: Composición de la Flota Vehicular ({nombre_espacio}).\n"
                f"- Tipo de vehículo predominante: '{top_t.get('tipo', 'N/D')}' con {top_t.get('total', 0):,} vehículos ({top_pct:.1f}% de la flota).\n"
                f"- Parque vehicular total analizado: {tot_v:,} vehículos.\n"
                f"{contexto_hitos}"
            )
            table_data = tipos if tipos else None

        # 16. Top Marcas
        elif any(k in slug for k in ["top_marcas", "top_marcas_de_vehiculos"]):
            data = await VehicleService.get_fleet_composition(db, espacio_id=2, fecha_inicio=d_ini, fecha_fin=d_fin, sector=sector)
            component = "FleetDonutChart"
            payload = data.get("por_marca", data)
            marcas = data.get("por_marca", [])
            top_m = max(marcas, key=lambda x: x.get("total", 0)) if marcas else {}
            lista_marcas = [f"{m.get('marca', 'N/D')} ({m.get('total', 0)})" for m in marcas[:5]]
            resumen_metricas = (
                f"Gráfico enfocado: Top Marcas de Vehículos ({nombre_espacio}).\n"
                f"- Marca más frecuente: '{top_m.get('marca', 'N/D')}' con {top_m.get('total', 0):,} vehículos registrados.\n"
                f"- Marcas líderes: {', '.join(lista_marcas)}.\n"
                f"{contexto_hitos}"
            )
            table_data = marcas[:20] if marcas else None

        # 17. Cámaras ANPR
        elif any(k in slug for k in ["camaras_anpr", "distribucion_de_capturas", "camaras"]):
            data = await VehicleService.get_camera_stats(
                session=db,
                espacio_id=2,
                fecha_inicio=d_ini,
                fecha_fin=d_fin,
                alcance=alcance,
                regimen_horario=regimen_horario,
                direccion=direccion,
                dias_semana=dias_semana,
                door=door,
                sector=sector,
                tipo_vehiculo=tipo_vehiculo,
            )
            component = "CameraStatsPlotlyChart"
            payload = data
            top_cam = max(data, key=lambda x: x.get("entradas", 0) + x.get("salidas", 0)) if data else {}
            tot_in = sum(x.get("entradas", 0) for x in (data or []))
            tot_out = sum(x.get("salidas", 0) for x in (data or []))
            resumen_metricas = (
                f"Gráfico enfocado: Distribución de Capturas por Cámara ANPR ({nombre_espacio}).\n"
                f"- Cámara con mayor volumen: '{top_cam.get('camara', 'N/D')}' con {top_cam.get('entradas', 0):,} entradas y {top_cam.get('salidas', 0):,} salidas.\n"
                f"- Total de pasadas capturadas por ANPR: {tot_in + tot_out:,} lecturas.\n"
                f"{contexto_hitos}"
            )
            table_data = data if isinstance(data, list) else None

        # 18. Movilidad Intercampus
        elif any(k in slug for k in ["movilidad_intercampus", "flujo_de_movilidad", "intercampus"]):
            data = await VehicleService.get_intercampus_mobility(db)
            component = "IntercampusMobilityPlotlyChart"
            payload = data
            tot_viajes = data.get("total_traslados", 0) or data.get("total_viajes", 0)
            resumen_metricas = (
                f"Gráfico enfocado: Flujo de Movilidad Inter-Campus (CSF ↔ San Juan Pablo II).\n"
                f"- Total de traslados detectados entre campus: {tot_viajes:,} viajes vehiculares.\n"
                f"- Sentido CSF → CHS: {data.get('csf_a_chs', 0):,} traslados.\n"
                f"- Sentido CHS → CSF: {data.get('chs_a_csf', 0):,} traslados.\n"
                f"{contexto_hitos}"
            )
            table_data = [data] if isinstance(data, dict) else None

        # 19. Evolución Diaria Vehicular
        elif any(k in slug for k in ["evolucion_diaria", "evolucion_diaria_de_accesos"]):
            data = await VehicleService.get_daily_evolution(db, espacio_id=2, fecha_inicio=d_ini, fecha_fin=d_fin)
            component = "VehicleDailyPlotlyChart"
            payload = data
            top_d = max(data, key=lambda x: x.get("entradas", 0) or x.get("total", 0)) if data else {}
            tot_e = sum(x.get("entradas", 0) for x in (data or []))
            resumen_metricas = (
                f"Gráfico enfocado: Evolución Diaria de Accesos Vehiculares (Plotly).\n"
                f"- Día con mayor afluencia vehicular: {top_d.get('fecha', 'N/D')} con {top_d.get('entradas', 0):,} accesos.\n"
                f"- Total acumulado en la serie: {tot_e:,} entradas.\n"
                f"{contexto_hitos}"
            )
            table_data = data[:30] if isinstance(data, list) else None

        # 20. K-Means Clusters
        elif any(k in slug for k in ["kmeans", "clusters", "conductuales"]):
            data = await VehicleService.get_behavioral_clusters(db)
            component = "VehicleBehavioralClustersPlotlyChart"
            payload = data
            ext_c = data.get("vehiculos_externos_count", 0)
            ext_pct = data.get("vehiculos_externos_pct", 0)
            tot_v = data.get("total_vehiculos_analizados", 0)
            resumen_metricas = (
                f"Gráfico enfocado: Segmentación y Clústeres de Comportamiento K-Means ({nombre_espacio}).\n"
                f"- Universo total analizado: {tot_v:,} vehículos/patentes.\n"
                f"- Posible uso externo detectado: {ext_c:,} vehículos ({ext_pct:.1f}% de la muestra).\n"
                f"- Clústeres identificados: {', '.join([c.get('perfil', '') for c in data.get('distribucion', [])])}.\n"
                f"{contexto_hitos}"
            )
            table_data = data.get("distribucion", []) if isinstance(data, dict) else None

        # 21. Campaña 24 Horas & Análisis de Justificación Operativa
        elif any(k in slug for k in ["campana_24h", "analisis_24h", "flujo_nocturno", "justificacion_24h", "nocturno", "pecera_24h"]):
            data = await AttendanceService.get_analisis_24h(
                session=db,
                espacio_id=1,
                fecha_inicio=d_ini,
                fecha_fin=d_fin,
                bloque_horario="nocturno" if regimen_horario == "24h_delta" else "todos"
            )
            component = "Campaign24hPlotlyChart"
            payload = data
            kpis = data.get("kpis_comparativa", {}) if isinstance(data, dict) else {}
            pico = data.get("pico_nocturno", {}) if isinstance(data, dict) else {}
            top_carr = data.get("top_carreras", []) if isinstance(data, dict) else []
            carr_prin = top_carr[0] if top_carr else {}
            pct_delta = kpis.get("porcentaje_delta_24h", 0)
            ing_noct = kpis.get("ingresos_nocturnos", 0)
            tot_ing = kpis.get("total_ingresos", 0)
            horas_noct = kpis.get("horas_estudio_nocturnas", 0)
            est_noct = kpis.get("estudiantes_nocturnos_unicos", 0)
            resumen_metricas = (
                f"Gráfico enfocado: Campaña 24 Horas & Análisis de Justificación Operativa (Sala 2 CSF04 Pecera: {CAP_SALA_2_NOCTURNA} Asientos calibrados).\n"
                f"- Evaluación de demanda nocturna (L-J 23:00 a 07:00 h | Vie 22:00 a 06:00 h) durante régimen de exámenes.\n"
                f"- Aporte Nocturno (Delta 24h): {pct_delta:.2f}% ({ing_noct:,} de {tot_ing:,} accesos totales).\n"
                f"- Concurrencia Máxima Simultánea: {pico.get('aforo_maximo', 0)} alumnos ({pico.get('tasa_ocupacion_asientos_pct', 0):.1f}% sobre 226 asientos, hora pico: {pico.get('hora_pico', 'N/D')}).\n"
                f"- Horas de Estudio Nocturnas: {horas_noct:,.0f} hrs ({est_noct:,} estudiantes únicos con permanencia nocturna).\n"
                f"- Segmentación Curricular Clave: {carr_prin.get('carrera', 'N/D')} ({carr_prin.get('porcentaje', 0):.1f}% del uso nocturno, {carr_prin.get('visitas', 0):,} visitas).\n"
                f"- Puntos de Control Físico Pecera:\n"
                f"  * Torniquete Principal Pecera: Canal 2592/2587 (CSF04_110 IN 01 / OUT)\n"
                f"  * Acceso Universal Prioritario Pecera: Canal 3411/3416 (CSF04_110 IN 02_Door_1 / OUT 02_Door_1)\n"
                f"{contexto_hitos}"
            )
            table_data = top_carr[:15] if top_carr else None

        else:
            # Fallback determinista general por si el nombre no coincide exactamente
            component, payload, fig_data, table_data = await ejecutar_consulta_tool(
                "consultar_aforo_historico", {"espacio_id": espacio_id}, db, espacio_id
            )
            resumen_metricas = f"Gráfico enfocado: {slug}. Se han cargado los registros históricos correspondientes al espacio {nombre_espacio}."

    except Exception as exc:
        logger.error(f"Error resolviendo datos del gráfico de contexto '{slug}': {exc}", exc_info=True)
        component = "RawDataTable"
        payload = []
        resumen_metricas = f"No se pudieron cargar las métricas en tiempo real para el gráfico '{slug}' debido a: {str(exc)}."

    return component, payload, resumen_metricas, fig_data, table_data


async def resolver_datos_grafico_contexto(
    grafico_id: str,
    espacio_id: int,
    fecha_inicio: Optional[str],
    fecha_fin: Optional[str],
    db: AsyncSession,
    filtros: Optional[Dict[str, Any]] = None,
) -> tuple[Optional[str], Any, str, Optional[Dict[str, Any]], Optional[List[Dict[str, Any]]]]:
    clave_cache = f"grafico:{grafico_id}:{espacio_id}:{fecha_inicio}:{fecha_fin}:{json.dumps(filtros or {}, sort_keys=True, default=str)}"
    if clave_cache in _cache_resultados_herramientas:
        return _cache_resultados_herramientas[clave_cache]
    resultado = await _resolver_datos_grafico_contexto_interno(grafico_id, espacio_id, fecha_inicio, fecha_fin, db, filtros)
    _cache_resultados_herramientas[clave_cache] = resultado
    return resultado



async def _ejecutar_consulta_tool_interno(tool_name: str, args: dict, db: AsyncSession, espacio_id: int, req: Optional[ChatRequest] = None):
    """
    Ejecuta la consulta analítica correspondiente al Tool Calling libre de Gemini.
    Retorna: (componente_react, datos_crudos, resumen_metricas, fig_data_fallback, table_data_fallback)
    """
    from datetime import date
    espacio = args.get("espacio_id", espacio_id) or espacio_id
    f_ini = args.get("fecha_inicio") or (req.fecha_inicio if req else None)
    f_fin = args.get("fecha_fin") or (req.fecha_fin if req else None)
    prompt_txt = req.prompt if req else ""
    anio_activo = await obtener_anio_activo_espacio(db, espacio)
    d_ini, d_fin = extraer_o_normalizar_fechas(f_ini, f_fin, prompt_txt, anio_defecto=anio_activo)

    HERRAMIENTAS_BIBLIOTECA = {
        "consultar_distribucion_carreras",
        "consultar_torniquetes_accesos",
        "consultar_comparativa_salas",
        "consultar_perfiles_visita",
        "consultar_pronostico_14d",
    }
    HERRAMIENTAS_ESTACIONAMIENTO = {
        "consultar_flota_vehicular",
        "consultar_camaras_anpr",
        "consultar_movilidad_intercampus",
        "consultar_clustering_vehicular",
    }
    if espacio == 1 and tool_name in HERRAMIENTAS_ESTACIONAMIENTO:
        return None, None, "Acceso denegado: herramienta vehicular no permitida en módulo Biblioteca CSF.", None, None
    if espacio == 2 and tool_name in HERRAMIENTAS_BIBLIOTECA:
        return None, None, "Acceso denegado: herramienta de biblioteca no permitida en módulo Estacionamiento CSF.", None, None

    if tool_name == "consultar_mapa_calor":
        if espacio == 2:
            data = await VehicleService.get_heatmap(db, espacio_id=2)
        else:
            data = await AttendanceService.get_heatmap(db, espacio_id=1)
        top_spot = max(data, key=lambda x: x.get("ocupacion_promedio", 0) or x.get("aforo", 0)) if data else {}
        res_m = f"Matriz de concurrencia: mayor afluencia detectada el día {top_spot.get('dia_semana', 'N/D')} a las {top_spot.get('hora', 'N/D')} hrs."
        return "HeatmapChart", data, res_m, None, data[:35] if isinstance(data, list) else None

    elif tool_name == "consultar_picos_flujo":
        if espacio == 2:
            data = await VehicleService.get_hourly_flow(session=db, espacio_id=2, fecha_inicio=d_ini, fecha_fin=d_fin)
            res_m = "Flujo vehicular horario y análisis de ocupación en Estacionamiento CSF."
            return "HourlyBarChart", data, res_m, None, data[:40] if isinstance(data, list) else None
        else:
            data = await AttendanceService.get_peak_valley_bands(db, espacio_id=1, fecha_inicio=d_ini, fecha_fin=d_fin)
            res_m = "Franjas de afluencia máxima (picos) y menor concurrencia (valles) en Biblioteca CSF."
            return "PeakValleyPlotlyChart", data, res_m, None, data[:40] if isinstance(data, list) else None

    elif tool_name == "consultar_proyeccion_prophet":
        data = await get_prophet_forecast(db, recinto="vehicular" if espacio == 2 else "biblioteca")
        pron = data.get("pronostico_7d") or data.get("forecast") or []
        res_m = f"Proyección analítica con modelo Prophet calculada para los próximos 7 días ({len(pron)} puntos de pronóstico)."
        return "ForecastLineChart", data, res_m, None, pron[:40] if pron else None

    elif tool_name == "consultar_kpis_actuales":
        if espacio == 2:
            data = await VehicleService.get_parking_occupancy(db, espacio_id=2)
        else:
            data = await AttendanceService.get_occupancy_realtime(db, espacio_id=1)
        res_m = f"Métricas instantáneas actuales: {json.dumps(data, default=str)}."
        return "RawDataTable", data, res_m, None, [data] if isinstance(data, dict) else data

    elif tool_name == "consultar_distribucion_carreras":
        c, p, res_m, f, t = await resolver_datos_grafico_contexto("distribucion_curricular", espacio, str(d_ini) if d_ini else None, str(d_fin) if d_fin else None, db, req.filtros if req else None)
        return c, p, res_m, f, t

    elif tool_name == "consultar_torniquetes_accesos":
        c, p, res_m, f, t = await resolver_datos_grafico_contexto("torniquetes", espacio, str(d_ini) if d_ini else None, str(d_fin) if d_fin else None, db, req.filtros if req else None)
        return c, p, res_m, f, t

    elif tool_name == "consultar_comparativa_salas":
        c, p, res_m, f, t = await resolver_datos_grafico_contexto("comparativa_salas", espacio, str(d_ini) if d_ini else None, str(d_fin) if d_fin else None, db, req.filtros if req else None)
        return c, p, res_m, f, t

    elif tool_name == "consultar_flota_vehicular":
        c, p, res_m, f, t = await resolver_datos_grafico_contexto("composicion_flota", espacio, str(d_ini) if d_ini else None, str(d_fin) if d_fin else None, db, req.filtros if req else None)
        return c, p, res_m, f, t

    elif tool_name == "consultar_camaras_anpr":
        c, p, res_m, f, t = await resolver_datos_grafico_contexto("camaras_anpr", espacio, str(d_ini) if d_ini else None, str(d_fin) if d_fin else None, db, req.filtros if req else None)
        return c, p, res_m, f, t

    elif tool_name == "consultar_movilidad_intercampus":
        c, p, res_m, f, t = await resolver_datos_grafico_contexto("movilidad_intercampus", espacio, str(d_ini) if d_ini else None, str(d_fin) if d_fin else None, db, req.filtros if req else None)
        return c, p, res_m, f, t

    elif tool_name == "consultar_perfiles_visita":
        c, p, res_m, f, t = await resolver_datos_grafico_contexto("perfiles_visita", espacio, str(d_ini) if d_ini else None, str(d_fin) if d_fin else None, db, req.filtros if req else None)
        return c, p, res_m, f, t

    elif tool_name == "consultar_pronostico_14d":
        c, p, res_m, f, t = await resolver_datos_grafico_contexto("pronostico_14d", espacio, str(d_ini) if d_ini else None, str(d_fin) if d_fin else None, db, req.filtros if req else None)
        return c, p, res_m, f, t

    elif tool_name in ["consultar_campana_24h", "consultar_flujo_nocturno"]:
        c, p, res_m, f, t = await resolver_datos_grafico_contexto("campana_24h", espacio, str(d_ini) if d_ini else None, str(d_fin) if d_fin else None, db, req.filtros if req else None)
        return c, p, res_m, f, t

    elif tool_name == "consultar_calendario_academico":
        semana_arg = args.get("semana")
        mes_arg = args.get("mes")
        busqueda_arg = args.get("busqueda", "")
        if not semana_arg:
            m_sem = re.search(r'\b(?:semana|sem|w)\s*0?([1-9]|[1-4][0-9]|5[0-3])\b', prompt_txt.lower())
            if m_sem:
                semana_arg = int(m_sem.group(1))

        if semana_arg and (not d_ini or not d_fin):
            d_ini = date.fromisocalendar(anio_activo, int(semana_arg), 1)
            d_fin = date.fromisocalendar(anio_activo, int(semana_arg), 7)
        elif mes_arg and (not d_ini or not d_fin):
            m_num = int(mes_arg)
            d_ini = date(anio_activo, m_num, 1)
            ultimo_d = 31 if m_num in [1, 3, 5, 7, 8, 10, 12] else (28 if m_num == 2 else 30)
            d_fin = date(anio_activo, m_num, ultimo_d)

        if not d_ini or not d_fin:
            d_ini = date(anio_activo, 1, 1)
            d_fin = date(anio_activo, 12, 31)

        query_cal = select(CalendarioAcademico).where(
            CalendarioAcademico.fecha >= d_ini,
            CalendarioAcademico.fecha <= d_fin
        ).order_by(CalendarioAcademico.fecha.asc())

        if busqueda_arg:
            query_cal = query_cal.where(CalendarioAcademico.descripcion.ilike(f"%{busqueda_arg.strip()}%"))

        filas_cal = (await db.execute(query_cal)).scalars().all()

        if espacio == 2:
            datos_flujo = await VehicleService.get_daily_summary(session=db, espacio_id=2, fecha_inicio=d_ini, fecha_fin=d_fin)
        else:
            datos_flujo = await AttendanceService.get_daily_summary(session=db, espacio_id=1, fecha_inicio=d_ini, fecha_fin=d_fin)

        tot_asistencias = sum(int(f.get("ingresos", 0) or 0) for f in (datos_flujo or []))
        usuarios_unicos = sum(int(f.get("personas_unicas", 0) or 0) for f in (datos_flujo or []))

        hitos_detalle = []
        es_receso = False
        es_feriado = False
        es_suspension = False
        es_examenes = False
        es_paro = False

        for c_row in filas_cal:
            etiquetas = []
            if c_row.is_break:
                etiquetas.append("SEMANA DE RECESO")
                es_receso = True
            if c_row.is_holiday:
                etiquetas.append("FERIADO OFICIAL")
                es_feriado = True
            if c_row.suspension_actividades:
                etiquetas.append("SUSPENSIÓN DE ACTIVIDADES")
                es_suspension = True
            if c_row.is_exam_period:
                etiquetas.append("PERÍODO DE EXÁMENES")
                es_examenes = True
            if c_row.is_strike_federado or c_row.is_strike_carrera:
                etiquetas.append("PARO")
                es_paro = True
            if getattr(c_row, "is_class_milestone", False):
                etiquetas.append("HITO DE CLASES")

            etq_str = f" [{', '.join(etiquetas)}]" if etiquetas else ""
            desc = c_row.descripcion.strip() if c_row.descripcion else "Sin descripción específica"
            hitos_detalle.append(f"- {c_row.fecha.strftime('%d/%m/%Y (%A)')}: {desc}{etq_str}")

        tipo_periodo = "Período Regular de Clases Lectivas"
        if es_receso:
            tipo_periodo = "SEMANA DE RECESO ESTUDIANTIL"
        elif es_feriado and es_suspension:
            tipo_periodo = "FERIADO CON SUSPENSIÓN DE ACTIVIDADES"
        elif es_examenes:
            tipo_periodo = "PERÍODO DE EXÁMENES Y EVALUACIONES"
        elif es_paro:
            tipo_periodo = "CONTINGENCIA / PARO ESTUDIANTIL"

        nombre_recinto = "Estacionamiento CSF" if espacio == 2 else "Biblioteca CSF"
        resumen_lineas = [
            f"REPORTE OFICIAL DEL CALENDARIO ACADÉMICO UCT (AÑO {anio_activo}):",
            f"Período evaluado: {d_ini.strftime('%d/%m/%Y')} al {d_fin.strftime('%d/%m/%Y')}" + (f" (Semana {semana_arg})" if semana_arg else "") + ".",
            f"Clasificación oficial institucional: {tipo_periodo}.",
            f"Hitos programados en el Calendario Académico ({len(filas_cal)} registros encontrados):",
        ]
        if hitos_detalle:
            resumen_lineas.extend(hitos_detalle)
        else:
            resumen_lineas.append("- Período regular de clases lectivas; no hubo feriados, recesos ni suspensiones programadas.")

        resumen_lineas.append(f"\nIMPACTO EN LA CONCURRENCIA REGISTRADA ({nombre_recinto.upper()}):")
        resumen_lineas.append(f"- Total acumulado en este período: {tot_asistencias:,} {'asistencias peatonales' if espacio == 1 else 'entradas vehiculares'}.")
        if espacio == 1:
            resumen_lineas.append(f"- Usuarios únicos registrados: {usuarios_unicos:,} personas.")
        resumen_lineas.append(f"- Explicación causal de asistencia: La afluencia observada responde directamente a la programación de {tipo_periodo}.")

        resumen_hechos_8 = await obtener_resumen_hechos_institucionales(db, d_ini, d_fin, espacio_id=espacio)
        resumen_lineas.append(f"\n{resumen_hechos_8}")

        res_m = "\n".join(resumen_lineas)

        if espacio == 2:
            comp_hitos = await VehicleService.get_academic_milestones_comparison(db, espacio_id=2)
        else:
            comp_hitos = await AttendanceService.get_academic_milestones_comparison(db, espacio_id=1)

        if not comp_hitos:
            comp_hitos = [
                {
                    "hito": tipo_periodo,
                    "promedio_diario": round(tot_asistencias / max(1, len(filas_cal)), 1),
                    "max_dia": tot_asistencias,
                    "dias_totales": len(filas_cal),
                    "total_asistencias": tot_asistencias,
                }
            ]

        detalle_tabla = []
        mapa_flujo = {str(f.get("fecha", ""))[:10]: f for f in (datos_flujo or [])}
        for r in filas_cal:
            f_iso = r.fecha.isoformat()
            flujo_dia = mapa_flujo.get(f_iso, {})
            detalle_tabla.append({
                "fecha": r.fecha.strftime("%d/%m/%Y"),
                "dia": r.fecha.strftime("%A"),
                "evento_calendario": r.descripcion or "Sin descripción",
                "tipo": "Receso" if r.is_break else ("Feriado" if r.is_holiday else ("Examen" if r.is_exam_period else "Regular")),
                "asistencias": flujo_dia.get("ingresos", 0) or flujo_dia.get("entradas", 0) or 0,
            })

        return "AcademicMilestonesPlotlyChart", comp_hitos, res_m, None, detalle_tabla

    elif tool_name == "consultar_clustering_vehicular":
        c, p, res_m, f, t = await resolver_datos_grafico_contexto("kmeans_clusters", espacio, str(d_ini) if d_ini else None, str(d_fin) if d_fin else None, db, req.filtros if req else None)
        return c, p, res_m, f, t

    else:
        # Enrutamiento inteligente según granularidad: semanal, mensual o diario
        es_semanal = (tool_name == "consultar_evolucion_semanal") or (args.get("intervalo") == "semanal") or any(k in prompt_txt.lower() for k in ["semana", "semanal", "semanas"])
        es_mensual = (tool_name == "consultar_volumen_mensual") or (args.get("intervalo") == "mensual") or any(k in prompt_txt.lower() for k in ["mensual", "por mes", "meses"])

        if es_semanal and espacio == 1:
            data_semanal = await AttendanceService.get_weekly_evolution(
                session=db, espacio_id=1, fecha_inicio=d_ini, fecha_fin=d_fin
            )
            hitos_cal = await obtener_contexto_calendario_rango(db, d_ini, d_fin)
            tot_asist = sum(w.get("total_asistencias", 0) for w in data_semanal)
            prom_semanal = round(tot_asist / len(data_semanal), 1) if data_semanal else 0
            desglose_semanas = [
                f"- {w['semana_iso']} (inicio {w.get('inicio_semana', 'N/D')}): {w.get('total_asistencias', 0):,} asistencias ({w.get('usuarios_unicos', 0):,} usuarios únicos)"
                for w in data_semanal
            ]
            res_m = (
                f"MÉTRICAS OFICIALES POR SEMANA (BIBLIOTECA CSF - AÑO ACADÉMICO 2026):\n"
                f"Rango evaluado: {d_ini or 'Inicio'} al {d_fin or 'Actual'}.\n"
                f"Total de semanas analizadas: {len(data_semanal)} semanas ISO.\n"
                f"Total de asistencias acumuladas: {tot_asist:,} asistencias.\n"
                f"Promedio semanal de afluencia: {prom_semanal:,} usuarios/semana.\n"
                f"Desglose por semana ISO:\n"
                f"{chr(10).join(desglose_semanas)}\n"
                f"Hitos relevantes del Calendario Académico UCT:\n"
                f"{chr(10).join(hitos_cal) if hitos_cal else 'Semanas regulares lectivas.'}"
            )
            return "WeeklyEvolutionPlotlyChart", data_semanal, res_m, None, data_semanal

        elif es_mensual and espacio == 1:
            data_mensual = await AttendanceService.get_monthly_volume(
                session=db, espacio_id=1, fecha_inicio=d_ini, fecha_fin=d_fin
            )
            hitos_cal = await obtener_contexto_calendario_rango(db, d_ini, d_fin)
            tot_asist = sum(m.get("total_asistencias", 0) for m in data_mensual)
            prom_mes = round(tot_asist / len(data_mensual), 1) if data_mensual else 0
            desglose_meses = [
                f"- Mes {m['mes']}: {m.get('total_asistencias', 0):,} asistencias ({m.get('dias_activos', 0)} días activos, prom diario {m.get('promedio_diario', 0)})"
                for m in data_mensual
            ]
            res_m = (
                f"MÉTRICAS OFICIALES POR MES (BIBLIOTECA CSF - AÑO ACADÉMICO 2026):\n"
                f"Rango evaluado: {d_ini or 'Inicio'} al {d_fin or 'Actual'}.\n"
                f"Total asistencias en el período: {tot_asist:,}.\n"
                f"Promedio mensual: {prom_mes:,}.\n"
                f"Desglose mensual:\n"
                f"{chr(10).join(desglose_meses)}\n"
                f"Hitos de Calendario Académico UCT:\n"
                f"{chr(10).join(hitos_cal) if hitos_cal else 'Meses regulares de docencia.'}"
            )
            return "MonthlyVolumePlotlyChart", data_mensual, res_m, None, data_mensual

        # Flujo diario general
        if espacio == 2:
            raw_rows = await VehicleService.get_daily_summary(session=db, espacio_id=2, fecha_inicio=d_ini, fecha_fin=d_fin)
        else:
            raw_rows = await AttendanceService.get_daily_summary(session=db, espacio_id=1, fecha_inicio=d_ini, fecha_fin=d_fin)

        hitos_cal = await obtener_contexto_calendario_rango(db, d_ini, d_fin)
        nombre_recinto = "Estacionamiento CSF" if espacio == 2 else "Biblioteca CSF"

        if not raw_rows:
            res_m = (
                f"NO HAY REGISTROS: Para las fechas consultadas ({d_ini or 'inicio'} al {d_fin or 'fin'}) "
                f"no existen eventos registrados en la base de datos institucional para {nombre_recinto}.\n"
                f"Hitos de calendario académico en ese período: {'; '.join(hitos_cal) if hitos_cal else 'Sin hitos registrados'}."
            )
            return "OccupancyAreaChart", [], res_m, None, []

        rows = []
        desglose_lineas = []
        tot_in = 0
        max_item = None
        min_item = None
        dias_es = {
            "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
            "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"
        }

        for r in raw_rows:
            f_iso = r["fecha"].isoformat() if hasattr(r["fecha"], "isoformat") else str(r["fecha"])
            f_str = r["fecha"].strftime("%d/%m/%Y") if hasattr(r["fecha"], "strftime") else str(r["fecha"])
            dia_raw = r.get("dia_semana", "")
            dia_nom = dias_es.get(dia_raw, dia_raw)
            ing = int(r.get("ingresos", 0) or 0)
            sal = int(r.get("salidas", 0) or 0)
            per = int(r.get("personas_unicas", 0) or ing)
            tot_in += ing

            item = {
                "bucket": f_iso,
                "fecha": f_iso,
                "dia_semana": dia_nom,
                "ingresos": ing,
                "entradas": ing,
                "salidas": sal,
                "personas_unicas": per,
            }
            rows.append(item)
            desglose_lineas.append(f"- {dia_nom} {f_str}: {ing:,} {'usuarios' if espacio == 1 else 'vehículos'} (Salidas: {sal:,})")
            if max_item is None or ing > max_item["ing"]:
                max_item = {"dia": dia_nom, "fecha": f_str, "ing": ing}
            if min_item is None or ing < min_item["ing"]:
                min_item = {"dia": dia_nom, "fecha": f_str, "ing": ing}

        prom_diario = round(tot_in / len(rows), 1) if rows else 0
        hitos_texto = "\n".join(hitos_cal) if hitos_cal else "Días hábiles regulares del calendario académico institucional."

        res_m = (
            f"MÉTRICAS OFICIALES CALCULADAS DESDE LA BASE DE DATOS INSTITUCIONAL (AÑO ACADÉMICO 2026):\n"
            f"Recinto: {nombre_recinto} (espacio_id={espacio}).\n"
            f"Rango evaluado: {d_ini or 'Inicio'} al {d_fin or 'Actual'}.\n"
            f"Desglose por día registrado:\n"
            f"{chr(10).join(desglose_lineas)}\n"
            f"Resumen del período:\n"
            f"- Total acumulado: {tot_in:,} {'asistencias/ingresos' if espacio == 1 else 'entradas vehiculares'}.\n"
            f"- Promedio diario: {prom_diario:,} por día con actividad registrada.\n"
            f"- Día de máxima afluencia: {max_item['dia']} {max_item['fecha']} con {max_item['ing']:,} registros.\n"
            f"- Día de menor afluencia: {min_item['dia']} {min_item['fecha']} con {min_item['ing']:,} registros.\n"
            f"Contexto del Calendario Académico UCT:\n"
            f"{hitos_texto}"
        )
        return "OccupancyAreaChart", rows, res_m, None, rows


async def ejecutar_consulta_tool(tool_name: str, args: dict, db: AsyncSession, espacio_id: int, req: Optional[ChatRequest] = None):
    f_ini = args.get("fecha_inicio") or (req.fecha_inicio if req else None)
    f_fin = args.get("fecha_fin") or (req.fecha_fin if req else None)
    clave_cache = f"tool:{tool_name}:{espacio_id}:{json.dumps(args, sort_keys=True, default=str)}:{f_ini}:{f_fin}"
    if clave_cache in _cache_resultados_herramientas:
        return _cache_resultados_herramientas[clave_cache]
    resultado = await _ejecutar_consulta_tool_interno(tool_name, args, db, espacio_id, req)
    _cache_resultados_herramientas[clave_cache] = resultado
    return resultado



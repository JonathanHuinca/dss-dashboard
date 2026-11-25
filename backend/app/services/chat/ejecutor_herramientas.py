from sqlalchemy import select
from app.domain.models import CalendarioAcademico
import json
import logging
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from cachetools import TTLCache
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.chat_schemas import ChatRequest
from app.services.attendance_service import AttendanceService, obtener_capacidades_salas_cacheadas
from app.services.calendar_service import CalendarService, TIPOS_INCIDENCIA_OPERATIVA
from app.services.vehicle_service import VehicleService
from app.services.prediction_service import get_prophet_forecast, get_prophet_presence_forecast, get_gbr_forecast_14days, get_visit_profiles
from app.services.chat.fechas_chat import (
    extraer_o_normalizar_fechas,
    obtener_anio_activo_espacio,
    obtener_contexto_calendario_rango,
    obtener_resumen_hechos_institucionales,
)

logger = logging.getLogger(__name__)

_cache_resultados_herramientas: TTLCache = TTLCache(maxsize=300, ttl=60)
_cache_graficos_contexto: TTLCache = TTLCache(maxsize=300, ttl=60)


def _fmt_fecha_cl(iso_str: Optional[str]) -> str:
    if not iso_str:
        return ""
    try:
        return date.fromisoformat(str(iso_str)[:10]).strftime("%d/%m/%Y")
    except Exception:
        return str(iso_str)


def _fmt_ts_cl(iso_str: Optional[str]) -> str:
    if not iso_str:
        return "N/D"
    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(iso_str)


def _normalizar_sala_objetivo(sala: Optional[str]) -> str:
    if not sala:
        return "todos"
    s = str(sala).strip().lower()
    if "1" in s or "csf02" in s:
        return "sala_1"
    if "2" in s or "csf04" in s or "pecera" in s:
        return "sala_2"
    return "todos"


def _normalizar_sala_prophet_bib(sala: Optional[str]) -> str:
    if not sala:
        return "todas"
    s = str(sala).strip().lower()
    if "1" in s or "csf02" in s:
        return "sala1"
    if "2" in s or "csf04" in s or "pecera" in s:
        return "sala2"
    return "todas"


def _normalizar_sector_prophet_veh(sector: Optional[str]) -> str:
    if not sector:
        return "todos"
    s = str(sector).strip().upper()
    if s in ("CSF11", "CSF21", "CHS01"):
        return s
    return "todos"


def _resumen_desglose_prophet(data: Dict[str, Any], espacio_id: int) -> str:
    if not isinstance(data, dict) or data.get("reconciliacion") != "bottom_up":
        return ""
    pron = data.get("pronostico_7d") or []
    if not pron:
        return ""
    if espacio_id == 2:
        p11 = max((float(pt.get("yhat_csf11") or 0) for pt in pron), default=0.0)
        p21 = max((float(pt.get("yhat_csf21") or 0) for pt in pron), default=0.0)
        p01 = max((float(pt.get("yhat_chs01") or 0) for pt in pron), default=0.0)
        return (
            f"\n- Desglose Bottom-Up por sector (picos proyectados): "
            f"CSF11={p11:.0f} veh | CSF21={p21:.0f} veh | CHS01={p01:.0f} veh."
        )
    ps1 = max((float(pt.get("yhat_sala1") or 0) for pt in pron), default=0.0)
    ps2 = max((float(pt.get("yhat_sala2") or 0) for pt in pron), default=0.0)
    return (
        f"\n- Desglose Bottom-Up por sala (picos proyectados): "
        f"Sala 1={ps1:.0f} pers. | Sala 2={ps2:.0f} pers."
    )


async def _construir_alerta_operativa_biblioteca(
    db: AsyncSession,
    d_ini: Optional[date],
    d_fin: Optional[date],
    sala: Optional[str],
    filtros: Optional[Dict[str, Any]] = None,
    curva_presencia: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Resume días operativos con 0 marcajes, último marcaje por sala e incidencias registradas."""
    f_dict = filtros or {}
    alcance = f_dict.get("alcance") or "conformes"
    regimen_horario = f_dict.get("regimen_horario") or "todos"
    direccion = f_dict.get("direccion") or "todos"
    dias_semana = f_dict.get("dias_semana")
    door = f_dict.get("torniquetes") or f_dict.get("door") or f_dict.get("puerta")
    perfil_visita = f_dict.get("perfil_visita") or "todos"
    marcajes = f_dict.get("marcajes") or "todos"
    carrera = f_dict.get("carrera")
    facultad = f_dict.get("facultad")
    cohorte = f_dict.get("cohorte")
    incluir_pausas_bano = bool(f_dict.get("incluir_pausas_bano", True))
    incluir_funcionarios = bool(f_dict.get("incluir_funcionarios", True))
    incluir_sin_identificar = bool(f_dict.get("incluir_sin_identificar", True))

    try:
        curva = curva_presencia
        if curva is None:
            curva = await AttendanceService.get_realtime_presence_curve(
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
                incluir_pausas_bano=incluir_pausas_bano,
                desduplicar_rafagas=bool(f_dict.get("desduplicar_rafagas", True)),
                incluir_funcionarios=incluir_funcionarios,
                incluir_sin_identificar=incluir_sin_identificar,
            )
    except Exception:
        curva = []

    try:
        vivo = await AttendanceService.get_occupancy_realtime(
            db,
            espacio_id=1,
            sala=sala,
            incluir_funcionarios=incluir_funcionarios,
            incluir_sin_identificar=incluir_sin_identificar,
        )
    except Exception:
        vivo = {}

    ts_global = _fmt_ts_cl(vivo.get("timestamp"))
    ts_s1 = _fmt_ts_cl(vivo.get("ultimo_marcaje_sala1") or (vivo.get("timestamp") if _normalizar_sala_objetivo(sala) == "sala_1" else None))
    ts_s2 = _fmt_ts_cl(vivo.get("ultimo_marcaje_sala2") or (vivo.get("timestamp") if _normalizar_sala_objetivo(sala) == "sala_2" else None))

    por_fecha: Dict[str, Dict[str, bool]] = {}
    for p in (curva or []):
        f_iso = str(p.get("bucket") or "")[:10]
        if not f_iso:
            continue
        st = por_fecha.setdefault(f_iso, {"g": False, "s1": False, "s2": False})
        if p.get("sin_registros"):
            st["g"] = True
        if p.get("sin_registros_sala1"):
            st["s1"] = True
        if p.get("sin_registros_sala2"):
            st["s2"] = True

    if not por_fecha and not vivo:
        return ""

    anio_ref = (d_fin or d_ini or date.today()).year
    cal_map: Dict[str, Dict[str, Any]] = {}
    try:
        cal_res = await CalendarService().obtener_resumen_anual_calendario(db, anio_ref)
        cal_map = {str(d.get("fecha")): d for d in cal_res}
    except Exception:
        cal_map = {}

    def _incs_para(f_iso: str, sub_obj: str) -> List[Dict[str, Any]]:
        cal_d = cal_map.get(f_iso) or {}
        out = []
        for inc in (cal_d.get("incidencias_operativas") or []):
            if (inc.get("tipo") or "").lower() not in TIPOS_INCIDENCIA_OPERATIVA:
                continue
            esp_i = inc.get("espacio_id")
            if esp_i is not None and esp_i != 1:
                continue
            sub_i = (inc.get("subespacio") or "todos").strip().lower()
            if sub_i == "todos" or sub_obj == "todos" or sub_i == sub_obj:
                out.append(inc)
        return out

    def _ctx_cal_txt(f_iso: str) -> Optional[str]:
        cal_d = cal_map.get(f_iso) or {}
        if cal_d.get("is_strike_federado"):
            return "Paro Federado FEUCT"
        if cal_d.get("is_strike_carrera"):
            return "Paro por Carrera"
        if cal_d.get("is_break"):
            return "Vacaciones / Receso académico"
        if cal_d.get("is_holiday"):
            return "Feriado oficial"
        if cal_d.get("suspension_actividades"):
            return "Suspensión institucional"
        return None

    sala_obj = _normalizar_sala_objetivo(sala)
    fechas_ord = sorted(por_fecha.keys())
    lineas: List[str] = ["ESTADO OPERATIVO Y ALERTAS DE MARCAJES (DINÁMICO):"]

    if fechas_ord:
        f_fin_iso = fechas_ord[-1]
        st_fin = por_fecha[f_fin_iso]
        fmt_fin = _fmt_fecha_cl(f_fin_iso)

        def _fmt_motivo(f_iso: str, sub_obj: str) -> str:
            incs = _incs_para(f_iso, sub_obj)
            if incs:
                det = "; ".join(f"{i.get('titulo')} [{i.get('tipo')}]" for i in incs)
                return f"Incidencia operativa registrada: {det}."
            ctx_c = _ctx_cal_txt(f_iso)
            return f"Sin motivo operativo registrado (contexto calendario: {ctx_c})." if ctx_c else "Sin motivo operativo registrado."

        if st_fin["g"]:
            etiq = (
                "Sala 1 (CSF02 2° Piso)" if sala_obj == "sala_1"
                else ("Sala 2 (CSF04 Pecera 1° Piso)" if sala_obj == "sala_2" else "Biblioteca CSF (ambas salas)")
            )
            ts_use = ts_s1 if sala_obj == "sala_1" else (ts_s2 if sala_obj == "sala_2" else ts_global)
            lineas.append(
                f"- ALERTA ÚLTIMO DÍA OPERATIVO ({fmt_fin}): Sin marcajes registrados en {etiq} "
                f"(horario operativo graficado en 0). Último marcaje registrado: {ts_use}. {_fmt_motivo(f_fin_iso, sala_obj)}"
            )
        elif sala_obj == "todos":
            if st_fin["s1"]:
                lineas.append(
                    f"- ALERTA ÚLTIMO DÍA OPERATIVO ({fmt_fin}): Sin marcajes registrados en Sala 1 (CSF02 2° Piso) "
                    f"(horario operativo graficado en 0). Último marcaje registrado: {ts_s1}. {_fmt_motivo(f_fin_iso, 'sala_1')}"
                )
            if st_fin["s2"]:
                lineas.append(
                    f"- ALERTA ÚLTIMO DÍA OPERATIVO ({fmt_fin}): Sin marcajes registrados en Sala 2 (CSF04 Pecera 1° Piso) "
                    f"(horario operativo graficado en 0). Último marcaje registrado: {ts_s2}. {_fmt_motivo(f_fin_iso, 'sala_2')}"
                )

        vacios_sin_motivo: List[str] = []
        for f_iso in sorted(por_fecha.keys(), reverse=True):
            st = por_fecha[f_iso]
            if not (st["g"] or st["s1"] or st["s2"]):
                continue
            if _ctx_cal_txt(f_iso):
                continue
            sub_ev = sala_obj if sala_obj != "todos" else ("todos" if st["g"] else ("sala_1" if st["s1"] else "sala_2"))
            if _incs_para(f_iso, sub_ev):
                continue
            etiq_sub = "Ambas salas" if st["g"] and sala_obj == "todos" else ("Sala 1" if (sala_obj == "sala_1" or st["s1"]) else "Sala 2")
            vacios_sin_motivo.append(f"{_fmt_fecha_cl(f_iso)} ({etiq_sub})")

        if vacios_sin_motivo:
            muestra = ", ".join(vacios_sin_motivo[:6])
            extra = f" (+{len(vacios_sin_motivo) - 6} más)" if len(vacios_sin_motivo) > 6 else ""
            lineas.append(
                f"- Días operativos sin marcajes y sin motivo registrado en el período ({len(vacios_sin_motivo)}): {muestra}{extra}."
            )

    if sala_obj == "todos":
        lineas.append(f"- Últimos marcajes registrados por sala: Sala 1 (CSF02) {ts_s1} | Sala 2 (CSF04 Pecera) {ts_s2}.")
    elif sala_obj == "sala_1":
        lineas.append(f"- Último marcaje registrado Sala 1 (CSF02): {ts_s1}.")
    else:
        lineas.append(f"- Último marcaje registrado Sala 2 (CSF04 Pecera): {ts_s2}.")

    return "\n".join(lineas)

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
    incluir_pausas_bano = bool(filtros.get("incluir_pausas_bano", True))
    desduplicar_rafagas = bool(filtros.get("desduplicar_rafagas", True))
    incluir_funcionarios = bool(filtros.get("incluir_funcionarios", True))
    incluir_sin_identificar = bool(filtros.get("incluir_sin_identificar", True))
    nombre_espacio = "Estacionamiento CSF" if espacio_id == 2 else "Biblioteca CSF"

    # Capacidades reales desde BD (con respaldo determinista para pruebas mock)
    caps_veh = {"CSF11": 40, "CSF21": 50, "CHS01": 35, "total": 125}
    if espacio_id == 1:
        caps = await obtener_capacidades_salas_cacheadas(db, espacio_id=1)
        CAP_SALA_1 = int(caps.get("sala_1") or 150)
        CAP_SALA_2 = int(caps.get("sala_2") or 126)
        CAP_CAMPUS_CALIBRADA = int(caps.get("total") or (CAP_SALA_1 + CAP_SALA_2))
        if sala and ("1" in str(sala) or "csf02" in str(sala).lower()):
            cap_activa = CAP_SALA_1
            sala_desc = f"Sala 1 — CSF02 (2° Piso, Estudio y Biblioteca con Locker: {CAP_SALA_1} asientos)"
        elif sala and ("2" in str(sala) or "csf04" in str(sala).lower() or "pecera" in str(sala).lower()):
            cap_activa = CAP_SALA_2
            sala_desc = f"Sala 2 — CSF04 Pecera (1° Piso, Estudio 24h: {CAP_SALA_2} asientos)"
        else:
            cap_activa = CAP_CAMPUS_CALIBRADA
            sala_desc = f"Campus San Francisco Completo (Sala 1: {CAP_SALA_1} as. + Sala 2: {CAP_SALA_2} as. = {CAP_CAMPUS_CALIBRADA} asientos)"
    else:
        CAP_SALA_1 = 150
        CAP_SALA_2 = 126
        try:
            caps_veh_bd = await VehicleService._obtener_capacidades_sectores_vehiculares(db, 2)
            if isinstance(caps_veh_bd, dict) and caps_veh_bd.get("total"):
                caps_veh = caps_veh_bd
        except Exception:
            pass
        sector_cod = _normalizar_sector_prophet_veh(sector)
        if sector_cod != "todos" and sector_cod in caps_veh:
            cap_activa = int(caps_veh[sector_cod])
            sala_desc = f"Sector {sector_cod} ({cap_activa} plazas)"
        else:
            cap_activa = int(caps_veh.get("total") or 125)
            sala_desc = (
                f"Estacionamiento Campus San Francisco Completo "
                f"(CSF11: {caps_veh.get('CSF11', 40)} + CSF21: {caps_veh.get('CSF21', 50)} + CHS01: {caps_veh.get('CHS01', 35)} = {cap_activa} plazas)"
            )

    reg_tokens = {t.strip().lower() for t in str(regimen_horario or "todos").split(",") if t.strip()}
    if "dentro_horario" in reg_tokens and "24h_delta" in reg_tokens:
        regimen_desc = "Régimen Horario Activo: Horario Oficial Regular + Extensión Nocturna Delta 24h (Sala 2 Pecera)."
    elif "24h_delta" in reg_tokens or "nocturno_24h" in reg_tokens:
        regimen_desc = "Régimen Horario Activo: Turno Nocturno Delta 24h (Sala 2 Pecera)."
    elif "dentro_horario" in reg_tokens or "diurno" in reg_tokens or "regular" in reg_tokens:
        regimen_desc = "Régimen Horario Activo: Horario Oficial Regular."
    elif "fuera_horario" in reg_tokens:
        regimen_desc = "Régimen Horario Activo: Fuera de Horario Oficial."
    elif "examen" in reg_tokens or "extendido_24h" in reg_tokens:
        regimen_desc = "Régimen Horario Activo: Extensión Horaria Especial Exámenes."
    else:
        regimen_desc = "Régimen Horario Activo: Todos los horarios."

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
    es_presencia_bib = espacio_id == 1 and any(k in slug for k in ["presencia_intervalos", "aforo_presencia", "realtime_presence"])
    if espacio_id == 1 and not es_presencia_bib:
        alerta_bib = await _construir_alerta_operativa_biblioteca(db, d_ini, d_fin, sala, filtros)
        if alerta_bib:
            contexto_hitos = f"{contexto_hitos}\n{alerta_bib}"

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
        # 0. Curva de Presencia Física por Intervalos de Sesión [entrada, salida]
        if any(k in slug for k in ["presencia_intervalos", "aforo_presencia", "realtime_presence"]):
            if espacio_id == 2 or "vehic" in slug:
                data = await VehicleService.get_realtime_presence_curve(
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
                cap = cap_activa if cap_activa else 125
                max_val = 0
                max_time = "N/D"
                max_csf11 = 0
                max_csf21 = 0
                max_chs01 = 0
                tot_in = 0
                tot_out = 0
                for r in (data or []):
                    tot_in += r.get("entradas", 0) or r.get("ingresos", 0) or 0
                    tot_out += r.get("salidas", 0) or 0
                    val = r.get("vehiculos_presentes") or r.get("personas_unicas") or 0
                    max_csf11 = max(max_csf11, r.get("vehiculos_csf11") or 0)
                    max_csf21 = max(max_csf21, r.get("vehiculos_csf21") or 0)
                    max_chs01 = max(max_chs01, r.get("vehiculos_chs01") or 0)
                    if val > max_val:
                        max_val = val
                        max_time = r.get("bucket", "N/D")
                pct_cap = (max_val / cap * 100) if cap else 0
                desglose_sec_txt = ""
                if _normalizar_sector_prophet_veh(sector) == "todos":
                    desglose_sec_txt = (
                        f"\n- Picos por sector: CSF11={max_csf11}/{caps_veh.get('CSF11', 40)} veh | "
                        f"CSF21={max_csf21}/{caps_veh.get('CSF21', 50)} veh | "
                        f"CHS01={max_chs01}/{caps_veh.get('CHS01', 35)} veh."
                    )
                resumen_metricas = (
                    f"Gráfico enfocado: Curva de Presencia Vehicular por Intervalos de Sesión ({nombre_espacio}).\n"
                    f"- Metodología: Conteo minuto a minuto de patentes activas [entrada <= T < salida] por vehículo único.\n"
                    f"- Entorno y Capacidad Calibrada: {cap} plazas ({sala_desc}).\n"
                    f"- Pico máximo de presencia vehicular simultánea: {max_val} vehículos ({pct_cap:.1f}% sobre capacidad calibrada de {cap} plazas) el {max_time}.{desglose_sec_txt}\n"
                    f"- Total de ingresos vehiculares en el período: {tot_in:,}.\n"
                    f"- Total de salidas vehiculares en el período: {tot_out:,}.\n"
                    f"- Intervalos horarios evaluados: {len(data or [])} registros.\n"
                    f"{contexto_hitos}"
                )
                table_data = data[:50] if isinstance(data, list) else None
            else:
                data = await AttendanceService.get_realtime_presence_curve(
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
                    incluir_pausas_bano=incluir_pausas_bano,
                    desduplicar_rafagas=desduplicar_rafagas,
                    incluir_funcionarios=incluir_funcionarios,
                    incluir_sin_identificar=incluir_sin_identificar,
                )
                component = "OccupancyAreaChart"
                payload = data
                cap = cap_activa
                max_val = 0
                max_time = "N/D"
                s1_en_pico = 0
                s2_en_pico = 0
                max_s1 = 0
                max_time_s1 = "N/D"
                max_s2 = 0
                max_time_s2 = "N/D"
                tot_in = 0
                tot_in_s1 = 0
                tot_in_s2 = 0
                tot_out = 0
                for r in (data or []):
                    tot_in += r.get("ingresos", 0) or r.get("entradas", 0) or 0
                    tot_in_s1 += r.get("ingresos_sala1", 0) or 0
                    tot_in_s2 += r.get("ingresos_sala2", 0) or 0
                    tot_out += r.get("salidas", 0) or 0
                    val = r.get("personas_unicas") or 0
                    v_s1 = r.get("personas_sala1") or 0
                    v_s2 = r.get("personas_sala2") or 0
                    b_str = r.get("bucket", "N/D")
                    if val > max_val:
                        max_val = val
                        max_time = b_str
                        s1_en_pico = v_s1
                        s2_en_pico = v_s2
                    if v_s1 > max_s1:
                        max_s1 = v_s1
                        max_time_s1 = b_str
                    if v_s2 > max_s2:
                        max_s2 = v_s2
                        max_time_s2 = b_str
                pct_cap = (max_val / cap * 100) if cap else 0
                pct_s1 = (max_s1 / CAP_SALA_1 * 100) if CAP_SALA_1 else 0
                pct_s2 = (max_s2 / CAP_SALA_2 * 100) if CAP_SALA_2 else 0

                alerta_op = await _construir_alerta_operativa_biblioteca(
                    db, d_ini, d_fin, sala, filtros, curva_presencia=data
                )
                ctx_completo = f"{contexto_hitos}\n{alerta_op}" if alerta_op else contexto_hitos
                desglose_salas_txt = ""
                if not sala:
                    desglose_salas_txt = (
                        f"\n- Desglose en pico combinado ({max_time}): Sala 1 = {s1_en_pico} personas | Sala 2 = {s2_en_pico} personas.\n"
                        f"- Pico individual Sala 1 (CSF02 2° Piso, {CAP_SALA_1} asientos): {max_s1} personas ({pct_s1:.1f}%) el {max_time_s1}; ingresos acumulados: {tot_in_s1:,}.\n"
                        f"- Pico individual Sala 2 (CSF04 Pecera 1° Piso, {CAP_SALA_2} asientos): {max_s2} personas ({pct_s2:.1f}%) el {max_time_s2}; ingresos acumulados: {tot_in_s2:,}."
                    )
                resumen_metricas = (
                    f"Gráfico enfocado: Curva de Presencia Física en Sala por Intervalos de Sesión ({nombre_espacio}).\n"
                    f"- Metodología: Conteo de sesiones activas [entrada <= T y salida >= T] por usuario único.\n"
                    f"- Entorno y Capacidad: {sala_desc}.\n"
                    f"- {regimen_desc}\n"
                    f"- Pico máximo de presencia física simultánea: {max_val} personas ({pct_cap:.1f}% sobre capacidad de {cap} asientos) el {max_time}.{desglose_salas_txt}\n"
                    f"- Total de ingresos registrados en el período: {tot_in:,}.\n"
                    f"- Total de salidas registradas en el período: {tot_out:,}.\n"
                    f"- Intervalos horarios evaluados: {len(data or [])} registros.\n"
                    f"{ctx_completo}"
                )
                table_data = data[:50] if isinstance(data, list) else None

        # 1. Curva de Aforo / Ocupación
        elif any(k in slug for k in ["aforo_curva", "curva_ocupacion", "curva_de_aforo", "curva_de_ocupacion"]):
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
                cap = cap_activa if cap_activa else 125
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
                    incluir_pausas_bano=incluir_pausas_bano,
                    desduplicar_rafagas=desduplicar_rafagas,
                    incluir_funcionarios=incluir_funcionarios,
                    incluir_sin_identificar=incluir_sin_identificar,
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

        # 2a. Pronóstico Prophet de Presencia Física
        elif any(k in slug for k in ["prophet_presencia", "presencia_prophet"]):
            data = await get_prophet_presence_forecast(db, sala=_normalizar_sala_prophet_bib(sala))
            component = "ForecastLineChart"
            payload = data
            pron = data.get("pronostico_7d") or data.get("forecast") or []
            max_p = max((pt.get("yhat", 0) for pt in pron), default=0)
            avg_p = sum(pt.get("yhat", 0) for pt in pron) / len(pron) if pron else 0
            m_stat = data.get("model_status", {})
            desglose_bu = _resumen_desglose_prophet(data, 1)
            resumen_metricas = (
                f"Gráfico enfocado: Pronóstico Continuo de Presencia Física en Sala ({m_stat.get('model_type', 'Prophet Jerárquico Bottom-Up')}).\n"
                f"- Modelo: Prophet horario condicional entrenado sobre horario operativo con capacidad física de referencia ({data.get('capacidad_asientos')} asientos).\n"
                f"- Alcance: 7 días históricos de presencia por intervalos y 7 días proyectados.\n"
                f"- Pico de ocupación física proyectado: {max_p:.0f} ocupantes simultáneos.\n"
                f"- Demanda media: {avg_p:.0f} ocupantes.{desglose_bu}\n"
                f"- Estado del modelo: {m_stat.get('status', 'ok')} ({m_stat.get('model_date', 'reciente')}).\n"
                f"{contexto_hitos}"
            )
            table_data = pron[:40] if pron else None

        # 2. Pronóstico Prophet Continuo (Presencia Física)
        elif any(k in slug for k in ["prophet", "pronostico_prophet", "prediccion_prophet"]):
            if espacio_id == 2:
                data = await get_prophet_forecast(db, recinto="vehicular", sala=_normalizar_sector_prophet_veh(sector))
            else:
                data = await get_prophet_presence_forecast(db, sala=_normalizar_sala_prophet_bib(sala))
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
            cap_ref = data.get("capacidad_asientos") or data.get("capacidad") or cap_activa
            unidad_cap = "plazas" if espacio_id == 2 else "asientos"
            unidad_occ = "vehículos presentes" if espacio_id == 2 else "ocupantes simultáneos"
            desglose_bu = _resumen_desglose_prophet(data, espacio_id)
            resumen_metricas = (
                f"Gráfico enfocado: Pronóstico Continuo Prophet ({nombre_espacio} — {m_stat.get('model_type', 'Prophet Jerárquico')}).\n"
                f"- Alcance: 7 días de serie histórica de presencia y 7 días de proyección futura continua.\n"
                f"- Capacidad institucional calibrada de referencia: {cap_ref} {unidad_cap} ({sala_desc}).\n"
                f"- Pico proyectado más elevado: {max_p:.0f} {unidad_occ} en fecha/hora {max_t}.\n"
                f"- Demanda promedio estimada en el horizonte: {avg_p:.0f} {unidad_occ}.{desglose_bu}\n"
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
                    incluir_pausas_bano=incluir_pausas_bano,
                    desduplicar_rafagas=desduplicar_rafagas,
                    incluir_funcionarios=incluir_funcionarios,
                    incluir_sin_identificar=incluir_sin_identificar,
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
                incluir_pausas_bano=incluir_pausas_bano,
                desduplicar_rafagas=desduplicar_rafagas,
                incluir_funcionarios=incluir_funcionarios,
                incluir_sin_identificar=incluir_sin_identificar,
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
                incluir_pausas_bano=incluir_pausas_bano,
                desduplicar_rafagas=desduplicar_rafagas,
                incluir_funcionarios=incluir_funcionarios,
                incluir_sin_identificar=incluir_sin_identificar,
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
            resumen_metricas = (
                f"Gráfico enfocado: Comparativa de Afluencia entre Salas (Sala 1 vs Sala 2).\n"
                f"- Sala 1 (CSF02 2° Piso, Estudio y Biblioteca con Locker): {tot_s1:,} accesos ({u_s1:,} alumnos únicos, {pct_s1:.1f}% de afluencia, capacidad: {CAP_SALA_1} asientos).\n"
                f"- Sala 2 (CSF04 Pecera 1° Piso, Estudio 24h): {tot_s2:,} accesos ({u_s2:,} alumnos únicos, {pct_s2:.1f}% de afluencia, capacidad: {CAP_SALA_2} asientos).\n"
                f"- Capacidad combinada: {CAP_CAMPUS_CALIBRADA} asientos.\n"
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
                incluir_pausas_bano=incluir_pausas_bano,
                desduplicar_rafagas=desduplicar_rafagas,
                incluir_funcionarios=incluir_funcionarios,
                incluir_sin_identificar=incluir_sin_identificar,
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
                incluir_pausas_bano=incluir_pausas_bano,
                desduplicar_rafagas=desduplicar_rafagas,
                incluir_funcionarios=incluir_funcionarios,
                incluir_sin_identificar=incluir_sin_identificar,
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
                incluir_pausas_bano=incluir_pausas_bano,
                desduplicar_rafagas=desduplicar_rafagas,
                incluir_funcionarios=incluir_funcionarios,
                incluir_sin_identificar=incluir_sin_identificar,
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
                incluir_pausas_bano=incluir_pausas_bano,
                desduplicar_rafagas=desduplicar_rafagas,
                incluir_funcionarios=incluir_funcionarios,
                incluir_sin_identificar=incluir_sin_identificar,
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
                incluir_pausas_bano=incluir_pausas_bano,
                desduplicar_rafagas=desduplicar_rafagas,
                incluir_funcionarios=incluir_funcionarios,
                incluir_sin_identificar=incluir_sin_identificar,
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
                incluir_pausas_bano=incluir_pausas_bano,
                desduplicar_rafagas=desduplicar_rafagas,
                incluir_funcionarios=incluir_funcionarios,
                incluir_sin_identificar=incluir_sin_identificar,
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
            cap_camp = int((data.get("campana") or {}).get("capacidad_asientos") or CAP_SALA_2)
            bloque_lbl = data.get("bloque_horario_label") or "Extensión Nocturna 24h"
            resumen_metricas = (
                f"Gráfico enfocado: Campaña 24 Horas & Análisis de Justificación Operativa (Sala 2 CSF04 Pecera: {cap_camp} Asientos).\n"
                f"- Bloque horario evaluado ({bloque_lbl}): ver detalle exacto de Campaña 24 Horas en los hechos institucionales.\n"
                f"- Aporte Nocturno (Delta 24h): {pct_delta:.2f}% ({ing_noct:,} de {tot_ing:,} accesos totales).\n"
                f"- Concurrencia Máxima Simultánea: {pico.get('aforo_maximo', 0)} alumnos ({pico.get('tasa_ocupacion_asientos_pct', 0):.1f}% sobre {cap_camp} asientos, hora pico: {pico.get('hora_pico', 'N/D')}).\n"
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
        filtros_req = (req.filtros if req else None) or {}
        if espacio == 2:
            sector_norm = _normalizar_sector_prophet_veh(args.get("sector") or filtros_req.get("sector"))
            data = await get_prophet_forecast(db, recinto="vehicular", sala=sector_norm)
            unidad_cap, unidad_occ = "plazas", "vehículos presentes"
        else:
            sala_norm = _normalizar_sala_prophet_bib(args.get("sala") or filtros_req.get("sala"))
            data = await get_prophet_presence_forecast(db, sala=sala_norm)
            unidad_cap, unidad_occ = "asientos", "ocupantes simultáneos"
        pron = data.get("pronostico_7d") or data.get("forecast") or []
        max_p, max_t = 0.0, "N/D"
        for pt in pron:
            v = float(pt.get("yhat", 0) or pt.get("aforo_proyectado", 0) or 0)
            if v > max_p:
                max_p = v
                max_t = str(pt.get("ds", pt.get("bucket", "N/D")))
        cap_ref = data.get("capacidad_asientos") or data.get("capacidad") or (125 if espacio == 2 else 276)
        desglose_bu = _resumen_desglose_prophet(data, espacio)
        res_m = (
            f"Proyección de presencia física con modelo Prophet Jerárquico calculada para los próximos 7 días ({len(pron)} puntos). "
            f"Capacidad de referencia: {cap_ref} {unidad_cap}. Pico proyectado: {max_p:.0f} {unidad_occ} el {max_t}.{desglose_bu}"
        )
        return "ForecastLineChart", data, res_m, None, pron[:40] if pron else None

    elif tool_name == "consultar_kpis_actuales":
        filtros_req = req.filtros if req else None
        if espacio == 2:
            data = await VehicleService.get_parking_occupancy(db, espacio_id=2)
            res_m = f"Métricas instantáneas actuales: {json.dumps(data, default=str)}."
        else:
            sala_req = (filtros_req or {}).get("sala")
            data = await AttendanceService.get_occupancy_realtime(db, espacio_id=1, sala=sala_req)
            alerta_op = await _construir_alerta_operativa_biblioteca(db, d_ini, d_fin, sala_req, filtros_req)
            res_m = f"Métricas instantáneas actuales: {json.dumps(data, default=str)}."
            if alerta_op:
                res_m = f"{res_m}\n{alerta_op}"
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

        filas_cal = [
            c_row
            for c_row in (await db.execute(query_cal)).scalars().all()
            if not (
                str(getattr(c_row, "fuente", "") or "") == "contingencia_manual"
                and not any([
                    bool(c_row.is_break),
                    bool(c_row.is_holiday),
                    bool(c_row.suspension_actividades),
                    bool(c_row.is_exam_period),
                    bool(getattr(c_row, "is_strike_federado", False)),
                    bool(getattr(c_row, "is_strike_carrera", False)),
                    bool(getattr(c_row, "is_class_milestone", False)),
                ])
            )
        ]

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
        alerta_hist = ""
        if espacio == 1:
            filtros_req = req.filtros if req else None
            alerta_hist = await _construir_alerta_operativa_biblioteca(
                db, d_ini, d_fin, (filtros_req or {}).get("sala"), filtros_req
            )

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
        if alerta_hist:
            res_m = f"{res_m}\n{alerta_hist}"
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



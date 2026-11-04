import asyncio
import json
import logging
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.domain.auth_models import Rol, TokenActivacion, Usuario, UsuarioRol
from app.domain.models import Espacio
from app.domain.reportes_compartidos_models import (
    AuditoriaAccesoReporte,
    DestinatarioReporte,
    ReporteCompartido,
)
from app.services.attendance_service import AttendanceService
from app.services.auth_service import generar_token_activacion
from app.services.email_service import (
    enviar_correo_activacion_consultor,
    enviar_correo_reporte_ejecutivo,
)
from app.services.llm_client import build_llm_client
from app.services.vehicle_service import VehicleService

logger = logging.getLogger(__name__)


CATALOGO_GRAFICOS_BIBLIOTECA = [
    {"id": "aforo_curva", "titulo": "Curva de Aforo Concurrente vs Capacidad"},
    {"id": "prophet_diario", "titulo": "Pronóstico Continuo Prophet (7 Días)"},
    {"id": "flujo_horario", "titulo": "Flujo Horario de Ingresos y Salidas"},
    {"id": "mapa_calor", "titulo": "Mapa de Calor (Día de Semana x Hora)"},
    {"id": "comparativa_salas", "titulo": "Comparativa Sala 1 vs Sala 2 (Pecera)"},
    {"id": "uso_torniquetes", "titulo": "Flujo por Torniquetes y Accesos Universales"},
    {"id": "frecuencia_marcajes", "titulo": "Distribución de Frecuencia de Marcajes"},
    {"id": "volumen_mensual", "titulo": "Volumen y Promedio Diario Mensual"},
    {"id": "evolucion_semanal", "titulo": "Evolución Semanal (Semanas ISO)"},
    {"id": "promedio_dia_semana", "titulo": "Promedio de Ingresos por Día de la Semana"},
    {"id": "hitos_academicos", "titulo": "Comparativa por Hito del Calendario Académico"},
    {"id": "distribucion_curricular", "titulo": "Distribución por Carrera y Facultad (Ley 21.719)"},
    {"id": "perfiles_visita", "titulo": "Perfiles de Estadía y Permanencia (Donut)"},
    {"id": "campana_24_horas", "titulo": "8. Campaña 24 Horas Exámenes & Análisis de Flujo Nocturno"},
]

CATALOGO_INDICADORES_BIBLIOTECA = [
    {"id": "dias_operativos", "titulo": "Días Operativos"},
    {"id": "carrera_mas_concurrida", "titulo": "Carrera Más Concurrida"},
    {"id": "recurrencia_mensual", "titulo": "Recurrencia Mensual"},
    {"id": "hora_pico_ingreso", "titulo": "Hora Pico de Ingreso"},
    {"id": "pico_concurrente", "titulo": "Pico Concurrente"},
    {"id": "afluencia_total", "titulo": "Afluencia Total"},
    {"id": "aforo_maximo_registrado", "titulo": "Aforo Máximo Registrado"},
    {"id": "estadia_promedio", "titulo": "Estadía Promedio"},
    {"id": "tasa_rebote", "titulo": "Tasa de Rebote"},
]

CATALOGO_GRAFICOS_ESTACIONAMIENTO = [
    {"id": "aforo_vehicular_curva", "titulo": "Curva de Concurrencia vs Capacidad Vehicular"},
    {"id": "prophet_vehicular", "titulo": "Pronóstico Continuo Prophet Vehicular"},
    {"id": "flujo_horario_vehicular", "titulo": "Flujo Horario de Ingresos y Salidas Vehiculares"},
    {"id": "evolucion_diaria_vehicular", "titulo": "Serie Temporal de Accesos Diarios"},
    {"id": "composicion_flota", "titulo": "Composición por Tipo de Vehículo"},
    {"id": "distribucion_marcas", "titulo": "Distribución por Marca de Vehículo"},
    {"id": "estadisticas_camaras", "titulo": "Distribución por Pórtico y Cámara ANPR"},
    {"id": "distribucion_estadia", "titulo": "Distribución de Tiempos de Permanencia"},
    {"id": "hitos_academicos_vehicular", "titulo": "Comparativa por Hito Académico Vehicular"},
    {"id": "movilidad_intercampus", "titulo": "Movilidad Intercampus CSF - CHS"},
    {"id": "clusters_comportamiento", "titulo": "Perfiles de Uso Vehicular (Clustering K-Means)"},
]

CATALOGO_INDICADORES_ESTACIONAMIENTO = [
    {"id": "dias_operativos", "titulo": "Días Operativos"},
    {"id": "sector_mas_concurrido", "titulo": "Sector Más Demandado"},
    {"id": "recurrencia_vehicular", "titulo": "Recurrencia Vehicular"},
    {"id": "hora_pico_acceso", "titulo": "Hora Pico de Acceso"},
    {"id": "pico_concurrente", "titulo": "Pico Concurrente"},
    {"id": "vehiculos_dentro", "titulo": "Vehículos Dentro"},
    {"id": "plazas_libres", "titulo": "Plazas Libres"},
    {"id": "total_ingresos", "titulo": "Total Ingresos"},
    {"id": "total_salidas", "titulo": "Total Salidas"},
    {"id": "rotacion_diaria", "titulo": "Rotación Diaria"},
    {"id": "permanencia_mediana", "titulo": "Permanencia Mediana"},
]


def _serializar_json_seguro(objeto: Any) -> str:
    return json.dumps(objeto, ensure_ascii=False, default=str)


def _cargar_json_seguro(texto: Optional[str], valor_defecto: Any) -> Any:
    if not texto:
        return valor_defecto
    try:
        return json.loads(texto)
    except Exception:
        return valor_defecto


class ServicioReportesCompartidos:
    """Servicio de negocio para creación, confinamiento, auditoría y consulta de reportes ejecutivos."""

    @staticmethod
    async def calcular_indicadores_ejecutivos_biblioteca(
        session: AsyncSession,
        fecha_inicio: date,
        fecha_fin: date,
        filtros: Dict[str, Any],
        kpis_base: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Calcula las 9 métricas originales del Dashboard de Biblioteca (Panel Gerencial + KPIs Principales)."""
        from app.services.metrics_service import MetricsService

        resumen_gerencial = {}
        try:
            resumen_gerencial = await MetricsService.get_kpi_summary(
                session=session,
                espacio_id=1,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
            )
        except Exception as exc:
            logger.warning("Fallo resumen gerencial biblioteca: %s", exc)

        total_registros = int(kpis_base.get("total_registros", kpis_base.get("total_accesos", 0)) or 0)
        usuarios_unicos = int(kpis_base.get("usuarios_unicos", kpis_base.get("usuarios_unicos_periodo", 0)) or 0)
        dias_operativos = int(
            kpis_base.get("dias_operativos") or resumen_gerencial.get("dias_operativos") or 0
        )
        recurrencia_mensual = float(
            kpis_base.get("tasa_recurrencia_mensual")
            or resumen_gerencial.get("recurrencia_mensual")
            or (round(total_registros / usuarios_unicos, 1) if usuarios_unicos > 0 else 0.0)
        )
        hora_pico_ingreso = str(
            kpis_base.get("hora_punta")
            or resumen_gerencial.get("hora_pico_ingreso")
            or "14:00 hrs"
        )
        max_aforo_historico = int(kpis_base.get("max_aforo_historico") or 0)
        pico_concurrente = int(
            resumen_gerencial.get("pico_concurrente") or max_aforo_historico or 0
        )

        # Estadía promedio (perfil Estándar) y Tasa de Rebote idénticos a BibliotecaView.tsx
        estadia_promedio_min = float(kpis_base.get("permanencia_promedio_min") or 0.0)
        tasa_rebote_pct = float(kpis_base.get("tasa_rebote_pct") or 0.0)
        try:
            perfiles_donut = await AttendanceService.get_visit_profiles_donut(
                session=session,
                espacio_id=1,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                alcance=filtros.get("alcance") or "conformes",
                regimen_horario=filtros.get("regimen_horario") or "todos",
                direccion=filtros.get("direccion") or "todos",
                dias_semana=filtros.get("dias_semana") or None,
                door=filtros.get("door") or None,
                perfil_visita=filtros.get("perfil_visita") or "todos",
                marcajes=filtros.get("marcajes") or "todos",
                sala=filtros.get("sala") or None,
                carrera=filtros.get("carrera") or None,
                facultad=filtros.get("facultad") or None,
                incluir_pausas_bano=bool(filtros.get("incluir_pausas_bano", True)),
                desduplicar_rafagas=bool(filtros.get("desduplicar_rafagas", True)),
            )
            if perfiles_donut:
                if perfiles_donut.get("tasa_rebote_pct") is not None:
                    tasa_rebote_pct = float(perfiles_donut["tasa_rebote_pct"])
                for item_p in perfiles_donut.get("items") or []:
                    if "Estándar" in str(item_p.get("perfil", "")):
                        if item_p.get("promedio_min") is not None:
                            estadia_promedio_min = float(item_p["promedio_min"])
                        break
        except Exception as exc:
            logger.warning("Fallo consulta perfiles donut en indicadores reporte: %s", exc)

        # Carrera más concurrida (respeta carrera filtrada o top del filtro activo)
        carrera_mas_concurrida = filtros.get("carrera") or resumen_gerencial.get("carrera_mas_concurrida") or "Sin catalogar"
        if not filtros.get("carrera"):
            try:
                dist_curr = await AttendanceService.get_curricular_distribution(
                    session=session,
                    espacio_id=1,
                    fecha_inicio=fecha_inicio,
                    fecha_fin=fecha_fin,
                    alcance=filtros.get("alcance") or "conformes",
                    regimen_horario=filtros.get("regimen_horario") or "todos",
                    direccion=filtros.get("direccion") or "todos",
                    dias_semana=filtros.get("dias_semana") or None,
                    door=filtros.get("door") or None,
                    perfil_visita=filtros.get("perfil_visita") or "todos",
                    marcajes=filtros.get("marcajes") or "todos",
                    sala=filtros.get("sala") or None,
                    carrera=None,
                    facultad=filtros.get("facultad") or None,
                    cohorte=filtros.get("cohorte") or None,
                    incluir_pausas_bano=bool(filtros.get("incluir_pausas_bano", True)),
                    desduplicar_rafagas=bool(filtros.get("desduplicar_rafagas", True)),
                )
                carreras_lista = (dist_curr or {}).get("carreras") or []
                for c_item in carreras_lista:
                    nombre_c = str(c_item.get("carrera") or "").strip()
                    if nombre_c and nombre_c.lower() not in ("sin carrera catalogada", "sin catalogar"):
                        carrera_mas_concurrida = nombre_c
                        break
            except Exception:
                pass

        # Capacidad de asientos según sala seleccionada (igual que BibliotecaView.tsx)
        sala_raw = str(filtros.get("sala") or "").lower()
        cap_sala1 = 124
        cap_sala2 = 226
        try:
            salas_bd = await AttendanceService.get_salas_biblioteca(session, 1)
            for s_bd in salas_bd or []:
                cod_s = str(s_bd.get("codigo") or "")
                if "CSF02" in cod_s or s_bd.get("id") == 1:
                    cap_sala1 = int(s_bd.get("capacidad_asientos") or 124)
                elif "CSF04" in cod_s or s_bd.get("id") == 2:
                    cap_sala2 = int(s_bd.get("capacidad_asientos") or 226)
        except Exception:
            pass

        stmt_cap_bib = select(Espacio.capacidad_max).where(Espacio.id == 1)
        cap_espacio = int((await session.execute(stmt_cap_bib)).scalar_one_or_none() or (cap_sala1 + cap_sala2))

        if "csf02" in sala_raw or "sala_1" in sala_raw or sala_raw == "1":
            sala_legible = "Sala 1 (CSF02 2° Piso)"
            capacidad_activa = cap_sala1
        elif "csf04" in sala_raw or "sala_2" in sala_raw or sala_raw == "2":
            sala_legible = "Sala 2 (CSF04 Pecera 1° Piso)"
            capacidad_activa = cap_sala2
        else:
            sala_legible = "Global"
            capacidad_activa = cap_espacio

        return {
            "dias_operativos": dias_operativos,
            "carrera_mas_concurrida": carrera_mas_concurrida,
            "recurrencia_mensual": round(recurrencia_mensual, 1),
            "hora_pico_ingreso": hora_pico_ingreso,
            "pico_concurrente": pico_concurrente,
            "afluencia_total": total_registros,
            "total_accesos": total_registros,
            "usuarios_unicos": usuarios_unicos,
            "aforo_maximo_registrado": max_aforo_historico,
            "capacidad_asientos": capacidad_activa,
            "estadia_promedio_min": round(estadia_promedio_min, 0),
            "permanencia_promedio_min": round(estadia_promedio_min, 1),
            "tasa_rebote_pct": round(tasa_rebote_pct, 1),
            "carrera_filtrada": filtros.get("carrera") or "Todas las carreras",
            "facultad_filtrada": filtros.get("facultad") or "Todas las facultades",
            "sala_filtrada": sala_legible,
        }

    @staticmethod
    async def calcular_indicadores_ejecutivos_estacionamiento(
        session: AsyncSession,
        fecha_inicio: date,
        fecha_fin: date,
        filtros: Dict[str, Any],
        kpis_base: Dict[str, Any],
        flujo_horario: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Calcula las 11 métricas originales del Dashboard de Estacionamiento (Panel Gerencial + KPIs Principales)."""
        from app.services.metrics_service import MetricsService

        resumen_gerencial = {}
        try:
            resumen_gerencial = await MetricsService.get_kpi_summary(
                session=session,
                espacio_id=2,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
            )
        except Exception as exc:
            logger.warning("Fallo resumen gerencial estacionamiento: %s", exc)

        sector_filtro = filtros.get("sector") or "todos"
        ocupacion_vivo = {}
        try:
            ocupacion_vivo = await VehicleService.get_occupancy_realtime(
                session=session,
                espacio_id=2,
                sector=sector_filtro if sector_filtro != "todos" else None,
            )
        except Exception as exc:
            logger.warning("Fallo ocupacion vivo estacionamiento en reporte: %s", exc)

        capacidad_plazas = int(
            ocupacion_vivo.get("capacidad_maxima")
            or kpis_base.get("capacidad_calibrada")
            or 125
        )
        vehiculos_presentes = int(ocupacion_vivo.get("vehiculos_presentes") or 0)
        plazas_disponibles = int(ocupacion_vivo.get("plazas_disponibles") or max(0, capacidad_plazas - vehiculos_presentes))
        ocupacion_pct = float(ocupacion_vivo.get("ocupacion_pct") or round((vehiculos_presentes / max(1, capacidad_plazas)) * 100.0, 1))

        total_ingresos = int(kpis_base.get("total_accesos", kpis_base.get("total_ingresos", 0)) or 0)
        total_salidas = int(kpis_base.get("total_salidas") or 0)
        patentes_unicas = int(kpis_base.get("vehiculos_unicos", kpis_base.get("patentes_unicas", 0)) or 0)
        dias_operativos = int(kpis_base.get("dias_operativos") or resumen_gerencial.get("dias_operativos") or 0)
        rotacion_diaria = float(kpis_base.get("turnover_rate_diario") or 0.0)
        permanencia_mediana_min = float(kpis_base.get("permanencia_mediana_min") or 0.0)
        hora_pico_acceso = str(kpis_base.get("hora_punta") or resumen_gerencial.get("hora_pico_ingreso") or "08:00 hrs")
        pico_concurrente = int(
            resumen_gerencial.get("pico_concurrente") or kpis_base.get("max_aforo_historico") or 0
        )
        recurrencia_vehicular = float(
            resumen_gerencial.get("recurrencia_mensual")
            or (round(total_ingresos / patentes_unicas, 1) if patentes_unicas > 0 else 0.0)
        )
        sector_mas_concurrido = str(
            resumen_gerencial.get("sector_mas_concurrido") or "CSF11 — Edificio 11"
        )

        return {
            "dias_operativos": dias_operativos,
            "sector_mas_concurrido": sector_mas_concurrido,
            "recurrencia_vehicular": round(recurrencia_vehicular, 1),
            "hora_pico_acceso": hora_pico_acceso,
            "pico_concurrente": pico_concurrente,
            "vehiculos_dentro": vehiculos_presentes,
            "ocupacion_pct": ocupacion_pct,
            "plazas_libres": plazas_disponibles,
            "total_ingresos": total_ingresos,
            "total_ingresos_vehiculares": total_ingresos,
            "total_salidas": total_salidas,
            "patentes_unicas": patentes_unicas,
            "rotacion_diaria": rotacion_diaria,
            "indice_rotacion_plaza": rotacion_diaria,
            "permanencia_mediana_min": round(permanencia_mediana_min, 0),
            "permanencia_promedio_min": round(permanencia_mediana_min, 0),
            "capacidad_plazas": capacidad_plazas,
            "sector_filtrado": filtros.get("sector") or "Todos los sectores CSF",
            "tipo_vehiculo_filtrado": filtros.get("tipo_vehiculo") or "Toda la flota",
        }

    @classmethod
    async def ensamblar_datos_reporte_confinado(
        cls,
        session: AsyncSession,
        espacio_id: int,
        fecha_inicio: date,
        fecha_fin: date,
        filtros: Dict[str, Any],
        graficos_visibles: List[str],
        indicadores_visibles: List[str],
    ) -> Dict[str, Any]:
        """
        Ejecuta en el servidor únicamente las consultas de los gráficos e indicadores autorizados,
        aplicando de manera inmutable los filtros sellados del reporte.
        """
        alcance = filtros.get("alcance") or "conformes"
        regimen_horario = filtros.get("regimen_horario") or "todos"
        direccion = filtros.get("direccion") or "todos"
        dias_semana = filtros.get("dias_semana") or None
        door = filtros.get("door") or None
        perfil_visita = filtros.get("perfil_visita") or "todos"
        marcajes = filtros.get("marcajes") or "todos"
        sala = filtros.get("sala") or None
        carrera = filtros.get("carrera") or None
        facultad = filtros.get("facultad") or None
        cohorte = filtros.get("cohorte") or None
        sector = filtros.get("sector") or None
        tipo_vehiculo = filtros.get("tipo_vehiculo") or None
        incluir_pausas_bano = bool(filtros.get("incluir_pausas_bano", True))
        desduplicar_rafagas = bool(filtros.get("desduplicar_rafagas", True))

        graficos_resultado: Dict[str, Any] = {}

        if espacio_id == 1:
            kpis_base = await AttendanceService.get_kpis(
                session=session,
                espacio_id=1,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
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
            )
            indicadores_ejecutivos = await cls.calcular_indicadores_ejecutivos_biblioteca(
                session=session,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                filtros=filtros,
                kpis_base=kpis_base,
            )

            kwargs_comunes = dict(
                session=session,
                espacio_id=1,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
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
            )

            from app.services.prediction_service import get_prophet_forecast

            flujo_bib = None
            if (
                "flujo_horario" in graficos_visibles
                or "aforo_curva" in graficos_visibles
                or "prophet_diario" in graficos_visibles
            ):
                flujo_bib = await AttendanceService.get_hourly_flow(**kwargs_comunes)
                graficos_resultado["flujo_horario"] = flujo_bib
                if "aforo_curva" in graficos_visibles:
                    graficos_resultado["aforo_curva"] = flujo_bib

            if "prophet_diario" in graficos_visibles:
                sala_raw_p = str(sala or "").lower()
                if "csf02" in sala_raw_p or "sala_1" in sala_raw_p or sala_raw_p == "1":
                    sala_prophet = "sala1"
                elif "csf04" in sala_raw_p or "sala_2" in sala_raw_p or sala_raw_p == "2":
                    sala_prophet = "sala2"
                else:
                    sala_prophet = "todas"
                try:
                    graficos_resultado["prophet_diario"] = await get_prophet_forecast(
                        session, recinto="biblioteca", sala=sala_prophet
                    )
                except Exception as exc:
                    logger.warning("Fallo prophet biblioteca en reporte: %s", exc)
                    graficos_resultado["prophet_diario"] = {}

            if "evolucion_semanal" in graficos_visibles:
                graficos_resultado["evolucion_semanal"] = await AttendanceService.get_weekly_evolution(**kwargs_comunes)
            if "volumen_mensual" in graficos_visibles:
                graficos_resultado["volumen_mensual"] = await AttendanceService.get_monthly_volume(**kwargs_comunes)
            if "mapa_calor" in graficos_visibles:
                graficos_resultado["mapa_calor"] = await AttendanceService.get_heatmap(**kwargs_comunes)
            if "comparativa_salas" in graficos_visibles:
                graficos_resultado["comparativa_salas"] = await AttendanceService.get_rooms_comparison(
                    session=session,
                    espacio_id=1,
                    fecha_inicio=fecha_inicio,
                    fecha_fin=fecha_fin,
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
                )
            if "promedio_dia_semana" in graficos_visibles:
                graficos_resultado["promedio_dia_semana"] = await AttendanceService.get_daily_average_attendance(
                    session=session,
                    espacio_id=1,
                    fecha_inicio=fecha_inicio,
                    fecha_fin=fecha_fin,
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
                )
            if "distribucion_curricular" in graficos_visibles:
                graficos_resultado["distribucion_curricular"] = await AttendanceService.get_curricular_distribution(
                    **kwargs_comunes
                )
            if "perfiles_visita" in graficos_visibles:
                graficos_resultado["perfiles_visita"] = await AttendanceService.get_visit_profiles_donut(
                    session=session,
                    espacio_id=1,
                    fecha_inicio=fecha_inicio,
                    fecha_fin=fecha_fin,
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
                )
            if "uso_torniquetes" in graficos_visibles:
                graficos_resultado["uso_torniquetes"] = await AttendanceService.get_door_usage(
                    session,
                    espacio_id=1,
                    fecha_inicio=fecha_inicio,
                    fecha_fin=fecha_fin,
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
                )
            if "hitos_academicos" in graficos_visibles:
                graficos_resultado["hitos_academicos"] = await AttendanceService.get_academic_milestones_comparison(
                    **kwargs_comunes
                )
            if "frecuencia_marcajes" in graficos_visibles:
                graficos_resultado["frecuencia_marcajes"] = await AttendanceService.get_checkin_distribution(
                    session=session,
                    espacio_id=1,
                    fecha_inicio=fecha_inicio,
                    fecha_fin=fecha_fin,
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
                )
            if "campana_24_horas" in graficos_visibles:
                try:
                    graficos_resultado["campana_24_horas"] = await AttendanceService.get_analisis_24h(
                        session=session,
                        espacio_id=1,
                        fecha_inicio=fecha_inicio,
                        fecha_fin=fecha_fin,
                        bloque_horario="todos",
                    )
                except Exception as exc:
                    logger.warning("Fallo analisis 24h en reporte confinado: %s", exc)
                    graficos_resultado["campana_24_horas"] = None
        else:
            kpis_base = await VehicleService.get_kpis(
                session=session,
                espacio_id=2,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                alcance=alcance,
                regimen_horario=regimen_horario,
                direccion=direccion,
                dias_semana=dias_semana,
                door=door,
                sector=sector,
                tipo_vehiculo=tipo_vehiculo,
            )
            flujo_h = await VehicleService.get_hourly_flow(
                session=session,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                espacio_id=2,
                alcance=alcance,
                regimen_horario=regimen_horario,
                direccion=direccion,
                dias_semana=dias_semana,
                door=door,
                sector=sector,
                tipo_vehiculo=tipo_vehiculo,
            )
            indicadores_ejecutivos = await cls.calcular_indicadores_ejecutivos_estacionamiento(
                session=session,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                filtros=filtros,
                kpis_base=kpis_base,
                flujo_horario=flujo_h if isinstance(flujo_h, list) else (flujo_h.get("data", []) if isinstance(flujo_h, dict) else []),
            )

            from app.services.prediction_service import get_prophet_forecast

            if (
                "flujo_horario_vehicular" in graficos_visibles
                or "aforo_vehicular_curva" in graficos_visibles
                or "prophet_vehicular" in graficos_visibles
            ):
                graficos_resultado["flujo_horario_vehicular"] = flujo_h
                if "aforo_vehicular_curva" in graficos_visibles:
                    graficos_resultado["aforo_vehicular_curva"] = flujo_h

            if "prophet_vehicular" in graficos_visibles:
                try:
                    graficos_resultado["prophet_vehicular"] = await get_prophet_forecast(
                        session, recinto="vehicular"
                    )
                except Exception as exc:
                    logger.warning("Fallo prophet vehicular en reporte: %s", exc)
                    graficos_resultado["prophet_vehicular"] = {}

            if "evolucion_diaria_vehicular" in graficos_visibles:
                graficos_resultado["evolucion_diaria_vehicular"] = await VehicleService.get_daily_evolution(
                    session, 2, fecha_inicio, fecha_fin, sector=sector
                )
            if "composicion_flota" in graficos_visibles or "distribucion_marcas" in graficos_visibles:
                flota_data = await VehicleService.get_fleet_composition(
                    session, 2, fecha_inicio, fecha_fin, sector=sector
                )
                graficos_resultado["composicion_flota"] = flota_data
                if "distribucion_marcas" in graficos_visibles:
                    graficos_resultado["distribucion_marcas"] = flota_data
            if "estadisticas_camaras" in graficos_visibles:
                graficos_resultado["estadisticas_camaras"] = await VehicleService.get_camera_stats(
                    session,
                    espacio_id=2,
                    fecha_inicio=fecha_inicio,
                    fecha_fin=fecha_fin,
                    alcance=alcance,
                    regimen_horario=regimen_horario,
                    direccion=direccion,
                    dias_semana=dias_semana,
                    door=door,
                    sector=sector,
                    tipo_vehiculo=tipo_vehiculo,
                )
            if "distribucion_estadia" in graficos_visibles:
                graficos_resultado["distribucion_estadia"] = await VehicleService.get_stay_distribution(session, 2)
            if "hitos_academicos_vehicular" in graficos_visibles:
                graficos_resultado["hitos_academicos_vehicular"] = (
                    await VehicleService.get_academic_milestones_comparison(session, 2)
                )
            if "movilidad_intercampus" in graficos_visibles:
                graficos_resultado["movilidad_intercampus"] = await VehicleService.get_intercampus_mobility(session)
            if "clusters_comportamiento" in graficos_visibles:
                graficos_resultado["clusters_comportamiento"] = await VehicleService.get_behavioral_clusters(session)

        catalogo_ind_actual = (
            CATALOGO_INDICADORES_BIBLIOTECA if espacio_id == 1 else CATALOGO_INDICADORES_ESTACIONAMIENTO
        )
        ids_catalogo_ind = {i["id"] for i in catalogo_ind_actual}
        if not indicadores_visibles or not any(i in ids_catalogo_ind for i in indicadores_visibles):
            indicadores_visibles = [i["id"] for i in catalogo_ind_actual]
        else:
            indicadores_visibles = [i for i in indicadores_visibles if i in ids_catalogo_ind]

        return {
            "kpis_base": kpis_base,
            "indicadores_ejecutivos": indicadores_ejecutivos,
            "indicadores_visibles": indicadores_visibles,
            "graficos_visibles": graficos_visibles,
            "graficos": graficos_resultado,
            "generado_en": datetime.now().isoformat(),
        }

    @classmethod
    async def _asegurar_usuario_consultor_reporte(
        cls,
        session: AsyncSession,
        email_dest: str,
        nombre_dest: str,
        creador_id: Optional[int],
        forzar_nuevo_token: bool = False,
    ) -> tuple[Usuario, Optional[str]]:
        """
        Garantiza que exista un Usuario con rol Consultor_Reporte asociado al correo del solicitante.
        Si la cuenta está pendiente de activación, retorna (usuario, token_plano_activacion).
        """
        stmt_rol = select(Rol).where(Rol.nombre == "Consultor_Reporte")
        rol_consultor = (await session.execute(stmt_rol)).scalar_one_or_none()
        if not rol_consultor:
            rol_consultor = Rol(
                nombre="Consultor_Reporte",
                descripcion="Solicitante institucional con acceso exclusivo a su bandeja de reportes ejecutivos",
                rate_limit_quota="50/day",
            )
            session.add(rol_consultor)
            await session.flush()

        stmt_usr = (
            select(Usuario)
            .options(selectinload(Usuario.roles))
            .where(Usuario.email == email_dest)
        )
        usuario_dest = (await session.execute(stmt_usr)).scalar_one_or_none()
        token_plano: Optional[str] = None

        CUENTAS_SISTEMA_PROTEGIDAS = {"admin@uct.cl", "directivo@uct.cl", "analista@uct.cl", "guardia@uct.cl"}

        if not usuario_dest:
            usuario_dest = Usuario(
                email=email_dest,
                hashed_password="PENDIENTE_ACTIVACION",
                nombre_completo=nombre_dest,
                is_active=False,
                allowed_datasets=[],
                can_use_ai=False,
                can_export=True,
                can_ingest=False,
                espacio_id=None,
                created_by_user_id=creador_id,
            )
            session.add(usuario_dest)
            await session.flush()
            session.add(UsuarioRol(usuario_id=usuario_dest.id, rol_id=rol_consultor.id))
            await session.flush()

            token_plano, token_hash = generar_token_activacion()
            session.add(
                TokenActivacion(
                    usuario_id=usuario_dest.id,
                    token_hash=token_hash,
                    tipo_token="ACTIVACION_INICIAL",
                    expira_en=datetime.now(timezone.utc) + timedelta(hours=72),
                    utilizado=False,
                )
            )
            await session.flush()
        else:
            # Si el usuario ya existe en el sistema (ej. Admin_Sistema, Directora, etc.):
            # Su contraseña se preserva intacta y solo se le agrega el rol Consultor_Reporte.
            roles_actuales_ids = {r.id for r in (usuario_dest.roles or [])}
            if rol_consultor.id not in roles_actuales_ids:
                session.add(UsuarioRol(usuario_id=usuario_dest.id, rol_id=rol_consultor.id))
                await session.flush()

            pendiente_clave = (
                usuario_dest.hashed_password == "PENDIENTE_ACTIVACION"
                or not usuario_dest.hashed_password.startswith("$2")
            )
            if pendiente_clave or (forzar_nuevo_token and pendiente_clave):
                token_plano, token_hash = generar_token_activacion()
                session.add(
                    TokenActivacion(
                        usuario_id=usuario_dest.id,
                        token_hash=token_hash,
                        tipo_token="ACTIVACION_INICIAL",
                        expira_en=datetime.now(timezone.utc) + timedelta(hours=72),
                        utilizado=False,
                    )
                )
                await session.flush()

        return usuario_dest, token_plano

    @classmethod
    async def registrar_consultor_reporte(
        cls,
        session: AsyncSession,
        usuario_actual: Usuario,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Registra o actualiza una cuenta de usuario tipo Consultor_Reporte junto con su perfil
        DestinatarioReporte y despacha al correo institucional el enlace para crear su contraseña.
        """
        email_dest = str(payload.get("email") or "").strip().lower()
        nombre_dest = str(payload.get("nombre_completo") or "").strip()
        cargo_dest = str(payload.get("cargo") or "").strip()
        unidad_dest = str(payload.get("unidad_academica") or "").strip()

        if not email_dest or not nombre_dest or not cargo_dest or not unidad_dest:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debe indicar nombre completo, correo institucional, cargo y carrera/unidad.",
            )

        ahora = datetime.now()
        stmt_dest = select(DestinatarioReporte).where(DestinatarioReporte.email == email_dest)
        destinatario = (await session.execute(stmt_dest)).scalar_one_or_none()

        if not destinatario:
            destinatario = DestinatarioReporte(
                email=email_dest,
                nombre_completo=nombre_dest,
                cargo=cargo_dest,
                unidad_academica=unidad_dest,
                token_portal=secrets.token_urlsafe(32),
                activo=True,
                creado_en=ahora,
                actualizado_en=ahora,
            )
            session.add(destinatario)
            await session.flush()
        else:
            destinatario.nombre_completo = nombre_dest
            destinatario.cargo = cargo_dest
            destinatario.unidad_academica = unidad_dest
            destinatario.activo = True
            destinatario.actualizado_en = ahora

        usuario_dest, token_plano = await cls._asegurar_usuario_consultor_reporte(
            session=session,
            email_dest=email_dest,
            nombre_dest=nombre_dest,
            creador_id=usuario_actual.id,
            forzar_nuevo_token=True,
        )

        await session.commit()
        await session.refresh(destinatario)

        base_url = (settings.FRONTEND_URL or "http://localhost:3000").rstrip("/")
        enlace_portal = f"{base_url}/mis-reportes/{destinatario.token_portal}"
        enlace_activacion = f"{base_url}/activar-cuenta?token={token_plano}" if token_plano else None

        correo_enviado = False
        if enlace_activacion:
            correo_enviado = await enviar_correo_activacion_consultor(
                destinatario=destinatario.email,
                nombre_destinatario=destinatario.nombre_completo,
                cargo=destinatario.cargo,
                unidad_academica=destinatario.unidad_academica,
                enlace_activacion=enlace_activacion,
                enlace_portal=enlace_portal,
            )

        cuenta_activada = bool(
            usuario_dest.is_active
            and usuario_dest.hashed_password != "PENDIENTE_ACTIVACION"
            and usuario_dest.hashed_password.startswith("$2")
        )

        return {
            "id": destinatario.id,
            "usuario_id": usuario_dest.id,
            "nombre_completo": destinatario.nombre_completo,
            "email": destinatario.email,
            "cargo": destinatario.cargo,
            "unidad_academica": destinatario.unidad_academica,
            "token_portal": destinatario.token_portal,
            "activo": destinatario.activo,
            "cuenta_activada": cuenta_activada,
            "enlace_activacion": enlace_activacion,
            "correo_enviado": correo_enviado,
        }

    @classmethod
    async def crear_reporte_compartido(
        cls,
        session: AsyncSession,
        usuario_actual: Usuario,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Crea un reporte compartido, registra/actualiza el perfil Consultor_Reporte y despacha el correo."""
        email_dest = str(payload.get("destinatario_email") or "").strip().lower()
        nombre_dest = str(payload.get("destinatario_nombre") or "").strip()
        cargo_dest = str(payload.get("destinatario_cargo") or "").strip()
        unidad_dest = str(payload.get("destinatario_unidad") or "").strip()

        if not email_dest or not nombre_dest or not cargo_dest or not unidad_dest:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debe seleccionar un usuario Consultor de Reporte o completar sus datos institucionales.",
            )

        stmt_dest = select(DestinatarioReporte).where(DestinatarioReporte.email == email_dest)
        destinatario = (await session.execute(stmt_dest)).scalar_one_or_none()
        ahora = datetime.now()
        es_nuevo_destinatario = destinatario is None

        if not destinatario:
            destinatario = DestinatarioReporte(
                email=email_dest,
                nombre_completo=nombre_dest,
                cargo=cargo_dest,
                unidad_academica=unidad_dest,
                token_portal=secrets.token_urlsafe(32),
                activo=True,
                creado_en=ahora,
                actualizado_en=ahora,
            )
            session.add(destinatario)
            await session.flush()
        else:
            destinatario.nombre_completo = nombre_dest
            destinatario.cargo = cargo_dest
            destinatario.unidad_academica = unidad_dest
            destinatario.actualizado_en = ahora

        usuario_dest, token_activacion_plano = await cls._asegurar_usuario_consultor_reporte(
            session=session,
            email_dest=email_dest,
            nombre_dest=nombre_dest,
            creador_id=usuario_actual.id,
            forzar_nuevo_token=es_nuevo_destinatario,
        )

        espacio_id = int(payload.get("espacio_id") or 1)
        fecha_inicio = payload.get("fecha_inicio")
        fecha_fin = payload.get("fecha_fin")
        if isinstance(fecha_inicio, str):
            fecha_inicio = date.fromisoformat(fecha_inicio)
        if isinstance(fecha_fin, str):
            fecha_fin = date.fromisoformat(fecha_fin)

        filtros_bloqueados = payload.get("filtros_bloqueados") or {}
        graficos_visibles = payload.get("graficos_visibles") or (
            ["flujo_horario", "evolucion_semanal", "comparativa_salas", "distribucion_curricular"]
            if espacio_id == 1
            else ["flujo_horario_vehicular", "evolucion_diaria_vehicular", "composicion_flota", "estadisticas_camaras"]
        )
        indicadores_visibles = payload.get("indicadores_visibles") or (
            [i["id"] for i in CATALOGO_INDICADORES_BIBLIOTECA]
            if espacio_id == 1
            else [i["id"] for i in CATALOGO_INDICADORES_ESTACIONAMIENTO]
        )
        modo_datos = str(payload.get("modo_datos") or "dinamico_acotado")
        notas_items = payload.get("notas_items") or []

        datos_instantanea_str: Optional[str] = None
        if modo_datos == "instantanea_fija":
            datos_ensamblados = await cls.ensamblar_datos_reporte_confinado(
                session=session,
                espacio_id=espacio_id,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                filtros=filtros_bloqueados,
                graficos_visibles=graficos_visibles,
                indicadores_visibles=indicadores_visibles,
            )
            datos_instantanea_str = _serializar_json_seguro(datos_ensamblados)

        expira_en = payload.get("expira_en")
        if isinstance(expira_en, str) and expira_en.strip():
            expira_en = datetime.fromisoformat(expira_en.replace("Z", ""))
        elif not isinstance(expira_en, datetime):
            expira_en = None

        token_acceso = secrets.token_urlsafe(32)
        codigo_corto = f"UCT-{ahora.year}-{secrets.token_hex(3).upper()}"

        nuevo_reporte = ReporteCompartido(
            id=uuid.uuid4(),
            token_acceso=token_acceso,
            codigo_corto=codigo_corto,
            creado_por_id=usuario_actual.id,
            destinatario_id=destinatario.id,
            espacio_id=espacio_id,
            titulo_reporte=str(payload.get("titulo_reporte") or "Reporte Ejecutivo Institucional").strip(),
            finalidad_reporte=str(payload.get("finalidad_reporte") or "Análisis de gestión académica").strip(),
            nota_general=str(payload.get("nota_general") or "").strip() or None,
            notas_items_json=_serializar_json_seguro(notas_items),
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            modo_datos=modo_datos,
            filtros_bloqueados_json=_serializar_json_seguro(filtros_bloqueados),
            graficos_visibles_json=_serializar_json_seguro(graficos_visibles),
            indicadores_visibles_json=_serializar_json_seguro(indicadores_visibles),
            datos_instantanea_json=datos_instantanea_str,
            permitir_exportacion=bool(payload.get("permitir_exportacion", True)),
            permitir_ia=bool(payload.get("permitir_ia", False)),
            activo=True,
            expira_en=expira_en,
            total_accesos=0,
            creado_en=ahora,
        )

        session.add(nuevo_reporte)
        await session.commit()
        await session.refresh(nuevo_reporte)
        await session.refresh(destinatario)

        base_url = (settings.FRONTEND_URL or "http://localhost:3000").rstrip("/")
        enlace_reporte = f"{base_url}/reporte-compartido/{nuevo_reporte.token_acceso}"
        enlace_portal = f"{base_url}/mis-reportes/{destinatario.token_portal}"
        enlace_activacion = (
            f"{base_url}/activar-cuenta?token={token_activacion_plano}" if token_activacion_plano else None
        )

        correo_enviado = await enviar_correo_reporte_ejecutivo(
            destinatario=destinatario.email,
            nombre_destinatario=destinatario.nombre_completo,
            cargo=destinatario.cargo,
            unidad_academica=destinatario.unidad_academica,
            titulo_reporte=nuevo_reporte.titulo_reporte,
            codigo_corto=nuevo_reporte.codigo_corto,
            espacio_nombre="Biblioteca CSF" if nuevo_reporte.espacio_id == 1 else "Estacionamiento CSF",
            periodo_texto=f"{nuevo_reporte.fecha_inicio.isoformat()} al {nuevo_reporte.fecha_fin.isoformat()}",
            finalidad_reporte=nuevo_reporte.finalidad_reporte,
            nota_general=nuevo_reporte.nota_general,
            enlace_reporte=enlace_reporte,
            enlace_portal=enlace_portal,
            enlace_activacion_pendiente=enlace_activacion,
        )

        resumen = cls._formatear_resumen_reporte(nuevo_reporte, destinatario)
        resumen["correo_enviado"] = correo_enviado
        resumen["enlace_activacion"] = enlace_activacion
        return resumen

    @staticmethod
    def _formatear_resumen_reporte(
        reporte: ReporteCompartido,
        destinatario: Optional[DestinatarioReporte] = None,
    ) -> Dict[str, Any]:
        dest = destinatario or reporte.destinatario
        ahora = datetime.now()
        expirado = bool(reporte.expira_en and reporte.expira_en < ahora)
        vigente = bool(reporte.activo and (dest.activo if dest else True) and not expirado)

        return {
            "id": str(reporte.id),
            "codigo_corto": reporte.codigo_corto,
            "token_acceso": reporte.token_acceso,
            "espacio_id": reporte.espacio_id,
            "espacio_nombre": "Biblioteca CSF" if reporte.espacio_id == 1 else "Estacionamiento CSF",
            "titulo_reporte": reporte.titulo_reporte,
            "finalidad_reporte": reporte.finalidad_reporte,
            "nota_general": reporte.nota_general or "",
            "notas_items": _cargar_json_seguro(reporte.notas_items_json, []),
            "fecha_inicio": reporte.fecha_inicio.isoformat(),
            "fecha_fin": reporte.fecha_fin.isoformat(),
            "modo_datos": reporte.modo_datos,
            "filtros_bloqueados": _cargar_json_seguro(reporte.filtros_bloqueados_json, {}),
            "graficos_visibles": _cargar_json_seguro(reporte.graficos_visibles_json, []),
            "indicadores_visibles": _cargar_json_seguro(reporte.indicadores_visibles_json, []),
            "permitir_exportacion": reporte.permitir_exportacion,
            "permitir_ia": reporte.permitir_ia,
            "activo": reporte.activo,
            "expirado": expirado,
            "vigente": vigente,
            "expira_en": reporte.expira_en.isoformat() if reporte.expira_en else None,
            "total_accesos": reporte.total_accesos,
            "ultimo_acceso_en": reporte.ultimo_acceso_en.isoformat() if reporte.ultimo_acceso_en else None,
            "creado_en": reporte.creado_en.isoformat() if reporte.creado_en else None,
            "destinatario": {
                "id": dest.id if dest else None,
                "nombre_completo": dest.nombre_completo if dest else "",
                "email": dest.email if dest else "",
                "cargo": dest.cargo if dest else "",
                "unidad_academica": dest.unidad_academica if dest else "",
                "token_portal": dest.token_portal if dest else "",
                "activo": dest.activo if dest else True,
            },
            "creador": {
                "id": reporte.creador.id if reporte.creador else reporte.creado_por_id,
                "nombre_completo": reporte.creador.nombre_completo if reporte.creador else "Sistema DSS",
                "email": reporte.creador.email if reporte.creador else "",
                "rol": (reporte.creador.roles[0].nombre if reporte.creador and reporte.creador.roles else "Usuario"),
            },
        }

    @classmethod
    async def listar_reportes_emitidos(
        cls,
        session: AsyncSession,
        usuario_actual: Usuario,
        espacio_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Devuelve la lista de reportes emitidos y el catálogo de destinatarios registrados según jerarquía RLS."""
        roles_usuario = {r.nombre for r in usuario_actual.roles}
        es_admin = bool({"Admin_Sistema", "SuperAdmin"}.intersection(roles_usuario))
        es_directora = bool({"Directora_Recinto", "Director_Recinto"}.intersection(roles_usuario))

        stmt = (
            select(ReporteCompartido)
            .options(
                selectinload(ReporteCompartido.destinatario),
                selectinload(ReporteCompartido.creador).selectinload(Usuario.roles),
            )
            .order_by(desc(ReporteCompartido.creado_en))
        )
        if not es_admin:
            if es_directora:
                subquery_analistas = select(Usuario.id).where(
                    (Usuario.created_by_user_id == usuario_actual.id) |
                    ((Usuario.espacio_id == usuario_actual.espacio_id) & (Usuario.espacio_id != None))
                )
                stmt = stmt.where(
                    (ReporteCompartido.creado_por_id == usuario_actual.id) |
                    (ReporteCompartido.creado_por_id.in_(subquery_analistas))
                )
            else:
                stmt = stmt.where(ReporteCompartido.creado_por_id == usuario_actual.id)
        if espacio_id is not None:
            stmt = stmt.where(ReporteCompartido.espacio_id == espacio_id)

        filas_reportes = (await session.execute(stmt)).scalars().all()

        stmt_dest = select(DestinatarioReporte).order_by(desc(DestinatarioReporte.actualizado_en))
        filas_dest = (await session.execute(stmt_dest)).scalars().all()

        emails_dest = [d.email for d in filas_dest if d.email]
        mapa_usuarios: Dict[str, Usuario] = {}
        if emails_dest:
            stmt_usrs = select(Usuario).where(Usuario.email.in_(emails_dest))
            for u in (await session.execute(stmt_usrs)).scalars().all():
                mapa_usuarios[u.email.lower()] = u

        return {
            "reportes": [cls._formatear_resumen_reporte(r, r.destinatario) for r in filas_reportes],
            "destinatarios": [
                {
                    "id": d.id,
                    "nombre_completo": d.nombre_completo,
                    "email": d.email,
                    "cargo": d.cargo,
                    "unidad_academica": d.unidad_academica,
                    "token_portal": d.token_portal,
                    "activo": d.activo,
                    "cuenta_activada": bool(
                        d.email.lower() in mapa_usuarios
                        and mapa_usuarios[d.email.lower()].is_active
                        and mapa_usuarios[d.email.lower()].hashed_password != "PENDIENTE_ACTIVACION"
                        and mapa_usuarios[d.email.lower()].hashed_password.startswith("$2")
                    ),
                    "total_reportes": len(d.reportes or []),
                    "actualizado_en": d.actualizado_en.isoformat() if d.actualizado_en else None,
                }
                for d in filas_dest
            ],
            "catalogos": {
                "1": {
                    "graficos": CATALOGO_GRAFICOS_BIBLIOTECA,
                    "indicadores": CATALOGO_INDICADORES_BIBLIOTECA,
                },
                "2": {
                    "graficos": CATALOGO_GRAFICOS_ESTACIONAMIENTO,
                    "indicadores": CATALOGO_INDICADORES_ESTACIONAMIENTO,
                },
            },
        }

    @classmethod
    async def actualizar_estado_y_configuracion_reporte(
        cls,
        session: AsyncSession,
        usuario_actual: Usuario,
        reporte_id: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Permite habilitar/deshabilitar el link, habilitar/deshabilitar IA, editar vigencia, notas y gráficos."""
        try:
            uuid_obj = uuid.UUID(str(reporte_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="Identificador de reporte inválido.")

        stmt = (
            select(ReporteCompartido)
            .options(selectinload(ReporteCompartido.destinatario))
            .where(ReporteCompartido.id == uuid_obj)
        )
        reporte = (await session.execute(stmt)).scalar_one_or_none()
        if not reporte:
            raise HTTPException(status_code=404, detail="Reporte compartido no encontrado.")

        roles_usuario = {r.nombre for r in usuario_actual.roles}
        es_admin = "Admin_Sistema" in roles_usuario or "SuperAdmin" in roles_usuario
        if not es_admin and reporte.creado_por_id != usuario_actual.id:
            raise HTTPException(status_code=403, detail="No tiene permisos para modificar este reporte.")

        estaba_activo = bool(reporte.activo)
        se_habilito_ahora = False
        if "activo" in payload and payload["activo"] is not None:
            nuevo_activo = bool(payload["activo"])
            if not estaba_activo and nuevo_activo:
                se_habilito_ahora = True
            reporte.activo = nuevo_activo
        if "permitir_ia" in payload and payload["permitir_ia"] is not None:
            reporte.permitir_ia = bool(payload["permitir_ia"])
        if "permitir_exportacion" in payload and payload["permitir_exportacion"] is not None:
            reporte.permitir_exportacion = bool(payload["permitir_exportacion"])
        if "titulo_reporte" in payload and payload["titulo_reporte"]:
            reporte.titulo_reporte = str(payload["titulo_reporte"]).strip()
        if "finalidad_reporte" in payload and payload["finalidad_reporte"]:
            reporte.finalidad_reporte = str(payload["finalidad_reporte"]).strip()
        if "nota_general" in payload:
            reporte.nota_general = str(payload["nota_general"] or "").strip() or None
        if "notas_items" in payload and payload["notas_items"] is not None:
            reporte.notas_items_json = _serializar_json_seguro(payload["notas_items"])
        if "graficos_visibles" in payload and payload["graficos_visibles"] is not None:
            reporte.graficos_visibles_json = _serializar_json_seguro(payload["graficos_visibles"])
        if "indicadores_visibles" in payload and payload["indicadores_visibles"] is not None:
            reporte.indicadores_visibles_json = _serializar_json_seguro(payload["indicadores_visibles"])
        if "expira_en" in payload:
            val_exp = payload["expira_en"]
            if not val_exp:
                reporte.expira_en = None
            elif isinstance(val_exp, str):
                reporte.expira_en = datetime.fromisoformat(val_exp.replace("Z", ""))

        await session.commit()
        await session.refresh(reporte)

        correo_enviado = False
        reenviar_correo = bool(payload.get("reenviar_correo", False))
        dest = reporte.destinatario
        if (se_habilito_ahora or reenviar_correo) and reporte.activo and dest:
            _, token_act_plano = await cls._asegurar_usuario_consultor_reporte(
                session=session,
                email_dest=dest.email,
                nombre_dest=dest.nombre_completo,
                creador_id=usuario_actual.id,
            )
            await session.commit()
            base_url = (settings.FRONTEND_URL or "http://localhost:3000").rstrip("/")
            enlace_reporte = f"{base_url}/reporte-compartido/{reporte.token_acceso}"
            enlace_portal = f"{base_url}/mis-reportes/{dest.token_portal}"
            enlace_activacion = (
                f"{base_url}/activar-cuenta?token={token_act_plano}" if token_act_plano else None
            )
            correo_enviado = await enviar_correo_reporte_ejecutivo(
                destinatario=dest.email,
                nombre_destinatario=dest.nombre_completo,
                cargo=dest.cargo,
                unidad_academica=dest.unidad_academica,
                titulo_reporte=reporte.titulo_reporte,
                codigo_corto=reporte.codigo_corto,
                espacio_nombre="Biblioteca CSF" if reporte.espacio_id == 1 else "Estacionamiento CSF",
                periodo_texto=f"{reporte.fecha_inicio.isoformat()} al {reporte.fecha_fin.isoformat()}",
                finalidad_reporte=reporte.finalidad_reporte,
                nota_general=reporte.nota_general,
                enlace_reporte=enlace_reporte,
                enlace_portal=enlace_portal,
                enlace_activacion_pendiente=enlace_activacion,
            )

        resumen = cls._formatear_resumen_reporte(reporte, reporte.destinatario)
        resumen["correo_enviado"] = correo_enviado
        return resumen

    @classmethod
    async def obtener_mis_reportes_consultor(
        cls,
        session: AsyncSession,
        usuario_actual: Usuario,
    ) -> Dict[str, Any]:
        """Devuelve la bandeja histórica de reportes para el usuario Consultor_Reporte autenticado."""
        stmt = (
            select(DestinatarioReporte)
            .options(selectinload(DestinatarioReporte.reportes))
            .where(DestinatarioReporte.email == usuario_actual.email.lower())
        )
        dest = (await session.execute(stmt)).scalar_one_or_none()
        if not dest:
            return {
                "destinatario": {
                    "id": 0,
                    "nombre_completo": usuario_actual.nombre_completo,
                    "email": usuario_actual.email,
                    "cargo": "Consultor de Reportes",
                    "unidad_academica": "Universidad Católica de Temuco",
                    "token_portal": "",
                },
                "reportes": [],
            }
        return await cls.obtener_portal_destinatario_por_token(session=session, token_portal=dest.token_portal)

    @classmethod
    async def actualizar_estado_destinatario(
        cls,
        session: AsyncSession,
        destinatario_id: int,
        activo: bool,
    ) -> Dict[str, Any]:
        stmt = select(DestinatarioReporte).where(DestinatarioReporte.id == destinatario_id)
        dest = (await session.execute(stmt)).scalar_one_or_none()
        if not dest:
            raise HTTPException(status_code=404, detail="Destinatario no encontrado.")
        dest.activo = bool(activo)
        dest.actualizado_en = datetime.now()
        await session.commit()
        await session.refresh(dest)
        return {
            "id": dest.id,
            "nombre_completo": dest.nombre_completo,
            "email": dest.email,
            "activo": dest.activo,
        }

    @classmethod
    async def eliminar_destinatario_consultor(
        cls,
        session: AsyncSession,
        usuario_actual: Usuario,
        destinatario_id: int,
    ) -> Dict[str, Any]:
        """
        Elimina el registro del usuario Consultor de Reportes (DestinatarioReporte y sus reportes asociados)
        y elimina también su cuenta Usuario en el sistema.
        """
        from sqlalchemy import delete as sql_delete
        from app.services.auth_service import limpiar_cache_usuario

        stmt = select(DestinatarioReporte).where(DestinatarioReporte.id == destinatario_id)
        dest = (await session.execute(stmt)).scalar_one_or_none()
        if not dest:
            raise HTTPException(status_code=404, detail="Usuario consultor de reportes no encontrado.")

        email_dest = dest.email.lower()

        # Eliminar explícitamente auditorías y reportes compartidos asociados a este destinatario
        stmt_reps = select(ReporteCompartido.id).where(ReporteCompartido.destinatario_id == destinatario_id)
        rep_ids = list((await session.execute(stmt_reps)).scalars().all())
        if rep_ids:
            await session.execute(
                sql_delete(AuditoriaAccesoReporte).where(AuditoriaAccesoReporte.reporte_id.in_(rep_ids))
            )
            await session.execute(
                sql_delete(ReporteCompartido).where(ReporteCompartido.id.in_(rep_ids))
            )
        await session.execute(
            sql_delete(DestinatarioReporte).where(DestinatarioReporte.id == destinatario_id)
        )

        CUENTAS_SISTEMA_PROTEGIDAS = {"admin@uct.cl", "directivo@uct.cl", "analista@uct.cl", "guardia@uct.cl"}
        stmt_usr = select(Usuario).where(Usuario.email == email_dest)
        usr = (await session.execute(stmt_usr)).scalar_one_or_none()
        if usr and usr.id != usuario_actual.id and email_dest not in CUENTAS_SISTEMA_PROTEGIDAS:
            limpiar_cache_usuario(usr.id)
            await session.execute(sql_delete(TokenActivacion).where(TokenActivacion.usuario_id == usr.id))
            await session.execute(sql_delete(UsuarioRol).where(UsuarioRol.usuario_id == usr.id))
            await session.execute(sql_delete(Usuario).where(Usuario.id == usr.id))

        await session.commit()
        return {"eliminado": True, "id": destinatario_id, "email": email_dest}

    @classmethod
    async def eliminar_reporte_compartido(
        cls,
        session: AsyncSession,
        usuario_actual: Usuario,
        reporte_id: str,
    ) -> Dict[str, Any]:
        try:
            uuid_obj = uuid.UUID(str(reporte_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="Identificador inválido.")

        stmt = select(ReporteCompartido).where(ReporteCompartido.id == uuid_obj)
        reporte = (await session.execute(stmt)).scalar_one_or_none()
        if not reporte:
            raise HTTPException(status_code=404, detail="Reporte no encontrado.")

        roles_usuario = {r.nombre for r in usuario_actual.roles}
        es_admin = "Admin_Sistema" in roles_usuario or "SuperAdmin" in roles_usuario
        if not es_admin and reporte.creado_por_id != usuario_actual.id:
            raise HTTPException(status_code=403, detail="No autorizado para eliminar este reporte.")

        await session.delete(reporte)
        await session.commit()
        return {"eliminado": True, "id": str(reporte_id)}

    @classmethod
    async def obtener_reporte_publico_por_token(
        cls,
        session: AsyncSession,
        token_acceso: str,
        ip_origen: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Resuelve un reporte público confinado por su token_acceso.
        Verifica estado activo y expiración, registra auditoría y devuelve el historial del destinatario.
        """
        stmt = (
            select(ReporteCompartido)
            .options(selectinload(ReporteCompartido.destinatario).selectinload(DestinatarioReporte.reportes))
            .where(ReporteCompartido.token_acceso == token_acceso)
        )
        reporte = (await session.execute(stmt)).scalar_one_or_none()
        if not reporte:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="El enlace de reporte solicitado no existe.",
            )

        dest = reporte.destinatario
        if not reporte.activo or (dest and not dest.activo):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Este reporte ejecutivo ha sido deshabilitado por el emisor institucional.",
            )

        ahora = datetime.now()
        if reporte.expira_en and reporte.expira_en < ahora:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail=f"El plazo de vigencia de este reporte expiró el {reporte.expira_en.strftime('%d-%m-%Y %H:%M')}.",
            )

        # Registrar acceso en auditoría
        reporte.total_accesos = int(reporte.total_accesos or 0) + 1
        reporte.ultimo_acceso_en = ahora
        session.add(
            AuditoriaAccesoReporte(
                reporte_id=reporte.id,
                fecha_hora=ahora,
                ip_origen=ip_origen,
                accion="apertura_reporte",
            )
        )
        await session.commit()

        filtros_bloqueados = _cargar_json_seguro(reporte.filtros_bloqueados_json, {})
        graficos_visibles = _cargar_json_seguro(reporte.graficos_visibles_json, [])
        indicadores_visibles = _cargar_json_seguro(reporte.indicadores_visibles_json, [])

        if reporte.modo_datos == "instantanea_fija" and reporte.datos_instantanea_json:
            datos_confinados = _cargar_json_seguro(reporte.datos_instantanea_json, {})
            ind_ej_guardados = datos_confinados.get("indicadores_ejecutivos") or {}
            ids_cat_actual = {
                i["id"]
                for i in (
                    CATALOGO_INDICADORES_BIBLIOTECA
                    if reporte.espacio_id == 1
                    else CATALOGO_INDICADORES_ESTACIONAMIENTO
                )
            }
            ind_vis_guardados = datos_confinados.get("indicadores_visibles") or []
            if (
                "dias_operativos" not in ind_ej_guardados
                or not any(i in ids_cat_actual for i in ind_vis_guardados)
            ):
                datos_confinados = await cls.ensamblar_datos_reporte_confinado(
                    session=session,
                    espacio_id=reporte.espacio_id,
                    fecha_inicio=reporte.fecha_inicio,
                    fecha_fin=reporte.fecha_fin,
                    filtros=filtros_bloqueados,
                    graficos_visibles=graficos_visibles,
                    indicadores_visibles=indicadores_visibles,
                )
                reporte.datos_instantanea_json = _serializar_json_seguro(datos_confinados)
                reporte.indicadores_visibles_json = _serializar_json_seguro(
                    datos_confinados.get("indicadores_visibles", [])
                )
                await session.commit()
        else:
            datos_confinados = await cls.ensamblar_datos_reporte_confinado(
                session=session,
                espacio_id=reporte.espacio_id,
                fecha_inicio=reporte.fecha_inicio,
                fecha_fin=reporte.fecha_fin,
                filtros=filtros_bloqueados,
                graficos_visibles=graficos_visibles,
                indicadores_visibles=indicadores_visibles,
            )

        # Historial de todos los reportes enviados al mismo destinatario
        historial_destinatario = []
        if dest and dest.reportes:
            for rep_hist in sorted(dest.reportes, key=lambda x: x.creado_en or ahora, reverse=True):
                exp_h = bool(rep_hist.expira_en and rep_hist.expira_en < ahora)
                historial_destinatario.append(
                    {
                        "id": str(rep_hist.id),
                        "codigo_corto": rep_hist.codigo_corto,
                        "token_acceso": rep_hist.token_acceso,
                        "titulo_reporte": rep_hist.titulo_reporte,
                        "finalidad_reporte": rep_hist.finalidad_reporte,
                        "espacio_id": rep_hist.espacio_id,
                        "espacio_nombre": "Biblioteca CSF" if rep_hist.espacio_id == 1 else "Estacionamiento CSF",
                        "fecha_inicio": rep_hist.fecha_inicio.isoformat(),
                        "fecha_fin": rep_hist.fecha_fin.isoformat(),
                        "creado_en": rep_hist.creado_en.isoformat() if rep_hist.creado_en else None,
                        "vigente": bool(rep_hist.activo and not exp_h),
                        "activo": rep_hist.activo,
                        "expirado": exp_h,
                        "es_actual": rep_hist.id == reporte.id,
                    }
                )

        # Verificar si el usuario Consultor_Reporte ya creó su contraseña o si es nuevo y debe definirla
        requiere_crear_password = False
        token_activacion_pendiente: Optional[str] = None
        if dest:
            usr_dest, token_act = await cls._asegurar_usuario_consultor_reporte(
                session=session,
                email_dest=dest.email,
                nombre_dest=dest.nombre_completo,
                creador_id=reporte.creado_por_id,
            )
            await session.commit()
            if (
                usr_dest.hashed_password == "PENDIENTE_ACTIVACION"
                or not usr_dest.hashed_password.startswith("$2")
            ):
                requiere_crear_password = True
                token_activacion_pendiente = token_act

        return {
            "reporte": cls._formatear_resumen_reporte(reporte, dest),
            "datos": datos_confinados,
            "historial_destinatario": historial_destinatario,
            "requiere_crear_password": requiere_crear_password,
            "token_activacion": token_activacion_pendiente,
            "catalogos": {
                "graficos": (
                    CATALOGO_GRAFICOS_BIBLIOTECA
                    if reporte.espacio_id == 1
                    else CATALOGO_GRAFICOS_ESTACIONAMIENTO
                ),
                "indicadores": (
                    CATALOGO_INDICADORES_BIBLIOTECA
                    if reporte.espacio_id == 1
                    else CATALOGO_INDICADORES_ESTACIONAMIENTO
                ),
            },
        }

    @classmethod
    async def obtener_portal_destinatario_por_token(
        cls,
        session: AsyncSession,
        token_portal: str,
    ) -> Dict[str, Any]:
        """Devuelve la bandeja histórica completa de reportes de un destinatario."""
        stmt = (
            select(DestinatarioReporte)
            .options(selectinload(DestinatarioReporte.reportes))
            .where(DestinatarioReporte.token_portal == token_portal)
        )
        dest = (await session.execute(stmt)).scalar_one_or_none()
        if not dest:
            raise HTTPException(status_code=404, detail="Bandeja de destinatario no encontrada.")
        if not dest.activo:
            raise HTTPException(status_code=403, detail="La cuenta de destinatario se encuentra deshabilitada.")

        ahora = datetime.now()
        reportes_lista = []
        for rep in sorted(dest.reportes or [], key=lambda r: r.creado_en or ahora, reverse=True):
            exp_h = bool(rep.expira_en and rep.expira_en < ahora)
            reportes_lista.append(
                {
                    "id": str(rep.id),
                    "codigo_corto": rep.codigo_corto,
                    "token_acceso": rep.token_acceso,
                    "titulo_reporte": rep.titulo_reporte,
                    "finalidad_reporte": rep.finalidad_reporte,
                    "nota_general": rep.nota_general or "",
                    "espacio_id": rep.espacio_id,
                    "espacio_nombre": "Biblioteca CSF" if rep.espacio_id == 1 else "Estacionamiento CSF",
                    "fecha_inicio": rep.fecha_inicio.isoformat(),
                    "fecha_fin": rep.fecha_fin.isoformat(),
                    "creado_en": rep.creado_en.isoformat() if rep.creado_en else None,
                    "expira_en": rep.expira_en.isoformat() if rep.expira_en else None,
                    "activo": rep.activo,
                    "expirado": exp_h,
                    "vigente": bool(rep.activo and not exp_h),
                    "permitir_ia": rep.permitir_ia,
                }
            )

        return {
            "destinatario": {
                "id": dest.id,
                "nombre_completo": dest.nombre_completo,
                "email": dest.email,
                "cargo": dest.cargo,
                "unidad_academica": dest.unidad_academica,
                "token_portal": dest.token_portal,
            },
            "reportes": reportes_lista,
        }

    @classmethod
    async def consultar_ia_reporte_confinado(
        cls,
        session: AsyncSession,
        token_acceso: str,
        pregunta: str,
        ip_origen: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Ejecuta una consulta al asistente IA estrictamente confinada a los datos del reporte compartido.
        Solo funciona cuando reporte.permitir_ia == True.
        """
        stmt = (
            select(ReporteCompartido)
            .options(selectinload(ReporteCompartido.destinatario))
            .where(ReporteCompartido.token_acceso == token_acceso)
        )
        reporte = (await session.execute(stmt)).scalar_one_or_none()
        if not reporte:
            raise HTTPException(status_code=404, detail="Reporte no encontrado.")

        if not reporte.activo or (reporte.destinatario and not reporte.destinatario.activo):
            raise HTTPException(status_code=403, detail="Este reporte se encuentra deshabilitado.")

        if reporte.expira_en and reporte.expira_en < datetime.now():
            raise HTTPException(status_code=410, detail="Este reporte ha expirado.")

        if not reporte.permitir_ia:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El asistente de IA no está habilitado para este reporte compartido.",
            )

        filtros_bloqueados = _cargar_json_seguro(reporte.filtros_bloqueados_json, {})
        graficos_visibles = _cargar_json_seguro(reporte.graficos_visibles_json, [])
        indicadores_visibles = _cargar_json_seguro(reporte.indicadores_visibles_json, [])

        if reporte.modo_datos == "instantanea_fija" and reporte.datos_instantanea_json:
            datos_confinados = _cargar_json_seguro(reporte.datos_instantanea_json, {})
            ind_ej_guardados = datos_confinados.get("indicadores_ejecutivos") or {}
            ids_cat_actual = {
                i["id"]
                for i in (
                    CATALOGO_INDICADORES_BIBLIOTECA
                    if reporte.espacio_id == 1
                    else CATALOGO_INDICADORES_ESTACIONAMIENTO
                )
            }
            ind_vis_guardados = datos_confinados.get("indicadores_visibles") or []
            if (
                "dias_operativos" not in ind_ej_guardados
                or not any(i in ids_cat_actual for i in ind_vis_guardados)
            ):
                datos_confinados = await cls.ensamblar_datos_reporte_confinado(
                    session=session,
                    espacio_id=reporte.espacio_id,
                    fecha_inicio=reporte.fecha_inicio,
                    fecha_fin=reporte.fecha_fin,
                    filtros=filtros_bloqueados,
                    graficos_visibles=graficos_visibles,
                    indicadores_visibles=indicadores_visibles,
                )
                reporte.datos_instantanea_json = _serializar_json_seguro(datos_confinados)
                reporte.indicadores_visibles_json = _serializar_json_seguro(
                    datos_confinados.get("indicadores_visibles", [])
                )
                await session.commit()
        else:
            datos_confinados = await cls.ensamblar_datos_reporte_confinado(
                session=session,
                espacio_id=reporte.espacio_id,
                fecha_inicio=reporte.fecha_inicio,
                fecha_fin=reporte.fecha_fin,
                filtros=filtros_bloqueados,
                graficos_visibles=graficos_visibles,
                indicadores_visibles=indicadores_visibles,
            )

        resumen_contexto = {
            "titulo_reporte": reporte.titulo_reporte,
            "finalidad": reporte.finalidad_reporte,
            "destinatario": {
                "nombre": reporte.destinatario.nombre_completo if reporte.destinatario else "",
                "cargo": reporte.destinatario.cargo if reporte.destinatario else "",
                "unidad": reporte.destinatario.unidad_academica if reporte.destinatario else "",
            },
            "recinto": "Biblioteca CSF" if reporte.espacio_id == 1 else "Estacionamiento CSF",
            "periodo": f"{reporte.fecha_inicio.isoformat()} a {reporte.fecha_fin.isoformat()}",
            "filtros_aplicados": filtros_bloqueados,
            "nota_general_emisor": reporte.nota_general or "",
            "notas_especificas_emisor": _cargar_json_seguro(reporte.notas_items_json, []),
            "indicadores_ejecutivos": datos_confinados.get("indicadores_ejecutivos", {}),
            "kpis_base": datos_confinados.get("kpis_base", {}),
        }

        instruccion_sistema = (
            "Eres el Asistente Analítico Ejecutivo del DSS de la Universidad Católica de Temuco. "
            "DIRECTIVA ESTRICTA DE CONFINAMIENTO: Estás respondiendo dentro de un Reporte Ejecutivo Compartido con alcance cerrado. "
            "ÚNICAMENTE puedes utilizar las cifras, notas e indicadores incluidos en el JSON de contexto adjunto. "
            "Si el usuario pregunta por otras carreras, otros períodos o recintos fuera de este reporte, "
            "indica cortésmente que tu alcance está confinado exclusivamente a los datos sellados en este reporte ejecutivo. "
            "Responde siempre en español claro, ejecutivo y conciso."
        )

        prompt_completo = (
            f"CONTEXTO SELLADO DEL REPORTE EJECUTIVO:\n{_serializar_json_seguro(resumen_contexto)}\n\n"
            f"CONSULTA DEL DESTINATARIO:\n{pregunta}"
        )

        session.add(
            AuditoriaAccesoReporte(
                reporte_id=reporte.id,
                fecha_hora=datetime.now(),
                ip_origen=ip_origen,
                accion="consulta_ia_confinada",
            )
        )
        await session.commit()

        cliente_llm = await build_llm_client(session, reporte.espacio_id)
        respuesta_texto = await cliente_llm.generate_response(
            prompt=prompt_completo,
            system_instruction=instruccion_sistema,
            temperature=0.15,
        )

        return {
            "respuesta": respuesta_texto or "No fue posible generar una síntesis con los datos actuales.",
            "timestamp": datetime.now().isoformat(),
        }

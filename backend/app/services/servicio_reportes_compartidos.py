import asyncio
import json
import logging
import re
import secrets
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy import case, desc, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer, selectinload

from app.core.config import settings, obtener_url_frontend
from app.core.tiempo import ZONA_CHILE, ahora_chile_naive, marcar_chile
from app.domain.auth_models import Rol, TokenActivacion, Usuario, UsuarioRol
from app.domain.models import Espacio
from app.domain.reportes_compartidos_models import (
    AuditoriaAccesoReporte,
    DestinatarioReporte,
    MensajeIAReporte,
    ReporteCompartido,
)
from app.services.attendance_service import AttendanceService
from app.services.auth_service import generar_token_activacion, limpiar_cache_usuario, normalizar_rol
from app.services.chat.auditoria_chat import registrar_auditoria_chat
from app.services.email_service import (
    enviar_correo_activacion_consultor,
    enviar_correo_reporte_ejecutivo,
)
from app.services.llm_client import build_llm_client
from app.services.vehicle_service import VehicleService

logger = logging.getLogger(__name__)


IDS_CAMPANA_24H_GRANULARES = (
    "campana_24h_resumen",
    "campana_24h_curva_calor",
    "campana_24h_fases_dias",
    "campana_24h_academico",
    "campana_24h_comparativa",
)

CATALOGO_GRAFICOS_BIBLIOTECA = [
    {"id": "aforo_presencia_intervalos", "titulo": "Curva de Presencia Física en Sala por Intervalos de Sesión vs Capacidad Máxima", "seccion": "1. Resumen y Demanda General"},
    {"id": "prophet_presencia_14dias", "titulo": "Pronóstico Continuo de Presencia Física en Sala (Prophet Jerárquico)", "seccion": "1. Resumen y Demanda General"},
    {"id": "distribucion_curricular", "titulo": "Distribución por Carrera y Facultad (Ley 21.719)", "seccion": "1. Resumen y Demanda General"},
    {"id": "perfiles_visita", "titulo": "Perfiles de Estadía y Permanencia (Donut)", "seccion": "1. Resumen y Demanda General"},
    {"id": "flujo_horario", "titulo": "Flujo Horario de Ingresos y Salidas", "seccion": "1. Resumen y Demanda General"},
    {"id": "mapa_calor", "titulo": "Mapa de Calor (Día de Semana x Hora)", "seccion": "1. Resumen y Demanda General"},
    {"id": "comparativa_salas", "titulo": "Comparativa Sala 1 vs Sala 2 (Pecera)", "seccion": "2. Salas y Torniquetes"},
    {"id": "uso_torniquetes", "titulo": "Flujo por Torniquetes y Accesos Universales", "seccion": "2. Salas y Torniquetes"},
    {"id": "frecuencia_marcajes", "titulo": "Distribución de Frecuencia de Marcajes", "seccion": "2. Salas y Torniquetes"},
    {"id": "volumen_mensual", "titulo": "Volumen y Promedio Diario Mensual", "seccion": "3. Evolución e Hitos"},
    {"id": "evolucion_semanal", "titulo": "Evolución Semanal (Semanas ISO)", "seccion": "3. Evolución e Hitos"},
    {"id": "promedio_dia_semana", "titulo": "Promedio de Ingresos por Día de la Semana", "seccion": "3. Evolución e Hitos"},
    {"id": "hitos_academicos", "titulo": "Comparativa por Hito del Calendario Académico", "seccion": "3. Evolución e Hitos"},
    {"id": "campana_24h_resumen", "titulo": "KPIs Nocturnos, Delta 24h y Dictamen Ejecutivo", "seccion": "5. Campaña 24 Horas Exámenes"},
    {"id": "campana_24h_curva_calor", "titulo": "Curva Continua Nocturna (20:00-07:00) y Mapa de Calor", "seccion": "5. Campaña 24 Horas Exámenes"},
    {"id": "campana_24h_fases_dias", "titulo": "Fases de la Noche y Distribución por Día de Semana", "seccion": "5. Campaña 24 Horas Exámenes"},
    {"id": "campana_24h_academico", "titulo": "Top Carreras y Facultades en Horario Nocturno", "seccion": "5. Campaña 24 Horas Exámenes"},
    {"id": "campana_24h_comparativa", "titulo": "Comparativa Multicampaña (Históricas vs Actuales)", "seccion": "5. Campaña 24 Horas Exámenes"},
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
    {"id": "presencia_vehicular_intervalos", "titulo": "Curva de Presencia Física Vehicular por Intervalos de Sesión vs Capacidad", "seccion": "1. Aforo y Pronóstico"},
    {"id": "prophet_vehicular", "titulo": "Pronóstico Continuo Prophet Vehicular (Presencia en Plazas)", "seccion": "1. Aforo y Pronóstico"},
    {"id": "flujo_horario_vehicular", "titulo": "Flujo Horario de Ingresos y Salidas Vehiculares", "seccion": "2. Flujo Horario de Accesos"},
    {"id": "composicion_flota", "titulo": "Composición por Tipo de Vehículo", "seccion": "3. Flota y Cámaras ANPR"},
    {"id": "distribucion_marcas", "titulo": "Distribución por Marca de Vehículo", "seccion": "3. Flota y Cámaras ANPR"},
    {"id": "estadisticas_camaras", "titulo": "Distribución por Pórtico y Cámara ANPR", "seccion": "3. Flota y Cámaras ANPR"},
    {"id": "movilidad_intercampus", "titulo": "Movilidad Intercampus CSF - CHS", "seccion": "4. Movilidad y Calendario"},
    {"id": "hitos_academicos_vehicular", "titulo": "Comparativa por Hito Académico Vehicular", "seccion": "4. Movilidad y Calendario"},
    {"id": "clusters_comportamiento", "titulo": "Perfiles de Uso Vehicular (Clustering K-Means)", "seccion": "5. Machine Learning (K-Means) y Estadía"},
    {"id": "distribucion_estadia", "titulo": "Distribución de Tiempos de Permanencia", "seccion": "5. Machine Learning (K-Means) y Estadía"},
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
    def _es_grafico_campana_24h(grafico_id: str) -> bool:
        return grafico_id == "campana_24_horas" or str(grafico_id).startswith("campana_24h_")

    @classmethod
    def _normalizar_clave_grafico_snapshot(cls, grafico_id: str) -> str:
        return "campana_24_horas" if cls._es_grafico_campana_24h(grafico_id) else grafico_id

    @classmethod
    async def _rango_tiene_campana_24h(
        cls,
        session: AsyncSession,
        espacio_id: int,
        fecha_inicio: Optional[date],
        fecha_fin: Optional[date],
    ) -> bool:
        if espacio_id != 1 or not fecha_inicio or not fecha_fin:
            return False
        from app.domain.config_models import HorarioOperacion

        f_ini_dt = datetime.combine(fecha_inicio, datetime.min.time())
        f_fin_dt = datetime.combine(fecha_fin, datetime.max.time())
        stmt = select(HorarioOperacion.id).where(
            HorarioOperacion.espacio_id == 1,
            HorarioOperacion.activo == True,
            or_(HorarioOperacion.es_continuo_24h == True, HorarioOperacion.tipo_horario == "extendido_24h"),
            or_(HorarioOperacion.fecha_inicio.is_(None), HorarioOperacion.fecha_inicio <= f_fin_dt),
            or_(HorarioOperacion.fecha_fin.is_(None), HorarioOperacion.fecha_fin >= f_ini_dt),
        )
        return (await session.execute(stmt)).first() is not None

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
                incluir_funcionarios=bool(filtros.get("incluir_funcionarios", True)),
                incluir_sin_identificar=bool(filtros.get("incluir_sin_identificar", True)),
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
                cohorte=filtros.get("cohorte") or None,
                incluir_pausas_bano=bool(filtros.get("incluir_pausas_bano", True)),
                desduplicar_rafagas=bool(filtros.get("desduplicar_rafagas", True)),
                incluir_funcionarios=bool(filtros.get("incluir_funcionarios", True)),
                incluir_sin_identificar=bool(filtros.get("incluir_sin_identificar", True)),
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
                    incluir_funcionarios=bool(filtros.get("incluir_funcionarios", True)),
                    incluir_sin_identificar=bool(filtros.get("incluir_sin_identificar", True)),
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
        cap_sala1 = 150
        cap_sala2 = 126
        try:
            salas_bd = await AttendanceService.get_salas_biblioteca(session, 1)
            for s_bd in salas_bd or []:
                cod_s = str(s_bd.get("codigo") or "")
                if "CSF02" in cod_s or s_bd.get("id") == 1:
                    cap_sala1 = int(s_bd.get("capacidad_asientos") or 150)
                elif "CSF04" in cod_s or s_bd.get("id") == 2:
                    cap_sala2 = int(s_bd.get("capacidad_asientos") or 126)
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
            "capacidad_sala1": cap_sala1,
            "capacidad_sala2": cap_sala2,
            "total_registros_sala1": int(kpis_base.get("total_registros_sala1") or 0),
            "total_registros_sala2": int(kpis_base.get("total_registros_sala2") or 0),
            "max_aforo_sala1": int(kpis_base.get("max_aforo_sala1") or 0),
            "max_aforo_sala2": int(kpis_base.get("max_aforo_sala2") or 0),
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
            "total_accesos_csf11": int(kpis_base.get("total_accesos_csf11") or 0),
            "total_accesos_csf21": int(kpis_base.get("total_accesos_csf21") or 0),
            "total_accesos_chs01": int(kpis_base.get("total_accesos_chs01") or 0),
            "max_aforo_csf11": int(kpis_base.get("max_aforo_csf11") or 0),
            "max_aforo_csf21": int(kpis_base.get("max_aforo_csf21") or 0),
            "max_aforo_chs01": int(kpis_base.get("max_aforo_chs01") or 0),
            "capacidad_csf11": int(kpis_base.get("capacidad_csf11") or 40),
            "capacidad_csf21": int(kpis_base.get("capacidad_csf21") or 50),
            "capacidad_chs01": int(kpis_base.get("capacidad_chs01") or 35),
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
        incluir_funcionarios = bool(filtros.get("incluir_funcionarios", True))
        incluir_sin_identificar = bool(filtros.get("incluir_sin_identificar", True))

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
                incluir_funcionarios=incluir_funcionarios,
                incluir_sin_identificar=incluir_sin_identificar,
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
                incluir_funcionarios=incluir_funcionarios,
                incluir_sin_identificar=incluir_sin_identificar,
            )

            from app.services.prediction_service import get_prophet_forecast

            flujo_bib = None
            if "flujo_horario" in graficos_visibles:
                flujo_bib = await AttendanceService.get_hourly_flow(**kwargs_comunes)
                graficos_resultado["flujo_horario"] = flujo_bib

            if "aforo_presencia_intervalos" in graficos_visibles:
                try:
                    graficos_resultado["aforo_presencia_intervalos"] = (
                        await AttendanceService.get_realtime_presence_curve(**kwargs_comunes)
                    )
                except Exception as exc:
                    logger.warning("Fallo aforo_presencia_intervalos en reporte: %s", exc)
                    graficos_resultado["aforo_presencia_intervalos"] = []

            if "prophet_presencia_14dias" in graficos_visibles:
                from app.services.prediction_service import get_prophet_presence_forecast
                sala_raw_p = str(sala or "").lower()
                if "csf02" in sala_raw_p or "sala_1" in sala_raw_p or sala_raw_p == "1":
                    sala_prophet = "sala1"
                elif "csf04" in sala_raw_p or "sala_2" in sala_raw_p or sala_raw_p == "2":
                    sala_prophet = "sala2"
                else:
                    sala_prophet = "todas"
                try:
                    graficos_resultado["prophet_presencia_14dias"] = await get_prophet_presence_forecast(
                        session, sala=sala_prophet
                    )
                except Exception as exc:
                    logger.warning("Fallo prophet_presencia_14dias en reporte: %s", exc)
                    graficos_resultado["prophet_presencia_14dias"] = {}

            if "evolucion_semanal" in graficos_visibles:
                graficos_resultado["evolucion_semanal"] = await AttendanceService.get_weekly_evolution(**kwargs_comunes)
            if "volumen_mensual" in graficos_visibles:
                graficos_resultado["volumen_mensual"] = await AttendanceService.get_monthly_volume(**kwargs_comunes)
            if "mapa_calor" in graficos_visibles:
                graficos_resultado["mapa_calor"] = await AttendanceService.get_heatmap(**kwargs_comunes)
            if "comparativa_salas" in graficos_visibles:
                graficos_resultado["comparativa_salas"] = await AttendanceService.get_rooms_comparison(
                    **kwargs_comunes
                )
            if "promedio_dia_semana" in graficos_visibles:
                graficos_resultado["promedio_dia_semana"] = await AttendanceService.get_daily_average_attendance(
                    **kwargs_comunes
                )
            if "distribucion_curricular" in graficos_visibles:
                graficos_resultado["distribucion_curricular"] = await AttendanceService.get_curricular_distribution(
                    **kwargs_comunes
                )
            if "perfiles_visita" in graficos_visibles:
                graficos_resultado["perfiles_visita"] = await AttendanceService.get_visit_profiles_donut(
                    **kwargs_comunes
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
                    cohorte=cohorte,
                    incluir_pausas_bano=incluir_pausas_bano,
                    desduplicar_rafagas=desduplicar_rafagas,
                    incluir_funcionarios=incluir_funcionarios,
                    incluir_sin_identificar=incluir_sin_identificar,
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
                    cohorte=cohorte,
                    incluir_pausas_bano=incluir_pausas_bano,
                    desduplicar_rafagas=desduplicar_rafagas,
                    incluir_funcionarios=incluir_funcionarios,
                    incluir_sin_identificar=incluir_sin_identificar,
                )
            if any(cls._es_grafico_campana_24h(g) for g in graficos_visibles):
                tiene_24h = await cls._rango_tiene_campana_24h(session, 1, fecha_inicio, fecha_fin)
                if tiene_24h:
                    try:
                        graficos_resultado["campana_24_horas"] = await AttendanceService.get_analisis_24h(
                            session=session,
                            espacio_id=1,
                            fecha_inicio=fecha_inicio,
                            fecha_fin=fecha_fin,
                            bloque_horario="todos",
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
                    except Exception as exc:
                        logger.warning("Fallo analisis 24h en reporte confinado: %s", exc)
                        graficos_resultado["campana_24_horas"] = None
                else:
                    graficos_visibles = [g for g in graficos_visibles if not cls._es_grafico_campana_24h(g)]
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

            if "flujo_horario_vehicular" in graficos_visibles or "prophet_vehicular" in graficos_visibles:
                graficos_resultado["flujo_horario_vehicular"] = flujo_h

            if "presencia_vehicular_intervalos" in graficos_visibles:
                try:
                    graficos_resultado["presencia_vehicular_intervalos"] = (
                        await VehicleService.get_realtime_presence_curve(
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
                    )
                except Exception as exc:
                    logger.warning("Fallo presencia_vehicular_intervalos en reporte: %s", exc)
                    graficos_resultado["presencia_vehicular_intervalos"] = []

            if "prophet_vehicular" in graficos_visibles:
                try:
                    graficos_resultado["prophet_vehicular"] = await get_prophet_forecast(
                        session, recinto="vehicular", sala=sector or "todos"
                    )
                except Exception as exc:
                    logger.warning("Fallo prophet vehicular en reporte: %s", exc)
                    graficos_resultado["prophet_vehicular"] = {}

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
                can_use_ai=True,
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
        background_tasks: Optional[BackgroundTasks] = None,
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
        limpiar_cache_usuario(usuario_dest.id)
        await session.refresh(destinatario)

        base_url = obtener_url_frontend()
        enlace_portal = f"{base_url}/mis-reportes/{destinatario.token_portal}"
        enlace_activacion = f"{base_url}/activar-cuenta?token={token_plano}" if token_plano else None

        correo_enviado = False
        if enlace_activacion:
            kwargs_correo = dict(
                destinatario=destinatario.email,
                nombre_destinatario=destinatario.nombre_completo,
                cargo=destinatario.cargo,
                unidad_academica=destinatario.unidad_academica,
                enlace_activacion=enlace_activacion,
                enlace_portal=enlace_portal,
            )
            if background_tasks is not None:
                background_tasks.add_task(enviar_correo_activacion_consultor, **kwargs_correo)
                correo_enviado = True
            else:
                correo_enviado = await enviar_correo_activacion_consultor(**kwargs_correo)

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
    async def obtener_usuarios_candidatos_consultor(
        cls,
        session: AsyncSession,
        usuario_actual: Optional[Usuario] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retorna la lista de usuarios institucionales activos que pueden ser vinculados
        al rol Consultor_Reporte, filtrada según la jerarquía RBAC/RLS del solicitante.
        """
        es_admin_req = cls._es_admin(usuario_actual) if usuario_actual else True
        espacios_req = cls._espacios_autorizados(usuario_actual) if usuario_actual else None
        if usuario_actual and not es_admin_req and not cls._es_directivo(usuario_actual):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo Administración o Dirección de Recinto pueden listar usuarios candidatos.",
            )

        stmt_users = (
            select(Usuario)
            .options(selectinload(Usuario.roles))
            .where(Usuario.is_active == True)
            .order_by(Usuario.nombre_completo.asc())
        )
        usuarios = (await session.execute(stmt_users)).scalars().all()

        stmt_dest = select(DestinatarioReporte)
        destinatarios = (await session.execute(stmt_dest)).scalars().all()
        dest_por_email = {d.email.strip().lower(): d for d in destinatarios}

        candidatos: List[Dict[str, Any]] = []
        for u in usuarios:
            email_norm = u.email.strip().lower()
            roles_nombres = [r.nombre for r in (u.roles or [])]
            roles_norm = {normalizar_rol(r) for r in roles_nombres}
            if not es_admin_req:
                # Un director no puede enumerar administradores ni usuarios fuera de sus recintos
                if "Admin_Sistema" in roles_norm:
                    continue
                espacios_cand = cls._espacios_autorizados(u)
                if espacios_req is not None and espacios_cand:
                    if not set(espacios_cand).intersection(set(espacios_req)):
                        continue
            es_consultor = "Consultor_Reporte" in roles_norm
            dest_asociado = dest_por_email.get(email_norm)

            cargo_sugerido = "Consultor/a Institucional"
            if dest_asociado and dest_asociado.cargo:
                cargo_sugerido = dest_asociado.cargo
            elif any("Director" in r for r in roles_nombres):
                cargo_sugerido = "Director/a Institucional"
            elif any("Analista" in r for r in roles_nombres):
                cargo_sugerido = "Analista Curricular y de Gestión"
            elif any("Admin" in r for r in roles_nombres):
                cargo_sugerido = "Administrador/a del Sistema DSS"
            elif any("Guardia" in r for r in roles_nombres):
                cargo_sugerido = "Personal de Seguridad del Campus"

            unidad_sugerida = "Universidad Católica de Temuco"
            if dest_asociado and dest_asociado.unidad_academica:
                unidad_sugerida = dest_asociado.unidad_academica

            candidatos.append(
                {
                    "id": u.id,
                    "email": u.email,
                    "nombre_completo": u.nombre_completo,
                    "roles": roles_nombres,
                    "es_consultor": es_consultor,
                    "destinatario_id": dest_asociado.id if dest_asociado else None,
                    "cargo_sugerido": cargo_sugerido,
                    "unidad_sugerida": unidad_sugerida,
                }
            )

        return candidatos

    @classmethod
    async def vincular_usuario_existente_consultor(
        cls,
        session: AsyncSession,
        usuario_actual: Usuario,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Asigna el rol Consultor_Reporte a un usuario institucional existente y crea o actualiza su perfil
        en destinatarios_reportes preservando su contraseña actual (sin forzar nueva contraseña ni enviar correo de activación).
        """
        usuario_id = int(payload.get("usuario_id") or 0)
        cargo = str(payload.get("cargo") or "").strip()
        unidad_academica = str(payload.get("unidad_academica") or "").strip()

        if usuario_id <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debe especificar un usuario institucional válido.",
            )
        if not cargo or not unidad_academica:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debe indicar cargo y carrera o unidad académica del destinatario.",
            )

        es_admin_req = cls._es_admin(usuario_actual)
        if not es_admin_req and not cls._es_directivo(usuario_actual):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo Administración o Dirección de Recinto pueden vincular usuarios existentes.",
            )

        stmt_usr = select(Usuario).options(selectinload(Usuario.roles)).where(Usuario.id == usuario_id)
        usuario = (await session.execute(stmt_usr)).scalar_one_or_none()
        if not usuario or not usuario.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="El usuario seleccionado no existe o se encuentra inactivo.",
            )

        if not es_admin_req:
            roles_obj_norm = {normalizar_rol(r.nombre) for r in (usuario.roles or [])}
            if "Admin_Sistema" in roles_obj_norm:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No puede modificar ni vincular roles de una cuenta Admin_Sistema.",
                )
            espacios_req = cls._espacios_autorizados(usuario_actual) or []
            espacios_obj = cls._espacios_autorizados(usuario) or []
            if espacios_obj and not set(espacios_obj).intersection(set(espacios_req)):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="El usuario seleccionado pertenece a un recinto fuera de su jurisdicción.",
                )

        stmt_rol = select(Rol).where(Rol.nombre == "Consultor_Reporte")
        rol_consultor = (await session.execute(stmt_rol)).scalar_one_or_none()
        if not rol_consultor:
            rol_consultor = Rol(
                nombre="Consultor_Reporte",
                descripcion="Consultor institucional con acceso a reportes ejecutivos compartidos",
            )
            session.add(rol_consultor)
            await session.flush()

        roles_actuales_ids = {r.id for r in (usuario.roles or [])}
        if rol_consultor.id not in roles_actuales_ids:
            session.add(UsuarioRol(usuario_id=usuario.id, rol_id=rol_consultor.id))
            await session.flush()

        email_dest = usuario.email.strip().lower()
        ahora = datetime.now()

        stmt_dest = select(DestinatarioReporte).where(DestinatarioReporte.email == email_dest)
        destinatario = (await session.execute(stmt_dest)).scalar_one_or_none()

        if not destinatario:
            destinatario = DestinatarioReporte(
                email=email_dest,
                nombre_completo=usuario.nombre_completo,
                cargo=cargo,
                unidad_academica=unidad_academica,
                token_portal=secrets.token_urlsafe(32),
                activo=True,
                creado_en=ahora,
                actualizado_en=ahora,
            )
            session.add(destinatario)
            await session.flush()
        else:
            destinatario.nombre_completo = usuario.nombre_completo
            destinatario.cargo = cargo
            destinatario.unidad_academica = unidad_academica
            destinatario.activo = True
            destinatario.actualizado_en = ahora

        await session.commit()
        limpiar_cache_usuario(usuario.id)
        await session.refresh(destinatario)

        cuenta_activada = bool(
            usuario.is_active
            and usuario.hashed_password != "PENDIENTE_ACTIVACION"
            and usuario.hashed_password.startswith("$2")
        )

        return {
            "id": destinatario.id,
            "usuario_id": usuario.id,
            "nombre_completo": destinatario.nombre_completo,
            "email": destinatario.email,
            "cargo": destinatario.cargo,
            "unidad_academica": destinatario.unidad_academica,
            "token_portal": destinatario.token_portal,
            "activo": destinatario.activo,
            "cuenta_activada": cuenta_activada,
            "enlace_activacion": None,
            "correo_enviado": False,
        }

    @classmethod
    async def crear_reporte_compartido(
        cls,
        session: AsyncSession,
        usuario_actual: Usuario,
        payload: Dict[str, Any],
        background_tasks: Optional[BackgroundTasks] = None,
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
            else ["flujo_horario_vehicular", "composicion_flota", "estadisticas_camaras"]
        )
        indicadores_visibles = payload.get("indicadores_visibles") or (
            [i["id"] for i in CATALOGO_INDICADORES_BIBLIOTECA]
            if espacio_id == 1
            else [i["id"] for i in CATALOGO_INDICADORES_ESTACIONAMIENTO]
        )
        modo_datos = str(payload.get("modo_datos") or "dinamico_acotado")
        notas_items = payload.get("notas_items") or []

        if any(cls._es_grafico_campana_24h(g) for g in graficos_visibles):
            if not await cls._rango_tiene_campana_24h(session, espacio_id, fecha_inicio, fecha_fin):
                graficos_visibles = [g for g in graficos_visibles if not cls._es_grafico_campana_24h(g)]
                notas_items = [
                    n for n in notas_items
                    if not (isinstance(n, dict) and cls._es_grafico_campana_24h(str(n.get("seccion") or "")))
                ]

        # Siempre pre-ensamblamos los datos iniciales al emitir el reporte
        # para que tanto en 'instantanea_fija' como en 'dinamico_acotado'
        # la primera visualizacion y la bandeja respondan de inmediato.
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

        expira_en = cls._normalizar_expira_en(payload.get("expira_en"))

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
        limpiar_cache_usuario(usuario_dest.id)
        await session.refresh(nuevo_reporte)
        await session.refresh(destinatario)

        base_url = obtener_url_frontend()
        enlace_reporte = f"{base_url}/reporte-compartido/{nuevo_reporte.token_acceso}"
        enlace_portal = f"{base_url}/mis-reportes/{destinatario.token_portal}"
        enlace_activacion = (
            f"{base_url}/activar-cuenta?token={token_activacion_plano}" if token_activacion_plano else None
        )

        kwargs_correo = dict(
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
        if background_tasks is not None:
            background_tasks.add_task(enviar_correo_reporte_ejecutivo, **kwargs_correo)
            correo_enviado = True
        else:
            correo_enviado = await enviar_correo_reporte_ejecutivo(**kwargs_correo)

        roles_actual = [normalizar_rol(r.nombre) for r in (getattr(usuario_actual, "roles", None) or [])]
        rol_actual = (
            "Admin_Sistema"
            if "Admin_Sistema" in roles_actual
            else ("Director_Recinto" if "Director_Recinto" in roles_actual else (roles_actual[0] if roles_actual else "Analista_Consulta"))
        )
        emisor_actual_info = {
            "id": usuario_actual.id,
            "nombre_completo": usuario_actual.nombre_completo,
            "email": usuario_actual.email,
            "rol": rol_actual,
        }
        resumen = cls._formatear_resumen_reporte(nuevo_reporte, destinatario, emisor_info=emisor_actual_info)
        resumen["correo_enviado"] = correo_enviado
        resumen["enlace_activacion"] = enlace_activacion
        return resumen

    @staticmethod
    def _normalizar_expira_en(valor: Any) -> Optional[datetime]:
        if not valor:
            return None
        if isinstance(valor, datetime):
            return valor.astimezone(ZONA_CHILE).replace(tzinfo=None) if valor.tzinfo is not None else valor
        if isinstance(valor, str) and valor.strip():
            dt = datetime.fromisoformat(valor.strip().replace("Z", "+00:00"))
            return dt.astimezone(ZONA_CHILE).replace(tzinfo=None) if dt.tzinfo is not None else dt
        return None

    @staticmethod
    def _es_expirado(expira_en: Optional[datetime]) -> bool:
        if not expira_en:
            return False
        if getattr(expira_en, "tzinfo", None) is not None:
            return expira_en.astimezone(ZONA_CHILE).replace(tzinfo=None) < ahora_chile_naive()
        return expira_en < ahora_chile_naive()

    @staticmethod
    def _formatear_resumen_reporte(
        reporte: ReporteCompartido,
        destinatario: Optional[DestinatarioReporte] = None,
        metricas: Optional[Dict[str, Any]] = None,
        emisor_info: Optional[Dict[str, Any]] = None,
        espacio_nombre: Optional[str] = None,
        tiene_campana_24h: Optional[bool] = None,
        incluir_token_portal: bool = False,
    ) -> Dict[str, Any]:
        dest = destinatario or reporte.destinatario
        expirado = ServicioReportesCompartidos._es_expirado(reporte.expira_en)
        vigente = bool(reporte.activo and (dest.activo if dest else True) and not expirado)

        aperturas_evento = int(metricas.get("total_aperturas", 0)) if metricas else 0
        total_aperturas = max(aperturas_evento, int(reporte.total_accesos or 0))
        desc_excel = int(metricas.get("total_descargas_excel", 0)) if metricas else 0
        desc_csv = int(metricas.get("total_descargas_csv", 0)) if metricas else 0
        desc_pdf = int(metricas.get("total_descargas_pdf", 0)) if metricas else 0
        desc_img = int(metricas.get("total_descargas_imagen", 0)) if metricas else 0
        total_descargas = desc_excel + desc_csv + desc_pdf + desc_img
        total_consultas_ia = int(metricas.get("total_consultas_ia", 0)) if metricas else 0

        primer_acceso_dt = metricas.get("primer_acceso_en") if metricas else None
        ultimo_evento_dt = metricas.get("ultimo_acceso_en") if metricas else None
        ultimo_dt = reporte.ultimo_acceso_en
        if ultimo_evento_dt and (ultimo_dt is None or ultimo_evento_dt > ultimo_dt):
            ultimo_dt = ultimo_evento_dt

        expira_ch = marcar_chile(reporte.expira_en) if reporte.expira_en else None
        creado_ch = marcar_chile(reporte.creado_en) if reporte.creado_en else None
        primer_ch = marcar_chile(primer_acceso_dt) if primer_acceso_dt else None
        ultimo_ch = marcar_chile(ultimo_dt) if ultimo_dt else None

        if emisor_info is not None:
            creador_data = emisor_info
        else:
            creador_obj = getattr(reporte, "creador", None)
            creador_data = {
                "id": creador_obj.id if creador_obj else reporte.creado_por_id,
                "nombre_completo": creador_obj.nombre_completo if creador_obj else "Sistema DSS",
                "email": creador_obj.email if creador_obj else "",
                "rol": (
                    normalizar_rol(creador_obj.roles[0].nombre)
                    if creador_obj and getattr(creador_obj, "roles", None)
                    else "Usuario"
                ),
            }

        return {
            "id": str(reporte.id),
            "codigo_corto": reporte.codigo_corto,
            "token_acceso": reporte.token_acceso,
            "espacio_id": reporte.espacio_id,
            "espacio_nombre": espacio_nombre or ("Biblioteca CSF" if reporte.espacio_id == 1 else "Estacionamiento CSF"),
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
            "expira_en": expira_ch.isoformat() if expira_ch else None,
            "total_accesos": reporte.total_accesos,
            "revisado": total_aperturas > 0,
            "total_aperturas": total_aperturas,
            "total_descargas": total_descargas,
            "total_descargas_excel": desc_excel,
            "total_descargas_csv": desc_csv,
            "total_descargas_pdf": desc_pdf,
            "total_descargas_imagen": desc_img,
            "total_consultas_ia": total_consultas_ia,
            "primer_acceso_en": primer_ch.isoformat() if primer_ch else None,
            "ultimo_acceso_en": ultimo_ch.isoformat() if ultimo_ch else None,
            "ultima_ip": metricas.get("ultima_ip") if metricas else None,
            "ultimo_user_agent": metricas.get("ultimo_user_agent") if metricas else None,
            "creado_en": creado_ch.isoformat() if creado_ch else None,
            "destinatario": {
                "id": dest.id if dest else None,
                "nombre_completo": dest.nombre_completo if dest else "",
                "email": dest.email if dest else "",
                "cargo": dest.cargo if dest else "",
                "unidad_academica": dest.unidad_academica if dest else "",
                "token_portal": (dest.token_portal if (incluir_token_portal and dest) else ""),
                "activo": dest.activo if dest else True,
            },
            "creador": creador_data,
            "emisor": creador_data,
            "tiene_campana_24h": bool(tiene_campana_24h) if tiene_campana_24h is not None else False,
        }

    @classmethod
    async def listar_reportes_emitidos(
        cls,
        session: AsyncSession,
        usuario_actual: Usuario,
        espacio_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Devuelve la lista de reportes emitidos y el catálogo de destinatarios registrados según jerarquía RLS."""
        from app.domain.config_models import HorarioOperacion

        stmt = (
            select(ReporteCompartido)
            .options(
                defer(ReporteCompartido.datos_instantanea_json),
                selectinload(ReporteCompartido.destinatario),
                selectinload(ReporteCompartido.creador).selectinload(Usuario.roles),
            )
            .order_by(desc(ReporteCompartido.creado_en))
        )
        stmt = cls._aplicar_filtro_rls_reportes(stmt, usuario_actual)
        if espacio_id is not None:
            stmt = stmt.where(ReporteCompartido.espacio_id == espacio_id)

        filas_reportes = (await session.execute(stmt)).scalars().all()

        stmt_24h = select(HorarioOperacion).where(
            HorarioOperacion.espacio_id == 1,
            HorarioOperacion.activo == True,
            or_(HorarioOperacion.es_continuo_24h == True, HorarioOperacion.tipo_horario == "extendido_24h"),
        )
        campanas_24h = (await session.execute(stmt_24h)).scalars().all()

        def _rep_tiene_24h(rep: ReporteCompartido) -> bool:
            if rep.espacio_id != 1 or not rep.fecha_inicio or not rep.fecha_fin:
                return False
            f_ini_dt = datetime.combine(rep.fecha_inicio, datetime.min.time())
            f_fin_dt = datetime.combine(rep.fecha_fin, datetime.max.time())
            return any(
                (c.fecha_inicio is None or c.fecha_inicio <= f_fin_dt)
                and (c.fecha_fin is None or c.fecha_fin >= f_ini_dt)
                for c in campanas_24h
            )

        es_admin_list = cls._es_admin(usuario_actual)
        reportes_por_dest: Dict[int, int] = {}
        if es_admin_list:
            stmt_dest = select(DestinatarioReporte).order_by(desc(DestinatarioReporte.actualizado_en))
            filas_dest = (await session.execute(stmt_dest)).scalars().all()
            res_cnt = await session.execute(
                select(ReporteCompartido.destinatario_id, func.count(ReporteCompartido.id)).group_by(
                    ReporteCompartido.destinatario_id
                )
            )
            for d_id, cnt in res_cnt.all():
                if d_id is not None:
                    reportes_por_dest[int(d_id)] = int(cnt or 0)
        else:
            dest_ids_visibles = {r.destinatario_id for r in filas_reportes if r.destinatario_id is not None}
            if dest_ids_visibles:
                stmt_dest = (
                    select(DestinatarioReporte)
                    .where(DestinatarioReporte.id.in_(dest_ids_visibles))
                    .order_by(desc(DestinatarioReporte.actualizado_en))
                )
                filas_dest = (await session.execute(stmt_dest)).scalars().all()
            else:
                filas_dest = []
            for r in filas_reportes:
                if r.destinatario_id is not None:
                    reportes_por_dest[r.destinatario_id] = reportes_por_dest.get(r.destinatario_id, 0) + 1

        emails_dest = [d.email for d in filas_dest if d.email]
        mapa_usuarios: Dict[str, Usuario] = {}
        if emails_dest:
            stmt_usrs = select(Usuario).where(Usuario.email.in_(emails_dest))
            for u in (await session.execute(stmt_usrs)).scalars().all():
                mapa_usuarios[u.email.lower()] = u

        return {
            "reportes": [
                cls._formatear_resumen_reporte(r, r.destinatario, tiene_campana_24h=_rep_tiene_24h(r))
                for r in filas_reportes
            ],
            "destinatarios": [
                {
                    "id": d.id,
                    "nombre_completo": d.nombre_completo,
                    "email": d.email,
                    "cargo": d.cargo,
                    "unidad_academica": d.unidad_academica,
                    "token_portal": "",
                    "activo": d.activo,
                    "cuenta_activada": bool(
                        d.email.lower() in mapa_usuarios
                        and mapa_usuarios[d.email.lower()].is_active
                        and mapa_usuarios[d.email.lower()].hashed_password != "PENDIENTE_ACTIVACION"
                        and mapa_usuarios[d.email.lower()].hashed_password.startswith("$2")
                    ),
                    "total_reportes": reportes_por_dest.get(d.id, 0),
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
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> Dict[str, Any]:
        """Permite habilitar/deshabilitar el link, habilitar/deshabilitar IA, editar vigencia, notas y gráficos."""
        try:
            uuid_obj = uuid.UUID(str(reporte_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="Identificador de reporte inválido.")

        stmt = (
            select(ReporteCompartido)
            .options(
                selectinload(ReporteCompartido.destinatario),
                selectinload(ReporteCompartido.creador).selectinload(Usuario.roles),
            )
            .where(ReporteCompartido.id == uuid_obj)
        )
        reporte = (await session.execute(stmt)).scalar_one_or_none()
        if not reporte:
            raise HTTPException(status_code=404, detail="Reporte compartido no encontrado.")

        emisor = reporte.creador
        if not emisor and reporte.creado_por_id:
            emisor_stmt = (
                select(Usuario)
                .options(selectinload(Usuario.roles))
                .where(Usuario.id == reporte.creado_por_id)
            )
            emisor = (await session.execute(emisor_stmt)).scalar_one_or_none()
        if not cls._puede_ver_o_gestionar_reporte(usuario_actual, reporte, emisor):
            raise HTTPException(status_code=403, detail="No tiene permisos para modificar este reporte.")

        tiene_24h_rango = await cls._rango_tiene_campana_24h(
            session, reporte.espacio_id, reporte.fecha_inicio, reporte.fecha_fin
        )

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

        cambio_contenido = False
        if "graficos_visibles" in payload and payload["graficos_visibles"] is not None:
            graf_nuevos = list(payload["graficos_visibles"])
            if reporte.espacio_id == 1 and not tiene_24h_rango:
                graf_nuevos = [g for g in graf_nuevos if not cls._es_grafico_campana_24h(g)]
            reporte.graficos_visibles_json = _serializar_json_seguro(graf_nuevos)
            cambio_contenido = True
        if "indicadores_visibles" in payload and payload["indicadores_visibles"] is not None:
            reporte.indicadores_visibles_json = _serializar_json_seguro(payload["indicadores_visibles"])
            cambio_contenido = True

        if cambio_contenido:
            graf_act = _cargar_json_seguro(reporte.graficos_visibles_json, [])
            ind_act = _cargar_json_seguro(reporte.indicadores_visibles_json, [])
            filtros_act = _cargar_json_seguro(reporte.filtros_bloqueados_json, {})
            datos_inst = _cargar_json_seguro(reporte.datos_instantanea_json, {})
            graf_guardados = datos_inst.get("graficos") or {}
            falta_alguno = any(
                cls._normalizar_clave_grafico_snapshot(g) not in graf_guardados
                for g in graf_act
            )
            if not datos_inst or falta_alguno:
                datos_inst = await cls.ensamblar_datos_reporte_confinado(
                    session=session,
                    espacio_id=reporte.espacio_id,
                    fecha_inicio=reporte.fecha_inicio,
                    fecha_fin=reporte.fecha_fin,
                    filtros=filtros_act,
                    graficos_visibles=graf_act,
                    indicadores_visibles=ind_act,
                )
            else:
                datos_inst["graficos_visibles"] = graf_act
                datos_inst["indicadores_visibles"] = ind_act
            reporte.datos_instantanea_json = _serializar_json_seguro(datos_inst)

        if "expira_en" in payload:
            reporte.expira_en = cls._normalizar_expira_en(payload["expira_en"])

        await session.commit()

        correo_enviado = False
        reenviar_correo = bool(payload.get("reenviar_correo", False))
        dest = reporte.destinatario
        if (se_habilito_ahora or reenviar_correo) and reporte.activo and dest:
            usr_dest, token_act_plano = await cls._asegurar_usuario_consultor_reporte(
                session=session,
                email_dest=dest.email,
                nombre_dest=dest.nombre_completo,
                creador_id=usuario_actual.id,
            )
            await session.commit()
            limpiar_cache_usuario(usr_dest.id)
            base_url = obtener_url_frontend()
            enlace_reporte = f"{base_url}/reporte-compartido/{reporte.token_acceso}"
            enlace_portal = f"{base_url}/mis-reportes/{dest.token_portal}"
            enlace_activacion = (
                f"{base_url}/activar-cuenta?token={token_act_plano}" if token_act_plano else None
            )
            kwargs_correo = dict(
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
            if background_tasks is not None:
                background_tasks.add_task(enviar_correo_reporte_ejecutivo, **kwargs_correo)
                correo_enviado = True
            else:
                correo_enviado = await enviar_correo_reporte_ejecutivo(**kwargs_correo)

        resumen = cls._formatear_resumen_reporte(
            reporte, reporte.destinatario, tiene_campana_24h=tiene_24h_rango
        )
        resumen["correo_enviado"] = correo_enviado
        return resumen

    @classmethod
    async def obtener_mis_reportes_consultor(
        cls,
        session: AsyncSession,
        usuario_actual: Usuario,
    ) -> Dict[str, Any]:
        """Devuelve la bandeja histórica de reportes para el usuario Consultor_Reporte autenticado."""
        stmt = select(DestinatarioReporte).where(DestinatarioReporte.email == usuario_actual.email.lower())
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
        return await cls.obtener_portal_destinatario_por_token(
            session=session,
            token_portal=dest.token_portal,
            usuario_actual=usuario_actual,
        )

    @classmethod
    def _roles_normalizados(cls, usuario: Optional[Usuario]) -> set[str]:
        if not usuario:
            return set()
        return {normalizar_rol(r.nombre) for r in (getattr(usuario, "roles", None) or [])}

    @classmethod
    def _es_admin(cls, usuario: Optional[Usuario]) -> bool:
        return "Admin_Sistema" in cls._roles_normalizados(usuario)

    @classmethod
    def _es_directivo(cls, usuario: Optional[Usuario]) -> bool:
        return "Director_Recinto" in cls._roles_normalizados(usuario)

    @classmethod
    def _espacios_autorizados(cls, usuario: Usuario) -> Optional[List[int]]:
        """Retorna None si es Admin (sin restricción) o los espacio_id autorizados al usuario."""
        if cls._es_admin(usuario):
            return None
        mapa_modulo = {"biblioteca": 1, "estacionamiento": 2}
        datasets = [str(d).strip().lower() for d in (getattr(usuario, "allowed_datasets", None) or []) if d]
        ids_dataset = {mapa_modulo[d] for d in datasets if d in mapa_modulo}
        esp_id = getattr(usuario, "espacio_id", None)
        if esp_id is not None:
            esp_int = int(esp_id)
            if ids_dataset and esp_int not in ids_dataset:
                return []
            return [esp_int]
        if datasets:
            return sorted(ids_dataset)
        return []

    @classmethod
    def _es_emisor_directivo_o_analista(cls, emisor: Optional[Usuario]) -> bool:
        roles_emisor = cls._roles_normalizados(emisor)
        if not roles_emisor or "Admin_Sistema" in roles_emisor:
            return False
        return bool(roles_emisor.intersection({"Director_Recinto", "Analista_Consulta"}))

    @classmethod
    def _verificar_acceso_usuario_a_reporte(
        cls,
        usuario_actual: Usuario,
        reporte: ReporteCompartido,
    ) -> None:
        """Verifica que el usuario autenticado sea el destinatario titular, emisor autorizado o Admin_Sistema."""
        if cls._es_admin(usuario_actual):
            return
        email_usr = str(getattr(usuario_actual, "email", "") or "").strip().lower()
        email_dest = str(getattr(reporte.destinatario, "email", "") or "").strip().lower() if reporte.destinatario else ""
        if email_usr and email_dest and email_usr == email_dest:
            return
        if cls._puede_ver_o_gestionar_reporte(usuario_actual, reporte, getattr(reporte, "creador", None)):
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No cuenta con autorización para acceder a este reporte compartido.",
        )

    @classmethod
    def _puede_ver_o_gestionar_reporte(
        cls,
        usuario_actual: Usuario,
        reporte: ReporteCompartido,
        emisor: Optional[Usuario] = None,
    ) -> bool:
        if cls._es_admin(usuario_actual):
            return True
        if cls._es_directivo(usuario_actual):
            espacios = cls._espacios_autorizados(usuario_actual)
            if espacios is not None and int(reporte.espacio_id) not in espacios:
                return False
            if reporte.creado_por_id == usuario_actual.id:
                return True
            return cls._es_emisor_directivo_o_analista(emisor)
        return reporte.creado_por_id == usuario_actual.id

    @classmethod
    def _aplicar_filtro_rls_reportes(cls, stmt: Any, usuario_actual: Usuario) -> Any:
        if cls._es_admin(usuario_actual):
            return stmt
        if cls._es_directivo(usuario_actual):
            espacios = cls._espacios_autorizados(usuario_actual)
            if not espacios:
                return stmt.where(text("1 = 0"))
            roles_permitidos_sql = (
                "Director_Recinto",
                "Directivo",
                "Directora_Recinto",
                "Analista_Consulta",
                "Analista",
            )
            roles_admin_sql = ("Admin_Sistema", "SuperAdmin")
            subq_emisor_valido = (
                select(UsuarioRol.usuario_id)
                .join(Rol, Rol.id == UsuarioRol.rol_id)
                .where(Rol.nombre.in_(roles_permitidos_sql))
            )
            subq_emisor_admin = (
                select(UsuarioRol.usuario_id)
                .join(Rol, Rol.id == UsuarioRol.rol_id)
                .where(Rol.nombre.in_(roles_admin_sql))
            )
            return (
                stmt.where(ReporteCompartido.espacio_id.in_(espacios))
                .where(ReporteCompartido.creado_por_id.in_(subq_emisor_valido))
                .where(~ReporteCompartido.creado_por_id.in_(subq_emisor_admin))
            )
        return stmt.where(ReporteCompartido.creado_por_id == usuario_actual.id)

    @classmethod
    async def _cargar_contexto_resumen_reportes(
        cls,
        session: AsyncSession,
        reportes: List[ReporteCompartido],
    ) -> tuple[Dict[uuid.UUID, Dict[str, Any]], Dict[int, Dict[str, Any]], Dict[int, str]]:
        if not reportes:
            return {}, {}, {}
        rep_ids = [r.id for r in reportes]
        emisor_ids = sorted({int(r.creado_por_id) for r in reportes if r.creado_por_id is not None})

        metricas_map: Dict[uuid.UUID, Dict[str, Any]] = {}
        stmt_ev = (
            select(AuditoriaAccesoReporte)
            .where(AuditoriaAccesoReporte.reporte_id.in_(rep_ids))
            .order_by(AuditoriaAccesoReporte.fecha_hora.asc(), AuditoriaAccesoReporte.id.asc())
        )
        eventos = (await session.execute(stmt_ev)).scalars().all()
        for ev in eventos:
            m = metricas_map.setdefault(
                ev.reporte_id,
                {
                    "total_aperturas": 0,
                    "total_descargas_excel": 0,
                    "total_descargas_csv": 0,
                    "total_descargas_pdf": 0,
                    "total_descargas_imagen": 0,
                    "total_consultas_ia": 0,
                    "primer_acceso_en": None,
                    "ultimo_acceso_en": None,
                    "ultima_ip": None,
                    "ultimo_user_agent": None,
                },
            )
            accion = (ev.accion or "").strip()
            if accion == "apertura_reporte":
                m["total_aperturas"] += 1
            elif accion == "descarga_excel":
                m["total_descargas_excel"] += 1
            elif accion == "descarga_csv":
                m["total_descargas_csv"] += 1
            elif accion == "descarga_pdf":
                m["total_descargas_pdf"] += 1
            elif accion == "descarga_imagen":
                m["total_descargas_imagen"] += 1
            elif accion == "consulta_ia_confinada":
                m["total_consultas_ia"] += 1

            if m["primer_acceso_en"] is None or (ev.fecha_hora and ev.fecha_hora < m["primer_acceso_en"]):
                m["primer_acceso_en"] = ev.fecha_hora
            if m["ultimo_acceso_en"] is None or (ev.fecha_hora and ev.fecha_hora >= m["ultimo_acceso_en"]):
                m["ultimo_acceso_en"] = ev.fecha_hora
                if ev.ip_origen:
                    m["ultima_ip"] = ev.ip_origen
                if getattr(ev, "user_agent", None):
                    m["ultimo_user_agent"] = ev.user_agent

        emisores_map: Dict[int, Dict[str, Any]] = {}
        if emisor_ids:
            stmt_em = select(Usuario).options(selectinload(Usuario.roles)).where(Usuario.id.in_(emisor_ids))
            for u in (await session.execute(stmt_em)).scalars().all():
                roles_u = [normalizar_rol(r.nombre) for r in (u.roles or [])]
                rol_principal = (
                    "Admin_Sistema"
                    if "Admin_Sistema" in roles_u
                    else ("Director_Recinto" if "Director_Recinto" in roles_u else (roles_u[0] if roles_u else "Analista_Consulta"))
                )
                emisores_map[int(u.id)] = {
                    "id": int(u.id),
                    "nombre_completo": u.nombre_completo,
                    "email": u.email,
                    "rol": rol_principal,
                }

        espacios_map: Dict[int, str] = {}
        stmt_esp = select(Espacio)
        for esp in (await session.execute(stmt_esp)).scalars().all():
            espacios_map[int(esp.id)] = esp.nombre

        return metricas_map, emisores_map, espacios_map

    @classmethod
    async def obtener_auditoria_reportes_emitidos(
        cls,
        session: AsyncSession,
        usuario_actual: Usuario,
        espacio_id: Optional[int] = None,
        emisor_rol: Optional[str] = None,
        estado_revision: Optional[str] = None,
        solo_activos: Optional[bool] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        base_stmt = select(
            ReporteCompartido.id.label("rep_id"),
            ReporteCompartido.total_accesos.label("total_accesos"),
            ReporteCompartido.creado_en.label("creado_en"),
        )
        base_stmt = cls._aplicar_filtro_rls_reportes(base_stmt, usuario_actual)

        if espacio_id is not None:
            base_stmt = base_stmt.where(ReporteCompartido.espacio_id == espacio_id)
        if solo_activos is not None:
            base_stmt = base_stmt.where(ReporteCompartido.activo == solo_activos)

        emisor_norm = (emisor_rol or "").strip().lower()
        if emisor_norm == "directivo":
            subq_dir = (
                select(UsuarioRol.usuario_id)
                .join(Rol, Rol.id == UsuarioRol.rol_id)
                .where(Rol.nombre.in_(("Director_Recinto", "Directivo", "Directora_Recinto")))
            )
            base_stmt = base_stmt.where(ReporteCompartido.creado_por_id.in_(subq_dir))
        elif emisor_norm == "analista":
            subq_ana = (
                select(UsuarioRol.usuario_id)
                .join(Rol, Rol.id == UsuarioRol.rol_id)
                .where(Rol.nombre.in_(("Analista_Consulta", "Analista")))
            )
            base_stmt = base_stmt.where(ReporteCompartido.creado_por_id.in_(subq_ana))
        elif emisor_norm == "admin":
            subq_adm = (
                select(UsuarioRol.usuario_id)
                .join(Rol, Rol.id == UsuarioRol.rol_id)
                .where(Rol.nombre.in_(("Admin_Sistema", "SuperAdmin")))
            )
            base_stmt = base_stmt.where(ReporteCompartido.creado_por_id.in_(subq_adm))

        if search and search.strip():
            termino = f"%{search.strip()}%"
            base_stmt = base_stmt.outerjoin(
                DestinatarioReporte, ReporteCompartido.destinatario_id == DestinatarioReporte.id
            ).where(
                or_(
                    ReporteCompartido.titulo_reporte.ilike(termino),
                    ReporteCompartido.codigo_corto.ilike(termino),
                    DestinatarioReporte.nombre_completo.ilike(termino),
                    DestinatarioReporte.email.ilike(termino),
                )
            )

        base_subq = base_stmt.subquery("base_rep")
        ev_agg_subq = (
            select(
                AuditoriaAccesoReporte.reporte_id.label("reporte_id"),
                func.sum(case((AuditoriaAccesoReporte.accion == "apertura_reporte", 1), else_=0)).label("ap_ev"),
                func.sum(
                    case(
                        (
                            AuditoriaAccesoReporte.accion.in_(
                                ("descarga_excel", "descarga_csv", "descarga_pdf", "descarga_imagen")
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("desc_ev"),
                func.sum(case((AuditoriaAccesoReporte.accion == "consulta_ia_confinada", 1), else_=0)).label("ia_ev"),
            )
            .group_by(AuditoriaAccesoReporte.reporte_id)
            .subquery("ev_agg")
        )

        ap_ev_expr = func.coalesce(ev_agg_subq.c.ap_ev, 0)
        tot_acc_expr = func.coalesce(base_subq.c.total_accesos, 0)
        total_ap_expr = case((ap_ev_expr > tot_acc_expr, ap_ev_expr), else_=tot_acc_expr)

        agg_stmt = select(
            func.count(base_subq.c.rep_id).label("total_universo"),
            func.coalesce(func.sum(case((total_ap_expr > 0, 1), else_=0)), 0).label("revisados_total"),
            func.coalesce(func.sum(total_ap_expr), 0).label("aperturas_total"),
            func.coalesce(func.sum(func.coalesce(ev_agg_subq.c.desc_ev, 0)), 0).label("descargas_total"),
            func.coalesce(func.sum(func.coalesce(ev_agg_subq.c.ia_ev, 0)), 0).label("consultas_ia_total"),
        ).select_from(base_subq.outerjoin(ev_agg_subq, base_subq.c.rep_id == ev_agg_subq.c.reporte_id))

        kpi_row = (await session.execute(agg_stmt)).one()
        total_universo = int(kpi_row.total_universo or 0)
        revisados_total = int(kpi_row.revisados_total or 0)
        aperturas_total = int(kpi_row.aperturas_total or 0)
        descargas_total = int(kpi_row.descargas_total or 0)
        consultas_ia_total = int(kpi_row.consultas_ia_total or 0)

        rev_norm = (estado_revision or "").strip().lower()
        if rev_norm == "revisado":
            total_items = revisados_total
        elif rev_norm == "sin_revisar":
            total_items = max(0, total_universo - revisados_total)
        else:
            total_items = total_universo

        page_safe = max(1, int(page))
        size_safe = max(1, min(100, int(page_size)))
        total_pages = max(1, (total_items + size_safe - 1) // size_safe)
        offset = (page_safe - 1) * size_safe

        page_stmt = (
            select(base_subq.c.rep_id)
            .select_from(base_subq.outerjoin(ev_agg_subq, base_subq.c.rep_id == ev_agg_subq.c.reporte_id))
            .order_by(desc(base_subq.c.creado_en))
        )
        if rev_norm == "revisado":
            page_stmt = page_stmt.where(total_ap_expr > 0)
        elif rev_norm == "sin_revisar":
            page_stmt = page_stmt.where(total_ap_expr == 0)

        page_ids = list((await session.execute(page_stmt.offset(offset).limit(size_safe))).scalars().all())

        paginados: List[Dict[str, Any]] = []
        if page_ids:
            stmt_page_reps = (
                select(ReporteCompartido)
                .options(
                    defer(ReporteCompartido.datos_instantanea_json),
                    selectinload(ReporteCompartido.destinatario),
                )
                .where(ReporteCompartido.id.in_(page_ids))
            )
            reps_by_id = {r.id: r for r in (await session.execute(stmt_page_reps)).scalars().all()}
            reportes_ordenados = [reps_by_id[rid] for rid in page_ids if rid in reps_by_id]
            metricas_map, emisores_map, espacios_map = await cls._cargar_contexto_resumen_reportes(
                session, reportes_ordenados
            )
            for rep in reportes_ordenados:
                m = metricas_map.get(rep.id)
                emisor_info = emisores_map.get(int(rep.creado_por_id)) if rep.creado_por_id is not None else None
                paginados.append(
                    cls._formatear_resumen_reporte(
                        rep,
                        metricas=m,
                        emisor_info=emisor_info,
                        espacio_nombre=espacios_map.get(int(rep.espacio_id)),
                    )
                )

        return {
            "rol_auditor": (
                "Admin_Sistema"
                if cls._es_admin(usuario_actual)
                else ("Director_Recinto" if cls._es_directivo(usuario_actual) else "Analista_Consulta")
            ),
            "espacios_autorizados": cls._espacios_autorizados(usuario_actual),
            "kpis": {
                "total_reportes": total_universo,
                "reportes_revisados": revisados_total,
                "reportes_sin_revisar": total_universo - revisados_total,
                "tasa_lectura_pct": round((revisados_total / total_universo) * 100, 1) if total_universo > 0 else 0.0,
                "total_aperturas": aperturas_total,
                "total_descargas": descargas_total,
                "total_consultas_ia": consultas_ia_total,
            },
            "total": total_items,
            "page": page_safe,
            "page_size": size_safe,
            "total_pages": total_pages,
            "items": paginados,
        }

    @classmethod
    async def obtener_eventos_reporte(
        cls,
        session: AsyncSession,
        usuario_actual: Usuario,
        reporte_id: str,
        accion: Optional[str] = None,
        limit: int = 200,
    ) -> Dict[str, Any]:
        try:
            uuid_obj = uuid.UUID(reporte_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="ID de reporte inválido.")

        reporte = (
            await session.execute(
                select(ReporteCompartido)
                .options(
                    defer(ReporteCompartido.datos_instantanea_json),
                    selectinload(ReporteCompartido.destinatario),
                )
                .where(ReporteCompartido.id == uuid_obj)
            )
        ).scalar_one_or_none()
        if not reporte:
            raise HTTPException(status_code=404, detail="Reporte compartido no encontrado.")

        emisor = (
            await session.execute(
                select(Usuario).options(selectinload(Usuario.roles)).where(Usuario.id == reporte.creado_por_id)
            )
        ).scalar_one_or_none()
        if not cls._puede_ver_o_gestionar_reporte(usuario_actual, reporte, emisor):
            raise HTTPException(status_code=403, detail="No tiene permisos para auditar este reporte.")

        stmt = (
            select(AuditoriaAccesoReporte)
            .where(AuditoriaAccesoReporte.reporte_id == uuid_obj)
            .order_by(desc(AuditoriaAccesoReporte.fecha_hora), desc(AuditoriaAccesoReporte.id))
            .limit(max(1, min(500, int(limit))))
        )
        if accion and accion.strip():
            stmt = stmt.where(AuditoriaAccesoReporte.accion == accion.strip())

        eventos = (await session.execute(stmt)).scalars().all()
        return {
            "reporte_id": str(reporte.id),
            "codigo_corto": reporte.codigo_corto,
            "titulo_reporte": reporte.titulo_reporte,
            "destinatario": {
                "nombre_completo": reporte.destinatario.nombre_completo if reporte.destinatario else None,
                "email": reporte.destinatario.email if reporte.destinatario else None,
            },
            "eventos": [
                {
                    "id": ev.id,
                    "fecha_hora": marcar_chile(ev.fecha_hora).isoformat() if ev.fecha_hora else None,
                    "accion": ev.accion,
                    "ip_origen": ev.ip_origen,
                    "detalle": getattr(ev, "detalle", None),
                    "user_agent": getattr(ev, "user_agent", None),
                }
                for ev in eventos
            ],
        }

    @classmethod
    async def registrar_evento_reporte_publico(
        cls,
        session: AsyncSession,
        token_acceso: str,
        accion: str,
        detalle: Optional[str] = None,
        ip_origen: Optional[str] = None,
        user_agent: Optional[str] = None,
        usuario_actual: Optional[Usuario] = None,
    ) -> Dict[str, Any]:
        acciones_permitidas = {"descarga_excel", "descarga_csv", "descarga_pdf", "descarga_imagen"}
        if accion not in acciones_permitidas:
            raise HTTPException(status_code=400, detail="Acción de seguimiento no válida.")

        stmt = (
            select(ReporteCompartido)
            .options(
                defer(ReporteCompartido.datos_instantanea_json),
                selectinload(ReporteCompartido.destinatario),
                selectinload(ReporteCompartido.creador).selectinload(Usuario.roles),
            )
            .where(ReporteCompartido.token_acceso == token_acceso)
        )
        reporte = (await session.execute(stmt)).scalar_one_or_none()
        if not reporte:
            raise HTTPException(status_code=404, detail="El enlace de reporte solicitado no existe.")

        if usuario_actual is not None:
            cls._verificar_acceso_usuario_a_reporte(usuario_actual, reporte)

        dest = reporte.destinatario
        if not reporte.activo or (dest and not dest.activo):
            raise HTTPException(status_code=403, detail="Este reporte ejecutivo ha sido deshabilitado.")
        if cls._es_expirado(reporte.expira_en):
            raise HTTPException(status_code=410, detail="El plazo de vigencia de este reporte expiró.")
        if not reporte.permitir_exportacion:
            raise HTTPException(status_code=403, detail="La exportación está deshabilitada para este reporte.")

        ahora = ahora_chile_naive()
        reporte.ultimo_acceso_en = ahora
        session.add(
            AuditoriaAccesoReporte(
                reporte_id=reporte.id,
                fecha_hora=ahora,
                ip_origen=ip_origen,
                accion=accion,
                detalle=(detalle or "")[:500] or None,
                user_agent=(user_agent or "")[:255] or None,
            )
        )
        await session.commit()
        return {
            "ok": True,
            "accion": accion,
            "fecha_hora": marcar_chile(ahora).isoformat(),
        }

    @classmethod
    async def actualizar_estado_destinatario(
        cls,
        session: AsyncSession,
        destinatario_id: int,
        activo: bool,
        usuario_actual: Optional[Usuario] = None,
    ) -> Dict[str, Any]:
        stmt = (
            select(DestinatarioReporte)
            .options(selectinload(DestinatarioReporte.reportes).defer(ReporteCompartido.datos_instantanea_json))
            .where(DestinatarioReporte.id == destinatario_id)
        )
        dest = (await session.execute(stmt)).scalar_one_or_none()
        if not dest:
            raise HTTPException(status_code=404, detail="Destinatario no encontrado.")
        if usuario_actual is not None and not cls._es_admin(usuario_actual):
            if not cls._es_directivo(usuario_actual):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No está autorizado para modificar destinatarios de reportes.",
                )
            espacios_dir = set(cls._espacios_autorizados(usuario_actual) or [])
            espacios_dest = {int(r.espacio_id) for r in (dest.reportes or [])}
            if not espacios_dest or not espacios_dest.issubset(espacios_dir):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="El destinatario tiene reportes fuera de su recinto autorizado.",
                )
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
        Elimina el registro del usuario Consultor de Reportes (exclusivo para Admin_Sistema).
        """
        from sqlalchemy import delete as sql_delete, update as sql_update
        from app.domain.models import IngestionJob
        from app.services.auth_service import limpiar_cache_usuario

        if not cls._es_admin(usuario_actual):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo Admin_Sistema puede eliminar cuentas consultoras y su historial de auditoría.",
            )

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

        stmt_usr = (
            select(Usuario)
            .options(selectinload(Usuario.roles))
            .where(Usuario.email == email_dest)
        )
        usr = (await session.execute(stmt_usr)).scalar_one_or_none()
        if usr:
            roles_usr = {normalizar_rol(r.nombre) for r in (usr.roles or [])}
            tiene_otros_roles = bool(roles_usr - {"Consultor_Reporte"})
            limpiar_cache_usuario(usr.id)
            if usr.id != usuario_actual.id and not tiene_otros_roles:
                await session.execute(
                    sql_update(Usuario).where(Usuario.created_by_user_id == usr.id).values(created_by_user_id=None)
                )
                await session.execute(
                    sql_update(IngestionJob).where(IngestionJob.creado_por == usr.id).values(creado_por=None)
                )
                await session.execute(sql_delete(TokenActivacion).where(TokenActivacion.usuario_id == usr.id))
                await session.execute(sql_delete(UsuarioRol).where(UsuarioRol.usuario_id == usr.id))
                await session.execute(sql_delete(Usuario).where(Usuario.id == usr.id))
            elif "Consultor_Reporte" in roles_usr:
                rol_c = (
                    await session.execute(select(Rol.id).where(Rol.nombre == "Consultor_Reporte"))
                ).scalar_one_or_none()
                if rol_c:
                    await session.execute(
                        sql_delete(UsuarioRol).where(
                            UsuarioRol.usuario_id == usr.id,
                            UsuarioRol.rol_id == rol_c,
                        )
                    )

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

        stmt = (
            select(ReporteCompartido)
            .options(defer(ReporteCompartido.datos_instantanea_json))
            .where(ReporteCompartido.id == uuid_obj)
        )
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
        user_agent: Optional[str] = None,
        usuario_actual: Optional[Usuario] = None,
    ) -> Dict[str, Any]:
        """
        Resuelve un reporte compartido por su token_acceso.
        Sin JWT devuelve únicamente metadatos mínimos (requiere_login=True).
        Con JWT verifica pertenencia antes de entregar datos y nunca expone token_activacion ni token_portal.
        """
        stmt = (
            select(ReporteCompartido)
            .options(
                selectinload(ReporteCompartido.destinatario),
                selectinload(ReporteCompartido.creador).selectinload(Usuario.roles),
            )
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

        ahora = ahora_chile_naive()
        if cls._es_expirado(reporte.expira_en):
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail=f"El plazo de vigencia de este reporte expiró el {reporte.expira_en.strftime('%d-%m-%Y %H:%M')}.",
            )

        # Sin autenticación JWT: retorna solo metadatos no sensibles y bloquea datos/tokens
        if usuario_actual is None:
            return {
                "requiere_login": True,
                "reporte": {
                    "codigo_corto": reporte.codigo_corto,
                    "titulo_reporte": reporte.titulo_reporte,
                    "espacio_id": reporte.espacio_id,
                    "espacio_nombre": "Biblioteca CSF" if reporte.espacio_id == 1 else "Estacionamiento CSF",
                    "fecha_inicio": reporte.fecha_inicio.isoformat(),
                    "fecha_fin": reporte.fecha_fin.isoformat(),
                    "activo": reporte.activo,
                    "expirado": False,
                    "vigente": True,
                },
                "datos": None,
                "historial_destinatario": [],
                "destinatario_puede_ia": False,
                "cuota_ia": None,
                "mensajes_ia": [],
            }

        cls._verificar_acceso_usuario_a_reporte(usuario_actual, reporte)

        # Registrar acceso en auditoría con incremento atómico SQL solo tras autenticación verificada
        if hasattr(session, "execute"):
            await session.execute(
                update(ReporteCompartido)
                .where(ReporteCompartido.id == reporte.id)
                .values(
                    total_accesos=func.coalesce(ReporteCompartido.total_accesos, 0) + 1,
                    ultimo_acceso_en=ahora,
                )
            )
        reporte.total_accesos = int(reporte.total_accesos or 0) + 1
        reporte.ultimo_acceso_en = ahora
        session.add(
            AuditoriaAccesoReporte(
                reporte_id=reporte.id,
                fecha_hora=ahora,
                ip_origen=ip_origen,
                accion="apertura_reporte",
                detalle=f"Apertura autenticada del reporte {reporte.codigo_corto}",
                user_agent=(user_agent or "")[:255] or None,
            )
        )
        await session.commit()

        filtros_bloqueados = _cargar_json_seguro(reporte.filtros_bloqueados_json, {})
        graficos_visibles = _cargar_json_seguro(reporte.graficos_visibles_json, [])
        indicadores_visibles = _cargar_json_seguro(reporte.indicadores_visibles_json, [])

        if reporte.datos_instantanea_json:
            datos_confinados = _cargar_json_seguro(reporte.datos_instantanea_json, {})
            ind_ej_guardados = datos_confinados.get("indicadores_ejecutivos") or {}
            graficos_guardados = datos_confinados.get("graficos") or {}
            ids_cat_actual = {
                i["id"]
                for i in (
                    CATALOGO_INDICADORES_BIBLIOTECA
                    if reporte.espacio_id == 1
                    else CATALOGO_INDICADORES_ESTACIONAMIENTO
                )
            }
            ind_vis_guardados = datos_confinados.get("indicadores_visibles") or []
            faltan_graficos = any(
                cls._normalizar_clave_grafico_snapshot(g) not in graficos_guardados
                for g in graficos_visibles
            )
            es_dinamico = (reporte.modo_datos or "dinamico_acotado") == "dinamico_acotado"
            if (
                es_dinamico
                or "dias_operativos" not in ind_ej_guardados
                or not any(i in ids_cat_actual for i in ind_vis_guardados)
                or faltan_graficos
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
            reporte.datos_instantanea_json = _serializar_json_seguro(datos_confinados)
            await session.commit()

        usr_dest = await cls._obtener_usuario_destinatario_con_roles(session, reporte)
        usuario_ia_ref = usuario_actual or usr_dest
        destinatario_puede_ia = bool(
            cls._es_admin(usuario_actual) or getattr(usuario_ia_ref, "can_use_ai", True)
        )

        cuota_ia: Optional[Dict[str, Any]] = None
        mensajes_ia_resp: List[Dict[str, Any]] = []
        if reporte.permitir_ia and destinatario_puede_ia:
            cuota_ia = await cls._obtener_cuota_ia_reporte(session, reporte, usuario_ia_ref)
            stmt_msg = (
                select(MensajeIAReporte)
                .where(MensajeIAReporte.reporte_id == reporte.id)
                .order_by(MensajeIAReporte.creado_en.asc(), MensajeIAReporte.id.asc())
            )
            filas_msg = (await session.execute(stmt_msg)).scalars().all()
            mensajes_ia_resp = [
                {
                    "id": m.id,
                    "sesion_id": m.sesion_id or "principal",
                    "pregunta": m.pregunta,
                    "respuesta": m.respuesta,
                    "modelo_utilizado": m.modelo_utilizado,
                    "tiempo_respuesta_ms": m.tiempo_respuesta_ms,
                    "creado_en": marcar_chile(m.creado_en).isoformat() if m.creado_en else None,
                }
                for m in filas_msg
            ]

        return {
            "requiere_login": False,
            "reporte": cls._formatear_resumen_reporte(reporte, dest, incluir_token_portal=False),
            "datos": datos_confinados,
            "historial_destinatario": [],
            "destinatario_puede_ia": destinatario_puede_ia,
            "cuota_ia": cuota_ia,
            "mensajes_ia": mensajes_ia_resp,
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
        usuario_actual: Optional[Usuario] = None,
    ) -> Dict[str, Any]:
        """Devuelve la bandeja histórica completa de reportes de un destinatario autenticado."""
        stmt = (
            select(DestinatarioReporte)
            .options(
                selectinload(DestinatarioReporte.reportes).defer(ReporteCompartido.datos_instantanea_json)
            )
            .where(DestinatarioReporte.token_portal == token_portal)
        )
        dest = (await session.execute(stmt)).scalar_one_or_none()
        if not dest:
            raise HTTPException(status_code=404, detail="Bandeja de destinatario no encontrada.")
        if not dest.activo:
            raise HTTPException(status_code=403, detail="La cuenta de destinatario se encuentra deshabilitada.")
        if usuario_actual is not None and not cls._es_admin(usuario_actual):
            email_usr = str(getattr(usuario_actual, "email", "") or "").strip().lower()
            if email_usr != str(dest.email or "").strip().lower():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No tiene autorización para consultar el portal histórico de otro destinatario.",
                )

        ahora = datetime.now()
        reportes_lista = []
        for rep in sorted(dest.reportes or [], key=lambda r: (r.creado_en.replace(tzinfo=None) if getattr(r.creado_en, "tzinfo", None) else r.creado_en) or ahora, reverse=True):
            exp_h = cls._es_expirado(rep.expira_en)
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
    async def _obtener_usuario_destinatario_con_roles(
        cls,
        session: AsyncSession,
        reporte: ReporteCompartido,
    ) -> Optional[Usuario]:
        """Obtiene la cuenta de usuario del destinatario (si existe) con sus roles cargados."""
        email = getattr(reporte.destinatario, "email", None) if reporte.destinatario else None
        if not email:
            return None
        stmt_usr = (
            select(Usuario)
            .options(selectinload(Usuario.roles))
            .where(Usuario.email == str(email).strip().lower())
        )
        usr = (await session.execute(stmt_usr)).scalar_one_or_none()
        return usr if usr and hasattr(usr, "email") and hasattr(usr, "id") else None

    @classmethod
    async def _obtener_cuota_ia_reporte(
        cls,
        session: AsyncSession,
        reporte: ReporteCompartido,
        usuario_dest: Optional[Usuario] = None,
    ) -> Dict[str, Any]:
        """Calcula la cuota diaria de consultas IA en reportes compartidos según el rol del consultor."""
        roles_objs = list(getattr(usuario_dest, "roles", None) or [])
        if not roles_objs:
            try:
                stmt_rol = select(Rol).where(Rol.nombre == "Consultor_Reporte")
                rol_c = (await session.execute(stmt_rol)).scalar_one_or_none()
                if rol_c and hasattr(rol_c, "rate_limit_quota"):
                    roles_objs = [rol_c]
            except Exception:
                roles_objs = []

        limite: Optional[int] = None
        es_ilimitado = False
        for r in roles_objs:
            q_str = str(getattr(r, "rate_limit_quota", "") or "50/día").lower().strip()
            if any(unl in q_str for unl in ("ilimitado", "unlimited", "none", "-1", "100000")):
                es_ilimitado = True
            elif not es_ilimitado:
                m_num = re.search(r"\d+", q_str)
                if m_num:
                    val = int(m_num.group(0))
                    if limite is None or val > limite:
                        limite = val
                elif limite is None:
                    limite = 50

        if not es_ilimitado and limite is None:
            limite = 50

        inicio_dia = ahora_chile_naive().replace(hour=0, minute=0, second=0, microsecond=0)
        usadas = 0
        try:
            filtro_objetivo = (
                MensajeIAReporte.usuario_id == usuario_dest.id
                if usuario_dest and getattr(usuario_dest, "id", None) is not None
                else MensajeIAReporte.reporte_id == reporte.id
            )
            stmt_cnt = select(func.count(MensajeIAReporte.id)).where(
                filtro_objetivo,
                MensajeIAReporte.creado_en >= inicio_dia,
            )
            res_cnt = await session.execute(stmt_cnt)
            val_cnt = res_cnt.scalar() if hasattr(res_cnt, "scalar") else res_cnt.scalar_one_or_none()
            usadas = int(val_cnt) if isinstance(val_cnt, (int, float)) else 0
        except Exception:
            usadas = 0

        restantes = None if es_ilimitado else max(0, (limite or 0) - usadas)
        return {
            "usadas": usadas,
            "limite": None if es_ilimitado else limite,
            "restantes": restantes,
            "ilimitado": es_ilimitado,
        }

    @classmethod
    async def obtener_historial_ia_reporte_publico(
        cls,
        session: AsyncSession,
        token_acceso: str,
        usuario_actual: Optional[Usuario] = None,
    ) -> Dict[str, Any]:
        """Devuelve el historial persistido de conversaciones IA y cuota diaria para un reporte autorizado."""
        stmt = (
            select(ReporteCompartido)
            .options(
                defer(ReporteCompartido.datos_instantanea_json),
                selectinload(ReporteCompartido.destinatario),
                selectinload(ReporteCompartido.creador).selectinload(Usuario.roles),
            )
            .where(ReporteCompartido.token_acceso == token_acceso)
        )
        reporte = (await session.execute(stmt)).scalar_one_or_none()
        if not reporte:
            raise HTTPException(status_code=404, detail="Reporte no encontrado.")
        if usuario_actual is not None:
            cls._verificar_acceso_usuario_a_reporte(usuario_actual, reporte)
        if not reporte.activo or (reporte.destinatario and not reporte.destinatario.activo):
            raise HTTPException(status_code=403, detail="Este reporte se encuentra deshabilitado.")
        if cls._es_expirado(reporte.expira_en):
            raise HTTPException(status_code=410, detail="Este reporte ha expirado.")
        if not reporte.permitir_ia:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El asistente de IA no está habilitado para este reporte compartido.",
            )

        usr_dest = await cls._obtener_usuario_destinatario_con_roles(session, reporte)
        usuario_ia_ref = usuario_actual or usr_dest
        if usuario_ia_ref is not None and not cls._es_admin(usuario_ia_ref) and not getattr(usuario_ia_ref, "can_use_ai", True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El acceso al Asistente IA ha sido deshabilitado para su cuenta por el administrador.",
            )

        cuota = await cls._obtener_cuota_ia_reporte(session, reporte, usuario_ia_ref)
        stmt_msg = (
            select(MensajeIAReporte)
            .where(MensajeIAReporte.reporte_id == reporte.id)
            .order_by(MensajeIAReporte.creado_en.asc(), MensajeIAReporte.id.asc())
        )
        filas = (await session.execute(stmt_msg)).scalars().all()
        return {
            "cuota": cuota,
            "mensajes": [
                {
                    "id": m.id,
                    "sesion_id": m.sesion_id or "principal",
                    "pregunta": m.pregunta,
                    "respuesta": m.respuesta,
                    "modelo_utilizado": m.modelo_utilizado,
                    "tiempo_respuesta_ms": m.tiempo_respuesta_ms,
                    "creado_en": marcar_chile(m.creado_en).isoformat() if m.creado_en else None,
                }
                for m in filas
            ],
        }

    @classmethod
    async def consultar_ia_reporte_confinado(
        cls,
        session: AsyncSession,
        token_acceso: str,
        pregunta: str,
        sesion_id: str = "principal",
        ip_origen: Optional[str] = None,
        user_agent: Optional[str] = None,
        usuario_actual: Optional[Usuario] = None,
    ) -> Dict[str, Any]:
        """
        Ejecuta una consulta al asistente IA estrictamente confinada a los datos del reporte compartido.
        Solo funciona cuando reporte.permitir_ia == True.
        """
        stmt = (
            select(ReporteCompartido)
            .options(
                selectinload(ReporteCompartido.destinatario),
                selectinload(ReporteCompartido.creador).selectinload(Usuario.roles),
            )
            .where(ReporteCompartido.token_acceso == token_acceso)
        )
        reporte = (await session.execute(stmt)).scalar_one_or_none()
        if not reporte:
            raise HTTPException(status_code=404, detail="Reporte no encontrado.")

        if usuario_actual is not None:
            cls._verificar_acceso_usuario_a_reporte(usuario_actual, reporte)

        if not reporte.activo or (reporte.destinatario and not reporte.destinatario.activo):
            raise HTTPException(status_code=403, detail="Este reporte se encuentra deshabilitado.")

        if cls._es_expirado(reporte.expira_en):
            raise HTTPException(status_code=410, detail="Este reporte ha expirado.")

        if not reporte.permitir_ia:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El asistente de IA no está habilitado para este reporte compartido.",
            )

        usr_dest = await cls._obtener_usuario_destinatario_con_roles(session, reporte)
        usuario_ia_ref = usuario_actual or usr_dest
        if usuario_ia_ref is not None and not cls._es_admin(usuario_ia_ref) and not getattr(usuario_ia_ref, "can_use_ai", True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El acceso al Asistente IA ha sido deshabilitado para su cuenta por el administrador.",
            )

        cuota_previa = await cls._obtener_cuota_ia_reporte(session, reporte, usuario_ia_ref)
        if not cuota_previa["ilimitado"] and (cuota_previa["restantes"] or 0) <= 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Has alcanzado tu límite diario de {cuota_previa['limite']} consultas "
                    "al Asistente IA. La cuota se restablecerá mañana."
                ),
            )

        filtros_bloqueados = _cargar_json_seguro(reporte.filtros_bloqueados_json, {})
        graficos_visibles = _cargar_json_seguro(reporte.graficos_visibles_json, [])
        indicadores_visibles = _cargar_json_seguro(reporte.indicadores_visibles_json, [])

        if reporte.datos_instantanea_json:
            datos_confinados = _cargar_json_seguro(reporte.datos_instantanea_json, {})
            ind_ej_guardados = datos_confinados.get("indicadores_ejecutivos") or {}
            graficos_guardados = datos_confinados.get("graficos") or {}
            ids_cat_actual = {
                i["id"]
                for i in (
                    CATALOGO_INDICADORES_BIBLIOTECA
                    if reporte.espacio_id == 1
                    else CATALOGO_INDICADORES_ESTACIONAMIENTO
                )
            }
            ind_vis_guardados = datos_confinados.get("indicadores_visibles") or []
            faltan_graficos = any(
                cls._normalizar_clave_grafico_snapshot(g) not in graficos_guardados
                for g in graficos_visibles
            )
            es_dinamico = (reporte.modo_datos or "dinamico_acotado") == "dinamico_acotado"
            if (
                es_dinamico
                or "dias_operativos" not in ind_ej_guardados
                or not any(i in ids_cat_actual for i in ind_vis_guardados)
                or faltan_graficos
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
            reporte.datos_instantanea_json = _serializar_json_seguro(datos_confinados)
            await session.commit()

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
            "Responde siempre en español claro, directo y ejecutivo, evitando saludos largos repetitivos (como 'Estimado/a Consultor/a'). "
            "Formatea las cifras numéricas según estándar chileno: punto para miles y coma para decimales (ej. 14.208; 58,0 minutos; 33,8%). "
            "Cuando enumeres métricas o indicadores clave, preséntalos en formato limpio '- **Nombre del Indicador:** Valor'."
        )

        prompt_completo = (
            f"CONTEXTO SELLADO DEL REPORTE EJECUTIVO:\n{_serializar_json_seguro(resumen_contexto)}\n\n"
            f"CONSULTA DEL DESTINATARIO:\n{pregunta}"
        )

        ahora_evento = ahora_chile_naive()
        session.add(
            AuditoriaAccesoReporte(
                reporte_id=reporte.id,
                fecha_hora=ahora_evento,
                ip_origen=ip_origen,
                accion="consulta_ia_confinada",
                detalle=pregunta[:500],
                user_agent=(user_agent or "")[:255] or None,
            )
        )
        reporte.ultimo_acceso_en = ahora_evento
        await session.commit()

        cliente_llm = await build_llm_client(session, reporte.espacio_id)
        t_inicio = time.perf_counter()
        dataset_tipo = "biblioteca" if reporte.espacio_id == 1 else "estacionamiento"
        modelo_usado = (
            getattr(cliente_llm, "default_model", None)
            or getattr(cliente_llm, "model_name", None)
            or getattr(cliente_llm, "model", None)
            or getattr(settings, "MODELO_GEMINI_POR_DEFECTO", "gemini-3.1-flash-lite")
        )
        sesion_limpia = (sesion_id or "principal").strip()[:64] or "principal"

        # Resolver ID del usuario autenticado o Consultor_Reporte sin atribuir accesos anónimos al creador
        usuario_auditoria_id = (
            usuario_actual.id
            if usuario_actual is not None and getattr(usuario_actual, "id", None) is not None
            else (usr_dest.id if usr_dest else getattr(reporte.destinatario, "usuario_id", None))
        )
        if not usuario_auditoria_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Se requiere una cuenta autenticada para consultar el Asistente IA.",
            )

        # Cargar últimos 6 turnos de esta sesión como contexto conversacional
        stmt_hist = (
            select(MensajeIAReporte)
            .where(
                MensajeIAReporte.reporte_id == reporte.id,
                MensajeIAReporte.sesion_id == sesion_limpia,
            )
            .order_by(MensajeIAReporte.creado_en.desc(), MensajeIAReporte.id.desc())
            .limit(6)
        )
        res_hist = await session.execute(stmt_hist)
        previos = list(reversed(res_hist.scalars().all())) if hasattr(res_hist, "scalars") else []
        historial_llm: List[Dict[str, str]] = []
        for m in previos:
            if m.pregunta:
                historial_llm.append({"role": "user", "content": m.pregunta})
            if m.respuesta:
                historial_llm.append({"role": "assistant", "content": m.respuesta})

        reporte_id_val = reporte.id
        reporte_codigo_val = reporte.codigo_corto
        es_sesion_real = isinstance(session, AsyncSession)
        if es_sesion_real:
            await session.close()

        estado_chat = "éxito"
        try:
            respuesta_texto = await cliente_llm.generate_response(
                prompt=prompt_completo,
                system_instruction=instruccion_sistema,
                temperature=0.15,
                history=historial_llm or None,
            )
            respuesta_texto = respuesta_texto or "No fue posible generar una síntesis con los datos actuales."
        except Exception as err_llm:
            estado_chat = "error"
            elapsed_err_ms = round((time.perf_counter() - t_inicio) * 1000, 2)
            try:
                await registrar_auditoria_chat(
                    usuario_id=usuario_auditoria_id,
                    prompt_text=f"[Reporte {reporte_codigo_val}] {pregunta[:400]}",
                    dataset_tipo=dataset_tipo,
                    modelo_utilizado=str(modelo_usado),
                    status=estado_chat,
                    response_time_ms=elapsed_err_ms,
                    respuesta_text=f"Error: {str(err_llm)[:300]}",
                    origen="reporte_compartido",
                    reporte_codigo=reporte_codigo_val,
                )
            except Exception as err_aud:
                logger.warning("No se pudo registrar auditoría de error IA en reporte compartido: %s", err_aud)
            raise

        elapsed_ms = round((time.perf_counter() - t_inicio) * 1000, 2)
        ahora_msg = ahora_chile_naive()
        nuevo_msg = MensajeIAReporte(
            reporte_id=reporte_id_val,
            sesion_id=sesion_limpia,
            usuario_id=usuario_auditoria_id,
            pregunta=pregunta,
            respuesta=respuesta_texto,
            modelo_utilizado=str(modelo_usado),
            tiempo_respuesta_ms=elapsed_ms,
            creado_en=ahora_msg,
        )
        if es_sesion_real:
            from app.core.database import AsyncSessionLocal
            async with AsyncSessionLocal() as s_msg:
                s_msg.add(nuevo_msg)
                await s_msg.commit()
                await s_msg.refresh(nuevo_msg)
        else:
            session.add(nuevo_msg)
            await session.commit()
            await session.refresh(nuevo_msg)

        try:
            await registrar_auditoria_chat(
                usuario_id=usuario_auditoria_id,
                prompt_text=f"[Reporte {reporte_codigo_val}] {pregunta[:400]}",
                dataset_tipo=dataset_tipo,
                modelo_utilizado=str(modelo_usado),
                status=estado_chat,
                response_time_ms=elapsed_ms,
                respuesta_text=respuesta_texto,
                origen="reporte_compartido",
                reporte_codigo=reporte_codigo_val,
            )
        except Exception as err_aud:
            logger.warning("No se pudo registrar telemetría IA de reporte compartido: %s", err_aud)

        usadas_post = int(cuota_previa.get("usadas") or 0) + 1
        limite_post = cuota_previa.get("limite")
        ilimitado_post = bool(cuota_previa.get("ilimitado"))
        cuota_post = {
            "usadas": usadas_post,
            "limite": limite_post,
            "restantes": None if ilimitado_post else max(0, int(limite_post or 0) - usadas_post),
            "ilimitado": ilimitado_post,
        }

        return {
            "id": nuevo_msg.id,
            "sesion_id": sesion_limpia,
            "pregunta": pregunta,
            "respuesta": respuesta_texto,
            "modelo_utilizado": str(modelo_usado),
            "tiempo_respuesta_ms": elapsed_ms,
            "timestamp": marcar_chile(ahora_msg).isoformat(),
            "cuota": cuota_post,
        }

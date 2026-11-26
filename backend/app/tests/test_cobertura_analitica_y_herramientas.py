"""Pruebas extensivas de servicios analíticos, herramientas de chat y generadores de gráficos."""
import asyncio
from contextlib import ExitStack
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.schemas.chat_schemas import ChatRequest
from app.services.attendance_service import AttendanceService
from app.services.chat import generadores_grafico
from app.services.chat.ejecutor_herramientas import (
    ejecutar_consulta_tool,
    limpiar_cache_herramientas_chat,
    resolver_datos_grafico_contexto,
)
from app.services.metrics_service import MetricsService
from app.services.vehicle_service import VehicleService


class _SmartRow(SimpleNamespace):
    """Fila compatible con acceso por atributo, _mapping e indexación posicional."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._mapping = dict(kwargs)
        self._vals = list(kwargs.values())

    def __getitem__(self, item):
        if isinstance(item, int):
            return self._vals[item]
        return self._mapping[item]

    def __iter__(self):
        return iter(self._vals)

    def __getattr__(self, _name):
        return None


def _crear_db_analitica(rows=None, scalar_val=2026):
    """Crea un AsyncMock de BD con filas sintéticas compatibles con cualquier query analítica."""
    sample_rows = rows or [
        _SmartRow(
            total_eventos=120,
            total_asistentes=95,
            fecha_min=date(2026, 3, 1),
            fecha_max=date(2026, 10, 31),
            fecha=date(2026, 10, 14),
            bucket=datetime(2026, 10, 14, 10, 0),
            hora=10,
            dia_semana="Miércoles",
            dia_semana_iso=3,
            anio=2026,
            semana=42,
            mes=10,
            mes_num=10,
            codigo="CSF02",
            sala_nombre="Sala 1 (CSF02)",
            puerta_nombre="CSF02-T1",
            subespacio="sala_1",
            espacio_nombre="Biblioteca",
            etiqueta="Ok",
            nombre="Test",
            estado="activo",
            total_marcajes=120,
            hora_punta_num=14,
            dias_operativos=5,
            total_registros=120,
            permanencia_mediana_min=35.0,
            dias_totales=10,
            tasa_jornada_extrema=15.0,
            porcentaje=50.0,
            pct=50.0,
            aforo_pico_simultaneo=25,
            total_accesos=120,
            perfil="Estándar (15-120 min)",
            promedio_min=90.0,
            total_entradas=120,
            total_salidas=110,
            vehiculos=30,
            vehiculos_unicos=25,
            lecturas_fallidas=1,
            total_pasos=30,
            origen="CSF",
            destino="CHS",
            minutos_traslado=15.0,
            hora_salida=10,
            cantidad=30,
            estudiantes=70,
            docentes=10,
            funcionarios=15,
            visitantes=5,
            externos=5,
            ingresos=120,
            max_ingresos=140,
            entradas=120,
            salidas=110,
            personas_unicas=95,
            usuarios_unicos=95,
            total_asistencias=120,
            inicio_semana=date(2026, 10, 12),
            semana_iso="2026-W42",
            max_dia=140,
            personas_sala1=70,
            personas_sala2=50,
            entradas_sala1=70,
            entradas_sala2=50,
            salidas_sala1=60,
            salidas_sala2=50,
            promedio_entradas=95.0,
            promedio_salidas=85.0,
            max_salidas=120,
            fecha_inicio=date(2026, 3, 1),
            fecha_fin=date(2026, 12, 20),
            total=120,
            total_general=120,
            aforo_actual=40,
            aforo_sala1=25,
            aforo_sala2=15,
            sala_1=70,
            sala_2=50,
            total_sala1=70,
            total_sala2=50,
            permanencia_promedio=45.0,
            permanencia_mediana=35.0,
            rotacion_diaria=2.1,
            tasa_rebote=5.0,
            door_entrada="CSF02-T1",
            door_salida="CSF02-T1",
            puerta="CSF02-T1",
            sentido="entrada",
            carrera="Ingeniería Civil Informática",
            facultad="Ingeniería",
            cohorte=2024,
            estudiantes_asistentes=60,
            total_estudiantes=100,
            eventos_asistencia=120,
            camara="CSF11-E1",
            sector="CSF11",
            direccion="entrada",
            tipo_vehiculo="SUV",
            marca="Toyota",
            color="Gris",
            calidad_lectura="ok",
            patente_hash="aabbccdd1122",
            person_id_hash="112233445566",
            primera_entrada=datetime(2026, 10, 14, 9, 0),
            ultima_salida=datetime(2026, 10, 14, 11, 0),
            permanencia_min=120.0,
            marcajes_totales=2,
            salida_imputada=0,
            entrada_imputada=0,
            alerta_coherencia_fechas=0,
            hito="Regular",
            tipo="regular",
            dias=5,
            promedio_diario=110.0,
            promedio_ingresos=95.0,
            ocupacion_promedio=55.0,
            vehiculos_presentes=30,
            plazas_ocupadas=30,
            max_event_time=datetime(2026, 10, 14, 10, 0),
            time=datetime(2026, 10, 14, 10, 0),
            dia_num=3,
        )
    ]

    class _Res:
        def __init__(self):
            self.rowcount = len(sample_rows)

        def scalar(self):
            return scalar_val

        def scalar_one_or_none(self):
            return None

        def fetchone(self):
            return sample_rows[0]

        def one(self):
            return sample_rows[0]

        def first(self):
            return sample_rows[0]

        def all(self):
            return sample_rows

        def fetchall(self):
            return sample_rows

        @property
        def scalars(self):
            m = MagicMock()
            m.all.return_value = sample_rows
            m.first.return_value = sample_rows[0]
            return m

        @property
        def mappings(self):
            m = MagicMock()
            m.all.return_value = [r._mapping for r in sample_rows]
            m.first.return_value = sample_rows[0]._mapping
            return m

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_Res())
    db.add = MagicMock()
    db.delete = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.close = AsyncMock()
    return db


def test_filtros_y_metodos_analiticos_attendance_y_vehicle():
    async def _run():
        db = _crear_db_analitica()
        f_ini, f_fin = date(2026, 10, 1), date(2026, 10, 14)

        with (
            patch("app.services.attendance_service.obtener_horarios_operacion_cacheados", new=AsyncMock(return_value=[])),
            patch("app.services.attendance_service.obtener_horarios_regulares_cacheados", new=AsyncMock(return_value=[])),
            patch("app.services.attendance_service.obtener_calendario_contingencias_cacheados", new=AsyncMock(return_value={
                "feriados": [],
                "paros_fed": [],
                "paros_car": [],
                "suspensiones_institucionales": [],
                "contingencias": [],
            })),
            patch("app.services.attendance_service.obtener_capacidades_salas_cacheadas", new=AsyncMock(return_value={"total": 276, "sala_1": 180, "sala_2": 96})),
            patch("app.services.vehicle_service.obtener_horarios_operacion_cacheados", new=AsyncMock(return_value=[])),
            patch("app.services.vehicle_service._obtener_capacidades_sectores_vehiculares", new=AsyncMock(return_value={"total": 125, "CSF11": 60, "CSF21": 40, "CHS01": 25})),
            patch("app.services.config_service.get_horarios_operacion", new=AsyncMock(return_value=[])),
        ):
            w_sql, w_params = await AttendanceService._build_attendance_filters(
                session=db,
                espacio_id=1,
                fecha_inicio=f_ini,
                fecha_fin=f_fin,
                alcance="conformes",
                regimen_horario="dentro_horario",
                direccion="entrada",
                dias_semana="1,2,3",
                door="CSF02-T1",
                perfil_visita="media",
                marcajes="normal",
                sala="sala_1",
                carrera="Informática",
                facultad="Ingeniería",
                cohorte="2024",
                incluir_pausas_bano=False,
                desduplicar_rafagas=True,
                incluir_funcionarios=False,
                incluir_sin_identificar=False,
            )
            assert "espacio_id = :espacio_id" in w_sql and w_params["espacio_id"] == 1

            # Métodos clave de AttendanceService
            assert isinstance(await AttendanceService.get_occupancy_realtime(db, espacio_id=1), dict)
            assert isinstance(await AttendanceService.get_hourly_flow(db, fecha_inicio=f_ini, fecha_fin=f_fin), list)
            assert isinstance(await AttendanceService.get_heatmap(db, espacio_id=1, fecha_inicio=f_ini, fecha_fin=f_fin), list)
            assert isinstance(await AttendanceService.get_peak_valley_bands(db, espacio_id=1, fecha_inicio=f_ini, fecha_fin=f_fin), list)
            assert isinstance(await AttendanceService.get_weekly_evolution(db, espacio_id=1, fecha_inicio=f_ini, fecha_fin=f_fin), list)
            assert isinstance(await AttendanceService.get_monthly_volume(db, espacio_id=1, fecha_inicio=f_ini, fecha_fin=f_fin), list)
            assert isinstance(await AttendanceService.get_door_usage(db, espacio_id=1, fecha_inicio=f_ini, fecha_fin=f_fin), list)
            assert isinstance(await AttendanceService.get_rooms_comparison(db, espacio_id=1, fecha_inicio=f_ini, fecha_fin=f_fin), dict)
            assert isinstance(await AttendanceService.get_daily_average_attendance(db, espacio_id=1, fecha_inicio=f_ini, fecha_fin=f_fin), dict)
            assert isinstance(await AttendanceService.get_realtime_presence_curve(db, espacio_id=1, fecha_inicio=f_ini, fecha_fin=f_fin), list)
            assert isinstance(await AttendanceService.get_curricular_distribution(db, espacio_id=1, fecha_inicio=f_ini, fecha_fin=f_fin), dict)
            assert isinstance(await AttendanceService.get_available_filters(db, espacio_id=1), dict)
            assert isinstance(await AttendanceService.get_checkin_distribution(db, espacio_id=1, fecha_inicio=f_ini, fecha_fin=f_fin), list)
            assert isinstance(await AttendanceService.get_visit_profiles_donut(db, espacio_id=1, fecha_inicio=f_ini, fecha_fin=f_fin), dict)
            assert isinstance(await AttendanceService.get_academic_milestones_comparison(db, espacio_id=1), list)
            assert isinstance(await AttendanceService.get_raw_events(db, espacio_id=1, fecha_inicio=f_ini, fecha_fin=f_fin, page_size=10), dict)
            assert isinstance(await AttendanceService.get_daily_summary(db, espacio_id=1), list)
            csv_a, cnt_a = await AttendanceService.export_raw_csv(db, espacio_id=1, fecha_inicio=f_ini, fecha_fin=f_fin, limit=10)
            assert cnt_a >= 0 and "Identificador_Seudonimizado" in csv_a

            # VehicleService filtros y analítica
            vw_sql, vw_params = await VehicleService._build_vehicle_filters(
                session=db,
                espacio_id=2,
                fecha_inicio=f_ini,
                fecha_fin=f_fin,
                alcance="todos",
                regimen_horario="todos",
                direccion="entrada",
                dias_semana="1,2,3",
                door="CSF11-E1",
                sector="CSF11",
                tipo_vehiculo="SUV",
            )
            assert "espacio_id = :espacio_id" in vw_sql and vw_params["espacio_id"] == 2
            assert isinstance(await VehicleService.get_parking_occupancy(db, espacio_id=2), dict)
            assert isinstance(await VehicleService.get_hourly_flow(db, fecha_inicio=f_ini, fecha_fin=f_fin), list)
            assert isinstance(await VehicleService.get_fleet_composition(db, fecha_inicio=f_ini, fecha_fin=f_fin), dict)
            assert isinstance(await VehicleService.get_daily_evolution(db, fecha_inicio=f_ini, fecha_fin=f_fin), list)
            assert isinstance(await VehicleService.get_camera_stats(db, fecha_inicio=f_ini, fecha_fin=f_fin), list)
            assert isinstance(await VehicleService.get_intercampus_mobility(db, fecha_inicio=f_ini, fecha_fin=f_fin), dict)
            assert isinstance(await VehicleService.get_academic_milestones_comparison(db, espacio_id=2), list)
            csv_v, cnt_v = await VehicleService.export_raw_csv(db, espacio_id=2, fecha_inicio=f_ini, fecha_fin=f_fin, limit=10)
            assert cnt_v >= 0 and "Patente_Seudonimizada" in csv_v

            # MetricsService
            assert isinstance(await MetricsService.get_kpi_summary(db, espacio_id=1, fecha_inicio=f_ini, fecha_fin=f_fin), dict)
            assert isinstance(await MetricsService.get_date_bounds(db, espacio_id=1), dict)

    asyncio.run(_run())


def test_generadores_grafico_completos():
    async def _run():
        db = _crear_db_analitica()
        for ds in ("biblioteca", "estacionamiento"):
            f1, d1, m1 = await generadores_grafico.generate_weekly_chart(db, ds)
            assert f1 is not None and d1 and "Semana" in m1
            f2, d2, m2 = await generadores_grafico.generate_peak_hours_chart(db, ds)
            assert f2 is not None and d2 and m2
            f3, d3, m3 = await generadores_grafico.generate_monthly_trend_chart(db, ds, 8, 10)
            assert f3 is not None and d3 and m3

        f_ex, d_ex, m_ex = await generadores_grafico.generate_exams_impact_chart(db)
        assert f_ex is not None and d_ex and m_ex
        f_cam, d_cam, m_cam = await generadores_grafico.generate_cameras_chart(db)
        assert f_cam is not None and d_cam and m_cam

    asyncio.run(_run())


def test_ejecutor_herramientas_y_contexto_amplio():
    async def _run():
        limpiar_cache_herramientas_chat()
        db = _crear_db_analitica()
        req_bib = ChatRequest(prompt="Análisis de octubre 2026", dataset_tipo="biblioteca", session_id="s-bib", fecha_inicio="2026-10-01", fecha_fin="2026-10-14")
        req_veh = ChatRequest(prompt="Análisis de octubre 2026", dataset_tipo="estacionamiento", session_id="s-veh", fecha_inicio="2026-10-01", fecha_fin="2026-10-14")

        parches = [
            patch("app.services.chat.ejecutor_herramientas.obtener_anio_activo_espacio", new=AsyncMock(return_value=2026)),
            patch("app.services.chat.ejecutor_herramientas.obtener_contexto_calendario_rango", new=AsyncMock(return_value=[])),
            patch("app.services.chat.ejecutor_herramientas.obtener_resumen_hechos_institucionales", new=AsyncMock(return_value="Hechos UCT")),
            patch("app.services.attendance_service.AttendanceService.get_kpis", new=AsyncMock(return_value={"total_registros": 100})),
            patch("app.services.attendance_service.AttendanceService.get_occupancy_realtime", new=AsyncMock(return_value={"aforo_actual": 30, "capacidad": 276})),
            patch("app.services.attendance_service.AttendanceService.get_hourly_flow", new=AsyncMock(return_value=[{"hora": "10:00", "entradas": 50, "salidas": 20}])),
            patch("app.services.attendance_service.AttendanceService.get_peak_valley_bands", new=AsyncMock(return_value={"picos": [{"hora": "11:00", "promedio": 90}], "valles": []})),
            patch("app.services.attendance_service.AttendanceService.get_heatmap", new=AsyncMock(return_value=[{"dia_semana": "Lunes", "hora": "11:00", "ocupacion_promedio": 90}])),
            patch("app.services.attendance_service.AttendanceService.get_curricular_distribution", new=AsyncMock(return_value={"carreras": [{"carrera": "Inf", "eventos_asistencia": 50}], "facultades": [], "cohortes": []})),
            patch("app.services.attendance_service.AttendanceService.get_door_usage", new=AsyncMock(return_value=[{"puerta": "CSF02-T1", "entradas": 40, "salidas": 30}])),
            patch("app.services.attendance_service.AttendanceService.get_rooms_comparison", new=AsyncMock(return_value=[{"sala": "Sala 1", "ingresos": 80}])),
            patch("app.services.attendance_service.AttendanceService.get_visit_profiles_donut", new=AsyncMock(return_value={"perfiles": [{"perfil": "Media", "cantidad": 10}]})),
            patch("app.services.attendance_service.AttendanceService.get_weekly_evolution", new=AsyncMock(return_value=[{"semana_iso": "S42", "inicio_semana": "2026-10-12", "total_asistencias": 300, "usuarios_unicos": 200}])),
            patch("app.services.attendance_service.AttendanceService.get_monthly_volume", new=AsyncMock(return_value=[{"mes": "Oct", "mes_num": 10, "total_asistencias": 1000, "usuarios_unicos": 400, "promedio_diario": 100}])),
            patch("app.services.attendance_service.AttendanceService.get_academic_milestones_comparison", new=AsyncMock(return_value=[{"hito": "Regular", "promedio": 100}])),
            patch("app.services.vehicle_service.VehicleService.get_kpis", new=AsyncMock(return_value={"vehiculos_unicos": 50})),
            patch("app.services.vehicle_service.VehicleService.get_parking_occupancy", new=AsyncMock(return_value={"vehiculos_dentro": 20, "capacidad": 125})),
            patch("app.services.vehicle_service.VehicleService.get_hourly_flow", new=AsyncMock(return_value=[{"hora": "09:00", "entradas": 20, "salidas": 5}])),
            patch("app.services.vehicle_service.VehicleService.get_fleet_composition", new=AsyncMock(return_value={"tipos": [{"tipo": "SUV", "total": 20}], "marcas": [{"marca": "Toyota", "total": 15}]})),
            patch("app.services.vehicle_service.VehicleService.get_camera_stats", new=AsyncMock(return_value=[{"camara": "CSF11-E1", "total": 30}])),
            patch("app.services.vehicle_service.VehicleService.get_intercampus_mobility", new=AsyncMock(return_value={"flujos": [{"origen": "CSF", "destino": "CHS", "total": 5}]})),
            patch("app.services.prediction_service.get_prophet_presence_forecast", new=AsyncMock(return_value={"pronostico_7d": [{"ds": "2026-10-15 10:00", "yhat": 70}]})),
            patch("app.services.prediction_service.get_prophet_forecast", new=AsyncMock(return_value={"pronostico_7d": [{"ds": "2026-10-15 10:00", "yhat": 25}]})),
            patch("app.services.chat.ejecutor_herramientas.get_prophet_presence_forecast", new=AsyncMock(return_value={"pronostico_7d": [{"ds": "2026-10-15 10:00", "yhat": 70}]})),
            patch("app.services.chat.ejecutor_herramientas.get_prophet_forecast", new=AsyncMock(return_value={"pronostico_7d": [{"ds": "2026-10-15 10:00", "yhat": 25}]})),
        ]
        with ExitStack() as stack:
            for p in parches:
                stack.enter_context(p)
            for t_bib in (
                "consultar_picos_flujo",
                "consultar_proyeccion_prophet",
                "consultar_kpis_actuales",
                "consultar_distribucion_carreras",
                "consultar_torniquetes_accesos",
                "consultar_comparativa_salas",
                "consultar_perfiles_visita",
                "consultar_evolucion_semanal",
                "consultar_volumen_mensual",
                "consultar_aforo_historico",
            ):
                comp, _, msg, _, _ = await ejecutar_consulta_tool(t_bib, {}, db, espacio_id=1, req=req_bib)
                assert isinstance(msg, str)

            for t_veh in (
                "consultar_picos_flujo",
                "consultar_proyeccion_prophet",
                "consultar_kpis_actuales",
                "consultar_flota_vehicular",
                "consultar_camaras_anpr",
                "consultar_movilidad_intercampus",
                "consultar_aforo_historico",
            ):
                comp, _, msg, _, _ = await ejecutar_consulta_tool(t_veh, {}, db, espacio_id=2, req=req_veh)
                assert isinstance(msg, str)

            for g_bib in (
                "flujo_horario",
                "mapa_calor",
                "comparativa_salas",
                "uso_torniquetes",
                "volumen_mensual",
                "evolucion_semanal",
                "distribucion_curricular",
                "perfiles_visita",
            ):
                _, _, msg_g, _, _ = await resolver_datos_grafico_contexto(
                    g_bib, 1, "2026-10-01", "2026-10-14", db
                )
                assert isinstance(msg_g, str)

            for g_veh in ("flujo_horario_vehicular", "composicion_flota", "estadisticas_camaras", "movilidad_intercampus"):
                _, _, msg_gv, _, _ = await resolver_datos_grafico_contexto(
                    g_veh, 2, "2026-10-01", "2026-10-14", db
                )
                assert isinstance(msg_gv, str)

    asyncio.run(_run())

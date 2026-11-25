"""Pruebas automatizadas para alertas de bloqueo al SuperAdmin y recorte a hora presente."""
import asyncio
from datetime import date, datetime, timezone
import os
import sys
from types import SimpleNamespace
from typing import List
from unittest.mock import patch

import pytest
from fastapi import BackgroundTasks, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.api.v1.endpoints import predictions as predictions_endpoint
from app.core.cache import limpiar_toda_la_cache
from app.core.database import get_db
from app.core.security import get_current_user
from app.domain.auth_models import NotificacionAdmin, Rol, TokenActivacion, Usuario
from app.main import app
from app.ml.prophet_service import _normalizar_sector_vehicular
from app.services import auth_service
from app.services.attendance_service import (
    AttendanceService,
    _calcular_curva_presencia_por_hora,
    _construir_expresiones_limites_presencia,
    _construir_sql_horario_regular,
    _extraer_hora_pico_curva,
    _rellenar_dias_operativos_sin_registros,
    cache_horarios_espacio,
    invalidar_cache_horarios,
    obtener_capacidades_salas_cacheadas,
)
from app.services.config_service import _normalizar_subespacio, es_horario_conforme
from app.services.email_service import enviar_correo_bloqueo_login
from app.services.vehicle_service import VehicleService


def _crear_usuario_prueba(email: str, rol_nombre: str, password: str = "ClaveSegura2026!") -> Usuario:
    u = Usuario(
        id=101,
        email=email,
        nombre_completo=f"Prueba {rol_nombre}",
        hashed_password=auth_service.hash_password(password),
        is_active=True,
        espacio_id=1,
        allowed_datasets=["biblioteca", "estacionamiento"],
        intentos_fallidos_login=0,
        bloqueado_hasta=None,
    )
    u.roles = [Rol(id=1, nombre=rol_nombre)]
    return u


def test_bloqueo_cinco_intentos_crea_notificacion_y_agenda_correo():
    usuario = _crear_usuario_prueba("analista.bloqueo@uct.cl", "Analista_Consulta")
    objetos_guardados: List[object] = []

    class _FakeDb:
        def add(self, obj):
            objetos_guardados.append(obj)

        async def commit(self):
            return None

    async def _fake_get_user(_db, _email):
        return usuario

    async def _run():
        bg = BackgroundTasks()
        db = _FakeDb()

        with patch.object(auth_service, "get_user_by_email", _fake_get_user):
            # Primeros 4 intentos fallidos: 401 sin bloqueo ni correo
            for intento in range(1, 5):
                with pytest.raises(HTTPException) as exc:
                    await auth_service.authenticate_user(
                        db=db,
                        email=usuario.email,
                        password="PasswordIncorrecta!",
                        ip_origen="10.20.30.40",
                        background_tasks=bg,
                    )
                assert exc.value.status_code == 401
                assert f"Le quedan {5 - intento} intento(s)" in exc.value.detail
            assert len(bg.tasks) == 0
            assert len(objetos_guardados) == 0

            # 5.º intento fallido: bloqueo 423 + notificación admin + token recuperación + correo
            with pytest.raises(HTTPException) as exc_blk:
                await auth_service.authenticate_user(
                    db=db,
                    email=usuario.email,
                    password="PasswordIncorrecta!",
                    ip_origen="10.20.30.40",
                    background_tasks=bg,
                )
            assert exc_blk.value.status_code == 423
            assert usuario.bloqueado_hasta is not None
            assert usuario.bloqueado_hasta > datetime.now(timezone.utc)

            notifs = [o for o in objetos_guardados if isinstance(o, NotificacionAdmin)]
            tokens = [o for o in objetos_guardados if isinstance(o, TokenActivacion)]
            assert len(notifs) == 1
            assert notifs[0].tipo == "bloqueo_login"
            assert notifs[0].leida is False
            assert notifs[0].intentos_fallidos == 5
            assert notifs[0].ip_origen == "10.20.30.40"
            assert notifs[0].usuario_afectado_email == usuario.email

            assert len(tokens) == 1
            assert tokens[0].tipo_token == "RECUPERACION_PASSWORD"
            assert tokens[0].utilizado is False

            assert len(bg.tasks) == 1
            tarea = bg.tasks[0]
            assert tarea.func is enviar_correo_bloqueo_login
            assert tarea.args[0] == usuario.email
            assert "/recuperar-password?token=" in tarea.args[2]
            assert tarea.args[3] == 5

    asyncio.run(_run())


def test_rbac_y_flujo_marcar_vistas_notificaciones_admin():
    notif = NotificacionAdmin(
        id=1,
        tipo="bloqueo_login",
        titulo="Cuenta bloqueada tras 5 intentos fallidos",
        mensaje="El usuario bloqueado@uct.cl falló 5 veces consecutivas.",
        usuario_afectado_id=101,
        usuario_afectado_email="bloqueado@uct.cl",
        usuario_afectado_nombre="Usuario Prueba",
        intentos_fallidos=5,
        ip_origen="192.168.10.25",
        leida=False,
        creado_en=datetime.utcnow(),
    )

    class _FakeResult:
        def __init__(self, items=None, scalar_val=None, rowcount=0):
            self._items = items or []
            self._scalar = scalar_val
            self.rowcount = rowcount

        def scalars(self):
            return SimpleNamespace(all=lambda: list(self._items))

        def all(self):
            return list(self._items)

        def scalar(self):
            return self._scalar

        def scalar_one_or_none(self):
            return self._items[0] if self._items else None

    class _FakeSession:
        async def execute(self, stmt):
            sql_str = str(stmt)
            if "UPDATE notificaciones_admin" in sql_str:
                cnt = 0
                if not notif.leida:
                    notif.leida = True
                    notif.leida_en = datetime.utcnow()
                    cnt = 1
                return _FakeResult(rowcount=cnt)
            if "count(notificaciones_admin.id)" in sql_str.lower():
                return _FakeResult(scalar_val=0 if notif.leida else 1)
            if "FROM usuarios" in sql_str:
                return _FakeResult(items=[(101, None)])
            if "FROM notificaciones_admin" in sql_str:
                return _FakeResult(items=[notif])
            return _FakeResult()

        async def commit(self):
            return None

    async def _fake_db():
        yield _FakeSession()

    try:
        # 1. Roles no SuperAdmin deben recibir 403
        for rol in ("Director_Recinto", "Analista_Consulta"):
            no_admin = _crear_usuario_prueba(f"{rol.lower()}@uct.cl", rol)
            app.dependency_overrides[get_current_user] = lambda u=no_admin: u
            app.dependency_overrides[get_db] = _fake_db
            client = TestClient(app)

            assert client.get("/api/v1/admin/notificaciones").status_code == 403
            assert client.post("/api/v1/admin/notificaciones/marcar-vistas").status_code == 403
            assert client.delete("/api/v1/admin/notificaciones/1").status_code == 403

        # 2. SuperAdmin ve no_leidas=1 y tras marcar-vistas pasa a no_leidas=0
        admin = _crear_usuario_prueba("admin@uct.cl", "Admin_Sistema")
        app.dependency_overrides[get_current_user] = lambda: admin
        app.dependency_overrides[get_db] = _fake_db
        client = TestClient(app)

        r1 = client.get("/api/v1/admin/notificaciones")
        assert r1.status_code == 200, r1.text
        data1 = r1.json()
        assert data1["no_leidas"] == 1
        assert len(data1["items"]) == 1
        assert data1["items"][0]["leida"] is False

        r_mark = client.post("/api/v1/admin/notificaciones/marcar-vistas")
        assert r_mark.status_code == 200, r_mark.text
        assert r_mark.json()["marcadas"] == 1
        assert r_mark.json()["no_leidas"] == 0

        r2 = client.get("/api/v1/admin/notificaciones")
        assert r2.status_code == 200
        data2 = r2.json()
        assert data2["no_leidas"] == 0
        assert data2["items"][0]["leida"] is True
    finally:
        app.dependency_overrides.clear()


def test_sql_curvas_reales_recortan_a_getdate():
    sqls_capturadas: List[str] = []

    class _FakeExecResult:
        def scalar(self):
            return 0

        def fetchall(self):
            return []

    class _CaptureSession:
        async def execute(self, stmt, _params=None):
            sqls_capturadas.append(str(stmt))
            return _FakeExecResult()

    async def _run():
        db = _CaptureSession()
        hoy = date.today()
        await VehicleService.get_realtime_presence_curve(db, hoy, hoy, espacio_id=2, sector="CHS01")
        await VehicleService.get_hourly_flow(db, hoy, hoy, espacio_id=2, sector="CHS01")
        await AttendanceService.get_realtime_presence_curve(db, hoy, hoy, espacio_id=1)

    asyncio.run(_run())

    sql_veh_curve = next(s for s in sqls_capturadas if "SELECT" in s and "e.sector_num" in s and "e.time AS t_entrada" in s)
    assert "time <= GETDATE()" in sql_veh_curve
    assert "WHEN DATEADD(MINUTE, 120, e.time) > c_lim THEN c_lim" in sql_veh_curve
    assert "> GETDATE() THEN GETDATE()" in sql_veh_curve

    sql_veh_flow = next(s for s in sqls_capturadas if "deltas_estancia" in s)
    assert "time <= GETDATE()" in sql_veh_flow
    assert "WHEN DATEADD(hour, 2, time) > GETDATE()" in sql_veh_flow

    sql_bib_ses = next(s for s in sqls_capturadas if "cap_vivo" in s)
    assert "time <= GETDATE()" in sql_bib_ses
    assert "DATEDIFF(MINUTE, e.time, GETDATE()) <= 180" in sql_bib_ses
    assert "DATEADD(MINUTE, 60, e.time)" in sql_bib_ses
    assert "DATEADD(MINUTE, -60, e.time)" in sql_bib_ses

    sql_bib_flujo = next(s for s in sqls_capturadas if "FlujoBruto" in s)
    assert "time <= GETDATE()" in sql_bib_flujo


def test_prophet_vehicular_normalizacion_y_endpoint_por_sector():
    assert _normalizar_sector_vehicular(None) == "todos"
    assert _normalizar_sector_vehicular("todos") == "todos"
    assert _normalizar_sector_vehicular("todas") == "todos"
    assert _normalizar_sector_vehicular("csf11") == "CSF11"
    assert _normalizar_sector_vehicular("CSF21") == "CSF21"
    assert _normalizar_sector_vehicular("ChS01") == "CHS01"
    assert _normalizar_sector_vehicular("otro'; DROP TABLE--") == "todos"

    assert _normalizar_subespacio("csf11") == "CSF11"
    assert _normalizar_subespacio("csf21") == "CSF21"
    assert _normalizar_subespacio("chs01") == "CHS01"

    llamadas = []

    async def _fake_get_prophet_forecast(_db, recinto: str, sala: str = "todas"):
        llamadas.append((recinto, sala))
        caps = {"CSF11": 40, "CSF21": 50, "CHS01": 35}
        return {
            "recinto": recinto,
            "sala": sala,
            "sector": sala,
            "capacidad_asientos": caps.get(sala, 125),
            "forecast": [],
            "model_status": {"status": "ok", "model_date": "2026-11-19 23:00"},
        }

    class _FakeDb:
        pass

    async def _fake_db():
        yield _FakeDb()

    asyncio.run(limpiar_toda_la_cache())
    usuario = _crear_usuario_prueba("analista.vehicular@uct.cl", "Analista_Consulta")
    app.dependency_overrides[get_current_user] = lambda: usuario
    app.dependency_overrides[get_db] = _fake_db

    try:
        with patch.object(predictions_endpoint, "get_prophet_forecast", _fake_get_prophet_forecast):
            client = TestClient(app)
            r1 = client.get("/api/v1/predictions/forecast-parking?sector=CSF11")
            assert r1.status_code == 200, r1.text
            assert r1.json()["sala"] == "CSF11"
            assert r1.json()["capacidad_asientos"] == 40

            r2 = client.get("/api/v1/predictions/forecast-parking?sector=CHS01")
            assert r2.status_code == 200, r2.text
            assert r2.json()["sala"] == "CHS01"
            assert r2.json()["capacidad_asientos"] == 35

        assert llamadas == [("vehicular", "CSF11"), ("vehicular", "CHS01")]
    finally:
        app.dependency_overrides.clear()
        asyncio.run(limpiar_toda_la_cache())


def test_analisis_24h_dinamico_multianio_y_consolidado_por_rango():
    campanas_mock = [
        SimpleNamespace(
            id=20,
            descripcion="Campaña 24h Junio 2027",
            fecha_inicio=datetime(2027, 6, 1, 0, 0),
            fecha_fin=datetime(2027, 6, 30, 0, 0),
            subespacio="sala_2",
        ),
        SimpleNamespace(
            id=9,
            descripcion="Campaña 24h Noviembre 2026",
            fecha_inicio=datetime(2026, 11, 2, 0, 0),
            fecha_fin=datetime(2026, 11, 28, 0, 0),
            subespacio="sala_2",
        ),
        SimpleNamespace(
            id=11,
            descripcion="Campaña 24h Junio 2026",
            fecha_inicio=datetime(2026, 6, 1, 0, 0),
            fecha_fin=datetime(2026, 6, 30, 0, 0),
            subespacio="sala_2",
        ),
    ]

    class _FakeExec24h:
        def __init__(self, first_row=None, all_rows=None, scalar_items=None):
            self._first = first_row
            self._all = all_rows or []
            self._scalars = scalar_items or []

        def scalars(self):
            return SimpleNamespace(
                all=lambda: list(self._scalars),
                first=lambda: self._scalars[0] if self._scalars else None,
            )

        def first(self):
            return self._first

        def fetchall(self):
            return list(self._all)

    class _CaptureSession24h:
        def __init__(self):
            self.consultas = []

        async def execute(self, stmt, params=None):
            sql_str = str(stmt)
            self.consultas.append((sql_str, dict(params or {})))
            if "FROM horarios_operacion" in sql_str:
                return _FakeExec24h(scalar_items=campanas_mock)
            if "AS ingresos_diurnos" in sql_str:
                vacio = "1 = 0" in sql_str
                return _FakeExec24h(
                    first_row=SimpleNamespace(
                        ingresos_diurnos=0 if vacio else 900,
                        ingresos_nocturnos=0 if vacio else 100,
                        total_ingresos=0 if vacio else 1000,
                        estudiantes_nocturnos_unicos=0 if vacio else 60,
                        estudiantes_totales_unicos=0 if vacio else 400,
                        horas_estudio_nocturnas=0.0 if vacio else 180.0,
                        permanencia_promedio_nocturna_min=0.0 if vacio else 140.0,
                        permanencia_promedio_diurna_min=0.0 if vacio else 105.0,
                    )
                )
            if "estudiantes_presencia_total" in sql_str:
                return _FakeExec24h(first_row=SimpleNamespace(estudiantes_presencia_total=65))
            if "fase_vespertina" in sql_str:
                return _FakeExec24h(first_row=SimpleNamespace(fase_vespertina=30, fase_profunda=50, fase_cierre=20))
            if "AS concurrencia" in sql_str:
                return _FakeExec24h(first_row=SimpleNamespace(hora=23, concurrencia=42))
            if "AS nocturnos" in sql_str:
                return _FakeExec24h(first_row=SimpleNamespace(nocturnos=50, diurnos=450, est_nocturnos=30, horas_nocturnas=100.0))
            return _FakeExec24h(all_rows=[])

    async def _run():
        # 1. Marzo 2027 sin campañas activas: consolidado acotado debe desactivarse en 0
        ses_mar27 = _CaptureSession24h()
        res_mar27 = await AttendanceService.get_analisis_24h(
            session=ses_mar27,
            espacio_id=1,
            campana_id=0,
            fecha_inicio=date(2027, 3, 1),
            fecha_fin=date(2027, 3, 31),
        )
        assert res_mar27["campana"]["tiene_campana_activa"] is False
        assert res_mar27["kpis_comparativa"]["ingresos_nocturnos"] == 0
        assert res_mar27["kpis_comparativa"]["porcentaje_delta_24h"] == 0.0
        item_global = next(c for c in res_mar27["campanas_disponibles"] if c["id"] == 0)
        assert "2026–2027 (3 campañas)" in item_global["descripcion"]
        sql_kpi_mar = next(s for s, _ in ses_mar27.consultas if "AS ingresos_diurnos" in s)
        assert "1 = 0" in sql_kpi_mar

        # 2. Año 2026 completo: consolidado acotado incluye solo las 2 campañas de 2026 y excluye 2027
        ses_2026 = _CaptureSession24h()
        res_2026 = await AttendanceService.get_analisis_24h(
            session=ses_2026,
            espacio_id=1,
            campana_id=0,
            fecha_inicio=date(2026, 1, 1),
            fecha_fin=date(2026, 12, 31),
        )
        assert res_2026["campana"]["tiene_campana_activa"] is True
        assert "2 campañas en período" in res_2026["campana"]["descripcion"]
        assert res_2026["campana"]["fecha_inicio"] == "2026-06-01"
        assert res_2026["campana"]["fecha_fin"] == "2026-11-28"
        _, params_kpi_26 = next((s, p) for s, p in ses_2026.consultas if "AS ingresos_diurnos" in s)
        assert params_kpi_26["c_ini_0"] == date(2026, 11, 2)
        assert params_kpi_26["c_ini_1"] == date(2026, 6, 1)
        assert "c_ini_2" not in params_kpi_26

    asyncio.run(_run())


def test_barrido_presencia_por_minuto_casos_borde():
    ahora = datetime(2026, 11, 20, 23, 0, 0)
    dia = date(2026, 11, 19)

    # 1. Visitas cortas (< 1h) simultáneas: 12:02-12:12 y 12:10-12:20 => pico 2 en hora 12
    sesiones_solapadas = [
        (dia, 1, datetime(2026, 11, 19, 12, 10), datetime(2026, 11, 19, 12, 20)),
        (dia, 2, datetime(2026, 11, 19, 12, 2), datetime(2026, 11, 19, 12, 12)),
    ]
    flujo_1 = [(datetime(2026, 11, 19, 12, 0), dia, 2, 2, 1, 1)]
    res1 = _calcular_curva_presencia_por_hora(sesiones_solapadas, flujo_1, ahora)
    assert len(res1) == 1
    assert res1[0]["personas_unicas"] == 2
    assert res1[0]["personas_sala1"] == 1
    assert res1[0]["personas_sala2"] == 1

    # 2. Dos visitas cortas NO superpuestas en la misma hora: 12:05-12:15 y 12:20-12:30 => pico 1
    sesiones_secuenciales = [
        (dia, 2, datetime(2026, 11, 19, 12, 5), datetime(2026, 11, 19, 12, 15)),
        (dia, 2, datetime(2026, 11, 19, 12, 20), datetime(2026, 11, 19, 12, 30)),
    ]
    res2 = _calcular_curva_presencia_por_hora(sesiones_secuenciales, flujo_1, ahora)
    assert len(res2) == 1
    assert res2[0]["personas_unicas"] == 1

    # 3. Arrastre limpio por horas intermedias sin eventos: 10:15 -> 13:20
    sesiones_arrastre = [
        (dia, 1, datetime(2026, 11, 19, 10, 15), datetime(2026, 11, 19, 13, 20)),
    ]
    flujo_arrastre = [
        (datetime(2026, 11, 19, 10, 0), dia, 1, 0, 1, 0),
        (datetime(2026, 11, 19, 13, 0), dia, 0, 1, 0, 0),
    ]
    res3 = _calcular_curva_presencia_por_hora(sesiones_arrastre, flujo_arrastre, ahora)
    por_hora3 = {datetime.fromisoformat(r["bucket"]).hour: r["personas_unicas"] for r in res3}
    assert por_hora3 == {10: 1, 11: 1, 12: 1, 13: 1}

    # 4. Salida exacta en el borde horario 13:00:00 (2 personas 10:00 -> 13:00:00)
    sesiones_borde = [
        (dia, 2, datetime(2026, 11, 19, 10, 0), datetime(2026, 11, 19, 13, 0)),
        (dia, 2, datetime(2026, 11, 19, 10, 0), datetime(2026, 11, 19, 13, 0)),
    ]
    flujo_borde = [
        (datetime(2026, 11, 19, 10, 0), dia, 2, 0, 0, 2),
        (datetime(2026, 11, 19, 13, 0), dia, 0, 2, 0, 0),
    ]
    res4 = _calcular_curva_presencia_por_hora(sesiones_borde, flujo_borde, ahora)
    por_hora4 = {datetime.fromisoformat(r["bucket"]).hour: r["personas_unicas"] for r in res4}
    assert por_hora4 == {10: 2, 11: 2, 12: 2, 13: 0}


def test_filtros_usuarios_y_aforo_vivo_calibrado():
    class _FakeExecVivo:
        def __init__(self, scalar_val=None, first_row=None, all_rows=None):
            self._scalar = scalar_val
            self._first = first_row
            self._all = all_rows or []

        def scalar(self):
            return self._scalar

        def scalar_one_or_none(self):
            return self._scalar

        def first(self):
            return self._first

        def fetchall(self):
            return list(self._all)

    class _CaptureSessionVivo:
        def __init__(self, ts_real: datetime):
            self.consultas = []
            self.ts_real = ts_real

        async def execute(self, stmt, params=None):
            sql_str = str(stmt)
            self.consultas.append((sql_str, dict(params or {})))
            if "FROM horarios_operacion" in sql_str:
                return _FakeExecVivo(all_rows=[])
            if "FROM salas_biblioteca" in sql_str:
                return _FakeExecVivo(all_rows=[SimpleNamespace(
                    id=1, codigo="CSF02", nombre="Sala 1", edificio="CSF02",
                    piso="2", descripcion="", capacidad_asientos=124,
                    permite_horario_extendido=False, puerta_principal_in="",
                    puerta_principal_out="", puerta_universal_in="",
                    puerta_universal_out="", activo=True,
                )])
            if "MAX(time) AS ultimo_ts" in sql_str:
                return _FakeExecVivo(scalar_val=self.ts_real)
            if "AS aforo_actual" in sql_str:
                return _FakeExecVivo(first_row=SimpleNamespace(aforo_actual=18, aforo_sala1=18, aforo_sala2=0))
            return _FakeExecVivo(all_rows=[])

    async def _run():
        ts_esperado = datetime(2026, 11, 20, 17, 42, 15)
        ses = _CaptureSessionVivo(ts_esperado)

        where_def, _ = await AttendanceService._build_attendance_filters(ses, espacio_id=1)
        assert "Funcionario" not in where_def
        assert "Sin persona identificada" not in where_def

        where_fil, _ = await AttendanceService._build_attendance_filters(
            ses, espacio_id=1, incluir_funcionarios=False, incluir_sin_identificar=False
        )
        assert "COALESCE(facultad, '') <> 'Funcionario'" in where_fil
        assert "COALESCE(facultad, '') <> 'Sin persona identificada'" in where_fil

        vivo = await AttendanceService.get_occupancy_realtime(
            ses, espacio_id=1, sala="sala_1", incluir_funcionarios=False, incluir_sin_identificar=False
        )
        sql_vivo = next(s for s, _ in ses.consultas if "AS aforo_actual" in s)
        assert "DATEDIFF(MINUTE, e.time, GETDATE()) <= 180" in sql_vivo
        assert "COALESCE(facultad, '') <> 'Funcionario'" in sql_vivo
        assert "COALESCE(facultad, '') <> 'Sin persona identificada'" in sql_vivo
        assert vivo["aforo_actual"] == 18
        assert vivo["capacidad_maxima"] == 124
        assert vivo["timestamp"] == ts_esperado.isoformat()
        assert not vivo["timestamp"].endswith("T00:00:00")

    asyncio.run(_run())


def test_hora_pico_sincronizada_y_filtros_completos_biblioteca():
    import inspect

    # 1. Escenario 16/11: 11:00 tuvo mas ingresos (50 vs 41) pero 13:00 tuvo el pico simultaneo (54 vs 47)
    curva_nov16 = [
        {"bucket": "2026-11-16T11:00:00", "ingresos": 50, "salidas": 33, "personas_unicas": 47},
        {"bucket": "2026-11-16T12:00:00", "ingresos": 37, "salidas": 40, "personas_unicas": 45},
        {"bucket": "2026-11-16T13:00:00", "ingresos": 41, "salidas": 32, "personas_unicas": 54},
    ]
    assert _extraer_hora_pico_curva(curva_nov16) == "13:00 hrs"
    assert _extraer_hora_pico_curva([]) is None
    assert _extraer_hora_pico_curva([{"bucket": "2026-11-16T10:00:00", "personas_unicas": 0}]) is None

    # 2. Verificar firmas completas de filtros cerrados en AttendanceService
    assert "cohorte" in inspect.signature(AttendanceService.get_door_usage).parameters
    assert "cohorte" in inspect.signature(AttendanceService.get_checkin_distribution).parameters
    assert "cohorte" in inspect.signature(AttendanceService.get_visit_profiles_donut).parameters
    for fn in (AttendanceService.get_rooms_comparison, AttendanceService.get_daily_average_attendance):
        sig = inspect.signature(fn).parameters
        for p in ("perfil_visita", "sala", "cohorte"):
            assert p in sig
    for fn in (AttendanceService.get_raw_events, AttendanceService.export_raw_csv):
        sig = inspect.signature(fn).parameters
        for p in ("sala", "carrera", "facultad", "cohorte"):
            assert p in sig

    # 3. Verificar lectura dinámica de capacidades desde salas_biblioteca (150 + 126 = 276)
    class _FakeExecSalas:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return list(self._rows)

    class _FakeSessionSalas:
        async def execute(self, stmt, _params=None):
            if "FROM salas_biblioteca" in str(stmt):
                return _FakeExecSalas([
                    SimpleNamespace(
                        id=1, codigo="SALA_1_CSF02", nombre="Sala 1", edificio="CSF02",
                        piso="2do Piso", descripcion="", capacidad_asientos=150,
                        permite_horario_extendido=False, puerta_principal_in="",
                        puerta_principal_out="", puerta_universal_in="",
                        puerta_universal_out="", activo=True,
                    ),
                    SimpleNamespace(
                        id=2, codigo="SALA_2_CSF04", nombre="Sala 2", edificio="CSF04",
                        piso="1er Piso", descripcion="", capacidad_asientos=126,
                        permite_horario_extendido=True, puerta_principal_in="",
                        puerta_principal_out="", puerta_universal_in="",
                        puerta_universal_out="", activo=True,
                    ),
                ])
            return _FakeExecSalas([])

    async def _run_caps():
        caps = await obtener_capacidades_salas_cacheadas(_FakeSessionSalas(), 1)
        assert caps == {"sala_1": 150, "sala_2": 126, "total": 276}

    asyncio.run(_run_caps())


def test_horarios_regulares_dinamicos_y_tolerancia_salida():
    import json

    cfg_s1 = json.dumps({
        "lunes": {"abierto": True, "apertura": "08:30", "cierre": "20:30", "cierre_dia_siguiente": False},
        "martes": {"abierto": True, "apertura": "08:30", "cierre": "20:30", "cierre_dia_siguiente": False},
        "miercoles": {"abierto": True, "apertura": "08:30", "cierre": "20:30", "cierre_dia_siguiente": False},
        "jueves": {"abierto": True, "apertura": "08:30", "cierre": "20:30", "cierre_dia_siguiente": False},
        "viernes": {"abierto": True, "apertura": "08:30", "cierre": "19:30", "cierre_dia_siguiente": False},
        "sabado": {"abierto": True, "apertura": "10:30", "cierre": "15:00", "cierre_dia_siguiente": False},
        "domingo": {"abierto": False, "apertura": "00:00", "cierre": "00:00", "cierre_dia_siguiente": False},
    })
    cfg_s2 = json.dumps({
        "lunes": {"abierto": True, "apertura": "08:30", "cierre": "23:00", "cierre_dia_siguiente": False},
        "martes": {"abierto": True, "apertura": "08:30", "cierre": "23:00", "cierre_dia_siguiente": False},
        "miercoles": {"abierto": True, "apertura": "08:30", "cierre": "23:00", "cierre_dia_siguiente": False},
        "jueves": {"abierto": True, "apertura": "08:30", "cierre": "23:00", "cierre_dia_siguiente": False},
        "viernes": {"abierto": True, "apertura": "08:30", "cierre": "22:00", "cierre_dia_siguiente": False},
        "sabado": {"abierto": True, "apertura": "09:30", "cierre": "15:00", "cierre_dia_siguiente": False},
        "domingo": {"abierto": False, "apertura": "00:00", "cierre": "00:00", "cierre_dia_siguiente": False},
    })
    regla_s1 = SimpleNamespace(
        id=3, anio=2026, subespacio="sala_1", tipo_horario="regular", activo=True,
        fecha_inicio=None, fecha_fin=None, hora_apertura="08:30", hora_cierre="20:30",
        cierre_dia_siguiente=False, es_continuo_24h=False, configuracion_dias=cfg_s1,
    )
    regla_s2 = SimpleNamespace(
        id=4, anio=2026, subespacio="sala_2", tipo_horario="regular", activo=True,
        fecha_inicio=None, fecha_fin=None, hora_apertura="08:30", hora_cierre="23:00",
        cierre_dia_siguiente=False, es_continuo_24h=False, configuracion_dias=cfg_s2,
    )
    camp_s2 = SimpleNamespace(
        id=9, anio=2026, subespacio="sala_2", tipo_horario="extendido_24h", activo=True,
        fecha_inicio=datetime(2026, 11, 2, 0, 0), fecha_fin=datetime(2026, 11, 28, 23, 59),
        hora_apertura="08:30", hora_cierre="07:00", cierre_dia_siguiente=True,
        es_continuo_24h=True, configuracion_dias=None,
    )

    # 1. SQL diferenciado por sala y tolerancia de 15 min exclusiva para salidas
    sql_reg = _construir_sql_horario_regular([regla_s1, regla_s2], date(2026, 11, 21), date(2026, 11, 21), 15)
    assert "CSF02" in sql_reg and "CSF04" in sql_reg
    assert "15:00:00" in sql_reg and "15:15:00" in sql_reg
    assert "20:30:00" in sql_reg and "20:45:00" in sql_reg
    assert "23:00:00" in sql_reg and "23:15:00" in sql_reg
    assert "COALESCE(door_entrada, '') LIKE '%CSF02%'" in sql_reg
    assert "COALESCE(door_entrada, '') LIKE '%CSF04%'" in sql_reg
    assert "COALESCE(salida_imputada, 0) = 1" in sql_reg

    # Tope 23:59:59 cuando cierre + tolerancia supera medianoche
    regla_tarde = SimpleNamespace(
        id=99, anio=2026, subespacio="sala_2", tipo_horario="regular", activo=True,
        fecha_inicio=None, fecha_fin=None, hora_apertura="08:30", hora_cierre="23:50",
        cierre_dia_siguiente=False, es_continuo_24h=False,
        configuracion_dias={"lunes": {"abierto": True, "apertura": "08:30", "cierre": "23:50", "cierre_dia_siguiente": False}},
    )
    sql_tarde = _construir_sql_horario_regular([regla_s1, regla_tarde], date(2026, 11, 23), date(2026, 11, 23), 15)
    assert "23:59:59" in sql_tarde and "24:" not in sql_tarde

    # 2. Reglas versionadas historicas emiten guardas de fecha
    regla_hist = SimpleNamespace(
        id=30, anio=2026, subespacio="sala_1", tipo_horario="historico_regular", activo=True,
        fecha_inicio=datetime(2026, 1, 1, 0, 0), fecha_fin=datetime(2026, 11, 20, 23, 59),
        hora_apertura="08:30", hora_cierre="13:30", cierre_dia_siguiente=False, es_continuo_24h=False,
        configuracion_dias={"sabado": {"abierto": True, "apertura": "10:30", "cierre": "13:30", "cierre_dia_siguiente": False}},
    )
    regla_nueva = SimpleNamespace(
        id=31, anio=2026, subespacio="sala_1", tipo_horario="regular", activo=True,
        fecha_inicio=datetime(2026, 11, 21, 0, 0), fecha_fin=None,
        hora_apertura="08:30", hora_cierre="15:00", cierre_dia_siguiente=False, es_continuo_24h=False,
        configuracion_dias=cfg_s1,
    )
    sql_ver = _construir_sql_horario_regular([regla_hist, regla_nueva, regla_s2], date(2026, 11, 1), date(2026, 11, 25), 15)
    assert "2026-11-20" in sql_ver and "2026-11-21" in sql_ver

    # 3. Expresiones dinamicas piso_apertura y cierre_efectivo
    expr_ap, expr_ci = _construir_expresiones_limites_presencia([regla_s1, regla_s2], "1=0", date(2026, 11, 21), date(2026, 11, 21))
    assert "630" in expr_ap and "570" in expr_ap
    assert "900" in expr_ci and "ELSE 0 END" in expr_ci

    # 4. es_horario_conforme por subespacio + tolerancia solo para salidas
    horarios_all = [regla_s1, regla_s2, camp_s2]
    sab_1501 = datetime(2026, 11, 21, 15, 1, 52)
    sab_1520 = datetime(2026, 11, 21, 15, 20, 0)
    sab_0934 = datetime(2026, 11, 21, 9, 34, 19)
    assert es_horario_conforme(sab_1501, horarios_all, subespacio="sala_1", es_salida=True, tolerancia_salida_min=15) is True
    assert es_horario_conforme(sab_1501, horarios_all, subespacio="sala_1", es_salida=False, tolerancia_salida_min=15) is False
    assert es_horario_conforme(sab_1520, horarios_all, subespacio="sala_1", es_salida=True, tolerancia_salida_min=15) is False
    assert es_horario_conforme(sab_0934, horarios_all, subespacio="sala_1", es_salida=False, tolerancia_salida_min=15) is False
    assert es_horario_conforme(datetime(2026, 11, 21, 23, 30, 0), horarios_all, subespacio="sala_2", es_salida=False, tolerancia_salida_min=15) is True

    # 5. Invalidacion de cache limpia horarios_regulares:1
    cache_horarios_espacio["horarios_regulares:1"] = [regla_s1]
    invalidar_cache_horarios(1)
    assert "horarios_regulares:1" not in cache_horarios_espacio


def test_relleno_cero_dias_operativos_y_ultimo_ts_por_sala():
    import json

    cfg_s1 = json.dumps({
        "lunes": {"abierto": True, "apertura": "08:30", "cierre": "20:30", "cierre_dia_siguiente": False},
        "viernes": {"abierto": True, "apertura": "08:30", "cierre": "19:30", "cierre_dia_siguiente": False},
        "sabado": {"abierto": True, "apertura": "10:30", "cierre": "15:00", "cierre_dia_siguiente": False},
        "domingo": {"abierto": False, "apertura": "00:00", "cierre": "00:00", "cierre_dia_siguiente": False},
    })
    cfg_s2 = json.dumps({
        "lunes": {"abierto": True, "apertura": "08:30", "cierre": "23:00", "cierre_dia_siguiente": False},
        "viernes": {"abierto": True, "apertura": "08:30", "cierre": "22:00", "cierre_dia_siguiente": False},
        "sabado": {"abierto": True, "apertura": "09:30", "cierre": "15:00", "cierre_dia_siguiente": False},
        "domingo": {"abierto": False, "apertura": "00:00", "cierre": "00:00", "cierre_dia_siguiente": False},
    })
    reglas = [
        SimpleNamespace(
            id=3, anio=2026, subespacio="sala_1", tipo_horario="regular", activo=True,
            fecha_inicio=None, fecha_fin=None, hora_apertura="08:30", hora_cierre="20:30",
            cierre_dia_siguiente=False, es_continuo_24h=False, configuracion_dias=cfg_s1,
        ),
        SimpleNamespace(
            id=4, anio=2026, subespacio="sala_2", tipo_horario="regular", activo=True,
            fecha_inicio=None, fecha_fin=None, hora_apertura="08:30", hora_cierre="23:00",
            cierre_dia_siguiente=False, es_continuo_24h=False, configuracion_dias=cfg_s2,
        ),
    ]
    ahora = datetime(2026, 11, 21, 16, 50, 0)

    # 1. Rango 20-21 nov con Sala 2 vacía el sábado 21: conserva 20/11 y rellena 21/11 09:00..15:00 en 0
    curva_vie = [
        {
            "bucket": "2026-11-20T22:00:00", "ingresos": 3, "salidas": 1,
            "personas_unicas": 5, "personas_sala1": 0, "personas_sala2": 5,
            "ingresos_sala1": 0, "ingresos_sala2": 3,
        }
    ]
    res_2d = _rellenar_dias_operativos_sin_registros(
        curva=curva_vie, fecha_inicio=date(2026, 11, 20), fecha_fin=date(2026, 11, 21),
        ahora_servidor=ahora, reglas_regulares=reglas, sala="sala_2",
        alcance="conformes", regimen_horario="dentro_horario,24h_delta",
    )
    assert res_2d[0]["bucket"] == "2026-11-20T22:00:00" and "sin_registros" not in res_2d[0]
    sab_pts = [p for p in res_2d[1:]]
    assert [p["bucket"] for p in sab_pts] == [f"2026-11-21T{h:02d}:00:00" for h in range(9, 16)]
    assert all(p["personas_unicas"] == 0 and p["ingresos"] == 0 and p["sin_registros"] is True for p in sab_pts)

    # 2. Un solo día vacío (21/11): devuelve 09:00..15:00 en 0 y _extraer_hora_pico_curva sigue en None
    res_1d = _rellenar_dias_operativos_sin_registros(
        curva=[], fecha_inicio=date(2026, 11, 21), fecha_fin=date(2026, 11, 21),
        ahora_servidor=ahora, reglas_regulares=reglas, sala="sala_2",
        alcance="conformes", regimen_horario="dentro_horario,24h_delta",
    )
    assert len(res_1d) == 7
    assert _extraer_hora_pico_curva(res_1d) is None

    # 3. Recorte a hora actual, omisión de domingos/feriados/anomalías/futuro y anclas en >7 días
    res_rec = _rellenar_dias_operativos_sin_registros(
        curva=[], fecha_inicio=date(2026, 11, 21), fecha_fin=date(2026, 11, 21),
        ahora_servidor=datetime(2026, 11, 21, 11, 20, 0), reglas_regulares=reglas, sala="sala_2",
    )
    assert [p["bucket"] for p in res_rec] == [f"2026-11-21T{h:02d}:00:00" for h in range(9, 12)]

    assert _rellenar_dias_operativos_sin_registros(
        [], date(2026, 11, 22), date(2026, 11, 22), datetime(2026, 11, 22, 14, 0, 0), reglas, sala="sala_2"
    ) == []
    assert _rellenar_dias_operativos_sin_registros(
        [], date(2026, 11, 21), date(2026, 11, 21), ahora, reglas, sala="sala_2",
        cal_data={"feriados": [date(2026, 11, 21)], "contingencias": []},
    ) == []
    assert _rellenar_dias_operativos_sin_registros(
        [], date(2026, 11, 21), date(2026, 11, 21), ahora, reglas, sala="sala_2", alcance="anomalias"
    ) == []
    assert _rellenar_dias_operativos_sin_registros(
        [], date(2026, 11, 25), date(2026, 11, 26), ahora, reglas, sala="sala_2"
    ) == []

    # Rango > 7 días: exactamente 2 puntos ancla (inicio y cierre) por día vacío
    res_10d = _rellenar_dias_operativos_sin_registros(
        [], date(2026, 11, 21), date(2026, 11, 21), ahora, reglas, sala="sala_2"
    )
    assert len(res_10d) == 7
    res_multi = _rellenar_dias_operativos_sin_registros(
        [{"bucket": f"2026-11-{d:02d}T10:00:00", "ingresos": 1, "salidas": 1, "personas_unicas": 1} for d in range(12, 21)],
        date(2026, 11, 12), date(2026, 11, 21), ahora, reglas, sala="sala_2",
    )
    pts_21_multi = [p for p in res_multi if p["bucket"].startswith("2026-11-21")]
    assert [p["bucket"] for p in pts_21_multi] == ["2026-11-21T09:00:00", "2026-11-21T15:00:00"]

    # 4. get_occupancy_realtime filtra ultimo_ts por Sala 2 (CSF04)
    class _FakeExecVivoS2:
        def __init__(self, scalar_val=None, first_row=None, all_rows=None):
            self._scalar = scalar_val
            self._first = first_row
            self._all = all_rows or []

        def scalar(self):
            return self._scalar

        def first(self):
            return self._first

        def fetchall(self):
            return list(self._all)

    class _CaptureVivoS2:
        def __init__(self):
            self.sqls = []

        async def execute(self, stmt, _params=None):
            sql_str = str(stmt)
            self.sqls.append(sql_str)
            if "MAX(time) AS ultimo_ts" in sql_str:
                return _FakeExecVivoS2(scalar_val=datetime(2026, 11, 20, 22, 38, 48))
            if "AS aforo_actual" in sql_str:
                return _FakeExecVivoS2(first_row=SimpleNamespace(aforo_actual=0, aforo_sala1=0, aforo_sala2=0))
            if "FROM salas_biblioteca" in sql_str:
                return _FakeExecVivoS2(all_rows=[SimpleNamespace(
                    id=2, codigo="CSF04", nombre="Sala 2", edificio="CSF04",
                    piso="1", descripcion="", capacidad_asientos=126,
                    permite_horario_extendido=True, puerta_principal_in="",
                    puerta_principal_out="", puerta_universal_in="",
                    puerta_universal_out="", activo=True,
                )])
            return _FakeExecVivoS2(all_rows=[])

    async def _run_s2():
        ses = _CaptureVivoS2()
        vivo = await AttendanceService.get_occupancy_realtime(ses, espacio_id=1, sala="sala_2")
        sql_ts = next(s for s in ses.sqls if "MAX(time) AS ultimo_ts" in s)
        assert "CSF04" in sql_ts
        assert vivo["timestamp"] == "2026-11-20T22:38:48"
        assert vivo["capacidad_maxima"] == 126

    asyncio.run(_run_s2())


def test_incidencias_operativas_calendario_y_mascara_ml():
    import numpy as np
    import pandas as pd
    from app.ml.prophet_service import _enrich_features, aplicar_mascara_anomalias_entrenamiento

    df_base = pd.DataFrame({
        "ds": pd.to_datetime([
            "2026-11-20 11:00:00",
            "2026-11-21 11:00:00",
            "2026-11-21 12:00:00",
            "2026-11-21 13:00:00",
        ]),
        "y": [40.0, 0.0, 0.0, 0.0],
    })
    df_cal = pd.DataFrame(columns=["fecha", "is_holiday", "is_break", "is_exam_period", "suspension_actividades", "is_strike"])
    horarios_cfg = [
        {
            "espacio_id": 1, "subespacio": "sala_1", "anio": 2026, "tipo_horario": "regular",
            "fecha_inicio": None, "fecha_fin": None, "hora_apertura": "08:30", "hora_cierre": "20:30",
            "cierre_dia_siguiente": False, "es_continuo_24h": False, "activo": True,
            "configuracion_dias": {"viernes": {"abierto": True, "apertura": "08:30", "cierre": "19:30"}, "sabado": {"abierto": True, "apertura": "10:30", "cierre": "15:00"}},
        },
        {
            "espacio_id": 1, "subespacio": "sala_2", "anio": 2026, "tipo_horario": "regular",
            "fecha_inicio": None, "fecha_fin": None, "hora_apertura": "08:30", "hora_cierre": "23:00",
            "cierre_dia_siguiente": False, "es_continuo_24h": False, "activo": True,
            "configuracion_dias": {"viernes": {"abierto": True, "apertura": "08:30", "cierre": "22:00"}, "sabado": {"abierto": True, "apertura": "09:30", "cierre": "15:00"}},
        },
    ]

    # 1. Falla de sensor en Sala 2 solo enmascara Sala 2 (no Sala 1) manteniendo es_horario_abierto=1
    cont_falla = [{
        "id": 1, "fecha_inicio": date(2026, 11, 21), "fecha_fin": date(2026, 11, 21),
        "tipo": "falla_sensor", "espacio_id": 1, "subespacio": "sala_2",
        "hora_inicio": None, "hora_fin": None, "implica_cierre_total": False,
    }]
    enr_s2 = _enrich_features(df_base, df_cal, sala="sala2", horarios=horarios_cfg, contingencias=cont_falla, espacio_id=1)
    assert list(enr_s2["es_horario_abierto"]) == [1, 1, 1, 1]
    assert list(enr_s2["dato_faltante_sensor"]) == [0, 1, 1, 1]
    masked_s2 = aplicar_mascara_anomalias_entrenamiento(enr_s2)
    assert masked_s2.loc[0, "y"] == 40.0
    assert np.isnan(masked_s2.loc[1, "y"]) and np.isnan(masked_s2.loc[2, "y"])

    enr_s1 = _enrich_features(df_base, df_cal, sala="sala1", horarios=horarios_cfg, contingencias=cont_falla, espacio_id=1)
    assert list(enr_s1["dato_faltante_sensor"]) == [0, 0, 0, 0]
    masked_s1 = aplicar_mascara_anomalias_entrenamiento(enr_s1)
    assert list(masked_s1["y"]) == [40.0, 0.0, 0.0, 0.0]

    # 2. Jornada sin demanda real (sin_demanda) NO enmascara y
    cont_sin_demanda = [{
        "id": 2, "fecha_inicio": date(2026, 11, 21), "fecha_fin": date(2026, 11, 21),
        "tipo": "sin_demanda", "espacio_id": 1, "subespacio": "sala_2",
        "hora_inicio": None, "hora_fin": None, "implica_cierre_total": False,
    }]
    enr_sd = _enrich_features(df_base, df_cal, sala="sala2", horarios=horarios_cfg, contingencias=cont_sin_demanda, espacio_id=1)
    masked_sd = aplicar_mascara_anomalias_entrenamiento(enr_sd)
    assert list(enr_sd["dato_faltante_sensor"]) == [0, 0, 0, 0]
    assert list(masked_sd["y"]) == [40.0, 0.0, 0.0, 0.0]

    # 3. Mantencion con cierre total cierra horario y enmascara en DF si suspension=1
    cont_mant = [{
        "id": 3, "fecha_inicio": date(2026, 11, 21), "fecha_fin": date(2026, 11, 21),
        "tipo": "mantencion_cierre", "espacio_id": 1, "subespacio": "sala_2",
        "hora_inicio": None, "hora_fin": None, "implica_cierre_total": True,
    }]
    enr_mant = _enrich_features(df_base, df_cal, sala="sala2", horarios=horarios_cfg, contingencias=cont_mant, espacio_id=1)
    assert list(enr_mant["es_horario_abierto"]) == [1, 0, 0, 0]

    # 4. Relleno diario en <=7 dias mantiene las horas en 0 aun con contingencia para mostrar motivo
    regla_s2 = SimpleNamespace(
        id=4, anio=2026, subespacio="sala_2", tipo_horario="regular", activo=True,
        fecha_inicio=None, fecha_fin=None, hora_apertura="08:30", hora_cierre="23:00",
        cierre_dia_siguiente=False, es_continuo_24h=False,
        configuracion_dias={"sabado": {"abierto": True, "apertura": "09:30", "cierre": "15:00", "cierre_dia_siguiente": False}},
    )
    res_corto = _rellenar_dias_operativos_sin_registros(
        [], date(2026, 11, 21), date(2026, 11, 21),
        datetime(2026, 11, 21, 16, 0), [regla_s2], sala="sala_2",
        cal_data={"feriados": [], "contingencias": [SimpleNamespace(**cont_mant[0])]},
    )
    assert len(res_corto) == 7 and all(p["sin_registros"] is True for p in res_corto)

    res_largo = _rellenar_dias_operativos_sin_registros(
        [], date(2026, 11, 10), date(2026, 11, 21),
        datetime(2026, 11, 21, 16, 0), [regla_s2], sala="sala_2",
        cal_data={"feriados": [], "contingencias": [SimpleNamespace(**cont_mant[0])]},
    )
    assert not any(p["bucket"].startswith("2026-11-21") for p in res_largo)


def test_deteccion_sala_individual_en_global_y_filtro_incidencias_calendario():
    import json
    from app.services.calendar_service import CalendarService

    cfg_s1 = json.dumps({
        **{d: {"abierto": True, "apertura": "08:30", "cierre": "20:30", "cierre_dia_siguiente": False} for d in ("lunes", "martes", "miercoles", "jueves")},
        "viernes": {"abierto": True, "apertura": "08:30", "cierre": "19:30", "cierre_dia_siguiente": False},
        "sabado": {"abierto": True, "apertura": "10:30", "cierre": "15:00", "cierre_dia_siguiente": False},
        "domingo": {"abierto": False, "apertura": "00:00", "cierre": "00:00", "cierre_dia_siguiente": False},
    })
    cfg_s2 = json.dumps({
        **{d: {"abierto": True, "apertura": "08:30", "cierre": "23:00", "cierre_dia_siguiente": False} for d in ("lunes", "martes", "miercoles", "jueves")},
        "viernes": {"abierto": True, "apertura": "08:30", "cierre": "22:00", "cierre_dia_siguiente": False},
        "sabado": {"abierto": True, "apertura": "09:30", "cierre": "15:00", "cierre_dia_siguiente": False},
        "domingo": {"abierto": False, "apertura": "00:00", "cierre": "00:00", "cierre_dia_siguiente": False},
    })
    reglas = [
        SimpleNamespace(
            id=3, anio=2026, subespacio="sala_1", tipo_horario="regular", activo=True,
            fecha_inicio=None, fecha_fin=None, hora_apertura="08:30", hora_cierre="20:30",
            cierre_dia_siguiente=False, es_continuo_24h=False, configuracion_dias=cfg_s1,
        ),
        SimpleNamespace(
            id=4, anio=2026, subespacio="sala_2", tipo_horario="regular", activo=True,
            fecha_inicio=None, fecha_fin=None, hora_apertura="08:30", hora_cierre="23:00",
            cierre_dia_siguiente=False, es_continuo_24h=False, configuracion_dias=cfg_s2,
        ),
    ]

    # 1. En vista global con Sala 1 activa y Sala 2 en 0 el sábado 21/11, anota sin_registros_sala2 sin mutar entrada
    pto_orig = {
        "bucket": "2026-11-21T12:00:00", "ingresos": 4, "salidas": 1,
        "personas_unicas": 5, "personas_sala1": 5, "personas_sala2": 0,
        "ingresos_sala1": 4, "ingresos_sala2": 0,
    }
    res_s2_vacia = _rellenar_dias_operativos_sin_registros(
        [pto_orig], date(2026, 11, 20), date(2026, 11, 21),
        datetime(2026, 11, 21, 16, 0), reglas, sala=None,
    )
    assert "sin_registros_sala2" not in pto_orig
    pts_sab = [p for p in res_s2_vacia if p["bucket"].startswith("2026-11-21")]
    assert len(pts_sab) == 1
    assert pts_sab[0]["personas_unicas"] == 5
    assert "sin_registros" not in pts_sab[0]
    assert pts_sab[0].get("sin_registros_sala2") is True
    assert "sin_registros_sala1" not in pts_sab[0]

    # 2. A las 10:00 (antes de apertura 10:30 de Sala 1), con Sala 2 activa y Sala 1 en 0, NO marca sin_registros_sala1
    pto_10h_s2 = {
        "bucket": "2026-11-21T10:00:00", "ingresos": 3, "salidas": 0,
        "personas_unicas": 3, "personas_sala1": 0, "personas_sala2": 3,
        "ingresos_sala1": 0, "ingresos_sala2": 3,
    }
    res_antes_ap = _rellenar_dias_operativos_sin_registros(
        [pto_10h_s2], date(2026, 11, 21), date(2026, 11, 21),
        datetime(2026, 11, 21, 10, 0), reglas, sala=None,
    )
    assert len(res_antes_ap) == 1
    assert "sin_registros_sala1" not in res_antes_ap[0]

    # 3. Día vacío en ambas salas (sala=None) marca sin_registros, sin_registros_sala1 y sin_registros_sala2
    res_ambas_vacias = _rellenar_dias_operativos_sin_registros(
        [], date(2026, 11, 21), date(2026, 11, 21),
        datetime(2026, 11, 21, 14, 0), reglas, sala=None,
    )
    assert len(res_ambas_vacias) == 6
    assert all(
        p.get("sin_registros") is True
        and p.get("sin_registros_sala1") is True
        and p.get("sin_registros_sala2") is True
        for p in res_ambas_vacias
    )

    # 4. get_occupancy_realtime(sala=None) devuelve ultimo_marcaje_sala1 y ultimo_marcaje_sala2 independientes
    class _FakeExecGlobal:
        def __init__(self, first_row=None, all_rows=None):
            self._first = first_row
            self._all = all_rows or []

        def first(self):
            return self._first

        def fetchall(self):
            return list(self._all)

        def scalar_one_or_none(self):
            return 350

    class _CaptureVivoGlobal:
        def __init__(self):
            self.sqls = []

        async def execute(self, stmt, _params=None):
            sql_str = str(stmt)
            self.sqls.append(sql_str)
            if "ultimo_ts_sala1" in sql_str:
                return _FakeExecGlobal(first_row=SimpleNamespace(
                    ultimo_ts=datetime(2026, 11, 21, 15, 45, 0),
                    ultimo_ts_sala1=datetime(2026, 11, 21, 15, 45, 0),
                    ultimo_ts_sala2=datetime(2026, 11, 20, 22, 38, 48),
                ))
            if "AS aforo_actual" in sql_str:
                return _FakeExecGlobal(first_row=SimpleNamespace(aforo_actual=3, aforo_sala1=3, aforo_sala2=0))
            if "FROM espacios" in sql_str:
                return _FakeExecGlobal()
            return _FakeExecGlobal(all_rows=[])

    async def _run_global():
        ses = _CaptureVivoGlobal()
        vivo = await AttendanceService.get_occupancy_realtime(ses, espacio_id=1, sala=None)
        assert vivo["timestamp"] == "2026-11-21T15:45:00"
        assert vivo["ultimo_marcaje_sala1"] == "2026-11-21T15:45:00"
        assert vivo["ultimo_marcaje_sala2"] == "2026-11-20T22:38:48"

    asyncio.run(_run_global())

    # 5. obtener_resumen_anual_calendario excluye paro_federado de incidencias_operativas pero conserva falla_sensor y suspension_sala
    contingencias_mock = [
        SimpleNamespace(
            id=1, fecha_inicio=date(2026, 9, 19), fecha_fin=date(2026, 9, 19),
            tipo="paro_federado", titulo="Paro FEUCT", descripcion=None,
            espacio_id=None, subespacio="todos", hora_inicio=None, hora_fin=None, implica_cierre_total=False,
        ),
        SimpleNamespace(
            id=4, fecha_inicio=date(2026, 10, 21), fecha_fin=date(2026, 10, 21),
            tipo="suspension_sala", titulo="Suspensión Sala 2", descripcion=None,
            espacio_id=1, subespacio="sala_2", hora_inicio="15:00", hora_fin=None, implica_cierre_total=True,
        ),
        SimpleNamespace(
            id=9, fecha_inicio=date(2026, 11, 21), fecha_fin=date(2026, 11, 21),
            tipo="falla_sensor", titulo="Falla sensor S2", descripcion="Corte",
            espacio_id=1, subespacio="sala_2", hora_inicio=None, hora_fin=None, implica_cierre_total=False,
        ),
    ]

    class _FakeCalDb:
        def __init__(self):
            self.n = 0

        async def execute(self, _stmt):
            self.n += 1
            items = [] if self.n == 1 else contingencias_mock
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: items))

    async def _run_cal():
        resumen = await CalendarService().obtener_resumen_anual_calendario(_FakeCalDb(), 2026)
        por_fecha = {d["fecha"]: d for d in resumen}
        assert por_fecha["2026-09-19"]["is_strike_federado"] is True
        assert por_fecha["2026-09-19"]["incidencias_operativas"] == []
        assert [i["id"] for i in por_fecha["2026-10-21"]["incidencias_operativas"]] == [4]
        assert [i["id"] for i in por_fecha["2026-11-21"]["incidencias_operativas"]] == [9]

    asyncio.run(_run_cal())

    # 6. Suspensiones institucionales de calendario se omiten tanto en vista por sala como en global (<=7d)
    cal_susp = {
        "feriados": [],
        "suspensiones_institucionales": [date(2026, 4, 3), date(2026, 4, 4)],
        "contingencias": [],
    }
    res_susp_s2 = _rellenar_dias_operativos_sin_registros(
        [], date(2026, 4, 3), date(2026, 4, 4),
        datetime(2026, 4, 10, 12, 0), reglas, sala="sala_2", cal_data=cal_susp,
    )
    assert res_susp_s2 == []
    res_susp_global = _rellenar_dias_operativos_sin_registros(
        [], date(2026, 4, 3), date(2026, 4, 4),
        datetime(2026, 4, 10, 12, 0), reglas, sala=None, cal_data=cal_susp,
    )
    assert res_susp_global == []

    # 7. Fechas previas al primer registro histórico de cada sala no generan falsos vacíos
    inicio_salas = {1: date(2026, 3, 17), 2: date(2026, 3, 19)}
    res_ini_s2 = _rellenar_dias_operativos_sin_registros(
        [], date(2026, 3, 17), date(2026, 3, 20),
        datetime(2026, 3, 25, 12, 0), reglas, sala="sala_2", inicio_por_sala=inicio_salas,
    )
    fechas_ini_s2 = sorted({p["bucket"][:10] for p in res_ini_s2})
    assert fechas_ini_s2 == ["2026-03-19", "2026-03-20"]

    curva_mar17_19 = [
        {"bucket": "2026-03-17T14:00:00", "ingresos": 10, "salidas": 2, "personas_unicas": 10, "personas_sala1": 10, "personas_sala2": 0, "ingresos_sala1": 10, "ingresos_sala2": 0},
        {"bucket": "2026-03-18T14:00:00", "ingresos": 20, "salidas": 5, "personas_unicas": 20, "personas_sala1": 20, "personas_sala2": 0, "ingresos_sala1": 20, "ingresos_sala2": 0},
        {"bucket": "2026-03-19T16:00:00", "ingresos": 15, "salidas": 3, "personas_unicas": 15, "personas_sala1": 15, "personas_sala2": 0, "ingresos_sala1": 15, "ingresos_sala2": 0},
    ]
    res_ini_global = _rellenar_dias_operativos_sin_registros(
        curva_mar17_19, date(2026, 3, 17), date(2026, 3, 19),
        datetime(2026, 3, 25, 12, 0), reglas, sala=None, inicio_por_sala=inicio_salas,
    )
    assert "sin_registros_sala2" not in res_ini_global[0]
    assert "sin_registros_sala2" not in res_ini_global[1]
    assert res_ini_global[2].get("sin_registros_sala2") is True


def test_prophet_horario_24h_y_estacionalidad_condicional():
    import pandas as pd
    from app.ml.prophet_service import (
        _build_prophet,
        _enrich_features,
        _preparar_columnas_prediccion,
    )
    from app.services.config_service import evaluar_horario_abierto_subespacio

    horarios_24h = [
        {
            "espacio_id": 1, "subespacio": "sala_2", "anio": 2026, "tipo_horario": "extendido_24h",
            "fecha_inicio": datetime(2026, 11, 2, 0, 0), "fecha_fin": datetime(2026, 11, 28, 0, 0),
            "hora_apertura": "08:30", "hora_cierre": "07:00", "cierre_dia_siguiente": True,
            "es_continuo_24h": True, "activo": True,
            "configuracion_dias": {
                "lunes": {"abierto": True, "apertura": "08:30", "cierre": "07:00", "cierre_dia_siguiente": True},
                "martes": {"abierto": True, "apertura": "08:30", "cierre": "07:00", "cierre_dia_siguiente": True},
                "miercoles": {"abierto": True, "apertura": "08:30", "cierre": "07:00", "cierre_dia_siguiente": True},
                "jueves": {"abierto": True, "apertura": "08:30", "cierre": "07:00", "cierre_dia_siguiente": True},
                "viernes": {"abierto": True, "apertura": "08:30", "cierre": "06:00", "cierre_dia_siguiente": True},
                "sabado": {"abierto": True, "apertura": "10:30", "cierre": "15:00", "cierre_dia_siguiente": False},
                "domingo": {"abierto": False, "apertura": "00:00", "cierre": "00:00", "cierre_dia_siguiente": False},
            },
        }
    ]
    df_test = pd.DataFrame({
        "ds": pd.to_datetime([
            "2026-11-25 03:00:00",  # Miércoles madrugada (abierto 24h)
            "2026-11-28 12:00:00",  # Sábado mediodía (abierto)
            "2026-11-28 20:00:00",  # Sábado noche (cerrado)
            "2026-11-29 12:00:00",  # Domingo mediodía (cerrado)
        ]),
        "y": [5.0, 20.0, 0.0, 0.0],
    })
    df_cal = pd.DataFrame({
        "fecha": pd.to_datetime(["2026-11-25", "2026-11-28", "2026-11-29"]),
        "is_holiday": [0, 0, 0],
        "is_break": [0, 0, 0],
        "is_exam_period": [1, 1, 1],
        "suspension_actividades": [0, 0, 0],
        "is_strike": [0, 0, 0],
    })
    enr = _enrich_features(df_test, df_cal, sala="sala2", horarios=horarios_24h, contingencias=[], espacio_id=1)
    assert list(enr["es_horario_abierto"]) == [1, 1, 0, 0]
    assert list(enr["es_habil"]) == [1, 0, 0, 0]
    assert list(enr["es_sabado"]) == [0, 1, 0, 0]
    assert list(enr["es_domingo"]) == [0, 0, 0, 0]

    # Sin regla de rango, el fallback automático 24h nunca fuerza apertura en domingo
    assert evaluar_horario_abierto_subespacio(
        datetime(2026, 11, 29, 12, 0), espacio_id=1, subespacio="sala_2",
        horarios=[], es_feriado_oficial=False, es_24h_automatico=True,
    ) == 0

    enr["cap"] = 126.0
    enr["floor"] = 0.0
    m_cond = _build_prophet(growth="linear", seasonality_mode="multiplicative", solo_abierto=True)
    cols_cond = _preparar_columnas_prediccion(m_cond, enr)
    assert "es_habil" in cols_cond and "es_sabado" in cols_cond
    assert "es_horario_abierto" not in cols_cond and "cap" not in cols_cond

    m_legacy = _build_prophet(growth="logistic", seasonality_mode="additive", solo_abierto=False)
    cols_legacy = _preparar_columnas_prediccion(m_legacy, enr)
    assert "cap" in cols_legacy and "floor" in cols_legacy and "es_horario_abierto" in cols_legacy


def test_opcion1_reconciliacion_bottom_up_y_alertas_por_sala(monkeypatch):
    import pandas as pd
    from app.ml import prophet_service as ps
    from app.services import prediction_service as pred_svc
    from app.services.attendance_service import AttendanceService

    class _DummyModel:
        def __init__(self, valor: float):
            self.valor = valor
            self.growth = "linear"
            self.seasonalities = {}
            self.extra_regressors = {}

        def predict(self, df):
            n = len(df)
            return pd.DataFrame({
                "yhat": [self.valor] * n,
                "yhat_lower": [max(0.0, self.valor - 5.0)] * n,
                "yhat_upper": [self.valor + 5.0] * n,
            })

    class _FakeDbPresencia:
        async def execute(self, _stmt, _params=None):
            return SimpleNamespace(scalar=lambda: datetime(2026, 11, 25, 22, 0, 0))

    async def _fake_caps(_db):
        return {"sala1": 150, "sala2": 126, "todas": 276}

    async def _fake_cal(_db):
        return pd.DataFrame(columns=["fecha", "is_holiday", "is_break", "is_exam_period", "suspension_actividades", "is_strike"])

    async def _fake_hor(_db, espacio_id=1):
        return [
            {
                "espacio_id": 1, "subespacio": "sala_1", "anio": 2026, "tipo_horario": "regular",
                "fecha_inicio": None, "fecha_fin": None, "hora_apertura": "08:30", "hora_cierre": "20:30",
                "cierre_dia_siguiente": False, "es_continuo_24h": False, "activo": True,
                "configuracion_dias": None,
            },
            {
                "espacio_id": 1, "subespacio": "sala_2", "anio": 2026, "tipo_horario": "extendido_24h",
                "fecha_inicio": datetime(2026, 11, 2, 0, 0), "fecha_fin": datetime(2026, 11, 28, 0, 0),
                "hora_apertura": "00:00", "hora_cierre": "23:59",
                "cierre_dia_siguiente": False, "es_continuo_24h": True, "activo": True,
                "configuracion_dias": None,
            },
        ]

    async def _fake_cont(_db, espacio_id=1):
        return []

    async def _fake_curve(**_kwargs):
        return [{"bucket": "2026-11-25T15:00:00", "personas_unicas": 155, "personas_sala1": 135, "personas_sala2": 20}]

    monkeypatch.setattr(ps, "_fetch_capacidades", _fake_caps)
    monkeypatch.setattr(ps, "_fetch_calendar", _fake_cal)
    monkeypatch.setattr(ps, "_fetch_horarios_info", _fake_hor)
    monkeypatch.setattr(ps, "_fetch_contingencias_info", _fake_cont)
    monkeypatch.setattr(AttendanceService, "get_realtime_presence_curve", _fake_curve)

    modelos = {
        "prophet_presencia_sala1": _DummyModel(135.0),
        "prophet_presencia_sala2": _DummyModel(20.0),
    }
    monkeypatch.setattr(ps, "load_active_model", lambda k: modelos.get(k))
    monkeypatch.setattr(ps, "active_model_date", lambda _k: "2026-11-25 10:00")

    async def _run():
        res_todas = await ps.predict_presence_continuous(_FakeDbPresencia(), sala="todas")
        assert res_todas["reconciliacion"] == "bottom_up"
        assert res_todas["capacidad_sala1"] == 150
        assert res_todas["capacidad_sala2"] == 126

        # Hora madrugada (23:00 del 25/11): Sala 1 cerrada (=0), Sala 2 abierta (=20) -> Total = 20
        madrugada = res_todas["pronostico_7d"][0]
        assert madrugada["yhat_sala1"] == 0.0
        assert madrugada["yhat_sala2"] == 20.0
        assert madrugada["yhat"] == 20.0

        # Hora diurna (10:00 del 26/11): Sala 1 (135) + Sala 2 (20) -> Total = 155
        diurno = next(p for p in res_todas["pronostico_7d"] if "T10:00:00" in p["ds"])
        assert diurno["yhat_sala1"] == 135.0
        assert diurno["yhat_sala2"] == 20.0
        assert diurno["yhat"] == 155.0

        # Alertas por sala: Sala 1 (135/150 = 90% >= 85%) dispara alerta aun con Global en 56%
        async def _fake_esp(_db):
            return {"biblioteca": 276}, "bd"

        async def _fake_pred_pres(_db, sala="todas"):
            if sala == "sala1":
                return {"model_status": {"status": "ok"}, "pronostico_7d": [{"yhat": 135.0}, {"yhat": 135.0}, {"yhat": 135.0}]}
            if sala == "sala2":
                return {"model_status": {"status": "ok"}, "pronostico_7d": [{"yhat": 20.0}, {"yhat": 20.0}, {"yhat": 20.0}]}
            return {"model_status": {"status": "ok"}, "pronostico_7d": [{"yhat": 155.0}, {"yhat": 155.0}, {"yhat": 155.0}]}

        monkeypatch.setattr(pred_svc, "get_espacios_activos_capacidades", _fake_esp)
        monkeypatch.setattr(pred_svc, "_fetch_capacidades", _fake_caps)
        monkeypatch.setattr(pred_svc, "predict_presence_continuous", _fake_pred_pres)

        alertas = await pred_svc.get_active_alerts(_FakeDbPresencia())
        assert alertas["total_alertas"] == 1
        assert alertas["alertas"][0]["subespacio"] == "sala1"
        assert alertas["alertas"][0]["nivel"] == "critico"

    asyncio.run(_run())


def test_estacionamiento_sweep_line_reconciliacion_y_alertas_por_sector(monkeypatch):
    import pandas as pd
    from app.ml import prophet_service as ps
    from app.services import prediction_service as pred_svc
    from app.services.vehicle_service import (
        _calcular_curva_presencia_vehicular_por_hora,
        _extraer_hora_pico_curva_vehicular,
    )

    ahora = datetime(2026, 11, 25, 22, 0, 0)
    dia = date(2026, 11, 25)
    caps_sec = {"CSF11": 40, "CSF21": 50, "CHS01": 35}

    # 1. Barrido sweep-line: dos vehículos no simultáneos en la hora 10 (10:05 salida vs 10:55 entrada) -> pico=1
    sesiones = [
        (dia, 1, datetime(2026, 11, 25, 9, 0), datetime(2026, 11, 25, 10, 5)),
        (dia, 2, datetime(2026, 11, 25, 10, 55), datetime(2026, 11, 25, 12, 30)),
        (dia, 1, datetime(2026, 11, 25, 11, 10), datetime(2026, 11, 25, 12, 20)),
    ]
    flujo = [
        (datetime(2026, 11, 25, 9, 0), dia, 1, 0, 1, 0, 0, 0, 0, 0),
        (datetime(2026, 11, 25, 10, 0), dia, 1, 1, 0, 1, 1, 0, 0, 0),
        (datetime(2026, 11, 25, 11, 0), dia, 1, 0, 1, 0, 0, 0, 0, 0),
        (datetime(2026, 11, 25, 12, 0), dia, 0, 2, 0, 1, 0, 1, 0, 0),
    ]
    curva = _calcular_curva_presencia_vehicular_por_hora(sesiones, flujo, ahora, caps_sec, 125)
    por_h = {datetime.fromisoformat(p["bucket"]).hour: p["vehiculos_presentes"] for p in curva}
    assert por_h[10] == 1
    assert por_h[11] == 2
    assert _extraer_hora_pico_curva_vehicular(curva) == "11:00 hrs"

    # 2. Reconciliación Bottom-Up en predict_continuous('vehicular', 'todos') + alertas por sector
    class _DummyVehModel:
        def __init__(self, v: float):
            self.v = v
            self.growth = "linear"
            self.seasonalities = {}
            self.extra_regressors = {}

        def predict(self, df):
            n = len(df)
            return pd.DataFrame({
                "yhat": [self.v] * n,
                "yhat_lower": [max(0.0, self.v - 2.0)] * n,
                "yhat_upper": [self.v + 2.0] * n,
            })

    class _FakeDbVeh:
        async def execute(self, _stmt, _params=None):
            return SimpleNamespace(scalar=lambda: datetime(2026, 11, 25, 10, 0, 0))

    async def _fake_caps(_db):
        return {"CSF11": 40, "CSF21": 50, "CHS01": 35, "vehicular": 125}

    async def _fake_cal(_db):
        return pd.DataFrame(columns=["fecha", "is_holiday", "is_break", "is_exam_period", "suspension_actividades", "is_strike"])

    async def _fake_hor(_db, espacio_id=2):
        return [
            {
                "espacio_id": 2, "subespacio": s, "anio": 2026, "tipo_horario": "regular",
                "fecha_inicio": None, "fecha_fin": None, "hora_apertura": "07:00", "hora_cierre": "22:00",
                "cierre_dia_siguiente": False, "es_continuo_24h": False, "activo": True, "configuracion_dias": None,
            }
            for s in ("CSF11", "CSF21", "CHS01")
        ]

    async def _fake_cont(_db, espacio_id=2):
        return []

    async def _fake_curva_veh(**_kwargs):
        return curva

    from app.services.vehicle_service import VehicleService
    monkeypatch.setattr(ps, "_fetch_capacidades", _fake_caps)
    monkeypatch.setattr(ps, "_fetch_calendar", _fake_cal)
    monkeypatch.setattr(ps, "_fetch_horarios_info", _fake_hor)
    monkeypatch.setattr(ps, "_fetch_contingencias_info", _fake_cont)
    monkeypatch.setattr(VehicleService, "get_realtime_presence_curve", _fake_curva_veh)

    modelos_veh = {
        "prophet_vehicular_csf11": _DummyVehModel(36.0),
        "prophet_vehicular_csf21": _DummyVehModel(15.0),
        "prophet_vehicular_chs01": _DummyVehModel(5.0),
    }
    monkeypatch.setattr(ps, "load_active_model", lambda k: modelos_veh.get(k))
    monkeypatch.setattr(ps, "active_model_date", lambda _k: "2026-11-25 11:00")

    async def _run_veh():
        res_v = await ps.predict_continuous(_FakeDbVeh(), recinto="vehicular", sala="todos")
        assert res_v["reconciliacion"] == "bottom_up"
        assert res_v["capacidad_csf11"] == 40
        p_dia = next(p for p in res_v["pronostico_7d"] if "T12:00:00" in p["ds"])
        assert p_dia["yhat_csf11"] == 36.0 and p_dia["yhat_csf21"] == 15.0 and p_dia["yhat_chs01"] == 5.0
        assert p_dia["yhat"] == 56.0

        async def _fake_esp(_db):
            return {"vehicular": 125}, "bd"

        async def _fake_pred_veh(_db, recinto="vehicular", sala="todos"):
            vals = {"CSF11": 36.0, "CSF21": 15.0, "CHS01": 5.0, "todos": 56.0}
            v = vals.get(sala, 0.0)
            return {"model_status": {"status": "ok"}, "pronostico_7d": [{"yhat": v}, {"yhat": v}, {"yhat": v}]}

        monkeypatch.setattr(pred_svc, "get_espacios_activos_capacidades", _fake_esp)
        monkeypatch.setattr(pred_svc, "_fetch_capacidades", _fake_caps)
        monkeypatch.setattr(pred_svc, "predict_continuous", _fake_pred_veh)

        alertas = await pred_svc.get_active_alerts(_FakeDbVeh())
        assert alertas["total_alertas"] == 1
        assert alertas["alertas"][0]["recinto"] == "vehicular"
        assert alertas["alertas"][0]["subespacio"] == "CSF11"

    asyncio.run(_run_veh())


def test_actualizar_capacidad_sector_invalida_caches(monkeypatch):
    """Verifica que editar la capacidad de un sector vehicular invalida las cachés del módulo Estacionamiento."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.services import servicio_smart_campus as sc_svc
    from app.services import vehicle_service as veh_svc
    from app.core import cache as core_cache

    sector_mock = SimpleNamespace(codigo="CSF11", capacidad_max=40, activo=True)

    class _FakeResSector:
        def scalar_one_or_none(self):
            return sector_mock

    class _FakeResSum:
        def scalar(self):
            return 135

    class _FakeDb:
        def __init__(self):
            self.calls = 0
            self.commit = AsyncMock()
            self.flush = AsyncMock()
            self.refresh = AsyncMock()

        async def execute(self, _stmt):
            self.calls += 1
            if self.calls == 1:
                return _FakeResSector()
            if self.calls == 2:
                return _FakeResSum()
            return SimpleNamespace()

    horarios_invs: list[int] = []
    espacio_invs: list[int] = []

    monkeypatch.setattr(veh_svc, "invalidar_cache_horarios_vehiculos", lambda eid=2: horarios_invs.append(eid))

    async def _fake_inv_esp(eid: int):
        espacio_invs.append(eid)

    monkeypatch.setattr(core_cache, "invalidar_cache_por_espacio", _fake_inv_esp)

    async def _run():
        res = await sc_svc.actualizar_capacidad_sector(_FakeDb(), "csf11", 50)
        assert res.capacidad_max == 50
        assert horarios_invs == [2]
        assert espacio_invs == [2]

    asyncio.run(_run())


def test_chat_prophet_enruta_presencia_y_sector(monkeypatch):
    """Verifica que el Asistente IA use presencia para Biblioteca y sector activo/plazas para Estacionamiento."""
    from types import SimpleNamespace
    from app.services.chat import ejecutor_herramientas as eh

    llamadas_bib: list[str] = []
    llamadas_veh: list[tuple[str, str]] = []

    async def _fake_bib_pres(_db, sala="todas"):
        llamadas_bib.append(sala)
        return {
            "capacidad_asientos": 150,
            "pronostico_7d": [{"ds": "2026-11-26T12:00:00", "yhat": 42.0}],
            "model_status": {"status": "ok", "model_type": "Prophet Horario Condicional", "model_date": "2026-11-25"},
        }

    async def _fake_veh_fore(_db, recinto="vehicular", sala="todos"):
        llamadas_veh.append((recinto, sala))
        return {
            "capacidad_asientos": 40,
            "pronostico_7d": [{"ds": "2026-11-26T12:00:00", "yhat": 31.0}],
            "model_status": {"status": "ok", "model_type": "Prophet Horario Condicional Vehicular", "model_date": "2026-11-25"},
        }

    async def _fake_anio(_db, _eid):
        return 2026

    monkeypatch.setattr(eh, "get_prophet_presence_forecast", _fake_bib_pres)
    monkeypatch.setattr(eh, "get_prophet_forecast", _fake_veh_fore)
    monkeypatch.setattr(eh, "obtener_anio_activo_espacio", _fake_anio)

    async def _run():
        req_bib = SimpleNamespace(fecha_inicio=None, fecha_fin=None, prompt="pronostico", filtros={"sala": "CSF02"})
        comp_b, _data_b, res_b, _fig_b, _tbl_b = await eh._ejecutar_consulta_tool_interno(
            "consultar_proyeccion_prophet", {}, object(), 1, req_bib
        )
        assert comp_b == "ForecastLineChart"
        assert llamadas_bib == ["sala1"]
        assert "150 asientos" in res_b

        req_veh = SimpleNamespace(fecha_inicio=None, fecha_fin=None, prompt="pronostico", filtros={"sector": "csf11"})
        comp_v, _data_v, res_v, _fig_v, _tbl_v = await eh._ejecutar_consulta_tool_interno(
            "consultar_proyeccion_prophet", {}, object(), 2, req_veh
        )
        assert comp_v == "ForecastLineChart"
        assert llamadas_veh == [("vehicular", "CSF11")]
        assert "40 plazas" in res_v
        assert "vehículos presentes" in res_v

    asyncio.run(_run())


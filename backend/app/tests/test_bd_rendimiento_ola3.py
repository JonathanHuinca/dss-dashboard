"""
Pruebas unitarias para integridad referencial, rollbacks, deduplicación y optimización BD (Ola 3):
- Nulificación de FKs NO ACTION al eliminar cuentas de usuario o destinatarios consultores.
- Rollback explícito en bloques except de ingesta, smart campus, calendario anual y caché.
- Deduplicación con clave camara y ventana de +60s en VehicleService y AttendanceService.
- Eliminación de tormenta N+1 en GET /api/v1/admin/tareas y precargar_contexto_operativo.
- Agregaciones SQL en get_download_audit_history y obtener_auditoria_reportes_emitidos (creado_por_id=None).
- Uso de LEAD() y exclusión de 'unknown' en estadía e intercampus vehicular.
- Escapado LIKE '%[[]%' en CalendarService y .limit(1) en cuota IA chat.
"""
import asyncio
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.dialects import mssql

from app.api.v1.endpoints.admin import listar_tareas_admin
from app.cli.limpiar_demo import limpiar_cuentas_demo
from app.core import cache as cache_mod
from app.domain.auth_models import Rol, Usuario
from app.ml.orquestador_entrenamiento import precargar_contexto_operativo
from app.schemas.tarea_schemas import ResumenTareasResponse
from app.services import audit_service, auth_service, ingestion_service
from app.services import servicio_calendario_anual, servicio_chat_persistente, servicio_smart_campus
from app.services.attendance_service import AttendanceService
from app.services.calendar_service import CalendarService
from app.services.servicio_reportes_compartidos import ServicioReportesCompartidos
from app.services.vehicle_service import VehicleService


def _crear_usuario(uid: int, email: str, rol_nombre: str) -> Usuario:
    u = Usuario(
        id=uid,
        email=email,
        nombre_completo=f"Usuario {rol_nombre}",
        hashed_password="$2b$12$dummyhash000000000000000000000000000000000000000000",
        is_active=True,
        espacio_id=None,
    )
    u.roles = [Rol(id=uid, nombre=rol_nombre)]
    return u


def _compilar_sql(stmt, literal_binds: bool = False) -> str:
    try:
        kwargs = {"literal_binds": True} if literal_binds else {}
        return str(stmt.compile(dialect=mssql.dialect(), compile_kwargs=kwargs))
    except Exception:
        return str(stmt)


class _FakeResult:
    def __init__(self, obj=None, items=None, scalar_val=None, rows=None):
        self._obj = obj
        self._items = items if items is not None else []
        self._scalar = scalar_val
        self._rows = rows if rows is not None else self._items

    def scalar_one_or_none(self):
        return self._obj

    def scalar(self):
        return self._scalar if self._scalar is not None else self._obj

    def fetchall(self):
        return self._rows

    def all(self):
        return self._rows

    def one(self):
        return self._obj

    def first(self):
        return self._rows[0] if self._rows else self._obj

    def scalars(self):
        items = self._items
        return SimpleNamespace(
            all=lambda: items,
            first=lambda: items[0] if items else None,
        )


def test_eliminar_usuario_cuenta_nulifica_fks_antes_de_borrar():
    """Verifica nulificación de created_by_user_id y ingestion_jobs.creado_por antes de DELETE Usuario."""
    admin = _crear_usuario(1, "admin@uct.cl", "Admin_Sistema")
    objetivo = _crear_usuario(50, "", "Analista_Consulta")
    sqls = []

    db = MagicMock()
    async def _exec(stmt, params=None):
        sqls.append(_compilar_sql(stmt))
        return _FakeResult()

    db.execute = AsyncMock(side_effect=_exec)
    db.commit = AsyncMock()

    with patch("app.services.auth_service.get_user_by_id", new=AsyncMock(return_value=objetivo)):
        ok = asyncio.run(auth_service.eliminar_usuario_cuenta(db, 50, admin))

    assert ok is True
    assert db.commit.await_count == 1
    idx_upd_usr = next(i for i, s in enumerate(sqls) if "UPDATE usuarios SET created_by_user_id=" in s)
    idx_upd_job = next(i for i, s in enumerate(sqls) if "UPDATE ingestion_jobs SET creado_por=" in s)
    idx_del_usr = next(i for i, s in enumerate(sqls) if "DELETE FROM usuarios" in s)
    assert idx_upd_usr < idx_del_usr
    assert idx_upd_job < idx_del_usr


def test_eliminar_destinatario_consultor_nulifica_fks_usuario():
    """Verifica nulificación previa al eliminar Usuario asociado a un destinatario consultor."""
    admin = _crear_usuario(1, "admin@uct.cl", "Admin_Sistema")
    dest = SimpleNamespace(id=77, email="consultor@uct.cl", nombre_completo="Consultor", creado_por_id=1)
    usr = _crear_usuario(88, "consultor@uct.cl", "Consultor_Reporte")
    sqls = []

    session = MagicMock()
    async def _exec(stmt, params=None):
        sql = _compilar_sql(stmt)
        sqls.append(sql)
        if "SELECT destinatarios_reportes." in sql:
            return _FakeResult(obj=dest)
        if "SELECT reportes_compartidos.id" in sql:
            return _FakeResult(items=[])
        if "SELECT usuarios." in sql:
            return _FakeResult(obj=usr)
        return _FakeResult()

    session.execute = AsyncMock(side_effect=_exec)
    session.commit = AsyncMock()

    res = asyncio.run(ServicioReportesCompartidos.eliminar_destinatario_consultor(session, admin, 77))
    assert res["eliminado"] is True
    idx_upd_usr = next(i for i, s in enumerate(sqls) if "UPDATE usuarios SET created_by_user_id=" in s)
    idx_upd_job = next(i for i, s in enumerate(sqls) if "UPDATE ingestion_jobs SET creado_por=" in s)
    idx_del_usr = next(i for i, s in enumerate(sqls) if "DELETE FROM usuarios" in s)
    assert idx_upd_usr < idx_del_usr
    assert idx_upd_job < idx_del_usr


def test_limpiar_cuentas_demo_sin_lower_y_nulifica_fks():
    """Verifica búsqueda SARGable por email y limpieza de FKs antes de borrar usuarios demo."""
    sqls = []
    usr_demo = SimpleNamespace(id=99, email="directivo@uct.cl", roles=[])

    db = MagicMock()
    async def _exec(stmt, params=None):
        sql = _compilar_sql(stmt)
        sqls.append(sql)
        if "FROM usuarios" in sql and sql.startswith("SELECT"):
            return _FakeResult(items=[usr_demo])
        if "SELECT reportes_compartidos.id" in sql:
            return _FakeResult(items=[])
        if "SELECT destinatarios_reportes.id" in sql:
            return _FakeResult(items=[])
        return _FakeResult()

    db.execute = AsyncMock(side_effect=_exec)
    db.commit = AsyncMock()

    ctx_mgr = MagicMock()
    ctx_mgr.__aenter__ = AsyncMock(return_value=db)
    ctx_mgr.__aexit__ = AsyncMock(return_value=False)

    with patch("app.cli.limpiar_demo.AsyncSessionLocal", return_value=ctx_mgr):
        res = asyncio.run(limpiar_cuentas_demo(dry_run=False, incluir_consultores_prueba=False))

    assert "directivo@uct.cl" in res["eliminados"]
    selects_email = [s for s in sqls if "destinatarios_reportes" in s and s.startswith("SELECT")]
    assert selects_email and all("lower(" not in s.lower() for s in selects_email)
    idx_upd_usr = next(i for i, s in enumerate(sqls) if "UPDATE usuarios SET created_by_user_id=" in s)
    idx_upd_job = next(i for i, s in enumerate(sqls) if "UPDATE ingestion_jobs SET creado_por=" in s)
    idx_del_usr = next(i for i, s in enumerate(sqls) if "DELETE FROM usuarios" in s)
    assert idx_upd_usr < idx_del_usr
    assert idx_upd_job < idx_del_usr


def test_rollbacks_explicitos_en_bloques_except():
    """Valida que los except críticos invoquen await db.rollback() tras excepciones SQL."""
    # 1. ingestion_service.procesar_archivo_por_lotes
    job_id = uuid.uuid4()
    job_obj = SimpleNamespace(id=job_id, estado="pending", detalle_error=None, errores_count=0, progreso_porcentaje=0)
    db_ing = MagicMock()
    db_ing.get = AsyncMock(return_value=job_obj)
    db_ing.commit = AsyncMock()
    db_ing.rollback = AsyncMock()
    ctx_ing = MagicMock()
    ctx_ing.__aenter__ = AsyncMock(return_value=db_ing)
    ctx_ing.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.ingestion_service.AsyncSessionLocal", return_value=ctx_ing), patch(
        "app.services.ingestion_service.es_archivo_institucional_uct",
        side_effect=RuntimeError("fallo_simulado_ingesta"),
    ):
        asyncio.run(
            ingestion_service.procesar_archivo_por_lotes(
                job_id=job_id,
                ruta_archivo=Path("/tmp/inexistente.csv"),
                tipo="asistencia",
                espacio_id=1,
            )
        )
    assert db_ing.rollback.await_count >= 1
    assert job_obj.estado == "failed"

    # 2. servicio_smart_campus.sincronizar_aforo_vivo_horario (fallo dentro de try de sincronización)
    db_sc = MagicMock()
    sc_calls = {"n": 0}
    async def _sc_exec(stmt, params=None):
        sc_calls["n"] += 1
        if sc_calls["n"] == 1:
            raise RuntimeError("fallo_sql_smart_campus")
        return _FakeResult(obj=None)
    db_sc.execute = AsyncMock(side_effect=_sc_exec)
    db_sc.add = MagicMock()
    db_sc.commit = AsyncMock()
    db_sc.refresh = AsyncMock()
    db_sc.rollback = AsyncMock()
    fake_adapt = MagicMock()
    fake_adapt.obtener_marcajes_torniquetes = AsyncMock(
        return_value=[{"fecha": "2026-11-20T10:00:00", "matricula": "123"}]
    )
    fake_adapt.obtener_marcajes_estacionamiento = AsyncMock(return_value=[])
    fake_adapt.obtener_accesos_vehiculares = AsyncMock(return_value=[])
    with patch("app.services.servicio_smart_campus.SmartCampusAdapter", return_value=fake_adapt):
        res_sc = asyncio.run(
            servicio_smart_campus.sincronizar_aforo_vivo_horario(
                db_sc,
                desde_manual=date(2026, 11, 20),
                hasta_manual=date(2026, 11, 20),
            )
        )
    assert len(res_sc["errores"]) >= 1
    assert db_sc.rollback.await_count >= 1

    # 3. servicio_calendario_anual.sincronizar_calendario_anual
    db_cal = MagicMock()
    db_cal.execute = AsyncMock(return_value=_FakeResult(obj=None))
    db_cal.flush = AsyncMock()
    db_cal.rollback = AsyncMock()
    db_cal.add = MagicMock()
    db_cal.commit = AsyncMock()
    db_cal.refresh = AsyncMock()
    with patch(
        "app.services.servicio_calendario_anual.scrape_and_sync_uct_calendar",
        new=AsyncMock(side_effect=RuntimeError("fallo_sql_calendario")),
    ):
        res_cal = asyncio.run(servicio_calendario_anual.sincronizar_calendario_anual(db_cal, anio_objetivo=2026))
    assert res_cal["status"] == "pendiente"
    assert db_cal.rollback.await_count >= 1

    # 4. core.cache.precalentar_cache_modulos
    db_cache = MagicMock()
    db_cache.execute = AsyncMock(side_effect=RuntimeError("fallo_sql_cache"))
    db_cache.rollback = AsyncMock()
    ctx_cache = MagicMock()
    ctx_cache.__aenter__ = AsyncMock(return_value=db_cache)
    ctx_cache.__aexit__ = AsyncMock(return_value=False)
    cache_mod._precalentamiento_en_curso = False
    with patch("app.core.database.AsyncSessionLocal", return_value=ctx_cache), patch(
        "app.api.v1.endpoints.metrics.get_date_bounds",
        new=AsyncMock(return_value={"fecha_min": "2026-03-01", "fecha_max": "2026-10-14"}),
    ), patch("os.makedirs", side_effect=OSError("no escribir en test")):
        asyncio.run(cache_mod.precalentar_cache_modulos())
    assert db_cache.rollback.await_count >= 1


def test_deduplicacion_vehicle_incluye_camara_y_ventana_60s():
    """Valida que VehicleService considere camara en la clave de duplicados y ventana +60s."""
    ts = datetime(2026, 11, 20, 10, 0, 0)
    dtos = [
        SimpleNamespace(
            espacio_id=2, patente_hash="HASH_A", time=ts, camara="CAM_NORTE",
            direccion="entrada", tipo_vehiculo="auto", marca=None, color=None, calidad_lectura="ok",
        ),
        SimpleNamespace(
            espacio_id=2, patente_hash="HASH_A", time=ts, camara="CAM_SUR",
            direccion="entrada", tipo_vehiculo="auto", marca=None, color=None, calidad_lectura="ok",
        ),
    ]
    captured_params = []
    db = MagicMock()

    async def _exec(stmt, params=None):
        sql = _compilar_sql(stmt)
        if "SELECT eventos_vehiculares.time" in sql:
            compiled = stmt.compile(dialect=mssql.dialect())
            captured_params.append(dict(compiled.params))
            return _FakeResult(rows=[(ts, 2, "HASH_A", "CAM_NORTE")])
        return _FakeResult()

    db.execute = AsyncMock(side_effect=_exec)
    db.commit = AsyncMock()

    res = asyncio.run(VehicleService.bulk_insert_events(db, dtos, modo_solapamiento="merge", espacio_id=2))
    assert res["insertados"] == 1
    assert captured_params
    assert any(v == ts + timedelta(seconds=60) for v in captured_params[0].values())


def test_deduplicacion_attendance_ventana_60s():
    """Valida que AttendanceService consulte duplicados hasta max_ts + 60 segundos."""
    ts = datetime(2026, 11, 20, 14, 30, 0)
    dtos = [
        SimpleNamespace(
            espacio_id=1, person_id_hash="PER_1", time=ts,
            primera_entrada=ts, ultima_salida=None, permanencia_min=None,
            marcajes_totales=1, estado_marcaje="completo", puerta="P1",
            door_entrada="P1", door_salida=None, salida_imputada=0, entrada_imputada=0,
            alerta_coherencia_fechas=0, alerta_marcajes=False,
            carrera=None, facultad=None, estamento="Estudiante",
        ),
    ]
    captured_params = []
    db = MagicMock()

    async def _exec(stmt, params=None):
        sql = _compilar_sql(stmt)
        if "SELECT eventos_asistencia.time" in sql:
            compiled = stmt.compile(dialect=mssql.dialect())
            captured_params.append(dict(compiled.params))
            return _FakeResult(rows=[(ts, 1, "PER_1")])
        return _FakeResult()

    db.execute = AsyncMock(side_effect=_exec)
    db.commit = AsyncMock()

    res = asyncio.run(AttendanceService.bulk_insert_events(db, dtos, modo_solapamiento="merge", espacio_id=1))
    assert res["insertados"] == 0
    assert captured_params
    assert any(v == ts + timedelta(seconds=60) for v in captured_params[0].values())


def test_listar_tareas_admin_sin_n_plus_1_y_precargar_contexto():
    """Verifica que listar_tareas_admin y precargar_contexto_operativo operen en queries constantes."""
    s_ctx = MagicMock()
    s_ctx.execute = AsyncMock(return_value=_FakeResult(items=[]))
    asyncio.run(precargar_contexto_operativo(s_ctx, fecha_inicio=date(2026, 11, 20), dias=35))
    assert s_ctx.execute.await_count == 3

    admin = _crear_usuario(1, "admin@uct.cl", "Admin_Sistema")
    db = MagicMock()
    db.execute = AsyncMock(return_value=_FakeResult(items=[]))
    resp = asyncio.run(listar_tareas_admin(current_user=admin, db=db))
    assert isinstance(resp, ResumenTareasResponse)
    assert len(resp.catalogo) >= 1
    assert db.execute.await_count <= 6


def test_get_download_audit_history_agregaciones_sql():
    """Verifica stats calculadas en SQL sin cargar toda la tabla de descargas."""
    reg = SimpleNamespace(
        id=10, usuario_id=1, modulo="biblioteca", formato="csv",
        filtro_fecha_inicio="2026-11-01", filtro_fecha_fin="2026-11-20",
        filtro_detalle=None, total_registros=50, ip_origen="127.0.0.1",
        timestamp=datetime(2026, 11, 20, 12, 0, 0),
        usuario=SimpleNamespace(email="admin@uct.cl", nombre_completo="Admin"),
    )
    session = MagicMock()

    async def _exec(stmt, params=None):
        sql = _compilar_sql(stmt)
        if "count(download_audit_logs.id) AS count_1, sum(" in sql.lower() or "sum(CASE" in sql:
            return _FakeResult(obj=(2, 1, 1, 1))
        if "GROUP BY download_audit_logs.modulo" in sql:
            return _FakeResult(rows=[("biblioteca", 2)])
        if "count(download_audit_logs.id)" in sql.lower():
            return _FakeResult(scalar_val=2)
        return _FakeResult(items=[reg])

    session.execute = AsyncMock(side_effect=_exec)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.audit_service.AsyncSessionLocal", return_value=ctx):
        res = asyncio.run(audit_service.get_download_audit_history(page=1, page_size=10))

    assert res["total"] == 2
    assert len(res["items"]) == 1
    assert res["stats"]["total_descargas"] == 2
    assert res["stats"]["descargas_hoy"] == 1
    assert res["stats"]["descargas_por_modulo"] == {"biblioteca": 2}


def test_obtener_auditoria_reportes_emitidos_creado_por_none():
    """Valida KPIs agregados, paginación SQL y soporte para creado_por_id=None."""
    admin = _crear_usuario(1, "admin@uct.cl", "Admin_Sistema")
    rep_id = str(uuid.uuid4())
    dest = SimpleNamespace(
        id=5, nombre_completo="Decano", email="decano@uct.cl",
        cargo="Decano", unidad_academica="Ingenieria", token_portal="tok_portal", activo=True,
    )
    rep = SimpleNamespace(
        id=rep_id, codigo_corto="RPT-001", titulo_reporte="Informe Test",
        finalidad_reporte="Seguimiento", nota_general="", modo_datos="instantanea",
        filtros_bloqueados_json="{}", permitir_exportacion=True, permitir_ia=True,
        espacio_id=1, subespacio="todos", fecha_inicio=date(2026, 10, 1), fecha_fin=date(2026, 10, 31),
        creado_por_id=None, creado_en=datetime(2026, 11, 1, 10, 0),
        expira_en=None, activo=True, estado="activo", total_accesos=3,
        primer_acceso_en=None, ultimo_acceso_en=datetime(2026, 11, 2, 9, 0),
        notas_items_json=None, indicadores_visibles_json=None, graficos_visibles_json=None,
        permite_ia=True, cuota_ia_max=10, periodo_texto="Octubre 2026",
        token_acceso="tok_acc", destinatario=dest, destinatario_id=5,
    )
    kpi_row = SimpleNamespace(
        total_universo=1, revisados_total=1, aperturas_total=3, descargas_total=1, consultas_ia_total=2
    )
    session = MagicMock()

    async def _exec(stmt, params=None):
        sql = _compilar_sql(stmt)
        if "AS total_universo" in sql:
            return _FakeResult(obj=kpi_row)
        if "FROM (" in sql and "rep_id" in sql:
            return _FakeResult(items=[rep_id])
        if "FROM reportes_compartidos" in sql:
            return _FakeResult(items=[rep])
        if "FROM auditoria_accesos_reporte" in sql:
            return _FakeResult(rows=[])
        if "FROM mensajes_ia_reporte" in sql:
            return _FakeResult(rows=[])
        if "FROM espacios" in sql:
            return _FakeResult(rows=[(1, "Biblioteca CSF")])
        return _FakeResult(rows=[])

    session.execute = AsyncMock(side_effect=_exec)
    res = asyncio.run(ServicioReportesCompartidos.obtener_auditoria_reportes_emitidos(session, admin))
    assert res["kpis"]["total_reportes"] == 1
    assert res["kpis"]["total_aperturas"] == 3
    assert len(res["items"]) == 1
    assert res["items"][0]["emisor"]["id"] is None
    assert res["items"][0]["emisor"]["nombre_completo"] == "Sistema DSS"


def test_vehicle_stay_y_intercampus_usan_lead_y_sin_unknown():
    """Verifica uso de LEAD() y exclusión de patente_hash='unknown' en analítica vehicular."""
    sqls_stay = []
    s_stay = MagicMock()
    async def _exec_stay(stmt, params=None):
        sqls_stay.append(str(stmt))
        return _FakeResult(rows=[SimpleNamespace(rango="drop_off", total=4)])
    s_stay.execute = AsyncMock(side_effect=_exec_stay)
    res_stay = asyncio.run(
        VehicleService.get_stay_distribution(
            s_stay, espacio_id=2, fecha_inicio=date(2026, 11, 1), fecha_fin=date(2026, 11, 20)
        )
    )
    assert sqls_stay
    assert "LEAD(" in sqls_stay[0]
    assert "patente_hash <> 'unknown'" in sqls_stay[0]
    assert res_stay == [{"rango": "drop_off", "total": 4}]

    sqls_mob = []
    s_mob = MagicMock()
    async def _exec_mob(stmt, params=None):
        sqls_mob.append(str(stmt))
        return _FakeResult(rows=[])
    s_mob.execute = AsyncMock(side_effect=_exec_mob)
    res_mob = asyncio.run(
        VehicleService.get_intercampus_mobility(
            s_mob, espacio_id=2, fecha_inicio=date(2026, 11, 1), fecha_fin=date(2026, 11, 20)
        )
    )
    assert sqls_mob
    assert "LEAD(" in sqls_mob[0]
    assert "espacio_id = :espacio_id" in sqls_mob[0]
    assert res_mob["total_viajes"] == 0


def test_calendar_like_escapado_y_cuota_chat_limit_1():
    """Valida LIKE '%[[]%' en CalendarService y TOP 1 / LIMIT 1 en cuota IA chat."""
    cal_sqls = []
    db_cal = MagicMock()
    async def _exec_cal(stmt, params=None):
        cal_sqls.append(_compilar_sql(stmt, literal_binds=True))
        return _FakeResult(rows=[], items=[])
    db_cal.execute = AsyncMock(side_effect=_exec_cal)
    db_cal.commit = AsyncMock()
    asyncio.run(CalendarService().sanear_calendario_contingencias(db_cal))
    assert cal_sqls and "%[[]%" in cal_sqls[0]

    chat_sqls = []
    usr = _crear_usuario(10, "ana@uct.cl", "Analista_Consulta")
    db_chat = MagicMock()
    async def _exec_chat(stmt, params=None):
        chat_sqls.append(_compilar_sql(stmt, literal_binds=True))
        return _FakeResult(scalar_val=0, items=[])
    db_chat.execute = AsyncMock(side_effect=_exec_chat)
    asyncio.run(servicio_chat_persistente.obtener_cuota_ia_usuario(db_chat, usr))
    assert len(chat_sqls) >= 2
    assert "TOP 1" in chat_sqls[-1] or "TOP (1)" in chat_sqls[-1] or "LIMIT 1" in chat_sqls[-1]

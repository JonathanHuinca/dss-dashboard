"""Matriz exhaustiva de control de acceso RBAC/RLS por rol, recinto y verbo HTTP sobre los 12 routers."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.security import (
    create_access_token,
    get_current_user,
    require_permission,
    require_role,
    require_roles,
    validar_acceso_espacio,
)
from app.main import app
from app.services.attendance_service import AttendanceService
from app.services.vehicle_service import VehicleService
from app.tests.conftest import crear_usuario_mock


# ---------------------------------------------------------------------------
# Matriz parametrizada: (rol, espacio_id, datasets, flags) x (metodo, ruta, payload, esperado_401_o_403)
# ---------------------------------------------------------------------------

ROLES_MATRIZ = {
    "anonimo": None,
    "admin": crear_usuario_mock("admin@uct.cl", ["Admin_Sistema"], espacio_id=None, can_use_ai=True, can_export=True, can_ingest=True, user_id=1),
    "director_bib": crear_usuario_mock("dir.bib@uct.cl", ["Director_Recinto"], espacio_id=1, allowed_datasets=["biblioteca"], can_use_ai=True, can_export=True, can_ingest=True, user_id=2),
    "director_est": crear_usuario_mock("dir.est@uct.cl", ["Director_Recinto"], espacio_id=2, allowed_datasets=["estacionamiento"], can_use_ai=True, can_export=True, can_ingest=True, user_id=3),
    "analista_bib": crear_usuario_mock("ana.bib@uct.cl", ["Analista_Consulta"], espacio_id=1, allowed_datasets=["biblioteca"], can_use_ai=True, can_export=True, can_ingest=False, user_id=4),
    "guardia_bib": crear_usuario_mock("gua.bib@uct.cl", ["Guardia_Seguridad"], espacio_id=1, allowed_datasets=["biblioteca"], can_use_ai=False, can_export=False, can_ingest=False, user_id=5),
    "consultor": crear_usuario_mock("con@uct.cl", ["Consultor_Reporte"], espacio_id=1, allowed_datasets=["biblioteca"], can_use_ai=False, can_export=False, can_ingest=False, user_id=6),
}


@pytest.mark.parametrize(
    "metodo,ruta,body,denegados",
    [
        # 1. Router auth
        ("GET", "/api/v1/auth/me", None, {"anonimo"}),
        ("GET", "/api/v1/auth/users", None, {"anonimo", "analista_bib", "guardia_bib", "consultor"}),
        ("POST", "/api/v1/auth/invite", {"email": "n@uct.cl", "nombre_completo": "N"}, {"anonimo", "analista_bib", "guardia_bib", "consultor"}),
        ("DELETE", "/api/v1/auth/users/99", None, {"anonimo", "director_bib", "director_est", "analista_bib", "guardia_bib", "consultor"}),
        # 2. Router admin
        ("GET", "/api/v1/admin/config", None, {"anonimo", "director_bib", "director_est", "analista_bib", "guardia_bib", "consultor"}),
        ("PUT", "/api/v1/admin/config", {"active_provider": "gemini", "default_model": "gemini-2.5-flash"}, {"anonimo", "director_bib", "director_est", "analista_bib", "guardia_bib", "consultor"}),
        ("POST", "/api/v1/admin/cache/limpiar", {}, {"anonimo", "director_bib", "director_est", "analista_bib", "guardia_bib", "consultor"}),
        # 3. Router config
        ("GET", "/api/v1/config/espacios", None, {"anonimo"}),
        ("PUT", "/api/v1/config/espacios/1/capacidad", {"capacidad_max": 300}, {"anonimo", "analista_bib", "guardia_bib", "consultor"}),
        ("POST", "/api/v1/config/calendar/depurar", None, {"anonimo", "director_bib", "director_est", "analista_bib", "guardia_bib", "consultor"}),
        ("POST", "/api/v1/config/horarios", {"espacio_id": 1, "anio": 2026, "descripcion": "Test", "hora_apertura": "08:00", "hora_cierre": "20:00"}, {"anonimo", "analista_bib", "guardia_bib", "consultor"}),
        ("DELETE", "/api/v1/config/horarios/1", None, {"anonimo", "analista_bib", "guardia_bib", "consultor"}),
        # 4. Router metrics
        ("GET", "/api/v1/metrics/kpi-summary?espacio_id=1", None, {"anonimo", "director_est"}),
        ("GET", "/api/v1/metrics/date-bounds?espacio_id=2", None, {"anonimo", "director_bib", "analista_bib", "guardia_bib", "consultor"}),
        # 5. Router attendance
        ("GET", "/api/v1/attendance/kpis?espacio_id=1", None, {"anonimo", "director_est"}),
        ("GET", "/api/v1/attendance/export-raw-csv?espacio_id=1", None, {"anonimo", "director_est", "guardia_bib", "consultor"}),
        # 6. Router vehicles
        ("GET", "/api/v1/vehicles/kpis?espacio_id=2", None, {"anonimo", "director_bib", "analista_bib", "guardia_bib", "consultor"}),
        ("GET", "/api/v1/vehicles/sectores", None, {"anonimo", "director_bib", "analista_bib", "guardia_bib", "consultor"}),
        # 7. Router predictions
        ("GET", "/api/v1/predictions/forecast-parking?sector=todos", None, {"anonimo", "director_bib", "analista_bib", "guardia_bib", "consultor"}),
        # 8. Router ingestion
        ("GET", "/api/v1/ingestion/history", None, {"anonimo", "analista_bib", "guardia_bib", "consultor"}),
        ("POST", "/api/v1/ingestion/retroactive-enrich", None, {"anonimo", "analista_bib", "guardia_bib", "consultor"}),
        # 9. Router assistant
        ("GET", "/api/v1/assistant/models", None, {"anonimo"}),
        ("POST", "/api/v1/assistant/chat", {"message": "Hola"}, {"anonimo", "guardia_bib", "consultor"}),
        # 10. Router chat
        ("GET", "/api/v1/chat/cuota", None, {"anonimo", "guardia_bib", "consultor"}),
        ("POST", "/api/v1/chat/purgar-eliminadas", None, {"anonimo", "director_bib", "director_est", "analista_bib", "guardia_bib", "consultor"}),
        ("PATCH", "/api/v1/chat/conversaciones/11111111-1111-1111-1111-111111111111/renombrar", {"titulo": "Nuevo"}, {"anonimo", "guardia_bib", "consultor"}),
        # 11. Router export
        ("POST", "/api/v1/export/excel/grafico", {"id": "g1", "titulo": "T", "categorias_x": ["A"], "series": [{"nombre": "S", "valores": [1]}]}, {"anonimo", "guardia_bib", "consultor"}),
        ("GET", "/api/v1/export/excel/plantilla-salas-estudio?espacio_id=1", None, {"anonimo", "director_est", "guardia_bib", "consultor"}),
        # 12. Router reportes-compartidos
        ("GET", "/api/v1/reportes-compartidos", None, {"anonimo", "guardia_bib", "consultor"}),
        ("GET", "/api/v1/reportes-compartidos/auditoria", None, {"anonimo", "analista_bib", "guardia_bib", "consultor"}),
        ("DELETE", "/api/v1/reportes-compartidos/destinatarios/1", None, {"anonimo", "director_bib", "director_est", "analista_bib", "guardia_bib", "consultor"}),
    ],
)
def test_matriz_rbac_rls_12_routers(app_client, metodo, ruta, body, denegados):
    """Verifica denegación 401/403 para cada combinación no autorizada sobre los 12 routers."""
    for rol_key, usuario in ROLES_MATRIZ.items():
        if rol_key not in denegados:
            continue
        client = app_client(usuario)
        resp = client.request(metodo, ruta, json=body)
        if rol_key == "anonimo":
            assert resp.status_code in (401, 403), f"{metodo} {ruta} anónimo devolvió {resp.status_code}"
        else:
            assert resp.status_code == 403, f"{metodo} {ruta} para {rol_key} devolvió {resp.status_code}: {resp.text}"


def test_seguridad_core_jwt_roles_permisos_y_rls():
    """Cubre create_access_token, get_current_user, require_role, require_roles, require_permission y validar_acceso_espacio."""
    token = create_access_token(user_id=1, rol="Admin_Sistema", roles=["Admin_Sistema"])
    assert isinstance(token, str) and token.count(".") == 2

    admin = crear_usuario_mock("a@uct.cl", ["Admin_Sistema"], espacio_id=None, can_use_ai=True, can_export=True, can_ingest=True)
    analista = crear_usuario_mock("b@uct.cl", ["Analista_Consulta"], espacio_id=1, allowed_datasets=["biblioteca"], can_use_ai=False, can_export=False)
    guardia = crear_usuario_mock("g@uct.cl", ["Guardia_Seguridad"], espacio_id=2, allowed_datasets=["estacionamiento"], can_use_ai=False, can_export=False)

    # RLS por espacio y dataset
    validar_acceso_espacio(1, admin)
    validar_acceso_espacio(2, admin)
    validar_acceso_espacio(1, analista)
    with pytest.raises(HTTPException) as exc1:
        validar_acceso_espacio(2, analista)
    assert exc1.value.status_code == 403

    validar_acceso_espacio(2, guardia)
    with pytest.raises(HTTPException) as exc2:
        validar_acceso_espacio(1, guardia)
    assert exc2.value.status_code == 403

    async def _run():
        dep_admin = require_role("Admin_Sistema")
        assert await dep_admin(admin) is admin
        with pytest.raises(HTTPException):
            await dep_admin(analista)

        dep_multi = require_roles(["Director_Recinto", "Analista_Consulta"])
        assert await dep_multi(analista) is analista
        with pytest.raises(HTTPException):
            await dep_multi(guardia)

        dep_perm = require_permission("can_export")
        assert await dep_perm(admin) is admin
        with pytest.raises(HTTPException):
            await dep_perm(guardia)

        # Token expirado o inválido en get_current_user
        token_exp = create_access_token(user_id=1, rol="Admin_Sistema", expires_delta=timedelta(minutes=-5))
        with pytest.raises(HTTPException) as exc_exp:
            await get_current_user(credentials=SimpleNamespace(credentials=token_exp), db=AsyncMock())
        assert exc_exp.value.status_code == 401

        with pytest.raises(HTTPException) as exc_bad:
            await get_current_user(credentials=SimpleNamespace(credentials="token.malformado.xyz"), db=AsyncMock())
        assert exc_bad.value.status_code == 401

    asyncio.run(_run())


def test_endpoints_permitidos_con_mocks_para_roles_autorizados(app_client, admin_user, director_bib_user, analista_bib_user):
    """Valida respuestas 200 en endpoints clave para roles autorizados usando mocks sin BD viva."""
    # Auth /me
    client_ana = app_client(analista_bib_user)
    r_me = client_ana.get("/api/v1/auth/me")
    assert r_me.status_code == 200
    assert r_me.json()["email"] == "analista.bib@uct.cl"

    # Metrics /kpi-summary y /date-bounds
    with (
        patch("app.api.v1.endpoints.metrics.MetricsService.get_kpi_summary", new=AsyncMock(return_value={
            "dias_operativos": 10,
            "horas_estudiante": 120.5,
            "recurrencia_mensual": 2.3,
            "hora_pico_ingreso": "10:00",
            "pico_concurrente": 80,
        })),
        patch("app.api.v1.endpoints.metrics.MetricsService.get_date_bounds", new=AsyncMock(return_value={
            "fecha_min": "2026-03-01",
            "fecha_max": "2026-10-14",
            "meses_disponibles": [],
        })),
    ):
        assert client_ana.get("/api/v1/metrics/kpi-summary?espacio_id=1").status_code == 200
        assert client_ana.get("/api/v1/metrics/date-bounds?espacio_id=1").status_code == 200

    # Attendance y Vehicles con Admin
    client_adm = app_client(admin_user)
    with (
        patch.object(AttendanceService, "get_kpis", new=AsyncMock(return_value={"total_registros": 5})),
        patch.object(VehicleService, "get_kpis", new=AsyncMock(return_value={"vehiculos_unicos": 3})),
        patch("app.services.servicio_smart_campus.listar_sectores_estacionamiento", new=AsyncMock(return_value=[])),
    ):
        assert client_adm.get("/api/v1/attendance/kpis?espacio_id=1").status_code == 200
        assert client_adm.get("/api/v1/vehicles/kpis?espacio_id=2").status_code == 200
        assert client_adm.get("/api/v1/vehicles/sectores").status_code == 200

    # Predictions /alerts y /visit-profiles
    with (
        patch("app.api.v1.endpoints.predictions.get_active_alerts", new=AsyncMock(return_value={"alertas": [], "total_alertas": 0})),
        patch("app.api.v1.endpoints.predictions.get_visit_profiles", new=AsyncMock(return_value={"espacio_id": 1, "perfiles": []})),
    ):
        assert client_ana.get("/api/v1/predictions/alerts?espacio_id=1").status_code == 200
        assert client_ana.get("/api/v1/predictions/visit-profiles?espacio_id=1").status_code == 200

    # Ingestion history con Director_Recinto
    client_dir = app_client(director_bib_user)
    assert client_dir.get("/api/v1/ingestion/history").status_code == 200

    # Assistant models (deshabilitando check_ia_active o devolviendo activo)
    with patch("app.services.config_service.get_configuracion_espacio", new=AsyncMock(return_value=SimpleNamespace(ia_asistente_activo=True))):
        r_mod = client_ana.get("/api/v1/assistant/models")
        assert r_mod.status_code == 200
        assert "models" in r_mod.json()

    # Admin cache stats y purga con Admin
    client_adm = app_client(admin_user)
    with patch("app.core.cache.obtener_cache") as mock_cache:
        c_inst = MagicMock()
        c_inst.get_stats = MagicMock(return_value={"aforo_vivo_items": 0, "kpis_dia_items": 0, "historicos_items": 0, "general_items": 0, "total_items": 0})
        mock_cache.return_value = c_inst
        assert client_adm.get("/api/v1/admin/cache/stats").status_code == 200

"""Pruebas de contratos full-stack, RBAC, validación y fugas de recursos (Ola 5)."""
import asyncio
import os
import sys
from types import SimpleNamespace
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.api.v1.endpoints.admin import _enmascarar_api_key_cifrada
from app.api.v1.endpoints.config import check_ia_active
from app.core.cache import CacheEnMemoria, TTL_HISTORICOS, invalidar_cache_por_espacio, limpiar_toda_la_cache
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.security_cipher import encrypt_api_key
from app.domain.auth_models import Rol, Usuario
from app.domain.models import IngestionJob
from app.main import app
from app.services import ingestion_service
from app.services.attendance_service import AttendanceService
from app.services.vehicle_service import VehicleService


def _crear_usuario(
    email: str,
    roles_nombres: List[str],
    espacio_id: Optional[int] = None,
    allowed_datasets: Optional[List[str]] = None,
    can_export: bool = True,
) -> Usuario:
    u = Usuario(
        id=900,
        email=email,
        nombre_completo=f"Usuario {email}",
        hashed_password="hash",
        is_active=True,
        espacio_id=espacio_id,
        allowed_datasets=allowed_datasets if allowed_datasets is not None else ["biblioteca", "estacionamiento"],
        can_use_ai=True,
        can_export=can_export,
        can_ingest=False,
    )
    u.roles = [Rol(id=i + 1, nombre=nom) for i, nom in enumerate(roles_nombres)]
    return u


async def _fake_db():
    yield SimpleNamespace()


def test_vehicles_sectores_accesible_no_admin_y_protegido_por_rls():
    sectores_mock = [
        SimpleNamespace(
            id=1,
            espacio_id=2,
            codigo="CSF11",
            nombre="Sector CSF11",
            capacidad_max=40,
            camaras_entrada="E1",
            camaras_salida="S1",
            activo=True,
        )
    ]
    usuario_estac = _crear_usuario(
        "analista.est@uct.cl",
        ["Analista_Consulta"],
        espacio_id=2,
        allowed_datasets=["estacionamiento"],
    )
    usuario_bib = _crear_usuario(
        "analista.bib@uct.cl",
        ["Analista_Consulta"],
        espacio_id=1,
        allowed_datasets=["biblioteca"],
    )

    try:
        app.dependency_overrides[get_db] = _fake_db
        app.dependency_overrides[get_current_user] = lambda: usuario_estac
        with patch(
            "app.services.servicio_smart_campus.listar_sectores_estacionamiento",
            new=AsyncMock(return_value=sectores_mock),
        ):
            client = TestClient(app)
            resp_ok = client.get("/api/v1/vehicles/sectores")
            assert resp_ok.status_code == 200
            data = resp_ok.json()
            assert len(data) == 1
            assert data[0]["codigo"] == "CSF11"
            assert data[0]["espacio_id"] == 2

        app.dependency_overrides[get_current_user] = lambda: usuario_bib
        resp_forbidden = TestClient(app).get("/api/v1/vehicles/sectores")
        assert resp_forbidden.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_chat_purgar_eliminadas_exige_admin_sistema():
    try:
        app.dependency_overrides[get_db] = _fake_db
        app.dependency_overrides[check_ia_active] = lambda: None
        client = TestClient(app)
        for rol in ("Director_Recinto", "Analista_Consulta"):
            usuario = _crear_usuario(f"{rol.lower()}@uct.cl", [rol])
            app.dependency_overrides[get_current_user] = lambda u=usuario: u
            resp = client.post("/api/v1/chat/purgar-eliminadas")
            assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_admin_cache_limpiar_selectivo_por_espacio():
    async def _run():
        await limpiar_toda_la_cache()
        from app.core.cache import obtener_cache

        cache = obtener_cache()
        await cache.set("k_esp_1", {"v": 1}, ttl=TTL_HISTORICOS, tags=["espacio:1"])
        await cache.set("k_esp_2", {"v": 2}, ttl=TTL_HISTORICOS, tags=["espacio:2"])

        admin_user = _crear_usuario("admin@uct.cl", ["Admin_Sistema"])
        app.dependency_overrides[get_current_user] = lambda: admin_user
        try:
            resp = TestClient(app).post("/api/v1/admin/cache/limpiar?espacio_id=1")
            assert resp.status_code == 200
            body = resp.json()
            assert body["espacio_id"] == 1
            assert body["entradas_eliminadas"] >= 1
            assert await cache.get("k_esp_1") is None
            assert await cache.get("k_esp_2") == {"v": 2}
        finally:
            app.dependency_overrides.clear()
            await invalidar_cache_por_espacio(2)

    asyncio.run(_run())


def test_validacion_422_cuota_y_config_llm_y_enmascaramiento():
    admin_user = _crear_usuario("admin@uct.cl", ["Admin_Sistema"])
    try:
        app.dependency_overrides[get_current_user] = lambda: admin_user
        app.dependency_overrides[get_db] = _fake_db
        client = TestClient(app)

        resp_quota = client.put(
            "/api/v1/admin/roles/1/ia-quota",
            json={"rate_limit_quota": "ilimitado", "cooldown_segundos": -5},
        )
        assert resp_quota.status_code == 422

        resp_cfg = client.put(
            "/api/v1/admin/config",
            json={"active_provider": "x", "default_model": "y"},
        )
        assert resp_cfg.status_code == 422
    finally:
        app.dependency_overrides.clear()

    secreto = "sk-ant-api03-clave-secreta-uct-123456"
    cifrada = encrypt_api_key(secreto)
    assert cifrada.startswith("gAAAAAB")
    enmascarada = _enmascarar_api_key_cifrada(cifrada)
    assert "gAAAAAB" not in enmascarada
    assert enmascarada.endswith("3456")


def test_validacion_emailstr_en_reportes_compartidos():
    admin_user = _crear_usuario("admin@uct.cl", ["Admin_Sistema"])
    try:
        app.dependency_overrides[get_current_user] = lambda: admin_user
        app.dependency_overrides[get_db] = _fake_db
        client = TestClient(app)

        resp_cons = client.post(
            "/api/v1/reportes-compartidos/consultores",
            json={
                "nombre_completo": "Consultor Inválido",
                "email": "no-es-un-correo",
                "cargo": "Decano",
                "unidad_academica": "Facultad",
            },
        )
        assert resp_cons.status_code == 422

        resp_rep = client.post(
            "/api/v1/reportes-compartidos",
            json={
                "espacio_id": 1,
                "destinatario_nombre": "Consultor",
                "destinatario_email": "correo_invalido",
                "destinatario_cargo": "Director",
                "destinatario_unidad": "Biblioteca",
                "titulo_reporte": "Informe",
                "finalidad_reporte": "Revisión",
                "fecha_inicio": "2026-10-01",
                "fecha_fin": "2026-10-07",
                "modo_datos": "dinamico_acotado",
                "filtros_bloqueados": {},
                "graficos_visibles": ["kpi"],
                "indicadores_visibles": ["aforo"],
                "permitir_exportacion": True,
                "permitir_ia": False,
            },
        )
        assert resp_rep.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_cache_en_memoria_poda_key_tags_al_evictar_por_maxsize():
    async def _run():
        cache = CacheEnMemoria(maxsize=4, default_ttl=TTL_HISTORICOS)
        for idx in range(150):
            await cache.set(f"clave_{idx}", {"i": idx}, ttl=TTL_HISTORICOS, tags=["espacio:1"])
        assert len(cache._key_tags) <= 50

    asyncio.run(_run())


def test_limpiar_ingesta_huerfanos_borra_pii_y_export_raw_csv_streaming(tmp_path):
    async def _run():
        archivo_huerfano = tmp_path / "job123_datos_sensibles.xlsx"
        archivo_activo = tmp_path / "otro_archivo.xlsx"
        archivo_huerfano.write_bytes(b"rut;nombre\n1-9;Test")
        archivo_activo.write_bytes(b"ok")

        job = IngestionJob(job_id="job123", tipo="asistencia", filename="datos.xlsx", file_hash="h", estado="processing")
        fake_res = MagicMock()
        fake_res.scalars.return_value.all.return_value = [job]

        fake_session = AsyncMock()
        fake_session.execute = AsyncMock(return_value=fake_res)
        fake_session.commit = AsyncMock()

        class _SessionCtx:
            async def __aenter__(self):
                return fake_session

            async def __aexit__(self, *args):
                return False

        with (
            patch.object(ingestion_service, "AsyncSessionLocal", return_value=_SessionCtx()),
            patch("app.core.config.settings.DIRECTORIO_INGESTA", str(tmp_path)),
        ):
            total = await ingestion_service.limpiar_trabajos_ingesta_huerfanos()

        assert total == 1
        assert job.estado == "failed"
        assert not archivo_huerfano.exists()
        assert archivo_activo.exists()

    asyncio.run(_run())

    async def _stream_bib(**kwargs):
        if kwargs.get("conteo_ref") is not None:
            kwargs["conteo_ref"][0] = 2
        yield "time,usuario_hash\r\n"
        yield "2026-10-10T10:00:00Z,abc123\r\n"

    async def _stream_veh(**kwargs):
        if kwargs.get("conteo_ref") is not None:
            kwargs["conteo_ref"][0] = 1
        yield "time,camara\r\n"
        yield "2026-10-10T10:00:00Z,CSF11\r\n"

    admin_user = _crear_usuario("admin@uct.cl", ["Admin_Sistema"])
    try:
        app.dependency_overrides[get_current_user] = lambda: admin_user
        client = TestClient(app)
        with (
            patch.object(AttendanceService, "stream_raw_csv", side_effect=_stream_bib),
            patch.object(VehicleService, "stream_raw_csv", side_effect=_stream_veh),
            patch("app.services.audit_service.record_download_audit", new=AsyncMock()),
        ):
            r_bib = client.get("/api/v1/attendance/export-raw-csv?espacio_id=1")
            assert r_bib.status_code == 200
            assert r_bib.headers["content-type"].startswith("text/csv")
            assert "abc123" in r_bib.text

            r_veh = client.get("/api/v1/vehicles/export-raw-csv?espacio_id=2")
            assert r_veh.status_code == 200
            assert r_veh.headers["content-type"].startswith("text/csv")
            assert "CSF11" in r_veh.text
    finally:
        app.dependency_overrides.clear()

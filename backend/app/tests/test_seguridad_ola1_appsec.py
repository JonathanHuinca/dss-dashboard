"""
Pruebas de seguridad críticas (Ola 1 AppSec / RBAC / RLS):
- Prevención de inyección SQL en VehicleService (parámetro sector).
- Protección de Reportes Compartidos (sin fuga de tokens/datos sin JWT y RBAC en gestión).
- Prevención de envenenamiento global de settings.FRONTEND_URL por Origin/Host.
- Aislamiento RLS estricto en Chat IA (Tool Calling y grafico_contexto).
- Matriz RBAC/RLS en auth, attendance, config, ingestion, predictions, metrics y assistant.
- Escape HTML en correos SMTP y escape XML en exportación PDF.
"""
import asyncio
import json
import uuid
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.config import obtener_url_frontend, settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.domain.auth_models import Rol, Usuario
from app.main import app
from app.schemas.chat_schemas import ExportPdfRequest
from app.services.chat.ejecutor_herramientas import (
    _ejecutar_consulta_tool_interno,
    _resolver_datos_grafico_contexto_interno,
)
from app.services.chat.exportacion_pdf import generar_pdf_conversacion
from app.services.email_service import enviar_correo_reporte_ejecutivo
from app.services.llm_client import _normalizar_resultado_tool_call
from app.services.servicio_reportes_compartidos import ServicioReportesCompartidos
from app.services.vehicle_service import VehicleService, _validar_sectores_vehiculares


def _crear_usuario(
    uid: int,
    email: str,
    rol_nombre: str,
    *,
    espacio_id=None,
    allowed_datasets=None,
    can_ingest: bool = False,
    can_use_ai: bool = True,
    can_export: bool = False,
) -> Usuario:
    u = Usuario(
        id=uid,
        email=email,
        nombre_completo=f"Usuario {rol_nombre}",
        hashed_password="$2b$12$hashedpassworddummyvalue000000000000000000000000000",
        is_active=True,
        espacio_id=espacio_id,
        allowed_datasets=allowed_datasets,
        can_ingest=can_ingest,
        can_use_ai=can_use_ai,
        can_export=can_export,
    )
    u.roles = [Rol(id=uid, nombre=rol_nombre)]
    return u


class _FakeResult:
    def __init__(self, obj=None, items=None, scalar_val=None):
        self._obj = obj
        self._items = items if items is not None else []
        self._scalar = scalar_val

    def scalar_one_or_none(self):
        return self._obj

    def scalar(self):
        return self._scalar if self._scalar is not None else self._obj

    def fetchall(self):
        return self._items

    def one(self):
        return self._obj

    def scalars(self):
        items = self._items
        return SimpleNamespace(all=lambda: items)


def test_sqli_sector_rechazado_y_parametrizado_en_vehicle_service():
    """Valida que payloads SQLi en sector sean rechazados con 400 y que sectores válidos usen bind parameters."""
    payloads_maliciosos = [
        "CSF11' OR '1'='1",
        "CSF11; DROP TABLE usuarios;--",
        "CSF11') UNION SELECT email FROM usuarios--",
        "SECTOR_INEXISTENTE",
    ]
    for malo in payloads_maliciosos:
        with pytest.raises(HTTPException) as exc_info:
            _validar_sectores_vehiculares(malo)
        assert exc_info.value.status_code == 400

    assert _validar_sectores_vehiculares("csf11, csf21") == ["CSF11", "CSF21"]
    assert _validar_sectores_vehiculares("todos") == []

    async def _run():
        consultas_capturadas = []

        async def _fake_execute(stmt, params=None):
            consultas_capturadas.append((str(stmt), params or {}))
            return _FakeResult(items=[], scalar_val=0)

        db_fake = AsyncMock()
        db_fake.execute = AsyncMock(side_effect=_fake_execute)

        # Intento SQLi en los 4 métodos críticos debe fallar con 400 antes de ejecutar SQL
        with pytest.raises(HTTPException) as e1:
            await VehicleService.get_fleet_composition(db_fake, espacio_id=2, sector="CSF11' OR '1'='1")
        assert e1.value.status_code == 400

        with pytest.raises(HTTPException) as e2:
            await VehicleService.get_daily_evolution(db_fake, espacio_id=2, sector="CSF11; SELECT 1")
        assert e2.value.status_code == 400

        with pytest.raises(HTTPException) as e3:
            await VehicleService.get_parking_occupancy(db_fake, espacio_id=2, sector="CSF11' UNION SELECT 1--")
        assert e3.value.status_code == 400

        with pytest.raises(HTTPException) as e4:
            await VehicleService.get_hourly_flow(
                db_fake,
                espacio_id=2,
                fecha_inicio=date(2026, 10, 1),
                fecha_fin=date(2026, 10, 10),
                sector="CSF11' OR 1=1--",
            )
        assert e4.value.status_code == 400

        # Sector válido debe ejecutarse con parámetro enlazado y nunca interpolado literalmente
        consultas_capturadas.clear()
        await VehicleService.get_fleet_composition(db_fake, espacio_id=2, sector="CSF11,CSF21")
        sqls_con_camara = [(s, p) for s, p in consultas_capturadas if "eventos_vehiculares" in s]
        assert len(sqls_con_camara) == 2
        for sql_txt, params in sqls_con_camara:
            assert "'%CSF11%'" not in sql_txt
            assert ":flota_sec_0" in sql_txt
            assert params.get("flota_sec_0") == "%CSF11%"
            assert params.get("flota_sec_1") == "%CSF21%"

        consultas_capturadas.clear()
        await VehicleService.get_daily_evolution(db_fake, espacio_id=2, sector="CHS01")
        sqls_evol = [(s, p) for s, p in consultas_capturadas if "vehiculos_diario_estacionamiento" in s]
        assert len(sqls_evol) == 1
        assert "'%CHS01%'" not in sqls_evol[0][0]
        assert ":evol_sec_0" in sqls_evol[0][0]
        assert sqls_evol[0][1].get("evol_sec_0") == "%CHS01%"

    asyncio.run(_run())


def test_reportes_compartidos_sin_jwt_no_filtra_tokens_ni_datos_y_bloquea_acciones():
    """Sin JWT, /publico/{token} entrega solo metadatos mínimos y los demás endpoints exigen autenticación."""
    dest = SimpleNamespace(
        id=5,
        email="consultor@uct.cl",
        nombre_completo="Consultor UCT",
        cargo="Director",
        unidad_academica="Ingeniería",
        token_portal="tok_portal_secreto_123",
        activo=True,
        reportes=[],
    )
    reporte_fake = SimpleNamespace(
        id=uuid.uuid4(),
        codigo_corto="RPT-2026-SEC1",
        token_acceso="tok_acceso_seguro_1",
        espacio_id=1,
        destinatario_id=5,
        destinatario=dest,
        creado_por_id=10,
        creador=_crear_usuario(10, "director@uct.cl", "Director_Recinto", espacio_id=1, allowed_datasets=["biblioteca"]),
        titulo_reporte="Informe Ejecutivo Confidencial",
        finalidad_reporte="Comité Directivo",
        nota_general="Nota privada confidencial",
        notas_items_json='[{"id":"n1","contenido":"Dato sensible"}]',
        fecha_inicio=date(2026, 10, 1),
        fecha_fin=date(2026, 10, 15),
        modo_datos="instantanea_fija",
        filtros_bloqueados_json="{}",
        graficos_visibles_json='["aforo_curva"]',
        indicadores_visibles_json='["dias_operativos"]',
        datos_instantanea_json=json.dumps({
            "kpis_base": {"total": 999},
            "indicadores_ejecutivos": {"dias_operativos": 12},
            "indicadores_visibles": ["dias_operativos"],
            "graficos_visibles": ["aforo_curva"],
            "graficos": {"aforo_curva": [{"x": 1}]},
        }),
        permitir_exportacion=True,
        permitir_ia=True,
        activo=True,
        expira_en=None,
        total_accesos=0,
        ultimo_acceso_en=None,
        creado_en=datetime(2026, 10, 16, 10, 0, 0),
    )

    async def _run_unit():
        db_anon = AsyncMock()
        db_anon.execute = AsyncMock(return_value=_FakeResult(obj=reporte_fake))

        # 1. Sin usuario autenticado: solo metadatos públicos mínimos
        resp_anon = await ServicioReportesCompartidos.obtener_reporte_publico_por_token(
            session=db_anon,
            token_acceso="tok_acceso_seguro_1",
            usuario_actual=None,
        )
        assert resp_anon["requiere_login"] is True
        assert resp_anon["datos"] is None
        assert resp_anon["historial_destinatario"] == []
        assert "token_activacion" not in resp_anon
        assert "token_portal" not in json.dumps(resp_anon)
        assert "Nota privada confidencial" not in json.dumps(resp_anon)
        assert resp_anon["reporte"]["codigo_corto"] == "RPT-2026-SEC1"

        # 2. Usuario autenticado ajeno -> 403
        otro_consultor = _crear_usuario(99, "ajeno@uct.cl", "Consultor_Reporte")
        db_ajeno = AsyncMock()
        db_ajeno.execute = AsyncMock(return_value=_FakeResult(obj=reporte_fake))
        with pytest.raises(HTTPException) as exc_403:
            await ServicioReportesCompartidos.obtener_reporte_publico_por_token(
                session=db_ajeno,
                token_acceso="tok_acceso_seguro_1",
                usuario_actual=otro_consultor,
            )
        assert exc_403.value.status_code == 403

        # 3. Destinatario titular autenticado -> acceso permitido sin filtrar token_activacion ni token_portal
        titular = _crear_usuario(55, "consultor@uct.cl", "Consultor_Reporte", can_use_ai=False)
        db_titular = AsyncMock()
        db_titular.execute = AsyncMock(
            side_effect=[_FakeResult(obj=reporte_fake), _FakeResult(obj=None), _FakeResult(obj=titular)]
        )
        db_titular.add = MagicMock()
        db_titular.commit = AsyncMock()
        with patch(
            "app.services.servicio_reportes_compartidos.CATALOGO_INDICADORES_BIBLIOTECA",
            [{"id": "dias_operativos"}],
        ):
            resp_ok = await ServicioReportesCompartidos.obtener_reporte_publico_por_token(
                session=db_titular,
                token_acceso="tok_acceso_seguro_1",
                usuario_actual=titular,
            )
        assert resp_ok["requiere_login"] is False
        assert resp_ok["datos"] is not None
        assert "token_activacion" not in resp_ok
        assert resp_ok["reporte"]["destinatario"]["token_portal"] == ""
        assert resp_ok["historial_destinatario"] == []

    asyncio.run(_run_unit())

    # 4. Endpoints HTTP públicos sin token JWT deben rechazar 401/403
    db_http = AsyncMock()
    try:
        app.dependency_overrides[get_db] = lambda: db_http
        client = TestClient(app)
        assert client.get("/api/v1/reportes-compartidos/portal/tok_portal_secreto_123").status_code in (401, 403)
        assert client.post(
            "/api/v1/reportes-compartidos/publico/tok_acceso_seguro_1/consultar-ia",
            json={"pregunta": "Resumen"},
        ).status_code in (401, 403)
        assert client.get("/api/v1/reportes-compartidos/publico/tok_acceso_seguro_1/ia/historial").status_code in (401, 403)
        assert client.post(
            "/api/v1/reportes-compartidos/publico/tok_acceso_seguro_1/evento",
            json={"accion": "descarga_pdf"},
        ).status_code in (401, 403)
    finally:
        app.dependency_overrides.clear()


def test_rbac_gestion_reportes_compartidos_bloquea_analista_y_borrado_destinatario():
    """Analista_Consulta no puede enumerar candidatos, vincular roles ni modificar/borrar destinatarios."""
    analista = _crear_usuario(20, "analista@uct.cl", "Analista_Consulta", allowed_datasets=["biblioteca"])
    director = _crear_usuario(21, "dir.bib@uct.cl", "Director_Recinto", espacio_id=1, allowed_datasets=["biblioteca"])
    db_fake = AsyncMock()

    try:
        app.dependency_overrides[get_db] = lambda: db_fake
        app.dependency_overrides[get_current_user] = lambda: analista
        client = TestClient(app)

        assert client.get("/api/v1/reportes-compartidos/usuarios-candidatos").status_code == 403
        assert client.post(
            "/api/v1/reportes-compartidos/vincular-usuario-existente",
            json={"usuario_id": 1, "cargo": "Admin", "unidad_academica": "TI"},
        ).status_code == 403
        assert client.patch(
            "/api/v1/reportes-compartidos/destinatarios/5",
            json={"activo": False},
        ).status_code == 403
        assert client.delete("/api/v1/reportes-compartidos/destinatarios/5").status_code == 403

        # Director_Recinto tampoco puede eliminar destinatarios/cuentas Usuario
        app.dependency_overrides[get_current_user] = lambda: director
        assert client.delete("/api/v1/reportes-compartidos/destinatarios/5").status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_middleware_frontend_url_no_muta_settings_ni_acepta_origen_malicioso():
    """Origin/Referer/X-Forwarded-Host no autorizados no alteran settings.FRONTEND_URL."""
    url_original = settings.FRONTEND_URL
    client = TestClient(app)

    resp = client.get(
        "/health",
        headers={
            "Origin": "https://phishing-uct.evil.example",
            "X-Forwarded-Host": "phishing-uct.evil.example",
        },
    )
    assert resp.status_code == 200
    assert settings.FRONTEND_URL == url_original
    assert "evil.example" not in obtener_url_frontend()

    # Incluso con origen institucional válido, settings.FRONTEND_URL permanece inmutable
    resp_ok = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert resp_ok.status_code == 200
    assert settings.FRONTEND_URL == url_original


def test_chat_ia_bloquea_bypass_rls_en_tool_calling_y_grafico_contexto():
    """Valida que el LLM no pueda forzar otro espacio_id y que grafico_contexto/tools usen lista blanca estricta."""
    # 1. _normalizar_resultado_tool_call sobrescribe espacio_id del LLM
    norm = _normalizar_resultado_tool_call(
        tool_name="consultar_kpis_actuales",
        raw_args={"espacio_id": 2},
        espacio_id=1,
        fecha_inicio=None,
        fecha_fin=None,
        match_anio_usuario=None,
        anio_objetivo=2026,
    )
    assert norm["args"]["espacio_id"] == 1

    async def _run():
        db_fake = AsyncMock()
        db_fake.execute = AsyncMock(return_value=_FakeResult(items=[]))

        with (
            patch(
                "app.services.chat.ejecutor_herramientas.obtener_anio_activo_espacio",
                new=AsyncMock(return_value=2026),
            ),
            patch(
                "app.services.chat.ejecutor_herramientas.obtener_contexto_calendario_rango",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.services.chat.ejecutor_herramientas.obtener_resumen_hechos_institucionales",
                new=AsyncMock(return_value=""),
            ),
            patch(
                "app.services.chat.ejecutor_herramientas._construir_alerta_operativa_biblioteca",
                new=AsyncMock(return_value=""),
            ),
        ):
            # 2. Tool calling: usuario de Biblioteca (espacio_id=1) con args maliciosos espacio_id=2
            comp, payload, msg, _, _ = await _ejecutar_consulta_tool_interno(
                "consultar_flota_vehicular", {"espacio_id": 2}, db_fake, espacio_id=1
            )
            assert comp is None and payload is None
            assert "Acceso denegado" in msg

            # 3. Usuario de Estacionamiento (espacio_id=2) intentando consultar_campana_24h o flujo nocturno
            for tool_bib in ("consultar_campana_24h", "consultar_flujo_nocturno", "tool_inventada"):
                c2, p2, m2, _, _ = await _ejecutar_consulta_tool_interno(
                    tool_bib, {"espacio_id": 1}, db_fake, espacio_id=2
                )
                assert c2 is None and p2 is None
                assert "Acceso denegado" in m2

            # 4. grafico_contexto: biblioteca (espacio_id=1) intentando slugs vehiculares
            for slug_veh in ("top_marcas", "fleet_composition", "camaras", "intercampus", "clusters", "conductuales"):
                cg, pg, mg, _, _ = await _resolver_datos_grafico_contexto_interno(
                    slug_veh, espacio_id=1, fecha_inicio=None, fecha_fin=None, db=db_fake
                )
                assert cg is None and pg is None
                assert "Estacionamiento" in mg or "Acceso denegado" in mg

            # 5. grafico_contexto: estacionamiento (espacio_id=2) intentando slugs de biblioteca
            for slug_bib in ("curricular", "doors_usage", "visit_profiles", "nocturno", "pecera_24h", "prophet_presencia"):
                cg, pg, mg, _, _ = await _resolver_datos_grafico_contexto_interno(
                    slug_bib, espacio_id=2, fecha_inicio=None, fecha_fin=None, db=db_fake
                )
                assert cg is None and pg is None
                assert "Biblioteca" in mg or "Acceso denegado" in mg

            # 6. grafico_contexto: "aforo_presencia_vehic" desde espacio_id=1 NO debe invocar VehicleService
            with (
                patch.object(VehicleService, "get_realtime_presence_curve", new=AsyncMock()) as mock_veh_curve,
                patch(
                    "app.services.chat.ejecutor_herramientas.AttendanceService.get_realtime_presence_curve",
                    new=AsyncMock(return_value=[]),
                ) as mock_bib_curve,
            ):
                await _resolver_datos_grafico_contexto_interno(
                    "aforo_presencia_vehic", espacio_id=1, fecha_inicio=None, fecha_fin=None, db=db_fake
                )
                mock_veh_curve.assert_not_awaited()
                mock_bib_curve.assert_awaited_once()

            # 7. Slug desconocido fuera de lista blanca debe ser denegado
            cu, pu, mu, _, _ = await _resolver_datos_grafico_contexto_interno(
                "grafico_no_autorizado_xyz", espacio_id=1, fecha_inicio=None, fecha_fin=None, db=db_fake
            )
            assert cu is None and pu is None
            assert "Acceso denegado" in mu

    asyncio.run(_run())


def test_matriz_rbac_y_rls_en_endpoints_corregidos():
    """Verifica el control de acceso RBAC y aislamiento cross-recinto en todos los endpoints corregidos."""
    analista_bib = _crear_usuario(
        30, "analista.bib@uct.cl", "Analista_Consulta", allowed_datasets=["biblioteca"], can_ingest=False
    )
    director_bib = _crear_usuario(
        31, "dir.bib@uct.cl", "Director_Recinto", espacio_id=1, allowed_datasets=["biblioteca"], can_ingest=True
    )
    consultor = _crear_usuario(32, "cons@uct.cl", "Consultor_Reporte", can_ingest=False)
    guardia = _crear_usuario(
        33, "guardia@uct.cl", "Guardia_Seguridad", espacio_id=1, allowed_datasets=["biblioteca"], can_ingest=False
    )

    db_fake = AsyncMock()
    horario_est = SimpleNamespace(id=77, espacio_id=2)
    contingencia_est = SimpleNamespace(id=88, espacio_id=2)
    contingencia_global = SimpleNamespace(id=89, espacio_id=None)
    job_est = SimpleNamespace(job_id=uuid.uuid4(), espacio_id=2, creado_por=999, estado="completed", registros_ok=10, registros_error=0, error_detail=None)

    async def _fake_get(model, pk):
        if model.__name__ == "HorarioOperacion" and pk == 77:
            return horario_est
        if model.__name__ == "ContingenciaAcademica" and pk == 88:
            return contingencia_est
        if model.__name__ == "ContingenciaAcademica" and pk == 89:
            return contingencia_global
        if model.__name__ == "IngestionJob":
            return job_est
        return None

    db_fake.get = AsyncMock(side_effect=_fake_get)
    db_fake.execute = AsyncMock(return_value=_FakeResult(obj=SimpleNamespace(ia_asistente_activo=True)))

    try:
        app.dependency_overrides[get_db] = lambda: db_fake
        client = TestClient(app)

        # 1. /auth/seed-roles bloqueado sin auth y para no-Admin
        assert client.post("/api/v1/auth/seed-roles").status_code in (401, 403)
        app.dependency_overrides[get_current_user] = lambda: director_bib
        assert client.post("/api/v1/auth/seed-roles").status_code == 403

        # 2. /attendance/salas bloqueado para Analista_Consulta y Guardia_Seguridad
        for usr_no_dir in (analista_bib, guardia):
            app.dependency_overrides[get_current_user] = lambda u=usr_no_dir: u
            assert client.post(
                "/api/v1/attendance/salas",
                json={"codigo": "SALA_X", "nombre": "Sala X", "edificio": "CSF02", "espacio_id": 1, "capacidad_asientos": 20},
            ).status_code == 403
            assert client.put(
                "/api/v1/attendance/salas/1/capacidad",
                json={"capacidad_asientos": 100},
            ).status_code == 403

        # 3. /config/horarios, /contingencias y /calendar/* cross-recinto bloqueados para Director Biblioteca
        app.dependency_overrides[get_current_user] = lambda: director_bib
        assert client.post(
            "/api/v1/config/horarios",
            json={
                "espacio_id": 2,
                "anio": 2026,
                "descripcion": "Horario Estacionamiento",
                "tipo_horario": "regular",
                "hora_apertura": "08:00",
                "hora_cierre": "20:00",
            },
        ).status_code == 403
        assert client.put(
            "/api/v1/config/horarios/77",
            json={"hora_cierre": "21:00"},
        ).status_code == 403
        assert client.delete("/api/v1/config/horarios/77").status_code == 403

        assert client.post(
            "/api/v1/config/contingencias",
            json={"fecha_inicio": "2026-10-10", "fecha_fin": "2026-10-11", "tipo": "paro_federado", "titulo": "Test", "espacio_id": 2},
        ).status_code == 403
        assert client.post(
            "/api/v1/config/contingencias",
            json={"fecha_inicio": "2026-10-10", "fecha_fin": "2026-10-11", "tipo": "paro_federado", "titulo": "Global", "espacio_id": None},
        ).status_code == 403
        assert client.delete("/api/v1/config/contingencias/88").status_code == 403
        assert client.delete("/api/v1/config/contingencias/89").status_code == 403

        assert client.post("/api/v1/config/calendar/depurar").status_code == 403
        assert client.post("/api/v1/config/calendar/sync-scrape").status_code == 403
        assert client.delete("/api/v1/config/calendar/events/2026-10-10").status_code == 403

        # 4. /ingestion/{job_id}/status y /history con RBAC y RLS
        assert client.get(f"/api/v1/ingestion/{job_est.job_id}/status").status_code == 403
        app.dependency_overrides[get_current_user] = lambda: guardia
        assert client.get("/api/v1/ingestion/history").status_code == 403
        assert client.get(f"/api/v1/ingestion/{job_est.job_id}/status").status_code == 403

        # 5. /predictions/alerts filtra por recinto y bloquea Consultor_Reporte
        app.dependency_overrides[get_current_user] = lambda: consultor
        assert client.get("/api/v1/predictions/alerts").status_code == 403
        assert client.get("/api/v1/metrics/date-bounds").status_code == 403

        app.dependency_overrides[get_current_user] = lambda: director_bib
        with patch(
            "app.api.v1.endpoints.predictions.get_active_alerts",
            new=AsyncMock(return_value={
                "total_alertas": 2,
                "alertas": [
                    {"recinto": "biblioteca", "nivel": "preventivo", "mensaje": "Bib"},
                    {"recinto": "vehicular", "nivel": "critico", "mensaje": "Est"},
                ],
            }),
        ):
            resp_al = client.get("/api/v1/predictions/alerts")
            assert resp_al.status_code == 200
            body_al = resp_al.json()
            assert body_al["total_alertas"] == 1
            assert body_al["alertas"][0]["recinto"] == "biblioteca"

        # 6. /metrics/date-bounds sin espacio_id acota automáticamente a recinto 1 para Director Biblioteca
        with patch(
            "app.api.v1.endpoints.metrics.MetricsService.get_date_bounds",
            new=AsyncMock(return_value={
                "fecha_min": "2026-03-01",
                "fecha_max": "2026-10-31",
                "espacio_id": 1,
                "meses_disponibles": [
                    {"label": "Octubre 2026", "inicio": "2026-10-01", "fin": "2026-10-31", "year": 2026, "month": 10}
                ],
            }),
        ) as mock_bounds:
            resp_b = client.get("/api/v1/metrics/date-bounds")
            assert resp_b.status_code == 200
            assert mock_bounds.await_args.kwargs["espacio_id"] == 1

        # 7. /assistant/query y /assistant/chat legacy bloqueados con 410 Gone
        assert client.post("/api/v1/assistant/query", json={"message": "hola"}).status_code == 410
        assert client.post("/api/v1/assistant/chat", json={"message": "hola"}).status_code == 410
    finally:
        app.dependency_overrides.clear()


def test_escape_html_en_correos_y_escape_xml_en_exportacion_pdf():
    """Verifica neutralización de HTML en email_service y XML seguro + IDs nulos en exportacion_pdf."""
    async def _run():
        capturado = {}

        async def _fake_despacho(destinatario, asunto, cuerpo_html, cuerpo_texto=None):
            capturado["html"] = cuerpo_html
            return True

        with patch("app.services.email_service.enviar_correo_despacho", side_effect=_fake_despacho):
            ok = await enviar_correo_reporte_ejecutivo(
                destinatario="user@uct.cl",
                nombre_destinatario='<b>Admin</b><script>alert(1)</script>',
                cargo="Jefe <TI>",
                unidad_academica="Facultad & Gestión",
                titulo_reporte='Reporte <img src=x onerror=alert(1)>',
                codigo_corto="RPT-01",
                espacio_nombre="Biblioteca CSF",
                periodo_texto="2026-10-01 a 2026-10-10",
                finalidad_reporte="Evaluación <script>",
                nota_general="Revisar <script>evil()</script> & validar",
                enlace_reporte="https://indicadoreshikcentral.dev.uct.cl/reporte/abc",
                enlace_portal="https://indicadoreshikcentral.dev.uct.cl/portal/xyz",
            )
            assert ok is True
            assert "<script>" not in capturado["html"]
            assert "<img src=x" not in capturado["html"]
            assert "&lt;script&gt;alert(1)&lt;/script&gt;" in capturado["html"]

        req_pdf = ExportPdfRequest(
            conversacion_id=None,
            session_id="sesion-seguridad-1",
            espacio_id=1,
            titulo="Informe <Visitas Cortas (<60m)> & Análisis",
            consulta_texto="¿Qué pasó con <script> & 1 < 2?",
            respuesta_texto="Visitas Cortas (<60m) & Estándar (>60m)\nLínea 2",
            datos_tabla=[{"perfil_<tipo>": "Cortas (<60m) & rápidas", "total": 12}],
        )
        pdf_resp = await generar_pdf_conversacion(db=AsyncMock(), req=req_pdf, usuario_id=1)
        assert pdf_resp.media_type == "application/pdf"
        assert pdf_resp.body.startswith(b"%PDF-")
        assert "informe_ejecutivo_sesion-s.pdf" in pdf_resp.headers["Content-Disposition"]

        req_pdf_sin_id = SimpleNamespace(
            conversacion_id=None,
            session_id=None,
            espacio_id=1,
            titulo="Informe <Sin ID>",
            consulta_texto="Consulta <60m>",
            respuesta_texto="Respuesta <60m> & ok",
            datos_tabla=None,
            graficos_b64=None,
        )
        pdf_resp_sin_id = await generar_pdf_conversacion(db=AsyncMock(), req=req_pdf_sin_id, usuario_id=1)
        assert pdf_resp_sin_id.body.startswith(b"%PDF-")
        assert "informe_ejecutivo_consulta.pdf" in pdf_resp_sin_id.headers["Content-Disposition"]

    asyncio.run(_run())

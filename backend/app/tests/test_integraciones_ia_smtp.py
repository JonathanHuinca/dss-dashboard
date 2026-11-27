"""Pruebas automatizadas para integraciones Multi-Proveedor IA, SMTP dinámico y seguridad anti-SSRF."""
import asyncio
import json
import os
import sys
from datetime import datetime
from types import SimpleNamespace
from typing import Any, List, Optional
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.security_cipher import decrypt_api_key, encrypt_api_key, mask_api_key
from app.core.validacion_red import (
    sanitizar_error_credencial,
    validar_host_smtp,
    validar_url_proveedor_ia,
)
from app.domain.auth_models import Rol, Usuario
from app.domain.config_models import ConfiguracionEspacios, ConfiguracionSMTP, CredencialProveedorIA
from app.main import app
from app.services.llm_client import (
    ClaudeClient,
    OpenAICompatibleClient,
    get_gemini_tools,
    obtener_esquema_herramientas_neutral,
    obtener_herramientas_claude,
    obtener_herramientas_openai,
)


def _crear_usuario(email: str, rol_nombre: str) -> Usuario:
    u = Usuario(
        id=999,
        email=email,
        nombre_completo=f"Usuario {rol_nombre}",
        hashed_password="hash",
        is_active=True,
        espacio_id=1,
        allowed_datasets=["biblioteca", "estacionamiento"],
    )
    u.roles = [Rol(id=1, nombre=rol_nombre)]
    return u


def test_validacion_anti_ssrf_proveedores_ia():
    assert validar_url_proveedor_ia("https://api.openai.com/v1/") == "https://api.openai.com/v1"
    assert (
        validar_url_proveedor_ia("http://host.docker.internal:11434/v1", permitir_local=True)
        == "http://host.docker.internal:11434/v1"
    )

    for url_invalida in [
        "http://169.254.169.254/latest/meta-data",
        "https://169.254.169.254/v1",
        "http://api.openai.com/v1",
        "https://localhost:8000/v1",
        "https://127.0.0.1:8000/v1",
        "https://10.0.0.15/v1",
        "https://user:pass@api.openai.com/v1",
    ]:
        with pytest.raises(ValueError):
            validar_url_proveedor_ia(url_invalida, permitir_local=False)

    # Incluso con permitir_local=True, metadatos cloud deben permanecer bloqueados
    with pytest.raises(ValueError):
        validar_url_proveedor_ia("http://169.254.169.254/latest", permitir_local=True)


def test_validacion_anti_ssrf_smtp():
    assert validar_host_smtp("smtp.uct.cl", 587) == ("smtp.uct.cl", 587)
    assert validar_host_smtp("10.20.15.40", 587) == ("10.20.15.40", 587)

    for host, port in [
        ("localhost", 587),
        ("127.0.0.1", 587),
        ("169.254.169.254", 587),
        ("db", 587),
        ("http://smtp.uct.cl", 587),
        ("smtp.uct.cl", 80),
    ]:
        with pytest.raises(ValueError):
            validar_host_smtp(host, port)


def test_sanitizacion_secretos_en_errores():
    secreto = "sk-proj-supersecreto12345"
    err = Exception(f"401 Unauthorized con Authorization: Bearer {secreto} y clave AIzaSyABC123456")
    limpio = sanitizar_error_credencial(err, secreto)
    assert secreto not in limpio
    assert "AIzaSyABC123456" not in limpio
    assert "[REDACTED]" in limpio


def test_traduccion_herramientas_agnosica_espacios():
    for espacio_id in (1, 2):
        neutral = obtener_esquema_herramientas_neutral(espacio_id)
        openai_tools = obtener_herramientas_openai(espacio_id)
        claude_tools = obtener_herramientas_claude(espacio_id)
        gemini_tools = get_gemini_tools(espacio_id)

        nombres_neutral = [t["name"] for t in neutral]
        assert [t["function"]["name"] for t in openai_tools] == nombres_neutral
        assert [t["name"] for t in claude_tools] == nombres_neutral
        assert [fd.name for fd in gemini_tools[0].function_declarations] == nombres_neutral

        if espacio_id == 1:
            assert "consultar_campana_24h" in nombres_neutral
            assert "consultar_flota_vehicular" not in nombres_neutral
        else:
            assert "consultar_flota_vehicular" in nombres_neutral
            assert "consultar_campana_24h" not in nombres_neutral


def test_openai_compatible_client_tool_call_y_stream():
    async def _run():
        cliente = OpenAICompatibleClient(
            api_key="sk-test-openai-9999",
            default_model="gpt-4o-mini",
            base_url="https://api.openai.com/v1",
            provider_id="openai",
        )

        # 1. Prueba tool_call
        payload_tool = {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "consultar_kpis_actuales",
                                    "arguments": json.dumps({"espacio_id": 1}),
                                }
                            }
                        ],
                    }
                }
            ]
        }
        with patch.object(cliente, "_post_completions", return_value=payload_tool):
            res_tool = await cliente.analyze_query_with_tools("Cuál es el aforo actual?", espacio_id=1)
        assert res_tool["type"] == "tool_call"
        assert res_tool["tool_name"] == "consultar_kpis_actuales"
        assert res_tool["args"]["espacio_id"] == 1

        # 2. Prueba respuesta textual
        payload_text = {"choices": [{"message": {"content": "Hola desde OpenAI."}}]}
        with patch.object(cliente, "_post_completions", return_value=payload_text):
            res_text = await cliente.generate_response("Hola")
        assert res_text == "Hola desde OpenAI."

        # 3. Prueba streaming SSE simulado
        class _FakeStreamResp:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            def raise_for_status(self):
                return None

            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"Afluencia "}}]}'
                yield 'data: {"choices":[{"delta":{"content":"estable."}}]}'
                yield "data: [DONE]"

        class _FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            def stream(self, *args, **kwargs):
                return _FakeStreamResp()

        with patch("httpx.AsyncClient", _FakeAsyncClient):
            chunks = [c async for c in cliente.generate_narrative_stream("Resume")]
        assert "".join(chunks) == "Afluencia estable."

    asyncio.run(_run())


def test_claude_client_tool_use_y_stream():
    async def _run():
        cliente = ClaudeClient(
            api_key="sk-ant-test-9999",
            default_model="claude-sonnet-4-20250514",
        )
        payload_tool = {
            "content": [
                {
                    "type": "tool_use",
                    "name": "consultar_calendario_academico",
                    "input": {"espacio_id": 1, "busqueda": "examen"},
                }
            ]
        }
        with patch.object(cliente, "_post_messages", return_value=payload_tool):
            res = await cliente.analyze_query_with_tools("Cuándo hay exámenes?", espacio_id=1)
        assert res["type"] == "tool_call"
        assert res["tool_name"] == "consultar_calendario_academico"
        assert res["args"]["busqueda"] == "examen"

        class _FakeClaudeStream:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            def raise_for_status(self):
                return None

            async def aiter_lines(self):
                yield 'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Resumen "}}'
                yield 'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Claude."}}'

        class _FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            def stream(self, *args, **kwargs):
                return _FakeClaudeStream()

        with patch("httpx.AsyncClient", _FakeAsyncClient):
            chunks = [c async for c in cliente.generate_narrative_stream("Resume")]
        assert "".join(chunks) == "Resumen Claude."

    asyncio.run(_run())


def test_rbac_rechaza_roles_no_admin_en_config_ia_y_smtp():
    async def _fake_db():
        yield SimpleNamespace()

    try:
        for rol in ("Director_Recinto", "Analista_Consulta"):
            usuario = _crear_usuario(f"{rol.lower()}@uct.cl", rol)
            app.dependency_overrides[get_current_user] = lambda u=usuario: u
            app.dependency_overrides[get_db] = _fake_db
            client = TestClient(app)

            for ruta in ("/api/v1/config/llm/catalog", "/api/v1/config/llm/credentials", "/api/v1/config/smtp"):
                r = client.get(ruta)
                assert r.status_code == 403, f"Rol {rol} debió recibir 403 en {ruta}"
    finally:
        app.dependency_overrides.clear()


def test_ciclo_seguro_credenciales_y_hard_delete():
    almacen_ia: List[CredencialProveedorIA] = []
    almacen_smtp: List[ConfiguracionSMTP] = []
    espacio_cfg = ConfiguracionEspacios(
        id=1,
        espacio_id=1,
        ia_asistente_activo=True,
        active_provider="gemini",
        default_model="gemini-3.1-flash-lite",
    )

    class _FakeResult:
        def __init__(self, items):
            self._items = items

        def scalar_one_or_none(self):
            return self._items[0] if self._items else None

        def scalars(self):
            return SimpleNamespace(all=lambda: list(self._items))

    class _FakeSession:
        def __init__(self):
            self._seq = 1

        def add(self, obj):
            if not getattr(obj, "id", None):
                obj.id = self._seq
                self._seq += 1
            obj.created_at = obj.created_at or datetime.utcnow()
            obj.updated_at = datetime.utcnow()
            if isinstance(obj, CredencialProveedorIA):
                almacen_ia.append(obj)
            elif isinstance(obj, ConfiguracionSMTP):
                almacen_smtp.append(obj)

        async def execute(self, stmt):
            sql_str = str(stmt)
            if "UPDATE" in sql_str and "credenciales_proveedores_ia" in sql_str:
                for c in almacen_ia:
                    c.es_activa = False
                return _FakeResult([])
            if "UPDATE" in sql_str and "configuracion_smtp" in sql_str:
                for s in almacen_smtp:
                    s.es_activa = False
                return _FakeResult([])
            if "credenciales_proveedores_ia" in sql_str:
                if "WHERE credenciales_proveedores_ia.id =" in sql_str:
                    return _FakeResult(almacen_ia[:1])
                return _FakeResult(almacen_ia)
            if "configuracion_smtp" in sql_str:
                if "WHERE configuracion_smtp.id =" in sql_str:
                    return _FakeResult(almacen_smtp[:1])
                return _FakeResult(almacen_smtp)
            if "configuracion_espacios" in sql_str:
                return _FakeResult([espacio_cfg])
            return _FakeResult([])

        async def delete(self, obj):
            if isinstance(obj, CredencialProveedorIA) and obj in almacen_ia:
                almacen_ia.remove(obj)
            elif isinstance(obj, ConfiguracionSMTP) and obj in almacen_smtp:
                almacen_smtp.remove(obj)

        async def commit(self):
            return None

        async def refresh(self, obj):
            obj.updated_at = datetime.utcnow()

    async def _fake_db():
        yield _FakeSession()

    admin = _crear_usuario("admin@uct.cl", "Admin_Sistema")
    secreto_ia = "sk-deepseek-secret-987654"
    secreto_smtp = "smtp-super-secret-5544"

    try:
        app.dependency_overrides[get_current_user] = lambda: admin
        app.dependency_overrides[get_db] = _fake_db
        client = TestClient(app)

        # 1. Crear credencial IA y verificar que no se expone secreto
        r_ia = client.post(
            "/api/v1/config/llm/credentials",
            json={
                "nombre": "DeepSeek Prueba",
                "provider_id": "deepseek",
                "modelo": "deepseek-chat",
                "api_key": secreto_ia,
                "activar": True,
            },
        )
        assert r_ia.status_code == 201, r_ia.text
        assert secreto_ia not in r_ia.text
        body_ia = r_ia.json()
        assert body_ia["key_hint"] == mask_api_key(secreto_ia)
        assert body_ia["es_activa"] is True
        assert decrypt_api_key(almacen_ia[0].encrypted_api_key) == secreto_ia

        # 2. Listar credenciales IA sin exponer clave
        r_list_ia = client.get("/api/v1/config/llm/credentials")
        assert r_list_ia.status_code == 200
        assert secreto_ia not in r_list_ia.text

        # 3. Crear perfil SMTP y verificar que no se expone contraseña
        r_smtp = client.post(
            "/api/v1/config/smtp",
            json={
                "nombre": "SMTP Institucional UCT",
                "host": "smtp.uct.cl",
                "port": 587,
                "use_tls": True,
                "use_ssl": False,
                "username": "dss@uct.cl",
                "from_email": "dss@uct.cl",
                "from_name": "DSS UCT",
                "password": secreto_smtp,
                "activar": True,
            },
        )
        assert r_smtp.status_code == 201, r_smtp.text
        assert secreto_smtp not in r_smtp.text
        assert r_smtp.json()["password_hint"] == mask_api_key(secreto_smtp)
        assert decrypt_api_key(almacen_smtp[0].encrypted_password) == secreto_smtp

        # 4. Hard delete definitivo de ambos registros
        r_del_ia = client.delete(f"/api/v1/config/llm/credentials/{body_ia['id']}")
        assert r_del_ia.status_code == 200
        assert len(almacen_ia) == 0

        r_del_smtp = client.delete(f"/api/v1/config/smtp/{r_smtp.json()['id']}")
        assert r_del_smtp.status_code == 200
        assert len(almacen_smtp) == 0
    finally:
        app.dependency_overrides.clear()


def test_clientes_multi_proveedor_protegen_modelo_por_defecto():
    claude = ClaudeClient(api_key="sk-ant-test", default_model="claude-sonnet-4-20250514")
    assert claude._resolver_modelo("gemini-3.1-flash-lite") == "claude-sonnet-4-20250514"
    assert claude._resolver_modelo("claude-3-7-sonnet-latest") == "claude-3-7-sonnet-latest"

    openai_cli = OpenAICompatibleClient(
        api_key="sk-openai-test",
        default_model="gpt-4o-mini",
        base_url="https://api.openai.com/v1",
        provider_id="openai",
    )
    assert openai_cli._resolver_modelo("gemini-3.1-flash-lite") == "gpt-4o-mini"
    assert openai_cli._resolver_modelo("gpt-4o") == "gpt-4o"

    openrouter_cli = OpenAICompatibleClient(
        api_key="sk-or-test",
        default_model="openai/gpt-4o-mini",
        base_url="https://openrouter.ai/api/v1",
        provider_id="openrouter",
    )
    assert openrouter_cli._resolver_modelo("google/gemini-2.5-flash") == "google/gemini-2.5-flash"


def test_editar_ollama_a_gemini_limpia_base_url_sin_ssrf():
    almacen_ia: List[CredencialProveedorIA] = []

    class _FakeResult:
        def __init__(self, items):
            self._items = items

        def scalar_one_or_none(self):
            return self._items[0] if self._items else None

        def scalars(self):
            return SimpleNamespace(all=lambda: list(self._items))

    class _FakeSession:
        def __init__(self):
            self._seq = 1

        def add(self, obj):
            if not getattr(obj, "id", None):
                obj.id = self._seq
                self._seq += 1
            obj.created_at = obj.created_at or datetime.utcnow()
            obj.updated_at = datetime.utcnow()
            if isinstance(obj, CredencialProveedorIA):
                almacen_ia.append(obj)

        async def execute(self, stmt):
            sql_str = str(stmt)
            if "UPDATE" in sql_str and "credenciales_proveedores_ia" in sql_str:
                for c in almacen_ia:
                    c.es_activa = False
                return _FakeResult([])
            if "credenciales_proveedores_ia" in sql_str:
                if "WHERE credenciales_proveedores_ia.id =" in sql_str:
                    return _FakeResult(almacen_ia[:1])
                return _FakeResult(almacen_ia)
            return _FakeResult([])

        async def commit(self):
            return None

        async def refresh(self, obj):
            obj.updated_at = datetime.utcnow()

    async def _fake_db():
        yield _FakeSession()

    admin = _crear_usuario("admin@uct.cl", "Admin_Sistema")
    nueva_key_gemini = "AIzaSyGeminiActualizada998877"

    try:
        app.dependency_overrides[get_current_user] = lambda: admin
        app.dependency_overrides[get_db] = _fake_db
        client = TestClient(app)

        r_create = client.post(
            "/api/v1/config/llm/credentials",
            json={
                "nombre": "Ollama Local",
                "provider_id": "ollama",
                "modelo": "llama3.2",
                "base_url": "http://host.docker.internal:11434/v1",
                "api_key": "",
                "activar": True,
            },
        )
        assert r_create.status_code == 201, r_create.text
        cred_id = r_create.json()["id"]

        r_edit = client.put(
            f"/api/v1/config/llm/credentials/{cred_id}",
            json={
                "nombre": "Gemini Producción",
                "provider_id": "gemini",
                "modelo": "gemini-2.5-flash",
                "base_url": "",
                "api_key": nueva_key_gemini,
            },
        )
        assert r_edit.status_code == 200, r_edit.text
        assert nueva_key_gemini not in r_edit.text
        body = r_edit.json()
        assert body["provider_id"] == "gemini"
        assert body["modelo"] == "gemini-2.5-flash"
        assert body["base_url"] is None
        assert body["has_api_key"] is True
        assert body["key_hint"] == mask_api_key(nueva_key_gemini)
    finally:
        app.dependency_overrides.clear()


def test_memoria_chat_horarios_24h_dinamicos_y_alerta_en_resumen():
    from datetime import date
    from app.services.chat.fechas_chat import _formatear_horario_24h_dinamico
    from app.services.chat import ejecutor_herramientas as eh
    from app.services.llm_client import _normalizar_historial_conversacion

    # 1. Normalización de historial conserva alternancia estricta user/assistant
    hist_raw = [
        {"role": "assistant", "content": "Saludo inicial"},
        {"role": "user", "content": "P1"},
        {"role": "user", "content": "P1b"},
        {"role": "assistant", "content": "R1"},
        {"role": "user", "content": "P2 sin respuesta"},
    ]
    assert _normalizar_historial_conversacion(hist_raw) == [
        {"role": "user", "content": "P1\nP1b"},
        {"role": "assistant", "content": "R1"},
    ]

    # 2. Envío de history en OpenAICompatibleClient y ClaudeClient
    async def _run_history_clients():
        openai_cli = OpenAICompatibleClient(
            api_key="sk-test-mem",
            default_model="gpt-4o-mini",
            base_url="https://api.openai.com/v1",
            provider_id="openai",
        )
        capturas_openai = []

        async def _fake_openai_post(payload, timeout_seg=None):
            capturas_openai.append(payload)
            return {"choices": [{"message": {"content": "Continuando análisis previo."}}]}

        with patch.object(openai_cli, "_post_completions", side_effect=_fake_openai_post):
            await openai_cli.analyze_query_with_tools(
                "¿Y qué pasó en Sala 2 ese día?",
                espacio_id=1,
                history=[{"role": "user", "content": "Pico del 16/11"}, {"role": "assistant", "content": "Fue 158."}],
            )
        assert [m["role"] for m in capturas_openai[0]["messages"]] == ["system", "user", "assistant", "user"]
        assert capturas_openai[0]["messages"][1]["content"] == "Pico del 16/11"

        claude_cli = ClaudeClient(api_key="sk-ant-mem", default_model="claude-sonnet-4-20250514")
        capturas_claude = []

        async def _fake_claude_post(payload, timeout_seg=None):
            capturas_claude.append(payload)
            return {"content": [{"type": "text", "text": "Respuesta Claude con memoria."}]}

        with patch.object(claude_cli, "_post_messages", side_effect=_fake_claude_post):
            await claude_cli.generate_response(
                "Profundiza lo anterior",
                history=[{"role": "user", "content": "Pregunta 1"}, {"role": "assistant", "content": "Respuesta 1"}],
            )
        assert [m["role"] for m in capturas_claude[0]["messages"]] == ["user", "assistant", "user"]

    asyncio.run(_run_history_clients())

    # 3. Formato dinámico horario 24h lee L-J 07:00, Vie 06:00 y capacidad real 126 (sin 08:30 ni 226)
    hor_mock = SimpleNamespace(
        descripcion="Campaña 24 Horas Noviembre 2026",
        hora_cierre="07:00",
        configuracion_dias=json.dumps({
            "lunes": {"abierto": True, "apertura": "08:30", "cierre": "07:00", "cierre_dia_siguiente": True},
            "viernes": {"abierto": True, "apertura": "08:30", "cierre": "06:00", "cierre_dia_siguiente": True},
            "sabado": {"abierto": True, "apertura": "10:30", "cierre": "15:00", "cierre_dia_siguiente": False},
        }),
    )
    txt_24h = _formatear_horario_24h_dinamico(hor_mock, cap_s2=126)
    assert "07:00" in txt_24h and "06:00" in txt_24h and "126 asientos" in txt_24h
    assert "08:30" not in txt_24h and "226" not in txt_24h

    # 4. Resumen de aforo_presencia_intervalos incluye pico combinado + individual S1/S2 + alerta sin marcajes S2
    curva_mock = [
        {
            "bucket": "2026-11-16T13:00:00",
            "ingresos": 90,
            "salidas": 40,
            "personas_unicas": 158,
            "personas_sala1": 104,
            "personas_sala2": 54,
            "ingresos_sala1": 60,
            "ingresos_sala2": 30,
        },
        {
            "bucket": "2026-11-21T15:00:00",
            "ingresos": 3,
            "salidas": 3,
            "personas_unicas": 3,
            "personas_sala1": 3,
            "personas_sala2": 0,
            "ingresos_sala1": 3,
            "ingresos_sala2": 0,
            "sin_registros_sala2": True,
        },
    ]

    class _MockDb:
        pass

    async def _run_resumen():
        async def _fake_caps(*_a, **_kw):
            return {"sala_1": 150, "sala_2": 126, "total": 276}

        async def _fake_hitos(*_a, **_kw):
            return []

        async def _fake_hechos(*_a, **_kw):
            return "HECHOS INSTITUCIONALES: OK"

        async def _fake_curve(*_a, **_kw):
            return curva_mock

        async def _fake_vivo(*_a, **_kw):
            return {
                "aforo_actual": 0,
                "capacidad_maxima": 276,
                "timestamp": "2026-11-21T15:45:52",
                "ultimo_marcaje_sala1": "2026-11-21T15:45:52",
                "ultimo_marcaje_sala2": "2026-11-20T22:38:48",
            }

        with (
            patch.object(eh, "obtener_capacidades_salas_cacheadas", _fake_caps),
            patch.object(eh, "obtener_contexto_calendario_rango", _fake_hitos),
            patch.object(eh, "obtener_resumen_hechos_institucionales", _fake_hechos),
            patch.object(eh.AttendanceService, "get_realtime_presence_curve", _fake_curve),
            patch.object(eh.AttendanceService, "get_occupancy_realtime", _fake_vivo),
            patch.object(eh.CalendarService, "obtener_resumen_anual_calendario", return_value=[]),
        ):
            _, _, resumen, _, _ = await eh._resolver_datos_grafico_contexto_interno(
                grafico_id="aforo_presencia_intervalos",
                espacio_id=1,
                fecha_inicio="2026-11-15",
                fecha_fin="2026-11-21",
                db=_MockDb(),
                filtros={"alcance": "conformes", "regimen_horario": "dentro_horario,24h_delta", "sala": ""},
            )
            assert "158 personas" in resumen
            assert "Sala 1 = 104" in resumen and "Sala 2 = 54" in resumen
            assert "Pico individual Sala 1" in resumen and "104 personas" in resumen
            assert "Pico individual Sala 2" in resumen and "54 personas" in resumen
            assert "Sin marcajes registrados en Sala 2 (CSF04 Pecera 1° Piso)" in resumen
            assert "20/11/2026 22:38" in resumen
            assert "21/11/2026" in resumen

    asyncio.run(_run_resumen())


def test_reconciliacion_contingencias_y_filtro_huerfanas_fechas_chat():
    from datetime import date
    from app.domain.config_models import HorarioOperacion
    from app.domain.models import CalendarioAcademico, ContingenciaAcademica
    from app.services.calendar_service import CalendarService
    from app.services.chat import fechas_chat as fc

    class _FakeScalarResult:
        def __init__(self, items):
            self._items = items

        def all(self):
            return list(self._items)

    class _FakeExecResult:
        def __init__(self, items):
            self._items = items

        def scalars(self):
            return _FakeScalarResult(self._items)

    class _FakeCalSession:
        def __init__(self, cals: dict, conts: dict):
            self.cals = cals
            self.conts = conts
            self._deleted: list = []

        async def get(self, model, key):
            if model is CalendarioAcademico:
                return self.cals.get(key)
            if model is ContingenciaAcademica:
                return self.conts.get(key)
            return None

        def add(self, obj):
            if isinstance(obj, CalendarioAcademico):
                self.cals[obj.fecha] = obj
            elif isinstance(obj, ContingenciaAcademica):
                self.conts[obj.id] = obj

        async def delete(self, obj):
            self._deleted.append(obj)

        async def flush(self):
            for obj in list(self._deleted):
                if isinstance(obj, CalendarioAcademico):
                    self.cals.pop(obj.fecha, None)
                elif isinstance(obj, ContingenciaAcademica):
                    self.conts.pop(obj.id, None)
            self._deleted.clear()

        async def commit(self):
            await self.flush()

        async def execute(self, stmt):
            entity = stmt.column_descriptions[0]["entity"] if getattr(stmt, "column_descriptions", None) else None
            params = stmt.compile().params
            if entity is ContingenciaAcademica:
                items = sorted(self.conts.values(), key=lambda x: x.fecha_inicio)
                d_fin = next((v for k, v in params.items() if "fecha_inicio" in k and isinstance(v, date)), None)
                d_ini = next((v for k, v in params.items() if "fecha_fin" in k and isinstance(v, date)), None)
                if d_ini and d_fin:
                    items = [c for c in items if c.fecha_inicio <= d_fin and c.fecha_fin >= d_ini]
                esp_vals = [v for k, v in params.items() if "espacio_id" in k]
                if esp_vals:
                    esp_id = esp_vals[0]
                    items = [c for c in items if c.espacio_id is None or c.espacio_id == esp_id]
                return _FakeExecResult(items)
            if entity is CalendarioAcademico:
                items = sorted(self.cals.values(), key=lambda x: x.fecha)
                fechas_p = sorted(v for k, v in params.items() if "fecha" in k and isinstance(v, date))
                if len(fechas_p) == 2:
                    items = [c for c in items if fechas_p[0] <= c.fecha <= fechas_p[1]]
                return _FakeExecResult(items)
            if entity is HorarioOperacion:
                return _FakeExecResult([])
            return _FakeExecResult([])

    async def _run():
        cal_store = {
            # Feriado mixto con contingencia manual
            date(2026, 9, 19): CalendarioAcademico(
                fecha=date(2026, 9, 19),
                is_holiday=True,
                is_break=False,
                is_exam_period=False,
                is_class_milestone=False,
                suspension_actividades=True,
                is_strike_federado=True,
                is_strike_carrera=False,
                tipo_contingencia="paro_federado",
                fuente="contingencia_manual",
                descripcion="Feriado. Día de las Glorias del Ejército. | [Paro General Estudiantil FEUCT]",
            ),
            # Contingencia pura con codificación corrupta + solapamiento
            date(2026, 10, 21): CalendarioAcademico(
                fecha=date(2026, 10, 21),
                is_holiday=False,
                is_break=False,
                is_exam_period=False,
                is_class_milestone=False,
                suspension_actividades=True,
                is_strike_federado=False,
                is_strike_carrera=False,
                tipo_contingencia="suspension_sala",
                fuente="contingencia_manual",
                descripcion="[Sala 2 (CSF04 Pecera)] [Suspensi?n de Actividades Sala 2 Pecera]",
            ),
            date(2026, 10, 22): CalendarioAcademico(
                fecha=date(2026, 10, 22),
                is_holiday=False,
                is_break=False,
                is_exam_period=False,
                is_class_milestone=False,
                suspension_actividades=True,
                is_strike_federado=False,
                is_strike_carrera=False,
                tipo_contingencia="suspension_sala",
                fuente="contingencia_manual",
                descripcion="[Sala 2 (CSF04 Pecera)] [Suspensi?n de Actividades Sala 2 Pecera]",
            ),
            # Huérfanas heredadas 26-29/10 sin registro en contingencias_academicas
            date(2026, 10, 26): CalendarioAcademico(
                fecha=date(2026, 10, 26),
                is_holiday=False,
                is_break=False,
                is_exam_period=False,
                is_class_milestone=False,
                suspension_actividades=False,
                is_strike_federado=False,
                is_strike_carrera=False,
                tipo_contingencia=None,
                fuente="contingencia_manual",
                descripcion="[Sala 2 (CSF04 Pecera)] [Suspensión de Actividades Sala 2 Pecera (03:00 a 12:59 hrs)]",
            ),
            date(2026, 10, 27): CalendarioAcademico(
                fecha=date(2026, 10, 27),
                is_holiday=False,
                is_break=False,
                is_exam_period=False,
                is_class_milestone=False,
                suspension_actividades=False,
                is_strike_federado=False,
                is_strike_carrera=False,
                tipo_contingencia=None,
                fuente="contingencia_manual",
                descripcion="[Sala 2 (CSF04 Pecera)] [Suspensión de Actividades Sala 2 Pecera (03:00 a 12:59 hrs)]",
            ),
        }
        cont_store = {
            1: ContingenciaAcademica(
                id=1,
                fecha_inicio=date(2026, 9, 19),
                fecha_fin=date(2026, 9, 19),
                tipo="paro_federado",
                titulo="Paro General Estudiantil FEUCT",
                descripcion="",
                espacio_id=None,
                subespacio="todos",
                implica_cierre_total=False,
            ),
            4: ContingenciaAcademica(
                id=4,
                fecha_inicio=date(2026, 10, 21),
                fecha_fin=date(2026, 10, 22),
                tipo="suspension_sala",
                titulo="Suspensión de Actividades Sala 2 Pecera",
                descripcion="",
                espacio_id=1,
                subespacio="sala_2",
                hora_inicio="15:00",
                hora_fin=None,
                implica_cierre_total=True,
            ),
            5: ContingenciaAcademica(
                id=5,
                fecha_inicio=date(2026, 10, 22),
                fecha_fin=date(2026, 10, 22),
                tipo="mantencion_cierre",
                titulo="Mantención Eléctrica Sala 2",
                descripcion="",
                espacio_id=1,
                subespacio="sala_2",
                hora_inicio="09:00",
                hora_fin="11:00",
                implica_cierre_total=True,
            ),
        }
        db = _FakeCalSession(cal_store, cont_store)

        async def _fake_caps(*_a, **_kw):
            return {"sala_1": 150, "sala_2": 126, "total": 276}

        with patch.object(fc, "obtener_capacidades_salas_cacheadas", _fake_caps):
            # 1. fechas_chat ignora huérfanas, no duplica 21-22/10, formatea desde 15:00 y conserva feriado 19/09
            hitos_oct = await fc.obtener_contexto_calendario_rango(db, date(2026, 10, 1), date(2026, 10, 31), espacio_id=1)
            txt_oct = "\n".join(hitos_oct)
            assert "26/10" not in txt_oct and "27/10" not in txt_oct
            assert "desde 15:00 hrs" in txt_oct
            assert txt_oct.count("Suspensión de Actividades Sala 2 Pecera") == 1

            res_oct = await fc.obtener_resumen_hechos_institucionales(db, date(2026, 10, 1), date(2026, 10, 31), espacio_id=1)
            assert "26/10" not in res_oct and "27/10" not in res_oct
            assert "desde 15:00 hrs" in res_oct

            hitos_sep = await fc.obtener_contexto_calendario_rango(db, date(2026, 9, 19), date(2026, 9, 19), espacio_id=1)
            assert any("Glórias" in h or "Glorias" in h for h in hitos_sep)
            assert sum("Paro General Estudiantil FEUCT" in h for h in hitos_sep) == 1

        # 2. Al borrar contingencia superpuesta id=5 (22/10), conserva id=4 vigente en 22/10
        srv = CalendarService()
        assert await srv.eliminar_contingencia(db, 5) is True
        assert date(2026, 10, 22) in cal_store
        assert "Suspensión de Actividades Sala 2 Pecera (desde 15:00 hrs)" in cal_store[date(2026, 10, 22)].descripcion
        assert "Mantención Eléctrica Sala 2" not in cal_store[date(2026, 10, 22)].descripcion

        # 3. Al borrar id=4 (even with Suspensi?n mismatch), elimina 21-22/10 puras por completo
        assert await srv.eliminar_contingencia(db, 4) is True
        assert date(2026, 10, 21) not in cal_store
        assert date(2026, 10, 22) not in cal_store

        # 4. Al borrar paro id=1 en día mixto 19/09, conserva el feriado oficial y limpia paro/tipo_contingencia
        assert await srv.eliminar_contingencia(db, 1) is True
        sep19 = cal_store[date(2026, 9, 19)]
        assert sep19.is_holiday is True
        assert sep19.is_strike_federado is False
        assert sep19.tipo_contingencia is None
        assert sep19.descripcion == "Feriado. Día de las Glorias del Ejército."

    asyncio.run(_run())


def test_utilidades_tiempo_chile_dst_y_auditoria():
    from datetime import timezone
    from app.core.tiempo import (
        ZONA_CHILE,
        inicio_dia_chile_en_utc_naive,
        marcar_chile,
        marcar_utc,
        utc_a_chile,
    )

    dt_naive_verano = datetime(2026, 11, 22, 20, 45, 22, 154748)
    dt_utc_verano = marcar_utc(dt_naive_verano)
    assert dt_utc_verano == datetime(2026, 11, 22, 20, 45, 22, 154748, tzinfo=timezone.utc)
    assert utc_a_chile(dt_naive_verano) == datetime(2026, 11, 22, 17, 45, 22, 154748, tzinfo=ZONA_CHILE)

    dt_naive_invierno = datetime(2026, 7, 15, 20, 45, 22)
    assert utc_a_chile(dt_naive_invierno) == datetime(2026, 7, 15, 16, 45, 22, tzinfo=ZONA_CHILE)

    # 21:30–23:59 hora Chile sigue perteneciendo al mismo día operativo en Chile (03:00/04:00 UTC)
    assert inicio_dia_chile_en_utc_naive(datetime(2026, 11, 23, 1, 30, 0, tzinfo=timezone.utc)) == datetime(2026, 11, 22, 3, 0, 0)
    assert inicio_dia_chile_en_utc_naive(datetime(2026, 7, 16, 1, 30, 0, tzinfo=timezone.utc)) == datetime(2026, 7, 15, 4, 0, 0)

    loc_verano = marcar_chile(datetime(2026, 11, 22, 17, 45, 0))
    loc_invierno = marcar_chile(datetime(2026, 7, 15, 16, 45, 0))
    assert loc_verano.utcoffset().total_seconds() == -3 * 3600
    assert loc_invierno.utcoffset().total_seconds() == -4 * 3600
    assert marcar_utc(None) is None and utc_a_chile(None) is None and marcar_chile(None) is None


def test_auditoria_reportes_compartidos_rls_y_eventos():
    import asyncio
    import uuid
    from datetime import date, timedelta
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock, patch

    from fastapi import HTTPException
    from app.services.servicio_reportes_compartidos import ServicioReportesCompartidos

    rol_admin = SimpleNamespace(id=1, nombre="Admin_Sistema")
    rol_super = SimpleNamespace(id=1, nombre="SuperAdmin")
    rol_dir = SimpleNamespace(id=2, nombre="Directivo")
    rol_dir_norm = SimpleNamespace(id=2, nombre="Director_Recinto")
    rol_ana = SimpleNamespace(id=3, nombre="Analista")

    u_admin = SimpleNamespace(
        id=1, nombre_completo="Super Admin", email="admin@uct.cl",
        roles=[rol_super], allowed_datasets=["biblioteca", "estacionamiento"], espacio_id=None,
    )
    u_dir_bib = SimpleNamespace(
        id=2, nombre_completo="Directivo Bib", email="dir.bib@uct.cl",
        roles=[rol_dir], allowed_datasets=["biblioteca"], espacio_id=None,
    )
    u_dir_est = SimpleNamespace(
        id=3, nombre_completo="Directivo Est", email="dir.est@uct.cl",
        roles=[rol_dir_norm], allowed_datasets=["estacionamiento"], espacio_id=2,
    )
    u_ana_bib = SimpleNamespace(
        id=4, nombre_completo="Analista Bib", email="ana.bib@uct.cl",
        roles=[rol_ana], allowed_datasets=["biblioteca"], espacio_id=1,
    )
    u_dir_invalido = SimpleNamespace(
        id=5, nombre_completo="Directivo Sin Match", email="dir.none@uct.cl",
        roles=[rol_dir], allowed_datasets=["estacionamiento"], espacio_id=1,
    )

    assert ServicioReportesCompartidos._es_admin(u_admin) is True
    assert ServicioReportesCompartidos._espacios_autorizados(u_admin) is None
    assert ServicioReportesCompartidos._es_directivo(u_dir_bib) is True
    assert ServicioReportesCompartidos._espacios_autorizados(u_dir_bib) == [1]
    assert ServicioReportesCompartidos._espacios_autorizados(u_dir_est) == [2]
    assert ServicioReportesCompartidos._espacios_autorizados(u_dir_invalido) == []
    assert ServicioReportesCompartidos._es_emisor_directivo_o_analista(u_admin) is False
    assert ServicioReportesCompartidos._es_emisor_directivo_o_analista(u_dir_bib) is True
    assert ServicioReportesCompartidos._es_emisor_directivo_o_analista(u_ana_bib) is True

    rep_bib_ana = SimpleNamespace(id=uuid.uuid4(), espacio_id=1, creado_por_id=u_ana_bib.id, creador=u_ana_bib)
    rep_bib_dir = SimpleNamespace(id=uuid.uuid4(), espacio_id=1, creado_por_id=u_dir_bib.id, creador=u_dir_bib)
    rep_bib_adm = SimpleNamespace(id=uuid.uuid4(), espacio_id=1, creado_por_id=u_admin.id, creador=u_admin)
    rep_est_est = SimpleNamespace(id=uuid.uuid4(), espacio_id=2, creado_por_id=u_dir_est.id, creador=u_dir_est)

    # Admin ve y gestiona todo
    for rep, emisor in [
        (rep_bib_ana, u_ana_bib),
        (rep_bib_dir, u_dir_bib),
        (rep_bib_adm, u_admin),
        (rep_est_est, u_dir_est),
    ]:
        assert ServicioReportesCompartidos._puede_ver_o_gestionar_reporte(u_admin, rep, emisor) is True

    # Directivo Biblioteca solo ve/gestiona reportes de Directivo o Analista de Biblioteca (nunca Admin ni Estacionamiento)
    assert ServicioReportesCompartidos._puede_ver_o_gestionar_reporte(u_dir_bib, rep_bib_ana, u_ana_bib) is True
    assert ServicioReportesCompartidos._puede_ver_o_gestionar_reporte(u_dir_bib, rep_bib_dir, u_dir_bib) is True
    assert ServicioReportesCompartidos._puede_ver_o_gestionar_reporte(u_dir_bib, rep_bib_adm, u_admin) is False
    assert ServicioReportesCompartidos._puede_ver_o_gestionar_reporte(u_dir_bib, rep_est_est, u_dir_est) is False

    # Analista solo ve los propios
    assert ServicioReportesCompartidos._puede_ver_o_gestionar_reporte(u_ana_bib, rep_bib_ana, u_ana_bib) is True
    assert ServicioReportesCompartidos._puede_ver_o_gestionar_reporte(u_ana_bib, rep_bib_dir, u_dir_bib) is False

    # Verificar resumen y desglose de métricas por acción sin tocar lazy attributes si emisor_info se provee
    dest_obj = SimpleNamespace(
        id=10,
        usuario_id=99,
        nombre_completo="Decana Facultad",
        email="decana@uct.cl",
        cargo="Decana",
        unidad_academica="Ingeniería",
        token_portal="portal-tok",
        activo=True,
    )
    ahora = datetime(2026, 11, 22, 18, 30, 0)
    rep_completo = SimpleNamespace(
        id=uuid.uuid4(),
        codigo_corto="RPT-0001",
        token_acceso="tok-rep-1",
        espacio_id=1,
        creado_por_id=u_ana_bib.id,
        titulo_reporte="Uso Biblioteca Noviembre",
        finalidad_reporte="Seguimiento mensual",
        nota_general="Sin novedad",
        notas_items_json="[]",
        fecha_inicio=date(2026, 11, 1),
        fecha_fin=date(2026, 11, 22),
        modo_datos="instantanea_fija",
        filtros_bloqueados_json="{}",
        graficos_visibles_json="[]",
        indicadores_visibles_json="[]",
        datos_instantanea_json='{"kpis_base": {}, "indicadores_ejecutivos": {"dias_operativos": 10}, "indicadores_visibles": ["kpi_demo"], "graficos": {}}',
        permitir_exportacion=True,
        permitir_ia=True,
        activo=True,
        expira_en=ahora + timedelta(days=7),
        total_accesos=2,
        ultimo_acceso_en=ahora,
        creado_en=ahora - timedelta(days=1),
        destinatario=dest_obj,
    )
    metricas_demo = {
        "total_aperturas": 2,
        "total_descargas_excel": 1,
        "total_descargas_csv": 1,
        "total_descargas_pdf": 1,
        "total_descargas_imagen": 0,
        "total_consultas_ia": 3,
        "primer_acceso_en": ahora - timedelta(hours=3),
        "ultimo_acceso_en": ahora,
        "ultima_ip": "10.10.2.5",
        "ultimo_user_agent": "Mozilla/5.0 Chrome/131.0",
    }
    resumen = ServicioReportesCompartidos._formatear_resumen_reporte(
        rep_completo,
        metricas=metricas_demo,
        emisor_info={"id": u_ana_bib.id, "nombre_completo": u_ana_bib.nombre_completo, "email": u_ana_bib.email, "rol": "Analista_Consulta"},
        espacio_nombre="Biblioteca CSF",
    )
    assert resumen["revisado"] is True
    assert resumen["total_aperturas"] == 2
    assert resumen["total_descargas"] == 3
    assert resumen["total_consultas_ia"] == 3
    assert "-03:00" in resumen["creado_en"]
    assert "-03:00" in resumen["ultimo_acceso_en"]
    assert resumen["emisor"]["nombre_completo"] == "Analista Bib"

    async def _run_async():
        eventos_agregados = []

        class _ScalarRes:
            def __init__(self, obj):
                self._obj = obj

            def scalar_one_or_none(self):
                return self._obj

            def scalars(self):
                return SimpleNamespace(all=lambda: [])

        fake_session = AsyncMock()
        fake_session.execute = AsyncMock(return_value=_ScalarRes(rep_completo))
        fake_session.add = MagicMock(side_effect=lambda obj: eventos_agregados.append(obj))
        fake_session.commit = AsyncMock()

        # 1. Descarga válida registra evento sin inflar total_accesos
        resp_ev = await ServicioReportesCompartidos.registrar_evento_reporte_publico(
            session=fake_session,
            token_acceso="tok-rep-1",
            accion="descarga_excel",
            detalle="curva_hora.xlsx",
            ip_origen="192.168.1.50",
            user_agent="Mozilla/5.0 Chrome/131.0",
        )
        assert resp_ev["ok"] is True
        assert resp_ev["accion"] == "descarga_excel"
        assert rep_completo.total_accesos == 2
        assert len(eventos_agregados) == 1
        assert eventos_agregados[0].detalle == "curva_hora.xlsx"
        assert "Chrome/131.0" in eventos_agregados[0].user_agent

        # 2. Acción inválida rechaza con HTTP 400
        try:
            await ServicioReportesCompartidos.registrar_evento_reporte_publico(
                session=fake_session,
                token_acceso="tok-rep-1",
                accion="accion_invalida",
            )
            assert False, "Debió fallar con 400"
        except HTTPException as exc:
            assert exc.status_code == 400

        # 3. Reporte con exportación deshabilitada rechaza con HTTP 403
        rep_completo.permitir_exportacion = False
        try:
            await ServicioReportesCompartidos.registrar_evento_reporte_publico(
                session=fake_session,
                token_acceso="tok-rep-1",
                accion="descarga_pdf",
            )
            assert False, "Debió fallar con 403"
        except HTTPException as exc:
            assert exc.status_code == 403
        finally:
            rep_completo.permitir_exportacion = True

        # 4. Consulta IA confinada registra detalle, user_agent y telemetría en chat_audit_logs
        eventos_agregados.clear()
        fake_llm = SimpleNamespace(
            model_name="gemini-2.5-flash",
            generate_response=AsyncMock(return_value="Síntesis ejecutiva confirmada."),
        )
        with (
            patch(
                "app.services.servicio_reportes_compartidos.CATALOGO_INDICADORES_BIBLIOTECA",
                [{"id": "kpi_demo"}],
            ),
            patch(
                "app.services.servicio_reportes_compartidos.build_llm_client",
                new=AsyncMock(return_value=fake_llm),
            ),
            patch(
                "app.services.servicio_reportes_compartidos.registrar_auditoria_chat",
                new=AsyncMock(),
            ) as mock_audit_chat,
        ):
            ia_resp = await ServicioReportesCompartidos.consultar_ia_reporte_confinado(
                session=fake_session,
                token_acceso="tok-rep-1",
                pregunta="¿Cuál fue la hora peak del período?",
                ip_origen="10.0.0.9",
                user_agent="Mozilla/5.0 Edg/130.0",
            )
            assert ia_resp["respuesta"] == "Síntesis ejecutiva confirmada."
            eventos_aud = [e for e in eventos_agregados if e.__class__.__name__ == "AuditoriaAccesoReporte"]
            assert len(eventos_aud) == 1
            assert eventos_aud[0].accion == "consulta_ia_confinada"
            assert eventos_aud[0].detalle == "¿Cuál fue la hora peak del período?"
            assert eventos_aud[0].user_agent == "Mozilla/5.0 Edg/130.0"
            mock_audit_chat.assert_awaited_once()
            kwargs_aud = mock_audit_chat.await_args.kwargs
            assert kwargs_aud["usuario_id"] == 99
            assert "[Reporte RPT-0001]" in kwargs_aud["prompt_text"]
            assert kwargs_aud["dataset_tipo"] == "biblioteca"
            assert kwargs_aud["modelo_utilizado"] == "gemini-2.5-flash"
            assert kwargs_aud["status"] == "éxito"

        # 5. obtener_eventos_reporte rechaza 403 cuando Directivo intenta auditar reporte de Admin
        fake_session_rls = AsyncMock()
        fake_session_rls.execute = AsyncMock(
            side_effect=[_ScalarRes(rep_bib_adm), _ScalarRes(u_admin)]
        )
        try:
            await ServicioReportesCompartidos.obtener_eventos_reporte(
                session=fake_session_rls,
                usuario_actual=u_dir_bib,
                reporte_id=str(rep_bib_adm.id),
            )
            assert False, "Debió rechazar auditoría cruzada con 403"
        except HTTPException as exc:
            assert exc.status_code == 403

    asyncio.run(_run_async())


def test_gobernanza_opcion_a_guardia_y_consultores_prueba():
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import HTTPException
    from app.core.security import validar_acceso_espacio
    from app.core.startup_seed import obtener_consultores_prueba, obtener_usuarios_demo
    from app.domain.auth_models import Rol, Usuario
    from app.schemas.auth_schemas import UsuarioInviteRequest
    from app.services.auth_service import (
        _es_gestionable_por_director,
        _resolver_espacio_por_datasets,
        invitar_usuario,
    )

    # 1. Prioridad de primary_role coloca Guardia_Seguridad por encima de Consultor_Reporte
    usr_dual = Usuario(
        id=4,
        email="guardia@uct.cl",
        nombre_completo="Guardia",
        hashed_password="x",
        is_active=True,
        allowed_datasets=["biblioteca", "estacionamiento"],
    )
    usr_dual.roles = [Rol(id=5, nombre="Consultor_Reporte"), Rol(id=4, nombre="Guardia_Seguridad")]
    assert usr_dual.primary_role == "Guardia_Seguridad"

    # 2. Mapeo coherente datasets -> espacio_id y confinamiento Consultor_Reporte
    assert _resolver_espacio_por_datasets(["biblioteca"], ["Guardia_Seguridad"]) == (["biblioteca"], 1)
    assert _resolver_espacio_por_datasets(["estacionamiento"], ["Analista_Consulta"]) == (["estacionamiento"], 2)
    assert _resolver_espacio_por_datasets(["biblioteca", "estacionamiento"], ["Guardia_Seguridad"]) == (
        ["biblioteca", "estacionamiento"],
        None,
    )
    assert _resolver_espacio_por_datasets(["biblioteca", "estacionamiento"], ["Consultor_Reporte"]) == ([], None)
    try:
        _resolver_espacio_por_datasets([], ["Guardia_Seguridad"])
        assert False, "Debió exigir al menos un módulo para Guardia_Seguridad"
    except HTTPException as exc:
        assert exc.status_code == 400

    # 3. Consultor_Reporte con allowed_datasets=[] queda bloqueado en endpoints analíticos (403)
    consultor_puro = Usuario(
        id=20,
        email="consultor1@uct.cl",
        nombre_completo="Consultor 1",
        hashed_password="x",
        is_active=True,
        allowed_datasets=[],
        espacio_id=None,
    )
    consultor_puro.roles = [Rol(id=5, nombre="Consultor_Reporte")]
    for esp_id in (1, 2):
        try:
            validar_acceso_espacio(esp_id, consultor_puro)
            assert False, f"Consultor_Reporte no debía pasar validar_acceso_espacio({esp_id})"
        except HTTPException as exc:
            assert exc.status_code == 403

    # 4. Gobernanza Opción A entre Director mono-módulo, Director multi-módulo y personal compartido
    dir_bib = SimpleNamespace(
        id=10, espacio_id=1, allowed_datasets=["biblioteca"], roles=[SimpleNamespace(nombre="Director_Recinto")]
    )
    dir_ambos = SimpleNamespace(
        id=11, espacio_id=None, allowed_datasets=["biblioteca", "estacionamiento"], roles=[SimpleNamespace(nombre="Director_Recinto")]
    )
    guardia_bib = SimpleNamespace(
        id=12, espacio_id=1, allowed_datasets=["biblioteca"], created_by_user_id=10, roles=[SimpleNamespace(nombre="Guardia_Seguridad")]
    )
    guardia_ambos = SimpleNamespace(
        id=13, espacio_id=None, allowed_datasets=["biblioteca", "estacionamiento"], created_by_user_id=1, roles=[SimpleNamespace(nombre="Guardia_Seguridad")]
    )
    assert _es_gestionable_por_director(dir_bib, guardia_bib) is True
    assert _es_gestionable_por_director(dir_bib, guardia_ambos) is False
    assert _es_gestionable_por_director(dir_ambos, guardia_ambos) is True

    # 5. Seed: guardia demo en ambos módulos (espacio_id=None) y exactamente 2 consultores de prueba
    demos = {u["email"]: u for u in obtener_usuarios_demo()}
    assert demos["guardia@uct.cl"]["espacio_id"] is None
    assert demos["guardia@uct.cl"]["allowed_datasets"] == ["biblioteca", "estacionamiento"]
    consultores = obtener_consultores_prueba()
    assert len(consultores) == 2
    assert {c["email"] for c in consultores} == {"consultor1@uct.cl", "consultor2@uct.cl"}
    for c in consultores:
        assert c["roles"] == ["Consultor_Reporte"]
        assert c["allowed_datasets"] == []
        assert c["espacio_id"] is None

    # 6. Invitar Consultor_Reporte desde Administración vacía datasets y crea DestinatarioReporte
    async def _run_invite():
        agregados = []

        class _Res:
            def __init__(self, obj=None):
                self._obj = obj

            def scalar_one_or_none(self):
                return self._obj

        rol_c = Rol(id=5, nombre="Consultor_Reporte")
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[_Res(rol_c), _Res(None), _Res(None)])
        db.add = MagicMock(side_effect=lambda obj: (setattr(obj, "id", 55) if isinstance(obj, Usuario) else None, agregados.append(obj)))
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        req = UsuarioInviteRequest(
            email="nuevo.consultor@uct.cl",
            nombre_completo="Nuevo Consultor",
            roles=["Consultor_Reporte"],
            allowed_datasets=["biblioteca", "estacionamiento"],
        )
        creado, tok_pl, _ = await invitar_usuario(db, req, creator=None)
        assert creado.allowed_datasets == []
        assert creado.espacio_id is None
        assert creado.can_use_ai is True
        assert any(obj.__class__.__name__ == "DestinatarioReporte" for obj in agregados)
        assert len(tok_pl) > 10

    asyncio.run(_run_invite())


def test_campana_24h_opcion3_y_enfoque_a_reportes_compartidos():
    from datetime import date
    from unittest.mock import AsyncMock, patch
    from app.services.servicio_reportes_compartidos import (
        CATALOGO_GRAFICOS_BIBLIOTECA,
        CATALOGO_GRAFICOS_ESTACIONAMIENTO,
        IDS_CAMPANA_24H_GRANULARES,
        ServicioReportesCompartidos,
    )
    from app.services.attendance_service import AttendanceService

    # 1. Catálogos agrupados por sección con 5 sub-bloques granulares en Sección 5
    for item in CATALOGO_GRAFICOS_BIBLIOTECA + CATALOGO_GRAFICOS_ESTACIONAMIENTO:
        assert item.get("seccion"), f"Falta seccion en {item['id']}"

    ids_bib = {g["id"] for g in CATALOGO_GRAFICOS_BIBLIOTECA}
    for sub_id in IDS_CAMPANA_24H_GRANULARES:
        assert sub_id in ids_bib
        assert ServicioReportesCompartidos._es_grafico_campana_24h(sub_id) is True
        assert ServicioReportesCompartidos._normalizar_clave_grafico_snapshot(sub_id) == "campana_24_horas"
    assert ServicioReportesCompartidos._normalizar_clave_grafico_snapshot("campana_24_horas") == "campana_24_horas"
    assert ServicioReportesCompartidos._normalizar_clave_grafico_snapshot("flujo_horario") == "flujo_horario"

    # 2. _rango_tiene_campana_24h valida traslape en espacio 1 y retorna False para espacio 2
    async def _run_validaciones():
        class _ResFirst:
            def __init__(self, row):
                self._row = row

            def first(self):
                return self._row

        db_con = AsyncMock()
        db_con.execute = AsyncMock(return_value=_ResFirst((7,)))
        assert await ServicioReportesCompartidos._rango_tiene_campana_24h(
            db_con, 1, date(2026, 6, 15), date(2026, 6, 30)
        ) is True

        db_sin = AsyncMock()
        db_sin.execute = AsyncMock(return_value=_ResFirst(None))
        assert await ServicioReportesCompartidos._rango_tiene_campana_24h(
            db_sin, 1, date(2026, 4, 1), date(2026, 4, 15)
        ) is False
        assert await ServicioReportesCompartidos._rango_tiene_campana_24h(
            db_con, 2, date(2026, 6, 15), date(2026, 6, 30)
        ) is False

        # 3. ensamblar_datos_reporte_confinado: sin campaña 24h elimina campana_24h_* y no llama get_analisis_24h
        filtros_prueba = {
            "alcance": "anomalias",
            "regimen_horario": "24h_delta",
            "direccion": "solo_ingreso",
            "dias_semana": "lunes,martes",
            "door": "s2_principal",
            "perfil_visita": "profundo",
            "marcajes": "2",
            "sala": "sala_2",
            "carrera": "Derecho",
            "facultad": "Ciencias Jurídicas",
            "cohorte": "2024",
            "incluir_pausas_bano": False,
            "desduplicar_rafagas": False,
            "incluir_funcionarios": False,
            "incluir_sin_identificar": False,
        }

        captura_24h = {}

        async def _fake_get_24h(**kwargs):
            captura_24h.update(kwargs)
            return {"campana": {"id": 1, "tiene_campana_activa": True}}

        with (
            patch.object(AttendanceService, "get_kpis", new=AsyncMock(return_value={"total_registros": 10})),
            patch.object(AttendanceService, "get_hourly_flow", new=AsyncMock(return_value=[])),
            patch.object(
                ServicioReportesCompartidos,
                "calcular_indicadores_ejecutivos_biblioteca",
                new=AsyncMock(return_value={"dias_operativos": 5}),
            ),
            patch.object(AttendanceService, "get_analisis_24h", side_effect=_fake_get_24h),
            patch.object(ServicioReportesCompartidos, "_rango_tiene_campana_24h", new=AsyncMock(return_value=False)),
        ):
            res_sin = await ServicioReportesCompartidos.ensamblar_datos_reporte_confinado(
                session=AsyncMock(),
                espacio_id=1,
                fecha_inicio=date(2026, 4, 1),
                fecha_fin=date(2026, 4, 15),
                filtros=filtros_prueba,
                graficos_visibles=["flujo_horario", "campana_24h_resumen"],
                indicadores_visibles=["dias_operativos"],
            )
            assert "campana_24h_resumen" not in res_sin["graficos_visibles"]
            assert "campana_24_horas" not in res_sin["graficos"]
            assert captura_24h == {}

        # 4. Con campaña 24h activa reenvía todos los filtros (Enfoque A) a get_analisis_24h
        with (
            patch.object(AttendanceService, "get_kpis", new=AsyncMock(return_value={"total_registros": 10})),
            patch.object(AttendanceService, "get_hourly_flow", new=AsyncMock(return_value=[])),
            patch.object(
                ServicioReportesCompartidos,
                "calcular_indicadores_ejecutivos_biblioteca",
                new=AsyncMock(return_value={"dias_operativos": 5}),
            ),
            patch.object(AttendanceService, "get_analisis_24h", side_effect=_fake_get_24h),
            patch.object(ServicioReportesCompartidos, "_rango_tiene_campana_24h", new=AsyncMock(return_value=True)),
        ):
            res_con = await ServicioReportesCompartidos.ensamblar_datos_reporte_confinado(
                session=AsyncMock(),
                espacio_id=1,
                fecha_inicio=date(2026, 6, 15),
                fecha_fin=date(2026, 6, 30),
                filtros=filtros_prueba,
                graficos_visibles=["campana_24h_resumen", "campana_24h_academico"],
                indicadores_visibles=["dias_operativos"],
            )
            assert res_con["graficos"]["campana_24_horas"]["campana"]["tiene_campana_activa"] is True
            for clave, valor in filtros_prueba.items():
                assert captura_24h.get(clave) == valor, f"Filtro {clave} no reenviado correctamente"

    asyncio.run(_run_validaciones())


def test_edicion_graficos_persistencia_ia_reporte_y_auditoria_superadmin():
    import uuid
    import json
    from datetime import date, datetime
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock, patch
    from fastapi import HTTPException
    from fastapi.testclient import TestClient

    from app.main import app
    from app.core.database import get_db
    from app.core.security import get_current_user
    from app.domain.auth_models import Rol, Usuario
    from app.domain.reportes_compartidos_models import MensajeIAReporte
    from app.services.servicio_reportes_compartidos import ServicioReportesCompartidos

    async def _run_flows():
        rep_id = uuid.uuid4()
        dest = SimpleNamespace(
            id=1,
            nombre_completo="Consultor Uno",
            email="consultor1@uct.cl",
            cargo="Jefe Carrera",
            unidad_academica="Ingeniería",
            token_portal="tok_p",
            activo=True,
            reportes=[],
        )
        creador = SimpleNamespace(
            id=2,
            nombre_completo="Director Biblioteca",
            email="dir@uct.cl",
            roles=[SimpleNamespace(nombre="Director_Recinto")],
        )
        admin_usr = Usuario(
            id=1,
            email="admin@uct.cl",
            nombre_completo="Super Admin",
            hashed_password="x",
            is_active=True,
        )
        admin_usr.roles = [Rol(id=1, nombre="Admin_Sistema")]

        reporte_mock = SimpleNamespace(
            id=rep_id,
            token_acceso="tok_rep_test",
            codigo_corto="UCT-2026-XYZ999",
            creado_por_id=2,
            destinatario_id=1,
            destinatario=dest,
            creador=creador,
            espacio_id=1,
            titulo_reporte="Informe Test",
            finalidad_reporte="Evaluación semestral",
            nota_general=None,
            notas_items_json="[]",
            fecha_inicio=date(2026, 4, 1),
            fecha_fin=date(2026, 4, 15),
            modo_datos="instantanea_fija",
            filtros_bloqueados_json="{}",
            graficos_visibles_json='["flujo_horario"]',
            indicadores_visibles_json='["dias_operativos"]',
            datos_instantanea_json=json.dumps({
                "kpis_base": {},
                "indicadores_ejecutivos": {"dias_operativos": 10},
                "indicadores_visibles": ["dias_operativos"],
                "graficos_visibles": ["flujo_horario"],
                "graficos": {"flujo_horario": [{"hora": 9, "entradas": 12}]},
            }),
            permitir_exportacion=True,
            permitir_ia=True,
            activo=True,
            expira_en=None,
            total_accesos=1,
            ultimo_acceso_en=None,
            creado_en=datetime(2026, 11, 24, 10, 0, 0),
        )

        # 1. Edición de graficos_visibles depura campana_24h_* en período sin campaña y actualiza instantánea
        class _ResObj:
            def __init__(self, obj=None, items=None):
                self._obj = obj
                self._items = items or []

            def scalar_one_or_none(self):
                return self._obj

            def scalars(self):
                return SimpleNamespace(all=lambda: self._items)

        db_edit = AsyncMock()
        db_edit.execute = AsyncMock(return_value=_ResObj(obj=reporte_mock))
        db_edit.commit = AsyncMock()
        db_edit.refresh = AsyncMock()

        with patch.object(ServicioReportesCompartidos, "_rango_tiene_campana_24h", new=AsyncMock(return_value=False)):
            res_edit = await ServicioReportesCompartidos.actualizar_estado_y_configuracion_reporte(
                session=db_edit,
                usuario_actual=admin_usr,
                reporte_id=str(rep_id),
                payload={
                    "graficos_visibles": ["flujo_horario", "campana_24h_resumen"],
                    "indicadores_visibles": ["dias_operativos", "afluencia_total"],
                },
            )
            assert res_edit["graficos_visibles"] == ["flujo_horario"]
            assert res_edit["indicadores_visibles"] == ["dias_operativos", "afluencia_total"]
            inst = json.loads(reporte_mock.datos_instantanea_json)
            assert inst["graficos_visibles"] == ["flujo_horario"]
            assert inst["indicadores_visibles"] == ["dias_operativos", "afluencia_total"]

        # 2. Persistencia en MensajeIAReporte + registro auditoría con status="éxito", origen y respuesta_text
        consultor_usr = SimpleNamespace(
            id=77,
            email="consultor1@uct.cl",
            can_use_ai=True,
            roles=[Rol(id=5, nombre="Consultor_Reporte", rate_limit_quota="50/day")],
        )
        agregados = []
        auditoria_llamadas = []

        async def _fake_audit(*args, **kwargs):
            auditoria_llamadas.append({"args": args, "kwargs": kwargs})

        fake_llm = SimpleNamespace(
            model_name="gemini-2.5-flash",
            generate_response=AsyncMock(return_value="Síntesis ejecutiva basada en 10 días operativos."),
        )

        db_ia = AsyncMock()
        db_ia.execute = AsyncMock(
            side_effect=[
                _ResObj(obj=reporte_mock),
                _ResObj(obj=consultor_usr),
                _ResObj(obj=0),
                _ResObj(items=[]),
            ]
        )
        db_ia.add = MagicMock(side_effect=lambda obj: agregados.append(obj))
        db_ia.commit = AsyncMock()
        db_ia.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, "id", 501))

        with (
            patch("app.services.servicio_reportes_compartidos.build_llm_client", new=AsyncMock(return_value=fake_llm)),
            patch("app.services.servicio_reportes_compartidos.registrar_auditoria_chat", side_effect=_fake_audit),
        ):
            resp_ia = await ServicioReportesCompartidos.consultar_ia_reporte_confinado(
                session=db_ia,
                token_acceso="tok_rep_test",
                pregunta="Resume el período",
                sesion_id="sesion_abc",
            )
            assert resp_ia["id"] == 501
            assert resp_ia["sesion_id"] == "sesion_abc"
            assert "10 días operativos" in resp_ia["respuesta"]
            assert resp_ia["cuota"] == {"usadas": 1, "limite": 50, "restantes": 49, "ilimitado": False}
            msgs = [o for o in agregados if isinstance(o, MensajeIAReporte)]
            assert len(msgs) == 1
            assert msgs[0].usuario_id == 77
            assert msgs[0].sesion_id == "sesion_abc"
            assert len(auditoria_llamadas) == 1
            assert auditoria_llamadas[0]["kwargs"]["status"] == "éxito"
            assert auditoria_llamadas[0]["kwargs"]["origen"] == "reporte_compartido"
            assert auditoria_llamadas[0]["kwargs"]["reporte_codigo"] == "UCT-2026-XYZ999"
            assert "10 días operativos" in auditoria_llamadas[0]["kwargs"]["respuesta_text"]

        # 3. Rechazo 403 cuando permitir_ia == False
        reporte_mock.permitir_ia = False
        db_no_ia = AsyncMock()
        db_no_ia.execute = AsyncMock(return_value=_ResObj(obj=reporte_mock))
        try:
            await ServicioReportesCompartidos.obtener_historial_ia_reporte_publico(
                session=db_no_ia,
                token_acceso="tok_rep_test",
            )
            assert False, "Debió rechazar historial IA cuando permitir_ia=False"
        except HTTPException as exc:
            assert exc.status_code == 403

    asyncio.run(_run_flows())

    # 4. Auditoría IA en /api/v1/admin/chat-audit exclusiva para SuperAdmin (Director recibe 403)
    director_usr = Usuario(
        id=10,
        email="directivo@uct.cl",
        nombre_completo="Director Recinto",
        hashed_password="x",
        is_active=True,
    )
    director_usr.roles = [Rol(id=2, nombre="Director_Recinto")]
    try:
        app.dependency_overrides[get_current_user] = lambda: director_usr
        client = TestClient(app)
        resp_dir = client.get("/api/v1/admin/chat-audit")
        assert resp_dir.status_code == 403
    finally:
        app.dependency_overrides.clear()

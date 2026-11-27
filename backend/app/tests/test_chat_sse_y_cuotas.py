"""Pruebas de asistente analítico IA, streaming SSE, cuotas, fechas y gráficos."""
import asyncio
import json
import uuid
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import plotly.graph_objects as go
import pytest

from app.core.database import AsyncSession
from app.tests.conftest import crear_db_mock
from app.schemas.chat_schemas import ChatRequest
from app.services import llm_client
from app.services.chat import auditoria_chat, fechas_chat, generadores_grafico, procesador_chat
from app.services.chat.ejecutor_herramientas import (
    ejecutar_consulta_tool,
    limpiar_cache_herramientas_chat,
    resolver_datos_grafico_contexto,
)


class _AsyncSessionCtx:
    def __init__(self, sess):
        self._sess = sess

    async def __aenter__(self):
        return self._sess

    async def __aexit__(self, *args):
        return False


def test_fechas_chat_extraccion_meses_semanas_y_cruce_anio():
    assert fechas_chat.detect_months_in_text("Comparar marzo y octubre mes 12") == [3, 10, 12]

    # Semana ISO explícita
    d_ini_s, d_fin_s = fechas_chat.extraer_o_normalizar_fechas(None, None, "Flujo en la semana 42 de 2026")
    assert d_ini_s == date.fromisocalendar(2026, 42, 1)
    assert d_fin_s == date.fromisocalendar(2026, 42, 7)

    # Cruce de año implícito
    d_ini_c, d_fin_c = fechas_chat.extraer_o_normalizar_fechas(
        None, None, "del 20 de diciembre al 5 de enero", anio_defecto=2026
    )
    assert d_ini_c == date(2025, 12, 20)
    assert d_fin_c == date(2026, 1, 5)

    # Sobrescritura de año explícito en prompt sobre fechas raw
    d_ini_y, d_fin_y = fechas_chat.extraer_o_normalizar_fechas(
        "2025-02-28", "2025-03-10", "aforo en marzo 2026"
    )
    assert d_ini_y == date(2026, 2, 28)
    assert d_fin_y == date(2026, 3, 10)


def test_generadores_grafico_y_serializacion():
    async def _run():
        assert generadores_grafico._rango_meses_sargable(2026, 12, 12) == (
            datetime(2026, 12, 1, 0, 0),
            datetime(2027, 1, 1, 0, 0),
        )

        fig = go.Figure(data=[go.Bar(x=["A", "B"], y=[10, 20])])
        ser = generadores_grafico.serialize_fig(fig)
        assert "data" in ser and "layout" in ser
        assert generadores_grafico.serialize_df(pd.DataFrame([{"x": 1}])) == [{"x": 1}]

        # generate_monthly_chart (biblioteca)
        res_anio = MagicMock()
        res_anio.scalar.return_value = 2026
        res_rows = MagicMock()
        res_rows.all.return_value = [
            SimpleNamespace(_mapping={"fecha": date(2026, 10, 12), "ingresos": 150, "salidas": 140, "personas_unicas": 130}),
            SimpleNamespace(_mapping={"fecha": date(2026, 10, 13), "ingresos": 180, "salidas": 175, "personas_unicas": 155}),
        ]
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[res_anio, res_rows])

        fig_out, df_out, msg_out = await generadores_grafico.generate_monthly_chart(db, "biblioteca", 10)
        assert fig_out is not None and isinstance(df_out, list) and len(df_out) == 2
        assert "Octubre" in msg_out

    asyncio.run(_run())


def test_auditoria_chat_normaliza_estado_y_tolera_fallos():
    async def _run():
        sess = AsyncMock()
        sess.add = MagicMock()
        sess.commit = AsyncMock()

        with patch.object(auditoria_chat, "AsyncSessionLocal", return_value=_AsyncSessionCtx(sess)):
            await auditoria_chat.registrar_auditoria_chat(
                usuario_id=5,
                prompt_text="¿Cuál fue el pico?",
                dataset_tipo="biblioteca",
                modelo_utilizado="gemini-2.5-flash",
                status="success",
                response_time_ms=123.4,
                respuesta_text="11:00 hrs",
                origen="reporte_compartido",
                reporte_codigo="RPT-2026-001",
            )
        audit_obj = sess.add.call_args[0][0]
        assert audit_obj.status == "éxito"

        # No propaga error si la sesión falla
        sess_err = AsyncMock()
        sess_err.add = MagicMock(side_effect=RuntimeError("db caida"))
        with patch.object(auditoria_chat, "AsyncSessionLocal", return_value=_AsyncSessionCtx(sess_err)):
            await auditoria_chat.registrar_auditoria_chat(
                usuario_id=1, prompt_text="x", dataset_tipo="biblioteca", modelo_utilizado="m", status="error", response_time_ms=10.0
            )

    asyncio.run(_run())


def test_ejecutor_herramientas_rls_y_cache():
    async def _run():
        limpiar_cache_herramientas_chat()
        req_bib = ChatRequest(prompt="Ver flota vehicular en 2026", dataset_tipo="biblioteca", session_id="s1")
        db_falsa = crear_db_mock()

        # Espacio 1 (Biblioteca) bloquea herramienta exclusiva de Estacionamiento
        with patch("app.services.chat.ejecutor_herramientas.obtener_anio_activo_espacio", new=AsyncMock(return_value=2026)):
            comp, data, msg, _, _ = await ejecutar_consulta_tool(
                "consultar_flota_vehicular", {}, db_falsa, espacio_id=1, req=req_bib
            )
        assert comp is None and "Acceso denegado" in msg

        # Espacio 2 (Estacionamiento) bloquea herramienta exclusiva de Biblioteca
        with patch("app.services.chat.ejecutor_herramientas.obtener_anio_activo_espacio", new=AsyncMock(return_value=2026)):
            comp2, _, msg2, _, _ = await ejecutar_consulta_tool(
                "consultar_distribucion_carreras", {}, db_falsa, espacio_id=2, req=req_bib
            )
        assert comp2 is None and "Acceso denegado" in msg2

        # Cache hit en tool válido (consultar_mapa_calor)
        mock_heat = [{"dia_semana": "Lunes", "hora": "11:00", "ocupacion_promedio": 180}]
        with (
            patch("app.services.chat.ejecutor_herramientas.obtener_anio_activo_espacio", new=AsyncMock(return_value=2026)),
            patch("app.services.attendance_service.AttendanceService.get_heatmap", new=AsyncMock(return_value=mock_heat)) as m_heat,
            patch("app.services.attendance_service.AttendanceService.get_occupancy_realtime", new=AsyncMock(return_value={})),
            patch("app.services.chat.ejecutor_herramientas.obtener_contexto_calendario_rango", new=AsyncMock(return_value=[])),
            patch("app.services.chat.ejecutor_herramientas.obtener_resumen_hechos_institucionales", new=AsyncMock(return_value="")),
        ):
            r1 = await ejecutar_consulta_tool("consultar_mapa_calor", {}, db_falsa, espacio_id=1, req=req_bib)
            r2 = await ejecutar_consulta_tool("consultar_mapa_calor", {}, db_falsa, espacio_id=1, req=req_bib)
        assert r1[0] == "HeatmapChart" and r2[0] == "HeatmapChart"
        assert m_heat.await_count == 1

        # Gráfico de contexto por gráfico_id inválido retorna vacío controlado
        with patch("app.services.chat.ejecutor_herramientas.obtener_anio_activo_espacio", new=AsyncMock(return_value=2026)):
            g_comp, _, _, _, _ = await resolver_datos_grafico_contexto(
                "grafico_inexistente", 1, "2026-10-01", "2026-10-07", db_falsa
            )
        assert g_comp is None

    asyncio.run(_run())


def test_procesador_chat_sync_sse_y_desconexion():
    async def _run():
        assert procesador_chat.detectar_intencion_visualizacion("Muéstrame un gráfico de barras") is True
        assert procesador_chat.detectar_intencion_visualizacion("Hola, buenos días") is False

        req_obj = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={"accept": "application/json"})
        user_obj = SimpleNamespace(id=10, rol="Director_Biblioteca", esp_id=1, email="dir@uct.cl")
        bg_tasks = MagicMock()
        db_sync = MagicMock(spec=AsyncSession)
        db_sync.close = AsyncMock()

        fake_client = MagicMock()
        fake_client.api_key = "test-key"
        fake_client.provider_id = "gemini"
        fake_client.default_model = "gemini-2.5-flash"
        fake_client.analyze_query_with_tools = AsyncMock(
            return_value={
                "type": "tool_call",
                "tool_name": "consultar_mapa_calor",
                "args": {},
                "model_used": "gemini-2.5-flash",
            }
        )
        fake_client.generate_response = AsyncMock(return_value="El pico es el lunes a las 11:00.")

        # 1) Flujo JSON síncrono: verifica cierre temprano de db y persistencia + cierre de reserva
        chat_req_sync = ChatRequest(
            prompt="¿Cuál es la hora pico de Biblioteca en gráfico?",
            dataset_tipo="biblioteca",
            session_id="sess-sync",
        )
        sess_persist = AsyncMock()
        sess_persist.commit = AsyncMock()
        conv_uuid = uuid.uuid4()

        with (
            patch.object(procesador_chat, "reservar_cuota_ia_usuario", new=AsyncMock(return_value=101)),
            patch.object(procesador_chat, "finalizar_reserva_cuota_ia", new=AsyncMock()) as m_fin_sync,
            patch.object(procesador_chat, "build_llm_client", new=AsyncMock(return_value=fake_client)),
            patch.object(
                procesador_chat,
                "ejecutar_consulta_tool",
                new=AsyncMock(return_value=("HeatmapChart", [{"h": 11}], "Resumen métrico", None, [{"h": 11}])),
            ),
            patch.object(procesador_chat, "AsyncSessionLocal", return_value=_AsyncSessionCtx(sess_persist)),
            patch.object(procesador_chat, "crear_conversacion", new=AsyncMock(return_value=SimpleNamespace(id=conv_uuid))),
            patch.object(procesador_chat, "agregar_mensaje", new=AsyncMock()),
            patch.object(procesador_chat, "obtener_anio_activo_espacio", new=AsyncMock(return_value=2026)),
            patch.object(procesador_chat, "validar_acceso_espacio", return_value=None),
        ):
            resp_sync = await procesador_chat.procesar_consulta_analitica(
                req_obj, chat_req_sync, bg_tasks, user_obj, db_sync, stream=False
            )
        db_sync.close.assert_awaited_once()
        m_fin_sync.assert_awaited_once()
        assert resp_sync.component == "HeatmapChart"
        assert "11:00" in resp_sync.explicacion

        # 2) Flujo SSE completo y desconexión abrupta (aclose + finalizar_reserva en finally)
        async def _stream_ok():
            yield "Hola "
            yield "mundo"

        fake_client.generate_narrative_stream = MagicMock(return_value=_stream_ok())
        db_sse = MagicMock(spec=AsyncSession)
        db_sse.close = AsyncMock()
        chat_req_sse = ChatRequest(prompt="Dame un resumen", dataset_tipo="biblioteca", session_id="sess-sse")

        with (
            patch.object(procesador_chat, "reservar_cuota_ia_usuario", new=AsyncMock(return_value=102)),
            patch.object(procesador_chat, "finalizar_reserva_cuota_ia", new=AsyncMock()) as m_fin_sse,
            patch.object(procesador_chat, "build_llm_client", new=AsyncMock(return_value=fake_client)),
            patch.object(
                procesador_chat,
                "ejecutar_consulta_tool",
                new=AsyncMock(return_value=("HeatmapChart", [{"h": 11}], "Resumen", None, None)),
            ),
            patch.object(procesador_chat, "AsyncSessionLocal", return_value=_AsyncSessionCtx(sess_persist)),
            patch.object(procesador_chat, "crear_conversacion", new=AsyncMock(return_value=SimpleNamespace(id=conv_uuid))),
            patch.object(procesador_chat, "agregar_mensaje", new=AsyncMock()),
            patch.object(procesador_chat, "obtener_anio_activo_espacio", new=AsyncMock(return_value=2026)),
            patch.object(procesador_chat, "validar_acceso_espacio", return_value=None),
        ):
            streaming_resp = await procesador_chat.procesar_consulta_analitica(
                req_obj, chat_req_sse, bg_tasks, user_obj, db_sse, stream=True
            )
            eventos = [chunk async for chunk in streaming_resp.body_iterator]
        assert any('"type": "meta"' in e for e in eventos)
        assert any('"type": "done"' in e for e in eventos)
        m_fin_sse.assert_awaited_once()

        # Simular desconexión temprana cerrando el iterador tras el primer evento
        cerrado = {"ok": False}

        async def _stream_largo():
            try:
                yield "Parte 1"
                yield "Parte 2"
            finally:
                cerrado["ok"] = True

        fake_client.generate_narrative_stream = MagicMock(return_value=_stream_largo())
        with (
            patch.object(procesador_chat, "reservar_cuota_ia_usuario", new=AsyncMock(return_value=103)),
            patch.object(procesador_chat, "finalizar_reserva_cuota_ia", new=AsyncMock()) as m_fin_disc,
            patch.object(procesador_chat, "build_llm_client", new=AsyncMock(return_value=fake_client)),
            patch.object(
                procesador_chat,
                "ejecutar_consulta_tool",
                new=AsyncMock(return_value=("HeatmapChart", [{"h": 11}], "Resumen", None, None)),
            ),
            patch.object(procesador_chat, "AsyncSessionLocal", return_value=_AsyncSessionCtx(sess_persist)),
            patch.object(procesador_chat, "crear_conversacion", new=AsyncMock(return_value=SimpleNamespace(id=conv_uuid))),
            patch.object(procesador_chat, "agregar_mensaje", new=AsyncMock()),
            patch.object(procesador_chat, "obtener_anio_activo_espacio", new=AsyncMock(return_value=2026)),
            patch.object(procesador_chat, "validar_acceso_espacio", return_value=None),
        ):
            streaming_abort = await procesador_chat.procesar_consulta_analitica(
                req_obj, chat_req_sse, bg_tasks, user_obj, crear_db_mock(), stream=True
            )
            it = streaming_abort.body_iterator
            primer_evento = await it.__anext__()
            assert "meta" in primer_evento
            await it.aclose()
        assert m_fin_disc.await_count == 1

    asyncio.run(_run())


def test_llm_client_esquemas_y_parsers():
    assert llm_client._limpiar_json_markdown('```json\n{"tool": "x"}\n```') == {"tool": "x"}
    with pytest.raises(json.JSONDecodeError):
        llm_client._limpiar_json_markdown("texto invalido")

    hist = llm_client._normalizar_historial_conversacion(
        [{"role": "user", "content": "Hola"}, {"role": "assistant", "content": "Buen día"}]
    )
    assert len(hist) == 2

    res_tool = llm_client._normalizar_resultado_tool_call(
        "consultar_mapa_calor", {"sala": "S1"}, 1, "2026-10-01", "2026-10-14", None, 2026
    )
    assert res_tool["type"] == "tool_call" and res_tool["tool_name"] == "consultar_mapa_calor"

    assert len(llm_client.obtener_esquema_herramientas_neutral(espacio_id=1)) > 5
    assert len(llm_client.obtener_herramientas_openai(espacio_id=2)) > 5
    assert len(llm_client.obtener_herramientas_claude(espacio_id=1)) > 5
    assert len(llm_client.get_gemini_tools(espacio_id=1)) >= 1
    assert any(p["id"] == "gemini" for p in llm_client.obtener_catalogo_proveedores())
    llm_client.limpiar_cache_clientes_llm()

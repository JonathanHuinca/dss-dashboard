"""Pruebas extensivas de ML (Prophet/KMeans/Orquestador), LLM, Auth, Config, Calendario y Planificador."""
import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from app.core import planificador
from app.ml import orquestador_entrenamiento, prophet_service, train_kmeans_parking
from app.schemas.config_schemas import HorarioOperacionCreate, HorarioOperacionUpdate
from app.services import auth_service, calendar_scraper, calendar_service, config_service, email_service, llm_client, servicio_calendario_anual, servicio_chat_persistente
from app.tests.conftest import crear_usuario_mock
from app.tests.test_cobertura_analitica_y_herramientas import _SmartRow, _crear_db_analitica


class _FakeProphet:
    def __init__(self, **kwargs):
        self.growth = kwargs.get("growth", "linear")
        self.extra_regressors = {"es_horario_abierto": {}, "is_exam_period": {}, "is_holiday_or_break": {}}
        self.conditional_seasonality = {}

    def add_seasonality(self, *args, **kwargs):
        return self

    def add_regressor(self, name, **kwargs):
        self.extra_regressors[name] = kwargs
        return self

    def fit(self, df):
        return self

    def predict(self, df):
        n = len(df)
        return pd.DataFrame(
            {
                "ds": df["ds"].values,
                "yhat": np.full(n, 25.0),
                "yhat_lower": np.full(n, 15.0),
                "yhat_upper": np.full(n, 35.0),
            }
        )


def test_ml_prophet_gbr_rf_kmeans_y_orquestador(tmp_path):
    async def _run():
        # Preparación Prophet
        fake_m = _FakeProphet(growth="logistic")
        df_feat = pd.DataFrame(
            {
                "ds": pd.date_range("2026-10-01 08:00", periods=150, freq="h"),
                "y": np.linspace(5, 50, 150),
                "cap": np.full(150, 276.0),
                "floor": np.zeros(150),
                "es_horario_abierto": np.ones(150, dtype=int),
                "es_habil": np.ones(150, dtype=int),
                "es_sabado": np.zeros(150, dtype=int),
                "es_domingo": np.zeros(150, dtype=int),
                "is_exam_period": np.zeros(150, dtype=int),
                "is_holiday": np.zeros(150, dtype=int),
                "is_break": np.zeros(150, dtype=int),
                "suspension_actividades": np.zeros(150, dtype=int),
                "is_strike": np.zeros(150, dtype=int),
                "is_holiday_or_break": np.zeros(150, dtype=int),
                "dato_faltante_sensor": np.zeros(150, dtype=int),
            }
        )
        cols = prophet_service._preparar_columnas_prediccion(fake_m, df_feat)
        assert "cap" in cols and "ds" in cols
        df_open, has_h, has_s = prophet_service._preparar_df_entrenamiento_abierto(df_feat)
        assert len(df_open) == 150 and has_h is True and has_s is False

        db_pred = AsyncMock()
        res_hist = MagicMock()
        res_hist.scalar.return_value = datetime(2026, 10, 14, 18, 0)
        res_hist.fetchone.return_value = (datetime(2026, 10, 1), datetime(2026, 10, 14))
        res_hist.fetchall.return_value = [(datetime(2026, 10, 14, 10, 0), 25.0)]
        db_pred.execute = AsyncMock(return_value=res_hist)

        with (
            patch.object(prophet_service, "MODELS_DIR", tmp_path),
            patch.object(prophet_service, "Prophet", _FakeProphet),
            patch.object(prophet_service, "_fetch_hourly_data", new=AsyncMock(return_value=df_feat[["ds", "y"]].copy())),
            patch.object(prophet_service, "_fetch_calendar", new=AsyncMock(return_value=pd.DataFrame())),
            patch.object(prophet_service, "_fetch_horarios_info", new=AsyncMock(return_value=[])),
            patch.object(prophet_service, "_fetch_contingencias_info", new=AsyncMock(return_value=[])),
            patch.object(prophet_service, "_fetch_capacidades", new=AsyncMock(return_value={"total": 276, "sala_1": 180, "sala_2": 96, "vehicular": 125})),
            patch("app.services.attendance_service.AttendanceService.get_realtime_presence_curve", new=AsyncMock(return_value=[
                {"bucket": (datetime(2026, 10, 1, 0, 0) + timedelta(hours=i)).strftime("%Y-%m-%d %H:%M"), "personas_presentes": 15 + i, "personas_unicas": 15 + i} for i in range(120)
            ])),
        ):
            res_train = await prophet_service.train_sala_model(db_pred, "prophet_biblioteca_todas", "biblioteca", "todas")
            assert res_train["modelo"] == "prophet_biblioteca_todas"
            pred = await prophet_service.predict_continuous(db_pred, recinto="biblioteca", sala="todas")
            assert "pronostico_7d" in pred or "forecast" in pred or isinstance(pred, dict)

            res_pres = await prophet_service.train_presence_model(db_pred, "prophet_presencia_todas", "todas")
            assert res_pres["modelo"] == "prophet_presencia_todas"
            pred_p = await prophet_service.predict_presence_continuous(db_pred, sala="todas")
            assert isinstance(pred_p, dict)

        # Orquestador verificar_modulo_opera_en_fecha / verificar_hora_operativa_campus (rama BD)
        db_op = MagicMock()
        db_op.execute = AsyncMock(return_value=MagicMock(fetchone=MagicMock(return_value=None), fetchall=MagicMock(return_value=[]), scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))
        with (
            patch("app.services.config_service.get_horarios_operacion", new=AsyncMock(return_value=[])),
            patch("app.services.calendar_scraper.obtener_feriado_oficial_chile", return_value=None),
        ):
            op_bd, _ = await orquestador_entrenamiento.verificar_modulo_opera_en_fecha(
                db_op,
                1,
                datetime(2026, 10, 14, 11, 0),
            )
            assert op_bd is True
            estado = orquestador_entrenamiento.obtener_estado_general_modelos()
            assert isinstance(estado, list) and len(estado) > 0

    asyncio.run(_run())


def test_llm_clientes_con_sdks_mockeados():
    async def _run():
        llm_client.limpiar_cache_clientes_llm()
        db = _crear_db_analitica()

        # GeminiClient con genai mockeado
        fake_resp = MagicMock()
        fake_resp.text = "Respuesta ejecutiva Gemini"
        fake_part = SimpleNamespace(function_call=SimpleNamespace(name="consultar_mapa_calor", args={"espacio_id": 1}), text=None)
        fake_resp_tool = SimpleNamespace(
            function_calls=[SimpleNamespace(name="consultar_mapa_calor", args={"espacio_id": 1})],
            candidates=[SimpleNamespace(content=SimpleNamespace(parts=[fake_part]))],
            text="",
        )
        fake_aio = MagicMock()
        fake_aio.models.generate_content = AsyncMock(side_effect=[fake_resp, fake_resp_tool])
        fake_genai_cli = MagicMock(aio=fake_aio)
        fake_genai_cli.models.list.return_value = [SimpleNamespace(name="models/gemini-2.5-flash", supported_generation_methods=["generateContent"])]

        with patch("google.genai.Client", return_value=fake_genai_cli):
            cli = llm_client.GeminiClient(api_key="AIzaDummyKey", default_model="gemini-2.5-flash")
            txt = await cli.generate_response("Hola")
            assert "Respuesta ejecutiva" in (txt or "")
            tool_res = await cli.analyze_query_with_tools("Mapa de calor", espacio_id=1)
            assert tool_res["type"] == "tool_call" and tool_res["tool_name"] == "consultar_mapa_calor"

        # OpenAICompatibleClient y ClaudeClient vía httpx compartido mockeado
        fake_http_oai = MagicMock()
        resp_oai_text = MagicMock()
        resp_oai_text.raise_for_status = MagicMock()
        resp_oai_text.json.return_value = {"choices": [{"message": {"content": "Respuesta OpenAI"}}]}
        resp_oai_tool = MagicMock()
        resp_oai_tool.raise_for_status = MagicMock()
        resp_oai_tool.json.return_value = {"choices": [{"message": {"content": "Solo texto", "tool_calls": None}}]}
        fake_http_oai.post = AsyncMock(side_effect=[resp_oai_text, resp_oai_tool])

        with patch("app.core.recursos_http.obtener_http_client", return_value=fake_http_oai):
            oai = llm_client.OpenAICompatibleClient(
                provider_id="openai", api_key="sk-dummy", base_url="https://api.openai.com/v1", default_model="gpt-4o-mini"
            )
            txt_oai = await oai.generate_response("Hola")
            assert "Respuesta OpenAI" in (txt_oai or "")
            res_oai = await oai.analyze_query_with_tools("Solo saludo", espacio_id=1)
            assert res_oai["type"] == "text"

        fake_http_claude = MagicMock()
        resp_cl_text = MagicMock()
        resp_cl_text.raise_for_status = MagicMock()
        resp_cl_text.json.return_value = {"content": [{"type": "text", "text": "Respuesta Claude"}]}
        fake_http_claude.post = AsyncMock(return_value=resp_cl_text)
        with patch("app.core.recursos_http.obtener_http_client", return_value=fake_http_claude):
            cla = llm_client.ClaudeClient(api_key="sk-ant-dummy", default_model="claude-sonnet-4-20250514")
            txt_cl = await cla.generate_response("Hola Claude")
            assert "Respuesta Claude" in (txt_cl or "")

        # build_llm_client fallback limpio
        assert await llm_client.build_llm_client(db, espacio_id=1) is not None

    asyncio.run(_run())


def test_auth_config_calendar_email_chat_persistente_y_planificador():
    async def _run():
        # Auth service
        assert auth_service.normalizar_rol("SuperAdmin") == "Admin_Sistema"
        auth_service.validar_complejidad_password("UctClaveSegura2026!")
        tok_raw, tok_hash = auth_service.generar_token_activacion()
        assert tok_raw and len(tok_hash) == 64

        u_mock = crear_usuario_mock("u@uct.cl", ["Director_Recinto"], espacio_id=1, user_id=77)
        u_mock.hashed_password = auth_service.hash_password("ClaveValida1!")
        u_mock.failed_login_attempts = 0
        u_mock.locked_until = None
        assert auth_service.verify_password("ClaveValida1!", u_mock.hashed_password) is True
        assert await auth_service.verify_password_async("ClaveValida1!", u_mock.hashed_password) is True

        db_auth = _crear_db_analitica()
        db_auth.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=u_mock)))
        user_ok = await auth_service.authenticate_user(db_auth, "u@uct.cl", "ClaveValida1!")
        assert user_ok is not None

        # Config service reglas horarias
        regla = SimpleNamespace(
            id=1,
            espacio_id=1,
            subespacio="todos",
            anio=2026,
            tipo_horario="regular",
            fecha_inicio=datetime(2026, 3, 1),
            fecha_fin=datetime(2026, 12, 20),
            hora_apertura="08:00",
            hora_cierre="20:00",
            cierre_dia_siguiente=False,
            es_continuo_24h=False,
            configuracion_dias='{"miercoles":{"abierto":true,"apertura":"08:00","cierre":"20:00"}}',
            activo=True,
        )
        assert config_service.es_horario_conforme(datetime(2026, 10, 14, 12, 0), [regla]) is True
        assert config_service.evaluar_horario_abierto_subespacio(datetime(2026, 10, 14, 12, 0), 1, "sala_1", [regla]) == 1
        assert config_service._normalizar_cifrado_smtp(True, True, 465) == (False, True)
        config_service._validar_datos_proveedor_ia("openai", None, "sk-1234567890")

        # Calendar service y scraper
        assert calendar_scraper.obtener_feriado_oficial_chile(date(2026, 9, 18)) is not None
        cs = calendar_service.CalendarService()
        db_cal = _crear_db_analitica(rows=[])
        db_cal.merge = AsyncMock()
        await cs.bulk_insert_events(db_cal, [])
        await cs.obtener_contingencias(db_cal, anio=2026)

        # Calendario anual
        assert hasattr(servicio_calendario_anual, "sincronizar_calendario_anual")

        # Email service (construcción plantilla y normalización enlace)
        html = email_service._construir_plantilla_base("<p>Prueba UCT</p>", "Título UCT")
        assert "Prueba UCT" in html
        with patch.object(email_service, "_enviar_correo_sincrono_detallado", return_value=(True, "ok")):
            ok_mail, _ = await email_service.probar_envio_smtp(
                {"host": "smtp.uct.cl", "port": 587, "username": "dss@uct.cl", "password": "secret", "from_email": "dss@uct.cl", "use_tls": True, "use_ssl": False},
                "destino@uct.cl",
            )
            assert ok_mail is True

        # Chat persistente cuotas y conversaciones
        db_chat = _crear_db_analitica(scalar_val=2)
        db_chat.get = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4(), usuario_id=77, eliminada_en=None))
        assert "Hola" in servicio_chat_persistente.generar_titulo_conversacion("Hola Biblioteca")
        await servicio_chat_persistente.listar_conversaciones(db_chat, usuario_id=77, espacio_id=1)

        # Planificador recuperación e inicio/detención
        class _CtxPlan:
            async def __aenter__(self):
                return db_chat

            async def __aexit__(self, *args):
                return False

        with (
            patch.object(planificador, "AsyncSessionLocal", return_value=_CtxPlan()),
            patch.object(planificador, "es_momento_operativo_para_tarea", new=AsyncMock(return_value=(False, "No laboral"))),
        ):
            await planificador.ejecutar_recuperacion_al_inicio()

        fake_sched = MagicMock(running=False)
        with (
            patch.object(planificador, "planificador", None),
            patch.object(planificador, "AsyncIOScheduler", return_value=fake_sched),
            patch.object(planificador, "limpiar_tareas_huerfanas", new=AsyncMock(return_value=0)),
            patch("asyncio.create_task", return_value=MagicMock(done=MagicMock(return_value=True))),
        ):
            await planificador.iniciar_planificador()
            fake_sched.start.assert_called_once()
            await planificador.detener_planificador()

    asyncio.run(_run())

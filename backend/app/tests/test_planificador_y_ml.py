"""Pruebas del planificador autónomo APScheduler y pipeline/inferencia ML."""
import asyncio
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from app.core import planificador
from app.core.planificador import (
    ReentranciaError,
    TareaNoEncontradaError,
    calcular_proxima_ejecucion_habil,
    es_momento_operativo_para_tarea,
    limpiar_tareas_huerfanas,
)
from app.ml import gestor_modelos, orquestador_entrenamiento, prophet_service
from app.ml.isolation_forest import detect_vehicular_anomalies
from app.ml.train_kmeans_parking import _compute_clusters_sync


class _AsyncSessionCtx:
    def __init__(self, sess):
        self._sess = sess

    async def __aenter__(self):
        return self._sess

    async def __aexit__(self, *args):
        return False


def test_es_momento_operativo_para_tarea_y_proxima_habil():
    async def _run():
        sess = AsyncMock()
        ctx_mock = orquestador_entrenamiento.ContextoOperativoPrecargado(
            horarios_por_espacio={},
            calendario_por_fecha={},
            contingencias=[],
        )

        # Jueves 15 de octubre de 2026 a las 10:00 (hora hábil estándar)
        jueves_10 = datetime(2026, 10, 15, 10, 0)
        op_live, msg_live = await es_momento_operativo_para_tarea(
            sess, "sincronizar_smart_campus_en_vivo", jueves_10, contexto=ctx_mock
        )
        assert op_live is True
        assert "Horario" in msg_live

        # Domingo no laboral
        domingo_10 = datetime(2026, 10, 18, 10, 0)
        op_ml_dom, _ = await es_momento_operativo_para_tarea(
            sess, "reentrenar_modelos_ml", domingo_10, contexto=ctx_mock
        )
        assert op_ml_dom is False

        # Consolidar nocturno lunes usa D-1 (domingo -> False)
        lunes_01 = datetime(2026, 10, 19, 1, 15)
        op_noc_lun, _ = await es_momento_operativo_para_tarea(
            sess, "consolidar_smart_campus_nocturno", lunes_01, contexto=ctx_mock
        )
        assert op_noc_lun is False

        # Tarea periódica general
        op_gen, _ = await es_momento_operativo_para_tarea(
            sess, "sincronizar_calendario_academico", jueves_10, contexto=ctx_mock
        )
        assert op_gen is True

        # Próxima ejecución hábil saltando domingo
        cursor_dom = datetime(2026, 10, 18, 5, 0, tzinfo=planificador.ZONA_HORARIA_CHILE)
        prox = await calcular_proxima_ejecucion_habil(
            sess, "reentrenar_modelos_ml", ahora_cl=cursor_dom, contexto=ctx_mock
        )
        assert prox is not None
        assert prox.astimezone(planificador.ZONA_HORARIA_CHILE).weekday() == 0

    asyncio.run(_run())


def test_limpiar_tareas_huerfanas():
    async def _run():
        sess = AsyncMock()
        res = MagicMock()
        res.rowcount = 3
        sess.execute = AsyncMock(return_value=res)
        sess.commit = AsyncMock()

        with patch.object(planificador, "AsyncSessionLocal", return_value=_AsyncSessionCtx(sess)):
            cant = await limpiar_tareas_huerfanas(al_iniciar=True)
        assert cant == 3
        sess.commit.assert_awaited_once()

    asyncio.run(_run())


def test_ejecutar_tarea_errores_reentrancia_exito_y_reintento():
    async def _run():
        with pytest.raises(TareaNoEncontradaError):
            await planificador.ejecutar_tarea("tarea_inexistente")

        # Caso ReentranciaError en ejecución manual cuando hay fila activa
        sess_reent = AsyncMock()
        activa_mock = MagicMock()
        activa_mock.scalars.return_value.first.return_value = SimpleNamespace(
            latido_en=datetime.now(timezone.utc).replace(tzinfo=None)
        )
        sess_reent.execute = AsyncMock(return_value=activa_mock)

        with (
            patch.object(planificador, "AsyncSessionLocal", return_value=_AsyncSessionCtx(sess_reent)),
            pytest.raises(ReentranciaError),
        ):
            await planificador.ejecutar_tarea("tarea_prueba", disparador="manual", usuario_id=1)

        # Caso ejecución automática omitida por reentrancia
        sess_omit = AsyncMock()
        sess_omit.execute = AsyncMock(return_value=activa_mock)
        sess_omit.add = MagicMock()
        sess_omit.commit = AsyncMock()
        sess_omit.refresh = AsyncMock()

        with patch.object(planificador, "AsyncSessionLocal", return_value=_AsyncSessionCtx(sess_omit)):
            res_omit = await planificador.ejecutar_tarea("tarea_prueba", disparador="programado")
        assert res_omit.estado == "omitido"

        # Caso ejecución exitosa de tarea_prueba
        no_activa = MagicMock()
        no_activa.scalars.return_value.first.return_value = None
        ej_id = uuid.uuid4()
        fila_final = SimpleNamespace(id=ej_id, estado="exitoso", tarea="tarea_prueba")

        sess_run = AsyncMock()
        sess_run.execute = AsyncMock(side_effect=[no_activa, MagicMock(), MagicMock()])
        sess_run.add = MagicMock()

        def _set_id_refresh(obj):
            if getattr(obj, "id", None) is None:
                obj.id = ej_id

        sess_run.commit = AsyncMock()
        sess_run.refresh = AsyncMock(side_effect=_set_id_refresh)
        sess_run.get = AsyncMock(return_value=fila_final)

        fake_info = {**planificador.CATALOGO_TAREAS["tarea_prueba"], "handler": AsyncMock(return_value={"ok": True})}
        with (
            patch.object(planificador, "AsyncSessionLocal", return_value=_AsyncSessionCtx(sess_run)),
            patch.dict(planificador.CATALOGO_TAREAS, {"tarea_prueba": fake_info}),
            patch.object(planificador, "_actualizar_latido_periodico", new=AsyncMock()),
        ):
            res_ok = await planificador.ejecutar_tarea("tarea_prueba", disparador="manual", usuario_id=7)
            tarea_bg = planificador._tareas_en_ejecucion_tasks.get(res_ok.id)
            if tarea_bg is not None:
                await tarea_bg
        assert sess_run.execute.await_count >= 3

        # Caso fallo en reentrenar_modelos_ml con planificador activo -> agenda reintento 30 min
        sess_fail = AsyncMock()
        sess_fail.execute = AsyncMock(side_effect=[no_activa, MagicMock(), MagicMock()])
        sess_fail.add = MagicMock()
        sess_fail.commit = AsyncMock()
        sess_fail.refresh = AsyncMock(side_effect=_set_id_refresh)
        sess_fail.get = AsyncMock(return_value=SimpleNamespace(id=ej_id, estado="fallido"))

        fake_ml_info = {
            **planificador.CATALOGO_TAREAS["reentrenar_modelos_ml"],
            "handler": AsyncMock(side_effect=RuntimeError("fallo ML simulado")),
        }
        fake_scheduler = MagicMock()
        fake_scheduler.running = True
        with (
            patch.object(planificador, "AsyncSessionLocal", return_value=_AsyncSessionCtx(sess_fail)),
            patch.dict(planificador.CATALOGO_TAREAS, {"reentrenar_modelos_ml": fake_ml_info}),
            patch.object(planificador, "_actualizar_latido_periodico", new=AsyncMock()),
            patch.object(planificador, "planificador", fake_scheduler),
        ):
            res_fail = await planificador.ejecutar_tarea("reentrenar_modelos_ml", disparador="programado")
            tarea_bg_fail = planificador._tareas_en_ejecucion_tasks.get(res_fail.id)
            if tarea_bg_fail is not None:
                await tarea_bg_fail
        fake_scheduler.add_job.assert_called_once()

    asyncio.run(_run())


def test_gestor_modelos_lru_async_y_hilo(tmp_path):
    async def _run():
        gestor_modelos._cache_modelos_memoria.clear()
        archivo = tmp_path / "modelo_test.joblib"
        archivo.write_bytes(b"dummy")

        assert gestor_modelos.cargar_modelo_en_memoria(tmp_path / "no_existe.joblib") is None

        obj_modelo = {"peso": 42}
        with patch.object(gestor_modelos.joblib, "load", return_value=obj_modelo) as m_load:
            c1 = gestor_modelos.cargar_modelo_en_memoria(archivo)
            c2 = gestor_modelos.cargar_modelo_en_memoria(archivo)
            assert c1 == {"peso": 42}
            assert c2 == {"peso": 42}
            assert m_load.call_count == 1

            # Async y ejecución en hilo
            c3 = await gestor_modelos.cargar_modelo_en_memoria_async(archivo)
            assert c3 == {"peso": 42}
            res_hilo = await gestor_modelos.ejecutar_inferencia_en_hilo(lambda a, b: a + b, 3, 4)
            assert res_hilo == 7

        gestor_modelos.invalidar_cache_modelo(archivo)
        assert len(gestor_modelos._cache_modelos_memoria) == 0

    asyncio.run(_run())


def test_orquestador_calendario_atomico_y_campeon(tmp_path):
    ctx = orquestador_entrenamiento.ContextoOperativoPrecargado(
        horarios_por_espacio={
            1: [
                SimpleNamespace(
                    id=1,
                    espacio_id=1,
                    anio=2026,
                    descripcion="Regular",
                    tipo_horario="regular",
                    fecha_inicio=datetime(2026, 3, 1),
                    fecha_fin=datetime(2026, 12, 20),
                    hora_apertura="08:00",
                    hora_cierre="20:00",
                    cierre_dia_siguiente=False,
                    es_continuo_24h=False,
                    configuracion_dias=json.dumps({"lunes": {"abierto": True, "apertura": "08:00", "cierre": "20:00"}}),
                    activo=True,
                ),
                SimpleNamespace(
                    id=2,
                    espacio_id=1,
                    anio=2026,
                    descripcion="Campaña Exámenes",
                    tipo_horario="campana_24h",
                    fecha_inicio=datetime(2026, 11, 20),
                    fecha_fin=datetime(2026, 11, 28),
                    hora_apertura="00:00",
                    hora_cierre="23:59",
                    cierre_dia_siguiente=False,
                    es_continuo_24h=True,
                    configuracion_dias=None,
                    activo=True,
                ),
            ]
        },
        calendario_por_fecha={
            date(2026, 10, 15): SimpleNamespace(
                hito="Suspensión académica",
                is_holiday=0,
                is_break=0,
                suspension_actividades=1,
                is_strike_federado=0,
            ),
            date(2026, 11, 22): SimpleNamespace(
                hito="Domingo campaña",
                is_holiday=0,
                is_break=0,
                suspension_actividades=0,
                is_strike_federado=0,
            ),
        },
        contingencias=[
            SimpleNamespace(
                fecha_inicio=date(2026, 10, 20),
                fecha_fin=date(2026, 10, 21),
                espacio_id=1,
                titulo="Mantención eléctrica",
                tipo="cierre",
            )
        ],
    )

    op_susp, _ = orquestador_entrenamiento.evaluar_modulo_opera_en_fecha_memoria(
        ctx, 1, datetime(2026, 10, 15, 10, 0)
    )
    assert op_susp is False

    op_cont, _ = orquestador_entrenamiento.evaluar_modulo_opera_en_fecha_memoria(
        ctx, 1, datetime(2026, 10, 20, 10, 0)
    )
    assert op_cont is False

    op_24h, msg_24h = orquestador_entrenamiento.evaluar_modulo_opera_en_fecha_memoria(
        ctx, 1, datetime(2026, 11, 22, 3, 0)
    )
    assert op_24h is True
    assert "24h" in msg_24h

    op_hora, _ = orquestador_entrenamiento.evaluar_hora_operativa_campus_memoria(
        ctx, datetime(2026, 10, 14, 11, 0)
    )
    assert op_hora is True

    # Escritura atómica, metadatos y evaluación de campeón Prophet
    with patch.object(orquestador_entrenamiento, "DIRECTORIO_MODELOS", tmp_path):
        src = tmp_path / "cand.joblib"
        dst = tmp_path / "act.joblib"
        src.write_bytes(b"v2")
        orquestador_entrenamiento._promover_archivo_atomico(src, dst)
        assert dst.read_bytes() == b"v2"

        meta = {"clave": "k1", "version": "20261126", "wape": 12.5, "mae": 2.1, "estado": "activo", "es_campeon": True}
        orquestador_entrenamiento._guardar_metadatos_campeon("k1", meta)
        leido = orquestador_entrenamiento._leer_metadatos_campeon("k1", {"archivo_activo": "act.joblib"})
        assert leido["wape"] == 12.5

        class _FakeProphetEval:
            def predict(self, df_in):
                return pd.DataFrame({"yhat": [10.0, 20.0]})

        with (
            patch.object(orquestador_entrenamiento.joblib, "load", return_value=_FakeProphetEval()),
            patch("app.ml.prophet_service._preparar_columnas_prediccion", return_value=["ds"]),
        ):
            wape, mae = orquestador_entrenamiento._evaluar_campeon_existente(
                "k1",
                "act.joblib",
                "Prophet",
                pd.DataFrame({"ds": pd.date_range("2026-10-15", periods=2, freq="h")}),
                np.array([12.0, 18.0]),
            )
        assert wape == 13.33
        assert mae == 2.0


def test_isolation_forest_prophet_y_kmeans(tmp_path):
    # Isolation Forest
    with pytest.raises(ValueError):
        detect_vehicular_anomalies(pd.DataFrame({"hora_ingreso": [10]}))

    df_chico = pd.DataFrame({"hora_ingreso": [9, 10], "permanencia": [30, 40], "frecuencia": [1, 2]})
    assert detect_vehicular_anomalies(df_chico).empty

    df_valido = pd.DataFrame(
        {
            "hora_ingreso": [9, 10, 11, 10, 9, 11, 10, 9, 10, 11, 10, 9, 10, 11, 3],
            "permanencia": [60, 55, 65, 58, 62, 60, 57, 59, 61, 58, 60, 55, 63, 59, 950],
            "frecuencia": [2, 2, 1, 2, 2, 1, 2, 2, 1, 2, 2, 1, 2, 2, 50],
        }
    )
    df_orig = df_valido.copy()
    anomalias = detect_vehicular_anomalies(df_valido)
    assert df_valido.equals(df_orig)
    assert "anomaly_score" in anomalias.columns

    # Prophet helpers puros
    assert prophet_service._normalizar_sector_vehicular("  csf11  ") == "CSF11"
    assert prophet_service._normalizar_sector_vehicular("invalido") == "todos"
    cont_sensor = [{"tipo": "falla_sensor", "espacio_id": 1, "subespacio": "todos", "fecha_inicio": date(2026, 10, 14), "fecha_fin": date(2026, 10, 14)}]
    assert prophet_service._evaluar_dato_faltante_sensor(datetime(2026, 10, 14, 11, 0), 1, "todas", cont_sensor) == 1
    assert prophet_service._evaluar_dato_faltante_sensor(datetime(2026, 10, 14, 23, 0), 1, "todas", []) == 0

    df_raw = pd.DataFrame(
        {
            "ds": pd.date_range("2026-10-12 08:00:00", periods=6, freq="h"),
            "y": [10.0, 20.0, 0.0, 25.0, 30.0, 15.0],
        }
    )
    df_cal = pd.DataFrame({
        "fecha": pd.date_range("2026-10-12 00:00:00", periods=1, freq="D"),
        "is_exam_period": [1],
        "is_holiday": [0],
        "is_break": [0],
        "suspension_actividades": [0],
        "is_strike": [0],
    })
    df_feat = prophet_service._enrich_features(df_raw, df_cal, sala="todas")
    assert "es_horario_abierto" in df_feat.columns
    assert "es_habil" in df_feat.columns
    assert prophet_service._hiperparametros_prophet_por_recinto("vehicular")["changepoint_prior_scale"] == 0.05
    assert prophet_service._hiperparametros_prophet_por_recinto("biblioteca")["changepoint_prior_scale"] == 0.10

    # KMeans parking clustering
    df_veh = pd.DataFrame(
        {
            "patente_hash": [f"P{i}" for i in range(12)],
            "dias_totales": [1, 1, 2, 2, 5, 6, 7, 8, 12, 14, 15, 16],
            "permanencia_avg_min": [20, 25, 30, 35, 180, 200, 210, 220, 480, 500, 520, 510],
            "hora_llegada_avg": [11, 12, 14, 15, 9, 9, 10, 10, 8, 8, 8, 8],
            "tasa_jornada_extrema": [0, 0, 0, 0, 10, 15, 20, 25, 80, 90, 95, 100],
        }
    )
    with patch("app.ml.train_kmeans_parking.MODEL_PATH", tmp_path / "kmeans_parking.joblib"):
        clusters_res = _compute_clusters_sync(df_veh)
    assert clusters_res["total_vehiculos_analizados"] == 12
    assert len(clusters_res["distribucion"]) == 3

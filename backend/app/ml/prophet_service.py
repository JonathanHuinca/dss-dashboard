"""
prophet_service.py — Servicio jerárquico de predicción de aforo horario con Prophet (RF27).

Características:
  1. Enfoque jerárquico por sala para Biblioteca:
     - Sala 1 (CSF02): Operación diurna regular (capacidad dinámica de salas_biblioteca).
     - Sala 2 (CSF04 Pecera): Operación diurna y régimen nocturno 24h/23h en épocas de exámenes.
     - Global (Todas las Salas): Suma jerárquica directa (Sala 1 + Sala 2).
  2. Vehicular: Pronóstico de entradas vehiculares para Estacionamiento (espacio_id = 2).
  3. Regularización horaria: Relleno explícito de ceros en horas de cierre (elimina interpolación fantasma).
  4. Parsimonia de regresores:
     - es_horario_abierto: Calculado dinámicamente desde horarios_operacion y calendario.
     - is_exam_period: Época de exámenes / solemnes.
     - is_holiday_or_break: Feriados y semanas de receso.
  5. Salida continua de 14 días (336 horas):
     - Últimos 7 días (168 horas) de datos reales empíricos.
     - Próximos 7 días (168 horas) de proyección futura continua con intervalos de incertidumbre del 80%.
"""
import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from prophet import Prophet
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.gestor_modelos import cargar_modelo_en_memoria, ejecutar_inferencia_en_hilo

logger = logging.getLogger("uvicorn.error")

MODELS_DIR = Path(__file__).resolve().parents[2] / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

MODELOS_SALA = {
    "sala1": "prophet_biblioteca_sala1",
    "sala2": "prophet_biblioteca_sala2",
    "todas": "prophet_biblioteca_todas",
    "vehicular": "prophet_vehicular",
}

TRAIN_RATIO = 0.85
MIN_ROWS_REQUIRED = 100


# ---------------------------------------------------------------------------
# Helpers de persistencia
# ---------------------------------------------------------------------------

def _active_path(modelo_key: str) -> Path:
    return MODELS_DIR / f"{modelo_key}_active.joblib"


def _versioned_path(modelo_key: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    return MODELS_DIR / f"{modelo_key}_v{ts}.joblib"


def _save_model(model: Prophet, modelo_key: str) -> Path:
    versioned = _versioned_path(modelo_key)
    joblib.dump(model, versioned)
    active = _active_path(modelo_key)
    shutil.copy2(versioned, active)
    logger.info(f"[Prophet] Modelo {modelo_key} guardado: {versioned.name}")
    _prune_old_models(modelo_key, keep=3)
    return versioned


def _prune_old_models(modelo_key: str, keep: int = 3) -> None:
    pattern = f"{modelo_key}_v*.joblib"
    versions = sorted(MODELS_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in versions[keep:]:
        old.unlink(missing_ok=True)


def load_active_model(modelo_key: str) -> Optional[Prophet]:
    path = _active_path(modelo_key)
    return cargar_modelo_en_memoria(path)



def active_model_date(modelo_key: str) -> Optional[str]:
    path = _active_path(modelo_key)
    if not path.exists():
        return None
    ts = datetime.fromtimestamp(path.stat().st_mtime)
    return ts.strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------------------
# Consultas de Base de Datos y Horarios
# ---------------------------------------------------------------------------

async def _fetch_capacidades(session: AsyncSession) -> Dict[str, int]:
    """
    Obtiene dinámicamente las capacidades de salas y recinto para no hardcodearlas.
    """
    sql_salas = text("SELECT codigo, capacidad_asientos FROM salas_biblioteca")
    res_salas = await session.execute(sql_salas)
    capacidades = {"sala1": 200, "sala2": 226, "todas": 426, "vehicular": 150}

    for row in res_salas.fetchall():
        if "CSF02" in row.codigo:
            capacidades["sala1"] = int(row.capacidad_asientos)
        elif "CSF04" in row.codigo:
            capacidades["sala2"] = int(row.capacidad_asientos)

    capacidades["todas"] = capacidades["sala1"] + capacidades["sala2"]

    sql_espacio = text("SELECT id, capacidad_max FROM espacios WHERE id IN (1, 2)")
    res_esp = await session.execute(sql_espacio)
    for row in res_esp.fetchall():
        if row.id == 1 and row.capacidad_max:
            capacidades["todas"] = int(row.capacidad_max)
        elif row.id == 2 and row.capacidad_max:
            capacidades["vehicular"] = int(row.capacidad_max)

    return capacidades


async def _fetch_horarios_info(session: AsyncSession, espacio_id: int = 1) -> list[dict]:
    sql = text("""
        SELECT 
            id,
            espacio_id,
            subespacio,
            anio,
            tipo_horario,
            fecha_inicio,
            fecha_fin,
            hora_apertura,
            hora_cierre,
            cierre_dia_siguiente,
            configuracion_dias,
            es_continuo_24h,
            activo
        FROM horarios_operacion
        WHERE espacio_id = :espacio_id AND activo = 1
    """)
    res = await session.execute(sql, {"espacio_id": espacio_id})
    return [dict(r._mapping) for r in res.fetchall()]


async def _fetch_contingencias_info(session: AsyncSession, espacio_id: int = 1) -> list[dict]:
    sql = text("""
        SELECT
            id,
            fecha_inicio,
            fecha_fin,
            tipo,
            espacio_id,
            subespacio,
            hora_inicio,
            hora_fin,
            implica_cierre_total
        FROM contingencias_academicas
        WHERE (espacio_id IS NULL OR espacio_id = :espacio_id)
    """)
    res = await session.execute(sql, {"espacio_id": espacio_id})
    return [dict(r._mapping) for r in res.fetchall()]


async def _fetch_calendar(session: AsyncSession) -> pd.DataFrame:
    sql = text("""
        SELECT
            fecha,
            CAST(is_holiday AS INT) AS is_holiday,
            CAST(is_break AS INT) AS is_break,
            CAST(is_exam_period AS INT) AS is_exam_period,
            CAST(suspension_actividades AS INT) AS suspension_actividades,
            CASE WHEN (is_strike_federado = 1 OR is_strike_carrera = 1) THEN 1 ELSE 0 END AS is_strike
        FROM calendario_academico
        ORDER BY fecha ASC
    """)
    res = await session.execute(sql)
    rows = res.fetchall()
    if not rows:
        return pd.DataFrame(columns=["fecha", "is_holiday", "is_break", "is_exam_period", "suspension_actividades", "is_strike"])
    df = pd.DataFrame(rows, columns=["fecha", "is_holiday", "is_break", "is_exam_period", "suspension_actividades", "is_strike"])
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df


def _calcular_es_abierto(dt: datetime, sala: str, es_24h: bool = False, es_feriado: bool = False) -> int:
    """
    Regla determinista de horario:
    - Sala 1: L-J 08:30-20:30, V 08:30-19:30, S 10:30-13:30, D cerrado. Cierre nocturno 100%.
    - Sala 2: Horario regular + apertura 24h cuando es_24h está activo.
    """
    if es_feriado and not es_24h:
        return 0

    if es_24h and sala in ("sala2", "todas", "biblioteca"):
        return 1

    dow = dt.weekday()
    if dow == 6:  # Domingo
        return 0

    hr = dt.hour
    if dow == 5:  # Sábado
        return 1 if (10 <= hr <= 13) else 0
    if dow == 4:  # Viernes
        return 1 if (8 <= hr <= 19) else 0
    return 1 if (8 <= hr <= 20) else 0  # Lunes a Jueves


async def _fetch_hourly_data(session: AsyncSession, recinto: str, sala: str = "todas") -> pd.DataFrame:
    """
    Obtiene la serie horaria regularizada con ceros para el recinto o sala específica.
    """
    if recinto == "vehicular":
        sql = text("""
            SELECT
                DATEADD(hour, DATEDIFF(hour, CONVERT(DATETIME2, '2000-01-01T00:00:00', 126), time), CONVERT(DATETIME2, '2000-01-01T00:00:00', 126)) as ds,
                COUNT(*) as y
            FROM eventos_vehiculares
            WHERE espacio_id = 2 AND direccion = 'entrada'
            GROUP BY DATEADD(hour, DATEDIFF(hour, CONVERT(DATETIME2, '2000-01-01T00:00:00', 126), time), CONVERT(DATETIME2, '2000-01-01T00:00:00', 126))
            ORDER BY ds ASC
        """)
        res = await session.execute(sql)
    else:
        door_filter = ""
        if sala == "sala1":
            door_filter = "AND door_entrada LIKE 'CSF02%'"
        elif sala == "sala2":
            door_filter = "AND door_entrada LIKE 'CSF04%'"

        sql = text(f"""
            SELECT 
                DATEADD(hour, DATEDIFF(hour, CONVERT(DATETIME2, '2000-01-01T00:00:00', 126), time), CONVERT(DATETIME2, '2000-01-01T00:00:00', 126)) as ds,
                COUNT(*) as y
            FROM eventos_asistencia
            WHERE espacio_id = 1 AND salida_imputada = 0 {door_filter}
            GROUP BY DATEADD(hour, DATEDIFF(hour, CONVERT(DATETIME2, '2000-01-01T00:00:00', 126), time), CONVERT(DATETIME2, '2000-01-01T00:00:00', 126))
            ORDER BY ds ASC
        """)
        res = await session.execute(sql)

    rows = res.fetchall()
    if not rows:
        return pd.DataFrame(columns=["ds", "y"])

    df = pd.DataFrame(rows, columns=["ds", "y"])
    df["ds"] = pd.to_datetime(df["ds"]).dt.tz_localize(None)

    # Grilla regular continua de 1h para rellenar las horas cerradas con 0
    full_idx = pd.date_range(df["ds"].min(), df["ds"].max(), freq="1h")
    df = df.set_index("ds").reindex(full_idx, fill_value=0).reset_index()
    df.columns = ["ds", "y"]
    df["y"] = pd.to_numeric(df["y"], errors="coerce").fillna(0).clip(lower=0)
    return df


def _enrich_features(
    df: pd.DataFrame,
    df_cal: pd.DataFrame,
    sala: str,
    horarios: Optional[list[dict]] = None,
    contingencias: Optional[list[dict]] = None,
    espacio_id: int = 1,
) -> pd.DataFrame:
    from app.services.config_service import evaluar_horario_abierto_subespacio

    df = df.copy()
    df["_fecha"] = df["ds"].dt.normalize()
    if not df_cal.empty:
        df = df.merge(df_cal, left_on="_fecha", right_on="fecha", how="left").fillna(0)
    else:
        df["is_holiday"] = 0
        df["is_break"] = 0
        df["is_exam_period"] = 0
        df["suspension_actividades"] = 0
        df["is_strike"] = 0

    df["is_holiday"] = df["is_holiday"].astype(int)
    df["is_break"] = df["is_break"].astype(int)
    df["is_exam_period"] = df["is_exam_period"].astype(int)
    # Paro: los recintos siguen abiertos pero los alumnos no tienen clases presenciales
    df["is_strike"] = df["is_strike"].astype(int)

    # Bandera dinámica 24h: exámenes en períodos de cierre o campaña (junio, julio, noviembre, diciembre)
    es_24h_mask = (df["is_exam_period"] == 1) & (df["ds"].dt.month.isin([6, 7, 11, 12]))

    if horarios is not None:
        abierto_vals = [
            evaluar_horario_abierto_subespacio(
                dt=row.ds.to_pydatetime() if hasattr(row.ds, "to_pydatetime") else row.ds,
                espacio_id=espacio_id,
                subespacio=sala,
                horarios=horarios,
                contingencias=contingencias,
                es_feriado_oficial=bool(row.is_holiday == 1),
                es_24h_automatico=bool(es_24h_mask.iloc[idx]),
            )
            for idx, row in df.iterrows()
        ]
    else:
        abierto_vals = [
            _calcular_es_abierto(row.ds, sala=sala, es_24h=bool(es_24h_mask.iloc[idx]), es_feriado=bool(row.is_holiday == 1))
            for idx, row in df.iterrows()
        ]
    df["es_horario_abierto"] = abierto_vals

    cols_to_drop = [c for c in ["_fecha", "fecha", "is_holiday", "suspension_actividades"] if c in df.columns]
    df.drop(columns=cols_to_drop, inplace=True)
    return df


# ---------------------------------------------------------------------------
# Pipeline de Entrenamiento
# ---------------------------------------------------------------------------

def _build_prophet() -> Prophet:
    model = Prophet(
        seasonality_mode="additive",
        daily_seasonality=True,
        weekly_seasonality=True,
        yearly_seasonality=False,
        changepoint_prior_scale=0.05,
        seasonality_prior_scale=10.0,
        interval_width=0.80,
    )
    model.add_seasonality(name="diaria_uct", period=1, fourier_order=8)
    model.add_seasonality(name="semanal_uct", period=7, fourier_order=4)
    model.add_regressor("es_horario_abierto", standardize=False)
    model.add_regressor("is_exam_period", standardize=False)
    model.add_regressor("is_break", standardize=False)
    model.add_regressor("is_strike", standardize=False)
    return model


async def train_sala_model(session: AsyncSession, modelo_key: str, recinto: str, sala: str) -> dict:
    logger.info(f"[Prophet] Iniciando entrenamiento modelo={modelo_key} (recinto={recinto}, sala={sala})")
    df = await _fetch_hourly_data(session, recinto=recinto, sala=sala)
    if len(df) < MIN_ROWS_REQUIRED:
        raise ValueError(f"Datos insuficientes para '{modelo_key}': {len(df)} filas.")

    cal = await _fetch_calendar(session)
    espacio_id_entrenamiento = 2 if recinto == "vehicular" else 1
    horarios_cfg = await _fetch_horarios_info(session, espacio_id=espacio_id_entrenamiento)
    contingencias_cfg = await _fetch_contingencias_info(session, espacio_id=espacio_id_entrenamiento)
    df = _enrich_features(
        df,
        cal,
        sala=sala,
        horarios=horarios_cfg,
        contingencias=contingencias_cfg,
        espacio_id=espacio_id_entrenamiento,
    )

    split_idx = int(len(df) * TRAIN_RATIO)
    train_df = df.iloc[:split_idx].copy()
    test_df = df.iloc[split_idx:].copy()

    regressors = ["es_horario_abierto", "is_exam_period", "is_break", "is_strike"]
    model = _build_prophet()

    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model.fit(train_df[["ds", "y"] + regressors])

    # Evaluación sobre test set
    test_features = test_df[["ds"] + regressors].copy()
    forecast_test = model.predict(test_features)

    y_true = test_df["y"].values
    y_pred = np.clip(forecast_test["yhat"].values, a_min=0, a_max=None)
    # Forzar a 0 en horas cerradas
    y_pred[test_df["es_horario_abierto"].values == 0] = 0.0

    denom = np.sum(y_true)
    wape = float(100.0 * np.sum(np.abs(y_true - y_pred)) / denom) if denom > 0 else 0.0
    mae = float(np.mean(np.abs(y_true - y_pred)))

    versioned_path = _save_model(model, modelo_key)

    return {
        "modelo": modelo_key,
        "recinto": recinto,
        "sala": sala,
        "train_rows": len(train_df),
        "test_rows": len(test_df),
        "mae": round(mae, 2),
        "wape": round(wape, 2),
        "path": str(versioned_path),
        "trained_at": datetime.now().isoformat(),
    }


async def train_all(session: AsyncSession) -> list[dict]:
    """
    Entrena los modelos jerárquicos de biblioteca (Sala 1, Sala 2 y Global) y vehicular.
    """
    tasks = [
        ("prophet_biblioteca_sala1", "biblioteca", "sala1"),
        ("prophet_biblioteca_sala2", "biblioteca", "sala2"),
        ("prophet_biblioteca_todas", "biblioteca", "todas"),
        ("prophet_vehicular", "vehicular", "todas"),
    ]
    results = []
    for m_key, rec, sl in tasks:
        try:
            res = await train_sala_model(session, m_key, rec, sl)
            results.append(res)
        except Exception as e:
            logger.error(f"[Prophet] Error entrenando {m_key}: {e}", exc_info=True)
            results.append({"modelo": m_key, "error": str(e)})
    return results


# ---------------------------------------------------------------------------
# Predicción Continua (7 Días Históricos Reales + 7 Días Proyección = 14 Días)
# ---------------------------------------------------------------------------

async def predict_continuous(
    session: AsyncSession,
    recinto: str = "biblioteca",
    sala: str = "todas",
) -> Dict[str, Any]:
    """
    Retorna 14 días continuos (336 puntos horarios):
    - 7 días históricos reales anteriores (168 horas empíricas).
    - 7 días proyectados a futuro (168 horas Prophet con intervalos de confianza del 80%).
    Soporta desglose por sala ('todas', 'sala1', 'sala2').
    """
    capacidades = await _fetch_capacidades(session)
    cap_sala = capacidades.get(sala, capacidades.get("todas", 426))

    # Determinar fecha de anclaje (máximo tiempo real en la base de datos)
    if recinto == "vehicular":
        res_t = await session.execute(text("SELECT MAX(time) FROM eventos_vehiculares WHERE espacio_id = 2"))
    else:
        res_t = await session.execute(text("SELECT MAX(time) FROM eventos_asistencia WHERE espacio_id = 1"))
    max_time_val = res_t.scalar()
    anchor_dt = (max_time_val or datetime.utcnow()).replace(minute=0, second=0, microsecond=0)

    # 1. Extraer los últimos 10 días de datos reales (240 horas completas hasta anchor_dt inclusive)
    h_start = anchor_dt - timedelta(hours=239)
    h_end_exclusive = anchor_dt + timedelta(hours=1)
    door_filter = ""
    if recinto == "biblioteca":
        if sala == "sala1":
            door_filter = "AND door_entrada LIKE 'CSF02%'"
        elif sala == "sala2":
            door_filter = "AND door_entrada LIKE 'CSF04%'"

        sql_hist = text(f"""
            SELECT 
                DATEADD(hour, DATEDIFF(hour, CONVERT(DATETIME2, '2000-01-01T00:00:00', 126), time), CONVERT(DATETIME2, '2000-01-01T00:00:00', 126)) as ds,
                COUNT(*) as actual
            FROM eventos_asistencia
            WHERE espacio_id = 1 AND salida_imputada = 0 {door_filter}
              AND time >= :h_start AND time < :h_end_exclusive
            GROUP BY DATEADD(hour, DATEDIFF(hour, CONVERT(DATETIME2, '2000-01-01T00:00:00', 126), time), CONVERT(DATETIME2, '2000-01-01T00:00:00', 126))
            ORDER BY ds ASC
        """)
    else:
        sql_hist = text("""
            SELECT 
                DATEADD(hour, DATEDIFF(hour, CONVERT(DATETIME2, '2000-01-01T00:00:00', 126), time), CONVERT(DATETIME2, '2000-01-01T00:00:00', 126)) as ds,
                COUNT(*) as actual
            FROM eventos_vehiculares
            WHERE espacio_id = 2 AND direccion = 'entrada'
              AND time >= :h_start AND time < :h_end_exclusive
            GROUP BY DATEADD(hour, DATEDIFF(hour, CONVERT(DATETIME2, '2000-01-01T00:00:00', 126), time), CONVERT(DATETIME2, '2000-01-01T00:00:00', 126))
            ORDER BY ds ASC
        """)

    res_hist = await session.execute(sql_hist, {"h_start": h_start, "h_end_exclusive": h_end_exclusive})
    df_hist_raw = pd.DataFrame(res_hist.fetchall(), columns=["ds", "actual"])
    df_hist_raw["ds"] = pd.to_datetime(df_hist_raw["ds"]).dt.tz_localize(None)

    # Grilla continua de exactamente 168 horas históricas (desde h_start hasta anchor_dt inclusive)
    hist_idx = pd.date_range(h_start, anchor_dt, freq="1h")
    df_hist = df_hist_raw.set_index("ds").reindex(hist_idx, fill_value=0).reset_index()
    df_hist.columns = ["ds", "actual"]

    cal = await _fetch_calendar(session)
    espacio_id_actual = 2 if recinto == "vehicular" else 1
    horarios_cfg = await _fetch_horarios_info(session, espacio_id=espacio_id_actual)
    contingencias_cfg = await _fetch_contingencias_info(session, espacio_id=espacio_id_actual)

    # 2. Generar predicción futura para los próximos 7 días (exactamente 168 horas desde anchor_dt + 1h)
    future_dates = [anchor_dt + timedelta(hours=h) for h in range(1, 169)]
    df_fut_base = pd.DataFrame({"ds": future_dates})
    df_fut = _enrich_features(
        df_fut_base,
        cal,
        sala=sala,
        horarios=horarios_cfg,
        contingencias=contingencias_cfg,
        espacio_id=espacio_id_actual,
    )
    if recinto == "biblioteca" and sala == "todas":
        df_fut_s1 = _enrich_features(
            df_fut_base, cal, sala="sala1", horarios=horarios_cfg, contingencias=contingencias_cfg, espacio_id=1
        )
        df_fut_s2 = _enrich_features(
            df_fut_base, cal, sala="sala2", horarios=horarios_cfg, contingencias=contingencias_cfg, espacio_id=1
        )
    else:
        df_fut_s1 = df_fut
        df_fut_s2 = df_fut

    # Cargar modelos según selección jerárquica
    regressors = ["es_horario_abierto", "is_exam_period", "is_break", "is_strike"]

    def _calcular_predicciones_sincronas() -> Tuple[pd.DataFrame, str]:
        def _infer_single(m_key: str, df_features: pd.DataFrame) -> pd.DataFrame:
            m = load_active_model(m_key)
            if not m:
                return pd.DataFrame({"yhat": [0.0]*168, "yhat_lower": [0.0]*168, "yhat_upper": [0.0]*168})
            pred = m.predict(df_features[["ds"] + regressors])
            yhat = np.clip(pred["yhat"].values, 0, None)
            lower = np.clip(pred["yhat_lower"].values, 0, None)
            upper = np.clip(pred["yhat_upper"].values, 0, None)

            # Forzar a cero en horas de cierre de esa sala específica
            cerrado_mask = df_features["es_horario_abierto"].values == 0
            yhat[cerrado_mask] = 0.0
            lower[cerrado_mask] = 0.0
            upper[cerrado_mask] = 0.0

            return pd.DataFrame({"yhat": yhat, "yhat_lower": lower, "yhat_upper": upper})

        if recinto == "vehicular":
            return _infer_single(MODELOS_SALA["vehicular"], df_fut), MODELOS_SALA["vehicular"]
        elif sala == "sala1":
            return _infer_single(MODELOS_SALA["sala1"], df_fut), MODELOS_SALA["sala1"]
        elif sala == "sala2":
            return _infer_single(MODELOS_SALA["sala2"], df_fut), MODELOS_SALA["sala2"]
        else:  # Todas / Global: Suma jerárquica Sala 1 + Sala 2 respetando horarios y suspensiones de cada sala
            df_s1 = _infer_single(MODELOS_SALA["sala1"], df_fut_s1)
            df_s2 = _infer_single(MODELOS_SALA["sala2"], df_fut_s2)
            if df_s1["yhat"].sum() == 0 and df_s2["yhat"].sum() == 0:
                return _infer_single(MODELOS_SALA["todas"], df_fut), MODELOS_SALA["todas"]
            return pd.DataFrame({
                "yhat": df_s1["yhat"] + df_s2["yhat"],
                "yhat_lower": df_s1["yhat_lower"] + df_s2["yhat_lower"],
                "yhat_upper": df_s1["yhat_upper"] + df_s2["yhat_upper"],
            }), MODELOS_SALA["todas"]

    df_pred, active_key = await ejecutar_inferencia_en_hilo(_calcular_predicciones_sincronas)


    # 3. Construir listas de salida
    puntos_historicos = [
        {
            "ds": row.ds.isoformat(),
            "actual": float(row.actual),
            "yhat": float(row.actual),
            "yhat_lower": float(row.actual),
            "yhat_upper": float(row.actual),
            "es_abierto": int(row.actual > 0),
        }
        for row in df_hist.itertuples()
    ]

    puntos_pronostico = []
    for idx, row in df_fut.iterrows():
        yhat_val = round(float(df_pred["yhat"].iloc[idx]), 1)
        low_val = round(float(df_pred["yhat_lower"].iloc[idx]), 1)
        up_val = round(float(df_pred["yhat_upper"].iloc[idx]), 1)
        puntos_pronostico.append({
            "ds": row["ds"].isoformat(),
            "actual": None,
            "yhat": yhat_val,
            "yhat_lower": low_val,
            "yhat_upper": up_val,
            "es_abierto": int(row["es_horario_abierto"]),
        })

    # Línea continua unificada de 336 puntos (168 reales + 168 pronosticados)
    puntos_totales = puntos_historicos + puntos_pronostico

    model_date = active_model_date(active_key)
    status_str = "ok" if model_date else "fallback"

    return {
        "recinto": recinto,
        "sala": sala,
        "capacidad_asientos": cap_sala,
        "horizon_hours": len(puntos_pronostico),
        "total_timeline_hours": len(puntos_totales),
        "anchor_timestamp": anchor_dt.isoformat(),
        "historico_7d": puntos_historicos,
        "pronostico_7d": puntos_pronostico,
        "forecast": puntos_totales,
        "model_status": {
            "status": status_str,
            "model_type": "Prophet Jerárquico por Sala" if recinto == "biblioteca" else "Prophet Univariado",
            "model_date": model_date or "Sin calibración",
        },
    }


async def predict_next_7_days(session: AsyncSession, recinto: str = "biblioteca") -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Función de retrocompatibilidad con la API anterior."""
    res = await predict_continuous(session, recinto=recinto)
    return res["pronostico_7d"], res["model_status"]


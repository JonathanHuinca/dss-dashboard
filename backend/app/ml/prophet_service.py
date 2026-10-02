"""
prophet_service.py — Servicio de entrenamiento, evaluación y predicción Prophet.

Responsabilidades:
  1. Extraer datos agregados de Continuous Aggregates de TimescaleDB.
  2. Enriquecer con regresores del calendario académico UCT.
  3. Entrenar Prophet con estacionalidad diaria + semanal.
  4. Evaluar WAPE, MAE y baseline estacional ingenuo (time-based split).
  5. Serializar modelo versionado + enlace simbólico "active".
  6. Predicción horaria para los próximos 7 días con bandas de incertidumbre.
  7. Fallback si no existe modelo: retorna None con mensaje explicativo.
"""
import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from prophet import Prophet
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rutas de persistencia
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parents[3]
MODELS_DIR = BASE_DIR / "backend" / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

RECINTOS = ("biblioteca", "vehicular")

VIEW_MAP = {
    "biblioteca": "aforo_horario_biblioteca",
    "vehicular":  "aforo_horario_estacionamiento",
}
TARGET_COL_MAP = {
    "biblioteca": "ingresos",
    "vehicular":  "entradas",
}

TRAIN_RATIO = 0.85
MIN_ROWS_REQUIRED = 100


# ---------------------------------------------------------------------------
# Helpers de persistencia
# ---------------------------------------------------------------------------

def _versioned_path(recinto: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    return MODELS_DIR / f"prophet_{recinto}_v{ts}.joblib"


def _active_path(recinto: str) -> Path:
    return MODELS_DIR / f"prophet_{recinto}_active.joblib"


def _save_model(model: Prophet, recinto: str) -> Path:
    """Serializa el modelo versionado y actualiza el enlace simbólico 'active'."""
    versioned = _versioned_path(recinto)
    joblib.dump(model, versioned)

    active = _active_path(recinto)
    # En Windows los symlinks requieren permisos elevados; usamos copia directa
    # pero preservamos el comportamiento de "apuntar al último válido".
    shutil.copy2(versioned, active)
    logger.info(f"Modelo {recinto} guardado: {versioned.name}")

    _prune_old_models(recinto, keep=3)
    return versioned


def _prune_old_models(recinto: str, keep: int = 3) -> None:
    """Retiene los últimos N modelos versionados, elimina el resto."""
    pattern = f"prophet_{recinto}_v*.joblib"
    versions = sorted(MODELS_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in versions[keep:]:
        old.unlink(missing_ok=True)
        logger.debug(f"Modelo purgado: {old.name}")


def load_active_model(recinto: str) -> Optional[Prophet]:
    """Carga el modelo activo. Retorna None si no existe (primer arranque)."""
    path = _active_path(recinto)
    if not path.exists():
        return None
    try:
        return joblib.load(path)
    except Exception as e:
        logger.error(f"Error cargando modelo {recinto}: {e}")
        return None


def active_model_date(recinto: str) -> Optional[str]:
    path = _active_path(recinto)
    if not path.exists():
        return None
    ts = datetime.fromtimestamp(path.stat().st_mtime)
    return ts.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Extracción de datos desde TimescaleDB
# ---------------------------------------------------------------------------

async def _fetch_aggregate(session: AsyncSession, recinto: str) -> pd.DataFrame:
    view = VIEW_MAP[recinto]
    target = TARGET_COL_MAP[recinto]

    if recinto == "biblioteca":
        sql = text(f"""
            SELECT
                bucket                  AS ds,
                COALESCE({target}, 0)   AS y,
                espacio_id
            FROM {view}
            ORDER BY bucket ASC
        """)
    else:
        sql = text(f"""
            SELECT
                bucket                  AS ds,
                COALESCE(SUM({target}), 0) AS y,
                espacio_id
            FROM {view}
            GROUP BY bucket, espacio_id
            ORDER BY bucket ASC
        """)

    result = await session.execute(sql)
    rows = result.fetchall()
    if not rows:
        return pd.DataFrame(columns=["ds", "y"])

    df = pd.DataFrame(rows, columns=["ds", "y", "espacio_id"])
    df["ds"] = pd.to_datetime(df["ds"], utc=True).dt.tz_localize(None)
    df["y"] = pd.to_numeric(df["y"], errors="coerce").fillna(0).clip(lower=0)
    return df[["ds", "y"]]


async def _fetch_calendar(session: AsyncSession) -> pd.DataFrame:
    sql = text("""
        SELECT
            fecha,
            is_holiday,
            is_break,
            is_exam_period,
            is_class_milestone,
            suspension_actividades
        FROM calendario_academico
        ORDER BY fecha ASC
    """)
    result = await session.execute(sql)
    rows = result.fetchall()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(
        rows,
        columns=["fecha", "is_holiday", "is_break", "is_exam_period",
                 "is_class_milestone", "suspension_actividades"],
    )
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df


def _enrich_with_calendar(df: pd.DataFrame, cal: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega los regresores del calendario académico al DataFrame de Prophet.
    La granularidad del calendario es diaria; se expande a horaria por join de fecha.
    """
    if cal.empty:
        for col in ["is_holiday", "is_break", "is_exam_period",
                    "is_class_milestone", "suspension_actividades"]:
            df[col] = 0
        return df

    df["_fecha"] = df["ds"].dt.normalize()
    cal["_fecha"] = cal["fecha"]
    df = df.merge(
        cal[["_fecha", "is_holiday", "is_break", "is_exam_period",
             "is_class_milestone", "suspension_actividades"]],
        on="_fecha",
        how="left",
    )
    for col in ["is_holiday", "is_break", "is_exam_period",
                "is_class_milestone", "suspension_actividades"]:
        df[col] = df[col].fillna(0).astype(int)
    df.drop(columns=["_fecha"], inplace=True)
    return df


# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------

def _wape(y_true: np.ndarray, y_pred: np.ndarray) -> Optional[float]:
    """
    WAPE = 100 * sum(|y - ŷ|) / sum(|y|)
    Retorna None si el denominador es 0 (ej. noches o feriados completos cerrados).
    """
    denom = np.sum(np.abs(y_true))
    if denom == 0:
        return None
    return float(100.0 * np.sum(np.abs(y_true - y_pred)) / denom)


def _mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(np.abs(y_true - y_pred)))


def _baseline_wape(df_test: pd.DataFrame) -> Optional[float]:
    """
    Baseline de persistencia estacional ingenua: ŷ_t = y_(t - 7 días).
    """
    df_test = df_test.copy().sort_values("ds").reset_index(drop=True)
    df_test["_7d_ago"] = df_test["ds"] - pd.Timedelta(days=7)

    lookup = df_test.set_index("ds")["y"]
    baseline = df_test["_7d_ago"].map(lookup).fillna(0).values
    return _wape(df_test["y"].values, baseline)


# ---------------------------------------------------------------------------
# Construcción y entrenamiento de Prophet
# ---------------------------------------------------------------------------

def _build_prophet(regressors: list[str]) -> Prophet:
    """
    Configura Prophet con estacionalidades y regresores del calendario UCT.
    """
    holidays = None

    model = Prophet(
        seasonality_mode="additive",
        daily_seasonality=True,
        weekly_seasonality=True,
        yearly_seasonality=False,
        holidays=holidays,
        changepoint_prior_scale=0.05,
        seasonality_prior_scale=10.0,
        interval_width=0.80,
    )

    model.add_seasonality(name="diaria_uct", period=1, fourier_order=8)
    model.add_seasonality(name="semanal_uct", period=7, fourier_order=3)

    for reg in regressors:
        model.add_regressor(reg, standardize=False)

    return model


# ---------------------------------------------------------------------------
# Pipeline principal: train + evaluate + save
# ---------------------------------------------------------------------------

async def train_and_save(session: AsyncSession, recinto: str) -> dict:
    """
    Pipeline completo para un recinto:
      1. Extrae datos de Continuous Aggregate + calendario
      2. Divide train/test (time-based split, TRAIN_RATIO)
      3. Entrena Prophet con regresores académicos
      4. Evalúa WAPE, MAE, WAPE baseline
      5. Serializa modelo y retorna métricas

    Retorna dict con métricas y paths o lanza ValueError si hay datos insuficientes.
    """
    logger.info(f"[Prophet] Iniciando entrenamiento para recinto='{recinto}'")

    df = await _fetch_aggregate(session, recinto)
    if len(df) < MIN_ROWS_REQUIRED:
        raise ValueError(
            f"Datos insuficientes para entrenar '{recinto}': "
            f"{len(df)} filas (mínimo {MIN_ROWS_REQUIRED})"
        )

    cal = await _fetch_calendar(session)
    df = _enrich_with_calendar(df, cal)
    df = df.sort_values("ds").reset_index(drop=True)

    split_idx = int(len(df) * TRAIN_RATIO)
    df_train = df.iloc[:split_idx].copy()
    df_test  = df.iloc[split_idx:].copy()

    REGRESSORS = [
        "is_holiday", "is_break", "is_exam_period",
        "is_class_milestone", "suspension_actividades",
    ]

    model = _build_prophet(REGRESSORS)

    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model.fit(df_train)

    # Evaluación sobre test set
    future_test = df_test[["ds"] + REGRESSORS].copy()
    forecast_test = model.predict(future_test)
    y_true = df_test["y"].values
    y_pred = np.clip(forecast_test["yhat"].values, a_min=0, a_max=None)

    wape_val     = _wape(y_true, y_pred)
    mae_val      = _mae(y_true, y_pred)
    wape_base    = _baseline_wape(df_test)

    versioned_path = _save_model(model, recinto)

    metrics = {
        "recinto": recinto,
        "train_rows": len(df_train),
        "test_rows": len(df_test),
        "wape": round(wape_val, 4) if wape_val is not None else None,
        "wape_undefined": wape_val is None,
        "mae": round(mae_val, 4),
        "wape_baseline": round(wape_base, 4) if wape_base is not None else None,
        "model_path": str(versioned_path),
        "trained_at": datetime.now().isoformat(),
    }
    logger.info(
        f"[Prophet] {recinto} — WAPE: {metrics['wape']}% | "
        f"MAE: {metrics['mae']} | Baseline WAPE: {metrics['wape_baseline']}%"
    )
    return metrics


async def train_all(session: AsyncSession) -> list[dict]:
    """Entrena y serializa los modelos de biblioteca y vehicular."""
    results = []
    for recinto in RECINTOS:
        try:
            m = await train_and_save(session, recinto)
            results.append(m)
        except Exception as e:
            logger.error(f"[Prophet] Fallo en entrenamiento '{recinto}': {e}")
            results.append({"recinto": recinto, "error": str(e)})
    return results


# ---------------------------------------------------------------------------
# Predicción: próximos 7 días
# ---------------------------------------------------------------------------

async def predict_next_7_days(
    session: AsyncSession,
    recinto: str,
) -> tuple[list[dict], dict]:
    """
    Carga el modelo activo y retorna el pronóstico horario para las próximas
    168 horas (7 días) con yhat, yhat_lower, yhat_upper.

    Retorna (forecast_list, model_status_dict).
    Si no existe modelo activo, retorna ([], {"status": "unavailable"}).
    """
    model = load_active_model(recinto)
    if model is None:
        return [], {
            "status": "unavailable",
            "message": (
                "Modelo no disponible. Ejecute el primer entrenamiento "
                "desde el panel de administrador (POST /api/v1/predictions/retrain)."
            ),
        }

    now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    future_dates = [now + timedelta(hours=h) for h in range(1, 169)]
    future_df = pd.DataFrame({"ds": future_dates})

    cal = await _fetch_calendar(session)

    REGRESSORS = [
        "is_holiday", "is_break", "is_exam_period",
        "is_class_milestone", "suspension_actividades",
    ]
    future_df = _enrich_with_calendar(future_df, cal)

    for col in REGRESSORS:
        if col not in future_df.columns:
            future_df[col] = 0

    forecast = model.predict(future_df[["ds"] + REGRESSORS])

    result = [
        {
            "ds": row["ds"].isoformat(),
            "yhat":       max(0.0, round(row["yhat"], 2)),
            "yhat_lower": max(0.0, round(row["yhat_lower"], 2)),
            "yhat_upper": max(0.0, round(row["yhat_upper"], 2)),
        }
        for _, row in forecast.iterrows()
    ]

    model_status = {
        "status": "ok",
        "model_date": active_model_date(recinto),
    }

    return result, model_status

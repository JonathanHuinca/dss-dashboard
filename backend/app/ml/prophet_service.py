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
import json
import logging
import os
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

from app.core.tiempo import ahora_chile_naive
from app.ml.gestor_modelos import (
    cargar_modelo_en_memoria,
    ejecutar_inferencia_en_hilo,
    invalidar_cache_modelo,
)

logger = logging.getLogger("uvicorn.error")

MODELS_DIR = Path(__file__).resolve().parents[2] / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

MODELOS_SALA = {
    "sala1": "prophet_biblioteca_sala1",
    "sala2": "prophet_biblioteca_sala2",
    "todas": "prophet_biblioteca_todas",
    "vehicular": "prophet_vehicular",
}

MODELOS_PRESENCIA = {
    "sala1": "prophet_presencia_sala1",
    "sala2": "prophet_presencia_sala2",
    "todas": "prophet_presencia_todas",
}

SECTORES_VEHICULARES = ("CSF11", "CSF21", "CHS01")

MODELOS_VEHICULAR = {
    "todos": "prophet_vehicular",
    "CSF11": "prophet_vehicular_csf11",
    "CSF21": "prophet_vehicular_csf21",
    "CHS01": "prophet_vehicular_chs01",
}


def _normalizar_sector_vehicular(sector: Optional[str]) -> str:
    if not sector:
        return "todos"
    s = sector.strip().upper()
    if s in SECTORES_VEHICULARES:
        return s
    return "todos"

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
    tmp_ver = versioned.with_name(f".{versioned.name}.tmp.{os.getpid()}")
    joblib.dump(model, tmp_ver)
    os.replace(tmp_ver, versioned)
    active = _active_path(modelo_key)
    tmp_act = active.with_name(f".{active.name}.tmp.{os.getpid()}")
    shutil.copy2(versioned, tmp_act)
    os.replace(tmp_act, active)
    invalidar_cache_modelo(active)
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
    meta_path = MODELS_DIR / f"{modelo_key}_metadata.json"
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                dt_str = data.get("actualizado_en") or data.get("promovido_en") or data.get("ultima_auditoria_en")
                if dt_str:
                    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                    return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass
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
    capacidades = {
        "sala1": 150,
        "sala2": 126,
        "todas": 276,
        "vehicular": 125,
        "CSF11": 40,
        "CSF21": 50,
        "CHS01": 35,
    }

    for row in res_salas.fetchall():
        if "CSF02" in row.codigo:
            capacidades["sala1"] = int(row.capacidad_asientos)
        elif "CSF04" in row.codigo:
            capacidades["sala2"] = int(row.capacidad_asientos)

    capacidades["todas"] = capacidades["sala1"] + capacidades["sala2"]

    try:
        res_sec = await session.execute(
            text("SELECT codigo, capacidad_max FROM sectores_estacionamiento WHERE activo = 1")
        )
        for row in res_sec.fetchall():
            if row.codigo and row.capacidad_max:
                capacidades[row.codigo.strip().upper()] = int(row.capacidad_max)
    except Exception:
        pass

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
    Para recinto='vehicular', extrae la ocupación física simultánea (plazas) desde la curva sweep-line.
    """
    if recinto == "vehicular":
        from app.services.vehicle_service import VehicleService

        sector_norm = _normalizar_sector_vehicular(sala)
        res_t = await session.execute(text("""
            SELECT MIN(time), MAX(time)
            FROM eventos_vehiculares
            WHERE espacio_id = 2 AND time <= GETDATE()
        """))
        min_t, max_t = res_t.fetchone()
        if not max_t:
            return pd.DataFrame(columns=["ds", "y"])

        f_fin = max_t.date()
        f_ini = max(min_t.date(), f_fin - timedelta(days=180)) if min_t else f_fin - timedelta(days=180)
        curva_veh = await VehicleService.get_realtime_presence_curve(
            session=session,
            fecha_inicio=f_ini,
            fecha_fin=f_fin,
            espacio_id=2,
            sector=None if sector_norm == "todos" else sector_norm,
        )
        if not curva_veh:
            return pd.DataFrame(columns=["ds", "y"])

        col_y = "vehiculos_presentes"
        if sector_norm == "CSF11":
            col_y = "vehiculos_csf11"
        elif sector_norm == "CSF21":
            col_y = "vehiculos_csf21"
        elif sector_norm == "CHS01":
            col_y = "vehiculos_chs01"

        df_raw = pd.DataFrame(curva_veh)
        df_raw["ds"] = pd.to_datetime(df_raw["bucket"]).dt.tz_localize(None)
        df_series = pd.DataFrame({
            "ds": df_raw["ds"],
            "y": pd.to_numeric(df_raw[col_y], errors="coerce").fillna(0.0),
        })
        full_idx = pd.date_range(df_series["ds"].min(), df_series["ds"].max(), freq="1h")
        df = df_series.set_index("ds").reindex(full_idx, fill_value=0.0).reset_index()
        df.columns = ["ds", "y"]
        df["y"] = pd.to_numeric(df["y"], errors="coerce").fillna(0.0).clip(lower=0.0)
        return df
    else:
        door_filter = ""
        if sala == "sala1":
            door_filter = "AND (door_entrada LIKE '%CSF02%' OR door_salida LIKE '%CSF02%')"
        elif sala == "sala2":
            door_filter = "AND (door_entrada LIKE '%CSF04%' OR door_salida LIKE '%CSF04%')"
        else:
            door_filter = "AND (door_entrada LIKE '%CSF02%' OR door_salida LIKE '%CSF02%' OR door_entrada LIKE '%CSF04%' OR door_salida LIKE '%CSF04%')"

        sql = text(f"""
            SELECT 
                DATEADD(hour, DATEDIFF(hour, CONVERT(DATETIME2, '2000-01-01T00:00:00', 126), time), CONVERT(DATETIME2, '2000-01-01T00:00:00', 126)) as ds,
                COUNT(DISTINCT person_id_hash) as y
            FROM eventos_asistencia
            WHERE espacio_id = 1 
              AND time <= GETDATE()
              AND alerta_coherencia_fechas = 0
              AND person_id_hash NOT LIKE 'TEST_HASH%'
              AND (marcajes_totales < 5 OR (permanencia_min IS NOT NULL AND permanencia_min > 0))
              AND NOT (marcajes_totales >= 5 AND permanencia_min IS NULL)
              {door_filter}
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


def _evaluar_dato_faltante_sensor(
    dt: datetime,
    espacio_id: int,
    sala: str,
    contingencias: Optional[list[dict]],
) -> int:
    """Identifica franjas con falla de sensor o apertura manual para excluirlas del entrenamiento ML."""
    if not contingencias:
        return 0
    from datetime import time as time_cls
    from app.services.config_service import _normalizar_subespacio, _obtener_valor_campo

    sub_norm = _normalizar_subespacio(sala)
    fecha_dt = dt.date()
    hora_dt = dt.time()

    for c in contingencias:
        tipo_c = str(_obtener_valor_campo(c, "tipo", "") or "").strip().lower()
        if tipo_c not in ("falla_sensor", "apertura_manual"):
            continue
        c_esp = _obtener_valor_campo(c, "espacio_id")
        if c_esp is not None and int(c_esp) != int(espacio_id):
            continue
        c_sub = _normalizar_subespacio(_obtener_valor_campo(c, "subespacio", "todos"))
        if sub_norm != "todos" and c_sub not in ("todos", sub_norm):
            continue

        f_ini = _obtener_valor_campo(c, "fecha_inicio")
        f_fin = _obtener_valor_campo(c, "fecha_fin")
        if isinstance(f_ini, datetime):
            f_ini = f_ini.date()
        if isinstance(f_fin, datetime):
            f_fin = f_fin.date()
        if f_ini and f_fin and not (f_ini <= fecha_dt <= f_fin):
            continue

        h_ini_str = _obtener_valor_campo(c, "hora_inicio")
        h_fin_str = _obtener_valor_campo(c, "hora_fin")
        if h_ini_str and h_fin_str:
            try:
                hi_h, hi_m = map(int, str(h_ini_str).split(":")[:2])
                hf_h, hf_m = map(int, str(h_fin_str).split(":")[:2])
                if time_cls(hi_h, hi_m) <= hora_dt <= time_cls(hf_h, hf_m):
                    return 1
            except Exception:
                return 1
        else:
            return 1
    return 0


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
    df["suspension_actividades"] = df["suspension_actividades"].astype(int)
    # Paro: los recintos siguen abiertos pero los alumnos no tienen clases presenciales
    df["is_strike"] = df["is_strike"].astype(int)

    # Bandera dinámica 24h: solo lunes-viernes o madrugada de sábado (nunca domingo)
    dow = df["ds"].dt.day_of_week
    es_24h_mask = (
        (df["is_exam_period"] == 1)
        & (df["ds"].dt.month.isin([6, 7, 11, 12]))
        & ((dow < 5) | ((dow == 5) & (df["ds"].dt.hour < 6)))
    )

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
    df["es_habil"] = ((dow < 5) & (df["es_horario_abierto"] == 1)).astype(int)
    df["es_sabado"] = ((dow == 5) & (df["es_horario_abierto"] == 1)).astype(int)
    df["es_domingo"] = ((dow == 6) & (df["es_horario_abierto"] == 1)).astype(int)
    if contingencias:
        df["dato_faltante_sensor"] = [
            _evaluar_dato_faltante_sensor(
                dt=row.ds.to_pydatetime() if hasattr(row.ds, "to_pydatetime") else row.ds,
                espacio_id=espacio_id,
                sala=sala,
                contingencias=contingencias,
            )
            for _, row in df.iterrows()
        ]
    else:
        df["dato_faltante_sensor"] = 0

    cols_to_drop = [c for c in ["_fecha", "fecha"] if c in df.columns]
    df = df.drop(columns=cols_to_drop)
    return df


# ---------------------------------------------------------------------------
# Pipeline de Entrenamiento
# ---------------------------------------------------------------------------

REGRESORES_PROPHET: list[str] = [
    "es_horario_abierto",
    "is_holiday",
    "suspension_actividades",
    "is_exam_period",
    "is_break",
    "is_strike",
]


def aplicar_mascara_anomalias_entrenamiento(df: pd.DataFrame) -> pd.DataFrame:
    """
    Opción A: Reemplaza 'y' por np.nan en feriados oficiales, recesos académicos cerrados,
    suspensiones de actividades, contingencias (paros) y fallas de sensor durante el entrenamiento.
    Prophet omite estos registros en el cálculo del likelihood/pérdida, preservando
    la estacionalidad semanal real de los días lectivos regulares sin contaminación por ceros.
    """
    df_mod = df.copy()
    mascara_anomalia = (
        (df_mod["is_holiday"] == 1) |
        ((df_mod["is_break"] == 1) & (df_mod["es_horario_abierto"] == 0)) |
        (df_mod["suspension_actividades"] == 1) |
        (df_mod["is_strike"] == 1)
    )
    if "dato_faltante_sensor" in df_mod.columns:
        mascara_anomalia = mascara_anomalia | (df_mod["dato_faltante_sensor"] == 1)
    df_mod.loc[mascara_anomalia, "y"] = np.nan
    return df_mod


def _preparar_columnas_prediccion(model: Prophet, df_features: pd.DataFrame) -> list[str]:
    """Arma las columnas requeridas según crecimiento, estacionalidades condicionales y regresores del modelo."""
    cols: list[str] = ["ds"]
    if getattr(model, "growth", "linear") == "logistic":
        for c in ("cap", "floor"):
            if c in df_features.columns and c not in cols:
                cols.append(c)

    for seas in getattr(model, "seasonalities", {}).values():
        cond = seas.get("condition_name") if isinstance(seas, dict) else getattr(seas, "condition_name", None)
        if cond and cond in df_features.columns and cond not in cols:
            cols.append(cond)

    for reg in getattr(model, "extra_regressors", {}).keys():
        if reg in df_features.columns and reg not in cols:
            cols.append(reg)

    return cols


def _preparar_df_entrenamiento_abierto(df: pd.DataFrame) -> tuple[pd.DataFrame, bool, bool]:
    """Aplica máscara de anomalías y filtra horas abiertas si existe volumen suficiente."""
    df_masked = aplicar_mascara_anomalias_entrenamiento(df)
    if "es_horario_abierto" in df_masked.columns:
        df_abierto = df_masked[df_masked["es_horario_abierto"] == 1].copy()
        if len(df_abierto) >= MIN_ROWS_REQUIRED and int(df_abierto["y"].notna().sum()) >= MIN_ROWS_REQUIRED:
            incluir_domingo = bool("es_domingo" in df_abierto.columns and int((df_abierto["es_domingo"] == 1).sum()) >= 10)
            return df_abierto, True, incluir_domingo

    incluir_domingo = bool("es_domingo" in df_masked.columns and int((df_masked["es_domingo"] == 1).sum()) >= 10)
    return df_masked, False, incluir_domingo


def _hiperparametros_prophet_por_recinto(recinto: str) -> dict[str, Any]:
    """Hiperparámetros diferenciados: aditivo para ocupación vehicular en plazas y multiplicativo para biblioteca."""
    if str(recinto).strip().lower() == "vehicular":
        return {
            "seasonality_mode": "additive",
            "changepoint_prior_scale": 0.05,
            "seasonality_prior_scale": 8.0,
        }
    return {
        "seasonality_mode": "multiplicative",
        "changepoint_prior_scale": 0.10,
        "seasonality_prior_scale": 10.0,
    }


def _build_prophet(
    growth: str = "linear",
    seasonality_mode: str = "multiplicative",
    solo_abierto: bool = True,
    incluir_domingo: bool = False,
    changepoint_prior_scale: float = 0.10,
    seasonality_prior_scale: float = 10.0,
) -> Prophet:
    model = Prophet(
        growth=growth,
        seasonality_mode=seasonality_mode,
        daily_seasonality=False,
        weekly_seasonality=False,
        yearly_seasonality=False,
        changepoint_prior_scale=changepoint_prior_scale,
        seasonality_prior_scale=seasonality_prior_scale,
        interval_width=0.80,
    )
    model.add_seasonality(name="diaria_habil", period=1, fourier_order=8, condition_name="es_habil")
    model.add_seasonality(name="diaria_sabado", period=1, fourier_order=4, condition_name="es_sabado")
    if incluir_domingo:
        model.add_seasonality(name="diaria_domingo", period=1, fourier_order=4, condition_name="es_domingo")
    model.add_seasonality(name="semanal_uct", period=7, fourier_order=5)
    if not solo_abierto:
        model.add_regressor("es_horario_abierto", prior_scale=15.0, standardize=False)
    model.add_regressor("is_holiday", prior_scale=15.0, standardize=False)
    model.add_regressor("suspension_actividades", prior_scale=10.0, standardize=False)
    model.add_regressor("is_exam_period", prior_scale=12.0, standardize=False)
    model.add_regressor("is_break", standardize=False)
    model.add_regressor("is_strike", standardize=False)
    return model


async def train_sala_model(session: AsyncSession, modelo_key: str, recinto: str, sala: str) -> dict:
    if recinto == "vehicular":
        sala = _normalizar_sector_vehicular(sala)
    logger.info(f"[Prophet] Iniciando entrenamiento modelo={modelo_key} (recinto={recinto}, sala={sala})")
    df = await _fetch_hourly_data(session, recinto=recinto, sala=sala)
    if len(df) < MIN_ROWS_REQUIRED:
        raise ValueError(f"Datos insuficientes para '{modelo_key}': {len(df)} filas.")

    cal = await _fetch_calendar(session)
    espacio_id_entrenamiento = 2 if recinto == "vehicular" else 1
    horarios_cfg = await _fetch_horarios_info(session, espacio_id=espacio_id_entrenamiento)
    contingencias_cfg = await _fetch_contingencias_info(session, espacio_id=espacio_id_entrenamiento)
    capacidades = await _fetch_capacidades(session)

    cap_val = float(capacidades.get(sala, capacidades.get("todas", 276)))
    if recinto == "vehicular":
        cap_val = float(
            capacidades.get(sala, capacidades.get("vehicular", 125))
            if sala != "todos"
            else capacidades.get("vehicular", 125)
        )

    df = _enrich_features(
        df,
        cal,
        sala=sala,
        horarios=horarios_cfg,
        contingencias=contingencias_cfg,
        espacio_id=espacio_id_entrenamiento,
    )
    df["cap"] = cap_val
    df["floor"] = 0.0

    split_idx = int(len(df) * TRAIN_RATIO)
    train_df = df.iloc[:split_idx].copy()
    test_df = df.iloc[split_idx:].copy()

    # Entrenar solo en horas abiertas + máscara de anomalías
    hp = _hiperparametros_prophet_por_recinto(recinto)
    train_df_fit, solo_ab_eval, inc_dom_eval = _preparar_df_entrenamiento_abierto(train_df)

    import warnings
    model_eval = _build_prophet(
        growth="linear",
        solo_abierto=solo_ab_eval,
        incluir_domingo=inc_dom_eval,
        **hp,
    )
    fit_cols_eval = ["y"] + _preparar_columnas_prediccion(model_eval, train_df_fit)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model_eval.fit(train_df_fit[fit_cols_eval])

    # Evaluación sobre test set
    test_cols = _preparar_columnas_prediccion(model_eval, test_df)
    forecast_test = model_eval.predict(test_df[test_cols])

    y_true = test_df["y"].values
    y_pred = np.clip(forecast_test["yhat"].values, a_min=0, a_max=cap_val)
    # Forzar a 0 en horas cerradas
    y_pred[test_df["es_horario_abierto"].values == 0] = 0.0

    denom = np.sum(y_true)
    wape = float(100.0 * np.sum(np.abs(y_true - y_pred)) / denom) if denom > 0 else 0.0
    mae = float(np.mean(np.abs(y_true - y_pred)))

    # Error en Hora Pico (PHE) sobre horas con asistencia >= 75% del máximo
    max_test = np.max(y_true) if len(y_true) > 0 else 0
    mask_peak = (y_true >= (0.75 * max_test)) if max_test > 0 else np.zeros_like(y_true, dtype=bool)
    if np.any(mask_peak):
        phe = float(100.0 * np.mean(np.abs(y_true[mask_peak] - y_pred[mask_peak]) / y_true[mask_peak]))
    else:
        phe = 0.0

    # Calibrar y persistir el modelo de producción activo sobre la serie completa enmascarada
    df_prod_fit, solo_ab_prod, inc_dom_prod = _preparar_df_entrenamiento_abierto(df)
    model_prod = _build_prophet(
        growth="linear",
        solo_abierto=solo_ab_prod,
        incluir_domingo=inc_dom_prod,
        **hp,
    )
    fit_cols_prod = ["y"] + _preparar_columnas_prediccion(model_prod, df_prod_fit)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model_prod.fit(df_prod_fit[fit_cols_prod])

    versioned_path = _save_model(model_prod, modelo_key)

    # Persistir metadatos analíticos de validación
    meta_path = MODELS_DIR / f"{modelo_key}_metadata.json"
    try:
        with open(meta_path, "w", encoding="utf-8") as f_meta:
            json.dump({
                "modelo": modelo_key,
                "recinto": recinto,
                "sala": sala,
                "train_rows": len(train_df),
                "test_rows": len(test_df),
                "mae": round(mae, 2),
                "wape": round(wape, 2),
                "phe": round(phe, 2),
                "actualizado_en": datetime.now().isoformat(),
            }, f_meta, indent=2)
    except Exception as e_meta:
        logger.warning(f"Error guardando metadatos para {modelo_key}: {e_meta}")

    return {
        "modelo": modelo_key,
        "recinto": recinto,
        "sala": sala,
        "train_rows": len(train_df),
        "test_rows": len(test_df),
        "mae": round(mae, 2),
        "wape": round(wape, 2),
        "phe": round(phe, 2),
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
        ("prophet_vehicular", "vehicular", "todos"),
        ("prophet_vehicular_csf11", "vehicular", "CSF11"),
        ("prophet_vehicular_csf21", "vehicular", "CSF21"),
        ("prophet_vehicular_chs01", "vehicular", "CHS01"),
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
    Soporta desglose por sala ('todas', 'sala1', 'sala2') o por sector vehicular ('todos', 'CSF11', 'CSF21', 'CHS01').
    """
    capacidades = await _fetch_capacidades(session)
    sector_veh = _normalizar_sector_vehicular(sala) if recinto == "vehicular" else None
    if recinto == "vehicular":
        cap_sala = (
            capacidades.get(sector_veh, capacidades.get("vehicular", 125))
            if sector_veh != "todos"
            else capacidades.get("vehicular", 125)
        )
    else:
        cap_sala = capacidades.get(sala, capacidades.get("todas", 276))

    # Determinar fecha de anclaje (máximo tiempo real no futuro en la base de datos)
    if recinto == "vehicular":
        res_t = await session.execute(text("SELECT MAX(time) FROM eventos_vehiculares WHERE espacio_id = 2 AND time <= GETDATE()"))
    else:
        res_t = await session.execute(text("""
            SELECT MAX(time) 
            FROM eventos_asistencia 
            WHERE espacio_id = 1 
              AND time <= GETDATE()
              AND alerta_coherencia_fechas = 0 
              AND person_id_hash NOT LIKE 'TEST_HASH%'
        """))
    max_time_val = res_t.scalar()
    anchor_dt = (max_time_val or ahora_chile_naive()).replace(minute=0, second=0, microsecond=0)

    # 1. Extraer los últimos 7 días de datos reales (168 horas completas hasta anchor_dt inclusive)
    h_start = anchor_dt - timedelta(hours=167)
    h_end_exclusive = anchor_dt + timedelta(hours=1)
    hist_idx = pd.date_range(h_start, anchor_dt, freq="1h")
    mapa_veh_sec: Dict[str, Dict[datetime, float]] = {"CSF11": {}, "CSF21": {}, "CHS01": {}}

    if recinto == "vehicular":
        from app.services.vehicle_service import VehicleService

        curva_veh = await VehicleService.get_realtime_presence_curve(
            session=session,
            fecha_inicio=h_start.date() - timedelta(days=1),
            fecha_fin=anchor_dt.date(),
            espacio_id=2,
            sector=None if sector_veh == "todos" else sector_veh,
        )
        col_veh = "vehiculos_presentes"
        if sector_veh == "CSF11":
            col_veh = "vehiculos_csf11"
        elif sector_veh == "CSF21":
            col_veh = "vehiculos_csf21"
        elif sector_veh == "CHS01":
            col_veh = "vehiculos_chs01"

        mapa_veh: Dict[datetime, float] = {}
        for r in curva_veh:
            dt_b = pd.to_datetime(r["bucket"]).tz_localize(None)
            mapa_veh[dt_b] = float(r.get(col_veh, 0))
            if sector_veh == "todos":
                mapa_veh_sec["CSF11"][dt_b] = float(r.get("vehiculos_csf11", 0))
                mapa_veh_sec["CSF21"][dt_b] = float(r.get("vehiculos_csf21", 0))
                mapa_veh_sec["CHS01"][dt_b] = float(r.get("vehiculos_chs01", 0))

        df_hist = pd.DataFrame({
            "ds": hist_idx,
            "actual": [mapa_veh.get(dt_h, 0.0) for dt_h in hist_idx],
        })
    else:
        hist_params: Dict[str, Any] = {"h_start": h_start, "h_end_exclusive": h_end_exclusive}
        if sala == "sala1":
            door_filter = "AND (door_entrada LIKE '%CSF02%' OR door_salida LIKE '%CSF02%')"
        elif sala == "sala2":
            door_filter = "AND (door_entrada LIKE '%CSF04%' OR door_salida LIKE '%CSF04%')"
        else:
            door_filter = "AND (door_entrada LIKE '%CSF02%' OR door_salida LIKE '%CSF02%' OR door_entrada LIKE '%CSF04%' OR door_salida LIKE '%CSF04%')"

        sql_hist = text(f"""
            SELECT 
                DATEADD(hour, DATEDIFF(hour, CONVERT(DATETIME2, '2000-01-01T00:00:00', 126), time), CONVERT(DATETIME2, '2000-01-01T00:00:00', 126)) as ds,
                COUNT(DISTINCT person_id_hash) as actual
            FROM eventos_asistencia
            WHERE espacio_id = 1 
              AND time <= GETDATE()
              AND alerta_coherencia_fechas = 0
              AND person_id_hash NOT LIKE 'TEST_HASH%'
              AND (marcajes_totales < 5 OR (permanencia_min IS NOT NULL AND permanencia_min > 0))
              AND NOT (marcajes_totales >= 5 AND permanencia_min IS NULL)
              {door_filter}
              AND time >= :h_start AND time < :h_end_exclusive
            GROUP BY DATEADD(hour, DATEDIFF(hour, CONVERT(DATETIME2, '2000-01-01T00:00:00', 126), time), CONVERT(DATETIME2, '2000-01-01T00:00:00', 126))
            ORDER BY ds ASC
        """)
        res_hist = await session.execute(sql_hist, hist_params)
        df_hist_raw = pd.DataFrame(res_hist.fetchall(), columns=["ds", "actual"])
        df_hist_raw["ds"] = pd.to_datetime(df_hist_raw["ds"]).dt.tz_localize(None)
        df_hist = df_hist_raw.set_index("ds").reindex(hist_idx, fill_value=0).reset_index()
        df_hist.columns = ["ds", "actual"]

    cal = await _fetch_calendar(session)
    espacio_id_actual = 2 if recinto == "vehicular" else 1
    horarios_cfg = await _fetch_horarios_info(session, espacio_id=espacio_id_actual)
    contingencias_cfg = await _fetch_contingencias_info(session, espacio_id=espacio_id_actual)

    # 2. Generar predicción futura para los próximos 7 días (exactamente 168 horas desde anchor_dt + 1h)
    future_dates = [anchor_dt + timedelta(hours=h) for h in range(1, 169)]
    df_fut_base = pd.DataFrame({"ds": future_dates})
    sala_eval = sector_veh if recinto == "vehicular" else sala
    df_fut = _enrich_features(
        df_fut_base,
        cal,
        sala=sala_eval,
        horarios=horarios_cfg,
        contingencias=contingencias_cfg,
        espacio_id=espacio_id_actual,
    )
    df_fut["cap"] = cap_sala
    df_fut["floor"] = 0.0

    df_fut_veh_sec: Dict[str, pd.DataFrame] = {}
    cap_veh_sec: Dict[str, float] = {}
    if recinto == "vehicular" and sector_veh == "todos":
        for sec_cod in SECTORES_VEHICULARES:
            cap_sec = float(capacidades.get(sec_cod, 40 if sec_cod == "CSF11" else (50 if sec_cod == "CSF21" else 35)))
            cap_veh_sec[sec_cod] = cap_sec
            df_sec = _enrich_features(
                df_fut_base, cal, sala=sec_cod, horarios=horarios_cfg, contingencias=contingencias_cfg, espacio_id=2
            )
            df_sec["cap"] = cap_sec
            df_sec["floor"] = 0.0
            df_fut_veh_sec[sec_cod] = df_sec
        df_fut["es_horario_abierto"] = (
            (df_fut_veh_sec["CSF11"]["es_horario_abierto"].values == 1)
            | (df_fut_veh_sec["CSF21"]["es_horario_abierto"].values == 1)
            | (df_fut_veh_sec["CHS01"]["es_horario_abierto"].values == 1)
        ).astype(int)

    if recinto == "biblioteca" and sala == "todas":
        cap_s1 = float(capacidades.get("sala1", 150))
        cap_s2 = float(capacidades.get("sala2", 126))
        df_fut_s1 = _enrich_features(
            df_fut_base, cal, sala="sala1", horarios=horarios_cfg, contingencias=contingencias_cfg, espacio_id=1
        )
        df_fut_s1["cap"] = cap_s1
        df_fut_s1["floor"] = 0.0

        df_fut_s2 = _enrich_features(
            df_fut_base, cal, sala="sala2", horarios=horarios_cfg, contingencias=contingencias_cfg, espacio_id=1
        )
        df_fut_s2["cap"] = cap_s2
        df_fut_s2["floor"] = 0.0
    else:
        df_fut_s1 = df_fut
        df_fut_s2 = df_fut

    modelo_veh_key = MODELOS_VEHICULAR.get(sector_veh, MODELOS_VEHICULAR["todos"]) if recinto == "vehicular" else None
    usa_bottom_up_veh = False

    # Cargar modelos según selección jerárquica
    def _calcular_predicciones_sincronas() -> Tuple[pd.DataFrame, str]:
        nonlocal usa_bottom_up_veh

        def _infer_single(m_key: str, df_features: pd.DataFrame, cap_max: float) -> pd.DataFrame:
            m = load_active_model(m_key)
            if not m:
                return pd.DataFrame({"yhat": [0.0]*168, "yhat_lower": [0.0]*168, "yhat_upper": [0.0]*168})
            cols = _preparar_columnas_prediccion(m, df_features)
            pred = m.predict(df_features[cols])
            yhat = np.clip(pred["yhat"].values, 0, cap_max)
            lower = np.clip(pred["yhat_lower"].values, 0, cap_max)
            upper = np.clip(pred["yhat_upper"].values, 0, cap_max)

            # Forzar a cero en horas de cierre de esa sala específica
            cerrado_mask = df_features["es_horario_abierto"].values == 0
            yhat[cerrado_mask] = 0.0
            lower[cerrado_mask] = 0.0
            upper[cerrado_mask] = 0.0

            return pd.DataFrame({"yhat": yhat, "yhat_lower": lower, "yhat_upper": upper})

        if recinto == "vehicular":
            if sector_veh == "todos":
                modelos_sec = {s: load_active_model(MODELOS_VEHICULAR[s]) for s in SECTORES_VEHICULARES}
                if any(modelos_sec.values()):
                    usa_bottom_up_veh = True
                    preds_sec = {
                        s: _infer_single(MODELOS_VEHICULAR[s], df_fut_veh_sec[s], cap_veh_sec[s])
                        for s in SECTORES_VEHICULARES
                    }
                    yhat_sum = np.clip(sum(preds_sec[s]["yhat"] for s in SECTORES_VEHICULARES), 0, cap_sala)
                    low_sum = np.clip(sum(preds_sec[s]["yhat_lower"] for s in SECTORES_VEHICULARES), 0, cap_sala)
                    up_sum = np.clip(sum(preds_sec[s]["yhat_upper"] for s in SECTORES_VEHICULARES), 0, cap_sala)
                    return pd.DataFrame({
                        "yhat": yhat_sum,
                        "yhat_lower": low_sum,
                        "yhat_upper": up_sum,
                        "yhat_csf11": preds_sec["CSF11"]["yhat"],
                        "yhat_csf21": preds_sec["CSF21"]["yhat"],
                        "yhat_chs01": preds_sec["CHS01"]["yhat"],
                    }), MODELOS_VEHICULAR["CSF11"]
            m_veh = modelo_veh_key or MODELOS_SALA["vehicular"]
            return _infer_single(m_veh, df_fut, cap_sala), m_veh
        elif sala == "sala1":
            return _infer_single(MODELOS_SALA["sala1"], df_fut, cap_sala), MODELOS_SALA["sala1"]
        elif sala == "sala2":
            return _infer_single(MODELOS_SALA["sala2"], df_fut, cap_sala), MODELOS_SALA["sala2"]
        else:  # Reconciliación jerárquica Bottom-Up: Sala 1 + Sala 2 para coincidencia matemática exacta
            cap_s1 = float(capacidades.get("sala1", 150))
            cap_s2 = float(capacidades.get("sala2", 126))
            df_s1 = _infer_single(MODELOS_SALA["sala1"], df_fut_s1, cap_s1)
            df_s2 = _infer_single(MODELOS_SALA["sala2"], df_fut_s2, cap_s2)
            if df_s1["yhat"].sum() == 0 and df_s2["yhat"].sum() == 0:
                return _infer_single(MODELOS_SALA["todas"], df_fut, cap_sala), MODELOS_SALA["todas"]
            return pd.DataFrame({
                "yhat": np.clip(df_s1["yhat"] + df_s2["yhat"], 0, cap_sala),
                "yhat_lower": np.clip(df_s1["yhat_lower"] + df_s2["yhat_lower"], 0, cap_sala),
                "yhat_upper": np.clip(df_s1["yhat_upper"] + df_s2["yhat_upper"], 0, cap_sala),
            }), MODELOS_SALA["todas"]

    df_pred, active_key = await ejecutar_inferencia_en_hilo(_calcular_predicciones_sincronas)

    # 3. Construir listas de salida
    puntos_historicos = []
    for row in df_hist.itertuples():
        punto_h: Dict[str, Any] = {
            "ds": row.ds.isoformat(),
            "actual": float(row.actual),
            "yhat": float(row.actual),
            "yhat_lower": float(row.actual),
            "yhat_upper": float(row.actual),
            "es_abierto": int(row.actual > 0),
        }
        if recinto == "vehicular" and sector_veh == "todos":
            dt_key = row.ds.to_pydatetime() if hasattr(row.ds, "to_pydatetime") else row.ds
            punto_h["actual_csf11"] = mapa_veh_sec["CSF11"].get(dt_key, 0.0)
            punto_h["actual_csf21"] = mapa_veh_sec["CSF21"].get(dt_key, 0.0)
            punto_h["actual_chs01"] = mapa_veh_sec["CHS01"].get(dt_key, 0.0)
        puntos_historicos.append(punto_h)

    puntos_pronostico = []
    for idx, row in df_fut.iterrows():
        yhat_val = round(float(df_pred["yhat"].iloc[idx]), 1)
        low_val = round(float(df_pred["yhat_lower"].iloc[idx]), 1)
        up_val = round(float(df_pred["yhat_upper"].iloc[idx]), 1)
        punto_f: Dict[str, Any] = {
            "ds": row["ds"].isoformat(),
            "actual": None,
            "yhat": yhat_val,
            "yhat_lower": low_val,
            "yhat_upper": up_val,
            "es_abierto": int(row["es_horario_abierto"]),
        }
        if usa_bottom_up_veh and "yhat_csf11" in df_pred.columns:
            punto_f["yhat_csf11"] = round(float(df_pred["yhat_csf11"].iloc[idx]), 1)
            punto_f["yhat_csf21"] = round(float(df_pred["yhat_csf21"].iloc[idx]), 1)
            punto_f["yhat_chs01"] = round(float(df_pred["yhat_chs01"].iloc[idx]), 1)
        puntos_pronostico.append(punto_f)

    # Línea continua unificada de 336 puntos (168 reales + 168 pronosticados)
    puntos_totales = puntos_historicos + puntos_pronostico

    if usa_bottom_up_veh:
        fechas_veh = [d for d in (active_model_date(MODELOS_VEHICULAR[s]) for s in SECTORES_VEHICULARES) if d]
        model_date = max(fechas_veh) if fechas_veh else active_model_date(active_key)
        model_type_str = "Prophet Jerárquico Bottom-Up Vehicular (Presencia en Plazas)"
    elif recinto == "vehicular":
        model_date = active_model_date(active_key)
        model_type_str = "Prophet Presencia Vehicular por Sector"
    else:
        model_date = active_model_date(active_key)
        model_type_str = "Prophet Jerárquico por Sala"
    status_str = "ok" if model_date else "unavailable"

    respuesta: Dict[str, Any] = {
        "recinto": recinto,
        "sala": sector_veh if recinto == "vehicular" else sala,
        "capacidad_asientos": cap_sala,
        "horizon_hours": len(puntos_pronostico),
        "total_timeline_hours": len(puntos_totales),
        "anchor_timestamp": anchor_dt.isoformat(),
        "historico_7d": puntos_historicos,
        "pronostico_7d": puntos_pronostico,
        "forecast": puntos_totales,
        "model_status": {
            "status": status_str,
            "model_type": model_type_str,
            "model_date": model_date or "Sin calibración",
            **({"message": "Modelo Prophet aún no entrenado. Ejecute reentrenamiento desde Administración."} if status_str == "unavailable" else {}),
        },
    }
    if recinto == "vehicular":
        respuesta["sector"] = sector_veh
        if usa_bottom_up_veh:
            respuesta["reconciliacion"] = "bottom_up"
            respuesta["capacidad_csf11"] = int(cap_veh_sec.get("CSF11", 40))
            respuesta["capacidad_csf21"] = int(cap_veh_sec.get("CSF21", 50))
            respuesta["capacidad_chs01"] = int(cap_veh_sec.get("CHS01", 35))
    return respuesta


async def predict_next_7_days(session: AsyncSession, recinto: str = "biblioteca") -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Función de retrocompatibilidad con la API anterior."""
    res = await predict_continuous(session, recinto=recinto)
    return res["pronostico_7d"], res["model_status"]


# ---------------------------------------------------------------------------
# Pronóstico Continuo de Presencia Física por Intervalos (Prophet Logístico Acotado)
# ---------------------------------------------------------------------------

async def train_presence_model(session: AsyncSession, modelo_key: str, sala: str = "todas") -> dict:
    """
    Entrena el modelo de presencia física en sala con crecimiento logístico acotado (growth='logistic').
    """
    from app.services.attendance_service import AttendanceService
    logger.info(f"[Prophet Logístico Presencia] Entrenando modelo={modelo_key} (sala={sala})")

    res_t = await session.execute(text("""
        SELECT MIN(time), MAX(time) 
        FROM eventos_asistencia 
        WHERE espacio_id = 1 
          AND time <= GETDATE()
          AND alerta_coherencia_fechas = 0 
          AND person_id_hash NOT LIKE 'TEST_HASH%'
    """))
    min_t, max_t = res_t.fetchone()
    if not max_t:
        raise ValueError("Sin eventos de asistencia para entrenar modelo de presencia.")

    anchor_dt = max_t.replace(minute=0, second=0, microsecond=0)
    f_fin = anchor_dt.date()
    f_ini = max(min_t.date(), f_fin - timedelta(days=180))

    raw_hist = await AttendanceService.get_realtime_presence_curve(
        session=session,
        fecha_inicio=f_ini,
        fecha_fin=f_fin,
        espacio_id=1,
    )
    if not raw_hist:
        raise ValueError(f"Datos de presencia insuficientes para '{modelo_key}'.")

    df_raw = pd.DataFrame(raw_hist)
    df_raw["ds"] = pd.to_datetime(df_raw["bucket"]).dt.tz_localize(None)

    col_y = "personas_unicas"
    if sala == "sala1":
        col_y = "personas_sala1"
    elif sala == "sala2":
        col_y = "personas_sala2"

    df_series = pd.DataFrame({
        "ds": df_raw["ds"],
        "y": pd.to_numeric(df_raw[col_y], errors="coerce").fillna(0.0),
    })

    # Reindexar sobre grilla continua de 1h con relleno en 0
    full_idx = pd.date_range(df_series["ds"].min(), df_series["ds"].max(), freq="1h")
    df = df_series.set_index("ds").reindex(full_idx, fill_value=0.0).reset_index()
    df.columns = ["ds", "y"]
    df["y"] = pd.to_numeric(df["y"], errors="coerce").fillna(0.0).clip(lower=0.0)

    capacidades = await _fetch_capacidades(session)
    cap_val = float(capacidades.get(sala, capacidades.get("todas", 276)))

    cal = await _fetch_calendar(session)
    horarios_cfg = await _fetch_horarios_info(session, espacio_id=1)
    contingencias_cfg = await _fetch_contingencias_info(session, espacio_id=1)

    df = _enrich_features(
        df,
        cal,
        sala=sala,
        horarios=horarios_cfg,
        contingencias=contingencias_cfg,
        espacio_id=1,
    )
    df["cap"] = cap_val
    df["floor"] = 0.0

    df_prod_fit, solo_abierto, incluir_domingo = _preparar_df_entrenamiento_abierto(df)
    model_prod = _build_prophet(
        growth="linear",
        seasonality_mode="multiplicative",
        solo_abierto=solo_abierto,
        incluir_domingo=incluir_domingo,
    )
    fit_cols = ["y"] + _preparar_columnas_prediccion(model_prod, df_prod_fit)

    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model_prod.fit(df_prod_fit[fit_cols])

    versioned_path = _save_model(model_prod, modelo_key)

    meta_path = MODELS_DIR / f"{modelo_key}_metadata.json"
    try:
        with open(meta_path, "w", encoding="utf-8") as f_meta:
            json.dump({
                "modelo": modelo_key,
                "recinto": "biblioteca",
                "sala": sala,
                "capacidad_acotada": cap_val,
                "growth": "linear",
                "seasonality_mode": "multiplicative",
                "solo_horario_abierto": solo_abierto,
                "train_rows": len(df_prod_fit),
                "actualizado_en": datetime.now().isoformat(),
            }, f_meta, indent=2)
    except Exception as e_meta:
        logger.warning(f"Error guardando metadatos para {modelo_key}: {e_meta}")

    return {
        "modelo": modelo_key,
        "sala": sala,
        "capacidad": cap_val,
        "trained_at": datetime.now().isoformat(),
        "path": str(versioned_path),
    }


async def predict_presence_continuous(
    session: AsyncSession,
    sala: str = "todas",
) -> Dict[str, Any]:
    """
    Retorna 14 días continuos de presencia física en sala (168 h históricas reales + 168 h proyectadas)
    mediante Prophet con saturación logística acotada (growth='logistic').
    """
    from app.services.attendance_service import AttendanceService
    capacidades = await _fetch_capacidades(session)
    cap_sala = capacidades.get(sala, capacidades.get("todas", 276))

    res_t = await session.execute(text("""
        SELECT MAX(time) 
        FROM eventos_asistencia 
        WHERE espacio_id = 1 
          AND time <= GETDATE()
          AND alerta_coherencia_fechas = 0 
          AND person_id_hash NOT LIKE 'TEST_HASH%'
    """))
    max_time_val = res_t.scalar()
    anchor_dt = (max_time_val or ahora_chile_naive()).replace(minute=0, second=0, microsecond=0)

    # 1. 7 días históricos reales de presencia física (168 horas hasta anchor_dt)
    h_start = anchor_dt - timedelta(hours=167)

    hist_raw = await AttendanceService.get_realtime_presence_curve(
        session=session,
        fecha_inicio=h_start.date() - timedelta(days=1),
        fecha_fin=anchor_dt.date(),
        espacio_id=1,
    )

    mapa_hist = {}
    mapa_hist_s1 = {}
    mapa_hist_s2 = {}
    col_persona = "personas_unicas"
    if sala == "sala1":
        col_persona = "personas_sala1"
    elif sala == "sala2":
        col_persona = "personas_sala2"

    for r in hist_raw:
        dt_b = pd.to_datetime(r["bucket"]).tz_localize(None)
        mapa_hist[dt_b] = float(r.get(col_persona, 0))
        mapa_hist_s1[dt_b] = float(r.get("personas_sala1", 0))
        mapa_hist_s2[dt_b] = float(r.get("personas_sala2", 0))

    hist_idx = pd.date_range(h_start, anchor_dt, freq="1h")
    puntos_historicos = []
    for dt_h in hist_idx:
        val = mapa_hist.get(dt_h, 0.0)
        punto_h: Dict[str, Any] = {
            "ds": dt_h.isoformat(),
            "actual": val,
            "yhat": val,
            "yhat_lower": val,
            "yhat_upper": val,
            "es_abierto": int(val > 0),
        }
        if sala == "todas":
            punto_h["actual_sala1"] = mapa_hist_s1.get(dt_h, 0.0)
            punto_h["actual_sala2"] = mapa_hist_s2.get(dt_h, 0.0)
        puntos_historicos.append(punto_h)

    # 2. 7 días proyectados a futuro (168 horas desde anchor_dt + 1h)
    future_dates = [anchor_dt + timedelta(hours=h) for h in range(1, 169)]
    df_fut_base = pd.DataFrame({"ds": future_dates})

    cal = await _fetch_calendar(session)
    horarios_cfg = await _fetch_horarios_info(session, espacio_id=1)
    contingencias_cfg = await _fetch_contingencias_info(session, espacio_id=1)

    def _inferir_presencia_frame(modelo: Optional[Prophet], df_feat: pd.DataFrame, cap_lim: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        if not modelo:
            n = len(df_feat)
            return np.zeros(n), np.zeros(n), np.zeros(n)
        cols_m = _preparar_columnas_prediccion(modelo, df_feat)
        pred_m = modelo.predict(df_feat[cols_m])
        y_m = np.clip(pred_m["yhat"].values, 0, cap_lim)
        l_m = np.clip(pred_m["yhat_lower"].values, 0, cap_lim)
        u_m = np.clip(pred_m["yhat_upper"].values, 0, cap_lim)
        cerrado_m = df_feat["es_horario_abierto"].values == 0
        y_m[cerrado_m] = 0.0
        l_m[cerrado_m] = 0.0
        u_m[cerrado_m] = 0.0
        return y_m, l_m, u_m

    modelo_key = MODELOS_PRESENCIA.get(sala, MODELOS_PRESENCIA["todas"])
    usa_bottom_up = False
    cap_s1 = float(capacidades.get("sala1", 150))
    cap_s2 = float(capacidades.get("sala2", 126))
    yhat_s1: Optional[np.ndarray] = None
    yhat_s2: Optional[np.ndarray] = None

    if sala == "todas":
        df_fut_s1 = _enrich_features(
            df_fut_base, cal, sala="sala1", horarios=horarios_cfg, contingencias=contingencias_cfg, espacio_id=1
        )
        df_fut_s1["cap"] = cap_s1
        df_fut_s1["floor"] = 0.0

        df_fut_s2 = _enrich_features(
            df_fut_base, cal, sala="sala2", horarios=horarios_cfg, contingencias=contingencias_cfg, espacio_id=1
        )
        df_fut_s2["cap"] = cap_s2
        df_fut_s2["floor"] = 0.0

        df_fut = df_fut_s1[["ds"]].copy()
        df_fut["es_horario_abierto"] = (
            (df_fut_s1["es_horario_abierto"].values == 1) | (df_fut_s2["es_horario_abierto"].values == 1)
        ).astype(int)

        def _inferir_presencia_todas_sync() -> Tuple[bool, np.ndarray, np.ndarray, np.ndarray, Optional[np.ndarray], Optional[np.ndarray]]:
            m_s1 = load_active_model(MODELOS_PRESENCIA["sala1"])
            m_s2 = load_active_model(MODELOS_PRESENCIA["sala2"])
            if m_s1 or m_s2:
                y1, l1, u1 = _inferir_presencia_frame(m_s1, df_fut_s1, cap_s1)
                y2, l2, u2 = _inferir_presencia_frame(m_s2, df_fut_s2, cap_s2)
                return (
                    True,
                    np.clip(y1 + y2, 0, cap_sala),
                    np.clip(l1 + l2, 0, cap_sala),
                    np.clip(u1 + u2, 0, cap_sala),
                    y1,
                    y2,
                )
            df_glob = _enrich_features(
                df_fut_base, cal, sala=sala, horarios=horarios_cfg, contingencias=contingencias_cfg, espacio_id=1
            )
            df_glob["cap"] = float(cap_sala)
            df_glob["floor"] = 0.0
            m_glob = load_active_model(modelo_key)
            yg, lg, ug = _inferir_presencia_frame(m_glob, df_glob, cap_sala)
            return False, yg, lg, ug, None, None

        usa_bottom_up, yhat, lower, upper, yhat_s1, yhat_s2 = await ejecutar_inferencia_en_hilo(_inferir_presencia_todas_sync)
    else:
        df_fut = _enrich_features(
            df_fut_base,
            cal,
            sala=sala,
            horarios=horarios_cfg,
            contingencias=contingencias_cfg,
            espacio_id=1,
        )
        df_fut["cap"] = float(cap_sala)
        df_fut["floor"] = 0.0

        def _inferir_presencia_sala_sync() -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
            m_loc = load_active_model(modelo_key)
            return _inferir_presencia_frame(m_loc, df_fut, cap_sala)

        yhat, lower, upper = await ejecutar_inferencia_en_hilo(_inferir_presencia_sala_sync)

    puntos_pronostico = []
    for idx, row in df_fut.iterrows():
        punto_f: Dict[str, Any] = {
            "ds": row["ds"].isoformat(),
            "actual": None,
            "yhat": round(float(yhat[idx]), 1),
            "yhat_lower": round(float(lower[idx]), 1),
            "yhat_upper": round(float(upper[idx]), 1),
            "es_abierto": int(row["es_horario_abierto"]),
        }
        if usa_bottom_up and yhat_s1 is not None and yhat_s2 is not None:
            punto_f["yhat_sala1"] = round(float(yhat_s1[idx]), 1)
            punto_f["yhat_sala2"] = round(float(yhat_s2[idx]), 1)
        puntos_pronostico.append(punto_f)

    puntos_totales = puntos_historicos + puntos_pronostico
    if usa_bottom_up:
        fechas_sub = [
            d for d in (
                active_model_date(MODELOS_PRESENCIA["sala1"]),
                active_model_date(MODELOS_PRESENCIA["sala2"]),
            )
            if d
        ]
        model_date = max(fechas_sub) if fechas_sub else active_model_date(modelo_key)
        model_type_str = "Prophet Jerárquico Bottom-Up (Sala 1 + Sala 2)"
    else:
        model_date = active_model_date(modelo_key)
        model_type_str = "Prophet Horario Condicional (Presencia Física en Sala)"
    status_str = "ok" if model_date else "unavailable"

    respuesta: Dict[str, Any] = {
        "recinto": "biblioteca",
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
            "model_type": model_type_str,
            "model_date": model_date or "Sin calibración",
            **({"message": "Modelo Prophet de presencia aún no entrenado. Ejecute reentrenamiento desde Administración."} if status_str == "unavailable" else {}),
        },
    }
    if usa_bottom_up:
        respuesta["reconciliacion"] = "bottom_up"
        respuesta["capacidad_sala1"] = int(cap_s1)
        respuesta["capacidad_sala2"] = int(cap_s2)
    return respuesta



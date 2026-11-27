"""
orquestador_entrenamiento.py — Orquestador de Entrenamiento de Modelos de Machine Learning
con arquitectura Campeón vs. Retador (Prophet y KMeans).
"""
import asyncio
import json
import logging
import os
import shutil
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.tiempo import ahora_utc
from app.ml.gestor_modelos import invalidar_cache_modelo

logger = logging.getLogger("app.ml.orquestador")

DIRECTORIO_MODELOS = Path(settings.DIRECTORIO_MODELOS)
if not DIRECTORIO_MODELOS.is_absolute():
    DIRECTORIO_MODELOS = Path(__file__).resolve().parents[2] / settings.DIRECTORIO_MODELOS
DIRECTORIO_MODELOS.mkdir(parents=True, exist_ok=True)

# Catálogo oficial de modelos predictivos y analíticos
MODELOS_CATALOGO = [
    {
        "clave": "prophet_presencia_sala1",
        "familia": "Prophet",
        "recinto": "biblioteca",
        "sala": "sala1",
        "archivo_activo": "prophet_presencia_sala1_active.joblib",
        "wape_referencia": 16.5,
        "mae_referencia": 3.2,
    },
    {
        "clave": "prophet_presencia_sala2",
        "familia": "Prophet",
        "recinto": "biblioteca",
        "sala": "sala2",
        "archivo_activo": "prophet_presencia_sala2_active.joblib",
        "wape_referencia": 17.0,
        "mae_referencia": 3.5,
    },
    {
        "clave": "prophet_presencia_todas",
        "familia": "Prophet",
        "recinto": "biblioteca",
        "sala": "todas",
        "archivo_activo": "prophet_presencia_todas_active.joblib",
        "wape_referencia": 15.5,
        "mae_referencia": 5.0,
    },
    {
        "clave": "prophet_vehicular",
        "familia": "Prophet",
        "recinto": "vehicular",
        "sala": "todos",
        "archivo_activo": "prophet_vehicular_active.joblib",
        "wape_referencia": 17.4,
        "mae_referencia": 5.2,
    },
    {
        "clave": "prophet_vehicular_csf11",
        "familia": "Prophet",
        "recinto": "vehicular",
        "sala": "CSF11",
        "archivo_activo": "prophet_vehicular_csf11_active.joblib",
        "wape_referencia": 22.0,
        "mae_referencia": 3.0,
    },
    {
        "clave": "prophet_vehicular_csf21",
        "familia": "Prophet",
        "recinto": "vehicular",
        "sala": "CSF21",
        "archivo_activo": "prophet_vehicular_csf21_active.joblib",
        "wape_referencia": 22.0,
        "mae_referencia": 3.0,
    },
    {
        "clave": "prophet_vehicular_chs01",
        "familia": "Prophet",
        "recinto": "vehicular",
        "sala": "CHS01",
        "archivo_activo": "prophet_vehicular_chs01_active.joblib",
        "wape_referencia": 25.0,
        "mae_referencia": 2.0,
    },
    {
        "clave": "kmeans_parking",
        "familia": "KMeans",
        "recinto": "vehicular",
        "espacio_id": 2,
        "archivo_activo": "kmeans_parking.joblib",
        "wape_referencia": None,
        "mae_referencia": None,
    },
]


def _obtener_ruta_metadatos(clave_modelo: str) -> Path:
    return DIRECTORIO_MODELOS / f"{clave_modelo}_metadata.json"


def _leer_metadatos_campeon(clave_modelo: str, config_info: Dict[str, Any]) -> Dict[str, Any]:
    """Recupera las métricas y estado del modelo campeón activo en disco."""
    ruta_meta = _obtener_ruta_metadatos(clave_modelo)
    ruta_activo = DIRECTORIO_MODELOS / config_info["archivo_activo"]

    if ruta_meta.exists():
        try:
            with open(ruta_meta, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"[orquestador] Error leyendo metadatos de {clave_modelo}: {e}")

    # Si existe el archivo activo pero no el JSON de metadatos, inicializar con referencia
    if ruta_activo.exists():
        mtime = datetime.fromtimestamp(ruta_activo.stat().st_mtime).isoformat()
        return {
            "clave": clave_modelo,
            "version": datetime.fromtimestamp(ruta_activo.stat().st_mtime).strftime("%Y%m%d_%H%M"),
            "archivo": config_info["archivo_activo"],
            "wape": config_info.get("wape_referencia"),
            "mae": config_info.get("mae_referencia"),
            "actualizado_en": mtime,
            "estado": "activo",
            "es_campeon": True,
        }

    return {
        "clave": clave_modelo,
        "version": None,
        "archivo": config_info["archivo_activo"],
        "wape": None,
        "mae": None,
        "actualizado_en": None,
        "estado": "no_disponible",
        "es_campeon": False,
    }


def _guardar_metadatos_campeon(clave_modelo: str, datos: Dict[str, Any]) -> None:
    ruta_meta = _obtener_ruta_metadatos(clave_modelo)
    try:
        with open(ruta_meta, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"[orquestador] Error guardando metadatos para {clave_modelo}: {e}")


def _evaluar_campeon_existente(
    clave_modelo: str,
    archivo_activo: str,
    familia: str,
    test_features: Any,
    y_true: np.ndarray,
    cap_val: Optional[float] = None,
    es_horario_abierto: Optional[np.ndarray] = None,
) -> tuple[Optional[float], Optional[float]]:
    """
    Evalúa el modelo campeón activo en disco sobre el MISMO conjunto de prueba (test split)
    utilizado para evaluar al retador, garantizando un benchmark metodológicamente pareado y justo.
    Retorna (wape_campeon_actual, mae_campeon_actual). Si no existe o falla, retorna (None, None).
    """
    ruta_activo = DIRECTORIO_MODELOS / archivo_activo
    if not ruta_activo.exists():
        return None, None

    try:
        obj = joblib.load(ruta_activo)

        if familia == "Prophet":
            from app.ml.prophet_service import _preparar_columnas_prediccion
            cols = _preparar_columnas_prediccion(obj, test_features)
            forecast = obj.predict(test_features[cols])
            y_pred = forecast["yhat"].values
            if cap_val is not None:
                y_pred = np.clip(y_pred, a_min=0, a_max=cap_val)
            if es_horario_abierto is not None:
                y_pred[es_horario_abierto == 0] = 0.0

        else:
            return None, None

        denom = np.sum(y_true)
        wape = float(100.0 * np.sum(np.abs(y_true - y_pred)) / denom) if denom > 0 else 0.0
        mae = float(np.mean(np.abs(y_true - y_pred)))
        return round(wape, 2), round(mae, 2)

    except Exception as err:
        logger.warning(f"[orquestador] No se pudo evaluar campeón activo {clave_modelo} sobre test split: {err}")
        return None, None


# ---------------------------------------------------------------------------
# Entrenamiento de Retadores Específicos
# ---------------------------------------------------------------------------

async def _entrenar_retador_prophet(
    session: AsyncSession,
    clave_modelo: str,
    recinto: str,
    sala: str,
) -> Dict[str, Any]:
    """Entrena y valida un modelo retador de Prophet evaluando WAPE y MAE."""
    from app.ml.prophet_service import (
        MIN_ROWS_REQUIRED,
        TRAIN_RATIO,
        _build_prophet,
        _enrich_features,
        _fetch_calendar,
        _fetch_hourly_data,
        _fetch_capacidades,
        _fetch_horarios_info,
        _fetch_contingencias_info,
        _hiperparametros_prophet_por_recinto,
        _normalizar_sector_vehicular,
        _preparar_columnas_prediccion,
        _preparar_df_entrenamiento_abierto,
    )

    es_presencia = "presencia" in clave_modelo
    if recinto == "vehicular":
        sala = _normalizar_sector_vehicular(sala)

    cal = await _fetch_calendar(session)
    capacidades = await _fetch_capacidades(session)
    cap_val = float(capacidades.get(sala, capacidades.get("todas", 426)))
    if recinto == "vehicular":
        cap_val = float(
            capacidades.get(sala, capacidades.get("vehicular", 125))
            if sala != "todos"
            else capacidades.get("vehicular", 125)
        )

    if es_presencia:
        from app.services.attendance_service import AttendanceService
        res_t = await session.execute(text("""
            SELECT MIN(time), MAX(time) 
            FROM eventos_asistencia 
            WHERE espacio_id = 1 
              AND alerta_coherencia_fechas = 0 
              AND person_id_hash NOT LIKE 'TEST_HASH%'
        """))
        min_t, max_t = res_t.fetchone()
        if not max_t:
            raise ValueError(f"Sin eventos de asistencia para entrenar '{clave_modelo}'.")

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
            raise ValueError(f"Datos de presencia insuficientes para '{clave_modelo}'.")

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

        full_idx = pd.date_range(df_series["ds"].min(), df_series["ds"].max(), freq="1h")
        df = df_series.set_index("ds").reindex(full_idx, fill_value=0.0).reset_index()
        df.columns = ["ds", "y"]
        df["y"] = pd.to_numeric(df["y"], errors="coerce").fillna(0.0).clip(lower=0.0)

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
    else:
        df = await _fetch_hourly_data(session, recinto=recinto, sala=sala)
        if len(df) < MIN_ROWS_REQUIRED:
            raise ValueError(f"Datos insuficientes para '{clave_modelo}': {len(df)} filas encontradas (requiere >= {MIN_ROWS_REQUIRED}).")
        espacio_id_ent = 2 if recinto == "vehicular" else 1
        horarios_cfg = await _fetch_horarios_info(session, espacio_id=espacio_id_ent)
        contingencias_cfg = await _fetch_contingencias_info(session, espacio_id=espacio_id_ent)
        df = _enrich_features(
            df,
            cal,
            sala=sala,
            horarios=horarios_cfg,
            contingencias=contingencias_cfg,
            espacio_id=espacio_id_ent,
        )

    df["cap"] = cap_val
    df["floor"] = 0.0

    split_idx = int(len(df) * TRAIN_RATIO)
    train_df = df.iloc[:split_idx].copy()
    test_df = df.iloc[split_idx:].copy()

    hp = _hiperparametros_prophet_por_recinto(recinto)
    train_df_fit, solo_ab, inc_dom = _preparar_df_entrenamiento_abierto(train_df)
    model_eval = _build_prophet(
        growth="linear",
        solo_abierto=solo_ab,
        incluir_domingo=inc_dom,
        **hp,
    )
    fit_cols = ["y"] + _preparar_columnas_prediccion(model_eval, train_df_fit)

    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model_eval.fit(train_df_fit[fit_cols])

    # Evaluación sobre la ventana de validación
    test_cols = _preparar_columnas_prediccion(model_eval, test_df)
    forecast_test = model_eval.predict(test_df[test_cols])

    y_true = test_df["y"].values
    y_pred = np.clip(forecast_test["yhat"].values, a_min=0, a_max=cap_val)
    y_pred[test_df["es_horario_abierto"].values == 0] = 0.0

    denom = np.sum(y_true)
    wape = float(100.0 * np.sum(np.abs(y_true - y_pred)) / denom) if denom > 0 else 0.0
    mae = float(np.mean(np.abs(y_true - y_pred)))

    # Evaluación pareada del campeón activo existente sobre el MISMO conjunto de prueba
    wape_camp_test, mae_camp_test = _evaluar_campeon_existente(
        clave_modelo=clave_modelo,
        archivo_activo=f"{clave_modelo}_active.joblib",
        familia="Prophet",
        test_features=test_df,
        y_true=y_true,
        cap_val=cap_val,
        es_horario_abierto=test_df["es_horario_abierto"].values,
    )

    # Reentrenar modelo final de producción sobre el 100% de la serie histórica
    df_prod_fit, solo_ab_p, inc_dom_p = _preparar_df_entrenamiento_abierto(df)
    model_prod = _build_prophet(
        growth="linear",
        solo_abierto=solo_ab_p,
        incluir_domingo=inc_dom_p,
        **hp,
    )
    prod_cols = ["y"] + _preparar_columnas_prediccion(model_prod, df_prod_fit)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model_prod.fit(df_prod_fit[prod_cols])

    # Guardar artefacto retador temporal
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    ruta_retador = DIRECTORIO_MODELOS / f"{clave_modelo}_retador_v{ts}.joblib"
    joblib.dump(model_prod, ruta_retador)

    return {
        "objeto_modelo": model_prod,
        "ruta_retador": ruta_retador,
        "wape": round(wape, 2),
        "mae": round(mae, 2),
        "wape_campeon_test": wape_camp_test,
        "mae_campeon_test": mae_camp_test,
        "filas_train": len(train_df),
        "filas_test": len(test_df),
        "version": ts,
        "target_tipo": "presencia_plazas" if recinto == "vehicular" else "presencia_sala",
    }


async def _entrenar_retador_kmeans(
    session: AsyncSession,
    clave_modelo: str,
) -> Dict[str, Any]:
    """Entrena y valida un modelo retador KMeans de clustering vehicular."""
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler
    from app.ml.train_kmeans_parking import extract_vehicle_features

    df = await extract_vehicle_features(session)
    if df.empty or len(df) < 10:
        raise ValueError(f"Datos insuficientes para KMeans: {len(df)} perfiles vehiculares (requiere >= 10).")

    feats = ['hora_llegada_avg', 'permanencia_avg_min', 'dias_totales', 'tasa_jornada_extrema']
    X = df[feats].astype(float).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    n_distinct = max(1, int(X.drop_duplicates().shape[0]))
    n_clusters = min(3, len(df), n_distinct)
    scaler = StandardScaler()
    x_scaled = scaler.fit_transform(X)

    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    df['cluster_raw'] = km.fit_predict(x_scaled)
    inercia = float(km.inertia_)
    inercia_media = round(inercia / max(1, len(df)), 4)

    cluster_profiles = []
    for c in sorted(df['cluster_raw'].unique().tolist()):
        cdf = df[df['cluster_raw'] == c]
        cluster_profiles.append({
            "raw_id": int(c),
            "dias_totales": float(cdf['dias_totales'].mean()),
            "permanencia_min": float(cdf['permanencia_avg_min'].mean()),
            "tasa_extrema": float(cdf['tasa_jornada_extrema'].mean()),
        })
    cluster_profiles.sort(key=lambda x: (x["tasa_extrema"], x["permanencia_min"]), reverse=True)
    external_raw = cluster_profiles[0]["raw_id"]
    remaining = sorted([cp for cp in cluster_profiles if cp["raw_id"] != external_raw], key=lambda x: x["dias_totales"], reverse=True)
    label_map: Dict[int, str] = {external_raw: "Posible Uso Externo / Prolongado"}
    if remaining:
        label_map[remaining[0]["raw_id"]] = "Comunidad Regular / Funcionarios"
    if len(remaining) > 1:
        label_map[remaining[1]["raw_id"]] = "Estudiantes / Bloques Acotados"

    # Inercia media por fila del campeón existente si está disponible
    ruta_activo = DIRECTORIO_MODELOS / f"{clave_modelo}.joblib"
    inercia_campeon = None
    if ruta_activo.exists():
        try:
            c_data = joblib.load(ruta_activo)
            if isinstance(c_data, dict):
                inercia_campeon = c_data.get("inertia_per_row") or c_data.get("inertia")
        except Exception:
            pass

    ts = datetime.now().strftime("%Y%m%d_%H%M")
    ruta_retador = DIRECTORIO_MODELOS / f"{clave_modelo}_retador_v{ts}.joblib"
    payload = {
        "model": km,
        "scaler": scaler,
        "features": feats,
        "label_map": label_map,
        "inertia": inercia,
        "inertia_per_row": inercia_media,
    }
    joblib.dump(payload, ruta_retador)

    return {
        "objeto_modelo": payload,
        "ruta_retador": ruta_retador,
        "wape": 0.0,
        "mae": inercia_media,
        "inercia_campeon": inercia_campeon,
        "filas_train": len(df),
        "filas_test": 0,
        "version": ts,
    }


# ---------------------------------------------------------------------------
# Verificación de Día Operativo por Módulo (Horario y Calendario Académico)
# ---------------------------------------------------------------------------

@dataclass
class ContextoOperativoPrecargado:
    """Cache en memoria de horarios, calendario y contingencias para evitar tormentas N+1."""

    horarios_por_espacio: Dict[int, List[Any]] = field(default_factory=dict)
    calendario_por_fecha: Dict[date, Any] = field(default_factory=dict)
    contingencias: List[Any] = field(default_factory=list)


async def precargar_contexto_operativo(
    session: AsyncSession,
    fecha_inicio: Optional[date] = None,
    dias: int = 35,
) -> ContextoOperativoPrecargado:
    """Carga horarios, calendario académico y contingencias de cierre total en exactamente 3 consultas SQL."""
    from zoneinfo import ZoneInfo

    f_ini = fecha_inicio or (datetime.now(ZoneInfo("America/Santiago")).date() - timedelta(days=1))
    f_fin = f_ini + timedelta(days=dias)

    res_h = await session.execute(
        text("""
            SELECT id, espacio_id, anio, descripcion, tipo_horario,
                   fecha_inicio, fecha_fin, hora_apertura, hora_cierre,
                   cierre_dia_siguiente, es_continuo_24h, configuracion_dias, activo
            FROM horarios_operacion
            WHERE activo = 1
            ORDER BY id ASC
        """)
    )
    horarios_por_espacio: Dict[int, List[Any]] = {}
    for row in res_h.fetchall():
        m = SimpleNamespace(**dict(row._mapping))
        horarios_por_espacio.setdefault(int(m.espacio_id), []).append(m)

    res_cal = await session.execute(
        text("""
            SELECT fecha,
                   COALESCE(descripcion, tipo_contingencia, 'Sin hito') AS hito,
                   COALESCE(is_holiday, 0) AS is_holiday,
                   COALESCE(is_break, 0) AS is_break,
                   COALESCE(suspension_actividades, 0) AS suspension_actividades,
                   COALESCE(is_strike_federado, 0) AS is_strike_federado
            FROM calendario_academico
            WHERE fecha >= :ini AND fecha <= :fin
        """),
        {"ini": f_ini, "fin": f_fin},
    )
    calendario_por_fecha: Dict[date, Any] = {}
    for row in res_cal.fetchall():
        f_val = row.fecha.date() if isinstance(row.fecha, datetime) else row.fecha
        calendario_por_fecha[f_val] = SimpleNamespace(
            hito=row.hito,
            is_holiday=row.is_holiday,
            is_break=row.is_break,
            suspension_actividades=row.suspension_actividades,
            is_strike_federado=row.is_strike_federado,
        )

    contingencias: List[Any] = []
    try:
        res_cont = await session.execute(
            text("""
                SELECT fecha_inicio, fecha_fin, espacio_id, titulo, tipo
                FROM contingencias_academicas
                WHERE fecha_inicio <= :fin AND fecha_fin >= :ini
                  AND implica_cierre_total = 1
                  AND (subespacio IS NULL OR subespacio IN ('todos', 'todas', 'global'))
                  AND (hora_inicio IS NULL OR hora_inicio = '')
            """),
            {"ini": f_ini, "fin": f_fin},
        )
        for row in res_cont.fetchall():
            fi = row.fecha_inicio.date() if isinstance(row.fecha_inicio, datetime) else row.fecha_inicio
            ff = row.fecha_fin.date() if isinstance(row.fecha_fin, datetime) else row.fecha_fin
            contingencias.append(
                SimpleNamespace(
                    fecha_inicio=fi,
                    fecha_fin=ff,
                    espacio_id=row.espacio_id,
                    titulo=row.titulo,
                    tipo=row.tipo,
                )
            )
    except Exception:
        contingencias = []

    return ContextoOperativoPrecargado(
        horarios_por_espacio=horarios_por_espacio,
        calendario_por_fecha=calendario_por_fecha,
        contingencias=contingencias,
    )


def evaluar_modulo_opera_en_fecha_memoria(
    ctx: ContextoOperativoPrecargado,
    espacio_id: int,
    fecha_consulta: datetime,
) -> tuple[bool, str]:
    """Evalúa en memoria si un recinto opera en `fecha_consulta` sin emitir consultas SQL."""
    from app.services.calendar_scraper import obtener_feriado_oficial_chile

    fecha_dia = fecha_consulta.date()
    dias_map = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
    dia_nombre = dias_map[fecha_dia.weekday()]

    horarios = ctx.horarios_por_espacio.get(int(espacio_id), [])
    reglas_rango = [
        h for h in horarios
        if h.activo and h.fecha_inicio and h.fecha_fin and (h.fecha_inicio.date() <= fecha_dia <= h.fecha_fin.date())
    ]
    tiene_campana_24h = any(h.es_continuo_24h for h in reglas_rango)

    feriado_civil = obtener_feriado_oficial_chile(fecha_dia)
    if feriado_civil and not tiene_campana_24h:
        return False, f"{feriado_civil} el {fecha_dia.isoformat()}"

    fila_cal = ctx.calendario_por_fecha.get(fecha_dia)
    if fila_cal and not tiene_campana_24h:
        if fila_cal.is_holiday:
            return False, f"Feriado en calendario académico ({fila_cal.hito}) el {fecha_dia.isoformat()}"
        if fila_cal.suspension_actividades:
            return False, f"Suspensión de actividades ({fila_cal.hito}) el {fecha_dia.isoformat()}"
        if fila_cal.is_break:
            return False, f"Receso académico ({fila_cal.hito}) el {fecha_dia.isoformat()}"
        if fila_cal.is_strike_federado:
            return False, f"Contingencia o paro registrado ({fila_cal.hito}) el {fecha_dia.isoformat()}"

    if not tiene_campana_24h:
        for c in ctx.contingencias:
            if c.fecha_inicio <= fecha_dia <= c.fecha_fin and (c.espacio_id is None or int(c.espacio_id) == int(espacio_id)):
                return False, f"Cierre total registrado ({c.titulo}) el {fecha_dia.isoformat()}"

    reglas_a_evaluar = reglas_rango if reglas_rango else [
        h for h in horarios if h.activo and h.anio == fecha_dia.year
    ]
    if not reglas_a_evaluar and horarios:
        reglas_a_evaluar = [h for h in horarios if h.activo]

    if not reglas_a_evaluar:
        if dia_nombre == "domingo":
            return False, f"Día domingo sin horario operativo configurado ({fecha_dia.isoformat()})"
        return True, f"Día hábil estándar {dia_nombre} ({fecha_dia.isoformat()})"

    for regla in reglas_a_evaluar:
        if regla.es_continuo_24h:
            return True, f"Operativo por campaña continua 24h ({getattr(regla, 'descripcion', '24h')})"

        cfg_dias = None
        if regla.configuracion_dias:
            if isinstance(regla.configuracion_dias, dict):
                cfg_dias = regla.configuracion_dias
            elif isinstance(regla.configuracion_dias, str) and regla.configuracion_dias.strip():
                try:
                    cfg_dias = json.loads(regla.configuracion_dias)
                except Exception:
                    cfg_dias = None

        if cfg_dias and isinstance(cfg_dias, dict) and dia_nombre in cfg_dias:
            dia_info = cfg_dias[dia_nombre]
            if dia_info.get("abierto", True):
                ap = dia_info.get("apertura", regla.hora_apertura)
                ci = dia_info.get("cierre", regla.hora_cierre)
                return True, f"Operativo en {dia_nombre} ({ap} - {ci})"
        else:
            if dia_nombre != "domingo" and regla.hora_apertura and regla.hora_cierre:
                return True, f"Operativo en {dia_nombre} ({regla.hora_apertura} - {regla.hora_cierre})"

    return False, f"Módulo cerrado según horario de operación para {dia_nombre} ({fecha_dia.isoformat()})"


def evaluar_hora_operativa_campus_memoria(
    ctx: ContextoOperativoPrecargado,
    dt_consulta: datetime,
    margen_post_cierre_horas: int = 1,
) -> tuple[bool, str]:
    """Evalúa en memoria si alguna sede opera a la hora exacta `dt_consulta`."""
    fecha_dia = dt_consulta.date()
    hora_actual = dt_consulta.hour
    dias_map = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
    dia_nombre = dias_map[fecha_dia.weekday()]

    motivos_cerrado = []
    for esp_id in (1, 2):
        opera_dia, motivo_dia = evaluar_modulo_opera_en_fecha_memoria(ctx, esp_id, dt_consulta)
        if not opera_dia:
            motivos_cerrado.append(f"Espacio {esp_id}: {motivo_dia}")
            continue

        horarios = ctx.horarios_por_espacio.get(esp_id, [])
        reglas_rango = [
            h for h in horarios
            if h.activo and h.fecha_inicio and h.fecha_fin and (h.fecha_inicio.date() <= fecha_dia <= h.fecha_fin.date())
        ]
        reglas_a_evaluar = reglas_rango if reglas_rango else [
            h for h in horarios if h.activo and h.anio == fecha_dia.year
        ]
        if not reglas_a_evaluar and horarios:
            reglas_a_evaluar = [h for h in horarios if h.activo]

        if not reglas_a_evaluar:
            ap_h = 9 if dia_nombre == "sabado" else 8
            ci_h = 14 if dia_nombre == "sabado" else 21
            if ap_h <= hora_actual <= min(23, ci_h + margen_post_cierre_horas):
                return True, f"Horario hábil estándar espacio {esp_id} ({ap_h:02d}:00-{ci_h:02d}:00)"
            motivos_cerrado.append(f"Espacio {esp_id} fuera de horario ({ap_h:02d}:00-{ci_h:02d}:00)")
            continue

        for regla in reglas_a_evaluar:
            if regla.es_continuo_24h:
                return True, f"Campaña 24h activa ({getattr(regla, 'descripcion', '24h')})"

            cfg_dias = None
            if regla.configuracion_dias:
                if isinstance(regla.configuracion_dias, dict):
                    cfg_dias = regla.configuracion_dias
                elif isinstance(regla.configuracion_dias, str) and regla.configuracion_dias.strip():
                    try:
                        cfg_dias = json.loads(regla.configuracion_dias)
                    except Exception:
                        cfg_dias = None

            ap_str = regla.hora_apertura or "08:00"
            ci_str = regla.hora_cierre or "21:00"
            abierto_hoy = dia_nombre != "domingo"

            if cfg_dias and isinstance(cfg_dias, dict) and dia_nombre in cfg_dias:
                dia_info = cfg_dias[dia_nombre]
                abierto_hoy = bool(dia_info.get("abierto", True))
                ap_str = dia_info.get("apertura", ap_str) or ap_str
                ci_str = dia_info.get("cierre", ci_str) or ci_str

            if not abierto_hoy:
                continue

            try:
                ap_h = int(str(ap_str).split(":")[0])
                ci_h = int(str(ci_str).split(":")[0])
                if regla.cierre_dia_siguiente or (cfg_dias and cfg_dias.get(dia_nombre, {}).get("cierre_dia_siguiente")):
                    if hora_actual >= ap_h or hora_actual <= (ci_h + margen_post_cierre_horas):
                        return True, f"Horario nocturno activo espacio {esp_id}"
                else:
                    if ap_h <= hora_actual <= min(23, ci_h + margen_post_cierre_horas):
                        return True, f"Horario operativo activo espacio {esp_id} ({ap_str}-{ci_str})"
            except Exception:
                return True, f"Horario operativo espacio {esp_id}"

        motivos_cerrado.append(f"Espacio {esp_id} fuera de horario de atención a las {hora_actual:02d}:00")

    return False, "; ".join(motivos_cerrado) if motivos_cerrado else "Fuera de horario laboral"


async def verificar_modulo_opera_en_fecha(
    session: AsyncSession,
    espacio_id: int,
    fecha_consulta: Optional[datetime] = None,
    contexto: Optional[ContextoOperativoPrecargado] = None,
) -> tuple[bool, str]:
    """
    Verifica si el módulo correspondiente a `espacio_id` (1 = Biblioteca, 2 = Estacionamiento)
    opera en la fecha indicada según el Calendario Académico UCT, Feriados Legales Chilenos,
    Contingencias de Cierre y los Horarios de Operación activos.
    """
    from zoneinfo import ZoneInfo

    dt_eval = fecha_consulta or datetime.now(ZoneInfo("America/Santiago")).replace(tzinfo=None)
    if contexto is not None:
        return evaluar_modulo_opera_en_fecha_memoria(contexto, espacio_id, dt_eval)

    from app.services.config_service import get_horarios_operacion
    from app.services.calendar_scraper import obtener_feriado_oficial_chile
    fecha_dia = dt_eval.date()
    dias_map = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
    dia_nombre = dias_map[fecha_dia.weekday()]

    # 1. Consultar horarios de operación activos para el recinto
    horarios = await get_horarios_operacion(session, espacio_id=espacio_id)
    reglas_rango = [
        h for h in horarios
        if h.activo and h.fecha_inicio and h.fecha_fin and (h.fecha_inicio.date() <= fecha_dia <= h.fecha_fin.date())
    ]
    tiene_campana_24h = any(h.es_continuo_24h for h in reglas_rango)

    # 2. Verificar feriado oficial chileno de calendario civil
    feriado_civil = obtener_feriado_oficial_chile(fecha_dia)
    if feriado_civil and not tiene_campana_24h:
        return False, f"{feriado_civil} el {fecha_dia.isoformat()}"

    # 3. Consultar calendario académico en base de datos para la fecha (columna descripcion)
    sql_cal = text("""
        SELECT TOP 1
            COALESCE(descripcion, tipo_contingencia, 'Sin hito') AS hito,
            COALESCE(is_holiday, 0) AS is_holiday,
            COALESCE(is_break, 0) AS is_break,
            COALESCE(suspension_actividades, 0) AS suspension_actividades,
            COALESCE(is_strike_federado, 0) AS is_strike_federado
        FROM calendario_academico
        WHERE fecha = :fecha
    """)
    fila_cal = (await session.execute(sql_cal, {"fecha": fecha_dia})).fetchone()
    if fila_cal and not tiene_campana_24h:
        if fila_cal.is_holiday:
            return False, f"Feriado en calendario académico ({fila_cal.hito}) el {fecha_dia.isoformat()}"
        if fila_cal.suspension_actividades:
            return False, f"Suspensión de actividades ({fila_cal.hito}) el {fecha_dia.isoformat()}"
        if fila_cal.is_break:
            return False, f"Receso académico ({fila_cal.hito}) el {fecha_dia.isoformat()}"
        if fila_cal.is_strike_federado:
            return False, f"Contingencia o paro registrado ({fila_cal.hito}) el {fecha_dia.isoformat()}"

    # 4. Consultar contingencias administrativas que impliquen cierre total del recinto
    try:
        sql_cont = text("""
            SELECT TOP 1 titulo, tipo
            FROM contingencias_academicas
            WHERE fecha_inicio <= :fecha AND fecha_fin >= :fecha
              AND implica_cierre_total = 1
              AND (espacio_id IS NULL OR espacio_id = :espacio_id)
              AND (subespacio IS NULL OR subespacio IN ('todos', 'todas', 'global'))
              AND (hora_inicio IS NULL OR hora_inicio = '')
        """)
        fila_cont = (await session.execute(sql_cont, {"fecha": fecha_dia, "espacio_id": espacio_id})).fetchone()
        if fila_cont and not tiene_campana_24h:
            return False, f"Cierre total registrado ({fila_cont.titulo}) el {fecha_dia.isoformat()}"
    except Exception:
        pass

    # 5. Evaluar reglas horarias del módulo para el día de la semana
    reglas_a_evaluar = reglas_rango if reglas_rango else [
        h for h in horarios if h.activo and h.anio == fecha_dia.year
    ]
    if not reglas_a_evaluar and horarios:
        reglas_a_evaluar = [h for h in horarios if h.activo]

    if not reglas_a_evaluar:
        # Si no hay reglas configuradas en BD, lunes a sábado se considera hábil y domingo cerrado
        if dia_nombre == "domingo":
            return False, f"Día domingo sin horario operativo configurado ({fecha_dia.isoformat()})"
        return True, f"Día hábil estándar {dia_nombre} ({fecha_dia.isoformat()})"

    for regla in reglas_a_evaluar:
        if regla.es_continuo_24h:
            desc_regla = getattr(regla, "descripcion", "24h")
            return True, f"Operativo por campaña continua 24h ({desc_regla})"

        cfg_dias = None
        if regla.configuracion_dias:
            if isinstance(regla.configuracion_dias, dict):
                cfg_dias = regla.configuracion_dias
            elif isinstance(regla.configuracion_dias, str) and regla.configuracion_dias.strip():
                try:
                    cfg_dias = json.loads(regla.configuracion_dias)
                except Exception:
                    cfg_dias = None

        if cfg_dias and isinstance(cfg_dias, dict) and dia_nombre in cfg_dias:
            dia_info = cfg_dias[dia_nombre]
            if dia_info.get("abierto", True):
                ap = dia_info.get("apertura", regla.hora_apertura)
                ci = dia_info.get("cierre", regla.hora_cierre)
                return True, f"Operativo en {dia_nombre} ({ap} - {ci})"
        else:
            # Si la regla no desglosa días, opera lunes a sábado por defecto
            if dia_nombre != "domingo" and regla.hora_apertura and regla.hora_cierre:
                return True, f"Operativo en {dia_nombre} ({regla.hora_apertura} - {regla.hora_cierre})"

    return False, f"Módulo cerrado según horario de operación para {dia_nombre} ({fecha_dia.isoformat()})"


async def verificar_hora_operativa_campus(
    session: AsyncSession,
    dt_consulta: Optional[datetime] = None,
    margen_post_cierre_horas: int = 1,
    contexto: Optional[ContextoOperativoPrecargado] = None,
) -> tuple[bool, str]:
    """
    Verifica si en la fecha y hora exacta `dt_consulta` corresponde ejecutar la sincronización
    horaria en vivo (al menos un recinto opera ese día y la hora está dentro de [apertura, cierre + margen]).
    """
    from zoneinfo import ZoneInfo

    dt_eval = dt_consulta or datetime.now(ZoneInfo("America/Santiago")).replace(tzinfo=None)
    if contexto is not None:
        return evaluar_hora_operativa_campus_memoria(
            contexto, dt_eval, margen_post_cierre_horas=margen_post_cierre_horas
        )

    from app.services.config_service import get_horarios_operacion
    fecha_dia = dt_eval.date()
    hora_actual = dt_eval.hour
    dias_map = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
    dia_nombre = dias_map[fecha_dia.weekday()]

    motivos_cerrado = []
    for esp_id in (1, 2):
        opera_dia, motivo_dia = await verificar_modulo_opera_en_fecha(session, esp_id, dt_eval)
        if not opera_dia:
            motivos_cerrado.append(f"Espacio {esp_id}: {motivo_dia}")
            continue

        horarios = await get_horarios_operacion(session, espacio_id=esp_id)
        reglas_rango = [
            h for h in horarios
            if h.activo and h.fecha_inicio and h.fecha_fin and (h.fecha_inicio.date() <= fecha_dia <= h.fecha_fin.date())
        ]
        reglas_a_evaluar = reglas_rango if reglas_rango else [
            h for h in horarios if h.activo and h.anio == fecha_dia.year
        ]
        if not reglas_a_evaluar and horarios:
            reglas_a_evaluar = [h for h in horarios if h.activo]

        if not reglas_a_evaluar:
            # Horario estándar institucional por defecto: Lunes-Viernes 08:00 a 21:00, Sábado 09:00 a 14:00
            ap_h = 9 if dia_nombre == "sabado" else 8
            ci_h = 14 if dia_nombre == "sabado" else 21
            if ap_h <= hora_actual <= min(23, ci_h + margen_post_cierre_horas):
                return True, f"Horario hábil estándar espacio {esp_id} ({ap_h:02d}:00-{ci_h:02d}:00)"
            motivos_cerrado.append(f"Espacio {esp_id} fuera de horario ({ap_h:02d}:00-{ci_h:02d}:00)")
            continue

        for regla in reglas_a_evaluar:
            if regla.es_continuo_24h:
                desc_regla = getattr(regla, "descripcion", "24h")
                return True, f"Campaña 24h activa ({desc_regla})"

            cfg_dias = None
            if regla.configuracion_dias:
                if isinstance(regla.configuracion_dias, dict):
                    cfg_dias = regla.configuracion_dias
                elif isinstance(regla.configuracion_dias, str) and regla.configuracion_dias.strip():
                    try:
                        cfg_dias = json.loads(regla.configuracion_dias)
                    except Exception:
                        cfg_dias = None

            ap_str = regla.hora_apertura or "08:00"
            ci_str = regla.hora_cierre or "21:00"
            abierto_hoy = dia_nombre != "domingo"

            if cfg_dias and isinstance(cfg_dias, dict) and dia_nombre in cfg_dias:
                dia_info = cfg_dias[dia_nombre]
                abierto_hoy = bool(dia_info.get("abierto", True))
                ap_str = dia_info.get("apertura", ap_str) or ap_str
                ci_str = dia_info.get("cierre", ci_str) or ci_str

            if not abierto_hoy:
                continue

            try:
                ap_h = int(str(ap_str).split(":")[0])
                ci_h = int(str(ci_str).split(":")[0])
                if regla.cierre_dia_siguiente or (cfg_dias and cfg_dias.get(dia_nombre, {}).get("cierre_dia_siguiente")):
                    if hora_actual >= ap_h or hora_actual <= (ci_h + margen_post_cierre_horas):
                        return True, f"Horario nocturno activo espacio {esp_id}"
                else:
                    if ap_h <= hora_actual <= min(23, ci_h + margen_post_cierre_horas):
                        return True, f"Horario operativo activo espacio {esp_id} ({ap_str}-{ci_str})"
            except Exception:
                return True, f"Horario operativo espacio {esp_id}"

        motivos_cerrado.append(f"Espacio {esp_id} fuera de horario de atención a las {hora_actual:02d}:00")

    return False, "; ".join(motivos_cerrado) if motivos_cerrado else "Fuera de horario laboral"


# ---------------------------------------------------------------------------
# Orquestación Campeón vs. Retador
# ---------------------------------------------------------------------------

def _promover_archivo_atomico(src: Path, dst: Path) -> None:
    """Copia a archivo temporal en el mismo directorio y reemplaza atómicamente con os.replace."""
    tmp_dst = dst.with_name(f".{dst.name}.tmp.{os.getpid()}")
    shutil.copyfile(src, tmp_dst)
    os.replace(tmp_dst, dst)


def _podar_versiones_antiguas(clave: str, conservar: int = 5) -> None:
    """Elimina snapshots versionados antiguos conservando únicamente los últimos N."""
    versiones = sorted(
        DIRECTORIO_MODELOS.glob(f"{clave}_v*.joblib"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for obsoleto in versiones[conservar:]:
        try:
            obsoleto.unlink(missing_ok=True)
        except Exception as exc_poda:
            logger.warning(f"[orquestador] No se pudo podar versión antigua {obsoleto.name}: {exc_poda}")


async def entrenar_todos_los_modelos(
    db: Optional[AsyncSession] = None,
    solo_modulos_operativos_hoy: bool = False,
) -> List[Dict[str, Any]]:
    """
    Entrena modelos retadores para Prophet y KMeans.
    Si `solo_modulos_operativos_hoy=True` (ejecución automática matutina), verifica primero
    si cada módulo (`biblioteca` = 1, `vehicular` = 2) trabaja en la fecha actual según su
    horario de operación y el calendario académico.
    Evalúa métricas sobre ventana de validación (WAPE, MAE) y promueve a producción
    (*_active.joblib) ÚNICAMENTE si supera o iguala al modelo campeón actual.
    """
    logger.info("=================================================================")
    logger.info("   INICIANDO ORQUESTADOR DE REENTRENAMIENTO CAMPEÓN vs. RETADOR   ")
    logger.info("=================================================================")

    resultados: List[Dict[str, Any]] = []

    async def _procesar_con_sesion(session: AsyncSession):
        estado_operativo_por_espacio: Dict[int, tuple[bool, str]] = {}
        if solo_modulos_operativos_hoy:
            for esp_id in (1, 2):
                estado_operativo_por_espacio[esp_id] = await verificar_modulo_opera_en_fecha(session, esp_id)
                opera, motivo = estado_operativo_por_espacio[esp_id]
                logger.info(f"[orquestador] Verificación operativa espacio_id={esp_id}: opera={opera} ({motivo})")

        for config_m in MODELOS_CATALOGO:
            clave = config_m["clave"]
            campeon = _leer_metadatos_campeon(clave, config_m)
            wape_campeon = campeon.get("wape")
            mae_campeon = campeon.get("mae")

            espacio_id_modelo = config_m.get("espacio_id") or (1 if config_m.get("recinto") == "biblioteca" else 2)
            if solo_modulos_operativos_hoy and espacio_id_modelo in estado_operativo_por_espacio:
                opera_hoy, motivo_op = estado_operativo_por_espacio[espacio_id_modelo]
                if not opera_hoy:
                    logger.info(f"[orquestador] Omitiendo entrenamiento de {clave}: {motivo_op}")
                    resultados.append({
                        "modelo": clave,
                        "familia": config_m["familia"],
                        "estado": "omitido_dia_no_laboral",
                        "promovido": False,
                        "motivo": motivo_op,
                        "campeon_conservado": True,
                        "wape_campeon": wape_campeon,
                    })
                    continue

            logger.info(f"[orquestador] Evaluando modelo: {clave} (Campeón actual: WAPE={wape_campeon}%, MAE={mae_campeon})")

            # 1. Intentar entrenar retador
            try:
                if config_m["familia"] == "Prophet":
                    retador = await _entrenar_retador_prophet(session, clave, config_m["recinto"], config_m["sala"])
                elif config_m["familia"] == "KMeans":
                    retador = await _entrenar_retador_kmeans(session, clave)
                else:
                    continue

                wape_retador = retador["wape"]
                mae_retador = retador["mae"]
                ruta_retador: Path = retador["ruta_retador"]

                wape_campeon_pareado = retador.get("wape_campeon_test")
                mae_campeon_pareado = retador.get("mae_campeon_test")
                target_retador = retador.get("target_tipo")
                target_campeon = campeon.get("target_tipo")

                # Migración única de modelos vehiculares desde flujo (veh/h) a presencia física (plazas)
                if config_m.get("recinto") == "vehicular" and target_retador == "presencia_plazas" and target_campeon != "presencia_plazas":
                    es_pareado = False
                    wape_benchmark = None
                    mae_benchmark = None
                else:
                    es_pareado = wape_campeon_pareado is not None
                    wape_benchmark = wape_campeon_pareado if es_pareado else wape_campeon
                    mae_benchmark = mae_campeon_pareado if es_pareado else mae_campeon

                # 2. Evaluación de Promoción: Supera o iguala al benchmark del campeón
                if config_m["familia"] == "KMeans":
                    inercia_retador = mae_retador
                    inercia_ref = retador.get("inercia_campeon") or mae_campeon
                    debe_promover = (inercia_ref is None) or (inercia_retador <= inercia_ref * 1.05)
                else:
                    debe_promover = (wape_benchmark is None) or (wape_retador <= wape_benchmark)

                desc_benchmark = (
                    f"WAPE={wape_benchmark}% (evaluación pareada en test actual)"
                    if es_pareado
                    else f"WAPE={wape_benchmark}% (referencia histórica)"
                )

                if debe_promover:
                    # Promover retador a campeón activo de forma atómica con os.replace
                    ruta_activa = DIRECTORIO_MODELOS / config_m["archivo_activo"]
                    _promover_archivo_atomico(ruta_retador, ruta_activa)

                    # Guardar copia versionada oficial y podar históricas antiguas
                    ts = retador["version"]
                    ruta_versionada = DIRECTORIO_MODELOS / f"{clave}_v{ts}.joblib"
                    _promover_archivo_atomico(ruta_retador, ruta_versionada)
                    _podar_versiones_antiguas(clave, conservar=5)

                    # Actualizar metadatos del campeón
                    nuevos_meta = {
                        "clave": clave,
                        "familia": config_m["familia"],
                        "version": ts,
                        "archivo": config_m["archivo_activo"],
                        "wape": wape_retador,
                        "mae": mae_retador,
                        "actualizado_en": ahora_utc().isoformat(),
                        "estado": "activo",
                        "es_campeon": True,
                        "promovido_en": ahora_utc().isoformat(),
                        "campeon_anterior_wape": wape_benchmark,
                        "evaluacion_pareada": es_pareado,
                        "target_tipo": retador.get("target_tipo"),
                    }
                    _guardar_metadatos_campeon(clave, nuevos_meta)
                    invalidar_cache_modelo(ruta_activa)

                    logger.info(
                        f"[orquestador] ¡RETADOR PROMOVIDO! {clave}: Retador WAPE={wape_retador}% vs Campeón {desc_benchmark}."
                    )
                    resultados.append({
                        "modelo": clave,
                        "familia": config_m["familia"],
                        "estado": "promovido",
                        "promovido": True,
                        "wape": wape_retador,
                        "mae": mae_retador,
                        "wape_retador": wape_retador,
                        "wape_campeon": wape_benchmark,
                        "campeon_anterior_wape": wape_campeon,
                        "evaluacion_pareada": es_pareado,
                        "motivo": f"Retador promovido con éxito ({wape_retador}% vs {wape_benchmark}% del campeón pareado).",
                        "version": ts,
                    })
                else:
                    # Retador no superó al campeón actual: se descarta y se registra la auditoría del campeón
                    logger.warning(
                        f"[orquestador] Retador descartado para {clave}: WAPE={wape_retador}% no superó al campeón ({desc_benchmark})."
                    )
                    meta_campeon_existente = _leer_metadatos_campeon(clave, config_m)
                    meta_campeon_existente["ultima_auditoria_en"] = ahora_utc().isoformat()
                    meta_campeon_existente["ultimo_resultado_auditoria"] = f"Campeón validado (WAPE={wape_benchmark}% vs retador {wape_retador}%)"
                    _guardar_metadatos_campeon(clave, meta_campeon_existente)
                    resultados.append({
                        "modelo": clave,
                        "familia": config_m["familia"],
                        "estado": "rechazado",
                        "promovido": False,
                        "motivo": f"Retador (WAPE {wape_retador}%) no superó al campeón actual ({desc_benchmark}).",
                        "wape_retador": wape_retador,
                        "wape_campeon": wape_benchmark,
                        "campeon_conservado": True,
                        "evaluacion_pareada": es_pareado,
                    })

                # Limpieza de archivo temporal retador
                if ruta_retador.exists():
                    ruta_retador.unlink(missing_ok=True)

            except Exception as e_train:
                logger.warning(
                    f"[orquestador] Entrenamiento de retador fallido para {clave}: {e_train}. "
                    "El modelo campeón actual se conserva intacto en producción."
                )
                resultados.append({
                    "modelo": clave,
                    "familia": config_m["familia"],
                    "estado": "fallido",
                    "promovido": False,
                    "error": str(e_train),
                    "campeon_conservado": True,
                    "wape_campeon": wape_campeon,
                })

    if db is not None:
        await _procesar_con_sesion(db)
    else:
        async with AsyncSessionLocal() as session:
            await _procesar_con_sesion(session)

    try:
        from app.core.cache import limpiar_toda_la_cache
        await limpiar_toda_la_cache()
    except Exception as err_cache:
        logger.warning(f"[orquestador] No se pudo limpiar caché tras reentrenamiento: {err_cache}")

    return resultados


# ---------------------------------------------------------------------------
# Consulta de Estado para Admin
# ---------------------------------------------------------------------------

def obtener_estado_general_modelos() -> List[Dict[str, Any]]:
    """Genera el reporte integral de versiones activas, WAPE, MAE y estado para Admin_Sistema."""
    reporte = []
    for config_m in MODELOS_CATALOGO:
        clave = config_m["clave"]
        campeon = _leer_metadatos_campeon(clave, config_m)
        ruta_activa = DIRECTORIO_MODELOS / config_m["archivo_activo"]

        disponible = ruta_activa.exists()
        mtime = None
        if disponible:
            try:
                mtime = datetime.fromtimestamp(ruta_activa.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass

        reporte.append({
            "clave": clave,
            "familia": config_m["familia"],
            "archivo": config_m["archivo_activo"],
            "disponible": disponible,
            "version": campeon.get("version"),
            "wape": campeon.get("wape"),
            "mae": campeon.get("mae"),
            "ultima_modificacion": mtime or campeon.get("actualizado_en"),
            "estado": "operativo" if disponible else "no_disponible",
        })
    return reporte

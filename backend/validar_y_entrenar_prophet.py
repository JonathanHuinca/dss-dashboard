"""
Módulo de Validación, Backtesting y Entrenamiento Riguroso para Prophet (DSS UCT).

Implementa el pipeline de validación cruzada temporal con diagnósticos de
residuos, cobertura probabilística y cálculo de métricas para la Biblioteca
del Campus San Francisco (Universidad Católica de Temuco).
"""

from typing import Dict, Any, Optional, Tuple
import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from prophet import Prophet
from prophet.diagnostics import cross_validation, performance_metrics
import joblib


# -----------------------------------------------------------------------------
# 1. Preparación y Regularización del Conjunto de Datos
# -----------------------------------------------------------------------------

def preparar_dataset(
    df: pd.DataFrame,
    columna_fecha: str = "ds",
    columna_valor: str = "y",
    freq: str = "1h",
) -> pd.DataFrame:
    """
    Normaliza y regulariza la serie temporal horaria de asistencia peatonal.

    - Convierte la columna temporal a datetime sin zona horaria.
    - Genera una grilla temporal continua para rellenar horas cerradas con cero explícito.
    - Limpia valores atípicos negativos y asegura tipos numéricos estrictos.
    """
    if columna_fecha not in df.columns or columna_valor not in df.columns:
        raise ValueError(
            f"El DataFrame debe contener las columnas '{columna_fecha}' y '{columna_valor}'."
        )

    df_limpio = df[[columna_fecha, columna_valor]].copy()
    df_limpio[columna_fecha] = pd.to_datetime(df_limpio[columna_fecha]).dt.tz_localize(None)
    df_limpio = df_limpio.sort_values(columna_fecha).drop_duplicates(subset=[columna_fecha])

    # Reindexación temporal completa para evitar 'interpolaciones fantasma' en la noche
    fecha_min = df_limpio[columna_fecha].min()
    fecha_max = df_limpio[columna_fecha].max()
    indice_completo = pd.date_range(fecha_min, fecha_max, freq=freq, name=columna_fecha)

    df_regularizado = (
        df_limpio.set_index(columna_fecha)
        .reindex(indice_completo, fill_value=0)
        .reset_index()
    )
    df_regularizado.rename(columns={"index": columna_fecha}, inplace=True)

    # Sanitización de flujo de entradas (no admite valores negativos)
    df_regularizado[columna_valor] = (
        pd.to_numeric(df_regularizado[columna_valor], errors="coerce")
        .fillna(0)
        .clip(lower=0)
    )

    # Incorporar regresores de calendario académico si vienen en el DataFrame original
    regresores_opcionales = [
        "es_horario_abierto",
        "is_exam_period",
        "is_break",
        "is_strike",
    ]
    for reg in regresores_opcionales:
        if reg in df.columns:
            mapeo = df.set_index(columna_fecha)[reg].to_dict()
            df_regularizado[reg] = df_regularizado[columna_fecha].map(mapeo).fillna(0).astype(int)
        else:
            # Si no vienen en el origen, derivar horario operativo por defecto
            if reg == "es_horario_abierto":
                # Horario estándar: lunes a viernes 08:00-20:00, sábados 09:00-14:00, domingos cerrado
                hora = df_regularizado[columna_fecha].dt.hour
                dia_sem = df_regularizado[columna_fecha].dt.dayofweek
                es_habil = (dia_sem < 5) & (hora >= 8) & (hora < 20)
                es_sabado = (dia_sem == 5) & (hora >= 9) & (hora < 14)
                df_regularizado["es_horario_abierto"] = (es_habil | es_sabado).astype(int)
            else:
                df_regularizado[reg] = 0

    return df_regularizado


# -----------------------------------------------------------------------------
# 2. Configuración y Entrenamiento del Modelo Prophet
# -----------------------------------------------------------------------------

def entrenar_modelo(df_train: pd.DataFrame, config: Optional[Dict[str, Any]] = None) -> Prophet:
    """
    Instancia y calibra el modelo aditivo Prophet con los parámetros institucionales del DSS UCT.
    """
    if config is None:
        config = {
            "growth": "linear",
            "seasonality_mode": "additive",
            "daily_seasonality": False,  # Se reemplaza por estacionalidad personalizada de Fourier
            "weekly_seasonality": False,
            "yearly_seasonality": False,
            "changepoint_prior_scale": 0.05,
            "seasonality_prior_scale": 10.0,
            "holidays_prior_scale": 10.0,
            "interval_width": 0.80,
            "orden_fourier_diario": 8,
            "orden_fourier_semanal": 4,
        }

    modelo = Prophet(
        growth=config.get("growth", "linear"),
        seasonality_mode=config.get("seasonality_mode", "additive"),
        daily_seasonality=False,
        weekly_seasonality=False,
        yearly_seasonality=False,
        changepoint_prior_scale=config.get("changepoint_prior_scale", 0.05),
        seasonality_prior_scale=config.get("seasonality_prior_scale", 10.0),
        holidays_prior_scale=config.get("holidays_prior_scale", 10.0),
        interval_width=config.get("interval_width", 0.80),
    )

    # Estacionalidad Diaria UCT: armónicos de orden 8 para capturar picos de 11:00 y 16:00
    modelo.add_seasonality(
        name="diaria_uct",
        period=1,
        fourier_order=config.get("orden_fourier_diario", 8),
    )

    # Estacionalidad Semanal UCT: armónicos de orden 4 para capturar caída del viernes y sábado
    modelo.add_seasonality(
        name="semanal_uct",
        period=7,
        fourier_order=config.get("orden_fourier_semanal", 4),
    )

    # Regresores deterministas de calendario y operación
    regresores = ["es_horario_abierto", "is_exam_period", "is_break", "is_strike"]
    for reg in regresores:
        if reg in df_train.columns:
            modelo.add_regressor(reg, standardize=False)

    columnas_ajuste = ["ds", "y"] + [r for r in regresores if r in df_train.columns]
    modelo.fit(df_train[columnas_ajuste])
    return modelo


# -----------------------------------------------------------------------------
# 3. Backtesting con Validación Cruzada Temporal
# -----------------------------------------------------------------------------

def ejecutar_backtesting(
    model: Prophet,
    initial: str = "90 days",
    period: str = "14 days",
    horizon: str = "7 days",
) -> pd.DataFrame:
    """
    Ejecuta backtesting simulado en ventanas rodantes con la librería nativa de Prophet.

    - initial: Ventana histórica mínima de entrenamiento (ej. 90 días).
    - period: Frecuencia de corte con la que avanza el horizonte de simulación (ej. cada 14 días).
    - horizon: Período prospectivo a evaluar en cada corte (ej. 7 días / 168 horas).
    """
    df_cv = cross_validation(
        model,
        initial=initial,
        period=period,
        horizon=horizon,
        parallel=None,
    )

    # Clipping físico determinista: asistencia predicha no puede ser negativa
    df_cv["yhat"] = df_cv["yhat"].clip(lower=0)
    df_cv["yhat_lower"] = df_cv["yhat_lower"].clip(lower=0)
    df_cv["yhat_upper"] = df_cv["yhat_upper"].clip(lower=0)

    return df_cv


# -----------------------------------------------------------------------------
# 4. Cálculo e Interpretación de Métricas Cuantitativas
# -----------------------------------------------------------------------------

def calcular_metricas(df_cv: pd.DataFrame) -> Dict[str, Any]:
    """
    Calcula MAE, RMSE, WAPE y la Cobertura Empírica del intervalo de incertidumbre al 80%.
    """
    y_real = df_cv["y"].to_numpy(dtype=float)
    y_pred = df_cv["yhat"].to_numpy(dtype=float)
    y_inf = df_cv["yhat_lower"].to_numpy(dtype=float)
    y_sup = df_cv["yhat_upper"].to_numpy(dtype=float)

    errores = y_real - y_pred
    mae = float(np.mean(np.abs(errores)))
    rmse = float(np.sqrt(np.mean(errores ** 2)))

    # WAPE (Weighted Absolute Percentage Error) evita división por cero en horas cerradas
    suma_real = float(np.sum(y_real))
    wape = float(100.0 * np.sum(np.abs(errores)) / suma_real) if suma_real > 0 else 0.0

    # Cobertura empírica: Porcentaje de observaciones reales dentro de [yhat_lower, yhat_upper]
    dentro_intervalo = (y_real >= y_inf) & (y_real <= y_sup)
    cobertura_pct = float(100.0 * np.mean(dentro_intervalo))

    # Criterio de veredicto para producción
    apto = (mae <= 6.0) and (cobertura_pct >= 72.0)

    metricas = {
        "total_observaciones_evaluadas": int(len(df_cv)),
        "mae_personas_hora": round(mae, 2),
        "rmse_personas_hora": round(rmse, 2),
        "wape_porcentaje": round(wape, 2),
        "cobertura_empirica_80pct": round(cobertura_pct, 2),
        "cobertura_objetivo_80pct": 80.0,
        "desvio_cobertura_puntos": round(cobertura_pct - 80.0, 2),
        "veredicto_produccion": "APTO PARA PRODUCCION" if apto else "REQUIERE RECALIBRACION",
        "criterios_evaluados": {
            "mae_tolerancia_max": 6.0,
            "mae_cumplido": bool(mae <= 6.0),
            "cobertura_tolerancia_min": 72.0,
            "cobertura_cumplida": bool(cobertura_pct >= 72.0),
        },
    }
    return metricas


# -----------------------------------------------------------------------------
# 5. Persistencia y Exportación de Artefactos
# -----------------------------------------------------------------------------

def guardar_reporte_y_modelo(
    model: Prophet,
    metricas: Dict[str, Any],
    output_dir: str = "backend/models",
    nombre_base: str = "prophet_biblioteca_validado",
) -> Tuple[Path, Path]:
    """
    Serializa el modelo calibrado en formato .joblib y exporta el informe de métricas JSON.
    """
    dir_salida = Path(output_dir)
    dir_salida.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta_modelo = dir_salida / f"{nombre_base}_{timestamp}.joblib"
    ruta_activo = dir_salida / f"{nombre_base}_active.joblib"
    ruta_reporte = dir_salida / f"metricas_{nombre_base}_{timestamp}.json"

    # Guardar modelo versionado y enlace activo
    joblib.dump(model, ruta_modelo)
    joblib.dump(model, ruta_activo)

    # Exportar informe JSON
    metricas_completas = {
        "timestamp_evaluacion": datetime.now().isoformat(),
        "archivo_modelo": str(ruta_modelo.name),
        "archivo_activo": str(ruta_activo.name),
        "metricas": metricas,
    }
    with open(ruta_reporte, "w", encoding="utf-8") as f:
        json.dump(metricas_completas, f, indent=2, ensure_ascii=False)

    return ruta_modelo, ruta_reporte


# -----------------------------------------------------------------------------
# 6. Generador de Datos de Demostración para Prueba Aislada
# -----------------------------------------------------------------------------

def _generar_serie_sintetica_uct(dias: int = 150) -> pd.DataFrame:
    """
    Genera serie representativa de la biblioteca universitaria para ejecución directa.
    """
    fecha_fin = datetime(2026, 10, 14, 23, 0)
    fecha_ini = fecha_fin - timedelta(days=dias)
    fechas = pd.date_range(fecha_ini, fecha_fin, freq="1h")

    np.random.seed(42)
    registros = []
    for dt in fechas:
        hora = dt.hour
        dia_sem = dt.dayofweek
        # Horario regular UCT
        abierto = 1 if ((dia_sem < 5 and 8 <= hora < 20) or (dia_sem == 5 and 9 <= hora < 14)) else 0
        if abierto == 0:
            aforo = 0
        else:
            # Curva bimodal: pico 11:00 y 16:00
            patron_hora = np.sin((hora - 8) / 12 * np.pi) * 45
            patron_dia = 1.0 if dia_sem < 4 else (0.8 if dia_sem == 4 else 0.4)
            ruido = np.random.normal(0, 5)
            aforo = max(0, int(patron_hora * patron_dia + ruido))

        registros.append({
            "ds": dt,
            "y": aforo,
            "es_horario_abierto": abierto,
            "is_exam_period": 1 if dt.month in [7, 10] and dt.day in range(5, 18) else 0,
            "is_break": 1 if dt.month == 9 and dt.day in range(14, 21) else 0,
            "is_strike": 0,
        })
    return pd.DataFrame(registros)


# -----------------------------------------------------------------------------
# Interfaz de Línea de Comandos (CLI)
# -----------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Pipeline MLOps de Validación y Entrenamiento para Prophet (UCT)."
    )
    parser.add_argument("--csv", type=str, default=None, help="Ruta opcional a CSV con columnas ds e y")
    parser.add_argument("--output_dir", type=str, default="backend/models", help="Directorio de artefactos")
    parser.add_argument("--initial", type=str, default="60 days", help="Ventana inicial de backtesting")
    parser.add_argument("--period", type=str, default="14 days", help="Frecuencia de corte")
    parser.add_argument("--horizon", type=str, default="7 days", help="Horizonte de pronóstico")
    parser.add_argument("--nombre_modelo", type=str, default="prophet_biblioteca_sala1", help="Nombre del artefacto")
    args = parser.parse_args()

    print("=" * 70)
    print(" INICIO DE AUDITORIA Y VALIDACION MLOPS — MODELO PROPHET DSS UCT")
    print("=" * 70)

    # 1. Cargar o generar dataset
    if args.csv and os.path.exists(args.csv):
        print(f"[*] Cargando datos desde archivo: {args.csv}")
        df_raw = pd.read_csv(args.csv)
    else:
        print("[*] No se especificó CSV externo. Generando muestra representativa UCT (150 días)...")
        df_raw = _generar_serie_sintetica_uct(dias=150)

    # 2. Preparar dataset
    print(f"[*] Regularizando serie temporal horaria...")
    df_preparado = preparar_dataset(df_raw)
    print(f"    - Registros totales procesados: {len(df_preparado):,} horas continuas.")
    print(f"    - Rango temporal: {df_preparado['ds'].min()} al {df_preparado['ds'].max()}")

    # 3. Entrenar modelo
    print("[*] Calibrando modelo Prophet con estacionalidades armónicas UCT...")
    modelo = entrenar_modelo(df_preparado)

    # 4. Backtesting con validación cruzada
    print(f"[*] Ejecutando backtesting rodante (initial={args.initial}, period={args.period}, horizon={args.horizon})...")
    df_cv = ejecutar_backtesting(
        modelo,
        initial=args.initial,
        period=args.period,
        horizon=args.horizon,
    )
    print(f"    - Cortes evaluados: {df_cv['cutoff'].nunique()} ventanas temporales independientes.")
    print(f"    - Muestras de prueba contrastadas: {len(df_cv):,} horas.")

    # 5. Calcular métricas
    print("[*] Calculando métricas de error y cobertura probabilística...")
    metricas = calcular_metricas(df_cv)

    print("\n" + "-" * 70)
    print(" REPORTE DE RESULTADOS DE EVALUACION PREDICTIVA:")
    print("-" * 70)
    print(f"  MAE  (Error Absoluto Medio):      {metricas['mae_personas_hora']} personas/hora")
    print(f"  RMSE (Raíz Error Cuadrático Medio): {metricas['rmse_personas_hora']} personas/hora")
    print(f"  WAPE (Error Ponderado Porcentual): {metricas['wape_porcentaje']} %")
    print(f"  Cobertura Empírica del Intervalo:  {metricas['cobertura_empirica_80pct']} % (Objetivo: 80.0 %)")
    print(f"  Desvío de Calibración:            {metricas['desvio_cobertura_puntos']} puntos porcentuales")
    print(f"  Veredicto Final:                  {metricas['veredicto_produccion']}")
    print("-" * 70 + "\n")

    # 6. Guardar artefactos
    ruta_mod, ruta_rep = guardar_reporte_y_modelo(
        modelo,
        metricas,
        output_dir=args.output_dir,
        nombre_base=args.nombre_modelo,
    )
    print(f"[*] Artefactos guardados exitosamente:")
    print(f"    - Modelo serializado: {ruta_mod}")
    print(f"    - Reporte de auditoría: {ruta_rep}")
    print("=" * 70)


if __name__ == "__main__":
    main()

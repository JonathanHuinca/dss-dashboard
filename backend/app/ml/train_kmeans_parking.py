from pathlib import Path
from typing import Dict, Any, List
import joblib
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "kmeans_parking.joblib"

async def extract_vehicle_features(session: AsyncSession) -> pd.DataFrame:
    sql = text("""
        WITH estadia_base AS (
            SELECT 
                patente_hash,
                DATE(time) as fecha,
                MIN(EXTRACT(HOUR FROM time) + EXTRACT(MINUTE FROM time)/60.0) as hora_entrada,
                MAX(EXTRACT(HOUR FROM time) + EXTRACT(MINUTE FROM time)/60.0) as hora_salida,
                GREATEST(15.0, (EXTRACT(EPOCH FROM (MAX(time) - MIN(time))) / 60.0)) as duracion_min
            FROM eventos_vehiculares
            WHERE patente_hash != 'unknown'
            GROUP BY patente_hash, DATE(time)
        )
        SELECT 
            patente_hash,
            COUNT(fecha) as dias_totales,
            ROUND(AVG(hora_entrada)::numeric, 2) as hora_llegada_avg,
            ROUND(AVG(duracion_min)::numeric, 1) as permanencia_avg_min,
            ROUND((100.0 * COUNT(*) FILTER (WHERE hora_entrada <= 8.5 AND duracion_min >= 480) / COUNT(*))::numeric, 1) as tasa_jornada_extrema
        FROM estadia_base
        GROUP BY patente_hash
        HAVING COUNT(fecha) >= 2
    """)
    res = await session.execute(sql)
    rows = [dict(r._mapping) for r in res.fetchall()]
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)

async def compute_behavioral_clusters(session: AsyncSession) -> Dict[str, Any]:
    df = await extract_vehicle_features(session)
    if df.empty or len(df) < 3:
        return {
            "total_vehiculos_analizados": 0,
            "distribucion": [],
            "vehiculos_externos_count": 0,
            "vehiculos_externos_pct": 0.0,
            "scatter_sample": []
        }

    feats = ['hora_llegada_avg', 'permanencia_avg_min', 'dias_totales', 'tasa_jornada_extrema']
    X = df[feats].astype(float)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    km = KMeans(n_clusters=3, random_state=42, n_init=10)
    df['cluster_raw'] = km.fit_predict(X_scaled)

    cluster_profiles = []
    for c in range(3):
        cdf = df[df['cluster_raw'] == c]
        cluster_profiles.append({
            "raw_id": c,
            "count": len(cdf),
            "pct": round(len(cdf) / len(df) * 100, 1),
            "hora_llegada": round(float(cdf['hora_llegada_avg'].mean()), 2),
            "permanencia_min": round(float(cdf['permanencia_avg_min'].mean()), 1),
            "dias_totales": round(float(cdf['dias_totales'].mean()), 1),
            "tasa_extrema": round(float(cdf['tasa_jornada_extrema'].mean()), 1),
        })

    cluster_profiles.sort(key=lambda x: (x["tasa_extrema"], x["permanencia_min"]), reverse=True)
    external_raw = cluster_profiles[0]["raw_id"]

    remaining = [cp for cp in cluster_profiles if cp["raw_id"] != external_raw]
    remaining.sort(key=lambda x: x["dias_totales"], reverse=True)
    regular_raw = remaining[0]["raw_id"]
    students_raw = remaining[1]["raw_id"]

    label_map = {
        external_raw: "Posible Uso Externo / Prolongado",
        regular_raw: "Comunidad Regular / Funcionarios",
        students_raw: "Estudiantes / Bloques Acotados"
    }
    color_map = {
        external_raw: "#EF4444",
        regular_raw: "#003865",
        students_raw: "#C59B27"
    }

    df['label'] = df['cluster_raw'].map(label_map)
    df['color'] = df['cluster_raw'].map(color_map)

    summary_list = []
    for raw_id in [students_raw, regular_raw, external_raw]:
        cp = next(item for item in cluster_profiles if item["raw_id"] == raw_id)
        summary_list.append({
            "perfil": label_map[raw_id],
            "color": color_map[raw_id],
            "total_vehiculos": cp["count"],
            "porcentaje": cp["pct"],
            "hora_llegada_promedio": cp["hora_llegada"],
            "permanencia_promedio_min": cp["permanencia_min"],
            "dias_activos_promedio": cp["dias_totales"],
            "tasa_jornada_extrema_pct": cp["tasa_extrema"]
        })

    sample_records = []
    for _, r in df.sample(min(len(df), 350), random_state=42).iterrows():
        sample_records.append({
            "patente_hash": r["patente_hash"][:10] + "...",
            "hora_llegada": float(r["hora_llegada_avg"]),
            "permanencia_min": float(r["permanencia_avg_min"]),
            "dias": int(r["dias_totales"]),
            "perfil": r["label"],
            "color": r["color"]
        })

    external_info = next(item for item in summary_list if item["perfil"] == "Posible Uso Externo / Prolongado")

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": km, "scaler": scaler, "label_map": label_map}, MODEL_PATH)

    return {
        "total_vehiculos_analizados": len(df),
        "distribucion": summary_list,
        "vehiculos_externos_count": external_info["total_vehiculos"],
        "vehiculos_externos_pct": external_info["porcentaje"],
        "scatter_sample": sample_records
    }

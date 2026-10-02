import asyncio
from pathlib import Path
import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal

MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "rf_visit_profiles.joblib"

def _categorize_stay(minutes: float) -> str:
    if minutes < 60.0:
        return "Corta (< 1h)"
    elif minutes <= 180.0:
        return "Media (1 a 3h)"
    return "Larga (> 3h)"

async def train_rf_model(session: AsyncSession, espacio_id: int = 1) -> dict:
    sql = text("""
        SELECT
            permanencia_min,
            marcajes_totales,
            EXTRACT(HOUR FROM primera_entrada)::int AS hora_entrada,
            EXTRACT(DOW FROM primera_entrada)::int  AS dia_semana,
            EXTRACT(MONTH FROM primera_entrada)::int AS mes
        FROM eventos_asistencia
        WHERE espacio_id = :espacio_id
          AND permanencia_min IS NOT NULL
          AND permanencia_min > 0
    """)
    rows = (await session.execute(sql, {"espacio_id": espacio_id})).fetchall()
    if not rows:
        return {"status": "error", "message": "No hay datos de permanencia para entrenar"}

    df = pd.DataFrame([
        {
            "permanencia_min": float(r.permanencia_min),
            "marcajes_totales": int(r.marcajes_totales),
            "hora_entrada": int(r.hora_entrada),
            "dia_semana": int(r.dia_semana),
            "mes": int(r.mes),
        }
        for r in rows
    ])

    df["perfil"] = df["permanencia_min"].apply(_categorize_stay)

    feature_cols = ["marcajes_totales", "hora_entrada", "dia_semana", "mes"]
    X = df[feature_cols]
    y = df["perfil"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    clf = RandomForestClassifier(
        n_estimators=100,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1
    )
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    acc = round(float(accuracy_score(y_test, y_pred)), 4)
    report = classification_report(y_test, y_pred, output_dict=True)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": clf, "features": feature_cols, "accuracy": acc}, MODEL_PATH)

    distribucion = (
        df.groupby("perfil")
        .agg(
            total=("permanencia_min", "count"),
            permanencia_promedio=("permanencia_min", "mean")
        )
        .reset_index()
    )
    distribucion["porcentaje"] = (
        100.0 * distribucion["total"] / distribucion["total"].sum()
    ).round(2)
    distribucion["permanencia_promedio"] = distribucion["permanencia_promedio"].round(1)

    return {
        "status": "success",
        "total_muestras": len(df),
        "accuracy": acc,
        "distribucion": distribucion.to_dict(orient="records"),
        "metricas": report,
        "model_path": str(MODEL_PATH),
    }

async def get_visit_profiles_report(session: AsyncSession, espacio_id: int = 1) -> dict:
    sql = text("""
        SELECT
            CASE
                WHEN permanencia_min < 60  THEN 'Corta (< 1h)'
                WHEN permanencia_min <= 180 THEN 'Media (1 a 3h)'
                ELSE 'Larga (> 3h)'
            END AS perfil,
            COUNT(*) AS total,
            ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS porcentaje,
            ROUND(AVG(permanencia_min)::numeric, 1) AS permanencia_promedio_min
        FROM eventos_asistencia
        WHERE espacio_id = :espacio_id
          AND permanencia_min IS NOT NULL
          AND permanencia_min > 0
        GROUP BY perfil
        ORDER BY total DESC
    """)
    rows = (await session.execute(sql, {"espacio_id": espacio_id})).fetchall()
    
    model_loaded = MODEL_PATH.exists()
    accuracy = None
    if model_loaded:
        try:
            meta = joblib.load(MODEL_PATH)
            accuracy = meta.get("accuracy")
        except Exception:
            pass

    return {
        "espacio_id": espacio_id,
        "modelo_entrenado": model_loaded,
        "accuracy": accuracy,
        "perfiles": [
            {
                "perfil": r.perfil,
                "total": int(r.total),
                "porcentaje": float(r.porcentaje),
                "permanencia_promedio_min": float(r.permanencia_promedio_min or 0),
            }
            for r in rows
        ],
    }

if __name__ == "__main__":
    async def _main():
        async with AsyncSessionLocal() as session:
            res = await train_rf_model(session, espacio_id=1)
            print("RF Training:", res)
    asyncio.run(_main())

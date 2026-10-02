import asyncio
from datetime import date, timedelta
from pathlib import Path
import joblib
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal

MODEL_DIR = Path(__file__).resolve().parents[2] / "models"
MODEL_FILE_BIB = MODEL_DIR / "gbr_demand_biblioteca.joblib"
MODEL_FILE_VEH = MODEL_DIR / "gbr_demand_vehicular.joblib"

FEATURE_COLS = ["dia_semana", "mes", "dia_ano", "is_exam_period", "is_break", "is_holiday"]

DIAS_SEMANA_MAP = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

async def train_gbr_model(session: AsyncSession, espacio_id: int = 1) -> dict:
    if espacio_id == 1:
        sql = text("""
            SELECT
                DATE(ea.time) AS fecha,
                COUNT(*) AS total_demanda,
                COALESCE(BOOL_OR(ca.is_exam_period), FALSE) AS is_exam_period,
                COALESCE(BOOL_OR(ca.is_break), FALSE)       AS is_break,
                COALESCE(BOOL_OR(ca.is_holiday), FALSE)     AS is_holiday
            FROM eventos_asistencia ea
            LEFT JOIN calendario_academico ca ON DATE(ea.time) = ca.fecha
            WHERE ea.espacio_id = :espacio_id
            GROUP BY DATE(ea.time)
            ORDER BY fecha ASC
        """)
        model_path = MODEL_FILE_BIB
    else:
        sql = text("""
            SELECT
                DATE(ev.time) AS fecha,
                COUNT(*) FILTER (WHERE ev.direccion = 'entrada') AS total_demanda,
                COALESCE(BOOL_OR(ca.is_exam_period), FALSE) AS is_exam_period,
                COALESCE(BOOL_OR(ca.is_break), FALSE)       AS is_break,
                COALESCE(BOOL_OR(ca.is_holiday), FALSE)     AS is_holiday
            FROM eventos_vehiculares ev
            LEFT JOIN calendario_academico ca ON DATE(ev.time) = ca.fecha
            WHERE ev.espacio_id = :espacio_id
            GROUP BY DATE(ev.time)
            ORDER BY fecha ASC
        """)
        model_path = MODEL_FILE_VEH

    rows = (await session.execute(sql, {"espacio_id": espacio_id})).fetchall()
    if not rows:
        return {"status": "error", "message": "Sin datos para entrenar GBR"}

    df = pd.DataFrame([
        {
            "fecha": r.fecha,
            "total_demanda": float(r.total_demanda),
            "is_exam_period": int(bool(r.is_exam_period)),
            "is_break": int(bool(r.is_break)),
            "is_holiday": int(bool(r.is_holiday)),
        }
        for r in rows
    ])

    df["dia_semana"] = pd.to_datetime(df["fecha"]).dt.dayofweek
    df["mes"] = pd.to_datetime(df["fecha"]).dt.month
    df["dia_ano"] = pd.to_datetime(df["fecha"]).dt.dayofyear

    X = df[FEATURE_COLS]
    y = df["total_demanda"]

    reg = HistGradientBoostingRegressor(
        max_iter=200,
        learning_rate=0.08,
        min_samples_leaf=5,
        random_state=42
    )
    reg.fit(X, y)

    score = round(float(reg.score(X, y)), 4)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        "model": reg,
        "features": FEATURE_COLS,
        "score_r2": score,
        "trained_date": date.today().isoformat(),
        "total_days": len(df)
    }, model_path)

    return {
        "status": "success",
        "espacio_id": espacio_id,
        "r2_score": score,
        "total_days_trained": len(df),
        "model_path": str(model_path),
    }

async def predict_next_14_days(session: AsyncSession, espacio_id: int = 1) -> dict:
    model_path = MODEL_FILE_BIB if espacio_id == 1 else MODEL_FILE_VEH
    if not model_path.exists():
        await train_gbr_model(session, espacio_id)

    meta = joblib.load(model_path)
    reg = meta["model"]

    if espacio_id == 1:
        sql_max = text("SELECT COALESCE(MAX(DATE(time)), CURRENT_DATE) FROM eventos_asistencia WHERE espacio_id = :espacio_id")
    else:
        sql_max = text("SELECT COALESCE(MAX(DATE(time)), CURRENT_DATE) FROM eventos_vehiculares WHERE espacio_id = :espacio_id")

    latest_date = (await session.execute(sql_max, {"espacio_id": espacio_id})).scalar() or date.today()

    future_dates = [latest_date + timedelta(days=i) for i in range(1, 15)]

    sql_cal = text("SELECT fecha, is_holiday, is_break, is_exam_period FROM calendario_academico WHERE fecha >= :inicio AND fecha <= :fin")
    cal_rows = (await session.execute(sql_cal, {"inicio": future_dates[0], "fin": future_dates[-1]})).fetchall()
    cal_map = {r.fecha: r for r in cal_rows}

    pred_rows = []
    features_list = []

    for d in future_dates:
        cal = cal_map.get(d)
        is_holiday = int(bool(cal.is_holiday if cal else (d.weekday() >= 5)))
        is_break = int(bool(cal.is_break if cal else False))
        is_exam = int(bool(cal.is_exam_period if cal else False))

        dia_semana = d.weekday()
        mes = d.month
        dia_ano = d.timetuple().tm_yday

        features_list.append([dia_semana, mes, dia_ano, is_exam, is_break, is_holiday])

        if is_exam:
            hito = "Certámenes / Exámenes"
            color = "#DC2626"
        elif is_break:
            hito = "Receso Académico"
            color = "#C59B27"
        elif is_holiday or dia_semana in (5, 6):
            hito = "Fin de semana / Feriado"
            color = "#0284C7"
        else:
            hito = "Clases Regulares"
            color = "#003865"

        pred_rows.append({
            "fecha": d.isoformat(),
            "dia_nombre": DIAS_SEMANA_MAP[dia_semana],
            "hito": hito,
            "color": color,
            "is_exam_period": bool(is_exam),
            "is_break": bool(is_break),
            "is_holiday": bool(is_holiday),
        })

    X_pred = pd.DataFrame(features_list, columns=FEATURE_COLS)
    preds = reg.predict(X_pred)

    for i, p in enumerate(preds):
        if pred_rows[i]["is_holiday"] and pred_rows[i]["dia_nombre"] in ("Sábado", "Domingo"):
            val = max(0, int(round(p * 0.15)))
        else:
            val = max(0, int(round(p)))
        pred_rows[i]["demanda_estimada"] = val

    return {
        "recinto": "biblioteca" if espacio_id == 1 else "estacionamiento",
        "espacio_id": espacio_id,
        "horizon_days": 14,
        "fecha_inicio": future_dates[0].isoformat(),
        "fecha_fin": future_dates[-1].isoformat(),
        "predicciones": pred_rows,
        "model_status": {
            "status": "ok",
            "model_type": "HistGradientBoostingRegressor",
            "r2_score": meta.get("score_r2"),
            "trained_date": meta.get("trained_date"),
        }
    }

if __name__ == "__main__":
    async def _main():
        async with AsyncSessionLocal() as session:
            r1 = await train_gbr_model(session, espacio_id=1)
            print("GBR Biblioteca:", r1)
            r2 = await train_gbr_model(session, espacio_id=2)
            print("GBR Estacionamiento:", r2)
            pred = await predict_next_14_days(session, espacio_id=1)
            print("Predictions 14d:", len(pred["predicciones"]))
    asyncio.run(_main())

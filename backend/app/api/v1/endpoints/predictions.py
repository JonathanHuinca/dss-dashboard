import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_role
from app.ml.prophet_service import predict_next_7_days, train_all

router = APIRouter()


@router.get("/forecast-attendance", summary="Pronóstico horario de afluencia peatonal — 7 días")
async def get_forecast_attendance(
    db: AsyncSession = Depends(get_db),
):
    forecasts, model_status = await predict_next_7_days(db, recinto="biblioteca")
    if model_status["status"] == "unavailable":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=model_status["message"],
            headers={"X-Model-Status": "unavailable"},
        )
    return {
        "recinto": "biblioteca",
        "model_status": model_status,
        "horizon_hours": len(forecasts),
        "forecast": forecasts,
    }


@router.get("/forecast-parking", summary="Pronóstico horario de ocupación de estacionamientos — 7 días")
async def get_forecast_parking(
    db: AsyncSession = Depends(get_db),
):
    forecasts, model_status = await predict_next_7_days(db, recinto="vehicular")
    if model_status["status"] == "unavailable":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=model_status["message"],
            headers={"X-Model-Status": "unavailable"},
        )
    return {
        "recinto": "vehicular",
        "model_status": model_status,
        "horizon_hours": len(forecasts),
        "forecast": forecasts,
    }


@router.get("/alerts", summary="Alertas preventivas activas basadas en pronóstico")
async def get_alerts(
    db: AsyncSession = Depends(get_db),
):
    """
    Genera alertas cuando el pronóstico de las próximas 3 horas supera
    umbrales de ocupación (85% capacidad máxima).
    Capacidades: Biblioteca=350, Estacionamiento=180.
    """
    CAPACIDADES = {"biblioteca": 350, "vehicular": 180}
    UMBRAL_ALERTA = 0.85

    alerts = []
    for recinto, cap in CAPACIDADES.items():
        forecasts, model_status = await predict_next_7_days(db, recinto=recinto)
        if model_status["status"] == "unavailable":
            continue

        proximas_3h = forecasts[:3]
        horas_sobre_umbral = [
            f for f in proximas_3h if f["yhat"] >= cap * UMBRAL_ALERTA
        ]
        if len(horas_sobre_umbral) >= 2:
            alerts.append({
                "recinto": recinto,
                "nivel": "critico" if len(horas_sobre_umbral) == 3 else "preventivo",
                "mensaje": (
                    f"Ocupación proyectada ≥ {int(UMBRAL_ALERTA * 100)}% de capacidad "
                    f"en {len(horas_sobre_umbral)} de las próximas 3 horas."
                ),
                "horas_afectadas": horas_sobre_umbral,
                "capacidad_max": cap,
            })

    return {"total_alertas": len(alerts), "alertas": alerts}


@router.post(
    "/retrain",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Disparar reentrenamiento de modelos Prophet (rol Administrador)",
)
async def trigger_retrain(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("administrador")),
):
    """
    Encola el reentrenamiento de ambos modelos Prophet.
    En producción esto se delega al worker APScheduler; aquí se ejecuta
    en background de FastAPI para el entorno de tesis.
    """
    import asyncio

    job_id = str(uuid.uuid4())

    async def _run():
        try:
            results = await train_all(db)
            import logging
            logging.getLogger(__name__).info(
                f"Reentrenamiento {job_id} completado: {results}"
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Reentrenamiento {job_id} fallido: {e}")

    asyncio.create_task(_run())

    return {
        "job_id": job_id,
        "status": "queued",
        "message": "Reentrenamiento de modelos Prophet encolado. "
                   "Consulta los logs del servidor para el resultado.",
    }


@router.get("/forecast-14days", summary="Proyección de demanda a 14 días con HistGradientBoosting")
async def get_forecast_14days(
    espacio_id: int = 1,
    db: AsyncSession = Depends(get_db),
):
    from app.ml.train_gbr_demand import predict_next_14_days
    return await predict_next_14_days(db, espacio_id=espacio_id)


@router.get("/visit-profiles", summary="Reporte de perfiles de permanencia (Random Forest)")
async def get_visit_profiles(
    espacio_id: int = 1,
    db: AsyncSession = Depends(get_db),
):
    from app.ml.train_rf_classifier import get_visit_profiles_report
    return await get_visit_profiles_report(db, espacio_id=espacio_id)


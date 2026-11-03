from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cachear_respuesta, TTL_KPIS_DIA, TTL_HISTORICOS
from app.core.config import settings
from app.core.database import get_db
from app.core.security import require_role, get_current_user, validar_acceso_espacio
from app.domain.auth_models import Usuario
from app.services.prediction_service import (
    get_prophet_forecast,
    get_gbr_forecast_14days,
    get_visit_profiles,
    get_active_alerts,
)

router = APIRouter()


@router.get("/forecast-attendance", summary="Pronóstico horario de afluencia peatonal — 7 días")
@cachear_respuesta(ttl_segundos=TTL_HISTORICOS, categoria="predicciones")
async def get_forecast_attendance(
    response: Response,
    sala: str = "todas",
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    validar_acceso_espacio(1, current_user)
    return await get_prophet_forecast(db, recinto="biblioteca", sala=sala)


@router.get("/forecast-parking", summary="Pronóstico horario de ocupación de estacionamientos — 7 días")
@cachear_respuesta(ttl_segundos=TTL_HISTORICOS, categoria="predicciones")
async def get_forecast_parking(
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    validar_acceso_espacio(2, current_user)
    return await get_prophet_forecast(db, recinto="vehicular")


@router.get("/alerts", summary="Alertas preventivas activas basadas en pronóstico")
@cachear_respuesta(ttl_segundos=TTL_KPIS_DIA, categoria="predicciones", por_espacio=False)
async def get_alerts(
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    return await get_active_alerts(db)


@router.get("/forecast-14days", summary="Proyección de demanda a 14 días con HistGradientBoosting")
@cachear_respuesta(ttl_segundos=TTL_HISTORICOS, categoria="predicciones")
async def get_forecast_14days_endpoint(
    response: Response,
    espacio_id: int = 1,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    validar_acceso_espacio(espacio_id, current_user)
    return await get_gbr_forecast_14days(db, espacio_id=espacio_id)


@router.get("/visit-profiles", summary="Análisis estadístico determinista de perfiles de permanencia (Base de Datos)")
@cachear_respuesta(ttl_segundos=TTL_HISTORICOS, categoria="predicciones")
async def get_visit_profiles_endpoint(
    response: Response,
    espacio_id: int = 1,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    validar_acceso_espacio(espacio_id, current_user)
    return await get_visit_profiles(db, espacio_id=espacio_id)

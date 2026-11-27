from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cachear_respuesta, TTL_KPIS_DIA, TTL_HISTORICOS
from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    require_role,
    get_current_user,
    obtener_espacios_autorizados,
    validar_acceso_espacio,
)
from app.domain.auth_models import Usuario
from app.services.prediction_service import (
    get_prophet_forecast,
    get_prophet_presence_forecast,
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


@router.get("/forecast-presence", summary="Pronóstico continuo de presencia física en sala con Prophet Logístico — 14 días")
@cachear_respuesta(ttl_segundos=TTL_HISTORICOS, categoria="predicciones")
async def get_forecast_presence_endpoint(
    response: Response,
    sala: str = "todas",
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    validar_acceso_espacio(1, current_user)
    return await get_prophet_presence_forecast(db, sala=sala)


@router.get("/forecast-parking", summary="Pronóstico horario de ocupación de estacionamientos — 7 días")
@cachear_respuesta(ttl_segundos=TTL_HISTORICOS, categoria="predicciones")
async def get_forecast_parking(
    response: Response,
    sector: str = "todos",
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    validar_acceso_espacio(2, current_user)
    return await get_prophet_forecast(db, recinto="vehicular", sala=sector)


@router.get("/alerts", summary="Alertas preventivas activas basadas en pronóstico")
@cachear_respuesta(ttl_segundos=TTL_KPIS_DIA, categoria="predicciones", por_espacio=False)
async def get_alerts(
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    espacios_autorizados = obtener_espacios_autorizados(current_user)
    if espacios_autorizados is not None and not espacios_autorizados:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: no cuenta con recintos autorizados para consultar alertas.",
        )
    resultado = await get_active_alerts(db)
    if espacios_autorizados is None:
        return resultado
    recintos_permitidos = set()
    if 1 in espacios_autorizados:
        recintos_permitidos.add("biblioteca")
    if 2 in espacios_autorizados:
        recintos_permitidos.update({"vehicular", "estacionamiento"})
    alertas_filtradas = [
        a for a in (resultado.get("alertas") or [])
        if str(a.get("recinto", "")).strip().lower() in recintos_permitidos
    ]
    salida = dict(resultado)
    salida["alertas"] = alertas_filtradas
    salida["total_alertas"] = len(alertas_filtradas)
    return salida


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

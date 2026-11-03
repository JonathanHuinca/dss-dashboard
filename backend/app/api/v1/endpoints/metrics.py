from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cachear_respuesta, TTL_KPIS_DIA, TTL_HISTORICOS
from app.core.database import get_db
from app.core.security import get_current_user, validar_acceso_espacio
from app.domain.auth_models import Usuario
from app.services.metrics_service import MetricsService
from app.schemas.metrics_schemas import KPISummaryResponse, DateBoundsResponse

router = APIRouter()


@router.get("/kpi-summary", response_model=KPISummaryResponse, summary="Resumen gerencial de KPIs por período o acumulado")
@cachear_respuesta(ttl_segundos=TTL_KPIS_DIA, categoria="kpis")
async def get_kpi_summary(
    response: Response,
    espacio_id: int = Query(1, description="ID del espacio (1=Biblioteca CSF, 2=Estacionamiento CSF)"),
    fecha_inicio: Optional[date] = Query(None, description="Fecha de inicio del período (YYYY-MM-DD)"),
    fecha_fin: Optional[date] = Query(None, description="Fecha de fin del período (YYYY-MM-DD)"),
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    return await MetricsService.get_kpi_summary(
        session=db,
        espacio_id=espacio_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
    )


@router.get("/date-bounds", response_model=DateBoundsResponse, summary="Límites cronológicos y meses disponibles según registros")
@cachear_respuesta(ttl_segundos=TTL_HISTORICOS, categoria="historicos")
async def get_date_bounds(
    response: Response,
    espacio_id: Optional[int] = Query(None, description="ID del espacio (1=Biblioteca, 2=Estacionamiento, None=global)"),
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if espacio_id is not None:
        validar_acceso_espacio(espacio_id, current_user)
    return await MetricsService.get_date_bounds(
        session=db,
        espacio_id=espacio_id,
    )

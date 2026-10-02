from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.metrics_service import MetricsService
from app.schemas.metrics_schemas import KPISummaryResponse

router = APIRouter()


@router.get("/kpi-summary", response_model=KPISummaryResponse, summary="Resumen gerencial de KPIs por período o acumulado")
async def get_kpi_summary(
    espacio_id: int = Query(1, description="ID del espacio (1=Biblioteca CSF, 2=Estacionamiento CSF)"),
    fecha_inicio: Optional[date] = Query(None, description="Fecha de inicio del período (YYYY-MM-DD)"),
    fecha_fin: Optional[date] = Query(None, description="Fecha de fin del período (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    return await MetricsService.get_kpi_summary(
        session=db,
        espacio_id=espacio_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
    )

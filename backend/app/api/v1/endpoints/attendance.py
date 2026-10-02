"""
/api/v1/attendance — Sin autenticación en este paso de prueba (Prompt 1.5).
La autenticación se reactivará en Prompt 1.6 cuando el frontend esté conectado.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.attendance_service import AttendanceService

router = APIRouter()


@router.get("/kpis", summary="KPIs generales de biblioteca")
async def get_kpis(
    espacio_id: int = Query(1, description="ID del espacio (1=Biblioteca CSF)"),
    db: AsyncSession = Depends(get_db),
):
    return await AttendanceService.get_kpis(db, espacio_id)


@router.get("/occupancy-realtime", summary="Aforo concurrente en tiempo real vs capacidad")
async def get_occupancy_realtime(
    espacio_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
):
    return await AttendanceService.get_occupancy_realtime(db, espacio_id)


@router.get("/hourly-flow", summary="Flujo horario de entradas y salidas")
async def get_hourly_flow(
    fecha_inicio: Optional[date] = Query(None, description="YYYY-MM-DD"),
    fecha_fin:    Optional[date] = Query(None, description="YYYY-MM-DD"),
    espacio_id:   int            = Query(1),
    db: AsyncSession = Depends(get_db),
):
    return await AttendanceService.get_hourly_flow(db, fecha_inicio, fecha_fin, espacio_id)


@router.get("/heatmap", summary="Matriz de ocupación: día semana × hora")
async def get_heatmap(
    espacio_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
):
    return await AttendanceService.get_heatmap(db, espacio_id)


@router.get("/anomalies", summary="Registros con alertas de coherencia o marcajes")
async def get_anomalies(
    espacio_id: int = Query(1),
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import text
    sql = text("""
        SELECT
            time, person_id_hash, door_entrada, marcajes_totales,
            alerta_coherencia_fechas, alerta_marcajes
        FROM eventos_asistencia
        WHERE espacio_id = :espacio_id
          AND (alerta_coherencia_fechas = TRUE OR alerta_marcajes = TRUE)
        ORDER BY time DESC
        LIMIT :limit
    """)
    rows = (await db.execute(sql, {"espacio_id": espacio_id, "limit": limit})).fetchall()
    return [
        {
            "time":                    r.time.isoformat(),
            "person_id_hash":          r.person_id_hash,
            "door_entrada":            r.door_entrada,
            "marcajes_totales":        r.marcajes_totales,
            "alerta_coherencia_fechas": r.alerta_coherencia_fechas,
            "alerta_marcajes":         r.alerta_marcajes,
        }
        for r in rows
    ]


@router.get("/academic-distribution", summary="Distribución de uso — placeholder hasta datos académicos")
async def get_academic_distribution(db: AsyncSession = Depends(get_db)):
    return {
        "mensaje": "Disponible cuando se integren datos académicos (carrera, PMA, cohorte).",
        "estado": "pendiente_datos",
    }


@router.get("/peak-valley", summary="Franjas horarias de pico y valle")
async def get_peak_valley(
    espacio_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
):
    return await AttendanceService.get_peak_valley_bands(db, espacio_id)


@router.get("/weekly-evolution", summary="Evolución semanal por semanas ISO")
async def get_weekly_evolution(
    espacio_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
):
    return await AttendanceService.get_weekly_evolution(db, espacio_id)


@router.get("/monthly-volume", summary="Volumen y promedio diario mensual")
async def get_monthly_volume(
    espacio_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
):
    return await AttendanceService.get_monthly_volume(db, espacio_id)


@router.get("/academic-milestones-comparison", summary="Comparativa por hito del calendario académico")
async def get_academic_milestones_comparison(
    espacio_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
):
    return await AttendanceService.get_academic_milestones_comparison(db, espacio_id)


@router.get("/doors-usage", summary="Histograma de accesos por torniquetes")
async def get_doors_usage(
    espacio_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
):
    return await AttendanceService.get_door_usage(db, espacio_id)


@router.get("/checkins-distribution", summary="Distribución de usuarios por marcajes diarios")
async def get_checkins_distribution(
    espacio_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
):
    return await AttendanceService.get_checkin_distribution(db, espacio_id)


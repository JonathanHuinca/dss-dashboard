"""
/api/v1/vehicles — Sin autenticación en este paso de prueba (Prompt 1.5).
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.vehicle_service import VehicleService

router = APIRouter()


@router.get("/kpis", summary="KPIs generales de estacionamiento")
async def get_kpis(
    espacio_id: int = Query(2, description="ID del espacio (2=Estacionamiento CSF)"),
    db: AsyncSession = Depends(get_db),
):
    return await VehicleService.get_kpis(db, espacio_id)


@router.get("/parking-occupancy", summary="Aforo vehicular actual vs capacidad")
async def get_parking_occupancy(
    espacio_id: int = Query(2),
    db: AsyncSession = Depends(get_db),
):
    return await VehicleService.get_parking_occupancy(db, espacio_id)


@router.get("/hourly-flow", summary="Ingresos vs salidas vehiculares por bloque horario")
async def get_hourly_flow(
    fecha_inicio: Optional[date] = Query(None, description="YYYY-MM-DD"),
    fecha_fin:    Optional[date] = Query(None, description="YYYY-MM-DD"),
    espacio_id:   int            = Query(2),
    db: AsyncSession = Depends(get_db),
):
    return await VehicleService.get_hourly_flow(db, fecha_inicio, fecha_fin, espacio_id)


@router.get("/stay-distribution", summary="Histograma de tiempos de permanencia vehicular")
async def get_stay_distribution(
    espacio_id: int = Query(2),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import text
    sql = text("""
        SELECT
            CASE
                WHEN EXTRACT(EPOCH FROM (sal.time - ent.time)) / 60.0 < 15   THEN 'drop_off'
                WHEN EXTRACT(EPOCH FROM (sal.time - ent.time)) / 60.0 < 180  THEN '0-3h'
                WHEN EXTRACT(EPOCH FROM (sal.time - ent.time)) / 60.0 < 360  THEN '3-6h'
                ELSE 'jornada_completa'
            END AS rango,
            COUNT(*) AS total
        FROM eventos_vehiculares ent
        JOIN eventos_vehiculares sal
          ON ent.patente_hash = sal.patente_hash
         AND ent.espacio_id   = sal.espacio_id
         AND sal.time > ent.time
         AND sal.time < ent.time + INTERVAL '24 hours'
         AND ent.direccion = 'entrada'
         AND sal.direccion = 'salida'
        WHERE ent.espacio_id = :espacio_id
        GROUP BY rango
        ORDER BY total DESC
    """)
    rows = (await db.execute(sql, {"espacio_id": espacio_id})).fetchall()
    return [{"rango": r.rango, "total": int(r.total)} for r in rows]


@router.get("/fleet-composition", summary="Composición de flota — tipología y marcas (donut chart)")
async def get_fleet_composition(
    espacio_id: int = Query(2),
    db: AsyncSession = Depends(get_db),
):
    return await VehicleService.get_fleet_composition(db, espacio_id)


@router.get("/camera-stats", summary="Distribución de flujo por cámara ANPR")
async def get_camera_stats(
    espacio_id: int = Query(2),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import text
    sql = text("""
        SELECT
            camara,
            COUNT(*) FILTER (WHERE direccion = 'entrada') AS entradas,
            COUNT(*) FILTER (WHERE direccion = 'salida')  AS salidas,
            COUNT(*) FILTER (WHERE calidad_lectura = 'unknown') AS lecturas_fallidas
        FROM eventos_vehiculares
        WHERE espacio_id = :espacio_id
        GROUP BY camara
        ORDER BY (COUNT(*) FILTER (WHERE direccion = 'entrada') + COUNT(*) FILTER (WHERE direccion = 'salida')) DESC
    """)
    rows = (await db.execute(sql, {"espacio_id": espacio_id})).fetchall()
    return [
        {
            "camara":           r.camara,
            "entradas":         int(r.entradas),
            "salidas":          int(r.salidas),
            "lecturas_fallidas": int(r.lecturas_fallidas),
        }
        for r in rows
    ]


@router.get("/daily-evolution", summary="Serie temporal de accesos diarios")
async def get_daily_evolution(
    espacio_id: int = Query(2),
    db: AsyncSession = Depends(get_db),
):
    return await VehicleService.get_daily_evolution(db, espacio_id)


@router.get("/academic-milestones-comparison", summary="Comparativa vehicular por hito académico")
async def get_academic_milestones_comparison(
    espacio_id: int = Query(2),
    db: AsyncSession = Depends(get_db),
):
    return await VehicleService.get_academic_milestones_comparison(db, espacio_id)


@router.get("/intercampus-mobility", summary="Movilidad y traslados intercampus CSF y CHS")
async def get_intercampus_mobility(
    db: AsyncSession = Depends(get_db),
):
    return await VehicleService.get_intercampus_mobility(db)


@router.get("/behavioral-clusters", summary="Clustering no supervisado de perfiles de uso y ocupación externa")
async def get_behavioral_clusters(
    db: AsyncSession = Depends(get_db),
):
    return await VehicleService.get_behavioral_clusters(db)



"""
Router para endpoints de vehículos (/api/v1/vehicles).
"""
import asyncio
import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_permission, validar_acceso_espacio
from app.domain.auth_models import Usuario
from app.services.vehicle_service import VehicleService
from app.ml.isolation_forest import detect_vehicular_anomalies
from app.core.cache import cachear_respuesta, TTL_AFORO_VIVO, TTL_KPIS_DIA, TTL_HISTORICOS

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/kpis", summary="KPIs generales de estacionamiento")
@cachear_respuesta(ttl_segundos=TTL_KPIS_DIA, categoria="kpis")
async def get_kpis(
    response:        Response,
    fecha_inicio:    Optional[date] = Query(None, description="YYYY-MM-DD"),
    fecha_fin:       Optional[date] = Query(None, description="YYYY-MM-DD"),
    espacio_id:      int            = Query(2, description="ID del espacio (2=Estacionamiento CSF)"),
    alcance:         Optional[str]  = Query("conformes", description="conformes | todos | anomalias"),
    regimen_horario: Optional[str]  = Query("todos", description="todos | dentro_horario | fuera_horario"),
    direccion:       Optional[str]  = Query("todos", description="todos | solo_ingreso | solo_salida"),
    dias_semana:     Optional[str]  = Query(None),
    door:            Optional[str]  = Query(None),
    sector:          Optional[str]  = Query(None, description="CSF11 | CSF21 | CHS01 | todos"),
    tipo_vehiculo:   Optional[str]  = Query(None, description="SUV/MPV, Camioneta, etc."),
    current_user:    Usuario        = Depends(get_current_user),
    db:              AsyncSession   = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    return await VehicleService.get_kpis(
        session=db,
        espacio_id=espacio_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        alcance=alcance or "conformes",
        regimen_horario=regimen_horario or "todos",
        direccion=direccion or "todos",
        dias_semana=dias_semana,
        door=door,
        sector=sector,
        tipo_vehiculo=tipo_vehiculo,
    )


@router.get("/parking-occupancy", summary="Aforo vehicular actual vs capacidad")
@cachear_respuesta(ttl_segundos=TTL_AFORO_VIVO, categoria="aforo_vivo")
async def get_parking_occupancy(
    response: Response,
    espacio_id: int = Query(2),
    sector: Optional[str] = Query(None),
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    return await VehicleService.get_parking_occupancy(db, espacio_id, sector=sector)


@router.get("/hourly-flow", summary="Ingresos vs salidas vehiculares por bloque horario")
@cachear_respuesta(ttl_segundos=TTL_KPIS_DIA, categoria="kpis")
async def get_hourly_flow(
    response:        Response,
    fecha_inicio:    Optional[date] = Query(None, description="YYYY-MM-DD"),
    fecha_fin:       Optional[date] = Query(None, description="YYYY-MM-DD"),
    espacio_id:      int            = Query(2),
    alcance:         Optional[str]  = Query("conformes"),
    regimen_horario: Optional[str]  = Query("todos"),
    direccion:       Optional[str]  = Query("todos"),
    dias_semana:     Optional[str]  = Query(None),
    door:            Optional[str]  = Query(None),
    sector:          Optional[str]  = Query(None),
    tipo_vehiculo:   Optional[str]  = Query(None),
    current_user:    Usuario        = Depends(get_current_user),
    db:              AsyncSession   = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    return await VehicleService.get_hourly_flow(
        session=db,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        espacio_id=espacio_id,
        alcance=alcance or "conformes",
        regimen_horario=regimen_horario or "todos",
        direccion=direccion or "todos",
        dias_semana=dias_semana,
        door=door,
        sector=sector,
        tipo_vehiculo=tipo_vehiculo,
    )


@router.get("/stay-distribution", summary="Histograma de tiempos de permanencia vehicular")
@cachear_respuesta(ttl_segundos=TTL_HISTORICOS, categoria="historicos")
async def get_stay_distribution(
    response: Response,
    espacio_id: int = Query(2),
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    return await VehicleService.get_stay_distribution(db, espacio_id)


@router.get("/fleet-composition", summary="Composición de flota — tipología y marcas (donut chart)")
@cachear_respuesta(ttl_segundos=TTL_HISTORICOS, categoria="historicos")
async def get_fleet_composition(
    response: Response,
    fecha_inicio: Optional[date] = Query(None, description="YYYY-MM-DD"),
    fecha_fin: Optional[date] = Query(None, description="YYYY-MM-DD"),
    espacio_id: int = Query(2),
    sector: Optional[str] = Query(None),
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    return await VehicleService.get_fleet_composition(db, espacio_id, fecha_inicio, fecha_fin, sector=sector)


@router.get("/camera-stats", summary="Distribución de flujo por cámara ANPR")
@cachear_respuesta(ttl_segundos=TTL_HISTORICOS, categoria="historicos")
async def get_camera_stats(
    response: Response,
    fecha_inicio: Optional[date] = Query(None, description="YYYY-MM-DD"),
    fecha_fin: Optional[date] = Query(None, description="YYYY-MM-DD"),
    alcance: Optional[str] = Query("conformes"),
    regimen_horario: Optional[str] = Query("todos"),
    direccion: Optional[str] = Query("todos"),
    dias_semana: Optional[str] = Query(None),
    door: Optional[str] = Query(None),
    sector: Optional[str] = Query(None),
    tipo_vehiculo: Optional[str] = Query(None),
    espacio_id: int = Query(2),
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    return await VehicleService.get_camera_stats(
        db,
        espacio_id=espacio_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        alcance=alcance or "conformes",
        regimen_horario=regimen_horario or "todos",
        direccion=direccion or "todos",
        dias_semana=dias_semana,
        door=door,
        sector=sector,
        tipo_vehiculo=tipo_vehiculo,
    )


@router.get("/daily-evolution", summary="Serie temporal de accesos diarios")
@cachear_respuesta(ttl_segundos=TTL_HISTORICOS, categoria="historicos")
async def get_daily_evolution(
    response: Response,
    fecha_inicio: Optional[date] = Query(None, description="YYYY-MM-DD"),
    fecha_fin: Optional[date] = Query(None, description="YYYY-MM-DD"),
    espacio_id: int = Query(2),
    sector: Optional[str] = Query(None),
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    return await VehicleService.get_daily_evolution(db, espacio_id, fecha_inicio, fecha_fin, sector=sector)


@router.get("/academic-milestones-comparison", summary="Comparativa vehicular por hito académico")
@cachear_respuesta(ttl_segundos=TTL_HISTORICOS, categoria="historicos")
async def get_academic_milestones_comparison(
    response: Response,
    espacio_id: int = Query(2),
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    return await VehicleService.get_academic_milestones_comparison(db, espacio_id)


@router.get("/intercampus-mobility", summary="Movilidad y traslados intercampus CSF y CHS")
@cachear_respuesta(ttl_segundos=TTL_HISTORICOS, categoria="historicos")
async def get_intercampus_mobility(
    response: Response,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    validar_acceso_espacio(2, current_user)
    return await VehicleService.get_intercampus_mobility(db)


@router.get("/behavioral-clusters", summary="Clustering no supervisado de perfiles de uso")
@cachear_respuesta(ttl_segundos=TTL_HISTORICOS, categoria="historicos")
async def get_behavioral_clusters(
    response: Response,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    validar_acceso_espacio(2, current_user)
    return await VehicleService.get_behavioral_clusters(db)


@router.get("/anomalies", summary="Detección de anomalías en comportamiento vehicular (Isolation Forest)")
async def get_vehicular_anomalies(
    espacio_id: int = Query(2),
    dias: int = Query(30),
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    df = await VehicleService.get_raw_vehicle_data_for_anomalies(db, espacio_id, dias)
    
    if df.empty:
        raise HTTPException(status_code=404, detail="Sin datos suficientes")
        
    if len(df) < 5:
        raise HTTPException(
            status_code=422, 
            detail="Datos insuficientes para deteccion de anomalias (minimo 5 registros)"
        )
        
    try:
        df_anomalies = await asyncio.to_thread(detect_vehicular_anomalies, df)
        anomalies_list = df_anomalies.to_dict(orient="records")
        total_anomalias = len(anomalies_list)
        porcentaje = round((total_anomalias / len(df)) * 100, 2)
        
        return {
            "total_anomalias": total_anomalias,
            "porcentaje": porcentaje,
            "anomalias": anomalies_list,
        }
    except Exception as e:
        logger.error(f"Error detect_vehicular_anomalies: {e}")
        raise HTTPException(
            status_code=503,
            detail="Modelo ML no disponible",
            headers={"X-Model-Status": "unavailable"},
        )


@router.get("/raw-events", summary="Listado paginado de microdatos vehiculares")
async def get_raw_vehicle_events(
    page:            int            = Query(1, ge=1),
    page_size:       int            = Query(50, ge=1, le=200),
    fecha_inicio:    Optional[date] = Query(None, description="YYYY-MM-DD"),
    fecha_fin:       Optional[date] = Query(None, description="YYYY-MM-DD"),
    camara:          Optional[str]  = Query(None),
    direccion:       Optional[str]  = Query(None),
    tipo_vehiculo:   Optional[str]  = Query(None),
    search_hash:     Optional[str]  = Query(None),
    categoria:       Optional[str]  = Query(None, description="lectura_fallida | fuera_de_horario | conforme | anomalias"),
    alcance:         Optional[str]  = Query("todos", description="todos | conformes | anomalias"),
    regimen_horario: Optional[str]  = Query("todos"),
    dias_semana:     Optional[str]  = Query(None),
    door:            Optional[str]  = Query(None),
    espacio_id:      int            = Query(2),
    current_user:    Usuario        = Depends(get_current_user),
    db:              AsyncSession   = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    return await VehicleService.get_raw_events(
        session=db,
        espacio_id=espacio_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        camara=camara,
        direccion=direccion,
        tipo_vehiculo=tipo_vehiculo,
        search_hash=search_hash,
        categoria=categoria,
        alcance=alcance or "todos",
        regimen_horario=regimen_horario or "todos",
        dias_semana=dias_semana,
        door=door,
        page=page,
        page_size=page_size,
    )


@router.get("/export-raw-csv", summary="Exportar microdatos vehiculares a CSV con registro de auditoría")
async def export_raw_vehicle_csv(
    background_tasks: BackgroundTasks,
    request: Request,
    fecha_inicio:    Optional[date] = Query(None, description="YYYY-MM-DD"),
    fecha_fin:       Optional[date] = Query(None, description="YYYY-MM-DD"),
    camara:          Optional[str]  = Query(None),
    direccion:       Optional[str]  = Query(None),
    tipo_vehiculo:   Optional[str]  = Query(None),
    search_hash:     Optional[str]  = Query(None),
    categoria:       Optional[str]  = Query(None),
    alcance:         Optional[str]  = Query("todos"),
    regimen_horario: Optional[str]  = Query("todos"),
    dias_semana:     Optional[str]  = Query(None),
    door:            Optional[str]  = Query(None),
    espacio_id:      int            = Query(2),
    current_user:    Usuario        = Depends(require_permission("can_export")),
    db:              AsyncSession   = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    csv_content, total_count = await VehicleService.export_raw_csv(
        session=db,
        espacio_id=espacio_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        camara=camara,
        direccion=direccion,
        tipo_vehiculo=tipo_vehiculo,
        search_hash=search_hash,
        categoria=categoria,
        alcance=alcance or "todos",
        regimen_horario=regimen_horario or "todos",
        dias_semana=dias_semana,
        door=door,
    )

    client_ip = request.client.host if request.client else "127.0.0.1"
    detalle = f"Filtros: camara={camara or 'todas'}, dir={direccion or 'ambas'}, tipo={tipo_vehiculo or 'todos'}, categoria={categoria or 'todas'}, alcance={alcance or 'todos'}"

    from app.services.audit_service import record_download_audit
    background_tasks.add_task(
        record_download_audit,
        usuario_id=current_user.id,
        modulo="estacionamiento",
        formato="csv",
        filtro_fecha_inicio=str(fecha_inicio) if fecha_inicio else None,
        filtro_fecha_fin=str(fecha_fin) if fecha_fin else None,
        filtro_detalle=detalle,
        total_registros=total_count,
        ip_origen=client_ip,
    )

    filename = f"microdatos_estacionamiento_{fecha_inicio or 'inicio'}_{fecha_fin or 'fin'}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

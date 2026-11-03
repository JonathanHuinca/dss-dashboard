"""
/api/v1/attendance — Endpoints analíticos de asistencia peatonal y biblioteca.
Protegido con autenticación JWT, RBAC por roles/permisos y Ley N° 21.719.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, BackgroundTasks, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_permission, validar_acceso_espacio
from app.domain.auth_models import Usuario
from app.services.attendance_service import AttendanceService
from app.core.cache import (
    cachear_respuesta,
    invalidar_cache_por_espacio,
    TTL_AFORO_VIVO,
    TTL_KPIS_DIA,
    TTL_HISTORICOS,
)

router = APIRouter()


class SalaBibliotecaCreate(BaseModel):
    codigo: str = Field(..., description="Código único de sala, ej. SALA_3_CSF")
    nombre: str = Field(..., description="Nombre formal de la sala")
    edificio: str = Field(..., description="Edificio físico, ej. CSF02, CSF04")
    piso: str = Field("1er Piso", description="Piso donde se ubica la sala")
    descripcion: Optional[str] = Field(None, description="Detalle o uso de sala")
    capacidad_asientos: int = Field(100, ge=1)
    permite_horario_extendido: bool = False
    puerta_principal_in: Optional[str] = None
    puerta_principal_out: Optional[str] = None
    puerta_universal_in: Optional[str] = None
    puerta_universal_out: Optional[str] = None
    espacio_id: int = 1


@router.get("/kpis", summary="KPIs generales de biblioteca")
@cachear_respuesta(ttl_segundos=TTL_KPIS_DIA, categoria="kpis")
async def get_kpis(
    response:            Response,
    fecha_inicio:        Optional[date] = Query(None, description="YYYY-MM-DD"),
    fecha_fin:           Optional[date] = Query(None, description="YYYY-MM-DD"),
    espacio_id:          int            = Query(1, description="ID del espacio (1=Biblioteca CSF)"),
    alcance:             Optional[str]  = Query("conformes", description="conformes | todos | anomalias"),
    regimen_horario:     Optional[str]  = Query("todos", description="todos | dentro_horario | fuera_horario"),
    direccion:           Optional[str]  = Query("todos", description="todos | solo_ingreso | solo_salida"),
    dias_semana:         Optional[str]  = Query(None, description="lunes,martes..."),
    door:                Optional[str]  = Query(None),
    perfil_visita:       Optional[str]  = Query("todos", description="todos | rebote | estandar | profundo"),
    marcajes:            Optional[str]  = Query("todos", description="todos | 1 | 2 | 3-4 | 5+"),
    sala:                Optional[str]  = Query(None, description="sala_1 | sala_2 | todas"),
    carrera:             Optional[str]  = Query(None, description="Nombre de carrera"),
    facultad:            Optional[str]  = Query(None, description="Nombre de facultad"),
    cohorte:             Optional[str]  = Query(None, description="Año de ingreso o cohorte"),
    incluir_pausas_bano: bool           = Query(True, description="Incluir pausas de baño (3-15 min) en conformes"),
    desduplicar_rafagas: bool           = Query(True, description="Desduplicar ráfagas mecánicas de sensor < 1 min"),
    current_user:        Usuario        = Depends(get_current_user),
    db:                  AsyncSession   = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    return await AttendanceService.get_kpis(
        session=db,
        espacio_id=espacio_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        alcance=alcance or "conformes",
        regimen_horario=regimen_horario or "todos",
        direccion=direccion or "todos",
        dias_semana=dias_semana,
        door=door,
        perfil_visita=perfil_visita or "todos",
        marcajes=marcajes or "todos",
        sala=sala,
        carrera=carrera,
        facultad=facultad,
        cohorte=cohorte,
        incluir_pausas_bano=incluir_pausas_bano,
        desduplicar_rafagas=desduplicar_rafagas,
    )


@router.get("/occupancy-realtime", summary="Aforo concurrente en tiempo real vs capacidad")
@cachear_respuesta(ttl_segundos=TTL_AFORO_VIVO, categoria="aforo_vivo")
async def get_occupancy_realtime(
    response: Response,
    espacio_id: int = Query(1),
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    return await AttendanceService.get_occupancy_realtime(db, espacio_id)


@router.get("/hourly-flow", summary="Flujo horario de entradas y salidas")
@cachear_respuesta(ttl_segundos=TTL_KPIS_DIA, categoria="kpis")
async def get_hourly_flow(
    response:            Response,
    fecha_inicio:        Optional[date] = Query(None, description="YYYY-MM-DD"),
    fecha_fin:           Optional[date] = Query(None, description="YYYY-MM-DD"),
    espacio_id:          int            = Query(1),
    alcance:             Optional[str]  = Query("conformes", description="conformes | todos | anomalias"),
    regimen_horario:     Optional[str]  = Query("todos", description="todos | dentro_horario | fuera_horario"),
    direccion:           Optional[str]  = Query("todos", description="todos | solo_ingreso | solo_salida"),
    dias_semana:         Optional[str]  = Query(None, description="lunes,martes..."),
    door:                Optional[str]  = Query(None),
    perfil_visita:       Optional[str]  = Query("todos", description="todos | rebote | estandar | profundo"),
    marcajes:            Optional[str]  = Query("todos", description="todos | 1 | 2 | 3-4 | 5+"),
    sala:                Optional[str]  = Query(None, description="sala_1 | sala_2 | todas"),
    carrera:             Optional[str]  = Query(None),
    facultad:            Optional[str]  = Query(None),
    cohorte:             Optional[str]  = Query(None),
    incluir_pausas_bano: bool           = Query(True, description="Incluir pausas de baño (3-15 min) en conformes"),
    desduplicar_rafagas: bool           = Query(True, description="Desduplicar ráfagas mecánicas de sensor < 1 min"),
    current_user:        Usuario        = Depends(get_current_user),
    db:                  AsyncSession   = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    return await AttendanceService.get_hourly_flow(
        session=db,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        espacio_id=espacio_id,
        alcance=alcance or "conformes",
        regimen_horario=regimen_horario or "todos",
        direccion=direccion or "todos",
        dias_semana=dias_semana,
        door=door,
        perfil_visita=perfil_visita or "todos",
        marcajes=marcajes or "todos",
        sala=sala,
        carrera=carrera,
        facultad=facultad,
        cohorte=cohorte,
        incluir_pausas_bano=incluir_pausas_bano,
        desduplicar_rafagas=desduplicar_rafagas,
    )


@router.get("/heatmap", summary="Matriz de ocupación: día semana × hora")
@cachear_respuesta(ttl_segundos=TTL_HISTORICOS, categoria="historicos")
async def get_heatmap(
    response:            Response,
    espacio_id:          int            = Query(1),
    fecha_inicio:        Optional[date] = Query(None, description="Fecha de inicio (YYYY-MM-DD)"),
    fecha_fin:           Optional[date] = Query(None, description="Fecha de fin (YYYY-MM-DD)"),
    alcance:             Optional[str]  = Query("conformes", description="conformes | todos | anomalias"),
    regimen_horario:     Optional[str]  = Query("todos"),
    direccion:           Optional[str]  = Query("todos"),
    dias_semana:         Optional[str]  = Query(None),
    door:                Optional[str]  = Query(None),
    perfil_visita:       Optional[str]  = Query("todos"),
    marcajes:            Optional[str]  = Query("todos"),
    sala:                Optional[str]  = Query(None, description="sala_1 | sala_2 | todas"),
    carrera:             Optional[str]  = Query(None),
    facultad:            Optional[str]  = Query(None),
    cohorte:             Optional[str]  = Query(None),
    incluir_pausas_bano: bool           = Query(True, description="Incluir pausas de baño (3-15 min) en conformes"),
    desduplicar_rafagas: bool           = Query(True, description="Desduplicar ráfagas mecánicas de sensor < 1 min"),
    current_user:        Usuario        = Depends(get_current_user),
    db:                  AsyncSession   = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    return await AttendanceService.get_heatmap(
        session=db,
        espacio_id=espacio_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        alcance=alcance or "conformes",
        regimen_horario=regimen_horario or "todos",
        direccion=direccion or "todos",
        dias_semana=dias_semana,
        door=door,
        perfil_visita=perfil_visita or "todos",
        marcajes=marcajes or "todos",
        sala=sala,
        carrera=carrera,
        facultad=facultad,
        cohorte=cohorte,
        incluir_pausas_bano=incluir_pausas_bano,
        desduplicar_rafagas=desduplicar_rafagas,
    )


@router.get("/anomalies", summary="Registros con alertas de coherencia o marcajes")
async def get_anomalies(
    espacio_id: int = Query(1),
    limit: int = Query(100, le=500),
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    return await AttendanceService.obtener_anomalias_marcajes(
        session=db,
        espacio_id=espacio_id,
        limite=limit,
    )


@router.get("/academic-distribution", summary="Distribución de uso — placeholder hasta datos académicos")
async def get_academic_distribution(
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return {
        "mensaje": "Disponible cuando se integren datos académicos (carrera, PMA, cohorte).",
        "estado": "pendiente_datos",
    }


@router.get("/peak-valley", summary="Franjas horarias de pico y valle")
@cachear_respuesta(ttl_segundos=TTL_HISTORICOS, categoria="historicos")
async def get_peak_valley(
    response:     Response,
    fecha_inicio: Optional[date] = Query(None, description="YYYY-MM-DD"),
    fecha_fin:    Optional[date] = Query(None, description="YYYY-MM-DD"),
    espacio_id:   int            = Query(1),
    current_user: Usuario        = Depends(get_current_user),
    db:           AsyncSession   = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    return await AttendanceService.get_peak_valley_bands(db, espacio_id, fecha_inicio, fecha_fin)


@router.get("/weekly-evolution", summary="Evolución semanal por semanas ISO")
@cachear_respuesta(ttl_segundos=TTL_HISTORICOS, categoria="historicos")
async def get_weekly_evolution(
    response:            Response,
    espacio_id:          int            = Query(1),
    fecha_inicio:        Optional[date] = Query(None, description="YYYY-MM-DD"),
    fecha_fin:           Optional[date] = Query(None, description="YYYY-MM-DD"),
    alcance:             Optional[str]  = Query("conformes"),
    regimen_horario:     Optional[str]  = Query("todos"),
    direccion:           Optional[str]  = Query("todos"),
    dias_semana:         Optional[str]  = Query(None),
    door:                Optional[str]  = Query(None),
    perfil_visita:       Optional[str]  = Query("todos"),
    marcajes:            Optional[str]  = Query("todos"),
    sala:                Optional[str]  = Query(None, description="sala_1 | sala_2 | todas"),
    carrera:             Optional[str]  = Query(None),
    facultad:            Optional[str]  = Query(None),
    cohorte:             Optional[str]  = Query(None),
    incluir_pausas_bano: bool           = Query(True, description="Incluir pausas de baño (3-15 min) en conformes"),
    desduplicar_rafagas: bool           = Query(True, description="Desduplicar ráfagas mecánicas de sensor < 1 min"),
    current_user:        Usuario        = Depends(get_current_user),
    db:                  AsyncSession   = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    return await AttendanceService.get_weekly_evolution(
        session=db,
        espacio_id=espacio_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        alcance=alcance or "conformes",
        regimen_horario=regimen_horario or "todos",
        direccion=direccion or "todos",
        dias_semana=dias_semana,
        door=door,
        perfil_visita=perfil_visita or "todos",
        marcajes=marcajes or "todos",
        sala=sala,
        carrera=carrera,
        facultad=facultad,
        cohorte=cohorte,
        incluir_pausas_bano=incluir_pausas_bano,
        desduplicar_rafagas=desduplicar_rafagas,
    )


@router.get("/monthly-volume", summary="Volumen y promedio diario mensual")
@cachear_respuesta(ttl_segundos=TTL_HISTORICOS, categoria="historicos")
async def get_monthly_volume(
    response:            Response,
    espacio_id:          int            = Query(1),
    fecha_inicio:        Optional[date] = Query(None, description="YYYY-MM-DD"),
    fecha_fin:           Optional[date] = Query(None, description="YYYY-MM-DD"),
    alcance:             Optional[str]  = Query("conformes"),
    regimen_horario:     Optional[str]  = Query("todos"),
    direccion:           Optional[str]  = Query("todos"),
    dias_semana:         Optional[str]  = Query(None),
    door:                Optional[str]  = Query(None),
    perfil_visita:       Optional[str]  = Query("todos"),
    marcajes:            Optional[str]  = Query("todos"),
    sala:                Optional[str]  = Query(None, description="sala_1 | sala_2 | todas"),
    carrera:             Optional[str]  = Query(None),
    facultad:            Optional[str]  = Query(None),
    cohorte:             Optional[str]  = Query(None),
    incluir_pausas_bano: bool           = Query(True, description="Incluir pausas de baño (3-15 min) en conformes"),
    desduplicar_rafagas: bool           = Query(True, description="Desduplicar ráfagas mecánicas de sensor < 1 min"),
    current_user:        Usuario        = Depends(get_current_user),
    db:                  AsyncSession   = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    return await AttendanceService.get_monthly_volume(
        session=db,
        espacio_id=espacio_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        alcance=alcance or "conformes",
        regimen_horario=regimen_horario or "todos",
        direccion=direccion or "todos",
        dias_semana=dias_semana,
        door=door,
        perfil_visita=perfil_visita or "todos",
        marcajes=marcajes or "todos",
        sala=sala,
        carrera=carrera,
        facultad=facultad,
        cohorte=cohorte,
        incluir_pausas_bano=incluir_pausas_bano,
        desduplicar_rafagas=desduplicar_rafagas,
    )


@router.get("/academic-milestones-comparison", summary="Comparativa por hito del calendario académico")
@cachear_respuesta(ttl_segundos=TTL_HISTORICOS, categoria="historicos")
async def get_academic_milestones_comparison(
    response:            Response,
    espacio_id:          int            = Query(1),
    fecha_inicio:        Optional[date] = Query(None, description="YYYY-MM-DD"),
    fecha_fin:           Optional[date] = Query(None, description="YYYY-MM-DD"),
    alcance:             Optional[str]  = Query("conformes"),
    regimen_horario:     Optional[str]  = Query("todos"),
    direccion:           Optional[str]  = Query("todos"),
    dias_semana:         Optional[str]  = Query(None),
    door:                Optional[str]  = Query(None),
    perfil_visita:       Optional[str]  = Query("todos"),
    marcajes:            Optional[str]  = Query("todos"),
    sala:                Optional[str]  = Query(None, description="sala_1 | sala_2 | todas"),
    carrera:             Optional[str]  = Query(None),
    facultad:            Optional[str]  = Query(None),
    cohorte:             Optional[str]  = Query(None),
    incluir_pausas_bano: bool           = Query(True, description="Incluir pausas de baño (3-15 min) en conformes"),
    desduplicar_rafagas: bool           = Query(True, description="Desduplicar ráfagas mecánicas de sensor < 1 min"),
    current_user:        Usuario        = Depends(get_current_user),
    db:                  AsyncSession   = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    return await AttendanceService.get_academic_milestones_comparison(
        session=db,
        espacio_id=espacio_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        alcance=alcance or "conformes",
        regimen_horario=regimen_horario or "todos",
        direccion=direccion or "todos",
        dias_semana=dias_semana,
        door=door,
        perfil_visita=perfil_visita or "todos",
        marcajes=marcajes or "todos",
        sala=sala,
        carrera=carrera,
        facultad=facultad,
        cohorte=cohorte,
        incluir_pausas_bano=incluir_pausas_bano,
        desduplicar_rafagas=desduplicar_rafagas,
    )


@router.get("/doors-usage", summary="Histograma de accesos por torniquetes")
@cachear_respuesta(ttl_segundos=TTL_HISTORICOS, categoria="historicos")
async def get_doors_usage(
    response:            Response,
    fecha_inicio:        Optional[date] = Query(None, description="YYYY-MM-DD"),
    fecha_fin:           Optional[date] = Query(None, description="YYYY-MM-DD"),
    alcance:             Optional[str]  = Query("conformes"),
    regimen_horario:     Optional[str]  = Query("todos"),
    direccion:           Optional[str]  = Query("todos"),
    dias_semana:         Optional[str]  = Query(None),
    door:                Optional[str]  = Query(None),
    perfil_visita:       Optional[str]  = Query("todos"),
    marcajes:            Optional[str]  = Query("todos"),
    sala:                Optional[str]  = Query(None, description="sala_1 | sala_2 | todas"),
    carrera:             Optional[str]  = Query(None),
    facultad:            Optional[str]  = Query(None),
    incluir_pausas_bano: bool           = Query(True, description="Incluir pausas de baño (3-15 min) en conformes"),
    desduplicar_rafagas: bool           = Query(True, description="Desduplicar ráfagas mecánicas de sensor < 1 min"),
    espacio_id:          int            = Query(1),
    current_user:        Usuario        = Depends(get_current_user),
    db:                  AsyncSession   = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    return await AttendanceService.get_door_usage(
        db,
        espacio_id=espacio_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        alcance=alcance or "conformes",
        regimen_horario=regimen_horario or "todos",
        direccion=direccion or "todos",
        dias_semana=dias_semana,
        door=door,
        perfil_visita=perfil_visita or "todos",
        marcajes=marcajes or "todos",
        sala=sala,
        carrera=carrera,
        facultad=facultad,
        incluir_pausas_bano=incluir_pausas_bano,
        desduplicar_rafagas=desduplicar_rafagas,
    )


@router.get("/salas", summary="Listado dinámico de salas de biblioteca")
async def get_salas(
    espacio_id: int = Query(1),
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    return await AttendanceService.get_salas_biblioteca(session=db, espacio_id=espacio_id)


@router.post("/salas", summary="Registrar nueva sala dinámicamente")
async def create_sala(
    payload: SalaBibliotecaCreate,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    validar_acceso_espacio(payload.espacio_id, current_user)
    resultado_sala = await AttendanceService.create_sala_biblioteca(session=db, data=payload.model_dump())
    await invalidar_cache_por_espacio(payload.espacio_id)
    return resultado_sala


class SalaCapacidadUpdate(BaseModel):
    capacidad_asientos: int = Field(..., ge=1, description="Nueva capacidad física en asientos")


@router.put("/salas/{sala_id}/capacidad", summary="Actualizar capacidad de sala y sincronizar espacio")
async def update_sala_capacidad(
    sala_id: int,
    payload: SalaCapacidadUpdate,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    validar_acceso_espacio(1, current_user)
    resultado_actualizacion = await AttendanceService.update_capacidad_sala_biblioteca(
        session=db,
        sala_id=sala_id,
        capacidad_asientos=payload.capacidad_asientos,
    )
    await invalidar_cache_por_espacio(1)
    return resultado_actualizacion


@router.get("/rooms-comparison", summary="Comparativa analítica entre salas (Sala 1 vs Sala 2)")
@cachear_respuesta(ttl_segundos=TTL_HISTORICOS, categoria="historicos")
async def get_rooms_comparison(
    response:            Response,
    fecha_inicio:        Optional[date] = Query(None, description="YYYY-MM-DD"),
    fecha_fin:           Optional[date] = Query(None, description="YYYY-MM-DD"),
    alcance:             Optional[str]  = Query("todos"),
    regimen_horario:     Optional[str]  = Query("todos"),
    direccion:           Optional[str]  = Query("todos"),
    dias_semana:         Optional[str]  = Query(None),
    door:                Optional[str]  = Query(None),
    marcajes:            Optional[str]  = Query("todos"),
    carrera:             Optional[str]  = Query(None),
    facultad:            Optional[str]  = Query(None),
    espacio_id:          int            = Query(1),
    incluir_pausas_bano: bool           = Query(True, description="Incluir pausas de baño (3-15 min) en conformes"),
    desduplicar_rafagas: bool           = Query(True, description="Desduplicar ráfagas mecánicas de sensor < 1 min"),
    current_user:        Usuario        = Depends(get_current_user),
    db:                  AsyncSession   = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    return await AttendanceService.get_rooms_comparison(
        session=db,
        espacio_id=espacio_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        alcance=alcance or "todos",
        regimen_horario=regimen_horario or "todos",
        direccion=direccion or "todos",
        dias_semana=dias_semana,
        door=door,
        marcajes=marcajes or "todos",
        carrera=carrera,
        facultad=facultad,
        incluir_pausas_bano=incluir_pausas_bano,
        desduplicar_rafagas=desduplicar_rafagas,
    )


@router.get("/daily-average", summary="Promedio de ingresos por día de la semana (Lunes a Domingo)")
@cachear_respuesta(ttl_segundos=TTL_HISTORICOS, categoria="historicos")
async def get_daily_average_attendance(
    response:            Response,
    fecha_inicio:        Optional[date] = Query(None, description="YYYY-MM-DD"),
    fecha_fin:           Optional[date] = Query(None, description="YYYY-MM-DD"),
    alcance:             Optional[str]  = Query("todos"),
    regimen_horario:     Optional[str]  = Query("todos"),
    direccion:           Optional[str]  = Query("todos"),
    dias_semana:         Optional[str]  = Query(None),
    door:                Optional[str]  = Query(None),
    marcajes:            Optional[str]  = Query("todos"),
    carrera:             Optional[str]  = Query(None),
    facultad:            Optional[str]  = Query(None),
    espacio_id:          int            = Query(1),
    incluir_pausas_bano: bool           = Query(True, description="Incluir pausas de baño (3-15 min) en conformes"),
    desduplicar_rafagas: bool           = Query(True, description="Desduplicar ráfagas mecánicas de sensor < 1 min"),
    current_user:        Usuario        = Depends(get_current_user),
    db:                  AsyncSession   = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    return await AttendanceService.get_daily_average_attendance(
        session=db,
        espacio_id=espacio_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        alcance=alcance or "todos",
        regimen_horario=regimen_horario or "todos",
        direccion=direccion or "todos",
        dias_semana=dias_semana,
        door=door,
        marcajes=marcajes or "todos",
        carrera=carrera,
        facultad=facultad,
        incluir_pausas_bano=incluir_pausas_bano,
        desduplicar_rafagas=desduplicar_rafagas,
    )


@router.get("/curricular-distribution", summary="Distribución agregada de carreras y facultades (Ley 21.719)")
@cachear_respuesta(ttl_segundos=TTL_HISTORICOS, categoria="historicos")
async def get_curricular_distribution(
    response:            Response,
    fecha_inicio:        Optional[date] = Query(None, description="YYYY-MM-DD"),
    fecha_fin:           Optional[date] = Query(None, description="YYYY-MM-DD"),
    espacio_id:          int            = Query(1),
    alcance:             Optional[str]  = Query("conformes", description="conformes | todos | anomalias"),
    regimen_horario:     Optional[str]  = Query("todos", description="todos | dentro_horario | fuera_horario"),
    direccion:           Optional[str]  = Query("todos", description="todos | solo_ingreso | solo_salida"),
    dias_semana:         Optional[str]  = Query(None, description="lunes,martes..."),
    door:                Optional[str]  = Query(None),
    perfil_visita:       Optional[str]  = Query("todos", description="todos | rebote | estandar | profundo"),
    marcajes:            Optional[str]  = Query("todos", description="todos | 1 | 2 | 3-4 | 5+"),
    sala:                Optional[str]  = Query(None, description="sala_1 | sala_2 | todas"),
    carrera:             Optional[str]  = Query(None),
    facultad:            Optional[str]  = Query(None),
    cohorte:             Optional[str]  = Query(None),
    incluir_pausas_bano: bool           = Query(True, description="Incluir pausas de baño (3-15 min) en conformes"),
    desduplicar_rafagas: bool           = Query(True, description="Desduplicar ráfagas mecánicas de sensor < 1 min"),
    current_user:        Usuario        = Depends(get_current_user),
    db:                  AsyncSession   = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    return await AttendanceService.get_curricular_distribution(
        session=db,
        espacio_id=espacio_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        alcance=alcance or "conformes",
        regimen_horario=regimen_horario or "todos",
        direccion=direccion or "todos",
        dias_semana=dias_semana,
        door=door,
        perfil_visita=perfil_visita or "todos",
        marcajes=marcajes or "todos",
        sala=sala,
        carrera=carrera,
        facultad=facultad,
        cohorte=cohorte,
        incluir_pausas_bano=incluir_pausas_bano,
        desduplicar_rafagas=desduplicar_rafagas,
    )


@router.get("/available-filters", summary="Opciones dinámicas de filtros (Salas, Puertas, Carreras)")
async def get_available_filters(
    espacio_id: int = Query(1),
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    return await AttendanceService.get_available_filters(session=db, espacio_id=espacio_id)


@router.get("/checkins-distribution", summary="Distribución de usuarios por marcajes diarios")
@cachear_respuesta(ttl_segundos=TTL_HISTORICOS, categoria="historicos")
async def get_checkins_distribution(
    response:            Response,
    fecha_inicio:        Optional[date] = Query(None, description="YYYY-MM-DD"),
    fecha_fin:           Optional[date] = Query(None, description="YYYY-MM-DD"),
    alcance:             Optional[str]  = Query("conformes"),
    regimen_horario:     Optional[str]  = Query("todos"),
    direccion:           Optional[str]  = Query("todos"),
    dias_semana:         Optional[str]  = Query(None),
    door:                Optional[str]  = Query(None),
    perfil_visita:       Optional[str]  = Query("todos"),
    marcajes:            Optional[str]  = Query("todos"),
    sala:                Optional[str]  = Query(None, description="sala_1 | sala_2 | todas"),
    carrera:             Optional[str]  = Query(None),
    facultad:            Optional[str]  = Query(None),
    espacio_id:          int            = Query(1),
    incluir_pausas_bano: bool           = Query(True, description="Incluir pausas de baño (3-15 min) en conformes"),
    desduplicar_rafagas: bool           = Query(True, description="Desduplicar ráfagas mecánicas de sensor < 1 min"),
    current_user:        Usuario        = Depends(get_current_user),
    db:                  AsyncSession   = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    return await AttendanceService.get_checkin_distribution(
        session=db,
        espacio_id=espacio_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        alcance=alcance or "conformes",
        regimen_horario=regimen_horario or "todos",
        direccion=direccion or "todos",
        dias_semana=dias_semana,
        door=door,
        perfil_visita=perfil_visita or "todos",
        marcajes=marcajes or "todos",
        sala=sala,
        carrera=carrera,
        facultad=facultad,
        incluir_pausas_bano=incluir_pausas_bano,
        desduplicar_rafagas=desduplicar_rafagas,
    )


@router.get("/visit-profiles-donut", summary="Distribución analítica de perfiles de visita (Donut Plotly)")
@cachear_respuesta(ttl_segundos=TTL_HISTORICOS, categoria="historicos")
async def get_visit_profiles_donut(
    response:            Response,
    fecha_inicio:        Optional[date] = Query(None, description="YYYY-MM-DD"),
    fecha_fin:           Optional[date] = Query(None, description="YYYY-MM-DD"),
    alcance:             Optional[str]  = Query("todos"),
    regimen_horario:     Optional[str]  = Query("todos"),
    direccion:           Optional[str]  = Query("todos"),
    dias_semana:         Optional[str]  = Query(None),
    door:                Optional[str]  = Query(None),
    perfil_visita:       Optional[str]  = Query("todos"),
    marcajes:            Optional[str]  = Query("todos"),
    sala:                Optional[str]  = Query(None, description="sala_1 | sala_2 | todas"),
    carrera:             Optional[str]  = Query(None),
    facultad:            Optional[str]  = Query(None),
    espacio_id:          int            = Query(1),
    incluir_pausas_bano: bool           = Query(True, description="Incluir pausas de baño (3-15 min) en conformes"),
    desduplicar_rafagas: bool           = Query(True, description="Desduplicar ráfagas mecánicas de sensor < 1 min"),
    current_user:        Usuario        = Depends(get_current_user),
    db:                  AsyncSession   = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    return await AttendanceService.get_visit_profiles_donut(
        session=db,
        espacio_id=espacio_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        alcance=alcance or "todos",
        regimen_horario=regimen_horario or "todos",
        direccion=direccion or "todos",
        dias_semana=dias_semana,
        door=door,
        perfil_visita=perfil_visita or "todos",
        marcajes=marcajes or "todos",
        sala=sala,
        carrera=carrera,
        facultad=facultad,
        incluir_pausas_bano=incluir_pausas_bano,
        desduplicar_rafagas=desduplicar_rafagas,
    )


@router.get("/raw-events", summary="Listado paginado de microdatos de asistencia")
async def get_raw_attendance_events(
    page:                int            = Query(1, ge=1),
    page_size:           int            = Query(50, ge=1, le=200),
    fecha_inicio:        Optional[date] = Query(None, description="YYYY-MM-DD"),
    fecha_fin:           Optional[date] = Query(None, description="YYYY-MM-DD"),
    door:                Optional[str]  = Query(None),
    search_hash:         Optional[str]  = Query(None),
    categoria:           Optional[str]  = Query(None, description="fuera_de_horario | sin_salida | hora_invertida | sin_credencial | marcaje_excesivo | conforme | anomalias"),
    alcance:             Optional[str]  = Query("todos", description="todos | conformes | anomalias"),
    regimen_horario:     Optional[str]  = Query("todos", description="todos | dentro_horario | fuera_horario"),
    direccion:           Optional[str]  = Query("todos", description="todos | solo_ingreso | solo_salida"),
    dias_semana:         Optional[str]  = Query(None),
    perfil_visita:       Optional[str]  = Query("todos"),
    marcajes:            Optional[str]  = Query("todos"),
    espacio_id:          int            = Query(1),
    incluir_pausas_bano: bool           = Query(True, description="Incluir pausas de baño (3-15 min) en conformes"),
    desduplicar_rafagas: bool           = Query(True, description="Desduplicar ráfagas mecánicas de sensor < 1 min"),
    current_user:        Usuario        = Depends(get_current_user),
    db:                  AsyncSession   = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    return await AttendanceService.get_raw_events(
        session=db,
        espacio_id=espacio_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        door=door,
        search_hash=search_hash,
        categoria=categoria,
        alcance=alcance or "todos",
        regimen_horario=regimen_horario or "todos",
        direccion=direccion or "todos",
        dias_semana=dias_semana,
        perfil_visita=perfil_visita or "todos",
        marcajes=marcajes or "todos",
        page=page,
        page_size=page_size,
        incluir_pausas_bano=incluir_pausas_bano,
        desduplicar_rafagas=desduplicar_rafagas,
    )


@router.get("/export-raw-csv", summary="Exportar microdatos de asistencia a CSV con registro de auditoría")
async def export_raw_attendance_csv(
    background_tasks:    BackgroundTasks,
    request:             Request,
    fecha_inicio:        Optional[date] = Query(None, description="YYYY-MM-DD"),
    fecha_fin:           Optional[date] = Query(None, description="YYYY-MM-DD"),
    door:                Optional[str]  = Query(None),
    search_hash:         Optional[str]  = Query(None),
    categoria:           Optional[str]  = Query(None),
    alcance:             Optional[str]  = Query("todos"),
    regimen_horario:     Optional[str]  = Query("todos"),
    direccion:           Optional[str]  = Query("todos"),
    dias_semana:         Optional[str]  = Query(None),
    perfil_visita:       Optional[str]  = Query("todos"),
    marcajes:            Optional[str]  = Query("todos"),
    espacio_id:          int            = Query(1),
    incluir_pausas_bano: bool           = Query(True, description="Incluir pausas de baño (3-15 min) en conformes"),
    desduplicar_rafagas: bool           = Query(True, description="Desduplicar ráfagas mecánicas de sensor < 1 min"),
    current_user:        Usuario        = Depends(require_permission("can_export")),
    db:                  AsyncSession   = Depends(get_db),
):
    validar_acceso_espacio(espacio_id, current_user)
    csv_content, total_count = await AttendanceService.export_raw_csv(
        session=db,
        espacio_id=espacio_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        door=door,
        search_hash=search_hash,
        categoria=categoria,
        alcance=alcance or "todos",
        regimen_horario=regimen_horario or "todos",
        direccion=direccion or "todos",
        dias_semana=dias_semana,
        perfil_visita=perfil_visita or "todos",
        marcajes=marcajes or "todos",
        incluir_pausas_bano=incluir_pausas_bano,
        desduplicar_rafagas=desduplicar_rafagas,
    )

    client_ip = request.client.host if request.client else "127.0.0.1"
    detalle = f"Filtros: puerta={door or 'todas'}, categoria={categoria or 'todas'}, alcance={alcance or 'todos'}, horario={regimen_horario or 'todos'}, direccion={direccion or 'todos'}"

    from app.services.audit_service import record_download_audit
    background_tasks.add_task(
        record_download_audit,
        usuario_id=current_user.id,
        modulo="biblioteca",
        formato="csv",
        filtro_fecha_inicio=str(fecha_inicio) if fecha_inicio else None,
        filtro_fecha_fin=str(fecha_fin) if fecha_fin else None,
        filtro_detalle=detalle,
        total_registros=total_count,
        ip_origen=client_ip,
    )

    filename = f"microdatos_asistencia_biblioteca_{fecha_inicio or 'inicio'}_{fecha_fin or 'fin'}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/analisis-24h", summary="Análisis de rendimiento y métricas Delta de Campaña 24 Horas")
async def get_analisis_24h(
    espacio_id: int = Query(1),
    campana_id: Optional[int] = Query(None),
    fecha_inicio: Optional[date] = Query(None),
    fecha_fin: Optional[date] = Query(None),
    bloque_horario: Optional[str] = Query("todos", description="todos | lunes_jueves | viernes"),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Retorna métricas comparativas diurnas vs nocturnas, delta 24h,
    segmentación curricular nocturna y fases de madrugada para Sala 2 Pecera.
    """
    return await AttendanceService.get_analisis_24h(
        session=db,
        espacio_id=espacio_id,
        campana_id=campana_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        bloque_horario=bloque_horario,
    )


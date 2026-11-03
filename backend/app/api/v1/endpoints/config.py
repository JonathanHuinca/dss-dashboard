from datetime import date
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import get_current_user, require_role
from app.core.cache import invalidar_cache_por_espacio, limpiar_toda_la_cache
from app.core.security import validar_acceso_espacio
from app.core.database import get_db
from app.core.security_cipher import decrypt_api_key, mask_api_key
from app.domain.auth_models import Usuario
from app.schemas.config_schemas import (
    ConfiguracionEspaciosResponse,
    ConfiguracionEspaciosUpdate,
    LLMProviderUpdate,
    HorarioOperacionResponse,
    HorarioOperacionCreate,
    HorarioOperacionUpdate,
    EspacioResponse,
    EspacioCapacidadUpdate,
    ContingenciaCrear,
    ContingenciaRespuesta,
    EventoCalendarioActualizar,
    EventoCalendarioCrear,
)
from app.services.calendar_service import CalendarService
from app.services.config_service import (
    get_configuracion_espacio,
    toggle_ia_asistente,
    update_llm_provider,
    get_horarios_operacion,
    create_horario_operacion,
    update_horario_operacion,
    delete_horario_operacion,
    get_espacios,
    get_espacio_by_id,
    update_espacio_capacidad,
)


router = APIRouter()
public_router = APIRouter()


async def require_superadmin(
    current_user: Usuario = Depends(get_current_user),
) -> Usuario:
    user_roles = [r.nombre for r in current_user.roles]
    if "SuperAdmin" not in user_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permisos insuficientes: se requiere rol SuperAdmin",
        )
    return current_user


from typing import Optional

async def get_espacio_id(
    x_espacio_id: Optional[int] = Header(None, alias="x-espacio-id"),
    espacio_id: Optional[int] = None,
) -> int:
    return x_espacio_id or espacio_id or 1


async def check_ia_active(
    db: AsyncSession = Depends(get_db),
    espacio_id: int = Depends(get_espacio_id),
) -> bool:
    config = await get_configuracion_espacio(db, 1)
    if not config.ia_asistente_activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El asistente de IA se encuentra desactivado temporalmente para toda la plataforma.",
        )
    return True


@public_router.get("/ia-status", summary="Consultar estado de disponibilidad global de IA")
@router.get("/ia-status", summary="Consultar estado de disponibilidad global de IA")
async def consultar_estado_ia(
    db: AsyncSession = Depends(get_db),
):
    """Retorna si el Asistente de IA está activo globalmente en la plataforma."""
    config = await get_configuracion_espacio(db, 1)
    return {
        "ia_asistente_activo": bool(config.ia_asistente_activo),
    }


@router.get("", response_model=ConfiguracionEspaciosResponse, summary="Obtener configuración de espacio")
@router.get("/", response_model=ConfiguracionEspaciosResponse, include_in_schema=False)
async def get_config(
    db: AsyncSession = Depends(get_db),
    espacio_id: int = Depends(get_espacio_id),
    current_user: Usuario = Depends(get_current_user),
) -> ConfiguracionEspaciosResponse:
    validar_acceso_espacio(espacio_id, current_user)
    config = await get_configuracion_espacio(db, espacio_id)
    has_key = bool(config.encrypted_api_key and config.encrypted_api_key.strip())
    masked = None
    if has_key:
        try:
            plain = decrypt_api_key(config.encrypted_api_key)
            masked = mask_api_key(plain)
        except Exception:
            masked = "••••••••"

    return ConfiguracionEspaciosResponse(
        id=config.id,
        espacio_id=config.espacio_id,
        ia_asistente_activo=config.ia_asistente_activo,
        active_provider=config.active_provider,
        default_model=config.default_model,
        has_api_key=has_key,
        masked_api_key=masked,
        updated_at=config.updated_at,
    )


@router.put("/toggle-ia", response_model=ConfiguracionEspaciosResponse, summary="Alternar estado del asistente de IA")
async def toggle_ia(
    _: Usuario = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
    espacio_id: int = Depends(get_espacio_id),
) -> ConfiguracionEspaciosResponse:
    config = await toggle_ia_asistente(db, espacio_id)
    has_key = bool(config.encrypted_api_key and config.encrypted_api_key.strip())
    masked = None
    if has_key:
        try:
            plain = decrypt_api_key(config.encrypted_api_key)
            masked = mask_api_key(plain)
        except Exception:
            masked = "••••••••"

    return ConfiguracionEspaciosResponse(
        id=config.id,
        espacio_id=config.espacio_id,
        ia_asistente_activo=config.ia_asistente_activo,
        active_provider=config.active_provider,
        default_model=config.default_model,
        has_api_key=has_key,
        masked_api_key=masked,
        updated_at=config.updated_at,
    )


@router.put("/llm-provider", response_model=ConfiguracionEspaciosResponse, summary="Configurar proveedor y API Key del LLM")
async def set_llm_provider(
    req: LLMProviderUpdate,
    _: Usuario = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
    espacio_id: int = Depends(get_espacio_id),
) -> ConfiguracionEspaciosResponse:
    if not req.api_key or not req.api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La API Key no puede estar vacía",
        )
    if req.provider.lower() == "claude":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El proveedor 'claude' no está implementado actualmente en el sistema. Utilice 'gemini'.",
        )
    if req.provider.lower() != "gemini":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Proveedor '{req.provider}' no soportado. Proveedor soportado: 'gemini'.",
        )
    config = await update_llm_provider(
        db=db,
        espacio_id=espacio_id,
        provider=req.provider,
        default_model=req.default_model,
        api_key=req.api_key,
    )
    plain = req.api_key.strip()
    return ConfiguracionEspaciosResponse(
        id=config.id,
        espacio_id=config.espacio_id,
        ia_asistente_activo=config.ia_asistente_activo,
        active_provider=config.active_provider,
        default_model=config.default_model,
        has_api_key=True,
        masked_api_key=mask_api_key(plain),
        updated_at=config.updated_at,
    )


@router.get("/horarios", response_model=list[HorarioOperacionResponse], summary="Listar horarios de operación")
async def list_horarios(
    espacio_id: Optional[int] = None,
    anio: Optional[int] = None,
    subespacio: Optional[str] = None,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[HorarioOperacionResponse]:
    if espacio_id is not None:
        validar_acceso_espacio(espacio_id, current_user)
    horarios = await get_horarios_operacion(db=db, espacio_id=espacio_id, anio=anio, subespacio=subespacio)
    return [HorarioOperacionResponse.model_validate(h) for h in horarios]


def _notificar_cambio_operativo_a_modelos() -> None:
    try:
        from app.ml.orquestador_entrenamiento import estado_entrenamiento, ejecutar_entrenamiento_en_fondo
        if not estado_entrenamiento.get("en_progreso", False):
            asyncio.create_task(ejecutar_entrenamiento_en_fondo(forzar=True))
    except Exception:
        pass


@router.post("/horarios", response_model=HorarioOperacionResponse, summary="Crear horario de operación")
async def create_horario(
    data: HorarioOperacionCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_role("SuperAdmin", "Directivo")),
) -> HorarioOperacionResponse:
    horario = await create_horario_operacion(db=db, data=data)
    from app.services.attendance_service import invalidar_cache_horarios_asistencia
    from app.services.vehicle_service import invalidar_cache_horarios_vehiculos
    invalidar_cache_horarios_asistencia(horario.espacio_id)
    invalidar_cache_horarios_vehiculos(horario.espacio_id)
    await invalidar_cache_por_espacio(horario.espacio_id)
    _notificar_cambio_operativo_a_modelos()
    return HorarioOperacionResponse.model_validate(horario)


@router.put("/horarios/{horario_id}", response_model=HorarioOperacionResponse, summary="Actualizar horario de operación")
async def update_horario(
    horario_id: int,
    data: HorarioOperacionUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_role("SuperAdmin", "Directivo")),
) -> HorarioOperacionResponse:
    horario = await update_horario_operacion(db=db, horario_id=horario_id, data=data)
    if not horario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Horario de operación no encontrado",
        )
    from app.services.attendance_service import invalidar_cache_horarios_asistencia
    from app.services.vehicle_service import invalidar_cache_horarios_vehiculos
    invalidar_cache_horarios_asistencia(horario.espacio_id)
    invalidar_cache_horarios_vehiculos(horario.espacio_id)
    await invalidar_cache_por_espacio(horario.espacio_id)
    _notificar_cambio_operativo_a_modelos()
    return HorarioOperacionResponse.model_validate(horario)


@router.delete("/horarios/{horario_id}", summary="Eliminar horario de operación")
async def delete_horario(
    horario_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_role("SuperAdmin", "Directivo")),
) -> dict:
    deleted = await delete_horario_operacion(db=db, horario_id=horario_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Horario de operación no encontrado",
        )
    from app.services.attendance_service import invalidar_cache_horarios_asistencia
    from app.services.vehicle_service import invalidar_cache_horarios_vehiculos
    invalidar_cache_horarios_asistencia()
    invalidar_cache_horarios_vehiculos()
    await limpiar_toda_la_cache()
    _notificar_cambio_operativo_a_modelos()
    return {"detail": "Horario eliminado exitosamente"}


@router.get("/espacios", response_model=list[EspacioResponse], summary="Listar todos los espacios y capacidades")
async def list_espacios(
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
) -> list[EspacioResponse]:
    espacios = await get_espacios(db)
    return [EspacioResponse.model_validate(e) for e in espacios]


@router.get("/espacios/{espacio_id}", response_model=EspacioResponse, summary="Obtener información de un espacio")
async def get_espacio_info(
    espacio_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> EspacioResponse:
    validar_acceso_espacio(espacio_id, current_user)
    espacio = await get_espacio_by_id(db, espacio_id)
    if not espacio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Espacio no encontrado",
        )
    return EspacioResponse.model_validate(espacio)


@router.put("/espacios/{espacio_id}/capacidad", response_model=EspacioResponse, summary="Actualizar capacidad máxima de aforo de un espacio")
async def update_capacidad(
    espacio_id: int,
    data: EspacioCapacidadUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role("SuperAdmin", "Directivo")),
) -> EspacioResponse:
    validar_acceso_espacio(espacio_id, current_user)
    espacio = await update_espacio_capacidad(db, espacio_id, data.capacidad_max)
    if not espacio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Espacio no encontrado",
        )
    await invalidar_cache_por_espacio(espacio_id)
    return EspacioResponse.model_validate(espacio)


@router.post("/calendar/sync-scrape", summary="Sincronizar calendario académico UCT mediante web scraping")
async def sync_calendar_scrape(
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_role("SuperAdmin", "Directivo")),
) -> dict:
    from app.services.calendar_scraper import scrape_and_sync_uct_calendar
    try:
        result = await scrape_and_sync_uct_calendar(db)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error durante el scraping del calendario académico: {str(e)}",
        )


@router.get("/calendar/status", summary="Consultar estado y resumen del calendario académico")
async def get_calendar_status(
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
) -> dict:
    from sqlalchemy import text
    sql = text("""
        SELECT 
            COUNT(*) AS total_dias,
            SUM(CASE WHEN is_holiday = 1 THEN 1 ELSE 0 END) AS total_feriados,
            SUM(CASE WHEN is_break = 1 THEN 1 ELSE 0 END) AS total_recesos,
            SUM(CASE WHEN suspension_actividades = 1 THEN 1 ELSE 0 END) AS total_suspensiones,
            SUM(CASE WHEN is_exam_period = 1 THEN 1 ELSE 0 END) AS total_examenes,
            SUM(CASE WHEN is_strike_federado = 1 THEN 1 ELSE 0 END) AS total_paros_federados,
            SUM(CASE WHEN is_strike_carrera = 1 THEN 1 ELSE 0 END) AS total_paros_carrera,
            MIN(fecha) AS fecha_min,
            MAX(fecha) AS fecha_max
        FROM calendario_academico
    """)
    row = (await db.execute(sql)).first()
    return {
        "total_dias": int(row.total_dias or 0),
        "total_feriados": int(row.total_feriados or 0),
        "total_recesos": int(row.total_recesos or 0),
        "total_suspensiones": int(row.total_suspensiones or 0),
        "total_examenes": int(row.total_examenes or 0),
        "total_paros_federados": int(row.total_paros_federados or 0),
        "total_paros_carrera": int(row.total_paros_carrera or 0),
        "fecha_min": str(row.fecha_min) if row.fecha_min else None,
        "fecha_max": str(row.fecha_max) if row.fecha_max else None,
        "fuente_oficial": "https://www.uct.cl/calendario-academico/",
    }


@router.get("/contingencias", response_model=list[ContingenciaRespuesta], summary="Listar contingencias y paros académicos")
async def listar_contingencias(
    anio: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
) -> list[ContingenciaRespuesta]:
    servicio = CalendarService()
    items = await servicio.obtener_contingencias(db, anio)
    return [ContingenciaRespuesta.model_validate(c) for c in items]


@router.post("/contingencias", response_model=ContingenciaRespuesta, status_code=status.HTTP_201_CREATED, summary="Registrar contingencia, paro federado o por carrera")
async def registrar_contingencia(
    data: ContingenciaCrear,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_role("SuperAdmin", "Directivo")),
) -> ContingenciaRespuesta:
    servicio = CalendarService()
    nueva = await servicio.crear_contingencia(db, data)
    await limpiar_toda_la_cache()
    _notificar_cambio_operativo_a_modelos()
    return ContingenciaRespuesta.model_validate(nueva)


@router.delete("/contingencias/{contingencia_id}", summary="Eliminar contingencia o paro registrado")
async def eliminar_contingencia(
    contingencia_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_role("SuperAdmin", "Directivo")),
) -> dict:
    servicio = CalendarService()
    eliminado = await servicio.eliminar_contingencia(db, contingencia_id)
    if not eliminado:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contingencia académica no encontrada",
        )
    await limpiar_toda_la_cache()
    _notificar_cambio_operativo_a_modelos()
    return {"detail": "Contingencia académica eliminada exitosamente"}


@router.get("/calendar/resumen-anual", summary="Obtener días del año clasificados para visualización en gráficos")
async def obtener_resumen_anual_calendario(
    anio: int = 2026,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
) -> list[dict]:
    servicio = CalendarService()
    return await servicio.obtener_resumen_anual_calendario(db, anio)


@router.get("/calendar/events", summary="Listar eventos del calendario académico guardados en la BD")
async def listar_eventos_calendario(
    anio: int = None,
    categoria: str = None,
    busqueda: str = None,
    agrupar_periodos: bool = True,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
) -> list[dict]:
    servicio = CalendarService()
    return await servicio.obtener_eventos_calendario(db, anio, categoria, busqueda, agrupar_periodos)


@router.post("/calendar/depurar", summary="Depurar registros irrelevantes del calendario académico")
async def depurar_calendario_academico(
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_role("Admin_Sistema", "Director_Recinto")),
) -> dict:
    servicio = CalendarService()
    eliminados = await servicio.depurar_calendario_basura(db)
    return {
        "registros_eliminados": eliminados,
        "mensaje": f"Se eliminaron {eliminados} registros no conformes del calendario.",
    }


@router.put("/calendar/events/{fecha}", summary="Modificar o categorizar manualmente un evento del calendario")
async def actualizar_evento_calendario(
    fecha: date,
    datos: EventoCalendarioActualizar,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_role("Admin_Sistema", "Director_Recinto")),
) -> dict:
    servicio = CalendarService()
    item = await servicio.actualizar_evento_calendario(
        db=db,
        fecha=fecha,
        descripcion=datos.descripcion,
        is_holiday=datos.is_holiday,
        is_break=datos.is_break,
        is_exam_period=datos.is_exam_period,
        is_class_milestone=datos.is_class_milestone,
        suspension_actividades=datos.suspension_actividades,
        is_strike_federado=datos.is_strike_federado,
        is_strike_carrera=datos.is_strike_carrera,
        tipo_contingencia=datos.tipo_contingencia,
    )
    return {
        "mensaje": "Evento actualizado exitosamente",
        "fecha": item.fecha.isoformat(),
        "descripcion": item.descripcion,
        "fuente": item.fuente,
    }


@router.post("/calendar/events", summary="Crear manualmente un hito o rango de fechas en el calendario")
async def crear_evento_calendario(
    datos: EventoCalendarioCrear,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_role("Admin_Sistema", "Director_Recinto")),
) -> dict:
    servicio = CalendarService()
    fecha_fin = datos.fecha_fin or datos.fecha_inicio
    items = await servicio.crear_evento_calendario(
        db=db,
        fecha_inicio=datos.fecha_inicio,
        fecha_fin=fecha_fin,
        descripcion=datos.descripcion,
        is_holiday=datos.is_holiday,
        is_break=datos.is_break,
        is_exam_period=datos.is_exam_period,
        is_class_milestone=datos.is_class_milestone,
        suspension_actividades=datos.suspension_actividades,
        is_strike_federado=datos.is_strike_federado,
        is_strike_carrera=datos.is_strike_carrera,
        tipo_contingencia=datos.tipo_contingencia,
    )
    return {
        "mensaje": f"Se registraron {len(items)} días en el calendario",
        "dias_creados": len(items),
    }


@router.delete("/calendar/events/{fecha}", summary="Eliminar manualmente un evento del calendario")
async def eliminar_evento_calendario(
    fecha: date,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_role("Admin_Sistema", "Director_Recinto")),
) -> dict:
    servicio = CalendarService()
    eliminado = await servicio.eliminar_evento_calendario(db, fecha)
    if not eliminado:
        raise HTTPException(status_code=404, detail="Evento de calendario no encontrado")
    return {"mensaje": "Evento eliminado exitosamente"}







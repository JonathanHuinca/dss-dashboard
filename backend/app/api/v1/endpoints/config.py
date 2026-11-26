from datetime import date
import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import get_current_user, require_role
from app.core.cache import invalidar_cache_por_espacio, limpiar_toda_la_cache
from app.core.config import settings
from app.core.security import obtener_espacios_autorizados, validar_acceso_espacio
from app.core.database import get_db
from app.core.security_cipher import decrypt_api_key, mask_api_key
from app.core.tiempo import marcar_utc
from app.domain.auth_models import Usuario
from app.domain.config_models import HorarioOperacion
from app.domain.models import ContingenciaAcademica
from app.services.auth_service import normalizar_rol
from app.schemas.config_schemas import (
    CatalogoProveedoresIAResponse,
    ConfiguracionEspaciosResponse,
    ConfiguracionEspaciosUpdate,
    ConfiguracionSMTPCreate,
    ConfiguracionSMTPListResponse,
    ConfiguracionSMTPResponse,
    ConfiguracionSMTPUpdate,
    CredencialIACreate,
    CredencialIAResponse,
    CredencialIAUpdate,
    CredencialesIAListResponse,
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
    ProveedorCatalogoItem,
    SMTPTestRequest,
    TestConexionIAResponse,
    TestConexionSMTPResponse,
)
from app.services.calendar_service import CalendarService
from app.services.config_service import (
    activar_configuracion_smtp,
    activar_credencial_ia,
    actualizar_configuracion_smtp,
    actualizar_credencial_ia,
    crear_configuracion_smtp,
    crear_credencial_ia,
    eliminar_configuracion_smtp,
    eliminar_credencial_ia,
    get_configuracion_espacio,
    listar_configuraciones_smtp,
    listar_credenciales_ia,
    obtener_configuracion_smtp,
    obtener_credencial_ia,
    probar_configuracion_smtp_guardada,
    probar_credencial_ia_guardada,
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

logger = logging.getLogger(__name__)
router = APIRouter()
public_router = APIRouter()

require_superadmin = require_role("Admin_Sistema", "SuperAdmin")


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
    from app.services.llm_client import CATALOGO_PROVEEDORES_IA

    pid = (req.provider or "").strip().lower()
    if pid not in CATALOGO_PROVEEDORES_IA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Proveedor '{req.provider}' no soportado.",
        )
    meta = CATALOGO_PROVEEDORES_IA[pid]
    if meta.get("requires_api_key", True) and (not req.api_key or not req.api_key.strip()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La API Key no puede estar vacía",
        )
    config = await update_llm_provider(
        db=db,
        espacio_id=espacio_id,
        provider=pid,
        default_model=req.default_model,
        api_key=req.api_key,
    )
    plain = (req.api_key or "").strip()
    return ConfiguracionEspaciosResponse(
        id=config.id,
        espacio_id=config.espacio_id,
        ia_asistente_activo=config.ia_asistente_activo,
        active_provider=config.active_provider,
        default_model=config.default_model,
        has_api_key=bool(plain),
        masked_api_key=mask_api_key(plain) if plain else "",
        updated_at=config.updated_at,
    )


def _es_admin_sistema(user: Usuario) -> bool:
    return any(normalizar_rol(r.nombre) == "Admin_Sistema" for r in (getattr(user, "roles", None) or []))


@router.get("/horarios", response_model=list[HorarioOperacionResponse], summary="Listar horarios de operación")
async def list_horarios(
    espacio_id: Optional[int] = None,
    anio: Optional[int] = None,
    subespacio: Optional[str] = None,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[HorarioOperacionResponse]:
    espacios_autorizados = obtener_espacios_autorizados(current_user)
    if espacio_id is not None:
        validar_acceso_espacio(espacio_id, current_user)
    elif espacios_autorizados is not None and not espacios_autorizados:
        return []
    horarios = await get_horarios_operacion(db=db, espacio_id=espacio_id, anio=anio, subespacio=subespacio)
    if espacios_autorizados is not None:
        horarios = [h for h in horarios if h.espacio_id in espacios_autorizados]
    return [HorarioOperacionResponse.model_validate(h) for h in horarios]


@router.post("/horarios", response_model=HorarioOperacionResponse, summary="Crear horario de operación")
async def create_horario(
    data: HorarioOperacionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role("Admin_Sistema", "Director_Recinto")),
) -> HorarioOperacionResponse:
    validar_acceso_espacio(data.espacio_id, current_user)
    horario = await create_horario_operacion(db=db, data=data)
    from app.services.attendance_service import invalidar_cache_horarios_asistencia
    from app.services.vehicle_service import invalidar_cache_horarios_vehiculos
    invalidar_cache_horarios_asistencia(horario.espacio_id)
    invalidar_cache_horarios_vehiculos(horario.espacio_id)
    await invalidar_cache_por_espacio(horario.espacio_id)
    return HorarioOperacionResponse.model_validate(horario)


@router.put("/horarios/{horario_id}", response_model=HorarioOperacionResponse, summary="Actualizar horario de operación")
async def update_horario(
    horario_id: int,
    data: HorarioOperacionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role("Admin_Sistema", "Director_Recinto")),
) -> HorarioOperacionResponse:
    existente = await db.get(HorarioOperacion, horario_id)
    if not existente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Horario de operación no encontrado",
        )
    validar_acceso_espacio(existente.espacio_id, current_user)
    nuevo_espacio = getattr(data, "espacio_id", None)
    if nuevo_espacio is not None:
        validar_acceso_espacio(nuevo_espacio, current_user)
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
    return HorarioOperacionResponse.model_validate(horario)


@router.delete("/horarios/{horario_id}", summary="Eliminar horario de operación")
async def delete_horario(
    horario_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role("Admin_Sistema", "Director_Recinto")),
) -> dict:
    existente = await db.get(HorarioOperacion, horario_id)
    if not existente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Horario de operación no encontrado",
        )
    validar_acceso_espacio(existente.espacio_id, current_user)
    deleted = await delete_horario_operacion(db=db, horario_id=horario_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Horario de operación no encontrado",
        )
    from app.services.attendance_service import invalidar_cache_horarios_asistencia
    from app.services.vehicle_service import invalidar_cache_horarios_vehiculos
    invalidar_cache_horarios_asistencia(existente.espacio_id)
    invalidar_cache_horarios_vehiculos(existente.espacio_id)
    await invalidar_cache_por_espacio(existente.espacio_id)
    return {"detail": "Horario eliminado exitosamente"}


@router.get("/espacios", response_model=list[EspacioResponse], summary="Listar todos los espacios y capacidades")
async def list_espacios(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> list[EspacioResponse]:
    espacios_autorizados = obtener_espacios_autorizados(current_user)
    if espacios_autorizados is not None and not espacios_autorizados:
        return []
    espacios = await get_espacios(db)
    if espacios_autorizados is not None:
        espacios = [e for e in espacios if e.id in espacios_autorizados]
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
    _: Usuario = Depends(require_role("Admin_Sistema")),
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
    current_user: Usuario = Depends(require_role("Admin_Sistema", "Director_Recinto")),
) -> ContingenciaRespuesta:
    if data.espacio_id is None:
        if not _es_admin_sistema(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo Admin_Sistema puede registrar contingencias globales sin recinto asignado.",
            )
    else:
        validar_acceso_espacio(data.espacio_id, current_user)
    servicio = CalendarService()
    nueva = await servicio.crear_contingencia(db, data)
    if data.espacio_id is not None:
        await invalidar_cache_por_espacio(data.espacio_id)
    else:
        await limpiar_toda_la_cache()
    _notificar_cambio_operativo_a_modelos()
    return ContingenciaRespuesta.model_validate(nueva)


@router.delete("/contingencias/{contingencia_id}", summary="Eliminar contingencia o paro registrado")
async def eliminar_contingencia(
    contingencia_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role("Admin_Sistema", "Director_Recinto")),
) -> dict:
    existente = await db.get(ContingenciaAcademica, contingencia_id)
    if not existente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contingencia académica no encontrada",
        )
    if existente.espacio_id is None:
        if not _es_admin_sistema(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo Admin_Sistema puede eliminar contingencias globales.",
            )
    else:
        validar_acceso_espacio(existente.espacio_id, current_user)
    servicio = CalendarService()
    eliminado = await servicio.eliminar_contingencia(db, contingencia_id)
    if not eliminado:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contingencia académica no encontrada",
        )
    if existente.espacio_id is not None:
        await invalidar_cache_por_espacio(existente.espacio_id)
    else:
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
    _: Usuario = Depends(require_role("Admin_Sistema")),
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
    _: Usuario = Depends(require_role("Admin_Sistema")),
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
    _: Usuario = Depends(require_role("Admin_Sistema")),
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
    _: Usuario = Depends(require_role("Admin_Sistema")),
) -> dict:
    servicio = CalendarService()
    eliminado = await servicio.eliminar_evento_calendario(db, fecha)
    if not eliminado:
        raise HTTPException(status_code=404, detail="Evento de calendario no encontrado")
    return {"mensaje": "Evento eliminado exitosamente"}


# ---------------------------------------------------------------------------
# Endpoints de Gestión Multi-Proveedor IA y Servidor SMTP (Solo Admin_Sistema)
# ---------------------------------------------------------------------------
def _serializar_credencial_ia(cred) -> CredencialIAResponse:
    return CredencialIAResponse(
        id=cred.id,
        nombre=cred.nombre,
        provider_id=cred.provider_id,
        modelo=cred.modelo,
        base_url=cred.base_url,
        has_api_key=bool(cred.encrypted_api_key),
        key_hint=cred.key_hint or "",
        es_activa=bool(cred.es_activa),
        ultimo_test_ok=cred.ultimo_test_ok,
        ultimo_test_en=marcar_utc(cred.ultimo_test_en),
        created_at=marcar_utc(cred.created_at),
        updated_at=marcar_utc(cred.updated_at),
    )


def _serializar_smtp(cfg) -> ConfiguracionSMTPResponse:
    return ConfiguracionSMTPResponse(
        id=cfg.id,
        nombre=cfg.nombre,
        host=cfg.host,
        port=cfg.port,
        use_tls=bool(cfg.use_tls),
        use_ssl=bool(cfg.use_ssl),
        username=cfg.username,
        from_email=cfg.from_email,
        from_name=cfg.from_name,
        has_password=bool(cfg.encrypted_password),
        password_hint=cfg.password_hint or "",
        es_activa=bool(cfg.es_activa),
        ultimo_test_ok=cfg.ultimo_test_ok,
        ultimo_test_en=marcar_utc(cfg.ultimo_test_en),
        created_at=marcar_utc(cfg.created_at),
        updated_at=marcar_utc(cfg.updated_at),
    )


@router.get("/llm/catalog", response_model=CatalogoProveedoresIAResponse, summary="Listar catálogo de proveedores IA soportados")
async def listar_catalogo_ia(
    _: Usuario = Depends(require_superadmin),
) -> CatalogoProveedoresIAResponse:
    from app.services.llm_client import obtener_catalogo_proveedores
    return CatalogoProveedoresIAResponse(
        proveedores=[ProveedorCatalogoItem(**p) for p in obtener_catalogo_proveedores()]
    )


@router.get("/llm/credentials", response_model=CredencialesIAListResponse, summary="Listar credenciales IA guardadas (enmascaradas)")
async def listar_credenciales_ia_endpoint(
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_superadmin),
) -> CredencialesIAListResponse:
    items = await listar_credenciales_ia(db)
    config_esp = await get_configuracion_espacio(db, 1)
    fallback_env = bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY.strip())

    activa = next((c for c in items if c.es_activa), None)
    if activa:
        origen = "bd"
        resumen = f"{activa.nombre} ({activa.provider_id} / {activa.modelo})"
    elif fallback_env:
        origen = "env"
        resumen = f"Respaldo .env (gemini / {settings.MODELO_GEMINI_POR_DEFECTO})"
    else:
        origen = "ninguno"
        resumen = None

    return CredencialesIAListResponse(
        items=[_serializar_credencial_ia(c) for c in items],
        ia_asistente_activo=bool(config_esp.ia_asistente_activo),
        fallback_env_disponible=fallback_env,
        origen_activo=origen,
        proveedor_activo_resumen=resumen,
    )


@router.post("/llm/credentials", response_model=CredencialIAResponse, status_code=status.HTTP_201_CREATED, summary="Registrar nueva credencial de proveedor IA")
async def crear_credencial_ia_endpoint(
    datos: CredencialIACreate,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_superadmin),
) -> CredencialIAResponse:
    try:
        cred = await crear_credencial_ia(
            db=db,
            nombre=datos.nombre,
            provider_id=datos.provider_id,
            modelo=datos.modelo,
            base_url=datos.base_url,
            api_key=datos.api_key,
            activar=datos.activar,
            usuario_id=usuario.id,
        )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

    logger.info("Credencial IA '%s' (%s) creada por %s", cred.nombre, cred.provider_id, usuario.email)
    return _serializar_credencial_ia(cred)


@router.put("/llm/credentials/{cred_id}", response_model=CredencialIAResponse, summary="Actualizar credencial de proveedor IA")
async def actualizar_credencial_ia_endpoint(
    cred_id: int,
    datos: CredencialIAUpdate,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_superadmin),
) -> CredencialIAResponse:
    cred = await obtener_credencial_ia(db, cred_id)
    if not cred:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credencial de IA no encontrada")
    try:
        actualizada = await actualizar_credencial_ia(
            db=db,
            cred=cred,
            nombre=datos.nombre,
            provider_id=datos.provider_id,
            modelo=datos.modelo,
            base_url=datos.base_url,
            api_key=datos.api_key,
        )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

    logger.info("Credencial IA id=%s ('%s') actualizada por %s", cred_id, actualizada.nombre, usuario.email)
    return _serializar_credencial_ia(actualizada)


@router.post("/llm/credentials/{cred_id}/activate", response_model=CredencialIAResponse, summary="Activar credencial de proveedor IA")
async def activar_credencial_ia_endpoint(
    cred_id: int,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_superadmin),
) -> CredencialIAResponse:
    cred = await obtener_credencial_ia(db, cred_id)
    if not cred:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credencial de IA no encontrada")
    activada = await activar_credencial_ia(db, cred)
    logger.info("Credencial IA id=%s ('%s') activada por %s", cred_id, activada.nombre, usuario.email)
    return _serializar_credencial_ia(activada)


@router.post("/llm/credentials/{cred_id}/test", response_model=TestConexionIAResponse, summary="Probar conectividad real de una credencial IA")
async def probar_credencial_ia_endpoint(
    cred_id: int,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_superadmin),
) -> TestConexionIAResponse:
    cred = await obtener_credencial_ia(db, cred_id)
    if not cred:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credencial de IA no encontrada")
    res = await probar_credencial_ia_guardada(db, cred)
    logger.info("Prueba de conexión IA id=%s ('%s') por %s: ok=%s", cred_id, cred.nombre, usuario.email, res["ok"])
    return TestConexionIAResponse(**res)


@router.delete("/llm/credentials/{cred_id}", summary="Eliminar definitivamente una credencial de proveedor IA")
async def eliminar_credencial_ia_endpoint(
    cred_id: int,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_superadmin),
) -> dict:
    cred = await obtener_credencial_ia(db, cred_id)
    if not cred:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credencial de IA no encontrada")
    nombre = cred.nombre
    await eliminar_credencial_ia(db, cred)
    logger.info("Credencial IA id=%s ('%s') eliminada definitivamente por %s", cred_id, nombre, usuario.email)
    return {"mensaje": f"Credencial '{nombre}' eliminada definitivamente."}


@router.get("/smtp", response_model=ConfiguracionSMTPListResponse, summary="Listar perfiles de servidor SMTP configurados")
async def listar_smtp_endpoint(
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_superadmin),
) -> ConfiguracionSMTPListResponse:
    items = await listar_configuraciones_smtp(db)
    fallback_env = bool(settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD)
    activa = next((c for c in items if c.es_activa), None)
    origen = "bd" if activa else ("env" if fallback_env else "ninguno")

    return ConfiguracionSMTPListResponse(
        items=[_serializar_smtp(c) for c in items],
        fallback_env_disponible=fallback_env,
        fallback_env_host=settings.SMTP_HOST or None,
        fallback_env_user=settings.SMTP_USER or None,
        origen_activo=origen,
    )


@router.post("/smtp", response_model=ConfiguracionSMTPResponse, status_code=status.HTTP_201_CREATED, summary="Registrar nuevo perfil SMTP")
async def crear_smtp_endpoint(
    datos: ConfiguracionSMTPCreate,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_superadmin),
) -> ConfiguracionSMTPResponse:
    try:
        cfg = await crear_configuracion_smtp(
            db=db,
            nombre=datos.nombre,
            host=datos.host,
            port=datos.port,
            use_tls=datos.use_tls,
            use_ssl=datos.use_ssl,
            username=datos.username,
            from_email=str(datos.from_email),
            from_name=datos.from_name,
            password=datos.password,
            activar=datos.activar,
            usuario_id=usuario.id,
        )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

    logger.info("Perfil SMTP '%s' (%s:%s) creado por %s", cfg.nombre, cfg.host, cfg.port, usuario.email)
    return _serializar_smtp(cfg)


@router.put("/smtp/{smtp_id}", response_model=ConfiguracionSMTPResponse, summary="Actualizar perfil SMTP")
async def actualizar_smtp_endpoint(
    smtp_id: int,
    datos: ConfiguracionSMTPUpdate,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_superadmin),
) -> ConfiguracionSMTPResponse:
    cfg = await obtener_configuracion_smtp(db, smtp_id)
    if not cfg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Configuración SMTP no encontrada")
    try:
        actualizado = await actualizar_configuracion_smtp(
            db=db,
            cfg=cfg,
            nombre=datos.nombre,
            host=datos.host,
            port=datos.port,
            use_tls=datos.use_tls,
            use_ssl=datos.use_ssl,
            username=datos.username,
            from_email=str(datos.from_email) if datos.from_email is not None else None,
            from_name=datos.from_name,
            password=datos.password,
        )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

    logger.info("Perfil SMTP id=%s ('%s') actualizado por %s", smtp_id, actualizado.nombre, usuario.email)
    return _serializar_smtp(actualizado)


@router.post("/smtp/{smtp_id}/activate", response_model=ConfiguracionSMTPResponse, summary="Activar perfil SMTP en caliente")
async def activar_smtp_endpoint(
    smtp_id: int,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_superadmin),
) -> ConfiguracionSMTPResponse:
    cfg = await obtener_configuracion_smtp(db, smtp_id)
    if not cfg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Configuración SMTP no encontrada")
    activado = await activar_configuracion_smtp(db, cfg)
    logger.info("Perfil SMTP id=%s ('%s') activado por %s", smtp_id, activado.nombre, usuario.email)
    return _serializar_smtp(activado)


@router.post("/smtp/{smtp_id}/test", response_model=TestConexionSMTPResponse, summary="Enviar correo de prueba desde un perfil SMTP")
async def probar_smtp_endpoint(
    smtp_id: int,
    req: SMTPTestRequest,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_superadmin),
) -> TestConexionSMTPResponse:
    cfg = await obtener_configuracion_smtp(db, smtp_id)
    if not cfg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Configuración SMTP no encontrada")
    destino = str(req.destinatario or usuario.email)
    ok, msg = await probar_configuracion_smtp_guardada(db, cfg, destino)
    logger.info("Prueba SMTP id=%s ('%s') hacia %s por %s: ok=%s", smtp_id, cfg.nombre, destino, usuario.email, ok)
    return TestConexionSMTPResponse(ok=ok, mensaje=msg, destinatario=destino)


@router.delete("/smtp/{smtp_id}", summary="Eliminar definitivamente un perfil SMTP")
async def eliminar_smtp_endpoint(
    smtp_id: int,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_superadmin),
) -> dict:
    cfg = await obtener_configuracion_smtp(db, smtp_id)
    if not cfg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Configuración SMTP no encontrada")
    nombre = cfg.nombre
    await eliminar_configuracion_smtp(db, cfg)
    logger.info("Perfil SMTP id=%s ('%s') eliminado definitivamente por %s", smtp_id, nombre, usuario.email)
    return {"mensaje": f"Perfil SMTP '{nombre}' eliminado definitivamente."}







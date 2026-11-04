from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.security import require_role, require_roles, require_permission
from app.core.database import get_db
from app.core.config import settings
from app.domain.auth_models import Usuario
from app.domain.chat_audit_models import ChatAuditLog
from app.domain.ejecucion_tarea_models import EjecucionTarea
from app.schemas.tarea_schemas import (
    EjecucionTareaResponse,
    TareaCatalogoItem,
    ResumenTareasResponse,
)
from app.core.planificador import (
    CATALOGO_TAREAS,
    ejecutar_tarea,
    ReentranciaError,
    TareaNoEncontradaError,
    es_planificador_activo,
    obtener_planificador,
)

router = APIRouter()


class ChatAuditItem(BaseModel):
    id: int
    usuario_id: Optional[int] = None
    usuario_email: Optional[str] = None
    usuario_nombre: Optional[str] = None
    prompt_text: str
    dataset_tipo: Optional[str] = None
    modelo_utilizado: Optional[str] = None
    status: str
    response_time_ms: Optional[float] = None
    timestamp: datetime


class HourlyStat(BaseModel):
    hora: str
    cantidad: int


class ChatAuditStats(BaseModel):
    consultas_hoy: int
    consultas_exitosas_hoy: int
    consultas_error_hoy: int
    promedio_tiempo_hoy_ms: float
    consultas_por_dataset_hoy: Dict[str, int]
    consultas_por_hora_hoy: List[HourlyStat]


class ChatAuditResponse(BaseModel):
    items: List[ChatAuditItem]
    total: int
    page: int
    page_size: int
    total_pages: int
    stats: ChatAuditStats


@router.get("/chat-audit", response_model=ChatAuditResponse)
async def get_chat_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=100),
    dataset_tipo: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: Usuario = Depends(require_role("SuperAdmin")),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(ChatAuditLog)
        .options(joinedload(ChatAuditLog.usuario))
        .order_by(ChatAuditLog.timestamp.desc())
    )
    count_stmt = select(func.count(ChatAuditLog.id))

    if dataset_tipo:
        stmt = stmt.where(ChatAuditLog.dataset_tipo == dataset_tipo)
        count_stmt = count_stmt.where(ChatAuditLog.dataset_tipo == dataset_tipo)
    if status_filter:
        stmt = stmt.where(ChatAuditLog.status == status_filter)
        count_stmt = count_stmt.where(ChatAuditLog.status == status_filter)
    if search:
        search_pattern = f"%{search}%"
        stmt = stmt.where(ChatAuditLog.prompt_text.ilike(search_pattern))
        count_stmt = count_stmt.where(ChatAuditLog.prompt_text.ilike(search_pattern))

    total = (await db.execute(count_stmt)).scalar() or 0
    total_pages = max(1, (total + page_size - 1) // page_size)

    paginated_stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(paginated_stmt)).scalars().all()

    items = [
        ChatAuditItem(
            id=r.id,
            usuario_id=r.usuario_id,
            usuario_email=r.usuario.email if r.usuario else None,
            usuario_nombre=r.usuario.nombre_completo if r.usuario else None,
            prompt_text=r.prompt_text,
            dataset_tipo=r.dataset_tipo,
            modelo_utilizado=r.modelo_utilizado,
            status=r.status,
            response_time_ms=r.response_time_ms,
            timestamp=r.timestamp,
        )
        for r in rows
    ]

    now_utc = datetime.now(timezone.utc)
    today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

    today_stmt = select(ChatAuditLog).where(ChatAuditLog.timestamp >= today_start)
    today_rows = (await db.execute(today_stmt)).scalars().all()

    consultas_hoy = len(today_rows)
    consultas_exitosas_hoy = sum(1 for r in today_rows if r.status == "éxito")
    consultas_error_hoy = sum(1 for r in today_rows if r.status == "error")

    times = [r.response_time_ms for r in today_rows if r.response_time_ms is not None]
    promedio_tiempo_hoy_ms = round(sum(times) / len(times), 2) if times else 0.0

    datasets_count: Dict[str, int] = {}
    for r in today_rows:
        ds = r.dataset_tipo or "general"
        datasets_count[ds] = datasets_count.get(ds, 0) + 1

    hours_map = {f"{h:02d}:00": 0 for h in range(8, 22)}
    for r in today_rows:
        h_str = f"{r.timestamp.hour:02d}:00"
        if h_str in hours_map:
            hours_map[h_str] += 1
        else:
            hours_map[h_str] = 1

    consultas_por_hora_hoy = [
        HourlyStat(hora=h, cantidad=c) for h, c in sorted(hours_map.items())
    ]

    return ChatAuditResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        stats=ChatAuditStats(
            consultas_hoy=consultas_hoy,
            consultas_exitosas_hoy=consultas_exitosas_hoy,
            consultas_error_hoy=consultas_error_hoy,
            promedio_tiempo_hoy_ms=promedio_tiempo_hoy_ms,
            consultas_por_dataset_hoy=datasets_count,
            consultas_por_hora_hoy=consultas_por_hora_hoy,
        ),
    )


class DownloadAuditItem(BaseModel):
    id: int
    usuario_id: Optional[int] = None
    usuario_email: Optional[str] = None
    usuario_nombre: Optional[str] = None
    modulo: str
    formato: str
    filtro_fecha_inicio: Optional[str] = None
    filtro_fecha_fin: Optional[str] = None
    filtro_detalle: Optional[str] = None
    total_registros: int
    ip_origen: Optional[str] = None
    timestamp: Optional[str] = None


class DownloadAuditStats(BaseModel):
    total_descargas: int
    descargas_hoy: int
    descargas_csv: int
    descargas_pdf: int
    descargas_por_modulo: Dict[str, int]


class DownloadAuditResponse(BaseModel):
    items: List[DownloadAuditItem]
    total: int
    page: int
    page_size: int
    total_pages: int
    stats: DownloadAuditStats


class RecordDownloadRequest(BaseModel):
    modulo: str
    formato: str
    filtro_fecha_inicio: Optional[str] = None
    filtro_fecha_fin: Optional[str] = None
    filtro_detalle: Optional[str] = None
    total_registros: int = 0


@router.get("/download-audit", response_model=DownloadAuditResponse, summary="Historial de descargas para el Administrador")
async def get_download_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=100),
    modulo: Optional[str] = Query(None),
    formato: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: Usuario = Depends(require_role("SuperAdmin")),
):
    from app.services.audit_service import get_download_audit_history
    return await get_download_audit_history(
        page=page,
        page_size=page_size,
        modulo=modulo,
        formato=formato,
        search=search,
    )


@router.post("/record-download", summary="Registrar evento de descarga de datos")
async def record_download_event(
    body: RecordDownloadRequest,
    current_user: Optional[Usuario] = Depends(require_role("SuperAdmin")),
):
    from app.services.audit_service import record_download_audit
    await record_download_audit(
        usuario_id=current_user.id if current_user else None,
        modulo=body.modulo,
        formato=body.formato,
        filtro_fecha_inicio=body.filtro_fecha_inicio,
        filtro_fecha_fin=body.filtro_fecha_fin,
        filtro_detalle=body.filtro_detalle,
        total_registros=body.total_registros,
    )
    return {"status": "ok", "message": "Descarga auditada correctamente"}


def _serializar_ejecucion(e: EjecucionTarea) -> EjecucionTareaResponse:
    duracion = (e.fin_en - e.inicio_en).total_seconds() if e.fin_en and e.inicio_en else None
    return EjecucionTareaResponse(
        id=str(e.id),
        tarea=e.tarea,
        disparador=e.disparador,
        estado=e.estado,
        inicio_en=e.inicio_en,
        fin_en=e.fin_en,
        latido_en=e.latido_en,
        usuario_id=e.usuario_id,
        resumen_json=e.resumen_json,
        error=e.error,
        memoria_pico_mb=e.memoria_pico_mb,
        duracion_segundos=duracion,
    )


@router.get("/tareas", response_model=ResumenTareasResponse, summary="Listar catálogo y estado de tareas programadas")
@router.get("/tareas/resumen", response_model=ResumenTareasResponse, include_in_schema=False)
async def listar_tareas_admin(
    current_user: Usuario = Depends(require_role("Admin_Sistema")),
    db: AsyncSession = Depends(get_db),
):
    from app.core.planificador import _ahora_chile_naive
    ahora = _ahora_chile_naive()
    limite_latido = ahora - timedelta(minutes=15)

    catalogo_items: List[TareaCatalogoItem] = []
    for nombre, info in CATALOGO_TAREAS.items():
        stmt_ult = (
            select(EjecucionTarea)
            .where(EjecucionTarea.tarea == nombre)
            .order_by(desc(EjecucionTarea.inicio_en))
            .limit(1)
        )
        ult_ej = (await db.execute(stmt_ult)).scalars().first()

        stmt_activa = (
            select(EjecucionTarea)
            .where(
                EjecucionTarea.tarea == nombre,
                EjecucionTarea.estado == "en_curso",
                EjecucionTarea.latido_en >= limite_latido,
            )
            .limit(1)
        )
        en_curso = (await db.execute(stmt_activa)).scalars().first() is not None

        proxima = None
        if info.get("cron_trigger") is not None:
            try:
                from app.core.planificador import ZONA_HORARIA_CHILE, calcular_proxima_ejecucion_habil
                ahora_cl = datetime.now(ZONA_HORARIA_CHILE)
                proxima = await calcular_proxima_ejecucion_habil(db, nombre, ahora_cl)
            except Exception:
                proxima = None
        if proxima is None:
            sched = obtener_planificador()
            if sched and sched.running:
                job = sched.get_job(nombre)
                if job and job.next_run_time:
                    proxima = job.next_run_time

        catalogo_items.append(
            TareaCatalogoItem(
                nombre=nombre,
                descripcion=info["descripcion"],
                cron_expresion=info["cron_str"],
                en_curso=en_curso,
                proxima_ejecucion=proxima,
                ultima_ejecucion=_serializar_ejecucion(ult_ej) if ult_ej else None,
            )
        )

    stmt_hist = (
        select(EjecucionTarea)
        .order_by(desc(EjecucionTarea.inicio_en))
        .limit(50)
    )
    historial = (await db.execute(stmt_hist)).scalars().all()

    return ResumenTareasResponse(
        catalogo=catalogo_items,
        ultimas_ejecuciones=[_serializar_ejecucion(h) for h in historial],
        planificador_activo=es_planificador_activo(),
    )


@router.post("/tareas/{nombre}/ejecutar", response_model=EjecucionTareaResponse, summary="Ejecutar manualmente una tarea del planificador")
async def ejecutar_tarea_admin(
    nombre: str,
    current_user: Usuario = Depends(require_role("Admin_Sistema")),
):
    try:
        ejecucion = await ejecutar_tarea(
            nombre=nombre,
            disparador="manual",
            usuario_id=current_user.id,
        )
        return _serializar_ejecucion(ejecucion)
    except TareaNoEncontradaError as e_nf:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e_nf),
        )
    except ReentranciaError as e_re:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e_re),
        )


@router.post(
    "/modelos/actualizar",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Actualizar y reentrenar modelos predictivos (Campeón vs. Retador)",
)
async def actualizar_modelos_admin(
    current_user: Usuario = Depends(require_role("Admin_Sistema")),
):
    """
    Despacha el proceso de reentrenamiento de modelos (Prophet, GBR, KMeans)
    mediante el planificador interno de tareas.
    Exclusivo para rol Admin_Sistema. Retorna HTTP 202 Accepted.
    """
    try:
        ejecucion = await ejecutar_tarea(
            nombre="reentrenar_modelos_ml",
            disparador="manual",
            usuario_id=current_user.id,
        )
        return {
            "mensaje": "Reentrenamiento de modelos iniciado en segundo plano",
            "tarea_id": str(ejecucion.id),
            "estado": ejecucion.estado,
        }
    except ReentranciaError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(err),
        )


@router.get(
    "/modelos/estado",
    summary="Reporte de estado de modelos predictivos (versiones activas, WAPE, MAE y estado)",
)
async def obtener_estado_modelos_admin(
    current_user: Usuario = Depends(require_role("Admin_Sistema")),
):
    """
    Retorna el estado de los modelos de Machine Learning en producción, reportando
    versiones activas, WAPE, MAE, fecha de modificación y estado de calibración.
    Exclusivo para rol Admin_Sistema.
    """
    from app.ml.orquestador_entrenamiento import obtener_estado_general_modelos
    return obtener_estado_general_modelos()


@router.get(
    "/calendario/estado",
    summary="Consultar estado de sincronización del calendario académico anual",
)
async def obtener_estado_calendario_admin(
    anio: Optional[int] = Query(None, description="Año calendario objetivo a consultar"),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role("Admin_Sistema")),
):
    """
    Retorna el estado de sincronización y reintentos del calendario académico oficial.
    Exclusivo para rol Admin_Sistema.
    """
    from app.services.servicio_calendario_anual import obtener_estado_calendario_anual, listar_estados_calendario
    if anio:
        registro = await obtener_estado_calendario_anual(db, anio)
        if not registro:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No existe registro de sincronización para el año {anio}",
            )
        return {
            "anio_objetivo": registro.anio_objetivo,
            "estado": registro.estado,
            "intentos": registro.intentos,
            "ultimo_intento_en": registro.ultimo_intento_en.isoformat() if registro.ultimo_intento_en else None,
            "proximo_intento_en": registro.proximo_intento_en.isoformat() if registro.proximo_intento_en else None,
            "ultimo_error": registro.ultimo_error,
            "eventos_encontrados": registro.eventos_encontrados,
        }
    return await listar_estados_calendario(db)


@router.post(
    "/calendario/sincronizar",
    summary="Disparar sincronización y verificación de calendario académico",
)
async def sincronizar_calendario_admin(
    anio: Optional[int] = Query(None, description="Año calendario a sincronizar"),
    forzar: bool = Query(False, description="Forzar sincronización incluso si ya está marcado como completo"),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role("Admin_Sistema")),
):
    """
    Ejecuta la sincronización del calendario académico oficial contra la web de la UCT.
    Exclusivo para rol Admin_Sistema.
    """
    from app.services.servicio_calendario_anual import sincronizar_calendario_anual
    resultado = await sincronizar_calendario_anual(db, anio_objetivo=anio, forzar=forzar)
    return resultado


class SolicitudPurgaDatos(BaseModel):
    alcance: str  # "asistencia", "vehicular", "institucional_estudiantes", "ingestas", "todo"
    espacio_id: Optional[int] = None
    confirmacion: str


@router.post(
    "/purgar-datos",
    summary="Purga administrativa y controlada de datos de recintos o maestros institucionales",
)
async def purgar_datos_admin(
    solicitud: SolicitudPurgaDatos,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role("Admin_Sistema", "SuperAdmin")),
):
    """
    Permite a los administradores del sistema purgar datos de manera controlada y segura,
    reseteando aforos o limpiando tablas institucionales para una recarga limpia.
    Requiere obligatoriamente confirmacion == 'CONFIRMAR_PURGA'.
    """
    from sqlalchemy import delete, text
    from app.domain.models import EventoAsistencia, EventoVehicular, RollupHistoricoDiario, Espacio, IngestionJob, DimEstudianteCarrera
    from app.domain.modelos_institucionales_uct import (
        InstitucionalCampus,
        InstitucionalEdificios,
        InstitucionalTipoInmueble,
        InstitucionalAmbiente,
        InstitucionalTipoCarrera,
        InstitucionalCarreraPrograma,
        InstitucionalCarreraCampus,
        InstitucionalSituacionAlumno,
        InstitucionalViasIngreso,
        InstitucionalEstudiante,
        InstitucionalEstudianteCarrera,
    )
    from app.services.ingestion_service import invalidar_caches_recinto_y_actualizar_predicciones

    if solicitud.confirmacion.strip() != "CONFIRMAR_PURGA":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmación inválida. Debe escribir exactamente 'CONFIRMAR_PURGA' para autorizar el vaciado de datos.",
        )

    alcance = solicitud.alcance.strip().lower()
    espacio_id = solicitud.espacio_id
    registros_eliminados = {}

    if alcance in ("asistencia", "todo"):
        stmt = delete(EventoAsistencia)
        stmt_rollup = delete(RollupHistoricoDiario)
        if espacio_id and alcance != "todo":
            stmt = stmt.where(EventoAsistencia.espacio_id == espacio_id)
            stmt_rollup = stmt_rollup.where(RollupHistoricoDiario.espacio_id == espacio_id)
        elif alcance != "todo":
            stmt_rollup = stmt_rollup.where(RollupHistoricoDiario.espacio_id == 1)
        
        res = await db.execute(stmt)
        await db.execute(stmt_rollup)
        registros_eliminados["eventos_asistencia"] = res.rowcount
        await invalidar_caches_recinto_y_actualizar_predicciones(espacio_id or 1)

    if alcance in ("vehicular", "todo"):
        stmt_veh = delete(EventoVehicular)
        if espacio_id and alcance != "todo":
            stmt_veh = stmt_veh.where(EventoVehicular.espacio_id == espacio_id)
            await db.execute(delete(RollupHistoricoDiario).where(RollupHistoricoDiario.espacio_id == espacio_id))
        elif alcance != "todo":
            await db.execute(delete(RollupHistoricoDiario).where(RollupHistoricoDiario.espacio_id == 2))
        
        res_v = await db.execute(stmt_veh)
        registros_eliminados["eventos_vehiculares"] = res_v.rowcount
        await invalidar_caches_recinto_y_actualizar_predicciones(espacio_id or 2)

    if alcance in ("institucional_estudiantes", "todo"):
        # Borrado en orden inverso de dependencias de claves foráneas
        r_dim = await db.execute(delete(DimEstudianteCarrera))
        r_uec = await db.execute(delete(InstitucionalEstudianteCarrera))
        r_ue = await db.execute(delete(InstitucionalEstudiante))
        await db.execute(delete(InstitucionalCarreraCampus))
        r_ucp = await db.execute(delete(InstitucionalCarreraPrograma))
        await db.execute(delete(InstitucionalTipoCarrera))
        await db.execute(delete(InstitucionalSituacionAlumno))
        await db.execute(delete(InstitucionalViasIngreso))
        await db.execute(delete(InstitucionalAmbiente))
        await db.execute(delete(InstitucionalEdificios))
        await db.execute(delete(InstitucionalTipoInmueble))
        r_uca = await db.execute(delete(InstitucionalCampus))

        registros_eliminados["dim_estudiante_carrera"] = r_dim.rowcount
        registros_eliminados["uct_estudiante_carrera"] = r_uec.rowcount
        registros_eliminados["uct_estudiante"] = r_ue.rowcount
        registros_eliminados["uct_carrera_programa"] = r_ucp.rowcount
        registros_eliminados["uct_campus"] = r_uca.rowcount

    if alcance in ("ingestas", "todo"):
        stmt_ij = delete(IngestionJob)
        if espacio_id and alcance != "todo":
            stmt_ij = stmt_ij.where(IngestionJob.espacio_id == espacio_id)
        res_ij = await db.execute(stmt_ij)
        registros_eliminados["ingestion_jobs"] = res_ij.rowcount

    if not registros_eliminados and alcance not in ("asistencia", "vehicular", "institucional_estudiantes", "ingestas", "todo"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Alcance de purga '{alcance}' no reconocido. Opciones válidas: asistencia, vehicular, institucional_estudiantes, ingestas, todo.",
        )

    await db.commit()
    return {
        "status": "ok",
        "mensaje": f"Purga de datos con alcance '{alcance}' completada exitosamente.",
        "alcance": alcance,
        "espacio_id": espacio_id,
        "registros_eliminados": registros_eliminados,
    }


# =============================================================================
# ESQUEMAS Y ENDPOINTS DE INTEGRACIÓN SMART CAMPUS Y SECTORES DE ESTACIONAMIENTO
# =============================================================================

class ActualizarCapacidadSectorRequest(BaseModel):
    capacidad_max: int = Field(..., gt=0, description="Capacidad máxima de vehículos del sector (mayor a 0)")
    activo: Optional[bool] = Field(None, description="Estado operativo del sector")


class SectorEstacionamientoResponse(BaseModel):
    id: int
    codigo: str
    nombre: str
    capacidad_max: int
    camaras_entrada: Optional[str] = None
    camaras_salida: Optional[str] = None
    activo: bool

    class Config:
        from_attributes = True


class SmartCampusSincronizarRequest(BaseModel):
    fuente: str = Field("todas", description="'todas', 'torniquetes' o 'estacionamientos'")
    tipo_pipeline: str = Field("en_vivo", description="'en_vivo' (aforo actual) o 'cierre_diario' (día D-1)")
    desde: Optional[str] = Field(None, description="Fecha de inicio (YYYY-MM-DD)")
    hasta: Optional[str] = Field(None, description="Fecha de fin (YYYY-MM-DD)")


@router.get(
    "/smart-campus/estado",
    summary="Resumen de sincronizaciones y estado de salud de la API Smart Campus",
)
async def obtener_estado_smart_campus_admin(
    current_user: Usuario = Depends(require_role("SuperAdmin", "Admin_Sistema")),
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna el historial reciente de sincronizaciones incrementales de torniquetes y
    estacionamientos desde la API institucional Smart Campus UCT.
    """
    from app.services.servicio_smart_campus import obtener_resumen_estado_smart_campus
    return await obtener_resumen_estado_smart_campus(db)


@router.post(
    "/smart-campus/sincronizar",
    summary="Disparar sincronización manual de la API Smart Campus UCT",
)
async def sincronizar_smart_campus_admin(
    payload: Optional[SmartCampusSincronizarRequest] = None,
    current_user: Usuario = Depends(require_role("SuperAdmin", "Admin_Sistema")),
    db: AsyncSession = Depends(get_db),
):
    """
    Ejecuta bajo demanda la ingesta de la API Smart Campus.
    Permite seleccionar entre Pipeline 1 (Aforo en Vivo del día) o Pipeline 2 (Consolidación de Día Cerrado).
    """
    from app.services.servicio_smart_campus import (
        sincronizar_aforo_vivo_horario,
        consolidar_dia_cerrado,
    )
    from app.core.planificador import _ahora_chile_naive
    import json

    req = payload or SmartCampusSincronizarRequest()
    inicio_sinc = _ahora_chile_naive()
    nombre_tarea_asociada = (
        "consolidar_smart_campus_nocturno" if req.tipo_pipeline == "cierre_diario" else "sincronizar_smart_campus_en_vivo"
    )

    if req.tipo_pipeline == "cierre_diario":
        fecha_obj = None
        if req.desde:
            try:
                fecha_obj = datetime.strptime(req.desde[:10], "%Y-%m-%d").date()
            except Exception:
                pass
        resultado = await consolidar_dia_cerrado(db, fecha_objetivo=fecha_obj)
    else:
        desde_dt = None
        hasta_dt = None
        if req.desde:
            try:
                desde_dt = datetime.strptime(req.desde[:10], "%Y-%m-%d").date()
            except Exception:
                pass
        if req.hasta:
            try:
                hasta_dt = datetime.strptime(req.hasta[:10], "%Y-%m-%d").date()
            except Exception:
                pass
        resultado = await sincronizar_aforo_vivo_horario(db, desde_manual=desde_dt, hasta_manual=hasta_dt)

    fin_sinc = _ahora_chile_naive()
    errores_sinc = resultado.get("errores") or []
    t_ins = resultado.get("torniquetes", {}).get("insertados", 0)
    e_ins = resultado.get("estacionamientos", {}).get("insertados", 0)
    t_lei = resultado.get("torniquetes", {}).get("leidos", 0)
    e_lei = resultado.get("estacionamientos", {}).get("leidos", 0)
    hubo_fallo_total = bool(errores_sinc and t_lei == 0 and e_lei == 0)

    try:
        reg_ejec = EjecucionTarea(
            tarea=nombre_tarea_asociada,
            disparador="manual",
            estado="fallido" if hubo_fallo_total else "exitoso",
            inicio_en=inicio_sinc,
            fin_en=fin_sinc,
            latido_en=fin_sinc,
            usuario_id=current_user.id if current_user else None,
            resumen_json=json.dumps(resultado, ensure_ascii=False),
            error="; ".join(errores_sinc) if hubo_fallo_total else None,
        )
        db.add(reg_ejec)
        await db.commit()
    except Exception:
        await db.rollback()

    if hubo_fallo_total:
        mensaje_resp = f"Sincronización finalizada con observaciones: {'; '.join(errores_sinc)}"
    else:
        mensaje_resp = (
            f"Sincronización completada: +{t_ins} registros en Biblioteca "
            f"({resultado.get('rango_torniquetes', '')}) y +{e_ins} en Estacionamientos "
            f"({resultado.get('rango_estacionamientos', '')})."
        )

    return {
        "status": "error" if hubo_fallo_total else "ok",
        "mensaje": mensaje_resp,
        "resultado": resultado,
    }


@router.get(
    "/estacionamientos/sectores",
    response_model=List[SectorEstacionamientoResponse],
    summary="Listar los 3 sectores de estacionamiento catalogados y sus capacidades",
)
async def listar_sectores_estacionamiento_admin(
    current_user: Usuario = Depends(require_role("SuperAdmin", "Admin_Sistema", "Director_Recinto")),
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna los sectores vehiculares (CSF11, CSF21, CHS01) y sus capacidades máximas.
    """
    from app.services.servicio_smart_campus import listar_sectores_estacionamiento
    return await listar_sectores_estacionamiento(db)


@router.put(
    "/estacionamientos/sectores/{codigo}",
    response_model=SectorEstacionamientoResponse,
    summary="Actualizar la capacidad máxima de un sector de estacionamiento",
)
async def actualizar_capacidad_sector_admin(
    codigo: str,
    payload: ActualizarCapacidadSectorRequest,
    current_user: Usuario = Depends(require_role("SuperAdmin", "Admin_Sistema")),
    db: AsyncSession = Depends(get_db),
):
    """
    Permite a los administradores ajustar dinámicamente la capacidad vehicular de CSF11, CSF21 o CHS01.
    """
    from app.services.servicio_smart_campus import actualizar_capacidad_sector
    try:
        return await actualizar_capacidad_sector(
            db,
            codigo=codigo,
            nueva_capacidad=payload.capacidad_max,
            activo=payload.activo,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# =============================================================================
# ENDPOINTS DE CONTROL Y PURGA DE CACHÉ EN MEMORIA
# =============================================================================

@router.post(
    "/cache/limpiar",
    summary="Limpiar y purgar la totalidad de la memoria de caché en el sistema",
)
async def limpiar_cache_admin(
    current_user: Usuario = Depends(require_role("SuperAdmin", "Admin_Sistema")),
):
    """
    Purga de forma inmediata todas las particiones de la caché en memoria (aforo vivo, KPIs e históricos).
    """
    from app.core.cache import limpiar_toda_la_cache, obtener_cache
    conteo = await limpiar_toda_la_cache()
    stats = obtener_cache().stats()
    return {
        "status": "ok",
        "mensaje": f"Caché en memoria purgada exitosamente. {conteo} entradas eliminadas.",
        "entradas_eliminadas": conteo,
        "estadisticas_actuales": stats,
    }


@router.get(
    "/cache/stats",
    summary="Estadísticas de ocupación y particiones de la caché en memoria",
)
async def obtener_stats_cache_admin(
    current_user: Usuario = Depends(require_role("SuperAdmin", "Admin_Sistema")),
):
    """
    Retorna la ocupación en tiempo real de las particiones de caché en memoria.
    """
    from app.core.cache import obtener_cache
    return obtener_cache().stats()


# =============================================================================
# ENDPOINTS DE CONFIGURACIÓN GLOBAL E INTERRUPTOR MAESTRO DE IA
# =============================================================================

@router.get(
    "/config",
    summary="Obtener configuración global de IA y sistema",
)
async def obtener_config_global_admin(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role("Admin_Sistema", "SuperAdmin")),
):
    from app.core.security_cipher import mask_api_key
    from app.services.config_service import get_configuracion_espacio
    config = await get_configuracion_espacio(db, espacio_id=1)
    if not config:
        return {
            "id": 1,
            "ia_asistente_activo": True,
            "active_provider": "gemini",
            "default_model": "gemini-2.5-flash",
            "has_api_key": False,
            "masked_api_key": "",
            "updated_at": None,
        }
    has_key = bool(config.encrypted_api_key)
    masked = mask_api_key(config.encrypted_api_key) if has_key else ""
    return {
        "id": config.id,
        "espacio_id": config.espacio_id,
        "ia_asistente_activo": config.ia_asistente_activo,
        "active_provider": config.active_provider,
        "default_model": config.default_model,
        "has_api_key": has_key,
        "masked_api_key": masked,
        "updated_at": config.updated_at,
    }


@router.post(
    "/config/toggle-ia",
    summary="Alternar estado maestro del asistente de IA",
)
@router.put(
    "/config/toggle-ia",
    summary="Alternar estado maestro del asistente de IA (PUT)",
)
async def alternar_ia_global_admin(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role("Admin_Sistema", "SuperAdmin")),
):
    from app.core.security_cipher import mask_api_key
    from app.services.config_service import get_configuracion_espacio
    from sqlalchemy import text

    c1 = await get_configuracion_espacio(db, espacio_id=1)
    nuevo_estado = not c1.ia_asistente_activo
    
    # Alternar sincrónicamente en todos los recintos del sistema
    await db.execute(text("UPDATE configuracion_espacios SET ia_asistente_activo = :val"), {"val": nuevo_estado})
    await db.commit()
    await db.refresh(c1)

    has_key = bool(c1.encrypted_api_key)
    masked = mask_api_key(c1.encrypted_api_key) if has_key else ""
    return {
        "id": c1.id,
        "espacio_id": c1.espacio_id,
        "ia_asistente_activo": c1.ia_asistente_activo,
        "active_provider": c1.active_provider,
        "default_model": c1.default_model,
        "has_api_key": has_key,
        "masked_api_key": masked,
        "updated_at": c1.updated_at,
    }


@router.put(
    "/roles/{rol_id}/ia-quota",
    summary="Actualizar cuota diaria y tiempo entre preguntas por rol (seguridad y tokens)",
)
async def actualizar_cuota_ia_rol(
    rol_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role("Admin_Sistema", "SuperAdmin")),
):
    from app.domain.auth_models import Rol
    stmt = select(Rol).where(Rol.id == rol_id)
    rol = (await db.execute(stmt)).scalar_one_or_none()
    if not rol:
        raise HTTPException(status_code=404, detail="Rol no encontrado")
    
    quota_raw = str(payload.get("rate_limit_quota", "30/día")).strip().replace("/day", "/día")
    cooldown_val = int(payload.get("cooldown_segundos", 10))
    if cooldown_val < 0:
        cooldown_val = 0

    rol.rate_limit_quota = quota_raw
    rol.cooldown_segundos = cooldown_val
    await db.commit()
    await db.refresh(rol)

    return {
        "id": rol.id,
        "nombre": rol.nombre,
        "descripcion": rol.descripcion,
        "rate_limit_quota": rol.rate_limit_quota,
        "cooldown_segundos": rol.cooldown_segundos,
    }


@router.put(
    "/config",
    summary="Actualizar proveedor y credenciales globales de IA",
)
async def actualizar_config_global_admin(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role("Admin_Sistema", "SuperAdmin")),
):
    from app.core.security_cipher import mask_api_key
    from app.services.config_service import update_llm_provider
    provider = payload.get("active_provider", "gemini")
    model = payload.get("default_model", "gemini-2.5-flash")
    api_key = payload.get("api_key")
    config = await update_llm_provider(
        db=db,
        espacio_id=1,
        provider=provider,
        default_model=model,
        api_key=api_key,
    )
    has_key = bool(config.api_key_encrypted)
    masked = mask_api_key(config.api_key_encrypted) if has_key else ""
    return {
        "id": config.id,
        "espacio_id": config.espacio_id,
        "ia_asistente_activo": config.ia_asistente_activo,
        "active_provider": config.active_provider,
        "default_model": config.default_model,
        "has_api_key": has_key,
        "masked_api_key": masked,
        "updated_at": config.updated_at,
    }






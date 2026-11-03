import uuid
from typing import List, Optional
from cachetools import TTLCache
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.limiter import limiter, get_rate_limit_by_role
from app.core.security import require_permission, validar_acceso_espacio
from app.domain.auth_models import Usuario
from app.api.v1.endpoints.config import check_ia_active
from app.schemas.chat_schemas import (
    ChatRequest, ChatResponse, ConversacionCrearRequest, ConversacionRenombrarRequest,
    ConversacionArchivarRequest, MensajeItemResponse, ConversacionResumenResponse,
    ConversacionDetalleResponse, ExportPdfRequest,
)
from app.services.servicio_chat_persistente import (
    crear_conversacion, obtener_conversacion, listar_conversaciones,
    renombrar_conversacion, archivar_conversacion, eliminar_conversacion,
    obtener_cuota_ia_usuario, purgar_conversaciones_eliminadas,
)
from app.services.chat import (
    procesar_consulta_analitica, generar_pdf_conversacion, _cache_resultados_herramientas,
    registrar_auditoria_chat, record_chat_audit,
)

router = APIRouter(dependencies=[Depends(check_ia_active)])
CHAT_CACHE: TTLCache = TTLCache(maxsize=128, ttl=600)


@router.post("", response_model=ChatResponse, summary="Procesar consulta analítica con asistente IA")
@router.post("/", include_in_schema=False)
@limiter.limit(get_rate_limit_by_role)
async def process_chat(
    request: Request, req: ChatRequest, background_tasks: BackgroundTasks,
    current_user: Usuario = Depends(require_permission("can_use_ai")),
    db: AsyncSession = Depends(get_db),
    stream: bool = Query(False, description="Activar streaming Server-Sent Events (SSE)"),
):
    return await procesar_consulta_analitica(request, req, background_tasks, current_user, db, stream)


@router.get("/conversaciones", response_model=List[ConversacionResumenResponse], summary="Listar conversaciones")
@router.get("/conversations", include_in_schema=False, response_model=List[ConversacionResumenResponse])
async def list_user_conversations(
    espacio_id: Optional[int] = Query(None), archivada: bool = Query(False), incluir_archivadas: bool = Query(False),
    db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(require_permission("can_use_ai")),
):
    if espacio_id:
        validar_acceso_espacio(espacio_id, current_user)
    convs = await listar_conversaciones(db, current_user.id, espacio_id, archivada or incluir_archivadas)
    return [
        ConversacionResumenResponse(
            id=str(c.id), usuario_id=c.usuario_id, espacio_id=c.espacio_id, titulo=c.titulo,
            creada_en=c.creada_en.isoformat() if c.creada_en else "",
            actualizada_en=c.actualizada_en.isoformat() if c.actualizada_en else "", archivada=c.archivada
        ) for c in convs
    ]


@router.post("/conversaciones", response_model=ConversacionResumenResponse, summary="Crear conversación")
@router.post("/conversations", include_in_schema=False, response_model=ConversacionResumenResponse)
async def create_user_conversation(
    req: ConversacionCrearRequest, db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permission("can_use_ai")),
):
    validar_acceso_espacio(req.espacio_id, current_user)
    c = await crear_conversacion(db, current_user.id, req.espacio_id, req.titulo)
    return ConversacionResumenResponse(
        id=str(c.id), usuario_id=c.usuario_id, espacio_id=c.espacio_id, titulo=c.titulo,
        creada_en=c.creada_en.isoformat() if c.creada_en else "",
        actualizada_en=c.actualizada_en.isoformat() if c.actualizada_en else "", archivada=c.archivada
    )


@router.get("/conversaciones/{conversacion_id}", response_model=ConversacionDetalleResponse, summary="Detalle conversación")
@router.get("/conversations/{conversacion_id}", include_in_schema=False, response_model=ConversacionDetalleResponse)
async def get_user_conversation_detail(
    conversacion_id: str, db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permission("can_use_ai")),
):
    try:
        conv_uuid = uuid.UUID(conversacion_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Identificador de conversación inválido.")
    conv = await obtener_conversacion(db, conv_uuid, current_user.id, cargar_mensajes=True)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada o no autorizada.")
    mensajes = [
        MensajeItemResponse(
            id=str(m.id), conversacion_id=str(m.conversacion_id), rol=m.rol, tipo=m.tipo,
            contenido=m.contenido, herramienta=m.herramienta, argumentos_json=m.argumentos_json,
            modelo=m.modelo, creado_en=m.creado_en.isoformat() if m.creado_en else ""
        ) for m in conv.mensajes
    ]
    return ConversacionDetalleResponse(
        id=str(conv.id), usuario_id=conv.usuario_id, espacio_id=conv.espacio_id, titulo=conv.titulo,
        creada_en=conv.creada_en.isoformat() if conv.creada_en else "",
        actualizada_en=conv.actualizada_en.isoformat() if conv.actualizada_en else "",
        archivada=conv.archivada, mensajes=mensajes
    )


@router.patch("/conversaciones/{conversacion_id}/renombrar", summary="Renombrar conversación")
@router.patch("/conversations/{conversacion_id}/rename", include_in_schema=False)
async def rename_user_conversation(
    conversacion_id: str, req: ConversacionRenombrarRequest,
    db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(require_permission("can_use_ai")),
):
    try:
        conv_uuid = uuid.UUID(conversacion_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Identificador de conversación inválido.")
    conv = await renombrar_conversacion(db, conv_uuid, current_user.id, req.titulo)
    return {"status": "success", "id": str(conv.id), "titulo": conv.titulo}


@router.patch("/conversaciones/{conversacion_id}/archivar", summary="Archivar conversación")
@router.patch("/conversations/{conversacion_id}/archive", include_in_schema=False)
async def archive_user_conversation(
    conversacion_id: str, req: ConversacionArchivarRequest,
    db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(require_permission("can_use_ai")),
):
    try:
        conv_uuid = uuid.UUID(conversacion_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Identificador de conversación inválido.")
    conv = await archivar_conversacion(db, conv_uuid, current_user.id, req.archivada)
    return {"status": "success", "id": str(conv.id), "archivada": conv.archivada}


@router.delete("/conversaciones/{conversacion_id}", summary="Eliminar conversación")
@router.delete("/conversations/{conversacion_id}", include_in_schema=False)
async def delete_user_conversation(
    conversacion_id: str, db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permission("can_use_ai")),
):
    try:
        conv_uuid = uuid.UUID(conversacion_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Identificador de conversación inválido.")
    await eliminar_conversacion(db, conv_uuid, current_user.id)
    return {"status": "success", "id": conversacion_id, "eliminada": True}


@router.get("/cuota", summary="Consultar cuota IA diaria")
@router.get("/quota", include_in_schema=False)
async def get_user_quota_info(
    db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(require_permission("can_use_ai")),
):
    return await obtener_cuota_ia_usuario(db, current_user)


@router.post("/purgar-eliminadas", summary="Purgar conversaciones expiradas")
@router.post("/purge-deleted", include_in_schema=False)
async def purge_expired_conversations(
    db: AsyncSession = Depends(get_db), current_user: Usuario = Depends(require_permission("can_manage_users")),
):
    purgadas = await purgar_conversaciones_eliminadas(db)
    return {"status": "success", "purgadas": purgadas, "retencion_dias": settings.RETENCION_CHAT_DIAS}


@router.get("/history", summary="Obtener historial de chat")
async def get_chat_history(
    session_id: Optional[str] = Query(None), conversacion_id: Optional[str] = Query(None),
    espacio_id: int = Query(1), db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permission("can_use_ai")),
):
    validar_acceso_espacio(espacio_id, current_user)
    mensajes_out = []
    if conversacion_id:
        try:
            conv = await obtener_conversacion(db, uuid.UUID(conversacion_id), current_user.id, cargar_mensajes=True)
            if conv:
                mensajes_out = [
                    {
                        "id": str(m.id), "rol": m.rol, "tipo": m.tipo, "contenido": m.contenido,
                        "herramienta": m.herramienta, "argumentos_json": m.argumentos_json,
                        "modelo": m.modelo, "creado_en": m.creado_en.isoformat() if m.creado_en else "",
                    } for m in conv.mensajes
                ]
        except Exception:
            pass
    return {"session_id": session_id or conversacion_id, "conversacion_id": conversacion_id, "messages": mensajes_out}


@router.post("/export-pdf", summary="Exportar reporte PDF consolidado")
async def export_chat_pdf(
    req: ExportPdfRequest, db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permission("can_use_ai")),
):
    validar_acceso_espacio(req.espacio_id, current_user)
    return await generar_pdf_conversacion(db, req, current_user.id)

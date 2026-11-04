import json
import logging
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.domain.auth_models import Usuario
from app.domain.chat_audit_models import ChatAuditLog
from app.domain.chat_models import ChatConversacion, ChatMensaje

logger = logging.getLogger(__name__)


def generar_titulo_conversacion(prompt: str) -> str:
    """Genera un título corto a partir de las primeras palabras del prompt."""
    if not prompt or not prompt.strip():
        return "Nueva Consulta Analítica"
    palabras = prompt.strip().split()
    titulo = " ".join(palabras[:6])
    if len(titulo) > 60:
        titulo = titulo[:57] + "..."
    return titulo[0].upper() + titulo[1:] if titulo else "Consulta Analítica"


async def crear_conversacion(
    db: AsyncSession,
    usuario_id: int,
    espacio_id: int,
    titulo: Optional[str] = None,
    prompt_inicial: Optional[str] = None,
) -> ChatConversacion:
    """Crea una nueva conversación vinculada al usuario y al espacio."""
    if not titulo:
        titulo = generar_titulo_conversacion(prompt_inicial or "")
    
    ahora = datetime.utcnow()
    conversacion = ChatConversacion(
        id=uuid.uuid4(),
        usuario_id=usuario_id,
        espacio_id=espacio_id,
        titulo=titulo,
        creada_en=ahora,
        actualizada_en=ahora,
        archivada=False,
        eliminada_en=None,
    )
    db.add(conversacion)
    await db.commit()
    await db.refresh(conversacion)
    return conversacion


async def obtener_conversacion(
    db: AsyncSession,
    conversacion_id: uuid.UUID,
    usuario_id: int,
    cargar_mensajes: bool = True,
) -> Optional[ChatConversacion]:
    """Obtiene una conversación validando pertenencia al usuario y estado no eliminado."""
    query = (
        select(ChatConversacion)
        .where(
            ChatConversacion.id == conversacion_id,
            ChatConversacion.usuario_id == usuario_id,
            ChatConversacion.eliminada_en.is_(None),
        )
    )
    if cargar_mensajes:
        query = query.options(selectinload(ChatConversacion.mensajes))
    
    res = await db.execute(query)
    return res.scalar_one_or_none()


async def listar_conversaciones(
    db: AsyncSession,
    usuario_id: int,
    espacio_id: Optional[int] = None,
    incluir_archivadas: bool = False,
) -> List[ChatConversacion]:
    """Lista las conversaciones activas del usuario, ordenadas por última actualización."""
    query = (
        select(ChatConversacion)
        .where(
            ChatConversacion.usuario_id == usuario_id,
            ChatConversacion.eliminada_en.is_(None),
        )
    )
    if espacio_id is not None:
        query = query.where(ChatConversacion.espacio_id == espacio_id)
    if not incluir_archivadas:
        query = query.where(ChatConversacion.archivada == False)  # noqa: E712
    
    query = query.order_by(ChatConversacion.actualizada_en.desc())
    res = await db.execute(query)
    return list(res.scalars().all())


async def renombrar_conversacion(
    db: AsyncSession,
    conversacion_id: uuid.UUID,
    usuario_id: int,
    nuevo_titulo: str,
) -> ChatConversacion:
    """Actualiza el título de una conversación perteneciente al usuario."""
    conversacion = await obtener_conversacion(db, conversacion_id, usuario_id, cargar_mensajes=False)
    if not conversacion:
        raise HTTPException(status_code=404, detail="Conversación no encontrada o no autorizada.")
    
    titulo_limpio = nuevo_titulo.strip() if nuevo_titulo else "Consulta Analítica"
    conversacion.titulo = titulo_limpio[:255]
    conversacion.actualizada_en = datetime.utcnow()
    await db.commit()
    await db.refresh(conversacion)
    return conversacion


async def archivar_conversacion(
    db: AsyncSession,
    conversacion_id: uuid.UUID,
    usuario_id: int,
    archivada: bool = True,
) -> ChatConversacion:
    """Modifica el estado de archivado de una conversación."""
    conversacion = await obtener_conversacion(db, conversacion_id, usuario_id, cargar_mensajes=False)
    if not conversacion:
        raise HTTPException(status_code=404, detail="Conversación no encontrada o no autorizada.")
    
    conversacion.archivada = archivada
    conversacion.actualizada_en = datetime.utcnow()
    await db.commit()
    await db.refresh(conversacion)
    return conversacion


async def eliminar_conversacion(
    db: AsyncSession,
    conversacion_id: uuid.UUID,
    usuario_id: int,
) -> bool:
    """Realiza borrado lógico registrando la marca de tiempo eliminada_en."""
    conversacion = await obtener_conversacion(db, conversacion_id, usuario_id, cargar_mensajes=False)
    if not conversacion:
        raise HTTPException(status_code=404, detail="Conversación no encontrada o no autorizada.")
    
    conversacion.eliminada_en = datetime.utcnow()
    await db.commit()
    return True


async def agregar_mensaje(
    db: AsyncSession,
    conversacion_id: uuid.UUID,
    rol: str,
    tipo: str,
    contenido: str,
    herramienta: Optional[str] = None,
    argumentos_json: Optional[str] = None,
    modelo: Optional[str] = None,
) -> ChatMensaje:
    """Registra un mensaje estructurado y actualiza la fecha de la conversación."""
    ahora = datetime.utcnow()
    mensaje = ChatMensaje(
        id=uuid.uuid4(),
        conversacion_id=conversacion_id,
        rol=rol,
        tipo=tipo,
        contenido=contenido,
        herramienta=herramienta,
        argumentos_json=argumentos_json,
        modelo=modelo,
        creado_en=ahora,
    )
    db.add(mensaje)
    await db.execute(
        update(ChatConversacion)
        .where(ChatConversacion.id == conversacion_id)
        .values(actualizada_en=ahora)
    )
    await db.commit()
    await db.refresh(mensaje)
    return mensaje


async def obtener_ultimos_mensajes_contexto(
    db: AsyncSession,
    conversacion_id: uuid.UUID,
    limite: int = 20,
) -> List[ChatMensaje]:
    """Recupera los últimos N mensajes ordenados cronológicamente para inyectar en el prompt."""
    query = (
        select(ChatMensaje)
        .where(ChatMensaje.conversacion_id == conversacion_id)
        .order_by(ChatMensaje.creado_en.desc())
        .limit(limite)
    )
    res = await db.execute(query)
    mensajes_desc = list(res.scalars().all())
    return list(reversed(mensajes_desc))


async def obtener_cuota_ia_usuario(
    db: AsyncSession,
    usuario: Usuario,
) -> Dict[str, Any]:
    """Calcula las cuotas diarias consumidas, restantes y cooldown consultando roles y chat_audit_logs."""
    from sqlalchemy.orm import selectinload

    # Cargar roles del usuario si no están en memoria
    roles_objs = getattr(usuario, "roles", [])
    if not roles_objs or not hasattr(roles_objs[0], "rate_limit_quota"):
        stmt_u = select(Usuario).options(selectinload(Usuario.roles)).where(Usuario.id == usuario.id)
        u_res = (await db.execute(stmt_u)).scalar_one_or_none()
        roles_objs = u_res.roles if u_res else []

    roles_nombres = [r.nombre for r in roles_objs]

    # Determinar cuota diaria y cooldown más permisivo entre los roles del usuario
    limite: Optional[int] = None
    min_cooldown: int = 10
    es_ilimitado: bool = False

    for r in roles_objs:
        q_str = str(getattr(r, "rate_limit_quota", "") or "30/día").lower().strip()
        cd = int(getattr(r, "cooldown_segundos", 10) or 10)
        if cd < min_cooldown:
            min_cooldown = cd

        if any(unl in q_str for unl in ("ilimitado", "unlimited", "none", "-1", "100000")):
            es_ilimitado = True
        elif not es_ilimitado:
            match = re.search(r'\d+', q_str)
            if match:
                val = int(match.group(0))
                if limite is None or val > limite:
                    limite = val
            elif limite is None:
                limite = 30

    if es_ilimitado:
        limite = None

    ahora = datetime.utcnow()
    inicio_dia = datetime(ahora.year, ahora.month, ahora.day, 0, 0, 0)

    # Consulta de solicitudes registradas en auditoría hoy
    query = (
        select(func.count(ChatAuditLog.id))
        .where(
            ChatAuditLog.usuario_id == usuario.id,
            ChatAuditLog.timestamp >= inicio_dia,
            ChatAuditLog.status == "éxito",
        )
    )
    res = await db.execute(query)
    usadas = res.scalar() or 0

    # Comprobar timestamp de última consulta para cooldown de seguridad
    query_last = (
        select(ChatAuditLog.timestamp)
        .where(ChatAuditLog.usuario_id == usuario.id)
        .order_by(ChatAuditLog.timestamp.desc())
    )
    res_last = await db.execute(query_last)
    last_time = res_last.scalars().first()

    segundos_espera = 0
    if last_time and min_cooldown > 0:
        diff = (ahora - last_time).total_seconds()
        if diff < min_cooldown:
            segundos_espera = int(min_cooldown - diff)

    if limite is None:
        return {
            "usuario_id": usuario.id,
            "roles": roles_nombres,
            "limite_diario": "ilimitado",
            "usadas": usadas,
            "restantes": "ilimitado",
            "excedida": False,
            "cooldown_segundos": min_cooldown,
            "segundos_para_siguiente_pregunta": segundos_espera,
        }

    restantes = max(0, limite - usadas)
    return {
        "usuario_id": usuario.id,
        "roles": roles_nombres,
        "limite_diario": limite,
        "usadas": usadas,
        "restantes": restantes,
        "excedida": usadas >= limite,
        "cooldown_segundos": min_cooldown,
        "segundos_para_siguiente_pregunta": segundos_espera,
    }


async def validar_cuota_ia_usuario(
    db: AsyncSession,
    usuario: Usuario,
) -> None:
    """Verifica si el usuario aún dispone de cuota diaria y respeta el cooldown; lanza HTTP 429 si se agotó."""
    cuota = await obtener_cuota_ia_usuario(db, usuario)
    if cuota.get("segundos_para_siguiente_pregunta", 0) > 0:
        secs = cuota["segundos_para_siguiente_pregunta"]
        raise HTTPException(
            status_code=429,
            detail=f"Control de flujo de tokens activo: por favor espera {secs} segundo(s) antes de enviar otra consulta.",
        )
    if cuota.get("excedida", False):
        limite = cuota.get("limite_diario")
        raise HTTPException(
            status_code=429,
            detail=f"Cuota diaria de consultas analíticas excedida ({limite} consultas permitidas por día para tu rol).",
        )


async def purgar_conversaciones_eliminadas(
    db: AsyncSession,
    retencion_dias: Optional[int] = None,
) -> int:
    """Elimina permanentemente de la base de datos conversaciones que lleven más de N días en borrado lógico."""
    dias = retencion_dias if retencion_dias is not None else settings.RETENCION_CHAT_DIAS
    fecha_corte = datetime.utcnow() - timedelta(days=dias)
    
    # Eliminación en cascada de conversaciones y sus mensajes
    stmt = (
        delete(ChatConversacion)
        .where(
            ChatConversacion.eliminada_en.is_not(None),
            ChatConversacion.eliminada_en < fecha_corte,
        )
    )
    res = await db.execute(stmt)
    await db.commit()
    purgadas = res.rowcount or 0
    if purgadas > 0:
        logger.info(f"Purga periódica de chat: {purgadas} conversaciones eliminadas permanentemente.")
    return purgadas

from datetime import datetime, timezone
from typing import Optional
from app.core.database import AsyncSessionLocal
from app.domain.chat_audit_models import ChatAuditLog


async def registrar_auditoria_chat(
    usuario_id: Optional[int],
    prompt_text: str,
    dataset_tipo: Optional[str],
    modelo_utilizado: Optional[str],
    status: str,
    response_time_ms: float,
    respuesta_text: Optional[str] = None,
    origen: str = "dashboard",
    reporte_codigo: Optional[str] = None,
):
    """Registra la auditoría de cada interacción del asistente IA en segundo plano."""
    try:
        estado_raw = (status or "éxito").strip()
        if estado_raw.lower() == "success":
            estado_raw = "éxito"
        estado_limpio = estado_raw[:20]
        async with AsyncSessionLocal() as session:
            audit = ChatAuditLog(
                usuario_id=usuario_id,
                prompt_text=prompt_text,
                respuesta_text=respuesta_text,
                origen=(origen or "dashboard")[:30],
                reporte_codigo=reporte_codigo[:32] if reporte_codigo else None,
                dataset_tipo=dataset_tipo,
                modelo_utilizado=modelo_utilizado,
                status=estado_limpio,
                response_time_ms=response_time_ms,
                timestamp=datetime.now(timezone.utc),
            )
            session.add(audit)
            await session.commit()
    except Exception:
        pass


record_chat_audit = registrar_auditoria_chat


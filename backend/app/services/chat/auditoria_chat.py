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
):
    """Registra la auditoría de cada interacción del asistente IA en segundo plano."""
    try:
        async with AsyncSessionLocal() as session:
            audit = ChatAuditLog(
                usuario_id=usuario_id,
                prompt_text=prompt_text,
                dataset_tipo=dataset_tipo,
                modelo_utilizado=modelo_utilizado,
                status=status,
                response_time_ms=response_time_ms,
            )
            session.add(audit)
            await session.commit()
    except Exception:
        pass


record_chat_audit = registrar_auditoria_chat


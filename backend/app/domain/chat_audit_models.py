from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Double, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.auth_models import Usuario


class ChatAuditLog(Base):
    __tablename__ = "chat_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True
    )
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_tipo: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    modelo_utilizado: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    response_time_ms: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    usuario: Mapped[Optional[Usuario]] = relationship(
        "Usuario", foreign_keys=[usuario_id], lazy="joined"
    )

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ConfiguracionGlobal(Base):
    __tablename__ = "configuracion_global"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    ia_asistente_activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    active_provider: Mapped[str] = mapped_column(String(50), default="gemini", nullable=False)
    default_model: Mapped[str] = mapped_column(String(100), default="gemini-2.5-flash", nullable=False)
    encrypted_api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("id = 1", name="ck_configuracion_global_single_row"),
    )


from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, func
from sqlalchemy.dialects.mssql import DATETIME2
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.auth_models import Usuario


class DownloadAuditLog(Base):
    __tablename__ = "download_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True
    )
    modulo: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    formato: Mapped[str] = mapped_column(String(20), nullable=False)
    filtro_fecha_inicio: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    filtro_fecha_fin: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    filtro_detalle: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    total_registros: Mapped[int] = mapped_column(Integer, default=0)
    ip_origen: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DATETIME2, server_default=func.now(), nullable=False, index=True
    )

    usuario: Mapped[Optional[Usuario]] = relationship(
        "Usuario", foreign_keys=[usuario_id], lazy="joined"
    )

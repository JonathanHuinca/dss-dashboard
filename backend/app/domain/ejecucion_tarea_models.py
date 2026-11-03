import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.mssql import DATETIME2, UNIQUEIDENTIFIER as UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class EjecucionTarea(Base):
    __tablename__ = "ejecuciones_tareas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4
    )
    tarea: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    disparador: Mapped[str] = mapped_column(String(20), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    inicio_en: Mapped[datetime] = mapped_column(
        DATETIME2, default=datetime.utcnow, nullable=False
    )
    fin_en: Mapped[Optional[datetime]] = mapped_column(DATETIME2, nullable=True)
    latido_en: Mapped[datetime] = mapped_column(
        DATETIME2, default=datetime.utcnow, nullable=False
    )
    usuario_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    resumen_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    memoria_pico_mb: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    usuario = relationship("Usuario")

    __table_args__ = (
        Index("ix_ejecuciones_tareas_tarea_inicio", "tarea", "inicio_en"),
        CheckConstraint(
            "disparador IN ('programado', 'manual', 'recuperacion')",
            name="ck_ejecuciones_tareas_disparador",
        ),
        CheckConstraint(
            "estado IN ('en_curso', 'exitoso', 'fallido', 'omitido')",
            name="ck_ejecuciones_tareas_estado",
        ),
    )

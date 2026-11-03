from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


from sqlalchemy.dialects.mssql import DATETIME2
from sqlalchemy import ForeignKey

class ConfiguracionEspacios(Base):
    __tablename__ = "configuracion_espacios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    espacio_id: Mapped[int] = mapped_column(Integer, ForeignKey("espacios.id"), nullable=False)
    ia_asistente_activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    active_provider: Mapped[str] = mapped_column(String(50), default="gemini", nullable=False)
    default_model: Mapped[str] = mapped_column(String(100), default="gemini-2.5-flash", nullable=False)
    encrypted_api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME2, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class HorarioOperacion(Base):
    __tablename__ = "horarios_operacion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    espacio_id: Mapped[int] = mapped_column(Integer, ForeignKey("espacios.id"), nullable=False, index=True)
    anio: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    descripcion: Mapped[str] = mapped_column(String(150), nullable=False)
    tipo_horario: Mapped[str] = mapped_column(String(50), default="regular", nullable=False)
    fecha_inicio: Mapped[Optional[datetime]] = mapped_column(DATETIME2, nullable=True)
    fecha_fin: Mapped[Optional[datetime]] = mapped_column(DATETIME2, nullable=True)
    hora_apertura: Mapped[str] = mapped_column(String(5), default="08:30", nullable=False)
    hora_cierre: Mapped[str] = mapped_column(String(5), default="20:30", nullable=False)
    cierre_dia_siguiente: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    es_continuo_24h: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    configuracion_dias: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    subespacio: Mapped[Optional[str]] = mapped_column(String(50), default="todos", nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME2, server_default=func.now(), onupdate=func.now(), nullable=False
    )


import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.mssql import DATETIME2, UNIQUEIDENTIFIER as UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ChatConversacion(Base):
    __tablename__ = "chat_conversaciones"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4
    )
    usuario_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    espacio_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("espacios.id"), nullable=False
    )
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    creada_en: Mapped[datetime] = mapped_column(
        DATETIME2, default=datetime.utcnow, nullable=False
    )
    actualizada_en: Mapped[datetime] = mapped_column(
        DATETIME2, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    archivada: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    eliminada_en: Mapped[Optional[datetime]] = mapped_column(DATETIME2, nullable=True)

    usuario = relationship("Usuario")
    espacio = relationship("Espacio")
    mensajes: Mapped[List["ChatMensaje"]] = relationship(
        "ChatMensaje",
        back_populates="conversacion",
        cascade="all, delete-orphan",
        order_by="ChatMensaje.creado_en",
    )

    __table_args__ = (
        Index("ix_chat_conversaciones_usuario_actualizada", "usuario_id", "actualizada_en"),
    )


class ChatMensaje(Base):
    __tablename__ = "chat_mensajes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4
    )
    conversacion_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("chat_conversaciones.id", ondelete="CASCADE"), nullable=False
    )
    rol: Mapped[str] = mapped_column(String(20), nullable=False)
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    contenido: Mapped[str] = mapped_column(Text, nullable=False)
    herramienta: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    argumentos_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    modelo: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DATETIME2, default=datetime.utcnow, nullable=False
    )

    conversacion: Mapped["ChatConversacion"] = relationship(
        "ChatConversacion", back_populates="mensajes"
    )

    __table_args__ = (
        Index("ix_chat_mensajes_conversacion_creado", "conversacion_id", "creado_en"),
    )

import uuid
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.mssql import DATETIME2, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DestinatarioReporte(Base):
    """Perfil de persona solicitante de reportes ejecutivos con bandeja histórica propia."""
    __tablename__ = "destinatarios_reportes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    nombre_completo: Mapped[str] = mapped_column(String(150), nullable=False)
    cargo: Mapped[str] = mapped_column(String(120), nullable=False)
    unidad_academica: Mapped[str] = mapped_column(String(180), nullable=False)
    token_portal: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DATETIME2, default=datetime.now, nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DATETIME2, default=datetime.now, nullable=False)

    reportes: Mapped[List["ReporteCompartido"]] = relationship(
        "ReporteCompartido",
        back_populates="destinatario",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ReporteCompartido(Base):
    """Reporte ejecutivo compartido con filtros sellados en servidor, notas y control de vigencia."""
    __tablename__ = "reportes_compartidos"

    id: Mapped[uuid.UUID] = mapped_column(UNIQUEIDENTIFIER, primary_key=True, default=uuid.uuid4)
    token_acceso: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    codigo_corto: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    creado_por_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True
    )
    destinatario_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("destinatarios_reportes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    espacio_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    titulo_reporte: Mapped[str] = mapped_column(String(200), nullable=False)
    finalidad_reporte: Mapped[str] = mapped_column(String(500), nullable=False)
    nota_general: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notas_items_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    modo_datos: Mapped[str] = mapped_column(String(30), default="dinamico_acotado", nullable=False)
    filtros_bloqueados_json: Mapped[str] = mapped_column(Text, nullable=False)
    graficos_visibles_json: Mapped[str] = mapped_column(Text, nullable=False)
    indicadores_visibles_json: Mapped[str] = mapped_column(Text, nullable=False)
    datos_instantanea_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    permitir_exportacion: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    permitir_ia: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expira_en: Mapped[Optional[datetime]] = mapped_column(DATETIME2, nullable=True)
    total_accesos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ultimo_acceso_en: Mapped[Optional[datetime]] = mapped_column(DATETIME2, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DATETIME2, default=datetime.now, nullable=False)

    destinatario: Mapped["DestinatarioReporte"] = relationship(
        "DestinatarioReporte", back_populates="reportes", lazy="selectin"
    )
    accesos: Mapped[List["AuditoriaAccesoReporte"]] = relationship(
        "AuditoriaAccesoReporte",
        back_populates="reporte",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class AuditoriaAccesoReporte(Base):
    """Registro de auditoría de aperturas, descargas y consultas sobre un reporte compartido."""
    __tablename__ = "auditoria_accesos_reporte"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reporte_id: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER, ForeignKey("reportes_compartidos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fecha_hora: Mapped[datetime] = mapped_column(DATETIME2, default=datetime.now, nullable=False)
    ip_origen: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    accion: Mapped[str] = mapped_column(String(50), default="apertura_reporte", nullable=False)

    reporte: Mapped["ReporteCompartido"] = relationship("ReporteCompartido", back_populates="accesos")


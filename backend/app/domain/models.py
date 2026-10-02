import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, DateTime,
    ForeignKey, Index, Integer, Numeric, SmallInteger,
    String, Text, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

from app.domain.auth_models import Usuario, Rol, UsuarioRol
from app.domain.config_models import ConfiguracionGlobal


class Espacio(Base):
    __tablename__ = "espacios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campus: Mapped[str] = mapped_column(String(80), nullable=False)
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    capacidad_max: Mapped[int] = mapped_column(Integer, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        CheckConstraint("tipo IN ('biblioteca', 'estacionamiento')", name="ck_espacios_tipo"),
        CheckConstraint("capacidad_max > 0", name="ck_espacios_capacidad"),
    )


class EventoAsistencia(Base):
    """
    Hipertabla TimescaleDB particionada por 'time' (chunks de 1 semana).
    La columna 'time' es la primera entrada del usuario — requerida por TimescaleDB.
    SQLAlchemy declara la tabla; create_hypertable se ejecuta en la migración Alembic vía op.execute().
    """
    __tablename__ = "eventos_asistencia"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, primary_key=True)
    espacio_id: Mapped[int] = mapped_column(Integer, ForeignKey("espacios.id"), nullable=False, primary_key=True)
    person_id_hash: Mapped[str] = mapped_column(String(64), nullable=False, primary_key=True)

    door_entrada: Mapped[Optional[str]] = mapped_column(String(80))
    door_salida: Mapped[Optional[str]] = mapped_column(String(80))
    primera_entrada: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ultima_salida: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    salida_imputada: Mapped[bool] = mapped_column(Boolean, default=False)
    permanencia_min: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2))
    marcajes_totales: Mapped[int] = mapped_column(SmallInteger, default=1)
    alerta_coherencia_fechas: Mapped[bool] = mapped_column(Boolean, default=False)
    alerta_marcajes: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        Index("ix_ea_espacio_time", "espacio_id", "time"),
        Index("ix_ea_person_time", "person_id_hash", "time"),
    )


class EventoVehicular(Base):
    """
    Hipertabla TimescaleDB particionada por 'time' (chunks de 1 semana).
    """
    __tablename__ = "eventos_vehiculares"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, primary_key=True)
    espacio_id: Mapped[int] = mapped_column(Integer, ForeignKey("espacios.id"), nullable=False, primary_key=True)
    patente_hash: Mapped[str] = mapped_column(String(64), nullable=False, primary_key=True)
    camara: Mapped[str] = mapped_column(String(80), nullable=False, primary_key=True)

    direccion: Mapped[str] = mapped_column(String(10), nullable=False)
    tipo_vehiculo: Mapped[Optional[str]] = mapped_column(String(40))
    marca: Mapped[Optional[str]] = mapped_column(String(60))
    color: Mapped[Optional[str]] = mapped_column(String(40))
    calidad_lectura: Mapped[str] = mapped_column(String(10), default="ok")

    __table_args__ = (
        CheckConstraint("direccion IN ('entrada', 'salida')", name="ck_ev_direccion"),
        CheckConstraint("calidad_lectura IN ('ok', 'unknown', 'baja')", name="ck_ev_calidad"),
        Index("ix_ev_espacio_time", "espacio_id", "time"),
        Index("ix_ev_patente_time", "patente_hash", "time"),
    )


class CalendarioAcademico(Base):
    __tablename__ = "calendario_academico"

    fecha: Mapped[date] = mapped_column(Date, primary_key=True)
    is_holiday: Mapped[bool] = mapped_column(Boolean, default=False)
    is_break: Mapped[bool] = mapped_column(Boolean, default=False)
    is_exam_period: Mapped[bool] = mapped_column(Boolean, default=False)
    is_class_milestone: Mapped[bool] = mapped_column(Boolean, default=False)
    suspension_actividades: Mapped[bool] = mapped_column(Boolean, default=False)
    descripcion: Mapped[Optional[str]] = mapped_column(Text)
    fuente: Mapped[str] = mapped_column(String(50), default="scraping")


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    registros_ok: Mapped[int] = mapped_column(Integer, default=0)
    registros_error: Mapped[int] = mapped_column(Integer, default=0)
    error_detail: Mapped[Optional[str]] = mapped_column(Text)
    creado_por: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completado_en: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("tipo IN ('asistencia', 'vehicular', 'academico')", name="ck_ij_tipo"),
        CheckConstraint(
            "estado IN ('queued', 'processing', 'completed', 'failed')", name="ck_ij_estado"
        ),
    )


class RollupHistoricoDiario(Base):
    __tablename__ = "rollup_historico_diario"

    fecha: Mapped[date] = mapped_column(Date, nullable=False, primary_key=True)
    espacio_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("espacios.id"), nullable=False, primary_key=True
    )
    tipo: Mapped[str] = mapped_column(String(20), nullable=False, primary_key=True)
    ingresos_total: Mapped[int] = mapped_column(Integer, nullable=False)
    salidas_total: Mapped[int] = mapped_column(Integer, nullable=False)
    personas_unicas: Mapped[Optional[int]] = mapped_column(Integer)
    permanencia_mediana_min: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2))

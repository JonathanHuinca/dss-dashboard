"""
modelos_institucionales_uct.py — Modelos ORM para el Esquema Espejo de Base de Datos Institucional UCT.
Mantiene las tablas, nombres exactos de campos, relaciones y claves foráneas de DATOS_PRUEBAS_INSTITUCIONALES_UCT.xlsx
con soporte SCD-2 (Dimensión de Cambio Lento Tipo 2) para el histórico de situaciones de estudiantes (Ley N° 21.719).
"""
from datetime import datetime, date
from typing import Optional
from sqlalchemy import (
    Integer,
    SmallInteger,
    String,
    Date,
    Boolean,
    ForeignKey,
    Index,
)
from sqlalchemy.dialects.mssql import DATETIME2
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class InstitucionalCampus(Base):
    __tablename__ = "uct_campus"

    camp_codigo_campus: Mapped[int] = mapped_column(Integer, primary_key=True)
    camp_campus: Mapped[str] = mapped_column(String(120), nullable=False)
    camp_direccion: Mapped[Optional[str]] = mapped_column(String(255))
    camp_vigente: Mapped[Optional[str]] = mapped_column(String(1), default="S")
    camp_fecha_registro: Mapped[Optional[datetime]] = mapped_column(DATETIME2)
    camp_usuario: Mapped[Optional[str]] = mapped_column(String(50))


class InstitucionalEdificios(Base):
    __tablename__ = "uct_edificios"

    edif_codigo_edificio: Mapped[int] = mapped_column(Integer, primary_key=True)
    camp_codigo_campus: Mapped[int] = mapped_column(
        Integer, ForeignKey("uct_campus.camp_codigo_campus"), nullable=False, index=True
    )
    edif_edificio: Mapped[str] = mapped_column(String(150), nullable=False)
    edif_vigente: Mapped[Optional[str]] = mapped_column(String(1), default="S")
    edif_observacion: Mapped[Optional[str]] = mapped_column(String(255))
    edif_fecha_registro: Mapped[Optional[datetime]] = mapped_column(DATETIME2)
    edif_usuario: Mapped[Optional[str]] = mapped_column(String(50))


class InstitucionalTipoInmueble(Base):
    __tablename__ = "uct_tipo_inmueble"

    tiin_codigo: Mapped[int] = mapped_column(Integer, primary_key=True)
    tiin_nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    tiin_descripcion: Mapped[Optional[str]] = mapped_column(String(255))
    tiin_vigente: Mapped[Optional[str]] = mapped_column(String(1), default="S")
    usuario_mod: Mapped[Optional[str]] = mapped_column(String(50))
    fecha_mod: Mapped[Optional[datetime]] = mapped_column(DATETIME2)


class InstitucionalAmbiente(Base):
    __tablename__ = "uct_ambiente"

    ambi_codigo: Mapped[int] = mapped_column(Integer, primary_key=True)
    camp_codigo: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    inmu_codigo: Mapped[Optional[int]] = mapped_column(Integer)
    nive_codigo: Mapped[Optional[int]] = mapped_column(Integer)
    tami_codigo: Mapped[Optional[int]] = mapped_column(Integer)
    ambi_nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    ambi_sigla_nuevo: Mapped[Optional[str]] = mapped_column(String(50))
    ambi_vigente: Mapped[Optional[str]] = mapped_column(String(1), default="S")
    usuario_mod: Mapped[Optional[str]] = mapped_column(String(50))
    fecha_mod: Mapped[Optional[datetime]] = mapped_column(DATETIME2)


class InstitucionalTipoCarrera(Base):
    __tablename__ = "uct_tipo_carrera"

    tcar_codigo: Mapped[int] = mapped_column(Integer, primary_key=True)
    clac_codigo: Mapped[int] = mapped_column(Integer, primary_key=True)
    tcar_nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    tcar_tipo: Mapped[Optional[str]] = mapped_column(String(50))
    clac_nombre: Mapped[Optional[str]] = mapped_column(String(100))
    clac_descripcion: Mapped[Optional[str]] = mapped_column(String(255))
    usuario_mod: Mapped[Optional[str]] = mapped_column(String(50))
    fecha_mod: Mapped[Optional[datetime]] = mapped_column(DATETIME2)


class InstitucionalCarreraPrograma(Base):
    __tablename__ = "uct_carrera_programa"

    carr_codigo: Mapped[int] = mapped_column(Integer, primary_key=True)
    tcar_codigo: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    clac_codigo: Mapped[Optional[int]] = mapped_column(Integer)
    carr_nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    uaca_codigo: Mapped[Optional[int]] = mapped_column(Integer)
    uaca_codigo_dicta: Mapped[Optional[int]] = mapped_column(Integer)
    usuario_mod: Mapped[Optional[str]] = mapped_column(String(50))
    fecha_mod: Mapped[Optional[datetime]] = mapped_column(DATETIME2)


class InstitucionalCarreraCampus(Base):
    __tablename__ = "uct_carrera_campus"

    carr_codigo: Mapped[int] = mapped_column(Integer, primary_key=True)
    camp_codigo: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_mod: Mapped[Optional[str]] = mapped_column(String(50))
    fecha_mod: Mapped[Optional[datetime]] = mapped_column(DATETIME2)


class InstitucionalSituacionAlumno(Base):
    __tablename__ = "uct_situacion_alumno"

    salu_codigo: Mapped[int] = mapped_column(Integer, primary_key=True)
    salu_nombre: Mapped[str] = mapped_column(String(100), nullable=False)


class InstitucionalViasIngreso(Base):
    __tablename__ = "uct_vias_ingreso"

    ving_codigo: Mapped[int] = mapped_column(Integer, primary_key=True)
    ving_nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    ving_descripcion: Mapped[Optional[str]] = mapped_column(String(255))
    usuario_mod: Mapped[Optional[str]] = mapped_column(String(50))
    fecha_mod: Mapped[Optional[datetime]] = mapped_column(DATETIME2)


class InstitucionalEstudiante(Base):
    """
    Entidad Estudiante UCT con Seudonimización Criptográfica según Ley N° 21.719.
    """
    __tablename__ = "uct_estudiante"

    estd_rut_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    estd_rut_cifrado: Mapped[Optional[str]] = mapped_column(String(255))
    estd_dv: Mapped[Optional[str]] = mapped_column(String(2))
    estd_paterno_cifrado: Mapped[Optional[str]] = mapped_column(String(255))
    estd_materno_cifrado: Mapped[Optional[str]] = mapped_column(String(255))
    estd_nombre1_cifrado: Mapped[Optional[str]] = mapped_column(String(255))
    estd_nombre2_cifrado: Mapped[Optional[str]] = mapped_column(String(255))
    sexo_codigo: Mapped[Optional[str]] = mapped_column(String(10))
    estd_fecha_nac: Mapped[Optional[date]] = mapped_column(Date)
    estd_email_cifrado: Mapped[Optional[str]] = mapped_column(String(255))


class InstitucionalEstudianteCarrera(Base):
    """
    Entidad Estudiante-Carrera UCT con soporte SCD-2 (Histórico por Período y Estado).
    """
    __tablename__ = "uct_estudiante_carrera"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    estu_registro: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    estd_rut_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    estd_dv: Mapped[Optional[str]] = mapped_column(String(2))
    carr_codigo: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    plan_codigo: Mapped[Optional[int]] = mapped_column(Integer)
    men_codigo: Mapped[Optional[int]] = mapped_column(Integer)
    salu_codigo: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    ving_codigo: Mapped[Optional[int]] = mapped_column(Integer)
    estu_anho_ing: Mapped[Optional[int]] = mapped_column(SmallInteger)
    estu_semestre_ing: Mapped[Optional[int]] = mapped_column(SmallInteger)
    timp_codigo: Mapped[Optional[int]] = mapped_column(Integer)

    # Atributos SCD-2 (Vigencia e Historial Temporal)
    periodo_academico: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    fecha_desde: Mapped[Optional[datetime]] = mapped_column(DATETIME2)
    fecha_hasta: Mapped[Optional[datetime]] = mapped_column(DATETIME2)
    es_actual: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    usuario_mod: Mapped[Optional[str]] = mapped_column(String(50))
    fecha_mod: Mapped[Optional[datetime]] = mapped_column(DATETIME2)

    __table_args__ = (
        Index("ix_uec_registro_actual", "estu_registro", "es_actual"),
        Index("ix_uec_rut_actual", "estd_rut_hash", "es_actual"),
    )

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, DateTime,
    ForeignKey, Index, Integer, Numeric, SmallInteger,
    String, Text, func,
)
from sqlalchemy.dialects.mssql import DATETIME2, UNIQUEIDENTIFIER as UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

from app.domain.auth_models import Usuario, Rol, UsuarioRol
from app.domain.config_models import ConfiguracionEspacios


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
    Tabla de hechos para eventos de asistencia (SQL Server).
    Optimizada con Clustered Columnstore Index (CCI) vía Alembic.
    """
    __tablename__ = "eventos_asistencia"

    time: Mapped[datetime] = mapped_column(DATETIME2, nullable=False, primary_key=True)
    espacio_id: Mapped[int] = mapped_column(Integer, ForeignKey("espacios.id"), nullable=False, primary_key=True)
    person_id_hash: Mapped[str] = mapped_column(String(64), nullable=False, primary_key=True)

    door_entrada: Mapped[Optional[str]] = mapped_column(String(80))
    door_salida: Mapped[Optional[str]] = mapped_column(String(80))
    primera_entrada: Mapped[Optional[datetime]] = mapped_column(DATETIME2, nullable=True)
    ultima_salida: Mapped[Optional[datetime]] = mapped_column(DATETIME2)
    salida_imputada: Mapped[bool] = mapped_column(Boolean, default=False)
    entrada_imputada: Mapped[bool] = mapped_column(Boolean, default=False)
    permanencia_min: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2))
    marcajes_totales: Mapped[int] = mapped_column(SmallInteger, default=1)
    alerta_coherencia_fechas: Mapped[bool] = mapped_column(Boolean, default=False)
    alerta_marcajes: Mapped[bool] = mapped_column(Boolean, default=False)
    carrera: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    facultad: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    estamento: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    __table_args__ = (
        Index("ix_ea_espacio_time", "espacio_id", "time"),
        Index("ix_ea_person_time", "person_id_hash", "time"),
    )


class EventoVehicular(Base):
    """
    Tabla de hechos para eventos vehiculares (SQL Server).
    Optimizada con Clustered Columnstore Index (CCI) vía Alembic.
    """
    __tablename__ = "eventos_vehiculares"

    time: Mapped[datetime] = mapped_column(DATETIME2, nullable=False, primary_key=True)
    espacio_id: Mapped[int] = mapped_column(Integer, ForeignKey("espacios.id"), nullable=False, primary_key=True)
    patente_hash: Mapped[str] = mapped_column(String(64), nullable=False, primary_key=True)
    patente_cifrada: Mapped[str] = mapped_column(String(255), nullable=False)
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
    is_strike_federado: Mapped[bool] = mapped_column(Boolean, default=False)
    is_strike_carrera: Mapped[bool] = mapped_column(Boolean, default=False)
    tipo_contingencia: Mapped[Optional[str]] = mapped_column(String(50))
    descripcion: Mapped[Optional[str]] = mapped_column(Text)
    fuente: Mapped[str] = mapped_column(String(50), default="scraping")


class EstadoCalendarioAnual(Base):
    __tablename__ = "estado_calendario_anual"

    anio_objetivo: Mapped[int] = mapped_column(Integer, primary_key=True)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="pendiente")
    intentos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ultimo_intento_en: Mapped[Optional[datetime]] = mapped_column(DATETIME2, nullable=True)
    proximo_intento_en: Mapped[Optional[datetime]] = mapped_column(DATETIME2, nullable=True)
    ultimo_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    eventos_encontrados: Mapped[int] = mapped_column(Integer, nullable=False, default=0)



class ContingenciaAcademica(Base):
    __tablename__ = "contingencias_academicas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    titulo: Mapped[str] = mapped_column(String(150), nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(Text)
    carreras_afectadas: Mapped[Optional[str]] = mapped_column(Text)
    implica_cierre_total: Mapped[bool] = mapped_column(Boolean, default=False)
    espacio_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    subespacio: Mapped[Optional[str]] = mapped_column(String(50), default="todos", nullable=True)
    hora_inicio: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    hora_fin: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DATETIME2, server_default=func.now())



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
    creado_en: Mapped[datetime] = mapped_column(DATETIME2, server_default=func.now())
    completado_en: Mapped[Optional[datetime]] = mapped_column(DATETIME2)
    file_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    fecha_min: Mapped[Optional[datetime]] = mapped_column(DATETIME2, nullable=True)
    fecha_max: Mapped[Optional[datetime]] = mapped_column(DATETIME2, nullable=True)
    modo_solapamiento: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    clave_enlace: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    modo_enlace: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    espacio_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("espacios.id"), nullable=True)

    __table_args__ = (
        CheckConstraint("tipo IN ('asistencia', 'marcajes_torniquete', 'vehicular', 'vehicular_anpr', 'academico', 'curricular', 'custom')", name="ck_ij_tipo"),
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


class DimCarreraPrograma(Base):
    __tablename__ = "dim_carrera_programa"

    carr_codigo: Mapped[str] = mapped_column(String(20), primary_key=True)
    carr_nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    facultad: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)


class DimEstudianteCarrera(Base):
    __tablename__ = "dim_estudiante_carrera"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    matricula: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    rut_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    carr_codigo: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    carr_nombre: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    facultad: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    anho_ingreso: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    estamento: Mapped[Optional[str]] = mapped_column(String(50), default="Estudiante")


class SalaBiblioteca(Base):
    __tablename__ = "salas_biblioteca"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    espacio_id: Mapped[int] = mapped_column(Integer, ForeignKey("espacios.id"), nullable=False, index=True)
    codigo: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    edificio: Mapped[str] = mapped_column(String(50), nullable=False)
    piso: Mapped[str] = mapped_column(String(50), nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    capacidad_asientos: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    permite_horario_extendido: Mapped[bool] = mapped_column(Boolean, default=False)
    puerta_principal_in: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    puerta_principal_out: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    puerta_universal_in: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    puerta_universal_out: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class EstadoSincronizacionFuente(Base):
    """
    Control y auditoría del estado de sincronización incremental desde fuentes externas (Smart Campus UCT).
    """
    __tablename__ = "estado_sincronizacion_fuente"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fuente: Mapped[str] = mapped_column(String(40), nullable=False)  # 'torniquetes' o 'estacionamientos'
    espacio_id: Mapped[int] = mapped_column(Integer, ForeignKey("espacios.id"), nullable=False, index=True)
    ultima_fecha_sincronizada: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    ultima_ejecucion_en: Mapped[Optional[datetime]] = mapped_column(DATETIME2, nullable=True)
    filas_leidas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    filas_insertadas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    filas_duplicadas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="exitoso")  # 'exitoso', 'fallido', 'en_curso'
    ultimo_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class SectorEstacionamiento(Base):
    """
    Sectores o campus específicos de estacionamiento vehicular (CSF11, CSF21, CHS01).
    Permite gobernanza individual de capacidad y aforo máximo desde el panel de administración.
    """
    __tablename__ = "sectores_estacionamiento"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    espacio_id: Mapped[int] = mapped_column(Integer, ForeignKey("espacios.id"), nullable=False, index=True, default=2)
    codigo: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)  # 'CSF11', 'CSF21', 'CHS01'
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    capacidad_max: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    camaras_entrada: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    camaras_salida: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


# Modelos Espejo de Base de Datos Institucional UCT
from app.domain.modelos_institucionales_uct import (
    InstitucionalCampus,
    InstitucionalEdificios,
    InstitucionalTipoInmueble,
    InstitucionalAmbiente,
    InstitucionalTipoCarrera,
    InstitucionalCarreraPrograma,
    InstitucionalCarreraCampus,
    InstitucionalSituacionAlumno,
    InstitucionalViasIngreso,
    InstitucionalEstudiante,
    InstitucionalEstudianteCarrera,
)


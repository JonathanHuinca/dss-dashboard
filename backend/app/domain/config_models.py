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
    espacio_id: Mapped[int] = mapped_column(Integer, ForeignKey("espacios.id"), nullable=False, unique=True)
    ia_asistente_activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    active_provider: Mapped[str] = mapped_column(String(50), default="gemini", nullable=False)
    default_model: Mapped[str] = mapped_column(String(100), default="gemini-3.1-flash-lite", nullable=False)
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


class CredencialProveedorIA(Base):
    """Credencial cifrada de proveedor LLM para conmutación dinámica desde administración."""

    __tablename__ = "credenciales_proveedores_ia"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    modelo: Mapped[str] = mapped_column(String(120), nullable=False)
    base_url: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    encrypted_api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    key_hint: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    es_activa: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    ultimo_test_ok: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    ultimo_test_en: Mapped[Optional[datetime]] = mapped_column(DATETIME2, nullable=True)
    creado_por_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DATETIME2, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME2, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ConfiguracionSMTP(Base):
    """Perfil cifrado de servidor SMTP para despacho de correos institucionales."""

    __tablename__ = "configuracion_smtp"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    host: Mapped[str] = mapped_column(String(200), nullable=False)
    port: Mapped[int] = mapped_column(Integer, default=587, nullable=False)
    use_tls: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    use_ssl: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    username: Mapped[str] = mapped_column(String(200), nullable=False)
    from_email: Mapped[str] = mapped_column(String(200), nullable=False)
    from_name: Mapped[str] = mapped_column(
        String(150), default="Sistema DSS Campus San Francisco UCT", nullable=False
    )
    encrypted_password: Mapped[str] = mapped_column(Text, nullable=False)
    password_hint: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    es_activa: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    ultimo_test_ok: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    ultimo_test_en: Mapped[Optional[datetime]] = mapped_column(DATETIME2, nullable=True)
    creado_por_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DATETIME2, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME2, server_default=func.now(), onupdate=func.now(), nullable=False
    )


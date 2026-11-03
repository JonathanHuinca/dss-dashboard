from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class UsuarioRol(Base):
    __tablename__ = "usuarios_roles"

    usuario_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), primary_key=True
    )
    rol_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    usuario: Mapped["Usuario"] = relationship("Usuario", back_populates="usuario_roles")
    rol: Mapped["Rol"] = relationship("Rol", back_populates="usuario_roles")


class Rol(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    descripcion: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    rate_limit_quota: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, default="10/day")
    cooldown_segundos: Mapped[int] = mapped_column(Integer, nullable=False, default=10)

    usuario_roles: Mapped[List[UsuarioRol]] = relationship(
        "UsuarioRol", back_populates="rol", cascade="all, delete-orphan"
    )
    usuarios: Mapped[List["Usuario"]] = relationship(
        "Usuario",
        secondary="usuarios_roles",
        back_populates="roles",
        viewonly=True,
        overlaps="rol,usuario_roles",
    )


from sqlalchemy import JSON

class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    nombre_completo: Mapped[str] = mapped_column(String(150), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allowed_datasets: Mapped[List[str]] = mapped_column(
        JSON, default=lambda: ["biblioteca", "estacionamiento"], nullable=False
    )
    can_use_ai: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_export: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_ingest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    espacio_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("espacios.id", ondelete="SET NULL"), nullable=True
    )
    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    intentos_fallidos_login: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bloqueado_hasta: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    usuario_roles: Mapped[List[UsuarioRol]] = relationship(
        "UsuarioRol", back_populates="usuario", cascade="all, delete-orphan", lazy="selectin"
    )
    roles: Mapped[List[Rol]] = relationship(
        "Rol",
        secondary="usuarios_roles",
        back_populates="usuarios",
        lazy="selectin",
        overlaps="rol,usuario,usuario_roles",
    )
    created_by_user: Mapped[Optional["Usuario"]] = relationship(
        "Usuario", remote_side="Usuario.id", foreign_keys=[created_by_user_id]
    )
    tokens_activacion: Mapped[List["TokenActivacion"]] = relationship(
        "TokenActivacion", back_populates="usuario", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def primary_role(self) -> str:
        if self.roles:
            role_names = [r.nombre for r in self.roles]
            for priority_role in [
                "Admin_Sistema",
                "SuperAdmin",
                "Director_Recinto",
                "Directivo",
                "Analista_Consulta",
                "Consultor_Reporte",
                "Guardia_Seguridad",
            ]:
                if priority_role in role_names:
                    return priority_role
            return self.roles[0].nombre
        return "Guardia_Seguridad"


class TokenActivacion(Base):
    __tablename__ = "tokens_activacion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tipo_token: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVACION_INICIAL")
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    utilizado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fecha_utilizacion: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ip_solicitante: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    usuario: Mapped["Usuario"] = relationship("Usuario", back_populates="tokens_activacion")


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


from sqlalchemy.dialects.postgresql import JSONB

class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    nombre_completo: Mapped[str] = mapped_column(String(150), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allowed_datasets: Mapped[List[str]] = mapped_column(
        JSONB, default=lambda: ["biblioteca", "estacionamiento"], nullable=False
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

    @property
    def primary_role(self) -> str:
        if self.roles:
            return self.roles[0].nombre
        return "Guardia_Seguridad"

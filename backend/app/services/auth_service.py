import bcrypt
if not hasattr(bcrypt, "__about__"):
    bcrypt.__about__ = type("about", (), {"__version__": getattr(bcrypt, "__version__", "4.0.0")})
import passlib.handlers.bcrypt
passlib.handlers.bcrypt._BcryptBackend._finalize_backend_mixin = classmethod(
    lambda cls, name, dryrun=False: True
)

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import jwt
from fastapi import HTTPException, status
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.domain.auth_models import Rol, Usuario, UsuarioRol
from app.schemas.auth_schemas import UsuarioCreate

DEFAULT_ROLES: tuple[str, ...] = ("SuperAdmin", "Directivo", "Guardia_Seguridad")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    user_id: int,
    rol: str,
    roles: Optional[List[str]] = None,
    allowed_datasets: Optional[List[str]] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "user_id": user_id,
        "rol": rol,
        "roles": roles if roles is not None else [rol],
        "allowed_datasets": allowed_datasets if allowed_datasets is not None else ["biblioteca", "estacionamiento"],
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def seed_default_roles(db: AsyncSession) -> List[Rol]:
    created_roles: List[Rol] = []
    descriptions: Dict[str, str] = {
        "SuperAdmin": "Acceso total administrativo y configuraciones de sistema",
        "Directivo": "Visualización ejecutiva de dashboards, aforos y reportes analíticos",
        "Guardia_Seguridad": "Monitoreo operativo de accesos, alertas y patentes vehiculares",
    }
    for role_name in DEFAULT_ROLES:
        stmt = select(Rol).where(Rol.nombre == role_name)
        result = await db.execute(stmt)
        role = result.scalar_one_or_none()
        if not role:
            role = Rol(nombre=role_name, descripcion=descriptions.get(role_name, ""))
            db.add(role)
            created_roles.append(role)
    if created_roles:
        await db.commit()
    return created_roles


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[Usuario]:
    stmt = (
        select(Usuario)
        .where(Usuario.id == user_id)
        .options(selectinload(Usuario.roles), selectinload(Usuario.usuario_roles))
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[Usuario]:
    stmt = (
        select(Usuario)
        .where(Usuario.email == email)
        .options(selectinload(Usuario.roles), selectinload(Usuario.usuario_roles))
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def authenticate_user(
    db: AsyncSession, email: str, password: str
) -> Optional[Usuario]:
    user = await get_user_by_email(db, email)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


async def create_user(db: AsyncSession, user_in: UsuarioCreate) -> Usuario:
    hashed_pwd = hash_password(user_in.password)
    user = Usuario(
        email=user_in.email,
        hashed_password=hashed_pwd,
        nombre_completo=user_in.nombre_completo,
        is_active=user_in.is_active,
        allowed_datasets=user_in.allowed_datasets,
    )
    db.add(user)
    await db.flush()

    for role_name in user_in.roles:
        stmt = select(Rol).where(Rol.nombre == role_name)
        result = await db.execute(stmt)
        role_obj = result.scalar_one_or_none()
        if not role_obj:
            role_obj = Rol(nombre=role_name, descripcion=None)
            db.add(role_obj)
            await db.flush()
        user_role = UsuarioRol(usuario_id=user.id, rol_id=role_obj.id)
        db.add(user_role)

    await db.commit()
    await db.refresh(user)
    return user


async def update_user_status(db: AsyncSession, user_id: int, is_active: bool) -> Optional[Usuario]:
    user = await get_user_by_id(db, user_id)
    if not user:
        return None
    user.is_active = is_active
    await db.commit()
    await db.refresh(user)
    return user


async def list_users(db: AsyncSession) -> List[Usuario]:
    stmt = (
        select(Usuario)
        .options(selectinload(Usuario.roles), selectinload(Usuario.usuario_roles))
        .order_by(Usuario.id)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())

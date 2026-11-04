import hmac
import hashlib
from datetime import datetime, timedelta, timezone
from ipaddress import IPv4Address, IPv4Network
from typing import Any, Callable, Dict, List, Optional, Union

from fastapi import Depends, HTTPException, Request, status, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from cryptography.fernet import Fernet

from app.core.config import settings
from app.core.database import get_db
from app.domain.auth_models import Usuario
from app.services.auth_service import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    get_user_by_id,
    normalizar_rol,
    ROL_ALIAS_MAP,
)

bearer_scheme = HTTPBearer(auto_error=True)


# ---------------------------------------------------------------------------
# Dependencias de Autenticación y Control de Acceso RBAC (RF22)
# ---------------------------------------------------------------------------
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Usuario:
    token = credentials.credentials
    payload = decode_access_token(token)
    user_id = payload.get("user_id")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales de autenticación no válidas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await get_user_by_id(db, user_id=int(user_id))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inactivo",
        )
    return user


def require_roles(allowed_roles: Union[List[str], tuple]) -> Callable:
    """
    Guard que verifica si el usuario autenticado posee alguno de los roles permitidos,
    aplicando normalización de alias institucionales.
    """
    normalized_allowed = {normalizar_rol(r) for r in allowed_roles}

    async def role_checker(
        current_user: Usuario = Depends(get_current_user),
    ) -> Usuario:
        user_roles = {normalizar_rol(r.nombre) for r in current_user.roles}
        if "Admin_Sistema" not in user_roles and not user_roles.intersection(normalized_allowed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permisos insuficientes para realizar esta acción",
            )
        return current_user

    return role_checker


def require_role(*allowed_roles: str) -> Callable:
    """Wrapper para compatibilidad con firmas de argumentos variables."""
    return require_roles(list(allowed_roles))


def require_permission(permission_flag: str) -> Callable:
    """
    Guard que valida banderas booleanas de permisos modulares (can_use_ai, can_export, can_ingest).
    Admin_Sistema siempre posee autorización activa.
    """
    async def permission_checker(
        current_user: Usuario = Depends(get_current_user),
    ) -> Usuario:
        user_roles = {normalizar_rol(r.nombre) for r in current_user.roles}
        if "Admin_Sistema" not in user_roles and not getattr(current_user, permission_flag, False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permiso insuficiente: se requiere la facultad '{permission_flag}'",
            )
        return current_user

    return permission_checker


def validar_acceso_espacio(espacio_id: int, current_user: Usuario) -> None:
    """
    Valida que los roles acotados a recinto (Director_Recinto, Guardia_Seguridad)
    únicamente operen sobre su espacio institucional asignado, y comprueba que
    el usuario posea autorización en allowed_datasets (Ley N° 21.719 / RBAC).
    """
    user_roles = {normalizar_rol(r.nombre) for r in current_user.roles}
    if "Admin_Sistema" in user_roles:
        return

    if ("Director_Recinto" in user_roles or "Guardia_Seguridad" in user_roles) and current_user.espacio_id is not None:
        if current_user.espacio_id != espacio_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado: usuario asignado al recinto {current_user.espacio_id}, no al recinto {espacio_id}",
            )

    modulo_por_espacio = {1: "biblioteca", 2: "estacionamiento"}
    dataset_nombre = modulo_por_espacio.get(espacio_id)
    if dataset_nombre and current_user.allowed_datasets:
        permitidos = [d.lower() for d in current_user.allowed_datasets]
        if dataset_nombre not in permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado: su usuario no cuenta con autorización para acceder al módulo '{dataset_nombre}'",
            )


# ---------------------------------------------------------------------------
# Funciones Criptográficas y Anonimización (Ley N° 21.719)
# ---------------------------------------------------------------------------
def pseudonymize_person(person_id: str) -> str:
    return hmac.new(
        settings.SALT_PERSON_SECRET.encode(),
        person_id.encode(),
        hashlib.sha256,
    ).hexdigest()


def pseudonymize_vehicle(patente: str) -> str:
    return hmac.new(
        settings.SALT_VEHICLE_SECRET.encode(),
        patente.encode(),
        hashlib.sha256,
    ).hexdigest()


def encrypt_vehicle_patente(patente: str) -> tuple[str, str]:
    patente_hash = pseudonymize_vehicle(patente)
    if not settings.FERNET_KEY or not settings.FERNET_KEY.strip():
        raise ValueError("FERNET_KEY no está configurada en las variables de entorno.")
    f = Fernet(settings.FERNET_KEY.strip().encode())
    patente_cifrada = f.encrypt(patente.encode()).decode()
    return patente_hash, patente_cifrada


import ipaddress

ALLOWED_SUBNETS = [ipaddress.ip_network(s) for s in settings.allowed_subnets_list]


async def ip_whitelist_middleware(request: Request, call_next):
    if settings.ENABLE_IP_WHITELIST:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            raw_ip = forwarded.split(",")[0].strip()
        else:
            raw_ip = request.client.host if request.client else "127.0.0.1"

        try:
            client_ip = ipaddress.ip_address(raw_ip)
        except ValueError:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Acceso restringido a red institucional UCT", "code": "IP_NOT_ALLOWED"},
            )
        if not any(client_ip in net for net in ALLOWED_SUBNETS):
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Acceso restringido a red institucional UCT", "code": "IP_NOT_ALLOWED"},
            )
    return await call_next(request)

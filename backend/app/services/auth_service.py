import bcrypt
if not hasattr(bcrypt, "__about__"):
    bcrypt.__about__ = type("about", (), {"__version__": getattr(bcrypt, "__version__", "4.0.0")})
import passlib.handlers.bcrypt
passlib.handlers.bcrypt._BcryptBackend._finalize_backend_mixin = classmethod(
    lambda cls, name, dryrun=False: True
)

from datetime import datetime, timedelta, timezone
import hashlib
import re
import secrets
from typing import Any, Dict, List, Optional

import jwt
from fastapi import HTTPException, status
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.cache import TTLCache
from app.core.config import settings
from app.domain.auth_models import Rol, TokenActivacion, Usuario, UsuarioRol
from app.schemas.auth_schemas import UsuarioCreate, UsuarioInviteRequest

# Caché en memoria de sesiones de usuario para evitar consultas repetitivas por petición
cache_usuarios_sesion: TTLCache = TTLCache(maxsize=256, ttl=60)


def limpiar_cache_usuario(usuario_id: Optional[int] = None) -> None:
    if usuario_id is not None:
        cache_usuarios_sesion.pop(usuario_id, None)
    else:
        cache_usuarios_sesion.clear()

# Mapeo de alias para compatibilidad total con roles institucionales
ROL_ALIAS_MAP: Dict[str, str] = {
    "superadmin": "Admin_Sistema",
    "admin_sistema": "Admin_Sistema",
    "directivo": "Director_Recinto",
    "director_recinto": "Director_Recinto",
    "analista_consulta": "Analista_Consulta",
    "analista": "Analista_Consulta",
    "consultor_reporte": "Consultor_Reporte",
    "consultor": "Consultor_Reporte",
    "guardia_seguridad": "Guardia_Seguridad",
    "guardia": "Guardia_Seguridad",
}


def normalizar_rol(rol: str) -> str:
    """Normaliza alias de roles a la jerarquía formal institucional."""
    return ROL_ALIAS_MAP.get(rol.strip().lower(), rol.strip())


DEFAULT_ROLES: tuple[str, ...] = (
    "Admin_Sistema",
    "Director_Recinto",
    "Analista_Consulta",
    "Consultor_Reporte",
    "Guardia_Seguridad",
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def validar_complejidad_password(password: str) -> None:
    """
    Valida las reglas institucionales de complejidad de contraseñas (RF27):
    - Longitud mínima de 8 caracteres
    - Al menos una letra mayúscula
    - Al menos un dígito numérico
    - Al menos un caracter especial
    """
    if len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña debe tener un mínimo de 8 caracteres.",
        )
    if not re.search(r"[A-Z]", password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña debe contener al menos una letra mayúscula.",
        )
    if not re.search(r"[0-9]", password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña debe contener al menos un dígito numérico.",
        )
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>\-_=+[\];/~`]", password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña debe contener al menos un caracter especial (!@#$%...).",
        )


def generar_token_activacion() -> tuple[str, str]:
    """
    Genera un token efímero de alta entropía y su hash SHA-256.
    Retorna (token_en_texto_plano, token_hash_sha256).
    """
    token_plano = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token_plano.encode("utf-8")).hexdigest()
    return token_plano, token_hash


def create_access_token(
    user_id: int,
    rol: str,
    roles: Optional[List[str]] = None,
    allowed_datasets: Optional[List[str]] = None,
    can_use_ai: bool = False,
    can_export: bool = False,
    can_ingest: bool = False,
    espacio_id: Optional[int] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    normalized_rol = normalizar_rol(rol)
    normalized_roles = [normalizar_rol(r) for r in (roles if roles is not None else [rol])]

    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "user_id": user_id,
        "rol": normalized_rol,
        "roles": normalized_roles,
        "allowed_datasets": allowed_datasets if allowed_datasets is not None else ["biblioteca", "estacionamiento"],
        "can_use_ai": can_use_ai,
        "can_export": can_export,
        "can_ingest": can_ingest,
        "espacio_id": espacio_id,
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
    descriptions: Dict[str, Dict[str, str]] = {
        "Admin_Sistema": {
            "desc": "SuperAdmin técnico global con control total de la plataforma y administración de usuarios",
            "quota": "1000/day",
        },
        "Director_Recinto": {
            "desc": "Jefatura de espacio físico asignado con administración delegada de analistas y guardias",
            "quota": "500/day",
        },
        "Analista_Consulta": {
            "desc": "Decanos, directores de carrera y analistas con acceso a dashboards y modelos analíticos",
            "quota": "200/day",
        },
        "Consultor_Reporte": {
            "desc": "Solicitante institucional con acceso exclusivo a su bandeja de reportes ejecutivos compartidos",
            "quota": "50/day",
        },
        "Guardia_Seguridad": {
            "desc": "Operador en terreno para monitoreo operativo de aforos y tránsito en su recinto asignado",
            "quota": "50/day",
        },
    }
    for role_name in DEFAULT_ROLES:
        stmt = select(Rol).where(Rol.nombre == role_name)
        result = await db.execute(stmt)
        role = result.scalar_one_or_none()
        if not role:
            info = descriptions.get(role_name, {"desc": "", "quota": "10/day"})
            role = Rol(nombre=role_name, descripcion=info["desc"], rate_limit_quota=info["quota"])
            db.add(role)
            created_roles.append(role)
    if created_roles:
        await db.commit()
    return created_roles


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[Usuario]:
    if user_id in cache_usuarios_sesion:
        return cache_usuarios_sesion[user_id]
    stmt = (
        select(Usuario)
        .where(Usuario.id == user_id)
        .options(selectinload(Usuario.roles), selectinload(Usuario.usuario_roles))
    )
    result = await db.execute(stmt)
    usuario = result.scalar_one_or_none()
    if usuario is not None:
        cache_usuarios_sesion[user_id] = usuario
    return usuario


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

    # Verificar si la cuenta se encuentra bloqueada por fuerza bruta
    ahora = datetime.now(timezone.utc)
    if user.bloqueado_hasta:
        bloqueo = user.bloqueado_hasta
        if bloqueo.tzinfo is None:
            bloqueo = bloqueo.replace(tzinfo=timezone.utc)
        if ahora < bloqueo:
            segundos_restantes = int((bloqueo - ahora).total_seconds())
            minutos = max(1, (segundos_restantes + 59) // 60)
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=f"Cuenta temporalmente bloqueada por seguridad tras 5 intentos fallidos consecutivos (OWASP ASVS). Intente de nuevo en {minutos} minuto(s) o use la opción de recuperación de contraseña.",
            )
        else:
            # Si el tiempo de bloqueo ya expiró, restablecer preventivamente el contador
            user.bloqueado_hasta = None
            user.intentos_fallidos_login = 0
            await db.commit()

    # No permitir autenticación si la cuenta está pendiente de activación
    if user.hashed_password == "PENDIENTE_ACTIVACION" or not user.hashed_password.startswith("$2"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Su cuenta se encuentra inactiva o pendiente de activación. Use el enlace de activación enviado a su correo institucional.",
        )

    # Validar contraseña
    if not verify_password(password, user.hashed_password):
        user.intentos_fallidos_login = (user.intentos_fallidos_login or 0) + 1
        if user.intentos_fallidos_login >= 5:
            user.bloqueado_hasta = ahora + timedelta(minutes=15)
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="Cuenta bloqueada preventivamente tras 5 intentos erróneos consecutivos (OWASP ASVS). Puede restablecer su contraseña mediante la opción '¿Olvidó su contraseña?' o esperar 15 minutos.",
            )
        else:
            await db.commit()
            intentos_restantes = 5 - user.intentos_fallidos_login
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Correo electrónico o contraseña incorrectos. Le quedan {intentos_restantes} intento(s) antes del bloqueo de seguridad.",
            )

    # Autenticación exitosa: resetear contadores de fallo
    if (user.intentos_fallidos_login or 0) > 0 or user.bloqueado_hasta is not None:
        user.intentos_fallidos_login = 0
        user.bloqueado_hasta = None
        await db.commit()

    return user


async def create_user(
    db: AsyncSession, user_in: UsuarioCreate, creator: Optional[Usuario] = None
) -> Usuario:
    """
    Crea un nuevo usuario aplicando reglas de administración delegada (RF22).
    """
    assigned_roles = [normalizar_rol(r) for r in user_in.roles]
    created_by_user_id = user_in.created_by_user_id
    espacio_id = user_in.espacio_id

    if creator:
        creator_roles = [normalizar_rol(r.nombre) for r in creator.roles]
        if "Admin_Sistema" in creator_roles:
            created_by_user_id = creator.id
        elif "Director_Recinto" in creator_roles:
            # Restricción delegada: únicamente Analista_Consulta acotado a su propio recinto
            for r in assigned_roles:
                if r != "Analista_Consulta":
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Los Directores de Recinto solo pueden crear usuarios con rol Analista de Consulta.",
                    )
            espacio_id = creator.espacio_id
            created_by_user_id = creator.id
            # Forzar dataset según el recinto del director
            if creator.espacio_id == 1:
                allowed_datasets = ["biblioteca"]
            elif creator.espacio_id == 2:
                allowed_datasets = ["estacionamiento"]
            else:
                allowed_datasets = creator.allowed_datasets or ["biblioteca"]
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permisos para crear usuarios en el sistema.",
            )

    # Configuración de permisos modulares por omisión según rol institucional
    can_use_ai = user_in.can_use_ai
    can_export = user_in.can_export
    can_ingest = user_in.can_ingest

    if "Admin_Sistema" in assigned_roles or "Director_Recinto" in assigned_roles:
        can_use_ai = True
        can_export = True
        can_ingest = True
    elif "Analista_Consulta" in assigned_roles:
        can_use_ai = True
        can_export = True

    final_allowed_datasets = user_in.allowed_datasets
    if creator and "Director_Recinto" in creator_roles:
        final_allowed_datasets = allowed_datasets

    hashed_pwd = hash_password(user_in.password)
    user = Usuario(
        email=user_in.email,
        hashed_password=hashed_pwd,
        nombre_completo=user_in.nombre_completo,
        is_active=user_in.is_active,
        allowed_datasets=final_allowed_datasets,
        can_use_ai=can_use_ai,
        can_export=can_export,
        can_ingest=can_ingest,
        espacio_id=espacio_id,
        created_by_user_id=created_by_user_id,
    )
    db.add(user)
    await db.flush()

    for role_name in assigned_roles:
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


async def update_user_status(
    db: AsyncSession,
    user_id: int,
    is_active: Optional[bool] = None,
    can_use_ai: Optional[bool] = None,
    current_user: Optional[Usuario] = None,
) -> Optional[Usuario]:
    limpiar_cache_usuario(user_id)
    user = await get_user_by_id(db, user_id)
    if not user:
        return None

    if current_user:
        creator_roles = [normalizar_rol(r.nombre) for r in current_user.roles]
        if "Admin_Sistema" not in creator_roles:
            if "Director_Recinto" in creator_roles:
                target_roles = [normalizar_rol(r.nombre) for r in user.roles]
                if "Admin_Sistema" in target_roles or "Director_Recinto" in target_roles:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="No tiene permisos para modificar el estado de usuarios con jerarquía superior o equivalente.",
                    )
                if user.created_by_user_id != current_user.id and user.espacio_id != current_user.espacio_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Solo puede modificar el estado de usuarios de su propio recinto.",
                    )
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No tiene permisos para modificar usuarios.",
                )

    if is_active is not None:
        user.is_active = is_active
    if can_use_ai is not None:
        user.can_use_ai = can_use_ai
    await db.commit()
    await db.refresh(user)
    return user
    limpiar_cache_usuario(user_id)
    return user


async def list_users(db: AsyncSession, current_user: Optional[Usuario] = None) -> List[Usuario]:
    stmt = (
        select(Usuario)
        .options(selectinload(Usuario.roles), selectinload(Usuario.usuario_roles))
        .order_by(Usuario.id)
    )

    if current_user:
        user_roles = [normalizar_rol(r.nombre) for r in current_user.roles]
        if "Admin_Sistema" not in user_roles:
            if "Director_Recinto" in user_roles:
                stmt = stmt.where(
                    (Usuario.created_by_user_id == current_user.id)
                    | (Usuario.espacio_id == current_user.espacio_id)
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No tiene permisos para listar usuarios del sistema.",
                )

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def invitar_usuario(
    db: AsyncSession,
    invite_in: UsuarioInviteRequest,
    creator: Optional[Usuario] = None,
) -> tuple[Usuario, str, TokenActivacion]:
    """
    Registra un usuario inactivo con contraseña 'PENDIENTE_ACTIVACION' y genera
    un token efímero en tokens_activacion según RF27 (Zero-Plaintext).
    """
    assigned_roles = [normalizar_rol(r) for r in invite_in.roles]
    created_by_user_id = None
    espacio_id = invite_in.espacio_id

    if creator:
        creator_roles = [normalizar_rol(r.nombre) for r in creator.roles]
        if "Admin_Sistema" in creator_roles:
            created_by_user_id = creator.id
        elif "Director_Recinto" in creator_roles:
            for r in assigned_roles:
                if r not in ("Analista_Consulta", "Guardia_Seguridad"):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Los Directores de Recinto solo pueden invitar usuarios con rol Analista_Consulta o Guardia_Seguridad.",
                    )
            espacio_id = creator.espacio_id
            created_by_user_id = creator.id
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permisos para invitar usuarios en el sistema.",
            )

    can_use_ai = invite_in.can_use_ai
    can_export = invite_in.can_export
    can_ingest = invite_in.can_ingest

    if "Admin_Sistema" in assigned_roles or "Director_Recinto" in assigned_roles:
        can_use_ai = True
        can_export = True
        can_ingest = True
    elif "Analista_Consulta" in assigned_roles:
        can_use_ai = True
        can_export = True

    # Persistir usuario en estado inactivo sin credencial en texto plano
    user = Usuario(
        email=invite_in.email,
        hashed_password="PENDIENTE_ACTIVACION",
        nombre_completo=invite_in.nombre_completo,
        is_active=False,
        allowed_datasets=invite_in.allowed_datasets,
        can_use_ai=can_use_ai,
        can_export=can_export,
        can_ingest=can_ingest,
        espacio_id=espacio_id,
        created_by_user_id=created_by_user_id,
    )
    db.add(user)
    await db.flush()

    for role_name in assigned_roles:
        stmt_role = select(Rol).where(Rol.nombre == role_name)
        res_role = await db.execute(stmt_role)
        role_obj = res_role.scalar_one_or_none()
        if role_obj:
            db.add(UsuarioRol(usuario_id=user.id, rol_id=role_obj.id))

    await db.flush()

    # Generación y almacenamiento del token efímero con vigencia de 1 hora
    token_plano, token_hash = generar_token_activacion()
    expira_en = datetime.now(timezone.utc) + timedelta(hours=1)

    token_obj = TokenActivacion(
        usuario_id=user.id,
        token_hash=token_hash,
        tipo_token="ACTIVACION_INICIAL",
        expira_en=expira_en,
        utilizado=False,
    )
    db.add(token_obj)
    await db.commit()

    user_refreshed = await get_user_by_id(db, user.id)
    return user_refreshed or user, token_plano, token_obj


async def reenviar_invitacion_usuario(
    db: AsyncSession,
    user_id: int,
    creator: Optional[Usuario] = None,
) -> tuple[Usuario, str, TokenActivacion]:
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )
    if creator:
        creator_roles = [normalizar_rol(r.nombre) for r in creator.roles]
        if "Admin_Sistema" not in creator_roles:
            if "Director_Recinto" in creator_roles:
                target_roles = [normalizar_rol(r.nombre) for r in user.roles]
                if "Admin_Sistema" in target_roles or "Director_Recinto" in target_roles:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="No tiene permisos para gestionar invitaciones de usuarios con jerarquía superior o equivalente.",
                    )
                if user.created_by_user_id != creator.id and user.espacio_id != creator.espacio_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Solo puede gestionar usuarios de su propio recinto.",
                    )
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No tiene permisos para gestionar usuarios.",
                )

    tipo_token = "ACTIVACION_INICIAL" if not user.is_active else "RECUPERACION_PASSWORD"
    token_plano, token_hash = generar_token_activacion()
    expira_en = datetime.now(timezone.utc) + timedelta(hours=48)

    token_obj = TokenActivacion(
        usuario_id=user.id,
        token_hash=token_hash,
        tipo_token=tipo_token,
        expira_en=expira_en,
        utilizado=False,
    )
    db.add(token_obj)
    await db.commit()
    return user, token_plano, token_obj


async def verificar_token_activacion(
    db: AsyncSession,
    token: str,
) -> tuple[TokenActivacion, Usuario]:
    """
    Verifica un token SHA-256 de activación o recuperación.
    Valida existencia, que no esté utilizado y que no haya expirado.
    """
    token_hash = hashlib.sha256(token.strip().encode("utf-8")).hexdigest()
    stmt = (
        select(TokenActivacion)
        .where(TokenActivacion.token_hash == token_hash)
        .options(selectinload(TokenActivacion.usuario).selectinload(Usuario.roles))
    )
    result = await db.execute(stmt)
    token_obj = result.scalar_one_or_none()

    if not token_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El enlace de activación es inválido o no existe en el sistema.",
        )

    if token_obj.utilizado:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este enlace de activación ya fue utilizado previamente. Solicite uno nuevo si requiere restablecer su acceso.",
        )

    ahora = datetime.now(timezone.utc)
    expira = token_obj.expira_en
    if expira.tzinfo is None:
        expira = expira.replace(tzinfo=timezone.utc)
    if ahora > expira:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El enlace de activación ha expirado (validez: 1 hora). Contacte al administrador para recibir un nuevo enlace.",
        )

    usuario = token_obj.usuario
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró la cuenta de usuario asociada a este enlace.",
        )

    return token_obj, usuario


async def activar_cuenta_usuario(
    db: AsyncSession,
    token: str,
    nueva_password: str,
    confirmar_password: str,
    ip_solicitante: Optional[str] = None,
) -> Usuario:
    """
    Activa la cuenta del usuario en una transacción atómica:
    - Valida fortaleza de la contraseña y coincidencia
    - Verifica vigencia y no reutilización del token
    - Actualiza hash bcrypt y activa la cuenta
    - Marca el token como utilizado con fecha e IP
    """
    if nueva_password != confirmar_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Las contraseñas ingresadas no coinciden.",
        )

    validar_complejidad_password(nueva_password)

    token_obj, usuario = await verificar_token_activacion(db, token)

    usuario.hashed_password = hash_password(nueva_password)
    usuario.is_active = True

    token_obj.utilizado = True
    token_obj.fecha_utilizacion = datetime.now(timezone.utc)
    if ip_solicitante:
        token_obj.ip_solicitante = ip_solicitante

    await db.commit()
    await db.refresh(usuario)
    return usuario


async def solicitar_recuperacion_password(
    db: AsyncSession,
    email: str,
    ip_solicitante: Optional[str] = None,
) -> tuple[bool, Optional[str], Optional[datetime], Optional[str]]:
    """
    Inicia el flujo de recuperación de credenciales según OWASP ASVS (RF27).
    Genera un token efímero de un solo uso con caducidad de 15 minutos almacenado
    en SHA-256 en tokens_activacion.
    """
    user = await get_user_by_email(db, email.strip().lower())
    if not user:
        # Prevención de enumeración de usuarios: respuesta silenciosa
        return False, None, None, None

    token_plano, token_hash = generar_token_activacion()
    expira_en = datetime.now(timezone.utc) + timedelta(minutes=15)

    token_obj = TokenActivacion(
        usuario_id=user.id,
        token_hash=token_hash,
        tipo_token="RECUPERACION_PASSWORD",
        expira_en=expira_en,
        utilizado=False,
        ip_solicitante=ip_solicitante,
    )
    db.add(token_obj)
    await db.commit()

    return True, token_plano, expira_en, user.nombre_completo


async def restablecer_password_con_token(
    db: AsyncSession,
    token: str,
    nueva_password: str,
    confirmar_password: str,
    ip_solicitante: Optional[str] = None,
) -> Usuario:
    """
    Restablece la credencial del usuario y desbloquea preventivamente la cuenta:
    - Valida coincidencia y complejidad de contraseña
    - Verifica vigencia, tipo y no reutilización del token
    - Actualiza hash bcrypt (12 rondas)
    - Desbloquea la cuenta y resetea el contador de fuerza bruta a 0
    - Marca el token como consumido
    """
    if nueva_password != confirmar_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Las contraseñas ingresadas no coinciden.",
        )

    validar_complejidad_password(nueva_password)

    token_obj, usuario = await verificar_token_activacion(db, token)

    if token_obj.tipo_token not in ("RECUPERACION_PASSWORD", "ACTIVACION_INICIAL"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El tipo de token suministrado no es válido para restablecer la contraseña.",
        )

    # Actualizar credencial y desbloquear cuenta
    usuario.hashed_password = hash_password(nueva_password)
    usuario.is_active = True
    usuario.intentos_fallidos_login = 0
    usuario.bloqueado_hasta = None

    token_obj.utilizado = True
    token_obj.fecha_utilizacion = datetime.now(timezone.utc)
    if ip_solicitante:
        token_obj.ip_solicitante = ip_solicitante

    await db.commit()
    await db.refresh(usuario)
    limpiar_cache_usuario(usuario.id)
    return usuario


async def desbloquear_cuenta_admin(
    db: AsyncSession,
    user_id: int,
    current_user: Usuario,
) -> Usuario:
    """
    Desbloqueo administrativo de cuentas con control RBAC delegado (RF22, RF27).
    """
    limpiar_cache_usuario(user_id)
    usuario = await get_user_by_id(db, user_id)
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado en el sistema.",
        )

    creator_roles = [normalizar_rol(r.nombre) for r in current_user.roles]
    if "Admin_Sistema" not in creator_roles:
        if "Director_Recinto" in creator_roles:
            if usuario.espacio_id != current_user.espacio_id and usuario.created_by_user_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Solo puede desbloquear cuentas pertenecientes a su recinto asignado.",
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No cuenta con facultades administrativas para desbloquear usuarios.",
            )

    usuario.intentos_fallidos_login = 0
    usuario.bloqueado_hasta = None
    await db.commit()
    await db.refresh(usuario)
    limpiar_cache_usuario(user_id)
    return usuario


async def eliminar_usuario_cuenta(
    db: AsyncSession,
    usuario_id: int,
    admin_solicitante: Usuario,
) -> bool:
    """
    Eliminación permanente de cuenta de usuario exclusiva para Super Administrador UCT (RF27).
    Impide la autoeliminación y gestiona la eliminación en cascada de roles y tokens asociados.
    """
    roles_solicitante = [normalizar_rol(r.nombre) for r in admin_solicitante.roles]
    if "Admin_Sistema" not in roles_solicitante:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo un Super Administrador UCT tiene facultades para eliminar cuentas del sistema.",
        )

    if admin_solicitante.id == usuario_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Un Super Administrador no puede eliminar su propia cuenta activa.",
        )

    limpiar_cache_usuario(usuario_id)
    usuario = await get_user_by_id(db, usuario_id)
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El usuario a eliminar no existe en el sistema.",
        )

    from sqlalchemy import delete, func
    from app.domain.auth_models import UsuarioRol, TokenActivacion
    from app.domain.reportes_compartidos_models import (
        AuditoriaAccesoReporte,
        DestinatarioReporte,
        ReporteCompartido,
    )

    email_usr = (usuario.email or "").strip().lower()
    if email_usr:
        stmt_dest = select(DestinatarioReporte.id).where(func.lower(DestinatarioReporte.email) == email_usr)
        dest_ids = list((await db.execute(stmt_dest)).scalars().all())
        if dest_ids:
            stmt_reps = select(ReporteCompartido.id).where(ReporteCompartido.destinatario_id.in_(dest_ids))
            rep_ids = list((await db.execute(stmt_reps)).scalars().all())
            if rep_ids:
                await db.execute(
                    delete(AuditoriaAccesoReporte).where(AuditoriaAccesoReporte.reporte_id.in_(rep_ids))
                )
                await db.execute(
                    delete(ReporteCompartido).where(ReporteCompartido.id.in_(rep_ids))
                )
            await db.execute(delete(DestinatarioReporte).where(DestinatarioReporte.id.in_(dest_ids)))

    await db.execute(delete(TokenActivacion).where(TokenActivacion.usuario_id == usuario_id))
    await db.execute(delete(UsuarioRol).where(UsuarioRol.usuario_id == usuario_id))
    await db.execute(delete(Usuario).where(Usuario.id == usuario_id))
    await db.commit()
    limpiar_cache_usuario(usuario_id)
    return True





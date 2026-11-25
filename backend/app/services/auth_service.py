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
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.cache import TTLCache
from app.core.config import obtener_url_frontend, settings
from app.core.tiempo import ahora_chile_naive
from app.domain.auth_models import NotificacionAdmin, Rol, TokenActivacion, Usuario, UsuarioRol
from app.domain.reportes_compartidos_models import DestinatarioReporte
from app.schemas.auth_schemas import UsuarioCreate, UsuarioInviteRequest, UsuarioUpdateRequest
from app.services.email_service import enviar_correo_bloqueo_login

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
    pw_bytes = password.encode("utf-8")[:72]
    try:
        import bcrypt
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(pw_bytes, salt).decode("utf-8")
    except Exception:
        return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not plain_password or not hashed_password:
        return False
    pw_bytes = plain_password.encode("utf-8")[:72]
    try:
        import bcrypt
        return bcrypt.checkpw(pw_bytes, hashed_password.encode("utf-8"))
    except Exception:
        try:
            return pwd_context.verify(plain_password, hashed_password)
        except Exception:
            return False


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
    nombre_completo: Optional[str] = None,
    email: Optional[str] = None,
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    normalized_rol = normalizar_rol(rol)
    normalized_roles = [normalizar_rol(r) for r in (roles if roles is not None else [rol])]

    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "user_id": user_id,
        "nombre_completo": nombre_completo,
        "email": email,
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
    email_limpio = (email or "").strip().lower()
    stmt = (
        select(Usuario)
        .where(func.lower(func.trim(Usuario.email)) == email_limpio)
        .options(selectinload(Usuario.roles), selectinload(Usuario.usuario_roles))
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def authenticate_user(
    db: AsyncSession,
    email: str,
    password: str,
    ip_origen: Optional[str] = None,
    background_tasks: Any = None,
) -> Optional[Usuario]:
    email_clean = (email or "").strip().lower()
    user = await get_user_by_email(db, email_clean)
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
    es_valida = verify_password(password, user.hashed_password)

    if not es_valida:
        user.intentos_fallidos_login = (user.intentos_fallidos_login or 0) + 1
        if user.intentos_fallidos_login >= 5:
            user.bloqueado_hasta = ahora + timedelta(minutes=15)
            # Registra alerta para SuperAdmin y emite enlace directo de recuperación al usuario
            notificacion = NotificacionAdmin(
                tipo="bloqueo_login",
                titulo="Cuenta bloqueada tras 5 intentos fallidos",
                mensaje=(
                    f"El usuario {user.nombre_completo} ({user.email}) falló 5 veces consecutivas "
                    "al ingresar su contraseña y fue bloqueado por 15 minutos."
                ),
                usuario_afectado_id=user.id,
                usuario_afectado_email=user.email,
                usuario_afectado_nombre=user.nombre_completo,
                intentos_fallidos=int(user.intentos_fallidos_login),
                ip_origen=ip_origen,
                leida=False,
            )
            db.add(notificacion)

            token_plano, token_hash = generar_token_activacion()
            token_obj = TokenActivacion(
                usuario_id=user.id,
                token_hash=token_hash,
                tipo_token="RECUPERACION_PASSWORD",
                expira_en=ahora + timedelta(minutes=15),
                utilizado=False,
                ip_solicitante=ip_origen,
            )
            db.add(token_obj)
            await db.commit()

            if background_tasks is not None:
                enlace = f"{obtener_url_frontend()}/recuperar-password?token={token_plano}"
                background_tasks.add_task(
                    enviar_correo_bloqueo_login,
                    user.email,
                    user.nombre_completo or "",
                    enlace,
                    int(user.intentos_fallidos_login),
                )

            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=(
                    "Cuenta bloqueada preventivamente tras 5 intentos erróneos consecutivos (OWASP ASVS). "
                    "Se envió un enlace de restablecimiento a su correo institucional y se notificó al administrador."
                ),
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

    limpiar_cache_usuario(user.id)
    return user


def _roles_usuario(usuario: Usuario) -> set[str]:
    return {normalizar_rol(r.nombre) for r in (getattr(usuario, "roles", None) or [])}


def _datasets_usuario(usuario: Usuario) -> set[str]:
    datasets = {
        str(d).strip().lower()
        for d in (getattr(usuario, "allowed_datasets", None) or [])
        if str(d).strip().lower() in ("biblioteca", "estacionamiento")
    }
    if not datasets:
        if getattr(usuario, "espacio_id", None) == 1:
            datasets.add("biblioteca")
        elif getattr(usuario, "espacio_id", None) == 2:
            datasets.add("estacionamiento")
    return datasets


def _es_solo_consultor(roles_norm: List[str] | set[str]) -> bool:
    roles_set = {normalizar_rol(r) for r in roles_norm if str(r).strip()}
    return bool(roles_set) and roles_set == {"Consultor_Reporte"}


def _resolver_espacio_por_datasets(
    allowed_datasets: Optional[List[str]],
    roles_norm: List[str] | set[str],
) -> tuple[List[str], Optional[int]]:
    """Deriva allowed_datasets normalizado y el espacio_id coherente (1, 2 o None para ambos)."""
    roles_set = {normalizar_rol(r) for r in roles_norm if str(r).strip()}
    if _es_solo_consultor(roles_set):
        return [], None

    limpios: List[str] = []
    for d in allowed_datasets or []:
        dl = str(d).strip().lower()
        if dl in ("biblioteca", "estacionamiento") and dl not in limpios:
            limpios.append(dl)

    if not limpios:
        if "Admin_Sistema" in roles_set:
            return ["biblioteca", "estacionamiento"], None
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe asignar al menos un módulo autorizado (biblioteca y/o estacionamiento).",
        )

    ds_set = set(limpios)
    if ds_set == {"biblioteca"}:
        return ["biblioteca"], 1
    if ds_set == {"estacionamiento"}:
        return ["estacionamiento"], 2
    return ["biblioteca", "estacionamiento"], None


def _es_gestionable_por_director(director: Usuario, target: Usuario) -> bool:
    """
    Gobernanza Opción A: un Director_Recinto solo puede gestionar usuarios cuyos módulos
    sean subconjunto de los suyos (nunca Admin, otros Directores ni multi-módulo ajenos).
    """
    if target.id == director.id:
        return False
    target_roles = _roles_usuario(target)
    if "Admin_Sistema" in target_roles or "Director_Recinto" in target_roles:
        return False
    if _es_solo_consultor(target_roles):
        return target.created_by_user_id == director.id
    dir_ds = _datasets_usuario(director)
    target_ds = _datasets_usuario(target)
    return bool(target_ds) and target_ds.issubset(dir_ds)


async def _asegurar_destinatario_consultor(db: AsyncSession, usuario: Usuario) -> None:
    email_norm = (usuario.email or "").strip().lower()
    if not email_norm:
        return
    stmt_dest = select(DestinatarioReporte).where(func.lower(DestinatarioReporte.email) == email_norm)
    dest = (await db.execute(stmt_dest)).scalar_one_or_none()
    if not dest:
        ahora = ahora_chile_naive()
        db.add(
            DestinatarioReporte(
                email=email_norm,
                nombre_completo=usuario.nombre_completo,
                cargo="Consultor de Reportes",
                unidad_academica="Universidad Católica de Temuco",
                token_portal=secrets.token_urlsafe(32),
                activo=True,
                creado_en=ahora,
                actualizado_en=ahora,
            )
        )


async def create_user(
    db: AsyncSession, user_in: UsuarioCreate, creator: Optional[Usuario] = None
) -> Usuario:
    """
    Crea un nuevo usuario aplicando reglas de administración delegada (RF22).
    """
    assigned_roles = [normalizar_rol(r) for r in user_in.roles]
    created_by_user_id = user_in.created_by_user_id
    raw_datasets = list(user_in.allowed_datasets or [])

    if creator:
        creator_roles = _roles_usuario(creator)
        if "Admin_Sistema" in creator_roles:
            created_by_user_id = creator.id
        elif "Director_Recinto" in creator_roles:
            for r in assigned_roles:
                if r not in ("Analista_Consulta", "Guardia_Seguridad", "Consultor_Reporte"):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Los Directores de Recinto solo pueden crear usuarios Analista, Guardia o Consultor de Reporte.",
                    )
            created_by_user_id = creator.id
            director_datasets = _datasets_usuario(creator)
            if not _es_solo_consultor(assigned_roles):
                req_ds = {str(d).strip().lower() for d in raw_datasets if str(d).strip()}
                if req_ds and not req_ds.issubset(director_datasets):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="No puede asignar módulos fuera de su jurisdicción.",
                    )
                if not req_ds:
                    raw_datasets = sorted(director_datasets)
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permisos para crear usuarios en el sistema.",
            )

    final_allowed_datasets, espacio_id = _resolver_espacio_por_datasets(raw_datasets, assigned_roles)

    can_use_ai = user_in.can_use_ai
    can_export = user_in.can_export
    can_ingest = user_in.can_ingest

    if _es_solo_consultor(assigned_roles):
        can_use_ai = bool(invite_in.can_use_ai) if "can_use_ai" in invite_in.model_fields_set else True
        can_export = True
        can_ingest = False
    elif "Admin_Sistema" in assigned_roles or "Director_Recinto" in assigned_roles:
        can_use_ai = True
        can_export = True
        can_ingest = True
    elif "Analista_Consulta" in assigned_roles:
        can_use_ai = True
        can_export = True

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

    for role_name in dict.fromkeys(assigned_roles):
        stmt = select(Rol).where(Rol.nombre == role_name)
        result = await db.execute(stmt)
        role_obj = result.scalar_one_or_none()
        if not role_obj:
            role_obj = Rol(nombre=role_name, descripcion=None)
            db.add(role_obj)
            await db.flush()
        db.add(UsuarioRol(usuario_id=user.id, rol_id=role_obj.id))

    if "Consultor_Reporte" in assigned_roles:
        await _asegurar_destinatario_consultor(db, user)

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
        creator_roles = _roles_usuario(current_user)
        if "Admin_Sistema" not in creator_roles:
            if "Director_Recinto" in creator_roles:
                if not _es_gestionable_por_director(current_user, user):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Solo puede gestionar usuarios cuyos módulos pertenezcan exclusivamente a su recinto asignado.",
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
    limpiar_cache_usuario(user_id)
    return user


async def list_users(db: AsyncSession, current_user: Optional[Usuario] = None) -> List[Usuario]:
    stmt = (
        select(Usuario)
        .options(selectinload(Usuario.roles), selectinload(Usuario.usuario_roles))
        .order_by(Usuario.id)
    )

    if current_user:
        user_roles = _roles_usuario(current_user)
        if "Admin_Sistema" not in user_roles:
            if "Director_Recinto" in user_roles:
                director_datasets = _datasets_usuario(current_user)
                result = await db.execute(stmt)
                todos = list(result.scalars().all())

                usuarios_filtrados: List[Usuario] = []
                for u in todos:
                    if u.id == current_user.id:
                        usuarios_filtrados.append(u)
                        continue

                    u_roles = _roles_usuario(u)
                    if "Admin_Sistema" in u_roles or "Director_Recinto" in u_roles:
                        continue

                    if u.created_by_user_id == current_user.id or _es_solo_consultor(u_roles):
                        usuarios_filtrados.append(u)
                        continue

                    if director_datasets.intersection(_datasets_usuario(u)):
                        usuarios_filtrados.append(u)

                return usuarios_filtrados
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
    assigned_roles = [normalizar_rol(r) for r in invite_in.roles if str(r).strip()]
    if not assigned_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe seleccionar al menos un rol institucional.",
        )

    created_by_user_id = None
    raw_datasets = list(invite_in.allowed_datasets or [])

    if creator:
        creator_roles = _roles_usuario(creator)
        if "Admin_Sistema" in creator_roles:
            created_by_user_id = creator.id
        elif "Director_Recinto" in creator_roles:
            for r in assigned_roles:
                if r not in ("Analista_Consulta", "Guardia_Seguridad", "Consultor_Reporte"):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Los Directores de Recinto solo pueden invitar usuarios con rol Analista_Consulta, Guardia_Seguridad o Consultor_Reporte.",
                    )
            created_by_user_id = creator.id
            director_datasets = _datasets_usuario(creator)
            if not _es_solo_consultor(assigned_roles):
                req_ds = {str(d).strip().lower() for d in raw_datasets if str(d).strip()}
                if req_ds and not req_ds.issubset(director_datasets):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="No puede asignar módulos fuera de su jurisdicción.",
                    )
                if not req_ds:
                    raw_datasets = sorted(director_datasets)
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permisos para invitar usuarios en el sistema.",
            )

    final_allowed_datasets, espacio_id = _resolver_espacio_por_datasets(raw_datasets, assigned_roles)

    can_use_ai = invite_in.can_use_ai
    can_export = invite_in.can_export
    can_ingest = invite_in.can_ingest

    if _es_solo_consultor(assigned_roles):
        can_use_ai = bool(invite_in.can_use_ai) if "can_use_ai" in invite_in.model_fields_set else True
        can_export = True
        can_ingest = False
    elif "Admin_Sistema" in assigned_roles or "Director_Recinto" in assigned_roles:
        can_use_ai = True
        can_export = True
        can_ingest = True
    elif "Analista_Consulta" in assigned_roles:
        can_use_ai = True
        can_export = True

    user = Usuario(
        email=invite_in.email.strip().lower(),
        hashed_password="PENDIENTE_ACTIVACION",
        nombre_completo=invite_in.nombre_completo.strip(),
        is_active=False,
        allowed_datasets=final_allowed_datasets,
        can_use_ai=can_use_ai,
        can_export=can_export,
        can_ingest=can_ingest,
        espacio_id=espacio_id,
        created_by_user_id=created_by_user_id,
    )
    db.add(user)
    await db.flush()

    for role_name in dict.fromkeys(assigned_roles):
        stmt_role = select(Rol).where(Rol.nombre == role_name)
        res_role = await db.execute(stmt_role)
        role_obj = res_role.scalar_one_or_none()
        if role_obj:
            db.add(UsuarioRol(usuario_id=user.id, rol_id=role_obj.id))

    await db.flush()

    if "Consultor_Reporte" in assigned_roles:
        await _asegurar_destinatario_consultor(db, user)

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


async def actualizar_usuario_admin(
    db: AsyncSession,
    user_id: int,
    update_in: UsuarioUpdateRequest,
    current_user: Usuario,
) -> Usuario:
    """Actualiza rol, módulos autorizados y flags de un usuario existente respetando gobernanza Opción A."""
    limpiar_cache_usuario(user_id)
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")

    actor_roles = _roles_usuario(current_user)
    es_admin = "Admin_Sistema" in actor_roles
    es_director = "Director_Recinto" in actor_roles

    if not es_admin:
        if not es_director:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permisos insuficientes.")
        if not _es_gestionable_por_director(current_user, user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo puede editar usuarios cuyos módulos pertenezcan exclusivamente a su recinto asignado.",
            )

    if update_in.roles is not None:
        assigned_roles = [normalizar_rol(r) for r in update_in.roles if str(r).strip()]
        if not assigned_roles:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Debe seleccionar al menos un rol.")
        if not es_admin:
            for r in assigned_roles:
                if r not in ("Analista_Consulta", "Guardia_Seguridad", "Consultor_Reporte"):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Los Directores de Recinto solo pueden asignar roles Analista, Guardia o Consultor de Reporte.",
                    )
        if user.id == current_user.id and "Admin_Sistema" in _roles_usuario(user) and "Admin_Sistema" not in assigned_roles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Un administrador no puede revocar su propio rol Admin_Sistema.",
            )
    else:
        assigned_roles = [normalizar_rol(r.nombre) for r in (user.roles or [])]

    raw_datasets = (
        list(update_in.allowed_datasets)
        if update_in.allowed_datasets is not None
        else list(user.allowed_datasets or [])
    )
    if not es_admin and not _es_solo_consultor(assigned_roles):
        dir_ds = _datasets_usuario(current_user)
        req_ds = {str(d).strip().lower() for d in raw_datasets if str(d).strip()}
        if req_ds and not req_ds.issubset(dir_ds):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No puede asignar módulos fuera de su jurisdicción.",
            )
        if not req_ds:
            raw_datasets = sorted(dir_ds)

    final_datasets, final_espacio = _resolver_espacio_por_datasets(raw_datasets, assigned_roles)

    if update_in.nombre_completo is not None and update_in.nombre_completo.strip():
        user.nombre_completo = update_in.nombre_completo.strip()
    user.allowed_datasets = final_datasets
    user.espacio_id = final_espacio

    if _es_solo_consultor(assigned_roles):
        if update_in.can_use_ai is not None:
            user.can_use_ai = update_in.can_use_ai
        user.can_export = True
        user.can_ingest = False
    else:
        if update_in.can_use_ai is not None:
            user.can_use_ai = update_in.can_use_ai
        elif "Admin_Sistema" in assigned_roles or "Director_Recinto" in assigned_roles:
            user.can_use_ai = True
        if update_in.can_export is not None:
            user.can_export = update_in.can_export
        elif any(r in assigned_roles for r in ("Admin_Sistema", "Director_Recinto", "Analista_Consulta")):
            user.can_export = True
        if update_in.can_ingest is not None:
            user.can_ingest = update_in.can_ingest
        elif "Admin_Sistema" in assigned_roles or "Director_Recinto" in assigned_roles:
            user.can_ingest = True

    if update_in.roles is not None:
        await db.execute(delete(UsuarioRol).where(UsuarioRol.usuario_id == user.id))
        await db.flush()
        for role_name in dict.fromkeys(assigned_roles):
            rol_obj = (await db.execute(select(Rol).where(Rol.nombre == role_name))).scalar_one_or_none()
            if rol_obj:
                db.add(UsuarioRol(usuario_id=user.id, rol_id=rol_obj.id))

    if "Consultor_Reporte" in assigned_roles:
        await _asegurar_destinatario_consultor(db, user)

    await db.commit()
    limpiar_cache_usuario(user_id)
    actualizado = await get_user_by_id(db, user_id)
    return actualizado or user


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
        creator_roles = _roles_usuario(creator)
        if "Admin_Sistema" not in creator_roles:
            if "Director_Recinto" in creator_roles:
                if not _es_gestionable_por_director(creator, user):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Solo puede reenviar invitaciones a usuarios cuyos módulos pertenezcan exclusivamente a su recinto asignado.",
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

    creator_roles = _roles_usuario(current_user)
    if "Admin_Sistema" not in creator_roles:
        if "Director_Recinto" in creator_roles:
            if not _es_gestionable_por_director(current_user, usuario):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Solo puede desbloquear cuentas cuyos módulos pertenezcan exclusivamente a su recinto asignado.",
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





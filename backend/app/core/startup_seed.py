"""
startup_seed.py — Seed automatico de roles y usuarios demo en cada arranque.

Idempotente: usa ON CONFLICT / scalar_one_or_none para no duplicar registros.
Se invoca desde el lifespan de FastAPI antes de abrir trafico.
"""
import logging
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.domain.auth_models import Rol, Usuario, UsuarioRol
from app.services.auth_service import hash_password

logger = logging.getLogger("uvicorn.error")

# ---------------------------------------------------------------------------
# Roles que deben existir siempre
# ---------------------------------------------------------------------------
DEFAULT_ROLES = [
    {
        "nombre": "Admin_Sistema",
        "descripcion": "Acceso total administrativo y configuraciones de sistema",
        "rate_limit_quota": "1000/day",
    },
    {
        "nombre": "Director_Recinto",
        "descripcion": "Jefatura de espacio físico asignado con administración delegada de analistas y guardias",
        "rate_limit_quota": "500/day",
    },
    {
        "nombre": "Analista_Consulta",
        "descripcion": "Decanos, directores de carrera y analistas con acceso a dashboards y modelos analíticos",
        "rate_limit_quota": "200/day",
    },
    {
        "nombre": "Guardia_Seguridad",
        "descripcion": "Monitoreo operativo de accesos, alertas y patentes vehiculares",
        "rate_limit_quota": "50/day",
    },
]

from app.core.config import settings

def obtener_usuarios_demo() -> List[dict]:
    admin_pw = settings.DEMO_ADMIN_PASSWORD
    user_pw = settings.DEMO_USER_PASSWORD
    return [
        {
            "email": "admin@uct.cl",
            "nombre_completo": "Super Administrador UCT",
            "password": admin_pw,
            "roles": ["Admin_Sistema"],
            "allowed_datasets": ["biblioteca", "estacionamiento"],
            "can_use_ai": True,
            "can_export": True,
            "can_ingest": True,
            "espacio_id": None,
        },
        {
            "email": "directivo@uct.cl",
            "nombre_completo": "Directivo UCT",
            "password": user_pw,
            "roles": ["Director_Recinto"],
            "allowed_datasets": ["biblioteca", "estacionamiento"],
            "can_use_ai": True,
            "can_export": True,
            "can_ingest": True,
            "espacio_id": 1,
        },
        {
            "email": "analista@uct.cl",
            "nombre_completo": "Analista Curricular UCT",
            "password": user_pw,
            "roles": ["Analista_Consulta"],
            "allowed_datasets": ["biblioteca", "estacionamiento"],
            "can_use_ai": True,
            "can_export": True,
            "can_ingest": False,
            "espacio_id": 1,
        },
        {
            "email": "guardia@uct.cl",
            "nombre_completo": "Guardia Seguridad UCT",
            "password": user_pw,
            "roles": ["Guardia_Seguridad"],
            "allowed_datasets": ["biblioteca", "estacionamiento"],
            "can_use_ai": False,
            "can_export": False,
            "can_ingest": False,
            "espacio_id": 1,
        },
    ]


async def _ensure_roles(db: AsyncSession) -> dict[str, Rol]:
    """Crea los roles que no existen; retorna mapa nombre -> Rol."""
    role_map: dict[str, Rol] = {}
    for rdef in DEFAULT_ROLES:
        stmt = select(Rol).where(Rol.nombre == rdef["nombre"])
        rol = (await db.execute(stmt)).scalar_one_or_none()
        if not rol:
            rol = Rol(
                nombre=rdef["nombre"],
                descripcion=rdef["descripcion"],
                rate_limit_quota=rdef["rate_limit_quota"],
            )
            db.add(rol)
            await db.flush()
            logger.info(f"[seed] Rol creado: {rdef['nombre']}")
        role_map[rdef["nombre"]] = rol
    return role_map


async def seed_test_users(db: AsyncSession, role_map: dict[str, Rol]) -> None:
    if not settings.SEMILLA_DEMO or settings.ENVIRONMENT.lower() != "development":
        logger.info("[seed] Creación de usuarios demo omitida (SEMILLA_DEMO=false o ENVIRONMENT != development).")
        return

    usuarios_demo = obtener_usuarios_demo()
    for udef in usuarios_demo:
        stmt = select(Usuario).where(Usuario.email == udef["email"])
        user: Usuario | None = (await db.execute(stmt)).scalar_one_or_none()

        if not user:
            # Sin contraseña definida en el entorno no se crea el usuario demo
            if not udef["password"]:
                logger.warning(f"[seed] Usuario demo omitido (falta DEMO_*_PASSWORD): {udef['email']}")
                continue
            user = Usuario(
                email=udef["email"],
                nombre_completo=udef["nombre_completo"],
                hashed_password=hash_password(udef["password"]),
                is_active=True,
                allowed_datasets=udef["allowed_datasets"],
                can_use_ai=udef.get("can_use_ai", False),
                can_export=udef.get("can_export", False),
                can_ingest=udef.get("can_ingest", False),
                espacio_id=udef.get("espacio_id"),
            )
            db.add(user)
            await db.flush()

            for role_name in udef["roles"]:
                rol = role_map.get(role_name)
                if rol:
                    db.add(UsuarioRol(usuario_id=user.id, rol_id=rol.id))

            logger.info(f"[seed] Usuario creado: {udef['email']} ({udef['roles']})")
        else:
            # Sincronizar roles y banderas si ya existía
            user.can_use_ai = udef.get("can_use_ai", user.can_use_ai)
            user.can_export = udef.get("can_export", user.can_export)
            user.can_ingest = udef.get("can_ingest", user.can_ingest)
            if udef.get("espacio_id") is not None:
                user.espacio_id = udef["espacio_id"]
            for role_name in udef["roles"]:
                rol = role_map.get(role_name)
                if rol:
                    stmt_ur = select(UsuarioRol).where(
                        UsuarioRol.usuario_id == user.id, UsuarioRol.rol_id == rol.id
                    )
                    ur = (await db.execute(stmt_ur)).scalar_one_or_none()
                    if not ur:
                        db.add(UsuarioRol(usuario_id=user.id, rol_id=rol.id))


async def run_startup_seed() -> None:
    """Punto de entrada; se llama desde el lifespan de FastAPI."""
    logger.info("[seed] Iniciando seed automatico de roles y usuarios demo...")
    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                role_map = await _ensure_roles(db)
                await seed_test_users(db, role_map)
        logger.info("[seed] Seed completado exitosamente.")
    except Exception as exc:
        logger.error(f"[seed] Error durante el seed automatico: {exc}", exc_info=True)

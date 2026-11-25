"""
startup_seed.py — Seed automatico de roles y usuarios demo en cada arranque.

Idempotente: usa ON CONFLICT / scalar_one_or_none para no duplicar registros.
Se invoca desde el lifespan de FastAPI antes de abrir trafico.
"""
import logging
import secrets
from typing import List

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.tiempo import ahora_chile_naive
from app.domain.auth_models import Rol, Usuario, UsuarioRol
from app.domain.reportes_compartidos_models import DestinatarioReporte
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
    {
        "nombre": "Consultor_Reporte",
        "descripcion": "Solicitante institucional con acceso exclusivo a su bandeja de reportes ejecutivos",
        "rate_limit_quota": "50/day",
    },
]


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
            "email": "jhuinca2020@alu.uct.cl",
            "nombre_completo": "Jonathan Huinca",
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
            "espacio_id": None,
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
            "espacio_id": None,
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
            "espacio_id": None,
        },
    ]


def obtener_consultores_prueba() -> List[dict]:
    """Retorna las 2 cuentas de prueba con rol único Consultor_Reporte disponibles en dev y prod."""
    consultor_pw = settings.DEMO_USER_PASSWORD or "UCTdemo2026!"
    return [
        {
            "email": "consultor1@uct.cl",
            "nombre_completo": "Consultor de Reportes Prueba 1",
            "cargo": "Jefe de Carrera (Prueba)",
            "unidad_academica": "Facultad de Ingeniería UCT",
            "password": consultor_pw,
            "roles": ["Consultor_Reporte"],
            "allowed_datasets": [],
            "can_use_ai": True,
            "can_export": True,
            "can_ingest": False,
            "espacio_id": None,
        },
        {
            "email": "consultor2@uct.cl",
            "nombre_completo": "Consultor de Reportes Prueba 2",
            "cargo": "Coordinador Académico (Prueba)",
            "unidad_academica": "Dirección de Docencia UCT",
            "password": consultor_pw,
            "roles": ["Consultor_Reporte"],
            "allowed_datasets": [],
            "can_use_ai": True,
            "can_export": True,
            "can_ingest": False,
            "espacio_id": None,
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


async def _ensure_consultores_prueba(db: AsyncSession, role_map: dict[str, Rol]) -> None:
    """Garantiza los 2 usuarios prueba Consultor_Reporte sin sobrescribir claves ni estado existente."""
    rol_consultor = role_map.get("Consultor_Reporte")
    ahora = ahora_chile_naive()
    for cdef in obtener_consultores_prueba():
        stmt = select(Usuario).where(func.lower(Usuario.email) == cdef["email"].lower())
        user = (await db.execute(stmt)).scalar_one_or_none()
        if not user:
            user = Usuario(
                email=cdef["email"],
                nombre_completo=cdef["nombre_completo"],
                hashed_password=hash_password(cdef["password"]),
                is_active=True,
                allowed_datasets=[],
                can_use_ai=False,
                can_export=True,
                can_ingest=False,
                espacio_id=None,
            )
            db.add(user)
            await db.flush()
            if rol_consultor:
                db.add(UsuarioRol(usuario_id=user.id, rol_id=rol_consultor.id))
            logger.info(f"[seed] Consultor de prueba creado: {cdef['email']}")
        elif rol_consultor:
            stmt_ur = select(UsuarioRol).where(UsuarioRol.usuario_id == user.id)
            tiene_roles = (await db.execute(stmt_ur)).scalars().all()
            if not tiene_roles:
                db.add(UsuarioRol(usuario_id=user.id, rol_id=rol_consultor.id))

        stmt_dest = select(DestinatarioReporte).where(
            func.lower(DestinatarioReporte.email) == cdef["email"].lower()
        )
        dest = (await db.execute(stmt_dest)).scalar_one_or_none()
        if not dest:
            db.add(
                DestinatarioReporte(
                    email=cdef["email"],
                    nombre_completo=cdef["nombre_completo"],
                    cargo=cdef["cargo"],
                    unidad_academica=cdef["unidad_academica"],
                    token_portal=secrets.token_urlsafe(32),
                    activo=True,
                    creado_en=ahora,
                    actualizado_en=ahora,
                )
            )


async def _ensure_admin_bootstrap_produccion(db: AsyncSession, role_map: dict[str, Rol]) -> None:
    """En producción crea un SuperAdmin inicial solo si no existe ningún Admin_Sistema en BD."""
    rol_admin = role_map.get("Admin_Sistema")
    if not rol_admin:
        return
    stmt_adm = select(UsuarioRol).where(UsuarioRol.rol_id == rol_admin.id)
    if (await db.execute(stmt_adm)).scalars().first() is not None:
        return

    email_adm = (settings.ADMIN_BOOTSTRAP_EMAIL or "admin@uct.cl").strip().lower()
    pass_adm = settings.ADMIN_BOOTSTRAP_PASSWORD or settings.DEMO_ADMIN_PASSWORD
    if not pass_adm:
        logger.warning("[seed] No se pudo crear administrador inicial: falta ADMIN_BOOTSTRAP_PASSWORD.")
        return

    stmt_usr = select(Usuario).where(func.lower(Usuario.email) == email_adm)
    user = (await db.execute(stmt_usr)).scalar_one_or_none()
    if not user:
        user = Usuario(
            email=email_adm,
            nombre_completo="Administrador UCT",
            hashed_password=hash_password(pass_adm),
            is_active=True,
            allowed_datasets=["biblioteca", "estacionamiento"],
            can_use_ai=True,
            can_export=True,
            can_ingest=True,
            espacio_id=None,
        )
        db.add(user)
        await db.flush()
    db.add(UsuarioRol(usuario_id=user.id, rol_id=rol_admin.id))
    logger.info(f"[seed] Administrador bootstrap creado para producción: {email_adm}")


async def seed_test_users(db: AsyncSession, role_map: dict[str, Rol]) -> None:
    usuarios_demo = obtener_usuarios_demo()
    for udef in usuarios_demo:
        stmt = select(Usuario).where(Usuario.email == udef["email"])
        user: Usuario | None = (await db.execute(stmt)).scalar_one_or_none()

        if not user:
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
            # Preservar ediciones administrativas y contraseñas; asegurar roles solo si la cuenta quedó sin roles
            stmt_ur = select(UsuarioRol).where(UsuarioRol.usuario_id == user.id)
            tiene_roles = (await db.execute(stmt_ur)).scalars().all()
            if not tiene_roles:
                for role_name in udef["roles"]:
                    rol = role_map.get(role_name)
                    if rol:
                        db.add(UsuarioRol(usuario_id=user.id, rol_id=rol.id))


async def run_startup_seed() -> None:
    """Punto de entrada; se llama desde el lifespan de FastAPI."""
    logger.info("[seed] Iniciando seed automatico de roles y cuentas iniciales...")
    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                role_map = await _ensure_roles(db)
                await _ensure_consultores_prueba(db, role_map)
                if settings.SEMILLA_DEMO and not settings.is_production:
                    await seed_test_users(db, role_map)
                else:
                    await _ensure_admin_bootstrap_produccion(db, role_map)
        logger.info("[seed] Seed completado exitosamente.")
    except Exception as exc:
        logger.error(f"[seed] Error durante el seed automatico: {exc}", exc_info=True)

"""
limpiar_demo.py — Herramienta CLI para limpiar cuentas de demostración antes o al pasar a producción.

Uso:
    python -m app.cli.limpiar_demo --dry-run
    python -m app.cli.limpiar_demo
    python -m app.cli.limpiar_demo --incluir-consultores-prueba
"""
import argparse
import asyncio
import logging

from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionLocal
from app.domain.auth_models import TokenActivacion, Usuario, UsuarioRol
from app.domain.reportes_compartidos_models import (
    AuditoriaAccesoReporte,
    DestinatarioReporte,
    ReporteCompartido,
)
from app.services.auth_service import limpiar_cache_usuario, normalizar_rol

logger = logging.getLogger("limpiar_demo")

CORREOS_DEMO_DESARROLLO = {
    "directivo@uct.cl",
    "analista@uct.cl",
    "guardia@uct.cl",
    "jhuinca2020@alu.uct.cl",
}
CORREOS_CONSULTORES_PRUEBA = {
    "consultor1@uct.cl",
    "consultor2@uct.cl",
}


async def limpiar_cuentas_demo(
    dry_run: bool = False,
    incluir_consultores_prueba: bool = False,
) -> dict:
    objetivos = set(CORREOS_DEMO_DESARROLLO)
    if incluir_consultores_prueba:
        objetivos.update(CORREOS_CONSULTORES_PRUEBA)

    resumen = {"objetivos": sorted(objetivos), "eliminados": [], "omitidos": [], "dry_run": dry_run}

    async with AsyncSessionLocal() as db:
        todos = (
            await db.execute(select(Usuario).options(selectinload(Usuario.roles)))
        ).scalars().all()
        admins_activos = [
            u
            for u in todos
            if any(normalizar_rol(r.nombre) == "Admin_Sistema" for r in (u.roles or []))
        ]

        for u in todos:
            email_low = (u.email or "").strip().lower()
            if email_low not in objetivos:
                continue

            es_admin = any(normalizar_rol(r.nombre) == "Admin_Sistema" for r in (u.roles or []))
            restantes_admin = [a for a in admins_activos if a.id != u.id]
            if es_admin and len(restantes_admin) == 0:
                resumen["omitidos"].append(
                    {"email": u.email, "motivo": "Único administrador activo; cree otro Admin_Sistema antes de eliminar."}
                )
                continue

            resumen["eliminados"].append(u.email)
            if es_admin:
                admins_activos = restantes_admin

            if dry_run:
                continue

            limpiar_cache_usuario(u.id)
            dest_ids = list(
                (
                    await db.execute(
                        select(DestinatarioReporte.id).where(func.lower(DestinatarioReporte.email) == email_low)
                    )
                )
                .scalars()
                .all()
            )
            if dest_ids:
                rep_ids = list(
                    (
                        await db.execute(
                            select(ReporteCompartido.id).where(ReporteCompartido.destinatario_id.in_(dest_ids))
                        )
                    )
                    .scalars()
                    .all()
                )
                if rep_ids:
                    await db.execute(
                        delete(AuditoriaAccesoReporte).where(AuditoriaAccesoReporte.reporte_id.in_(rep_ids))
                    )
                    await db.execute(delete(ReporteCompartido).where(ReporteCompartido.id.in_(rep_ids)))
                await db.execute(delete(DestinatarioReporte).where(DestinatarioReporte.id.in_(dest_ids)))

            await db.execute(delete(TokenActivacion).where(TokenActivacion.usuario_id == u.id))
            await db.execute(delete(UsuarioRol).where(UsuarioRol.usuario_id == u.id))
            await db.execute(delete(Usuario).where(Usuario.id == u.id))

        if not dry_run:
            await db.commit()

    return resumen


def main() -> None:
    parser = argparse.ArgumentParser(description="Limpia cuentas demo de desarrollo preservando administradores reales.")
    parser.add_argument("--dry-run", action="store_true", help="Muestra qué cuentas serían eliminadas sin modificar la BD.")
    parser.add_argument(
        "--incluir-consultores-prueba",
        action="store_true",
        help="Incluye también consultor1@uct.cl y consultor2@uct.cl en la limpieza.",
    )
    args = parser.parse_args()
    resultado = asyncio.run(
        limpiar_cuentas_demo(
            dry_run=args.dry_run,
            incluir_consultores_prueba=args.incluir_consultores_prueba,
        )
    )
    print(resultado)


if __name__ == "__main__":
    main()

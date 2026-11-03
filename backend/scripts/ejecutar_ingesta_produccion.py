"""
ejecutar_ingesta_produccion.py — Script de Ingesta Masiva y Enriquecimiento Retroactivo (RF04, RF30).
Opción Alternativa: Carga inicial HikCentral tolerante y enriquecimiento curricular dinámico posterior.
"""
import asyncio
import os
import sys
import logging
from pathlib import Path

# Ajustar PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import AsyncSessionLocal
from app.services.ingestion_service import (
    ejecutar_ingesta_atomica,
    enriquecer_asistencia_retroactiva,
)
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ingesta_produccion")

BASE_DIR = Path(__file__).resolve().parent.parent / "datos_crudos_prueba"

ARCHIVO_MARCAJES = BASE_DIR / "marcajes_bibliotecas_csf_2026-03-01_a_2026-10-14(1).xlsx"
ARCHIVO_VEHICULOS = BASE_DIR / "RegistroVehicular_base.xlsx"
ARCHIVO_SALAS = BASE_DIR / "Reporte Salas de estudio SEPTIEMBRE 2024 - Completo.xlsx"


async def main():
    logger.info("Iniciando proceso de ingesta integral...")

    if not ARCHIVO_MARCAJES.exists():
        logger.error(f"No se encuentra el archivo de marcajes: {ARCHIVO_MARCAJES}")
        return
    if not ARCHIVO_VEHICULOS.exists():
        logger.error(f"No se encuentra el archivo vehicular: {ARCHIVO_VEHICULOS}")
        return
    if not ARCHIVO_SALAS.exists():
        logger.error(f"No se encuentra el archivo de salas: {ARCHIVO_SALAS}")
        return

    async with AsyncSessionLocal() as db:
        # -------------------------------------------------------------
        # Paso 1: Carga Inicial Torniquetes Biblioteca en Modo Tolerante
        # -------------------------------------------------------------
        r_chk = await db.execute(text("SELECT COUNT(*) FROM eventos_asistencia WHERE espacio_id = 1"))
        cant_asist = r_chk.scalar() or 0
        if cant_asist >= 100000:
            logger.info(f"Paso 1: Biblioteca ya cuenta con {cant_asist} marcajes cargados en Modo Tolerante. Omitiendo relectura.")
        else:
            logger.info("Paso 1: Ingestando marcajes físicos de Biblioteca (Modo Tolerante)...")
            with open(ARCHIVO_MARCAJES, "rb") as f:
                bytes_marcajes = f.read()

            res_bib = await ejecutar_ingesta_atomica(
                file_bytes=bytes_marcajes,
                filename=ARCHIVO_MARCAJES.name,
                tipo="asistencia",
                espacio_id=1,
                modo_solapamiento="overwrite",
                clave_enlace="matricula",
                modo_enlace="tolerante",
                db=db,
            )
            logger.info(
                f"Biblioteca: {res_bib.registros_insertados} insertados, "
                f"{res_bib.registros_eliminados} eliminados, "
                f"{res_bib.carreras_catalogadas} catalogadas, "
                f"{res_bib.carreras_no_catalogadas} no catalogadas."
            )

        # -------------------------------------------------------------
        # Paso 2: Carga Base ANPR Estacionamiento
        # -------------------------------------------------------------
        r_veh = await db.execute(text("SELECT COUNT(*) FROM eventos_vehiculares WHERE espacio_id = 2"))
        cant_veh = r_veh.scalar() or 0
        if cant_veh >= 30000:
            logger.info(f"Paso 2: Estacionamiento ya cuenta con {cant_veh} tránsitos ANPR cargados. Omitiendo relectura.")
        else:
            logger.info("Paso 2: Ingestando tránsitos vehiculares ANPR (Estacionamiento)...")
            with open(ARCHIVO_VEHICULOS, "rb") as f:
                bytes_veh = f.read()

            res_veh = await ejecutar_ingesta_atomica(
                file_bytes=bytes_veh,
                filename=ARCHIVO_VEHICULOS.name,
                tipo="vehicular",
                espacio_id=2,
                modo_solapamiento="overwrite",
                clave_enlace="rut",
                modo_enlace="tolerante",
                db=db,
            )
            logger.info(
                f"Estacionamiento: {res_veh.registros_insertados} insertados, "
                f"{res_veh.registros_eliminados} eliminados."
            )

        # -------------------------------------------------------------
        # Paso 3: Carga del Catálogo Curricular (Reporte Salas de estudio)
        # -------------------------------------------------------------
        logger.info("Paso 3: Ingestando catálogo curricular institucional...")
        with open(ARCHIVO_SALAS, "rb") as f:
            bytes_salas = f.read()

        res_curr = await ejecutar_ingesta_atomica(
            file_bytes=bytes_salas,
            filename=ARCHIVO_SALAS.name,
            tipo="curricular",
            espacio_id=1,
            modo_solapamiento="overwrite",
            clave_enlace="rut",
            modo_enlace="tolerante",
            db=db,
        )
        logger.info(
            f"Catálogo Curricular: {res_curr.registros_insertados} estudiantes registrados en dim_estudiante_carrera."
        )

        # -------------------------------------------------------------
        # Paso 4: Enriquecimiento Curricular Retroactivo (RF30)
        # -------------------------------------------------------------
        logger.info("Paso 4: Ejecutando enriquecimiento retroactivo sobre eventos de asistencia...")
        res_enrich = await enriquecer_asistencia_retroactiva(
            db=db,
            espacio_id=1,
            clave_enlace="auto",
        )
        logger.info(f"Enriquecimiento: {res_enrich['detalle']}")

        # -------------------------------------------------------------
        # Verificación y Conteo en Base de Datos
        # -------------------------------------------------------------
        logger.info("Verificando totales finales en SQL Server...")
        tablas = [
            "eventos_asistencia",
            "eventos_vehiculares",
            "dim_estudiante_carrera",
            "ingestion_jobs",
        ]
        conteos = {}
        for t in tablas:
            r = await db.execute(text(f"SELECT COUNT(*) FROM {t}"))
            conteos[t] = r.scalar()

        # Conteo de asistencia por estado de carrera
        r_carr = await db.execute(
            text(
                "SELECT COUNT(*) FROM eventos_asistencia WHERE carrera IS NOT NULL AND carrera != 'Sin carrera catalogada'"
            )
        )
        con_carrera = r_carr.scalar()
        r_sin_carr = await db.execute(
            text(
                "SELECT COUNT(*) FROM eventos_asistencia WHERE carrera = 'Sin carrera catalogada' OR carrera IS NULL"
            )
        )
        sin_carrera = r_sin_carr.scalar()

        logger.info("==================================================")
        logger.info("RESUMEN DE ESTADO FINAL DE LA BASE DE DATOS")
        logger.info("==================================================")
        logger.info(f"Eventos Asistencia (Biblioteca): {conteos['eventos_asistencia']} registros")
        logger.info(f"  - Con carrera catalogada: {con_carrera}")
        logger.info(f"  - Sin carrera catalogada: {sin_carrera}")
        logger.info(f"Eventos Vehiculares (Estacionamiento): {conteos['eventos_vehiculares']} registros")
        logger.info(f"Dim Estudiante Carrera (Catálogo): {conteos['dim_estudiante_carrera']} registros")
        logger.info(f"Trabajos de Ingesta Registrados: {conteos['ingestion_jobs']} trabajos")
        logger.info("==================================================")


if __name__ == "__main__":
    asyncio.run(main())

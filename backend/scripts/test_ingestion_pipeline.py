"""
test_ingestion_pipeline.py — Prueba integral del pipeline de control de colisiones,
enlace curricular flexible y recarga retroactiva atómica (RF04, RF30).
"""
import asyncio
from datetime import datetime
from sqlalchemy import select, text
from fastapi import HTTPException

from app.core.database import AsyncSessionLocal
from app.domain.models import EventoAsistencia, IngestionJob
from app.services.ingestion_service import (
    calcular_hash_archivo,
    validar_archivo_ingesta,
    ejecutar_ingesta_atomica,
)


async def run_tests():
    print("=====================================================================")
    print("INICIANDO PRUEBAS DEL PIPELINE DE INGESTA ATÓMICA Y ENLACE (RF04/RF30)")
    print("=====================================================================")

    async with AsyncSessionLocal() as db:
        # Limpieza previa del rango de prueba (2026-04-10)
        await db.execute(
            text("DELETE FROM eventos_asistencia WHERE espacio_id = 1 AND time >= '2026-04-10 00:00:00' AND time <= '2026-04-10 23:59:59'")
        )
        await db.execute(
            text("DELETE FROM ingestion_jobs WHERE filename LIKE 'prueba_pipeline_%'")
        )
        await db.commit()

        # -------------------------------------------------------------------
        # TEST 1: Carga inicial de marcajes sin carrera en Modo Tolerante
        # -------------------------------------------------------------------
        print("\n--- TEST 1: Carga inicial sin carrera en Modo Tolerante ---")
        csv_sin_carrera = (
            "Fecha,Primera entrada,Ultima salida,Door de entrada,Door de salida,Numero de matricula,Marcajes\n"
            "2026-04-10,08:30:00,12:00:00,Acceso Norte,Acceso Norte,2023100001,2\n"
            "2026-04-10,09:15:00,14:20:00,Acceso Sur,Acceso Sur,2023100002,2\n"
            "2026-04-10,10:00:00,11:30:00,Acceso Norte,Acceso Norte,2023100003,1\n"
        ).encode("utf-8")

        val1 = await validar_archivo_ingesta(
            file_bytes=csv_sin_carrera,
            filename="prueba_pipeline_v1.csv",
            tipo="asistencia",
            espacio_id=1,
            db=db,
        )
        print(f"Hash calculado: {val1.file_hash[:16]}...")
        print(f"Rango detectado: {val1.fecha_min} a {val1.fecha_max}")
        print(f"Existe colisión previa: {val1.existe_colision} (registros: {val1.registros_existentes})")
        print(f"Clave detectada: {val1.clave_enlace_detectada}")
        assert val1.clave_enlace_detectada == "matricula"
        assert val1.existe_colision is False

        # Ingesta atómica en modo tolerante
        res1 = await ejecutar_ingesta_atomica(
            file_bytes=csv_sin_carrera,
            filename="prueba_pipeline_v1.csv",
            tipo="asistencia",
            espacio_id=1,
            modo_solapamiento="merge",
            clave_enlace="matricula",
            modo_enlace="tolerante",
            db=db,
        )
        print(f"Resultado Test 1: Insertados={res1.registros_insertados}, CarrerasCatalogadas={res1.carreras_catalogadas}, NoCatalogadas={res1.carreras_no_catalogadas}")
        assert res1.registros_insertados == 3
        assert res1.carreras_no_catalogadas == 3

        # Verificar en base de datos que se guardó 'Sin carrera catalogada'
        stmt_chk1 = select(EventoAsistencia).where(
            EventoAsistencia.espacio_id == 1,
            EventoAsistencia.time >= '2026-04-10 00:00:00',
            EventoAsistencia.time <= '2026-04-10 23:59:59',
        )
        filas1 = (await db.execute(stmt_chk1)).scalars().all()
        assert len(filas1) == 3
        for f in filas1:
            print(f"  Registro BD: time={f.time}, carrera='{f.carrera}', puerta='{f.door_entrada}'")
            assert f.carrera == "Sin carrera catalogada", f"Carrera esperada 'Sin carrera catalogada' pero obtuvo '{f.carrera}'"

        print("TEST 1 SUPERADO CON ÉXITO.")

        # -------------------------------------------------------------------
        # TEST 2: Intento de reingesta con mismo hash (Detección de Duplicado)
        # -------------------------------------------------------------------
        print("\n--- TEST 2: Intento de reingesta con mismo hash ---")
        val2 = await validar_archivo_ingesta(
            file_bytes=csv_sin_carrera,
            filename="prueba_pipeline_v1.csv",
            tipo="asistencia",
            espacio_id=1,
            db=db,
        )
        print(f"Hash ya procesado detectado: {val2.hash_ya_procesado}")
        print(f"Existe colisión de rango: {val2.existe_colision} (existentes: {val2.registros_existentes})")
        assert val2.hash_ya_procesado is True
        assert val2.existe_colision is True
        assert val2.registros_existentes == 3

        # En modo merge debe rechazar la duplicación con HTTP 409
        try:
            await ejecutar_ingesta_atomica(
                file_bytes=csv_sin_carrera,
                filename="prueba_pipeline_v1.csv",
                tipo="asistencia",
                espacio_id=1,
                modo_solapamiento="merge",
                clave_enlace="matricula",
                modo_enlace="tolerante",
                db=db,
            )
            assert False, "Debió rechazar con HTTP 409 por archivo duplicado"
        except HTTPException as he:
            print(f"Rechazo esperado HTTP {he.status_code}: {he.detail}")
            assert he.status_code == 409

        print("TEST 2 SUPERADO CON ÉXITO.")

        # -------------------------------------------------------------------
        # TEST 3: Recarga retroactiva en modo 'overwrite' con versión enriquecida
        # -------------------------------------------------------------------
        print("\n--- TEST 3: Recarga retroactiva con Sobrescritura Atómica de Rango ---")
        csv_enriquecido = (
            "Fecha,Primera entrada,Ultima salida,Door de entrada,Door de salida,Numero de matricula,Carrera,Facultad,Marcajes\n"
            "2026-04-10,08:30:00,12:00:00,Acceso Norte,Acceso Norte,2023100001,Ingeniería Civil Informática,Facultad de Ingeniería,2\n"
            "2026-04-10,09:15:00,14:20:00,Acceso Sur,Acceso Sur,2023100002,Derecho,Facultad de Ciencias Jurídicas,2\n"
            "2026-04-10,10:00:00,11:30:00,Acceso Norte,Acceso Norte,2023100003,Psicología,Facultad de Ciencias de la Salud,1\n"
        ).encode("utf-8")

        val3 = await validar_archivo_ingesta(
            file_bytes=csv_enriquecido,
            filename="prueba_pipeline_v2_enriquecida.csv",
            tipo="asistencia",
            espacio_id=1,
            db=db,
        )
        print(f"Hash V2: {val3.file_hash[:16]}...")
        print(f"Colisión detectada: {val3.existe_colision} ({val3.registros_existentes} registros previos)")
        print(f"Porcentaje coincidencia carreras: {val3.porcentaje_coincidencia_carreras}%")
        assert val3.existe_colision is True
        assert val3.registros_existentes == 3
        assert val3.porcentaje_coincidencia_carreras == 100.0

        # Ejecutar recarga con modo overwrite y modo mandatorio
        res3 = await ejecutar_ingesta_atomica(
            file_bytes=csv_enriquecido,
            filename="prueba_pipeline_v2_enriquecida.csv",
            tipo="asistencia",
            espacio_id=1,
            modo_solapamiento="overwrite",
            clave_enlace="matricula",
            modo_enlace="mandatorio",
            db=db,
        )
        print(f"Resultado Test 3: Insertados={res3.registros_insertados}, EliminadosPrevios={res3.registros_eliminados}, Catalogadas={res3.carreras_catalogadas}")
        assert res3.registros_eliminados == 3, f"Se esperaban 3 eliminados, obtuvo {res3.registros_eliminados}"
        assert res3.registros_insertados == 3
        assert res3.carreras_catalogadas == 3

        # Verificar en base de datos que ya NO existe 'Sin carrera catalogada'
        stmt_chk3 = select(EventoAsistencia).where(
            EventoAsistencia.espacio_id == 1,
            EventoAsistencia.time >= '2026-04-10 00:00:00',
            EventoAsistencia.time <= '2026-04-10 23:59:59',
        )
        filas3 = (await db.execute(stmt_chk3)).scalars().all()
        assert len(filas3) == 3
        for f in filas3:
            print(f"  Registro BD Enriquecido: time={f.time}, carrera='{f.carrera}', facultad='{f.facultad}'")
            assert f.carrera in ("Ingeniería Civil Informática", "Derecho", "Psicología")
            assert f.carrera != "Sin carrera catalogada"

        print("TEST 3 SUPERADO CON ÉXITO.")

        # Limpieza final de datos de prueba
        await db.execute(
            text("DELETE FROM eventos_asistencia WHERE espacio_id = 1 AND time >= '2026-04-10 00:00:00' AND time <= '2026-04-10 23:59:59'")
        )
        await db.execute(
            text("DELETE FROM ingestion_jobs WHERE filename LIKE 'prueba_pipeline_%'")
        )
        await db.commit()

        print("\n=====================================================================")
        print("TODAS LAS PRUEBAS DEL PIPELINE (TEST 1, TEST 2, TEST 3) PASARON EXITOSAMENTE")
        print("=====================================================================")


if __name__ == "__main__":
    asyncio.run(run_tests())

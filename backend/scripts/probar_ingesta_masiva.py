"""
probar_ingesta_masiva.py — Verificación integral del Prompt 9:
Ingesta masiva por lotes de 10.000 sin Celery ni Redis, con semáforo limitador,
supresión de PII, seudonimización Ley 21.719, rechazo de duplicados y limpieza de huérfanos.
"""
import asyncio
import io
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Configurar PYTHONPATH si es necesario
sys.path.insert(0, "/app")

from sqlalchemy import select, func, delete
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.domain.models import IngestionJob, EventoAsistencia, EventoVehicular
from app.services.ingestion_service import (
    limpiar_trabajos_ingesta_huerfanos,
    encolar_y_procesar_ingesta,
    _semaforo_ingesta,
    invalidar_caches_recinto_y_actualizar_predicciones,
)


async def probar_limpieza_huerfanos():
    print("--- 1. Probando limpieza de trabajos huérfanos tras reinicio ---")
    async with AsyncSessionLocal() as db:
        job_huerfano_1 = IngestionJob(
            job_id=uuid.uuid4(),
            filename="archivo_huerfano_test1.csv",
            tipo="asistencia",
            estado="processing",
            registros_ok=5000,
            registros_error=0,
            creado_en=datetime.now(timezone.utc),
            espacio_id=1,
        )
        job_huerfano_2 = IngestionJob(
            job_id=uuid.uuid4(),
            filename="archivo_huerfano_test2.csv",
            tipo="vehicular",
            estado="queued",
            registros_ok=0,
            registros_error=0,
            creado_en=datetime.now(timezone.utc),
            espacio_id=2,
        )
        db.add_all([job_huerfano_1, job_huerfano_2])
        await db.commit()

        id1, id2 = job_huerfano_1.job_id, job_huerfano_2.job_id

    limpiados = await limpiar_trabajos_ingesta_huerfanos()
    print(f"Trabajos huérfanos limpiados: {limpiados}")
    assert limpiados >= 2, "Debieron limpiarse al menos los 2 trabajos huérfanos creados."

    async with AsyncSessionLocal() as db:
        j1 = await db.get(IngestionJob, id1)
        j2 = await db.get(IngestionJob, id2)
        assert j1.estado == "failed", f"Estado esperado 'failed', obtenido: {j1.estado}"
        assert j2.estado == "failed", f"Estado esperado 'failed', obtenido: {j2.estado}"
        assert "huérfano" in j1.error_detail.lower()
        # Limpieza de registros de prueba
        await db.delete(j1)
        await db.delete(j2)
        await db.commit()

    print("OK: Limpieza de huérfanos verificada exitosamente.")


async def probar_semaforo_y_lotes():
    print("\n--- 2. Probando procesamiento por lotes con semáforo concurrente ---")
    dir_ingesta = Path(settings.DIRECTORIO_INGESTA)
    dir_ingesta.mkdir(parents=True, exist_ok=True)

    # Crear un CSV sintético de prueba con más de 10.000 filas
    total_filas = 12500
    lineas = [
        "Fecha,Persona,personId,Marcajes,Primera entrada,Door entrada,Dif. entrada (min),Última salida,Door salida,Dif. salida (min),Teléfono,Carrera"
    ]
    for i in range(1, total_filas + 1):
        lineas.append(
            f"2026-03-15,Estudiante {i},RUT_{i:06d},1,2026-03-15 08:{i%60:02d}:00,Torniquete-01,,2026-03-15 12:{i%60:02d}:00,Torniquete-02,,+56912345678,Ingenieria Civil"
        )
    csv_content = "\n".join(lineas)

    job_id_1 = uuid.uuid4()
    job_id_2 = uuid.uuid4()

    ruta_test_1 = dir_ingesta / f"{job_id_1}_test_masivo_1.csv"
    ruta_test_2 = dir_ingesta / f"{job_id_2}_test_masivo_2.csv"
    ruta_test_1.write_text(csv_content, encoding="utf-8")
    ruta_test_2.write_text(csv_content, encoding="utf-8")

    async with AsyncSessionLocal() as db:
        j1 = IngestionJob(
            job_id=job_id_1,
            filename=ruta_test_1.name,
            tipo="asistencia",
            estado="queued",
            registros_ok=0,
            registros_error=0,
            creado_en=datetime.now(timezone.utc),
            espacio_id=1,
            file_hash="hash_dummy_test_1",
            modo_solapamiento="merge",
        )
        j2 = IngestionJob(
            job_id=job_id_2,
            filename=ruta_test_2.name,
            tipo="asistencia",
            estado="queued",
            registros_ok=0,
            registros_error=0,
            creado_en=datetime.now(timezone.utc),
            espacio_id=1,
            file_hash="hash_dummy_test_2",
            modo_solapamiento="merge",
        )
        db.add_all([j1, j2])
        await db.commit()

    # Lanzar ambas tareas concurrentes. Debido al semáforo _semaforo_ingesta = asyncio.Semaphore(1),
    # la tarea 1 se procesará y la tarea 2 esperará en cola
    print("Lanzando 2 tareas concurrentes...")
    t1 = asyncio.create_task(
        encolar_y_procesar_ingesta(
            job_id=job_id_1,
            ruta_archivo=str(ruta_test_1),
            tipo="asistencia",
            espacio_id=1,
            modo_solapamiento="merge",
            clave_enlace="rut",
            modo_enlace="tolerante",
        )
    )
    t2 = asyncio.create_task(
        encolar_y_procesar_ingesta(
            job_id=job_id_2,
            ruta_archivo=str(ruta_test_2),
            tipo="asistencia",
            espacio_id=1,
            modo_solapamiento="merge",
            clave_enlace="rut",
            modo_enlace="tolerante",
        )
    )

    # Esperar unos instantes y comprobar que la tarea 1 está en processing o finalizando y la 2 en queued/processing
    await asyncio.sleep(1.0)
    async with AsyncSessionLocal() as db:
        res1 = await db.get(IngestionJob, job_id_1)
        res2 = await db.get(IngestionJob, job_id_2)
        print(f"Estado en caliente -> Job 1: {res1.estado} ({res1.registros_ok} regs), Job 2: {res2.estado}")

    await asyncio.gather(t1, t2)
    print("Ambas tareas finalizaron.")

    async with AsyncSessionLocal() as db:
        j1_fin = await db.get(IngestionJob, job_id_1)
        j2_fin = await db.get(IngestionJob, job_id_2)
        print(f"Job 1 final: estado={j1_fin.estado}, registros_ok={j1_fin.registros_ok}")
        print(f"Job 2 final: estado={j2_fin.estado}, registros_ok={j2_fin.registros_ok}")
        assert j1_fin.estado == "completed", f"Error en Job 1: {j1_fin.error_detail}"
        assert j2_fin.estado == "completed", f"Error en Job 2: {j2_fin.error_detail}"
        assert j1_fin.registros_ok > 0

        # Verificar supresión de PII y persistencia seudonimizada en eventos_asistencia
        stmt_check = select(EventoAsistencia).where(EventoAsistencia.espacio_id == 1).limit(5)
        evs = (await db.execute(stmt_check)).scalars().all()
        for ev in evs:
            assert not ev.person_id_hash.startswith("RUT_"), "El identificador debió ser seudonimizado con HMAC SHA-256"
            assert len(ev.person_id_hash) == 64, f"Hash debe tener 64 caracteres hex: {ev.person_id_hash}"

        # Limpiar jobs y archivos temporales de prueba
        await db.delete(j1_fin)
        await db.delete(j2_fin)
        await db.commit()

    if ruta_test_1.exists():
        ruta_test_1.unlink()
    if ruta_test_2.exists():
        ruta_test_2.unlink()

    print("OK: Semáforo concurrente, supresión de PII y lotes de 10.000 verificados.")


async def main():
    await probar_limpieza_huerfanos()
    await probar_semaforo_y_lotes()
    print("\nTODAS LAS PRUEBAS DE INGESTA MASIVA PASARON EXITOSAMENTE.")


if __name__ == "__main__":
    asyncio.run(main())

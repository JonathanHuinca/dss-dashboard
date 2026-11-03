"""
seed.py — Comando CLI de poblado inicial.

Uso:
    cd backend/
    python -m app.cli seed-data

Ejecuta FileIngestionAdapter sobre Documentos_soloVista/, seudonimiza
los identificadores (Ley 21.719), inserta por lotes en las hipertablas
de TimescaleDB y carga el calendario académico UCT.

Imprime resumen de filas insertadas por tabla.
"""
import asyncio
import sys
import time
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

BASE_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = Path("/Documentos_soloVista") if Path("/Documentos_soloVista").exists() else BASE_DIR / "Documentos_soloVista"
MODELS_DIR = BASE_DIR / "backend" / "models"

sys.path.insert(0, str(BASE_DIR / "backend"))

from app.adapters.file_adapter import FileIngestionAdapter
from app.core.database import AsyncSessionLocal

BATCH_SIZE = 500

ESPACIO_BIBLIOTECA_ID = 1
ESPACIO_ESTACIONAMIENTO_ID = 2


async def _insert_attendance(session: AsyncSession, adapter: FileIngestionAdapter) -> int:
    print("  -> Cargando eventos de asistencia...")
    await session.execute(
        sa.text("DELETE FROM eventos_asistencia WHERE espacio_id = :espacio_id"),
        {"espacio_id": ESPACIO_BIBLIOTECA_ID}
    )
    events = await adapter.fetch_attendance_events(espacio_id=ESPACIO_BIBLIOTECA_ID)
    total = 0
    for i in range(0, len(events), BATCH_SIZE):
        batch = events[i : i + BATCH_SIZE]
        rows = [
            {
                "time": e.time,
                "espacio_id": e.espacio_id,
                "person_id_hash": e.person_id_hash,
                "door_entrada": e.door_entrada,
                "door_salida": e.door_salida,
                "primera_entrada": e.primera_entrada,
                "ultima_salida": e.ultima_salida,
                "salida_imputada": e.salida_imputada,
                "entrada_imputada": e.entrada_imputada,
                "permanencia_min": e.permanencia_min,
                "marcajes_totales": e.marcajes_totales,
                "alerta_coherencia_fechas": e.alerta_coherencia_fechas,
                "alerta_marcajes": e.alerta_marcajes,
            }
            for e in batch
            if e.time is not None
        ]
        if rows:
            stmt = sa.text("""
                INSERT INTO eventos_asistencia (
                    time, espacio_id, person_id_hash, door_entrada, door_salida,
                    primera_entrada, ultima_salida, salida_imputada, entrada_imputada, permanencia_min,
                    marcajes_totales, alerta_coherencia_fechas, alerta_marcajes
                ) VALUES (
                    :time, :espacio_id, :person_id_hash, :door_entrada, :door_salida,
                    :primera_entrada, :ultima_salida, :salida_imputada, :entrada_imputada, :permanencia_min,
                    :marcajes_totales, :alerta_coherencia_fechas, :alerta_marcajes
                )
            """)
            await session.execute(stmt, rows)
            total += len(rows)
        sys.stdout.write(f"\r    Insertados: {total}/{len(events)}")
        sys.stdout.flush()
    print()
    return total


async def _insert_vehicles(session: AsyncSession, adapter: FileIngestionAdapter) -> int:
    print("  -> Cargando eventos vehiculares ANPR...")
    await session.execute(
        sa.text("DELETE FROM eventos_vehiculares WHERE espacio_id = :espacio_id"),
        {"espacio_id": ESPACIO_ESTACIONAMIENTO_ID}
    )
    raw_events = await adapter.fetch_vehicle_events(espacio_id=ESPACIO_ESTACIONAMIENTO_ID)
    seen_keys = set()
    events = []
    for e in raw_events:
        if e.time is not None:
            k = (e.time, e.espacio_id, e.patente_hash, e.camara)
            if k not in seen_keys:
                seen_keys.add(k)
                events.append(e)

    total = 0
    for i in range(0, len(events), BATCH_SIZE):
        batch = events[i : i + BATCH_SIZE]
        rows = [
            {
                "time": e.time,
                "espacio_id": e.espacio_id,
                "patente_hash": e.patente_hash,
                "patente_cifrada": e.patente_cifrada,
                "camara": e.camara,
                "direccion": e.direccion,
                "tipo_vehiculo": e.tipo_vehiculo,
                "marca": e.marca,
                "color": e.color,
                "calidad_lectura": e.calidad_lectura,
            }
            for e in batch
        ]
        if rows:
            stmt = sa.text("""
                INSERT INTO eventos_vehiculares (
                    time, espacio_id, patente_hash, patente_cifrada, camara, direccion,
                    tipo_vehiculo, marca, color, calidad_lectura
                ) VALUES (
                    :time, :espacio_id, :patente_hash, :patente_cifrada, :camara, :direccion,
                    :tipo_vehiculo, :marca, :color, :calidad_lectura
                )
            """)
            await session.execute(stmt, rows)
            total += len(rows)
        sys.stdout.write(f"\r    Insertados: {total}/{len(events)}")
        sys.stdout.flush()
    print()
    return total


async def _insert_calendar(session: AsyncSession, adapter: FileIngestionAdapter) -> int:
    print("  -> Cargando calendario academico UCT...")
    events = await adapter.fetch_calendar_events()
    valid = [e for e in events if e is not None]
    total = 0
    for i in range(0, len(valid), BATCH_SIZE):
        batch = valid[i : i + BATCH_SIZE]
        rows = [
            {
                "fecha": e.fecha,
                "is_holiday": e.is_holiday,
                "is_break": e.is_break,
                "is_exam_period": e.is_exam_period,
                "is_class_milestone": e.is_class_milestone,
                "suspension_actividades": e.suspension_actividades,
                "descripcion": e.descripcion,
                "fuente": e.fuente,
            }
            for e in batch
        ]
        stmt = sa.text("""
            MERGE INTO calendario_academico AS target
            USING (VALUES (:fecha, :is_holiday, :is_break, :is_exam_period, :is_class_milestone, :suspension_actividades, :descripcion, :fuente))
            AS source (fecha, is_holiday, is_break, is_exam_period, is_class_milestone, suspension_actividades, descripcion, fuente)
            ON target.fecha = source.fecha
            WHEN MATCHED THEN
                UPDATE SET
                    is_holiday = source.is_holiday,
                    is_break = source.is_break,
                    is_exam_period = source.is_exam_period,
                    is_class_milestone = source.is_class_milestone,
                    suspension_actividades = source.suspension_actividades,
                    descripcion = source.descripcion,
                    fuente = source.fuente
            WHEN NOT MATCHED THEN
                INSERT (fecha, is_holiday, is_break, is_exam_period, is_class_milestone, suspension_actividades, descripcion, fuente)
                VALUES (source.fecha, source.is_holiday, source.is_break, source.is_exam_period, source.is_class_milestone, source.suspension_actividades, source.descripcion, source.fuente);
        """)
        await session.execute(stmt, rows)
        total += len(rows)
    return total


async def seed() -> None:
    print("\n========================================================")
    print("  UCT Dashboard -- Seed inicial de datos (Ley 21.719)")
    print("========================================================\n")

    if not DATA_DIR.exists():
        print(f"ERROR: Directorio de datos no encontrado: {DATA_DIR}")
        sys.exit(1)

    adapter = FileIngestionAdapter(data_root=DATA_DIR)

    t0 = time.perf_counter()

    async with AsyncSessionLocal() as session:
        # 1. Espacios
        await session.execute(sa.text("""
            IF NOT EXISTS (SELECT 1 FROM espacios WHERE id = 1)
                INSERT INTO espacios (id, campus, tipo, nombre, capacidad_max, activo) 
                VALUES (1, 'CSF', 'biblioteca', 'Biblioteca Campus San Francisco', 350, 1);
            IF NOT EXISTS (SELECT 1 FROM espacios WHERE id = 2)
                INSERT INTO espacios (id, campus, tipo, nombre, capacidad_max, activo) 
                VALUES (2, 'CSF', 'estacionamiento', 'Estacionamiento Campus San Francisco', 180, 1);
        """))
        await session.commit()

        # 2. Eventos Asistencia (Biblioteca)
        n_attendance = await _insert_attendance(session, adapter)
        await session.commit()

        # 3. Eventos Vehiculares (Estacionamiento)
        n_vehicles = await _insert_vehicles(session, adapter)
        await session.commit()

        # 4. Calendario Academico
        n_calendar = await _insert_calendar(session, adapter)
        await session.commit()

    elapsed = time.perf_counter() - t0

    print("\n+-------------------------------------+")
    print("|         RESUMEN DE INSERCION        |")
    print("+-------------------------------------+")
    print(f"|  eventos_asistencia  : {n_attendance:>8} filas |")
    print(f"|  eventos_vehiculares : {n_vehicles:>8} filas |")
    print(f"|  calendario_academico: {n_calendar:>8} filas |")
    print(f"|  Tiempo total        : {elapsed:>7.2f} seg  |")
    print("+-------------------------------------+\n")
    print("[OK] Seed completado. Los Continuous Aggregates de TimescaleDB")
    print("  se materializaran automaticamente en los proximos 30 minutos.\n")


def main():
    """
    Punto de entrada CLI.
    Uso: python -m app.cli seed-data
    """
    if len(sys.argv) < 2 or sys.argv[1] != "seed-data":
        print("Uso: python -m app.cli seed-data")
        sys.exit(1)
    asyncio.run(seed())


if __name__ == "__main__":
    main()

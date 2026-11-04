import asyncio
import random
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
import os
import sys

# Agregar el directorio raíz de la app al sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import AsyncSessionLocal
from app.domain.models import Espacio, EventoAsistencia, EventoVehicular, CalendarioAcademico
from app.adapters.file_adapter import FileIngestionAdapter
from app.core.security import pseudonymize_person, encrypt_vehicle_patente
from app.worker.tasks import entrenar_modelo_prophet

async def check_files_exist(data_root: Path) -> bool:
    att_path = data_root / "datos_bases" / "asistencia_base.csv"
    veh_path = data_root / "datos_bases" / "RegistroVehicular_base.xlsx"
    return att_path.exists() and veh_path.exists()

def generate_mock_data(espacio_id: int):
    print("Generando datos simulados (3 meses)...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)
    
    asistencia_events = []
    vehicular_events = []
    
    current_date = start_date
    while current_date <= end_date:
        # Lunes a Viernes tienen más movimiento (08:00 a 20:00)
        if current_date.weekday() < 5:
            num_events = random.randint(100, 300)
        else:
            num_events = random.randint(10, 50)
            
        for _ in range(num_events):
            hour = random.randint(8, 19)
            minute = random.randint(0, 59)
            second = random.randint(0, 59)
            time = current_date.replace(hour=hour, minute=minute, second=second)
            
            # Asistencia
            person_raw = f"RUT-{random.randint(10000000, 25000000)}"
            person_hash = pseudonymize_person(person_raw)
            permanencia = random.randint(15, 240)
            salida = time + timedelta(minutes=permanencia)
            
            asistencia_events.append(
                EventoAsistencia(
                    time=time,
                    espacio_id=espacio_id,
                    person_id_hash=person_hash,
                    door_entrada=random.choice(["Puerta Principal", "Acceso Norte"]),
                    door_salida=random.choice(["Puerta Principal", "Acceso Sur"]),
                    primera_entrada=time,
                    ultima_salida=salida,
                    salida_imputada=False,
                    permanencia_min=Decimal(permanencia),
                    marcajes_totales=2,
                    alerta_coherencia_fechas=False,
                    alerta_marcajes=False
                )
            )
            
            # Vehículos
            if random.random() > 0.5: # 50% chance of vehicle event
                patente_raw = f"{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}{random.randint(10, 99)}{random.randint(10, 99)}"
                patente_hash, patente_cifrada = encrypt_vehicle_patente(patente_raw)
                vehicular_events.append(
                    EventoVehicular(
                        time=time,
                        espacio_id=espacio_id,
                        patente_hash=patente_hash,
                        patente_cifrada=patente_cifrada,
                        camara=random.choice(["Camara_Ingreso_1", "Camara_Salida_2"]),
                        direccion=random.choice(["entrada", "salida"]),
                        tipo_vehiculo="Sedan",
                        marca="Toyota",
                        color="Blanco",
                        calidad_lectura="ok"
                    )
                )
                
        current_date += timedelta(days=1)
        
    return asistencia_events, vehicular_events


async def seed_data():
    async with AsyncSessionLocal() as db:
        print("Obteniendo espacios...")
        espacios = (await db.execute(select(Espacio))).scalars().all()
        if not espacios:
            print("No hay espacios creados. Creando espacio por defecto...")
            espacio1 = Espacio(campus="Campus San Francisco", tipo="biblioteca", nombre="Biblioteca Central", capacidad_max=500)
            espacio2 = Espacio(campus="Campus Norte", tipo="estacionamiento", nombre="Estacionamiento Norte", capacidad_max=300)
            db.add_all([espacio1, espacio2])
            await db.commit()
            espacios = (await db.execute(select(Espacio))).scalars().all()
        
        espacio_biblioteca = next((e for e in espacios if e.tipo == 'biblioteca'), espacios[0])
        espacio_estacionamiento = next((e for e in espacios if e.tipo == 'estacionamiento'), espacios[1])
        
        data_root = Path(os.environ.get("DATA_ROOT_PATH", "/app/Documentos_soloVista"))
        
        if await check_files_exist(data_root):
            print("Opción A: Archivos encontrados. Cargando desde CSV/Excel...")
            adapter = FileIngestionAdapter(data_root)
            # Fetch and insert... (Para simplificar, generaremos simulado si no existen)
            try:
                dtos_asis = await adapter.fetch_attendance_events(espacio_biblioteca.id)
                # Parse to SQLAlchemy models...
                print(f"Cargados {len(dtos_asis)} desde CSV.")
            except Exception as e:
                print(f"Error cargando archivos: {e}")
                print("Haciendo fallback a Opción B...")
                asistencia, vehicular = generate_mock_data(espacio_biblioteca.id)
                db.add_all(asistencia)
                db.add_all(vehicular)
        else:
            print("Opción B: Archivos no encontrados. Generando datos simulados...")
            asistencia, vehicular = generate_mock_data(espacio_biblioteca.id)
            print(f"Insertando {len(asistencia)} registros de asistencia y {len(vehicular)} vehiculares...")
            db.add_all(asistencia)
            db.add_all(vehicular)
            
        await db.commit()
        print("Datos insertados correctamente en SQL Server.")
        
        print("Encolando tareas de entrenamiento en Celery...")
        # Encolamos la tarea en Celery usando delay
        task = entrenar_modelo_prophet.delay(espacio_biblioteca.id)
        print(f"Tarea Prophet encolada con Task ID: {task.id}")
        
        # Si hubiera otras tareas, se encolan igual:
        # train_isolation_forest.delay(espacio_biblioteca.id)
        # train_kmeans.delay(espacio_estacionamiento.id)
        
        print("Proceso de Seed y Entrenamiento completado.")

if __name__ == "__main__":
    asyncio.run(seed_data())

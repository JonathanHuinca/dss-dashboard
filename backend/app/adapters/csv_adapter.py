import io
import asyncio
import logging
import pandas as pd
from typing import List
from datetime import datetime

from app.adapters.base import (
    IngestionAdapter,
    AttendanceEventDTO,
    VehicleEventDTO,
    CalendarEventDTO
)
from app.core.security import pseudonymize_person, encrypt_vehicle_patente

logger = logging.getLogger(__name__)

class CsvIngestionAdapter(IngestionAdapter):
    """
    Adaptador para ingesta de archivos cargados via HTTP (bytes en memoria).
    - Asistencia: CSV
    - Vehicular: XLSX (con 6 lineas de cabecera previas)
    """

    def __init__(self, file_bytes: bytes, filename: str, espacio_id: int):
        self.file_bytes = file_bytes
        self.filename = filename.lower()
        self.espacio_id = espacio_id

    async def fetch_attendance_events(self, espacio_id: int) -> List[AttendanceEventDTO]:
        if not self.filename.endswith('.csv'):
            logger.error(f"Archivo {self.filename} no es CSV, retornando lista vacia para asistencia")
            return []

        def _process():
            try:
                df = pd.read_csv(io.BytesIO(self.file_bytes), encoding='utf-8')
            except UnicodeDecodeError as e:
                logger.error(f"Error UnicodeDecodeError leyendo CSV UTF-8, intentando latin-1: {e}")
                try:
                    df = pd.read_csv(io.BytesIO(self.file_bytes), encoding='latin-1')
                except Exception as ex:
                    logger.error(f"Error leyendo CSV latin-1: {ex}")
                    return []
            except Exception as e:
                logger.error(f"Error inesperado leyendo CSV de asistencia: {e}")
                return []

            # CRITICO Ley 21.719: Eliminar PII antes de cualquier procesamiento
            df.drop(columns=["Persona", "Telefono", "Lista de vehiculos"], errors="ignore", inplace=True)

            dtos = []
            for _, row in df.iterrows():
                try:
                    fecha_str = str(row['Fecha']) if pd.notna(row.get('Fecha')) else ""
                    hora_str = str(row['Primera entrada']) if pd.notna(row.get('Primera entrada')) else "00:00:00"

                    if not fecha_str or fecha_str.strip() == "nan":
                        continue

                    # Parse time
                    try:
                        time_val = pd.to_datetime(f"{fecha_str} {hora_str}")
                    except Exception as e:
                        logger.error(f"Error parseando fecha/hora en asistencia: {e}")
                        continue

                    primera_entrada = time_val
                    ultima_salida = pd.to_datetime(f"{fecha_str} {row['Ultima salida']}") if pd.notna(row.get('Ultima salida')) else None
                    
                    person_id = str(row.get('personId', ''))
                    person_id_hash = pseudonymize_person(person_id) if person_id else "UNKNOWN"

                    permanencia = 0.0
                    if pd.notna(row.get('Dif. salida (min)')):
                        try:
                            permanencia = float(row['Dif. salida (min)'])
                        except ValueError as e:
                            logger.error(f"Error parseando permanencia_min: {e}")
                            permanencia = 0.0

                    marcajes = 1
                    if pd.notna(row.get('Marcajes')):
                        try:
                            marcajes = int(row['Marcajes'])
                        except ValueError as e:
                            logger.error(f"Error parseando marcajes: {e}")
                            marcajes = 1

                    dtos.append(AttendanceEventDTO(
                        time=time_val,
                        espacio_id=espacio_id,
                        person_id_hash=person_id_hash,
                        door_entrada=str(row.get('Door entrada')) if pd.notna(row.get('Door entrada')) else None,
                        door_salida=str(row.get('Door salida')) if pd.notna(row.get('Door salida')) else None,
                        primera_entrada=primera_entrada,
                        ultima_salida=ultima_salida,
                        salida_imputada=pd.isna(row.get('Ultima salida')),
                        permanencia_min=permanencia,
                        marcajes_totales=marcajes,
                        alerta_coherencia_fechas=False,
                        alerta_marcajes=False,
                        carrera=None, facultad=None, modalidad=None, edad=None, sexo=None
                    ))
                except Exception as e:
                    logger.error(f"Error procesando fila asistencia: {e}")
            return dtos

        return await asyncio.to_thread(_process)

    async def fetch_vehicle_events(self, espacio_id: int) -> List[VehicleEventDTO]:
        if not self.filename.endswith('.xlsx'):
            logger.error(f"Archivo {self.filename} no es XLSX, retornando lista vacia para vehiculos")
            return []

        def _process():
            try:
                # XLSX de HikCentral tiene 6 filas de metadatos antes del header
                df = pd.read_excel(io.BytesIO(self.file_bytes), skiprows=6)
            except Exception as e:
                logger.error(f"Error leyendo XLSX vehicular: {e}")
                return []

            # CRITICO Ley 21.719: Eliminar PII antes de procesar
            df.drop(columns=["Persona", "Telefono", "Lista de vehiculos"], errors="ignore", inplace=True)

            dtos = []
            for _, row in df.iterrows():
                try:
                    if 'Hora' not in row or pd.isna(row['Hora']):
                        continue
                        
                    time_val = pd.to_datetime(row['Hora'])
                    
                    patente_raw = str(row.get('Numero de matricula', ''))
                    if not patente_raw or patente_raw.strip() == "nan":
                        continue
                        
                    patente_hash, patente_cifrada = encrypt_vehicle_patente(patente_raw)

                    dtos.append(VehicleEventDTO(
                        time=time_val,
                        espacio_id=espacio_id,
                        patente_hash=patente_hash,
                        patente_cifrada=patente_cifrada,
                        camara=str(row.get('Camara', 'Desconocida')),
                        direccion=str(row.get('Direccion de conduccion', 'Desconocida')),
                        tipo_vehiculo=str(row.get('Tipo de vehiculo')) if pd.notna(row.get('Tipo de vehiculo')) else None,
                        marca=str(row.get('Marca')) if pd.notna(row.get('Marca')) else None,
                        color=str(row.get('Color del vehiculo')) if pd.notna(row.get('Color del vehiculo')) else None,
                        calidad_lectura="ALTA"
                    ))
                except Exception as e:
                    logger.error(f"Error procesando fila vehicular: {e}")
            return dtos

        return await asyncio.to_thread(_process)

    async def fetch_calendar_events(self) -> List[CalendarEventDTO]:
        if not self.filename.endswith('.csv'):
            logger.error(f"Archivo calendario {self.filename} no es CSV, retornando vacio")
            return []

        def _process():
            try:
                df = pd.read_csv(io.BytesIO(self.file_bytes), encoding='utf-8')
            except UnicodeDecodeError as e:
                logger.error(f"Error UnicodeDecodeError calendario UTF-8: {e}")
                try:
                    df = pd.read_csv(io.BytesIO(self.file_bytes), encoding='latin-1')
                except Exception as ex:
                    logger.error(f"No se pudo leer calendario en latin-1: {ex}")
                    return []
            except Exception as e:
                logger.error(f"Error inesperado leyendo calendario: {e}")
                return []

            dtos = []
            for _, row in df.iterrows():
                try:
                    if 'fecha' not in row or pd.isna(row['fecha']):
                        continue
                        
                    dtos.append(CalendarEventDTO(
                        fecha=pd.to_datetime(row['fecha']).date(),
                        is_holiday=bool(row.get('is_holiday', False)),
                        is_break=bool(row.get('is_break', False)),
                        is_exam_period=bool(row.get('is_exam_period', False)),
                        is_class_milestone=bool(row.get('is_class_milestone', False)),
                        suspension_actividades=bool(row.get('suspension_actividades', False)),
                        descripcion=str(row.get('descripcion')) if pd.notna(row.get('descripcion')) else None,
                        fuente="upload"
                    ))
                except Exception as e:
                    logger.error(f"Error procesando fila calendario: {e}")
            return dtos

        return await asyncio.to_thread(_process)

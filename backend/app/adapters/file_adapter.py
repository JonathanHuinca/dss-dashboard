"""
FileIngestionAdapter — Implementación activa para la tesis.

Consume los archivos en Documentos_soloVista/, aplica la seudonimización
HMAC-SHA-256 (Ley 21.719) y entrega DTOs normalizados listos para insertar
en las hipertablas de TimescaleDB.

Columnas reales confirmadas:
  asistencia_base.csv:
    Fecha, Persona, personId, Marcajes, Primera entrada, Door entrada,
    Dif. entrada (min), Última salida, Door salida, Dif. salida (min)

  RegistroVehicular_base.xlsx  (6 filas de metadatos HikCentral antes de la cabecera):
    Número de matrícula, Hora, Cámara, Lista de vehículos, Teléfono,
    Tipo de vehículo, Marca, Color del vehículo, Dirección de conducción

  calendario_academico_ml - copia.xlsx:
    Año, Fecha de Inicio, Fecha de Término, Agente, Hito Académico,
    Feriado, Semana de Receso, is_holiday, is_break, is_exam_period,
    is_class_milestone, termino a las 1, suspensión actividades
"""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import zoneinfo

import pandas as pd

from app.adapters.base import (
    AttendanceEventDTO,
    CalendarEventDTO,
    IngestionAdapter,
    VehicleEventDTO,
)
from app.core.security import pseudonymize_person, pseudonymize_vehicle

TZ_SANTIAGO = zoneinfo.ZoneInfo("America/Santiago")

MARCAJES_MAX_UMBRAL = 20

HIKCENTRAL_HEADER_ROWS = 6

CAMARA_DIRECCION_MAP: dict[str, str] = {
    "Avanzar": "entrada",
    "Retroceder": "salida",
    "avanzar": "entrada",
    "retroceder": "salida",
}

CALIDAD_UNKNOWN = "unknown"


def _to_tz(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None or pd.isna(dt):
        return None
    if isinstance(dt, str):
        try:
            dt = pd.to_datetime(dt)
        except Exception:
            return None
    if hasattr(dt, "tzinfo") and dt.tzinfo is None:
        return dt.replace(tzinfo=TZ_SANTIAGO)
    return dt


def _parse_ts(value) -> Optional[datetime]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        ts = pd.to_datetime(value)
        return _to_tz(ts.to_pydatetime())
    except Exception:
        return None


class FileIngestionAdapter(IngestionAdapter):
    """
    Lee los archivos fuente de Documentos_soloVista/, seudonimiza los
    identificadores y devuelve DTOs normalizados.
    """

    def __init__(self, data_root: Path):
        self.data_root = data_root

    async def fetch_attendance_events(self, espacio_id: int) -> list[AttendanceEventDTO]:
        path = self.data_root / "datos_bases" / "asistencia_base.csv"
        df = await asyncio.to_thread(self._load_attendance, path)
        return [self._map_attendance_row(row, espacio_id) for _, row in df.iterrows()]

    async def fetch_vehicle_events(self, espacio_id: int) -> list[VehicleEventDTO]:
        path = self.data_root / "datos_bases" / "RegistroVehicular_base.xlsx"
        df = await asyncio.to_thread(self._load_vehicles, path)
        return [self._map_vehicle_row(row, espacio_id) for _, row in df.iterrows()]

    async def fetch_calendar_events(self) -> list[CalendarEventDTO]:
        path = (
            self.data_root
            / "datos_calendario_academico"
            / "scraping_calendario_academico"
            / "calendario_academico_ml - copia.xlsx"
        )
        df = await asyncio.to_thread(self._load_calendar, path)
        events = [self._map_calendar_row(row) for _, row in df.iterrows()]
        return [e for e in events if e is not None and e.fecha is not None]

    # ------------------------------------------------------------------
    # Loaders (ejecutados en hilo para no bloquear el event loop)
    # ------------------------------------------------------------------

    def _load_attendance(self, path: Path) -> pd.DataFrame:
        df = pd.read_csv(
            path,
            encoding="utf-8-sig",
            dtype={"personId": str},
        )
        df.columns = [c.strip() for c in df.columns]
        # Supresión inmediata en memoria de datos personales directos (Ley 21.719)
        df.drop(columns=["Persona"], errors="ignore", inplace=True)
        return df

    def _load_vehicles(self, path: Path) -> pd.DataFrame:
        df = pd.read_excel(
            path,
            header=HIKCENTRAL_HEADER_ROWS,
            dtype={"Número de matrícula": str},
        )
        df.columns = [c.strip() for c in df.columns]
        # Supresión inmediata de teléfonos (Ley 21.719)
        df.drop(columns=["Teléfono", "Lista de vehículos"], errors="ignore", inplace=True)
        return df

    def _load_calendar(self, path: Path) -> pd.DataFrame:
        df = pd.read_excel(path, dtype=str)
        df.columns = [c.strip() for c in df.columns]
        return df

    # ------------------------------------------------------------------
    # Mappers por fila
    # ------------------------------------------------------------------

    def _map_attendance_row(self, row: pd.Series, espacio_id: int) -> AttendanceEventDTO:
        person_id_raw = str(row.get("personId", "")).strip()
        person_id_hash = pseudonymize_person(person_id_raw) if person_id_raw else "unknown"

        primera_entrada = _parse_ts(row.get("Primera entrada"))
        ultima_salida   = _parse_ts(row.get("Última salida"))
        time            = primera_entrada or _parse_ts(row.get("Fecha"))
        if primera_entrada is None and time is not None:
            primera_entrada = time

        marcajes = int(row.get("Marcajes", 1) or 1)

        permanencia_min: Optional[float] = None
        if primera_entrada and ultima_salida and ultima_salida > primera_entrada:
            permanencia_min = round(
                (ultima_salida - primera_entrada).total_seconds() / 60, 2
            )

        alerta_coherencia = bool(
            primera_entrada and ultima_salida and primera_entrada > ultima_salida
        )
        alerta_marcajes = marcajes > MARCAJES_MAX_UMBRAL

        return AttendanceEventDTO(
            time=time,
            espacio_id=espacio_id,
            person_id_hash=person_id_hash,
            door_entrada=str(row.get("Door entrada", "")).strip() or None,
            door_salida=str(row.get("Door salida", "")).strip() or None,
            primera_entrada=primera_entrada,
            ultima_salida=ultima_salida,
            salida_imputada=ultima_salida is None,
            permanencia_min=permanencia_min,
            marcajes_totales=marcajes,
            alerta_coherencia_fechas=alerta_coherencia,
            alerta_marcajes=alerta_marcajes,
        )

    def _map_vehicle_row(self, row: pd.Series, espacio_id: int) -> VehicleEventDTO:
        patente_raw = str(row.get("Número de matrícula", "")).strip()
        es_unknown = not patente_raw or patente_raw.lower() == "unknown"
        patente_hash = pseudonymize_vehicle(patente_raw) if not es_unknown else "unknown"
        calidad = CALIDAD_UNKNOWN if es_unknown else "ok"

        time = _parse_ts(row.get("Hora"))

        direccion_raw = str(row.get("Dirección de conducción", "")).strip()
        direccion = CAMARA_DIRECCION_MAP.get(direccion_raw, "entrada")

        return VehicleEventDTO(
            time=time,
            espacio_id=espacio_id,
            patente_hash=patente_hash,
            camara=str(row.get("Cámara", "")).strip(),
            direccion=direccion,
            tipo_vehiculo=str(row.get("Tipo de vehículo", "")).strip() or None,
            marca=str(row.get("Marca", "")).strip() or None,
            color=str(row.get("Color del vehículo", "")).strip() or None,
            calidad_lectura=calidad,
        )

    def _map_calendar_row(self, row: pd.Series) -> Optional[CalendarEventDTO]:
        fecha_raw = str(row.get("Fecha de Inicio", "")).strip()
        try:
            ts = pd.to_datetime(fecha_raw, dayfirst=True)
            if pd.isna(ts):
                return None
            fecha = ts.date()
        except Exception:
            return None

        def _bool(val) -> bool:
            try:
                return int(float(str(val))) == 1
            except Exception:
                return False

        hito = str(row.get("Hito Académico", "")).strip() or None

        return CalendarEventDTO(
            fecha=fecha,
            is_holiday=_bool(row.get("is_holiday")),
            is_break=_bool(row.get("is_break")),
            is_exam_period=_bool(row.get("is_exam_period")),
            is_class_milestone=_bool(row.get("is_class_milestone")),
            suspension_actividades=_bool(row.get("suspensión actividades")),
            descripcion=hito,
            fuente="scraping",
        )

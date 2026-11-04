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
from app.core.security import pseudonymize_person, encrypt_vehicle_patente

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
        records = df.to_dict("records")
        return [self._map_attendance_row(row, espacio_id) for row in records]

    async def fetch_vehicle_events(self, espacio_id: int) -> list[VehicleEventDTO]:
        path = self.data_root / "datos_bases" / "RegistroVehicular_base.xlsx"
        df = await asyncio.to_thread(self._load_vehicles, path)
        records = df.to_dict("records")
        return [self._map_vehicle_row(row, espacio_id) for row in records]

    async def fetch_calendar_events(self) -> list[CalendarEventDTO]:
        path = (
            self.data_root
            / "datos_calendario_academico"
            / "calendario_academico_ml - copia.xlsx"
        )
        if not path.exists():
            path = (
                self.data_root
                / "datos_calendario_academico"
                / "scraping_calendario_academico"
                / "calendario_academico_ml - copia.xlsx"
            )
        df = await asyncio.to_thread(self._load_calendar, path)
        records = df.to_dict("records")
        events = [self._map_calendar_row(row) for row in records]
        
        # Agrupar por fecha unica para respetar PK en SQL Server
        grouped: dict[str, CalendarEventDTO] = {}
        for e in events:
            if e is not None and e.fecha is not None:
                if e.fecha not in grouped:
                    grouped[e.fecha] = e
                else:
                    curr = grouped[e.fecha]
                    curr.is_holiday = curr.is_holiday or e.is_holiday
                    curr.is_break = curr.is_break or e.is_break
                    curr.is_exam_period = curr.is_exam_period or e.is_exam_period
                    curr.is_class_milestone = curr.is_class_milestone or e.is_class_milestone
                    curr.suspension_actividades = curr.suspension_actividades or e.suspension_actividades
                    if e.descripcion and e.descripcion not in curr.descripcion:
                        curr.descripcion = f"{curr.descripcion} / {e.descripcion}"
        return list(grouped.values())

    # ------------------------------------------------------------------
    # Loaders (ejecutados en hilo para no bloquear el event loop)
    # ------------------------------------------------------------------

    def _load_attendance(self, path: Path) -> pd.DataFrame:
        df = pd.read_csv(
            path,
            encoding="utf-8-sig",
            dtype={"personId": str},
        )
        # Normalizar nombres de columnas (resuelve codificacion en 'Última salida')
        col_map = {}
        for c in df.columns:
            c_low = c.strip().lower()
            if "fecha" in c_low:
                col_map[c] = "fecha"
            elif "personid" in c_low:
                col_map[c] = "person_id"
            elif "marcajes" in c_low:
                col_map[c] = "marcajes"
            elif "primera" in c_low and "entrada" in c_low:
                col_map[c] = "primera_entrada"
            elif "door" in c_low and "entrada" in c_low:
                col_map[c] = "door_entrada"
            elif "dif" in c_low and "entrada" in c_low:
                col_map[c] = "dif_entrada"
            elif "salida" in c_low and "door" not in c_low and "dif" not in c_low:
                col_map[c] = "ultima_salida"
            elif "door" in c_low and "salida" in c_low:
                col_map[c] = "door_salida"
            elif "dif" in c_low and "salida" in c_low:
                col_map[c] = "dif_salida"
        df.rename(columns=col_map, inplace=True)
        
        # PRIVACIDAD ESTRICTA: Supresión inmediata
        df.drop(columns=["Persona", "persona", "nombre", "correo", "email", "telefono"], errors="ignore", inplace=True)
        
        # Vectorizar parseo de fechas para alto rendimiento
        df["pe_dt"] = pd.to_datetime(df["primera_entrada"], errors="coerce")
        df["us_dt"] = pd.to_datetime(df["ultima_salida"], errors="coerce")
        df["f_dt"] = pd.to_datetime(df["fecha"], errors="coerce")
        df["time_dt"] = df["pe_dt"].fillna(df["us_dt"]).fillna(df["f_dt"])

        # Enriquecimiento de Datos: CSV Complementario
        comp_path = path.parent / "institucional.csv"
        if comp_path.exists():
            df_comp = pd.read_csv(comp_path, encoding="utf-8-sig", dtype={"personId": str})
            df_comp.drop(columns=["nombre", "correo", "email", "telefono"], errors="ignore", inplace=True)
            df = pd.merge(df, df_comp, left_on="person_id", right_on="personId", how="left")
            
        return df

    def _load_vehicles(self, path: Path) -> pd.DataFrame:
        df = pd.read_excel(
            path,
            header=HIKCENTRAL_HEADER_ROWS,
            dtype={"Número de matrícula": str},
        )
        df.columns = [c.strip() for c in df.columns]
        # PRIVACIDAD ESTRICTA: Supresión inmediata de PII
        df.drop(columns=["Teléfono", "Lista de vehículos", "nombre", "correo", "email", "telefono"], errors="ignore", inplace=True)
        return df

    def _load_calendar(self, path: Path) -> pd.DataFrame:
        df = pd.read_excel(path, dtype=str)
        df.columns = [c.strip() for c in df.columns]
        return df

    # ------------------------------------------------------------------
    # Mappers por fila
    # ------------------------------------------------------------------

    def _map_attendance_row(self, row: dict, espacio_id: int) -> AttendanceEventDTO:
        person_id_raw = str(row.get("person_id") or row.get("personId") or "").strip()
        person_id_hash = pseudonymize_person(person_id_raw) if person_id_raw else "unknown"

        pe_val = row.get("pe_dt")
        primera_entrada = _to_tz(pe_val.to_pydatetime()) if pd.notna(pe_val) else None

        us_val = row.get("us_dt")
        ultima_salida = _to_tz(us_val.to_pydatetime()) if pd.notna(us_val) else None

        time_val = row.get("time_dt")
        time = _to_tz(time_val.to_pydatetime()) if pd.notna(time_val) else None

        entrada_imputada = bool(primera_entrada is None and ultima_salida is not None)
        salida_imputada = bool(ultima_salida is None and primera_entrada is not None)

        marcajes_raw = row.get("marcajes")
        try:
            marcajes = int(marcajes_raw) if pd.notna(marcajes_raw) else 1
        except Exception:
            marcajes = 1

        permanencia_min: Optional[float] = None
        if primera_entrada and ultima_salida and ultima_salida > primera_entrada:
            permanencia_min = round(
                (ultima_salida - primera_entrada).total_seconds() / 60, 2
            )

        alerta_coherencia = bool(
            primera_entrada and ultima_salida and primera_entrada > ultima_salida
        )
        alerta_marcajes = marcajes > MARCAJES_MAX_UMBRAL

        # Puertas limpias sin nan ni .0
        door_in = row.get("door_entrada")
        door_entrada = None
        if pd.notna(door_in) and str(door_in).strip() not in ("", "nan", "None"):
            door_entrada = str(int(door_in)) if isinstance(door_in, (int, float)) else str(door_in).strip().replace(".0", "")

        door_out = row.get("door_salida")
        door_salida = None
        if pd.notna(door_out) and str(door_out).strip() not in ("", "nan", "None"):
            door_salida = str(int(door_out)) if isinstance(door_out, (int, float)) else str(door_out).strip().replace(".0", "")

        return AttendanceEventDTO(
            time=time,
            espacio_id=espacio_id,
            person_id_hash=person_id_hash,
            door_entrada=door_entrada,
            door_salida=door_salida,
            primera_entrada=primera_entrada,
            ultima_salida=ultima_salida,
            salida_imputada=salida_imputada,
            entrada_imputada=entrada_imputada,
            permanencia_min=permanencia_min,
            marcajes_totales=marcajes,
            alerta_coherencia_fechas=alerta_coherencia,
            alerta_marcajes=alerta_marcajes,
            carrera=str(row.get("carrera", "")) or None if pd.notna(row.get("carrera")) else None,
            facultad=str(row.get("facultad", "")) or None if pd.notna(row.get("facultad")) else None,
            modalidad=str(row.get("modalidad", "")) or None if pd.notna(row.get("modalidad")) else None,
            edad=int(row["edad"]) if pd.notna(row.get("edad")) else None,
            sexo=str(row.get("sexo", "")) or None if pd.notna(row.get("sexo")) else None,
        )

    def _map_vehicle_row(self, row: pd.Series, espacio_id: int) -> VehicleEventDTO:
        patente_raw = str(row.get("Número de matrícula", "")).strip()
        es_unknown = not patente_raw or patente_raw.lower() == "unknown"
        
        if not es_unknown:
            patente_hash, patente_cifrada = encrypt_vehicle_patente(patente_raw)
        else:
            patente_hash, patente_cifrada = "unknown", "unknown"
            
        calidad = CALIDAD_UNKNOWN if es_unknown else "ok"

        time = _parse_ts(row.get("Hora"))

        direccion_raw = str(row.get("Dirección de conducción", "")).strip()
        direccion = CAMARA_DIRECCION_MAP.get(direccion_raw, "entrada")

        return VehicleEventDTO(
            time=time,
            espacio_id=espacio_id,
            patente_hash=patente_hash,
            patente_cifrada=patente_cifrada,
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

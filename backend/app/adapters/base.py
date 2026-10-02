from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional


@dataclass
class AttendanceEventDTO:
    """DTO normalizado de evento de asistencia — sin datos personales directos."""
    time: datetime
    espacio_id: int
    person_id_hash: str
    door_entrada: Optional[str]
    door_salida: Optional[str]
    primera_entrada: datetime
    ultima_salida: Optional[datetime]
    salida_imputada: bool
    permanencia_min: Optional[float]
    marcajes_totales: int
    alerta_coherencia_fechas: bool
    alerta_marcajes: bool


@dataclass
class VehicleEventDTO:
    """DTO normalizado de evento vehicular ANPR — sin patente en claro."""
    time: datetime
    espacio_id: int
    patente_hash: str
    camara: str
    direccion: str
    tipo_vehiculo: Optional[str]
    marca: Optional[str]
    color: Optional[str]
    calidad_lectura: str


@dataclass
class CalendarEventDTO:
    fecha: date
    is_holiday: bool
    is_break: bool
    is_exam_period: bool
    is_class_milestone: bool
    suspension_actividades: bool
    descripcion: Optional[str]
    fuente: str = "scraping"


class IngestionAdapter(ABC):
    """
    Interfaz abstracta (Patrón Adapter / GoF) para fuentes de datos de ingesta.
    Implementaciones:
      - FileIngestionAdapter: consume archivos CSV/XLSX de Documentos_soloVista/ (activa en tesis)
      - HikCentralOpenAPIAdapter: consume API REST de HikCentral en producción
    """

    @abstractmethod
    async def fetch_attendance_events(self, espacio_id: int) -> list[AttendanceEventDTO]:
        """Retorna eventos de asistencia peatonal normalizados y seudonimizados."""
        ...

    @abstractmethod
    async def fetch_vehicle_events(self, espacio_id: int) -> list[VehicleEventDTO]:
        """Retorna eventos vehiculares ANPR normalizados y seudonimizados."""
        ...

    @abstractmethod
    async def fetch_calendar_events(self) -> list[CalendarEventDTO]:
        """Retorna hitos del calendario académico UCT."""
        ...

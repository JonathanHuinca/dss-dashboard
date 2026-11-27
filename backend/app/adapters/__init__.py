from app.adapters.base import IngestionAdapter, AttendanceEventDTO, VehicleEventDTO, CalendarEventDTO
from app.adapters.file_adapter import FileIngestionAdapter
from app.adapters.smart_campus_adapter import SmartCampusAdapter

__all__ = [
    "IngestionAdapter",
    "AttendanceEventDTO",
    "VehicleEventDTO",
    "CalendarEventDTO",
    "FileIngestionAdapter",
    "SmartCampusAdapter",
]


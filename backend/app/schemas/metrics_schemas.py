from pydantic import BaseModel
from typing import Optional, List

class KPISummaryResponse(BaseModel):
    dias_operativos: int
    horas_estudiante: float
    recurrencia_mensual: float
    hora_pico_ingreso: str
    pico_concurrente: int
    carrera_mas_concurrida: Optional[str] = None
    sector_mas_concurrido: Optional[str] = None
    mes_referencia: Optional[str] = None
    periodo_label: Optional[str] = None

class MonthInfo(BaseModel):
    label: str
    inicio: str
    fin: str
    year: int
    month: int

class DateBoundsResponse(BaseModel):
    fecha_min: str
    fecha_max: str
    espacio_id: Optional[int] = None 
    meses_disponibles: List[MonthInfo]

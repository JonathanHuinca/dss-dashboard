from pydantic import BaseModel
from typing import Optional

class KPISummaryResponse(BaseModel):
    dias_operativos: int
    horas_estudiante: float
    recurrencia_mensual: float
    hora_pico_ingreso: str
    pico_concurrente: int
    mes_referencia: Optional[str] = None
    periodo_label: Optional[str] = None

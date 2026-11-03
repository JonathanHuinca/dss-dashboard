from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict


class EjecucionTareaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tarea: str
    disparador: str
    estado: str
    inicio_en: datetime
    fin_en: Optional[datetime] = None
    latido_en: datetime
    usuario_id: Optional[int] = None
    resumen_json: Optional[str] = None
    error: Optional[str] = None
    memoria_pico_mb: Optional[float] = None
    duracion_segundos: Optional[float] = None


class TareaCatalogoItem(BaseModel):
    nombre: str
    descripcion: str
    cron_expresion: str
    en_curso: bool
    proxima_ejecucion: Optional[datetime] = None
    ultima_ejecucion: Optional[EjecucionTareaResponse] = None


class ResumenTareasResponse(BaseModel):
    catalogo: List[TareaCatalogoItem]
    ultimas_ejecuciones: List[EjecucionTareaResponse]
    planificador_activo: bool

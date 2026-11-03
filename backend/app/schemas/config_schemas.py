from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ConfiguracionEspaciosResponse(BaseModel):
    id: int
    espacio_id: int
    ia_asistente_activo: bool
    active_provider: Optional[str] = "gemini"
    default_model: Optional[str] = "gemini-3.5-flash-lite"
    has_api_key: bool = False
    masked_api_key: Optional[str] = None
    updated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class ConfiguracionEspaciosUpdate(BaseModel):
    ia_asistente_activo: bool


class LLMProviderUpdate(BaseModel):
    provider: str
    default_model: str
    api_key: str


import json
from pydantic import BaseModel, ConfigDict, field_validator


class HorarioOperacionBase(BaseModel):
    espacio_id: int
    anio: int
    descripcion: str
    tipo_horario: Optional[str] = "regular"
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None
    hora_apertura: str = "08:30"
    hora_cierre: str = "20:30"
    cierre_dia_siguiente: bool = False
    es_continuo_24h: bool = False
    configuracion_dias: Optional[dict] = None
    subespacio: Optional[str] = "todos"
    activo: bool = True

    @field_validator("configuracion_dias", mode="before")
    @classmethod
    def parse_dias_json(cls, v):
        if isinstance(v, str) and v.strip():
            try:
                return json.loads(v)
            except Exception:
                return None
        return v


class HorarioOperacionCreate(HorarioOperacionBase):
    pass


class HorarioOperacionUpdate(BaseModel):
    espacio_id: Optional[int] = None
    anio: Optional[int] = None
    descripcion: Optional[str] = None
    tipo_horario: Optional[str] = None
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None
    hora_apertura: Optional[str] = None
    hora_cierre: Optional[str] = None
    cierre_dia_siguiente: Optional[bool] = None
    es_continuo_24h: Optional[bool] = None
    configuracion_dias: Optional[dict] = None
    subespacio: Optional[str] = None
    activo: Optional[bool] = None

    @field_validator("configuracion_dias", mode="before")
    @classmethod
    def parse_dias_json(cls, v):
        if isinstance(v, str) and v.strip():
            try:
                return json.loads(v)
            except Exception:
                return None
        return v


from pydantic import Field


class HorarioOperacionResponse(HorarioOperacionBase):
    id: int
    updated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class EspacioResponse(BaseModel):
    id: int
    campus: str
    tipo: str
    nombre: str
    capacidad_max: int
    activo: bool
    model_config = ConfigDict(from_attributes=True)


class EspacioCapacidadUpdate(BaseModel):
    capacidad_max: int = Field(gt=0, description="Capacidad máxima de aforo para el recinto (debe ser mayor a 0)")


from datetime import date


class ContingenciaCrear(BaseModel):
    fecha_inicio: date
    fecha_fin: date
    tipo: str = Field(..., description="paro_federado | paro_carrera | suspension_sala | toma_campus | climatica | duelo | otro")
    titulo: str
    descripcion: Optional[str] = None
    carreras_afectadas: Optional[str] = "Todas"
    implica_cierre_total: bool = False
    espacio_id: Optional[int] = None
    subespacio: Optional[str] = "todos"
    hora_inicio: Optional[str] = None
    hora_fin: Optional[str] = None


class ContingenciaRespuesta(ContingenciaCrear):
    id: int
    creado_en: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class EventoCalendarioActualizar(BaseModel):
    descripcion: str
    is_holiday: bool = False
    is_break: bool = False
    is_exam_period: bool = False
    is_class_milestone: bool = False
    suspension_actividades: bool = False
    is_strike_federado: bool = False
    is_strike_carrera: bool = False
    tipo_contingencia: Optional[str] = None


class EventoCalendarioCrear(EventoCalendarioActualizar):
    fecha_inicio: date
    fecha_fin: Optional[date] = None





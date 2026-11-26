from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, model_validator


class ConfiguracionEspaciosResponse(BaseModel):
    id: int
    espacio_id: int
    ia_asistente_activo: bool
    active_provider: Optional[str] = "gemini"
    default_model: Optional[str] = "gemini-3.1-flash-lite"
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
from pydantic import BaseModel, ConfigDict, model_validator, field_validator


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
    tipo: str = Field(
        ...,
        description=(
            "paro_federado | paro_carrera | suspension_sala | toma_campus | "
            "climatica | duelo | falla_sensor | apertura_manual | mantencion_cierre | sin_demanda | otro"
        ),
    )
    titulo: str
    descripcion: Optional[str] = None
    carreras_afectadas: Optional[str] = "Todas"
    implica_cierre_total: bool = False
    espacio_id: Optional[int] = None
    subespacio: Optional[str] = "todos"
    hora_inicio: Optional[str] = None
    hora_fin: Optional[str] = None

    @model_validator(mode="after")
    def validar_rango_fechas(self):
        if self.fecha_inicio and self.fecha_fin and self.fecha_inicio > self.fecha_fin:
            raise ValueError("fecha_inicio no puede ser posterior a fecha_fin")
        return self


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

    @model_validator(mode="after")
    def validar_rango_fechas(self):
        if self.fecha_inicio and self.fecha_fin and self.fecha_inicio > self.fecha_fin:
            raise ValueError("fecha_inicio no puede ser posterior a fecha_fin")
        return self


# ---------------------------------------------------------------------------
# Esquemas Multi-Proveedor IA y Servidor SMTP (Admin_Sistema)
# ---------------------------------------------------------------------------
from pydantic import EmailStr


class ProveedorCatalogoItem(BaseModel):
    id: str
    nombre: str
    protocolo: str
    default_base_url: str = ""
    requires_api_key: bool = True
    requires_base_url: bool = False
    allows_local_http: bool = False
    modelos_sugeridos: list[str] = []


class CatalogoProveedoresIAResponse(BaseModel):
    proveedores: list[ProveedorCatalogoItem]


class CredencialIACreate(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=100)
    provider_id: str = Field(..., min_length=2, max_length=50)
    modelo: str = Field(..., min_length=1, max_length=120)
    base_url: Optional[str] = Field(None, max_length=300)
    api_key: Optional[str] = Field(None, max_length=500)
    activar: bool = False


class CredencialIAUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=100)
    provider_id: Optional[str] = Field(None, min_length=2, max_length=50)
    modelo: Optional[str] = Field(None, min_length=1, max_length=120)
    base_url: Optional[str] = Field(None, max_length=300)
    api_key: Optional[str] = Field(None, max_length=500)


class CredencialIAResponse(BaseModel):
    id: int
    nombre: str
    provider_id: str
    modelo: str
    base_url: Optional[str] = None
    has_api_key: bool
    key_hint: str = ""
    es_activa: bool
    ultimo_test_ok: Optional[bool] = None
    ultimo_test_en: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class CredencialesIAListResponse(BaseModel):
    items: list[CredencialIAResponse]
    ia_asistente_activo: bool
    fallback_env_disponible: bool
    origen_activo: str
    proveedor_activo_resumen: Optional[str] = None


class TestConexionIAResponse(BaseModel):
    ok: bool
    latencia_ms: float
    mensaje: str
    provider_id: str
    modelo: str


class ConfiguracionSMTPCreate(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=100)
    host: str = Field(..., min_length=2, max_length=200)
    port: int = Field(587, ge=1, le=65535)
    use_tls: bool = True
    use_ssl: bool = False
    username: str = Field(..., min_length=1, max_length=200)
    from_email: EmailStr
    from_name: str = Field("Sistema DSS Campus San Francisco UCT", min_length=1, max_length=150)
    password: str = Field(..., min_length=1, max_length=500)
    activar: bool = False


class ConfiguracionSMTPUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=100)
    host: Optional[str] = Field(None, min_length=2, max_length=200)
    port: Optional[int] = Field(None, ge=1, le=65535)
    use_tls: Optional[bool] = None
    use_ssl: Optional[bool] = None
    username: Optional[str] = Field(None, min_length=1, max_length=200)
    from_email: Optional[EmailStr] = None
    from_name: Optional[str] = Field(None, min_length=1, max_length=150)
    password: Optional[str] = Field(None, max_length=500)


class ConfiguracionSMTPResponse(BaseModel):
    id: int
    nombre: str
    host: str
    port: int
    use_tls: bool
    use_ssl: bool
    username: str
    from_email: str
    from_name: str
    has_password: bool
    password_hint: str = ""
    es_activa: bool
    ultimo_test_ok: Optional[bool] = None
    ultimo_test_en: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class ConfiguracionSMTPListResponse(BaseModel):
    items: list[ConfiguracionSMTPResponse]
    fallback_env_disponible: bool
    fallback_env_host: Optional[str] = None
    fallback_env_user: Optional[str] = None
    origen_activo: str


class SMTPTestRequest(BaseModel):
    destinatario: Optional[EmailStr] = None


class TestConexionSMTPResponse(BaseModel):
    ok: bool
    mensaje: str
    destinatario: str





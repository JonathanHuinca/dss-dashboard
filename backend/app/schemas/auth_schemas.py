from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RolBase(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    rate_limit_quota: Optional[str] = "10/day"
    cooldown_segundos: Optional[int] = 10


class RolCreate(RolBase):
    pass


class RolResponse(RolBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class RolQuotaUpdate(BaseModel):
    rate_limit_quota: str
    cooldown_segundos: int = Field(ge=0, le=3600, default=10)


class UsuarioBase(BaseModel):
    email: EmailStr
    nombre_completo: str
    is_active: bool = True
    allowed_datasets: List[str] = Field(default_factory=lambda: ["biblioteca", "estacionamiento"])
    can_use_ai: bool = False
    can_export: bool = False
    can_ingest: bool = False
    espacio_id: Optional[int] = None
    created_by_user_id: Optional[int] = None


class UsuarioCreate(UsuarioBase):
    password: str = Field(min_length=6, max_length=72)
    roles: List[str] = Field(default_factory=lambda: ["Guardia_Seguridad"])


class UsuarioResponse(UsuarioBase):
    id: int
    created_at: datetime
    intentos_fallidos_login: int = 0
    bloqueado_hasta: Optional[datetime] = None
    roles: List[RolResponse] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)


class UserStatusUpdate(BaseModel):
    is_active: Optional[bool] = None
    can_use_ai: Optional[bool] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    rol: str
    roles: List[str]
    allowed_datasets: List[str] = Field(default_factory=lambda: ["biblioteca", "estacionamiento"])
    can_use_ai: bool = False
    can_export: bool = False
    can_ingest: bool = False
    espacio_id: Optional[int] = None


class TokenPayload(BaseModel):
    user_id: int
    rol: str
    roles: List[str] = Field(default_factory=list)
    allowed_datasets: List[str] = Field(default_factory=lambda: ["biblioteca", "estacionamiento"])
    can_use_ai: bool = False
    can_export: bool = False
    can_ingest: bool = False
    espacio_id: Optional[int] = None
    sub: Optional[str] = None
    exp: Optional[int] = None


class UsuarioInviteRequest(BaseModel):
    email: EmailStr
    nombre_completo: str
    roles: List[str] = Field(default_factory=lambda: ["Analista_Consulta"])
    allowed_datasets: List[str] = Field(default_factory=lambda: ["biblioteca", "estacionamiento"])
    can_use_ai: bool = False
    can_export: bool = False
    can_ingest: bool = False
    espacio_id: Optional[int] = None


class UsuarioInviteResponse(BaseModel):
    usuario: UsuarioResponse
    enlace_activacion: str
    token_temporal: Optional[str] = None
    expira_en: datetime
    mensaje: str = "Enlace de activación / restablecimiento generado correctamente."


class TokenVerifyResponse(BaseModel):
    es_valido: bool
    email: str
    nombre_completo: str
    expira_en: datetime
    tipo_token: str


class ActivarCuentaRequest(BaseModel):
    token: str = Field(min_length=10)
    nueva_password: str = Field(min_length=8, max_length=72)
    confirmar_password: str = Field(min_length=8, max_length=72)


class ActivarCuentaResponse(BaseModel):
    mensaje: str
    email: str
    exito: bool = True


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    mensaje: str
    enlace_recuperacion: Optional[str] = None
    token_temporal: Optional[str] = None
    expira_en: Optional[datetime] = None


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10)
    nueva_password: str = Field(min_length=8, max_length=72)
    confirmar_password: str = Field(min_length=8, max_length=72)


class ResetPasswordResponse(BaseModel):
    mensaje: str
    email: str
    exito: bool = True


class UnlockUserResponse(BaseModel):
    mensaje: str
    user_id: int
    desbloqueado: bool = True


class EliminarUsuarioResponse(BaseModel):
    mensaje: str
    usuario_id: int
    exito: bool = True





from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RolBase(BaseModel):
    nombre: str
    descripcion: Optional[str] = None


class RolCreate(RolBase):
    pass


class RolResponse(RolBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class UsuarioBase(BaseModel):
    email: EmailStr
    nombre_completo: str
    is_active: bool = True
    allowed_datasets: List[str] = Field(default_factory=lambda: ["biblioteca", "estacionamiento"])


class UsuarioCreate(UsuarioBase):
    password: str = Field(min_length=6, max_length=72)
    roles: List[str] = Field(default_factory=lambda: ["Guardia_Seguridad"])


class UsuarioResponse(UsuarioBase):
    id: int
    created_at: datetime
    roles: List[RolResponse] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)


class UserStatusUpdate(BaseModel):
    is_active: bool


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


class TokenPayload(BaseModel):
    user_id: int
    rol: str
    roles: List[str] = Field(default_factory=list)
    allowed_datasets: List[str] = Field(default_factory=lambda: ["biblioteca", "estacionamiento"])
    sub: Optional[str] = None
    exp: Optional[int] = None

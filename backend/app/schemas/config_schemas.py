from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ConfiguracionGlobalResponse(BaseModel):
    id: int
    ia_asistente_activo: bool
    active_provider: Optional[str] = "gemini"
    default_model: Optional[str] = "gemini-2.5-flash"
    has_api_key: bool = False
    masked_api_key: Optional[str] = None
    updated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class ConfiguracionGlobalUpdate(BaseModel):
    ia_asistente_activo: bool


class LLMProviderUpdate(BaseModel):
    provider: str
    default_model: str
    api_key: str


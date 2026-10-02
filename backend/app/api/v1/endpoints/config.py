from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import get_current_user
from app.core.database import get_db
from app.core.security_cipher import decrypt_api_key, mask_api_key
from app.domain.auth_models import Usuario
from app.schemas.config_schemas import (
    ConfiguracionGlobalResponse,
    ConfiguracionGlobalUpdate,
    LLMProviderUpdate,
)
from app.services.config_service import (
    get_configuracion_global,
    toggle_ia_asistente,
    update_llm_provider,
)

router = APIRouter()


async def require_superadmin(
    current_user: Usuario = Depends(get_current_user),
) -> Usuario:
    user_roles = [r.nombre for r in current_user.roles]
    if "SuperAdmin" not in user_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permisos insuficientes: se requiere rol SuperAdmin",
        )
    return current_user


async def check_ia_active(
    db: AsyncSession = Depends(get_db),
) -> bool:
    config = await get_configuracion_global(db)
    if not config.ia_asistente_activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El asistente de IA se encuentra desactivado temporalmente",
        )
    return True


@router.get("", response_model=ConfiguracionGlobalResponse, summary="Obtener configuración global")
async def get_config(
    db: AsyncSession = Depends(get_db),
) -> ConfiguracionGlobalResponse:
    config = await get_configuracion_global(db)
    has_key = bool(config.encrypted_api_key and config.encrypted_api_key.strip())
    masked = None
    if has_key:
        try:
            plain = decrypt_api_key(config.encrypted_api_key)
            masked = mask_api_key(plain)
        except Exception:
            masked = "••••••••"

    return ConfiguracionGlobalResponse(
        id=config.id,
        ia_asistente_activo=config.ia_asistente_activo,
        active_provider=config.active_provider,
        default_model=config.default_model,
        has_api_key=has_key,
        masked_api_key=masked,
        updated_at=config.updated_at,
    )


@router.put("/toggle-ia", response_model=ConfiguracionGlobalResponse, summary="Alternar estado del asistente de IA")
async def toggle_ia(
    _: Usuario = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> ConfiguracionGlobalResponse:
    config = await toggle_ia_asistente(db)
    has_key = bool(config.encrypted_api_key and config.encrypted_api_key.strip())
    masked = None
    if has_key:
        try:
            plain = decrypt_api_key(config.encrypted_api_key)
            masked = mask_api_key(plain)
        except Exception:
            masked = "••••••••"

    return ConfiguracionGlobalResponse(
        id=config.id,
        ia_asistente_activo=config.ia_asistente_activo,
        active_provider=config.active_provider,
        default_model=config.default_model,
        has_api_key=has_key,
        masked_api_key=masked,
        updated_at=config.updated_at,
    )


@router.put("/llm-provider", response_model=ConfiguracionGlobalResponse, summary="Configurar proveedor y API Key del LLM")
async def set_llm_provider(
    req: LLMProviderUpdate,
    _: Usuario = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> ConfiguracionGlobalResponse:
    if not req.api_key or not req.api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La API Key no puede estar vacía",
        )
    config = await update_llm_provider(
        db=db,
        provider=req.provider,
        default_model=req.default_model,
        api_key=req.api_key,
    )
    plain = req.api_key.strip()
    return ConfiguracionGlobalResponse(
        id=config.id,
        ia_asistente_activo=config.ia_asistente_activo,
        active_provider=config.active_provider,
        default_model=config.default_model,
        has_api_key=True,
        masked_api_key=mask_api_key(plain),
        updated_at=config.updated_at,
    )


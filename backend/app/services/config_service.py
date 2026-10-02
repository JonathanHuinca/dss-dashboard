from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.config_models import ConfiguracionGlobal


async def get_configuracion_global(db: AsyncSession) -> ConfiguracionGlobal:
    stmt = select(ConfiguracionGlobal).where(ConfiguracionGlobal.id == 1)
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()
    if not config:
        config = ConfiguracionGlobal(id=1, ia_asistente_activo=True)
        db.add(config)
        await db.commit()
        await db.refresh(config)
    return config

async def toggle_ia_asistente(db: AsyncSession) -> ConfiguracionGlobal:
    config = await get_configuracion_global(db)
    config.ia_asistente_activo = not config.ia_asistente_activo
    await db.commit()
    await db.refresh(config)
    return config


from app.core.security_cipher import encrypt_api_key



async def update_llm_provider(
    db: AsyncSession,
    provider: str,
    default_model: str,
    api_key: str,
) -> ConfiguracionGlobal:
    config = await get_configuracion_global(db)
    config.active_provider = provider.strip().lower()
    config.default_model = default_model.strip()
    if api_key and api_key.strip():
        config.encrypted_api_key = encrypt_api_key(api_key.strip())
    await db.commit()
    await db.refresh(config)
    return config


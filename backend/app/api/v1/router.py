from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.api.v1.endpoints import (
    auth,
    attendance,
    vehicles,
    predictions,
    ingestion,
    assistant,
    chat,
    config,
    metrics,
    admin,
    export,
    reportes_compartidos,
)

api_router = APIRouter()

# Autenticación institucional: rutas públicas (/login, /activate, /reset-password) y de cuenta
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(config.public_router, prefix="/config", tags=["config"])

# Módulos protegidos con validación obligatoria de token JWT
api_router.include_router(
    admin.router,
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(get_current_user)],
)
api_router.include_router(
    config.router,
    prefix="/config",
    tags=["config"],
    dependencies=[Depends(get_current_user)],
)
api_router.include_router(
    metrics.router,
    prefix="/metrics",
    tags=["metrics"],
    dependencies=[Depends(get_current_user)],
)
api_router.include_router(
    attendance.router,
    prefix="/attendance",
    tags=["attendance"],
    dependencies=[Depends(get_current_user)],
)
api_router.include_router(
    vehicles.router,
    prefix="/vehicles",
    tags=["vehicles"],
    dependencies=[Depends(get_current_user)],
)
api_router.include_router(
    predictions.router,
    prefix="/predictions",
    tags=["predictions"],
    dependencies=[Depends(get_current_user)],
)
api_router.include_router(
    ingestion.router,
    prefix="/ingestion",
    tags=["ingestion"],
    dependencies=[Depends(get_current_user)],
)
api_router.include_router(
    assistant.router,
    prefix="/assistant",
    tags=["assistant"],
    dependencies=[Depends(get_current_user)],
)
api_router.include_router(
    chat.router,
    prefix="/chat",
    tags=["chat"],
    dependencies=[Depends(get_current_user)],
)
api_router.include_router(
    export.router,
    prefix="/export",
    tags=["export"],
    dependencies=[Depends(get_current_user)],
)
api_router.include_router(
    reportes_compartidos.router,
    prefix="/reportes-compartidos",
    tags=["reportes-compartidos"],
)


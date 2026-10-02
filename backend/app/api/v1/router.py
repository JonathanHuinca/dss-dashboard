from fastapi import APIRouter

from app.api.v1.endpoints import auth, attendance, vehicles, predictions, ingestion, assistant, chat, config, metrics, admin

api_router = APIRouter()

api_router.include_router(auth.router,        prefix="/auth",       tags=["auth"])
api_router.include_router(auth.router,        prefix="",            tags=["users"])
api_router.include_router(admin.router,       prefix="/admin",      tags=["admin"])
api_router.include_router(config.router,      prefix="/config",     tags=["config"])
api_router.include_router(metrics.router,     prefix="/metrics",    tags=["metrics"])
api_router.include_router(attendance.router,  prefix="/attendance", tags=["attendance"])
api_router.include_router(vehicles.router,    prefix="/vehicles",   tags=["vehicles"])
api_router.include_router(predictions.router, prefix="/predictions",tags=["predictions"])
api_router.include_router(ingestion.router,   prefix="/ingestion",  tags=["ingestion"])
api_router.include_router(assistant.router,   prefix="/assistant",  tags=["assistant"])
api_router.include_router(chat.router,        prefix="/chat",       tags=["chat"])


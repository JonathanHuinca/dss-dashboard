from contextlib import asynccontextmanager
import logging
from pathlib import Path
import uuid
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import ip_whitelist_middleware, get_current_user
from app.core.startup_seed import run_startup_seed
from app.api.v1.router import api_router
from app.api.v1.endpoints.chat import router as chat_router
from slowapi.errors import RateLimitExceeded
from app.core.limiter import limiter, rate_limit_exceeded_handler

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.GEMINI_API_KEY or not settings.GEMINI_API_KEY.strip():
        logger.critical("Error crítico: GEMINI_API_KEY no está configurada o se encuentra vacía en las variables de entorno.")
        raise RuntimeError("Error crítico de configuración: GEMINI_API_KEY no está configurada o se encuentra vacía en las variables de entorno.")

    # Aprovisionamiento idempotente de uct_dashboard y login uct_app
    try:
        from scripts.inicializar_base_datos import inicializar_base_y_permisos
        inicializar_base_y_permisos()
    except Exception as exc_init:
        logger.warning(f"[startup] Inicialización de base de datos omitida o previa: {exc_init}")

    await run_startup_seed()

    # Limpieza de trabajos de ingesta huérfanos tras reinicio del servidor API
    try:
        from app.services.ingestion_service import limpiar_trabajos_ingesta_huerfanos
        await limpiar_trabajos_ingesta_huerfanos()
    except Exception as exc_ing:
        logger.warning(f"[startup] Limpieza de trabajos de ingesta huérfanos con error: {exc_ing}")

    if settings.PLANIFICADOR_ACTIVO:
        from app.core.planificador import iniciar_planificador, detener_planificador
        await iniciar_planificador()

    try:
        import asyncio
        from app.core.cache import precalentar_cache_modulos
        asyncio.create_task(precalentar_cache_modulos())
    except Exception as exc_cache:
        logger.warning(f"[startup] No se pudo iniciar precalentamiento de caché: {exc_cache}")

    try:
        yield
    finally:
        if settings.PLANIFICADOR_ACTIVO:
            from app.core.planificador import detener_planificador
            await detener_planificador()


es_produccion = settings.is_production

app = FastAPI(
    title="Dashboard UCT — API",
    description=(
        "API analítica y predictiva de afluencia de personas y vehículos — "
        "UCT Campus San Francisco"
    ),
    version="0.1.0",
    docs_url=None if es_produccion else "/docs",
    redoc_url=None if es_produccion else "/redoc",
    openapi_url=None if es_produccion else "/openapi.json",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return await http_exception_handler(request, exc)
    if isinstance(exc, RequestValidationError):
        return await request_validation_exception_handler(request, exc)

    id_correlacion = str(uuid.uuid4())
    logger.error(f"Error interno no controlado [{id_correlacion}] en ruta {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Error interno del servidor", "correlation_id": id_correlacion},
    )


app.middleware("http")(ip_whitelist_middleware)

# ---------------------------------------------------------------------------
# CORS — Restricción explícita de métodos y cabeceras utilizadas
# ---------------------------------------------------------------------------
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
if settings.is_production:
    CORS_ORIGINS = ["https://dashboard.uct.cl", settings.FRONTEND_URL]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/chat", tags=["chat"], dependencies=[Depends(get_current_user)])


@app.get("/health", tags=["infra"])
async def health_check():
    return {"status": "ok", "environment": settings.ENVIRONMENT, "version": "0.1.0"}


@app.get("/ready", tags=["infra"], summary="Verificación integral de dependencias (Base de datos y Modelos ML)")
async def readiness_check():
    estado_db = False
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
            estado_db = True
    except Exception as e:
        logger.warning(f"[ready] Fallo en verificación de base de datos: {e}")

    # Verificar disponibilidad de modelos predictivos en el directorio correspondiente
    directorio_modelos = Path("/app/models")
    if not directorio_modelos.exists():
        directorio_modelos = Path(__file__).resolve().parent.parent / "models"

    modelos_esperados = [
        "prophet_biblioteca_active.joblib",
        "prophet_vehicular_active.joblib",
    ]
    modelos_disponibles = {m: (directorio_modelos / m).exists() for m in modelos_esperados}
    al_menos_un_modelo = any(modelos_disponibles.values())

    if estado_db and al_menos_un_modelo:
        return {
            "status": "ready",
            "database": "connected",
            "models": modelos_disponibles,
            "environment": settings.ENVIRONMENT,
        }

    return JSONResponse(
        status_code=503,
        content={
            "status": "not_ready",
            "database": "connected" if estado_db else "disconnected",
            "models": modelos_disponibles,
            "environment": settings.ENVIRONMENT,
        },
    )

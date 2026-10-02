from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.security import ip_whitelist_middleware
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
    yield

app = FastAPI(
    title="Dashboard UCT — API",
    description=(
        "API analítica y predictiva de afluencia de personas y vehículos — "
        "UCT Campus San Francisco"
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

app.middleware("http")(ip_whitelist_middleware)

# ---------------------------------------------------------------------------
# CORS — permisivo para desarrollo (Prompt 1.5)
# En producción reemplazar allow_origins con el dominio institucional UCT.
# ---------------------------------------------------------------------------
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:3000",
]
if settings.ENVIRONMENT == "production":
    CORS_ORIGINS = ["https://dashboard.uct.cl"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/chat", tags=["chat"])


@app.get("/health", tags=["infra"])
async def health_check():
    return {"status": "ok", "environment": settings.ENVIRONMENT, "version": "0.1.0"}

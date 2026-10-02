import redis
from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings
from app.services.auth_service import decode_access_token

_redis_sync_client = None


def get_redis_sync_client():
    global _redis_sync_client
    if _redis_sync_client is None:
        try:
            _redis_sync_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        except Exception:
            _redis_sync_client = None
    return _redis_sync_client


def get_user_rate_limit_key(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        try:
            payload = decode_access_token(token)
            user_id = payload.get("user_id") or payload.get("sub")
            role = payload.get("rol", "otro")
            if user_id:
                return f"user:{user_id}:{role}"
        except Exception:
            pass
    return f"ip:{get_remote_address(request)}:otro"


def get_rate_limit_by_role(key: str = "") -> str:
    role = key.split(":")[-1] if ":" in key else key
    r = get_redis_sync_client()
    if r:
        try:
            cached_quota = r.get(f"role_rate_limit:{role}")
            if cached_quota:
                quota_str = str(cached_quota).strip()
                if quota_str.lower() in ("ilimitado", "unlimited", "none", "-1"):
                    return "100000/day"
                return quota_str
        except Exception:
            pass

    default_quotas = {
        "SuperAdmin": "100000/day",
        "Directivo": "25/day",
        "Guardia_Seguridad": "5/day",
    }
    return default_quotas.get(role, "30/day")


limiter = Limiter(
    key_func=get_user_rate_limit_key,
    storage_uri=settings.REDIS_URL,
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "error": "Too Many Requests",
            "detail": f"Cuota de solicitudes excedida: {exc.detail}",
            "limit": str(exc.detail),
        },
    )


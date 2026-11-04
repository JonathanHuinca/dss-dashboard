from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.services.auth_service import decode_access_token


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
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        client_ip = get_remote_address(request)
    return f"ip:{client_ip}:otro"


def get_rate_limit_by_role(key: str = "") -> str:
    role = key.split(":")[-1] if ":" in key else key
    default_quotas = {
        "SuperAdmin": "100000/day",
        "Directivo": "25/day",
        "Guardia_Seguridad": "5/day",
    }
    return default_quotas.get(role, "30/day")


limiter = Limiter(
    key_func=get_user_rate_limit_key,
    storage_uri="memory://",
)


def rate_limit_exceeded_handler(_request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "error": "Too Many Requests",
            "detail": f"Cuota de solicitudes excedida: {exc.detail}",
            "limit": str(exc.detail),
        },
    )


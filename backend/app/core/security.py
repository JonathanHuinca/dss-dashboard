import hmac
import hashlib
from datetime import datetime, timedelta, timezone
from ipaddress import IPv4Address, IPv4Network
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings
from app.services.auth_service import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)
from app.api.v1.endpoints.auth import get_current_user, require_role

ALLOWED_SUBNETS = [IPv4Network(s) for s in settings.allowed_subnets_list]


async def ip_whitelist_middleware(request: Request, call_next):
    if settings.ENABLE_IP_WHITELIST:
        raw_ip = request.client.host
        try:
            client_ip = IPv4Address(raw_ip)
        except ValueError:
            return _forbidden_response()
        if not any(client_ip in net for net in ALLOWED_SUBNETS):
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Acceso restringido a red institucional UCT", "code": "IP_NOT_ALLOWED"},
            )
    return await call_next(request)

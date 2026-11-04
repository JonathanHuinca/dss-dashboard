import asyncio
import time
from typing import Optional, List, Callable, Any
import httpx
from app.adapters.base import (
    AttendanceEventDTO,
    CalendarEventDTO,
    IngestionAdapter,
    VehicleEventDTO,
)
from app.core.config import settings


class CircuitBreakerOpenException(Exception):
    pass


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = "CLOSED"

    def can_execute(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if time.time() - (self.last_failure_time or 0) > self.recovery_timeout:
                self.state = "HALF_OPEN"
                return True
            return False
        return True

    def record_success(self):
        self.failure_count = 0
        self.state = "CLOSED"

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"

    async def execute(self, func: Callable, *args, **kwargs) -> Any:
        if not self.can_execute():
            raise CircuitBreakerOpenException("Circuit breaker is OPEN. Fast-failing request.")
        try:
            res = await func(*args, **kwargs)
            self.record_success()
            return res
        except Exception as e:
            self.record_failure()
            raise e


import json
import os
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security_cipher import decrypt_api_key
from app.domain.config_models import ConfiguracionEspacios


class HikCentralOpenAPIAdapter(IngestionAdapter):
    def __init__(
        self,
        base_url: Optional[str] = None,
        app_key: Optional[str] = None,
        app_secret: Optional[str] = None,
        ca_bundle: Optional[str] = None,
    ):
        self.base_url = base_url or getattr(settings, "HIKCENTRAL_BASE_URL", "https://hikcentral.uct.cl")
        self.app_key = app_key or getattr(settings, "HIKCENTRAL_APP_KEY", "")
        self.app_secret = app_secret or getattr(settings, "HIKCENTRAL_APP_SECRET", "")
        self.ca_bundle = ca_bundle or getattr(settings, "HIKCENTRAL_CA_BUNDLE", None)
        self.circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)

        # Mapa institucional de espacio_id a identificador de región o parqueadero HikCentral
        self.espacios_map = {}
        raw_espacios = getattr(settings, "HIKCENTRAL_ESPACIOS", "")
        if raw_espacios:
            try:
                self.espacios_map = json.loads(raw_espacios)
            except Exception:
                self.espacios_map = {"1": "REGION_BIBLIOTECA", "2": "REGION_ESTACIONAMIENTO"}

    def resolver_identificador_region(self, espacio_id: int) -> str:
        """Obtiene el identificador de región HikCentral configurado para el espacio institucional."""
        return self.espacios_map.get(str(espacio_id), str(espacio_id))

    @classmethod
    async def crear_desde_bd_o_entorno(
        cls,
        db: AsyncSession,
        espacio_id: int,
    ) -> "HikCentralOpenAPIAdapter":
        """
        Instancia el adaptador recuperando credenciales de configuracion_espacios cifradas con Fernet,
        o recurriendo a las variables de entorno institucional como fallback.
        """
        app_key = getattr(settings, "HIKCENTRAL_APP_KEY", "")
        app_secret = getattr(settings, "HIKCENTRAL_APP_SECRET", "")
        base_url = getattr(settings, "HIKCENTRAL_BASE_URL", "https://hikcentral.uct.cl")
        ca_bundle = getattr(settings, "HIKCENTRAL_CA_BUNDLE", None)

        try:
            stmt = select(ConfiguracionEspacios).where(ConfiguracionEspacios.espacio_id == espacio_id)
            resultado = await db.execute(stmt)
            config_espacio = resultado.scalar_one_or_none()

            if config_espacio and config_espacio.encrypted_api_key:
                credencial_descifrada = decrypt_api_key(config_espacio.encrypted_api_key)
                if ":" in credencial_descifrada:
                    app_key, app_secret = credencial_descifrada.split(":", 1)
                else:
                    app_key = credencial_descifrada
        except Exception:
            pass

        return cls(
            base_url=base_url,
            app_key=app_key,
            app_secret=app_secret,
            ca_bundle=ca_bundle,
        )

    async def _request_with_retry(
        self,
        endpoint: str,
        method: str = "POST",
        payload: Optional[dict] = None,
        max_retries: int = 3,
        backoff_factor: float = 1.5,
    ) -> dict:
        url = f"{self.base_url.rstrip('/')}{endpoint}"
        headers = {
            "Content-Type": "application/json",
            "X-Ca-Key": self.app_key,
        }

        # Verificación de certificados SSL/TLS
        verify_ssl: bool | str = False
        if self.ca_bundle and os.path.exists(self.ca_bundle):
            verify_ssl = self.ca_bundle
        elif settings.is_production:
            verify_ssl = True

        async def _do_req():
            async with httpx.AsyncClient(timeout=10.0, verify=verify_ssl) as client:
                if method.upper() == "POST":
                    resp = await client.post(url, json=payload or {}, headers=headers)
                else:
                    resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                return resp.json()

        last_err = None
        for attempt in range(max_retries):
            try:
                return await self.circuit_breaker.execute(_do_req)
            except Exception as exc:
                last_err = exc
                if isinstance(exc, CircuitBreakerOpenException):
                    raise exc
                if attempt < max_retries - 1:
                    await asyncio.sleep(backoff_factor * (2 ** attempt))
        raise last_err

    async def fetch_attendance_events(self, espacio_id: int) -> List[AttendanceEventDTO]:
        region_code = self.resolver_identificador_region(espacio_id)
        try:
            await self._request_with_retry(
                "/artemis/api/acs/v1/door/events",
                payload={"pageNo": 1, "pageSize": 100, "regionIndexCode": region_code},
            )
            return []
        except Exception:
            return []

    async def fetch_vehicle_events(self, espacio_id: int) -> List[VehicleEventDTO]:
        region_code = self.resolver_identificador_region(espacio_id)
        try:
            await self._request_with_retry(
                "/artemis/api/pms/v1/crossRecords/page",
                payload={"pageNo": 1, "pageSize": 100, "parkSyscode": region_code},
            )
            return []
        except Exception:
            return []

    async def fetch_calendar_events(self) -> List[CalendarEventDTO]:
        return []

"""Gestor compartido de cliente HTTP asíncrono y registro fuerte de tareas en segundo plano."""
import asyncio
import logging
from typing import Any, Coroutine, Optional, Set

import httpx

logger = logging.getLogger(__name__)

_http_client: Optional[httpx.AsyncClient] = None
_tareas_fondo: Set[asyncio.Task[Any]] = set()


async def iniciar_http_client() -> httpx.AsyncClient:
    """Inicializa el cliente httpx compartido para todo el ciclo de vida del servidor."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
    return _http_client


def obtener_http_client() -> Optional[httpx.AsyncClient]:
    """Retorna el cliente compartido si está inicializado y abierto."""
    if _http_client is not None and not _http_client.is_closed:
        return _http_client
    return None


async def cerrar_http_client() -> None:
    """Cierra ordenadamente el cliente HTTP compartido al apagar la aplicación."""
    global _http_client
    if _http_client is not None:
        if not _http_client.is_closed:
            await _http_client.aclose()
        _http_client = None


def crear_tarea_fondo(coro: Coroutine[Any, Any, Any], nombre: Optional[str] = None) -> asyncio.Task[Any]:
    """Crea una tarea asíncrona manteniendo referencia fuerte y registrando fallos no capturados."""
    task = asyncio.create_task(coro, name=nombre)
    _tareas_fondo.add(task)

    def _al_finalizar(t: asyncio.Task[Any]) -> None:
        _tareas_fondo.discard(t)
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            logger.error("Error en tarea de fondo '%s': %s", t.get_name(), exc, exc_info=exc)

    task.add_done_callback(_al_finalizar)
    return task


async def cancelar_tareas_fondo(timeout: float = 5.0) -> None:
    """Cancela y espera la finalización limpia de todas las tareas activas en segundo plano."""
    pendientes = [t for t in _tareas_fondo if not t.done()]
    if not pendientes:
        _tareas_fondo.clear()
        return
    for t in pendientes:
        t.cancel()
    try:
        await asyncio.wait_for(asyncio.gather(*pendientes, return_exceptions=True), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("Tiempo agotado cancelando %d tareas en segundo plano.", len(pendientes))
    finally:
        _tareas_fondo.clear()

"""
gestor_modelos.py — Gestor de modelos ML con recarga en caliente en memoria
y ejecución asíncrona no bloqueante (asyncio.to_thread).
"""
import asyncio
import logging
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Optional, Tuple

import joblib

logger = logging.getLogger("app.ml.gestor_modelos")

MAX_MODELOS_MEMORIA = 16
# Cache LRU en memoria protegida por lock: {ruta_absoluta: ((mtime_ns, size), objeto_modelo)}
_cache_modelos_memoria: "OrderedDict[str, Tuple[Tuple[int, int], Any]]" = OrderedDict()
_cache_lock = threading.Lock()


def cargar_modelo_en_memoria(ruta_modelo: Path) -> Optional[Any]:
    """
    Carga un modelo serializado en memoria con caché LRU protegida por lock
    y validación por (st_mtime_ns, st_size).
    """
    if not ruta_modelo.exists():
        return None

    ruta_str = str(ruta_modelo.resolve())
    try:
        st = ruta_modelo.stat()
        clave_version = (int(st.st_mtime_ns), int(st.st_size))
    except Exception as exc:
        logger.error(f"[gestor_modelos] Error al consultar stat de {ruta_modelo}: {exc}")
        return None

    with _cache_lock:
        entrada = _cache_modelos_memoria.get(ruta_str)
        if entrada is not None and entrada[0] == clave_version:
            _cache_modelos_memoria.move_to_end(ruta_str)
            return entrada[1]

    try:
        logger.info(f"[gestor_modelos] Cargando modelo en memoria desde disco: {ruta_modelo.name}")
        modelo_cargado = joblib.load(ruta_modelo)
        with _cache_lock:
            _cache_modelos_memoria[ruta_str] = (clave_version, modelo_cargado)
            _cache_modelos_memoria.move_to_end(ruta_str)
            while len(_cache_modelos_memoria) > MAX_MODELOS_MEMORIA:
                _cache_modelos_memoria.popitem(last=False)
        return modelo_cargado
    except Exception as exc:
        logger.error(f"[gestor_modelos] Error al cargar {ruta_modelo.name}: {exc}", exc_info=True)
        with _cache_lock:
            entrada = _cache_modelos_memoria.get(ruta_str)
            if entrada is not None:
                return entrada[1]
        return None


async def cargar_modelo_en_memoria_async(ruta_modelo: Path) -> Optional[Any]:
    """Carga el modelo desde disco en un hilo trabajador sin bloquear el event loop."""
    return await asyncio.to_thread(cargar_modelo_en_memoria, ruta_modelo)


def invalidar_cache_modelo(ruta_modelo: Path) -> None:
    """Invalida explícitamente un modelo en caché."""
    ruta_str = str(ruta_modelo.resolve())
    with _cache_lock:
        _cache_modelos_memoria.pop(ruta_str, None)


async def ejecutar_inferencia_en_hilo(funcion: Callable, *args, **kwargs) -> Any:
    """
    Ejecuta cómputos pesados de inferencia mediante asyncio.to_thread
    para evitar bloquear el bucle de eventos principal de FastAPI.
    """
    return await asyncio.to_thread(funcion, *args, **kwargs)

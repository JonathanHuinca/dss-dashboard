"""
gestor_modelos.py — Gestor de modelos ML con recarga en caliente en memoria
y ejecución asíncrona no bloqueante (asyncio.to_thread).
"""
import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

import joblib

logger = logging.getLogger("app.ml.gestor_modelos")

# Cache en memoria: {str(ruta_absoluta): (timestamp_mtime, objeto_modelo)}
_cache_modelos_memoria: Dict[str, Tuple[float, Any]] = {}


def cargar_modelo_en_memoria(ruta_modelo: Path) -> Optional[Any]:
    """
    Carga un modelo serializado en memoria con recarga en caliente automática
    basada en la fecha de última modificación (st_mtime) del archivo en disco.
    """
    if not ruta_modelo.exists():
        return None

    ruta_str = str(ruta_modelo.resolve())
    try:
        mtime_actual = ruta_modelo.stat().st_mtime
    except Exception as exc:
        logger.error(f"[gestor_modelos] Error al consultar st_mtime de {ruta_modelo}: {exc}")
        return None

    # Verificar si está en caché y si no ha cambiado en disco
    if ruta_str in _cache_modelos_memoria:
        mtime_cache, modelo_cache = _cache_modelos_memoria[ruta_str]
        if mtime_actual <= mtime_cache:
            return modelo_cache

    # Cargar o recargar desde disco
    try:
        logger.info(f"[gestor_modelos] Cargando modelo en memoria desde disco: {ruta_modelo.name}")
        modelo_cargado = joblib.load(ruta_modelo)
        _cache_modelos_memoria[ruta_str] = (mtime_actual, modelo_cargado)
        return modelo_cargado
    except Exception as exc:
        logger.error(f"[gestor_modelos] Error al cargar {ruta_modelo.name}: {exc}", exc_info=True)
        # Si falló la recarga pero teníamos una versión previa válida en caché, la conservamos
        if ruta_str in _cache_modelos_memoria:
            return _cache_modelos_memoria[ruta_str][1]
        return None


def invalidar_cache_modelo(ruta_modelo: Path) -> None:
    """Invalida explícitamente un modelo en caché."""
    ruta_str = str(ruta_modelo.resolve())
    _cache_modelos_memoria.pop(ruta_str, None)


async def ejecutar_inferencia_en_hilo(funcion: Callable, *args, **kwargs) -> Any:
    """
    Ejecuta cómputos pesados de inferencia mediante asyncio.to_thread
    para evitar bloquear el bucle de eventos principal de FastAPI.
    """
    return await asyncio.to_thread(funcion, *args, **kwargs)

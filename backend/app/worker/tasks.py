"""tasks.py — Adaptador de tareas asíncronas para el DSS UCT (APScheduler)."""

import asyncio
import logging
from app.core.database import AsyncSessionLocal
from app.core.planificador import ejecutar_tarea
from app.ml.prophet_service import train_all

logger = logging.getLogger(__name__)


async def entrenar_modelo_prophet_async(_espacio_id: int = 1):
    """Ejecuta el reentrenamiento de modelos analíticos."""
    return await ejecutar_tarea("reentrenar_modelos_ml", disparador="manual")


async def actualizar_calendario_academico_scraping_async():
    """Ejecuta la sincronización del calendario académico."""
    return await ejecutar_tarea("sincronizar_calendario_academico", disparador="manual")


async def purgar_conversaciones_eliminadas_async():
    """Ejecuta la purga periódica de conversaciones eliminadas."""
    return await ejecutar_tarea("purgar_conversaciones_chat", disparador="manual")

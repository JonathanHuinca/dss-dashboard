"""
probar_cache_rendimiento.py — Validación unitaria del sistema de caché en memoria y decorador.

Verifica:
1. Interfaz agnóstica CacheEnMemoria y particiones TTLCache.
2. Inyección de cabeceras HTTP X-Cache (MISS en primera llamada, HIT en subsecuente).
3. Tiempo de respuesta sub-100ms en aciertos (HIT).
4. Invalidación selectiva por espacio institucional (invalidar_cache_por_espacio).
5. Purga total del almacén (limpiar_toda_la_cache).
"""
import asyncio
import os
import sys
import time
from pathlib import Path

directorio_raiz = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(directorio_raiz))

from fastapi import Response
from app.core.cache import (
    CacheEnMemoria,
    cachear_respuesta,
    invalidar_cache_por_espacio,
    limpiar_toda_la_cache,
    obtener_cache,
    TTL_AFORO_VIVO,
    TTL_KPIS_DIA,
    TTL_HISTORICOS,
)


contador_ejecuciones = {"espacio_1": 0, "espacio_2": 0}


@cachear_respuesta(ttl_segundos=TTL_KPIS_DIA, categoria="kpis", por_espacio=True)
async def simular_consulta_kpis(espacio_id: int, response: Response):
    if espacio_id == 1:
        contador_ejecuciones["espacio_1"] += 1
    elif espacio_id == 2:
        contador_ejecuciones["espacio_2"] += 1
    # Simular latencia de base de datos
    await asyncio.sleep(0.05)
    return {
        "espacio_id": espacio_id,
        "aforo_actual": 42 * espacio_id,
        "marca_tiempo": time.time(),
    }


async def ejecutar_pruebas():
    print("[1/5] Verificando instanciación y limpieza inicial...")
    await limpiar_toda_la_cache()
    gestor = obtener_cache()
    estadisticas_iniciales = gestor.stats()
    assert estadisticas_iniciales["total_items"] == 0, "La caché no inició vacía."
    print("      Estado inicial limpio confirmado.")

    print("[2/5] Probando primera consulta (esperado MISS)...")
    resp1 = Response()
    t0 = time.perf_counter()
    datos1 = await simular_consulta_kpis(espacio_id=1, response=resp1)
    latencia1_ms = (time.perf_counter() - t0) * 1000

    assert resp1.headers.get("X-Cache") == "MISS", f"Esperado MISS, recibido: {resp1.headers.get('X-Cache')}"
    assert resp1.headers.get("X-Cache-TTL") == str(TTL_KPIS_DIA)
    assert contador_ejecuciones["espacio_1"] == 1, "La función no se ejecutó en MISS."
    print(f"      MISS confirmado ({latencia1_ms:.2f} ms).")

    print("[3/5] Probando segunda consulta repetida (esperado HIT y latencia < 100ms)...")
    resp2 = Response()
    t0 = time.perf_counter()
    datos2 = await simular_consulta_kpis(espacio_id=1, response=resp2)
    latencia2_ms = (time.perf_counter() - t0) * 1000

    assert resp2.headers.get("X-Cache") == "HIT", f"Esperado HIT, recibido: {resp2.headers.get('X-Cache')}"
    assert contador_ejecuciones["espacio_1"] == 1, "La función fue llamada de nuevo a pesar del HIT."
    assert datos2["aforo_actual"] == datos1["aforo_actual"]
    assert datos2["marca_tiempo"] == datos1["marca_tiempo"]
    assert latencia2_ms < 100, f"Latencia de HIT superó los 100 ms: {latencia2_ms:.2f} ms"
    print(f"      HIT confirmado ({latencia2_ms:.2f} ms < 100 ms).")

    print("[4/5] Probando partición e invalidación selectiva por espacio...")
    # Llenar espacio 2
    resp_e2 = Response()
    await simular_consulta_kpis(espacio_id=2, response=resp_e2)
    assert resp_e2.headers.get("X-Cache") == "MISS"
    assert contador_ejecuciones["espacio_2"] == 1

    # Invalidad espacio 1 solamente
    invalidados = await invalidar_cache_por_espacio(espacio_id=1)
    assert invalidados >= 1, "No se invalidaron entradas para el espacio 1."

    # Consultar espacio 1 de nuevo -> debe ser MISS y ejecutar la función
    resp1_post = Response()
    await simular_consulta_kpis(espacio_id=1, response=resp1_post)
    assert resp1_post.headers.get("X-Cache") == "MISS", "Espacio 1 debió ser MISS tras invalidar."
    assert contador_ejecuciones["espacio_1"] == 2, "La función no se reejecutó tras invalidación."

    # Consultar espacio 2 -> debe seguir siendo HIT
    resp2_post = Response()
    await simular_consulta_kpis(espacio_id=2, response=resp2_post)
    assert resp2_post.headers.get("X-Cache") == "HIT", "Espacio 2 debió permanecer en HIT."
    assert contador_ejecuciones["espacio_2"] == 1, "Espacio 2 se reejecutó indebidamente."
    print("      Invalidación selectiva confirmada.")

    print("[5/5] Probando purga total administrativa...")
    total_borrados = await limpiar_toda_la_cache()
    assert total_borrados >= 2, f"Se esperaba borrar al menos 2 claves, se borraron {total_borrados}"
    stats_finales = gestor.stats()
    assert stats_finales["total_items"] == 0, "Quedaron elementos tras limpiar_toda_la_cache"
    print("      Purga total exitosa.")

    print("\nPruebas de cache finalizadas con exito.")


if __name__ == "__main__":
    asyncio.run(ejecutar_pruebas())


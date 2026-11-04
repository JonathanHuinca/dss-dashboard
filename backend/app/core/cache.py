"""
cache.py — Sistema de Caché en Memoria y Decorador de Rendimiento para DSS UCT.

Provee:
1. Interfaz agnóstica de almacenamiento en memoria con TTLCache y control de concurrencia.
2. Decorador @cachear_respuesta con cabeceras HTTP X-Cache (HIT / MISS) y TTLs adaptativos:
   - 60 s para aforo en tiempo real (en vivo).
   - 300 s para KPIs y resúmenes del día.
   - 900 s para históricos y agregaciones consolidadas.
3. Función invalidar_cache_por_espacio(espacio_id) para invalidación tras ingesta o sincronización.
4. Función limpiar_toda_la_cache() para purga administrativa total.
"""
import asyncio
import functools
import hashlib
import inspect
import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

try:
    from cachetools import TTLCache
except ImportError:
    # Respaldo en memoria puro si cachetools no se encuentra en el entorno local
    class TTLCache(dict):
        def __init__(self, maxsize: int = 1000, ttl: float = 300.0):
            super().__init__()
            self.maxsize = maxsize
            self.ttl = ttl
            self._expiraciones: Dict[str, float] = {}

        def __setitem__(self, key: str, value: Any):
            if len(self) >= self.maxsize and key not in self:
                clave_antigua = min(self._expiraciones, key=self._expiraciones.get, default=None)
                if clave_antigua:
                    del self[clave_antigua]
            self._expiraciones[key] = time.time() + self.ttl
            super().__setitem__(key, value)

        def __getitem__(self, key: str) -> Any:
            if key in self._expiraciones and time.time() > self._expiraciones[key]:
                del self[key]
                raise KeyError(key)
            return super().__getitem__(key)

        def __contains__(self, key: object) -> bool:
            if key in self._expiraciones and time.time() > self._expiraciones[key]:
                del self[key]
                return False
            return super().__contains__(key)

        def __delitem__(self, key: str):
            self._expiraciones.pop(key, None)
            if key in self:
                super().__delitem__(key)

        def clear(self):
            self._expiraciones.clear()
            super().clear()
from fastapi import Request, Response

logger = logging.getLogger("app.core.cache")

# Constantes de TTL oficiales
TTL_AFORO_VIVO: int = 60         # 1 minuto
TTL_KPIS_DIA: int = 300          # 5 minutos
TTL_HISTORICOS: int = 900        # 15 minutos


class CacheInterface(ABC):
    """Interfaz abstracta para almacén de caché en el DSS."""

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        pass

    @abstractmethod
    async def invalidate_prefix(self, prefix: str) -> int:
        pass

    @abstractmethod
    async def clear(self) -> int:
        pass


class CacheEnMemoria(CacheInterface):
    """
    Implementación en memoria volátil de alto rendimiento basada en TTLCache de cachetools.
    Incorpora bloqueos asíncronos por clave para evitar condiciones de carrera.
    """

    def __init__(self, maxsize: int = 2000, default_ttl: int = TTL_KPIS_DIA):
        # Mantiene particiones por TTL para gestión precisa de expiraciones
        self._cache_vivo: TTLCache = TTLCache(maxsize=maxsize // 4, ttl=TTL_AFORO_VIVO)
        self._cache_kpis: TTLCache = TTLCache(maxsize=maxsize // 2, ttl=TTL_KPIS_DIA)
        self._cache_historicos: TTLCache = TTLCache(maxsize=maxsize // 4, ttl=TTL_HISTORICOS)
        self._cache_general: TTLCache = TTLCache(maxsize=maxsize, ttl=default_ttl)

        self._lock = asyncio.Lock()
        self._key_tags: Dict[str, Set[str]] = {}  # key -> set of tags (ej. 'espacio:1')

    def _seleccionar_cache(self, ttl: Optional[int]) -> TTLCache:
        if ttl == TTL_AFORO_VIVO:
            return self._cache_vivo
        elif ttl == TTL_KPIS_DIA:
            return self._cache_kpis
        elif ttl == TTL_HISTORICOS:
            return self._cache_historicos
        return self._cache_general

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            # Buscar en todas las particiones
            for cache in (self._cache_vivo, self._cache_kpis, self._cache_historicos, self._cache_general):
                if key in cache:
                    try:
                        return cache[key]
                    except KeyError:
                        pass
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None, tags: Optional[List[str]] = None) -> None:
        async with self._lock:
            cache = self._seleccionar_cache(ttl)
            cache[key] = value
            if tags:
                self._key_tags[key] = set(tags)

    async def delete(self, key: str) -> bool:
        async with self._lock:
            eliminado = False
            for cache in (self._cache_vivo, self._cache_kpis, self._cache_historicos, self._cache_general):
                if key in cache:
                    del cache[key]
                    eliminado = True
            self._key_tags.pop(key, None)
            return eliminado

    async def invalidate_prefix(self, prefix: str) -> int:
        """Invalida todas las claves que comiencen con el prefijo o que contengan la etiqueta."""
        async with self._lock:
            claves_a_borrar: Set[str] = set()

            # Revisar coincidencia de prefijo directo
            for cache in (self._cache_vivo, self._cache_kpis, self._cache_historicos, self._cache_general):
                for k in list(cache.keys()):
                    if k.startswith(prefix) or prefix in k:
                        claves_a_borrar.add(k)

            # Revisar coincidencia de etiquetas
            for k, tags in list(self._key_tags.items()):
                if any(prefix in tag for tag in tags):
                    claves_a_borrar.add(k)

            conteo = 0
            for k in claves_a_borrar:
                for cache in (self._cache_vivo, self._cache_kpis, self._cache_historicos, self._cache_general):
                    if k in cache:
                        del cache[k]
                self._key_tags.pop(k, None)
                conteo += 1

            return conteo

    async def clear(self) -> int:
        """Purga total de todas las particiones de la caché."""
        async with self._lock:
            total = (
                len(self._cache_vivo)
                + len(self._cache_kpis)
                + len(self._cache_historicos)
                + len(self._cache_general)
            )
            self._cache_vivo.clear()
            self._cache_kpis.clear()
            self._cache_historicos.clear()
            self._cache_general.clear()
            self._key_tags.clear()
            return total

    def stats(self) -> Dict[str, Any]:
        """Reporta métricas de ocupación de la caché."""
        return {
            "aforo_vivo_items": len(self._cache_vivo),
            "kpis_dia_items": len(self._cache_kpis),
            "historicos_items": len(self._cache_historicos),
            "general_items": len(self._cache_general),
            "total_items": (
                len(self._cache_vivo)
                + len(self._cache_kpis)
                + len(self._cache_historicos)
                + len(self._cache_general)
            ),
        }


# Instancia singleton global del gestor de caché
_cache_global = CacheEnMemoria()


def obtener_cache() -> CacheEnMemoria:
    """Retorna la instancia global del gestor de caché."""
    return _cache_global


async def invalidar_cache_por_espacio(espacio_id: int) -> int:
    """
    Invalida todas las claves de caché vinculadas a un espacio institucional específico.
    Se invoca automáticamente tras una ingesta de datos o sincronización horaria.
    """
    prefijo = f"espacio:{espacio_id}"
    cantidad = await _cache_global.invalidate_prefix(prefijo)
    logger.info(f"[cache] Invalidadas {cantidad} entradas para {prefijo}")
    return cantidad


async def limpiar_toda_la_cache() -> int:
    """Limpia la totalidad de la memoria de caché del sistema."""
    cantidad = await _cache_global.clear()
    logger.info(f"[cache] Purga total ejecutada: {cantidad} entradas eliminadas.")
    return cantidad


def _normalizar_argumentos_funcion(func: Callable, args: tuple, kwargs: dict) -> dict:
    """Resuelve valores por defecto (incluyendo objetos Query de FastAPI) y normaliza cadenas vacías."""
    import inspect
    try:
        sig = inspect.signature(func)
        bound = sig.bind_partial(*args, **kwargs)
        bound.apply_defaults()
        argumentos = dict(bound.arguments)
    except Exception:
        argumentos = dict(kwargs)

    normalizados = {}
    for k, v in argumentos.items():
        if hasattr(v, "default") and not isinstance(v, (int, float, str, bool, list, dict)):
            v = v.default
        if isinstance(v, str) and v.strip() == "":
            v = None
        normalizados[k] = v
    return normalizados


def _generar_clave_cache(
    func_nombre: str,
    args: tuple,
    kwargs: dict,
    categoria: str,
    espacio_id: Optional[int] = None,
) -> Tuple[str, List[str]]:
    """Construye una clave determinista basada en los argumentos de la función."""
    # Extraer espacio_id si viene en kwargs o args
    eid = espacio_id
    if eid is None:
        if "espacio_id" in kwargs and kwargs["espacio_id"] is not None:
            try:
                eid = int(kwargs["espacio_id"])
            except Exception:
                pass
        elif args:
            for arg in args:
                if isinstance(arg, int) and arg in (1, 2, 3, 4):
                    eid = arg
                    break

    # Sanitizar kwargs para excluir objetos no serializables (como Response, Request, AsyncSession)
    kwargs_limpios = {}
    for k, v in kwargs.items():
        if k in ("db", "session", "response", "request", "current_user", "background_tasks"):
            continue
        if isinstance(v, str) and v.strip() == "":
            v = None
        try:
            json.dumps(v, default=str)
            kwargs_limpios[k] = v
        except Exception:
            kwargs_limpios[k] = str(v)

    # Armar hash de parámetros
    str_params = json.dumps(kwargs_limpios, sort_keys=True, default=str)
    hash_params = hashlib.md5(str_params.encode()).hexdigest()[:12]

    tags = []
    if eid is not None:
        clave = f"espacio:{eid}:{categoria}:{func_nombre}:{hash_params}"
        tags.append(f"espacio:{eid}")
    else:
        clave = f"global:{categoria}:{func_nombre}:{hash_params}"

    return clave, tags


def cachear_respuesta(
    ttl_segundos: int = TTL_KPIS_DIA,
    categoria: str = "kpis",
    por_espacio: bool = True,
):
    """
    Decorador asíncrono para endpoints o métodos de servicio.
    Inyecta automáticamente la cabecera HTTP 'X-Cache: HIT' o 'X-Cache: MISS'
    si el objeto 'response' de FastAPI está presente en la llamada.
    """
    def decorador(func: Callable):
        @functools.wraps(func)
        async def envoltura(*args, **kwargs):
            kwargs_efectivos = _normalizar_argumentos_funcion(func, args, kwargs)

            # Buscar objeto Response de FastAPI en kwargs o args
            response_obj: Optional[Response] = kwargs_efectivos.get("response") or kwargs.get("response")
            if not response_obj:
                for a in args:
                    if isinstance(a, Response):
                        response_obj = a
                        break

            espacio_id_param = kwargs_efectivos.get("espacio_id") if por_espacio else None
            clave, tags = _generar_clave_cache(
                func_nombre=func.__name__,
                args=(),
                kwargs=kwargs_efectivos,
                categoria=categoria,
                espacio_id=espacio_id_param,
            )

            # 1. Comprobar caché
            valor_en_cache = await _cache_global.get(clave)
            if valor_en_cache is not None:
                if response_obj:
                    response_obj.headers["X-Cache"] = "HIT"
                    response_obj.headers["X-Cache-TTL"] = str(ttl_segundos)
                return valor_en_cache

            # 2. Computar resultado usando los argumentos normalizados si fue invocado internamente
            resultado = await func(**kwargs_efectivos) if not args else await func(*args, **kwargs)

            # 3. Guardar en caché y marcar MISS
            if resultado is not None:
                await _cache_global.set(clave, resultado, ttl=ttl_segundos, tags=tags)

            if response_obj:
                response_obj.headers["X-Cache"] = "MISS"
                response_obj.headers["X-Cache-TTL"] = str(ttl_segundos)

            return resultado

        return envoltura
    return decorador


_precalentamiento_en_curso: bool = False


async def precalentar_cache_modulos() -> None:
    """
    Precalienta en segundo plano las consultas analíticas y predictivas por defecto
    de la última semana registrada para Biblioteca (espacio_id=1) y Estacionamiento (espacio_id=2).
    """
    global _precalentamiento_en_curso
    if _precalentamiento_en_curso:
        return
    _precalentamiento_en_curso = True
    try:
        from datetime import date, timedelta
        from types import SimpleNamespace
        from app.core.database import AsyncSessionLocal
        from app.api.v1.endpoints import attendance, vehicles, predictions, metrics

        usuario_sistema = SimpleNamespace(
            id=0,
            roles=[SimpleNamespace(nombre="SuperAdmin")],
            allowed_datasets="todos",
            espacio_id=None,
            is_active=True,
        )
        respuesta_ficticia = Response()

        async with AsyncSessionLocal() as sesion:
            # 1. Límites de fechas y precalentamiento de Biblioteca (espacio_id = 1)
            limites_bib = await metrics.get_date_bounds(
                response=respuesta_ficticia,
                espacio_id=1,
                current_user=usuario_sistema,
                db=sesion,
            )
            fecha_max_str_bib = (limites_bib.get("fecha_max") if isinstance(limites_bib, dict) else getattr(limites_bib, "fecha_max", None)) or "2026-10-14"
            fin_bib = date.fromisoformat(str(fecha_max_str_bib)[:10])
            ini_bib = fin_bib - timedelta(days=6)

            tareas_biblioteca = [
                lambda: metrics.get_kpi_summary(response=respuesta_ficticia, espacio_id=1, fecha_inicio=ini_bib, fecha_fin=fin_bib, current_user=usuario_sistema, db=sesion),
                lambda: attendance.get_kpis(response=respuesta_ficticia, fecha_inicio=ini_bib, fecha_fin=fin_bib, espacio_id=1, current_user=usuario_sistema, db=sesion),
                lambda: attendance.get_occupancy_realtime(response=respuesta_ficticia, espacio_id=1, current_user=usuario_sistema, db=sesion),
                lambda: attendance.get_hourly_flow(response=respuesta_ficticia, fecha_inicio=ini_bib, fecha_fin=fin_bib, espacio_id=1, current_user=usuario_sistema, db=sesion),
                lambda: attendance.get_heatmap(response=respuesta_ficticia, fecha_inicio=ini_bib, fecha_fin=fin_bib, espacio_id=1, current_user=usuario_sistema, db=sesion),
                lambda: attendance.get_peak_valley(response=respuesta_ficticia, fecha_inicio=ini_bib, fecha_fin=fin_bib, espacio_id=1, current_user=usuario_sistema, db=sesion),
                lambda: attendance.get_weekly_evolution(response=respuesta_ficticia, fecha_inicio=ini_bib, fecha_fin=fin_bib, espacio_id=1, current_user=usuario_sistema, db=sesion),
                lambda: attendance.get_monthly_volume(response=respuesta_ficticia, fecha_inicio=ini_bib, fecha_fin=fin_bib, espacio_id=1, current_user=usuario_sistema, db=sesion),
                lambda: attendance.get_academic_milestones_comparison(response=respuesta_ficticia, fecha_inicio=ini_bib, fecha_fin=fin_bib, espacio_id=1, current_user=usuario_sistema, db=sesion),
                lambda: attendance.get_doors_usage(response=respuesta_ficticia, fecha_inicio=ini_bib, fecha_fin=fin_bib, espacio_id=1, current_user=usuario_sistema, db=sesion),
                lambda: attendance.get_rooms_comparison(response=respuesta_ficticia, fecha_inicio=ini_bib, fecha_fin=fin_bib, espacio_id=1, current_user=usuario_sistema, db=sesion),
                lambda: attendance.get_daily_average_attendance(response=respuesta_ficticia, fecha_inicio=ini_bib, fecha_fin=fin_bib, espacio_id=1, current_user=usuario_sistema, db=sesion),
                lambda: attendance.get_curricular_distribution(response=respuesta_ficticia, fecha_inicio=ini_bib, fecha_fin=fin_bib, espacio_id=1, current_user=usuario_sistema, db=sesion),
                lambda: attendance.get_checkins_distribution(response=respuesta_ficticia, fecha_inicio=ini_bib, fecha_fin=fin_bib, espacio_id=1, current_user=usuario_sistema, db=sesion),
                lambda: attendance.get_visit_profiles_donut(response=respuesta_ficticia, fecha_inicio=ini_bib, fecha_fin=fin_bib, espacio_id=1, current_user=usuario_sistema, db=sesion),
                lambda: predictions.get_forecast_attendance(response=respuesta_ficticia, sala="todas", db=sesion, current_user=usuario_sistema),
                lambda: predictions.get_forecast_14days_endpoint(response=respuesta_ficticia, espacio_id=1, db=sesion, current_user=usuario_sistema),
                lambda: predictions.get_alerts(response=respuesta_ficticia, db=sesion, current_user=usuario_sistema),
            ]
            for fn_bib in tareas_biblioteca:
                try:
                    await fn_bib()
                except Exception as exc_b:
                    logger.debug(f"[cache] Precalentamiento parcial biblioteca omitido: {exc_b}")

            # 2. Límites de fechas y precalentamiento de Estacionamiento (espacio_id = 2)
            limites_veh = await metrics.get_date_bounds(
                response=respuesta_ficticia,
                espacio_id=2,
                current_user=usuario_sistema,
                db=sesion,
            )
            fecha_max_str_veh = (limites_veh.get("fecha_max") if isinstance(limites_veh, dict) else getattr(limites_veh, "fecha_max", None)) or "2026-10-14"
            fin_veh = date.fromisoformat(str(fecha_max_str_veh)[:10])
            ini_veh = fin_veh - timedelta(days=6)

            tareas_estacionamiento = [
                lambda: metrics.get_kpi_summary(response=respuesta_ficticia, espacio_id=2, fecha_inicio=ini_veh, fecha_fin=fin_veh, current_user=usuario_sistema, db=sesion),
                lambda: vehicles.get_kpis(response=respuesta_ficticia, fecha_inicio=ini_veh, fecha_fin=fin_veh, espacio_id=2, current_user=usuario_sistema, db=sesion),
                lambda: vehicles.get_parking_occupancy(response=respuesta_ficticia, espacio_id=2, current_user=usuario_sistema, db=sesion),
                lambda: vehicles.get_hourly_flow(response=respuesta_ficticia, fecha_inicio=ini_veh, fecha_fin=fin_veh, espacio_id=2, current_user=usuario_sistema, db=sesion),
                lambda: vehicles.get_fleet_composition(response=respuesta_ficticia, fecha_inicio=ini_veh, fecha_fin=fin_veh, espacio_id=2, current_user=usuario_sistema, db=sesion),
                lambda: vehicles.get_camera_stats(response=respuesta_ficticia, fecha_inicio=ini_veh, fecha_fin=fin_veh, espacio_id=2, current_user=usuario_sistema, db=sesion),
                lambda: vehicles.get_daily_evolution(response=respuesta_ficticia, fecha_inicio=ini_veh, fecha_fin=fin_veh, espacio_id=2, current_user=usuario_sistema, db=sesion),
                lambda: vehicles.get_academic_milestones_comparison(response=respuesta_ficticia, espacio_id=2, current_user=usuario_sistema, db=sesion),
                lambda: vehicles.get_intercampus_mobility(response=respuesta_ficticia, current_user=usuario_sistema, db=sesion),
                lambda: vehicles.get_behavioral_clusters(response=respuesta_ficticia, current_user=usuario_sistema, db=sesion),
                lambda: predictions.get_forecast_parking(response=respuesta_ficticia, db=sesion, current_user=usuario_sistema),
            ]
            for fn_veh in tareas_estacionamiento:
                try:
                    await fn_veh()
                except Exception as exc_v:
                    logger.debug(f"[cache] Precalentamiento parcial estacionamiento omitido: {exc_v}")

        logger.info("[cache] Precalentamiento de caché completado para Biblioteca y Estacionamiento.")
    except Exception as exc:
        logger.warning(f"[cache] Error general en precalentar_cache_modulos: {exc}")
    finally:
        _precalentamiento_en_curso = False

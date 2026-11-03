"""
smart_campus_adapter.py — Adaptador Oficial API Smart Campus UCT.

Conecta de forma asíncrona con https://integrasmartcampus.uct.cl/api/lectura
para la ingesta directa de torniquetes peatonales y pasos vehiculares ANPR,
aplicando particionamiento en ventanas de 7 días, seudonimización estricta (Ley N° 21.719)
y manejo de resiliencia con reintentos exponenciales.
"""
import asyncio
import logging
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import (
    AttendanceEventDTO,
    CalendarEventDTO,
    IngestionAdapter,
    VehicleEventDTO,
)
from app.core.config import settings
from app.core.security import (
    encrypt_vehicle_patente,
    pseudonymize_person,
    pseudonymize_vehicle,
)

logger = logging.getLogger("app.adapters.smart_campus")


class SmartCampusAPIError(Exception):
    """Excepción para errores de respuesta de la API Smart Campus."""
    pass


class SmartCampusAdapter(IngestionAdapter):
    """
    Adaptador de integración para la API Smart Campus de la Universidad Católica de Temuco.
    Consume torniquetes peatonales de biblioteca y cámaras ANPR de los 3 sectores vehiculares.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_segundos: float = 120.0,
    ):
        self.base_url = (base_url or getattr(settings, "SMART_CAMPUS_API_URL", "https://integrasmartcampus.uct.cl/api/lectura")).rstrip("/")
        # Si la URL viene sin /api/lectura, asegurar el prefijo
        if not self.base_url.endswith("/api/lectura"):
            if "integrasmartcampus.uct.cl" in self.base_url:
                self.base_url = f"{self.base_url}/api/lectura"

        raw_key = (
            api_key
            or getattr(settings, "LECTURA_API_KEY", None)
            or os.environ.get("LECTURA_API_KEY", "")
        )
        if not raw_key or not str(raw_key).strip():
            try:
                from app.core.config import Settings
                recarga = Settings()
                if recarga.LECTURA_API_KEY and recarga.LECTURA_API_KEY.strip():
                    raw_key = recarga.LECTURA_API_KEY
                    settings.LECTURA_API_KEY = raw_key.strip()
            except Exception:
                pass
        self.api_key = str(raw_key or "").strip()
        self.timeout_segundos = timeout_segundos

    def _obtener_cabeceras(self) -> Dict[str, str]:
        """Construye las cabeceras HTTP de autenticación institucional."""
        if not self.api_key:
            raise SmartCampusAPIError(
                "No se encontró LECTURA_API_KEY configurada para autenticar con la API Smart Campus."
            )
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "User-Agent": "DSS-UCT-Platform/2.0",
        }

    async def _solicitar_con_reintento(
        self,
        endpoint: str,
        parametros: Optional[Dict[str, Any]] = None,
        intentos_maximos: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Ejecuta una petición GET con reintentos ante códigos 502/503/504 o fallos de red.
        """
        url = f"{self.base_url}{endpoint}"
        cabeceras = self._obtener_cabeceras()

        for intento in range(1, intentos_maximos + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_segundos) as cliente:
                    respuesta = await cliente.get(url, headers=cabeceras, params=parametros)

                if respuesta.status_code == 200:
                    datos = respuesta.json()
                    return datos.get("registros", [])

                if respuesta.status_code in (400, 401, 404):
                    mensaje_error = respuesta.text
                    try:
                        mensaje_error = respuesta.json().get("error", mensaje_error)
                    except Exception:
                        pass
                    raise SmartCampusAPIError(f"HTTP {respuesta.status_code} en Smart Campus: {mensaje_error}")

                # Respuestas transitorias 502, 503, etc.
                logger.warning(
                    f"[SmartCampusAdapter] Intento {intento}/{intentos_maximos} falló con HTTP {respuesta.status_code}. Reintentando..."
                )
            except httpx.RequestError as exc:
                logger.warning(f"[SmartCampusAdapter] Error de transporte en intento {intento}: {exc}")
                if intento == intentos_maximos:
                    raise SmartCampusAPIError(f"Error de conexión con Smart Campus tras {intentos_maximos} intentos: {exc}")

            if intento < intentos_maximos:
                await asyncio.sleep(2 * intento)

        raise SmartCampusAPIError(f"Sin respuesta válida de {url} tras {intentos_maximos} intentos")

    async def obtener_puntos(self) -> Dict[str, Any]:
        """Consulta el catálogo de puertas y cámaras ANPR disponibles."""
        url = f"{self.base_url}/puntos"
        async with httpx.AsyncClient(timeout=30.0) as cliente:
            resp = await cliente.get(url, headers=self._obtener_cabeceras())
            resp.raise_for_status()
            return resp.json()

    async def obtener_marcajes_torniquetes(
        self,
        desde: Optional[date | datetime | str] = None,
        hasta: Optional[date | datetime | str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene los marcajes peatonales individuales de torniquetes.
        Particiona en tramos de 7 días de forma automática si el rango es extenso.
        """
        return await self._extraer_por_tramos("/torniquetes", desde, hasta)

    async def obtener_pasos_estacionamientos(
        self,
        desde: Optional[date | datetime | str] = None,
        hasta: Optional[date | datetime | str] = None,
        solo_completas: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene los pasos vehiculares por cámaras ANPR.
        Si solo_completas es True, excluye lecturas parciales (lectura_completa == False).
        """
        registros = await self._extraer_por_tramos("/estacionamientos", desde, hasta)
        if solo_completas:
            registros = [r for r in registros if r.get("lectura_completa") is True]
        return registros

    async def _extraer_por_tramos(
        self,
        endpoint: str,
        desde: Optional[date | datetime | str] = None,
        hasta: Optional[date | datetime | str] = None,
    ) -> List[Dict[str, Any]]:
        """Itera en bloques de hasta 7 días respetando la cuota de la API institucional."""
        # Resolver fechas por defecto: día en curso si no se proporcionan
        fecha_fin = datetime.now().date() if hasta is None else (hasta.date() if isinstance(hasta, datetime) else (datetime.strptime(hasta[:10], "%Y-%m-%d").date() if isinstance(hasta, str) else hasta))
        fecha_inicio = fecha_fin if desde is None else (desde.date() if isinstance(desde, datetime) else (datetime.strptime(desde[:10], "%Y-%m-%d").date() if isinstance(desde, str) else desde))

        if fecha_inicio > fecha_fin:
            raise ValueError(f"Fecha de inicio ({fecha_inicio}) no puede ser posterior a fecha de fin ({fecha_fin})")

        todos_los_registros: List[Dict[str, Any]] = []
        actual = fecha_inicio

        while actual <= fecha_fin:
            siguiente = min(actual + timedelta(days=6), fecha_fin)
            params = {
                "desde": actual.isoformat(),
                "hasta": siguiente.isoformat(),
            }
            logger.info(f"[SmartCampusAdapter] Consultando {endpoint} tramo {actual} a {siguiente}...")
            lote = await self._solicitar_con_reintento(endpoint, parametros=params)
            todos_los_registros.extend(lote)
            actual = siguiente + timedelta(days=1)
            if actual <= fecha_fin:
                await asyncio.sleep(1.0)  # Evitar sobrecarga en la API institucional

        return todos_los_registros

    # =========================================================================
    # Implementación de la Interfaz IngestionAdapter (base.py)
    # =========================================================================

    async def fetch_attendance_events(self, espacio_id: int) -> List[AttendanceEventDTO]:
        """
        Descarga marcajes de torniquetes del día y los transforma a DTOs seudonimizados.
        """
        hoy = datetime.now().date()
        raw_events = await self.obtener_marcajes_torniquetes(desde=hoy, hasta=hoy)
        dtos: List[AttendanceEventDTO] = []

        for row in raw_events:
            try:
                # Parsear fecha ISO 8601
                fecha_str = row.get("fecha", "")
                dt = datetime.fromisoformat(fecha_str) if fecha_str else datetime.now()

                # Identificador seudónimo (Ley N° 21.719) priorizando matrícula para cruce con dim_estudiante_carrera
                raw_id = row.get("matricula") or row.get("id_visitante") or ""
                if raw_id:
                    person_hash = pseudonymize_person(str(raw_id).strip())
                else:
                    # Sin persona identificada (pulsador o salida sin tarjeta)
                    person_hash = f"sin_id_{dt.strftime('%Y%m%d%H%M%S')}_{row.get('puerta', 'desc')}"

                sentido = str(row.get("sentido", "")).lower()
                es_salida = any(s in sentido for s in ["salida", "out", "egreso"])

                puerta = row.get("puerta") or row.get("acceso") or "Torniquete"

                dto = AttendanceEventDTO(
                    time=dt,
                    espacio_id=espacio_id,
                    person_id_hash=person_hash,
                    door_entrada=None if es_salida else puerta,
                    door_salida=puerta if es_salida else None,
                    primera_entrada=None if es_salida else dt,
                    ultima_salida=dt if es_salida else None,
                    salida_imputada=False,
                    entrada_imputada=False,
                    permanencia_min=None,
                    marcajes_totales=1,
                    alerta_coherencia_fechas=False,
                    alerta_marcajes=False,
                    carrera=row.get("detalle_estamento") if row.get("estamento") == "Estudiante" else None,
                    facultad=row.get("estamento"),
                )
                dtos.append(dto)
            except Exception as e:
                logger.debug(f"[SmartCampusAdapter] Error mapeando fila de torniquete: {e}")

        return dtos

    async def fetch_vehicle_events(self, espacio_id: int) -> List[VehicleEventDTO]:
        """
        Descarga pasos vehiculares del día y los transforma a DTOs con cifrado Fernet.
        """
        hoy = datetime.now().date()
        raw_events = await self.obtener_pasos_estacionamientos(desde=hoy, hasta=hoy, solo_completas=True)
        dtos: List[VehicleEventDTO] = []

        for row in raw_events:
            try:
                fecha_str = row.get("fecha", "")
                dt = datetime.fromisoformat(fecha_str) if fecha_str else datetime.now()

                patente_raw = str(row.get("patente", "")).strip().upper()
                if not patente_raw:
                    continue

                try:
                    patente_hash, patente_cifrada = encrypt_vehicle_patente(patente_raw)
                except Exception:
                    patente_hash = pseudonymize_vehicle(patente_raw)
                    patente_cifrada = f"CIPHER_LOCAL_{patente_hash[:16]}"

                sentido_raw = str(row.get("sentido", "")).lower()
                # Mapeo: acercandose -> entrada, alejandose -> salida
                if "acercandose" in sentido_raw or "entrada" in sentido_raw:
                    direccion = "entrada"
                elif "alejandose" in sentido_raw or "salida" in sentido_raw:
                    direccion = "salida"
                else:
                    direccion = "entrada"

                dto = VehicleEventDTO(
                    time=dt,
                    espacio_id=espacio_id,
                    patente_hash=patente_hash,
                    patente_cifrada=patente_cifrada,
                    camara=row.get("camara") or row.get("acceso") or "ANPR",
                    direccion=direccion,
                    tipo_vehiculo=row.get("tipo_vehiculo"),
                    marca=row.get("marca"),
                    color=row.get("color"),
                    calidad_lectura="ok" if row.get("lectura_completa") else "baja",
                )
                dtos.append(dto)
            except Exception as e:
                logger.debug(f"[SmartCampusAdapter] Error mapeando fila vehicular: {e}")

        return dtos

    async def fetch_calendar_events(self) -> List[CalendarEventDTO]:
        """Smart Campus no entrega eventos de calendario."""
        return []

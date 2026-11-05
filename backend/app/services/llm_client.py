import asyncio
import hashlib
import inspect
import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional
from cachetools import TTLCache
from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security_cipher import decrypt_api_key
from app.domain.config_models import ConfiguracionEspacios
from app.core.config import settings
from app.domain import models

logger = logging.getLogger(__name__)

# Cachés en memoria TTL
_clientes_llm_cache: TTLCache = TTLCache(maxsize=50, ttl=300)
_modelos_disponibles_cache: TTLCache = TTLCache(maxsize=10, ttl=3600)
_herramientas_gemini_cache: Dict[int, Any] = {}

# Directivas y reglas de sistema preconstruidas al arrancar el servicio
REGLA_AISLAMIENTO_ESTACIONAMIENTO: str = (
    "DIRECTIVA CRÍTICA DE AISLAMIENTO: Estás operando EXCLUSIVAMENTE dentro del módulo Estacionamiento CSF. "
    "Está terminantemente prohibido llamar herramientas peatonales o responder preguntas sobre la biblioteca, salas de estudio, carreras o torniquetes de biblioteca. "
    "Si el usuario pregunta sobre la biblioteca o temas ajenos al estacionamiento, NO ejecutes ninguna función ni inventes datos; "
    "responde de forma concisa y profesional indicando que te encuentras en el módulo de Estacionamiento CSF y que para consultar sobre Biblioteca debe cambiar el módulo en el selector superior."
)

REGLA_AISLAMIENTO_BIBLIOTECA: str = (
    "DIRECTIVA CRÍTICA DE AISLAMIENTO: Estás operando EXCLUSIVAMENTE dentro del módulo Biblioteca CSF. "
    "Está terminantemente prohibido llamar herramientas vehiculares o responder preguntas sobre estacionamiento, vehículos, patentes o cámaras ANPR. "
    "Si el usuario pregunta sobre estacionamiento o temas automotrices, NO ejecutes ninguna función ni inventes datos; "
    "responde de forma concisa y profesional indicando que te encuentras en el módulo de Biblioteca CSF y que para consultar sobre Estacionamiento debe cambiar el módulo en el selector superior."
)

PLANTILLA_SISTEMA_ESTACIONAMIENTO: str = (
    "Eres el Asistente Analítico Institucional del DSS Campus San Francisco de la Universidad Católica de Temuco. "
    "El espacio operativo actual es Estacionamiento CSF (espacio_id=2).{context_info} "
    f"{REGLA_AISLAMIENTO_ESTACIONAMIENTO} "
    "DIRECTIVA TEMPORAL INSTITUCIONAL: El año operativo activo con registros en la base de datos es {anio_referencia}. "
    "Cuando el usuario mencione fechas o meses sin especificar año (ej. '23 al 28 de agosto'), "
    "debes asignar las fechas en el año activo ({anio_referencia}). "
    "Si el usuario indica expresamente un año en su consulta (ej. 'en {anio_objetivo}'), respeta estrictamente el año solicitado. "
    "REGLAS DE ENRUTAMIENTO SEMÁNTICO: "
    "1. Para preguntas generales sobre asistencia, concurrencia, aforo, ocupación o volumen en fechas o rangos, selecciona obligatoriamente 'consultar_aforo_historico'. "
    "2. Para preguntas sobre hechos institucionales (feriados oficiales, semanas de receso, vacaciones, períodos de exámenes o solemnes, hitos de clases, suspensiones de actividades, paros y contingencias, o régimen horario), selecciona obligatoriamente 'consultar_calendario_academico'. "
    "3. Tu tarea es seleccionar la herramienta de consulta más precisa para responder al usuario usando Function Calling. "
    "Si la consulta es meramente conceptual o un saludo, responde textualmente sin llamar herramientas."
)

PLANTILLA_SISTEMA_BIBLIOTECA: str = (
    "Eres el Asistente Analítico Institucional del DSS Campus San Francisco de la Universidad Católica de Temuco. "
    "El espacio operativo actual es Biblioteca CSF (espacio_id=1).{context_info} "
    f"{REGLA_AISLAMIENTO_BIBLIOTECA} "
    "DIRECTIVA TEMPORAL INSTITUCIONAL: El año operativo activo con registros en la base de datos es {anio_referencia}. "
    "Cuando el usuario mencione fechas o meses sin especificar año (ej. '23 al 28 de agosto'), "
    "debes asignar las fechas en el año activo ({anio_referencia}). "
    "Si el usuario indica expresamente un año en su consulta (ej. 'en {anio_objetivo}'), respeta estrictamente el año solicitado. "
    "REGLAS DE ENRUTAMIENTO SEMÁNTICO: "
    "1. Para preguntas generales sobre asistencia, concurrencia, aforo, ocupación o volumen en fechas o rangos, selecciona obligatoriamente 'consultar_aforo_historico'. "
    "2. Selecciona 'consultar_comparativa_salas' ÚNICAMENTE si la pregunta menciona explícitamente salas, Sala 1, Sala 2, Pecera, CSF02 o CSF04. "
    "3. Para preguntas sobre hechos institucionales (feriados oficiales, semanas de receso, vacaciones, períodos de exámenes o solemnes, hitos de clases, suspensiones de actividades, paros y contingencias, o régimen de Horario 24 Horas), selecciona obligatoriamente 'consultar_calendario_academico' o 'consultar_campana_24h'. "
    "4. Tu tarea es seleccionar la herramienta de consulta más precisa para responder al usuario usando Function Calling. "
    "Si la consulta es meramente conceptual o un saludo, responde textualmente sin llamar herramientas."
)

PLANTILLA_SISTEMA_INTENT: str = (
    "Eres el Asistente Analítico DSS de la Universidad Católica de Temuco (Campus San Francisco). "
    "{context_directive}"
    "El usuario consulta sobre el recinto: {dataset_tipo}. "
    "Debes clasificar la intención analítica de la consulta del usuario. "
    "Intents disponibles: "
    "'monthly', 'monthly_trend', 'weekly', 'exams', 'hourly', 'cameras', 'stay', 'table', 'text'. "
    "Responde estrictamente con un objeto JSON válido con las llaves: "
    "\"tipo\" (\"plotly\" | \"df\" | \"text\"), "
    "\"intent\" (\"monthly\" | \"monthly_trend\" | \"weekly\" | \"exams\" | \"hourly\" | \"cameras\" | \"stay\" | \"table\" | \"text\"), "
    "\"mes\" (entero del 1 al 12 o null si no aplica), "
    "\"explicacion\" (texto conciso respondiendo a la consulta)."
)


class LLMClientBase(ABC):
    @abstractmethod
    async def generate_response(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
        response_mime_type: Optional[str] = None,
    ) -> Optional[str]:
        pass

    @abstractmethod
    async def analyze_query_with_tools(
        self,
        prompt: str,
        espacio_id: int,
        grafico_contexto: Optional[str] = None,
        model_name: Optional[str] = None,
        fecha_inicio: Optional[str] = None,
        fecha_fin: Optional[str] = None,
        periodo_label: Optional[str] = None,
        filtros: Optional[Dict[str, Any]] = None,
        anio_referencia: int = 2026,
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def generate_narrative_stream(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> AsyncIterator[str]:
        pass

    @abstractmethod
    async def consult_intent(
        self,
        prompt: str,
        dataset_tipo: str,
        model_name: Optional[str] = None,
        grafico_contexto: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        pass


def get_gemini_tools(espacio_id: int = 1):
    if espacio_id in _herramientas_gemini_cache:
        return _herramientas_gemini_cache[espacio_id]

    from google.genai import types

    if espacio_id == 2:
        desc_aforo = "Consulta series temporales y curvas de ocupación vehicular por franja horaria, diaria o semanal en Estacionamiento CSF."
        desc_mapa = "Consulta la matriz de calor semanal y horaria de densidad y ocupación de estacionamientos (día vs hora)."
        desc_picos = "Consulta los picos de afluencia vehicular (horas punta) y valles de menor congestión en estacionamiento."
        desc_prophet = "Consulta la predicción analítica de ocupación vehicular futura calculada con el modelo Prophet para Estacionamiento."
        desc_kpis = "Consulta la ocupación vehicular actual instantánea, capacidad total de plazas y tasa de ocupación de Estacionamiento CSF."
    else:
        desc_aforo = "Consulta series temporales y curvas de asistencia peatonal por franja horaria, diaria o semanal en Biblioteca CSF."
        desc_mapa = "Consulta la matriz de calor semanal y horaria de concurrencia y aforo en Biblioteca CSF (día vs hora)."
        desc_picos = "Consulta los picos de afluencia peatonal (horas punta) y valles de menor congestión en Biblioteca CSF."
        desc_prophet = "Consulta la predicción analítica de asistencia futura calculada con el modelo Prophet para Biblioteca CSF."
        desc_kpis = "Consulta el aforo actual instantáneo, capacidad total y tasa de ocupación de Biblioteca CSF."

    herramientas_base = [
        types.FunctionDeclaration(
            name="consultar_calendario_academico",
            description="Consulta hechos institucionales oficiales del Calendario Académico UCT: Feriados Oficiales, Semanas de Receso, Vacaciones, Exámenes / Solemnes, Hitos de Clases, Suspensiones de Actividades, Paros y Contingencias, y régimen de Horario 24 Horas, analizando su impacto en la concurrencia.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "espacio_id": types.Schema(type="INTEGER", description=f"ID del espacio ({espacio_id})"),
                    "semana": types.Schema(type="INTEGER", description="Número de semana ISO (1 al 53)"),
                    "mes": types.Schema(type="INTEGER", description="Mes a consultar del 1 al 12"),
                    "fecha_inicio": types.Schema(type="STRING", description="Fecha de inicio YYYY-MM-DD"),
                    "fecha_fin": types.Schema(type="STRING", description="Fecha de fin YYYY-MM-DD"),
                    "busqueda": types.Schema(type="STRING", description="Término de búsqueda de texto (ej. 'receso', 'vacaciones', 'feriado')"),
                },
                required=["espacio_id"],
            ),
        ),

        types.FunctionDeclaration(
            name="consultar_aforo_historico",
            description=desc_aforo,
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "espacio_id": types.Schema(type="INTEGER", description=f"ID del espacio ({espacio_id})"),
                    "fecha_inicio": types.Schema(type="STRING", description="Fecha de inicio YYYY-MM-DD (opcional)"),
                    "fecha_fin": types.Schema(type="STRING", description="Fecha de fin YYYY-MM-DD (opcional)"),
                    "intervalo": types.Schema(type="STRING", description="Nivel de agregación: 'horario', 'diario' o 'semanal'"),
                },
                required=["espacio_id"],
            ),
        ),
        types.FunctionDeclaration(
            name="consultar_mapa_calor",
            description=desc_mapa,
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "espacio_id": types.Schema(type="INTEGER", description=f"ID del espacio ({espacio_id})"),
                    "mes": types.Schema(type="INTEGER", description="Mes a consultar del 1 al 12 (opcional)"),
                },
                required=["espacio_id"],
            ),
        ),
        types.FunctionDeclaration(
            name="consultar_picos_flujo",
            description=desc_picos,
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "espacio_id": types.Schema(type="INTEGER", description=f"ID del espacio ({espacio_id})"),
                    "fecha_inicio": types.Schema(type="STRING", description="Fecha de inicio YYYY-MM-DD (opcional)"),
                    "fecha_fin": types.Schema(type="STRING", description="Fecha de fin YYYY-MM-DD (opcional)"),
                },
                required=["espacio_id"],
            ),
        ),
        types.FunctionDeclaration(
            name="consultar_proyeccion_prophet",
            description=desc_prophet,
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "espacio_id": types.Schema(type="INTEGER", description=f"ID del espacio ({espacio_id})"),
                    "horizonte_dias": types.Schema(type="INTEGER", description="Días de pronóstico (7 o 14)"),
                },
                required=["espacio_id"],
            ),
        ),
        types.FunctionDeclaration(
            name="consultar_kpis_actuales",
            description=desc_kpis,
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "espacio_id": types.Schema(type="INTEGER", description=f"ID del espacio ({espacio_id})"),
                },
                required=["espacio_id"],
            ),
        ),
        types.FunctionDeclaration(
            name="consultar_evolucion_semanal",
            description="Consulta la evolución de afluencia o asistencia agrupada por semana ISO, comparando el impacto de hitos del calendario académico.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "espacio_id": types.Schema(type="INTEGER", description=f"ID del espacio ({espacio_id})"),
                    "fecha_inicio": types.Schema(type="STRING", description="Fecha de inicio YYYY-MM-DD (opcional)"),
                    "fecha_fin": types.Schema(type="STRING", description="Fecha de fin YYYY-MM-DD (opcional)"),
                },
                required=["espacio_id"],
            ),
        ),
    ]

    if espacio_id == 2:
        herramientas_especificas = [
            types.FunctionDeclaration(
                name="consultar_flota_vehicular",
                description="Consulta la composición del parque automotriz por tipo de vehículo o marcas principales en Estacionamiento CSF.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "espacio_id": types.Schema(type="INTEGER", description="ID del espacio (2: Estacionamiento CSF)"),
                        "fecha_inicio": types.Schema(type="STRING", description="Fecha de inicio YYYY-MM-DD (opcional)"),
                        "fecha_fin": types.Schema(type="STRING", description="Fecha de fin YYYY-MM-DD (opcional)"),
                    },
                    required=["espacio_id"],
                ),
            ),
            types.FunctionDeclaration(
                name="consultar_camaras_anpr",
                description="Consulta la distribución de capturas y tráfico vehicular por cámara ANPR física en Estacionamiento CSF.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "espacio_id": types.Schema(type="INTEGER", description="ID del espacio (2: Estacionamiento CSF)"),
                        "fecha_inicio": types.Schema(type="STRING", description="Fecha de inicio YYYY-MM-DD (opcional)"),
                        "fecha_fin": types.Schema(type="STRING", description="Fecha de fin YYYY-MM-DD (opcional)"),
                    },
                    required=["espacio_id"],
                ),
            ),
            types.FunctionDeclaration(
                name="consultar_movilidad_intercampus",
                description="Consulta los viajes y traslados vehiculares entre Campus San Francisco y San Juan Pablo II.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "espacio_id": types.Schema(type="INTEGER", description="ID del espacio (2: Estacionamiento CSF)"),
                    },
                    required=["espacio_id"],
                ),
            ),
            types.FunctionDeclaration(
                name="consultar_clustering_vehicular",
                description="Consulta los clústeres no supervisados K-Means y detección de posible uso vehicular externo.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "espacio_id": types.Schema(type="INTEGER", description="ID del espacio (2: Estacionamiento CSF)"),
                    },
                    required=["espacio_id"],
                ),
            ),
        ]
    else:
        herramientas_especificas = [
            types.FunctionDeclaration(
                name="consultar_distribucion_carreras",
                description="Consulta la distribución y padrón de carreras y facultades con mayor asistencia a biblioteca.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "espacio_id": types.Schema(type="INTEGER", description="ID del espacio (1: Biblioteca CSF)"),
                        "fecha_inicio": types.Schema(type="STRING", description="Fecha de inicio YYYY-MM-DD (opcional)"),
                        "fecha_fin": types.Schema(type="STRING", description="Fecha de fin YYYY-MM-DD (opcional)"),
                    },
                    required=["espacio_id"],
                ),
            ),
            types.FunctionDeclaration(
                name="consultar_torniquetes_accesos",
                description="Consulta el uso y concurrencia por torniquetes físicos y accesos universales en Biblioteca CSF.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "espacio_id": types.Schema(type="INTEGER", description="ID del espacio (1: Biblioteca CSF)"),
                        "fecha_inicio": types.Schema(type="STRING", description="Fecha de inicio YYYY-MM-DD (opcional)"),
                        "fecha_fin": types.Schema(type="STRING", description="Fecha de fin YYYY-MM-DD (opcional)"),
                    },
                    required=["espacio_id"],
                ),
            ),
            types.FunctionDeclaration(
                name="consultar_comparativa_salas",
                description="Consulta la afluencia comparativa entre Sala 1 (CSF02 2° Piso) y Sala 2 (CSF04 Pecera).",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "espacio_id": types.Schema(type="INTEGER", description="ID del espacio (1: Biblioteca CSF)"),
                        "fecha_inicio": types.Schema(type="STRING", description="Fecha de inicio YYYY-MM-DD (opcional)"),
                        "fecha_fin": types.Schema(type="STRING", description="Fecha de fin YYYY-MM-DD (opcional)"),
                    },
                    required=["espacio_id"],
                ),
            ),
            types.FunctionDeclaration(
                name="consultar_perfiles_visita",
                description="Consulta los perfiles de visita, permanencia y tasa de rebote en biblioteca.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "espacio_id": types.Schema(type="INTEGER", description="ID del espacio (1: Biblioteca CSF)"),
                        "fecha_inicio": types.Schema(type="STRING", description="Fecha de inicio YYYY-MM-DD (opcional)"),
                        "fecha_fin": types.Schema(type="STRING", description="Fecha de fin YYYY-MM-DD (opcional)"),
                    },
                    required=["espacio_id"],
                ),
            ),
            types.FunctionDeclaration(
                name="consultar_pronostico_14d",
                description="Consulta la proyección de demanda a 14 días con HistGradientBoosting y calendario institucional.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "espacio_id": types.Schema(type="INTEGER", description="ID del espacio (1: Biblioteca CSF)"),
                    },
                    required=["espacio_id"],
                ),
            ),
            types.FunctionDeclaration(
                name="consultar_campana_24h",
                description="Consulta el régimen de Horario 24 Horas y Campaña de Exámenes en Sala 2 Pecera CSF04, flujo nocturno 20:30 a 08:30 hrs y aforo delta.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "espacio_id": types.Schema(type="INTEGER", description="ID del espacio (1: Biblioteca CSF)"),
                        "fecha_inicio": types.Schema(type="STRING", description="Fecha de inicio YYYY-MM-DD (opcional)"),
                        "fecha_fin": types.Schema(type="STRING", description="Fecha de fin YYYY-MM-DD (opcional)"),
                    },
                    required=["espacio_id"],
                ),
            ),
        ]

    tool_def = [types.Tool(function_declarations=herramientas_base + herramientas_especificas)]
    _herramientas_gemini_cache[espacio_id] = tool_def
    return tool_def


def es_error_reintentable(error: Exception) -> bool:
    code = getattr(error, "code", None) or getattr(error, "status_code", None)
    if code is not None:
        try:
            c = int(code)
            return c == 429 or (500 <= c <= 599)
        except (ValueError, TypeError):
            pass
    msg = str(error).lower()
    for code_str in ["429", "500", "502", "503", "504", "resource_exhausted", "unavailable", "internal server error", "overloaded"]:
        if code_str in msg:
            return True
    return False


async def ejecutar_con_reintentos_y_tiempo_espera(
    coroutine_func,
    max_reintentos: int = 3,
    demoras: tuple = (1.0, 2.0, 4.0),
):
    ultimo_error = None
    tiempo_espera = float(getattr(settings, "TIEMPO_ESPERA_LLM_SEGUNDOS", 20))
    for intento in range(max_reintentos):
        try:
            return await asyncio.wait_for(coroutine_func(), timeout=tiempo_espera)
        except asyncio.TimeoutError as te:
            logger.warning(
                f"Tiempo de espera agotado ({tiempo_espera}s) en llamada a LLM (intento {intento + 1}/{max_reintentos})."
            )
            ultimo_error = te
            if intento < max_reintentos - 1:
                demora = demoras[intento] if intento < len(demoras) else demoras[-1]
                await asyncio.sleep(demora)
                continue
            raise
        except Exception as e:
            ultimo_error = e
            if es_error_reintentable(e) and intento < max_reintentos - 1:
                demora = demoras[intento] if intento < len(demoras) else demoras[-1]
                logger.warning(
                    f"Error reintentable LLM ({e}) en intento {intento + 1}/{max_reintentos}. Reintentando en {demora}s..."
                )
                await asyncio.sleep(demora)
                continue
            raise e
    if ultimo_error:
        raise ultimo_error


def listar_modelos_disponibles(client) -> list[str]:
    if "modelos" in _modelos_disponibles_cache:
        return _modelos_disponibles_cache["modelos"]
    try:
        modelos = []
        for m in client.models.list():
            nombre = m.name.replace("models/", "") if hasattr(m, "name") and m.name else ""
            if "gemini" in nombre.lower():
                modelos.append(nombre)
        if modelos:
            _modelos_disponibles_cache["modelos"] = modelos
            return modelos
    except Exception as e:
        logger.warning(
            f"Error consultando client.models.list(): {e}. Usando fallback a {settings.MODELO_GEMINI_POR_DEFECTO}."
        )

    fallback = [
        settings.MODELO_GEMINI_POR_DEFECTO,
        "gemini-3.5-flash",
        "gemini-3.8-flash",
        "gemini-flash-latest",
        "gemini-3.1-flash-lite",
    ]
    _modelos_disponibles_cache["modelos"] = fallback
    return fallback


class GeminiClient(LLMClientBase):
    def __init__(self, api_key: str, default_model: Optional[str] = None):
        self.api_key = api_key
        self.default_model = default_model or settings.MODELO_GEMINI_POR_DEFECTO
        from google import genai
        self.client = genai.Client(api_key=self.api_key)

    def _resolve_model(self, model: Optional[str] = None) -> str:
        chosen_model = model or self.default_model
        # Redirigir modelos deprecados o con cuota restringida al modelo por defecto de alta disponibilidad
        if chosen_model in ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-flash", "gemini-3.5-flash"]:
            chosen_model = settings.MODELO_GEMINI_POR_DEFECTO
        modelos_disponibles = listar_modelos_disponibles(self.client)
        if chosen_model in modelos_disponibles:
            return chosen_model
        logger.warning(f"Modelo '{chosen_model}' no disponible. Usando fallback {settings.MODELO_GEMINI_POR_DEFECTO}.")
        return settings.MODELO_GEMINI_POR_DEFECTO

    async def analyze_query_with_tools(
        self,
        prompt: str,
        espacio_id: int,
        grafico_contexto: Optional[str] = None,
        model_name: Optional[str] = None,
        fecha_inicio: Optional[str] = None,
        fecha_fin: Optional[str] = None,
        periodo_label: Optional[str] = None,
        filtros: Optional[Dict[str, Any]] = None,
        anio_referencia: int = 2026,
    ) -> Dict[str, Any]:
        from google.genai import types

        effective_model = self._resolve_model(model_name)
        tools = get_gemini_tools(espacio_id)

        context_parts = []
        if grafico_contexto:
            context_parts.append(f"El usuario tiene enfocado el gráfico institucional '{grafico_contexto}'.")
        if periodo_label or fecha_inicio:
            context_parts.append(f"Período activo: {periodo_label or ''} (desde {fecha_inicio or 'inicio'} hasta {fecha_fin or 'actual'}).")
        if filtros:
            context_parts.append(f"Filtros activos en el dashboard: {json.dumps(filtros)}.")
        context_info = f" Contexto activo en pantalla: {' '.join(context_parts)}" if context_parts else ""

        match_anio_usuario = re.search(r'\b(20\d{2})\b', prompt)
        anio_objetivo = int(match_anio_usuario.group(1)) if match_anio_usuario else anio_referencia

        plantilla = PLANTILLA_SISTEMA_ESTACIONAMIENTO if espacio_id == 2 else PLANTILLA_SISTEMA_BIBLIOTECA
        system_instruction = plantilla.format(
            context_info=context_info,
            anio_referencia=anio_referencia,
            anio_objetivo=anio_objetivo,
        )

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=tools,
            temperature=0.1,
        )

        modelos_candidatos = list(dict.fromkeys([
            effective_model,
            settings.MODELO_GEMINI_POR_DEFECTO,
            "gemini-3.5-flash-lite",
            "gemini-flash-latest",
            "gemini-3.1-flash-lite",
            "gemini-flash-lite-latest",
        ]))

        res = None
        ultimo_error = None
        for mod_cand in modelos_candidatos:
            if not mod_cand:
                continue
            try:
                async def _llamar():
                    return await self.client.aio.models.generate_content(
                        model=mod_cand,
                        contents=prompt,
                        config=config,
                    )
                res = await ejecutar_con_reintentos_y_tiempo_espera(_llamar)
                if res:
                    break
            except Exception as e_mod:
                ultimo_error = e_mod
                logger.warning(f"Error en analyze_query_with_tools con {mod_cand}: {e_mod}. Probando siguiente modelo...")

        try:
            if res and res.function_calls:
                call = res.function_calls[0]
                args = dict(call.args) if call.args else {}
                args.setdefault("espacio_id", espacio_id)
                for f_key in ["fecha_inicio", "fecha_fin"]:
                    if f_key in args and isinstance(args[f_key], str):
                        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", args[f_key])
                        if m and (not match_anio_usuario and m.group(1) != str(anio_objetivo)):
                            args[f_key] = f"{anio_objetivo}-{m.group(2)}-{m.group(3)}"
                if fecha_inicio and "fecha_inicio" not in args:
                    args["fecha_inicio"] = fecha_inicio
                if fecha_fin and "fecha_fin" not in args:
                    args["fecha_fin"] = fecha_fin
                return {
                    "type": "tool_call",
                    "tool_name": call.name,
                    "args": args,
                }

            text_resp = res.text if res else None
            if text_resp:
                return {
                    "type": "text",
                    "text": text_resp,
                }

            # Si el modelo no devolvió texto o todos fallaron, usar respuesta offline institucional
            from app.api.v1.endpoints.assistant import build_offline_response
            return {
                "type": "text",
                "text": build_offline_response(prompt),
            }
        except Exception as e:
            logger.error(f"Error procesando resultado en analyze_query_with_tools: {e}")
            from app.api.v1.endpoints.assistant import build_offline_response
            return {
                "type": "text",
                "text": build_offline_response(prompt),
            }

    async def generate_narrative_stream(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> AsyncIterator[str]:
        from google.genai import types

        effective_model = self._resolve_model(model_name)
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.2,
        )
        candidatos_stream = list(dict.fromkeys([
            effective_model,
            settings.MODELO_GEMINI_POR_DEFECTO,
            "gemini-3.5-flash-lite",
            "gemini-flash-latest",
            "gemini-3.1-flash-lite",
            "gemini-flash-lite-latest",
        ]))

        chunks_yielded = 0
        stream_exitoso = False

        for mod_stream in candidatos_stream:
            if not mod_stream:
                continue
            try:
                res = self.client.aio.models.generate_content_stream(
                    model=mod_stream,
                    contents=prompt,
                    config=config,
                )
                stream = await res if inspect.iscoroutine(res) else res
                async for chunk in stream:
                    if chunk and chunk.text:
                        chunks_yielded += 1
                        yield chunk.text
                stream_exitoso = True
                break
            except Exception as e:
                logger.warning(f"Error en generate_narrative_stream con {mod_stream}: {e}")
                if chunks_yielded > 0:
                    yield " (Consulta completada de forma parcial por interrupción del servicio)."
                    return

        if not stream_exitoso and chunks_yielded == 0:
            from app.api.v1.endpoints.assistant import build_offline_response
            yield build_offline_response(prompt)

    async def generate_response(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
        response_mime_type: Optional[str] = None,
    ) -> Optional[str]:
        from google.genai import types

        effective_model = self._resolve_model(model)
        config = types.GenerateContentConfig(
            temperature=temperature,
        )
        if system_instruction:
            config.system_instruction = system_instruction
        if response_mime_type:
            config.response_mime_type = response_mime_type

        candidatos_resp = list(dict.fromkeys([
            effective_model,
            settings.MODELO_GEMINI_POR_DEFECTO,
            "gemini-3.5-flash-lite",
            "gemini-flash-latest",
            "gemini-3.1-flash-lite",
            "gemini-flash-lite-latest",
        ]))

        for mod_resp in candidatos_resp:
            if not mod_resp:
                continue
            try:
                async def _llamar():
                    return await self.client.aio.models.generate_content(
                        model=mod_resp,
                        contents=prompt,
                        config=config,
                    )
                res = await ejecutar_con_reintentos_y_tiempo_espera(_llamar)
                if res and res.text:
                    return res.text
            except Exception as e:
                logger.warning(f"Error en generate_response con {mod_resp}: {e}")

        from app.api.v1.endpoints.assistant import build_offline_response
        return build_offline_response(prompt)

    async def consult_intent(
        self,
        prompt: str,
        dataset_tipo: str,
        model_name: Optional[str] = None,
        grafico_contexto: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        context_directive = ""
        if grafico_contexto and grafico_contexto.strip():
            context_directive = (
                f"El usuario te está haciendo una pregunta específicamente sobre el gráfico o sección [{grafico_contexto.strip()}]. "
                "Basa tu análisis y respuesta principalmente en este contexto. "
            )
        sys_prompt = PLANTILLA_SISTEMA_INTENT.format(
            context_directive=context_directive,
            dataset_tipo=dataset_tipo,
        )
        try:
            raw_text = await self.generate_response(
                prompt=prompt,
                system_instruction=sys_prompt,
                model=model_name or self.default_model,
                temperature=0.1,
                response_mime_type="application/json",
            )
            if not raw_text:
                return None
            cleaned = raw_text.strip()
            if cleaned.startswith("```"):
                if cleaned.startswith("```json"):
                    cleaned = cleaned[7:]
                else:
                    cleaned = cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()
            return json.loads(cleaned)
        except Exception as e:
            logger.error(f"Error consultando intent con Gemini: {e}")
            return None


class ClaudeClient(LLMClientBase):
    def __init__(self, api_key: str, default_model: str = "claude-3-opus"):
        self.api_key = api_key
        self.default_model = default_model

    async def generate_response(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
        response_mime_type: Optional[str] = None,
    ) -> Optional[str]:
        raise NotImplementedError("Claude no está implementado. Configure el proveedor como 'gemini' en el panel de administración.")

    async def analyze_query_with_tools(
        self,
        prompt: str,
        espacio_id: int,
        grafico_contexto: Optional[str] = None,
        model_name: Optional[str] = None,
        fecha_inicio: Optional[str] = None,
        fecha_fin: Optional[str] = None,
        periodo_label: Optional[str] = None,
        filtros: Optional[Dict[str, Any]] = None,
        anio_referencia: int = 2026,
    ) -> Dict[str, Any]:
        raise NotImplementedError("Claude no está implementado. Configure el proveedor como 'gemini' en el panel de administración.")

    async def generate_narrative_stream(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> AsyncIterator[str]:
        raise NotImplementedError("Claude no está implementado. Configure el proveedor como 'gemini' en el panel de administración.")

    async def consult_intent(
        self,
        prompt: str,
        dataset_tipo: str,
        model_name: Optional[str] = None,
        grafico_contexto: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError("Claude no está implementado. Configure el proveedor como 'gemini' en el panel de administración.")


async def build_llm_client(db: AsyncSession, espacio_id: int) -> LLMClientBase:
    stmt = select(ConfiguracionEspacios).where(ConfiguracionEspacios.espacio_id == espacio_id)
    config = (await db.execute(stmt)).scalar_one_or_none()

    decrypted_key = None
    if config and config.encrypted_api_key:
        try:
            decrypted_key = decrypt_api_key(config.encrypted_api_key)
        except Exception as e:
            logger.warning(f"Error al desencriptar API Key de BD: {e}")

    # Fallback a settings.GEMINI_API_KEY (.env)
    if not decrypted_key:
        decrypted_key = settings.GEMINI_API_KEY

    if not decrypted_key or not decrypted_key.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falta configurar la IA: API Key inválida o inexistente.",
        )

    provider = (config.active_provider.lower() if config and config.active_provider else "gemini")
    default_model = config.default_model if (config and config.default_model) else settings.MODELO_GEMINI_POR_DEFECTO

    # Cachea la instancia del cliente con TTLCache de 5 minutos por hash de credencial
    hash_credencial = hashlib.sha256(f"{decrypted_key.strip()}:{provider}:{default_model}".encode("utf-8")).hexdigest()
    if hash_credencial in _clientes_llm_cache:
        return _clientes_llm_cache[hash_credencial]

    if provider == "claude":
        cliente = ClaudeClient(api_key=decrypted_key.strip(), default_model=default_model)
    else:
        cliente = GeminiClient(api_key=decrypted_key.strip(), default_model=default_model)

    _clientes_llm_cache[hash_credencial] = cliente
    return cliente

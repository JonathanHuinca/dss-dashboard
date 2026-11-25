import asyncio
import hashlib
import inspect
import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple
from cachetools import TTLCache
from fastapi import Depends, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security_cipher import decrypt_api_key
from app.core.validacion_red import sanitizar_error_credencial, validar_url_proveedor_ia
from app.domain.config_models import ConfiguracionEspacios, CredencialProveedorIA

logger = logging.getLogger(__name__)

# Cachés en memoria TTL
_clientes_llm_cache: TTLCache = TTLCache(maxsize=50, ttl=300)
_modelos_disponibles_cache: TTLCache = TTLCache(maxsize=10, ttl=3600)
_herramientas_gemini_cache: Dict[int, Any] = {}

# Catálogo oficial de proveedores soportados
CATALOGO_PROVEEDORES_IA: Dict[str, Dict[str, Any]] = {
    "gemini": {
        "id": "gemini",
        "nombre": "Google Gemini",
        "protocolo": "gemini",
        "default_base_url": "",
        "requires_api_key": True,
        "requires_base_url": False,
        "allows_local_http": False,
        "modelos_sugeridos": [
            "gemini-3.1-flash-lite",
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-2.0-flash",
        ],
    },
    "openai": {
        "id": "openai",
        "nombre": "OpenAI (GPT)",
        "protocolo": "openai_compat",
        "default_base_url": "https://api.openai.com/v1",
        "requires_api_key": True,
        "requires_base_url": False,
        "allows_local_http": False,
        "modelos_sugeridos": [
            "gpt-4o-mini",
            "gpt-4o",
            "gpt-4.1-mini",
            "gpt-4.1",
            "o3-mini",
        ],
    },
    "claude": {
        "id": "claude",
        "nombre": "Anthropic Claude",
        "protocolo": "anthropic",
        "default_base_url": "https://api.anthropic.com",
        "requires_api_key": True,
        "requires_base_url": False,
        "allows_local_http": False,
        "modelos_sugeridos": [
            "claude-sonnet-4-20250514",
            "claude-3-7-sonnet-latest",
            "claude-3-5-haiku-latest",
            "claude-opus-4-20250514",
        ],
    },
    "deepseek": {
        "id": "deepseek",
        "nombre": "DeepSeek",
        "protocolo": "openai_compat",
        "default_base_url": "https://api.deepseek.com",
        "requires_api_key": True,
        "requires_base_url": False,
        "allows_local_http": False,
        "modelos_sugeridos": [
            "deepseek-chat",
            "deepseek-reasoner",
        ],
    },
    "groq": {
        "id": "groq",
        "nombre": "Groq",
        "protocolo": "openai_compat",
        "default_base_url": "https://api.groq.com/openai/v1",
        "requires_api_key": True,
        "requires_base_url": False,
        "allows_local_http": False,
        "modelos_sugeridos": [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "qwen-qwq-32b",
        ],
    },
    "mistral": {
        "id": "mistral",
        "nombre": "Mistral AI",
        "protocolo": "openai_compat",
        "default_base_url": "https://api.mistral.ai/v1",
        "requires_api_key": True,
        "requires_base_url": False,
        "allows_local_http": False,
        "modelos_sugeridos": [
            "mistral-large-latest",
            "mistral-small-latest",
            "codestral-latest",
        ],
    },
    "openrouter": {
        "id": "openrouter",
        "nombre": "OpenRouter (Multi-Modelo)",
        "protocolo": "openai_compat",
        "default_base_url": "https://openrouter.ai/api/v1",
        "requires_api_key": True,
        "requires_base_url": False,
        "allows_local_http": False,
        "modelos_sugeridos": [
            "openai/gpt-4o-mini",
            "anthropic/claude-sonnet-4",
            "deepseek/deepseek-chat",
            "google/gemini-2.5-flash",
        ],
    },
    "xai": {
        "id": "xai",
        "nombre": "xAI (Grok)",
        "protocolo": "openai_compat",
        "default_base_url": "https://api.x.ai/v1",
        "requires_api_key": True,
        "requires_base_url": False,
        "allows_local_http": False,
        "modelos_sugeridos": [
            "grok-3-mini",
            "grok-3",
            "grok-2-latest",
        ],
    },
    "ollama": {
        "id": "ollama",
        "nombre": "Ollama (Local On-Premise)",
        "protocolo": "openai_compat",
        "default_base_url": "http://host.docker.internal:11434/v1",
        "requires_api_key": False,
        "requires_base_url": False,
        "allows_local_http": True,
        "modelos_sugeridos": [
            "llama3.2",
            "qwen2.5:7b",
            "mistral",
        ],
    },
    "custom": {
        "id": "custom",
        "nombre": "Otro Proveedor (Compatible OpenAI)",
        "protocolo": "openai_compat",
        "default_base_url": "",
        "requires_api_key": True,
        "requires_base_url": True,
        "allows_local_http": False,
        "modelos_sugeridos": [],
    },
}


def obtener_catalogo_proveedores() -> List[Dict[str, Any]]:
    return list(CATALOGO_PROVEEDORES_IA.values())


def limpiar_cache_clientes_llm() -> None:
    """Invalida instancias cacheadas tras cambios o eliminaciones de credenciales."""
    _clientes_llm_cache.clear()
    _modelos_disponibles_cache.clear()


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
    "3. MEMORIA CONVERSACIONAL: Cuando existan turnos previos en la conversación, utilízalos para resolver referencias como 'eso', 'ese día', 'lo anterior' o 'el gráfico anterior'; si el usuario solo pide aclarar o profundizar sobre cifras ya entregadas en el historial puedes responder directamente con ellas, y si requiere datos nuevos ejecuta la herramienta correspondiente. "
    "4. Tu tarea es seleccionar la herramienta de consulta más precisa para responder al usuario usando Function Calling. "
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
    "4. MEMORIA CONVERSACIONAL: Cuando existan turnos previos en la conversación, utilízalos para resolver referencias como 'eso', 'ese día', 'esa sala', 'lo anterior' o 'el gráfico anterior'; si el usuario solo pide aclarar o profundizar sobre cifras ya entregadas en el historial puedes responder directamente con ellas, y si requiere datos nuevos ejecuta la herramienta correspondiente. "
    "5. Tu tarea es seleccionar la herramienta de consulta más precisa para responder al usuario usando Function Calling. "
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
        history: Optional[List[Dict[str, str]]] = None,
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
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def generate_narrative_stream(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model_name: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
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


def obtener_esquema_herramientas_neutral(espacio_id: int = 1) -> List[Dict[str, Any]]:
    """Catálogo JSON Schema agnóstico al proveedor para Function Calling."""
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

    def _schema_obj(props: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": props,
            "required": ["espacio_id"],
        }

    prop_esp = {"type": "integer", "description": f"ID del espacio ({espacio_id})"}
    prop_f_ini = {"type": "string", "description": "Fecha de inicio YYYY-MM-DD (opcional)"}
    prop_f_fin = {"type": "string", "description": "Fecha de fin YYYY-MM-DD (opcional)"}

    base = [
        {
            "name": "consultar_calendario_academico",
            "description": "Consulta hechos institucionales oficiales del Calendario Académico UCT: Feriados Oficiales, Semanas de Receso, Vacaciones, Exámenes / Solemnes, Hitos de Clases, Suspensiones de Actividades, Paros y Contingencias, y régimen de Horario 24 Horas, analizando su impacto en la concurrencia.",
            "parameters": _schema_obj({
                "espacio_id": prop_esp,
                "semana": {"type": "integer", "description": "Número de semana ISO (1 al 53)"},
                "mes": {"type": "integer", "description": "Mes a consultar del 1 al 12"},
                "fecha_inicio": {"type": "string", "description": "Fecha de inicio YYYY-MM-DD"},
                "fecha_fin": {"type": "string", "description": "Fecha de fin YYYY-MM-DD"},
                "busqueda": {"type": "string", "description": "Término de búsqueda de texto (ej. 'receso', 'vacaciones', 'feriado')"},
            }),
        },
        {
            "name": "consultar_aforo_historico",
            "description": desc_aforo,
            "parameters": _schema_obj({
                "espacio_id": prop_esp,
                "fecha_inicio": prop_f_ini,
                "fecha_fin": prop_f_fin,
                "intervalo": {"type": "string", "description": "Nivel de agregación: 'horario', 'diario' o 'semanal'"},
            }),
        },
        {
            "name": "consultar_mapa_calor",
            "description": desc_mapa,
            "parameters": _schema_obj({
                "espacio_id": prop_esp,
                "mes": {"type": "integer", "description": "Mes a consultar del 1 al 12 (opcional)"},
            }),
        },
        {
            "name": "consultar_picos_flujo",
            "description": desc_picos,
            "parameters": _schema_obj({
                "espacio_id": prop_esp,
                "fecha_inicio": prop_f_ini,
                "fecha_fin": prop_f_fin,
            }),
        },
        {
            "name": "consultar_proyeccion_prophet",
            "description": desc_prophet,
            "parameters": _schema_obj({
                "espacio_id": prop_esp,
                "horizonte_dias": {"type": "integer", "description": "Días de pronóstico (7 o 14)"},
            }),
        },
        {
            "name": "consultar_kpis_actuales",
            "description": desc_kpis,
            "parameters": _schema_obj({"espacio_id": prop_esp}),
        },
        {
            "name": "consultar_evolucion_semanal",
            "description": "Consulta la evolución de afluencia o asistencia agrupada por semana ISO, comparando el impacto de hitos del calendario académico.",
            "parameters": _schema_obj({
                "espacio_id": prop_esp,
                "fecha_inicio": prop_f_ini,
                "fecha_fin": prop_f_fin,
            }),
        },
    ]

    if espacio_id == 2:
        prop_esp2 = {"type": "integer", "description": "ID del espacio (2: Estacionamiento CSF)"}
        especificas = [
            {
                "name": "consultar_flota_vehicular",
                "description": "Consulta la composición del parque automotriz por tipo de vehículo o marcas principales en Estacionamiento CSF.",
                "parameters": _schema_obj({"espacio_id": prop_esp2, "fecha_inicio": prop_f_ini, "fecha_fin": prop_f_fin}),
            },
            {
                "name": "consultar_camaras_anpr",
                "description": "Consulta la distribución de capturas y tráfico vehicular por cámara ANPR física en Estacionamiento CSF.",
                "parameters": _schema_obj({"espacio_id": prop_esp2, "fecha_inicio": prop_f_ini, "fecha_fin": prop_f_fin}),
            },
            {
                "name": "consultar_movilidad_intercampus",
                "description": "Consulta los viajes y traslados vehiculares entre Campus San Francisco y San Juan Pablo II.",
                "parameters": _schema_obj({"espacio_id": prop_esp2}),
            },
            {
                "name": "consultar_clustering_vehicular",
                "description": "Consulta los clústeres no supervisados K-Means y detección de posible uso vehicular externo.",
                "parameters": _schema_obj({"espacio_id": prop_esp2}),
            },
        ]
    else:
        prop_esp1 = {"type": "integer", "description": "ID del espacio (1: Biblioteca CSF)"}
        especificas = [
            {
                "name": "consultar_distribucion_carreras",
                "description": "Consulta la distribución y padrón de carreras y facultades con mayor asistencia a biblioteca.",
                "parameters": _schema_obj({"espacio_id": prop_esp1, "fecha_inicio": prop_f_ini, "fecha_fin": prop_f_fin}),
            },
            {
                "name": "consultar_torniquetes_accesos",
                "description": "Consulta el uso y concurrencia por torniquetes físicos y accesos universales en Biblioteca CSF.",
                "parameters": _schema_obj({"espacio_id": prop_esp1, "fecha_inicio": prop_f_ini, "fecha_fin": prop_f_fin}),
            },
            {
                "name": "consultar_comparativa_salas",
                "description": "Consulta la afluencia comparativa entre Sala 1 (CSF02 2° Piso) y Sala 2 (CSF04 Pecera).",
                "parameters": _schema_obj({"espacio_id": prop_esp1, "fecha_inicio": prop_f_ini, "fecha_fin": prop_f_fin}),
            },
            {
                "name": "consultar_perfiles_visita",
                "description": "Consulta los perfiles de visita, permanencia y tasa de rebote en biblioteca.",
                "parameters": _schema_obj({"espacio_id": prop_esp1, "fecha_inicio": prop_f_ini, "fecha_fin": prop_f_fin}),
            },
            {
                "name": "consultar_pronostico_14d",
                "description": "Consulta la proyección de demanda a 14 días con HistGradientBoosting y calendario institucional.",
                "parameters": _schema_obj({"espacio_id": prop_esp1}),
            },
            {
                "name": "consultar_campana_24h",
                "description": "Consulta el régimen de Horario 24 Horas y Campaña de Exámenes en Sala 2 Pecera CSF04, flujo nocturno según horarios_operacion configurado y aforo delta.",
                "parameters": _schema_obj({"espacio_id": prop_esp1, "fecha_inicio": prop_f_ini, "fecha_fin": prop_f_fin}),
            },
        ]

    return base + especificas


def get_gemini_tools(espacio_id: int = 1):
    if espacio_id in _herramientas_gemini_cache:
        return _herramientas_gemini_cache[espacio_id]

    from google.genai import types

    declaraciones = []
    for tool in obtener_esquema_herramientas_neutral(espacio_id):
        params = tool["parameters"]
        props_gemini = {
            k: types.Schema(type=v["type"].upper(), description=v.get("description", ""))
            for k, v in params["properties"].items()
        }
        declaraciones.append(
            types.FunctionDeclaration(
                name=tool["name"],
                description=tool["description"],
                parameters=types.Schema(
                    type="OBJECT",
                    properties=props_gemini,
                    required=params.get("required", []),
                ),
            )
        )

    tool_def = [types.Tool(function_declarations=declaraciones)]
    _herramientas_gemini_cache[espacio_id] = tool_def
    return tool_def


def obtener_herramientas_openai(espacio_id: int = 1) -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            },
        }
        for t in obtener_esquema_herramientas_neutral(espacio_id)
    ]


def obtener_herramientas_claude(espacio_id: int = 1) -> List[Dict[str, Any]]:
    return [
        {
            "name": t["name"],
            "description": t["description"],
            "input_schema": t["parameters"],
        }
        for t in obtener_esquema_herramientas_neutral(espacio_id)
    ]


def _construir_system_prompt_herramientas(
    prompt: str,
    espacio_id: int,
    grafico_contexto: Optional[str],
    fecha_inicio: Optional[str],
    fecha_fin: Optional[str],
    periodo_label: Optional[str],
    filtros: Optional[Dict[str, Any]],
    anio_referencia: int,
) -> Tuple[str, Optional[re.Match], int]:
    context_parts = []
    if grafico_contexto:
        context_parts.append(f"El usuario tiene enfocado el gráfico institucional '{grafico_contexto}'.")
    if periodo_label or fecha_inicio:
        context_parts.append(
            f"Período activo: {periodo_label or ''} (desde {fecha_inicio or 'inicio'} hasta {fecha_fin or 'actual'})."
        )
    if filtros:
        context_parts.append(f"Filtros activos en el dashboard: {json.dumps(filtros)}.")
    context_info = f" Contexto activo en pantalla: {' '.join(context_parts)}" if context_parts else ""

    match_anio_usuario = re.search(r"\b(20\d{2})\b", prompt)
    anio_objetivo = int(match_anio_usuario.group(1)) if match_anio_usuario else anio_referencia

    plantilla = PLANTILLA_SISTEMA_ESTACIONAMIENTO if espacio_id == 2 else PLANTILLA_SISTEMA_BIBLIOTECA
    system_instruction = plantilla.format(
        context_info=context_info,
        anio_referencia=anio_referencia,
        anio_objetivo=anio_objetivo,
    )
    return system_instruction, match_anio_usuario, anio_objetivo


def _normalizar_resultado_tool_call(
    tool_name: str,
    raw_args: Optional[Dict[str, Any]],
    espacio_id: int,
    fecha_inicio: Optional[str],
    fecha_fin: Optional[str],
    match_anio_usuario: Optional[re.Match],
    anio_objetivo: int,
) -> Dict[str, Any]:
    args = dict(raw_args) if raw_args else {}
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
        "tool_name": tool_name,
        "args": args,
    }


def _limpiar_json_markdown(raw_text: str) -> Dict[str, Any]:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned[7:] if cleaned.startswith("```json") else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
    return json.loads(cleaned)


def _construir_prompt_intent(
    prompt: str,
    dataset_tipo: str,
    grafico_contexto: Optional[str],
) -> str:
    context_directive = ""
    if grafico_contexto and grafico_contexto.strip():
        context_directive = (
            f"El usuario te está haciendo una pregunta específicamente sobre el gráfico o sección [{grafico_contexto.strip()}]. "
            "Basa tu análisis y respuesta principalmente en este contexto. "
        )
    return PLANTILLA_SISTEMA_INTENT.format(
        context_directive=context_directive,
        dataset_tipo=dataset_tipo,
    )


def _normalizar_historial_conversacion(history: Optional[List[Dict[str, str]]]) -> List[Dict[str, str]]:
    """Garantiza alternancia estricta user/assistant antes del turno actual."""
    if not history:
        return []
    normalizados: List[Dict[str, str]] = []
    for msg in history:
        if not isinstance(msg, dict):
            continue
        contenido = str(msg.get("content") or "").strip()
        if not contenido:
            continue
        rol_raw = str(msg.get("role") or "").strip().lower()
        rol = "assistant" if rol_raw in ("assistant", "model") else "user"
        if not normalizados and rol == "assistant":
            continue
        if normalizados and normalizados[-1]["role"] == rol:
            normalizados[-1]["content"] = f"{normalizados[-1]['content']}\n{contenido}"
        else:
            normalizados.append({"role": rol, "content": contenido})
    if normalizados and normalizados[-1]["role"] == "user":
        normalizados.pop()
    return normalizados


def _construir_contents_gemini(prompt: str, history: Optional[List[Dict[str, str]]] = None):
    hist_norm = _normalizar_historial_conversacion(history)
    if not hist_norm:
        return prompt
    from google.genai import types

    contents = [
        types.Content(
            role="model" if m["role"] == "assistant" else "user",
            parts=[types.Part.from_text(text=m["content"])],
        )
        for m in hist_norm
    ]
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=prompt)]))
    return contents


def _fallback_offline(prompt: str) -> Dict[str, Any]:
    from app.api.v1.endpoints.assistant import build_offline_response
    return {"type": "text", "text": build_offline_response(prompt)}


def es_error_reintentable(error: Exception) -> bool:
    code = getattr(error, "code", None) or getattr(error, "status_code", None)
    if code is None and hasattr(error, "response") and getattr(error, "response") is not None:
        code = getattr(error.response, "status_code", None)
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
                "Tiempo de espera agotado (%ss) en llamada a LLM (intento %s/%s).",
                tiempo_espera,
                intento + 1,
                max_reintentos,
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
                    "Error reintentable LLM en intento %s/%s. Reintentando en %ss...",
                    intento + 1,
                    max_reintentos,
                    demora,
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
        logger.warning("Error consultando client.models.list(): %s. Usando fallback.", sanitizar_error_credencial(e))

    fallback = [
        settings.MODELO_GEMINI_POR_DEFECTO,
        "gemini-3.1-flash-lite",
        "gemini-3.1-flash-lite-preview",
        "gemini-3.5-flash-lite",
        "gemini-3.8-flash",
        "gemini-3-flash-preview",
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
        if chosen_model in ["gemini-1.5-flash", "gemini-3.5-flash", "gemini-3.6-flash"]:
            chosen_model = settings.MODELO_GEMINI_POR_DEFECTO
        modelos_disponibles = listar_modelos_disponibles(self.client)
        if chosen_model in modelos_disponibles:
            return chosen_model
        logger.warning("Modelo '%s' no disponible. Usando fallback %s.", chosen_model, settings.MODELO_GEMINI_POR_DEFECTO)
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
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        from google.genai import types

        effective_model = self._resolve_model(model_name)
        tools = get_gemini_tools(espacio_id)
        system_instruction, match_anio_usuario, anio_objetivo = _construir_system_prompt_herramientas(
            prompt, espacio_id, grafico_contexto, fecha_inicio, fecha_fin, periodo_label, filtros, anio_referencia
        )

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=tools,
            temperature=0.1,
        )

        modelos_candidatos = list(dict.fromkeys([
            effective_model,
            settings.MODELO_GEMINI_POR_DEFECTO,
            "gemini-3.1-flash-lite",
            "gemini-3.1-flash-lite-preview",
            "gemini-3.5-flash-lite",
            "gemini-3.8-flash",
            "gemini-3-flash-preview",
        ]))

        gemini_contents = _construir_contents_gemini(prompt, history)
        res = None
        for mod_cand in modelos_candidatos:
            if not mod_cand:
                continue
            try:
                async def _llamar(m=mod_cand):
                    return await self.client.aio.models.generate_content(
                        model=m,
                        contents=gemini_contents,
                        config=config,
                    )
                res = await ejecutar_con_reintentos_y_tiempo_espera(_llamar)
                if res:
                    break
            except Exception as e_mod:
                logger.warning("Error Gemini analyze_query_with_tools (%s): %s", mod_cand, sanitizar_error_credencial(e_mod, self.api_key))

        try:
            if res and res.function_calls:
                call = res.function_calls[0]
                return _normalizar_resultado_tool_call(
                    call.name, call.args, espacio_id, fecha_inicio, fecha_fin, match_anio_usuario, anio_objetivo
                )
            text_resp = res.text if res else None
            if text_resp:
                return {"type": "text", "text": text_resp}
            return _fallback_offline(prompt)
        except Exception as e:
            logger.error("Error procesando resultado Gemini: %s", sanitizar_error_credencial(e, self.api_key))
            return _fallback_offline(prompt)

    async def generate_narrative_stream(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model_name: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncIterator[str]:
        from google.genai import types

        effective_model = self._resolve_model(model_name)
        config = types.GenerateContentConfig(system_instruction=system_instruction, temperature=0.2)
        candidatos_stream = list(dict.fromkeys([
            effective_model,
            settings.MODELO_GEMINI_POR_DEFECTO,
            "gemini-3.1-flash-lite",
            "gemini-3.1-flash-lite-preview",
            "gemini-3.5-flash-lite",
            "gemini-3.8-flash",
            "gemini-3-flash-preview",
        ]))

        gemini_contents = _construir_contents_gemini(prompt, history)
        chunks_yielded = 0
        stream_exitoso = False

        for mod_stream in candidatos_stream:
            if not mod_stream:
                continue
            try:
                res = self.client.aio.models.generate_content_stream(
                    model=mod_stream,
                    contents=gemini_contents,
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
                logger.warning("Error Gemini stream (%s): %s", mod_stream, sanitizar_error_credencial(e, self.api_key))
                if chunks_yielded > 0:
                    yield " (Consulta completada de forma parcial por interrupción del servicio)."
                    return

        if not stream_exitoso and chunks_yielded == 0:
            yield _fallback_offline(prompt)["text"]

    async def generate_response(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
        response_mime_type: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Optional[str]:
        from google.genai import types

        effective_model = self._resolve_model(model)
        config = types.GenerateContentConfig(temperature=temperature)
        if system_instruction:
            config.system_instruction = system_instruction
        if response_mime_type:
            config.response_mime_type = response_mime_type

        candidatos_resp = list(dict.fromkeys([
            effective_model,
            settings.MODELO_GEMINI_POR_DEFECTO,
            "gemini-3.1-flash-lite",
            "gemini-3.1-flash-lite-preview",
            "gemini-3.5-flash-lite",
            "gemini-3.8-flash",
            "gemini-3-flash-preview",
        ]))

        gemini_contents = _construir_contents_gemini(prompt, history)
        for mod_resp in candidatos_resp:
            if not mod_resp:
                continue
            try:
                async def _llamar(m=mod_resp):
                    return await self.client.aio.models.generate_content(
                        model=m,
                        contents=gemini_contents,
                        config=config,
                    )
                res = await ejecutar_con_reintentos_y_tiempo_espera(_llamar)
                if res and res.text:
                    return res.text
            except Exception as e:
                logger.warning("Error Gemini generate_response (%s): %s", mod_resp, sanitizar_error_credencial(e, self.api_key))

        return _fallback_offline(prompt)["text"]

    async def consult_intent(
        self,
        prompt: str,
        dataset_tipo: str,
        model_name: Optional[str] = None,
        grafico_contexto: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        sys_prompt = _construir_prompt_intent(prompt, dataset_tipo, grafico_contexto)
        try:
            raw_text = await self.generate_response(
                prompt=prompt,
                system_instruction=sys_prompt,
                model=model_name or self.default_model,
                temperature=0.1,
                response_mime_type="application/json",
            )
            return _limpiar_json_markdown(raw_text) if raw_text else None
        except Exception as e:
            logger.error("Error consultando intent con Gemini: %s", sanitizar_error_credencial(e, self.api_key))
            return None


class ClaudeClient(LLMClientBase):
    """Adaptador nativo para Anthropic Claude Messages API vía httpx."""

    def __init__(self, api_key: str, default_model: str = "claude-sonnet-4-20250514", base_url: Optional[str] = None):
        self.api_key = api_key
        self.default_model = default_model or "claude-sonnet-4-20250514"
        self.base_url = (base_url or "https://api.anthropic.com").rstrip("/")

    def _resolver_modelo(self, model: Optional[str] = None) -> str:
        # Evita sobrescribir Claude con el modelo Gemini por defecto del front/ChatRequest
        if not model or not model.strip() or model.strip().lower().startswith("gemini-"):
            return self.default_model
        return model.strip()

    def _headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    async def _post_messages(self, payload: Dict[str, Any], timeout_seg: Optional[float] = None) -> Dict[str, Any]:
        import httpx

        timeout = timeout_seg or float(getattr(settings, "TIEMPO_ESPERA_LLM_SEGUNDOS", 20))
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{self.base_url}/v1/messages",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

    async def generate_response(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
        response_mime_type: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Optional[str]:
        hist_norm = _normalizar_historial_conversacion(history)
        payload: Dict[str, Any] = {
            "model": self._resolver_modelo(model),
            "max_tokens": 1536,
            "temperature": temperature,
            "messages": hist_norm + [{"role": "user", "content": prompt}],
        }
        if system_instruction:
            payload["system"] = system_instruction

        try:
            data = await ejecutar_con_reintentos_y_tiempo_espera(lambda: self._post_messages(payload))
            textos = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
            return "".join(textos) or _fallback_offline(prompt)["text"]
        except Exception as e:
            logger.warning("Error Claude generate_response: %s", sanitizar_error_credencial(e, self.api_key))
            return _fallback_offline(prompt)["text"]

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
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        system_instruction, match_anio_usuario, anio_objetivo = _construir_system_prompt_herramientas(
            prompt, espacio_id, grafico_contexto, fecha_inicio, fecha_fin, periodo_label, filtros, anio_referencia
        )
        hist_norm = _normalizar_historial_conversacion(history)
        payload = {
            "model": self._resolver_modelo(model_name),
            "max_tokens": 1024,
            "temperature": 0.1,
            "system": system_instruction,
            "tools": obtener_herramientas_claude(espacio_id),
            "messages": hist_norm + [{"role": "user", "content": prompt}],
        }
        try:
            data = await ejecutar_con_reintentos_y_tiempo_espera(lambda: self._post_messages(payload))
            content_blocks = data.get("content", [])
            for block in content_blocks:
                if block.get("type") == "tool_use":
                    return _normalizar_resultado_tool_call(
                        block.get("name", ""),
                        block.get("input"),
                        espacio_id,
                        fecha_inicio,
                        fecha_fin,
                        match_anio_usuario,
                        anio_objetivo,
                    )
            textos = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
            texto = "".join(textos).strip()
            return {"type": "text", "text": texto} if texto else _fallback_offline(prompt)
        except Exception as e:
            logger.warning("Error Claude analyze_query_with_tools: %s", sanitizar_error_credencial(e, self.api_key))
            return _fallback_offline(prompt)

    async def generate_narrative_stream(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model_name: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncIterator[str]:
        import httpx

        hist_norm = _normalizar_historial_conversacion(history)
        payload: Dict[str, Any] = {
            "model": self._resolver_modelo(model_name),
            "max_tokens": 1536,
            "temperature": 0.2,
            "stream": True,
            "messages": hist_norm + [{"role": "user", "content": prompt}],
        }
        if system_instruction:
            payload["system"] = system_instruction

        chunks_yielded = 0
        timeout = float(getattr(settings, "TIEMPO_ESPERA_LLM_SEGUNDOS", 20))
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", f"{self.base_url}/v1/messages", headers=self._headers(), json=payload) as resp:
                    resp.raise_for_status()
                    async for linea in resp.aiter_lines():
                        if not linea or not linea.startswith("data:"):
                            continue
                        raw_json = linea[5:].strip()
                        if not raw_json or raw_json == "[DONE]":
                            continue
                        try:
                            evento = json.loads(raw_json)
                        except json.JSONDecodeError:
                            continue
                        if evento.get("type") == "content_block_delta":
                            delta = evento.get("delta", {})
                            if delta.get("type") == "text_delta" and delta.get("text"):
                                chunks_yielded += 1
                                yield delta["text"]
        except Exception as e:
            logger.warning("Error Claude stream: %s", sanitizar_error_credencial(e, self.api_key))
            if chunks_yielded > 0:
                yield " (Consulta completada de forma parcial por interrupción del servicio)."
                return

        if chunks_yielded == 0:
            yield _fallback_offline(prompt)["text"]

    async def consult_intent(
        self,
        prompt: str,
        dataset_tipo: str,
        model_name: Optional[str] = None,
        grafico_contexto: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        sys_prompt = _construir_prompt_intent(prompt, dataset_tipo, grafico_contexto)
        try:
            raw_text = await self.generate_response(
                prompt=prompt,
                system_instruction=sys_prompt,
                model=self._resolver_modelo(model_name),
                temperature=0.1,
            )
            return _limpiar_json_markdown(raw_text) if raw_text else None
        except Exception as e:
            logger.error("Error consultando intent con Claude: %s", sanitizar_error_credencial(e, self.api_key))
            return None


class OpenAICompatibleClient(LLMClientBase):
    """Adaptador unificado para OpenAI GPT, DeepSeek, Groq, Mistral, OpenRouter, xAI, Ollama y Custom."""

    def __init__(
        self,
        api_key: str,
        default_model: str,
        base_url: str,
        provider_id: str = "openai",
    ):
        self.api_key = (api_key or "").strip()
        self.default_model = default_model
        self.base_url = base_url.rstrip("/")
        self.provider_id = provider_id

    def _resolver_modelo(self, model: Optional[str] = None) -> str:
        # Impide enviar gemini-3.1-flash-lite heredado cuando el proveedor activo no es OpenRouter
        if not model or not model.strip():
            return self.default_model
        limpio = model.strip()
        if limpio == "gemini-3.1-flash-lite" and self.provider_id != "openrouter":
            return self.default_model
        return limpio

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def _post_completions(self, payload: Dict[str, Any], timeout_seg: Optional[float] = None) -> Dict[str, Any]:
        import httpx

        timeout = timeout_seg or float(getattr(settings, "TIEMPO_ESPERA_LLM_SEGUNDOS", 20))
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

    async def generate_response(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
        response_mime_type: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Optional[str]:
        mensajes = []
        if system_instruction:
            mensajes.append({"role": "system", "content": system_instruction})
        mensajes.extend(_normalizar_historial_conversacion(history))
        mensajes.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": self._resolver_modelo(model),
            "messages": mensajes,
            "temperature": temperature,
        }
        if response_mime_type == "application/json":
            payload["response_format"] = {"type": "json_object"}

        try:
            data = await ejecutar_con_reintentos_y_tiempo_espera(lambda: self._post_completions(payload))
            content = data.get("choices", [{}])[0].get("message", {}).get("content")
            return content or _fallback_offline(prompt)["text"]
        except Exception as e:
            # Algunos endpoints compatibles no soportan response_format json_object; reintenta sin él
            if "response_format" in payload:
                payload.pop("response_format", None)
                try:
                    data = await ejecutar_con_reintentos_y_tiempo_espera(lambda: self._post_completions(payload))
                    content = data.get("choices", [{}])[0].get("message", {}).get("content")
                    if content:
                        return content
                except Exception as e2:
                    e = e2
            logger.warning(
                "Error %s generate_response: %s",
                self.provider_id,
                sanitizar_error_credencial(e, self.api_key),
            )
            return _fallback_offline(prompt)["text"]

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
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        system_instruction, match_anio_usuario, anio_objetivo = _construir_system_prompt_herramientas(
            prompt, espacio_id, grafico_contexto, fecha_inicio, fecha_fin, periodo_label, filtros, anio_referencia
        )
        hist_norm = _normalizar_historial_conversacion(history)
        payload: Dict[str, Any] = {
            "model": self._resolver_modelo(model_name),
            "messages": [
                {"role": "system", "content": system_instruction},
                *hist_norm,
                {"role": "user", "content": prompt},
            ],
            "tools": obtener_herramientas_openai(espacio_id),
            "tool_choice": "auto",
            "temperature": 0.1,
        }

        try:
            data = await ejecutar_con_reintentos_y_tiempo_espera(lambda: self._post_completions(payload))
            mensaje = data.get("choices", [{}])[0].get("message", {})
            tool_calls = mensaje.get("tool_calls") or []
            if tool_calls:
                fn = tool_calls[0].get("function", {})
                raw_args = fn.get("arguments", "{}")
                parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                return _normalizar_resultado_tool_call(
                    fn.get("name", ""),
                    parsed_args,
                    espacio_id,
                    fecha_inicio,
                    fecha_fin,
                    match_anio_usuario,
                    anio_objetivo,
                )
            texto = (mensaje.get("content") or "").strip()
            return {"type": "text", "text": texto} if texto else _fallback_offline(prompt)
        except Exception as e:
            logger.warning(
                "Error %s analyze_query_with_tools: %s",
                self.provider_id,
                sanitizar_error_credencial(e, self.api_key),
            )
            return _fallback_offline(prompt)

    async def generate_narrative_stream(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model_name: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncIterator[str]:
        import httpx

        mensajes = []
        if system_instruction:
            mensajes.append({"role": "system", "content": system_instruction})
        mensajes.extend(_normalizar_historial_conversacion(history))
        mensajes.append({"role": "user", "content": prompt})

        payload = {
            "model": self._resolver_modelo(model_name),
            "messages": mensajes,
            "temperature": 0.2,
            "stream": True,
        }

        chunks_yielded = 0
        timeout = float(getattr(settings, "TIEMPO_ESPERA_LLM_SEGUNDOS", 20))
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", f"{self.base_url}/chat/completions", headers=self._headers(), json=payload) as resp:
                    resp.raise_for_status()
                    async for linea in resp.aiter_lines():
                        if not linea or not linea.startswith("data:"):
                            continue
                        raw_json = linea[5:].strip()
                        if not raw_json or raw_json == "[DONE]":
                            continue
                        try:
                            evento = json.loads(raw_json)
                        except json.JSONDecodeError:
                            continue
                        choices = evento.get("choices") or []
                        if choices:
                            delta_txt = choices[0].get("delta", {}).get("content")
                            if delta_txt:
                                chunks_yielded += 1
                                yield delta_txt
        except Exception as e:
            logger.warning("Error %s stream: %s", self.provider_id, sanitizar_error_credencial(e, self.api_key))
            if chunks_yielded > 0:
                yield " (Consulta completada de forma parcial por interrupción del servicio)."
                return

        if chunks_yielded == 0:
            yield _fallback_offline(prompt)["text"]

    async def consult_intent(
        self,
        prompt: str,
        dataset_tipo: str,
        model_name: Optional[str] = None,
        grafico_contexto: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        sys_prompt = _construir_prompt_intent(prompt, dataset_tipo, grafico_contexto)
        try:
            raw_text = await self.generate_response(
                prompt=prompt,
                system_instruction=sys_prompt,
                model=self._resolver_modelo(model_name),
                temperature=0.1,
                response_mime_type="application/json",
            )
            return _limpiar_json_markdown(raw_text) if raw_text else None
        except Exception as e:
            logger.error("Error consultando intent con %s: %s", self.provider_id, sanitizar_error_credencial(e, self.api_key))
            return None


def crear_cliente_llm(
    provider_id: str,
    api_key: str,
    default_model: str,
    base_url: Optional[str] = None,
) -> LLMClientBase:
    pid = (provider_id or "gemini").strip().lower()
    meta = CATALOGO_PROVEEDORES_IA.get(pid)
    if not meta:
        raise ValueError(f"Proveedor de IA '{pid}' no soportado.")

    protocolo = meta["protocolo"]
    if protocolo == "gemini":
        return GeminiClient(api_key=api_key, default_model=default_model)

    url_efectiva = (base_url or meta.get("default_base_url") or "").strip()
    url_validada = validar_url_proveedor_ia(url_efectiva, permitir_local=bool(meta.get("allows_local_http")))

    if protocolo == "anthropic":
        return ClaudeClient(api_key=api_key, default_model=default_model, base_url=url_validada)

    return OpenAICompatibleClient(
        api_key=api_key,
        default_model=default_model,
        base_url=url_validada,
        provider_id=pid,
    )


async def probar_cliente_llm(
    provider_id: str,
    api_key: str,
    modelo: str,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Ejecuta una llamada real mínima para verificar conectividad y credenciales sin fallback offline."""
    inicio = time.perf_counter()
    pid = (provider_id or "gemini").strip().lower()
    secreto = (api_key or "").strip()
    try:
        cliente = crear_cliente_llm(pid, secreto, modelo, base_url)
        if isinstance(cliente, GeminiClient):
            from google.genai import types
            res = await asyncio.wait_for(
                cliente.client.aio.models.generate_content(
                    model=modelo,
                    contents="Responde únicamente: OK",
                    config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=10),
                ),
                timeout=15.0,
            )
            ok = bool(res and getattr(res, "text", None))
            msg = "Conexión verificada correctamente con Google Gemini." if ok else "El modelo no devolvió contenido."
        elif isinstance(cliente, ClaudeClient):
            data = await cliente._post_messages(
                {
                    "model": modelo,
                    "max_tokens": 16,
                    "temperature": 0.0,
                    "messages": [{"role": "user", "content": "Responde únicamente: OK"}],
                },
                timeout_seg=15.0,
            )
            ok = bool(data.get("content"))
            msg = "Conexión verificada correctamente con Anthropic Claude." if ok else "Respuesta vacía del proveedor."
        else:
            data = await cliente._post_completions(
                {
                    "model": modelo,
                    "max_tokens": 16,
                    "temperature": 0.0,
                    "messages": [{"role": "user", "content": "Responde únicamente: OK"}],
                },
                timeout_seg=15.0,
            )
            ok = bool(data.get("choices"))
            msg = f"Conexión verificada correctamente con {CATALOGO_PROVEEDORES_IA[pid]['nombre']}." if ok else "Respuesta vacía del proveedor."

        latencia_ms = round((time.perf_counter() - inicio) * 1000.0, 2)
        return {
            "ok": ok,
            "latencia_ms": latencia_ms,
            "mensaje": msg,
            "provider_id": pid,
            "modelo": modelo,
        }
    except Exception as exc:
        latencia_ms = round((time.perf_counter() - inicio) * 1000.0, 2)
        detalle = sanitizar_error_credencial(exc, secreto)
        return {
            "ok": False,
            "latencia_ms": latencia_ms,
            "mensaje": f"Error de conexión con el proveedor: {detalle}",
            "provider_id": pid,
            "modelo": modelo,
        }


async def build_llm_client(db: AsyncSession, espacio_id: int) -> LLMClientBase:
    # 1. Prioridad: credencial activa en el gestor multi-proveedor
    cred_activa = None
    try:
        stmt_cred = (
            select(CredencialProveedorIA)
            .where(CredencialProveedorIA.es_activa == True)
            .order_by(desc(CredencialProveedorIA.updated_at), desc(CredencialProveedorIA.id))
            .limit(1)
        )
        cred_activa = (await db.execute(stmt_cred)).scalar_one_or_none()
    except Exception as e:
        logger.debug("Consulta de credenciales_proveedores_ia omitida: %s", sanitizar_error_credencial(e))

    if cred_activa:
        pid = cred_activa.provider_id.strip().lower()
        meta = CATALOGO_PROVEEDORES_IA.get(pid, {})
        decrypted = ""
        if cred_activa.encrypted_api_key:
            try:
                decrypted = decrypt_api_key(cred_activa.encrypted_api_key).strip()
            except Exception as e:
                logger.warning("Error al desencriptar credencial IA id=%s: %s", cred_activa.id, sanitizar_error_credencial(e))

        if meta.get("requires_api_key", True) and not decrypted:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="La credencial de IA activa no posee una API Key válida.",
            )

        base_url = cred_activa.base_url or meta.get("default_base_url") or ""
        hash_cred = hashlib.sha256(f"{decrypted}:{pid}:{cred_activa.modelo}:{base_url}".encode("utf-8")).hexdigest()
        if hash_cred in _clientes_llm_cache:
            return _clientes_llm_cache[hash_cred]

        cliente = crear_cliente_llm(pid, decrypted, cred_activa.modelo, base_url or None)
        _clientes_llm_cache[hash_cred] = cliente
        return cliente

    # 2. Respaldo legado en ConfiguracionEspacios (evitando usar credenciales ANPR que llevan ':')
    stmt = select(ConfiguracionEspacios).where(ConfiguracionEspacios.espacio_id == espacio_id)
    config = (await db.execute(stmt)).scalar_one_or_none()

    decrypted_key = None
    if config and config.encrypted_api_key:
        try:
            candidato = decrypt_api_key(config.encrypted_api_key)
            if candidato and ":" not in candidato:
                decrypted_key = candidato
        except Exception as e:
            logger.warning("Error al desencriptar API Key de BD: %s", sanitizar_error_credencial(e))

    # 3. Respaldo final en .env
    if not decrypted_key:
        decrypted_key = settings.GEMINI_API_KEY

    if not decrypted_key or not decrypted_key.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falta configurar la IA: API Key inválida o inexistente.",
        )

    provider = config.active_provider.lower() if (config and config.active_provider) else "gemini"
    default_model = config.default_model if (config and config.default_model) else settings.MODELO_GEMINI_POR_DEFECTO
    if provider not in CATALOGO_PROVEEDORES_IA:
        provider = "gemini"

    hash_credencial = hashlib.sha256(f"{decrypted_key.strip()}:{provider}:{default_model}".encode("utf-8")).hexdigest()
    if hash_credencial in _clientes_llm_cache:
        return _clientes_llm_cache[hash_credencial]

    cliente = crear_cliente_llm(provider, decrypted_key.strip(), default_model)
    _clientes_llm_cache[hash_credencial] = cliente
    return cliente

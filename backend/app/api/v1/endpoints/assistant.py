import os
from typing import Any, List, Optional, Tuple
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.database import get_db
from app.core.security import require_permission
from app.core.validacion_red import sanitizar_error_credencial
from app.api.v1.endpoints.config import check_ia_active

router = APIRouter(dependencies=[Depends(check_ia_active)])

SYSTEM_PROMPT = """Eres el Asistente Analitico Inteligente del Sistema de Soporte a Decisiones (DSS) de la Universidad Catolica de Temuco (Campus San Francisco - CSF).
Tu funcion es responder consultas analiticas en lenguaje natural acerca de la afluencia, ocupacion, perfiles de permanencia, flujos vehiculares y correlacion con el calendario academico basandote estrictamente en los datos del sistema.

NORMAS DE PRIVACIDAD Y SEGURIDAD OBLIGATORIAS:
1. Queda estrictamente PROHIBIDO exponer identificadores personales, nombres, correos electronicos, identificadores de base de datos internos (IDs) o hashes anonimizados (HMAC/SHA-256).
2. Si el usuario solicita datos a nivel individual o llaves hash, debes declinar de forma cortes indicando que el sistema resguarda la privacidad segun normativas de anonimizacion irreversible.
3. Responde siempre con un tono profesional, ejecutivo y fundamentado en estadisticas agregadas.

ESQUEMA DE TABLAS DISPONIBLES:
1. aforo_horario_biblioteca:
   - bucket (TIMESTAMP): Marca temporal truncada a nivel horario.
   - espacio_id (INTEGER): Recinto (1 = Biblioteca Campus San Francisco).
   - ingresos (BIGINT): Accesos validados en la hora.
   - salidas (BIGINT): Salidas validadas en la hora.
   - personas_unicas (BIGINT): Cantidad de usuarios unicos en el intervalo.
   - permanencia_mediana_min (DOUBLE PRECISION): Mediana de permanencia en minutos.

2. aforo_horario_estacionamiento:
   - bucket (TIMESTAMP): Intervalo temporal por hora.
   - espacio_id (INTEGER): Recinto (2 = Estacionamiento Campus San Francisco).
   - camara (VARCHAR): Identificador de camara ANPR (CAM-ACCESO-NORTE, CAM-ACCESO-SUR, etc.).
   - entradas (BIGINT): Conteo de vehiculos que ingresaron.
   - salidas (BIGINT): Conteo de vehiculos que egresaron.
   - lecturas_fallidas (BIGINT): Registros con error optico o patente ilegible.

3. calendario_academico:
   - fecha (DATE): Fecha del ano academico 2026.
   - is_holiday (BOOLEAN): Feriado oficial nacional o regional.
   - is_break (BOOLEAN): Receso estudiantil o de invierno.
   - is_exam_period (BOOLEAN): Periodo de certamenes y evaluaciones solemnes.
   - is_class_milestone (BOOLEAN): Hito de clases (inicio/cierre de semestre).
   - suspension_actividades (BOOLEAN): Suspension extraordinaria.
   - descripcion (TEXT): Detalle o glosa del evento universitario.

METRICAS ANALITICAS GENERALES (CAMPUS SAN FRANCISCO 2026):
- Total ingresos analizados Biblioteca: 24.430 registros en 128 jornadas.
- Semana de maxima afluencia historica: Semana ISO 2026-16 con 2.097 ingresos registrados.
- Impacto de certamenes: Durante semanas con is_exam_period = True el promedio diario es de 321 ingresos/dia, en comparacion a ~70 ingresos/dia en semanas regulares sin evaluaciones (un aumento superior al 350%).
- Recesos estudiantiles (is_break = True): Reduccion drastica del aforo diario a menos de 15 personas/dia.
- Franja horaria de mayor afluencia y concurrencia: 10:00 - 13:00 hrs (promedio 120-150 usuarios concurrentes) y 15:00 - 17:00 hrs.
- Distribucion de perfiles de permanencia: Visitas cortas (<60m) representan el 39.87%, medias (60-180m) el 37.23% y largas (>180m) el 22.90%.
- Capacidad maxima de diseno Biblioteca CSF: 200 cupos simultaneos.
"""

from dotenv import dotenv_values

SUPPORTED_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-3-flash-preview",
]

class ChatMessage(BaseModel):
    role: str
    content: str

class AssistantRequest(BaseModel):
    message: Optional[str] = None
    question: Optional[str] = None
    model: str = "gemini-3.1-flash-lite"
    history: Optional[List[ChatMessage]] = None

class AssistantResponse(BaseModel):
    reply: str
    model_requested: str
    model_used: str
    success: bool
    live_llm: bool
    error: Optional[str] = None

def get_gemini_api_key() -> str:
    return settings.GEMINI_API_KEY.strip()

_REGLAS_OFFLINE = [
    (
        lambda s: ("qu" in s or "de que" in s or "origen" in s or "explic" in s) and ("dato" in s or "informaci" in s or "registro" in s),
        (
            "Estos datos corresponden a los registros consolidados de afluencia, ocupación y movilidad del Sistema DSS de Campus San Francisco (UCT). "
            "Incluyen el registro de ingresos peatonales por los 4 torniquetes de acceso en Biblioteca (Salas CSF02 y Sala 2 Pecera CSF04), "
            "así como el control de acceso vehicular por cámaras ANPR en estacionamientos Norte y Sur. "
            "Toda la información se encuentra seudonimizada bajo estándar HMAC/SHA-256 (conforme a Ley N° 21.719) y está correlacionada directamente "
            "con los hitos del Calendario Académico institucional (certámenes, exámenes, recesos, feriados, suspensiones y campaña de horario 24 horas)."
        ),
    ),
    (
        lambda s: "semana" in s and ("congesti" in s or "mayor" in s or "afluencia" in s or "pico" in s),
        (
            "Segun el registro historico de la tabla aforo_horario_biblioteca, la semana con mayor volumen de "
            "congestion y afluencia corresponde a la Semana ISO 2026-16, con un total acumulado de 2.097 ingresos. "
            "Esta concentracion coincidio directamente con el primer periodo solemne de certamenes registrado en la tabla calendario_academico."
        ),
    ),
    (
        lambda s: "examen" in s or "certamen" in s or "impactan" in s or "impacto" in s,
        (
            "El cruce entre aforo_horario_biblioteca y calendario_academico demuestra un impacto significativo: "
            "en jornadas donde is_exam_period es verdadero, el aforo promedio alcanza 321 ingresos diarios, "
            "mientras que en jornadas lectivas regulares sin evaluaciones promedia aproximadamente 70 ingresos diarios. "
            "Esto representa un incremento de afluencia superior al 350% durante certamenes solemnes."
        ),
    ),
    (
        lambda s: "permanencia" in s or "perfil" in s,
        (
            "La clasificacion de perfiles de permanencia registra: Visitas Cortas (<60m) con un 39.87%, "
            "Visitas Medias (60 a 180m) con un 37.23% y Visitas de Estudio Extenso (>180m) con un 22.90%, "
            "concentrandose las estancias largas en el segundo piso del recinto."
        ),
    ),
    (
        lambda s: "paro" in s or "contingencia" in s,
        (
            "En los registros de contingencias académicas de Campus San Francisco se registra el Paro General Estudiantil FEUCT "
            "(01 al 29 de septiembre de 2026) y suspensiones de salas, las cuales redujeron la concurrencia a niveles mínimos operativos."
        ),
    ),
    (
        lambda s: "24" in s and ("hora" in s or "nocturn" in s or "pecera" in s),
        (
            "La Campaña 24 Horas habilita la Sala 2 Pecera (CSF04, 126 asientos) "
            "con extensión nocturna de Lunes a Jueves (20:30 a 07:00 hrs) y Viernes (20:30 a 06:00 hrs) durante períodos de campaña."
        ),
    ),
    (
        lambda s: "receso" in s or "vacacion" in s or "feriado" in s or "suspensi" in s,
        (
            "El Calendario Académico UCT contempla Semanas de Receso Estudiantil, Períodos de Vacaciones y Feriados Oficiales "
            "con suspensión de actividades docentes y administrativas, reduciendo la concurrencia en recintos a mínimos operativos."
        ),
    ),
    (
        lambda s: "estacionamiento" in s or "vehicul" in s or "camara" in s,
        (
            "En la tabla aforo_horario_estacionamiento, las horas de maxima saturacion vehicular se registran entre "
            "las 07:45 y 09:15 hrs en los accesos norte y sur, con una segunda oleada de egresos entre 17:30 y 19:00 hrs."
        ),
    ),
]

_RESPUESTA_DEFAULT_OFFLINE = (
    "El DSS de Campus San Francisco cuenta con 24.430 ingresos consolidados en Biblioteca y monitoreo continuo de flujo vehicular. "
    "Los principales factores de variabilidad son los hitos del calendario academico (certamenes elevan el aforo a 321 usuarios/dia y recesos disminuyen a minimos operativos). "
    "Las horas de máxima afluencia se concentran entre 10:00 - 13:00 y 15:00 - 17:00 hrs."
)


def build_offline_response(prompt_text: str) -> str:
    """Retorna una respuesta contextual basada en reglas heurísticas institucionales precalculadas."""
    lower = prompt_text.lower()
    for predicado, respuesta in _REGLAS_OFFLINE:
        if predicado(lower):
            return respuesta
    return _RESPUESTA_DEFAULT_OFFLINE


def _ejecutar_generacion_gemini(client, candidate_models: List[str], contents: list, config: Any) -> Tuple[str, str, Optional[Exception]]:
    """Itera los modelos candidatos de Gemini hasta obtener respuesta o agotar fallbacks."""
    last_exception = None
    for candidate in candidate_models:
        try:
            response = client.models.generate_content(
                model=candidate,
                contents=contents,
                config=config,
            )
            return response.text or "", candidate, None
        except Exception as exc:
            last_exception = exc
    return "", candidate_models[0] if candidate_models else "gemini-3.1-flash-lite", last_exception

@router.get("/models")
async def list_available_models():
    return {
        "models": [
            {
                "id": "gemini-3.1-flash-lite",
                "name": "Gemini 3.1 Flash Lite (Recomendado)",
                "description": "Alta velocidad y cuota diaria amplia (500 consultas/día)",
            },
            {
                "id": "gemini-3.5-flash-lite",
                "name": "Gemini 3.5 Flash Lite",
                "description": "Alternativa de alta cuota y baja latencia",
            },
        ],
        "default": "gemini-3.1-flash-lite",
    }

@router.post("/query", response_model=AssistantResponse)
@router.post("/chat", response_model=AssistantResponse)
async def query_assistant(
    req: AssistantRequest,
    current_user=Depends(require_permission("can_use_ai")),
    db: AsyncSession = Depends(get_db),
):
    from app.services.llm_client import build_llm_client

    user_msg = (req.message or req.question or "").strip()
    if not user_msg:
        raise HTTPException(status_code=400, detail="Debe proporcionar un mensaje o pregunta")

    selected_model = req.model if req.model in SUPPORTED_MODELS else "gemini-3.1-flash-lite"

    try:
        llm_client = await build_llm_client(db, espacio_id=1)
        historial_txt = ""
        if req.history:
            lineas = [f"{'Usuario' if h.role == 'user' else 'Asistente'}: {h.content}" for h in req.history[-6:]]
            historial_txt = "\nContexto reciente:\n" + "\n".join(lineas) + "\n\n"

        modelo_activo = getattr(llm_client, "default_model", selected_model) or selected_model
        generated_text = await llm_client.generate_response(
            prompt=f"{historial_txt}Consulta actual: {user_msg}",
            system_instruction=SYSTEM_PROMPT,
            model=modelo_activo,
            temperature=0.2,
        )

        if not generated_text:
            fallback_text = build_offline_response(user_msg)
            return AssistantResponse(
                reply=fallback_text,
                model_requested=selected_model,
                model_used="local-analytics",
                success=True,
                live_llm=False,
                error=None,
            )

        return AssistantResponse(
            reply=generated_text,
            model_requested=selected_model,
            model_used=modelo_activo,
            success=True,
            live_llm=True,
        )

    except HTTPException:
        fallback_reply = build_offline_response(user_msg)
        return AssistantResponse(
            reply=fallback_reply,
            model_requested=selected_model,
            model_used="local-analytics",
            success=True,
            live_llm=False,
            error="Proveedor de IA no configurado. Respondiendo mediante base analítica local del DSS.",
        )
    except Exception as exc:
        fallback_text = build_offline_response(user_msg)
        return AssistantResponse(
            reply=fallback_text,
            model_requested=selected_model,
            model_used="local-analytics",
            success=True,
            live_llm=False,
            error=sanitizar_error_credencial(exc),
        )

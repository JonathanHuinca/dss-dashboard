import os
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.core.config import settings

router = APIRouter()

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
- Franja horaria de mayor congestion (Pico): 10:00 - 13:00 hrs (promedio 120-150 usuarios concurrentes) y 15:00 - 17:00 hrs.
- Distribucion de perfiles de permanencia: Visitas cortas (<60m) representan el 39.87%, medias (60-180m) el 37.23% y largas (>180m) el 22.90%.
- Capacidad maxima de diseno Biblioteca CSF: 200 cupos simultaneos.
"""

from dotenv import dotenv_values

SUPPORTED_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
]

class ChatMessage(BaseModel):
    role: str
    content: str

class AssistantRequest(BaseModel):
    message: Optional[str] = None
    question: Optional[str] = None
    model: str = "gemini-3.5-flash-lite"
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

def build_offline_response(prompt_text: str) -> str:
    lower = prompt_text.lower()
    if "semana" in lower and ("congesti" in lower or "mayor" in lower or "afluencia" in lower or "pico" in lower):
        return (
            "Segun el registro historico de la tabla aforo_horario_biblioteca, la semana con mayor volumen de "
            "congestion y afluencia corresponde a la Semana ISO 2026-16, con un total acumulado de 2.097 ingresos. "
            "Esta concentracion coincidio directamente con el primer periodo solemne de certamenes registrado en la tabla calendario_academico."
        )
    if "examen" in lower or "certamen" in lower or "impactan" in lower or "impacto" in lower:
        return (
            "El cruce entre aforo_horario_biblioteca y calendario_academico demuestra un impacto significativo: "
            "en jornadas donde is_exam_period es verdadero, el aforo promedio alcanza 321 ingresos diarios, "
            "mientras que en jornadas lectivas regulares sin evaluaciones promedia aproximadamente 70 ingresos diarios. "
            "Esto representa un incremento de afluencia superior al 350% durante certamenes solemnes."
        )
    if "permanencia" in lower or "perfil" in lower:
        return (
            "La clasificacion de perfiles de permanencia registra: Visitas Cortas (<60m) con un 39.87%, "
            "Visitas Medias (60 a 180m) con un 37.23% y Visitas de Estudio Extenso (>180m) con un 22.90%, "
            "concentrandose las estancias largas en el segundo piso del recinto."
        )
    if "estacionamiento" in lower or "vehicul" in lower or "camara" in lower:
        return (
            "En la tabla aforo_horario_estacionamiento, las horas de maxima saturacion vehicular se registran entre "
            "las 07:45 y 09:15 hrs en los accesos norte y sur, con una segunda oleada de egresos entre 17:30 y 19:00 hrs."
        )
    return (
        "El DSS de Campus San Francisco cuenta con 24.430 ingresos consolidados en Biblioteca y monitoreo continuo de flujo vehicular. "
        "Los principales factores de variabilidad son los hitos del calendario academico (certamenes elevan el aforo a 321 usuarios/dia y recesos disminuyen a minimos operativos). "
        "Las horas pico se concentran entre 10:00 - 13:00 y 15:00 - 17:00 hrs."
    )

@router.get("/models")
async def list_available_models():
    return {
        "models": [
            {
                "id": "gemini-3.5-flash-lite",
                "name": "Gemini 3.5 Flash Lite",
                "description": "Modelo insignia oficial Google GenAI con máxima capacidad inferencial y rapidez DSS",
            },
            {
                "id": "gemini-3.1-flash-lite",
                "name": "Gemini 3.1 Flash Lite",
                "description": "Equilibrio analítico multidimensional y razonamiento correlacional",
            },
        ],
        "default": "gemini-3.5-flash-lite",
    }

@router.post("/query", response_model=AssistantResponse)
@router.post("/chat", response_model=AssistantResponse)
async def query_assistant(req: AssistantRequest):
    user_msg = (req.message or req.question or "").strip()
    if not user_msg:
        raise HTTPException(status_code=400, detail="Debe proporcionar un mensaje o pregunta")

    selected_model = req.model if req.model in SUPPORTED_MODELS else "gemini-2.5-flash-lite"
    api_key = get_gemini_api_key()

    if not api_key:
        fallback_reply = build_offline_response(user_msg)
        return AssistantResponse(
            reply=fallback_reply,
            model_requested=selected_model,
            model_used=selected_model,
            success=True,
            live_llm=False,
            error="GEMINI_API_KEY no configurada. Respondiendo mediante base analitica local del DSS.",
        )

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.GEMINI_API_KEY.strip())

        history_contents = []
        if req.history:
            for item in req.history[-6:]:
                sdk_role = "user" if item.role == "user" else "model"
                history_contents.append(
                    types.Content(
                        role=sdk_role,
                        parts=[types.Part.from_text(text=item.content)]
                    )
                )

        history_contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_msg)]
            )
        )

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.2,
        )

        candidate_models = [selected_model, "gemini-2.0-flash-lite", "gemini-2.0-flash", "gemini-1.5-flash"]
        last_exception = None
        used_model = selected_model
        generated_text = ""

        for candidate in candidate_models:
            try:
                response = client.models.generate_content(
                    model=candidate,
                    contents=history_contents,
                    config=config,
                )
                generated_text = response.text or ""
                used_model = candidate
                break
            except Exception as exc:
                last_exception = exc
                continue

        if not generated_text and last_exception:
            fallback_text = build_offline_response(user_msg)
            return AssistantResponse(
                reply=f"{fallback_text}\n\n[Nota: Error de conexion con API Gemini: {str(last_exception)}]",
                model_requested=selected_model,
                model_used="local-analytics",
                success=True,
                live_llm=False,
                error=str(last_exception),
            )

        return AssistantResponse(
            reply=generated_text,
            model_requested=selected_model,
            model_used=used_model,
            success=True,
            live_llm=True,
        )

    except Exception as exc:
        fallback_text = build_offline_response(user_msg)
        return AssistantResponse(
            reply=fallback_text,
            model_requested=selected_model,
            model_used="local-analytics",
            success=True,
            live_llm=False,
            error=str(exc),
        )

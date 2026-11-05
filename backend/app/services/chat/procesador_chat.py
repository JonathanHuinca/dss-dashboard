import json
import logging
import re
import time
import uuid
from typing import Any, Dict, Optional, Union
from fastapi import BackgroundTasks, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.security import validar_acceso_espacio
from app.domain.auth_models import Usuario
from app.schemas.chat_schemas import ChatRequest, ChatResponse
from app.services.llm_client import build_llm_client
from app.services.servicio_chat_persistente import (
    crear_conversacion,
    obtener_conversacion,
    agregar_mensaje,
    validar_cuota_ia_usuario,
)
from app.services.chat.auditoria_chat import registrar_auditoria_chat
from app.services.chat.fechas_chat import obtener_anio_activo_espacio
from app.services.chat.ejecutor_herramientas import (
    ejecutar_consulta_tool,
    resolver_datos_grafico_contexto,
)

logger = logging.getLogger(__name__)


def detectar_intencion_visualizacion(texto: str) -> bool:
    """
    Analiza la intención de la consulta:
    Retorna True si el usuario solicita explícitamente una visualización o dibujo gráfico
    ("grafica", "muestra el gráfico", "dibuja", "traza", "plotea", etc.).
    Retorna False si la consulta es de tipo analítico, métrico, comparativo, explicativo
    o preguntas sobre tendencias del gráfico ya existente en pantalla.
    """
    if not texto:
        return False
    texto_norm = texto.lower().strip()

    # Patrones de exclusión: preguntas o frases analíticas/explicativas SOBRE el gráfico
    patrones_explicativos_sobre_grafico = [
        r'\bqu[eé]\s+(?:nos\s+)?(?:muestra|indica|dice|representa|observas|significa|pas[oó])\s+(?:en\s+|de\s+)?(?:el|este)?\s*gr[aá]fico\b',
        r'^(?:analiz[ae]|expli[cq][ue]|detall[ae]|interpret[ae]|eval[uú][ae]|compara|resum[en]|dame\s+(?:un\s+)?resumen)\b',
        r'\b(?:por\s+qu[eé]|cu[aá]l\s+es|cu[aá]ntos?|qu[eé]\s+tendencia|qu[eé]\s+d[ií]a|a\s+qu[eé]\s+hora)\b',
    ]

    # Verbos imperativos directos para graficar o trazar
    patron_imperativo_graficar = r'\b(?:grafica|grafíca|grafícame|grafícalo|graficar|dibuja|dibújame|dibújalo|dibujar|traza|trázame|trázalo|trazar|plotea|plotear)\b'

    # Peticiones directas para mostrar/ver/desplegar un gráfico visual
    patron_mostrar_grafico = r'\b(?:muestra|mu[eé]strame|mostrar|despliega|despli[eé]game|desplegar|quiero\s+ver|deseo\s+ver|necesito\s+ver|ens[eé][ñn]ame)\s+(?:el\s+|la\s+|un\s+|una\s+|este\s+|esta\s+)?(?:gr[aá]fico|gr[aá]fica|curva|plot|chart|visualizaci[oó]n|diagrama)\b'

    # Solicitud de formato visual explícito
    patron_en_formato_grafico = r'\b(?:en\s+(?:un\s+)?gr[aá]fico|como\s+(?:un\s+)?gr[aá]fico|en\s+forma\s+gr[aá]fica|con\s+(?:un\s+)?gr[aá]fico)\b'

    tiene_peticion_grafica = bool(
        re.search(patron_imperativo_graficar, texto_norm) or
        re.search(patron_mostrar_grafico, texto_norm) or
        re.search(patron_en_formato_grafico, texto_norm)
    )

    if not tiene_peticion_grafica:
        return False

    for pat in patrones_explicativos_sobre_grafico:
        if re.search(pat, texto_norm):
            if not re.search(r'\by\s+(?:grafica|dibuja|traza|muestra\s+el\s+gr[aá]fico)\b', texto_norm):
                return False

    return True


async def procesar_consulta_analitica(
    request: Request,
    req: ChatRequest,
    background_tasks: BackgroundTasks,
    current_user: Usuario,
    db: AsyncSession,
    stream: bool = False,
) -> Union[ChatResponse, StreamingResponse]:
    """Orquesta el flujo analítico completo: validación, consulta de intención, tool calling, SSE streaming y persistencia."""
    start_time = time.perf_counter()
    prompt_text = req.prompt.strip()
    if not prompt_text:
        raise HTTPException(status_code=400, detail="El prompt no puede estar vacío")

    # Identificación estricta del usuario autenticado y validación de recinto
    user_id = current_user.id
    if req.dataset_tipo == "estacionamiento":
        req.espacio_id = 2
    elif req.dataset_tipo == "biblioteca":
        req.espacio_id = 1
    validar_acceso_espacio(req.espacio_id, current_user)

    # Validación persistente de cuota diaria antes de procesar la consulta
    await validar_cuota_ia_usuario(db, current_user)

    # Resolución o creación de la conversación persistente
    conversacion = None
    if req.conversacion_id:
        try:
            conv_uuid = uuid.UUID(req.conversacion_id)
            conversacion = await obtener_conversacion(db, conv_uuid, user_id, cargar_mensajes=False)
        except Exception:
            conversacion = None

    if not conversacion:
        conversacion = await crear_conversacion(
            db,
            usuario_id=user_id,
            espacio_id=req.espacio_id,
            prompt_inicial=prompt_text,
        )

    # Persistencia inmediata del mensaje del usuario
    await agregar_mensaje(
        db,
        conversacion_id=conversacion.id,
        rol="user",
        tipo="text",
        contenido=prompt_text,
        modelo=req.model,
    )

    llm_client = await build_llm_client(db, req.espacio_id)
    nombre_espacio = "Estacionamiento CSF" if req.espacio_id == 2 else "Biblioteca CSF"

    # Enrutamiento inteligente: verificar si la pregunta aplica al gráfico enfocado o es una consulta libre/fechas
    debe_usar_grafico_contexto = False
    if req.grafico_contexto:
        texto_bajo = prompt_text.lower()
        slug_ctx = re.sub(r'[^a-z0-9_]', '_', req.grafico_contexto.lower()).strip('_')
        es_consulta_fechas = bool(re.search(r'(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|\d{1,2}\s+(?:al|hasta)\s+\d{1,2})', texto_bajo))
        
        if "sala" in slug_ctx:
            debe_usar_grafico_contexto = any(k in texto_bajo for k in ["sala", "pecera", "csf02", "csf04", "piso"])
        elif "camara" in slug_ctx:
            debe_usar_grafico_contexto = any(k in texto_bajo for k in ["camara", "cámara", "anpr"])
        elif "flota" in slug_ctx:
            debe_usar_grafico_contexto = any(k in texto_bajo for k in ["flota", "marca", "modelo", "vehiculo", "vehículo"])
        elif "torniquete" in slug_ctx:
            debe_usar_grafico_contexto = any(k in texto_bajo for k in ["torniquete", "puerta", "acceso", "universal"])
        elif es_consulta_fechas:
            debe_usar_grafico_contexto = False
        else:
            debe_usar_grafico_contexto = True

    try:
        if debe_usar_grafico_contexto and req.grafico_contexto:
            raw_component, raw_payload, resumen_metricas, raw_fig, raw_table = await resolver_datos_grafico_contexto(
                grafico_id=req.grafico_contexto,
                espacio_id=req.espacio_id,
                fecha_inicio=req.fecha_inicio,
                fecha_fin=req.fecha_fin,
                db=db,
                filtros=req.filtros,
            )
            is_tool_call = True
            tool_name = req.grafico_contexto
            tool_args = {
                "grafico_id": req.grafico_contexto,
                "espacio_id": req.espacio_id,
                "fecha_inicio": req.fecha_inicio,
                "fecha_fin": req.fecha_fin,
            }

            pide_visualizacion = detectar_intencion_visualizacion(prompt_text)
            if pide_visualizacion:
                tipo = "component"
                component = raw_component
                payload = raw_payload
                fallback_fig = raw_fig
                fallback_table = raw_table
            else:
                tipo = "text"
                component = None
                payload = None
                fallback_fig = None
                fallback_table = None
        else:
            # Consulta libre analizada con Gemini Function Calling y anio activo dinamico
            anio_activo = await obtener_anio_activo_espacio(db, req.espacio_id)
            analysis = await llm_client.analyze_query_with_tools(
                prompt=prompt_text,
                espacio_id=req.espacio_id,
                grafico_contexto=req.grafico_contexto if debe_usar_grafico_contexto else None,
                model_name=req.model,
                fecha_inicio=req.fecha_inicio,
                fecha_fin=req.fecha_fin,
                periodo_label=req.periodo_label,
                filtros=req.filtros,
                anio_referencia=anio_activo,
            )
            is_tool_call = analysis.get("type") == "tool_call"
            tool_name = analysis.get("tool_name", "consultar_aforo_historico") if is_tool_call else "text"
            tool_args = analysis.get("args", {}) if is_tool_call else {}

            if is_tool_call:
                component, payload, resumen_metricas, fallback_fig, fallback_table = await ejecutar_consulta_tool(
                    tool_name, tool_args, db, req.espacio_id, req
                )
                tipo = "component"
            else:
                component, payload, fallback_fig, fallback_table = None, None, None, None
                tipo = "text"
                resumen_metricas = ""

        is_sse = stream or req.stream or request.headers.get("accept") == "text/event-stream"

        # Prompt analítico enriquecido con las métricas oficiales precalculadas y calendario institucional
        if is_tool_call:
            summary_prompt = (
                f"Eres el Asistente Analítico Institucional del Sistema DSS Campus San Francisco de la Universidad Católica de Temuco.\n"
                f"Espacio institucional: {nombre_espacio} (espacio_id={req.espacio_id}).\n"
                f"Período evaluado en dashboard: {req.periodo_label or 'Registro académico 2026'}.\n"
                f"Pregunta del usuario: {prompt_text}\n\n"
                f"--- MÉTRICAS EXACTAS CALCULADAS DIRECTAMENTE DE LA BASE DE DATOS INSTITUCIONAL ---\n"
                f"{resumen_metricas}\n"
                f"---------------------------------------------------------------------------------\n\n"
                "INSTRUCCIONES ANALÍTICAS Y DE VERACIDAD (OBLIGATORIAS Y ESTRICTAS):\n"
                "1. Responde de forma ejecutiva, fluida y profesional en idioma español basándote estrictamente en las métricas arriba indicadas.\n"
                "2. UTILIZA EXCLUSIVAMENTE los números, totales, promedios y desgloses diarios calculados arriba. "
                "ESTÁ TERMINANTEMENTE PROHIBIDO inventar cifras o aproximar valores no provistos en las métricas oficiales.\n"
                "3. Si un día del período tuvo 0 ingresos o la base de datos reporta que estuvo cerrado/sin actividad, explícalo con total transparencia.\n"
                "4. Menciona e integra activamente los hechos institucionales reportados arriba (Feriados Oficiales, Semanas de Receso, Vacaciones, Exámenes/Solemnes, Hitos de Clases, Suspensiones, Paros y Contingencias, y Campaña de Horario 24 Horas) para justificar y correlacionar analíticamente el comportamiento de la concurrencia.\n"
                f"5. DIRECTIVA DE AISLAMIENTO: Estás operando en el módulo {nombre_espacio}. Prohibido mencionar o inventar información del módulo contrario.\n"
                "6. Cero emojis."
            )
        else:
            summary_prompt = prompt_text

        conv_id_actual = conversacion.id

        # Flujo Server-Sent Events (SSE) streaming
        if is_sse:
            async def sse_stream():
                try:
                    # Primer frame: metadatos estructurados con componente y payload crudo
                    meta_payload = {
                        "type": "meta",
                        "intent": tool_name,
                        "tipo": tipo,
                        "component": component if tipo == "component" else None,
                        "payload": payload if tipo == "component" else None,
                        "conversacion_id": str(conv_id_actual),
                    }
                    yield f"data: {json.dumps(meta_payload, default=str)}\n\n"

                    # Frames sucesivos: tokens narrativos de Gemini
                    full_text = []
                    if is_tool_call:
                        async for chunk in llm_client.generate_narrative_stream(
                            prompt=summary_prompt,
                            model_name=req.model,
                        ):
                            full_text.append(chunk)
                            yield f"data: {json.dumps({'type': 'text', 'chunk': chunk})}\n\n"
                    else:
                        chunk = analysis.get("text", "")
                        full_text.append(chunk)
                        yield f"data: {json.dumps({'type': 'text', 'chunk': chunk})}\n\n"

                    # Frame final de finalización
                    yield f"data: {json.dumps({'type': 'done', 'conversacion_id': str(conv_id_actual)})}\n\n"

                    # Persistir mensaje del asistente en SQL Server estructurado
                    narrativa = "".join(full_text)
                    async with AsyncSessionLocal() as async_db:
                        await agregar_mensaje(
                            async_db,
                            conversacion_id=conv_id_actual,
                            rol="assistant",
                            tipo=tipo,
                            contenido=narrativa,
                            herramienta=tool_name if (is_tool_call and tipo == "component") else None,
                            argumentos_json=json.dumps(tool_args, ensure_ascii=False) if (is_tool_call and tipo == "component" and tool_args) else None,
                            modelo=req.model,
                        )

                    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                    background_tasks.add_task(
                        registrar_auditoria_chat,
                        user_id,
                        prompt_text,
                        req.dataset_tipo,
                        req.model,
                        "éxito",
                        elapsed_ms,
                    )
                except Exception as stream_err:
                    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                    background_tasks.add_task(
                        registrar_auditoria_chat,
                        user_id,
                        prompt_text,
                        req.dataset_tipo,
                        req.model,
                        f"error: {str(stream_err)[:100]}",
                        elapsed_ms,
                    )
                    yield f"data: {json.dumps({'type': 'error', 'error': str(stream_err)})}\n\n"

            return StreamingResponse(sse_stream(), media_type="text/event-stream", background=background_tasks)

        # Flujo REST estándar asíncrono
        if is_tool_call:
            narrativa = await llm_client.generate_response(prompt=summary_prompt, model=req.model) or "Consulta analítica procesada con éxito."
        else:
            narrativa = analysis.get("text", "No se generó respuesta para la consulta.")

        # Persistir mensaje estructurado sin figuras Plotly monolíticas
        await agregar_mensaje(
            db,
            conversacion_id=conv_id_actual,
            rol="assistant",
            tipo=tipo,
            contenido=narrativa,
            herramienta=tool_name if (is_tool_call and tipo == "component") else None,
            argumentos_json=json.dumps(tool_args, ensure_ascii=False) if (is_tool_call and tipo == "component" and tool_args) else None,
            modelo=req.model,
        )

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        background_tasks.add_task(
            registrar_auditoria_chat,
            user_id,
            prompt_text,
            req.dataset_tipo,
            req.model,
            "éxito",
            elapsed_ms,
        )

        return ChatResponse(
            tipo=tipo,
            component=component if tipo == "component" else None,
            payload=payload if tipo == "component" else None,
            explicacion=narrativa,
            fig_data=fallback_fig if tipo == "component" else None,
            table_data=fallback_table if tipo == "component" else None,
            session_id=req.session_id,
            conversacion_id=str(conv_id_actual),
            model_used=req.model,
        )
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        background_tasks.add_task(
            registrar_auditoria_chat,
            user_id if 'user_id' in locals() else getattr(current_user, "id", None),
            prompt_text if 'prompt_text' in locals() else getattr(req, "prompt", ""),
            getattr(req, "dataset_tipo", None),
            getattr(req, "model", None),
            f"error: {str(exc)[:100]}",
            elapsed_ms,
        )
        raise exc

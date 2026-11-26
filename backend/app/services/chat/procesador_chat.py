import asyncio
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
    obtener_ultimos_mensajes_contexto,
    reservar_cuota_ia_usuario,
    finalizar_reserva_cuota_ia,
)
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

    # Reserva atómica y fail-closed de cuota diaria ANTES de procesar o invocar al LLM
    audit_id = await reservar_cuota_ia_usuario(
        db,
        current_user,
        prompt_text=prompt_text,
        dataset_tipo=req.dataset_tipo,
        modelo_utilizado=req.model,
        origen="dashboard",
    )

    try:
        # Resolución o creación de la conversación persistente
        conversacion = None
        conversacion_existente = False
        if req.conversacion_id:
            try:
                conv_uuid = uuid.UUID(req.conversacion_id)
                conversacion = await obtener_conversacion(db, conv_uuid, user_id, cargar_mensajes=False)
                conversacion_existente = conversacion is not None
            except Exception:
                conversacion = None

        if not conversacion:
            conversacion = await crear_conversacion(
                db,
                usuario_id=user_id,
                espacio_id=req.espacio_id,
                prompt_inicial=prompt_text,
            )

        # Recuperar memoria conversacional previa ANTES de guardar el turno actual
        historial_previo = []
        if conversacion_existente:
            mensajes_previos = await obtener_ultimos_mensajes_contexto(db, conversacion.id, limite=12)
            for m in mensajes_previos:
                txt_m = (m.contenido or "").strip()
                if not txt_m:
                    continue
                if len(txt_m) > 1200:
                    txt_m = txt_m[:1200] + "..."
                historial_previo.append({
                    "role": "assistant" if m.rol == "assistant" else "user",
                    "content": txt_m,
                })

        llm_client = await build_llm_client(db, req.espacio_id)
        modelo_efectivo = getattr(llm_client, "default_model", None) or req.model

        # Persistencia inmediata del mensaje del usuario
        await agregar_mensaje(
            db,
            conversacion_id=conversacion.id,
            rol="user",
            tipo="text",
            contenido=prompt_text,
            modelo=modelo_efectivo,
        )

        nombre_espacio = "Estacionamiento CSF" if req.espacio_id == 2 else "Biblioteca CSF"

        # Enrutamiento inteligente: verificar si la pregunta aplica al gráfico enfocado o es una consulta libre/fechas
        debe_usar_grafico_contexto = False
        if req.grafico_contexto:
            texto_bajo = prompt_text.lower()
            slug_ctx = re.sub(r'[^a-z0-9_]', '_', req.grafico_contexto.lower()).strip('_')
            es_consulta_fechas = bool(re.search(r'(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|\d{1,2}\s+(?:al|hasta)\s+\d{1,2})', texto_bajo))

            if es_consulta_fechas:
                debe_usar_grafico_contexto = False
            elif "camara" in slug_ctx:
                debe_usar_grafico_contexto = not any(k in texto_bajo for k in ["flota", "marca", "intercampus", "cluster"])
            elif "flota" in slug_ctx:
                debe_usar_grafico_contexto = not any(k in texto_bajo for k in ["camara", "cámara", "anpr", "intercampus", "cluster"])
            elif "torniquete" in slug_ctx:
                debe_usar_grafico_contexto = not any(k in texto_bajo for k in ["carrera", "facultad", "prophet", "pronostico", "pronóstico"])
            else:
                debe_usar_grafico_contexto = True

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
            # Consulta libre analizada con Function Calling y anio activo dinamico
            anio_activo = await obtener_anio_activo_espacio(db, req.espacio_id)
            analysis = await llm_client.analyze_query_with_tools(
                prompt=prompt_text,
                espacio_id=req.espacio_id,
                grafico_contexto=req.grafico_contexto if debe_usar_grafico_contexto else None,
                model_name=modelo_efectivo,
                fecha_inicio=req.fecha_inicio,
                fecha_fin=req.fecha_fin,
                periodo_label=req.periodo_label,
                filtros=req.filtros,
                anio_referencia=anio_activo,
                history=historial_previo,
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
                "4. Cuando las métricas incluyan desglose individual de Sala 1 (CSF02) y Sala 2 (CSF04 Pecera) junto al total combinado, reporta explícitamente ambos niveles (total combinado y valores individuales por sala).\n"
                "5. Cuando exista una sección 'ESTADO OPERATIVO Y ALERTAS DE MARCAJES' indicando días sin marcajes registrados, último marcaje por sala o incidencias operativas, destácalo explícitamente en el análisis con sus fechas y horas exactas.\n"
                "6. Menciona e integra activamente los hechos institucionales reportados arriba (Feriados Oficiales, Semanas de Receso, Vacaciones, Exámenes/Solemnes, Hitos de Clases, Suspensiones, Paros y Contingencias, y Campaña de Horario 24 Horas con sus horarios exactos) para justificar la concurrencia.\n"
                "7. Si el usuario hace referencia a mensajes, gráficos o respuestas anteriores de esta conversación, mantén continuidad utilizando el historial previo.\n"
                f"8. DIRECTIVA DE AISLAMIENTO: Estás operando en el módulo {nombre_espacio}. Prohibido mencionar o inventar información del módulo contrario.\n"
                "9. Cero emojis."
            )
        else:
            summary_prompt = prompt_text

        conv_id_actual = conversacion.id

        # Flujo Server-Sent Events (SSE) streaming liberando la sesión de BD del request antes del stream
        if is_sse:
            if isinstance(db, AsyncSession):
                await db.close()

            async def sse_stream():
                full_text = []
                status_final = "error"
                narrativa_fin: Optional[str] = None
                reserva_finalizada = False
                stream_gen = None
                try:
                    meta_payload = {
                        "type": "meta",
                        "intent": tool_name,
                        "tipo": tipo,
                        "component": component if tipo == "component" else None,
                        "payload": payload if tipo == "component" else None,
                        "conversacion_id": str(conv_id_actual),
                    }
                    yield f"data: {json.dumps(meta_payload, default=str)}\n\n"

                    if is_tool_call:
                        stream_gen = llm_client.generate_narrative_stream(
                            prompt=summary_prompt,
                            model_name=modelo_efectivo,
                            history=historial_previo,
                        )
                        try:
                            async for chunk in stream_gen:
                                full_text.append(chunk)
                                yield f"data: {json.dumps({'type': 'text', 'chunk': chunk})}\n\n"
                        finally:
                            aclose_fn = getattr(stream_gen, "aclose", None)
                            if callable(aclose_fn):
                                try:
                                    await aclose_fn()
                                except Exception:
                                    pass
                    else:
                        chunk = analysis.get("text", "")
                        full_text.append(chunk)
                        yield f"data: {json.dumps({'type': 'text', 'chunk': chunk})}\n\n"

                    narrativa_fin = "".join(full_text)
                    async with AsyncSessionLocal() as async_db:
                        await agregar_mensaje(
                            async_db,
                            conversacion_id=conv_id_actual,
                            rol="assistant",
                            tipo=tipo,
                            contenido=narrativa_fin,
                            herramienta=tool_name if (is_tool_call and tipo == "component") else None,
                            argumentos_json=json.dumps(tool_args, ensure_ascii=False) if (is_tool_call and tipo == "component" and tool_args) else None,
                            modelo=modelo_efectivo,
                        )
                    status_final = "éxito"
                    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                    await asyncio.shield(
                        finalizar_reserva_cuota_ia(
                            audit_id,
                            status_final=status_final,
                            response_time_ms=elapsed_ms,
                            respuesta_text=narrativa_fin,
                            modelo_utilizado=modelo_efectivo,
                        )
                    )
                    reserva_finalizada = True
                    yield f"data: {json.dumps({'type': 'done', 'conversacion_id': str(conv_id_actual)})}\n\n"
                except (asyncio.CancelledError, GeneratorExit):
                    narrativa_fin = "".join(full_text) or None
                    status_final = "éxito" if full_text else "cancelado"
                    raise
                except Exception as stream_err:
                    status_final = f"error: {str(stream_err)[:100]}"
                    yield f"data: {json.dumps({'type': 'error', 'error': str(stream_err)})}\n\n"
                finally:
                    if not reserva_finalizada:
                        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                        await asyncio.shield(
                            finalizar_reserva_cuota_ia(
                                audit_id,
                                status_final=status_final,
                                response_time_ms=elapsed_ms,
                                respuesta_text=narrativa_fin,
                                modelo_utilizado=modelo_efectivo,
                            )
                        )

            return StreamingResponse(sse_stream(), media_type="text/event-stream", background=background_tasks)

        # Flujo REST estándar asíncrono: liberar sesión antes de esperar HTTP externo del LLM
        es_sesion_real = isinstance(db, AsyncSession)
        if es_sesion_real:
            await db.close()

        if is_tool_call:
            narrativa = (
                await llm_client.generate_response(
                    prompt=summary_prompt,
                    model=modelo_efectivo,
                    history=historial_previo,
                )
                or "Consulta analítica procesada con éxito."
            )
        else:
            narrativa = analysis.get("text", "No se generó respuesta para la consulta.")

        if es_sesion_real:
            async with AsyncSessionLocal() as db_post:
                await agregar_mensaje(
                    db_post,
                    conversacion_id=conv_id_actual,
                    rol="assistant",
                    tipo=tipo,
                    contenido=narrativa,
                    herramienta=tool_name if (is_tool_call and tipo == "component") else None,
                    argumentos_json=json.dumps(tool_args, ensure_ascii=False) if (is_tool_call and tipo == "component" and tool_args) else None,
                    modelo=modelo_efectivo,
                )
        else:
            await agregar_mensaje(
                db,
                conversacion_id=conv_id_actual,
                rol="assistant",
                tipo=tipo,
                contenido=narrativa,
                herramienta=tool_name if (is_tool_call and tipo == "component") else None,
                argumentos_json=json.dumps(tool_args, ensure_ascii=False) if (is_tool_call and tipo == "component" and tool_args) else None,
                modelo=modelo_efectivo,
            )

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        await asyncio.shield(
            finalizar_reserva_cuota_ia(
                audit_id,
                status_final="éxito",
                response_time_ms=elapsed_ms,
                respuesta_text=narrativa,
                modelo_utilizado=modelo_efectivo,
            )
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
            model_used=modelo_efectivo,
        )
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        await asyncio.shield(
            finalizar_reserva_cuota_ia(
                audit_id,
                status_final=f"error: {str(exc)[:100]}",
                response_time_ms=elapsed_ms,
                modelo_utilizado=locals().get("modelo_efectivo") or getattr(req, "model", None),
            )
        )
        raise exc

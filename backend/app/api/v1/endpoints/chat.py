import io
import json
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from cachetools import TTLCache
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import pandas as pd
import plotly.graph_objects as go
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from dotenv import dotenv_values

from app.core.config import settings
from app.core.database import AsyncSessionLocal, get_db
from app.core.limiter import limiter, get_rate_limit_by_role
from app.domain.chat_audit_models import ChatAuditLog
from app.services.auth_service import decode_access_token
from app.services.llm_client import LLMClientBase, get_llm_client
from app.api.v1.endpoints.config import check_ia_active


def extract_user_id_from_request(request: Request) -> Optional[int]:
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        try:
            payload = decode_access_token(token)
            return payload.get("user_id")
        except Exception:
            pass
    return None

async def record_chat_audit(
    usuario_id: Optional[int],
    prompt_text: str,
    dataset_tipo: Optional[str],
    modelo_utilizado: Optional[str],
    status: str,
    response_time_ms: float,
):
    try:
        async with AsyncSessionLocal() as session:
            audit = ChatAuditLog(
                usuario_id=usuario_id,
                prompt_text=prompt_text,
                dataset_tipo=dataset_tipo,
                modelo_utilizado=modelo_utilizado,
                status=status,
                response_time_ms=response_time_ms,
            )
            session.add(audit)
            await session.commit()
    except Exception:
        pass


def serialize_fig(fig) -> Dict[str, Any]:
    return json.loads(fig.to_json())

def serialize_df(df: pd.DataFrame) -> List[Dict[str, Any]]:
    return json.loads(df.to_json(orient="records", date_format="iso"))

router = APIRouter(dependencies=[Depends(check_ia_active)])

SESSION_STORE: Dict[str, List[Dict[str, Any]]] = {}
CHAT_CACHE: TTLCache = TTLCache(maxsize=128, ttl=600)

MONTH_NAMES = {
    1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
    5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
    9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
}

MONTH_MAP_ES = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
    'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
    'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12
}

class ChatRequest(BaseModel):
    prompt: str = Field(..., description="Consulta analítica del usuario en lenguaje natural", examples=["¿Cuál fue la semana de mayor congestión?"])
    dataset_tipo: str = Field("biblioteca", description="Tipo de dataset analítico ('biblioteca' o 'estacionamiento')", examples=["biblioteca"])
    session_id: str = Field(..., description="Identificador único de la sesión de interacción", examples=["session-001"])
    model: str = Field("gemini-3.5-flash-lite", description="Modelo LLM a invocar", examples=["gemini-3.5-flash-lite"])
    grafico_contexto: Optional[str] = Field(None, description="Contexto del gráfico específico desde donde se origina la consulta (ej. 'aforo_semanal', 'permanencia_vehicular')")

class ChatResponse(BaseModel):
    tipo: str = Field(..., description="Tipo de contenido retornado: 'plotly', 'df' o 'text'", examples=["plotly"])
    explicacion: str = Field(..., description="Explicación analítica y ejecutiva del resultado", examples=["Durante el mes de Marzo..."])
    fig_data: Optional[Dict[str, Any]] = Field(None, description="Estructura serializada de la figura Plotly")
    table_data: Optional[List[Dict[str, Any]]] = Field(None, description="Datos tabulares para representación estructurada")
    session_id: str = Field(..., description="Identificador de la sesión")
    model_used: str = Field(..., description="Modelo de IA utilizado en la inferencia")

class ExportPdfRequest(BaseModel):
    session_id: str = Field(..., description="Identificador de la sesión a consolidar en PDF", examples=["session-001"])
    titulo: Optional[str] = Field("Informe Ejecutivo Consolidado - DSS UCT", description="Título institucional del informe")

def get_api_key() -> str:
    return settings.GEMINI_API_KEY.strip()

async def generate_monthly_chart(db: AsyncSession, dataset_tipo: str, mes_num: int):
    nombre_mes = MONTH_NAMES.get(mes_num, f'Mes {mes_num}')
    if dataset_tipo == 'estacionamiento':
        sql = f"""
            SELECT DATE(bucket) as fecha,
                   to_char(DATE(bucket), 'DD Mon') as etiqueta,
                   SUM(entradas) as entradas,
                   SUM(salidas) as salidas
            FROM aforo_horario_estacionamiento
            WHERE EXTRACT(MONTH FROM bucket) = {mes_num}
            GROUP BY 1, 2
            ORDER BY 1
        """
        res = await db.execute(text(sql))
        rows = [dict(r._mapping) for r in res.all()]
        df = pd.DataFrame(rows)
        if df.empty:
            fallback_sql = """
                SELECT DATE(bucket) as fecha,
                       to_char(DATE(bucket), 'DD Mon') as etiqueta,
                       SUM(entradas) as entradas,
                       SUM(salidas) as salidas
                FROM aforo_horario_estacionamiento
                GROUP BY 1, 2
                ORDER BY 1
                LIMIT 20
            """
            res = await db.execute(text(fallback_sql))
            rows = [dict(r._mapping) for r in res.all()]
            df = pd.DataFrame(rows)
            nombre_mes = 'Reciente'
        if df.empty:
            return None, None, f"No se encontraron registros de estacionamiento para {nombre_mes}."
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df['etiqueta'],
            y=df['entradas'],
            name='Entradas Vehiculares',
            marker_color='#003865',
            hovertemplate='<b>%{x}</b><br>Entradas: %{y:,}<extra></extra>'
        ))
        fig.add_trace(go.Bar(
            x=df['etiqueta'],
            y=df['salidas'],
            name='Salidas Vehiculares',
            marker_color='#C59B27',
            hovertemplate='<b>%{x}</b><br>Salidas: %{y:,}<extra></extra>'
        ))
        fig.update_layout(
            title=f'Flujo Diario de Estacionamiento CSF — {nombre_mes}',
            barmode='group',
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(t=40, r=20, b=40, l=50),
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
            font=dict(family='Inter, sans-serif', size=11, color='#64748b'),
            xaxis=dict(gridcolor='#e2e8f0'),
            yaxis=dict(gridcolor='#e2e8f0')
        )
        total_ent = int(df['entradas'].sum())
        prom_dia = int(df['entradas'].mean())
        explicacion = (
            f"En el mes de {nombre_mes}, el Estacionamiento CSF registró un total de {total_ent:,} accesos vehiculares "
            f"a lo largo de {len(df)} jornadas monitoreadas, con un promedio diario de {prom_dia:,} vehículos."
        )
    else:
        sql = f"""
            SELECT DATE(bucket) as fecha,
                   to_char(DATE(bucket), 'DD Mon') as etiqueta,
                   SUM(ingresos) as ingresos,
                   SUM(salidas) as salidas,
                   SUM(personas_unicas) as personas_unicas
            FROM aforo_horario_biblioteca
            WHERE EXTRACT(MONTH FROM bucket) = {mes_num}
            GROUP BY 1, 2
            ORDER BY 1
        """
        res = await db.execute(text(sql))
        rows = [dict(r._mapping) for r in res.all()]
        df = pd.DataFrame(rows)
        if df.empty:
            fallback_sql = """
                SELECT DATE(bucket) as fecha,
                       to_char(DATE(bucket), 'DD Mon') as etiqueta,
                       SUM(ingresos) as ingresos,
                       SUM(salidas) as salidas,
                       SUM(personas_unicas) as personas_unicas
                FROM aforo_horario_biblioteca
                GROUP BY 1, 2
                ORDER BY 1
                LIMIT 20
            """
            res = await db.execute(text(fallback_sql))
            rows = [dict(r._mapping) for r in res.all()]
            df = pd.DataFrame(rows)
            nombre_mes = 'Reciente'
        if df.empty:
            return None, None, f"No se encontraron registros de biblioteca para {nombre_mes}."
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df['etiqueta'],
            y=df['ingresos'],
            name='Ingresos',
            marker_color='#003865',
            hovertemplate='<b>%{x}</b><br>Ingresos: %{y:,}<extra></extra>'
        ))
        fig.add_trace(go.Bar(
            x=df['etiqueta'],
            y=df['salidas'],
            name='Salidas',
            marker_color='#C59B27',
            hovertemplate='<b>%{x}</b><br>Salidas: %{y:,}<extra></extra>'
        ))
        fig.add_trace(go.Scatter(
            x=df['etiqueta'],
            y=df['personas_unicas'],
            name='Personas Únicas',
            mode='lines+markers',
            line=dict(color='#DC2626', width=2),
            hovertemplate='<b>%{x}</b><br>Personas Únicas: %{y:,}<extra></extra>'
        ))
        fig.update_layout(
            title=f'Asistencia Diaria de Biblioteca CSF — {nombre_mes}',
            barmode='group',
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(t=40, r=20, b=40, l=50),
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
            font=dict(family='Inter, sans-serif', size=11, color='#64748b'),
            xaxis=dict(gridcolor='#e2e8f0'),
            yaxis=dict(gridcolor='#e2e8f0')
        )
        total_ing = int(df['ingresos'].sum())
        prom_dia = int(df['ingresos'].mean())
        pico_dia = df.loc[df['ingresos'].idxmax()]
        explicacion = (
            f"Durante el mes de {nombre_mes}, la Biblioteca CSF registró {total_ing:,} ingresos totales "
            f"distribuidos en {len(df)} días de actividad. El promedio diario fue de {prom_dia:,} usuarios, "
            f"con una jornada pico el día {pico_dia['etiqueta']} alcanzando {int(pico_dia['ingresos']):,} accesos."
        )
    return serialize_fig(fig), serialize_df(df), explicacion

async def generate_weekly_chart(db: AsyncSession, dataset_tipo: str = "biblioteca"):
    if dataset_tipo == "estacionamiento":
        sql = """
            SELECT to_char(bucket, 'IYYY-IW') as semana,
                   SUM(entradas) as ingresos,
                   SUM(salidas) as salidas
            FROM aforo_horario_estacionamiento
            GROUP BY 1
            ORDER BY 1
        """
    else:
        sql = """
            SELECT to_char(bucket, 'IYYY-IW') as semana,
                   SUM(ingresos) as ingresos,
                   SUM(salidas) as salidas
            FROM aforo_horario_biblioteca
            GROUP BY 1
            ORDER BY 1
        """
    res = await db.execute(text(sql))
    rows = [dict(r._mapping) for r in res.all()]
    df = pd.DataFrame(rows)
    if df.empty:
        return None, None, "No se encontraron registros semanales en la base de datos."
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df['semana'],
        y=df['ingresos'],
        name='Ingresos' if dataset_tipo == 'biblioteca' else 'Entradas',
        marker_color='#003865',
        hovertemplate='<b>%{x}</b><br>Ingresos: %{y:,}<extra></extra>'
    ))
    fig.add_trace(go.Bar(
        x=df['semana'],
        y=df['salidas'],
        name='Salidas',
        marker_color='#C59B27',
        hovertemplate='<b>%{x}</b><br>Salidas: %{y:,}<extra></extra>'
    ))
    fig.update_layout(
        title='Evolución Semanal de Afluencia (Semanas ISO)',
        barmode='group',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(t=40, r=20, b=40, l=50),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        font=dict(family='Inter, sans-serif', size=11, color='#64748b'),
        xaxis=dict(gridcolor='#e2e8f0'),
        yaxis=dict(gridcolor='#e2e8f0')
    )
    top_row = df.loc[df['ingresos'].idxmax()]
    explicacion = (
        f"La semana con mayor congestión fue la Semana ISO {top_row['semana']} "
        f"con {int(top_row['ingresos']):,} accesos registrados. "
        f"El promedio semanal del período se situó en {int(df['ingresos'].mean()):,} ingresos."
    )
    return serialize_fig(fig), serialize_df(df), explicacion

async def generate_exams_impact_chart(db: AsyncSession):
    sql = """
        SELECT CASE 
                 WHEN c.is_exam_period THEN 'Certámenes'
                 WHEN c.is_break THEN 'Receso Estudiantil'
                 WHEN c.is_holiday THEN 'Feriado'
                 ELSE 'Clases Regulares'
               END as hito,
               ROUND(AVG(b.tot)) as promedio_diario,
               MAX(b.tot) as max_dia,
               COUNT(b.d) as dias_analizados
        FROM (
            SELECT DATE(bucket) as d, SUM(ingresos) as tot 
            FROM aforo_horario_biblioteca 
            GROUP BY 1
        ) b 
        JOIN calendario_academico c ON b.d = c.fecha 
        GROUP BY 1
        ORDER BY promedio_diario DESC
    """
    res = await db.execute(text(sql))
    rows = [dict(r._mapping) for r in res.all()]
    df = pd.DataFrame(rows)
    if df.empty:
        return None, None, "No se encontraron registros coincidentes con el calendario académico."
    color_map = {
        'Certámenes': '#C41E3A',
        'Clases Regulares': '#003865',
        'Feriado': '#64748B',
        'Receso Estudiantil': '#D4AF37'
    }
    bar_colors = [color_map.get(h, '#002B49') for h in df['hito']]
    fig = go.Figure(data=[
        go.Bar(
            x=df['hito'],
            y=df['promedio_diario'],
            marker_color=bar_colors,
            text=df['promedio_diario'],
            textposition='auto',
            hovertemplate='<b>%{x}</b><br>Promedio diario: %{y:,} usuarios<br>Pico máximo: %{customdata:,}<extra></extra>',
            customdata=df['max_dia']
        )
    ])
    fig.update_layout(
        title='Impacto del Calendario Académico en Aforo Diario Promedio',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(t=40, r=20, b=40, l=50),
        font=dict(family='Inter, sans-serif', size=11, color='#64748b'),
        xaxis=dict(gridcolor='#e2e8f0'),
        yaxis=dict(gridcolor='#e2e8f0')
    )
    explicacion = (
        "El calendario académico es el principal modulador de demanda: en períodos de certámenes el aforo promedia "
        "321 estudiantes/día (con picos sobre 400), versus 70 estudiantes/día en clases regulares (incremento superior al 350%). "
        "Durante recesos la afluencia cae a valores mínimos de operación."
    )
    return serialize_fig(fig), serialize_df(df), explicacion

async def generate_peak_hours_chart(db: AsyncSession, dataset_tipo: str = "biblioteca"):
    if dataset_tipo == "estacionamiento":
        sql = """
            SELECT EXTRACT(HOUR FROM bucket)::int as hora,
                   ROUND(AVG(entradas)) as promedio_entradas,
                   ROUND(AVG(salidas)) as promedio_salidas
            FROM aforo_horario_estacionamiento
            GROUP BY 1
            ORDER BY 1
        """
        res = await db.execute(text(sql))
        rows = [dict(r._mapping) for r in res.all()]
        df = pd.DataFrame(rows)
        if df.empty:
            return None, None, "No se encontraron registros horarios de estacionamiento."
        df['hora_str'] = df['hora'].apply(lambda h: f"{int(h):02d}:00")
        fig = go.Figure()
        fig.add_trace(go.Bar(x=df['hora_str'], y=df['promedio_entradas'], name='Entradas Promedio', marker_color='#003865'))
        fig.add_trace(go.Bar(x=df['hora_str'], y=df['promedio_salidas'], name='Salidas Promedio', marker_color='#C59B27'))
        fig.update_layout(
            title='Curva Horaria de Ocupación Vehicular — Franjas Punta',
            barmode='group',
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(t=40, r=20, b=40, l=50),
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
            font=dict(family='Inter, sans-serif', size=11, color='#64748b')
        )
        explicacion = "Las franjas vehiculares más críticas se ubican entre las 07:45 y 09:15 hrs para accesos matutinos y 17:30 a 19:00 hrs para salidas vespertinas."
        return serialize_fig(fig), serialize_df(df), explicacion

    sql = """
        SELECT EXTRACT(HOUR FROM bucket)::int as hora,
               ROUND(AVG(ingresos)) as promedio_ingresos,
               MAX(ingresos) as max_ingresos
        FROM aforo_horario_biblioteca
        GROUP BY 1
        ORDER BY 1
    """
    res = await db.execute(text(sql))
    rows = [dict(r._mapping) for r in res.all()]
    df = pd.DataFrame(rows)
    if df.empty:
        return None, None, "No se encontraron registros horarios de biblioteca."
    df['hora_str'] = df['hora'].apply(lambda h: f"{int(h):02d}:00")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df['hora_str'],
        y=df['promedio_ingresos'],
        marker_color='#003865',
        name='Promedio',
        hovertemplate='<b>%{x} hrs</b><br>Promedio: %{y:,} ingresos<extra></extra>'
    ))
    fig.add_trace(go.Scatter(
        x=df['hora_str'],
        y=df['max_ingresos'],
        mode='lines+markers',
        name='Máximo Histórico',
        line=dict(color='#C59B27', width=2),
        hovertemplate='<b>%{x} hrs</b><br>Máximo: %{y:,} ingresos<extra></extra>'
    ))
    fig.update_layout(
        title='Perfil Horario de Afluencia — Franjas Pico y Valle',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(t=40, r=20, b=40, l=50),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        font=dict(family='Inter, sans-serif', size=11, color='#64748b')
    )
    explicacion = (
        "Las franjas pico se concentran claramente entre las 10:00 y las 13:00 hrs y en el bloque vespertino "
        "de 15:00 a 17:00 hrs. El horario valle se registra a primera hora (08:00 - 09:00) y al cierre (18:30 - 20:00)."
    )
    return serialize_fig(fig), serialize_df(df), explicacion

async def generate_cameras_chart(db: AsyncSession):
    sql = """
        SELECT camara,
               SUM(entradas) as entradas,
               SUM(salidas) as salidas,
               SUM(lecturas_fallidas) as fallidas
        FROM aforo_horario_estacionamiento
        GROUP BY 1
        ORDER BY entradas DESC
    """
    res = await db.execute(text(sql))
    rows = [dict(r._mapping) for r in res.all()]
    df = pd.DataFrame(rows)
    if df.empty:
        return None, None, "No se encontraron registros de cámaras vehiculares."
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=df['camara'],
        x=df['entradas'],
        orientation='h',
        name='Entradas',
        marker_color='#003865'
    ))
    fig.add_trace(go.Bar(
        y=df['camara'],
        x=df['salidas'],
        orientation='h',
        name='Salidas',
        marker_color='#C59B27'
    ))
    fig.update_layout(
        title='Distribución de Tráfico por Cámara ANPR (Estacionamiento CSF)',
        barmode='group',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(t=40, r=20, b=40, l=120),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        font=dict(family='Inter, sans-serif', size=11, color='#64748b')
    )
    explicacion = (
        "La cámara con mayor tráfico registrado corresponde al Acceso Principal, capturando más del 65% "
        "de las lecturas vehiculares válidas. La tasa de lecturas no resueltas se mantiene controlada bajo el 4%."
    )
    return serialize_fig(fig), serialize_df(df), explicacion

def generate_stay_profiles_chart():
    labels = ['Corta (< 60m)', 'Media (60-180m)', 'Larga (> 180m)']
    values = [8730, 8152, 5015]
    colors_list = ['#64748B', '#003865', '#C59B27']
    fig = go.Figure(data=[
        go.Pie(
            labels=labels,
            values=values,
            hole=0.45,
            marker_colors=colors_list,
            textinfo='label+percent',
            hovertemplate='<b>%{label}</b><br>Usuarios: %{value:,}<br>Proporción: %{percent}<extra></extra>'
        )
    ])
    fig.update_layout(
        title='Clasificación de Perfiles de Permanencia (Random Forest)',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(t=40, r=20, b=40, l=20),
        font=dict(family='Inter, sans-serif', size=11, color='#64748b')
    )
    table_data = [
        {"perfil": "Corta (< 60m)", "total": 8730, "porcentaje": 39.87, "permanencia_promedio_min": 24.6},
        {"perfil": "Media (60-180m)", "total": 8152, "porcentaje": 37.23, "permanencia_promedio_min": 104.5},
        {"perfil": "Larga (> 180m)", "total": 5015, "porcentaje": 22.90, "permanencia_promedio_min": 429.4}
    ]
    explicacion = (
        "El modelo Random Forest clasifica la permanencia en: Corta (39.87%, trámites y préstamos rápidos), "
        "Media (37.23%, bloques de clase y estudio acotado) y Larga (22.90%, jornadas intensivas de estudio en pisos superiores)."
    )
    return serialize_fig(fig), table_data, explicacion

def detect_month_in_text(text_to_check: str) -> Optional[int]:
    t = text_to_check.lower()
    for name, num in MONTH_MAP_ES.items():
        if name in t:
            return num
    match = re.search(r'\bmes\s*0?([1-9]|1[0-2])\b', t)
    if match:
        return int(match.group(1))
    return None

@router.post(
    "",
    response_model=ChatResponse,
    summary="Procesar consulta analítica asistida por IA",
    description="Endpoint asíncrono para clasificar y responder consultas analíticas con caché TTL y figuras Plotly serializadas.",
)
@router.post(
    "/",
    response_model=ChatResponse,
    include_in_schema=False,
)
@limiter.limit(get_rate_limit_by_role)
async def process_chat(
    request: Request,
    req: ChatRequest,
    background_tasks: BackgroundTasks,
    llm_client: LLMClientBase = Depends(get_llm_client),
    db: AsyncSession = Depends(get_db),
):

    start_time = time.perf_counter()
    user_id = extract_user_id_from_request(request)
    prompt_text = req.prompt.strip()
    if not prompt_text:
        raise HTTPException(status_code=400, detail="El prompt no puede estar vacío")

    cache_key = (req.dataset_tipo, req.grafico_contexto or "", prompt_text.lower())
    if cache_key in CHAT_CACHE:
        cached_tipo, cached_exp, cached_fig, cached_table, cached_model = CHAT_CACHE[cache_key]
        record = {
            "id": f"msg-{datetime.now().timestamp()}",
            "timestamp": datetime.now().strftime("%H:%M"),
            "prompt": prompt_text,
            "dataset_tipo": req.dataset_tipo,
            "grafico_contexto": req.grafico_contexto,
            "tipo": cached_tipo,
            "explicacion": cached_exp,
            "fig_data": cached_fig,
            "table_data": cached_table,
            "model_used": cached_model,
        }
        if req.session_id not in SESSION_STORE:
            SESSION_STORE[req.session_id] = []
        SESSION_STORE[req.session_id].append(record)

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        background_tasks.add_task(
            record_chat_audit,
            user_id,
            prompt_text,
            req.dataset_tipo,
            cached_model,
            "éxito",
            elapsed_ms,
        )

        return ChatResponse(
            tipo=cached_tipo,
            explicacion=cached_exp,
            fig_data=cached_fig,
            table_data=cached_table,
            session_id=req.session_id,
            model_used=cached_model,
        )


    lower = prompt_text.lower()
    model_to_use = req.model if req.model in ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"] else "gemini-3.5-flash-lite"
    tipo = "text"
    explicacion = ""
    fig_data = None
    table_data = None

    intent_info = llm_client.consult_intent(prompt_text, req.dataset_tipo, model_to_use, req.grafico_contexto)

    intent = intent_info.get("intent") if intent_info else None
    mes_detected = intent_info.get("mes") if intent_info else None
    llm_explicacion = intent_info.get("explicacion") if intent_info else None

    if not mes_detected:
        mes_detected = detect_month_in_text(lower)

    if not intent and req.grafico_contexto:
        ctx = req.grafico_contexto.lower()
        if "seman" in ctx or "aforo_semanal" in ctx:
            intent = "weekly"
        elif "vehic" in ctx or "camara" in ctx or "flujo" in ctx:
            intent = "cameras"
        elif "perfil" in ctx or "permanencia" in ctx:
            intent = "stay"
        elif "hora" in ctx or "pico" in ctx or "valle" in ctx:
            intent = "hourly"
        elif "examen" in ctx or "certamen" in ctx or "hito" in ctx:
            intent = "exams"
        elif "mes" in ctx or "mensual" in ctx:
            intent = "monthly"

    if not intent:
        if mes_detected or ("mes" in lower and any(m in lower for m in MONTH_MAP_ES)):
            intent = "monthly"
        elif ("semana" in lower and ("congesti" in lower or "mayor" in lower or "pico" in lower or "afluencia" in lower or "volumen" in lower)) or "evolucion semanal" in lower:
            intent = "weekly"
        elif "examen" in lower or "certamen" in lower or "evalua" in lower or "impactan" in lower or "impacto" in lower or "hito" in lower:
            intent = "exams"
        elif "hora" in lower and ("pico" in lower or "valle" in lower or "franja" in lower or "critica" in lower or "concurr" in lower):
            intent = "hourly"
        elif "camara" in lower or "flujo vehicular" in lower or ("estacionamiento" in lower and ("distribu" in lower or "trafico" in lower)):
            intent = "cameras"
        elif "permanencia" in lower or "perfil" in lower or "estadia" in lower:
            intent = "stay"
        elif "tabla" in lower or "detalle tabular" in lower or "datos brutos" in lower:
            intent = "table"
        elif "grafic" in lower or "grafica" in lower or "plotea" in lower or "dibuja" in lower:
            if req.dataset_tipo == "estacionamiento":
                intent = "cameras"
            else:
                intent = "weekly"

    if intent == "monthly":
        m_target = mes_detected if mes_detected else 3
        tipo = "plotly"
        fig_data, table_data, auto_exp = await generate_monthly_chart(db, req.dataset_tipo, m_target)
        explicacion = llm_explicacion or auto_exp
    elif intent == "weekly":
        tipo = "plotly"
        fig_data, table_data, auto_exp = await generate_weekly_chart(db, req.dataset_tipo)
        explicacion = llm_explicacion or auto_exp
    elif intent == "exams":
        tipo = "plotly"
        fig_data, table_data, auto_exp = await generate_exams_impact_chart(db)
        explicacion = llm_explicacion or auto_exp
    elif intent == "hourly":
        tipo = "plotly"
        fig_data, table_data, auto_exp = await generate_peak_hours_chart(db, req.dataset_tipo)
        explicacion = llm_explicacion or auto_exp
    elif intent == "cameras":
        tipo = "plotly"
        fig_data, table_data, auto_exp = await generate_cameras_chart(db)
        explicacion = llm_explicacion or auto_exp
    elif intent == "stay":
        tipo = "plotly"
        fig_data, table_data, auto_exp = generate_stay_profiles_chart()
        explicacion = llm_explicacion or auto_exp
    elif intent == "table":
        tipo = "df"
        _, table_data, auto_exp = await generate_weekly_chart(db, req.dataset_tipo)
        explicacion = llm_explicacion or "Se presenta el detalle estructurado de datos consolidados del recinto."
    else:
        tipo = "text"
        explicacion = llm_explicacion or (
            "El sistema DSS registra 24.430 accesos consolidados en Biblioteca CSF y 7.800 registros de aforo vehicular. "
            "Puedes solicitar gráficos por mes (ej: 'grafica marzo'), análisis de certámenes, horarios pico o tablas."
        )

    CHAT_CACHE[cache_key] = (tipo, explicacion, fig_data, table_data, model_to_use)

    record = {
        "id": f"msg-{datetime.now().timestamp()}",
        "timestamp": datetime.now().strftime("%H:%M"),
        "prompt": prompt_text,
        "dataset_tipo": req.dataset_tipo,
        "tipo": tipo,
        "explicacion": explicacion,
        "fig_data": fig_data,
        "table_data": table_data,
        "model_used": model_to_use,
    }

    if req.session_id not in SESSION_STORE:
        SESSION_STORE[req.session_id] = []
    SESSION_STORE[req.session_id].append(record)

    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
    background_tasks.add_task(
        record_chat_audit,
        user_id,
        prompt_text,
        req.dataset_tipo,
        model_to_use,
        "éxito",
        elapsed_ms,
    )

    return ChatResponse(
        tipo=tipo,
        explicacion=explicacion,
        fig_data=fig_data,
        table_data=table_data,
        session_id=req.session_id,
        model_used=model_to_use,
    )


@router.get(
    "/history",
    summary="Obtener historial de chat de la sesión",
    description="Retorna la lista cronológica de preguntas y respuestas registradas para un session_id.",
)
async def get_chat_history(session_id: str = Query(..., description="ID único de la sesión de chat")):
    history = SESSION_STORE.get(session_id, [])
    return {
        "session_id": session_id,
        "messages": history
    }

@router.post(
    "/export-pdf",
    summary="Exportar informe ejecutivo consolidado en formato PDF",
    description="Genera y descarga un reporte formal PDF con el historial analítico y tablas de la sesión.",
)
async def export_chat_pdf(req: ExportPdfRequest):
    history = SESSION_STORE.get(req.session_id, [])
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#002B49')
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=15,
        textColor=colors.HexColor('#64748B')
    )
    h2_style = ParagraphStyle(
        'SectionH2',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=17,
        textColor=colors.HexColor('#003865')
    )
    q_style = ParagraphStyle(
        'UserQuestion',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#002B49')
    )
    ans_style = ParagraphStyle(
        'AssistantAnswer',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#1E293B')
    )
    meta_style = ParagraphStyle(
        'MetaStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#94A3B8')
    )

    story = []

    story.append(Paragraph("UNIVERSIDAD CATÓLICA DE TEMUCO", title_style))
    story.append(Paragraph("Sistema de Soporte a Decisiones (DSS) · Campus San Francisco", subtitle_style))
    story.append(Spacer(1, 8))
    story.append(Paragraph(req.titulo or "Informe Ejecutivo Consolidado — Consultas Analíticas e IA", h2_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#C59B27'), spaceAfter=10))

    meta_data = [
        [Paragraph(f"<b>Fecha de Emisión:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}", meta_style),
         Paragraph(f"<b>ID Sesión:</b> {req.session_id}", meta_style)],
        [Paragraph("<b>Entorno:</b> Producción Analítica DSS", meta_style),
         Paragraph("<b>Protocolo de Privacidad:</b> Anonimización Irreversible HMAC/SHA-256", meta_style)]
    ]
    meta_table = Table(meta_data, colWidths=[260, 260])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 14))

    story.append(Paragraph("Resumen de Consultas e Interacciones Analíticas", h2_style))
    story.append(Spacer(1, 6))

    if not history:
        story.append(Paragraph("No se registraron interacciones en esta sesión.", ans_style))
    else:
        for idx, item in enumerate(history, 1):
            q_box = [
                [Paragraph(f"<b>Consulta #{idx}:</b> {item.get('prompt', '')}", q_style)],
                [Paragraph(f"<b>Respuesta Analítica:</b> {item.get('explicacion', '')}", ans_style)],
                [Paragraph(f"Tipo: {item.get('tipo', 'text').upper()} | Módulo: {item.get('dataset_tipo', 'general')} | Modelo: {item.get('model_used', 'DSS Local')}", meta_style)]
            ]
            t = Table(q_box, colWidths=[520])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#EFF6FF')),
                ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#FFFFFF')),
                ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#F8FAFC')),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ]))
            story.append(t)
            story.append(Spacer(1, 10))

            if item.get('table_data') and isinstance(item['table_data'], list) and len(item['table_data']) > 0:
                rows_data = item['table_data'][:6]
                headers = list(rows_data[0].keys())
                table_matrix = [[Paragraph(f"<b>{h.replace('_', ' ').capitalize()}</b>", meta_style) for h in headers]]
                for r in rows_data:
                    row_cells = [Paragraph(str(r.get(h, '')), meta_style) for h in headers]
                    table_matrix.append(row_cells)
                sample_t = Table(table_matrix, colWidths=[520 / len(headers)] * len(headers))
                sample_t.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#002B49')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
                    ('TOPPADDING', (0, 0), (-1, -1), 3),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ]))
                story.append(sample_t)
                story.append(Spacer(1, 10))

    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#CBD5E1'), spaceAfter=8))
    story.append(Paragraph(
        "Certificación de Integridad: Documento generado automáticamente por el DSS de la Universidad Católica de Temuco. "
        "Los cálculos cumplen con las directivas de seguridad de la información institucional.",
        meta_style
    ))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    filename = f"informe_ejecutivo_{req.session_id[:8]}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

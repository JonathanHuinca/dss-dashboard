import asyncio
import base64
import io
import logging
import uuid
from datetime import datetime
from types import SimpleNamespace
from typing import Optional
from xml.sax.saxutils import escape as escapar_xml
from fastapi import Response
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.chat_schemas import ExportPdfRequest
from app.services.servicio_chat_persistente import obtener_conversacion

logger = logging.getLogger(__name__)


async def generar_pdf_conversacion(
    db: AsyncSession,
    req: ExportPdfRequest,
    usuario_id: int,
) -> Response:
    """Genera un reporte PDF formal institucional con el historial analítico, gráficos incrustados y tablas."""
    mensajes = []
    titulo_conversacion = req.titulo or "Informe Ejecutivo Consolidado — Consultas Analíticas e IA"
    if req.conversacion_id:
        try:
            conv_uuid = uuid.UUID(req.conversacion_id)
            conv = await obtener_conversacion(db, conv_uuid, usuario_id, cargar_mensajes=True)
            if conv:
                mensajes = conv.mensajes
                if conv.titulo and not req.titulo:
                    titulo_conversacion = f"Informe Ejecutivo DSS UCT — {conv.titulo}"
        except Exception:
            pass

    mensajes_planos = [
        SimpleNamespace(
            id=getattr(m, "id", None),
            rol=getattr(m, "rol", None),
            contenido=getattr(m, "contenido", None),
            tipo=getattr(m, "tipo", None),
            herramienta=getattr(m, "herramienta", None),
            modelo=getattr(m, "modelo", None),
        )
        for m in mensajes
    ]
    pdf_bytes = await asyncio.to_thread(_renderizar_pdf_sync, req, titulo_conversacion, mensajes_planos)
    id_sesion_txt = str(req.conversacion_id or req.session_id or "consulta")
    sufijo_archivo = "".join(c for c in id_sesion_txt[:8] if c.isalnum() or c in ("-", "_")) or "consulta"
    filename = f"informe_ejecutivo_{sufijo_archivo}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


def _renderizar_pdf_sync(
    req: ExportPdfRequest,
    titulo_conversacion: str,
    mensajes: list,
) -> bytes:
    """Construye el documento ReportLab en hilo trabajador sin bloquear el event loop."""
    buffer = io.BytesIO()
    img_buffers: list[io.BytesIO] = []
    try:
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36,
        )
        story = _construir_story_pdf_sync(req, titulo_conversacion, mensajes, img_buffers)
        doc.build(story)
        return buffer.getvalue()
    finally:
        for ib in img_buffers:
            try:
                ib.close()
            except Exception:
                pass
        buffer.close()


def _construir_story_pdf_sync(
    req: ExportPdfRequest,
    titulo_conversacion: str,
    mensajes: list,
    img_buffers: list[io.BytesIO],
) -> list:
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=17,
        leading=21,
        textColor=colors.HexColor('#002B49'),
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#64748B'),
    )
    h2_style = ParagraphStyle(
        'SectionH2',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#003865'),
    )
    q_style = ParagraphStyle(
        'UserQuestion',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#002B49'),
    )
    ans_style = ParagraphStyle(
        'AssistantAnswer',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#1E293B'),
    )
    meta_style = ParagraphStyle(
        'MetaStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#94A3B8'),
    )

    story = []

    story.append(Paragraph("UNIVERSIDAD CATÓLICA DE TEMUCO", title_style))
    story.append(Paragraph("Sistema de Soporte a Decisiones (DSS) · Campus San Francisco", subtitle_style))
    story.append(Spacer(1, 6))
    story.append(Paragraph(escapar_xml(str(titulo_conversacion)), h2_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#C59B27'), spaceAfter=8))

    recinto_nombre = "Estacionamiento CSF" if req.espacio_id == 2 else "Biblioteca CSF"
    id_sesion_txt = str(req.conversacion_id or req.session_id or "consulta")
    meta_data = [
        [Paragraph(f"<b>Fecha de Emisión:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}", meta_style),
         Paragraph(f"<b>Módulo Institucional:</b> {escapar_xml(recinto_nombre)}", meta_style)],
        [Paragraph(f"<b>ID Sesión / Conversación:</b> {escapar_xml(id_sesion_txt)}", meta_style),
         Paragraph("<b>Privacidad:</b> Anonimización Irreversible SHA-256 (Ley N° 21.719)", meta_style)]
    ]
    meta_table = Table(meta_data, colWidths=[270, 270])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # Caso 1: Exportación directa de una consulta individual específica
    if req.consulta_texto and req.respuesta_texto:
        story.append(Paragraph("Detalle de la Consulta Analítica", h2_style))
        story.append(Spacer(1, 4))

        consulta_segura = escapar_xml(str(req.consulta_texto))
        respuesta_segura = escapar_xml(str(req.respuesta_texto)).replace(chr(10), '<br/>')
        q_box = [
            [Paragraph(f"<b>Pregunta / Instrucción:</b> {consulta_segura}", q_style)],
            [Paragraph(f"<b>Respuesta e Interpretación Oficial:</b><br/>{respuesta_segura}", ans_style)],
            [Paragraph("Fuente: Base de Datos Institucional UCT · Verificado por Asistente DSS", meta_style)]
        ]
        t = Table(q_box, colWidths=[540])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#EFF6FF')),
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#FFFFFF')),
            ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#F8FAFC')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(t)
        story.append(Spacer(1, 10))

        # Incrustar gráfico si viene en base64
        if req.graficos_b64:
            b64_str = req.graficos_b64.get("single") or req.graficos_b64.get("1") or list(req.graficos_b64.values())[0]
            if b64_str:
                try:
                    raw_b64 = b64_str.split(",")[-1]
                    img_bytes = base64.b64decode(raw_b64)
                    img_buf = io.BytesIO(img_bytes)
                    story.append(Paragraph("<b>Visualización Analítica Generada:</b>", h2_style))
                    story.append(Spacer(1, 4))
                    story.append(RLImage(img_buf, width=540, height=260))
                    story.append(Spacer(1, 10))
                except Exception as img_err:
                    logger.warning(f"Error procesando imagen para PDF: {img_err}")

        # Incrustar datos tabulares si vienen
        if req.datos_tabla and isinstance(req.datos_tabla, list) and len(req.datos_tabla) > 0:
            story.append(Paragraph(f"<b>Registro Tabular Detallado ({len(req.datos_tabla)} filas):</b>", h2_style))
            story.append(Spacer(1, 4))
            headers = list(req.datos_tabla[0].keys())
            table_rows = [[Paragraph(f"<b>{escapar_xml(str(h).replace('_', ' ').title())}</b>", meta_style) for h in headers]]
            for r in req.datos_tabla[:30]:
                table_rows.append([Paragraph(escapar_xml(str(r.get(h, ''))), ans_style) for h in headers])
            col_w = 540 / max(1, len(headers))
            dt_table = Table(table_rows, colWidths=[col_w] * len(headers))
            dt_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#002B49')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]))
            story.append(dt_table)

    # Caso 2: Conversación completa
    elif not mensajes:
        story.append(Paragraph("No se registraron interacciones en esta conversación.", ans_style))
    else:
        story.append(Paragraph("Resumen Cronológico de Consultas", h2_style))
        story.append(Spacer(1, 6))

        pregunta_actual = ""
        indice_q = 1
        for m in mensajes:
            if m.rol == "user":
                pregunta_actual = m.contenido
            elif m.rol == "assistant":
                preg_segura = escapar_xml(str(pregunta_actual or 'Consulta sin registro'))
                resp_segura = escapar_xml(str(m.contenido or '')).replace(chr(10), '<br/>')
                tipo_seguro = escapar_xml(str(m.tipo or '').upper())
                herr_segura = escapar_xml(str(m.herramienta or 'Directa'))
                mod_seguro = escapar_xml(str(m.modelo or 'Gemini DSS'))
                q_box = [
                    [Paragraph(f"<b>Consulta #{indice_q}:</b> {preg_segura}", q_style)],
                    [Paragraph(f"<b>Respuesta Analítica:</b><br/>{resp_segura}", ans_style)],
                    [Paragraph(f"Tipo: {tipo_seguro} | Herramienta: {herr_segura} | Modelo: {mod_seguro}", meta_style)]
                ]
                t = Table(q_box, colWidths=[540])
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
                story.append(Spacer(1, 6))

                # Si hay imagen para esta consulta
                if req.graficos_b64:
                    b64_str = (
                        req.graficos_b64.get(str(m.id))
                        or req.graficos_b64.get(str(indice_q))
                        or req.graficos_b64.get(f"consulta_{indice_q}")
                    )
                    if b64_str:
                        try:
                            raw_b64 = b64_str.split(",")[-1]
                            img_bytes = base64.b64decode(raw_b64)
                            img_buf = io.BytesIO(img_bytes)
                            img_buffers.append(img_buf)
                            story.append(RLImage(img_buf, width=540, height=250))
                            story.append(Spacer(1, 8))
                        except Exception as img_err:
                            logger.warning(f"Error procesando imagen para PDF: {img_err}")

                story.append(Spacer(1, 8))
                indice_q += 1
                pregunta_actual = ""

    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#CBD5E1'), spaceAfter=8))
    story.append(Paragraph(
        "Certificación de Integridad: Documento generado automáticamente por el DSS de la Universidad Católica de Temuco. "
        "Los cálculos cumplen con las directivas de seguridad de la información institucional (Ley N° 21.719).",
        meta_style
    ))
    return story

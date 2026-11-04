import asyncio
import logging
import re
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.adapters.base import CalendarEventDTO
from app.services.calendar_service import CalendarService

logger = logging.getLogger(__name__)

UCT_CALENDAR_URL = "https://www.uct.cl/calendario-academico/"

def _parse_chile_date(d_str: str) -> Optional[date]:
    d_str = d_str.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(d_str, fmt).date()
        except ValueError:
            pass
    return None


def analizar_fechas_calendario(fecha_texto: str) -> List[date]:
    """
    Analiza una cadena de texto proveniente del calendario y devuelve la lista de fechas correspondientes.
    Diferencia rigurosamente fechas individuales con guiones (ej. '25-12-2026') de rangos de fechas
    (ej. '01-03-2026 - 15-03-2026', '01 al 05-04-2026', '10/05/2026 a 12/05/2026').
    """
    texto = fecha_texto.strip()
    if not texto:
        return []

    # 1. Caso fecha individual directa: dd/mm/yyyy, dd-mm-yyyy, yyyy-mm-dd
    d_single = _parse_chile_date(texto)
    if d_single:
        return [d_single]

    # 2. Caso rango con dos fechas completas: 'dd-mm-yyyy - dd-mm-yyyy' o 'dd/mm/yyyy al dd/mm/yyyy'
    patron_dos_fechas = re.compile(
        r'^(\d{1,2}[/-]\d{1,2}[/-]\d{4})\s*(?:\s+[-–—]\s+|[-–—]|\s+al?\s+|\s+hasta\s+)\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})$',
        re.IGNORECASE
    )
    m_dos = patron_dos_fechas.match(texto)
    if m_dos:
        d_start = _parse_chile_date(m_dos.group(1))
        d_end = _parse_chile_date(m_dos.group(2))
        if d_start and d_end and d_start <= d_end:
            delta_days = (d_end - d_start).days
            if delta_days <= 120:
                return [d_start + timedelta(days=i) for i in range(delta_days + 1)]
            return [d_start, d_end]

    # 3. Caso rango con día inicial y fecha completa final: '01 al 05-04-2026' o '15 - 20/07/2026'
    patron_dia_a_fecha = re.compile(
        r'^(\d{1,2})\s*(?:\s+[-–—]\s+|[-–—]|\s+al?\s+|\s+hasta\s+)\s*(\d{1,2})[/-](\d{1,2})[/-](\d{4})$',
        re.IGNORECASE
    )
    m_dia = patron_dia_a_fecha.match(texto)
    if m_dia:
        try:
            dia_inicio = int(m_dia.group(1))
            dia_fin = int(m_dia.group(2))
            mes = int(m_dia.group(3))
            anio = int(m_dia.group(4))
            d_start = date(anio, mes, dia_inicio)
            d_end = date(anio, mes, dia_fin)
            if d_start <= d_end:
                delta_days = (d_end - d_start).days
                if delta_days <= 120:
                    return [d_start + timedelta(days=i) for i in range(delta_days + 1)]
                return [d_start, d_end]
        except ValueError:
            pass

    # 4. Caso separador de rango explícito (' - ', ' — ', ' al ', ' a ')
    delimitadores = [r'\s+[-–—]\s+', r'\s+al?\s+', r'\s+hasta\s+']
    for delim in delimitadores:
        partes = re.split(delim, texto, flags=re.IGNORECASE)
        if len(partes) == 2:
            d_start = _parse_chile_date(partes[0])
            d_end = _parse_chile_date(partes[1])
            if d_start and d_end and d_start <= d_end:
                delta_days = (d_end - d_start).days
                if delta_days <= 120:
                    return [d_start + timedelta(days=i) for i in range(delta_days + 1)]
                return [d_start, d_end]

    # 5. Búsqueda de todas las fechas individuales contenidas en el texto
    fechas_encontradas = re.findall(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b', texto)
    if len(fechas_encontradas) == 1:
        d = _parse_chile_date(fechas_encontradas[0])
        return [d] if d else []
    elif len(fechas_encontradas) >= 2:
        d_start = _parse_chile_date(fechas_encontradas[0])
        d_end = _parse_chile_date(fechas_encontradas[1])
        if d_start and d_end and d_start <= d_end:
            delta_days = (d_end - d_start).days
            if delta_days <= 120:
                return [d_start + timedelta(days=i) for i in range(delta_days + 1)]
            return [d_start, d_end]

    return []


def _classify_event_flags(desc: str) -> dict:
    d_lower = desc.lower()

    # Descarte explícito de trámites, becas, notas y procesos no presenciales (datos basura)
    discard_keywords = [
        "beca", "fuas", "gratuidad", "crédito", "credito", "recaudación", "recaudacion",
        "pagaré", "pagare", "convenio de pago", "arancel", "convalidaci", "reincorporaci",
        "renuncia académica", "renuncia academica", "admisión especial", "admision especial",
        "calificación", "calificacion", "ingreso de notas", "entrega de actas", "bitácora",
        "bitacora", "semillero", "adjudicación de proyectos", "adjudicacion de proyectos",
        "talleres recreativos", "solicitud de cursos", "rap", "evaluación socioeconómica",
        "evaluacion socioeconomica", "franja de integración", "franja de integracion",
        "reunión de comité", "reunion de comite", "adquisición de recursos", "adquisicion de recursos",
        "desempeño académico", "desempeno academico", "convocatoria proyectos"
    ]

    # Feriados Oficiales y Religiosos
    holiday_keywords = [
        "feriado", "año nuevo", "viernes santo", "sábado santo", "sabado santo", "dia del trabajador", "día del trabajador",
        "glorias navales", "pueblos indígenas", "pueblos indigenas", "san pedro", "san pablo", "virgen del carmen",
        "asunción de la virgen", "asuncion de la virgen", "fiestas patrias", "glorias del ejército", "glorias del ejercito",
        "encuentro de dos mundos", "iglesias evangélicas", "iglesias evangelicas", "todos los santos",
        "inmaculada concepción", "inmaculada concepcion", "navidad", "plebiscito", "elección", "elecciones", "votación"
    ]
    is_holiday = any(k in d_lower for k in holiday_keywords)

    # Recesos Académicos y Vacaciones (Alumnos y Administrativos)
    break_keywords = [
        "receso", "vacaciones", "receso de invierno", "vacaciones de invierno", "receso de fiestas patrias",
        "receso universitario", "receso administrativo", "vacaciones de funcionarios", "semana de receso",
        "receso de verano", "vacaciones estudiantes", "feriado legal funcionarios"
    ]
    is_break = any(k in d_lower for k in break_keywords)

    # Suspensión de Actividades y Jornadas de Salida Anticipada (ej. 13:00 hrs)
    suspension_keywords = [
        "suspensión de actividades", "suspension de actividades", "sin atención", "recinto cerrado",
        "salida anticipada", "término de jornada", "termino de jornada", "jornada hasta las",
        "13:00", "13 hrs", "13:00 hrs", "14:00", "salida a las 13", "suspensión desde las 13",
        "víspera de navidad", "vispera de navidad", "víspera de año nuevo", "vispera de ano nuevo",
        "celebración de la víspera", "celebracion de la vispera", "sin actividades"
    ]
    suspension_actividades = any(k in d_lower for k in suspension_keywords) or is_holiday

    # Períodos Solemnes de Exámenes y Certámenes (Campaña 24 Horas)
    exam_keywords = [
        "examen", "exámenes", "examenes", "certamen", "certámenes", "certamenes", "evaluación solemne", "evaluacion solemne",
        "evaluación final", "evaluaciones finales", "evaluacion final", "período evaluaciones finales",
        "periodo evaluaciones finales", "campaña 24", "campana 24", "rendición de certamen", "rendicion de certamen",
        "semana de exámenes", "semana de examenes"
    ]
    is_exam_period = any(k in d_lower for k in exam_keywords)

    # Hitos Oficiales de Clases e Inducción de Novatos
    milestone_keywords = [
        "inicio de clases", "inicio clases", "término de clases", "termino de clases",
        "inicio de semestre", "inicio primer semestre", "inicio segundo semestre",
        "cierre de semestre", "término primer semestre", "termino primer semestre",
        "término segundo semestre", "termino segundo semestre", "período lectivo", "periodo lectivo",
        "novato", "novatos", "inducción", "induccion", "recepción estudiantes", "recepcion estudiantes",
        "bienvenida novatos", "semana de inducción", "semana de induccion", "mechón", "mechona"
    ]
    is_class_milestone = any(k in d_lower for k in milestone_keywords)

    # Si contiene palabras de descarte y no es un feriado/receso estricto, descartar
    if any(dk in d_lower for dk in discard_keywords) and not (is_holiday or is_break):
        is_class_milestone = False
        is_exam_period = False
        suspension_actividades = False

    es_relevante = bool(is_holiday or is_break or suspension_actividades or is_exam_period or is_class_milestone)

    return {
        "is_holiday": is_holiday,
        "is_break": is_break,
        "suspension_actividades": suspension_actividades,
        "is_exam_period": is_exam_period,
        "is_class_milestone": is_class_milestone,
        "es_relevante": es_relevante,
    }


def obtener_feriado_oficial_chile(d: date) -> Optional[str]:
    """
    Retorna el nombre del feriado legal oficial chileno para fechas fijas o universales,
    garantizando que feriados nacionales (como el 12 de octubre o 1 de mayo) siempre se registren.
    """
    feriados_fijos = {
        (1, 1): "Feriado. Año Nuevo",
        (5, 1): "Feriado. Día del Trabajo",
        (5, 21): "Feriado. Día de las Glorias Navales",
        (6, 21): "Feriado. Día Nacional de los Pueblos Indígenas",
        (6, 29): "Feriado. San Pedro y San Pablo",
        (7, 16): "Feriado. Virgen del Carmen",
        (8, 15): "Feriado. Asunción de la Virgen",
        (9, 18): "Feriado. Fiestas Patrias",
        (9, 19): "Feriado. Día de las Glorias del Ejército",
        (10, 12): "Feriado. Encuentro de Dos Mundos",
        (10, 31): "Feriado. Día de las Iglesias Evangélicas y Protestantes",
        (11, 1): "Feriado. Día de Todos los Santos",
        (12, 8): "Feriado. Inmaculada Concepción",
        (12, 25): "Feriado. Navidad",
    }
    return feriados_fijos.get((d.month, d.day))


async def scrape_and_sync_uct_calendar(session: AsyncSession) -> dict:
    """
    Descarga y parsea el calendario académico oficial desde https://www.uct.cl/calendario-academico/
    e inserta/actualiza los eventos en la tabla calendario_academico.
    """
    logger.info(f"[CalendarScraper] Iniciando descarga desde {UCT_CALENDAR_URL}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-CL,es;q=0.9,en;q=0.8"
    }
    
    async with httpx.AsyncClient(timeout=25.0, follow_redirects=True, headers=headers) as client:
        resp = await client.get(UCT_CALENDAR_URL)
        if resp.status_code != 200:
            raise RuntimeError(f"Error HTTP {resp.status_code} al conectar con {UCT_CALENDAR_URL}")
        html = resp.text

    # Cada fila del calendario tiene 3 celdas div class="td"
    row_pattern = re.compile(
        r'<div class="tr">\s*<div class="td">(.*?)</div[^>]*>\s*<div class="td">(.*?)</div[^>]*>\s*<div class="td">(.*?)</div[^>]*>',
        re.DOTALL | re.IGNORECASE
    )
    rows = row_pattern.findall(html)
    logger.info(f"[CalendarScraper] Se encontraron {len(rows)} filas de eventos en el HTML.")

    events_by_date: Dict[date, CalendarEventDTO] = {}

    for raw_fecha, _, raw_desc in rows:
        fecha_clean = re.sub(r'<[^>]+>', '', raw_fecha).strip()
        desc_clean = re.sub(r'<[^>]+>', '', raw_desc).strip()

        if not fecha_clean or not desc_clean:
            continue

        flags = _classify_event_flags(desc_clean)
        if not flags["es_relevante"]:
            continue

        # Determinar si es fecha única o rango mediante el analizador sintáctico
        dates_to_add = analizar_fechas_calendario(fecha_clean)


        for d_target in dates_to_add:
            feriado_legal = obtener_feriado_oficial_chile(d_target)
            is_hol = flags["is_holiday"] or bool(feriado_legal)
            desc_final = desc_clean
            if feriado_legal and feriado_legal.lower() not in desc_clean.lower():
                desc_final = f"{feriado_legal} • {desc_clean}"

            if d_target not in events_by_date:
                events_by_date[d_target] = CalendarEventDTO(
                    fecha=d_target,
                    is_holiday=is_hol,
                    is_break=flags["is_break"],
                    is_exam_period=flags["is_exam_period"],
                    is_class_milestone=flags["is_class_milestone"],
                    suspension_actividades=flags["suspension_actividades"] or is_hol,
                    descripcion=desc_final,
                    fuente="scraping",
                )
            else:
                existing = events_by_date[d_target]
                existing.is_holiday = existing.is_holiday or is_hol
                existing.is_break = existing.is_break or flags["is_break"]
                existing.is_exam_period = existing.is_exam_period or flags["is_exam_period"]
                existing.is_class_milestone = existing.is_class_milestone or flags["is_class_milestone"]
                existing.suspension_actividades = existing.suspension_actividades or flags["suspension_actividades"] or is_hol
                if desc_clean not in existing.descripcion:
                    existing.descripcion = f"{existing.descripcion} / {desc_clean}"

    event_list = list(events_by_date.values())
    calendar_service = CalendarService()
    await calendar_service.bulk_insert_events(session, event_list)

    # Contadores de resumen
    total_holidays = sum(1 for e in event_list if e.is_holiday)
    total_breaks = sum(1 for e in event_list if e.is_break)
    total_suspensions = sum(1 for e in event_list if e.suspension_actividades)
    total_exams = sum(1 for e in event_list if e.is_exam_period)

    logger.info(
        f"[CalendarScraper] Sincronización exitosa: {len(event_list)} días registrados. "
        f"Feriados: {total_holidays}, Recesos: {total_breaks}, Suspensiones: {total_suspensions}, Exámenes: {total_exams}."
    )

    return {
        "status": "success",
        "total_days": len(event_list),
        "total_holidays": total_holidays,
        "total_breaks": total_breaks,
        "total_suspensions": total_suspensions,
        "total_exams": total_exams,
        "fuente": UCT_CALENDAR_URL,
        "timestamp": datetime.now().isoformat(),
    }

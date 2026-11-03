import logging
import re
from datetime import date, datetime
from typing import Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.services.attendance_service import AttendanceService
from app.services.vehicle_service import VehicleService
from app.domain.models import CalendarioAcademico

logger = logging.getLogger(__name__)

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


def detect_months_in_text(text_to_check: str) -> List[int]:
    """Detecta meses en texto en lenguaje natural."""
    t = text_to_check.lower()
    found_months = []
    for word in re.findall(r'\b[a-z]+\b', t):
        if word in MONTH_MAP_ES and MONTH_MAP_ES[word] not in found_months:
            found_months.append(MONTH_MAP_ES[word])
    for m in re.finditer(r'\bmes\s*0?([1-9]|1[0-2])\b', t):
        num = int(m.group(1))
        if num not in found_months:
            found_months.append(num)
    return found_months


async def obtener_anio_activo_espacio(db: AsyncSession, espacio_id: int) -> int:
    """Obtiene el año más reciente con registros en la base de datos o fallback al actual."""
    try:
        if espacio_id == 2:
            return await VehicleService.get_latest_year(db, espacio_id=2)
        return await AttendanceService.get_latest_year(db, espacio_id=1)
    except Exception:
        return datetime.now().year


def extraer_o_normalizar_fechas(
    f_ini_raw: Any,
    f_fin_raw: Any,
    prompt_texto: str,
    anio_defecto: int = 2026,
) -> tuple[Optional[date], Optional[date]]:
    """Normaliza fechas desde argumentos o expresiones de lenguaje natural."""
    d_ini = None
    d_fin = None

    texto = prompt_texto.lower()
    match_anio = re.search(r'\b(20\d{2})\b', texto)
    anio_objetivo = int(match_anio.group(1)) if match_anio else anio_defecto

    if f_ini_raw:
        try:
            d_ini = date.fromisoformat(str(f_ini_raw)[:10])
            if d_ini.year != anio_objetivo:
                d_ini = date(anio_objetivo, d_ini.month, d_ini.day)
        except Exception:
            pass
    if f_fin_raw:
        try:
            d_fin = date.fromisoformat(str(f_fin_raw)[:10])
            if d_fin.year != anio_objetivo:
                d_fin = date(anio_objetivo, d_fin.month, d_fin.day)
        except Exception:
            pass

    if not d_ini or not d_fin:
        meses_map = {
            "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
            "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
            "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
            "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
        }
        match_semana = re.search(r'\b(?:semana|sem|w)\s*0?([1-9]|[1-4][0-9]|5[0-3])\b', texto)
        if match_semana:
            num_sem = int(match_semana.group(1))
            try:
                if not d_ini:
                    d_ini = date.fromisocalendar(anio_objetivo, num_sem, 1)
                if not d_fin:
                    d_fin = date.fromisocalendar(anio_objetivo, num_sem, 7)
            except Exception:
                pass

        if not d_ini or not d_fin:
            match_rango = re.search(r'(?:del?\s+)?(\d{1,2})(?:\s+de\s+([a-záéíóú]+))?\s+(?:al?|hasta)\s+(?:el\s+)?(\d{1,2})\s+de\s+([a-záéíóú]+)', texto)
            if match_rango:
                dia1 = int(match_rango.group(1))
                mes1_str = match_rango.group(2)
                dia2 = int(match_rango.group(3))
                mes2_str = match_rango.group(4)
                mes2 = meses_map.get(mes2_str, 10)
                mes1 = meses_map.get(mes1_str, mes2) if mes1_str else mes2
                try:
                    if not d_ini:
                        d_ini = date(anio_objetivo, mes1, dia1)
                    if not d_fin:
                        d_fin = date(anio_objetivo, mes2, dia2)
                except Exception:
                    pass
            else:
                for mes_nombre, mes_num in meses_map.items():
                    if len(mes_nombre) > 3 and mes_nombre in texto:
                        if not d_ini:
                            d_ini = date(anio_objetivo, mes_num, 1)
                        if not d_fin:
                            if mes_num in [1, 3, 5, 7, 8, 10, 12]:
                                ultimo_dia = 31
                            elif mes_num == 2:
                                ultimo_dia = 28
                            else:
                                ultimo_dia = 30
                            d_fin = date(anio_objetivo, mes_num, ultimo_dia)
                        break

    return d_ini, d_fin


async def obtener_contexto_calendario_rango(
    db: AsyncSession,
    d_ini: Optional[date],
    d_fin: Optional[date],
) -> List[str]:
    """Recupera hitos académicos institucionales en el rango de fechas indicado."""
    if not d_ini or not d_fin:
        return []
    try:
        query = select(CalendarioAcademico).where(
            CalendarioAcademico.fecha >= d_ini,
            CalendarioAcademico.fecha <= d_fin
        ).order_by(CalendarioAcademico.fecha.asc())
        rows = (await db.execute(query)).scalars().all()
        hitos = []
        for r in rows:
            etiquetas = []
            if r.is_break:
                etiquetas.append("SEMANA DE RECESO")
            if r.is_holiday:
                etiquetas.append("FERIADO OFICIAL")
            if r.suspension_actividades:
                etiquetas.append("SUSPENSIÓN DE ACTIVIDADES")
            if r.is_exam_period:
                etiquetas.append("PERÍODO DE EXÁMENES")
            if r.is_strike_federado or r.is_strike_carrera:
                etiquetas.append("PARO")
            if getattr(r, "is_class_milestone", False):
                etiquetas.append("HITO DE CLASES")
            desc = r.descripcion.strip() if r.descripcion else ""
            etq_str = f" [{', '.join(etiquetas)}]" if etiquetas else ""
            if desc or etiquetas:
                hitos.append(f"- {r.fecha.strftime('%d/%m/%Y (%A)')}: {desc}{etq_str}")
        return hitos
    except Exception as e:
        logger.warning(f"Error consultando calendario académico: {e}")
        return []


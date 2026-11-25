import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_, select

from app.services.attendance_service import AttendanceService, obtener_capacidades_salas_cacheadas
from app.services.vehicle_service import VehicleService
from app.domain.models import CalendarioAcademico, ContingenciaAcademica
from app.domain.config_models import HorarioOperacion

logger = logging.getLogger(__name__)

ETIQUETAS_CONTINGENCIA_CHAT = {
    "paro_federado": "Paro Estudiantil FEUCT",
    "paro_carrera": "Paro por Carrera",
    "suspension_sala": "Suspensión de sala / sector",
    "toma_campus": "Toma de campus",
    "climatica": "Contingencia climática",
    "duelo": "Duelo institucional",
    "falla_sensor": "Falla de sensor / torniquete",
    "apertura_manual": "Apertura manual sin marcaje",
    "mantencion_cierre": "Cierre / mantención",
    "sin_demanda": "Sin afluencia confirmada",
    "otro": "Observación operativa",
}

ETIQUETAS_SUBESPACIO_CHAT = {
    "sala_1": "Sala 1 (CSF02)",
    "sala_2": "Sala 2 (CSF04 Pecera)",
    "csf11": "Estacionamiento CSF11",
    "csf21": "Estacionamiento CSF21",
    "chs01": "Estacionamiento CHS01",
}


def _parsear_config_dias(raw_cfg: Any) -> dict:
    if isinstance(raw_cfg, dict):
        return raw_cfg
    if isinstance(raw_cfg, str) and raw_cfg.strip():
        try:
            data = json.loads(raw_cfg)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _formatear_horario_regular_biblioteca(horarios_regulares: List[HorarioOperacion]) -> tuple[str, str, str]:
    por_sala: dict[str, str] = {}
    cierre_diurno_lj = "20:30"
    cierre_diurno_v = "20:30"
    for h in horarios_regulares or []:
        if (getattr(h, "tipo_horario", "") or "") != "regular" or not getattr(h, "activo", True):
            continue
        sub = (getattr(h, "subespacio", None) or "todos").strip().lower()
        cfg = _parsear_config_dias(getattr(h, "configuracion_dias", None))
        lun = cfg.get("lunes") or {}
        vie = cfg.get("viernes") or {}
        sab = cfg.get("sabado") or {}
        ap_lj = str(lun.get("apertura") or getattr(h, "hora_apertura", "08:30") or "08:30")
        ci_lj = str(lun.get("cierre") or getattr(h, "hora_cierre", "20:30") or "20:30")
        ap_v = str(vie.get("apertura") or ap_lj)
        ci_v = str(vie.get("cierre") or ci_lj)
        tramo = f"L-J {ap_lj}–{ci_lj}, Vie {ap_v}–{ci_v}"
        if sab.get("abierto"):
            tramo += f", Sáb {sab.get('apertura', '10:30')}–{sab.get('cierre', '15:00')}"
        if sub in ("sala_1", "sala1"):
            por_sala.setdefault("Sala 1", tramo)
            cierre_diurno_lj = ci_lj
        elif sub in ("sala_2", "sala2"):
            por_sala.setdefault("Sala 2", tramo)
        else:
            por_sala.setdefault("General", tramo)
            cierre_diurno_lj = ci_lj
    if por_sala:
        resumen = " | ".join(f"{k}: {v}" for k, v in por_sala.items())
        return resumen, cierre_diurno_lj, cierre_diurno_v
    return "Horario regular L-J 08:30–20:30, Vie 08:30–19:30 hrs", cierre_diurno_lj, cierre_diurno_v


def _formatear_horario_24h_dinamico(
    h: HorarioOperacion,
    cap_s2: int,
    hora_cierre_diurno_lj: str = "20:30",
    hora_cierre_diurno_v: str = "20:30",
) -> str:
    cfg = _parsear_config_dias(getattr(h, "configuracion_dias", None))
    cierre_lj = None
    for d_key in ("lunes", "martes", "miercoles", "jueves"):
        d_cfg = cfg.get(d_key) or {}
        if d_cfg.get("abierto") and d_cfg.get("cierre"):
            cierre_lj = str(d_cfg["cierre"])
            break
    cierre_lj = cierre_lj or str(getattr(h, "hora_cierre", None) or "07:00")
    vie_cfg = cfg.get("viernes") or {}
    cierre_v = str(vie_cfg.get("cierre") or cierre_lj) if vie_cfg else cierre_lj
    sab_cfg = cfg.get("sabado") or {}
    txt_sab = (
        f"; Sábado {sab_cfg.get('apertura', '10:30')}–{sab_cfg.get('cierre', '15:00')} hrs"
        if sab_cfg.get("abierto")
        else ""
    )
    desc = getattr(h, "descripcion", None) or "Campaña Horario 24 Horas"
    return (
        f"{desc} (Sala 2 Pecera CSF04, capacidad {cap_s2} asientos; "
        f"régimen continuo con extensión nocturna L-J {hora_cierre_diurno_lj}–{cierre_lj} hrs día sig. "
        f"y Viernes {hora_cierre_diurno_v}–{cierre_v} hrs día sig.{txt_sab})"
    )

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


def _descripcion_oficial_calendario(descripcion: Optional[str]) -> str:
    if not descripcion:
        return ""
    oficiales = [
        seg.strip()
        for seg in str(descripcion).split("|")
        if seg.strip() and not seg.strip().startswith("[")
    ]
    return " | ".join(oficiales)


def _formatear_tramo_contingencia(hora_inicio: Optional[str], hora_fin: Optional[str]) -> str:
    h_ini = (hora_inicio or "").strip()
    h_fin = (hora_fin or "").strip()
    if h_ini and h_fin:
        return f" ({h_ini}–{h_fin} hrs)"
    if h_ini:
        return f" (desde {h_ini} hrs)"
    if h_fin:
        return f" (hasta {h_fin} hrs)"
    return ""


async def obtener_contexto_calendario_rango(
    db: AsyncSession,
    d_ini: Optional[date],
    d_fin: Optional[date],
    espacio_id: Optional[int] = 1,
) -> List[str]:
    """Recupera hitos académicos e institucionales en el rango de fechas indicado."""
    if not d_ini or not d_fin:
        return []
    try:
        query_cont = select(ContingenciaAcademica).where(
            ContingenciaAcademica.fecha_inicio <= d_fin,
            ContingenciaAcademica.fecha_fin >= d_ini,
            or_(ContingenciaAcademica.espacio_id.is_(None), ContingenciaAcademica.espacio_id == espacio_id),
        ).order_by(ContingenciaAcademica.fecha_inicio.asc())
        contingencias = (await db.execute(query_cont)).scalars().all()
        fechas_en_contingencias: set[date] = set()
        for c in contingencias:
            f_cur = max(c.fecha_inicio, d_ini)
            f_lim = min(c.fecha_fin, d_fin)
            while f_cur <= f_lim:
                fechas_en_contingencias.add(f_cur)
                f_cur += timedelta(days=1)

        query = select(CalendarioAcademico).where(
            CalendarioAcademico.fecha >= d_ini,
            CalendarioAcademico.fecha <= d_fin
        ).order_by(CalendarioAcademico.fecha.asc())
        rows = (await db.execute(query)).scalars().all()
        hitos = []
        for r in rows:
            desc_oficial = _descripcion_oficial_calendario(r.descripcion)
            desc_lower = desc_oficial.lower()
            es_cont_manual = str(getattr(r, "fuente", "") or "") == "contingencia_manual"
            tiene_hito_oficial = bool(
                r.is_holiday
                or r.is_break
                or r.is_exam_period
                or getattr(r, "is_class_milestone", False)
            )
            if (es_cont_manual or getattr(r, "tipo_contingencia", None)) and not tiene_hito_oficial and not desc_oficial:
                continue

            etiquetas = []
            if r.is_holiday or "feriado" in desc_lower:
                etiquetas.append("FERIADO OFICIAL")
            if "vacacion" in desc_lower or (r.is_break and r.fecha.month in [1, 2, 7]):
                etiquetas.append("VACACIONES")
            elif r.is_break or "receso" in desc_lower:
                etiquetas.append("SEMANA DE RECESO")
            if r.is_exam_period or any(k in desc_lower for k in ["examen", "solemne", "certamen", "evaluaci"]):
                etiquetas.append("EXÁMENES / SOLEMNES")
            if getattr(r, "is_class_milestone", False) or any(k in desc_lower for k in ["inicio de clases", "fin de clases", "término lectivo", "cierre de actas", "matrícula"]):
                etiquetas.append("HITO DE CLASES")
            if "suspensi" in desc_lower or (
                r.suspension_actividades and not es_cont_manual and not getattr(r, "tipo_contingencia", None)
            ):
                etiquetas.append("SUSPENSIÓN DE ACTIVIDADES")
            if not es_cont_manual and r.fecha not in fechas_en_contingencias:
                if r.is_strike_federado:
                    etiquetas.append("PARO FEDERADO (FEUCT)")
                elif r.is_strike_carrera:
                    etiquetas.append("PARO DE CARRERA")
                elif r.tipo_contingencia:
                    etiquetas.append(f"CONTINGENCIA ({r.tipo_contingencia.upper()})")
                elif "paro" in desc_lower:
                    etiquetas.append("PARO ESTUDIANTIL")

            etq_str = f" [{', '.join(etiquetas)}]" if etiquetas else ""
            if desc_oficial or etiquetas:
                hitos.append(f"- {r.fecha.strftime('%d/%m/%Y (%A)')}: {desc_oficial}{etq_str}")

        # Contingencias académicas e incidencias operativas vigentes desde tabla fuente
        for c in contingencias:
            tipo_low = (c.tipo or "").strip().lower()
            sub_raw = (getattr(c, "subespacio", None) or "todos").strip()
            sub_etq = ETIQUETAS_SUBESPACIO_CHAT.get(sub_raw.lower(), sub_raw) if sub_raw.lower() != "todos" else ""
            sub_pref = f"[{sub_etq}] " if sub_etq else ""
            tramo_c = _formatear_tramo_contingencia(getattr(c, "hora_inicio", None), getattr(c, "hora_fin", None))
            cierre = " [CIERRE TOTAL]" if c.implica_cierre_total else ""
            carreras = f" (Carreras: {c.carreras_afectadas})" if (c.carreras_afectadas and c.carreras_afectadas != "Todas") else ""
            tipo_tag = ETIQUETAS_CONTINGENCIA_CHAT.get(tipo_low, "CONTINGENCIA OPERATIVA")
            desc_c = f" — {c.descripcion}" if getattr(c, "descripcion", None) else ""
            hitos.append(
                f"- Contingencia {c.fecha_inicio.strftime('%d/%m')} al {c.fecha_fin.strftime('%d/%m/%Y')}: "
                f"{sub_pref}{c.titulo}{tramo_c} [{tipo_tag}]{cierre}{carreras}{desc_c}"
            )

        # Horario 24 Horas dinámico leído desde horarios_operacion y salas_biblioteca
        if espacio_id == 1:
            caps = await obtener_capacidades_salas_cacheadas(db, espacio_id=1)
            cap_s2 = caps.get("sala_2", 126)
            reg_rows = (
                await db.execute(
                    select(HorarioOperacion).where(
                        HorarioOperacion.espacio_id == 1,
                        HorarioOperacion.tipo_horario == "regular",
                        HorarioOperacion.activo == True,
                    )
                )
            ).scalars().all()
            _, c_diurno_lj, c_diurno_v = _formatear_horario_regular_biblioteca(list(reg_rows))
            query_h24 = select(HorarioOperacion).where(
                HorarioOperacion.espacio_id == 1,
                HorarioOperacion.es_continuo_24h == True,
                HorarioOperacion.activo == True,
            )
            h24_rows = (await db.execute(query_h24)).scalars().all()
            for h in h24_rows:
                h_ini = h.fecha_inicio.date() if isinstance(h.fecha_inicio, datetime) else h.fecha_inicio
                h_fin = h.fecha_fin.date() if isinstance(h.fecha_fin, datetime) else h.fecha_fin
                aplica_rango = True
                if h_ini and h_fin:
                    aplica_rango = (h_ini <= d_fin and h_fin >= d_ini)
                if aplica_rango:
                    hitos.append(
                        f"- HORARIO 24 HORAS: {_formatear_horario_24h_dinamico(h, cap_s2, c_diurno_lj, c_diurno_v)}"
                    )

        return hitos
    except Exception as e:
        logger.warning(f"Error consultando calendario académico y hechos institucionales: {e}")
        return []


async def obtener_resumen_hechos_institucionales(
    db: AsyncSession,
    d_ini: Optional[date],
    d_fin: Optional[date],
    espacio_id: int = 1,
) -> str:
    """Genera un consolidado de los 8 hechos institucionales clave para el contexto del LLM."""
    if not d_ini or not d_fin:
        return "- Hechos Institucionales: Sin rango temporal definido (régimen regular lectivo)."

    try:
        query_cal = select(CalendarioAcademico).where(
            CalendarioAcademico.fecha >= d_ini,
            CalendarioAcademico.fecha <= d_fin
        ).order_by(CalendarioAcademico.fecha.asc())
        cal_rows = (await db.execute(query_cal)).scalars().all()

        query_cont = select(ContingenciaAcademica).where(
            ContingenciaAcademica.fecha_inicio <= d_fin,
            ContingenciaAcademica.fecha_fin >= d_ini,
            or_(ContingenciaAcademica.espacio_id.is_(None), ContingenciaAcademica.espacio_id == espacio_id),
        ).order_by(ContingenciaAcademica.fecha_inicio.asc())
        cont_rows = (await db.execute(query_cont)).scalars().all()
        fechas_en_contingencias: set[date] = set()
        for c in cont_rows:
            f_cur = max(c.fecha_inicio, d_ini)
            f_lim = min(c.fecha_fin, d_fin)
            while f_cur <= f_lim:
                fechas_en_contingencias.add(f_cur)
                f_cur += timedelta(days=1)

        h24_items = []
        reg_bib_resumen = "Horario regular Biblioteca CSF"
        if espacio_id == 1:
            caps = await obtener_capacidades_salas_cacheadas(db, espacio_id=1)
            cap_s2 = caps.get("sala_2", 126)
            reg_rows = (
                await db.execute(
                    select(HorarioOperacion).where(
                        HorarioOperacion.espacio_id == 1,
                        HorarioOperacion.tipo_horario == "regular",
                        HorarioOperacion.activo == True,
                    )
                )
            ).scalars().all()
            reg_bib_resumen, c_diurno_lj, c_diurno_v = _formatear_horario_regular_biblioteca(list(reg_rows))
            query_h24 = select(HorarioOperacion).where(
                HorarioOperacion.espacio_id == 1,
                HorarioOperacion.es_continuo_24h == True,
                HorarioOperacion.activo == True,
            )
            for h in (await db.execute(query_h24)).scalars().all():
                h_ini = h.fecha_inicio.date() if isinstance(h.fecha_inicio, datetime) else h.fecha_inicio
                h_fin = h.fecha_fin.date() if isinstance(h.fecha_fin, datetime) else h.fecha_fin
                if not h_ini or not h_fin or (h_ini <= d_fin and h_fin >= d_ini):
                    h24_items.append(_formatear_horario_24h_dinamico(h, cap_s2, c_diurno_lj, c_diurno_v))

        feriados = []
        recesos = []
        vacaciones = []
        examenes = []
        hitos_clases = []
        suspensiones = []
        paros_contingencias = []

        for r in cal_rows:
            f_str = r.fecha.strftime('%d/%m')
            desc = _descripcion_oficial_calendario(r.descripcion)
            desc_l = desc.lower()
            es_cont_manual = str(getattr(r, "fuente", "") or "") == "contingencia_manual"
            tiene_hito_oficial = bool(
                r.is_holiday
                or r.is_break
                or r.is_exam_period
                or getattr(r, "is_class_milestone", False)
            )
            if (es_cont_manual or getattr(r, "tipo_contingencia", None)) and not tiene_hito_oficial and not desc:
                continue

            if r.is_holiday or "feriado" in desc_l:
                feriados.append(f"{f_str}: {desc or 'Feriado oficial'}")
            if "vacacion" in desc_l or (r.is_break and r.fecha.month in [1, 2, 7]):
                vacaciones.append(f"{f_str}: {desc or 'Vacaciones'}")
            elif r.is_break or "receso" in desc_l:
                recesos.append(f"{f_str}: {desc or 'Semana de receso'}")
            if r.is_exam_period or any(k in desc_l for k in ["examen", "solemne", "certamen", "evaluaci"]):
                examenes.append(f"{f_str}: {desc or 'Período de exámenes / certámenes'}")
            if getattr(r, "is_class_milestone", False) or any(k in desc_l for k in ["inicio de clases", "fin de clases", "término lectivo", "cierre de actas"]):
                hitos_clases.append(f"{f_str}: {desc or 'Hito de clases'}")
            if "suspensi" in desc_l or (
                r.suspension_actividades and not es_cont_manual and not getattr(r, "tipo_contingencia", None)
            ):
                suspensiones.append(f"{f_str}: {desc or 'Suspensión de actividades'}")
            if not es_cont_manual and r.fecha not in fechas_en_contingencias and (
                r.is_strike_federado or r.is_strike_carrera or r.tipo_contingencia or "paro" in desc_l
            ):
                motivo = r.tipo_contingencia or ("Paro Federado" if r.is_strike_federado else "Paro de Carrera")
                paros_contingencias.append(f"{f_str}: {desc or motivo}")

        for c in cont_rows:
            rango_c = f"{c.fecha_inicio.strftime('%d/%m')}–{c.fecha_fin.strftime('%d/%m')}"
            sub_raw = (getattr(c, "subespacio", None) or "todos").strip()
            sub_etq = ETIQUETAS_SUBESPACIO_CHAT.get(sub_raw.lower(), sub_raw) if sub_raw.lower() != "todos" else ""
            sub_pref = f"[{sub_etq}] " if sub_etq else ""
            tramo_c = _formatear_tramo_contingencia(getattr(c, "hora_inicio", None), getattr(c, "hora_fin", None))
            tipo_etq = ETIQUETAS_CONTINGENCIA_CHAT.get((c.tipo or "").strip().lower(), c.tipo)
            cierre_txt = " (Cierre Total)" if c.implica_cierre_total else ""
            desc_txt = f" — {c.descripcion}" if getattr(c, "descripcion", None) else ""
            paros_contingencias.append(f"{rango_c}: {sub_pref}{c.titulo}{tramo_c} [{tipo_etq}]{cierre_txt}{desc_txt}")
            if (c.tipo or "").lower() in ("suspension_sala", "mantencion_cierre"):
                suspensiones.append(f"{rango_c}: {sub_pref}{c.titulo}{tramo_c}")

        if examenes and not h24_items and espacio_id == 1:
            caps_fb = await obtener_capacidades_salas_cacheadas(db, espacio_id=1)
            h24_items.append(
                f"Campaña 24 Horas Exámenes activa en Sala 2 Pecera CSF04 (capacidad {caps_fb.get('sala_2', 126)} asientos)"
            )

        lineas = [
            "HECHOS INSTITUCIONALES EN EL PERÍODO (UCT CSF):",
            f"1. Feriados Oficiales: {'; '.join(feriados) if feriados else 'Sin feriados oficiales en el rango'}",
            f"2. Semana de Receso: {'; '.join(recesos) if recesos else 'Sin semanas de receso en el rango'}",
            f"3. Vacaciones: {'; '.join(vacaciones) if vacaciones else 'Sin período de vacaciones en el rango'}",
            f"4. Exámenes / Solemnes: {'; '.join(examenes) if examenes else 'Régimen de clases regulares sin evaluaciones solemnes'}",
            f"5. Hitos de Clases: {'; '.join(hitos_clases) if hitos_clases else 'Régimen lectivo continuo'}",
            f"6. Suspensiones: {'; '.join(suspensiones) if suspensiones else 'Sin suspensiones de actividades reportadas'}",
            f"7. Paros y Contingencias: {'; '.join(paros_contingencias) if paros_contingencias else 'Sin paros ni contingencias activas'}",
            f"8. Horario 24 Horas: {'; '.join(h24_items) if h24_items else (f'{reg_bib_resumen} (sin apertura 24h en este período)' if espacio_id == 1 else 'Horario regular vehicular 07:00–22:00 hrs')}",
        ]
        return "\n".join(lineas)
    except Exception as e:
        logger.warning(f"Error generando resumen de hechos institucionales: {e}")
        return "- Hechos Institucionales: Régimen lectivo regular."


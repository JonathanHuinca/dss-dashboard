"""
AttendanceService — Consultas sobre Continuous Aggregates de TimescaleDB.
Todas las queries apuntan a las vistas pre-agregadas; nunca a microdatos.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta
import json
from typing import Any, Dict, List, Optional

import asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import TTLCache

CAPACIDAD_BIBLIOTECA = 276
UMBRAL_REBOTE_MIN = 15
UMBRAL_ALERTA_70 = 0.70
UMBRAL_ALERTA_85 = 0.85
VENTANA_ESPERA_VIVO_MIN = 180
IMPUTACION_SALIDA_PERDIDA_MIN = 60
IMPUTACION_ENTRADA_PERDIDA_MIN = 60
TOLERANCIA_SALIDA_POST_CIERRE_MIN = 15
# Prefijo de hash seudonimizado asociado a registros sin credencial / marcajes de prueba excluidos de conformes
PREFIJO_HASH_PRUEBA_EXCLUIDO = "e8f17a68%"

# Constantes SQL y etiquetas reutilizables
CLAUSULA_ESPACIO_ID = "espacio_id = :espacio_id"
ES_SALIDA_EVENTO_SQL = "(door_salida IS NOT NULL OR ultima_salida IS NOT NULL OR COALESCE(salida_imputada, 0) = 1)"
DOOR_SALA_1_LIKE = "(COALESCE(door_entrada, '') LIKE '%CSF02%' OR COALESCE(door_salida, '') LIKE '%CSF02%')"
DOOR_SALA_2_LIKE = "(COALESCE(door_entrada, '') LIKE '%CSF04%' OR COALESCE(door_salida, '') LIKE '%CSF04%')"
NOMBRE_SALA_1_CSF02 = "Sala 1 (CSF02)"
NOMBRE_SALA_2_CSF04 = "Sala 2 (CSF04 Pecera)"

# Respaldo determinista por sala si la BD no tiene reglas regulares configuradas
HORARIO_REGULAR_FALLBACK_SALA_1: dict[int, tuple[int, int, bool]] = {
    1: (510, 1230, False),
    2: (510, 1230, False),
    3: (510, 1230, False),
    4: (510, 1230, False),
    5: (510, 1170, False),
    6: (630, 900, False),
}
HORARIO_REGULAR_FALLBACK_SALA_2: dict[int, tuple[int, int, bool]] = {
    1: (510, 1380, False),
    2: (510, 1380, False),
    3: (510, 1380, False),
    4: (510, 1380, False),
    5: (510, 1320, False),
    6: (570, 900, False),
}

# Caché en memoria para reutilizar horarios de operación, calendario y contingencias entre gráficos simultáneos
cache_horarios_espacio: TTLCache = TTLCache(maxsize=64, ttl=300)
# Coalescing corto (60s) para compartir la curva de presencia exacta entre KPIs y gráfico
_cache_curva_presencia: TTLCache = TTLCache(maxsize=128, ttl=60)
_locks_curva_presencia: Dict[tuple, asyncio.Lock] = {}


async def obtener_horarios_operacion_cacheados(session: AsyncSession, espacio_id: int) -> list:
    clave_cache = f"horarios_24h:{espacio_id}"
    usar_cache = isinstance(session, AsyncSession)
    if usar_cache and clave_cache in cache_horarios_espacio:
        return cache_horarios_espacio[clave_cache]
    try:
        sql_24h = text("""
            SELECT fecha_inicio, fecha_fin, subespacio
            FROM horarios_operacion 
            WHERE espacio_id = :espacio_id AND activo = 1 AND es_continuo_24h = 1
        """)
        filas = (await session.execute(sql_24h, {"espacio_id": espacio_id})).fetchall()
    except Exception:
        filas = []
    if usar_cache:
        cache_horarios_espacio[clave_cache] = filas
    return filas


async def obtener_horarios_regulares_cacheados(session: AsyncSession, espacio_id: int) -> list:
    clave_cache = f"horarios_regulares:{espacio_id}"
    usar_cache = isinstance(session, AsyncSession)
    if usar_cache and clave_cache in cache_horarios_espacio:
        return cache_horarios_espacio[clave_cache]
    try:
        sql_reg = text("""
            SELECT id, anio, subespacio, tipo_horario, fecha_inicio, fecha_fin,
                   hora_apertura, hora_cierre, cierre_dia_siguiente, configuracion_dias
            FROM horarios_operacion
            WHERE espacio_id = :espacio_id
              AND activo = 1
              AND tipo_horario IN ('regular', 'historico_regular')
            ORDER BY anio DESC, fecha_inicio DESC, id DESC
        """)
        filas = (await session.execute(sql_reg, {"espacio_id": espacio_id})).fetchall()
    except Exception:
        filas = []
    if usar_cache:
        cache_horarios_espacio[clave_cache] = filas
    return filas


async def obtener_calendario_contingencias_cacheados(session: AsyncSession, espacio_id: int) -> dict:
    clave_cache = f"cal_contingencias:{espacio_id}"
    if clave_cache in cache_horarios_espacio:
        return cache_horarios_espacio[clave_cache]
    feriados: list[date] = []
    paros_fed: list[date] = []
    paros_car: list[date] = []
    suspensiones_institucionales: list[date] = []
    contingencias: list = []
    try:
        sql_cal = text("""
            SELECT CAST(fecha AS DATE) AS fecha,
                   is_holiday,
                   is_strike_federado,
                   is_strike_carrera,
                   suspension_actividades,
                   COALESCE(fuente, '') AS fuente,
                   tipo_contingencia
            FROM calendario_academico
            WHERE is_holiday = 1
               OR is_strike_federado = 1
               OR is_strike_carrera = 1
               OR suspension_actividades = 1
        """)
        for r in (await session.execute(sql_cal)).fetchall():
            f_val = r.fecha if isinstance(r.fecha, date) else date.fromisoformat(str(r.fecha)[:10])
            if getattr(r, "is_holiday", 0):
                feriados.append(f_val)
            if getattr(r, "is_strike_federado", 0):
                paros_fed.append(f_val)
            if getattr(r, "is_strike_carrera", 0):
                paros_car.append(f_val)
            # Solo suspensiones institucionales de calendario (las manuales se evalúan por sala en contingencias_academicas)
            if (
                getattr(r, "suspension_actividades", 0)
                and str(getattr(r, "fuente", "") or "") != "contingencia_manual"
                and not getattr(r, "tipo_contingencia", None)
            ):
                suspensiones_institucionales.append(f_val)
    except Exception:
        pass
    try:
        sql_cont = text("""
            SELECT CAST(fecha_inicio AS DATE) AS fecha_inicio,
                   CAST(fecha_fin AS DATE) AS fecha_fin,
                   subespacio,
                   hora_inicio,
                   hora_fin
            FROM contingencias_academicas
            WHERE implica_cierre_total = 1
              AND (espacio_id IS NULL OR espacio_id = :espacio_id)
        """)
        contingencias = (await session.execute(sql_cont, {"espacio_id": espacio_id})).fetchall()
    except Exception:
        contingencias = []
    datos = {
        "feriados": feriados,
        "paros_fed": paros_fed,
        "paros_car": paros_car,
        "suspensiones_institucionales": suspensiones_institucionales,
        "contingencias": contingencias,
    }
    cache_horarios_espacio[clave_cache] = datos
    return datos


async def obtener_inicio_registros_salas_cacheados(
    session: AsyncSession,
    espacio_id: int,
) -> dict[int, Optional[date]]:
    clave_cache = f"inicio_salas:{espacio_id}"
    usar_cache = isinstance(session, AsyncSession)
    if usar_cache and clave_cache in cache_horarios_espacio:
        return cache_horarios_espacio[clave_cache]
    inicio_salas: dict[int, Optional[date]] = {1: None, 2: None}
    try:
        sql_ini = text(f"""
            SELECT
                MIN(CASE WHEN {DOOR_SALA_1_LIKE} THEN CAST(time AS DATE) END) AS min_s1,
                MIN(CASE WHEN {DOOR_SALA_2_LIKE} THEN CAST(time AS DATE) END) AS min_s2
            FROM eventos_asistencia
            WHERE {CLAUSULA_ESPACIO_ID}
        """)
        row = (await session.execute(sql_ini, {"espacio_id": espacio_id})).first()
        if row is not None:
            min_s1 = getattr(row, "min_s1", None)
            min_s2 = getattr(row, "min_s2", None)
            inicio_salas = {
                1: _normalizar_fecha(min_s1) if min_s1 is not None else None,
                2: _normalizar_fecha(min_s2) if min_s2 is not None else None,
            }
    except Exception:
        inicio_salas = {1: None, 2: None}
    if usar_cache:
        cache_horarios_espacio[clave_cache] = inicio_salas
    return inicio_salas


def invalidar_cache_horarios(espacio_id: Optional[int] = None) -> None:
    if espacio_id is not None:
        cache_horarios_espacio.pop(f"horarios_24h:{espacio_id}", None)
        cache_horarios_espacio.pop(f"horarios_regulares:{espacio_id}", None)
        cache_horarios_espacio.pop(f"cal_contingencias:{espacio_id}", None)
        cache_horarios_espacio.pop(f"capacidades_salas:{espacio_id}", None)
        cache_horarios_espacio.pop(f"inicio_salas:{espacio_id}", None)
        for k in [k for k in list(cache_horarios_espacio.keys()) if str(k).startswith("horario_id:")]:
            cache_horarios_espacio.pop(k, None)
    else:
        cache_horarios_espacio.clear()
    _cache_curva_presencia.clear()


invalidar_cache_horarios_asistencia = invalidar_cache_horarios


def _leer_attr(obj: Any, attr: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


def _hhmm_a_minutos(valor: Any, default_min: int) -> int:
    if valor is None:
        return default_min
    txt = str(valor).strip()
    if not txt or ":" not in txt:
        return default_min
    try:
        hh, mm = map(int, txt.split(":")[:2])
        total = hh * 60 + mm
        if 0 <= total <= 1439:
            return total
    except (ValueError, TypeError):
        pass
    return default_min


def _minutos_a_sql_time(minutos: int) -> str:
    if minutos >= 1440:
        return "23:59:59"
    if minutos <= 0:
        return "00:00:00"
    return f"{minutos // 60:02d}:{minutos % 60:02d}:00"


def _normalizar_subespacio_biblioteca(sub: Optional[str]) -> str:
    s = str(sub or "todos").strip().lower()
    if s in ("sala_1", "sala1", "csf02"):
        return "sala_1"
    if s in ("sala_2", "sala2", "csf04"):
        return "sala_2"
    return "todos"


def _detectar_subespacio_fila(door_entrada: Any, door_salida: Any) -> Optional[str]:
    txt = f"{door_entrada or ''} {door_salida or ''}".upper()
    if "CSF02" in txt:
        return "sala_1"
    if "CSF04" in txt:
        return "sala_2"
    return None


def _parsear_mapa_dias_regla(regla: Any) -> dict[int, tuple[int, int, bool]]:
    dias_iso_map = {
        "lunes": 1,
        "martes": 2,
        "miercoles": 3,
        "miércoles": 3,
        "jueves": 4,
        "viernes": 5,
        "sabado": 6,
        "sábado": 6,
        "domingo": 7,
    }
    ap_def = _hhmm_a_minutos(_leer_attr(regla, "hora_apertura", "08:30"), 510)
    ci_def = _hhmm_a_minutos(_leer_attr(regla, "hora_cierre", "20:30"), 1230)
    ovn_def = bool(_leer_attr(regla, "cierre_dia_siguiente", False))

    cfg_raw = _leer_attr(regla, "configuracion_dias", None)
    cfg: Optional[dict] = None
    if isinstance(cfg_raw, dict):
        cfg = cfg_raw
    elif isinstance(cfg_raw, str) and cfg_raw.strip():
        try:
            parsed = json.loads(cfg_raw)
            if isinstance(parsed, dict):
                cfg = parsed
        except Exception:
            cfg = None

    resultado: dict[int, tuple[int, int, bool]] = {}
    if cfg:
        for nombre_dia, info in cfg.items():
            dow = dias_iso_map.get(str(nombre_dia).strip().lower())
            if dow is None or not isinstance(info, dict):
                continue
            if not info.get("abierto", True):
                continue
            ap_min = _hhmm_a_minutos(info.get("apertura"), ap_def)
            ci_min = _hhmm_a_minutos(info.get("cierre"), ci_def)
            ovn = bool(info.get("cierre_dia_siguiente", ovn_def))
            resultado[dow] = (ap_min, ci_min, ovn)
        return resultado

    for dow in range(1, 6):
        resultado[dow] = (ap_def, ci_def, ovn_def)
    return resultado


def _seleccionar_reglas_grupo(
    lista: list[dict],
    fecha_inicio: Optional[date],
    fecha_fin: Optional[date],
) -> list[dict]:
    if not lista:
        return []

    anios_rango: Optional[set[int]] = None
    if fecha_inicio and fecha_fin:
        anios_rango = set(range(fecha_inicio.year, fecha_fin.year + 1))
    elif fecha_inicio:
        anios_rango = {fecha_inicio.year}
    elif fecha_fin:
        anios_rango = {fecha_fin.year}

    if anios_rango:
        coincidentes = [
            r for r in lista
            if (r["anio"] in anios_rango) or (r["fecha_inicio"] is not None or r["fecha_fin"] is not None)
        ]
        if coincidentes:
            return coincidentes
        regulares = [r for r in lista if r["tipo_horario"] == "regular"] or lista
        max_anio = max((r["anio"] or 0) for r in regulares)
        return [r for r in regulares if (r["anio"] or 0) == max_anio]

    max_anio = max((r["anio"] or 0) for r in lista)
    return [
        r for r in lista
        if (r["anio"] or 0) == max_anio or (r["fecha_inicio"] is not None or r["fecha_fin"] is not None)
    ]


def _seleccionar_reglas_regulares_por_sala(
    reglas_raw: list,
    fecha_inicio: Optional[date],
    fecha_fin: Optional[date],
) -> dict[str, list[dict]]:
    por_sub: dict[str, list[dict]] = {"sala_1": [], "sala_2": [], "todos": []}
    for r in reglas_raw or []:
        dias = _parsear_mapa_dias_regla(r)
        if not dias:
            continue
        ini_raw = _leer_attr(r, "fecha_inicio", None)
        fin_raw = _leer_attr(r, "fecha_fin", None)
        r_ini = _normalizar_fecha(ini_raw) if ini_raw is not None else None
        r_fin = _normalizar_fecha(fin_raw) if fin_raw is not None else None
        if r_ini and fecha_fin and r_ini > fecha_fin:
            continue
        if r_fin and fecha_inicio and r_fin < fecha_inicio:
            continue
        anio_raw = _leer_attr(r, "anio", None)
        anio = int(anio_raw) if anio_raw is not None else None
        sub = _normalizar_subespacio_biblioteca(_leer_attr(r, "subespacio", "todos"))
        tipo_h = str(_leer_attr(r, "tipo_horario", "regular") or "regular")
        por_sub[sub].append({
            "anio": anio,
            "subespacio": sub,
            "tipo_horario": tipo_h,
            "fecha_inicio": r_ini,
            "fecha_fin": r_fin,
            "dias": dias,
        })

    todos = _seleccionar_reglas_grupo(por_sub["todos"], fecha_inicio, fecha_fin)
    s1 = _seleccionar_reglas_grupo(por_sub["sala_1"], fecha_inicio, fecha_fin) or todos or [{
        "anio": None, "subespacio": "sala_1", "tipo_horario": "regular",
        "fecha_inicio": None, "fecha_fin": None, "dias": HORARIO_REGULAR_FALLBACK_SALA_1,
    }]
    s2 = _seleccionar_reglas_grupo(por_sub["sala_2"], fecha_inicio, fecha_fin) or todos or [{
        "anio": None, "subespacio": "sala_2", "tipo_horario": "regular",
        "fecha_inicio": None, "fecha_fin": None, "dias": HORARIO_REGULAR_FALLBACK_SALA_2,
    }]
    return {"sala_1": s1, "sala_2": s2, "todos": todos}


def _construir_sql_dias_regla(
    dias: dict[int, tuple[int, int, bool]],
    tolerancia_salida_min: int = TOLERANCIA_SALIDA_POST_CIERRE_MIN,
) -> str:
    if not dias:
        return "1=0"

    grupos: dict[tuple[int, int, bool], list[int]] = defaultdict(list)
    for dow in sorted(dias.keys()):
        grupos[dias[dow]].append(dow)

    tramos: list[str] = []
    for (ap_min, ci_min, ovn), dows in sorted(grupos.items(), key=lambda item: min(item[1])):
        dia_cond = f"dia_semana_iso IN ({', '.join(str(d) for d in dows)})" if len(dows) > 1 else f"dia_semana_iso = {dows[0]}"
        t_ap = _minutos_a_sql_time(ap_min)
        t_ci = _minutos_a_sql_time(ci_min)
        t_ci_tol = _minutos_a_sql_time(ci_min + tolerancia_salida_min) if tolerancia_salida_min > 0 else t_ci
        tiene_tol = tolerancia_salida_min > 0 and t_ci_tol > t_ci

        if not ovn and ci_min >= ap_min:
            if tiene_tol:
                tramos.append(
                    f"({dia_cond} AND CAST(time AS TIME) >= '{t_ap}' AND "
                    f"(CAST(time AS TIME) <= '{t_ci}' OR ({ES_SALIDA_EVENTO_SQL} AND CAST(time AS TIME) <= '{t_ci_tol}')))"
                )
            else:
                tramos.append(f"({dia_cond} AND CAST(time AS TIME) >= '{t_ap}' AND CAST(time AS TIME) <= '{t_ci}')")
        else:
            tramos.append(f"({dia_cond} AND CAST(time AS TIME) >= '{t_ap}')")
            dows_next = sorted((d % 7) + 1 for d in dows)
            next_cond = (
                f"dia_semana_iso IN ({', '.join(str(d) for d in dows_next)})"
                if len(dows_next) > 1
                else f"dia_semana_iso = {dows_next[0]}"
            )
            if tiene_tol:
                tramos.append(
                    f"({next_cond} AND (CAST(time AS TIME) <= '{t_ci}' OR ({ES_SALIDA_EVENTO_SQL} AND CAST(time AS TIME) <= '{t_ci_tol}')))"
                )
            else:
                tramos.append(f"({next_cond} AND CAST(time AS TIME) <= '{t_ci}')")

    return " OR ".join(tramos) if tramos else "1=0"


def _construir_sql_reglas_sala(
    reglas_sala: list[dict],
    tolerancia_salida_min: int = TOLERANCIA_SALIDA_POST_CIERRE_MIN,
) -> str:
    if not reglas_sala:
        return "1=0"
    if len(reglas_sala) == 1:
        return _construir_sql_dias_regla(reglas_sala[0]["dias"], tolerancia_salida_min)

    partes: list[str] = []
    for r in reglas_sala:
        cond_dias = _construir_sql_dias_regla(r["dias"], tolerancia_salida_min)
        guardas: list[str] = []
        if r.get("fecha_inicio") is not None:
            guardas.append(f"CAST(time AS DATE) >= '{r['fecha_inicio'].isoformat()}'")
        if r.get("fecha_fin") is not None:
            guardas.append(f"CAST(time AS DATE) <= '{r['fecha_fin'].isoformat()}'")
        if not guardas and r.get("anio") is not None:
            guardas.append(f"DATEPART(YEAR, time) = {int(r['anio'])}")
        if guardas:
            partes.append(f"({' AND '.join(guardas)} AND ({cond_dias}))")
        else:
            partes.append(f"({cond_dias})")
    return " OR ".join(partes)


def _construir_sql_horario_regular(
    reglas_raw: list,
    fecha_inicio: Optional[date] = None,
    fecha_fin: Optional[date] = None,
    tolerancia_salida_min: int = TOLERANCIA_SALIDA_POST_CIERRE_MIN,
) -> str:
    sel = _seleccionar_reglas_regulares_por_sala(reglas_raw, fecha_inicio, fecha_fin)
    sql_s1 = _construir_sql_reglas_sala(sel["sala_1"], tolerancia_salida_min)
    sql_s2 = _construir_sql_reglas_sala(sel["sala_2"], tolerancia_salida_min)
    if sel["todos"]:
        sql_other = _construir_sql_reglas_sala(sel["todos"], tolerancia_salida_min)
    else:
        sql_other = f"({sql_s1}) OR ({sql_s2})"

    return (
        f"(({DOOR_SALA_1_LIKE} AND ({sql_s1})) "
        f"OR ({DOOR_SALA_2_LIKE} AND ({sql_s2})) "
        f"OR (NOT {DOOR_SALA_1_LIKE} AND NOT {DOOR_SALA_2_LIKE} AND ({sql_other})))"
    )


def _sql_case_dias_minutos(
    dias: dict[int, tuple[int, int, bool]],
    es_cierre: bool,
    expr_dow: str,
) -> str:
    por_min: dict[int, list[int]] = defaultdict(list)
    for dow in sorted(dias.keys()):
        ap_min, ci_min, ovn = dias[dow]
        val = (1439 if (ovn or ci_min < ap_min) else ci_min) if es_cierre else ap_min
        por_min[int(val)].append(dow)
    if not por_min:
        return "0"
    whens = []
    for val, dows in por_min.items():
        if len(dows) == 1:
            whens.append(f"WHEN {expr_dow} = {dows[0]} THEN {val}")
        else:
            whens.append(f"WHEN {expr_dow} IN ({', '.join(str(d) for d in dows)}) THEN {val}")
    return f"CASE {' '.join(whens)} ELSE 0 END"


def _construir_sql_minutos_limite_sala(
    reglas_sala: list[dict],
    es_cierre: bool,
    expr_dow: str = "e.dia_semana_iso",
    expr_fecha: str = "e.fecha",
) -> str:
    if not reglas_sala:
        return "0"
    if len(reglas_sala) == 1:
        return _sql_case_dias_minutos(reglas_sala[0]["dias"], es_cierre, expr_dow)

    ordenadas = sorted(
        reglas_sala,
        key=lambda r: (
            0 if (r.get("fecha_inicio") and r.get("fecha_fin")) else (1 if (r.get("fecha_inicio") or r.get("fecha_fin")) else 2),
            -(r.get("anio") or 0),
        ),
    )
    ramas: list[str] = []
    fallback_expr = "0"
    for r in ordenadas:
        case_dias = f"({_sql_case_dias_minutos(r['dias'], es_cierre, expr_dow)})"
        conds_f: list[str] = []
        if r.get("fecha_inicio") is not None:
            conds_f.append(f"{expr_fecha} >= '{r['fecha_inicio'].isoformat()}'")
        if r.get("fecha_fin") is not None:
            conds_f.append(f"{expr_fecha} <= '{r['fecha_fin'].isoformat()}'")
        if not conds_f and r.get("anio") is not None:
            conds_f.append(f"DATEPART(YEAR, {expr_fecha}) = {int(r['anio'])}")
        if conds_f:
            ramas.append(f"WHEN {' AND '.join(conds_f)} THEN {case_dias}")
        elif fallback_expr == "0":
            fallback_expr = case_dias
        if fallback_expr == "0" and r is ordenadas[-1]:
            fallback_expr = case_dias
    if not ramas:
        return fallback_expr
    return f"CASE {' '.join(ramas)} ELSE {fallback_expr} END"


def _construir_expresiones_limites_presencia(
    reglas_raw: list,
    cond_s2_24h: str,
    fecha_inicio: Optional[date] = None,
    fecha_fin: Optional[date] = None,
) -> tuple[str, str]:
    sel = _seleccionar_reglas_regulares_por_sala(reglas_raw, fecha_inicio, fecha_fin)
    min_ap_s1 = _construir_sql_minutos_limite_sala(sel["sala_1"], es_cierre=False)
    min_ap_s2 = _construir_sql_minutos_limite_sala(sel["sala_2"], es_cierre=False)
    min_ci_s1 = _construir_sql_minutos_limite_sala(sel["sala_1"], es_cierre=True)
    min_ci_s2 = _construir_sql_minutos_limite_sala(sel["sala_2"], es_cierre=True)

    expr_piso_apertura = f"""CASE
        WHEN e.sala_num = 2 AND ({cond_s2_24h}) THEN CAST(e.fecha AS DATETIME)
        WHEN e.sala_num = 1 THEN DATEADD(MINUTE, ({min_ap_s1}), CAST(e.fecha AS DATETIME))
        ELSE DATEADD(MINUTE, ({min_ap_s2}), CAST(e.fecha AS DATETIME))
    END"""

    expr_cierre_efectivo = f"""CASE
        WHEN e.sala_num = 1 THEN DATEADD(MINUTE, ({min_ci_s1}), CAST(e.fecha AS DATETIME))
        WHEN ({cond_s2_24h}) THEN DATEADD(SECOND, 86399, CAST(e.fecha AS DATETIME))
        ELSE DATEADD(MINUTE, ({min_ci_s2}), CAST(e.fecha AS DATETIME))
    END"""
    return expr_piso_apertura, expr_cierre_efectivo


def _construir_is_24h_sql(active_24h_rows: list, params: dict, prefijo: str = "h24") -> str:
    h24_clauses = []
    for i, r_24 in enumerate(active_24h_rows):
        if r_24.fecha_inicio and r_24.fecha_fin:
            p_ini = f"{prefijo}_ini_{i}"
            p_fin = f"{prefijo}_fin_{i}"
            sub_24 = _normalizar_subespacio_biblioteca(getattr(r_24, "subespacio", None))
            if sub_24 == "sala_1":
                h24_clauses.append(f"(time >= :{p_ini} AND time <= :{p_fin} AND {DOOR_SALA_1_LIKE})")
            elif sub_24 == "sala_2":
                h24_clauses.append(f"(time >= :{p_ini} AND time <= :{p_fin} AND {DOOR_SALA_2_LIKE})")
            else:
                h24_clauses.append(f"(time >= :{p_ini} AND time <= :{p_fin})")
            params[p_ini] = r_24.fecha_inicio
            params[p_fin] = r_24.fecha_fin
    return f"({' OR '.join(h24_clauses)})" if h24_clauses else "1=0"


async def _construir_sql_fuera_de_horario_categoria(
    session: AsyncSession,
    espacio_id: int,
    fecha_inicio: Optional[date],
    fecha_fin: Optional[date],
    params: dict,
) -> str:
    reglas_regulares = await obtener_horarios_regulares_cacheados(session, espacio_id)
    regular_open_sql = _construir_sql_horario_regular(
        reglas_regulares,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        tolerancia_salida_min=TOLERANCIA_SALIDA_POST_CIERRE_MIN,
    )
    active_24h_rows = await obtener_horarios_operacion_cacheados(session, espacio_id)
    is_24h_sql = _construir_is_24h_sql(active_24h_rows, params, prefijo="cat_h24")
    return f"(NOT ({regular_open_sql} OR {is_24h_sql}))"


async def obtener_capacidades_salas_cacheadas(session: AsyncSession, espacio_id: int = 1) -> dict:
    clave = f"capacidades_salas:{espacio_id}"
    usar_cache = isinstance(session, AsyncSession)
    if usar_cache and clave in cache_horarios_espacio:
        return cache_horarios_espacio[clave]

    salas: list[dict] = []
    try:
        salas = await AttendanceService.get_salas_biblioteca(session, espacio_id)
    except Exception:
        salas = []

    cap_s1 = 150
    cap_s2 = 126
    total_registradas = 0
    for s in salas or []:
        cod = str(s.get("codigo") or "")
        sid = s.get("id")
        cap = int(s.get("capacidad_asientos") or 0)
        if cap > 0:
            total_registradas += cap
            if "CSF02" in cod or sid == 1:
                cap_s1 = cap
            elif "CSF04" in cod or sid == 2:
                cap_s2 = cap

    caps = {
        "sala_1": cap_s1,
        "sala_2": cap_s2,
        "total": total_registradas if total_registradas > 0 else (cap_s1 + cap_s2),
    }
    if usar_cache and salas:
        cache_horarios_espacio[clave] = caps
    return caps


def _extraer_hora_pico_curva(curva: list[dict]) -> Optional[str]:
    if not curva:
        return None
    pico = max(
        curva,
        key=lambda r: (int(r.get("personas_unicas", 0) or 0), int(r.get("ingresos", 0) or 0)),
    )
    if int(pico.get("personas_unicas", 0) or 0) <= 0:
        return None
    bucket = str(pico.get("bucket") or "")
    if len(bucket) >= 13 and "T" in bucket:
        return f"{bucket[11:13]}:00 hrs"
    return None


def _normalizar_fecha(valor: Any) -> date:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor)[:10])


def _aplicar_cota_flujo_fecha(flujo_por_bucket: dict, max_hora_flujo_por_dia: dict, row: Any) -> None:
    bucket_raw = row[0] if isinstance(row, tuple) else row.bucket
    bucket_dt = bucket_raw if isinstance(bucket_raw, datetime) else datetime.fromisoformat(str(bucket_raw))
    fecha = _normalizar_fecha(row[1] if isinstance(row, tuple) else row.fecha)
    ingresos = int((row[2] if isinstance(row, tuple) else row.ingresos) or 0)
    salidas = int((row[3] if isinstance(row, tuple) else row.salidas) or 0)
    ing_s1 = int((row[4] if isinstance(row, tuple) else row.ingresos_sala1) or 0)
    ing_s2 = int((row[5] if isinstance(row, tuple) else row.ingresos_sala2) or 0)
    flujo_por_bucket[bucket_dt] = (ingresos, salidas, ing_s1, ing_s2)
    h = bucket_dt.hour
    if fecha not in max_hora_flujo_por_dia or h > max_hora_flujo_por_dia[fecha]:
        max_hora_flujo_por_dia[fecha] = h


def _calcular_curva_presencia_por_hora(
    sesiones_rows: list,
    flujo_rows: list,
    ahora_servidor: datetime,
) -> list[dict]:
    """Barrido cronológico exacto minuto/segundo por jornada para pico simultáneo horario y arrastre continuo."""
    eventos_por_dia: Dict[date, list] = defaultdict(list)
    for row in sesiones_rows:
        fecha_raw = row[0] if isinstance(row, tuple) else row.fecha
        sala_num = int((row[1] if isinstance(row, tuple) else row.sala_num) or 0)
        t_ent = row[2] if isinstance(row, tuple) else row.t_entrada
        t_sal = row[3] if isinstance(row, tuple) else row.t_salida
        if t_ent is None or t_sal is None:
            continue
        fecha = _normalizar_fecha(fecha_raw)
        t_sal_adj = t_sal if t_sal > t_ent else t_ent + timedelta(seconds=1)
        eventos_por_dia[fecha].append((t_ent, 1, sala_num))
        if t_sal_adj.date() == fecha:
            eventos_por_dia[fecha].append((t_sal_adj, -1, sala_num))

    flujo_por_bucket: Dict[datetime, tuple] = {}
    max_hora_flujo_por_dia: Dict[date, int] = {}
    for row in flujo_rows:
        _aplicar_cota_flujo_fecha(flujo_por_bucket, max_hora_flujo_por_dia, row)

    fechas_ordenadas = sorted(set(eventos_por_dia.keys()) | set(max_hora_flujo_por_dia.keys()))
    hoy_servidor = ahora_servidor.date()
    resultado: list[dict] = []

    for fecha in fechas_ordenadas:
        evs = eventos_por_dia.get(fecha, [])
        evs.sort(key=lambda x: x[0])

        occ_t = occ_1 = occ_2 = 0
        hour_first: Dict[int, datetime] = {}
        hour_peak: Dict[int, list] = {}
        hour_end: Dict[int, tuple] = {}

        # Agrupar exactamente por timestamp idéntico para evitar picos ficticios en salidas/entradas simultáneas
        idx = 0
        n_evs = len(evs)
        while idx < n_evs:
            ts_actual = evs[idx][0]
            dtot = ds1 = ds2 = 0
            while idx < n_evs and evs[idx][0] == ts_actual:
                _, delta, sala_num = evs[idx]
                dtot += delta
                if sala_num == 1:
                    ds1 += delta
                elif sala_num == 2:
                    ds2 += delta
                idx += 1

            occ_t = max(0, occ_t + dtot)
            occ_1 = max(0, occ_1 + ds1)
            occ_2 = max(0, occ_2 + ds2)

            h = ts_actual.hour
            if h not in hour_first:
                hour_first[h] = ts_actual
            pk = hour_peak.get(h)
            if pk is None:
                hour_peak[h] = [occ_t, occ_1, occ_2]
            else:
                if occ_t > pk[0]:
                    pk[0] = occ_t
                if occ_1 > pk[1]:
                    pk[1] = occ_1
                if occ_2 > pk[2]:
                    pk[2] = occ_2
            hour_end[h] = (occ_t, occ_1, occ_2)

        horas_flujo_dia = [b.hour for b in flujo_por_bucket if b.date() == fecha]
        h_min_candidates = list(hour_first.keys()) + horas_flujo_dia
        if not h_min_candidates:
            continue
        h_min = min(h_min_candidates)

        if fecha == hoy_servidor:
            h_max = max(max_hora_flujo_por_dia.get(fecha, -1), max(hour_first, default=-1))
        elif fecha in max_hora_flujo_por_dia:
            h_max = max_hora_flujo_por_dia[fecha]
        else:
            h_max = max(hour_first, default=-1)

        if h_max < h_min:
            continue

        prev_e = (0, 0, 0)
        for h in range(h_min, h_max + 1):
            bucket_dt = datetime.combine(fecha, datetime.min.time()) + timedelta(hours=h)
            if h in hour_peak:
                ft = hour_first[h]
                pk = hour_peak[h]
                if ft.minute > 0 or ft.second > 0 or ft.microsecond > 0:
                    p_t = max(prev_e[0], pk[0])
                    p_1 = max(prev_e[1], pk[1])
                    p_2 = max(prev_e[2], pk[2])
                else:
                    p_t, p_1, p_2 = pk[0], pk[1], pk[2]
                prev_e = hour_end[h]
            else:
                p_t, p_1, p_2 = prev_e

            if bucket_dt > ahora_servidor:
                continue

            ing, sal, ing1, ing2 = flujo_por_bucket.get(bucket_dt, (0, 0, 0, 0))
            if ing > 0 or sal > 0 or p_t > 0:
                resultado.append({
                    "bucket": bucket_dt.isoformat(),
                    "ingresos": ing,
                    "salidas": sal,
                    "personas_unicas": int(p_t),
                    "personas_sala1": int(p_1),
                    "personas_sala2": int(p_2),
                    "ingresos_sala1": ing1,
                    "ingresos_sala2": ing2,
                })

    return resultado


def _rango_dia_operativo_en_lista(lista_reglas: list[dict], dow: int) -> Optional[tuple[int, int, bool]]:
    ordenadas = sorted(
        lista_reglas,
        key=lambda r: (
            0 if (r.get("fecha_inicio") and r.get("fecha_fin")) else (1 if (r.get("fecha_inicio") or r.get("fecha_fin")) else 2),
            0 if r.get("tipo_horario") == "regular" else 1,
        ),
    )
    for r in ordenadas:
        dias_map_r = r.get("dias") or {}
        if dow in dias_map_r:
            return dias_map_r[dow]
        return None
    return None


def _rellenar_dias_operativos_sin_registros(
    curva: list[dict],
    fecha_inicio: Optional[date],
    fecha_fin: Optional[date],
    ahora_servidor: datetime,
    reglas_regulares: list,
    sala: Optional[str] = None,
    dias_semana: Optional[str] = None,
    cal_data: Optional[dict] = None,
    alcance: Optional[str] = "conformes",
    regimen_horario: Optional[str] = "todos",
    inicio_por_sala: Optional[dict[int, Optional[date]]] = None,
) -> list[dict]:
    """Rellena con cero las franjas operativas de días hábiles/programados sin marcajes hasta ahora_servidor."""
    if fecha_inicio is None or fecha_fin is None:
        return curva
    if (alcance or "conformes") == "anomalias":
        return curva

    reg_list = [r.strip().lower() for r in (regimen_horario or "todos").split(",") if r.strip()]
    reg_operativos = {
        "todos", "dentro_horario", "oficial", "regular",
        "24h_delta", "nocturno_24h", "delta_24h",
        "24h_total", "24h", "extendido_24h",
    }
    if reg_list and not any(r in reg_operativos or r.startswith("horario_") for r in reg_list):
        return curva

    f_fin_eff = min(fecha_fin, ahora_servidor.date())
    if f_fin_eff < fecha_inicio:
        return curva

    dias_permitidos: Optional[set[int]] = None
    if dias_semana:
        dias_map = {
            "domingo": 7,
            "lunes": 1,
            "martes": 2,
            "miercoles": 3,
            "miércoles": 3,
            "jueves": 4,
            "viernes": 5,
            "sabado": 6,
            "sábado": 6,
        }
        sel_dias = {dias_map[d.strip().lower()] for d in dias_semana.split(",") if d.strip().lower() in dias_map}
        if sel_dias:
            dias_permitidos = sel_dias

    sala_num = _resolver_codigo_sala(sala)
    cal_dict = cal_data or {}
    feriados_set = {_normalizar_fecha(f) for f in (cal_dict.get("feriados") or [])}
    suspensiones_inst_set = {_normalizar_fecha(f) for f in (cal_dict.get("suspensiones_institucionales") or [])}
    contingencias_list = cal_dict.get("contingencias") or []
    min_s1 = _normalizar_fecha(inicio_por_sala[1]) if (inicio_por_sala and inicio_por_sala.get(1)) else None
    min_s2 = _normalizar_fecha(inicio_por_sala[2]) if (inicio_por_sala and inicio_por_sala.get(2)) else None

    def _es_cierre_total_dia(dia: date, saltar_contingencias: bool = False, sala_eval: Optional[int] = None) -> bool:
        if dia in feriados_set or dia in suspensiones_inst_set:
            return True
        if saltar_contingencias:
            return False
        sala_obj = sala_num if sala_eval is None else sala_eval
        for cca in contingencias_list:
            h_ini_c = str(_leer_attr(cca, "hora_inicio", "") or "").strip()
            h_fin_c = str(_leer_attr(cca, "hora_fin", "") or "").strip()
            if h_ini_c and h_fin_c:
                continue
            c_ini_raw = _leer_attr(cca, "fecha_inicio", None)
            c_fin_raw = _leer_attr(cca, "fecha_fin", None)
            if c_ini_raw is None or c_fin_raw is None:
                continue
            if not (_normalizar_fecha(c_ini_raw) <= dia <= _normalizar_fecha(c_fin_raw)):
                continue
            sub_c = _normalizar_subespacio_biblioteca(_leer_attr(cca, "subespacio", "todos"))
            if sub_c == "todos":
                return True
            if sala_obj == 1 and sub_c == "sala_1":
                return True
            if sala_obj == 2 and sub_c == "sala_2":
                return True
        return False

    def _sala_estuvo_abierta(reglas_sala: list, dia: date, dow: int) -> Optional[tuple[int, int]]:
        t_rango = _rango_dia_operativo_en_lista(reglas_sala, dow)
        if t_rango is None:
            return None
        ap, ci, ovn = t_rango
        h_ini = ap // 60
        h_fin = 23 if (ovn or ci < ap) else ci // 60
        if dia == ahora_servidor.date():
            if (ahora_servidor.hour * 60 + ahora_servidor.minute) < ap:
                return None
            h_fin = min(h_fin, ahora_servidor.hour)
        if h_fin < h_ini:
            return None
        return (h_ini, h_fin)

    fechas_con_datos: set[date] = set()
    fechas_con_datos_s1: set[date] = set()
    fechas_con_datos_s2: set[date] = set()
    for p in curva:
        b = p.get("bucket")
        if b:
            f_b = _normalizar_fecha(b)
            fechas_con_datos.add(f_b)
            if sala_num is None:
                if (p.get("personas_sala1") or 0) > 0 or (p.get("ingresos_sala1") or 0) > 0:
                    fechas_con_datos_s1.add(f_b)
                if (p.get("personas_sala2") or 0) > 0 or (p.get("ingresos_sala2") or 0) > 0:
                    fechas_con_datos_s2.add(f_b)

    dias_rango = (f_fin_eff - fecha_inicio).days + 1
    granularidad_horaria = dias_rango <= 7

    puntos_cero: list[dict] = []
    dias_sin_reg_s1: set[date] = set()
    dias_sin_reg_s2: set[date] = set()
    dia_actual = fecha_inicio
    while dia_actual <= f_fin_eff:
        dow = dia_actual.isoweekday()
        if dias_permitidos is not None and dow not in dias_permitidos:
            dia_actual += timedelta(days=1)
            continue

        sel = _seleccionar_reglas_regulares_por_sala(reglas_regulares, dia_actual, dia_actual)
        s1_iniciada = min_s1 is None or dia_actual >= min_s1
        s2_iniciada = min_s2 is None or dia_actual >= min_s2
        s1_vacia = False
        s2_vacia = False
        if sala_num is None:
            r_s1 = _sala_estuvo_abierta(sel["sala_1"], dia_actual, dow)
            r_s2 = _sala_estuvo_abierta(sel["sala_2"], dia_actual, dow)
            s1_vacia = (
                s1_iniciada
                and r_s1 is not None
                and dia_actual not in fechas_con_datos_s1
                and not _es_cierre_total_dia(dia_actual, saltar_contingencias=granularidad_horaria, sala_eval=1)
            )
            s2_vacia = (
                s2_iniciada
                and r_s2 is not None
                and dia_actual not in fechas_con_datos_s2
                and not _es_cierre_total_dia(dia_actual, saltar_contingencias=granularidad_horaria, sala_eval=2)
            )

        if dia_actual not in fechas_con_datos:
            if not _es_cierre_total_dia(dia_actual, saltar_contingencias=granularidad_horaria):
                if sala_num == 1:
                    t1 = _rango_dia_operativo_en_lista(sel["sala_1"], dow) if s1_iniciada else None
                    activas = [t1] if t1 is not None else []
                elif sala_num == 2:
                    t2 = _rango_dia_operativo_en_lista(sel["sala_2"], dow) if s2_iniciada else None
                    activas = [t2] if t2 is not None else []
                else:
                    t1 = _rango_dia_operativo_en_lista(sel["sala_1"], dow) if s1_iniciada else None
                    t2 = _rango_dia_operativo_en_lista(sel["sala_2"], dow) if s2_iniciada else None
                    activas = [t for t in (t1, t2) if t is not None]

                if activas:
                    h_ini = min(ap // 60 for ap, _, _ in activas)
                    h_fin = max((23 if (ovn or ci < ap) else ci // 60) for ap, ci, ovn in activas)
                    if dia_actual == ahora_servidor.date():
                        h_fin = min(h_fin, ahora_servidor.hour)
                    if h_fin >= h_ini:
                        horas = list(range(h_ini, h_fin + 1)) if granularidad_horaria else ([h_ini] if h_ini == h_fin else [h_ini, h_fin])
                        base_dt = datetime.combine(dia_actual, datetime.min.time())
                        for h in horas:
                            pto = {
                                "bucket": (base_dt + timedelta(hours=h)).isoformat(),
                                "ingresos": 0,
                                "salidas": 0,
                                "personas_unicas": 0,
                                "personas_sala1": 0,
                                "personas_sala2": 0,
                                "ingresos_sala1": 0,
                                "ingresos_sala2": 0,
                                "sin_registros": True,
                            }
                            if sala_num is None:
                                if s1_vacia:
                                    pto["sin_registros_sala1"] = True
                                if s2_vacia:
                                    pto["sin_registros_sala2"] = True
                            puntos_cero.append(pto)
        elif sala_num is None:
            # En vista global, registrar si una sala operó en 0 mientras la otra tuvo flujo
            if s1_vacia:
                dias_sin_reg_s1.add(dia_actual)
            if s2_vacia:
                dias_sin_reg_s2.add(dia_actual)

        dia_actual += timedelta(days=1)

    if not puntos_cero and not dias_sin_reg_s1 and not dias_sin_reg_s2:
        return curva

    combinada: list[dict] = []
    for p in curva:
        b = p.get("bucket")
        if b and (dias_sin_reg_s1 or dias_sin_reg_s2):
            f_b = _normalizar_fecha(b)
            en_s1 = f_b in dias_sin_reg_s1
            en_s2 = f_b in dias_sin_reg_s2
            if en_s1 or en_s2:
                cp = dict(p)
                if en_s1:
                    cp["sin_registros_sala1"] = True
                if en_s2:
                    cp["sin_registros_sala2"] = True
                combinada.append(cp)
                continue
        combinada.append(p)

    if puntos_cero:
        combinada.extend(puntos_cero)
        combinada.sort(key=lambda item: str(item.get("bucket") or ""))
    return combinada


def _construir_cond_24h_sala2(
    h24_rows: list,
    expr_fecha: str = "e.fecha",
) -> tuple[str, dict]:
    conds: list[str] = []
    params: dict = {}
    for i, r in enumerate(h24_rows):
        f_ini_raw = getattr(r, "fecha_inicio", None)
        f_fin_raw = getattr(r, "fecha_fin", None)
        if not f_ini_raw or not f_fin_raw:
            continue
        sub = (getattr(r, "subespacio", None) or "todos").strip().lower()
        if sub in ("todos", "sala_2", "sala2"):
            k_i = f"c24_i_{i}"
            k_f = f"c24_f_{i}"
            conds.append(f"({expr_fecha} >= :{k_i} AND {expr_fecha} <= :{k_f})")
            params[k_i] = _normalizar_fecha(f_ini_raw)
            params[k_f] = _normalizar_fecha(f_fin_raw)
    return (" OR ".join(conds) if conds else "1=0"), params


def _resolver_codigo_sala(sala: Optional[str]) -> Optional[int]:
    if not sala:
        return None
    s_low = sala.strip().lower()
    if s_low in ("todos", "todas", ""):
        return None
    if any(k in s_low for k in ("csf02", "sala_1", "sala 1", "edificio 2", "locker", "2do piso")) or s_low == "1":
        return 1
    if any(k in s_low for k in ("csf04", "sala_2", "sala 2", "edificio 4", "pecera", "1er piso", "24h")) or s_low == "2":
        return 2
    return None


class AttendanceService:

    @staticmethod
    async def _build_attendance_filters(
        session: AsyncSession,
        espacio_id: int = 1,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        alcance: Optional[str] = "conformes",
        regimen_horario: Optional[str] = "todos",
        direccion: Optional[str] = "todos",
        dias_semana: Optional[str] = None,
        door: Optional[str] = None,
        perfil_visita: Optional[str] = "todos",
        marcajes: Optional[str] = "todos",
        sala: Optional[str] = None,
        carrera: Optional[str] = None,
        facultad: Optional[str] = None,
        cohorte: Optional[str] = None,
        incluir_pausas_bano: bool = True,
        desduplicar_rafagas: bool = True,
        incluir_funcionarios: bool = True,
        incluir_sin_identificar: bool = True,
    ) -> tuple[str, dict]:
        if isinstance(fecha_fin, str):
            try:
                fecha_fin = date.fromisoformat(fecha_fin[:10])
            except Exception:
                fecha_fin = None
        if isinstance(fecha_inicio, str):
            try:
                fecha_inicio = date.fromisoformat(fecha_inicio[:10])
            except Exception:
                fecha_inicio = None
        fin_exclusive = fecha_fin + timedelta(days=1) if fecha_fin else None
        conditions = [CLAUSULA_ESPACIO_ID]
        params: dict = {"espacio_id": espacio_id}

        if fecha_inicio:
            conditions.append("time >= :inicio")
            params["inicio"] = fecha_inicio
        if fin_exclusive:
            conditions.append("time < :fin")
            params["fin"] = fin_exclusive

        # Consulta dinámica de períodos especiales/24h activos en horarios_operacion con caché en memoria
        active_24h_rows = await obtener_horarios_operacion_cacheados(session, espacio_id)
        is_24h_sql = _construir_is_24h_sql(active_24h_rows, params, prefijo="h24")
        not_24h_sql = "(1=1)" if is_24h_sql == "1=0" else f"(NOT ({is_24h_sql}))"

        # Resolver calendario y contingencias en memoria para evitar subconsultas EXISTS por fila
        cal_data = await obtener_calendario_contingencias_cacheados(session, espacio_id)
        feriados_rango = [
            f for f in cal_data["feriados"]
            if (not fecha_inicio or f >= fecha_inicio) and (not fecha_fin or f <= fecha_fin)
        ]
        paros_fed_rango = [
            f for f in cal_data["paros_fed"]
            if (not fecha_inicio or f >= fecha_inicio) and (not fecha_fin or f <= fecha_fin)
        ]
        paros_car_rango = [
            f for f in cal_data["paros_car"]
            if (not fecha_inicio or f >= fecha_inicio) and (not fecha_fin or f <= fecha_fin)
        ]

        holiday_sql = (
            f"CAST(time AS DATE) IN ({', '.join(repr(f.isoformat()) for f in feriados_rango)})"
            if feriados_rango else "1=0"
        )
        strike_fed_sql = (
            f"CAST(time AS DATE) IN ({', '.join(repr(f.isoformat()) for f in paros_fed_rango)})"
            if paros_fed_rango else "1=0"
        )
        strike_car_sql = (
            f"CAST(time AS DATE) IN ({', '.join(repr(f.isoformat()) for f in paros_car_rango)})"
            if paros_car_rango else "1=0"
        )

        cont_clauses = []
        for idx_c, cca in enumerate(cal_data["contingencias"]):
            c_ini = cca.fecha_inicio if isinstance(cca.fecha_inicio, date) else date.fromisoformat(str(cca.fecha_inicio)[:10])
            c_fin = cca.fecha_fin if isinstance(cca.fecha_fin, date) else date.fromisoformat(str(cca.fecha_fin)[:10])
            if (fecha_fin and c_ini > fecha_fin) or (fecha_inicio and c_fin < fecha_inicio):
                continue
            partes_c = [f"(CAST(time AS DATE) BETWEEN '{c_ini.isoformat()}' AND '{c_fin.isoformat()}')"]
            sub_c = (getattr(cca, "subespacio", None) or "todos").strip()
            if sub_c == "sala_1":
                partes_c.append(DOOR_SALA_1_LIKE)
            elif sub_c == "sala_2":
                partes_c.append(DOOR_SALA_2_LIKE)
            h_ini_c = (getattr(cca, "hora_inicio", None) or "").strip()
            h_fin_c = (getattr(cca, "hora_fin", None) or "").strip()
            if h_ini_c and h_fin_c:
                p_hi = f"cca_hi_{idx_c}"
                p_hf = f"cca_hf_{idx_c}"
                params[p_hi] = h_ini_c if len(h_ini_c) > 5 else f"{h_ini_c}:00"
                params[p_hf] = h_fin_c if len(h_fin_c) > 5 else f"{h_fin_c}:00"
                partes_c.append(f"(CAST(time AS TIME) >= CAST(:{p_hi} AS TIME) AND CAST(time AS TIME) <= CAST(:{p_hf} AS TIME))")
            cont_clauses.append(f"({' AND '.join(partes_c)})")

        if feriados_rango and cont_clauses:
            closure_sql = f"({holiday_sql} OR {' OR '.join(cont_clauses)})"
        elif feriados_rango:
            closure_sql = f"({holiday_sql})"
        elif cont_clauses:
            closure_sql = f"({' OR '.join(cont_clauses)})"
        else:
            closure_sql = "1=0"

        reglas_regulares = await obtener_horarios_regulares_cacheados(session, espacio_id)
        regular_open_sql = _construir_sql_horario_regular(
            reglas_regulares,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            tolerancia_salida_min=TOLERANCIA_SALIDA_POST_CIERRE_MIN,
        )

        f_oficial_sql = f"({regular_open_sql} AND NOT ({holiday_sql}))" if feriados_rango else regular_open_sql

        regular_closed_sql = f"(NOT ({regular_open_sql}))"

        # 1. Alcance / Calidad
        dir_list = [d.strip().lower() for d in (direccion or "todos").split(",") if d.strip()]
        has_all_dirs = "todos" in dir_list or not dir_list

        if alcance == "conformes":
            base_conf = ["alerta_coherencia_fechas = 0", f"person_id_hash NOT LIKE '{PREFIJO_HASH_PRUEBA_EXCLUIDO}'"]
            if not marcajes or marcajes == "todos" or "5+" not in marcajes:
                if incluir_pausas_bano:
                    base_conf.append("(marcajes_totales < 5 OR (permanencia_min IS NOT NULL AND permanencia_min > 0))")
                else:
                    base_conf.append("marcajes_totales < 5")

            if desduplicar_rafagas:
                base_conf.append("NOT (marcajes_totales >= 5 AND permanencia_min IS NULL)")

            conditions.append(" AND ".join(base_conf))
        elif alcance == "anomalias":
            anom_conds = [
                "alerta_coherencia_fechas = 1",
                f"person_id_hash LIKE '{PREFIJO_HASH_PRUEBA_EXCLUIDO}'",
                f"({not_24h_sql} AND {regular_closed_sql})",
                f"({closure_sql})",
            ]
            if incluir_pausas_bano:
                anom_conds.append("(marcajes_totales >= 5 AND permanencia_min IS NULL)")
            else:
                anom_conds.append("marcajes_totales >= 5")
            conditions.append(f"({' OR '.join(anom_conds)})")

        # 2. Régimen de Horario (Desacoplado: Oficial, Delta 24h, Completo, Fuera de Horario, Cierres, Paros)
        regimen_list = [r.strip().lower() for r in (regimen_horario or "todos").split(",") if r.strip()]
        if regimen_list and "todos" not in regimen_list:
            regimen_clauses = []
            for r_item in regimen_list:
                if r_item in ("dentro_horario", "oficial", "regular"):
                    regimen_clauses.append(f_oficial_sql)
                elif r_item in ("24h_delta", "nocturno_24h", "delta_24h"):
                    regimen_clauses.append(f"({is_24h_sql} AND NOT ({regular_open_sql}))")
                elif r_item in ("24h_total", "24h", "extendido_24h"):
                    regimen_clauses.append(is_24h_sql)
                elif r_item == "fuera_horario":
                    regimen_clauses.append(f"(NOT ({regular_open_sql} OR {is_24h_sql}) AND NOT ({closure_sql}))")
                elif r_item in ("dias_cierre", "cierre", "feriados"):
                    regimen_clauses.append(f"({closure_sql})")
                elif r_item in ("paro_federado", "paro_general", "huelga_federada"):
                    regimen_clauses.append(f"({strike_fed_sql})")
                elif r_item in ("paro_carrera", "paro_facultad"):
                    regimen_clauses.append(f"({strike_car_sql})")
                elif r_item.startswith("horario_"):
                    try:
                        clean_item = r_item.replace("horario_", "")
                        is_delta = clean_item.endswith("_delta")
                        h_id = int(clean_item.replace("_delta", "").replace("_total", ""))
                        clave_h = f"horario_id:{h_id}"
                        if clave_h in cache_horarios_espacio:
                            h_row = cache_horarios_espacio[clave_h]
                        else:
                            sql_h = text("""
                                SELECT fecha_inicio, fecha_fin, hora_apertura, hora_cierre,
                                       cierre_dia_siguiente, es_continuo_24h, configuracion_dias, subespacio
                                FROM horarios_operacion WHERE id = :h_id
                            """)
                            h_row = (await session.execute(sql_h, {"h_id": h_id})).first()
                            cache_horarios_espacio[clave_h] = h_row
                        if h_row:
                            sub_clauses = []
                            p_ini = f"h_ini_{h_id}"
                            p_fin = f"h_fin_{h_id}"
                            if h_row.fecha_inicio and h_row.fecha_fin:
                                sub_clauses.append(f"(time >= :{p_ini} AND time <= :{p_fin})")
                                params[p_ini] = h_row.fecha_inicio
                                params[p_fin] = h_row.fecha_fin
                            elif h_row.fecha_inicio and not h_row.fecha_fin:
                                sub_clauses.append(f"(time >= :{p_ini})")
                                params[p_ini] = h_row.fecha_inicio
                            elif not h_row.fecha_inicio and h_row.fecha_fin:
                                sub_clauses.append(f"(time <= :{p_fin})")
                                params[p_fin] = h_row.fecha_fin
                            sub_h = _normalizar_subespacio_biblioteca(getattr(h_row, "subespacio", None))
                            if sub_h == "sala_1":
                                sub_clauses.append(DOOR_SALA_1_LIKE)
                            elif sub_h == "sala_2":
                                sub_clauses.append(DOOR_SALA_2_LIKE)
                            if not h_row.es_continuo_24h:
                                dias_h = _parsear_mapa_dias_regla(h_row)
                                cond_dias_h = _construir_sql_dias_regla(dias_h, TOLERANCIA_SALIDA_POST_CIERRE_MIN)
                                sub_clauses.append(f"({cond_dias_h})")
                            if sub_clauses:
                                base_sub = " AND ".join(sub_clauses)
                                if is_delta:
                                    regimen_clauses.append(f"(({base_sub}) AND NOT ({regular_open_sql}))")
                                else:
                                    regimen_clauses.append(f"({base_sub})")
                    except Exception:
                        pass
            if regimen_clauses:
                conditions.append(f"({' OR '.join(regimen_clauses)})")

        # 3. Dirección / Marcaje (Soporte dual para torniquetes y visitas consolidadas)
        if not has_all_dirs:
            dir_clauses = []
            for d in dir_list:
                if d in ("completos", "regular", "visita_regular"):
                    dir_clauses.append("((primera_entrada IS NOT NULL AND ultima_salida IS NOT NULL) OR marcajes_totales >= 2)")
                elif d in ("solo_ingreso", "sin_salida", "ingreso", "entradas"):
                    dir_clauses.append("(((salida_imputada = 0 OR door_entrada IS NOT NULL) AND marcajes_totales = 1) OR (primera_entrada IS NOT NULL AND ultima_salida IS NULL AND marcajes_totales = 1))")
                elif d in ("solo_salida", "sin_entrada", "salida", "salidas"):
                    dir_clauses.append("(((salida_imputada = 1 OR door_salida IS NOT NULL) AND marcajes_totales = 1) OR (primera_entrada IS NULL AND ultima_salida IS NOT NULL AND marcajes_totales = 1))")
            if dir_clauses:
                conditions.append(f"({' OR '.join(dir_clauses)})")

        # 4. Días de la semana
        if dias_semana:
            dias_map = {
                "domingo": 7,
                "lunes": 1,
                "martes": 2,
                "miercoles": 3,
                "miércoles": 3,
                "jueves": 4,
                "viernes": 5,
                "sabado": 6,
                "sábado": 6,
            }
            dias_solicitados = [d.strip().lower() for d in dias_semana.split(",") if d.strip().lower() in dias_map]
            if dias_solicitados:
                weekday_ints = [str(dias_map[d]) for d in dias_solicitados]
                conditions.append(f"dia_semana_iso IN ({','.join(weekday_ints)})")

        # 5. Filtro Dinámico por Sala (CSF02 124 asientos vs CSF04 Pecera 226 asientos)
        if sala and sala.lower() not in ("todos", "todas", ""):
            s_low = sala.strip().lower()
            if any(k in s_low for k in ["csf02", "sala_1", "sala 1", "edificio 2", "locker", "2do piso"]) or s_low == "1":
                conditions.append(DOOR_SALA_1_LIKE)
            elif any(k in s_low for k in ["csf04", "sala_2", "sala 2", "edificio 4", "pecera", "1er piso", "24h"]) or s_low == "2":
                conditions.append(DOOR_SALA_2_LIKE)
            else:
                p_sala = f"sala_{len(params)}"
                conditions.append(f"(door_entrada LIKE :{p_sala} OR door_salida LIKE :{p_sala})")
                params[p_sala] = f"%{sala}%"

        # 6. Puerta / Torniquete Multi-Sala
        if door and door != "todos":
            doors_list = [d.strip().lower() for d in door.split(",") if d.strip()]
            if doors_list:
                door_clauses = []
                for d in doors_list:
                    # Torniquetes Sala 1 (CSF02)
                    if d in ("s1_principal", "2202", "2184", "csf02_in02", "csf02_out02"):
                        door_clauses.append("(door_entrada LIKE '%CSF02_320 CTRA IN 02%' OR door_salida LIKE '%CSF02_320 CTRA OUT 02%' OR door_entrada IN ('2202', '2202.0') OR door_salida IN ('2184', '2184.0'))")
                    elif d in ("s1_universal", "2177", "2170", "csf02_in01", "csf02_out01"):
                        door_clauses.append("(door_entrada LIKE '%CSF02_320 CTRA IN 01%' OR door_salida LIKE '%CSF02_320 CTRA OUT 01%' OR door_entrada IN ('2177', '2177.0') OR door_salida IN ('2170', '2170.0'))")
                    elif d in ("1", "t1", "torniquete 1"):
                        door_clauses.append(DOOR_SALA_1_LIKE)
                    # Torniquetes Sala 2 (CSF04 Pecera)
                    elif d in ("s2_principal", "2592", "2587", "csf04_in01", "csf04_out"):
                        door_clauses.append("(door_entrada LIKE '%CSF04_110 IN 01%' OR door_salida LIKE '%CSF04_110 OUT%' OR door_entrada IN ('2592', '2592.0') OR door_salida IN ('2587', '2587.0'))")
                    elif d in ("s2_universal", "3411", "3416", "csf04_in02", "csf04_out02"):
                        door_clauses.append("(door_entrada LIKE '%CSF04_110 IN 02%' OR door_salida LIKE '%CSF04_110 OUT 02%' OR door_entrada IN ('3411', '3411.0') OR door_salida IN ('3416', '3416.0'))")
                    elif d in ("2", "t2", "torniquete 2"):
                        door_clauses.append(DOOR_SALA_2_LIKE)
                    else:
                        pname = f"door_{len(params)}"
                        door_clauses.append(f"(door_entrada LIKE :{pname} OR door_salida LIKE :{pname})")
                        params[pname] = f"%{d}%"
                if door_clauses:
                    conditions.append(f"({' OR '.join(door_clauses)})")

        # 7. Filtros Curriculares (Carrera y Facultad)
        if carrera and carrera.lower() not in ("todas", "todos", ""):
            p_carr = f"carr_{len(params)}"
            conditions.append(f"(person_id_hash IN (SELECT dec_c.person_id_hash FROM dim_estudiante_carrera dec_c WHERE dec_c.carr_nombre LIKE :{p_carr}) OR carrera LIKE :{p_carr})")
            params[p_carr] = f"%{carrera.strip()}%"

        if facultad and facultad.lower() not in ("todas", "todos", ""):
            p_fac = f"fac_{len(params)}"
            conditions.append(f"(person_id_hash IN (SELECT dec_f.person_id_hash FROM dim_estudiante_carrera dec_f WHERE dec_f.facultad LIKE :{p_fac}) OR facultad LIKE :{p_fac})")
            params[p_fac] = f"%{facultad.strip()}%"

        # 8. Filtro por Cohorte / Año de Ingreso
        if cohorte and str(cohorte).lower() not in ("todas", "todos", "", "0", "null"):
            p_coh = f"coh_{len(params)}"
            conditions.append(f"person_id_hash IN (SELECT dec_c.person_id_hash FROM dim_estudiante_carrera dec_c WHERE dec_c.anho_ingreso = :{p_coh})")
            try:
                params[p_coh] = int(str(cohorte).strip())
            except ValueError:
                params[p_coh] = 0

        # 6. Perfil de Visita
        if perfil_visita and perfil_visita != "todos":
            p_list = [p.strip() for p in perfil_visita.split(",") if p.strip()]
            p_clauses = []
            for p in p_list:
                if p == "rebote":
                    p_clauses.append("permanencia_min < 15")
                elif p == "estandar":
                    p_clauses.append("(permanencia_min >= 15 AND permanencia_min <= 120)")
                elif p == "profundo":
                    p_clauses.append("permanencia_min > 120")
            if p_clauses and len(p_clauses) < 3:
                conditions.append(f"({' OR '.join(p_clauses)})")

        # 7. Cantidad de marcajes
        if marcajes and marcajes != "todos":
            m_list = [m.strip() for m in marcajes.split(",") if m.strip()]
            m_clauses = []
            for m in m_list:
                if m == "1":
                    m_clauses.append("marcajes_totales = 1")
                elif m == "2":
                    m_clauses.append("marcajes_totales = 2")
                elif m in ("3-4", "3", "4", "3_4"):
                    m_clauses.append("marcajes_totales BETWEEN 3 AND 4")
                elif m in ("5+", "5", "5 ") or m.startswith("5"):
                    m_clauses.append("marcajes_totales >= 5")
            if m_clauses and len(m_clauses) < 4:
                conditions.append(f"({' OR '.join(m_clauses)})")

        # 8. Composición de usuarios (funcionarios / accesos sin persona identificada)
        if not incluir_funcionarios:
            conditions.append("COALESCE(facultad, '') <> 'Funcionario'")
        if not incluir_sin_identificar:
            conditions.append("COALESCE(facultad, '') <> 'Sin persona identificada'")

        where_str = " AND ".join(conditions)
        used_params = {k: v for k, v in params.items() if f":{k}" in where_str}
        return where_str, used_params

    # ------------------------------------------------------------------
    # KPIs generales
    # ------------------------------------------------------------------
    @staticmethod
    async def get_kpis(
        session: AsyncSession,
        espacio_id: int = 1,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        alcance: str = "conformes",
        regimen_horario: Optional[str] = "todos",
        direccion: Optional[str] = "todos",
        dias_semana: Optional[str] = None,
        door: Optional[str] = None,
        perfil_visita: Optional[str] = "todos",
        marcajes: Optional[str] = "todos",
        sala: Optional[str] = None,
        carrera: Optional[str] = None,
        facultad: Optional[str] = None,
        cohorte: Optional[str] = None,
        incluir_pausas_bano: bool = True,
        desduplicar_rafagas: bool = True,
        incluir_funcionarios: bool = True,
        incluir_sin_identificar: bool = True,
    ) -> dict:
        where_sql, params = await AttendanceService._build_attendance_filters(
            session=session,
            espacio_id=espacio_id,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            alcance=alcance,
            regimen_horario=regimen_horario,
            direccion=direccion,
            dias_semana=dias_semana,
            door=door,
            perfil_visita=perfil_visita,
            marcajes=marcajes,
            sala=sala,
            carrera=carrera,
            facultad=facultad,
            cohorte=cohorte,
            incluir_pausas_bano=incluir_pausas_bano,
            desduplicar_rafagas=desduplicar_rafagas,
            incluir_funcionarios=incluir_funcionarios,
            incluir_sin_identificar=incluir_sin_identificar,
        )
        params["rebote"] = UMBRAL_REBOTE_MIN

        sql = text(f"""
            WITH base AS (
                SELECT
                    person_id_hash,
                    time,
                    hora_dia,
                    permanencia_min,
                    door_entrada,
                    door_salida
                FROM eventos_asistencia
                WHERE {where_sql}
            ),
            kpis AS (
                SELECT
                    COUNT(*)                                        AS total_registros,
                    COUNT(DISTINCT person_id_hash)                  AS usuarios_unicos,
                    SUM(CASE WHEN {DOOR_SALA_1_LIKE} THEN 1 ELSE 0 END) AS total_registros_sala1,
                    SUM(CASE WHEN {DOOR_SALA_2_LIKE} THEN 1 ELSE 0 END) AS total_registros_sala2,
                    COUNT(DISTINCT CASE WHEN {DOOR_SALA_1_LIKE} THEN person_id_hash END) AS usuarios_unicos_sala1,
                    COUNT(DISTINCT CASE WHEN {DOOR_SALA_2_LIKE} THEN person_id_hash END) AS usuarios_unicos_sala2,
                    COUNT(DISTINCT CAST(time AS DATE))              AS dias_operativos,
                    ROUND(CAST(AVG(CAST(permanencia_min AS FLOAT)) AS DECIMAL(10,2)), 2) AS permanencia_promedio_min,
                    ROUND(
                        100.0 * SUM(CASE WHEN permanencia_min < :rebote THEN 1 ELSE 0 END)
                        / NULLIF(SUM(CASE WHEN permanencia_min IS NOT NULL THEN 1 ELSE 0 END), 0),
                    2)                                              AS tasa_rebote_pct,
                    ROUND(SUM(permanencia_min) / 60.0, 1)           AS horas_estudiante_total
                FROM base
            ),
            mediana AS (
                SELECT TOP 1
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY permanencia_min) OVER () AS permanencia_mediana_min
                FROM base
                WHERE permanencia_min IS NOT NULL
            ),
            peak AS (
                SELECT TOP 1 hora_dia AS hora, COUNT(DISTINCT person_id_hash) AS total
                FROM base
                GROUP BY hora_dia
                ORDER BY total DESC
            )
            SELECT
                kp.total_registros,
                kp.usuarios_unicos,
                kp.total_registros_sala1,
                kp.total_registros_sala2,
                kp.usuarios_unicos_sala1,
                kp.usuarios_unicos_sala2,
                kp.dias_operativos,
                kp.permanencia_promedio_min,
                kp.tasa_rebote_pct,
                kp.horas_estudiante_total,
                COALESCE((SELECT permanencia_mediana_min FROM mediana), 0) AS permanencia_mediana_min,
                (SELECT hora FROM peak) AS hora_punta_num
            FROM kpis kp
        """)
        row = (await session.execute(sql, params)).first()

        curva = await AttendanceService.get_realtime_presence_curve(
            session=session,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            espacio_id=espacio_id,
            alcance=alcance,
            regimen_horario=regimen_horario,
            direccion=direccion,
            dias_semana=dias_semana,
            door=door,
            perfil_visita=perfil_visita,
            marcajes=marcajes,
            sala=sala,
            carrera=carrera,
            facultad=facultad,
            cohorte=cohorte,
            incluir_pausas_bano=incluir_pausas_bano,
            desduplicar_rafagas=desduplicar_rafagas,
            incluir_funcionarios=incluir_funcionarios,
            incluir_sin_identificar=incluir_sin_identificar,
            aplicar_default_7d=False,
        )
        max_concurrente = max((int(r.get("personas_unicas", 0)) for r in curva), default=0)
        max_sala1 = max((int(r.get("personas_sala1", 0)) for r in curva), default=0)
        max_sala2 = max((int(r.get("personas_sala2", 0)) for r in curva), default=0)

        dias = row.dias_operativos or 1 if row else 1
        total = row.total_registros or 0 if row else 0
        unicos = row.usuarios_unicos or 0 if row else 0
        mediana = row.permanencia_mediana_min if row and row.permanencia_mediana_min is not None else 0
        hora_punta = _extraer_hora_pico_curva(curva) or (
            f"{row.hora_punta_num:02d}:00 hrs" if row and row.hora_punta_num is not None else "14:00 hrs"
        )

        return {
            "total_registros":          total,
            "usuarios_unicos":          unicos,
            "total_registros_sala1":    int(getattr(row, "total_registros_sala1", 0) or 0) if row else 0,
            "total_registros_sala2":    int(getattr(row, "total_registros_sala2", 0) or 0) if row else 0,
            "usuarios_unicos_sala1":    int(getattr(row, "usuarios_unicos_sala1", 0) or 0) if row else 0,
            "usuarios_unicos_sala2":    int(getattr(row, "usuarios_unicos_sala2", 0) or 0) if row else 0,
            "dias_operativos":          dias,
            "promedio_marcajes_diarios": round(total / dias, 1),
            "tasa_recurrencia_mensual": round((total / unicos) if unicos else 0, 2),
            "permanencia_promedio_min": float(row.permanencia_promedio_min or 0) if row else 0.0,
            "permanencia_mediana_min":  float(mediana),
            "tasa_rebote_pct":          float(row.tasa_rebote_pct or 0) if row else 0.0,
            "horas_estudiante_total":   float(row.horas_estudiante_total or 0) if row else 0.0,
            "hora_punta":               hora_punta,
            "max_aforo_historico":      int(max_concurrente),
            "max_aforo_sala1":          int(max_sala1),
            "max_aforo_sala2":          int(max_sala2),
        }

    # ------------------------------------------------------------------
    # Aforo concurrente en tiempo real
    # ------------------------------------------------------------------
    @staticmethod
    async def get_occupancy_realtime(
        session: AsyncSession,
        espacio_id: int = 1,
        sala: Optional[str] = None,
        incluir_funcionarios: bool = True,
        incluir_sin_identificar: bool = True,
    ) -> dict:
        from app.domain.models import Espacio

        sala_num_filtro = _resolver_codigo_sala(sala)
        conds_vivo = [
            CLAUSULA_ESPACIO_ID,
            "time >= CAST(CAST(GETDATE() AS DATE) AS DATETIME)",
            "time <= GETDATE()",
            "alerta_coherencia_fechas = 0",
            f"person_id_hash NOT LIKE '{PREFIJO_HASH_PRUEBA_EXCLUIDO}'",
        ]
        params: dict = {"espacio_id": espacio_id}
        if sala_num_filtro == 1:
            conds_vivo.append(DOOR_SALA_1_LIKE)
        elif sala_num_filtro == 2:
            conds_vivo.append(DOOR_SALA_2_LIKE)
        if not incluir_funcionarios:
            conds_vivo.append("COALESCE(facultad, '') <> 'Funcionario'")
        if not incluir_sin_identificar:
            conds_vivo.append("COALESCE(facultad, '') <> 'Sin persona identificada'")

        where_vivo = " AND ".join(conds_vivo)
        h24_rows = await obtener_horarios_operacion_cacheados(session, espacio_id)
        cond_s2_24h, h24_params = _construir_cond_24h_sala2(h24_rows, expr_fecha="CAST(GETDATE() AS DATE)")
        params.update(h24_params)
        reglas_regulares = await obtener_horarios_regulares_cacheados(session, espacio_id)
        hoy_local = date.today()
        _, expr_cierre_efectivo = _construir_expresiones_limites_presencia(
            reglas_regulares,
            cond_s2_24h,
            fecha_inicio=hoy_local,
            fecha_fin=hoy_local,
        )

        sql_vivo = text(f"""
            WITH EventosConContexto AS (
                SELECT
                    person_id_hash,
                    time,
                    CAST(time AS DATE) AS fecha,
                    dia_semana_iso,
                    COALESCE(facultad, '') AS facultad,
                    CASE WHEN door_salida IS NOT NULL OR ultima_salida IS NOT NULL OR salida_imputada = 1 THEN 1 ELSE 0 END AS es_salida,
                    CASE
                        WHEN door_entrada LIKE '%CSF02%' OR door_salida LIKE '%CSF02%' THEN 1
                        WHEN door_entrada LIKE '%CSF04%' OR door_salida LIKE '%CSF04%' THEN 2
                        ELSE 0
                    END AS sala_num,
                    LAG(CASE WHEN door_salida IS NOT NULL OR ultima_salida IS NOT NULL OR salida_imputada = 1 THEN 1 ELSE 0 END)
                        OVER (PARTITION BY CAST(time AS DATE), person_id_hash ORDER BY time) AS prev_es_salida,
                    LAG(time)
                        OVER (PARTITION BY CAST(time AS DATE), person_id_hash ORDER BY time) AS prev_time,
                    LEAD(CASE WHEN door_salida IS NOT NULL OR ultima_salida IS NOT NULL OR salida_imputada = 1 THEN 1 ELSE 0 END)
                        OVER (PARTITION BY CAST(time AS DATE), person_id_hash ORDER BY time) AS raw_next_es_salida
                FROM eventos_asistencia
                WHERE {where_vivo}
            ),
            EventosLimpios AS (
                SELECT
                    person_id_hash,
                    time,
                    fecha,
                    dia_semana_iso,
                    facultad,
                    es_salida,
                    sala_num,
                    LEAD(time) OVER (PARTITION BY fecha, person_id_hash ORDER BY time) AS next_time
                FROM EventosConContexto
                WHERE (
                    prev_es_salida IS NULL
                    OR prev_es_salida <> es_salida
                    OR DATEDIFF(MINUTE, prev_time, time) > 120
                )
                AND NOT (
                    es_salida = 0
                    AND COALESCE(prev_es_salida, -1) = 1
                    AND DATEDIFF(SECOND, COALESCE(prev_time, time), time) <= 60
                    AND raw_next_es_salida IS NULL
                )
            )
            SELECT
                COALESCE(COUNT(*), 0) AS aforo_actual,
                COALESCE(SUM(CASE WHEN e.sala_num = 1 THEN 1 ELSE 0 END), 0) AS aforo_sala1,
                COALESCE(SUM(CASE WHEN e.sala_num = 2 THEN 1 ELSE 0 END), 0) AS aforo_sala2
            FROM EventosLimpios e
            CROSS APPLY (
                SELECT
                    {expr_cierre_efectivo} AS cierre_efectivo
            ) AS lim
            WHERE e.es_salida = 0
              AND e.next_time IS NULL
              AND (
                  (e.facultad <> 'Sin persona identificada'
                   AND DATEDIFF(MINUTE, e.time, GETDATE()) <= {VENTANA_ESPERA_VIVO_MIN}
                   AND (lim.cierre_efectivo >= GETDATE() OR (e.time >= lim.cierre_efectivo AND DATEDIFF(MINUTE, e.time, GETDATE()) <= {IMPUTACION_SALIDA_PERDIDA_MIN})))
                  OR
                  (e.facultad = 'Sin persona identificada'
                   AND DATEDIFF(MINUTE, e.time, GETDATE()) <= {IMPUTACION_SALIDA_PERDIDA_MIN}
                   AND (lim.cierre_efectivo >= GETDATE() OR e.time >= lim.cierre_efectivo))
              )
        """)
        row = (await session.execute(sql_vivo, params)).first()
        aforo = max(0, int(getattr(row, "aforo_actual", 0) or 0))
        aforo_s1 = max(0, int(getattr(row, "aforo_sala1", 0) or 0))
        aforo_s2 = max(0, int(getattr(row, "aforo_sala2", 0) or 0))

        cond_ts = [CLAUSULA_ESPACIO_ID, "time <= GETDATE()"]
        ultimo_s1: Optional[str] = None
        ultimo_s2: Optional[str] = None
        if sala_num_filtro in (1, 2):
            cond_ts.append(DOOR_SALA_1_LIKE if sala_num_filtro == 1 else DOOR_SALA_2_LIKE)
            sql_ts = text(f"""
                SELECT MAX(time) AS ultimo_ts
                FROM eventos_asistencia
                WHERE {' AND '.join(cond_ts)}
            """)
            ts_val = (await session.execute(sql_ts, {"espacio_id": espacio_id})).scalar()
            if isinstance(ts_val, datetime):
                if sala_num_filtro == 1:
                    ultimo_s1 = ts_val.isoformat()
                else:
                    ultimo_s2 = ts_val.isoformat()
            else:
                ts_val = datetime.now()
        else:
            sql_ts = text(f"""
                SELECT
                    MAX(time) AS ultimo_ts,
                    MAX(CASE WHEN {DOOR_SALA_1_LIKE} THEN time END) AS ultimo_ts_sala1,
                    MAX(CASE WHEN {DOOR_SALA_2_LIKE} THEN time END) AS ultimo_ts_sala2
                FROM eventos_asistencia
                WHERE {' AND '.join(cond_ts)}
            """)
            row_ts = (await session.execute(sql_ts, {"espacio_id": espacio_id})).first()
            ts_raw = getattr(row_ts, "ultimo_ts", None) if row_ts is not None else None
            ts_s1_raw = getattr(row_ts, "ultimo_ts_sala1", None) if row_ts is not None else None
            ts_s2_raw = getattr(row_ts, "ultimo_ts_sala2", None) if row_ts is not None else None
            ts_val = ts_raw if isinstance(ts_raw, datetime) else datetime.now()
            if isinstance(ts_s1_raw, datetime):
                ultimo_s1 = ts_s1_raw.isoformat()
            if isinstance(ts_s2_raw, datetime):
                ultimo_s2 = ts_s2_raw.isoformat()

        cap_s1 = 150
        cap_s2 = 126
        try:
            salas_bd = await AttendanceService.get_salas_biblioteca(session, espacio_id)
        except Exception:
            salas_bd = []
        for s_bd in salas_bd or []:
            cod_s = str(s_bd.get("codigo") or "")
            sid_s = s_bd.get("id")
            if "CSF02" in cod_s or sid_s == 1:
                cap_s1 = int(s_bd.get("capacidad_asientos") or 150)
            elif "CSF04" in cod_s or sid_s == 2:
                cap_s2 = int(s_bd.get("capacidad_asientos") or 126)

        capacidad_max: Optional[int] = None
        if sala_num_filtro == 1:
            capacidad_max = cap_s1
        elif sala_num_filtro == 2:
            capacidad_max = cap_s2
        else:
            espacio_obj = (await session.execute(select(Espacio.capacidad_max).where(Espacio.id == espacio_id))).scalar_one_or_none()
            capacidad_max = int(espacio_obj or CAPACIDAD_BIBLIOTECA)

        def _clasificar_nivel(pct_val: float) -> str:
            if pct_val >= UMBRAL_ALERTA_85 * 100:
                return "critico"
            if pct_val >= UMBRAL_ALERTA_70 * 100:
                return "preventivo"
            return "normal"

        pct = round(aforo / capacidad_max * 100, 1) if capacidad_max > 0 else 0.0
        pct_s1 = round(aforo_s1 / cap_s1 * 100, 1) if cap_s1 > 0 else 0.0
        pct_s2 = round(aforo_s2 / cap_s2 * 100, 1) if cap_s2 > 0 else 0.0

        return {
            "aforo_actual":         aforo,
            "capacidad_maxima":     capacidad_max,
            "ocupacion_pct":        pct,
            "nivel_alerta":         _clasificar_nivel(pct),
            "timestamp":            ts_val.isoformat(),
            "aforo_sala1":          aforo_s1,
            "aforo_sala2":          aforo_s2,
            "capacidad_sala1":      cap_s1,
            "capacidad_sala2":      cap_s2,
            "ocupacion_pct_sala1":  pct_s1,
            "ocupacion_pct_sala2":  pct_s2,
            "nivel_alerta_sala1":   _clasificar_nivel(pct_s1),
            "nivel_alerta_sala2":   _clasificar_nivel(pct_s2),
            "ultimo_marcaje_sala1": ultimo_s1,
            "ultimo_marcaje_sala2": ultimo_s2,
        }

    @staticmethod
    async def get_hourly_flow(
        session: AsyncSession,
        fecha_inicio: Optional[date],
        fecha_fin: Optional[date],
        espacio_id: int = 1,
        alcance: str = "conformes",
        regimen_horario: Optional[str] = "todos",
        direccion: Optional[str] = "todos",
        dias_semana: Optional[str] = None,
        door: Optional[str] = None,
        perfil_visita: Optional[str] = "todos",
        marcajes: Optional[str] = "todos",
        sala: Optional[str] = None,
        carrera: Optional[str] = None,
        facultad: Optional[str] = None,
        cohorte: Optional[str] = None,
        incluir_pausas_bano: bool = True,
        desduplicar_rafagas: bool = True,
        incluir_funcionarios: bool = True,
        incluir_sin_identificar: bool = True,
    ) -> list[dict]:
        if fecha_inicio is None or fecha_fin is None:
            sql_max = text("""
                SELECT COALESCE(CAST(MAX(bucket) AS DATE), CAST(GETDATE() AS DATE))
                FROM aforo_horario_biblioteca WITH (NOEXPAND)
                WHERE espacio_id = :espacio_id
            """)
            max_date = (await session.execute(sql_max, {"espacio_id": espacio_id})).scalar() or date.today()
            if fecha_fin is None:
                fecha_fin = max_date
            if fecha_inicio is None:
                fecha_inicio = max_date - timedelta(days=6)

        where_sql, params = await AttendanceService._build_attendance_filters(
            session=session,
            espacio_id=espacio_id,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            alcance=alcance,
            regimen_horario=regimen_horario,
            direccion=direccion,
            dias_semana=dias_semana,
            door=door,
            perfil_visita=perfil_visita,
            marcajes=marcajes,
            sala=sala,
            carrera=carrera,
            facultad=facultad,
            cohorte=cohorte,
            incluir_pausas_bano=incluir_pausas_bano,
            desduplicar_rafagas=desduplicar_rafagas,
            incluir_funcionarios=incluir_funcionarios,
            incluir_sin_identificar=incluir_sin_identificar,
        )

        sql = text(f"""
            SELECT 
                DATEADD(hour, DATEDIFF(hour, 0, time), 0) AS bucket,
                SUM(CASE WHEN primera_entrada IS NOT NULL OR door_entrada IS NOT NULL OR salida_imputada = 0 THEN 1 ELSE 0 END) AS ingresos,
                SUM(CASE WHEN ultima_salida IS NOT NULL OR door_salida IS NOT NULL OR salida_imputada = 1 THEN 1 ELSE 0 END) AS salidas,
                COUNT(DISTINCT person_id_hash) AS personas_unicas,
                COUNT(DISTINCT CASE WHEN (door_entrada LIKE '%CSF02%' OR door_salida LIKE '%CSF02%') THEN person_id_hash END) AS personas_sala1,
                COUNT(DISTINCT CASE WHEN (door_entrada LIKE '%CSF04%' OR door_salida LIKE '%CSF04%') THEN person_id_hash END) AS personas_sala2,
                SUM(CASE WHEN (door_entrada LIKE '%CSF02%' OR door_salida LIKE '%CSF02%') AND (primera_entrada IS NOT NULL OR door_entrada IS NOT NULL OR salida_imputada = 0) THEN 1 ELSE 0 END) AS ingresos_sala1,
                SUM(CASE WHEN (door_entrada LIKE '%CSF04%' OR door_salida LIKE '%CSF04%') AND (primera_entrada IS NOT NULL OR door_entrada IS NOT NULL OR salida_imputada = 0) THEN 1 ELSE 0 END) AS ingresos_sala2
            FROM eventos_asistencia
            WHERE {where_sql}
            GROUP BY DATEADD(hour, DATEDIFF(hour, 0, time), 0)
            ORDER BY bucket ASC
        """)

        rows = (await session.execute(sql, params)).fetchall()

        return [
            {
                "bucket":          r.bucket.isoformat(),
                "ingresos":        int(r.ingresos),
                "salidas":         int(r.salidas),
                "personas_unicas": int(r.personas_unicas),
                "personas_sala1":  int(r.personas_sala1 or 0),
                "personas_sala2":  int(r.personas_sala2 or 0),
                "ingresos_sala1":  int(r.ingresos_sala1 or 0),
                "ingresos_sala2":  int(r.ingresos_sala2 or 0),
            }
            for r in rows
        ]

    @staticmethod
    async def get_realtime_presence_curve(
        session: AsyncSession,
        fecha_inicio: Optional[date],
        fecha_fin: Optional[date],
        espacio_id: int = 1,
        alcance: str = "conformes",
        regimen_horario: Optional[str] = "todos",
        direccion: Optional[str] = "todos",
        dias_semana: Optional[str] = None,
        door: Optional[str] = None,
        perfil_visita: Optional[str] = "todos",
        marcajes: Optional[str] = "todos",
        sala: Optional[str] = None,
        carrera: Optional[str] = None,
        facultad: Optional[str] = None,
        cohorte: Optional[str] = None,
        incluir_pausas_bano: bool = True,
        desduplicar_rafagas: bool = True,
        incluir_funcionarios: bool = True,
        incluir_sin_identificar: bool = True,
        aplicar_default_7d: bool = True,
    ) -> list[dict]:
        if aplicar_default_7d and (fecha_inicio is None or fecha_fin is None):
            sql_max = text("""
                SELECT COALESCE(CAST(MAX(bucket) AS DATE), CAST(GETDATE() AS DATE))
                FROM aforo_horario_biblioteca WITH (NOEXPAND)
                WHERE espacio_id = :espacio_id
            """)
            max_date = (await session.execute(sql_max, {"espacio_id": espacio_id})).scalar() or date.today()
            if fecha_fin is None:
                fecha_fin = max_date
            if fecha_inicio is None:
                fecha_inicio = max_date - timedelta(days=6)

        usar_cache = isinstance(session, AsyncSession)
        clave_curva = (
            espacio_id,
            str(fecha_inicio) if fecha_inicio else None,
            str(fecha_fin) if fecha_fin else None,
            alcance or "conformes",
            regimen_horario or "todos",
            direccion or "todos",
            dias_semana or "",
            door or "",
            perfil_visita or "todos",
            marcajes or "todos",
            sala or "",
            carrera or "",
            facultad or "",
            str(cohorte or ""),
            bool(incluir_pausas_bano),
            bool(incluir_funcionarios),
            bool(incluir_sin_identificar),
        )
        if usar_cache and clave_curva in _cache_curva_presencia:
            return _cache_curva_presencia[clave_curva]

        async def _ejecutar() -> list[dict]:
            # Para emparejar intervalos [entrada, salida] preservamos ambas direcciones y desduplicamos ráfagas en ventana SQL
            where_sql, base_params = await AttendanceService._build_attendance_filters(
                session=session,
                espacio_id=espacio_id,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                alcance="anomalias" if alcance == "anomalias" else "todos",
                regimen_horario=regimen_horario,
                direccion="todos",
                dias_semana=dias_semana,
                door=door,
                perfil_visita="todos",
                marcajes="todos",
                sala=sala,
                carrera=carrera,
                facultad=facultad,
                cohorte=cohorte,
                incluir_pausas_bano=incluir_pausas_bano,
                desduplicar_rafagas=False,
                incluir_funcionarios=incluir_funcionarios,
                incluir_sin_identificar=incluir_sin_identificar,
            )

            if (alcance or "conformes") == "conformes":
                where_sql = f"{where_sql} AND alerta_coherencia_fechas = 0 AND person_id_hash NOT LIKE '{PREFIJO_HASH_PRUEBA_EXCLUIDO}'"

            filtro_perfil_sesion = ""
            if perfil_visita and perfil_visita != "todos":
                p_list = [p.strip() for p in perfil_visita.split(",") if p.strip()]
                p_clauses = []
                for p in p_list:
                    if p == "rebote":
                        p_clauses.append("DATEDIFF(MINUTE, t_entrada, t_salida) < 15")
                    elif p == "estandar":
                        p_clauses.append("(DATEDIFF(MINUTE, t_entrada, t_salida) >= 15 AND DATEDIFF(MINUTE, t_entrada, t_salida) <= 120)")
                    elif p == "profundo":
                        p_clauses.append("DATEDIFF(MINUTE, t_entrada, t_salida) > 120")
                if p_clauses and len(p_clauses) < 3:
                    filtro_perfil_sesion = f"WHERE ({' OR '.join(p_clauses)})"

            h24_rows = await obtener_horarios_operacion_cacheados(session, espacio_id)
            cond_s2_24h, h24_params = _construir_cond_24h_sala2(h24_rows, expr_fecha="e.fecha")
            ses_params = {**base_params, **h24_params}
            reglas_regulares = await obtener_horarios_regulares_cacheados(session, espacio_id)
            expr_piso_apertura, expr_cierre_efectivo = _construir_expresiones_limites_presencia(
                reglas_regulares,
                cond_s2_24h,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
            )

            sql_sesiones = text(f"""
                WITH EventosConContexto AS (
                    SELECT
                        person_id_hash,
                        time,
                        CAST(time AS DATE) AS fecha,
                        dia_semana_iso,
                        COALESCE(facultad, '') AS facultad,
                        CASE WHEN door_salida IS NOT NULL OR ultima_salida IS NOT NULL OR salida_imputada = 1 THEN 1 ELSE 0 END AS es_salida,
                        CASE
                            WHEN door_entrada LIKE '%CSF02%' OR door_salida LIKE '%CSF02%' THEN 1
                            WHEN door_entrada LIKE '%CSF04%' OR door_salida LIKE '%CSF04%' THEN 2
                            ELSE 0
                        END AS sala_num,
                        LAG(CASE WHEN door_salida IS NOT NULL OR ultima_salida IS NOT NULL OR salida_imputada = 1 THEN 1 ELSE 0 END)
                            OVER (PARTITION BY CAST(time AS DATE), person_id_hash ORDER BY time) AS prev_es_salida,
                        LAG(time)
                            OVER (PARTITION BY CAST(time AS DATE), person_id_hash ORDER BY time) AS prev_time,
                        LEAD(CASE WHEN door_salida IS NOT NULL OR ultima_salida IS NOT NULL OR salida_imputada = 1 THEN 1 ELSE 0 END)
                            OVER (PARTITION BY CAST(time AS DATE), person_id_hash ORDER BY time) AS raw_next_es_salida
                    FROM eventos_asistencia
                    WHERE {where_sql}
                      AND time <= GETDATE()
                ),
                EventosLimpios AS (
                    SELECT
                        person_id_hash,
                        time,
                        fecha,
                        dia_semana_iso,
                        facultad,
                        es_salida,
                        sala_num,
                        LEAD(time) OVER (PARTITION BY fecha, person_id_hash ORDER BY time) AS next_time,
                        LEAD(es_salida) OVER (PARTITION BY fecha, person_id_hash ORDER BY time) AS next_es_salida,
                        LAG(time) OVER (PARTITION BY fecha, person_id_hash ORDER BY time) AS clean_prev_time,
                        LAG(es_salida) OVER (PARTITION BY fecha, person_id_hash ORDER BY time) AS clean_prev_es_salida
                    FROM EventosConContexto
                    WHERE (
                        prev_es_salida IS NULL
                        OR prev_es_salida <> es_salida
                        OR DATEDIFF(MINUTE, prev_time, time) > 120
                    )
                    AND NOT (
                        es_salida = 0
                        AND COALESCE(prev_es_salida, -1) = 1
                        AND DATEDIFF(SECOND, COALESCE(prev_time, time), time) <= 60
                        AND raw_next_es_salida IS NULL
                    )
                ),
                SesionesBase AS (
                    SELECT
                        e.fecha,
                        e.sala_num,
                        CASE
                            WHEN e.es_salida = 0 THEN e.time
                            ELSE floor_in.piso_in
                        END AS t_entrada,
                        CASE
                            WHEN e.es_salida = 1 THEN e.time
                            WHEN e.next_es_salida = 1 AND e.next_time IS NOT NULL THEN e.next_time
                            WHEN e.fecha = CAST(GETDATE() AS DATE)
                                 AND e.facultad <> 'Sin persona identificada'
                                 AND e.next_time IS NULL
                                 AND DATEDIFF(MINUTE, e.time, GETDATE()) <= {VENTANA_ESPERA_VIVO_MIN} THEN cap_vivo.t_vivo
                            ELSE cap_imp.t_imp
                        END AS t_salida
                    FROM EventosLimpios e
                    CROSS APPLY (
                        SELECT
                            CAST(e.fecha AS DATETIME) AS inicio_dia,
                            DATEADD(SECOND, 86399, CAST(e.fecha AS DATETIME)) AS fin_dia,
                            {expr_piso_apertura} AS piso_apertura,
                            {expr_cierre_efectivo} AS cierre_efectivo
                    ) AS lim
                    CROSS APPLY (
                        SELECT MAX(v) AS piso_in
                        FROM (VALUES
                            (DATEADD(MINUTE, -{IMPUTACION_ENTRADA_PERDIDA_MIN}, e.time)),
                            (lim.inicio_dia),
                            (CASE WHEN lim.piso_apertura < e.time THEN lim.piso_apertura ELSE lim.inicio_dia END),
                            (COALESCE(e.clean_prev_time, lim.inicio_dia))
                        ) AS t(v)
                    ) AS floor_in
                    CROSS APPLY (
                        SELECT MIN(v) AS t_vivo
                        FROM (VALUES
                            (GETDATE()),
                            (lim.fin_dia),
                            (CASE WHEN lim.cierre_efectivo > e.time THEN lim.cierre_efectivo ELSE lim.fin_dia END)
                        ) AS t(v)
                    ) AS cap_vivo
                    CROSS APPLY (
                        SELECT MIN(v) AS t_imp
                        FROM (VALUES
                            (DATEADD(MINUTE, {IMPUTACION_SALIDA_PERDIDA_MIN}, e.time)),
                            (GETDATE()),
                            (lim.fin_dia),
                            (CASE WHEN lim.cierre_efectivo > e.time THEN lim.cierre_efectivo ELSE lim.fin_dia END),
                            (COALESCE(e.next_time, lim.fin_dia))
                        ) AS t(v)
                    ) AS cap_imp
                    WHERE (
                        e.es_salida = 0
                        OR (e.es_salida = 1 AND (e.clean_prev_es_salida IS NULL OR e.clean_prev_es_salida = 1))
                    )
                      AND e.time <= GETDATE()
                ),
                Sesiones AS (
                    SELECT fecha, sala_num, t_entrada, t_salida
                    FROM SesionesBase
                    {filtro_perfil_sesion}
                )
                SELECT fecha, sala_num, t_entrada, t_salida
                FROM Sesiones
            """)

            sql_flujo = text(f"""
                WITH FlujoBruto AS (
                    SELECT
                        DATEADD(hour, DATEDIFF(hour, 0, time), 0) AS bucket,
                        CAST(time AS DATE) AS fecha,
                        SUM(CASE WHEN door_salida IS NULL AND ultima_salida IS NULL AND COALESCE(salida_imputada, 0) = 0 THEN 1 ELSE 0 END) AS ingresos,
                        SUM(CASE WHEN door_salida IS NOT NULL OR ultima_salida IS NOT NULL OR salida_imputada = 1 THEN 1 ELSE 0 END) AS salidas,
                        SUM(CASE WHEN (door_entrada LIKE '%CSF02%' OR door_salida LIKE '%CSF02%') AND (door_salida IS NULL AND ultima_salida IS NULL AND COALESCE(salida_imputada, 0) = 0) THEN 1 ELSE 0 END) AS ingresos_sala1,
                        SUM(CASE WHEN (door_entrada LIKE '%CSF04%' OR door_salida LIKE '%CSF04%') AND (door_salida IS NULL AND ultima_salida IS NULL AND COALESCE(salida_imputada, 0) = 0) THEN 1 ELSE 0 END) AS ingresos_sala2
                    FROM eventos_asistencia
                    WHERE {where_sql}
                      AND time <= GETDATE()
                    GROUP BY DATEADD(hour, DATEDIFF(hour, 0, time), 0), CAST(time AS DATE)
                )
                SELECT
                    bucket,
                    fecha,
                    ingresos,
                    salidas,
                    ingresos_sala1,
                    ingresos_sala2,
                    GETDATE() AS ahora_servidor
                FROM FlujoBruto
                ORDER BY bucket ASC
            """)

            sesiones_rows = (await session.execute(sql_sesiones, ses_params)).fetchall()
            flujo_rows = (await session.execute(sql_flujo, base_params)).fetchall()

            ahora_servidor = None
            if flujo_rows:
                r0 = flujo_rows[0]
                ahora_servidor = getattr(r0, "ahora_servidor", None)
                if ahora_servidor is None and isinstance(r0, tuple) and len(r0) > 6:
                    ahora_servidor = r0[6]
            if not isinstance(ahora_servidor, datetime):
                ahora_servidor = datetime.now()

            curva_calculada = _calcular_curva_presencia_por_hora(sesiones_rows, flujo_rows, ahora_servidor)
            cal_data = await obtener_calendario_contingencias_cacheados(session, espacio_id)
            inicio_por_sala = await obtener_inicio_registros_salas_cacheados(session, espacio_id)
            return _rellenar_dias_operativos_sin_registros(
                curva=curva_calculada,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                ahora_servidor=ahora_servidor,
                reglas_regulares=reglas_regulares,
                sala=sala,
                dias_semana=dias_semana,
                cal_data=cal_data,
                alcance=alcance,
                regimen_horario=regimen_horario,
                inicio_por_sala=inicio_por_sala,
            )

        if not usar_cache:
            return await _ejecutar()

        entrada_lock = _locks_curva_presencia.get(clave_curva)
        if entrada_lock is None:
            entrada_lock = [asyncio.Lock(), 0]
            _locks_curva_presencia[clave_curva] = entrada_lock
        entrada_lock[1] += 1
        lock = entrada_lock[0]
        try:
            async with lock:
                if clave_curva in _cache_curva_presencia:
                    return list(_cache_curva_presencia[clave_curva])
                curva = await _ejecutar()
                _cache_curva_presencia[clave_curva] = list(curva)
                return list(curva)
        finally:
            entrada_lock[1] -= 1
            if entrada_lock[1] <= 0 and _locks_curva_presencia.get(clave_curva) is entrada_lock:
                _locks_curva_presencia.pop(clave_curva, None)


    # ------------------------------------------------------------------
    # Heatmap semanal
    # ------------------------------------------------------------------
    @staticmethod
    async def get_heatmap(
        session: AsyncSession,
        espacio_id: int = 1,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        alcance: Optional[str] = "conformes",
        regimen_horario: Optional[str] = "todos",
        direccion: Optional[str] = "todos",
        dias_semana: Optional[str] = None,
        door: Optional[str] = None,
        perfil_visita: Optional[str] = "todos",
        marcajes: Optional[str] = "todos",
        sala: Optional[str] = None,
        carrera: Optional[str] = None,
        facultad: Optional[str] = None,
        cohorte: Optional[str] = None,
        incluir_pausas_bano: bool = True,
        desduplicar_rafagas: bool = True,
        incluir_funcionarios: bool = True,
        incluir_sin_identificar: bool = True,
    ) -> list[dict]:
        """
        Matriz: día_semana (0=Lun … 6=Dom) × hora (0-23) → ingresos_promedio.
        Soporta filtrado multidimensional por fechas, salas, carreras, facultades y cohortes.
        """
        tiene_filtros_particulares = bool(
            sala or carrera or facultad or cohorte or door or dias_semana
            or (perfil_visita and perfil_visita != "todos")
            or (marcajes and marcajes != "todos")
            or (regimen_horario and regimen_horario != "todos")
            or (direccion and direccion != "todos")
            or (alcance and alcance != "conformes")
            or not incluir_pausas_bano
            or not desduplicar_rafagas
            or not incluir_funcionarios
            or not incluir_sin_identificar
        )

        if not tiene_filtros_particulares:
            # Vía acelerada con vista indexada aforo_horario_biblioteca
            where_clauses = [CLAUSULA_ESPACIO_ID]
            params: dict = {"espacio_id": espacio_id}

            if fecha_inicio:
                where_clauses.append("bucket >= :fecha_inicio")
                params["fecha_inicio"] = fecha_inicio
            if fecha_fin:
                where_clauses.append("bucket < :fecha_fin_exclusive")
                params["fecha_fin_exclusive"] = fecha_fin + timedelta(days=1)

            where_sql = " AND ".join(where_clauses)
            sql = text(f"""
                SELECT
                    ((DATEPART(WEEKDAY, bucket) + @@DATEFIRST - 2) % 7 + 1) AS dia_semana_iso,
                    DATEPART(HOUR, bucket)    AS hora,
                    ROUND(CAST(AVG(CAST(ingresos AS FLOAT)) AS DECIMAL(10,2)), 2) AS ingresos_promedio
                FROM aforo_horario_biblioteca WITH (NOEXPAND)
                WHERE {where_sql}
                GROUP BY ((DATEPART(WEEKDAY, bucket) + @@DATEFIRST - 2) % 7 + 1), DATEPART(HOUR, bucket)
                ORDER BY dia_semana_iso, hora
            """)
            rows = (await session.execute(sql, params)).fetchall()
        else:
            # Vía analítica con filtros completos sobre eventos_asistencia
            where_sql, params = await AttendanceService._build_attendance_filters(
                session=session,
                espacio_id=espacio_id,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                alcance=alcance or "conformes",
                regimen_horario=regimen_horario or "todos",
                direccion=direccion or "todos",
                dias_semana=dias_semana,
                door=door,
                perfil_visita=perfil_visita or "todos",
                marcajes=marcajes or "todos",
                sala=sala,
                carrera=carrera,
                facultad=facultad,
                cohorte=cohorte,
                incluir_pausas_bano=incluir_pausas_bano,
                desduplicar_rafagas=desduplicar_rafagas,
                incluir_funcionarios=incluir_funcionarios,
                incluir_sin_identificar=incluir_sin_identificar,
            )
            sql = text(f"""
                WITH conteo_diario AS (
                    SELECT
                        dia_semana_iso,
                        hora_dia AS hora,
                        CAST(time AS DATE) AS dia_fecha,
                        COUNT(*) AS eventos
                    FROM eventos_asistencia
                    WHERE {where_sql}
                    GROUP BY dia_semana_iso, hora_dia, CAST(time AS DATE)
                )
                SELECT
                    dia_semana_iso,
                    hora,
                    ROUND(CAST(AVG(CAST(eventos AS FLOAT)) AS DECIMAL(10,2)), 2) AS ingresos_promedio
                FROM conteo_diario
                GROUP BY dia_semana_iso, hora
                ORDER BY dia_semana_iso, hora
            """)
            rows = (await session.execute(sql, params)).fetchall()

        # SQL Server DATEPART(WEEKDAY) defaults to Sunday=1, Monday=2, ..., Saturday=7
        DOW_MAP = {1: 6, 2: 0, 3: 1, 4: 2, 5: 3, 6: 4, 7: 5}
        DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

        return [
            {
                "dia_semana":        (int(getattr(r, "dia_semana_iso", 0)) - 1) if getattr(r, "dia_semana_iso", None) is not None else DOW_MAP[r.dia_semana],
                "dia_nombre":        DIAS[(int(getattr(r, "dia_semana_iso", 0)) - 1) if getattr(r, "dia_semana_iso", None) is not None else DOW_MAP[r.dia_semana]],
                "hora":              r.hora,
                "ingresos_promedio": float(r.ingresos_promedio or 0),
            }
            for r in rows
        ]

    @staticmethod
    async def get_peak_valley_bands(
        session: AsyncSession,
        espacio_id: int = 1,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
    ) -> list[dict]:
        where_clauses = ["espacio_id = :espacio_id"]
        params: dict = {"espacio_id": espacio_id}
        if fecha_inicio:
            where_clauses.append("bucket >= :inicio")
            params["inicio"] = fecha_inicio
        if fecha_fin:
            where_clauses.append("bucket < :fin")
            params["fin"] = fecha_fin + timedelta(days=1)
        where_sql = " AND ".join(where_clauses)
        sql = text(f"""
            SELECT 
                DATEPART(HOUR, bucket) AS hora,
                ROUND(CAST(AVG(CAST(ingresos AS FLOAT)) AS DECIMAL(10,1)), 1) AS promedio_ingresos,
                MAX(ingresos) AS max_ingresos,
                SUM(ingresos) AS total_ingresos
            FROM aforo_horario_biblioteca WITH (NOEXPAND)
            WHERE {where_sql}
            GROUP BY DATEPART(HOUR, bucket)
            ORDER BY hora ASC
        """)
        rows = (await session.execute(sql, params)).fetchall()
        max_avg = max([float(r.promedio_ingresos or 0) for r in rows], default=1.0)
        result = []
        for r in rows:
            prom = float(r.promedio_ingresos or 0)
            ratio = prom / max_avg if max_avg > 0 else 0
            if ratio >= 0.70:
                nivel = "Pico Saturación"
                color = "#DC2626"
            elif ratio >= 0.35:
                nivel = "Demanda Media"
                color = "#C59B27"
            else:
                nivel = "Valle Operativo"
                color = "#003865"
            result.append({
                "hora": f"{r.hora:02d}:00",
                "promedio_ingresos": prom,
                "max_ingresos": int(r.max_ingresos or 0),
                "total_ingresos": int(r.total_ingresos or 0),
                "nivel": nivel,
                "color": color,
            })
        return result

    @staticmethod
    async def get_weekly_evolution(
        session: AsyncSession,
        espacio_id: int = 1,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        alcance: Optional[str] = "conformes",
        regimen_horario: Optional[str] = "todos",
        direccion: Optional[str] = "todos",
        dias_semana: Optional[str] = None,
        door: Optional[str] = None,
        perfil_visita: Optional[str] = "todos",
        marcajes: Optional[str] = "todos",
        sala: Optional[str] = None,
        carrera: Optional[str] = None,
        facultad: Optional[str] = None,
        cohorte: Optional[str] = None,
        incluir_pausas_bano: bool = True,
        desduplicar_rafagas: bool = True,
        incluir_funcionarios: bool = True,
        incluir_sin_identificar: bool = True,
    ) -> list[dict]:
        where_sql, params = await AttendanceService._build_attendance_filters(
            session=session,
            espacio_id=espacio_id,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            alcance=alcance or "conformes",
            regimen_horario=regimen_horario or "todos",
            direccion=direccion or "todos",
            dias_semana=dias_semana,
            door=door,
            perfil_visita=perfil_visita or "todos",
            marcajes=marcajes or "todos",
            sala=sala,
            carrera=carrera,
            facultad=facultad,
            cohorte=cohorte,
            incluir_pausas_bano=incluir_pausas_bano,
            desduplicar_rafagas=desduplicar_rafagas,
            incluir_funcionarios=incluir_funcionarios,
            incluir_sin_identificar=incluir_sin_identificar,
        )
        sql = text(f"""
            SELECT 
                CONCAT('Semana ', RIGHT(CONCAT('0', DATEPART(ISO_WEEK, time)), 2)) AS semana_iso,
                MIN(CAST(time AS DATE)) AS inicio_semana,
                COUNT(*) AS total_asistencias,
                COUNT(DISTINCT person_id_hash) AS usuarios_unicos
            FROM eventos_asistencia
            WHERE {where_sql}
            GROUP BY DATEPART(ISO_WEEK, time)
            ORDER BY MIN(time) ASC
        """)
        rows = (await session.execute(sql, params)).fetchall()
        return [
            {
                "semana_iso": r.semana_iso,
                "inicio_semana": r.inicio_semana.isoformat() if r.inicio_semana else "",
                "total_asistencias": int(r.total_asistencias),
                "usuarios_unicos": int(r.usuarios_unicos),
            }
            for r in rows
        ]

    @staticmethod
    async def get_monthly_volume(
        session: AsyncSession,
        espacio_id: int = 1,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        alcance: Optional[str] = "conformes",
        regimen_horario: Optional[str] = "todos",
        direccion: Optional[str] = "todos",
        dias_semana: Optional[str] = None,
        door: Optional[str] = None,
        perfil_visita: Optional[str] = "todos",
        marcajes: Optional[str] = "todos",
        sala: Optional[str] = None,
        carrera: Optional[str] = None,
        facultad: Optional[str] = None,
        cohorte: Optional[str] = None,
        incluir_pausas_bano: bool = True,
        desduplicar_rafagas: bool = True,
        incluir_funcionarios: bool = True,
        incluir_sin_identificar: bool = True,
    ) -> list[dict]:
        where_sql, params = await AttendanceService._build_attendance_filters(
            session=session,
            espacio_id=espacio_id,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            alcance=alcance or "conformes",
            regimen_horario=regimen_horario or "todos",
            direccion=direccion or "todos",
            dias_semana=dias_semana,
            door=door,
            perfil_visita=perfil_visita or "todos",
            marcajes=marcajes or "todos",
            sala=sala,
            carrera=carrera,
            facultad=facultad,
            cohorte=cohorte,
            incluir_pausas_bano=incluir_pausas_bano,
            desduplicar_rafagas=desduplicar_rafagas,
            incluir_funcionarios=incluir_funcionarios,
            incluir_sin_identificar=incluir_sin_identificar,
        )
        sql = text(f"""
            SELECT 
                CONVERT(VARCHAR(7), time, 126) AS mes,
                COUNT(*) AS total_asistencias,
                COUNT(DISTINCT CAST(time AS DATE)) AS dias_activos,
                ROUND(CAST(COUNT(*) AS DECIMAL(10,2)) / NULLIF(COUNT(DISTINCT CAST(time AS DATE)), 0), 1) AS promedio_diario
            FROM eventos_asistencia
            WHERE {where_sql}
            GROUP BY CONVERT(VARCHAR(7), time, 126)
            ORDER BY mes ASC
        """)
        rows = (await session.execute(sql, params)).fetchall()
        return [
            {
                "mes": r.mes,
                "total_asistencias": int(r.total_asistencias),
                "dias_activos": int(r.dias_activos or 0),
                "promedio_diario": float(r.promedio_diario or 0),
            }
            for r in rows
        ]

    @staticmethod
    async def get_academic_milestones_comparison(
        session: AsyncSession,
        espacio_id: int = 1,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        alcance: Optional[str] = "conformes",
        regimen_horario: Optional[str] = "todos",
        direccion: Optional[str] = "todos",
        dias_semana: Optional[str] = None,
        door: Optional[str] = None,
        perfil_visita: Optional[str] = "todos",
        marcajes: Optional[str] = "todos",
        sala: Optional[str] = None,
        carrera: Optional[str] = None,
        facultad: Optional[str] = None,
        cohorte: Optional[str] = None,
        incluir_pausas_bano: bool = True,
        desduplicar_rafagas: bool = True,
        incluir_funcionarios: bool = True,
        incluir_sin_identificar: bool = True,
    ) -> list[dict]:
        where_sql, params = await AttendanceService._build_attendance_filters(
            session=session,
            espacio_id=espacio_id,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            alcance=alcance or "conformes",
            regimen_horario=regimen_horario or "todos",
            direccion=direccion or "todos",
            dias_semana=dias_semana,
            door=door,
            perfil_visita=perfil_visita or "todos",
            marcajes=marcajes or "todos",
            sala=sala,
            carrera=carrera,
            facultad=facultad,
            cohorte=cohorte,
            incluir_pausas_bano=incluir_pausas_bano,
            desduplicar_rafagas=desduplicar_rafagas,
            incluir_funcionarios=incluir_funcionarios,
            incluir_sin_identificar=incluir_sin_identificar,
        )
        sql = text(f"""
            WITH hourly AS (
                SELECT 
                    CAST(time AS DATE) AS dia,
                    hora_dia AS hora,
                    COUNT(DISTINCT person_id_hash) AS aforo_hora
                FROM eventos_asistencia
                WHERE {where_sql}
                GROUP BY CAST(time AS DATE), hora_dia
            ),
            daily_peak AS (
                SELECT 
                    dia, 
                    MAX(aforo_hora) AS pico_hora_dia
                FROM hourly
                GROUP BY dia
            ),
            ad AS (
                SELECT CAST(time AS DATE) AS dia, COUNT(*) AS total_dia
                FROM eventos_asistencia
                WHERE {where_sql}
                GROUP BY CAST(time AS DATE)
            )
            SELECT 
                CASE 
                    WHEN ca.is_exam_period = 1 THEN 'Exámenes / Certámenes'
                    WHEN ca.is_break = 1       THEN 'Receso Académico'
                    WHEN ca.is_holiday = 1     THEN 'Feriado'
                    ELSE 'Clases Regulares'
                END AS hito,
                COUNT(ad.dia) AS dias_totales,
                ROUND(AVG(ad.total_dia * 1.0), 1) AS promedio_diario,
                COALESCE(MAX(ad.total_dia), 0) AS max_dia,
                COALESCE(MAX(dp.pico_hora_dia), 0) AS aforo_pico_simultaneo,
                SUM(ad.total_dia) AS total_asistencias
            FROM ad
            LEFT JOIN daily_peak dp ON ad.dia = dp.dia
            LEFT JOIN calendario_academico ca ON ad.dia = ca.fecha
            GROUP BY 
                CASE 
                    WHEN ca.is_exam_period = 1 THEN 'Exámenes / Certámenes'
                    WHEN ca.is_break = 1       THEN 'Receso Académico'
                    WHEN ca.is_holiday = 1     THEN 'Feriado'
                    ELSE 'Clases Regulares'
                END
            ORDER BY promedio_diario DESC
        """)
        rows = (await session.execute(sql, params)).fetchall()
        return [
            {
                "hito": r.hito,
                "dias_totales": int(r.dias_totales),
                "promedio_diario": float(r.promedio_diario or 0),
                "max_dia": int(r.max_dia or 0),
                "aforo_pico_simultaneo": int(getattr(r, "aforo_pico_simultaneo", 0) or 0),
                "total_asistencias": int(r.total_asistencias or 0),
            }
            for r in rows
        ]

    @staticmethod
    async def get_door_usage(
        session: AsyncSession,
        espacio_id: int = 1,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        alcance: Optional[str] = "conformes",
        regimen_horario: Optional[str] = "todos",
        direccion: Optional[str] = "todos",
        dias_semana: Optional[str] = None,
        door: Optional[str] = None,
        perfil_visita: Optional[str] = "todos",
        marcajes: Optional[str] = "todos",
        sala: Optional[str] = None,
        carrera: Optional[str] = None,
        facultad: Optional[str] = None,
        cohorte: Optional[str] = None,
        incluir_pausas_bano: bool = True,
        desduplicar_rafagas: bool = True,
        incluir_funcionarios: bool = True,
        incluir_sin_identificar: bool = True,
    ) -> list[dict]:
        where_sql, params = await AttendanceService._build_attendance_filters(
            session=session,
            espacio_id=espacio_id,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            alcance=alcance,
            regimen_horario=regimen_horario,
            direccion=direccion,
            dias_semana=dias_semana,
            door=door,
            perfil_visita=perfil_visita,
            marcajes=marcajes,
            sala=sala,
            carrera=carrera,
            facultad=facultad,
            cohorte=cohorte,
            incluir_pausas_bano=incluir_pausas_bano,
            desduplicar_rafagas=desduplicar_rafagas,
            incluir_funcionarios=incluir_funcionarios,
            incluir_sin_identificar=incluir_sin_identificar,
        )
        sql = text(f"""
            SELECT 
                COALESCE(SUM(CASE WHEN door_entrada LIKE '%CSF02_320 CTRA IN 02%' OR door_entrada IN ('2202', '2202.0') THEN 1 ELSE 0 END), 0) AS entradas_s1_prin,
                COALESCE(SUM(CASE WHEN door_salida LIKE '%CSF02_320 CTRA OUT 02%' OR door_salida IN ('2184', '2184.0') THEN 1 ELSE 0 END), 0) AS salidas_s1_prin,
                COALESCE(SUM(CASE WHEN door_entrada LIKE '%CSF02_320 CTRA IN 01%' OR door_entrada IN ('2177', '2177.0') THEN 1 ELSE 0 END), 0) AS entradas_s1_univ,
                COALESCE(SUM(CASE WHEN door_salida LIKE '%CSF02_320 CTRA OUT 01%' OR door_salida IN ('2170', '2170.0') THEN 1 ELSE 0 END), 0) AS salidas_s1_univ,
                COALESCE(SUM(CASE WHEN door_entrada LIKE '%CSF04_110 IN 01%' OR door_entrada IN ('2592', '2592.0') THEN 1 ELSE 0 END), 0) AS entradas_s2_prin,
                COALESCE(SUM(CASE WHEN door_salida LIKE '%CSF04_110 OUT%' OR door_salida IN ('2587', '2587.0') THEN 1 ELSE 0 END), 0) AS salidas_s2_prin,
                COALESCE(SUM(CASE WHEN door_entrada LIKE '%CSF04_110 IN 02%' OR door_entrada IN ('3411', '3411.0') THEN 1 ELSE 0 END), 0) AS entradas_s2_univ,
                COALESCE(SUM(CASE WHEN door_salida LIKE '%CSF04_110 OUT 02%' OR door_salida IN ('3416', '3416.0') THEN 1 ELSE 0 END), 0) AS salidas_s2_univ
            FROM eventos_asistencia
            WHERE {where_sql}
        """)
        fila = (await session.execute(sql, params)).fetchone()
        ent_s1_p = int(fila.entradas_s1_prin or 0) if fila else 0
        sal_s1_p = int(fila.salidas_s1_prin or 0) if fila else 0
        ent_s1_u = int(fila.entradas_s1_univ or 0) if fila else 0
        sal_s1_u = int(fila.salidas_s1_univ or 0) if fila else 0
        ent_s2_p = int(fila.entradas_s2_prin or 0) if fila else 0
        sal_s2_p = int(fila.salidas_s2_prin or 0) if fila else 0
        ent_s2_u = int(fila.entradas_s2_univ or 0) if fila else 0
        sal_s2_u = int(fila.salidas_s2_univ or 0) if fila else 0

        return [
            {
                "puerta": "Torniquete Principal (2202 / 2184)",
                "puerta_id": "S1_PRINCIPAL",
                "cod_in": "CSF02_320 CTRA IN 02",
                "id_in": "2202",
                "cod_out": "CSF02_320 CTRA OUT 02",
                "id_out": "2184",
                "sala": NOMBRE_SALA_1_CSF02,
                "tipo_acceso": "Principal",
                "entradas": ent_s1_p,
                "salidas": sal_s1_p,
                "total": ent_s1_p + sal_s1_p,
            },
            {
                "puerta": "Acceso Universal Discapacitados (2177 / 2170)",
                "puerta_id": "S1_UNIVERSAL",
                "cod_in": "CSF02_320 CTRA IN 01",
                "id_in": "2177",
                "cod_out": "CSF02_320 CTRA OUT 01",
                "id_out": "2170",
                "sala": NOMBRE_SALA_1_CSF02,
                "tipo_acceso": "Universal",
                "entradas": ent_s1_u,
                "salidas": sal_s1_u,
                "total": ent_s1_u + sal_s1_u,
            },
            {
                "puerta": "Torniquete Principal (2592 / 2587)",
                "puerta_id": "S2_PRINCIPAL",
                "cod_in": "CSF04_110 IN 01",
                "id_in": "2592",
                "cod_out": "CSF04_110 OUT",
                "id_out": "2587",
                "sala": NOMBRE_SALA_2_CSF04,
                "tipo_acceso": "Principal",
                "entradas": ent_s2_p,
                "salidas": sal_s2_p,
                "total": ent_s2_p + sal_s2_p,
            },
            {
                "puerta": "Acceso Universal Discapacitados (3411 / 3416)",
                "puerta_id": "S2_UNIVERSAL",
                "cod_in": "CSF04_110 IN 02_Door_1",
                "id_in": "3411",
                "cod_out": "CSF04_110 OUT 02_Door_1",
                "id_out": "3416",
                "sala": NOMBRE_SALA_2_CSF04,
                "tipo_acceso": "Universal",
                "entradas": ent_s2_u,
                "salidas": sal_s2_u,
                "total": ent_s2_u + sal_s2_u,
            },
        ]

    @staticmethod
    async def get_salas_biblioteca(
        session: AsyncSession,
        espacio_id: int = 1,
    ) -> list[dict]:
        """Retorna lista dinámica de salas registradas en base de datos para el espacio."""
        sql = text("""
            SELECT id, espacio_id, codigo, nombre, edificio, piso, descripcion,
                   capacidad_asientos, permite_horario_extendido,
                   puerta_principal_in, puerta_principal_out,
                   puerta_universal_in, puerta_universal_out, activo
            FROM salas_biblioteca
            WHERE espacio_id = :espacio_id AND activo = 1
            ORDER BY id
        """)
        rows = (await session.execute(sql, {"espacio_id": espacio_id})).fetchall()
        return [
            {
                "id": r.id,
                "codigo": r.codigo,
                "nombre": r.nombre,
                "edificio": r.edificio,
                "piso": r.piso,
                "descripcion": r.descripcion,
                "capacidad_asientos": r.capacidad_asientos,
                "permite_horario_extendido": bool(r.permite_horario_extendido),
                "puerta_principal_in": r.puerta_principal_in,
                "puerta_principal_out": r.puerta_principal_out,
                "puerta_universal_in": r.puerta_universal_in,
                "puerta_universal_out": r.puerta_universal_out,
                "activo": bool(r.activo),
            }
            for r in rows
        ]

    @staticmethod
    async def create_sala_biblioteca(
        session: AsyncSession,
        data: dict,
    ) -> dict:
        """Permite registrar una nueva sala de estudio o biblioteca dinámicamente."""
        from app.domain.models import SalaBiblioteca
        nueva = SalaBiblioteca(
            espacio_id=data.get("espacio_id", 1),
            codigo=data["codigo"],
            nombre=data["nombre"],
            edificio=data["edificio"],
            piso=data.get("piso", "1er Piso"),
            descripcion=data.get("descripcion", ""),
            capacidad_asientos=data.get("capacidad_asientos", 100),
            permite_horario_extendido=data.get("permite_horario_extendido", False),
            puerta_principal_in=data.get("puerta_principal_in"),
            puerta_principal_out=data.get("puerta_principal_out"),
            puerta_universal_in=data.get("puerta_universal_in"),
            puerta_universal_out=data.get("puerta_universal_out"),
            activo=True,
        )
        session.add(nueva)
        await session.commit()
        await session.refresh(nueva)
        invalidar_cache_horarios(nueva.espacio_id)
        return {
            "id": nueva.id,
            "codigo": nueva.codigo,
            "nombre": nueva.nombre,
            "edificio": nueva.edificio,
            "capacidad_asientos": nueva.capacidad_asientos,
        }

    @staticmethod
    async def update_capacidad_sala_biblioteca(
        session: AsyncSession,
        sala_id: int,
        capacidad_asientos: int,
    ) -> dict:
        """Actualiza la capacidad de una sala y sincroniza el aforo total del espacio."""
        from app.domain.models import SalaBiblioteca, Espacio
        from fastapi import HTTPException

        sala = await session.get(SalaBiblioteca, sala_id)
        if not sala:
            raise HTTPException(status_code=404, detail=f"Sala con ID {sala_id} no encontrada")

        sala.capacidad_asientos = capacidad_asientos
        espacio_id = sala.espacio_id
        await session.flush()

        # Recalcular suma de capacidades de salas activas
        sql_sum = text("""
            SELECT COALESCE(SUM(capacidad_asientos), 0) AS total_cap
            FROM salas_biblioteca
            WHERE espacio_id = :espacio_id AND activo = 1
        """)
        total_cap = (await session.execute(sql_sum, {"espacio_id": espacio_id})).scalar() or 0

        if total_cap > 0:
            espacio = await session.get(Espacio, espacio_id)
            if espacio:
                espacio.capacidad_max = total_cap

        await session.commit()
        await session.refresh(sala)
        invalidar_cache_horarios(espacio_id)

        return {
            "sala_id": sala.id,
            "codigo": sala.codigo,
            "nombre": sala.nombre,
            "capacidad_asientos": sala.capacidad_asientos,
            "espacio_id": espacio_id,
            "capacidad_total_espacio": total_cap,
        }

    @staticmethod
    async def get_rooms_comparison(
        session: AsyncSession,
        espacio_id: int = 1,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        alcance: Optional[str] = "todos",
        regimen_horario: Optional[str] = "todos",
        direccion: Optional[str] = "todos",
        dias_semana: Optional[str] = None,
        door: Optional[str] = None,
        perfil_visita: Optional[str] = "todos",
        marcajes: Optional[str] = "todos",
        sala: Optional[str] = None,
        carrera: Optional[str] = None,
        facultad: Optional[str] = None,
        cohorte: Optional[str] = None,
        incluir_pausas_bano: bool = True,
        desduplicar_rafagas: bool = True,
        incluir_funcionarios: bool = True,
        incluir_sin_identificar: bool = True,
    ) -> dict:
        """Retorna comparativa analítica entre las salas de biblioteca (Sala 1 CSF02 vs Sala 2 CSF04)."""
        where_sql, params = await AttendanceService._build_attendance_filters(
            session=session,
            espacio_id=espacio_id,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            alcance=alcance,
            regimen_horario=regimen_horario,
            direccion=direccion,
            dias_semana=dias_semana,
            door=door,
            perfil_visita=perfil_visita,
            marcajes=marcajes,
            sala=sala,
            carrera=carrera,
            facultad=facultad,
            cohorte=cohorte,
            incluir_pausas_bano=incluir_pausas_bano,
            desduplicar_rafagas=desduplicar_rafagas,
            incluir_funcionarios=incluir_funcionarios,
            incluir_sin_identificar=incluir_sin_identificar,
        )

        sql_totals = text(f"""
            SELECT 
                CASE 
                    WHEN (door_entrada LIKE '%CSF02%' OR door_salida LIKE '%CSF02%') THEN 'Sala 1 (CSF02)'
                    WHEN (door_entrada LIKE '%CSF04%' OR door_salida LIKE '%CSF04%') THEN 'Sala 2 (CSF04 Pecera)'
                    ELSE 'Otra Sala'
                END AS sala_nombre,
                COUNT(*) AS total_marcajes,
                COUNT(DISTINCT person_id_hash) AS usuarios_unicos,
                SUM(CASE WHEN door_entrada IS NOT NULL THEN 1 ELSE 0 END) AS entradas,
                SUM(CASE WHEN door_salida IS NOT NULL THEN 1 ELSE 0 END) AS salidas
            FROM eventos_asistencia
            WHERE {where_sql}
            GROUP BY 
                CASE 
                    WHEN (door_entrada LIKE '%CSF02%' OR door_salida LIKE '%CSF02%') THEN 'Sala 1 (CSF02)'
                    WHEN (door_entrada LIKE '%CSF04%' OR door_salida LIKE '%CSF04%') THEN 'Sala 2 (CSF04 Pecera)'
                    ELSE 'Otra Sala'
                END
        """)
        rows_totals = (await session.execute(sql_totals, params)).fetchall()

        sql_hourly = text(f"""
            SELECT 
                hora_dia AS hora,
                SUM(CASE WHEN (door_entrada LIKE '%CSF02%' OR door_salida LIKE '%CSF02%') AND door_entrada IS NOT NULL THEN 1 ELSE 0 END) AS entradas_sala1,
                SUM(CASE WHEN (door_entrada LIKE '%CSF04%' OR door_salida LIKE '%CSF04%') AND door_entrada IS NOT NULL THEN 1 ELSE 0 END) AS entradas_sala2
            FROM eventos_asistencia
            WHERE {where_sql}
            GROUP BY hora_dia
            ORDER BY hora
        """)
        rows_hourly = (await session.execute(sql_hourly, params)).fetchall()

        map_hourly = {r.hora: r for r in rows_hourly}
        flujo_horario_comparado = []
        for h in range(24):
            rh = map_hourly.get(h)
            flujo_horario_comparado.append({
                "hora": f"{h:02d}:00",
                "hora_num": h,
                "entradas_sala1": int(rh.entradas_sala1) if rh else 0,
                "entradas_sala2": int(rh.entradas_sala2) if rh else 0,
            })

        caps = await obtener_capacidades_salas_cacheadas(session, espacio_id)
        cap_s1 = caps["sala_1"]
        cap_s2 = caps["sala_2"]

        map_salas = {}
        for r in rows_totals:
            if "CSF02" in r.sala_nombre or "Sala 1" in r.sala_nombre:
                map_salas[NOMBRE_SALA_1_CSF02] = r
            elif "CSF04" in r.sala_nombre or "Sala 2" in r.sala_nombre:
                map_salas[NOMBRE_SALA_2_CSF04] = r

        total_global = sum(r.total_marcajes for r in rows_totals)

        def construir_sala(nombre: str, cap: int, edificio: str, permite_24h: bool):
            r = map_salas.get(nombre)
            tot = int(r.total_marcajes) if r else 0
            pct = round((tot / total_global) * 100, 1) if total_global > 0 else 0.0
            return {
                "sala": nombre,
                "total_marcajes": tot,
                "usuarios_unicos": int(r.usuarios_unicos) if r else 0,
                "entradas": int(r.entradas) if r else 0,
                "salidas": int(r.salidas) if r else 0,
                "porcentaje_afluencia": pct,
                "capacidad_asientos": cap,
                "edificio": edificio,
                "permite_24h_examenes": permite_24h,
            }

        resumen_salas = [
            construir_sala(NOMBRE_SALA_1_CSF02, cap_s1, "CSF02", False),
            construir_sala(NOMBRE_SALA_2_CSF04, cap_s2, "CSF04", True),
        ]

        return {
            "resumen_salas": resumen_salas,
            "flujo_horario_comparado": flujo_horario_comparado,
            "total_global": total_global,
        }

    @staticmethod
    async def get_daily_average_attendance(
        session: AsyncSession,
        espacio_id: int = 1,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        alcance: str = "todos",
        regimen_horario: Optional[str] = "todos",
        direccion: Optional[str] = "todos",
        dias_semana: Optional[str] = None,
        door: Optional[str] = None,
        perfil_visita: Optional[str] = "todos",
        marcajes: Optional[str] = "todos",
        sala: Optional[str] = None,
        carrera: Optional[str] = None,
        facultad: Optional[str] = None,
        cohorte: Optional[str] = None,
        incluir_pausas_bano: bool = True,
        desduplicar_rafagas: bool = True,
        incluir_funcionarios: bool = True,
        incluir_sin_identificar: bool = True,
    ) -> dict:
        """
        Calcula el promedio diario de ingresos por día de la semana (Lunes a Domingo)
        discriminando por Sala 1, Sala 2 y total global, ponderado por días reales transcurridos.
        """
        where_sql, params = await AttendanceService._build_attendance_filters(
            session=session,
            espacio_id=espacio_id,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            alcance=alcance,
            regimen_horario=regimen_horario,
            direccion=direccion,
            dias_semana=dias_semana,
            door=door,
            perfil_visita=perfil_visita,
            marcajes=marcajes,
            sala=sala,
            carrera=carrera,
            facultad=facultad,
            cohorte=cohorte,
            incluir_pausas_bano=incluir_pausas_bano,
            desduplicar_rafagas=desduplicar_rafagas,
            incluir_funcionarios=incluir_funcionarios,
            incluir_sin_identificar=incluir_sin_identificar,
        )

        sql = text(f"""
            SELECT 
                dia_semana_iso AS dia_num,
                COUNT(DISTINCT CAST(time AS DATE)) AS dias_ocurridos,
                SUM(CASE WHEN door_entrada IS NOT NULL THEN 1 ELSE 0 END) AS entradas_totales,
                SUM(CASE WHEN (door_entrada LIKE '%CSF02%' OR door_salida LIKE '%CSF02%') AND door_entrada IS NOT NULL THEN 1 ELSE 0 END) AS entradas_sala1,
                SUM(CASE WHEN (door_entrada LIKE '%CSF04%' OR door_salida LIKE '%CSF04%') AND door_entrada IS NOT NULL THEN 1 ELSE 0 END) AS entradas_sala2
            FROM eventos_asistencia
            WHERE {where_sql}
            GROUP BY dia_semana_iso
        """)
        rows = (await session.execute(sql, params)).fetchall()
        map_dias = {int(r.dia_num): r for r in rows}

        nombres_dias = [
            (1, "Lunes", "Lun"),
            (2, "Martes", "Mar"),
            (3, "Miércoles", "Mié"),
            (4, "Jueves", "Jue"),
            (5, "Viernes", "Vie"),
            (6, "Sábado", "Sáb"),
            (7, "Domingo", "Dom"),
        ]

        caps = await obtener_capacidades_salas_cacheadas(session, espacio_id)
        cap_s1 = caps["sala_1"]
        cap_s2 = caps["sala_2"]

        items = []
        for d_num, d_nombre, d_corto in nombres_dias:
            r = map_dias.get(d_num)
            n_dias = int(r.dias_ocurridos) if r and r.dias_ocurridos else 0
            ent_tot = int(r.entradas_totales) if r and r.entradas_totales else 0
            ent_s1 = int(r.entradas_sala1) if r and r.entradas_sala1 else 0
            ent_s2 = int(r.entradas_sala2) if r and r.entradas_sala2 else 0

            prom_tot = round(ent_tot / n_dias, 1) if n_dias > 0 else 0.0
            prom_s1 = round(ent_s1 / n_dias, 1) if n_dias > 0 else 0.0
            prom_s2 = round(ent_s2 / n_dias, 1) if n_dias > 0 else 0.0

            pct_s1 = round((prom_s1 / cap_s1) * 100, 1) if cap_s1 > 0 else 0.0
            pct_s2 = round((prom_s2 / cap_s2) * 100, 1) if cap_s2 > 0 else 0.0

            items.append({
                "dia_num": d_num,
                "dia_nombre": d_nombre,
                "dia_corto": d_corto,
                "dias_muestreados": n_dias,
                "promedio_entradas_total": prom_tot,
                "promedio_entradas_sala1": prom_s1,
                "promedio_entradas_sala2": prom_s2,
                "total_entradas_acumuladas": ent_tot,
                "ocupacion_relativa_sala1_pct": pct_s1,
                "ocupacion_relativa_sala2_pct": pct_s2,
            })

        dias_con_datos = [it for it in items if it["dias_muestreados"] > 0]
        dia_pico = max(dias_con_datos, key=lambda x: x["promedio_entradas_total"]) if dias_con_datos else items[0]

        return {
            "dias": items,
            "resumen": {
                "dia_mayor_afluencia": dia_pico["dia_nombre"],
                "pico_promedio_diario": dia_pico["promedio_entradas_total"],
                "sala1_capacidad": cap_s1,
                "sala2_capacidad": cap_s2,
                "total_dias_evaluados": sum(it["dias_muestreados"] for it in items),
            }
        }

    @staticmethod
    async def get_curricular_distribution(
        session: AsyncSession,
        espacio_id: int = 1,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        alcance: str = "conformes",
        regimen_horario: Optional[str] = "todos",
        direccion: Optional[str] = "todos",
        dias_semana: Optional[str] = None,
        door: Optional[str] = None,
        perfil_visita: Optional[str] = "todos",
        marcajes: Optional[str] = "todos",
        sala: Optional[str] = None,
        carrera: Optional[str] = None,
        facultad: Optional[str] = None,
        cohorte: Optional[str] = None,
        incluir_pausas_bano: bool = True,
        desduplicar_rafagas: bool = True,
        incluir_funcionarios: bool = True,
        incluir_sin_identificar: bool = True,
    ) -> dict:
        """Retorna distribución agregada y anonimizada de carreras, facultades, cohortes y eventos según los filtros y período seleccionados (Ley 21.719)."""
        where_sql, params = await AttendanceService._build_attendance_filters(
            session=session,
            espacio_id=espacio_id,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            alcance=alcance,
            regimen_horario=regimen_horario,
            direccion=direccion,
            dias_semana=dias_semana,
            door=door,
            perfil_visita=perfil_visita,
            marcajes=marcajes,
            sala=sala,
            carrera=carrera,
            facultad=facultad,
            cohorte=cohorte,
            incluir_pausas_bano=incluir_pausas_bano,
            desduplicar_rafagas=desduplicar_rafagas,
            incluir_funcionarios=incluir_funcionarios,
            incluir_sin_identificar=incluir_sin_identificar,
        )

        # 1. Carreras con población y eventos de asistencia reales filtrados por período
        sql_carreras = text(f"""
            WITH ea_filtrada AS (
                SELECT person_id_hash, time, carrera, facultad
                FROM eventos_asistencia
                WHERE {where_sql}
            ),
            estudiantes_unificados AS (
                SELECT 
                    person_id_hash,
                    carr_nombre AS carrera,
                    facultad
                FROM dim_estudiante_carrera
                WHERE carr_nombre IS NOT NULL AND carr_nombre != ''
                UNION
                SELECT DISTINCT
                    person_id_hash,
                    carrera,
                    COALESCE(facultad, 'Estudiante') AS facultad
                FROM ea_filtrada
                WHERE carrera IS NOT NULL AND carrera != ''
                  AND person_id_hash NOT IN (
                      SELECT person_id_hash FROM dim_estudiante_carrera WHERE carr_nombre IS NOT NULL
                  )
            )
            SELECT TOP 70
                eu.carrera,
                COALESCE(eu.facultad, 'Sin facultad catalogada') AS facultad,
                COUNT(DISTINCT eu.person_id_hash) AS total_estudiantes,
                COUNT(DISTINCT ea.person_id_hash) AS estudiantes_asistentes,
                COUNT(ea.time) AS eventos_asistencia
            FROM estudiantes_unificados eu
            LEFT JOIN ea_filtrada ea 
                ON eu.person_id_hash = ea.person_id_hash
            GROUP BY eu.carrera, eu.facultad
            ORDER BY eventos_asistencia DESC, estudiantes_asistentes DESC
        """)
        rows_carr = (await session.execute(sql_carreras, params)).fetchall()

        # 2. Facultades con población y eventos de asistencia reales filtrados por período
        sql_fac = text(f"""
            WITH ea_filtrada AS (
                SELECT person_id_hash, time, carrera, facultad
                FROM eventos_asistencia
                WHERE {where_sql}
            ),
            estudiantes_unificados AS (
                SELECT 
                    person_id_hash,
                    facultad
                FROM dim_estudiante_carrera
                WHERE facultad IS NOT NULL AND facultad != ''
                UNION
                SELECT DISTINCT
                    person_id_hash,
                    COALESCE(facultad, 'Estudiante') AS facultad
                FROM ea_filtrada
                WHERE person_id_hash NOT IN (
                    SELECT person_id_hash FROM dim_estudiante_carrera WHERE facultad IS NOT NULL
                )
            )
            SELECT 
                COALESCE(eu.facultad, 'Sin facultad catalogada') AS facultad,
                COUNT(DISTINCT eu.person_id_hash) AS total_estudiantes,
                COUNT(DISTINCT ea.person_id_hash) AS estudiantes_asistentes,
                COUNT(ea.time) AS eventos_asistencia
            FROM estudiantes_unificados eu
            LEFT JOIN ea_filtrada ea 
                ON eu.person_id_hash = ea.person_id_hash
            GROUP BY eu.facultad
            ORDER BY eventos_asistencia DESC, estudiantes_asistentes DESC
        """)
        rows_fac = (await session.execute(sql_fac, params)).fetchall()

        # 3. Cohortes / Año de ingreso con población y eventos de asistencia filtrados por período
        sql_coh = text(f"""
            WITH ea_filtrada AS (
                SELECT person_id_hash, time
                FROM eventos_asistencia
                WHERE {where_sql}
            ),
            dec_unica AS (
                SELECT
                    person_id_hash,
                    anho_ingreso,
                    ROW_NUMBER() OVER (PARTITION BY person_id_hash ORDER BY id DESC) AS rn
                FROM dim_estudiante_carrera
            )
            SELECT 
                dec.anho_ingreso AS cohorte,
                COUNT(DISTINCT dec.person_id_hash) AS total_estudiantes,
                COUNT(DISTINCT ea.person_id_hash) AS estudiantes_asistentes,
                COUNT(ea.time) AS eventos_asistencia
            FROM dec_unica dec
            LEFT JOIN ea_filtrada ea 
                ON dec.person_id_hash = ea.person_id_hash
            WHERE dec.rn = 1 AND dec.anho_ingreso IS NOT NULL
            GROUP BY dec.anho_ingreso
            ORDER BY dec.anho_ingreso DESC
        """)
        rows_coh = (await session.execute(sql_coh, params)).fetchall()

        # 4. Totales generales del período y padrón
        sql_tot_padron = text("""
            SELECT (
                (SELECT COUNT(DISTINCT person_id_hash) FROM dim_estudiante_carrera) +
                (SELECT COUNT(DISTINCT person_id_hash) FROM eventos_asistencia WHERE person_id_hash NOT IN (SELECT person_id_hash FROM dim_estudiante_carrera))
            )
        """)
        total_padron = (await session.execute(sql_tot_padron)).scalar() or 0

        sql_tot_periodo = text(f"""
            SELECT 
                COUNT(*) AS total_eventos,
                COUNT(DISTINCT person_id_hash) AS total_asistentes
            FROM eventos_asistencia
            WHERE {where_sql}
        """)
        row_tot = (await session.execute(sql_tot_periodo, params)).fetchone()
        total_eventos = int(row_tot[0]) if row_tot and row_tot[0] is not None else 0
        total_asistentes = int(row_tot[1]) if row_tot and row_tot[1] is not None else 0

        return {
            "total_estudiantes_catalogados": total_padron,
            "total_eventos_asistencia": total_eventos,
            "total_estudiantes_asistentes": total_asistentes,
            "carreras": [
                {
                    "carrera": r.carrera,
                    "facultad": r.facultad,
                    "total_estudiantes": int(r.total_estudiantes),
                    "estudiantes_asistentes": int(r.estudiantes_asistentes),
                    "eventos_asistencia": int(r.eventos_asistencia),
                    "porcentaje": round((r.total_estudiantes / total_padron) * 100, 1) if total_padron else 0,
                    "porcentaje_eventos": round((r.eventos_asistencia / total_eventos) * 100, 1) if total_eventos else 0,
                    "porcentaje_asistentes": round((r.estudiantes_asistentes / total_asistentes) * 100, 1) if total_asistentes else 0,
                }
                for r in rows_carr
            ],
            "facultades": [
                {
                    "facultad": r.facultad,
                    "total_estudiantes": int(r.total_estudiantes),
                    "estudiantes_asistentes": int(r.estudiantes_asistentes),
                    "eventos_asistencia": int(r.eventos_asistencia),
                    "porcentaje": round((r.total_estudiantes / total_padron) * 100, 1) if total_padron else 0,
                    "porcentaje_eventos": round((r.eventos_asistencia / total_eventos) * 100, 1) if total_eventos else 0,
                    "porcentaje_asistentes": round((r.estudiantes_asistentes / total_asistentes) * 100, 1) if total_asistentes else 0,
                }
                for r in rows_fac
            ],
            "cohortes": [
                {
                    "cohorte": int(r.cohorte),
                    "etiqueta": f"Cohorte {r.cohorte}" + (" (Novatos)" if r.cohorte == 2026 else ""),
                    "total_estudiantes": int(r.total_estudiantes),
                    "estudiantes_asistentes": int(r.estudiantes_asistentes),
                    "eventos_asistencia": int(r.eventos_asistencia),
                    "porcentaje_estudiantes": round((r.total_estudiantes / total_padron) * 100, 1) if total_padron else 0,
                    "porcentaje_eventos": round((r.eventos_asistencia / total_eventos) * 100, 1) if total_eventos else 0,
                    "porcentaje_asistentes": round((r.estudiantes_asistentes / total_asistentes) * 100, 1) if total_asistentes else 0,
                }
                for r in rows_coh
            ],
        }

    @staticmethod
    async def get_available_filters(
        session: AsyncSession,
        espacio_id: int = 1,
    ) -> dict:
        """Retorna opciones dinámicas para poblar los filtros de salas, puertas, carreras, facultades y cohortes."""
        salas = await AttendanceService.get_salas_biblioteca(session, espacio_id)

        sql_f = text("""
            SELECT DISTINCT facultad FROM (
                SELECT facultad FROM dim_estudiante_carrera WHERE facultad IS NOT NULL AND facultad != ''
                UNION
                SELECT facultad FROM eventos_asistencia WHERE facultad IS NOT NULL AND facultad != ''
            ) f
            ORDER BY facultad
        """)
        rows_f = (await session.execute(sql_f)).fetchall()
        facultades = [r[0] for r in rows_f]

        sql_c = text("""
            SELECT DISTINCT carr_nombre FROM (
                SELECT carr_nombre FROM dim_estudiante_carrera WHERE carr_nombre IS NOT NULL AND carr_nombre != ''
                UNION
                SELECT carrera AS carr_nombre FROM eventos_asistencia WHERE carrera IS NOT NULL AND carrera != ''
            ) c
            ORDER BY carr_nombre
        """)
        rows_c = (await session.execute(sql_c)).fetchall()
        carreras = [r[0] for r in rows_c]

        sql_coh = text("""
            SELECT DISTINCT anho_ingreso
            FROM dim_estudiante_carrera
            WHERE anho_ingreso IS NOT NULL
            ORDER BY anho_ingreso DESC
        """)
        rows_coh = (await session.execute(sql_coh)).fetchall()
        cohortes = [int(r[0]) for r in rows_coh]

        return {
            "salas": salas,
            "facultades": facultades,
            "carreras": carreras,
            "cohortes": cohortes,
        }

    @staticmethod
    async def get_checkin_distribution(
        session: AsyncSession,
        espacio_id: int = 1,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        alcance: Optional[str] = "conformes",
        regimen_horario: Optional[str] = "todos",
        direccion: Optional[str] = "todos",
        dias_semana: Optional[str] = None,
        door: Optional[str] = None,
        perfil_visita: Optional[str] = "todos",
        marcajes: Optional[str] = "todos",
        sala: Optional[str] = None,
        carrera: Optional[str] = None,
        facultad: Optional[str] = None,
        cohorte: Optional[str] = None,
        incluir_pausas_bano: bool = True,
        desduplicar_rafagas: bool = True,
        incluir_funcionarios: bool = True,
        incluir_sin_identificar: bool = True,
    ) -> list[dict]:
        where_sql, params = await AttendanceService._build_attendance_filters(
            session=session,
            espacio_id=espacio_id,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            alcance=alcance,
            regimen_horario=regimen_horario,
            direccion=direccion,
            dias_semana=dias_semana,
            door=door,
            perfil_visita=perfil_visita,
            marcajes=marcajes,
            sala=sala,
            carrera=carrera,
            facultad=facultad,
            cohorte=cohorte,
            incluir_pausas_bano=incluir_pausas_bano,
            desduplicar_rafagas=desduplicar_rafagas,
            incluir_funcionarios=incluir_funcionarios,
            incluir_sin_identificar=incluir_sin_identificar,
        )
        sql = text(f"""
            SELECT 
                marcajes_totales AS marcajes,
                COUNT(*) AS total_registros,
                ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS porcentaje
            FROM eventos_asistencia
            WHERE {where_sql}
            GROUP BY marcajes_totales
            ORDER BY marcajes_totales ASC
        """)
        rows = (await session.execute(sql, params)).fetchall()
        agrupado = {}
        for r in rows:
            m = int(r.marcajes) if r.marcajes is not None else 1
            tot = int(r.total_registros)
            pct = float(r.porcentaje)
            label = str(m) if m <= 6 else "7+"
            if label not in agrupado:
                agrupado[label] = {"marcajes": label, "total_registros": 0, "porcentaje": 0.0}
            agrupado[label]["total_registros"] += tot
            agrupado[label]["porcentaje"] = round(agrupado[label]["porcentaje"] + pct, 2)
        return list(agrupado.values())

    @staticmethod
    async def get_visit_profiles_donut(
        session: AsyncSession,
        espacio_id: int = 1,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        alcance: Optional[str] = "todos",
        regimen_horario: Optional[str] = "todos",
        direccion: Optional[str] = "todos",
        dias_semana: Optional[str] = None,
        door: Optional[str] = None,
        perfil_visita: Optional[str] = "todos",
        marcajes: Optional[str] = "todos",
        sala: Optional[str] = None,
        carrera: Optional[str] = None,
        facultad: Optional[str] = None,
        cohorte: Optional[str] = None,
        incluir_pausas_bano: bool = True,
        desduplicar_rafagas: bool = True,
        incluir_funcionarios: bool = True,
        incluir_sin_identificar: bool = True,
    ) -> dict:
        """Calcula perfiles de visita emparejando entradas y salidas con LEAD, discriminando casos asimétricos."""
        where_sql, params = await AttendanceService._build_attendance_filters(
            session=session,
            espacio_id=espacio_id,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            alcance=alcance,
            regimen_horario=regimen_horario,
            direccion=direccion,
            dias_semana=dias_semana,
            door=door,
            perfil_visita=perfil_visita,
            marcajes=marcajes,
            sala=sala,
            carrera=carrera,
            facultad=facultad,
            cohorte=cohorte,
            incluir_pausas_bano=incluir_pausas_bano,
            desduplicar_rafagas=desduplicar_rafagas,
            incluir_funcionarios=incluir_funcionarios,
            incluir_sin_identificar=incluir_sin_identificar,
        )

        sql_emparejadas = text(f"""
            WITH EventosFiltrados AS (
                SELECT 
                    person_id_hash,
                    time,
                    CASE WHEN door_salida IS NOT NULL OR salida_imputada = 1 THEN 1 ELSE 0 END AS es_salida,
                    CAST(time AS DATE) AS fecha
                FROM eventos_asistencia
                WHERE {where_sql}
            ),
            PasadasConsecutivas AS (
                SELECT 
                    person_id_hash,
                    time,
                    es_salida,
                    LEAD(time) OVER (PARTITION BY fecha, person_id_hash ORDER BY time) AS next_time,
                    LEAD(es_salida) OVER (PARTITION BY fecha, person_id_hash ORDER BY time) AS next_es_salida
                FROM EventosFiltrados
            ),
            VisitasEmparejadas AS (
                SELECT 
                    CASE 
                        WHEN DATEDIFF(MINUTE, time, next_time) < 15 THEN 'Rebote (<15 min)'
                        WHEN DATEDIFF(MINUTE, time, next_time) <= 120 THEN 'Estándar (15-120 min)'
                        ELSE 'Profundo (>120 min)'
                    END AS perfil,
                    DATEDIFF(MINUTE, time, next_time) AS duracion_min
                FROM PasadasConsecutivas
                WHERE es_salida = 0 AND next_es_salida = 1 AND DATEDIFF(MINUTE, time, next_time) >= 0
            )
            SELECT 
                perfil,
                COUNT(*) AS total,
                ROUND(AVG(CAST(duracion_min AS FLOAT)), 1) AS promedio_min
            FROM VisitasEmparejadas
            GROUP BY perfil
            ORDER BY total DESC
        """)
        rows = (await session.execute(sql_emparejadas, params)).fetchall()

        sql_counts = text(f"""
            SELECT 
                COUNT(*) AS total_eventos,
                SUM(CASE WHEN door_entrada IS NOT NULL AND (door_salida IS NULL AND (salida_imputada IS NULL OR salida_imputada = 0)) THEN 1 ELSE 0 END) AS total_entradas,
                SUM(CASE WHEN door_salida IS NOT NULL OR salida_imputada = 1 THEN 1 ELSE 0 END) AS total_salidas
            FROM eventos_asistencia
            WHERE {where_sql}
        """)
        counts_row = (await session.execute(sql_counts, params)).mappings().first()
        total_eventos = int(counts_row["total_eventos"]) if counts_row and counts_row["total_eventos"] else 0
        total_entradas = int(counts_row["total_entradas"]) if counts_row and counts_row["total_entradas"] else 0
        total_salidas = int(counts_row["total_salidas"]) if counts_row and counts_row["total_salidas"] else 0

        map_cat = {
            "Rebote (<15 min)": {"color": "#EF4444", "order": 1, "desc": "Visitas breves de paso o consulta puntual"},
            "Estándar (15-120 min)": {"color": "#003865", "order": 2, "desc": "Estadía regular por bloque de estudio"},
            "Profundo (>120 min)": {"color": "#10B981", "order": 3, "desc": "Sesiones intensivas de estudio prolongado"},
        }
        res_dict = {r.perfil: {"total": int(r.total), "promedio_min": float(r.promedio_min)} for r in rows}

        total_visitas = sum(v["total"] for v in res_dict.values())
        items = []
        rebote_total = 0
        for perfil_nom, meta in sorted(map_cat.items(), key=lambda x: x[1]["order"]):
            info = res_dict.get(perfil_nom, {"total": 0, "promedio_min": 0.0})
            tot = info["total"]
            pct = round((tot / total_visitas * 100), 2) if total_visitas > 0 else 0.0
            if "Rebote" in perfil_nom:
                rebote_total = tot
            items.append({
                "perfil": perfil_nom,
                "total": tot,
                "porcentaje": pct,
                "promedio_min": info["promedio_min"],
                "color": meta["color"],
                "descripcion": meta["desc"],
            })

        tasa_rebote = round((rebote_total / total_visitas * 100), 1) if total_visitas > 0 else 0.0
        entradas_sin_salida = max(0, total_entradas - total_visitas)
        salidas_sin_entrada = max(0, total_salidas - total_visitas)
        total_no_analizados = entradas_sin_salida + salidas_sin_entrada

        return {
            "items": items,
            "total_visitas_analizadas": total_visitas,
            "tasa_rebote_pct": tasa_rebote,
            "entradas_sin_salida": entradas_sin_salida,
            "salidas_sin_entrada": salidas_sin_entrada,
            "total_no_analizados": total_no_analizados,
            "total_eventos": total_eventos,
        }

    @staticmethod
    async def get_raw_events(
        session: AsyncSession,
        espacio_id: int = 1,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        door: Optional[str] = None,
        search_hash: Optional[str] = None,
        categoria: Optional[str] = None,
        alcance: Optional[str] = "todos",
        regimen_horario: Optional[str] = "todos",
        direccion: Optional[str] = "todos",
        dias_semana: Optional[str] = None,
        perfil_visita: Optional[str] = "todos",
        marcajes: Optional[str] = "todos",
        sala: Optional[str] = None,
        carrera: Optional[str] = None,
        facultad: Optional[str] = None,
        cohorte: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
        incluir_pausas_bano: bool = True,
        desduplicar_rafagas: bool = True,
        incluir_funcionarios: bool = True,
        incluir_sin_identificar: bool = True,
    ) -> dict:
        from app.services.config_service import get_horarios_operacion, es_horario_conforme

        where_sql, params = await AttendanceService._build_attendance_filters(
            session=session,
            espacio_id=espacio_id,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            alcance=alcance,
            regimen_horario=regimen_horario,
            direccion=direccion,
            dias_semana=dias_semana,
            door=door,
            perfil_visita=perfil_visita,
            marcajes=marcajes,
            sala=sala,
            carrera=carrera,
            facultad=facultad,
            cohorte=cohorte,
            incluir_pausas_bano=incluir_pausas_bano,
            desduplicar_rafagas=desduplicar_rafagas,
            incluir_funcionarios=incluir_funcionarios,
            incluir_sin_identificar=incluir_sin_identificar,
        )

        conditions = [where_sql]

        if search_hash:
            conditions.append("person_id_hash LIKE :search_hash")
            params["search_hash"] = f"%{search_hash}%"

        # Filtro de categoría específica si se seleccionó en el dropdown de microdatos
        if categoria:
            cat_lower = categoria.lower()
            if cat_lower == "fuera_de_horario":
                cond_fuera_h = await _construir_sql_fuera_de_horario_categoria(
                    session, espacio_id, fecha_inicio, fecha_fin, params
                )
                conditions.append(cond_fuera_h)
            elif cat_lower == "sin_salida":
                conditions.append("salida_imputada = 1")
            elif cat_lower == "sin_entrada":
                conditions.append("(entrada_imputada = 1 OR primera_entrada IS NULL)")
            elif cat_lower == "hora_invertida":
                conditions.append("alerta_coherencia_fechas = 1")
            elif cat_lower == "sin_credencial":
                conditions.append(f"person_id_hash LIKE '{PREFIJO_HASH_PRUEBA_EXCLUIDO}'")
            elif cat_lower == "marcaje_excesivo":
                conditions.append("marcajes_totales >= 5")
            elif cat_lower == "conforme":
                conditions.append(f"alerta_coherencia_fechas = 0 AND salida_imputada = 0 AND entrada_imputada = 0 AND primera_entrada IS NOT NULL AND person_id_hash NOT LIKE '{PREFIJO_HASH_PRUEBA_EXCLUIDO}' AND (marcajes_totales < 5 OR (permanencia_min IS NOT NULL AND permanencia_min > 0))")

        where_clause = " AND ".join(conditions)

        count_sql = text(f"SELECT COUNT(*) FROM eventos_asistencia WHERE {where_clause}")
        total = (await session.execute(count_sql, params)).scalar() or 0

        offset = max(0, (page - 1) * page_size)
        params["limit"] = page_size
        params["offset"] = offset

        data_sql = text(f"""
            SELECT 
                time,
                person_id_hash,
                door_entrada,
                door_salida,
                primera_entrada,
                ultima_salida,
                permanencia_min,
                marcajes_totales,
                salida_imputada,
                entrada_imputada,
                alerta_coherencia_fechas
            FROM eventos_asistencia
            WHERE {where_clause}
            ORDER BY time DESC
            OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY
        """)
        rows = (await session.execute(data_sql, params)).fetchall()

        horarios = await get_horarios_operacion(session, espacio_id=espacio_id)

        items = []
        for r in rows:
            categorias_row = []
            sub_fila = _detectar_subespacio_fila(r.door_entrada, r.door_salida)
            es_sal_fila = bool(r.door_salida or r.ultima_salida or r.salida_imputada)
            if r.time and not es_horario_conforme(
                r.time,
                horarios,
                subespacio=sub_fila,
                es_salida=es_sal_fila,
                tolerancia_salida_min=TOLERANCIA_SALIDA_POST_CIERRE_MIN,
            ):
                categorias_row.append("Fuera de Horario")
            if r.alerta_coherencia_fechas:
                categorias_row.append("Hora Invertida")
            if r.salida_imputada:
                categorias_row.append("Sin Salida")
            if getattr(r, "entrada_imputada", False) or r.primera_entrada is None:
                categorias_row.append("Sin Entrada")
            if r.person_id_hash and r.person_id_hash.startswith("e8f17a68"):
                categorias_row.append("Sin Credencial")
            if r.marcajes_totales and int(r.marcajes_totales) >= 5:
                if r.permanencia_min is not None and float(r.permanencia_min) > 0:
                    categorias_row.append("Multirreingreso")
                else:
                    categorias_row.append("Marcaje Excesivo")

            if not categorias_row:
                categorias_row = ["Conforme"]
                nivel = "conforme"
            elif "Hora Invertida" in categorias_row or len(categorias_row) >= 2:
                nivel = "critico"
            else:
                nivel = "observado"

            items.append({
                "time": r.time.strftime("%Y-%m-%d %H:%M:%S") if r.time else None,
                "person_id_hash": r.person_id_hash,
                "person_id_short": "SIN-CREDENCIAL" if r.person_id_hash.startswith("e8f17a68") else f"USR-{r.person_id_hash[:8]}",
                "door_entrada": str(r.door_entrada).replace(".0", "") if r.door_entrada and str(r.door_entrada) != "nan" else "—",
                "door_salida": str(r.door_salida).replace(".0", "") if r.door_salida and str(r.door_salida) != "nan" else "—",
                "primera_entrada": r.primera_entrada.strftime("%H:%M:%S") if r.primera_entrada else "—",
                "ultima_salida": r.ultima_salida.strftime("%H:%M:%S") if r.ultima_salida else "—",
                "permanencia_min": round(float(r.permanencia_min), 1) if r.permanencia_min is not None else 0.0,
                "marcajes_totales": int(r.marcajes_totales) if r.marcajes_totales is not None else 1,
                "salida_imputada": bool(r.salida_imputada),
                "entrada_imputada": bool(getattr(r, "entrada_imputada", False)),
                "alerta_coherencia_fechas": bool(r.alerta_coherencia_fechas),
                "categorias": categorias_row,
                "nivel_integridad": nivel,
            })

        total_pages = max(1, (total + page_size - 1) // page_size)
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    @staticmethod
    async def export_raw_csv(
        session: AsyncSession,
        espacio_id: int = 1,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        door: Optional[str] = None,
        search_hash: Optional[str] = None,
        categoria: Optional[str] = None,
        alcance: Optional[str] = "todos",
        regimen_horario: Optional[str] = "todos",
        direccion: Optional[str] = "todos",
        dias_semana: Optional[str] = None,
        perfil_visita: Optional[str] = "todos",
        marcajes: Optional[str] = "todos",
        sala: Optional[str] = None,
        carrera: Optional[str] = None,
        facultad: Optional[str] = None,
        cohorte: Optional[str] = None,
        limit: int = 100000,
        incluir_pausas_bano: bool = True,
        desduplicar_rafagas: bool = True,
        incluir_funcionarios: bool = True,
        incluir_sin_identificar: bool = True,
    ) -> tuple[str, int]:
        import csv
        import io
        from app.services.config_service import get_horarios_operacion, es_horario_conforme

        where_sql, params = await AttendanceService._build_attendance_filters(
            session=session,
            espacio_id=espacio_id,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            alcance=alcance,
            regimen_horario=regimen_horario,
            direccion=direccion,
            dias_semana=dias_semana,
            door=door,
            perfil_visita=perfil_visita,
            marcajes=marcajes,
            sala=sala,
            carrera=carrera,
            facultad=facultad,
            cohorte=cohorte,
            incluir_pausas_bano=incluir_pausas_bano,
            desduplicar_rafagas=desduplicar_rafagas,
            incluir_funcionarios=incluir_funcionarios,
            incluir_sin_identificar=incluir_sin_identificar,
        )
        params["limit"] = limit

        conditions = [where_sql]
        if search_hash:
            conditions.append("person_id_hash LIKE :search_hash")
            params["search_hash"] = f"%{search_hash}%"

        if categoria:
            cat_lower = categoria.lower()
            if cat_lower == "fuera_de_horario":
                cond_fuera_h = await _construir_sql_fuera_de_horario_categoria(
                    session, espacio_id, fecha_inicio, fecha_fin, params
                )
                conditions.append(cond_fuera_h)
            elif cat_lower == "sin_salida":
                conditions.append("salida_imputada = 1")
            elif cat_lower == "sin_entrada":
                conditions.append("(entrada_imputada = 1 OR primera_entrada IS NULL)")
            elif cat_lower == "hora_invertida":
                conditions.append("alerta_coherencia_fechas = 1")
            elif cat_lower == "sin_credencial":
                conditions.append(f"person_id_hash LIKE '{PREFIJO_HASH_PRUEBA_EXCLUIDO}'")
            elif cat_lower == "marcaje_excesivo":
                conditions.append("marcajes_totales >= 5")
            elif cat_lower == "conforme":
                conditions.append(f"alerta_coherencia_fechas = 0 AND salida_imputada = 0 AND entrada_imputada = 0 AND primera_entrada IS NOT NULL AND person_id_hash NOT LIKE '{PREFIJO_HASH_PRUEBA_EXCLUIDO}' AND marcajes_totales < 5")

        where_clause = " AND ".join(conditions)

        data_sql = text(f"""
            SELECT TOP (:limit)
                time,
                person_id_hash,
                door_entrada,
                door_salida,
                primera_entrada,
                ultima_salida,
                permanencia_min,
                marcajes_totales,
                salida_imputada,
                entrada_imputada,
                alerta_coherencia_fechas
            FROM eventos_asistencia
            WHERE {where_clause}
            ORDER BY time DESC
        """)
        rows = (await session.execute(data_sql, params)).fetchall()

        horarios = await get_horarios_operacion(session, espacio_id=espacio_id)

        with io.StringIO() as output:
            writer = csv.writer(output)
            writer.writerow([
                "Fecha",
                "Hora",
                "Identificador_Seudonimizado",
                "Torniquete_Entrada",
                "Torniquete_Salida",
                "Primera_Entrada",
                "Ultima_Salida",
                "Permanencia_Minutos",
                "Total_Marcajes",
                "Salida_Imputada",
                "Entrada_Imputada",
                "Hora_Invertida",
                "Categorias_Calidad",
                "Nivel_Integridad",
            ])

            for r in rows:
                categorias_row = []
                sub_fila = _detectar_subespacio_fila(r.door_entrada, r.door_salida)
                es_sal_fila = bool(r.door_salida or r.ultima_salida or r.salida_imputada)
                if r.time and not es_horario_conforme(
                    r.time,
                    horarios,
                    subespacio=sub_fila,
                    es_salida=es_sal_fila,
                    tolerancia_salida_min=TOLERANCIA_SALIDA_POST_CIERRE_MIN,
                ):
                    categorias_row.append("Fuera de Horario")
                if r.alerta_coherencia_fechas:
                    categorias_row.append("Hora Invertida")
                if r.salida_imputada:
                    categorias_row.append("Sin Salida")
                if getattr(r, "entrada_imputada", False) or r.primera_entrada is None:
                    categorias_row.append("Sin Entrada")
                if r.person_id_hash and r.person_id_hash.startswith("e8f17a68"):
                    categorias_row.append("Sin Credencial")
                if r.marcajes_totales and int(r.marcajes_totales) >= 5:
                    categorias_row.append("Marcaje Excesivo")

                if not categorias_row:
                    categorias_row = ["Conforme"]
                    nivel = "conforme"
                elif "Hora Invertida" in categorias_row or len(categorias_row) >= 2:
                    nivel = "critico"
                else:
                    nivel = "observado"

                from app.services.csv_utils import sanitizar_celda_csv

                writer.writerow([
                    r.time.strftime("%Y-%m-%d") if r.time else "",
                    r.time.strftime("%H:%M:%S") if r.time else "",
                    sanitizar_celda_csv("SIN-CREDENCIAL" if r.person_id_hash.startswith("e8f17a68") else f"USR-{r.person_id_hash[:8]}"),
                    sanitizar_celda_csv(str(r.door_entrada).replace(".0", "") if r.door_entrada and str(r.door_entrada) != "nan" else "—"),
                    sanitizar_celda_csv(str(r.door_salida).replace(".0", "") if r.door_salida and str(r.door_salida) != "nan" else "—"),
                    r.primera_entrada.strftime("%H:%M:%S") if r.primera_entrada else "—",
                    r.ultima_salida.strftime("%H:%M:%S") if r.ultima_salida else "—",
                    round(float(r.permanencia_min), 1) if r.permanencia_min is not None else 0.0,
                    int(r.marcajes_totales) if r.marcajes_totales is not None else 1,
                    "Si" if r.salida_imputada else "No",
                    "Si" if getattr(r, "entrada_imputada", False) else "No",
                    "Si" if r.alerta_coherencia_fechas else "No",
                    sanitizar_celda_csv(" | ".join(categorias_row)),
                    nivel,
                ])

            return output.getvalue(), len(rows)

    @staticmethod
    async def stream_raw_csv(
        espacio_id: int = 1,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        door: Optional[str] = None,
        search_hash: Optional[str] = None,
        categoria: Optional[str] = None,
        alcance: Optional[str] = "todos",
        regimen_horario: Optional[str] = "todos",
        direccion: Optional[str] = "todos",
        dias_semana: Optional[str] = None,
        perfil_visita: Optional[str] = "todos",
        marcajes: Optional[str] = "todos",
        sala: Optional[str] = None,
        carrera: Optional[str] = None,
        facultad: Optional[str] = None,
        cohorte: Optional[str] = None,
        limit: int = 100000,
        incluir_pausas_bano: bool = True,
        desduplicar_rafagas: bool = True,
        incluir_funcionarios: bool = True,
        incluir_sin_identificar: bool = True,
        conteo_ref: Optional[list[int]] = None,
    ):
        """Genera el CSV de asistencia por lotes para StreamingResponse sin cargar 100k filas en RAM."""
        import csv
        import io
        from app.core.database import AsyncSessionLocal
        from app.services.config_service import get_horarios_operacion, es_horario_conforme

        async with AsyncSessionLocal() as s_stream:
            where_sql, params = await AttendanceService._build_attendance_filters(
                session=s_stream,
                espacio_id=espacio_id,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                alcance=alcance,
                regimen_horario=regimen_horario,
                direccion=direccion,
                dias_semana=dias_semana,
                door=door,
                perfil_visita=perfil_visita,
                marcajes=marcajes,
                sala=sala,
                carrera=carrera,
                facultad=facultad,
                cohorte=cohorte,
                incluir_pausas_bano=incluir_pausas_bano,
                desduplicar_rafagas=desduplicar_rafagas,
                incluir_funcionarios=incluir_funcionarios,
                incluir_sin_identificar=incluir_sin_identificar,
            )
            params["limit"] = limit

            conditions = [where_sql]
            if search_hash:
                conditions.append("person_id_hash LIKE :search_hash")
                params["search_hash"] = f"%{search_hash}%"
            if categoria:
                cat_lower = categoria.lower()
                if cat_lower == "fuera_de_horario":
                    conditions.append(await _construir_sql_fuera_de_horario_categoria(
                        s_stream, espacio_id, fecha_inicio, fecha_fin, params
                    ))
                elif cat_lower == "sin_salida":
                    conditions.append("salida_imputada = 1")
                elif cat_lower == "sin_entrada":
                    conditions.append("(entrada_imputada = 1 OR primera_entrada IS NULL)")
                elif cat_lower == "hora_invertida":
                    conditions.append("alerta_coherencia_fechas = 1")
                elif cat_lower == "sin_credencial":
                    conditions.append(f"person_id_hash LIKE '{PREFIJO_HASH_PRUEBA_EXCLUIDO}'")
                elif cat_lower == "marcaje_excesivo":
                    conditions.append("marcajes_totales >= 5")
                elif cat_lower == "conforme":
                    conditions.append(
                        f"alerta_coherencia_fechas = 0 AND salida_imputada = 0 AND entrada_imputada = 0 "
                        f"AND primera_entrada IS NOT NULL AND person_id_hash NOT LIKE '{PREFIJO_HASH_PRUEBA_EXCLUIDO}' "
                        f"AND marcajes_totales < 5"
                    )

            where_clause = " AND ".join(conditions)
            data_sql = text(f"""
                SELECT TOP (:limit)
                    time, person_id_hash, door_entrada, door_salida,
                    primera_entrada, ultima_salida, permanencia_min,
                    marcajes_totales, salida_imputada, entrada_imputada, alerta_coherencia_fechas
                FROM eventos_asistencia
                WHERE {where_clause}
                ORDER BY time DESC
            """)
            horarios = await get_horarios_operacion(s_stream, espacio_id=espacio_id)

            with io.StringIO() as buf:
                writer = csv.writer(buf)
                writer.writerow([
                    "Fecha", "Hora", "Identificador_Seudonimizado", "Torniquete_Entrada", "Torniquete_Salida",
                    "Primera_Entrada", "Ultima_Salida", "Permanencia_Minutos", "Total_Marcajes",
                    "Salida_Imputada", "Entrada_Imputada", "Hora_Invertida", "Categorias_Calidad", "Nivel_Integridad",
                ])
                yield buf.getvalue()
                buf.seek(0)
                buf.truncate(0)

                total_emitidas = 0
                stream_res = await s_stream.stream(data_sql, params)
                async for partition in stream_res.partitions(2000):
                    for r in partition:
                        total_emitidas += 1
                        categorias_row = []
                        sub_fila = _detectar_subespacio_fila(r.door_entrada, r.door_salida)
                        es_sal_fila = bool(r.door_salida or r.ultima_salida or r.salida_imputada)
                        if r.time and not es_horario_conforme(
                            r.time, horarios, subespacio=sub_fila,
                            es_salida=es_sal_fila, tolerancia_salida_min=TOLERANCIA_SALIDA_POST_CIERRE_MIN,
                        ):
                            categorias_row.append("Fuera de Horario")
                        if r.alerta_coherencia_fechas:
                            categorias_row.append("Hora Invertida")
                        if r.salida_imputada:
                            categorias_row.append("Sin Salida")
                        if getattr(r, "entrada_imputada", False) or r.primera_entrada is None:
                            categorias_row.append("Sin Entrada")
                        if r.person_id_hash and r.person_id_hash.startswith("e8f17a68"):
                            categorias_row.append("Sin Credencial")
                        if r.marcajes_totales and int(r.marcajes_totales) >= 5:
                            categorias_row.append("Marcaje Excesivo")

                        if not categorias_row:
                            categorias_row = ["Conforme"]
                            nivel = "conforme"
                        elif "Hora Invertida" in categorias_row or len(categorias_row) >= 2:
                            nivel = "critico"
                        else:
                            nivel = "observado"

                        from app.services.csv_utils import sanitizar_celda_csv

                        writer.writerow([
                            r.time.strftime("%Y-%m-%d") if r.time else "",
                            r.time.strftime("%H:%M:%S") if r.time else "",
                            sanitizar_celda_csv("SIN-CREDENCIAL" if r.person_id_hash.startswith("e8f17a68") else f"USR-{r.person_id_hash[:8]}"),
                            sanitizar_celda_csv(str(r.door_entrada).replace(".0", "") if r.door_entrada and str(r.door_entrada) != "nan" else "—"),
                            sanitizar_celda_csv(str(r.door_salida).replace(".0", "") if r.door_salida and str(r.door_salida) != "nan" else "—"),
                            r.primera_entrada.strftime("%H:%M:%S") if r.primera_entrada else "—",
                            r.ultima_salida.strftime("%H:%M:%S") if r.ultima_salida else "—",
                            round(float(r.permanencia_min), 1) if r.permanencia_min is not None else 0.0,
                            int(r.marcajes_totales) if r.marcajes_totales is not None else 1,
                            "Si" if r.salida_imputada else "No",
                            "Si" if getattr(r, "entrada_imputada", False) else "No",
                            "Si" if r.alerta_coherencia_fechas else "No",
                            sanitizar_celda_csv(" | ".join(categorias_row)),
                            nivel,
                        ])
                    if total_emitidas:
                        yield buf.getvalue()
                        buf.seek(0)
                        buf.truncate(0)
                if conteo_ref is not None:
                    conteo_ref[0] = total_emitidas

    @staticmethod
    async def obtener_anomalias_marcajes(
        session: AsyncSession,
        espacio_id: int = 1,
        limite: int = 100,
    ) -> list[dict]:
        sql = text("""
            SELECT
                time, person_id_hash, door_entrada, marcajes_totales,
                alerta_coherencia_fechas, alerta_marcajes
            FROM eventos_asistencia
            WHERE espacio_id = :espacio_id
              AND (alerta_coherencia_fechas = 1 OR alerta_marcajes = 1)
            ORDER BY time DESC
            OFFSET 0 ROWS FETCH NEXT :limit ROWS ONLY
        """)
        filas = (await session.execute(sql, {"espacio_id": espacio_id, "limit": limite})).fetchall()
        return [
            {
                "time":                     r.time.isoformat(),
                "person_id_hash":           r.person_id_hash,
                "door_entrada":             r.door_entrada,
                "marcajes_totales":         r.marcajes_totales,
                "alerta_coherencia_fechas": r.alerta_coherencia_fechas,
                "alerta_marcajes":          r.alerta_marcajes,
            }
            for r in filas
        ]

    @staticmethod
    async def bulk_insert_events(
        db: AsyncSession,
        dtos: list,
        modo_solapamiento: str = "merge",
        espacio_id: Optional[int] = None,
        fecha_min: Optional[datetime] = None,
        fecha_max: Optional[datetime] = None,
    ) -> dict:
        """
        Inserta eventos de asistencia con soporte atómico para 'merge' o 'overwrite' (RF04, RF30).
        """
        from decimal import Decimal
        from app.domain.models import EventoAsistencia
        from sqlalchemy import select, delete, insert

        if not dtos:
            return {"insertados": 0, "eliminados": 0, "total_procesados": 0}

        registros_eliminados = 0
        target_espacio_id = espacio_id or dtos[0].espacio_id

        # 1. Modo Overwrite: Eliminación atómica del rango previo
        if modo_solapamiento == "overwrite":
            min_ts = fecha_min or min(d.time for d in dtos)
            max_ts = fecha_max or max(d.time for d in dtos)
            stmt_del = (
                delete(EventoAsistencia)
                .where(
                    EventoAsistencia.espacio_id == target_espacio_id,
                    EventoAsistencia.time >= min_ts,
                    EventoAsistencia.time <= max_ts,
                )
            )
            res_del = await db.execute(stmt_del)
            registros_eliminados = res_del.rowcount or 0

        # 2. Obtener claves existentes si es modo merge
        existing_keys = set()
        if modo_solapamiento == "merge":
            min_ts = fecha_min or min(d.time for d in dtos)
            max_ts = (fecha_max or max(d.time for d in dtos)) + timedelta(seconds=60)
            stmt_keys = (
                select(EventoAsistencia.time, EventoAsistencia.espacio_id, EventoAsistencia.person_id_hash)
                .where(
                    EventoAsistencia.espacio_id == target_espacio_id,
                    EventoAsistencia.time >= min_ts,
                    EventoAsistencia.time <= max_ts,
                )
            )
            res_keys = await db.execute(stmt_keys)
            existing_keys = {(r[0], r[1], r[2]) for r in res_keys.fetchall()}

        # 3. Preparar inserción de eventos desambiguando colisiones por minuto
        seen_keys = set()
        a_insertar = []
        for dto in dtos:
            key = (dto.time, dto.espacio_id, dto.person_id_hash)

            # En modo merge, si el evento ya existe exactamente en la BD, se omite
            if modo_solapamiento == "merge" and key in existing_keys:
                continue

            # Si hay colisión con eventos ya vistos en el lote actual
            if key in seen_keys:
                offset = 1
                cand_time = dto.time + timedelta(seconds=offset)
                cand_key = (cand_time, dto.espacio_id, dto.person_id_hash)
                while (cand_key in seen_keys or (modo_solapamiento == "merge" and cand_key in existing_keys)) and offset < 59:
                    offset += 1
                    cand_time = dto.time + timedelta(seconds=offset)
                    cand_key = (cand_time, dto.espacio_id, dto.person_id_hash)

                if cand_key not in seen_keys and (modo_solapamiento != "merge" or cand_key not in existing_keys):
                    dto.time = cand_time
                    key = cand_key
                else:
                    # Sin segundos disponibles sin colisión; descartar para proteger PK
                    continue

            seen_keys.add(key)
            if modo_solapamiento == "merge":
                existing_keys.add(key)

            item_dict = {
                "time": dto.time,
                "espacio_id": dto.espacio_id,
                "person_id_hash": dto.person_id_hash,
                "door_entrada": dto.door_entrada,
                "door_salida": dto.door_salida,
                "primera_entrada": dto.primera_entrada,
                "ultima_salida": dto.ultima_salida,
                "salida_imputada": dto.salida_imputada,
                "entrada_imputada": getattr(dto, "entrada_imputada", False),
                "permanencia_min": Decimal(str(dto.permanencia_min)) if dto.permanencia_min is not None else None,
                "marcajes_totales": dto.marcajes_totales,
                "alerta_coherencia_fechas": dto.alerta_coherencia_fechas,
                "alerta_marcajes": dto.alerta_marcajes,
                "carrera": getattr(dto, "carrera", None),
                "facultad": getattr(dto, "facultad", None),
                "estamento": getattr(dto, "estamento", None) or "Estudiante",
            }
            a_insertar.append(item_dict)

        stmt_insert = text("""
        INSERT INTO eventos_asistencia (
            time, espacio_id, person_id_hash, door_entrada, door_salida,
            primera_entrada, ultima_salida, salida_imputada, entrada_imputada,
            permanencia_min, marcajes_totales, alerta_coherencia_fechas,
            alerta_marcajes, carrera, facultad, estamento
        ) VALUES (
            :time, :espacio_id, :person_id_hash, :door_entrada, :door_salida,
            :primera_entrada, :ultima_salida, :salida_imputada, :entrada_imputada,
            :permanencia_min, :marcajes_totales, :alerta_coherencia_fechas,
            :alerta_marcajes, :carrera, :facultad, :estamento
        )
        """)

        batch_size = 10000
        for i in range(0, len(a_insertar), batch_size):
            chunk = a_insertar[i:i + batch_size]
            await db.execute(stmt_insert, chunk)

        return {
            "insertados": len(a_insertar),
            "eliminados": registros_eliminados,
            "total_procesados": len(dtos),
        }
    @staticmethod
    async def get_latest_year(session: AsyncSession, espacio_id: int = 1) -> int:
        """Obtiene el año más reciente registrado en aforo_horario_biblioteca."""
        try:
            sql = text("SELECT YEAR(MAX(bucket)) FROM aforo_horario_biblioteca WITH (NOEXPAND) WHERE espacio_id = :espacio_id")
            res = await session.execute(sql, {"espacio_id": espacio_id})
            anio = res.scalar()
            if anio:
                return int(anio)
        except Exception:
            pass
        return datetime.now().year

    @staticmethod
    async def get_daily_summary(
        session: AsyncSession,
        espacio_id: int = 1,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
    ) -> list[dict]:
        """Obtiene el resumen diario de aforo de biblioteca agrupado por fecha."""
        params: dict = {"espacio_id": espacio_id}
        where_conds = [CLAUSULA_ESPACIO_ID]
        if fecha_inicio:
            where_conds.append("bucket >= :inicio")
            params["inicio"] = fecha_inicio
        if fecha_fin:
            where_conds.append("bucket < :fin_exclusivo")
            params["fin_exclusivo"] = fecha_fin + timedelta(days=1)
        where_clause = " AND ".join(where_conds)
        sql = text(f"""
            SELECT CAST(bucket AS DATE) as fecha,
                   DATENAME(weekday, CAST(bucket AS DATE)) as dia_semana,
                   SUM(ingresos) as ingresos,
                   SUM(salidas) as salidas,
                   SUM(personas_unicas) as personas_unicas
            FROM aforo_horario_biblioteca WITH (NOEXPAND)
            WHERE {where_clause}
            GROUP BY CAST(bucket AS DATE), DATENAME(weekday, CAST(bucket AS DATE))
            ORDER BY fecha ASC
        """)
        res = await session.execute(sql, params)
        return [dict(r._mapping) for r in res.all()]

    @staticmethod
    async def get_analisis_24h(
        session: AsyncSession,
        espacio_id: int = 1,
        campana_id: Optional[int] = None,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        bloque_horario: Optional[str] = "todos",
        alcance: str = "conformes",
        regimen_horario: Optional[str] = "todos",
        direccion: Optional[str] = "todos",
        dias_semana: Optional[str] = None,
        door: Optional[str] = None,
        perfil_visita: Optional[str] = "todos",
        marcajes: Optional[str] = "todos",
        sala: Optional[str] = None,
        carrera: Optional[str] = None,
        facultad: Optional[str] = None,
        cohorte: Optional[str] = None,
        incluir_pausas_bano: bool = True,
        desduplicar_rafagas: bool = True,
        incluir_funcionarios: bool = True,
        incluir_sin_identificar: bool = True,
    ) -> dict:
        """
        Calcula el análisis de rendimiento, métricas Delta 24h, segmentación curricular
        y reporte justificativo para la campaña de exámenes en horario extendido.
        """
        from app.domain.config_models import HorarioOperacion
        stmt_todas = select(HorarioOperacion).where(
            HorarioOperacion.espacio_id == espacio_id,
            HorarioOperacion.activo == True,
            (HorarioOperacion.es_continuo_24h == True) | (HorarioOperacion.tipo_horario == "extendido_24h")
        ).order_by(HorarioOperacion.fecha_inicio.desc(), HorarioOperacion.id.desc())
        todas_campanas = (await session.execute(stmt_todas)).scalars().all()
        campanas_con_fechas = [c for c in todas_campanas if c.fecha_inicio and c.fecha_fin]

        if campanas_con_fechas:
            min_fecha_global = min(c.fecha_inicio.date() for c in campanas_con_fechas)
            max_fecha_global = max(c.fecha_fin.date() for c in campanas_con_fechas)
            anios_unicos = sorted(
                {c.fecha_inicio.date().year for c in campanas_con_fechas}
                | {c.fecha_fin.date().year for c in campanas_con_fechas}
            )
            etiqueta_anios = (
                str(anios_unicos[0])
                if len(anios_unicos) == 1
                else f"{anios_unicos[0]}–{anios_unicos[-1]}"
            )
            desc_consolidado_global = f"Consolidado Histórico {etiqueta_anios} ({len(campanas_con_fechas)} campañas)"
        else:
            min_fecha_global = None
            max_fecha_global = None
            desc_consolidado_global = "Consolidado Histórico (Sin campañas 24h)"

        campanas_list = [
            {
                "id": c.id,
                "descripcion": c.descripcion,
                "fecha_inicio": c.fecha_inicio.date().isoformat() if c.fecha_inicio else None,
                "fecha_fin": c.fecha_fin.date().isoformat() if c.fecha_fin else None,
                "subespacio": c.subespacio or "sala_2",
            }
            for c in todas_campanas
        ]
        campanas_list.append({
            "id": 0,
            "descripcion": desc_consolidado_global,
            "fecha_inicio": min_fecha_global.isoformat() if min_fecha_global else None,
            "fecha_fin": max_fecha_global.isoformat() if max_fecha_global else None,
            "subespacio": "sala_2",
        })
        campanas_list.append({
            "id": -1,
            "descripcion": "Período Personalizado",
            "fecha_inicio": None,
            "fecha_fin": None,
            "subespacio": "sala_2",
        })

        params_extra: Dict[str, Any] = {}
        intervalos_objetivo: List[tuple[date, date]] = []
        tiene_campana_activa = True
        if campana_id is not None and campana_id >= 0:
            if campana_id > 0:
                stmt_sel = select(HorarioOperacion).where(HorarioOperacion.id == campana_id)
                regla_24h = (await session.execute(stmt_sel)).scalars().first()
                if regla_24h and regla_24h.fecha_inicio and regla_24h.fecha_fin:
                    f_ini = regla_24h.fecha_inicio.date()
                    f_fin = regla_24h.fecha_fin.date()
                    desc_campana = regla_24h.descripcion or f"Campaña #{campana_id}"
                    date_condition = "time >= :f_ini AND time < DATEADD(day, 1, CAST(:f_fin AS DATE))"
                else:
                    tiene_campana_activa = False
                    f_ini = date.today()
                    f_fin = f_ini
                    desc_campana = f"Campaña #{campana_id} sin vigencia configurada"
                    date_condition = "1 = 0"
            else:
                # campana_id == 0: Consolidado de campañas 24h (global o acotado al rango indicado)
                regla_24h = None
                acotado_por_rango = bool(fecha_inicio and fecha_fin)
                for c in campanas_con_fechas:
                    ci = c.fecha_inicio.date()
                    cf = c.fecha_fin.date()
                    if acotado_por_rango:
                        if cf < fecha_inicio or ci > fecha_fin:
                            continue
                        ci = max(ci, fecha_inicio)
                        cf = min(cf, fecha_fin)
                    intervalos_objetivo.append((ci, cf))

                if not intervalos_objetivo:
                    tiene_campana_activa = False
                    f_ini = fecha_inicio or date.today()
                    f_fin = fecha_fin or date.today()
                    desc_campana = "Sin campañas 24h en el período"
                    date_condition = "1 = 0"
                else:
                    f_ini = min(ci for ci, _ in intervalos_objetivo)
                    f_fin = max(cf for _, cf in intervalos_objetivo)
                    desc_campana = (
                        f"Consolidado 24h ({len(intervalos_objetivo)} campañas en período)"
                        if acotado_por_rango
                        else desc_consolidado_global
                    )
                    clausulas_rango = []
                    for idx_int, (ci, cf) in enumerate(intervalos_objetivo):
                        k_ini = f"c_ini_{idx_int}"
                        k_fin = f"c_fin_{idx_int}"
                        params_extra[k_ini] = ci
                        params_extra[k_fin] = cf
                        clausulas_rango.append(
                            f"(time >= :{k_ini} AND time < DATEADD(day, 1, CAST(:{k_fin} AS DATE)))"
                        )
                    date_condition = f"({' OR '.join(clausulas_rango)})"
        elif fecha_inicio and fecha_fin:
            # Período personalizado (campana_id == -1 o None con fechas específicas)
            regla_24h = None
            f_ini = fecha_inicio
            f_fin = fecha_fin
            campanas_en_periodo = [
                c for c in campanas_con_fechas
                if c.fecha_inicio.date() <= f_fin and c.fecha_fin.date() >= f_ini
            ]
            tiene_campana_activa = len(campanas_en_periodo) > 0
            if tiene_campana_activa:
                desc_campana = f"Período Personalizado ({f_ini.strftime('%d/%m/%Y')} al {f_fin.strftime('%d/%m/%Y')})"
            else:
                desc_campana = f"Período Regular sin Régimen 24h ({f_ini.strftime('%d/%m/%Y')} al {f_fin.strftime('%d/%m/%Y')})"
            date_condition = "time >= :f_ini AND time < DATEADD(day, 1, CAST(:f_fin AS DATE))"
        else:
            # Sin parámetros explícitos: seleccionar dinámicamente la campaña más reciente configurada
            regla_24h = campanas_con_fechas[0] if campanas_con_fechas else None
            if regla_24h and regla_24h.fecha_inicio and regla_24h.fecha_fin:
                f_ini = regla_24h.fecha_inicio.date()
                f_fin = regla_24h.fecha_fin.date()
                desc_campana = regla_24h.descripcion or "Campaña 24 Horas Exámenes"
                date_condition = "time >= :f_ini AND time < DATEADD(day, 1, CAST(:f_fin AS DATE))"
            else:
                tiene_campana_activa = False
                f_ini = date.today()
                f_fin = f_ini
                desc_campana = "Sin campañas 24h configuradas"
                date_condition = "1 = 0"

        caps_24h = await obtener_capacidades_salas_cacheadas(session, espacio_id)
        capacidad_asientos = caps_24h["sala_2"]
        subespacio = regla_24h.subespacio if regla_24h else "sala_2"
        # Contabilizar estrictamente ingresos/entradas peatonales (excluyendo salidas físicas de torniquete)
        door_condition = "door_entrada LIKE '%CSF04%'"

        # Horarios exactos según normativa de Sala 2 Pecera (cierra a las 23:00 de Lun-Jue y a las 22:00 los Viernes)
        cond_lj = "((dia_semana_iso IN (1, 2, 3, 4) AND CAST(time AS TIME) >= '23:00:00') OR (dia_semana_iso IN (2, 3, 4, 5) AND CAST(time AS TIME) < '07:00:00'))"
        cond_vie = "((dia_semana_iso = 5 AND CAST(time AS TIME) >= '22:00:00') OR (dia_semana_iso = 6 AND CAST(time AS TIME) < '06:00:00'))"

        if bloque_horario == "lunes_jueves":
            nocturno_condition = cond_lj
            label_bloque = "Lunes a Jueves (23:00 a 07:00 h)"
        elif bloque_horario == "viernes":
            nocturno_condition = cond_vie
            label_bloque = "Viernes (22:00 a 06:00 h)"
        else:
            nocturno_condition = f"(({cond_lj}) OR ({cond_vie}))"
            label_bloque = "Régimen 24h Completo (Lun-Jue 23:00-07:00 + Vie 22:00-06:00)"

        base_where, base_params = await AttendanceService._build_attendance_filters(
            session=session,
            espacio_id=espacio_id,
            fecha_inicio=None,
            fecha_fin=None,
            alcance=alcance,
            regimen_horario=regimen_horario,
            direccion=direccion,
            dias_semana=dias_semana,
            door=door,
            perfil_visita=perfil_visita,
            marcajes=marcajes,
            sala=sala,
            carrera=carrera,
            facultad=facultad,
            cohorte=cohorte,
            incluir_pausas_bano=incluir_pausas_bano,
            desduplicar_rafagas=desduplicar_rafagas,
            incluir_funcionarios=incluir_funcionarios,
            incluir_sin_identificar=incluir_sin_identificar,
        )

        params_base = {
            **base_params,
            "espacio_id": espacio_id,
            "f_ini": f_ini,
            "f_fin": f_fin,
        }
        params_base.update(params_extra)

        sql_kpis = text(f"""
            SELECT
                SUM(CASE WHEN NOT ({nocturno_condition}) THEN 1 ELSE 0 END) AS ingresos_diurnos,
                SUM(CASE WHEN {nocturno_condition} THEN 1 ELSE 0 END) AS ingresos_nocturnos,
                COUNT(*) AS total_ingresos,
                COUNT(DISTINCT CASE WHEN {nocturno_condition} THEN person_id_hash END) AS estudiantes_nocturnos_unicos,
                COUNT(DISTINCT person_id_hash) AS estudiantes_totales_unicos,
                ROUND(SUM(CASE WHEN {nocturno_condition} THEN COALESCE(permanencia_min, 120) ELSE 0 END) / 60.0, 1) AS horas_estudio_nocturnas,
                ROUND(AVG(CASE WHEN {nocturno_condition} THEN CAST(permanencia_min AS FLOAT) END), 1) AS permanencia_promedio_nocturna_min,
                ROUND(AVG(CASE WHEN NOT ({nocturno_condition}) THEN CAST(permanencia_min AS FLOAT) END), 1) AS permanencia_promedio_diurna_min
            FROM eventos_asistencia
            WHERE ({base_where})
              AND {date_condition}
              AND {door_condition}
        """)
        row_kpis = (await session.execute(sql_kpis, params_base)).first()

        nombres_dias = {
            1: "Lunes", 2: "Martes", 3: "Miércoles", 4: "Jueves",
            5: "Viernes", 6: "Sábado", 7: "Domingo"
        }

        if tiene_campana_activa:
            ing_diurnos = int(row_kpis.ingresos_diurnos or 0) if row_kpis else 0
            ing_nocturnos = int(row_kpis.ingresos_nocturnos or 0) if row_kpis else 0
            total_ing = ing_diurnos + ing_nocturnos
            pct_delta = round((100.0 * ing_nocturnos / total_ing), 2) if total_ing > 0 else 0.0
            horas_nocturnas = float(row_kpis.horas_estudio_nocturnas or 0.0) if row_kpis else 0.0
            perm_nocturna = float(row_kpis.permanencia_promedio_nocturna_min or 0.0) if row_kpis else 0.0

            # Estudiantes con presencia nocturna efectiva (entraron de noche O entraron de tarde y salieron de noche)
            sql_presencia = text(f"""
                SELECT COUNT(DISTINCT person_id_hash) AS estudiantes_presencia_total
                FROM eventos_asistencia
                WHERE ({base_where})
                  AND (door_entrada LIKE '%CSF04%' OR door_salida LIKE '%CSF04%')
                  AND {date_condition}
                  AND {nocturno_condition}
            """)
            row_presencia = (await session.execute(sql_presencia, params_base)).first()
            est_solo_in = int(row_kpis.estudiantes_nocturnos_unicos or 0) if row_kpis else 0
            est_presencia_total = int(row_presencia.estudiantes_presencia_total or 0) if row_presencia else est_solo_in
            est_remanentes = max(0, est_presencia_total - est_solo_in)
            est_nocturnos = est_presencia_total

            sql_fases = text(f"""
                SELECT
                    SUM(CASE WHEN (CAST(time AS TIME) >= '22:00:00' AND CAST(time AS TIME) <= '23:59:59' AND {nocturno_condition}) THEN 1 ELSE 0 END) AS fase_vespertina,
                    SUM(CASE WHEN (CAST(time AS TIME) >= '00:00:00' AND CAST(time AS TIME) < '04:00:00' AND {nocturno_condition}) THEN 1 ELSE 0 END) AS fase_profunda,
                    SUM(CASE WHEN (CAST(time AS TIME) >= '04:00:00' AND CAST(time AS TIME) < '07:00:00' AND {nocturno_condition}) THEN 1 ELSE 0 END) AS fase_cierre
                FROM eventos_asistencia
                WHERE ({base_where})
                  AND {date_condition}
                  AND {door_condition}
            """)
            row_fases = (await session.execute(sql_fases, params_base)).first()
            f_vesp = int(row_fases.fase_vespertina or 0) if row_fases else 0
            f_prof = int(row_fases.fase_profunda or 0) if row_fases else 0
            f_cier = int(row_fases.fase_cierre or 0) if row_fases else 0
            total_fases = f_vesp + f_prof + f_cier or 1

            fases_list = [
                {"fase": "Apertura Extensión Nocturna (22:00 / 23:00 a 00:00)", "ingresos": f_vesp, "porcentaje": round(100.0 * f_vesp / total_fases, 1)},
                {"fase": "Madrugada Profunda (00:00 a 04:00)", "ingresos": f_prof, "porcentaje": round(100.0 * f_prof / total_fases, 1)},
                {"fase": "Transición de Cierre (04:00 a 06:00 / 07:00)", "ingresos": f_cier, "porcentaje": round(100.0 * f_cier / total_fases, 1)},
            ]

            sql_pico = text(f"""
                SELECT TOP 1
                    hora_dia AS hora,
                    COUNT(*) AS concurrencia
                FROM eventos_asistencia
                WHERE ({base_where})
                  AND {date_condition}
                  AND {door_condition}
                  AND {nocturno_condition}
                GROUP BY hora_dia
                ORDER BY COUNT(*) DESC
            """)
            row_pico = (await session.execute(sql_pico, params_base)).first()
            pico_aforo = int(row_pico.concurrencia) if row_pico else 0
            hora_pico = f"{int(row_pico.hora):02d}:00 hrs" if row_pico else "Sin datos"
            tasa_ocupacion = round(100.0 * pico_aforo / capacidad_asientos, 1) if capacidad_asientos else 0.0

            sql_carreras = text(f"""
                WITH presencia_est AS (
                    SELECT 
                        COALESCE(carrera, 'Otras Carreras') AS carrera,
                        person_id_hash,
                        SUM(CASE WHEN door_entrada LIKE '%CSF04%' THEN 1 ELSE 0 END) AS entradas_noc,
                        SUM(CASE WHEN door_salida LIKE '%CSF04%' THEN 1 ELSE 0 END) AS salidas_noc
                    FROM eventos_asistencia
                    WHERE ({base_where})
                      AND {date_condition}
                      AND (door_entrada LIKE '%CSF04%' OR door_salida LIKE '%CSF04%')
                      AND {nocturno_condition}
                    GROUP BY carrera, person_id_hash
                )
                SELECT TOP 8
                    carrera,
                    SUM(CASE WHEN entradas_noc > 0 THEN entradas_noc ELSE 1 END) AS visitas,
                    COUNT(DISTINCT person_id_hash) AS estudiantes
                FROM presencia_est
                GROUP BY carrera
                ORDER BY visitas DESC, estudiantes DESC
            """)
            rows_carreras = (await session.execute(sql_carreras, params_base)).fetchall()
            tot_visitas_carr = sum(int(r.visitas) for r in rows_carreras) or ing_nocturnos or 1
            top_carreras = [
                {
                    "carrera": r.carrera,
                    "visitas": int(r.visitas),
                    "estudiantes": int(r.estudiantes),
                    "porcentaje": round(100.0 * int(r.visitas) / tot_visitas_carr, 1),
                }
                for r in rows_carreras
            ]

            sql_facultades = text(f"""
                WITH presencia_est AS (
                    SELECT 
                        COALESCE(facultad, 'Facultad General') AS facultad,
                        person_id_hash,
                        SUM(CASE WHEN door_entrada LIKE '%CSF04%' THEN 1 ELSE 0 END) AS entradas_noc,
                        SUM(CASE WHEN door_salida LIKE '%CSF04%' THEN 1 ELSE 0 END) AS salidas_noc
                    FROM eventos_asistencia
                    WHERE ({base_where})
                      AND {date_condition}
                      AND (door_entrada LIKE '%CSF04%' OR door_salida LIKE '%CSF04%')
                      AND {nocturno_condition}
                    GROUP BY facultad, person_id_hash
                )
                SELECT TOP 5
                    facultad,
                    SUM(CASE WHEN entradas_noc > 0 THEN entradas_noc ELSE 1 END) AS visitas,
                    COUNT(DISTINCT person_id_hash) AS estudiantes
                FROM presencia_est
                GROUP BY facultad
                ORDER BY visitas DESC, estudiantes DESC
            """)
            rows_facultades = (await session.execute(sql_facultades, params_base)).fetchall()
            tot_visitas_fac = sum(int(r.visitas) for r in rows_facultades) or ing_nocturnos or 1
            top_facultades = [
                {
                    "facultad": r.facultad,
                    "visitas": int(r.visitas),
                    "estudiantes": int(r.estudiantes),
                    "porcentaje": round(100.0 * int(r.visitas) / tot_visitas_fac, 1),
                }
                for r in rows_facultades
            ]

            sql_curva = text(f"""
                SELECT 
                    hora_dia AS hora,
                    COUNT(*) AS ingresos,
                    COUNT(DISTINCT CAST(time AS DATE)) AS dias_con_acceso
                FROM eventos_asistencia
                WHERE ({base_where})
                  AND {date_condition}
                  AND {door_condition}
                  AND {nocturno_condition}
                GROUP BY hora_dia
                ORDER BY 
                    CASE 
                        WHEN hora_dia >= 22 THEN hora_dia - 22
                        ELSE hora_dia + 2
                    END
            """)
            rows_curva = (await session.execute(sql_curva, params_base)).fetchall()
            horas_orden = [22, 23, 0, 1, 2, 3, 4, 5, 6, 7]
            dict_curva = {int(r.hora): int(r.ingresos) for r in rows_curva}
            curva_nocturna = [
                {
                    "hora": f"{h:02d}:00",
                    "hora_num": h,
                    "ingresos": dict_curva.get(h, 0),
                }
                for h in horas_orden
            ]

            sql_dias = text(f"""
                SELECT 
                    dia_semana_iso AS dia_num,
                    COUNT(*) AS ingresos,
                    COUNT(DISTINCT person_id_hash) AS estudiantes
                FROM eventos_asistencia
                WHERE ({base_where})
                  AND {date_condition}
                  AND {door_condition}
                  AND {nocturno_condition}
                GROUP BY dia_semana_iso
                ORDER BY dia_semana_iso
            """)
            rows_dias = (await session.execute(sql_dias, params_base)).fetchall()
            dict_dias = {int(r.dia_num): {"ingresos": int(r.ingresos), "estudiantes": int(r.estudiantes)} for r in rows_dias}
            dias_semana_list = []
            for d_num in [1, 2, 3, 4, 5, 6, 7]:
                info = dict_dias.get(d_num, {"ingresos": 0, "estudiantes": 0})
                pct = round(100.0 * info["ingresos"] / (ing_nocturnos or 1), 1)
                dias_semana_list.append({
                    "dia": nombres_dias[d_num],
                    "dia_num": d_num,
                    "ingresos": info["ingresos"],
                    "estudiantes": info["estudiantes"],
                    "porcentaje": pct,
                })
        else:
            # Período regular sin régimen 24 Horas activo
            ing_diurnos = int(row_kpis.total_ingresos or 0) if row_kpis else 0
            ing_nocturnos = 0
            total_ing = ing_diurnos
            pct_delta = 0.0
            est_nocturnos = 0
            horas_nocturnas = 0.0
            perm_nocturna = 0.0
            fases_list = [
                {"fase": "Apertura Extensión Nocturna (22:00 / 23:00 a 00:00)", "ingresos": 0, "porcentaje": 0.0},
                {"fase": "Madrugada Profunda (00:00 a 04:00)", "ingresos": 0, "porcentaje": 0.0},
                {"fase": "Transición de Cierre (04:00 a 06:00 / 07:00)", "ingresos": 0, "porcentaje": 0.0},
            ]
            hora_pico = "Sin régimen 24h"
            pico_aforo = 0
            tasa_ocupacion = 0.0
            top_carreras = []
            top_facultades = []
            curva_nocturna = [
                {"hora": f"{h:02d}:00", "hora_num": h, "ingresos": 0}
                for h in [22, 23, 0, 1, 2, 3, 4, 5, 6, 7]
            ]
            dias_semana_list = [
                {"dia": nombres_dias[d_num], "dia_num": d_num, "ingresos": 0, "estudiantes": 0, "porcentaje": 0.0}
                for d_num in [2, 3, 4, 5, 6, 7, 1]
            ]

        # 3. Comparativa entre campañas institucionales 24 Horas
        comparativa_campanas = []
        for c in todas_campanas:
            if not c.fecha_inicio or not c.fecha_fin:
                continue
            cf_ini = c.fecha_inicio.date()
            cf_fin = c.fecha_fin.date()
            p_camp = {**base_params, "espacio_id": espacio_id, "cf_ini": cf_ini, "cf_fin": cf_fin}
            sql_c_kpi = text(f"""
                SELECT 
                    SUM(CASE WHEN (({cond_lj}) OR ({cond_vie})) THEN 1 ELSE 0 END) AS nocturnos,
                    SUM(CASE WHEN NOT (({cond_lj}) OR ({cond_vie})) THEN 1 ELSE 0 END) AS diurnos,
                    COUNT(DISTINCT CASE WHEN (({cond_lj}) OR ({cond_vie})) THEN person_id_hash END) AS est_nocturnos,
                    ROUND(SUM(CASE WHEN (({cond_lj}) OR ({cond_vie})) THEN COALESCE(permanencia_min, 120) ELSE 0 END) / 60.0, 1) AS horas_nocturnas
                FROM eventos_asistencia
                WHERE ({base_where})
                  AND time >= :cf_ini AND time < DATEADD(day, 1, CAST(:cf_fin AS DATE))
                  AND {door_condition}
            """)
            row_c = (await session.execute(sql_c_kpi, p_camp)).first()
            c_noct = int(row_c.nocturnos or 0) if row_c else 0
            c_diur = int(row_c.diurnos or 0) if row_c else 0
            c_tot = c_noct + c_diur
            c_delta = round(100.0 * c_noct / (c_tot or 1), 2) if c_tot > 0 else 0.0
            comparativa_campanas.append({
                "id": c.id,
                "descripcion": c.descripcion,
                "fecha_inicio": cf_ini.isoformat(),
                "fecha_fin": cf_fin.isoformat(),
                "ingresos_nocturnos": c_noct,
                "ingresos_diurnos": c_diur,
                "total_ingresos": c_tot,
                "porcentaje_delta_24h": c_delta,
                "estudiantes_nocturnos_unicos": int(row_c.est_nocturnos or 0) if row_c else 0,
                "horas_estudio_nocturnas": float(row_c.horas_nocturnas or 0.0) if row_c else 0.0,
            })

        # 4. Mapa de Calor (Heatmap) por semanas (Lunes a Domingo × 24 Horas)
        sql_heatmap = text(f"""
            SELECT 
                (YEAR(time) * 100 + DATEPART(week, time)) as semana_num,
                MIN(CAST(time AS DATE)) as min_fecha,
                MAX(CAST(time AS DATE)) as max_fecha,
                dia_semana_iso as dia_dw,
                hora_dia as hora,
                COUNT(*) as ingresos
            FROM eventos_asistencia
            WHERE ({base_where})
              AND {date_condition}
              AND {door_condition}
            GROUP BY (YEAR(time) * 100 + DATEPART(week, time)), dia_semana_iso, hora_dia
            ORDER BY semana_num, dia_dw, hora
        """)
        rows_heatmap = (await session.execute(sql_heatmap, params_base)).fetchall()

        dw_to_idx = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6}
        dias_nombres = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}

        def es_franja_nocturna_24h(dia_idx: int, hora: int) -> bool:
            if dia_idx in (0, 1, 2, 3):  # Lunes a Jueves: 23:00 a 07:00 h
                return hora >= 23 or hora < 7
            elif dia_idx == 4:  # Viernes: 22:00 a 06:00 h
                return hora >= 22
            elif dia_idx == 5:  # Sábado madrugada (cierre viernes): hasta las 06:00 h
                return hora < 6
            return False

        # Filtrar exclusivamente semanas que pertenezcan a períodos con régimen 24 Horas activo
        rangos_24h = (
            intervalos_objetivo
            if (campana_id == 0 and intervalos_objetivo)
            else [
                (c.fecha_inicio.date(), c.fecha_fin.date())
                for c in campanas_con_fechas
            ]
        )

        def es_semana_valida_24h(d_min, d_max) -> bool:
            min_d = d_min if isinstance(d_min, date) else d_min.date()
            max_d = d_max if isinstance(d_max, date) else d_max.date()
            if regla_24h and regla_24h.fecha_inicio and regla_24h.fecha_fin:
                c_ini = regla_24h.fecha_inicio.date()
                c_fin = regla_24h.fecha_fin.date()
                return not (max_d < c_ini or min_d > c_fin)
            if rangos_24h:
                return any(not (max_d < c_ini or min_d > c_fin) for c_ini, c_fin in rangos_24h)
            return True

        semanas_dict = {}
        for r in rows_heatmap:
            if not es_semana_valida_24h(r.min_fecha, r.max_fecha):
                continue
            s_num = int(r.semana_num)
            idx_dia = dw_to_idx.get(int(r.dia_dw), 0)
            hora_int = int(r.hora)
            es_noc = es_franja_nocturna_24h(idx_dia, hora_int)
            if s_num not in semanas_dict:
                semanas_dict[s_num] = {
                    "min": r.min_fecha,
                    "max": r.max_fecha,
                    "puntos": []
                }
            else:
                if r.min_fecha < semanas_dict[s_num]["min"]:
                    semanas_dict[s_num]["min"] = r.min_fecha
                if r.max_fecha > semanas_dict[s_num]["max"]:
                    semanas_dict[s_num]["max"] = r.max_fecha

            semanas_dict[s_num]["puntos"].append({
                "dia_semana": idx_dia,
                "dia_nombre": dias_nombres.get(idx_dia, ""),
                "hora": hora_int,
                "ingresos_promedio": float(r.ingresos),
                "es_nocturno": es_noc,
            })

        semanas_disponibles = [
            {
                "id": "todas",
                "label": "Todas las semanas (Consolidado)",
                "fecha_inicio": f_ini.isoformat() if f_ini else None,
                "fecha_fin": f_fin.isoformat() if f_fin else None,
            }
        ]
        matriz_por_semana = {}

        todas_puntos = {}
        num_semanas = len(semanas_dict) or 1
        for s_idx, (s_num, s_data) in enumerate(sorted(semanas_dict.items()), 1):
            s_id = f"semana_{s_idx}"
            f_ini_sem = s_data["min"].strftime("%d/%m/%Y")
            f_fin_sem = s_data["max"].strftime("%d/%m/%Y")
            semanas_disponibles.append({
                "id": s_id,
                "label": f"Semana {s_idx} ({f_ini_sem} al {f_fin_sem})",
                "fecha_inicio": s_data["min"].isoformat(),
                "fecha_fin": s_data["max"].isoformat(),
            })
            matriz_por_semana[s_id] = s_data["puntos"]

            for p in s_data["puntos"]:
                k = (p["dia_semana"], p["hora"])
                todas_puntos[k] = todas_puntos.get(k, 0.0) + p["ingresos_promedio"]

        matriz_por_semana["todas"] = [
            {
                "dia_semana": k[0],
                "dia_nombre": dias_nombres.get(k[0], ""),
                "hora": k[1],
                "ingresos_promedio": round(v / num_semanas, 1),
                "es_nocturno": es_franja_nocturna_24h(k[0], k[1]),
            }
            for k, v in todas_puntos.items()
        ]

        return {
            "campana": {
                "id": regla_24h.id if regla_24h else (0 if (campana_id is not None and campana_id == 0) else -1),
                "descripcion": desc_campana,
                "subespacio": subespacio,
                "subespacio_label": "Sala 2 (CSF04 Pecera 1° Piso)",
                "capacidad_asientos": capacidad_asientos,
                "fecha_inicio": f_ini.isoformat() if f_ini else None,
                "fecha_fin": f_fin.isoformat() if f_fin else None,
                "tiene_campana_activa": tiene_campana_activa,
            },
            "campanas_disponibles": campanas_list,
            "bloque_horario_activo": bloque_horario or "todos",
            "bloque_horario_label": label_bloque,
            "kpis_comparativa": {
                "ingresos_diurnos": ing_diurnos,
                "ingresos_nocturnos": ing_nocturnos,
                "total_ingresos": total_ing,
                "porcentaje_delta_24h": pct_delta,
                "estudiantes_nocturnos_unicos": est_nocturnos,
                "estudiantes_remanentes_vespertinos": est_remanentes if tiene_campana_activa else 0,
                "estudiantes_totales_unicos": int(row_kpis.estudiantes_totales_unicos or 0) if row_kpis else 0,
                "horas_estudio_nocturnas": horas_nocturnas,
                "permanencia_promedio_nocturna_min": perm_nocturna,
                "permanencia_promedio_diurna_min": float(row_kpis.permanencia_promedio_diurna_min or 0.0) if row_kpis else 0.0,
            },
            "pico_nocturno": {
                "aforo_maximo": pico_aforo,
                "hora_pico": hora_pico,
                "tasa_ocupacion_asientos_pct": tasa_ocupacion,
            },
            "fases_madrugada": fases_list,
            "top_carreras": top_carreras,
            "top_facultades": top_facultades,
            "curva_nocturna": curva_nocturna,
            "dias_semana_nocturno": dias_semana_list,
            "comparativa_campanas": comparativa_campanas,
            "mapa_calor": {
                "semanas_disponibles": semanas_disponibles,
                "matriz_por_semana": matriz_por_semana,
            },
        }


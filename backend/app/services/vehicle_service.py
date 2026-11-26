"""
VehicleService — Consultas sobre Continuous Aggregates y tablas de estacionamiento en SQL Server.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta
import re
from typing import Dict, Optional

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import TTLCache

CAPACIDAD_ESTACIONAMIENTO = 125
UMBRAL_ALERTA_90 = 0.90
SECTORES_VEHICULARES_BASE = frozenset({"CSF11", "CSF21", "CHS01"})
_PATRON_SECTOR_VEHICULAR = re.compile(r"^[A-Z0-9_-]{2,20}$")


def _validar_sectores_vehiculares(
    sector: Optional[str],
    sectores_validos: Optional[set[str]] = None,
) -> list[str]:
    """Valida códigos de sector contra lista blanca estricta para prevenir SQLi."""
    if not sector or sector.strip().lower() == "todos":
        return []
    permitidos = {
        s.strip().upper()
        for s in ((sectores_validos or set()) | SECTORES_VEHICULARES_BASE)
        if s and s.strip().lower() != "todos"
    }
    validados: list[str] = []
    for raw in sector.split(","):
        cod = raw.strip().upper()
        if not cod or cod == "TODOS":
            continue
        if not _PATRON_SECTOR_VEHICULAR.match(cod) or cod not in permitidos:
            raise HTTPException(
                status_code=400,
                detail="Código de sector vehicular no válido.",
            )
        if cod not in validados:
            validados.append(cod)
    return validados


def _construir_filtro_camara_sectores(
    sec_keys: list[str],
    params: dict,
    prefijo: str = "sec",
) -> str:
    if not sec_keys:
        return ""
    clausulas = []
    for i, cod in enumerate(sec_keys):
        pname = f"{prefijo}_{i}"
        clausulas.append(f"camara LIKE :{pname}")
        params[pname] = f"%{cod}%"
    return " AND (" + " OR ".join(clausulas) + ")"


def _construir_filtro_codigo_sectores(
    sec_keys: list[str],
    params: dict,
    prefijo: str = "sec_cod",
) -> str:
    clausulas = []
    for i, cod in enumerate(sec_keys):
        pname = f"{prefijo}_{i}"
        clausulas.append(f"codigo = :{pname}")
        params[pname] = cod
    return " OR ".join(clausulas)

# Caché en memoria para reutilizar horarios de operación y calendario vehiculares
cache_horarios_espacio: TTLCache = TTLCache(maxsize=64, ttl=300)


async def obtener_horarios_operacion_cacheados(session: AsyncSession, espacio_id: int) -> list:
    clave_cache = f"horarios_24h:{espacio_id}"
    if clave_cache in cache_horarios_espacio:
        return cache_horarios_espacio[clave_cache]
    try:
        sql_24h = text("""
            SELECT fecha_inicio, fecha_fin 
            FROM horarios_operacion 
            WHERE espacio_id = :espacio_id AND activo = 1 AND es_continuo_24h = 1
        """)
        filas = (await session.execute(sql_24h, {"espacio_id": espacio_id})).fetchall()
    except Exception:
        filas = []
    cache_horarios_espacio[clave_cache] = filas
    return filas


async def obtener_calendario_vehicular_cacheado(session: AsyncSession) -> dict:
    clave_cache = "cal_vehicular"
    if clave_cache in cache_horarios_espacio:
        return cache_horarios_espacio[clave_cache]
    feriados: list[date] = []
    paros_fed: list[date] = []
    paros_car: list[date] = []
    try:
        sql_cal = text("""
            SELECT CAST(fecha AS DATE) AS fecha, is_holiday, is_strike_federado, is_strike_carrera
            FROM calendario_academico
            WHERE is_holiday = 1 OR is_strike_federado = 1 OR is_strike_carrera = 1
        """)
        for r in (await session.execute(sql_cal)).fetchall():
            f_val = r.fecha if isinstance(r.fecha, date) else date.fromisoformat(str(r.fecha)[:10])
            if getattr(r, "is_holiday", 0):
                feriados.append(f_val)
            if getattr(r, "is_strike_federado", 0):
                paros_fed.append(f_val)
            if getattr(r, "is_strike_carrera", 0):
                paros_car.append(f_val)
    except Exception:
        pass
    datos = {"feriados": feriados, "paros_fed": paros_fed, "paros_car": paros_car}
    cache_horarios_espacio[clave_cache] = datos
    return datos


def invalidar_cache_horarios(espacio_id: Optional[int] = None) -> None:
    if espacio_id is not None:
        cache_horarios_espacio.pop(f"horarios_24h:{espacio_id}", None)
        cache_horarios_espacio.pop(f"caps_vehiculares_detalle:{espacio_id}", None)
        cache_horarios_espacio.pop("cal_vehicular", None)
        for k in list(cache_horarios_espacio.keys()):
            if str(k).startswith("horario_id:"):
                cache_horarios_espacio.pop(k, None)
    else:
        cache_horarios_espacio.clear()


invalidar_cache_horarios_vehiculos = invalidar_cache_horarios


async def _obtener_capacidades_sectores_vehiculares(session: AsyncSession, espacio_id: int = 2) -> Dict[str, int]:
    """Obtiene dinámicamente capacidades por sector vehicular y total calibrado desde BD con caché."""
    clave_cache = f"caps_vehiculares_detalle:{espacio_id}"
    if clave_cache in cache_horarios_espacio:
        return dict(cache_horarios_espacio[clave_cache])

    caps: Dict[str, int] = {"CSF11": 40, "CSF21": 50, "CHS01": 35, "todos": 125}
    try:
        res_sec = await session.execute(
            text("SELECT codigo, capacidad_max FROM sectores_estacionamiento WHERE activo = 1")
        )
        filas_sec = res_sec.fetchall()
        suma_sec = 0
        for row in filas_sec:
            cod = str(getattr(row, "codigo", "") or "").strip().upper()
            cap_val = int(getattr(row, "capacidad_max", 0) or 0)
            if cod and cap_val > 0:
                caps[cod] = cap_val
                suma_sec += cap_val
        if suma_sec > 0:
            caps["todos"] = suma_sec
    except Exception:
        pass

    try:
        from app.domain.models import Espacio
        cap_esp = (await session.execute(select(Espacio.capacidad_max).where(Espacio.id == espacio_id))).scalar_one_or_none()
        if cap_esp and int(cap_esp) > 0:
            caps["todos"] = int(cap_esp)
    except Exception:
        pass

    cache_horarios_espacio[clave_cache] = dict(caps)
    return caps


def _extraer_hora_pico_curva_vehicular(curva: list[dict]) -> Optional[str]:
    """Extrae la hora (HH:00 hrs) correspondiente al máximo de vehículos simultáneos en la curva."""
    if not curva:
        return None
    pico = max(
        curva,
        key=lambda r: (int(r.get("vehiculos_presentes", 0) or 0), int(r.get("entradas", 0) or 0)),
    )
    if int(pico.get("vehiculos_presentes", 0) or 0) <= 0:
        return None
    bucket = str(pico.get("bucket") or "")
    if len(bucket) >= 13 and "T" in bucket:
        return f"{bucket[11:13]}:00 hrs"
    return None


def _construir_expr_cierre_vehicular_sql(cond_h24_sql: str) -> str:
    """Calcula el límite efectivo de salida por jornada para sesiones vehiculares sin marca de salida."""
    return f"""
        CASE
            WHEN ({cond_h24_sql}) THEN DATETIME2FROMPARTS(YEAR(e.fecha), MONTH(e.fecha), DAY(e.fecha), 23, 59, 59, 0, 0)
            WHEN ((DATEPART(WEEKDAY, e.fecha) + @@DATEFIRST - 2) % 7 + 1) = 6 THEN DATETIME2FROMPARTS(YEAR(e.fecha), MONTH(e.fecha), DAY(e.fecha), 14, 0, 0, 0, 0)
            WHEN ((DATEPART(WEEKDAY, e.fecha) + @@DATEFIRST - 2) % 7 + 1) BETWEEN 1 AND 5 THEN DATETIME2FROMPARTS(YEAR(e.fecha), MONTH(e.fecha), DAY(e.fecha), 22, 0, 0, 0, 0)
            ELSE DATETIME2FROMPARTS(YEAR(e.fecha), MONTH(e.fecha), DAY(e.fecha), 23, 59, 59, 0, 0)
        END
    """


def _calcular_curva_presencia_vehicular_por_hora(
    sesiones_rows: list,
    flujo_rows: list,
    ahora_servidor: datetime,
    caps_sector: Dict[str, int],
    capacidad_total: int,
) -> list[dict]:
    """Barrido cronológico minuto/segundo para concurrencia vehicular simultánea real sin solapamiento por hora."""
    eventos_por_dia: Dict[date, list] = defaultdict(list)
    for row in sesiones_rows:
        fecha_raw = row[0] if isinstance(row, tuple) else row.fecha
        sec_num = int((row[1] if isinstance(row, tuple) else row.sector_num) or 0)
        t_ent = row[2] if isinstance(row, tuple) else row.t_entrada
        t_sal = row[3] if isinstance(row, tuple) else row.t_salida
        if t_ent is None or t_sal is None:
            continue
        fecha = fecha_raw if isinstance(fecha_raw, date) and not isinstance(fecha_raw, datetime) else (
            fecha_raw.date() if isinstance(fecha_raw, datetime) else date.fromisoformat(str(fecha_raw)[:10])
        )
        t_sal_adj = t_sal if t_sal > t_ent else t_ent + timedelta(seconds=1)
        eventos_por_dia[fecha].append((t_ent, 1, sec_num))
        if t_sal_adj.date() == fecha:
            eventos_por_dia[fecha].append((t_sal_adj, -1, sec_num))

    flujo_por_bucket: Dict[datetime, tuple] = {}
    max_hora_flujo_por_dia: Dict[date, int] = {}
    for row in flujo_rows:
        b_raw = row[0] if isinstance(row, tuple) else row.bucket
        b_dt = b_raw if isinstance(b_raw, datetime) else datetime.fromisoformat(str(b_raw))
        f_raw = row[1] if isinstance(row, tuple) else row.fecha
        fecha_f = f_raw if isinstance(f_raw, date) and not isinstance(f_raw, datetime) else (
            f_raw.date() if isinstance(f_raw, datetime) else date.fromisoformat(str(f_raw)[:10])
        )
        vals = (
            int((row[2] if isinstance(row, tuple) else row.entradas) or 0),
            int((row[3] if isinstance(row, tuple) else row.salidas) or 0),
            int((row[4] if isinstance(row, tuple) else row.entradas_csf11) or 0),
            int((row[5] if isinstance(row, tuple) else row.salidas_csf11) or 0),
            int((row[6] if isinstance(row, tuple) else row.entradas_csf21) or 0),
            int((row[7] if isinstance(row, tuple) else row.salidas_csf21) or 0),
            int((row[8] if isinstance(row, tuple) else row.entradas_chs01) or 0),
            int((row[9] if isinstance(row, tuple) else row.salidas_chs01) or 0),
        )
        flujo_por_bucket[b_dt] = vals
        if fecha_f not in max_hora_flujo_por_dia or b_dt.hour > max_hora_flujo_por_dia[fecha_f]:
            max_hora_flujo_por_dia[fecha_f] = b_dt.hour

    cap_11 = int(caps_sector.get("CSF11", 40))
    cap_21 = int(caps_sector.get("CSF21", 50))
    cap_01 = int(caps_sector.get("CHS01", 35))

    fechas_ordenadas = sorted(set(eventos_por_dia.keys()) | set(max_hora_flujo_por_dia.keys()))
    hoy_servidor = ahora_servidor.date()
    resultado: list[dict] = []

    for fecha in fechas_ordenadas:
        evs = eventos_por_dia.get(fecha, [])
        evs.sort(key=lambda x: x[0])

        occ_t = occ_11 = occ_21 = occ_01 = 0
        hour_first: Dict[int, datetime] = {}
        hour_peak: Dict[int, list] = {}
        hour_end: Dict[int, tuple] = {}

        idx = 0
        n_evs = len(evs)
        while idx < n_evs:
            ts_actual = evs[idx][0]
            dtot = d11 = d21 = d01 = 0
            while idx < n_evs and evs[idx][0] == ts_actual:
                _, delta, sec_num = evs[idx]
                dtot += delta
                if sec_num == 1:
                    d11 += delta
                elif sec_num == 2:
                    d21 += delta
                elif sec_num == 3:
                    d01 += delta
                idx += 1

            occ_t = max(0, occ_t + dtot)
            occ_11 = max(0, occ_11 + d11)
            occ_21 = max(0, occ_21 + d21)
            occ_01 = max(0, occ_01 + d01)

            h = ts_actual.hour
            if h not in hour_first:
                hour_first[h] = ts_actual
            pk = hour_peak.get(h)
            if pk is None:
                hour_peak[h] = [occ_t, occ_11, occ_21, occ_01]
            else:
                if occ_t > pk[0]:
                    pk[0] = occ_t
                if occ_11 > pk[1]:
                    pk[1] = occ_11
                if occ_21 > pk[2]:
                    pk[2] = occ_21
                if occ_01 > pk[3]:
                    pk[3] = occ_01
            hour_end[h] = (occ_t, occ_11, occ_21, occ_01)

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

        prev_e = (0, 0, 0, 0)
        for h in range(h_min, h_max + 1):
            bucket_dt = datetime.combine(fecha, datetime.min.time()) + timedelta(hours=h)
            if bucket_dt > ahora_servidor:
                continue

            if h in hour_peak:
                ft = hour_first[h]
                pk = hour_peak[h]
                if ft.minute > 0 or ft.second > 0 or ft.microsecond > 0:
                    p_t = max(prev_e[0], pk[0])
                    p_11 = max(prev_e[1], pk[1])
                    p_21 = max(prev_e[2], pk[2])
                    p_01 = max(prev_e[3], pk[3])
                else:
                    p_t, p_11, p_21, p_01 = pk[0], pk[1], pk[2], pk[3]
                prev_e = hour_end[h]
            else:
                p_t, p_11, p_21, p_01 = prev_e

            fl = flujo_por_bucket.get(bucket_dt, (0, 0, 0, 0, 0, 0, 0, 0))
            v_tot = min(capacidad_total, max(0, int(p_t)))
            if fl[0] > 0 or fl[1] > 0 or v_tot > 0:
                resultado.append({
                    "bucket":              bucket_dt.isoformat(),
                    "vehiculos_presentes": v_tot,
                    "personas_unicas":     v_tot,
                    "entradas":            fl[0],
                    "salidas":             fl[1],
                    "ingresos":            fl[0],
                    "vehiculos_csf11":     min(cap_11, max(0, int(p_11))),
                    "vehiculos_csf21":     min(cap_21, max(0, int(p_21))),
                    "vehiculos_chs01":     min(cap_01, max(0, int(p_01))),
                    "entradas_csf11":      fl[2],
                    "salidas_csf11":       fl[3],
                    "entradas_csf21":      fl[4],
                    "salidas_csf21":       fl[5],
                    "entradas_chs01":      fl[6],
                    "salidas_chs01":       fl[7],
                    "capacidad_total":     capacidad_total,
                    "capacidad_csf11":     cap_11,
                    "capacidad_csf21":     cap_21,
                    "capacidad_chs01":     cap_01,
                })

    return resultado


class VehicleService:

    @staticmethod
    async def _build_vehicle_filters(
        session: AsyncSession,
        espacio_id: int = 2,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        alcance: Optional[str] = "conformes",
        regimen_horario: Optional[str] = "todos",
        direccion: Optional[str] = "todos",
        dias_semana: Optional[str] = None,
        door: Optional[str] = None,
        sector: Optional[str] = None,
        tipo_vehiculo: Optional[str] = None,
    ) -> tuple[str, dict]:
        fin_exclusive = fecha_fin + timedelta(days=1) if fecha_fin else None
        conditions = ["espacio_id = :espacio_id"]
        params: dict = {"espacio_id": espacio_id}

        if fecha_inicio:
            conditions.append("time >= :inicio")
            params["inicio"] = fecha_inicio
        if fin_exclusive:
            conditions.append("time < :fin")
            params["fin"] = fin_exclusive

        # Consulta dinámica de períodos especiales/24h activos en horarios_operacion con caché en memoria
        active_24h_rows = await obtener_horarios_operacion_cacheados(session, espacio_id)

        h24_clauses = []
        for i, r_24 in enumerate(active_24h_rows):
            if r_24.fecha_inicio and r_24.fecha_fin:
                p_ini = f"h24_ini_{i}"
                p_fin = f"h24_fin_{i}"
                h24_clauses.append(f"(time >= :{p_ini} AND time <= :{p_fin})")
                params[p_ini] = r_24.fecha_inicio
                params[p_fin] = r_24.fecha_fin

        is_24h_sql = f"({' OR '.join(h24_clauses)})" if h24_clauses else "1=0"
        not_24h_sql = f"(NOT ({' OR '.join(h24_clauses)}))" if h24_clauses else "1=1"

        cal_data = await obtener_calendario_vehicular_cacheado(session)
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

        closure_sql = (
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

        regular_open_sql = """(
            (((DATEPART(WEEKDAY, time) + @@DATEFIRST - 2) % 7 + 1) BETWEEN 1 AND 5 AND CAST(time AS TIME) >= '07:00:00' AND CAST(time AS TIME) <= '22:00:00')
            OR (((DATEPART(WEEKDAY, time) + @@DATEFIRST - 2) % 7 + 1) = 6 AND CAST(time AS TIME) >= '08:00:00' AND CAST(time AS TIME) <= '14:00:00')
        )"""

        f_oficial_sql = f"({regular_open_sql} AND NOT ({closure_sql}))" if feriados_rango else regular_open_sql

        regular_closed_sql = """(
            ((DATEPART(WEEKDAY, time) + @@DATEFIRST - 2) % 7 + 1) = 7
            OR (((DATEPART(WEEKDAY, time) + @@DATEFIRST - 2) % 7 + 1) BETWEEN 1 AND 5 AND (CAST(time AS TIME) < '07:00:00' OR CAST(time AS TIME) > '22:00:00'))
            OR (((DATEPART(WEEKDAY, time) + @@DATEFIRST - 2) % 7 + 1) = 6 AND (CAST(time AS TIME) < '08:00:00' OR CAST(time AS TIME) > '14:00:00'))
        )"""

        # 1. Alcance / Calidad
        if alcance == "conformes":
            conditions.append("calidad_lectura != 'unknown'")
        elif alcance == "anomalias":
            conditions.append(f"""(
                calidad_lectura = 'unknown'
                OR ({not_24h_sql} AND {regular_closed_sql})
                OR ({closure_sql})
            )""")

        # 2. Régimen de Horario
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
                            sql_h = text("SELECT fecha_inicio, fecha_fin, hora_apertura, hora_cierre, es_continuo_24h FROM horarios_operacion WHERE id = :h_id")
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
                            if not h_row.es_continuo_24h:
                                p_ape = f"h_apertura_{h_id}"
                                p_cie = f"h_cierre_{h_id}"
                                params[p_ape] = f"{h_row.hora_apertura}:00"
                                params[p_cie] = f"{h_row.hora_cierre}:00"
                                sub_clauses.append(f"(CAST(time AS TIME) >= :{p_ape} AND CAST(time AS TIME) <= :{p_cie})")
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

        # 3. Dirección (Soporte múltiple)
        dir_list = [d.strip().lower() for d in (direccion or "todos").split(",") if d.strip()]
        if dir_list and "todos" not in dir_list:
            dir_clauses = []
            for d in dir_list:
                if d in ("solo_ingreso", "entrada"):
                    dir_clauses.append("direccion = 'entrada'")
                elif d in ("solo_salida", "salida"):
                    dir_clauses.append("direccion = 'salida'")
            if dir_clauses:
                conditions.append(f"({' OR '.join(dir_clauses)})")

        # 4. Días de la semana (ISO 1=Lunes .. 7=Domingo, independiente de @@DATEFIRST)
        if dias_semana:
            dias_map = {
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
            dias_solicitados = [d.strip().lower() for d in dias_semana.split(",") if d.strip().lower() in dias_map]
            if dias_solicitados:
                weekday_ints = [str(dias_map[d]) for d in dias_solicitados]
                conditions.append(f"((DATEPART(WEEKDAY, time) + @@DATEFIRST - 2) % 7 + 1) IN ({','.join(weekday_ints)})")

        # 5. Puerta / Barrera / Cámara
        if door and door != "todos":
            doors_list = [d.strip() for d in door.split(",") if d.strip()]
            if doors_list:
                door_clauses = []
                for i, d in enumerate(doors_list):
                    pname = f"door_{i}"
                    door_clauses.append(f"camara LIKE :{pname}")
                    params[pname] = f"%{d}%"
                conditions.append(f"({' OR '.join(door_clauses)})")

        # 6. Sector Vehicular Institucional (CSF11, CSF21, CHS01)
        if sector and sector != "todos":
            caps_validos = await _obtener_capacidades_sectores_vehiculares(session, espacio_id)
            sectores_list = _validar_sectores_vehiculares(sector, set(caps_validos.keys()))
            if sectores_list:
                sec_clauses = []
                for i, sec_code in enumerate(sectores_list):
                    pname = f"sec_{i}"
                    sec_clauses.append(f"camara LIKE :{pname}")
                    params[pname] = f"%{sec_code}%"
                conditions.append(f"({' OR '.join(sec_clauses)})")

        # 7. Tipo de Vehículo
        if tipo_vehiculo and tipo_vehiculo != "todos":
            tipos_list = [t.strip() for t in tipo_vehiculo.split(",") if t.strip()]
            if tipos_list:
                tipo_clauses = []
                for i, t_val in enumerate(tipos_list):
                    pname = f"tipo_v_{i}"
                    tipo_clauses.append(f"tipo_vehiculo LIKE :{pname}")
                    params[pname] = f"%{t_val}%"
                conditions.append(f"({' OR '.join(tipo_clauses)})")

        return " AND ".join(conditions), params

    # ------------------------------------------------------------------
    # KPIs generales (con desduplicación de ráfagas ANPR <= 15 min)
    # ------------------------------------------------------------------
    @staticmethod
    async def get_kpis(
        session: AsyncSession,
        espacio_id: int = 2,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        alcance: str = "conformes",
        regimen_horario: Optional[str] = "todos",
        direccion: Optional[str] = "todos",
        dias_semana: Optional[str] = None,
        door: Optional[str] = None,
        sector: Optional[str] = None,
        tipo_vehiculo: Optional[str] = None,
    ) -> dict:
        where_sql, params = await VehicleService._build_vehicle_filters(
            session=session,
            espacio_id=espacio_id,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            alcance=alcance,
            regimen_horario=regimen_horario,
            direccion=direccion,
            dias_semana=dias_semana,
            door=door,
            sector=sector,
            tipo_vehiculo=tipo_vehiculo,
        )

        sql_global = text(f"""
            WITH ev_raw AS (
                SELECT
                    time,
                    patente_hash,
                    direccion,
                    camara,
                    calidad_lectura,
                    LAG(time) OVER (
                        PARTITION BY patente_hash, direccion, CAST(time AS DATE)
                        ORDER BY time
                    ) AS prev_same_dir_time
                FROM eventos_vehiculares
                WHERE {where_sql}
                  AND time <= GETDATE()
            ),
            ev_dedup AS (
                SELECT
                    time,
                    patente_hash,
                    direccion,
                    camara,
                    calidad_lectura
                FROM ev_raw
                WHERE patente_hash = 'unknown'
                   OR prev_same_dir_time IS NULL
                   OR DATEDIFF(minute, prev_same_dir_time, time) > 15
            ),
            kpis AS (
                SELECT
                    COUNT(DISTINCT patente_hash)                                   AS vehiculos_unicos,
                    SUM(CASE WHEN direccion = 'entrada' THEN 1 ELSE 0 END)         AS total_entradas,
                    SUM(CASE WHEN direccion = 'salida' THEN 1 ELSE 0 END)          AS total_salidas,
                    SUM(CASE WHEN direccion = 'entrada' AND camara LIKE '%CSF11%' THEN 1 ELSE 0 END) AS total_accesos_csf11,
                    SUM(CASE WHEN direccion = 'entrada' AND camara LIKE '%CSF21%' THEN 1 ELSE 0 END) AS total_accesos_csf21,
                    SUM(CASE WHEN direccion = 'entrada' AND camara LIKE '%CHS01%' THEN 1 ELSE 0 END) AS total_accesos_chs01,
                    COUNT(DISTINCT CAST(time AS DATE))                             AS dias_operativos,
                    ROUND(
                        100.0 * SUM(CASE WHEN calidad_lectura = 'unknown' THEN 1 ELSE 0 END)
                        / NULLIF(COUNT(*), 0),
                    2)                                                             AS tasa_lectura_fallida_pct
                FROM ev_dedup
            ),
            peak AS (
                SELECT TOP 1 DATEPART(hour, time) AS hora, COUNT(*) AS total
                FROM ev_raw
                GROUP BY DATEPART(hour, time)
                ORDER BY total DESC
            ),
            max_h AS (
                SELECT COALESCE(MAX(cnt), 0) AS max_entradas
                FROM (
                    SELECT COUNT(*) AS cnt
                    FROM ev_raw
                    GROUP BY DATEADD(hour, DATEDIFF(hour, 0, time), 0)
                ) sub
            )
            SELECT
                kp.vehiculos_unicos,
                kp.total_entradas,
                kp.total_salidas,
                kp.total_accesos_csf11,
                kp.total_accesos_csf21,
                kp.total_accesos_chs01,
                kp.dias_operativos,
                kp.tasa_lectura_fallida_pct,
                (SELECT hora FROM peak) AS hora_punta_num,
                mh.max_entradas
            FROM kpis kp
            CROSS JOIN max_h mh
        """)
        row_g = (await session.execute(sql_global, params)).one()

        dias = row_g.dias_operativos or 1
        entradas = row_g.total_entradas or 0
        salidas = row_g.total_salidas or 0
        hora_pico_entradas = f"{row_g.hora_punta_num:02d}:00 hrs" if row_g.hora_punta_num is not None else "08:00 hrs"
        max_entradas = row_g.max_entradas or 0

        caps_dict = await _obtener_capacidades_sectores_vehiculares(session, espacio_id)
        if sector and sector != "todos":
            sec_keys = [s.strip().upper() for s in sector.split(",") if s.strip()]
            capacidad_max = sum(caps_dict.get(s, 0) for s in sec_keys) or caps_dict.get("todos", 125)
        else:
            capacidad_max = caps_dict.get("todos", 125)

        turnover = round(entradas / dias / max(1, capacidad_max), 2)

        where_perm_sql, params_perm = await VehicleService._build_vehicle_filters(
            session=session,
            espacio_id=espacio_id,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            alcance=alcance,
            regimen_horario=regimen_horario,
            direccion="todos",
            dias_semana=dias_semana,
            door=door,
            sector=sector,
            tipo_vehiculo=tipo_vehiculo,
        )
        sql_perm = text(f"""
            WITH ev_perm_raw AS (
                SELECT
                    patente_hash,
                    time,
                    CAST(time AS DATE) AS fecha,
                    CASE WHEN direccion = 'salida' THEN 1 ELSE 0 END AS es_salida,
                    LAG(CASE WHEN direccion = 'salida' THEN 1 ELSE 0 END)
                        OVER (PARTITION BY patente_hash, CAST(time AS DATE) ORDER BY time) AS prev_es_salida,
                    LAG(time)
                        OVER (PARTITION BY patente_hash, CAST(time AS DATE) ORDER BY time) AS prev_time
                FROM eventos_vehiculares
                WHERE {where_perm_sql}
                  AND time <= GETDATE()
                  AND patente_hash != 'unknown'
            ),
            ev_perm_clean AS (
                SELECT
                    patente_hash,
                    time,
                    fecha,
                    es_salida,
                    LEAD(es_salida) OVER (PARTITION BY patente_hash, fecha ORDER BY time) AS next_es_salida,
                    LEAD(time) OVER (PARTITION BY patente_hash, fecha ORDER BY time) AS next_time
                FROM ev_perm_raw
                WHERE prev_es_salida IS NULL
                   OR prev_es_salida <> es_salida
                   OR DATEDIFF(minute, prev_time, time) > 15
            ),
            duraciones AS (
                SELECT DATEDIFF(second, time, next_time) / 60.0 AS stay_min
                FROM ev_perm_clean
                WHERE es_salida = 0
                  AND next_es_salida = 1
                  AND next_time > time
                  AND DATEDIFF(minute, time, next_time) BETWEEN 1 AND 1439
            )
            SELECT TOP 1
                ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY stay_min) OVER (), 2) AS permanencia_mediana_min
            FROM duraciones
        """)
        row_p = (await session.execute(sql_perm, params_perm)).first()
        mediana_min = float(row_p.permanencia_mediana_min) if row_p and row_p.permanencia_mediana_min is not None else 0.0

        # Fuente única de verdad: el pico concurrente y su hora punta coinciden exactamente con la curva sweep-line
        curva_presencia = await VehicleService.get_realtime_presence_curve(
            session=session,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            espacio_id=espacio_id,
            alcance=alcance,
            regimen_horario=regimen_horario,
            direccion=direccion,
            dias_semana=dias_semana,
            door=door,
            sector=sector,
            tipo_vehiculo=tipo_vehiculo,
        )
        punto_pico = max(curva_presencia, key=lambda r: r.get("vehiculos_presentes", 0), default=None)
        max_ocupacion_concurrente = int(punto_pico["vehiculos_presentes"]) if punto_pico else 0
        fecha_pico_ocupacion = (
            punto_pico["bucket"] if (punto_pico and max_ocupacion_concurrente > 0) else None
        )
        max_csf11 = max((int(r.get("vehiculos_csf11", 0)) for r in curva_presencia), default=0)
        max_csf21 = max((int(r.get("vehiculos_csf21", 0)) for r in curva_presencia), default=0)
        max_chs01 = max((int(r.get("vehiculos_chs01", 0)) for r in curva_presencia), default=0)
        hora_punta = _extraer_hora_pico_curva_vehicular(curva_presencia) or hora_pico_entradas

        return {
            "vehiculos_unicos":          int(row_g.vehiculos_unicos or 0),
            "total_accesos":             int(entradas),
            "total_salidas":             int(salidas),
            "total_accesos_csf11":       int(getattr(row_g, "total_accesos_csf11", 0) or 0),
            "total_accesos_csf21":       int(getattr(row_g, "total_accesos_csf21", 0) or 0),
            "total_accesos_chs01":       int(getattr(row_g, "total_accesos_chs01", 0) or 0),
            "dias_operativos":           int(dias),
            "turnover_rate_diario":      turnover,
            "permanencia_mediana_min":   mediana_min,
            "tasa_lectura_fallida_pct":  float(row_g.tasa_lectura_fallida_pct or 0),
            "hora_punta":                hora_punta,
            "hora_pico_entradas":        hora_pico_entradas,
            "max_aforo_historico":       max_ocupacion_concurrente,
            "max_aforo_csf11":           max_csf11,
            "max_aforo_csf21":           max_csf21,
            "max_aforo_chs01":           max_chs01,
            "max_entradas_hora":         int(max_entradas),
            "fecha_pico_ocupacion":      fecha_pico_ocupacion,
            "capacidad_calibrada":       int(capacidad_max),
            "capacidad_csf11":           int(caps_dict.get("CSF11", 40)),
            "capacidad_csf21":           int(caps_dict.get("CSF21", 50)),
            "capacidad_chs01":           int(caps_dict.get("CHS01", 35)),
        }

    # ------------------------------------------------------------------
    # Aforo vehicular en tiempo real (trazando entrada y salida desduplicadas)
    # ------------------------------------------------------------------
    @staticmethod
    async def get_parking_occupancy(
        session: AsyncSession,
        espacio_id: int = 2,
        sector: Optional[str] = None,
    ) -> dict:
        sql_date = text("""
            SELECT COALESCE(CAST(MAX(bucket) AS DATE), CAST(GETDATE() AS DATE))
            FROM aforo_horario_estacionamiento WITH (NOEXPAND)
            WHERE espacio_id = :espacio_id
        """)
        target_date = (await session.execute(sql_date, {"espacio_id": espacio_id})).scalar() or date.today()

        caps_dict = await _obtener_capacidades_sectores_vehiculares(session, espacio_id)
        vivo_params: dict = {"espacio_id": espacio_id, "target_date": target_date}
        sec_keys = _validar_sectores_vehiculares(sector, set(caps_dict.keys()))
        where_cam = _construir_filtro_camara_sectores(sec_keys, vivo_params, prefijo="vivo_sec")
        if sec_keys:
            capacidad_max = sum(caps_dict.get(s, 0) for s in sec_keys) or caps_dict.get("todos", 125)
        else:
            capacidad_max = caps_dict.get("todos", 125)

        h24_rows = await obtener_horarios_operacion_cacheados(session, espacio_id)
        h24_conds = []
        for i, r_24 in enumerate(h24_rows):
            f_ini = getattr(r_24, "fecha_inicio", None)
            f_fin = getattr(r_24, "fecha_fin", None)
            if f_ini and f_fin:
                vivo_params[f"vh24_ini_{i}"] = f_ini.date() if isinstance(f_ini, datetime) else f_ini
                vivo_params[f"vh24_fin_{i}"] = f_fin.date() if isinstance(f_fin, datetime) else f_fin
                h24_conds.append(f"(e.fecha >= :vh24_ini_{i} AND e.fecha <= :vh24_fin_{i})")
        cond_h24_sql = " OR ".join(h24_conds) if h24_conds else "1=0"
        expr_cierre_sql = _construir_expr_cierre_vehicular_sql(cond_h24_sql)

        sql = text(f"""
            WITH ev_base AS (
                SELECT
                    time,
                    CAST(time AS DATE) AS fecha,
                    patente_hash,
                    CASE WHEN direccion = 'salida' THEN 1 ELSE 0 END AS es_salida,
                    CASE
                        WHEN camara LIKE '%CSF11%' THEN 1
                        WHEN camara LIKE '%CSF21%' THEN 2
                        WHEN camara LIKE '%CHS01%' THEN 3
                        ELSE 0
                    END AS sector_num,
                    LAG(CASE WHEN direccion = 'salida' THEN 1 ELSE 0 END) OVER (
                        PARTITION BY patente_hash, CAST(time AS DATE) ORDER BY time
                    ) AS prev_es_salida,
                    LAG(time) OVER (
                        PARTITION BY patente_hash, CAST(time AS DATE) ORDER BY time
                    ) AS prev_time
                FROM eventos_vehiculares
                WHERE espacio_id = :espacio_id
                  AND time >= :target_date
                  AND time < DATEADD(day, 1, CAST(:target_date AS DATETIME))
                  AND time <= GETDATE()
                  AND calidad_lectura != 'unknown'
                  AND patente_hash != 'unknown'
                  {where_cam}
            ),
            ev_dedup AS (
                SELECT
                    time,
                    fecha,
                    patente_hash,
                    es_salida,
                    sector_num,
                    LEAD(time) OVER (
                        PARTITION BY patente_hash, fecha ORDER BY time
                    ) AS next_time
                FROM ev_base
                WHERE prev_es_salida IS NULL
                   OR prev_es_salida <> es_salida
                   OR DATEDIFF(minute, prev_time, time) > 15
            ),
            anchor AS (
                SELECT COALESCE(MAX(time), CAST(:target_date AS DATETIME2)) AS max_event_time
                FROM ev_dedup
            )
            SELECT
                COUNT(DISTINCT CASE
                    WHEN e.es_salida = 0
                     AND (
                         (e.next_time IS NOT NULL AND e.next_time > a.max_event_time)
                         OR (e.next_time IS NULL
                             AND DATEDIFF(minute, e.time, a.max_event_time) BETWEEN 0 AND 120
                             AND a.max_event_time <= ({expr_cierre_sql}))
                     )
                    THEN e.patente_hash
                END) AS vehiculos_presentes,
                COUNT(DISTINCT CASE
                    WHEN e.sector_num = 1 AND e.es_salida = 0
                     AND ((e.next_time IS NOT NULL AND e.next_time > a.max_event_time)
                          OR (e.next_time IS NULL AND DATEDIFF(minute, e.time, a.max_event_time) BETWEEN 0 AND 120 AND a.max_event_time <= ({expr_cierre_sql})))
                    THEN e.patente_hash
                END) AS vehiculos_csf11,
                COUNT(DISTINCT CASE
                    WHEN e.sector_num = 2 AND e.es_salida = 0
                     AND ((e.next_time IS NOT NULL AND e.next_time > a.max_event_time)
                          OR (e.next_time IS NULL AND DATEDIFF(minute, e.time, a.max_event_time) BETWEEN 0 AND 120 AND a.max_event_time <= ({expr_cierre_sql})))
                    THEN e.patente_hash
                END) AS vehiculos_csf21,
                COUNT(DISTINCT CASE
                    WHEN e.sector_num = 3 AND e.es_salida = 0
                     AND ((e.next_time IS NOT NULL AND e.next_time > a.max_event_time)
                          OR (e.next_time IS NULL AND DATEDIFF(minute, e.time, a.max_event_time) BETWEEN 0 AND 120 AND a.max_event_time <= ({expr_cierre_sql})))
                    THEN e.patente_hash
                END) AS vehiculos_chs01,
                MAX(a.max_event_time) AS max_event_time
            FROM ev_dedup e
            CROSS JOIN anchor a
        """)
        row = (await session.execute(sql, vivo_params)).one()

        cap_11 = int(caps_dict.get("CSF11", 40))
        cap_21 = int(caps_dict.get("CSF21", 50))
        cap_01 = int(caps_dict.get("CHS01", 35))

        aforo = min(capacidad_max, max(0, int(getattr(row, "vehiculos_presentes", 0) or 0)))
        v_11 = min(cap_11, max(0, int(getattr(row, "vehiculos_csf11", 0) or 0)))
        v_21 = min(cap_21, max(0, int(getattr(row, "vehiculos_csf21", 0) or 0)))
        v_01 = min(cap_01, max(0, int(getattr(row, "vehiculos_chs01", 0) or 0)))

        def _nivel_sector(pct_val: float) -> str:
            if pct_val >= 85.0:
                return "saturacion"
            if pct_val >= 70.0:
                return "preventivo"
            return "normal"

        disponibles = max(0, capacidad_max - aforo)
        pct = round(aforo / max(1, capacidad_max) * 100, 1)
        pct_11 = round(v_11 / max(1, cap_11) * 100, 1)
        pct_21 = round(v_21 / max(1, cap_21) * 100, 1)
        pct_01 = round(v_01 / max(1, cap_01) * 100, 1)

        max_ev_ts = getattr(row, "max_event_time", None)
        return {
            "vehiculos_presentes":   aforo,
            "plazas_disponibles":    disponibles,
            "capacidad_maxima":      capacidad_max,
            "ocupacion_pct":         pct,
            "nivel_alerta":          _nivel_sector(pct),
            "timestamp":             (max_ev_ts or datetime.combine(target_date, datetime.min.time())).isoformat(),
            "sector":                sector or "todos",
            "vehiculos_csf11":       v_11,
            "vehiculos_csf21":       v_21,
            "vehiculos_chs01":       v_01,
            "capacidad_csf11":       cap_11,
            "capacidad_csf21":       cap_21,
            "capacidad_chs01":       cap_01,
            "ocupacion_pct_csf11":   pct_11,
            "ocupacion_pct_csf21":   pct_21,
            "ocupacion_pct_chs01":   pct_01,
            "nivel_alerta_csf11":    _nivel_sector(pct_11),
            "nivel_alerta_csf21":    _nivel_sector(pct_21),
            "nivel_alerta_chs01":    _nivel_sector(pct_01),
        }

    # ------------------------------------------------------------------
    # Flujo y ocupación concurrente por fecha-hora (desduplicado y trazado entrada-salida)
    # ------------------------------------------------------------------
    @staticmethod
    async def get_hourly_flow(
        session: AsyncSession,
        fecha_inicio: Optional[date],
        fecha_fin: Optional[date],
        espacio_id: int = 2,
        alcance: str = "conformes",
        regimen_horario: Optional[str] = "todos",
        direccion: Optional[str] = "todos",
        dias_semana: Optional[str] = None,
        door: Optional[str] = None,
        sector: Optional[str] = None,
        tipo_vehiculo: Optional[str] = None,
    ) -> list[dict]:
        if fecha_inicio is None or fecha_fin is None:
            sql_max = text("""
                SELECT COALESCE(CAST(MAX(bucket) AS DATE), CAST(GETDATE() AS DATE))
                FROM aforo_horario_estacionamiento WITH (NOEXPAND)
                WHERE espacio_id = :espacio_id
            """)
            max_date = (await session.execute(sql_max, {"espacio_id": espacio_id})).scalar() or date.today()
            if fecha_fin is None:
                fecha_fin = max_date
            if fecha_inicio is None:
                fecha_inicio = max_date - timedelta(days=6)

        where_sql, params = await VehicleService._build_vehicle_filters(
            session=session,
            espacio_id=espacio_id,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            alcance=alcance,
            regimen_horario=regimen_horario,
            direccion=direccion,
            dias_semana=dias_semana,
            door=door,
            sector=sector,
            tipo_vehiculo=tipo_vehiculo,
        )

        capacidad_sector = 125
        if sector and sector != "todos":
            caps_validos = await _obtener_capacidades_sectores_vehiculares(session, espacio_id)
            sec_keys = _validar_sectores_vehiculares(sector, set(caps_validos.keys()))
            if sec_keys:
                cap_params: dict = {}
                sec_conds = _construir_filtro_codigo_sectores(sec_keys, cap_params, prefijo="hf_sec")
                try:
                    sql_sec_cap = text(f"SELECT COALESCE(SUM(capacidad_max), 0) FROM sectores_estacionamiento WHERE ({sec_conds}) AND activo = 1")
                    cap_sec = (await session.execute(sql_sec_cap, cap_params)).scalar()
                    if cap_sec and cap_sec > 0:
                        capacidad_sector = int(cap_sec)
                except Exception:
                    pass

        sql = text(f"""
            WITH ev_base AS (
                SELECT
                    time,
                    patente_hash,
                    direccion,
                    camara,
                    calidad_lectura,
                    LAG(time) OVER (
                        PARTITION BY patente_hash, direccion, CAST(time AS DATE)
                        ORDER BY time
                    ) AS prev_same_dir_time
                FROM eventos_vehiculares
                WHERE {where_sql}
                  AND time <= GETDATE()
            ),
            ev_dedup AS (
                SELECT
                    time,
                    patente_hash,
                    direccion,
                    camara,
                    calidad_lectura,
                    LEAD(direccion) OVER (
                        PARTITION BY patente_hash, CAST(time AS DATE)
                        ORDER BY time
                    ) AS next_dir,
                    LEAD(time) OVER (
                        PARTITION BY patente_hash, CAST(time AS DATE)
                        ORDER BY time
                    ) AS next_event_time
                FROM ev_base
                WHERE patente_hash = 'unknown'
                   OR prev_same_dir_time IS NULL
                   OR DATEDIFF(minute, prev_same_dir_time, time) > 15
            ),
            estancias AS (
                SELECT
                    CAST(time AS DATE) AS fecha_dia,
                    DATEADD(hour, DATEDIFF(hour, 0, time), 0) AS hora_ini,
                    DATEADD(hour, DATEDIFF(hour, 0,
                        CASE
                            WHEN patente_hash != 'unknown' AND next_dir = 'salida' AND next_event_time > time
                                THEN next_event_time
                            WHEN DATEADD(hour, 2, time) > GETDATE()
                                THEN GETDATE()
                            ELSE DATEADD(hour, 2, time)
                        END
                    ), 0) AS hora_fin
                FROM ev_dedup
                WHERE direccion = 'entrada'
            ),
            deltas_estancia AS (
                SELECT fecha_dia, hora_ini AS bucket, 1 AS delta FROM estancias
                UNION ALL
                SELECT
                    fecha_dia,
                    CASE WHEN hora_fin > hora_ini THEN hora_fin ELSE DATEADD(hour, 1, hora_ini) END AS bucket,
                    -1 AS delta
                FROM estancias
            ),
            deltas_por_hora AS (
                SELECT
                    fecha_dia,
                    bucket,
                    SUM(delta) AS delta_neto
                FROM deltas_estancia
                WHERE CAST(bucket AS DATE) = fecha_dia
                GROUP BY fecha_dia, bucket
            ),
            ocupacion_horaria AS (
                SELECT
                    bucket,
                    SUM(delta_neto) OVER (
                        PARTITION BY fecha_dia
                        ORDER BY bucket
                        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                    ) AS vehiculos_presentes
                FROM deltas_por_hora
            ),
            buckets AS (
                SELECT
                    DATEADD(hour, DATEDIFF(hour, 0, time), 0) AS bucket,
                    SUM(CASE WHEN direccion = 'entrada' THEN 1 ELSE 0 END) AS entradas,
                    SUM(CASE WHEN direccion = 'salida' THEN 1 ELSE 0 END) AS salidas,
                    SUM(CASE WHEN calidad_lectura = 'unknown' THEN 1 ELSE 0 END) AS lecturas_fallidas
                FROM ev_dedup
                GROUP BY DATEADD(hour, DATEDIFF(hour, 0, time), 0)
            )
            SELECT
                b.bucket,
                b.entradas,
                b.salidas,
                b.lecturas_fallidas,
                COALESCE(o.vehiculos_presentes, 0) AS vehiculos_presentes
            FROM buckets b
            LEFT JOIN ocupacion_horaria o ON b.bucket = o.bucket
            ORDER BY b.bucket ASC
        """)
        rows = (await session.execute(sql, params)).fetchall()

        return [
            {
                "bucket":              r.bucket.isoformat(),
                "entradas":            int(r.entradas),
                "salidas":             int(r.salidas),
                "lecturas_fallidas":   int(r.lecturas_fallidas),
                "vehiculos_presentes": min(capacidad_sector, max(0, int(r.vehiculos_presentes or 0))),
                "personas_unicas":     min(capacidad_sector, max(0, int(r.vehiculos_presentes or 0))),
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Curva de Presencia Vehicular por Intervalos de Sesión (Multi-Sector)
    # ------------------------------------------------------------------
    @staticmethod
    async def get_realtime_presence_curve(
        session: AsyncSession,
        fecha_inicio: Optional[date],
        fecha_fin: Optional[date],
        espacio_id: int = 2,
        alcance: str = "conformes",
        regimen_horario: Optional[str] = "todos",
        direccion: Optional[str] = "todos",
        dias_semana: Optional[str] = None,
        door: Optional[str] = None,
        sector: Optional[str] = None,
        tipo_vehiculo: Optional[str] = None,
    ) -> list[dict]:
        if fecha_inicio is None or fecha_fin is None:
            sql_max = text("""
                SELECT COALESCE(CAST(MAX(bucket) AS DATE), CAST(GETDATE() AS DATE))
                FROM aforo_horario_estacionamiento WITH (NOEXPAND)
                WHERE espacio_id = :espacio_id
            """)
            max_date = (await session.execute(sql_max, {"espacio_id": espacio_id})).scalar() or date.today()
            if fecha_fin is None:
                fecha_fin = max_date
            if fecha_inicio is None:
                fecha_inicio = max_date - timedelta(days=6)

        where_sql, params = await VehicleService._build_vehicle_filters(
            session=session,
            espacio_id=espacio_id,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            alcance=alcance,
            regimen_horario=regimen_horario,
            direccion="todos",
            dias_semana=dias_semana,
            door=door,
            sector=sector,
            tipo_vehiculo=tipo_vehiculo,
        )

        caps_dict = await _obtener_capacidades_sectores_vehiculares(session, espacio_id)
        if sector and sector != "todos":
            sec_keys = [s.strip().upper() for s in sector.split(",") if s.strip()]
            capacidad_total = sum(caps_dict.get(s, 0) for s in sec_keys) or caps_dict.get("todos", 125)
        else:
            capacidad_total = caps_dict.get("todos", 125)

        h24_rows = await obtener_horarios_operacion_cacheados(session, espacio_id)
        h24_conds = []
        for i, r_24 in enumerate(h24_rows):
            f_ini = getattr(r_24, "fecha_inicio", None)
            f_fin = getattr(r_24, "fecha_fin", None)
            if f_ini and f_fin:
                params[f"ch24_ini_{i}"] = f_ini.date() if isinstance(f_ini, datetime) else f_ini
                params[f"ch24_fin_{i}"] = f_fin.date() if isinstance(f_fin, datetime) else f_fin
                h24_conds.append(f"(e.fecha >= :ch24_ini_{i} AND e.fecha <= :ch24_fin_{i})")
        cond_h24_sql = " OR ".join(h24_conds) if h24_conds else "1=0"
        expr_cierre_sql = _construir_expr_cierre_vehicular_sql(cond_h24_sql)

        sql_sesiones = text(f"""
            WITH EventosConContexto AS (
                SELECT
                    patente_hash,
                    time,
                    CAST(time AS DATE) AS fecha,
                    CASE WHEN direccion = 'salida' THEN 1 ELSE 0 END AS es_salida,
                    CASE
                        WHEN camara LIKE '%CSF11%' THEN 1
                        WHEN camara LIKE '%CSF21%' THEN 2
                        WHEN camara LIKE '%CHS01%' THEN 3
                        ELSE 0
                    END AS sector_num,
                    LAG(CASE WHEN direccion = 'salida' THEN 1 ELSE 0 END)
                        OVER (PARTITION BY CAST(time AS DATE), patente_hash ORDER BY time) AS prev_es_salida,
                    LAG(time)
                        OVER (PARTITION BY CAST(time AS DATE), patente_hash ORDER BY time) AS prev_time,
                    LEAD(CASE WHEN direccion = 'salida' THEN 1 ELSE 0 END)
                        OVER (PARTITION BY CAST(time AS DATE), patente_hash ORDER BY time) AS raw_next_es_salida
                FROM eventos_vehiculares
                WHERE {where_sql}
                  AND time <= GETDATE()
                  AND patente_hash != 'unknown'
            ),
            EventosLimpios AS (
                SELECT
                    patente_hash,
                    time,
                    fecha,
                    es_salida,
                    sector_num,
                    LEAD(time) OVER (PARTITION BY fecha, patente_hash ORDER BY time) AS next_time
                FROM EventosConContexto
                WHERE (
                    prev_es_salida IS NULL
                    OR prev_es_salida <> es_salida
                    OR DATEDIFF(MINUTE, prev_time, time) > 15
                )
                AND NOT (
                    es_salida = 0
                    AND COALESCE(prev_es_salida, -1) = 1
                    AND DATEDIFF(SECOND, COALESCE(prev_time, time), time) <= 60
                    AND raw_next_es_salida IS NULL
                )
            )
            SELECT
                e.fecha,
                e.sector_num,
                e.time AS t_entrada,
                CASE
                    WHEN e.next_time IS NOT NULL THEN e.next_time
                    ELSE (
                        SELECT CASE
                            WHEN DATEADD(MINUTE, 120, e.time) > c_lim THEN c_lim
                            ELSE DATEADD(MINUTE, 120, e.time)
                        END
                        FROM (
                            SELECT CASE
                                WHEN ({expr_cierre_sql}) > GETDATE() THEN GETDATE()
                                ELSE ({expr_cierre_sql})
                            END AS c_lim
                        ) lim
                    )
                END AS t_salida
            FROM EventosLimpios e
            WHERE e.es_salida = 0
              AND e.time <= GETDATE()
        """)

        sql_flujo = text(f"""
            SELECT
                DATEADD(hour, DATEPART(hour, time), CAST(CAST(time AS DATE) AS DATETIME2)) AS bucket,
                CAST(time AS DATE) AS fecha,
                SUM(CASE WHEN direccion = 'entrada' THEN 1 ELSE 0 END) AS entradas,
                SUM(CASE WHEN direccion = 'salida' THEN 1 ELSE 0 END) AS salidas,
                SUM(CASE WHEN direccion = 'entrada' AND camara LIKE '%CSF11%' THEN 1 ELSE 0 END) AS entradas_csf11,
                SUM(CASE WHEN direccion = 'salida' AND camara LIKE '%CSF11%' THEN 1 ELSE 0 END) AS salidas_csf11,
                SUM(CASE WHEN direccion = 'entrada' AND camara LIKE '%CSF21%' THEN 1 ELSE 0 END) AS entradas_csf21,
                SUM(CASE WHEN direccion = 'salida' AND camara LIKE '%CSF21%' THEN 1 ELSE 0 END) AS salidas_csf21,
                SUM(CASE WHEN direccion = 'entrada' AND camara LIKE '%CHS01%' THEN 1 ELSE 0 END) AS entradas_chs01,
                SUM(CASE WHEN direccion = 'salida' AND camara LIKE '%CHS01%' THEN 1 ELSE 0 END) AS salidas_chs01
            FROM eventos_vehiculares
            WHERE {where_sql}
              AND time <= GETDATE()
            GROUP BY CAST(time AS DATE), DATEPART(hour, time)
            ORDER BY bucket ASC
        """)

        ses_rows = (await session.execute(sql_sesiones, params)).fetchall()
        flujo_rows = (await session.execute(sql_flujo, params)).fetchall()
        try:
            ahora_srv = (await session.execute(text("SELECT GETDATE()"))).scalar() or datetime.now()
        except Exception:
            ahora_srv = datetime.now()
        if isinstance(ahora_srv, date) and not isinstance(ahora_srv, datetime):
            ahora_srv = datetime.now()

        return _calcular_curva_presencia_vehicular_por_hora(
            sesiones_rows=ses_rows,
            flujo_rows=flujo_rows,
            ahora_servidor=ahora_srv,
            caps_sector=caps_dict,
            capacidad_total=capacidad_total,
        )

    # ------------------------------------------------------------------
    # Composición de flota (donut chart)
    # ------------------------------------------------------------------
    @staticmethod
    async def get_fleet_composition(
        session: AsyncSession,
        espacio_id: int = 2,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        sector: Optional[str] = None,
    ) -> dict:
        fin_exclusive = fecha_fin + timedelta(days=1) if fecha_fin else None
        params: dict = {"espacio_id": espacio_id, "inicio": fecha_inicio, "fin": fin_exclusive}
        where_sec = ""
        if sector and sector != "todos":
            caps_validos = await _obtener_capacidades_sectores_vehiculares(session, espacio_id)
            sec_keys = _validar_sectores_vehiculares(sector, set(caps_validos.keys()))
            where_sec = _construir_filtro_camara_sectores(sec_keys, params, prefijo="flota_sec")

        where_clauses = [
            "espacio_id = :espacio_id",
            "direccion = 'entrada'",
            "calidad_lectura = 'ok'",
        ]
        if params.get("inicio") is not None:
            where_clauses.append("time >= :inicio")
        if params.get("fin") is not None:
            where_clauses.append("time < :fin")
        where_flota = " AND ".join(where_clauses)

        sql_tipo = text(f"""
            SELECT
                COALESCE(tipo_vehiculo, 'Desconocido') AS tipo,
                COUNT(*)                                AS total,
                ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct
            FROM eventos_vehiculares
            WHERE {where_flota}
              {where_sec}
            GROUP BY tipo_vehiculo
            ORDER BY total DESC
        """)
        sql_marca = text(f"""
            SELECT TOP 10
                COALESCE(marca, 'Desconocida') AS marca,
                COUNT(*)                        AS total,
                ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct
            FROM eventos_vehiculares
            WHERE {where_flota}
              {where_sec}
            GROUP BY marca
            ORDER BY total DESC
        """)
        rows_tipo  = (await session.execute(sql_tipo,  params)).fetchall()
        rows_marca = (await session.execute(sql_marca, params)).fetchall()

        return {
            "por_tipo":  [{"tipo": r.tipo,   "total": int(r.total), "pct": float(r.pct)} for r in rows_tipo],
            "por_marca": [{"marca": r.marca, "total": int(r.total), "pct": float(r.pct)} for r in rows_marca],
        }

    @staticmethod
    async def get_daily_evolution(
        session: AsyncSession,
        espacio_id: int = 2,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        sector: Optional[str] = None,
    ) -> list[dict]:
        where_clauses = ["espacio_id = :espacio_id"]
        params: dict = {"espacio_id": espacio_id}
        if fecha_inicio:
            where_clauses.append("fecha_dia >= :inicio")
            params["inicio"] = fecha_inicio
        if fecha_fin:
            where_clauses.append("fecha_dia < :fin")
            params["fin"] = fecha_fin + timedelta(days=1)
        where_sec = ""
        if sector and sector != "todos":
            caps_validos = await _obtener_capacidades_sectores_vehiculares(session, espacio_id)
            sec_keys = _validar_sectores_vehiculares(sector, set(caps_validos.keys()))
            where_sec = _construir_filtro_camara_sectores(sec_keys, params, prefijo="evol_sec")

        where_evol = " AND ".join(where_clauses)
        sql = text(f"""
            SELECT 
                CAST(fecha_dia AS DATE) AS fecha,
                SUM(CASE WHEN direccion = 'entrada' THEN total_eventos ELSE 0 END) AS entradas,
                SUM(CASE WHEN direccion = 'salida' THEN total_eventos ELSE 0 END) AS salidas,
                SUM(total_eventos) AS vehiculos_unicos
            FROM dbo.vehiculos_diario_estacionamiento WITH (NOEXPAND)
            WHERE {where_evol}
              {where_sec}
            GROUP BY CAST(fecha_dia AS DATE)
            ORDER BY fecha ASC
        """)
        rows = (await session.execute(sql, params)).fetchall()
        return [
            {
                "fecha": r.fecha.isoformat(),
                "entradas": int(r.entradas),
                "salidas": int(r.salidas),
                "vehiculos_unicos": int(r.vehiculos_unicos),
            }
            for r in rows
        ]

    @staticmethod
    async def get_academic_milestones_comparison(session: AsyncSession, espacio_id: int = 2) -> list[dict]:
        sql = text("""
            WITH hourly AS (
                SELECT 
                    CAST(time AS DATE) AS dia,
                    DATEPART(hour, time) AS hora,
                    COUNT(DISTINCT patente_hash) AS aforo_hora
                FROM eventos_vehiculares
                WHERE espacio_id = :espacio_id AND direccion = 'entrada'
                GROUP BY CAST(time AS DATE), DATEPART(hour, time)
            ),
            daily_peak AS (
                SELECT 
                    dia, 
                    MAX(aforo_hora) AS pico_hora_dia
                FROM hourly
                GROUP BY dia
            ),
            vd AS (
                SELECT CAST(time AS DATE) AS dia, SUM(CASE WHEN direccion = 'entrada' THEN 1 ELSE 0 END) AS total_dia
                FROM eventos_vehiculares
                WHERE espacio_id = :espacio_id
                GROUP BY CAST(time AS DATE)
            )
            SELECT 
                CASE 
                    WHEN ca.is_exam_period = 1 THEN 'Exámenes / Certámenes'
                    WHEN ca.is_break = 1       THEN 'Receso Académico'
                    WHEN ca.is_holiday = 1     THEN 'Feriado'
                    ELSE 'Clases Regulares'
                END AS hito,
                COUNT(vd.dia) AS dias_totales,
                ROUND(AVG(vd.total_dia * 1.0), 1) AS promedio_diario,
                COALESCE(MAX(vd.total_dia), 0) AS max_dia,
                COALESCE(MAX(dp.pico_hora_dia), 0) AS aforo_pico_simultaneo,
                SUM(vd.total_dia) AS total_accesos
            FROM vd
            LEFT JOIN daily_peak dp ON vd.dia = dp.dia
            LEFT JOIN calendario_academico ca ON vd.dia = ca.fecha
            GROUP BY 
                CASE 
                    WHEN ca.is_exam_period = 1 THEN 'Exámenes / Certámenes'
                    WHEN ca.is_break = 1       THEN 'Receso Académico'
                    WHEN ca.is_holiday = 1     THEN 'Feriado'
                    ELSE 'Clases Regulares'
                END
            ORDER BY promedio_diario DESC
        """)
        rows = (await session.execute(sql, {"espacio_id": espacio_id})).fetchall()
        return [
            {
                "hito": r.hito,
                "dias_totales": int(r.dias_totales),
                "promedio_diario": float(r.promedio_diario or 0),
                "max_dia": int(r.max_dia or 0),
                "aforo_pico_simultaneo": int(getattr(r, "aforo_pico_simultaneo", 0) or 0),
                "total_accesos": int(r.total_accesos or 0),
            }
            for r in rows
        ]

    @staticmethod
    async def get_intercampus_mobility(
        session: AsyncSession,
        espacio_id: int = 2,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
    ) -> dict:
        if fecha_inicio is None or fecha_fin is None:
            sql_max = text("""
                SELECT COALESCE(CAST(MAX(bucket) AS DATE), CAST(GETDATE() AS DATE))
                FROM aforo_horario_estacionamiento WITH (NOEXPAND)
                WHERE espacio_id = :espacio_id
            """)
            max_date = (await session.execute(sql_max, {"espacio_id": espacio_id})).scalar() or date.today()
            if fecha_fin is None:
                fecha_fin = max_date
            if fecha_inicio is None:
                fecha_inicio = max_date - timedelta(days=365)

        inicio_dt = datetime.combine(fecha_inicio, datetime.min.time())
        fin_excl_dt = datetime.combine(fecha_fin + timedelta(days=1), datetime.min.time())

        sql_events = text("""
            WITH eventos_campus AS (
                SELECT
                    patente_hash,
                    CAST(time AS DATE) AS fecha,
                    time,
                    CASE WHEN camara LIKE 'CHS%' THEN 'CHS' ELSE 'CSF' END AS campus,
                    LEAD(time) OVER (PARTITION BY patente_hash ORDER BY time) AS next_time,
                    LEAD(CASE WHEN camara LIKE 'CHS%' THEN 'CHS' ELSE 'CSF' END) OVER (PARTITION BY patente_hash ORDER BY time) AS next_campus
                FROM eventos_vehiculares
                WHERE espacio_id = :espacio_id
                  AND patente_hash <> 'unknown'
                  AND (camara LIKE 'CSF%' OR camara LIKE 'CHS%')
                  AND time >= :inicio_dt
                  AND time < :fin_excl_dt
            ),
            traslados AS (
                SELECT
                    fecha,
                    campus AS origen,
                    next_campus AS destino,
                    time AS salida_origen,
                    DATEDIFF(minute, time, next_time) AS minutos_traslado,
                    DATEPART(hour, time) AS hora_salida
                FROM eventos_campus
                WHERE next_campus IS NOT NULL
                  AND campus <> next_campus
                  AND CAST(next_time AS DATE) = fecha
                  AND next_time > time
                  AND next_time <= DATEADD(hour, 6, time)
            )
            SELECT
                fecha,
                origen,
                destino,
                minutos_traslado,
                hora_salida
            FROM traslados
            ORDER BY fecha ASC, salida_origen ASC
        """)
        rows = (
            await session.execute(
                sql_events,
                {"espacio_id": espacio_id, "inicio_dt": inicio_dt, "fin_excl_dt": fin_excl_dt},
            )
        ).fetchall()

        total_traslados = len(rows)
        if total_traslados == 0:
            return {
                "total_viajes": 0,
                "csf_a_chs": 0,
                "chs_a_csf": 0,
                "tiempo_promedio_min": 0,
                "tiempo_mediano_min": 0,
                "franja_punta": "N/A",
                "flujo_por_fecha": [],
                "distribucion_horaria": []
            }

        csf_a_chs = sum(1 for r in rows if r.origen == 'CSF' and r.destino == 'CHS')
        chs_a_csf = sum(1 for r in rows if r.origen == 'CHS' and r.destino == 'CSF')
        tiempos = [float(r.minutos_traslado) for r in rows]
        tiempo_promedio = round(sum(tiempos) / len(tiempos), 1)
        tiempos_sorted = sorted(tiempos)
        tiempo_mediano = round(tiempos_sorted[len(tiempos_sorted) // 2], 1)

        horas_count = {}
        for r in rows:
            horas_count[r.hora_salida] = horas_count.get(r.hora_salida, 0) + 1
        hora_punta = max(horas_count.items(), key=lambda x: x[1])[0] if horas_count else 12

        fechas_dict = {}
        for r in rows:
            f_str = r.fecha.isoformat()
            if f_str not in fechas_dict:
                fechas_dict[f_str] = {"fecha": f_str, "csf_a_chs": 0, "chs_a_csf": 0, "total": 0}
            if r.origen == 'CSF':
                fechas_dict[f_str]["csf_a_chs"] += 1
            else:
                fechas_dict[f_str]["chs_a_csf"] += 1
            fechas_dict[f_str]["total"] += 1

        dist_horaria = [
            {"hora": f"{h:02d}:00", "viajes": horas_count.get(h, 0)}
            for h in range(7, 21)
        ]

        return {
            "total_viajes": total_traslados,
            "csf_a_chs": csf_a_chs,
            "chs_a_csf": chs_a_csf,
            "tiempo_promedio_min": tiempo_promedio,
            "tiempo_mediano_min": tiempo_mediano,
            "franja_punta": f"{hora_punta:02d}:00 hrs",
            "flujo_por_fecha": list(fechas_dict.values()),
            "distribucion_horaria": dist_horaria
        }

    @staticmethod
    async def get_behavioral_clusters(session: AsyncSession) -> dict:
        from app.ml.train_kmeans_parking import compute_behavioral_clusters
        return await compute_behavioral_clusters(session)

    @staticmethod
    async def get_raw_vehicle_data_for_anomalies(session: AsyncSession, espacio_id: int, dias: int = 30):
        import pandas as pd
        sql = text("""
            WITH ref_date AS (
                SELECT COALESCE(MAX(time), GETDATE()) as max_t
                FROM eventos_vehiculares
                WHERE espacio_id = :espacio_id
            ),
            entradas AS (
                SELECT 
                    patente_hash,
                    CAST(time AS DATE) as fecha,
                    DATEPART(hour, MIN(time)) as hora_ingreso,
                    MIN(time) as tiempo_ingreso
                FROM eventos_vehiculares, ref_date
                WHERE espacio_id = :espacio_id
                  AND direccion = 'entrada'
                  AND patente_hash != 'unknown'
                  AND time >= DATEADD(day, -:dias, ref_date.max_t)
                GROUP BY patente_hash, CAST(time AS DATE)
            ),
            salidas AS (
                SELECT 
                    patente_hash,
                    CAST(time AS DATE) as fecha,
                    MAX(time) as tiempo_salida
                FROM eventos_vehiculares, ref_date
                WHERE espacio_id = :espacio_id
                  AND direccion = 'salida'
                  AND patente_hash != 'unknown'
                  AND time >= DATEADD(day, -:dias, ref_date.max_t)
                GROUP BY patente_hash, CAST(time AS DATE)
            ),
            visitas AS (
                SELECT 
                    e.patente_hash,
                    e.fecha,
                    e.hora_ingreso,
                    DATEDIFF(minute, e.tiempo_ingreso, s.tiempo_salida) as permanencia
                FROM entradas e
                JOIN salidas s ON e.patente_hash = s.patente_hash AND e.fecha = s.fecha
                WHERE s.tiempo_salida > e.tiempo_ingreso
            )
            SELECT 
                patente_hash,
                AVG(hora_ingreso * 1.0) as hora_ingreso,
                AVG(permanencia * 1.0) as permanencia,
                COUNT(DISTINCT fecha) as frecuencia
            FROM visitas
            GROUP BY patente_hash
        """)
        result = await session.execute(sql, {"espacio_id": espacio_id, "dias": dias})
        rows = result.fetchall()
        if not rows:
            return pd.DataFrame(columns=["patente_hash", "hora_ingreso", "permanencia", "frecuencia"])
        return pd.DataFrame([dict(r._mapping) for r in rows])

    @staticmethod
    async def get_stay_distribution(
        session: AsyncSession,
        espacio_id: int = 2,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
    ) -> list[dict]:
        if fecha_inicio is None or fecha_fin is None:
            sql_max = text("""
                SELECT COALESCE(CAST(MAX(bucket) AS DATE), CAST(GETDATE() AS DATE))
                FROM aforo_horario_estacionamiento WITH (NOEXPAND)
                WHERE espacio_id = :espacio_id
            """)
            max_date = (await session.execute(sql_max, {"espacio_id": espacio_id})).scalar() or date.today()
            if fecha_fin is None:
                fecha_fin = max_date
            if fecha_inicio is None:
                fecha_inicio = max_date - timedelta(days=365)

        inicio_dt = datetime.combine(fecha_inicio, datetime.min.time())
        fin_excl_dt = datetime.combine(fecha_fin + timedelta(days=1), datetime.min.time())

        sql = text("""
            WITH seq AS (
                SELECT
                    patente_hash,
                    time AS t_actual,
                    direccion AS dir_actual,
                    LEAD(time) OVER (PARTITION BY patente_hash ORDER BY time) AS t_sig,
                    LEAD(direccion) OVER (PARTITION BY patente_hash ORDER BY time) AS dir_sig
                FROM eventos_vehiculares
                WHERE espacio_id = :espacio_id
                  AND patente_hash <> 'unknown'
                  AND time >= :inicio_dt
                  AND time < :fin_excl_dt
            ),
            estadias AS (
                SELECT DATEDIFF(minute, t_actual, t_sig) AS mins
                FROM seq
                WHERE dir_actual = 'entrada'
                  AND dir_sig = 'salida'
                  AND t_sig > t_actual
                  AND t_sig < DATEADD(hour, 24, t_actual)
            )
            SELECT
                CASE
                    WHEN mins < 15  THEN 'drop_off'
                    WHEN mins < 180 THEN '0-3h'
                    WHEN mins < 360 THEN '3-6h'
                    ELSE 'jornada_completa'
                END AS rango,
                COUNT(*) AS total
            FROM estadias
            GROUP BY
                CASE
                    WHEN mins < 15  THEN 'drop_off'
                    WHEN mins < 180 THEN '0-3h'
                    WHEN mins < 360 THEN '3-6h'
                    ELSE 'jornada_completa'
                END
            ORDER BY total DESC
        """)
        rows = (
            await session.execute(
                sql,
                {"espacio_id": espacio_id, "inicio_dt": inicio_dt, "fin_excl_dt": fin_excl_dt},
            )
        ).fetchall()
        return [{"rango": r.rango, "total": int(r.total)} for r in rows]

    @staticmethod
    async def get_camera_stats(
        session: AsyncSession,
        espacio_id: int = 2,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        alcance: Optional[str] = "conformes",
        regimen_horario: Optional[str] = "todos",
        direccion: Optional[str] = "todos",
        dias_semana: Optional[str] = None,
        door: Optional[str] = None,
        sector: Optional[str] = None,
        tipo_vehiculo: Optional[str] = None,
    ) -> list[dict]:
        where_sql, params = await VehicleService._build_vehicle_filters(
            session=session,
            espacio_id=espacio_id,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            alcance=alcance,
            regimen_horario=regimen_horario,
            direccion=direccion,
            dias_semana=dias_semana,
            door=door,
            sector=sector,
            tipo_vehiculo=tipo_vehiculo,
        )
        sql = text(f"""
            WITH ev_base AS (
                SELECT
                    time,
                    patente_hash,
                    direccion,
                    camara,
                    calidad_lectura,
                    LAG(time) OVER (
                        PARTITION BY patente_hash, direccion, CAST(time AS DATE)
                        ORDER BY time
                    ) AS prev_same_dir_time
                FROM eventos_vehiculares
                WHERE {where_sql}
                  AND time <= GETDATE()
            ),
            ev_dedup AS (
                SELECT
                    camara,
                    direccion,
                    calidad_lectura
                FROM ev_base
                WHERE patente_hash = 'unknown'
                   OR prev_same_dir_time IS NULL
                   OR DATEDIFF(minute, prev_same_dir_time, time) > 15
            )
            SELECT
                camara,
                SUM(CASE WHEN direccion = 'entrada' THEN 1 ELSE 0 END) AS entradas,
                SUM(CASE WHEN direccion = 'salida' THEN 1 ELSE 0 END)  AS salidas,
                SUM(CASE WHEN calidad_lectura = 'unknown' THEN 1 ELSE 0 END) AS lecturas_fallidas
            FROM ev_dedup
            GROUP BY camara
            ORDER BY (SUM(CASE WHEN direccion = 'entrada' THEN 1 ELSE 0 END) + SUM(CASE WHEN direccion = 'salida' THEN 1 ELSE 0 END)) DESC
        """)
        rows = (await session.execute(sql, params)).fetchall()
        return [
            {
                "camara":            r.camara,
                "entradas":          int(r.entradas),
                "salidas":           int(r.salidas),
                "lecturas_fallidas": int(r.lecturas_fallidas),
            }
            for r in rows
        ]

    @staticmethod
    async def get_raw_events(
        session: AsyncSession,
        espacio_id: int = 2,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        camara: Optional[str] = None,
        direccion: Optional[str] = None,
        tipo_vehiculo: Optional[str] = None,
        search_hash: Optional[str] = None,
        categoria: Optional[str] = None,
        alcance: Optional[str] = "todos",
        regimen_horario: Optional[str] = "todos",
        dias_semana: Optional[str] = None,
        door: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        from app.services.config_service import get_horarios_operacion, es_horario_conforme

        where_sql, params = await VehicleService._build_vehicle_filters(
            session=session,
            espacio_id=espacio_id,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            alcance=alcance,
            regimen_horario=regimen_horario,
            direccion=direccion or "todos",
            dias_semana=dias_semana,
            door=camara or door,
        )

        conditions = [where_sql]

        if tipo_vehiculo:
            conditions.append("tipo_vehiculo LIKE :tipo_vehiculo")
            params["tipo_vehiculo"] = f"%{tipo_vehiculo}%"

        if search_hash:
            conditions.append("patente_hash LIKE :search_hash")
            params["search_hash"] = f"%{search_hash}%"

        if categoria:
            cat_lower = categoria.lower()
            if cat_lower in ("lectura_fallida", "lectura_ilegible"):
                conditions.append("calidad_lectura = 'unknown'")
            elif cat_lower == "fuera_de_horario":
                conditions.append("""(
                    ((DATEPART(WEEKDAY, time) + @@DATEFIRST - 2) % 7 + 1) = 7
                    OR (((DATEPART(WEEKDAY, time) + @@DATEFIRST - 2) % 7 + 1) BETWEEN 1 AND 5 AND (CAST(time AS TIME) < '07:00:00' OR CAST(time AS TIME) > '22:00:00'))
                    OR (((DATEPART(WEEKDAY, time) + @@DATEFIRST - 2) % 7 + 1) = 6 AND (CAST(time AS TIME) < '08:00:00' OR CAST(time AS TIME) > '14:00:00'))
                )""")
            elif cat_lower == "conforme":
                conditions.append("""(
                    calidad_lectura != 'unknown'
                    AND (
                        (((DATEPART(WEEKDAY, time) + @@DATEFIRST - 2) % 7 + 1) BETWEEN 1 AND 5 AND CAST(time AS TIME) >= '07:00:00' AND CAST(time AS TIME) <= '22:00:00')
                        OR (((DATEPART(WEEKDAY, time) + @@DATEFIRST - 2) % 7 + 1) = 6 AND CAST(time AS TIME) >= '08:00:00' AND CAST(time AS TIME) <= '14:00:00')
                    )
                )""")

        where_clause = " AND ".join(conditions)
        count_sql = text(f"SELECT COUNT(*) FROM eventos_vehiculares WHERE {where_clause}")
        total = int((await session.execute(count_sql, params)).scalar() or 0)

        offset = (max(1, page) - 1) * page_size
        params["offset"] = offset
        params["limit"] = page_size

        data_sql = text(f"""
            SELECT 
                time,
                patente_hash,
                camara,
                direccion,
                tipo_vehiculo,
                marca,
                color,
                calidad_lectura
            FROM eventos_vehiculares
            WHERE {where_clause}
            ORDER BY time DESC
            OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY
        """)
        rows = (await session.execute(data_sql, params)).fetchall()
        horarios = await get_horarios_operacion(session, espacio_id=espacio_id)

        items = []
        for r in rows:
            categorias_row = []
            if r.time and not es_horario_conforme(r.time, horarios):
                categorias_row.append("Fuera de Horario")
            if r.calidad_lectura == "unknown":
                categorias_row.append("Lectura Ilegible")

            if not categorias_row:
                categorias_row = ["Conforme"]
                nivel = "conforme"
            elif len(categorias_row) >= 2:
                nivel = "critico"
            else:
                nivel = "observado"

            items.append({
                "time": r.time.isoformat() if r.time else "",
                "patente_hash": r.patente_hash,
                "patente_short": "DESCONOCIDO" if r.patente_hash == "unknown" else f"PAT-{r.patente_hash[:8]}",
                "camara": r.camara,
                "direccion": r.direccion,
                "tipo_vehiculo": r.tipo_vehiculo or "Desconocido",
                "marca": r.marca or "Desconocida",
                "color": r.color or "—",
                "calidad_lectura": r.calidad_lectura,
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
        espacio_id: int = 2,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        camara: Optional[str] = None,
        direccion: Optional[str] = None,
        tipo_vehiculo: Optional[str] = None,
        search_hash: Optional[str] = None,
        categoria: Optional[str] = None,
        alcance: Optional[str] = "todos",
        regimen_horario: Optional[str] = "todos",
        dias_semana: Optional[str] = None,
        door: Optional[str] = None,
        limit: int = 100000,
    ) -> tuple[str, int]:
        import csv
        import io
        from app.services.config_service import get_horarios_operacion, es_horario_conforme

        where_sql, params = await VehicleService._build_vehicle_filters(
            session=session,
            espacio_id=espacio_id,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            alcance=alcance,
            regimen_horario=regimen_horario,
            direccion=direccion or "todos",
            dias_semana=dias_semana,
            door=camara or door,
        )
        params["limit"] = limit

        conditions = [where_sql]
        if tipo_vehiculo:
            conditions.append("tipo_vehiculo LIKE :tipo_vehiculo")
            params["tipo_vehiculo"] = f"%{tipo_vehiculo}%"
        if search_hash:
            conditions.append("patente_hash LIKE :search_hash")
            params["search_hash"] = f"%{search_hash}%"

        where_clause = " AND ".join(conditions)
        data_sql = text(f"""
            SELECT TOP (:limit)
                time,
                patente_hash,
                camara,
                direccion,
                tipo_vehiculo,
                marca,
                color,
                calidad_lectura
            FROM eventos_vehiculares
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
                "Patente_Seudonimizada",
                "Camara_ANPR",
                "Direccion",
                "Tipo_Vehiculo",
                "Marca",
                "Color",
                "Calidad_Lectura",
                "Categorias_Calidad",
                "Nivel_Integridad",
            ])

            for r in rows:
                categorias_row = []
                if r.time and not es_horario_conforme(r.time, horarios):
                    categorias_row.append("Fuera de Horario")
                if r.calidad_lectura == "unknown":
                    categorias_row.append("Lectura Ilegible")

                if not categorias_row:
                    categorias_row = ["Conforme"]
                    nivel = "Conforme"
                elif len(categorias_row) >= 2:
                    nivel = "Critico"
                else:
                    nivel = "Observado"

                from app.services.csv_utils import sanitizar_celda_csv

                writer.writerow([
                    r.time.strftime("%Y-%m-%d") if r.time else "",
                    r.time.strftime("%H:%M:%S") if r.time else "",
                    sanitizar_celda_csv("DESCONOCIDO" if r.patente_hash == "unknown" else f"PAT-{r.patente_hash[:8]}"),
                    sanitizar_celda_csv(r.camara or ""),
                    sanitizar_celda_csv(r.direccion or ""),
                    sanitizar_celda_csv(r.tipo_vehiculo or "Desconocido"),
                    sanitizar_celda_csv(r.marca or "Desconocida"),
                    sanitizar_celda_csv(r.color or "—"),
                    sanitizar_celda_csv(r.calidad_lectura or ""),
                    sanitizar_celda_csv(" | ".join(categorias_row)),
                    nivel,
                ])

            return output.getvalue(), len(rows)

    @staticmethod
    async def stream_raw_csv(
        espacio_id: int = 2,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        camara: Optional[str] = None,
        direccion: Optional[str] = None,
        tipo_vehiculo: Optional[str] = None,
        search_hash: Optional[str] = None,
        categoria: Optional[str] = None,
        alcance: Optional[str] = "todos",
        regimen_horario: Optional[str] = "todos",
        dias_semana: Optional[str] = None,
        door: Optional[str] = None,
        limit: int = 100000,
        conteo_ref: Optional[list[int]] = None,
    ):
        """Genera el CSV vehicular por lotes para StreamingResponse sin acumular 100k filas en RAM."""
        import csv
        import io
        from app.core.database import AsyncSessionLocal
        from app.services.config_service import get_horarios_operacion, es_horario_conforme

        async with AsyncSessionLocal() as s_stream:
            where_sql, params = await VehicleService._build_vehicle_filters(
                session=s_stream,
                espacio_id=espacio_id,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                alcance=alcance,
                regimen_horario=regimen_horario,
                direccion=direccion or "todos",
                dias_semana=dias_semana,
                door=camara or door,
            )
            params["limit"] = limit

            conditions = [where_sql]
            if tipo_vehiculo:
                conditions.append("tipo_vehiculo LIKE :tipo_vehiculo")
                params["tipo_vehiculo"] = f"%{tipo_vehiculo}%"
            if search_hash:
                conditions.append("patente_hash LIKE :search_hash")
                params["search_hash"] = f"%{search_hash}%"

            where_clause = " AND ".join(conditions)
            data_sql = text(f"""
                SELECT TOP (:limit)
                    time, patente_hash, camara, direccion,
                    tipo_vehiculo, marca, color, calidad_lectura
                FROM eventos_vehiculares
                WHERE {where_clause}
                ORDER BY time DESC
            """)
            horarios = await get_horarios_operacion(s_stream, espacio_id=espacio_id)

            with io.StringIO() as buf:
                writer = csv.writer(buf)
                writer.writerow([
                    "Fecha", "Hora", "Patente_Seudonimizada", "Camara_ANPR", "Direccion",
                    "Tipo_Vehiculo", "Marca", "Color", "Calidad_Lectura", "Categorias_Calidad", "Nivel_Integridad",
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
                        if r.time and not es_horario_conforme(r.time, horarios):
                            categorias_row.append("Fuera de Horario")
                        if r.calidad_lectura == "unknown":
                            categorias_row.append("Lectura Ilegible")

                        if not categorias_row:
                            categorias_row = ["Conforme"]
                            nivel = "Conforme"
                        elif len(categorias_row) >= 2:
                            nivel = "Critico"
                        else:
                            nivel = "Observado"

                        from app.services.csv_utils import sanitizar_celda_csv

                        writer.writerow([
                            r.time.strftime("%Y-%m-%d") if r.time else "",
                            r.time.strftime("%H:%M:%S") if r.time else "",
                            sanitizar_celda_csv("DESCONOCIDO" if r.patente_hash == "unknown" else f"PAT-{r.patente_hash[:8]}"),
                            sanitizar_celda_csv(r.camara or ""),
                            sanitizar_celda_csv(r.direccion or ""),
                            sanitizar_celda_csv(r.tipo_vehiculo or "Desconocido"),
                            sanitizar_celda_csv(r.marca or "Desconocida"),
                            sanitizar_celda_csv(r.color or "—"),
                            sanitizar_celda_csv(r.calidad_lectura or ""),
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
    async def bulk_insert_events(
        db: AsyncSession,
        dtos: list,
        modo_solapamiento: str = "merge",
        espacio_id: Optional[int] = None,
        fecha_min: Optional[datetime] = None,
        fecha_max: Optional[datetime] = None,
    ) -> dict:
        """
        Inserta eventos vehiculares con soporte atómico para 'merge' o 'overwrite'.
        """
        from app.domain.models import EventoVehicular
        from sqlalchemy import select, delete

        if not dtos:
            return {"insertados": 0, "eliminados": 0, "total_procesados": 0}

        registros_eliminados = 0
        target_espacio_id = espacio_id or dtos[0].espacio_id

        if modo_solapamiento == "overwrite":
            min_ts = fecha_min or min(d.time for d in dtos)
            max_ts = fecha_max or max(d.time for d in dtos)
            stmt_del = (
                delete(EventoVehicular)
                .where(
                    EventoVehicular.espacio_id == target_espacio_id,
                    EventoVehicular.time >= min_ts,
                    EventoVehicular.time <= max_ts,
                )
            )
            res_del = await db.execute(stmt_del)
            registros_eliminados = res_del.rowcount or 0

        existing_keys = set()
        if modo_solapamiento == "merge":
            min_ts = fecha_min or min(d.time for d in dtos)
            max_ts = (fecha_max or max(d.time for d in dtos)) + timedelta(seconds=60)
            stmt_keys = (
                select(
                    EventoVehicular.time,
                    EventoVehicular.espacio_id,
                    EventoVehicular.patente_hash,
                    EventoVehicular.camara,
                )
                .where(
                    EventoVehicular.espacio_id == target_espacio_id,
                    EventoVehicular.time >= min_ts,
                    EventoVehicular.time <= max_ts,
                )
            )
            res_keys = await db.execute(stmt_keys)
            existing_keys = {(r[0], r[1], r[2], r[3]) for r in res_keys.fetchall()}

        seen_keys = set()
        a_insertar = []
        for dto in dtos:
            key = (dto.time, dto.espacio_id, dto.patente_hash, dto.camara)
            if modo_solapamiento == "merge" and key in existing_keys:
                continue

            if key in seen_keys:
                offset = 1
                cand_time = dto.time + timedelta(seconds=offset)
                cand_key = (cand_time, dto.espacio_id, dto.patente_hash, dto.camara)
                while (cand_key in seen_keys or (modo_solapamiento == "merge" and cand_key in existing_keys)) and offset < 59:
                    offset += 1
                    cand_time = dto.time + timedelta(seconds=offset)
                    cand_key = (cand_time, dto.espacio_id, dto.patente_hash, dto.camara)

                if cand_key not in seen_keys and (modo_solapamiento != "merge" or cand_key not in existing_keys):
                    dto.time = cand_time
                    key = cand_key
                else:
                    continue

            seen_keys.add(key)
            if modo_solapamiento == "merge":
                existing_keys.add(key)

            item_dict = {
                "time": dto.time,
                "espacio_id": dto.espacio_id,
                "patente_hash": dto.patente_hash,
                "patente_cifrada": getattr(dto, "patente_cifrada", None),
                "camara": dto.camara,
                "direccion": dto.direccion,
                "tipo_vehiculo": dto.tipo_vehiculo,
                "marca": dto.marca,
                "color": dto.color,
                "calidad_lectura": dto.calidad_lectura,
            }
            a_insertar.append(item_dict)

        stmt_insert = text("""
        INSERT INTO eventos_vehiculares (
            time, espacio_id, patente_hash, patente_cifrada, camara,
            direccion, tipo_vehiculo, marca, color, calidad_lectura
        ) VALUES (
            :time, :espacio_id, :patente_hash, :patente_cifrada, :camara,
            :direccion, :tipo_vehiculo, :marca, :color, :calidad_lectura
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
    async def get_latest_year(session: AsyncSession, espacio_id: int = 2) -> int:
        """Obtiene el año más reciente registrado en aforo_horario_estacionamiento."""
        try:
            sql = text("SELECT YEAR(MAX(bucket)) FROM aforo_horario_estacionamiento WITH (NOEXPAND) WHERE espacio_id = :espacio_id")
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
        espacio_id: int = 2,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
    ) -> list[dict]:
        """Obtiene el resumen diario de aforo vehicular agrupado por fecha."""
        params: dict = {"espacio_id": espacio_id}
        where_conds = ["espacio_id = :espacio_id"]
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
                   SUM(entradas) as ingresos,
                   SUM(salidas) as salidas
            FROM aforo_horario_estacionamiento WITH (NOEXPAND)
            WHERE {where_clause}
            GROUP BY CAST(bucket AS DATE), DATENAME(weekday, CAST(bucket AS DATE))
            ORDER BY fecha ASC
        """)
        res = await session.execute(sql, params)
        return [dict(r._mapping) for r in res.all()]

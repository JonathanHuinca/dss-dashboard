"""
VehicleService — Consultas sobre Continuous Aggregates y tablas de estacionamiento en SQL Server.
"""
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import TTLCache

CAPACIDAD_ESTACIONAMIENTO = 180
UMBRAL_ALERTA_90 = 0.90

# Caché en memoria para reutilizar horarios de operación vehiculares
cache_horarios_espacio: TTLCache = TTLCache(maxsize=32, ttl=300)


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


def invalidar_cache_horarios(espacio_id: Optional[int] = None) -> None:
    if espacio_id is not None:
        cache_horarios_espacio.pop(f"horarios_24h:{espacio_id}", None)
    else:
        cache_horarios_espacio.clear()


invalidar_cache_horarios_vehiculos = invalidar_cache_horarios


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

        closure_sql = """EXISTS (
            SELECT 1 FROM calendario_academico ca 
            WHERE ca.fecha = CAST(time AS DATE) 
              AND ca.is_holiday = 1
        )"""

        strike_fed_sql = """EXISTS (
            SELECT 1 FROM calendario_academico ca 
            WHERE ca.fecha = CAST(time AS DATE) 
              AND ca.is_strike_federado = 1
        )"""

        strike_car_sql = """EXISTS (
            SELECT 1 FROM calendario_academico ca 
            WHERE ca.fecha = CAST(time AS DATE) 
              AND ca.is_strike_carrera = 1
        )"""

        regular_open_sql = """(
            (DATEPART(WEEKDAY, time) BETWEEN 2 AND 6 AND CAST(time AS TIME) >= '07:00:00' AND CAST(time AS TIME) <= '22:00:00')
            OR (DATEPART(WEEKDAY, time) = 7 AND CAST(time AS TIME) >= '08:00:00' AND CAST(time AS TIME) <= '14:00:00')
        )"""

        f_oficial_sql = f"({regular_open_sql} AND NOT ({closure_sql}))"

        regular_closed_sql = """(
            DATEPART(WEEKDAY, time) = 1
            OR (DATEPART(WEEKDAY, time) BETWEEN 2 AND 6 AND (CAST(time AS TIME) < '07:00:00' OR CAST(time AS TIME) > '22:00:00'))
            OR (DATEPART(WEEKDAY, time) = 7 AND (CAST(time AS TIME) < '08:00:00' OR CAST(time AS TIME) > '14:00:00'))
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
                        sql_h = text("SELECT fecha_inicio, fecha_fin, hora_apertura, hora_cierre, es_continuo_24h FROM horarios_operacion WHERE id = :h_id")
                        h_row = (await session.execute(sql_h, {"h_id": h_id})).first()
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

        # 4. Días de la semana
        if dias_semana:
            dias_map = {
                "domingo": 1,
                "lunes": 2,
                "martes": 3,
                "miercoles": 4,
                "miércoles": 4,
                "jueves": 5,
                "viernes": 6,
                "sabado": 7,
                "sábado": 7,
            }
            dias_solicitados = [d.strip().lower() for d in dias_semana.split(",") if d.strip().lower() in dias_map]
            if dias_solicitados:
                weekday_ints = [str(dias_map[d]) for d in dias_solicitados]
                conditions.append(f"DATEPART(WEEKDAY, time) IN ({','.join(weekday_ints)})")

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
            sectores_list = [s.strip().upper() for s in sector.split(",") if s.strip()]
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
            ),
            ev_dedup AS (
                SELECT
                    time,
                    patente_hash,
                    direccion,
                    camara,
                    calidad_lectura
                FROM ev_base
                WHERE patente_hash = 'unknown'
                   OR prev_same_dir_time IS NULL
                   OR DATEDIFF(minute, prev_same_dir_time, time) > 15
            )
            SELECT
                COUNT(DISTINCT patente_hash)                                   AS vehiculos_unicos,
                SUM(CASE WHEN direccion = 'entrada' THEN 1 ELSE 0 END)         AS total_entradas,
                SUM(CASE WHEN direccion = 'salida' THEN 1 ELSE 0 END)          AS total_salidas,
                COUNT(DISTINCT CAST(time AS DATE))                             AS dias_operativos,
                ROUND(
                    100.0 * SUM(CASE WHEN calidad_lectura = 'unknown' THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(*), 0),
                2)                                                             AS tasa_lectura_fallida_pct
            FROM ev_dedup
        """)
        row_g = (await session.execute(sql_global, params)).one()

        dias = row_g.dias_operativos or 1
        entradas = row_g.total_entradas or 0
        salidas = row_g.total_salidas or 0

        # Calibración dinámica de capacidad según sector
        capacidad_max = 125
        if sector and sector != "todos":
            sec_keys = [s.strip().upper() for s in sector.split(",") if s.strip()]
            sec_conds = " OR ".join([f"codigo = '{c}'" for c in sec_keys])
            try:
                sql_sec_cap = text(f"SELECT COALESCE(SUM(capacidad_max), 0) FROM sectores_estacionamiento WHERE ({sec_conds}) AND activo = 1")
                cap_sec = (await session.execute(sql_sec_cap)).scalar()
                if cap_sec and cap_sec > 0:
                    capacidad_max = int(cap_sec)
            except Exception:
                pass
        else:
            from app.domain.models import Espacio
            espacio_obj = (await session.execute(select(Espacio.capacidad_max).where(Espacio.id == espacio_id))).scalar_one_or_none()
            capacidad_max = espacio_obj or 125

        turnover = round(entradas / dias / max(1, capacidad_max), 2)

        sql_perm = text("""
            SELECT TOP 1
                ROUND(
                    PERCENTILE_CONT(0.5) WITHIN GROUP (
                        ORDER BY DATEDIFF(second, ent.time, sal.time) / 60.0
                    ) OVER (), 2
                ) AS permanencia_mediana_min
            FROM eventos_vehiculares ent
            JOIN eventos_vehiculares sal
              ON ent.patente_hash = sal.patente_hash
             AND ent.espacio_id   = sal.espacio_id
             AND sal.time > ent.time
             AND sal.time < DATEADD(hour, 24, ent.time)
             AND ent.direccion = 'entrada'
             AND sal.direccion = 'salida'
            WHERE ent.espacio_id = :espacio_id
              AND (:inicio IS NULL OR ent.time >= :inicio)
              AND (:fin IS NULL OR ent.time < :fin)
        """)
        fin_exclusive = fecha_fin + timedelta(days=1) if fecha_fin else None
        params_perm = {**params, "inicio": fecha_inicio, "fin": fin_exclusive}
        row_p = (await session.execute(sql_perm, params_perm)).first()
        mediana_min = float(row_p.permanencia_mediana_min) if row_p and row_p.permanencia_mediana_min is not None else 0.0

        sql_peak = text(f"""
            SELECT TOP 1 DATEPART(hour, time) AS hora, COUNT(*) AS total
            FROM eventos_vehiculares
            WHERE {where_sql}
            GROUP BY DATEPART(hour, time)
            ORDER BY total DESC
        """)
        row_peak = (await session.execute(sql_peak, params)).first()
        hora_punta = f"{row_peak.hora:02d}:00 hrs" if row_peak and row_peak.hora is not None else "08:00 hrs"

        sql_max = text(f"""
            SELECT COALESCE(MAX(cnt), 0)
            FROM (
                SELECT COUNT(*) as cnt
                FROM eventos_vehiculares
                WHERE {where_sql}
                GROUP BY DATEADD(hour, DATEDIFF(hour, 0, time), 0)
            ) sub
        """)
        max_entradas = (await session.execute(sql_max, params)).scalar() or 0

        return {
            "vehiculos_unicos":          int(row_g.vehiculos_unicos or 0),
            "total_accesos":             int(entradas),
            "total_salidas":             int(salidas),
            "dias_operativos":           int(dias),
            "turnover_rate_diario":      turnover,
            "permanencia_mediana_min":   mediana_min,
            "tasa_lectura_fallida_pct":  float(row_g.tasa_lectura_fallida_pct or 0),
            "hora_punta":                hora_punta,
            "max_aforo_historico":       int(max_entradas),
            "capacidad_calibrada":       int(capacidad_max),
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
            SELECT COALESCE(MAX(CAST(bucket AS DATE)), CAST(GETDATE() AS DATE))
            FROM aforo_horario_estacionamiento WITH (NOEXPAND)
            WHERE espacio_id = :espacio_id
        """)
        target_date = (await session.execute(sql_date, {"espacio_id": espacio_id})).scalar() or date.today()

        where_cam = ""
        capacidad_max = 125
        if sector and sector != "todos":
            sec_keys = [s.strip().upper() for s in sector.split(",") if s.strip()]
            where_cam = " AND (" + " OR ".join([f"camara LIKE '%{s}%'" for s in sec_keys]) + ")"
            sec_conds = " OR ".join([f"codigo = '{c}'" for c in sec_keys])
            try:
                sql_sec_cap = text(f"SELECT COALESCE(SUM(capacidad_max), 0) FROM sectores_estacionamiento WHERE ({sec_conds}) AND activo = 1")
                cap_sec = (await session.execute(sql_sec_cap)).scalar()
                if cap_sec and cap_sec > 0:
                    capacidad_max = int(cap_sec)
            except Exception:
                pass
        else:
            from app.domain.models import Espacio
            espacio_obj = (await session.execute(select(Espacio.capacidad_max).where(Espacio.id == espacio_id))).scalar_one_or_none()
            capacidad_max = espacio_obj or 125

        sql = text(f"""
            WITH ev_base AS (
                SELECT
                    time,
                    patente_hash,
                    direccion,
                    LAG(time) OVER (
                        PARTITION BY patente_hash, direccion, CAST(time AS DATE)
                        ORDER BY time
                    ) AS prev_same_dir_time
                FROM eventos_vehiculares
                WHERE espacio_id = :espacio_id
                  AND time >= :target_date
                  AND time < DATEADD(day, 1, CAST(:target_date AS DATETIME))
                  AND calidad_lectura != 'unknown'
                  {where_cam}
            ),
            ev_dedup AS (
                SELECT
                    time,
                    patente_hash,
                    direccion,
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
            ultima_hora AS (
                SELECT MAX(DATEADD(hour, DATEDIFF(hour, 0, time), 0)) AS max_bucket
                FROM ev_dedup
            )
            SELECT
                COALESCE((
                    SELECT TOP 1 o.vehiculos_presentes
                    FROM ocupacion_horaria o, ultima_hora u
                    WHERE u.max_bucket IS NOT NULL
                      AND o.bucket <= u.max_bucket
                    ORDER BY o.bucket DESC
                ), 0) AS vehiculos_en_ultima_hora
        """)
        row = (await session.execute(sql, {"espacio_id": espacio_id, "target_date": target_date})).one()

        aforo = min(capacidad_max, max(0, int(row.vehiculos_en_ultima_hora)))
        disponibles = max(0, capacidad_max - aforo)
        pct = round(aforo / max(1, capacidad_max) * 100, 1)

        nivel = "normal"
        if pct >= UMBRAL_ALERTA_90 * 100:
            nivel = "saturacion"
        elif pct >= 70:
            nivel = "preventivo"

        return {
            "vehiculos_presentes": aforo,
            "plazas_disponibles":  disponibles,
            "capacidad_maxima":    capacidad_max,
            "ocupacion_pct":       pct,
            "nivel_alerta":        nivel,
            "timestamp":           datetime.combine(target_date, datetime.min.time()).isoformat(),
            "sector":              sector or "todos",
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
                SELECT COALESCE(MAX(CAST(bucket AS DATE)), CAST(GETDATE() AS DATE))
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
            sec_keys = [s.strip().upper() for s in sector.split(",") if s.strip()]
            sec_conds = " OR ".join([f"codigo = '{c}'" for c in sec_keys])
            try:
                sql_sec_cap = text(f"SELECT COALESCE(SUM(capacidad_max), 0) FROM sectores_estacionamiento WHERE ({sec_conds}) AND activo = 1")
                cap_sec = (await session.execute(sql_sec_cap)).scalar()
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
        where_sec = ""
        if sector and sector != "todos":
            sec_keys = [s.strip().upper() for s in sector.split(",") if s.strip()]
            where_sec = " AND (" + " OR ".join([f"camara LIKE '%{s}%'" for s in sec_keys]) + ")"

        sql_tipo = text(f"""
            SELECT
                COALESCE(tipo_vehiculo, 'Desconocido') AS tipo,
                COUNT(*)                                AS total,
                ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct
            FROM eventos_vehiculares
            WHERE espacio_id   = :espacio_id
              AND direccion     = 'entrada'
              AND calidad_lectura = 'ok'
              AND (:inicio IS NULL OR time >= :inicio)
              AND (:fin IS NULL OR time < :fin)
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
            WHERE espacio_id    = :espacio_id
              AND direccion      = 'entrada'
              AND calidad_lectura = 'ok'
              AND (:inicio IS NULL OR time >= :inicio)
              AND (:fin IS NULL OR time < :fin)
              {where_sec}
            GROUP BY marca
            ORDER BY total DESC
        """)
        params = {"espacio_id": espacio_id, "inicio": fecha_inicio, "fin": fin_exclusive}
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
        fin_exclusive = fecha_fin + timedelta(days=1) if fecha_fin else None
        where_sec = ""
        if sector and sector != "todos":
            sec_keys = [s.strip().upper() for s in sector.split(",") if s.strip()]
            where_sec = " AND (" + " OR ".join([f"camara LIKE '%{s}%'" for s in sec_keys]) + ")"

        sql = text(f"""
            SELECT 
                CAST(fecha_dia AS DATE) AS fecha,
                SUM(CASE WHEN direccion = 'entrada' THEN total_eventos ELSE 0 END) AS entradas,
                SUM(CASE WHEN direccion = 'salida' THEN total_eventos ELSE 0 END) AS salidas,
                SUM(total_eventos) AS vehiculos_unicos
            FROM dbo.vehiculos_diario_estacionamiento WITH (NOEXPAND)
            WHERE espacio_id = :espacio_id
              AND (:inicio IS NULL OR fecha_dia >= :inicio)
              AND (:fin IS NULL OR fecha_dia < :fin)
              {where_sec}
            GROUP BY CAST(fecha_dia AS DATE)
            ORDER BY fecha ASC
        """)
        rows = (await session.execute(sql, {
            "espacio_id": espacio_id,
            "inicio": fecha_inicio,
            "fin": fin_exclusive,
        })).fetchall()
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
    async def get_intercampus_mobility(session: AsyncSession) -> dict:
        sql_events = text("""
            WITH eventos_campus AS (
                SELECT 
                    patente_hash,
                    CAST(time AS DATE) as fecha,
                    time,
                    CASE WHEN camara LIKE 'CHS%' THEN 'CHS' ELSE 'CSF' END as campus
                FROM eventos_vehiculares
                WHERE patente_hash != 'unknown'
            ),
            traslados AS (
                SELECT 
                    c1.fecha,
                    c1.patente_hash,
                    c1.campus as origen,
                    c2.campus as destino,
                    c1.time as salida_origen,
                    c2.time as llegada_destino,
                    DATEDIFF(minute, c1.time, c2.time) as minutos_traslado,
                    DATEPART(hour, c1.time) as hora_salida
                FROM eventos_campus c1
                JOIN eventos_campus c2
                  ON c1.patente_hash = c2.patente_hash
                 AND c1.fecha = c2.fecha
                 AND c1.campus != c2.campus
                 AND c2.time > c1.time
                 AND c2.time <= DATEADD(hour, 6, c1.time)
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
        rows = (await session.execute(sql_events)).fetchall()

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
    async def get_stay_distribution(session: AsyncSession, espacio_id: int = 2) -> list[dict]:
        sql = text("""
            SELECT
                CASE
                    WHEN DATEDIFF(minute, ent.time, sal.time) < 15  THEN 'drop_off'
                    WHEN DATEDIFF(minute, ent.time, sal.time) < 180 THEN '0-3h'
                    WHEN DATEDIFF(minute, ent.time, sal.time) < 360 THEN '3-6h'
                    ELSE 'jornada_completa'
                END AS rango,
                COUNT(*) AS total
            FROM eventos_vehiculares ent
            JOIN eventos_vehiculares sal
              ON ent.patente_hash = sal.patente_hash
             AND ent.espacio_id   = sal.espacio_id
             AND sal.time > ent.time
             AND sal.time < DATEADD(hour, 24, ent.time)
             AND ent.direccion = 'entrada'
             AND sal.direccion = 'salida'
            WHERE ent.espacio_id = :espacio_id
            GROUP BY 
                CASE
                    WHEN DATEDIFF(minute, ent.time, sal.time) < 15  THEN 'drop_off'
                    WHEN DATEDIFF(minute, ent.time, sal.time) < 180 THEN '0-3h'
                    WHEN DATEDIFF(minute, ent.time, sal.time) < 360 THEN '3-6h'
                    ELSE 'jornada_completa'
                END
            ORDER BY total DESC
        """)
        rows = (await session.execute(sql, {"espacio_id": espacio_id})).fetchall()
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
                    DATEPART(WEEKDAY, time) = 1
                    OR (DATEPART(WEEKDAY, time) BETWEEN 2 AND 6 AND (CAST(time AS TIME) < '07:00:00' OR CAST(time AS TIME) > '22:00:00'))
                    OR (DATEPART(WEEKDAY, time) = 7 AND (CAST(time AS TIME) < '08:00:00' OR CAST(time AS TIME) > '14:00:00'))
                )""")
            elif cat_lower == "conforme":
                conditions.append("""(
                    calidad_lectura != 'unknown'
                    AND (
                        (DATEPART(WEEKDAY, time) BETWEEN 2 AND 6 AND CAST(time AS TIME) >= '07:00:00' AND CAST(time AS TIME) <= '22:00:00')
                        OR (DATEPART(WEEKDAY, time) = 7 AND CAST(time AS TIME) >= '08:00:00' AND CAST(time AS TIME) <= '14:00:00')
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

        output = io.StringIO()
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

            writer.writerow([
                r.time.strftime("%Y-%m-%d") if r.time else "",
                r.time.strftime("%H:%M:%S") if r.time else "",
                "DESCONOCIDO" if r.patente_hash == "unknown" else f"PAT-{r.patente_hash[:8]}",
                r.camara or "",
                r.direccion or "",
                r.tipo_vehiculo or "Desconocido",
                r.marca or "Desconocida",
                r.color or "—",
                r.calidad_lectura or "",
                " | ".join(categorias_row),
                nivel,
            ])

        return output.getvalue(), len(rows)

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
            max_ts = fecha_max or max(d.time for d in dtos)
            stmt_keys = (
                select(EventoVehicular.time, EventoVehicular.espacio_id, EventoVehicular.patente_hash)
                .where(
                    EventoVehicular.espacio_id == target_espacio_id,
                    EventoVehicular.time >= min_ts,
                    EventoVehicular.time <= max_ts,
                )
            )
            res_keys = await db.execute(stmt_keys)
            existing_keys = {(r[0], r[1], r[2]) for r in res_keys.fetchall()}

        seen_keys = set()
        a_insertar = []
        for dto in dtos:
            key = (dto.time, dto.espacio_id, dto.patente_hash)
            if modo_solapamiento == "merge" and key in existing_keys:
                continue

            if key in seen_keys:
                offset = 1
                cand_time = dto.time + timedelta(seconds=offset)
                cand_key = (cand_time, dto.espacio_id, dto.patente_hash)
                while (cand_key in seen_keys or (modo_solapamiento == "merge" and cand_key in existing_keys)) and offset < 59:
                    offset += 1
                    cand_time = dto.time + timedelta(seconds=offset)
                    cand_key = (cand_time, dto.espacio_id, dto.patente_hash)

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
            sql = text("SELECT YEAR(MAX(bucket)) FROM aforo_horario_estacionamiento WHERE espacio_id = :espacio_id")
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
            where_conds.append("bucket < DATEADD(day, 1, CAST(:fin AS DATETIME))")
            params["fin"] = fecha_fin
        where_clause = " AND ".join(where_conds)
        sql = text(f"""
            SELECT CAST(bucket AS DATE) as fecha,
                   DATENAME(weekday, CAST(bucket AS DATE)) as dia_semana,
                   SUM(entradas) as ingresos,
                   SUM(salidas) as salidas
            FROM aforo_horario_estacionamiento
            WHERE {where_clause}
            GROUP BY CAST(bucket AS DATE), DATENAME(weekday, CAST(bucket AS DATE))
            ORDER BY fecha ASC
        """)
        res = await session.execute(sql, params)
        return [dict(r._mapping) for r in res.all()]

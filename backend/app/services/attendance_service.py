"""
AttendanceService — Consultas sobre Continuous Aggregates de TimescaleDB.
Todas las queries apuntan a las vistas pre-agregadas; nunca a microdatos.
"""
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import TTLCache

CAPACIDAD_BIBLIOTECA = 350
UMBRAL_REBOTE_MIN = 15
UMBRAL_ALERTA_70 = 0.70
UMBRAL_ALERTA_85 = 0.85
# Prefijo de hash seudonimizado asociado a registros sin credencial / marcajes de prueba excluidos de conformes
PREFIJO_HASH_PRUEBA_EXCLUIDO = "e8f17a68%"

# Caché en memoria para reutilizar horarios de operación entre gráficos simultáneos
cache_horarios_espacio: TTLCache = TTLCache(maxsize=32, ttl=300)


async def obtener_horarios_operacion_cacheados(session: AsyncSession, espacio_id: int) -> list:
    clave_cache = f"horarios_24h:{espacio_id}"
    if clave_cache in cache_horarios_espacio:
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
    cache_horarios_espacio[clave_cache] = filas
    return filas


def invalidar_cache_horarios(espacio_id: Optional[int] = None) -> None:
    if espacio_id is not None:
        cache_horarios_espacio.pop(f"horarios_24h:{espacio_id}", None)
    else:
        cache_horarios_espacio.clear()


invalidar_cache_horarios_asistencia = invalidar_cache_horarios


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
                sub_24 = getattr(r_24, "subespacio", None) or "todos"
                if sub_24 in ("sala_1", "sala1"):
                    h24_clauses.append(f"(time >= :{p_ini} AND time <= :{p_fin} AND (door_entrada LIKE '%CSF02%' OR door_salida LIKE '%CSF02%'))")
                elif sub_24 in ("sala_2", "sala2"):
                    h24_clauses.append(f"(time >= :{p_ini} AND time <= :{p_fin} AND (door_entrada LIKE '%CSF04%' OR door_salida LIKE '%CSF04%'))")
                else:
                    h24_clauses.append(f"(time >= :{p_ini} AND time <= :{p_fin})")
                params[p_ini] = r_24.fecha_inicio
                params[p_fin] = r_24.fecha_fin

        is_24h_sql = f"({' OR '.join(h24_clauses)})" if h24_clauses else "1=0"
        not_24h_sql = f"(NOT ({' OR '.join(h24_clauses)}))" if h24_clauses else "1=1"

        holiday_sql = """EXISTS (
            SELECT 1 FROM calendario_academico ca 
            WHERE ca.fecha = CAST(time AS DATE) 
              AND ca.is_holiday = 1
        )"""

        closure_sql = """(
            EXISTS (
                SELECT 1 FROM calendario_academico ca 
                WHERE ca.fecha = CAST(time AS DATE) 
                  AND ca.is_holiday = 1
            )
            OR EXISTS (
                SELECT 1 FROM contingencias_academicas cca
                WHERE cca.implica_cierre_total = 1
                  AND (cca.espacio_id IS NULL OR cca.espacio_id = :espacio_id)
                  AND CAST(time AS DATE) BETWEEN cca.fecha_inicio AND cca.fecha_fin
                  AND (
                      cca.subespacio IS NULL OR cca.subespacio = 'todos'
                      OR (cca.subespacio = 'sala_1' AND (door_entrada LIKE '%CSF02%' OR door_salida LIKE '%CSF02%'))
                      OR (cca.subespacio = 'sala_2' AND (door_entrada LIKE '%CSF04%' OR door_salida LIKE '%CSF04%'))
                  )
                  AND (
                      cca.hora_inicio IS NULL OR cca.hora_fin IS NULL OR cca.hora_inicio = '' OR cca.hora_fin = ''
                      OR (CAST(time AS TIME) >= CAST(cca.hora_inicio AS TIME) AND CAST(time AS TIME) <= CAST(cca.hora_fin AS TIME))
                  )
            )
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
            (dia_semana_iso BETWEEN 1 AND 4 AND CAST(time AS TIME) >= '08:30:00' AND CAST(time AS TIME) <= '20:30:00')
            OR (dia_semana_iso = 5 AND CAST(time AS TIME) >= '08:30:00' AND CAST(time AS TIME) <= '19:30:00')
            OR (dia_semana_iso = 6 AND CAST(time AS TIME) >= '10:30:00' AND CAST(time AS TIME) <= '13:30:00')
        )"""

        f_oficial_sql = f"({regular_open_sql} AND NOT ({holiday_sql}))"

        regular_closed_sql = """(
            dia_semana_iso = 7
            OR (dia_semana_iso BETWEEN 1 AND 4 AND (CAST(time AS TIME) < '08:30:00' OR CAST(time AS TIME) > '20:30:00'))
            OR (dia_semana_iso = 5 AND (CAST(time AS TIME) < '08:30:00' OR CAST(time AS TIME) > '19:30:00'))
            OR (dia_semana_iso = 6 AND (CAST(time AS TIME) < '10:30:00' OR CAST(time AS TIME) > '13:30:00'))
        )"""

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
                        sql_h = text("SELECT fecha_inicio, fecha_fin, hora_apertura, hora_cierre, es_continuo_24h, subespacio FROM horarios_operacion WHERE id = :h_id")
                        h_row = (await session.execute(sql_h, {"h_id": h_id})).first()
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
                            sub_h = (getattr(h_row, "subespacio", None) or "todos").strip()
                            if sub_h in ("sala_1", "sala1"):
                                sub_clauses.append("(door_entrada LIKE '%CSF02%' OR door_salida LIKE '%CSF02%')")
                            elif sub_h in ("sala_2", "sala2"):
                                sub_clauses.append("(door_entrada LIKE '%CSF04%' OR door_salida LIKE '%CSF04%')")
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
                conditions.append("(door_entrada LIKE '%CSF02%' OR door_salida LIKE '%CSF02%')")
            elif any(k in s_low for k in ["csf04", "sala_2", "sala 2", "edificio 4", "pecera", "1er piso", "24h"]) or s_low == "2":
                conditions.append("(door_entrada LIKE '%CSF04%' OR door_salida LIKE '%CSF04%')")
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
                        door_clauses.append("(door_entrada LIKE '%CSF02%' OR door_salida LIKE '%CSF02%')")
                    # Torniquetes Sala 2 (CSF04 Pecera)
                    elif d in ("s2_principal", "2592", "2587", "csf04_in01", "csf04_out"):
                        door_clauses.append("(door_entrada LIKE '%CSF04_110 IN 01%' OR door_salida LIKE '%CSF04_110 OUT%' OR door_entrada IN ('2592', '2592.0') OR door_salida IN ('2587', '2587.0'))")
                    elif d in ("s2_universal", "3411", "3416", "csf04_in02", "csf04_out02"):
                        door_clauses.append("(door_entrada LIKE '%CSF04_110 IN 02%' OR door_salida LIKE '%CSF04_110 OUT 02%' OR door_entrada IN ('3411', '3411.0') OR door_salida IN ('3416', '3416.0'))")
                    elif d in ("2", "t2", "torniquete 2"):
                        door_clauses.append("(door_entrada LIKE '%CSF04%' OR door_salida LIKE '%CSF04%')")
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
        )
        params["rebote"] = UMBRAL_REBOTE_MIN

        sql = text(f"""
            SELECT
                COUNT(*)                                        AS total_registros,
                COUNT(DISTINCT person_id_hash)                  AS usuarios_unicos,
                COUNT(DISTINCT CAST(time AS DATE))              AS dias_operativos,
                ROUND(CAST(AVG(CAST(permanencia_min AS FLOAT)) AS DECIMAL(10,2)), 2) AS permanencia_promedio_min,
                ROUND(
                    100.0 * SUM(CASE WHEN permanencia_min < :rebote THEN 1 ELSE 0 END)
                    / NULLIF(SUM(CASE WHEN permanencia_min IS NOT NULL THEN 1 ELSE 0 END), 0),
                2)                                              AS tasa_rebote_pct,
                ROUND(SUM(permanencia_min) / 60.0, 1)           AS horas_estudiante_total
            FROM eventos_asistencia
            WHERE {where_sql}
        """)
        row = (await session.execute(sql, params)).first()

        sql_median = text(f"""
            SELECT DISTINCT
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY permanencia_min) OVER () AS permanencia_mediana_min
            FROM eventos_asistencia
            WHERE {where_sql}
              AND permanencia_min IS NOT NULL
        """)
        row_median = (await session.execute(sql_median, params)).first()
        mediana = row_median.permanencia_mediana_min if row_median and row_median.permanencia_mediana_min is not None else 0

        dias = row.dias_operativos or 1 if row else 1
        total = row.total_registros or 0 if row else 0
        unicos = row.usuarios_unicos or 0 if row else 0

        sql_peak = text(f"""
            SELECT TOP 1 hora_dia AS hora, COUNT(DISTINCT person_id_hash) AS total
            FROM eventos_asistencia
            WHERE {where_sql}
            GROUP BY hora_dia
            ORDER BY total DESC
        """)
        row_peak = (await session.execute(sql_peak, params)).first()
        hora_punta = f"{row_peak.hora:02d}:00 hrs" if row_peak and row_peak.hora is not None else "14:00 hrs"

        sql_max = text(f"""
            SELECT COALESCE(MAX(cnt), 0)
            FROM (
                SELECT COUNT(DISTINCT person_id_hash) as cnt
                FROM eventos_asistencia
                WHERE {where_sql}
                GROUP BY DATEADD(hour, DATEDIFF(hour, 0, time), 0)
            ) sub
        """)
        max_ingresos = (await session.execute(sql_max, params)).scalar() or 0

        return {
            "total_registros":          total,
            "usuarios_unicos":          unicos,
            "dias_operativos":          dias,
            "promedio_marcajes_diarios": round(total / dias, 1),
            "tasa_recurrencia_mensual": round((total / unicos) if unicos else 0, 2),
            "permanencia_promedio_min": float(row.permanencia_promedio_min or 0) if row else 0.0,
            "permanencia_mediana_min":  float(mediana),
            "tasa_rebote_pct":          float(row.tasa_rebote_pct or 0) if row else 0.0,
            "horas_estudiante_total":   float(row.horas_estudiante_total or 0) if row else 0.0,
            "hora_punta":               hora_punta,
            "max_aforo_historico":      int(max_ingresos),
        }

    # ------------------------------------------------------------------
    # Aforo concurrente en tiempo real
    # ------------------------------------------------------------------
    @staticmethod
    async def get_occupancy_realtime(session: AsyncSession, espacio_id: int = 1) -> dict:
        sql_date = text("""
            SELECT COALESCE(MAX(CAST(bucket AS DATE)), CAST(GETDATE() AS DATE))
            FROM aforo_horario_biblioteca WITH (NOEXPAND)
            WHERE espacio_id = :espacio_id
        """)
        target_date = (await session.execute(sql_date, {"espacio_id": espacio_id})).scalar() or date.today()

        sql = text("""
            SELECT
                COALESCE(SUM(ingresos), 0) AS total_ingresos,
                COALESCE(SUM(salidas),  0) AS total_salidas
            FROM aforo_horario_biblioteca WITH (NOEXPAND)
            WHERE espacio_id = :espacio_id
              AND bucket >= :target_date
              AND bucket <  DATEADD(day, 1, CAST(:target_date AS DATETIME))
        """)
        row = (await session.execute(sql, {"espacio_id": espacio_id, "target_date": target_date})).one()
        from app.domain.models import Espacio
        espacio_obj = (await session.execute(select(Espacio.capacidad_max).where(Espacio.id == espacio_id))).scalar_one_or_none()
        capacidad_max = espacio_obj or CAPACIDAD_BIBLIOTECA

        aforo = max(0, int(row.total_ingresos) - int(row.total_salidas))
        pct = round(aforo / capacidad_max * 100, 1)

        nivel = "normal"
        if pct >= UMBRAL_ALERTA_85 * 100:
            nivel = "critico"
        elif pct >= UMBRAL_ALERTA_70 * 100:
            nivel = "preventivo"

        return {
            "aforo_actual":     aforo,
            "capacidad_maxima": capacidad_max,
            "ocupacion_pct":    pct,
            "nivel_alerta":     nivel,
            "timestamp":        datetime.combine(target_date, datetime.min.time()).isoformat(),
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
    ) -> list[dict]:
        if fecha_inicio is None or fecha_fin is None:
            sql_max = text("""
                SELECT COALESCE(MAX(CAST(bucket AS DATE)), CAST(GETDATE() AS DATE))
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
        )

        if not tiene_filtros_particulares:
            # Vía acelerada con vista indexada aforo_horario_biblioteca
            where_clauses = ["espacio_id = :espacio_id"]
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
                    DATEPART(WEEKDAY, bucket) AS dia_semana,
                    DATEPART(HOUR, bucket)    AS hora,
                    ROUND(CAST(AVG(CAST(ingresos AS FLOAT)) AS DECIMAL(10,2)), 2) AS ingresos_promedio
                FROM aforo_horario_biblioteca WITH (NOEXPAND)
                WHERE {where_sql}
                GROUP BY DATEPART(WEEKDAY, bucket), DATEPART(HOUR, bucket)
                ORDER BY dia_semana, hora
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
        fin_exclusive = fecha_fin + timedelta(days=1) if fecha_fin else None
        sql = text("""
            SELECT 
                DATEPART(HOUR, bucket) AS hora,
                ROUND(CAST(AVG(CAST(ingresos AS FLOAT)) AS DECIMAL(10,1)), 1) AS promedio_ingresos,
                MAX(ingresos) AS max_ingresos,
                SUM(ingresos) AS total_ingresos
            FROM aforo_horario_biblioteca WITH (NOEXPAND)
            WHERE espacio_id = :espacio_id
              AND (:inicio IS NULL OR bucket >= :inicio)
              AND (:fin IS NULL OR bucket < :fin)
            GROUP BY DATEPART(HOUR, bucket)
            ORDER BY hora ASC
        """)
        rows = (await session.execute(sql, {
            "espacio_id": espacio_id,
            "inicio": fecha_inicio,
            "fin": fin_exclusive,
        })).fetchall()
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
        incluir_pausas_bano: bool = True,
        desduplicar_rafagas: bool = True,
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
            incluir_pausas_bano=incluir_pausas_bano,
            desduplicar_rafagas=desduplicar_rafagas,
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
                "sala": "Sala 1 (CSF02)",
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
                "sala": "Sala 1 (CSF02)",
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
                "sala": "Sala 2 (CSF04 Pecera)",
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
                "sala": "Sala 2 (CSF04 Pecera)",
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
        marcajes: Optional[str] = "todos",
        carrera: Optional[str] = None,
        facultad: Optional[str] = None,
        incluir_pausas_bano: bool = True,
        desduplicar_rafagas: bool = True,
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
            marcajes=marcajes,
            carrera=carrera,
            facultad=facultad,
            incluir_pausas_bano=incluir_pausas_bano,
            desduplicar_rafagas=desduplicar_rafagas,
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

        cap_s1 = 124
        cap_s2 = 226

        map_salas = {}
        for r in rows_totals:
            if "CSF02" in r.sala_nombre or "Sala 1" in r.sala_nombre:
                map_salas["Sala 1 (CSF02)"] = r
            elif "CSF04" in r.sala_nombre or "Sala 2" in r.sala_nombre:
                map_salas["Sala 2 (CSF04 Pecera)"] = r

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
            construir_sala("Sala 1 (CSF02)", cap_s1, "CSF02", False),
            construir_sala("Sala 2 (CSF04 Pecera)", cap_s2, "CSF04", True),
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
        marcajes: Optional[str] = "todos",
        carrera: Optional[str] = None,
        facultad: Optional[str] = None,
        incluir_pausas_bano: bool = True,
        desduplicar_rafagas: bool = True,
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
            marcajes=marcajes,
            carrera=carrera,
            facultad=facultad,
            incluir_pausas_bano=incluir_pausas_bano,
            desduplicar_rafagas=desduplicar_rafagas,
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

        cap_s1 = 124
        cap_s2 = 226

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
            )
            SELECT 
                dec.anho_ingreso AS cohorte,
                COUNT(DISTINCT dec.person_id_hash) AS total_estudiantes,
                COUNT(DISTINCT ea.person_id_hash) AS estudiantes_asistentes,
                COUNT(ea.time) AS eventos_asistencia
            FROM dim_estudiante_carrera dec
            LEFT JOIN ea_filtrada ea 
                ON dec.person_id_hash = ea.person_id_hash
            WHERE dec.anho_ingreso IS NOT NULL
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
        incluir_pausas_bano: bool = True,
        desduplicar_rafagas: bool = True,
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
            incluir_pausas_bano=incluir_pausas_bano,
            desduplicar_rafagas=desduplicar_rafagas,
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
        incluir_pausas_bano: bool = True,
        desduplicar_rafagas: bool = True,
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
            incluir_pausas_bano=incluir_pausas_bano,
            desduplicar_rafagas=desduplicar_rafagas,
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
        page: int = 1,
        page_size: int = 50,
        incluir_pausas_bano: bool = True,
        desduplicar_rafagas: bool = True,
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
            incluir_pausas_bano=incluir_pausas_bano,
            desduplicar_rafagas=desduplicar_rafagas,
        )

        conditions = [where_sql]

        if search_hash:
            conditions.append("person_id_hash LIKE :search_hash")
            params["search_hash"] = f"%{search_hash}%"

        # Filtro de categoría específica si se seleccionó en el dropdown de microdatos
        if categoria:
            cat_lower = categoria.lower()
            if cat_lower == "fuera_de_horario":
                conditions.append("""(
                    DATEPART(MONTH, time) != 7 AND (
                        dia_semana_iso = 7
                        OR (dia_semana_iso BETWEEN 1 AND 4 AND (CAST(time AS TIME) < '08:30:00' OR CAST(time AS TIME) > '20:30:00'))
                        OR (dia_semana_iso = 5 AND (CAST(time AS TIME) < '08:30:00' OR CAST(time AS TIME) > '19:30:00'))
                        OR (dia_semana_iso = 6 AND (CAST(time AS TIME) < '10:30:00' OR CAST(time AS TIME) > '13:30:00'))
                    )
                )""")
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
            if r.time and not es_horario_conforme(r.time, horarios):
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
        limit: int = 100000,
        incluir_pausas_bano: bool = True,
        desduplicar_rafagas: bool = True,
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
            incluir_pausas_bano=incluir_pausas_bano,
            desduplicar_rafagas=desduplicar_rafagas,
        )
        params["limit"] = limit

        conditions = [where_sql]
        if search_hash:
            conditions.append("person_id_hash LIKE :search_hash")
            params["search_hash"] = f"%{search_hash}%"

        if categoria:
            cat_lower = categoria.lower()
            if cat_lower == "fuera_de_horario":
                conditions.append("""(
                    DATEPART(MONTH, time) != 7 AND (
                        dia_semana_iso = 7
                        OR (dia_semana_iso BETWEEN 1 AND 4 AND (CAST(time AS TIME) < '08:30:00' OR CAST(time AS TIME) > '20:30:00'))
                        OR (dia_semana_iso = 5 AND (CAST(time AS TIME) < '08:30:00' OR CAST(time AS TIME) > '19:30:00'))
                        OR (dia_semana_iso = 6 AND (CAST(time AS TIME) < '10:30:00' OR CAST(time AS TIME) > '13:30:00'))
                    )
                )""")
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

        output = io.StringIO()
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
            if r.time and not es_horario_conforme(r.time, horarios):
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

            writer.writerow([
                r.time.strftime("%Y-%m-%d") if r.time else "",
                r.time.strftime("%H:%M:%S") if r.time else "",
                "SIN-CREDENCIAL" if r.person_id_hash.startswith("e8f17a68") else f"USR-{r.person_id_hash[:8]}",
                str(r.door_entrada).replace(".0", "") if r.door_entrada and str(r.door_entrada) != "nan" else "—",
                str(r.door_salida).replace(".0", "") if r.door_salida and str(r.door_salida) != "nan" else "—",
                r.primera_entrada.strftime("%H:%M:%S") if r.primera_entrada else "—",
                r.ultima_salida.strftime("%H:%M:%S") if r.ultima_salida else "—",
                round(float(r.permanencia_min), 1) if r.permanencia_min is not None else 0.0,
                int(r.marcajes_totales) if r.marcajes_totales is not None else 1,
                "Si" if r.salida_imputada else "No",
                "Si" if getattr(r, "entrada_imputada", False) else "No",
                "Si" if r.alerta_coherencia_fechas else "No",
                " | ".join(categorias_row),
                nivel,
            ])

        return output.getvalue(), len(rows)

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
            max_ts = fecha_max or max(d.time for d in dtos)
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
            sql = text("SELECT YEAR(MAX(bucket)) FROM aforo_horario_biblioteca WHERE espacio_id = :espacio_id")
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
                   SUM(ingresos) as ingresos,
                   SUM(salidas) as salidas,
                   SUM(personas_unicas) as personas_unicas
            FROM aforo_horario_biblioteca
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
        ).order_by(HorarioOperacion.id.desc())
        todas_campanas = (await session.execute(stmt_todas)).scalars().all()

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
            "descripcion": "Consolidado Histórico Anual 2026 (Todas las campañas)",
            "fecha_inicio": "2026-01-01",
            "fecha_fin": "2026-12-31",
            "subespacio": "sala_2",
        })
        campanas_list.append({
            "id": -1,
            "descripcion": "Período Personalizado",
            "fecha_inicio": None,
            "fecha_fin": None,
            "subespacio": "sala_2",
        })

        tiene_campana_activa = True
        if campana_id is not None and campana_id >= 0:
            if campana_id > 0:
                stmt_sel = select(HorarioOperacion).where(HorarioOperacion.id == campana_id)
                regla_24h = (await session.execute(stmt_sel)).scalars().first()
                if regla_24h and regla_24h.fecha_inicio and regla_24h.fecha_fin:
                    f_ini = regla_24h.fecha_inicio.date()
                    f_fin = regla_24h.fecha_fin.date()
                else:
                    f_ini = date(2026, 6, 1)
                    f_fin = date(2026, 6, 30)
                desc_campana = regla_24h.descripcion if regla_24h else f"Campaña #{campana_id}"
                date_condition = "time >= :f_ini AND time < DATEADD(day, 1, CAST(:f_fin AS DATE))"
            else:
                # campana_id == 0: Consolidado Histórico de todas las campañas 24 Horas
                regla_24h = None
                f_ini = date(2026, 1, 1)
                f_fin = date(2026, 12, 31)
                desc_campana = "Consolidado Histórico Anual 2026 (Todas las campañas)"
                campana_ranges = [
                    f"(time >= '{c.fecha_inicio.date().isoformat()}' AND time < '{(c.fecha_fin.date() + timedelta(days=1)).isoformat()}')"
                    for c in todas_campanas if c.fecha_inicio and c.fecha_fin
                ]
                if campana_ranges:
                    date_condition = f"({' OR '.join(campana_ranges)})"
                else:
                    date_condition = "time >= :f_ini AND time < DATEADD(day, 1, CAST(:f_fin AS DATE))"
        elif fecha_inicio and fecha_fin:
            # Período personalizado (campana_id == -1 o None con fechas específicas)
            regla_24h = None
            f_ini = fecha_inicio
            f_fin = fecha_fin
            campanas_en_periodo = [
                c for c in todas_campanas
                if c.fecha_inicio and c.fecha_fin and
                c.fecha_inicio.date() <= f_fin and c.fecha_fin.date() >= f_ini
            ]
            tiene_campana_activa = len(campanas_en_periodo) > 0
            if tiene_campana_activa:
                desc_campana = f"Período Personalizado ({f_ini.strftime('%d/%m/%Y')} al {f_fin.strftime('%d/%m/%Y')})"
            else:
                desc_campana = f"Período Regular sin Régimen 24h ({f_ini.strftime('%d/%m/%Y')} al {f_fin.strftime('%d/%m/%Y')})"
            date_condition = "time >= :f_ini AND time < DATEADD(day, 1, CAST(:f_fin AS DATE))"
        else:
            # Por defecto: seleccionar la campaña histórica que tiene datos consolidados (Junio 2026)
            regla_24h = next((c for c in todas_campanas if c.fecha_inicio and c.fecha_inicio.month == 6), todas_campanas[0] if todas_campanas else None)
            f_ini = regla_24h.fecha_inicio.date() if regla_24h and regla_24h.fecha_inicio else date(2026, 6, 1)
            f_fin = regla_24h.fecha_fin.date() if regla_24h and regla_24h.fecha_fin else date(2026, 6, 30)
            desc_campana = regla_24h.descripcion if regla_24h else "Campaña 24 Horas Exámenes"
            date_condition = "time >= :f_ini AND time < DATEADD(day, 1, CAST(:f_fin AS DATE))"

        capacidad_asientos = 226
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

        params_base = {
            "espacio_id": espacio_id,
            "f_ini": f_ini,
            "f_fin": f_fin,
        }

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
            WHERE espacio_id = :espacio_id
              AND {date_condition}
              AND {door_condition}
              AND alerta_coherencia_fechas = 0
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
                WHERE (door_entrada LIKE '%CSF04%' OR door_salida LIKE '%CSF04%')
                  AND {date_condition}
                  AND {nocturno_condition}
                  AND alerta_coherencia_fechas = 0
            """)
            row_presencia = (await session.execute(sql_presencia, params_base)).first()
            est_presencia_total = int(row_presencia.estudiantes_presencia_total or 0) if row_presencia else int(row_kpis.estudiantes_nocturnos_unicos or 0)
            est_solo_in = int(row_kpis.estudiantes_nocturnos_unicos or 0)
            est_remanentes = max(0, est_presencia_total - est_solo_in)
            est_nocturnos = est_presencia_total

            sql_fases = text(f"""
                SELECT
                    SUM(CASE WHEN (CAST(time AS TIME) >= '22:00:00' AND CAST(time AS TIME) <= '23:59:59' AND {nocturno_condition}) THEN 1 ELSE 0 END) AS fase_vespertina,
                    SUM(CASE WHEN (CAST(time AS TIME) >= '00:00:00' AND CAST(time AS TIME) < '04:00:00' AND {nocturno_condition}) THEN 1 ELSE 0 END) AS fase_profunda,
                    SUM(CASE WHEN (CAST(time AS TIME) >= '04:00:00' AND CAST(time AS TIME) < '07:00:00' AND {nocturno_condition}) THEN 1 ELSE 0 END) AS fase_cierre
                FROM eventos_asistencia
                WHERE espacio_id = :espacio_id
                  AND {date_condition}
                  AND {door_condition}
                  AND alerta_coherencia_fechas = 0
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
                WHERE espacio_id = :espacio_id
                  AND {date_condition}
                  AND {door_condition}
                  AND {nocturno_condition}
                  AND alerta_coherencia_fechas = 0
                GROUP BY hora_dia
                ORDER BY COUNT(*) DESC
            """)
            row_pico = (await session.execute(sql_pico, params_base)).first()
            pico_aforo = int(row_pico.concurrencia) if row_pico else 0
            hora_pico = f"{int(row_pico.hora):02d}:00 hrs" if row_pico else "23:00 hrs"
            tasa_ocupacion = round(100.0 * pico_aforo / capacidad_asientos, 1)

            sql_carreras = text(f"""
                WITH presencia_est AS (
                    SELECT 
                        COALESCE(carrera, 'Otras Carreras') AS carrera,
                        person_id_hash,
                        SUM(CASE WHEN door_entrada LIKE '%CSF04%' THEN 1 ELSE 0 END) AS entradas_noc,
                        SUM(CASE WHEN door_salida LIKE '%CSF04%' THEN 1 ELSE 0 END) AS salidas_noc
                    FROM eventos_asistencia
                    WHERE espacio_id = :espacio_id
                      AND {date_condition}
                      AND (door_entrada LIKE '%CSF04%' OR door_salida LIKE '%CSF04%')
                      AND {nocturno_condition}
                      AND alerta_coherencia_fechas = 0
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
                    WHERE espacio_id = :espacio_id
                      AND {date_condition}
                      AND (door_entrada LIKE '%CSF04%' OR door_salida LIKE '%CSF04%')
                      AND {nocturno_condition}
                      AND alerta_coherencia_fechas = 0
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
                WHERE espacio_id = :espacio_id
                  AND {date_condition}
                  AND {door_condition}
                  AND {nocturno_condition}
                  AND alerta_coherencia_fechas = 0
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
                WHERE espacio_id = :espacio_id
                  AND {date_condition}
                  AND {door_condition}
                  AND {nocturno_condition}
                  AND alerta_coherencia_fechas = 0
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
            p_camp = {"espacio_id": espacio_id, "cf_ini": cf_ini, "cf_fin": cf_fin}
            sql_c_kpi = text(f"""
                SELECT 
                    SUM(CASE WHEN (({cond_lj}) OR ({cond_vie})) THEN 1 ELSE 0 END) AS nocturnos,
                    SUM(CASE WHEN NOT (({cond_lj}) OR ({cond_vie})) THEN 1 ELSE 0 END) AS diurnos,
                    COUNT(DISTINCT CASE WHEN (({cond_lj}) OR ({cond_vie})) THEN person_id_hash END) AS est_nocturnos,
                    ROUND(SUM(CASE WHEN (({cond_lj}) OR ({cond_vie})) THEN COALESCE(permanencia_min, 120) ELSE 0 END) / 60.0, 1) AS horas_nocturnas
                FROM eventos_asistencia
                WHERE espacio_id = :espacio_id
                  AND time >= :cf_ini AND time < DATEADD(day, 1, CAST(:cf_fin AS DATE))
                  AND {door_condition}
                  AND alerta_coherencia_fechas = 0
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
                DATEPART(week, time) as semana_num,
                MIN(CAST(time AS DATE)) as min_fecha,
                MAX(CAST(time AS DATE)) as max_fecha,
                dia_semana_iso as dia_dw,
                hora_dia as hora,
                COUNT(*) as ingresos
            FROM eventos_asistencia
            WHERE espacio_id = :espacio_id
              AND {date_condition}
              AND {door_condition}
              AND alerta_coherencia_fechas = 0
            GROUP BY DATEPART(week, time), dia_semana_iso, hora_dia
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
        rangos_24h = [
            (c.fecha_inicio.date(), c.fecha_fin.date())
            for c in todas_campanas if c.fecha_inicio and c.fecha_fin
        ]

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


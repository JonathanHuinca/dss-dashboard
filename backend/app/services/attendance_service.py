"""
AttendanceService — Consultas sobre Continuous Aggregates de TimescaleDB.
Todas las queries apuntan a las vistas pre-agregadas; nunca a microdatos.
"""
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

CAPACIDAD_BIBLIOTECA = 350
UMBRAL_REBOTE_MIN = 15
UMBRAL_ALERTA_70 = 0.70
UMBRAL_ALERTA_85 = 0.85


class AttendanceService:

    # ------------------------------------------------------------------
    # KPIs generales
    # ------------------------------------------------------------------
    @staticmethod
    async def get_kpis(session: AsyncSession, espacio_id: int = 1) -> dict:
        sql = text("""
            SELECT
                COUNT(*)                                        AS total_registros,
                COUNT(DISTINCT person_id_hash)                  AS usuarios_unicos,
                COUNT(DISTINCT DATE(primera_entrada))           AS dias_operativos,
                ROUND(AVG(permanencia_min)::numeric, 2)         AS permanencia_promedio_min,
                ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP
                      (ORDER BY permanencia_min)::numeric, 2)   AS permanencia_mediana_min,
                ROUND(
                    100.0 * COUNT(*) FILTER (WHERE permanencia_min < :rebote)
                    / NULLIF(COUNT(*) FILTER (WHERE permanencia_min IS NOT NULL), 0),
                2)                                              AS tasa_rebote_pct,
                ROUND(SUM(permanencia_min) / 60.0, 1)           AS horas_estudiante_total
            FROM eventos_asistencia
            WHERE espacio_id = :espacio_id
              AND alerta_coherencia_fechas = FALSE
        """)
        row = (await session.execute(sql, {"espacio_id": espacio_id, "rebote": UMBRAL_REBOTE_MIN})).one()

        dias = row.dias_operativos or 1
        total = row.total_registros or 0
        unicos = row.usuarios_unicos or 0

        sql_peak = text("""
            SELECT EXTRACT(HOUR FROM bucket)::int AS hora, SUM(ingresos) AS total
            FROM aforo_horario_biblioteca
            WHERE espacio_id = :espacio_id
            GROUP BY hora
            ORDER BY total DESC
            LIMIT 1
        """)
        row_peak = (await session.execute(sql_peak, {"espacio_id": espacio_id})).first()
        hora_punta = f"{row_peak.hora:02d}:00 hrs" if row_peak and row_peak.hora is not None else "14:00 hrs"

        sql_max = text("""
            SELECT COALESCE(MAX(ingresos), 0) AS max_ingresos
            FROM aforo_horario_biblioteca
            WHERE espacio_id = :espacio_id
        """)
        max_ingresos = (await session.execute(sql_max, {"espacio_id": espacio_id})).scalar() or 0

        return {
            "total_registros":          total,
            "usuarios_unicos":          unicos,
            "dias_operativos":          dias,
            "promedio_marcajes_diarios": round(total / dias, 1),
            "tasa_recurrencia_mensual": round((total / unicos) if unicos else 0, 2),
            "permanencia_promedio_min": float(row.permanencia_promedio_min or 0),
            "permanencia_mediana_min":  float(row.permanencia_mediana_min or 0),
            "tasa_rebote_pct":          float(row.tasa_rebote_pct or 0),
            "horas_estudiante_total":   float(row.horas_estudiante_total or 0),
            "hora_punta":               hora_punta,
            "max_aforo_historico":      int(max_ingresos),
        }

    # ------------------------------------------------------------------
    # Aforo concurrente en tiempo real
    # ------------------------------------------------------------------
    @staticmethod
    async def get_occupancy_realtime(session: AsyncSession, espacio_id: int = 1) -> dict:
        sql_date = text("""
            SELECT COALESCE(MAX(DATE(bucket)), CURRENT_DATE)
            FROM aforo_horario_biblioteca
            WHERE espacio_id = :espacio_id
        """)
        target_date = (await session.execute(sql_date, {"espacio_id": espacio_id})).scalar() or date.today()

        sql = text("""
            SELECT
                COALESCE(SUM(ingresos), 0) AS total_ingresos,
                COALESCE(SUM(salidas),  0) AS total_salidas
            FROM aforo_horario_biblioteca
            WHERE espacio_id = :espacio_id
              AND bucket >= :target_date
              AND bucket <  :target_date + INTERVAL '1 day'
        """)
        row = (await session.execute(sql, {"espacio_id": espacio_id, "target_date": target_date})).one()
        aforo = max(0, int(row.total_ingresos) - int(row.total_salidas))
        pct = round(aforo / CAPACIDAD_BIBLIOTECA * 100, 1)

        nivel = "normal"
        if pct >= UMBRAL_ALERTA_85 * 100:
            nivel = "critico"
        elif pct >= UMBRAL_ALERTA_70 * 100:
            nivel = "preventivo"

        return {
            "aforo_actual":     aforo,
            "capacidad_maxima": CAPACIDAD_BIBLIOTECA,
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
    ) -> list[dict]:
        if fecha_inicio is None or fecha_fin is None:
            sql_max = text("""
                SELECT COALESCE(MAX(DATE(bucket)), CURRENT_DATE)
                FROM aforo_horario_biblioteca
                WHERE espacio_id = :espacio_id
            """)
            max_date = (await session.execute(sql_max, {"espacio_id": espacio_id})).scalar() or date.today()
            if fecha_fin is None:
                fecha_fin = max_date
            if fecha_inicio is None:
                fecha_inicio = max_date - timedelta(days=6)

        fin_exclusive = fecha_fin + timedelta(days=1)
        sql = text("""
            SELECT
                bucket,
                COALESCE(ingresos, 0)       AS ingresos,
                COALESCE(salidas,  0)        AS salidas,
                COALESCE(personas_unicas, 0) AS personas_unicas
            FROM aforo_horario_biblioteca
            WHERE espacio_id = :espacio_id
              AND bucket >= :inicio
              AND bucket <  :fin
            ORDER BY bucket ASC
        """)
        rows = (await session.execute(sql, {
            "espacio_id": espacio_id,
            "inicio": fecha_inicio,
            "fin": fin_exclusive,
        })).fetchall()

        return [
            {
                "bucket":          r.bucket.isoformat(),
                "ingresos":        int(r.ingresos),
                "salidas":         int(r.salidas),
                "personas_unicas": int(r.personas_unicas),
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Heatmap semanal
    # ------------------------------------------------------------------
    @staticmethod
    async def get_heatmap(session: AsyncSession, espacio_id: int = 1) -> list[dict]:
        """
        Matriz: día_semana (0=Lun … 6=Dom) × hora (0-23) → ingresos_promedio.
        """
        sql = text("""
            SELECT
                EXTRACT(DOW FROM bucket)::int    AS dia_semana,
                EXTRACT(HOUR FROM bucket)::int   AS hora,
                ROUND(AVG(ingresos)::numeric, 2) AS ingresos_promedio
            FROM aforo_horario_biblioteca
            WHERE espacio_id = :espacio_id
            GROUP BY dia_semana, hora
            ORDER BY dia_semana, hora
        """)
        rows = (await session.execute(sql, {"espacio_id": espacio_id})).fetchall()
        # PostgreSQL DOW: 0=domingo → normalizar a ISO: 0=Lunes
        DOW_MAP = {0: 6, 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5}
        DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

        return [
            {
                "dia_semana":        DOW_MAP[r.dia_semana],
                "dia_nombre":        DIAS[DOW_MAP[r.dia_semana]],
                "hora":              r.hora,
                "ingresos_promedio": float(r.ingresos_promedio or 0),
            }
            for r in rows
        ]

    @staticmethod
    async def get_peak_valley_bands(session: AsyncSession, espacio_id: int = 1) -> list[dict]:
        sql = text("""
            SELECT 
                EXTRACT(HOUR FROM bucket)::int AS hora,
                ROUND(AVG(ingresos)::numeric, 1) AS promedio_ingresos,
                MAX(ingresos) AS max_ingresos,
                SUM(ingresos) AS total_ingresos
            FROM aforo_horario_biblioteca
            WHERE espacio_id = :espacio_id
            GROUP BY hora
            ORDER BY hora ASC
        """)
        rows = (await session.execute(sql, {"espacio_id": espacio_id})).fetchall()
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
    async def get_weekly_evolution(session: AsyncSession, espacio_id: int = 1) -> list[dict]:
        sql = text("""
            SELECT 
                EXTRACT(isoyear FROM time)::int || '-W' || LPAD(EXTRACT(week FROM time)::text, 2, '0') AS semana_iso,
                MIN(DATE(time)) AS inicio_semana,
                COUNT(*) AS total_asistencias,
                COUNT(DISTINCT person_id_hash) AS usuarios_unicos
            FROM eventos_asistencia
            WHERE espacio_id = :espacio_id
            GROUP BY semana_iso
            ORDER BY semana_iso ASC
        """)
        rows = (await session.execute(sql, {"espacio_id": espacio_id})).fetchall()
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
    async def get_monthly_volume(session: AsyncSession, espacio_id: int = 1) -> list[dict]:
        sql = text("""
            SELECT 
                TO_CHAR(time, 'YYYY-MM') AS mes,
                COUNT(*) AS total_asistencias,
                COUNT(DISTINCT DATE(time)) AS dias_activos,
                ROUND(COUNT(*)::numeric / NULLIF(COUNT(DISTINCT DATE(time)), 0), 1) AS promedio_diario
            FROM eventos_asistencia
            WHERE espacio_id = :espacio_id
            GROUP BY mes
            ORDER BY mes ASC
        """)
        rows = (await session.execute(sql, {"espacio_id": espacio_id})).fetchall()
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
    async def get_academic_milestones_comparison(session: AsyncSession, espacio_id: int = 1) -> list[dict]:
        sql = text("""
            WITH ad AS (
                SELECT DATE(time) AS dia, COUNT(*) AS total_dia
                FROM eventos_asistencia
                WHERE espacio_id = :espacio_id
                GROUP BY dia
            )
            SELECT 
                CASE 
                    WHEN ca.is_exam_period = TRUE THEN 'Exámenes / Certámenes'
                    WHEN ca.is_break = TRUE       THEN 'Receso Académico'
                    WHEN ca.is_holiday = TRUE     THEN 'Feriado'
                    ELSE 'Clases Regulares'
                END AS hito,
                COUNT(ad.dia) AS dias_totales,
                ROUND(AVG(ad.total_dia), 1) AS promedio_diario,
                COALESCE(MAX(ad.total_dia), 0) AS max_dia,
                SUM(ad.total_dia) AS total_asistencias
            FROM ad
            LEFT JOIN calendario_academico ca ON ad.dia = ca.fecha
            GROUP BY hito
            ORDER BY promedio_diario DESC
        """)
        rows = (await session.execute(sql, {"espacio_id": espacio_id})).fetchall()
        return [
            {
                "hito": r.hito,
                "dias_totales": int(r.dias_totales),
                "promedio_diario": float(r.promedio_diario or 0),
                "max_dia": int(r.max_dia or 0),
                "total_asistencias": int(r.total_asistencias or 0),
            }
            for r in rows
        ]

    @staticmethod
    async def get_door_usage(session: AsyncSession, espacio_id: int = 1) -> list[dict]:
        sql = text("""
            WITH entradas AS (
                SELECT NULLIF(REGEXP_REPLACE(door_entrada, '\\.0$', ''), 'nan') AS puerta, COUNT(*) AS entradas
                FROM eventos_asistencia
                WHERE espacio_id = :espacio_id
                GROUP BY puerta
            ),
            salidas AS (
                SELECT NULLIF(REGEXP_REPLACE(door_salida, '\\.0$', ''), 'nan') AS puerta, COUNT(*) AS salidas
                FROM eventos_asistencia
                WHERE espacio_id = :espacio_id
                GROUP BY puerta
            )
            SELECT 
                COALESCE(e.puerta, s.puerta) AS puerta,
                COALESCE(e.entradas, 0) AS entradas,
                COALESCE(s.salidas, 0) AS salidas
            FROM entradas e
            FULL OUTER JOIN salidas s ON e.puerta = s.puerta
            WHERE COALESCE(e.puerta, s.puerta) IS NOT NULL
            ORDER BY (COALESCE(e.entradas, 0) + COALESCE(s.salidas, 0)) DESC
        """)
        rows = (await session.execute(sql, {"espacio_id": espacio_id})).fetchall()
        return [
            {
                "puerta": f"Torniquete {r.puerta}",
                "puerta_id": r.puerta,
                "entradas": int(r.entradas),
                "salidas": int(r.salidas),
                "total": int(r.entradas + r.salidas),
            }
            for r in rows
        ]

    @staticmethod
    async def get_checkin_distribution(session: AsyncSession, espacio_id: int = 1) -> list[dict]:
        sql = text("""
            SELECT 
                marcajes_totales AS marcajes,
                COUNT(*) AS total_registros,
                ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS porcentaje
            FROM eventos_asistencia
            WHERE espacio_id = :espacio_id
            GROUP BY marcajes_totales
            ORDER BY marcajes_totales ASC
        """)
        rows = (await session.execute(sql, {"espacio_id": espacio_id})).fetchall()
        agrupado = {}
        for r in rows:
            m = int(r.marcajes)
            tot = int(r.total_registros)
            pct = float(r.porcentaje)
            label = str(m) if m <= 6 else "7+"
            if label not in agrupado:
                agrupado[label] = {"marcajes": label, "total_registros": 0, "porcentaje": 0.0}
            agrupado[label]["total_registros"] += tot
            agrupado[label]["porcentaje"] = round(agrupado[label]["porcentaje"] + pct, 2)
        return list(agrupado.values())


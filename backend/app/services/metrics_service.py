from datetime import date
from typing import Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class MetricsService:
    @staticmethod
    async def get_kpi_summary(
        session: AsyncSession,
        espacio_id: int = 1,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
    ) -> dict:
        if espacio_id == 2:
            sql = text("""
            WITH bounds AS (
                SELECT 
                    COALESCE(CAST(:fecha_inicio AS DATETIME2), (SELECT MIN(time) FROM eventos_vehiculares WHERE espacio_id = :espacio_id), CAST('2000-01-01' AS DATETIME2)) AS start_time,
                    COALESCE(DATEADD(day, 1, CAST(:fecha_fin AS DATETIME2)), (SELECT DATEADD(second, 1, MAX(time)) FROM eventos_vehiculares WHERE espacio_id = :espacio_id), CAST('2100-01-01' AS DATETIME2)) AS end_time
            ),
            kpis AS (
                SELECT
                    COALESCE(COUNT(DISTINCT CAST(ev.time AS DATE)), 0) AS dias_operativos,
                    0.0 AS horas_estudiante,
                    ROUND(CAST(COUNT(*) AS FLOAT) / NULLIF(COUNT(DISTINCT ev.patente_hash), 0), 1) AS recurrencia_mensual
                FROM eventos_vehiculares ev, bounds b
                WHERE ev.time >= b.start_time AND ev.time < b.end_time
                  AND ev.espacio_id = :espacio_id
                  AND ev.direccion = 'entrada'
            ),
            top_sector AS (
                SELECT TOP 1
                    CASE 
                        WHEN ev.camara LIKE '%CSF11%' THEN 'CSF11 — Edificio 11'
                        WHEN ev.camara LIKE '%CSF21%' THEN 'CSF21 — Edificio 21'
                        WHEN ev.camara LIKE '%CHS01%' THEN 'CHS01 — Hosp. Simulación'
                        ELSE ev.camara
                    END AS sector_top
                FROM eventos_vehiculares ev, bounds b
                WHERE ev.time >= b.start_time AND ev.time < b.end_time
                  AND ev.espacio_id = :espacio_id
                  AND ev.direccion = 'entrada'
                GROUP BY CASE 
                        WHEN ev.camara LIKE '%CSF11%' THEN 'CSF11 — Edificio 11'
                        WHEN ev.camara LIKE '%CSF21%' THEN 'CSF21 — Edificio 21'
                        WHEN ev.camara LIKE '%CHS01%' THEN 'CHS01 — Hosp. Simulación'
                        ELSE ev.camara
                    END
                ORDER BY COUNT(*) DESC
            ),
            peak_hour AS (
                SELECT TOP 1
                    DATEPART(hour, ev.time) AS hora
                FROM eventos_vehiculares ev, bounds b
                WHERE ev.time >= b.start_time AND ev.time < b.end_time
                  AND ev.espacio_id = :espacio_id
                  AND ev.direccion = 'entrada'
                GROUP BY DATEPART(hour, ev.time)
                ORDER BY COUNT(*) DESC
            ),
            max_hourly AS (
                SELECT COALESCE(MAX(entradas), 0) AS pico_concurrente
                FROM aforo_horario_estacionamiento, bounds b
                WHERE bucket >= b.start_time AND bucket < b.end_time
                  AND espacio_id = :espacio_id
            )
            SELECT
                kp.dias_operativos,
                kp.horas_estudiante,
                kp.recurrencia_mensual,
                (SELECT hora FROM peak_hour) AS hora_pico,
                mh.pico_concurrente,
                (SELECT sector_top FROM top_sector) AS sector_mas_concurrido,
                CAST(NULL AS NVARCHAR(255)) AS carrera_mas_concurrida
            FROM kpis kp
            CROSS JOIN max_hourly mh;
            """)
        else:
            sql = text("""
            WITH bounds AS (
                SELECT 
                    COALESCE(CAST(:fecha_inicio AS DATETIME2), (SELECT MIN(time) FROM eventos_asistencia WHERE espacio_id = :espacio_id), CAST('2000-01-01' AS DATETIME2)) AS start_time,
                    COALESCE(DATEADD(day, 1, CAST(:fecha_fin AS DATETIME2)), (SELECT DATEADD(second, 1, MAX(time)) FROM eventos_asistencia WHERE espacio_id = :espacio_id), CAST('2100-01-01' AS DATETIME2)) AS end_time
            ),
            kpis AS (
                SELECT
                    COALESCE(COUNT(DISTINCT CAST(ea.time AS DATE)), 0) AS dias_operativos,
                    ROUND(COALESCE(SUM(ea.permanencia_min), 0) / 60.0, 0) AS horas_estudiante,
                    ROUND(CAST(COUNT(*) AS FLOAT) / NULLIF(COUNT(DISTINCT ea.person_id_hash), 0), 1) AS recurrencia_mensual
                FROM eventos_asistencia ea, bounds b
                WHERE ea.time >= b.start_time AND ea.time < b.end_time
                  AND ea.espacio_id = :espacio_id
                  AND ea.alerta_coherencia_fechas = 0
            ),
            top_career AS (
                SELECT TOP 1
                    ea.carrera
                FROM eventos_asistencia ea, bounds b
                WHERE ea.time >= b.start_time AND ea.time < b.end_time
                  AND ea.espacio_id = :espacio_id
                  AND ea.carrera IS NOT NULL
                  AND ea.carrera != 'Sin carrera catalogada'
                  AND ea.carrera != ''
                GROUP BY ea.carrera
                ORDER BY COUNT(*) DESC
            ),
            peak_hour AS (
                SELECT TOP 1
                    DATEPART(hour, ea.time) AS hora
                FROM eventos_asistencia ea, bounds b
                WHERE ea.time >= b.start_time AND ea.time < b.end_time
                  AND ea.espacio_id = :espacio_id
                GROUP BY DATEPART(hour, ea.time)
                ORDER BY COUNT(*) DESC
            ),
            max_hourly AS (
                SELECT COALESCE(MAX(ingresos), 0) AS pico_concurrente
                FROM aforo_horario_biblioteca, bounds b
                WHERE bucket >= b.start_time AND bucket < b.end_time
                  AND espacio_id = :espacio_id
            )
            SELECT
                kp.dias_operativos,
                kp.horas_estudiante,
                kp.recurrencia_mensual,
                (SELECT hora FROM peak_hour) AS hora_pico,
                mh.pico_concurrente,
                (SELECT carrera FROM top_career) AS carrera_mas_concurrida
            FROM kpis kp
            CROSS JOIN max_hourly mh;
            """)

        row = (
            await session.execute(
                sql,
                {
                    "espacio_id": espacio_id,
                    "fecha_inicio": fecha_inicio,
                    "fecha_fin": fecha_fin,
                },
            )
        ).fetchone()

        default_hora = "08:00 hrs" if espacio_id == 2 else "14:00 hrs"
        if not row:
            return {
                "dias_operativos": 0,
                "horas_estudiante": 0.0,
                "recurrencia_mensual": 0.0,
                "hora_pico_ingreso": default_hora,
                "pico_concurrente": 0,
                "carrera_mas_concurrida": None,
                "sector_mas_concurrido": None,
                "periodo_label": None,
            }

        periodo_label = (
            f"{fecha_inicio} a {fecha_fin}"
            if fecha_inicio and fecha_fin
            else "Historial Semestre Completo"
        )

        hora_pico_str = f"{row.hora_pico:02d}:00 hrs" if row.hora_pico is not None else default_hora

        return {
            "dias_operativos": int(row.dias_operativos or 0),
            "horas_estudiante": float(row.horas_estudiante or 0.0),
            "recurrencia_mensual": float(row.recurrencia_mensual or 0.0),
            "hora_pico_ingreso": hora_pico_str,
            "pico_concurrente": int(row.pico_concurrente or 0),
            "carrera_mas_concurrida": getattr(row, "carrera_mas_concurrida", None),
            "sector_mas_concurrido": getattr(row, "sector_mas_concurrido", None),
            "periodo_label": periodo_label,
        }

    @staticmethod
    async def get_date_bounds(
        session: AsyncSession,
        espacio_id: Optional[int] = None,
    ) -> dict:
        import calendar

        if espacio_id == 2:
            query = text("""
                SELECT 
                    CAST(MIN(time) AS DATE) AS fecha_min,
                    CAST(MAX(time) AS DATE) AS fecha_max
                FROM eventos_vehiculares
                WHERE espacio_id = :espacio_id
            """)
            result = (await session.execute(query, {"espacio_id": espacio_id})).fetchone()
        elif espacio_id == 1:
            query = text("""
                SELECT 
                    CAST(MIN(time) AS DATE) AS fecha_min,
                    CAST(MAX(time) AS DATE) AS fecha_max
                FROM eventos_asistencia
                WHERE espacio_id = :espacio_id
            """)
            result = (await session.execute(query, {"espacio_id": espacio_id})).fetchone()
        else:
            query = text("""
                SELECT 
                    MIN(f_min) AS fecha_min,
                    MAX(f_max) AS fecha_max
                FROM (
                    SELECT CAST(MIN(time) AS DATE) AS f_min, CAST(MAX(time) AS DATE) AS f_max FROM eventos_asistencia
                    UNION ALL
                    SELECT CAST(MIN(time) AS DATE) AS f_min, CAST(MAX(time) AS DATE) AS f_max FROM eventos_vehiculares
                ) t
            """)
            result = (await session.execute(query)).fetchone()

        month_names = [
            "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
            "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
        ]

        if not result or not result.fecha_min or not result.fecha_max:
            d_min = date(2026, 3, 1)
            d_max = date(2026, 10, 31)
        else:
            d_min = result.fecha_min
            d_max = result.fecha_max

        meses = []
        cur_year = d_min.year
        cur_month = d_min.month
        end_year = d_max.year
        end_month = d_max.month

        while (cur_year < end_year) or (cur_year == end_year and cur_month <= end_month):
            last_day = calendar.monthrange(cur_year, cur_month)[1]
            m_label = f"Mes de {month_names[cur_month - 1]} {cur_year}"
            m_inicio = f"{cur_year:04d}-{cur_month:02d}-01"
            m_fin = f"{cur_year:04d}-{cur_month:02d}-{last_day:02d}"
            meses.append({
                "label": m_label,
                "inicio": m_inicio,
                "fin": m_fin,
                "year": cur_year,
                "month": cur_month,
            })
            if cur_month == 12:
                cur_month = 1
                cur_year += 1
            else:
                cur_month += 1

        return {
            "fecha_min": d_min.isoformat(),
            "fecha_max": d_max.isoformat(),
            "espacio_id": espacio_id,
            "meses_disponibles": meses,
        }

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
                    COALESCE(CAST(:fecha_inicio AS timestamptz), (SELECT MIN(time) FROM eventos_vehiculares WHERE espacio_id = :espacio_id)) AS start_time,
                    COALESCE(CAST(:fecha_fin AS timestamptz) + INTERVAL '1 day', (SELECT MAX(time) + INTERVAL '1 second' FROM eventos_vehiculares WHERE espacio_id = :espacio_id)) AS end_time
            ),
            kpis AS (
                SELECT
                    COALESCE(COUNT(DISTINCT DATE(ev.time)), 0) AS dias_operativos,
                    0.0 AS horas_estudiante,
                    ROUND(COUNT(*)::numeric / NULLIF(COUNT(DISTINCT ev.patente_hash), 0), 1) AS recurrencia_mensual
                FROM eventos_vehiculares ev, bounds b
                WHERE ev.time >= b.start_time AND ev.time < b.end_time
                  AND ev.espacio_id = :espacio_id
                  AND ev.direccion = 'entrada'
            ),
            peak_hour AS (
                SELECT
                    COALESCE(TO_CHAR(DATE_TRUNC('hour', ev.time), 'HH24:00 hrs'), '08:00 hrs') AS hora_pico_ingreso
                FROM eventos_vehiculares ev, bounds b
                WHERE ev.time >= b.start_time AND ev.time < b.end_time
                  AND ev.espacio_id = :espacio_id
                  AND ev.direccion = 'entrada'
                GROUP BY EXTRACT(HOUR FROM ev.time), TO_CHAR(DATE_TRUNC('hour', ev.time), 'HH24:00 hrs')
                ORDER BY COUNT(*) DESC
                LIMIT 1
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
                ph.hora_pico_ingreso,
                mh.pico_concurrente
            FROM kpis kp
            CROSS JOIN peak_hour ph
            CROSS JOIN max_hourly mh;
            """)
        else:
            sql = text("""
            WITH bounds AS (
                SELECT 
                    COALESCE(CAST(:fecha_inicio AS timestamptz), (SELECT MIN(time) FROM eventos_asistencia WHERE espacio_id = :espacio_id)) AS start_time,
                    COALESCE(CAST(:fecha_fin AS timestamptz) + INTERVAL '1 day', (SELECT MAX(time) + INTERVAL '1 second' FROM eventos_asistencia WHERE espacio_id = :espacio_id)) AS end_time
            ),
            kpis AS (
                SELECT
                    COALESCE(COUNT(DISTINCT DATE(ea.time)), 0) AS dias_operativos,
                    ROUND(COALESCE(SUM(ea.permanencia_min), 0) / 60.0, 0) AS horas_estudiante,
                    ROUND(COUNT(*)::numeric / NULLIF(COUNT(DISTINCT ea.person_id_hash), 0), 1) AS recurrencia_mensual
                FROM eventos_asistencia ea, bounds b
                WHERE ea.time >= b.start_time AND ea.time < b.end_time
                  AND ea.espacio_id = :espacio_id
                  AND ea.alerta_coherencia_fechas = FALSE
            ),
            peak_hour AS (
                SELECT
                    COALESCE(TO_CHAR(DATE_TRUNC('hour', ea.time), 'HH24:00 hrs'), '14:00 hrs') AS hora_pico_ingreso
                FROM eventos_asistencia ea, bounds b
                WHERE ea.time >= b.start_time AND ea.time < b.end_time
                  AND ea.espacio_id = :espacio_id
                GROUP BY EXTRACT(HOUR FROM ea.time), TO_CHAR(DATE_TRUNC('hour', ea.time), 'HH24:00 hrs')
                ORDER BY COUNT(*) DESC
                LIMIT 1
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
                ph.hora_pico_ingreso,
                mh.pico_concurrente
            FROM kpis kp
            CROSS JOIN peak_hour ph
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

        if not row:
            return {
                "dias_operativos": 0,
                "horas_estudiante": 0.0,
                "recurrencia_mensual": 0.0,
                "hora_pico_ingreso": "14:00 hrs",
                "pico_concurrente": 0,
                "periodo_label": None,
            }

        periodo_label = (
            f"{fecha_inicio} a {fecha_fin}"
            if fecha_inicio and fecha_fin
            else "Historial Semestre Completo"
        )

        return {
            "dias_operativos": int(row.dias_operativos or 0),
            "horas_estudiante": float(row.horas_estudiante or 0.0),
            "recurrencia_mensual": float(row.recurrencia_mensual or 0.0),
            "hora_pico_ingreso": str(row.hora_pico_ingreso or "14:00 hrs"),
            "pico_concurrente": int(row.pico_concurrente or 0),
            "periodo_label": periodo_label,
        }

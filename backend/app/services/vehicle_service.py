"""
VehicleService — Consultas sobre Continuous Aggregates de estacionamiento.
"""
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

CAPACIDAD_ESTACIONAMIENTO = 180
UMBRAL_ALERTA_90 = 0.90


class VehicleService:

    # ------------------------------------------------------------------
    # KPIs generales
    # ------------------------------------------------------------------
    @staticmethod
    async def get_kpis(session: AsyncSession, espacio_id: int = 2) -> dict:
        sql_global = text("""
            SELECT
                COUNT(DISTINCT patente_hash)                         AS vehiculos_unicos,
                COUNT(*) FILTER (WHERE direccion = 'entrada')        AS total_entradas,
                COUNT(DISTINCT DATE(time))                           AS dias_operativos,
                ROUND(
                    100.0 * COUNT(*) FILTER (WHERE calidad_lectura = 'unknown')
                    / NULLIF(COUNT(*), 0),
                2)                                                   AS tasa_lectura_fallida_pct
            FROM eventos_vehiculares
            WHERE espacio_id = :espacio_id
        """)
        row_g = (await session.execute(sql_global, {"espacio_id": espacio_id})).one()

        dias = row_g.dias_operativos or 1
        entradas = row_g.total_entradas or 0

        # Turnover rate = total_entradas_diarias / capacidad_plazas
        turnover = round(entradas / dias / CAPACIDAD_ESTACIONAMIENTO, 2)

        # Permanencia mediana desde pares entrada/salida en raw (query simplificada)
        sql_perm = text("""
            SELECT ROUND(
                PERCENTILE_CONT(0.5) WITHIN GROUP (
                    ORDER BY EXTRACT(EPOCH FROM (sal.time - ent.time)) / 60.0
                )::numeric, 2
            ) AS permanencia_mediana_min
            FROM eventos_vehiculares ent
            JOIN eventos_vehiculares sal
              ON ent.patente_hash = sal.patente_hash
             AND ent.espacio_id   = sal.espacio_id
             AND sal.time > ent.time
             AND sal.time < ent.time + INTERVAL '24 hours'
             AND ent.direccion = 'entrada'
             AND sal.direccion = 'salida'
            WHERE ent.espacio_id = :espacio_id
        """)
        row_p = (await session.execute(sql_perm, {"espacio_id": espacio_id})).first()
        sql_peak = text("""
            SELECT EXTRACT(HOUR FROM bucket)::int AS hora, SUM(entradas) AS total
            FROM aforo_horario_estacionamiento
            WHERE espacio_id = :espacio_id
            GROUP BY hora
            ORDER BY total DESC
            LIMIT 1
        """)
        row_peak = (await session.execute(sql_peak, {"espacio_id": espacio_id})).first()
        hora_punta = f"{row_peak.hora:02d}:00 hrs" if row_peak and row_peak.hora is not None else "08:00 hrs"

        sql_max = text("""
            SELECT COALESCE(MAX(entradas), 0) AS max_entradas
            FROM aforo_horario_estacionamiento
            WHERE espacio_id = :espacio_id
        """)
        max_entradas = (await session.execute(sql_max, {"espacio_id": espacio_id})).scalar() or 0

        return {
            "vehiculos_unicos":          int(row_g.vehiculos_unicos or 0),
            "total_accesos":             int(entradas),
            "dias_operativos":           int(dias),
            "turnover_rate_diario":      turnover,
            "permanencia_mediana_min":   float(row_p.permanencia_mediana_min or 0),
            "tasa_lectura_fallida_pct":  float(row_g.tasa_lectura_fallida_pct or 0),
            "hora_punta":                hora_punta,
            "max_aforo_historico":       int(max_entradas),
        }

    # ------------------------------------------------------------------
    # Aforo vehicular en tiempo real
    # ------------------------------------------------------------------
    @staticmethod
    async def get_parking_occupancy(session: AsyncSession, espacio_id: int = 2) -> dict:
        sql_date = text("""
            SELECT COALESCE(MAX(DATE(bucket)), CURRENT_DATE)
            FROM aforo_horario_estacionamiento
            WHERE espacio_id = :espacio_id
        """)
        target_date = (await session.execute(sql_date, {"espacio_id": espacio_id})).scalar() or date.today()

        sql = text("""
            SELECT
                COALESCE(SUM(entradas), 0) AS total_entradas,
                COALESCE(SUM(salidas),  0) AS total_salidas
            FROM aforo_horario_estacionamiento
            WHERE espacio_id = :espacio_id
              AND bucket >= :target_date
              AND bucket <  :target_date + INTERVAL '1 day'
        """)
        row = (await session.execute(sql, {"espacio_id": espacio_id, "target_date": target_date})).one()
        aforo = max(0, int(row.total_entradas) - int(row.total_salidas))
        disponibles = max(0, CAPACIDAD_ESTACIONAMIENTO - aforo)
        pct = round(aforo / CAPACIDAD_ESTACIONAMIENTO * 100, 1)

        nivel = "normal"
        if pct >= UMBRAL_ALERTA_90 * 100:
            nivel = "saturacion"
        elif pct >= 70:
            nivel = "preventivo"

        return {
            "vehiculos_presentes": aforo,
            "plazas_disponibles":  disponibles,
            "capacidad_maxima":    CAPACIDAD_ESTACIONAMIENTO,
            "ocupacion_pct":       pct,
            "nivel_alerta":        nivel,
            "timestamp":           datetime.combine(target_date, datetime.min.time()).isoformat(),
        }

    @staticmethod
    async def get_hourly_flow(
        session: AsyncSession,
        fecha_inicio: Optional[date],
        fecha_fin: Optional[date],
        espacio_id: int = 2,
    ) -> list[dict]:
        if fecha_inicio is None or fecha_fin is None:
            sql_max = text("""
                SELECT COALESCE(MAX(DATE(bucket)), CURRENT_DATE)
                FROM aforo_horario_estacionamiento
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
                COALESCE(SUM(entradas), 0)         AS entradas,
                COALESCE(SUM(salidas),  0)          AS salidas,
                COALESCE(SUM(lecturas_fallidas), 0) AS lecturas_fallidas
            FROM aforo_horario_estacionamiento
            WHERE espacio_id = :espacio_id
              AND bucket >= :inicio
              AND bucket <  :fin
            GROUP BY bucket
            ORDER BY bucket ASC
        """)
        rows = (await session.execute(sql, {
            "espacio_id": espacio_id,
            "inicio": fecha_inicio,
            "fin": fin_exclusive,
        })).fetchall()

        return [
            {
                "bucket":           r.bucket.isoformat(),
                "entradas":         int(r.entradas),
                "salidas":          int(r.salidas),
                "lecturas_fallidas": int(r.lecturas_fallidas),
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Composición de flota (donut chart)
    # ------------------------------------------------------------------
    @staticmethod
    async def get_fleet_composition(session: AsyncSession, espacio_id: int = 2) -> dict:
        sql_tipo = text("""
            SELECT
                COALESCE(tipo_vehiculo, 'Desconocido') AS tipo,
                COUNT(*)                                AS total,
                ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct
            FROM eventos_vehiculares
            WHERE espacio_id   = :espacio_id
              AND direccion     = 'entrada'
              AND calidad_lectura = 'ok'
            GROUP BY tipo_vehiculo
            ORDER BY total DESC
        """)
        sql_marca = text("""
            SELECT
                COALESCE(marca, 'Desconocida') AS marca,
                COUNT(*)                        AS total,
                ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct
            FROM eventos_vehiculares
            WHERE espacio_id    = :espacio_id
              AND direccion      = 'entrada'
              AND calidad_lectura = 'ok'
            GROUP BY marca
            ORDER BY total DESC
            LIMIT 10
        """)
        rows_tipo  = (await session.execute(sql_tipo,  {"espacio_id": espacio_id})).fetchall()
        rows_marca = (await session.execute(sql_marca, {"espacio_id": espacio_id})).fetchall()

        return {
            "por_tipo":  [{"tipo": r.tipo,   "total": int(r.total), "pct": float(r.pct)} for r in rows_tipo],
            "por_marca": [{"marca": r.marca, "total": int(r.total), "pct": float(r.pct)} for r in rows_marca],
        }

    @staticmethod
    async def get_daily_evolution(session: AsyncSession, espacio_id: int = 2) -> list[dict]:
        sql = text("""
            SELECT 
                DATE(time) AS fecha,
                COUNT(*) FILTER (WHERE direccion = 'entrada') AS entradas,
                COUNT(*) FILTER (WHERE direccion = 'salida') AS salidas,
                COUNT(DISTINCT patente_hash) AS vehiculos_unicos
            FROM eventos_vehiculares
            WHERE espacio_id = :espacio_id
            GROUP BY fecha
            ORDER BY fecha ASC
        """)
        rows = (await session.execute(sql, {"espacio_id": espacio_id})).fetchall()
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
            WITH vd AS (
                SELECT DATE(time) AS dia, COUNT(*) FILTER (WHERE direccion = 'entrada') AS total_dia
                FROM eventos_vehiculares
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
                COUNT(vd.dia) AS dias_totales,
                ROUND(AVG(vd.total_dia), 1) AS promedio_diario,
                COALESCE(MAX(vd.total_dia), 0) AS max_dia,
                SUM(vd.total_dia) AS total_accesos
            FROM vd
            LEFT JOIN calendario_academico ca ON vd.dia = ca.fecha
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
                    DATE(time) as fecha,
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
                    ROUND(EXTRACT(EPOCH FROM (c2.time - c1.time)) / 60.0) as minutos_traslado,
                    EXTRACT(HOUR FROM c1.time)::int as hora_salida
                FROM eventos_campus c1
                JOIN eventos_campus c2
                  ON c1.patente_hash = c2.patente_hash
                 AND c1.fecha = c2.fecha
                 AND c1.campus != c2.campus
                 AND c2.time > c1.time
                 AND c2.time <= c1.time + INTERVAL '6 hours'
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



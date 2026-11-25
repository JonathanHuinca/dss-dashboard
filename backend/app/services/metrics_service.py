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
        sector: Optional[str] = None,
        tipo_vehiculo: Optional[str] = None,
        incluir_pausas_bano: bool = True,
        desduplicar_rafagas: bool = True,
        incluir_funcionarios: bool = True,
        incluir_sin_identificar: bool = True,
    ) -> dict:
        if espacio_id == 2:
            from app.services.vehicle_service import VehicleService, _extraer_hora_pico_curva_vehicular

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
            solo_salidas = (direccion or "todos").strip().lower() in ("out", "solo_salida")
            filtro_dir_metrica = "" if solo_salidas else "AND direccion = 'entrada'"

            sql = text(f"""
            WITH kpis AS (
                SELECT
                    COALESCE(COUNT(DISTINCT CAST(time AS DATE)), 0) AS dias_operativos,
                    0.0 AS horas_estudiante,
                    COALESCE(
                        ROUND(
                            CAST(NULLIF(SUM(CASE WHEN direccion = 'entrada' THEN 1 ELSE 0 END), 0) AS FLOAT)
                            / NULLIF(COUNT(DISTINCT CASE WHEN direccion = 'entrada' THEN patente_hash END), 0),
                        1),
                        ROUND(CAST(COUNT(*) AS FLOAT) / NULLIF(COUNT(DISTINCT patente_hash), 0), 1),
                        0.0
                    ) AS recurrencia_mensual
                FROM eventos_vehiculares
                WHERE {where_sql}
                  AND time <= GETDATE()
            ),
            top_sector AS (
                SELECT TOP 1
                    CASE
                        WHEN camara LIKE '%CSF11%' THEN 'CSF11 — Edificio 11'
                        WHEN camara LIKE '%CSF21%' THEN 'CSF21 — Edificio 21'
                        WHEN camara LIKE '%CHS01%' THEN 'CHS01 — Hosp. Simulación'
                        ELSE camara
                    END AS sector_top
                FROM eventos_vehiculares
                WHERE {where_sql}
                  AND time <= GETDATE()
                  {filtro_dir_metrica}
                GROUP BY CASE
                        WHEN camara LIKE '%CSF11%' THEN 'CSF11 — Edificio 11'
                        WHEN camara LIKE '%CSF21%' THEN 'CSF21 — Edificio 21'
                        WHEN camara LIKE '%CHS01%' THEN 'CHS01 — Hosp. Simulación'
                        ELSE camara
                    END
                ORDER BY COUNT(*) DESC
            ),
            peak_hour AS (
                SELECT TOP 1
                    DATEPART(hour, time) AS hora
                FROM eventos_vehiculares
                WHERE {where_sql}
                  AND time <= GETDATE()
                  {filtro_dir_metrica}
                GROUP BY DATEPART(hour, time)
                ORDER BY COUNT(*) DESC
            )
            SELECT
                kp.dias_operativos,
                kp.horas_estudiante,
                kp.recurrencia_mensual,
                (SELECT hora FROM peak_hour) AS hora_pico,
                (SELECT sector_top FROM top_sector) AS sector_mas_concurrido,
                CAST(NULL AS NVARCHAR(255)) AS carrera_mas_concurrida
            FROM kpis kp;
            """)
            row = (await session.execute(sql, params)).fetchone()

            curva = await VehicleService.get_realtime_presence_curve(
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
            pico_concurrente = max((int(r.get("vehiculos_presentes", 0)) for r in curva), default=0)

            periodo_label = (
                f"{fecha_inicio} a {fecha_fin}"
                if fecha_inicio and fecha_fin
                else "Historial Semestre Completo"
            )
            if not row:
                return {
                    "dias_operativos": 0,
                    "horas_estudiante": 0.0,
                    "recurrencia_mensual": 0.0,
                    "hora_pico_ingreso": "08:00 hrs",
                    "pico_concurrente": pico_concurrente,
                    "carrera_mas_concurrida": None,
                    "sector_mas_concurrido": None,
                    "periodo_label": periodo_label,
                }
            hora_pico_str = _extraer_hora_pico_curva_vehicular(curva) or (
                f"{row.hora_pico:02d}:00 hrs" if row.hora_pico is not None else "08:00 hrs"
            )
            return {
                "dias_operativos": int(row.dias_operativos or 0),
                "horas_estudiante": float(row.horas_estudiante or 0.0),
                "recurrencia_mensual": float(row.recurrencia_mensual or 0.0),
                "hora_pico_ingreso": hora_pico_str,
                "pico_concurrente": pico_concurrente,
                "carrera_mas_concurrida": None,
                "sector_mas_concurrido": getattr(row, "sector_mas_concurrido", None),
                "periodo_label": periodo_label,
            }
        else:
            from app.services.attendance_service import AttendanceService, _extraer_hora_pico_curva
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
            WITH kpis AS (
                SELECT
                    COALESCE(COUNT(DISTINCT CAST(time AS DATE)), 0) AS dias_operativos,
                    ROUND(COALESCE(SUM(permanencia_min), 0) / 60.0, 0) AS horas_estudiante,
                    ROUND(CAST(COUNT(*) AS FLOAT) / NULLIF(COUNT(DISTINCT person_id_hash), 0), 1) AS recurrencia_mensual
                FROM eventos_asistencia
                WHERE {where_sql}
            ),
            top_career AS (
                SELECT TOP 1
                    carrera
                FROM eventos_asistencia
                WHERE {where_sql}
                  AND carrera IS NOT NULL
                  AND carrera != 'Sin carrera catalogada'
                  AND carrera != ''
                GROUP BY carrera
                ORDER BY COUNT(*) DESC
            ),
            peak_hour AS (
                SELECT TOP 1
                    DATEPART(hour, time) AS hora
                FROM eventos_asistencia
                WHERE {where_sql}
                GROUP BY DATEPART(hour, time)
                ORDER BY COUNT(*) DESC
            )
            SELECT
                kp.dias_operativos,
                kp.horas_estudiante,
                kp.recurrencia_mensual,
                (SELECT hora FROM peak_hour) AS hora_pico,
                (SELECT carrera FROM top_career) AS carrera_mas_concurrida
            FROM kpis kp;
            """)

            row = (await session.execute(sql, params)).fetchone()

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
            pico_concurrente = max((int(r.get("personas_unicas", 0)) for r in curva), default=0)

            default_hora = "14:00 hrs"
            if not row:
                return {
                    "dias_operativos": 0,
                    "horas_estudiante": 0.0,
                    "recurrencia_mensual": 0.0,
                    "hora_pico_ingreso": default_hora,
                    "pico_concurrente": pico_concurrente,
                    "carrera_mas_concurrida": None,
                    "sector_mas_concurrido": None,
                    "periodo_label": None,
                }

            periodo_label = (
                f"{fecha_inicio} a {fecha_fin}"
                if fecha_inicio and fecha_fin
                else "Historial Semestre Completo"
            )

            hora_pico_str = _extraer_hora_pico_curva(curva) or (
                f"{row.hora_pico:02d}:00 hrs" if row.hora_pico is not None else default_hora
            )

            return {
                "dias_operativos": int(row.dias_operativos or 0),
                "horas_estudiante": float(row.horas_estudiante or 0.0),
                "recurrencia_mensual": float(row.recurrencia_mensual or 0.0),
                "hora_pico_ingreso": hora_pico_str,
                "pico_concurrente": pico_concurrente,
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

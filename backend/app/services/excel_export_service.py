import io
import re
import math
from datetime import datetime, date
from typing import Dict, List, Set, Optional, Any, Union
try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.excel_export_schemas import (
    SolicitudExportacionExcel,
    GraficoNativoPayload,
    SerieGrafico,
)

COLORES_UCT = [
    "#002B49",  # Azul Institucional Primario
    "#C59B27",  # Dorado UCT
    "#0284C7",  # Celeste Sky
    "#10B981",  # Verde Esmeralda
    "#8B5CF6",  # Púrpura
    "#F59E0B",  # Ámbar
    "#EF4444",  # Rojo Alerta
    "#06B6D4",  # Cian
    "#64748B",  # Pizarra
    "#EC4899",  # Rosa
]


def sanear_nombre_hoja(nombre: str, nombres_existentes: Set[str]) -> str:
    """Sanea el nombre de pestaña a un máximo de 31 caracteres válidos para Excel."""
    limpio = re.sub(r"[\\/?*:[\]']", "", nombre).strip()[:31]
    if not limpio:
        limpio = "Hoja"

    resultado = limpio
    contador = 1
    while resultado.lower() in nombres_existentes:
        sufijo = f"_{contador}"
        base = limpio[: 31 - len(sufijo)]
        resultado = f"{base}{sufijo}"
        contador += 1

    nombres_existentes.add(resultado.lower())
    return resultado


class ExcelExportService:
    @staticmethod
    def generar_excel_nativo(solicitud: SolicitudExportacionExcel) -> bytes:
        """
        Genera un archivo Excel (.xlsx) con objetos OpenXML de gráficos nativos,
        vinculados dinámicamente a tablas de celdas de datos con estilo institucional UCT.
        """
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True, "nan_inf_to_errors": True})

        # Estilos y formatos
        fmt_titulo_resumen = workbook.add_format({
            "bold": True,
            "font_size": 12,
            "font_name": "Arial",
            "bg_color": "#002B49",
            "font_color": "#FFFFFF",
            "align": "center",
            "valign": "vcenter",
        })

        fmt_subtitulo_resumen = workbook.add_format({
            "bold": True,
            "font_size": 10,
            "font_name": "Arial",
            "bg_color": "#F1F5F9",
            "font_color": "#1E293B",
            "align": "left",
            "valign": "vcenter",
        })

        fmt_seccion = workbook.add_format({
            "bold": True,
            "font_size": 10,
            "font_name": "Arial",
            "font_color": "#002B49",
            "bottom": 1,
            "bottom_color": "#002B49",
        })

        fmt_th = workbook.add_format({
            "bold": True,
            "font_size": 9,
            "font_name": "Arial",
            "bg_color": "#002B49",
            "font_color": "#FFFFFF",
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "border_color": "#001A2C",
        })

        fmt_td_text = workbook.add_format({
            "font_size": 9,
            "font_name": "Arial",
            "align": "left",
            "valign": "vcenter",
            "border": 1,
            "border_color": "#E2E8F0",
        })

        fmt_td_num = workbook.add_format({
            "font_size": 9,
            "font_name": "Arial",
            "align": "right",
            "valign": "vcenter",
            "num_format": "#,##0.0",
            "border": 1,
            "border_color": "#E2E8F0",
        })

        fmt_td_int = workbook.add_format({
            "font_size": 9,
            "font_name": "Arial",
            "align": "right",
            "valign": "vcenter",
            "num_format": "#,##0",
            "border": 1,
            "border_color": "#E2E8F0",
        })

        fmt_td_text_alt = workbook.add_format({
            "font_size": 9,
            "font_name": "Arial",
            "align": "left",
            "valign": "vcenter",
            "bg_color": "#F8FAFC",
            "border": 1,
            "border_color": "#E2E8F0",
        })

        fmt_td_num_alt = workbook.add_format({
            "font_size": 9,
            "font_name": "Arial",
            "align": "right",
            "valign": "vcenter",
            "bg_color": "#F8FAFC",
            "num_format": "#,##0.0",
            "border": 1,
            "border_color": "#E2E8F0",
        })

        fmt_td_int_alt = workbook.add_format({
            "font_size": 9,
            "font_name": "Arial",
            "align": "right",
            "valign": "vcenter",
            "bg_color": "#F8FAFC",
            "num_format": "#,##0",
            "border": 1,
            "border_color": "#E2E8F0",
        })

        fecha_str = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        nombres_usados: Set[str] = set()

        # Si hay más de un gráfico, crear primero la hoja de Resumen Ejecutivo
        ws_resumen = None
        fila_indice = 10
        if len(solicitud.graficos) > 1:
            ws_resumen = workbook.add_worksheet("Resumen_Ejecutivo")
            ws_resumen.set_tab_color("#002B49")
            nombres_usados.add("resumen_ejecutivo")

            ws_resumen.merge_range(
                "A1:F1",
                "SISTEMA DE APOYO A LA TOMA DE DECISIONES (DSS) — UNIVERSIDAD CATÓLICA DE TEMUCO",
                fmt_titulo_resumen,
            )
            ws_resumen.merge_range(
                "A2:F2",
                f"REPORTE CONSOLIDADO DE GRÁFICOS NATIVOS EDITABLES — {solicitud.modulo_nombre.upper()}",
                fmt_subtitulo_resumen,
            )
            ws_resumen.write("A3", f"Generado el: {fecha_str} | Período: {solicitud.periodo_label}")

            # Filtros aplicados
            ws_resumen.write("A5", "PARÁMETROS Y FILTROS DEL REPORTE:", fmt_seccion)
            f_row = 6
            if solicitud.filtros:
                for k, v in solicitud.filtros.items():
                    ws_resumen.write(f_row, 0, f"• {k}:", fmt_td_text)
                    ws_resumen.write(f_row, 1, str(v), fmt_td_text)
                    f_row += 1
            else:
                ws_resumen.write(f_row, 0, "• Filtros:", fmt_td_text)
                ws_resumen.write(f_row, 1, "Configuración activa en el panel", fmt_td_text)
                f_row += 1

            f_row += 1
            ws_resumen.write(f_row, 0, "ÍNDICE DE GRÁFICOS NATIVOS CONTENIDOS:", fmt_seccion)
            f_row += 1

            headers_indice = ["N°", "Pestaña Excel", "Nombre del Gráfico", "Categoría", "Tipo Gráfico", "Puntos / Filas"]
            for c_idx, h in enumerate(headers_indice):
                ws_resumen.write(f_row, c_idx, h, fmt_th)
            ws_resumen.set_row(f_row, 22)
            fila_indice = f_row + 1

            ws_resumen.set_column(0, 0, 6)
            ws_resumen.set_column(1, 1, 24)
            ws_resumen.set_column(2, 2, 45)
            ws_resumen.set_column(3, 3, 22)
            ws_resumen.set_column(4, 4, 16)
            ws_resumen.set_column(5, 5, 18)

        # Procesar cada gráfico nativo
        idx_grafico = 1
        for g in solicitud.graficos:
            sheet_name = sanear_nombre_hoja(g.titulo, nombres_usados)
            ws = workbook.add_worksheet(sheet_name)
            ws.set_tab_color("#C59B27")

            # Encabezado institucional de la hoja
            ws.merge_range(
                "A1:H1",
                "SISTEMA DE APOYO A LA TOMA DE DECISIONES (DSS) — UNIVERSIDAD CATÓLICA DE TEMUCO",
                fmt_titulo_resumen,
            )
            ws.merge_range(
                "A2:H2",
                f"GRÁFICO NATIVO OPENXML: {g.titulo.upper()} ({g.categoria})",
                fmt_subtitulo_resumen,
            )
            ws.write("A3", f"Generado: {fecha_str} | Campus San Francisco | Datos vinculados dinámicamente")
            ws.set_row(0, 24)
            ws.set_row(1, 20)

            es_tipo_bar = g.tipo_grafico.lower() in ["bar", "horizontal_bar"]
            alto_grafico = max(400, min(750, len(g.categorias_x) * 26 + 100)) if es_tipo_bar else 400
            fila_tabla_header = max(26, int(alto_grafico / 18) + 7) if es_tipo_bar else 26
            ws.write(fila_tabla_header - 1, 0, "DATOS TABULARES VINCULADOS AL GRÁFICO NATIVO:", fmt_seccion)

            # Headers de la tabla: Col A = Eje X, Col B+ = Series
            headers_tabla = [g.eje_x_nombre or "Categoría / Tiempo"]
            for s in g.series:
                headers_tabla.append(s.nombre)

            for col_idx, h in enumerate(headers_tabla):
                ws.write(fila_tabla_header, col_idx, h, fmt_th)
            ws.set_row(fila_tabla_header, 22)

            num_filas = len(g.categorias_x)
            fila_datos_inicio = fila_tabla_header + 1
            fila_datos_fin = fila_datos_inicio + num_filas - 1

            for r_idx, cat in enumerate(g.categorias_x):
                curr_row = fila_datos_inicio + r_idx
                is_alt = (r_idx % 2 == 1)
                fmt_txt = fmt_td_text_alt if is_alt else fmt_td_text
                ws.write(curr_row, 0, str(cat), fmt_txt)
                for s_idx, s in enumerate(g.series):
                    val = s.valores[r_idx] if r_idx < len(s.valores) else None
                    col = s_idx + 1
                    if val is None:
                        ws.write_blank(curr_row, col, "", fmt_td_num_alt if is_alt else fmt_td_num)
                    elif isinstance(val, (int, float)):
                        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                            ws.write_blank(curr_row, col, "", fmt_td_num_alt if is_alt else fmt_td_num)
                        elif isinstance(val, int) or (isinstance(val, float) and not math.isnan(val) and val.is_integer()):
                            fmt_val = fmt_td_int_alt if is_alt else fmt_td_int
                            ws.write_number(curr_row, col, int(val), fmt_val)
                        else:
                            fmt_val = fmt_td_num_alt if is_alt else fmt_td_num
                            ws.write_number(curr_row, col, float(val), fmt_val)
                    else:
                        ws.write(curr_row, col, str(val), fmt_txt)

            # Autoajuste de columnas
            ws.set_column(0, 0, max(18, min(len(headers_tabla[0]) + 4, 35)))
            for c_idx in range(1, len(headers_tabla)):
                ws.set_column(c_idx, c_idx, max(14, min(len(headers_tabla[c_idx]) + 4, 30)))

            # Crear y configurar el objeto Chart nativo de Excel solo si hay series y datos
            if g.series and num_filas > 0:
                chart_type = g.tipo_grafico.lower()
                if chart_type in ["pie", "torta", "donut", "doughnut"]:
                    nat_type = "doughnut" if chart_type in ["donut", "doughnut"] else "pie"
                    chart = workbook.add_chart({"type": nat_type})
                    points = []
                    for p_idx in range(num_filas):
                        color = COLORES_UCT[p_idx % len(COLORES_UCT)]
                        points.append({"fill": {"color": color}})

                    chart.add_series({
                        "name": g.titulo,
                        "categories": [sheet_name, fila_datos_inicio, 0, fila_datos_fin, 0],
                        "values": [sheet_name, fila_datos_inicio, 1, fila_datos_fin, 1],
                        "points": points,
                        "data_labels": {"percentage": True, "value": False},
                    })
                else:
                    # Gráficos cartesianos (column, bar, line, area)
                    if chart_type in ["bar", "horizontal_bar"]:
                        nat_type = "bar"
                    elif chart_type in ["area"]:
                        nat_type = "area"
                    elif chart_type in ["line", "linea"]:
                        nat_type = "line"
                    else:
                        nat_type = "column"

                    chart = workbook.add_chart({"type": nat_type})

                    for s_idx, s in enumerate(g.series):
                        color = s.color or COLORES_UCT[s_idx % len(COLORES_UCT)]
                        series_config = {
                            "name": [sheet_name, fila_tabla_header, s_idx + 1],
                            "categories": [sheet_name, fila_datos_inicio, 0, fila_datos_fin, 0],
                            "values": [sheet_name, fila_datos_inicio, s_idx + 1, fila_datos_fin, s_idx + 1],
                        }

                        if nat_type in ["line"]:
                            series_config["line"] = {"color": color, "width": 2.25}
                            if s.dash_type:
                                series_config["line"]["dash_type"] = s.dash_type
                        elif nat_type in ["area"]:
                            series_config["fill"] = {"color": color, "transparency": 30}
                            series_config["line"] = {"color": color, "width": 1.5}
                        else:
                            series_config["fill"] = {"color": color}
                            series_config["border"] = {"color": "#001A2C"}

                        chart.add_series(series_config)

                    if nat_type == "bar":
                        chart.set_y_axis({
                            "name": g.eje_x_nombre or "",
                            "reverse": True,
                            "major_gridlines": {"visible": False},
                            "num_font": {"name": "Arial", "size": 9},
                        })
                        chart.set_x_axis({
                            "name": g.eje_y_nombre or "",
                            "major_gridlines": {"visible": True, "line": {"color": "#E2E8F0", "dash_type": "dash"}},
                            "num_font": {"name": "Arial", "size": 9},
                        })
                    else:
                        chart.set_x_axis({
                            "name": g.eje_x_nombre or "",
                            "major_gridlines": {"visible": False},
                            "num_font": {"name": "Arial", "size": 9},
                        })
                        chart.set_y_axis({
                            "name": g.eje_y_nombre or "",
                            "major_gridlines": {"visible": True, "line": {"color": "#E2E8F0", "dash_type": "dash"}},
                            "num_font": {"name": "Arial", "size": 9},
                        })

                # Título nativo de Excel y leyenda
                chart.set_title({
                    "name": g.titulo,
                    "name_font": {"name": "Arial", "size": 11, "bold": True, "color": "#002B49"},
                })
                chart.set_legend({
                    "position": "bottom",
                    "font": {"name": "Arial", "size": 9},
                })

                # Dimensiones del gráfico nativo (expandible y editable libremente en Excel)
                chart.set_size({"width": 880, "height": alto_grafico})

                # Insertar el gráfico OpenXML nativo en la celda B5
                ws.insert_chart("B5", chart, {"x_offset": 5, "y_offset": 5})
            else:
                ws.write("B5", "Visualización nativa no disponible por falta de series o datos en este gráfico.", fmt_subtitulo_resumen)

            # Si hay hoja de resumen, registrar este gráfico en el índice
            if ws_resumen is not None:
                is_alt = (idx_grafico % 2 == 0)
                fmt_txt = fmt_td_text_alt if is_alt else fmt_td_text
                fmt_cnt = fmt_td_int_alt if is_alt else fmt_td_int

                ws_resumen.write_number(fila_indice, 0, idx_grafico, fmt_cnt)
                ws_resumen.write(fila_indice, 1, sheet_name, fmt_txt)
                ws_resumen.write(fila_indice, 2, g.titulo, fmt_txt)
                ws_resumen.write(fila_indice, 3, g.categoria or "General", fmt_txt)
                ws_resumen.write(fila_indice, 4, g.tipo_grafico.capitalize(), fmt_txt)
                ws_resumen.write_number(fila_indice, 5, num_filas, fmt_cnt)
                fila_indice += 1

            idx_grafico += 1

        workbook.close()
        return output.getvalue()

    @staticmethod
    async def generar_reporte_plantilla_salas_estudio(
        session: AsyncSession,
        espacio_id: int = 1,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        alcance: str = "conformes",
        regimen_horario: Optional[str] = "todos",
        direccion: Optional[str] = "todos",
        dias_semana: Optional[str] = None,
        door: Optional[str] = None,
        carrera: Optional[str] = None,
        facultad: Optional[str] = None,
        periodo_label: Optional[str] = None,
    ) -> bytes:
        """
        Genera el Reporte Ejecutivo Oficial de Salas de Estudio (Plantilla Institucional UCT),
        con 4 tablas maestras vinculadas dinámicamente mediante fórmulas y 5 gráficos OpenXML
        nativos con tema oscuro (#262626) y estilo Plotly.
        """
        from app.services.attendance_service import AttendanceService

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
            carrera=carrera,
            facultad=facultad,
        )

        # 1. Consulta: Carreras (Sala 1, Sala 2, Total)
        sql_carreras = text(f"""
            WITH ea_filtrada AS (
                SELECT person_id_hash, time, door_entrada, door_salida, carrera
                FROM eventos_asistencia
                WHERE {where_sql}
            )
            SELECT
                COALESCE(dec.carr_nombre, ea.carrera, 'Sin Carrera') AS carrera,
                SUM(CASE WHEN (ea.door_entrada LIKE '%CSF02%' OR ea.door_salida LIKE '%CSF02%') AND ea.door_entrada IS NOT NULL THEN 1 ELSE 0 END) AS sala_1,
                SUM(CASE WHEN (ea.door_entrada LIKE '%CSF04%' OR ea.door_salida LIKE '%CSF04%') AND ea.door_entrada IS NOT NULL THEN 1 ELSE 0 END) AS sala_2,
                COUNT(ea.time) AS total_general
            FROM ea_filtrada ea
            LEFT JOIN dim_estudiante_carrera dec ON dec.person_id_hash = ea.person_id_hash
            GROUP BY COALESCE(dec.carr_nombre, ea.carrera, 'Sin Carrera')
            HAVING COUNT(ea.time) > 0
            ORDER BY total_general DESC
        """)
        rows_carreras = (await session.execute(sql_carreras, params)).fetchall()

        # 2. Consulta: Días del mes (Fecha, Sala 1, Sala 2, Total)
        sql_dias_mes = text(f"""
            SELECT
                CAST(ea.time AS DATE) AS fecha,
                ((DATEPART(WEEKDAY, ea.time) + @@DATEFIRST - 2) % 7 + 1) AS dia_num,
                SUM(CASE WHEN (ea.door_entrada LIKE '%CSF02%' OR ea.door_salida LIKE '%CSF02%') AND ea.door_entrada IS NOT NULL THEN 1 ELSE 0 END) AS sala_1,
                SUM(CASE WHEN (ea.door_entrada LIKE '%CSF04%' OR ea.door_salida LIKE '%CSF04%') AND ea.door_entrada IS NOT NULL THEN 1 ELSE 0 END) AS sala_2,
                COUNT(ea.time) AS total_general
            FROM eventos_asistencia ea
            WHERE {where_sql}
            GROUP BY CAST(ea.time AS DATE), ((DATEPART(WEEKDAY, ea.time) + @@DATEFIRST - 2) % 7 + 1)
            ORDER BY fecha ASC
        """)
        rows_dias_mes = (await session.execute(sql_dias_mes, params)).fetchall()

        # 3. Consulta: Días de la semana (Lunes a Domingo, Sala 1, Sala 2, Total)
        sql_dias_sem = text(f"""
            SELECT
                ((DATEPART(WEEKDAY, ea.time) + @@DATEFIRST - 2) % 7 + 1) AS dia_num,
                SUM(CASE WHEN (ea.door_entrada LIKE '%CSF02%' OR ea.door_salida LIKE '%CSF02%') AND ea.door_entrada IS NOT NULL THEN 1 ELSE 0 END) AS sala_1,
                SUM(CASE WHEN (ea.door_entrada LIKE '%CSF04%' OR ea.door_salida LIKE '%CSF04%') AND ea.door_entrada IS NOT NULL THEN 1 ELSE 0 END) AS sala_2,
                COUNT(ea.time) AS total_general
            FROM eventos_asistencia ea
            WHERE {where_sql}
            GROUP BY ((DATEPART(WEEKDAY, ea.time) + @@DATEFIRST - 2) % 7 + 1)
            ORDER BY dia_num ASC
        """)
        rows_dias_sem = (await session.execute(sql_dias_sem, params)).fetchall()

        # 4. Consulta: Horas (0 a 23, Sala 1, Sala 2, Total)
        sql_horas = text(f"""
            SELECT
                DATEPART(HOUR, ea.time) AS hora,
                SUM(CASE WHEN (ea.door_entrada LIKE '%CSF02%' OR ea.door_salida LIKE '%CSF02%') AND ea.door_entrada IS NOT NULL THEN 1 ELSE 0 END) AS sala_1,
                SUM(CASE WHEN (ea.door_entrada LIKE '%CSF04%' OR ea.door_salida LIKE '%CSF04%') AND ea.door_entrada IS NOT NULL THEN 1 ELSE 0 END) AS sala_2,
                COUNT(ea.time) AS total_general
            FROM eventos_asistencia ea
            WHERE {where_sql}
            GROUP BY DATEPART(HOUR, ea.time)
            ORDER BY hora ASC
        """)
        rows_horas = (await session.execute(sql_horas, params)).fetchall()

        # Inicializar libro Excel
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet_name = "REPORTE SALAS DE ESTUDIOS"
        ws = workbook.add_worksheet(sheet_name)
        ws.set_tab_color("#002B49")

        # ── Formatos y Estilos de Celda ──
        fmt_banner = workbook.add_format({
            "bold": True,
            "font_size": 13,
            "font_name": "Calibri",
            "bg_color": "#1070BA",
            "font_color": "#FFFFFF",
            "align": "center",
            "valign": "vcenter",
        })

        fmt_sec_amarilla = workbook.add_format({
            "bold": True,
            "font_size": 10,
            "font_name": "Calibri",
            "bg_color": "#FFC000",
            "font_color": "#000000",
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "border_color": "#D4A000",
        })

        fmt_th = workbook.add_format({
            "bold": True,
            "font_size": 9,
            "font_name": "Calibri",
            "bg_color": "#203764",
            "font_color": "#FFFFFF",
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "border_color": "#102040",
        })

        fmt_td_text = workbook.add_format({
            "font_size": 9,
            "font_name": "Calibri",
            "align": "left",
            "valign": "vcenter",
            "border": 1,
            "border_color": "#D9D9D9",
        })

        fmt_td_num = workbook.add_format({
            "font_size": 9,
            "font_name": "Calibri",
            "align": "right",
            "valign": "vcenter",
            "num_format": "#,##0",
            "border": 1,
            "border_color": "#D9D9D9",
        })

        fmt_total_lbl = workbook.add_format({
            "bold": True,
            "font_size": 9,
            "font_name": "Calibri",
            "bg_color": "#FFC000",
            "font_color": "#000000",
            "align": "left",
            "valign": "vcenter",
            "border": 1,
            "border_color": "#000000",
        })

        fmt_total_num = workbook.add_format({
            "bold": True,
            "font_size": 9,
            "font_name": "Calibri",
            "bg_color": "#FFC000",
            "font_color": "#000000",
            "align": "right",
            "valign": "vcenter",
            "num_format": "#,##0",
            "border": 1,
            "border_color": "#000000",
        })

        # Configurar anchos de columnas
        ws.set_column(0, 0, 36)    # A: Carreras
        ws.set_column(1, 2, 11)    # B, C: Sala 1, Sala 2
        ws.set_column(3, 3, 13)    # D: Total general
        ws.set_column(4, 4, 3)     # E: Separador
        ws.set_column(5, 10, 10)   # F a K: Área de gráficos Top 10
        ws.set_column(11, 11, 3)   # L: Separador
        ws.set_column(12, 12, 22)  # M: Días mes
        ws.set_column(13, 14, 11)  # N, O: Sala 1, Sala 2
        ws.set_column(15, 15, 13)  # P: Total general
        ws.set_column(16, 16, 3)   # Q: Separador
        ws.set_column(17, 17, 18)  # R: Días semana
        ws.set_column(18, 19, 11)  # S, T: Sala 1, Sala 2
        ws.set_column(20, 20, 13)  # U: Total general
        ws.set_column(21, 21, 3)   # V: Separador
        ws.set_column(22, 22, 16)  # W: Horas
        ws.set_column(23, 24, 11)  # X, Y: Sala 1, Sala 2
        ws.set_column(25, 25, 13)  # Z: Total general

        # Fila 1: Banner Superior
        periodo_txt = (periodo_label or "SEPTIEMBRE").upper()
        ws.set_row(0, 32)
        ws.merge_range(0, 0, 0, 25, f"REPORTE SALAS DE ESTUDIOS ( {periodo_txt} )", fmt_banner)
        ws.set_row(1, 8)  # Fila 2 de respiro
        ws.set_row(2, 20) # Fila 3 cabeceras amarillas
        ws.set_row(3, 18) # Fila 4 encabezados columnas

        # Cabeceras de Sección Amarillas
        ws.merge_range(2, 0, 2, 3, "ACCESOS POR CARRERA", fmt_sec_amarilla)
        ws.merge_range(2, 12, 2, 15, "ACCESOS POR DÍA DEL MES", fmt_sec_amarilla)
        ws.merge_range(2, 17, 2, 20, "ACCESOS POR DÍA DE LA SEMANA", fmt_sec_amarilla)
        ws.merge_range(2, 22, 2, 25, "ACCESOS POR HORA", fmt_sec_amarilla)

        # Encabezados de Columnas
        headers_comunes = ["Sala Nº1", "Sala Nº2", "Total general"]
        ws.write(3, 0, "Etiquetas de fila", fmt_th)
        ws.write(3, 1, headers_comunes[0], fmt_th)
        ws.write(3, 2, headers_comunes[1], fmt_th)
        ws.write(3, 3, headers_comunes[2], fmt_th)

        ws.write(3, 12, "Fecha y Día de la S", fmt_th)
        ws.write(3, 13, headers_comunes[0], fmt_th)
        ws.write(3, 14, headers_comunes[1], fmt_th)
        ws.write(3, 15, headers_comunes[2], fmt_th)

        ws.write(3, 17, "Días de la semana", fmt_th)
        ws.write(3, 18, headers_comunes[0], fmt_th)
        ws.write(3, 19, headers_comunes[1], fmt_th)
        ws.write(3, 20, headers_comunes[2], fmt_th)

        ws.write(3, 22, "Etiquetas de fila", fmt_th)
        ws.write(3, 23, headers_comunes[0], fmt_th)
        ws.write(3, 24, headers_comunes[1], fmt_th)
        ws.write(3, 25, headers_comunes[2], fmt_th)

        # ── 1. Población de Tabla: ACCESOS POR CARRERA ──
        fila_inicio_carr = 4
        num_carr = len(rows_carreras)
        for i, r in enumerate(rows_carreras):
            curr_row = fila_inicio_carr + i
            ws.write(curr_row, 0, r.carrera, fmt_td_text)
            ws.write_number(curr_row, 1, int(r.sala_1 or 0), fmt_td_num)
            ws.write_number(curr_row, 2, int(r.sala_2 or 0), fmt_td_num)
            ws.write_formula(curr_row, 3, f"=B{curr_row+1}+C{curr_row+1}", fmt_td_num, value=int(r.total_general or 0))

        fila_total_carr = fila_inicio_carr + num_carr
        if num_carr > 0:
            ws.write(fila_total_carr, 0, "Total general", fmt_total_lbl)
            ws.write_formula(fila_total_carr, 1, f"=SUM(B5:B{fila_total_carr})", fmt_total_num)
            ws.write_formula(fila_total_carr, 2, f"=SUM(C5:C{fila_total_carr})", fmt_total_num)
            ws.write_formula(fila_total_carr, 3, f"=SUM(D5:D{fila_total_carr})", fmt_total_num)
            # Formato condicional de data bars
            ws.conditional_format(4, 1, fila_total_carr - 1, 3, {
                "type": "data_bar",
                "bar_color": "#5B9BD5",
                "bar_solid": True,
            })

        # ── 2. Población de Tabla: ACCESOS POR DÍA DEL MES ──
        fila_inicio_dias = 4
        num_dias = len(rows_dias_mes)
        mapa_dias_nom = {1: "lunes", 2: "martes", 3: "miércoles", 4: "jueves", 5: "viernes", 6: "sábado", 7: "domingo"}

        for i, r in enumerate(rows_dias_mes):
            curr_row = fila_inicio_dias + i
            fecha_str = r.fecha.strftime("%d-%m-%Y") if hasattr(r.fecha, "strftime") else str(r.fecha)
            ws.write(curr_row, 12, fecha_str, fmt_td_text)
            ws.write_number(curr_row, 13, int(r.sala_1 or 0), fmt_td_num)
            ws.write_number(curr_row, 14, int(r.sala_2 or 0), fmt_td_num)
            ws.write_formula(curr_row, 15, f"=N{curr_row+1}+O{curr_row+1}", fmt_td_num, value=int(r.total_general or 0))

        fila_total_dias = fila_inicio_dias + num_dias
        if num_dias > 0:
            ws.write(fila_total_dias, 12, "Total general", fmt_total_lbl)
            ws.write_formula(fila_total_dias, 13, f"=SUM(N5:N{fila_total_dias})", fmt_total_num)
            ws.write_formula(fila_total_dias, 14, f"=SUM(O5:O{fila_total_dias})", fmt_total_num)
            ws.write_formula(fila_total_dias, 15, f"=SUM(P5:P{fila_total_dias})", fmt_total_num)
            # Formato condicional 3_color_scale
            ws.conditional_format(4, 13, fila_total_dias - 1, 15, {
                "type": "3_color_scale",
                "min_color": "#F8696B",
                "mid_color": "#FFEB84",
                "max_color": "#63BE7B",
            })

        # ── 3. Población de Tabla: ACCESOS POR DÍA DE LA SEMANA ──
        mapa_sem = {int(r.dia_num): r for r in rows_dias_sem}
        dias_orden = [1, 2, 3, 4, 5, 6, 7]
        fila_inicio_sem = 4
        n_sem_escritos = 0

        for d_num in dias_orden:
            r = mapa_sem.get(d_num)
            tot = int(r.total_general) if r else 0
            if d_num == 7 and tot == 0:
                continue  # Omitir domingo si no hay asistencias
            curr_row = fila_inicio_sem + n_sem_escritos
            ws.write(curr_row, 17, mapa_dias_nom[d_num], fmt_td_text)
            ws.write_number(curr_row, 18, int(r.sala_1) if r else 0, fmt_td_num)
            ws.write_number(curr_row, 19, int(r.sala_2) if r else 0, fmt_td_num)
            ws.write_formula(curr_row, 20, f"=S{curr_row+1}+T{curr_row+1}", fmt_td_num, value=tot)
            n_sem_escritos += 1

        fila_total_sem = fila_inicio_sem + n_sem_escritos
        if n_sem_escritos > 0:
            ws.write(fila_total_sem, 17, "Total general", fmt_total_lbl)
            ws.write_formula(fila_total_sem, 18, f"=SUM(S5:S{fila_total_sem})", fmt_total_num)
            ws.write_formula(fila_total_sem, 19, f"=SUM(T5:T{fila_total_sem})", fmt_total_num)
            ws.write_formula(fila_total_sem, 20, f"=SUM(U5:U{fila_total_sem})", fmt_total_num)

        # ── 4. Población de Tabla: ACCESOS POR HORA ──
        mapa_horas = {int(r.hora): r for r in rows_horas}
        fila_inicio_horas = 4
        # Rango 8:00 a 23:00 según la plantilla institucional
        horas_rango = list(range(8, 24))
        n_horas_escritas = 0

        for h in horas_rango:
            r = mapa_horas.get(h)
            curr_row = fila_inicio_horas + n_horas_escritas
            ws.write(curr_row, 22, f"{h}:00", fmt_td_text)
            ws.write_number(curr_row, 23, int(r.sala_1) if r else 0, fmt_td_num)
            ws.write_number(curr_row, 24, int(r.sala_2) if r else 0, fmt_td_num)
            tot_h = int(r.total_general) if r else 0
            ws.write_formula(curr_row, 25, f"=X{curr_row+1}+Y{curr_row+1}", fmt_td_num, value=tot_h)
            n_horas_escritas += 1

        fila_total_horas = fila_inicio_horas + n_horas_escritas
        if n_horas_escritas > 0:
            ws.write(fila_total_horas, 22, "Total general", fmt_total_lbl)
            ws.write_formula(fila_total_horas, 23, f"=SUM(X5:X{fila_total_horas})", fmt_total_num)
            ws.write_formula(fila_total_horas, 24, f"=SUM(Y5:Y{fila_total_horas})", fmt_total_num)
            ws.write_formula(fila_total_horas, 25, f"=SUM(Z5:Z{fila_total_horas})", fmt_total_num)
            # Formato condicional de data bars
            ws.conditional_format(4, 23, fila_total_horas - 1, 25, {
                "type": "data_bar",
                "bar_color": "#5B9BD5",
                "bar_solid": True,
            })

        # ── Función Auxiliar: Configurar Tema Oscuro Institucional ──
        def aplicar_estilo_oscuro(chart, titulo: str):
            chart.set_chartarea({"fill": {"color": "#262626"}, "border": {"color": "#3A3A3A"}})
            chart.set_plotarea({"fill": {"color": "#262626"}, "border": {"color": "#3A3A3A"}})
            chart.set_title({
                "name": titulo,
                "name_font": {"name": "Calibri", "size": 10, "bold": True, "color": "#FFFFFF"},
            })
            chart.set_x_axis({
                "line": {"color": "#555555"},
                "num_font": {"name": "Calibri", "size": 8, "color": "#E0E0E0"},
                "major_gridlines": {"visible": False},
            })
            chart.set_y_axis({
                "line": {"color": "#555555"},
                "num_font": {"name": "Calibri", "size": 8, "color": "#E0E0E0"},
                "major_gridlines": {"visible": True, "line": {"color": "#404040", "dash_type": "dash"}},
            })
            chart.set_legend({
                "position": "bottom",
                "font": {"name": "Calibri", "size": 8, "color": "#E0E0E0"},
            })

        # ── GRÁFICO 1: Top 10 Accesos Sala Nº1 (Barras Horizontales) ──
        n_top10 = min(10, num_carr)
        if n_top10 > 0:
            c1 = workbook.add_chart({"type": "bar"})
            aplicar_estilo_oscuro(c1, "Top 10 Accesos Sala Nº1")
            c1.add_series({
                "name": [sheet_name, 3, 1],
                "categories": [sheet_name, 4, 0, 4 + n_top10 - 1, 0],
                "values": [sheet_name, 4, 1, 4 + n_top10 - 1, 1],
                "fill": {"color": "#00A3E0"},
                "border": {"color": "#002B49"},
                "data_labels": {"value": True, "font": {"name": "Calibri", "size": 8, "color": "#FFFFFF"}},
            })
            c1.set_size({"width": 430, "height": 260})
            ws.insert_chart("F3", c1, {"x_offset": 5, "y_offset": 5})

        # ── GRÁFICO 2: Top 10 Accesos Sala Nº2 (Barras Horizontales) ──
        if n_top10 > 0:
            c2 = workbook.add_chart({"type": "bar"})
            aplicar_estilo_oscuro(c2, "Top 10 Accesos Sala Nº2")
            c2.add_series({
                "name": [sheet_name, 3, 2],
                "categories": [sheet_name, 4, 0, 4 + n_top10 - 1, 0],
                "values": [sheet_name, 4, 2, 4 + n_top10 - 1, 2],
                "fill": {"color": "#ED7D31"},
                "border": {"color": "#8C3B00"},
                "data_labels": {"value": True, "font": {"name": "Calibri", "size": 8, "color": "#FFFFFF"}},
            })
            c2.set_size({"width": 430, "height": 260})
            ws.insert_chart("F18", c2, {"x_offset": 5, "y_offset": 5})

        # ── GRÁFICO 3: Total de Accesos por Día del mes (Líneas) ──
        if num_dias > 0:
            c3 = workbook.add_chart({"type": "line"})
            aplicar_estilo_oscuro(c3, "Total de Accesos por Día del mes")
            c3.add_series({
                "name": [sheet_name, 3, 13],
                "categories": [sheet_name, 4, 12, 4 + num_dias - 1, 12],
                "values": [sheet_name, 4, 13, 4 + num_dias - 1, 13],
                "line": {"color": "#00A3E0", "width": 2},
                "marker": {"type": "circle", "size": 4, "fill": {"color": "#00A3E0"}},
                "data_labels": {"value": True, "font": {"name": "Calibri", "size": 7, "color": "#FFFFFF"}},
            })
            c3.add_series({
                "name": [sheet_name, 3, 14],
                "categories": [sheet_name, 4, 12, 4 + num_dias - 1, 12],
                "values": [sheet_name, 4, 14, 4 + num_dias - 1, 14],
                "line": {"color": "#ED7D31", "width": 2},
                "marker": {"type": "square", "size": 4, "fill": {"color": "#ED7D31"}},
                "data_labels": {"value": True, "font": {"name": "Calibri", "size": 7, "color": "#FFFFFF"}},
            })
            c3.set_size({"width": 550, "height": 290})
            fila_pos_c3 = max(fila_total_dias + 2, 22)
            ws.insert_chart(f"M{fila_pos_c3}", c3, {"x_offset": 5, "y_offset": 5})

        # ── GRÁFICO 4: Accesos por día de la semana (Columnas Agrupadas) ──
        if n_sem_escritos > 0:
            c4 = workbook.add_chart({"type": "column"})
            aplicar_estilo_oscuro(c4, "Accesos por día de la semana por Sala de Estudio")
            c4.add_series({
                "name": [sheet_name, 3, 18],
                "categories": [sheet_name, 4, 17, 4 + n_sem_escritos - 1, 17],
                "values": [sheet_name, 4, 18, 4 + n_sem_escritos - 1, 18],
                "fill": {"color": "#00A3E0"},
                "border": {"color": "#002B49"},
                "data_labels": {"value": True, "font": {"name": "Calibri", "size": 8, "color": "#FFFFFF"}},
            })
            c4.add_series({
                "name": [sheet_name, 3, 19],
                "categories": [sheet_name, 4, 17, 4 + n_sem_escritos - 1, 17],
                "values": [sheet_name, 4, 19, 4 + n_sem_escritos - 1, 19],
                "fill": {"color": "#ED7D31"},
                "border": {"color": "#8C3B00"},
                "data_labels": {"value": True, "font": {"name": "Calibri", "size": 8, "color": "#FFFFFF"}},
            })
            c4.set_size({"width": 450, "height": 270})
            fila_pos_c4 = fila_total_sem + 2
            ws.insert_chart(f"R{fila_pos_c4}", c4, {"x_offset": 5, "y_offset": 5})

        # ── GRÁFICO 5: Accesos por Hora (Barras Horizontales) ──
        if n_horas_escritas > 0:
            c5 = workbook.add_chart({"type": "bar"})
            aplicar_estilo_oscuro(c5, "Accesos por Hora")
            c5.add_series({
                "name": [sheet_name, 3, 24],
                "categories": [sheet_name, 4, 22, 4 + n_horas_escritas - 1, 22],
                "values": [sheet_name, 4, 24, 4 + n_horas_escritas - 1, 24],
                "fill": {"color": "#ED7D31"},
                "border": {"color": "#8C3B00"},
                "data_labels": {"value": True, "font": {"name": "Calibri", "size": 7, "color": "#FFFFFF"}},
            })
            c5.add_series({
                "name": [sheet_name, 3, 23],
                "categories": [sheet_name, 4, 22, 4 + n_horas_escritas - 1, 22],
                "values": [sheet_name, 4, 23, 4 + n_horas_escritas - 1, 23],
                "fill": {"color": "#00A3E0"},
                "border": {"color": "#002B49"},
                "data_labels": {"value": True, "font": {"name": "Calibri", "size": 7, "color": "#FFFFFF"}},
            })
            c5.set_size({"width": 460, "height": 340})
            fila_pos_c5 = fila_total_horas + 2
            ws.insert_chart(f"W{fila_pos_c5}", c5, {"x_offset": 5, "y_offset": 5})

        workbook.close()
        return output.getvalue()


"""Pruebas de exportación Excel OpenXML, PDF ReportLab, streaming CSV y auditoría de descargas."""
import asyncio
import base64
import io
import zipfile
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import openpyxl

from app.schemas.chat_schemas import ExportPdfRequest
from app.schemas.excel_export_schemas import (
    GraficoNativoPayload,
    SerieGrafico,
    SolicitudExportacionExcel,
)
from app.services import audit_service
from app.services.attendance_service import AttendanceService
from app.services.chat.exportacion_pdf import _construir_story_pdf_sync, generar_pdf_conversacion
from app.services.excel_export_service import ExcelExportService, sanear_nombre_hoja
from app.services.vehicle_service import VehicleService


def test_sanear_nombre_hoja_respeta_limite_31_y_unicidad():
    usados: set[str] = set()
    n1 = sanear_nombre_hoja("Gráfico: [Aforo] *Biblioteca/2026? Muy Largo", usados)
    n2 = sanear_nombre_hoja("Gráfico: [Aforo] *Biblioteca/2026? Muy Largo", usados)
    n3 = sanear_nombre_hoja("///???", usados)

    assert len(n1) <= 31 and not any(c in n1 for c in "\\/?*:[]'")
    assert n2 != n1 and len(n2) <= 31
    assert n3 == "Hoja"


def test_generar_excel_nativo_consolidado_y_tipos_multiples():
    solicitud = SolicitudExportacionExcel(
        modulo_nombre="Biblioteca CSF",
        periodo_label="Octubre 2026",
        filtros={"alcance": "conformes", "sala": "todas"},
        graficos=[
            GraficoNativoPayload(
                id="g_col",
                titulo="Afluencia por Día / Sector?",
                categoria="Aforo",
                tipo_grafico="column",
                eje_x_nombre="Día",
                eje_y_nombre="Personas",
                categorias_x=["Lun", "Mar", "Mié"],
                series=[
                    SerieGrafico(nombre="Sala 1", valores=[120, None, 145.5], color="#002B49"),
                    SerieGrafico(nombre="Sala 2", valores=[80.0, float("nan"), float("inf")]),
                ],
            ),
            GraficoNativoPayload(
                id="g_line",
                titulo="Tendencia Horaria",
                tipo_grafico="line",
                categorias_x=["09:00", "10:00", "11:00"],
                series=[SerieGrafico(nombre="Pronóstico", valores=[50, 80, 95], dash_type="dash")],
            ),
            GraficoNativoPayload(
                id="g_area",
                titulo="Ocupación Acumulada",
                tipo_grafico="area",
                categorias_x=["09:00", "10:00"],
                series=[SerieGrafico(nombre="Total", valores=[30, 60])],
            ),
            GraficoNativoPayload(
                id="g_bar",
                titulo="Ranking Carreras",
                tipo_grafico="horizontal_bar",
                categorias_x=["Ing. Informática", "Derecho"],
                series=[SerieGrafico(nombre="Visitas", valores=[300, 180])],
            ),
            GraficoNativoPayload(
                id="g_donut",
                titulo="Participación Facultades",
                tipo_grafico="doughnut",
                categorias_x=["Ingeniería", "Salud"],
                series=[SerieGrafico(nombre="Porcentaje", valores=[60, 40])],
            ),
        ],
    )

    data_bytes = ExcelExportService.generar_excel_nativo(solicitud)
    assert data_bytes[:2] == b"PK"

    with zipfile.ZipFile(io.BytesIO(data_bytes)) as zf:
        nombres_zip = zf.namelist()
        assert any("xl/charts/chart" in n for n in nombres_zip)

    wb = openpyxl.load_workbook(io.BytesIO(data_bytes))
    try:
        assert "Resumen_Ejecutivo" in wb.sheetnames
        assert len(wb.sheetnames) == 6
    finally:
        wb.close()


def test_generar_reporte_plantilla_salas_estudio_con_db_mockeada():
    async def _run():
        rows_carreras = [
            SimpleNamespace(carrera="Ingeniería Civil Informática", sala_1=120, sala_2=80, total_general=200),
            SimpleNamespace(carrera="Derecho", sala_1=50, sala_2=30, total_general=80),
        ]
        rows_dias_mes = [
            SimpleNamespace(fecha=date(2026, 9, 14), dia_num=1, sala_1=70, sala_2=40, total_general=110),
        ]
        rows_dias_sem = [
            SimpleNamespace(dia_num=1, sala_1=70, sala_2=40, total_general=110),
        ]
        rows_horas = [
            SimpleNamespace(hora=10, sala_1=70, sala_2=40, total_general=110),
        ]

        res_list = []
        for rows in (rows_carreras, rows_dias_mes, rows_dias_sem, rows_horas):
            r = MagicMock()
            r.fetchall.return_value = rows
            res_list.append(r)

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=res_list)

        with patch.object(
            ExcelExportService,
            "generar_reporte_plantilla_salas_estudio",
            wraps=ExcelExportService.generar_reporte_plantilla_salas_estudio,
        ), patch("app.services.attendance_service.AttendanceService._build_attendance_filters", new=AsyncMock(return_value=("1=1", {}))):
            xlsx_bytes = await ExcelExportService.generar_reporte_plantilla_salas_estudio(
                session=db,
                espacio_id=1,
                fecha_inicio=date(2026, 9, 1),
                fecha_fin=date(2026, 9, 30),
                periodo_label="Septiembre 2026",
            )

        assert xlsx_bytes[:2] == b"PK"
        wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
        try:
            assert "REPORTE SALAS DE ESTUDIOS" in wb.sheetnames
            ws = wb["REPORTE SALAS DE ESTUDIOS"]
            assert ws["A5"].value == "Ingeniería Civil Informática"
        finally:
            wb.close()

    asyncio.run(_run())


def test_endpoints_export_excel_y_plantilla(app_client, admin_user):
    client = app_client(admin_user)
    with patch("app.api.v1.endpoints.export.record_download_audit", new=AsyncMock()):
        resp_g = client.post(
            "/api/v1/export/excel/grafico",
            json={
                "id": "g_test",
                "titulo": "Aforo Diario",
                "tipo_grafico": "column",
                "categorias_x": ["2026-10-01", "2026-10-02"],
                "series": [{"nombre": "Asistencia", "valores": [10, 20]}],
            },
        )
        assert resp_g.status_code == 200
        assert resp_g.content[:2] == b"PK"

        resp_c_vacio = client.post(
            "/api/v1/export/excel/consolidado",
            json={"modulo_nombre": "Bib", "periodo_label": "Oct", "graficos": []},
        )
        assert resp_c_vacio.status_code == 400

        resp_c = client.post(
            "/api/v1/export/excel/consolidado",
            json={
                "modulo_nombre": "Bib",
                "periodo_label": "Oct",
                "graficos": [
                    {
                        "id": "g1",
                        "titulo": "G1",
                        "categorias_x": ["A"],
                        "series": [{"nombre": "S1", "valores": [5]}],
                    }
                ],
            },
        )
        assert resp_c.status_code == 200
        assert resp_c.content[:2] == b"PK"

        with patch.object(ExcelExportService, "generar_reporte_plantilla_salas_estudio", new=AsyncMock(return_value=b"PK\x03\x04fake")):
            resp_p = client.get("/api/v1/export/excel/plantilla-salas-estudio?espacio_id=1&periodo_label=Oct")
            assert resp_p.status_code == 200
            assert resp_p.content.startswith(b"PK")


def test_exportacion_pdf_conversacion_con_tablas_imagenes_y_escape_xml():
    # PNG 1x1 transparente válido para incrustar en ReportLab RLImage
    png_1x1 = base64.b64encode(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c\x84"
        b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    ).decode("ascii")

    async def _run():
        # Caso 1: consulta individual con tabla, imagen y caracteres XML peligrosos (<>&")
        req_ind = ExportPdfRequest(
            session_id="sess-001",
            titulo="Informe <Seguro> & Auditado",
            espacio_id=1,
            consulta_texto="¿Aforo < 100 & > 10?",
            respuesta_texto="Resultado:\n10 < 20 & 'seguro'",
            datos_tabla=[{"carrera": "Ing. <Info>", "visitas": 42}],
            graficos_b64={"single": f"data:image/png;base64,{png_1x1}"},
        )
        resp_1 = await generar_pdf_conversacion(AsyncMock(), req_ind, usuario_id=1)
        assert resp_1.status_code == 200
        assert resp_1.body.startswith(b"%PDF")

        # Caso 2: conversación persistida completa
        conv_id = "11111111-1111-1111-1111-111111111111"
        conv_mock = SimpleNamespace(
            titulo="Análisis <Semestre>",
            mensajes=[
                SimpleNamespace(id=1, rol="user", contenido="¿Pico & hora?", tipo="text", herramienta=None, modelo=None),
                SimpleNamespace(id=2, rol="assistant", contenido="Pico a las 11:00 <ok>", tipo="plotly", herramienta="pico", modelo="gemini"),
            ],
        )
        req_conv = ExportPdfRequest(
            session_id="sess-002",
            conversacion_id=conv_id,
            graficos_b64={"1": png_1x1},
        )
        with patch("app.services.chat.exportacion_pdf.obtener_conversacion", new=AsyncMock(return_value=conv_mock)):
            resp_2 = await generar_pdf_conversacion(AsyncMock(), req_conv, usuario_id=1)
        assert resp_2.status_code == 200
        assert resp_2.body.startswith(b"%PDF")

        # Verificar que el story no contiene etiquetas XML crudas no escapadas
        story = _construir_story_pdf_sync(req_ind, "T < & >", [], [])
        assert len(story) >= 4

    asyncio.run(_run())


def test_stream_raw_csv_asistencia_y_vehicular():
    async def _run():
        # Streaming AttendanceService.stream_raw_csv
        fila_bib = SimpleNamespace(
            time=datetime(2026, 10, 14, 23, 30, 0),
            person_id_hash="abcdef1234567890",
            door_entrada="CSF02-T1",
            door_salida=None,
            primera_entrada=datetime(2026, 10, 14, 23, 30, 0),
            ultima_salida=None,
            permanencia_min=15.0,
            marcajes_totales=5,
            salida_imputada=1,
            entrada_imputada=0,
            alerta_coherencia_fechas=0,
        )

        class _FakeStreamRes:
            def __init__(self, filas):
                self._filas = filas

            async def partitions(self, _size):
                yield self._filas

        s_bib = AsyncMock()
        s_bib.stream = AsyncMock(return_value=_FakeStreamRes([fila_bib]))

        class _Ctx:
            def __init__(self, sess):
                self.sess = sess

            async def __aenter__(self):
                return self.sess

            async def __aexit__(self, *args):
                return False

        conteo_bib = [0]
        with (
            patch("app.core.database.AsyncSessionLocal", return_value=_Ctx(s_bib)),
            patch.object(AttendanceService, "_build_attendance_filters", new=AsyncMock(return_value=("1=1", {}))),
            patch("app.services.config_service.get_horarios_operacion", new=AsyncMock(return_value=[])),
            patch("app.services.config_service.es_horario_conforme", return_value=False),
        ):
            chunks_bib = [c async for c in AttendanceService.stream_raw_csv(espacio_id=1, conteo_ref=conteo_bib)]
        csv_bib = "".join(chunks_bib)
        assert conteo_bib[0] == 1
        assert "USR-abcdef12" in csv_bib
        assert "Marcaje Excesivo" in csv_bib

        # Streaming VehicleService.stream_raw_csv (incluyendo protección anti-formula injection)
        fila_veh = SimpleNamespace(
            time=datetime(2026, 10, 14, 10, 0, 0),
            patente_hash="112233445566",
            camara="=CMD('calc')",
            direccion="+entrada",
            tipo_vehiculo="-SUV",
            marca="@Toyota",
            color="Gris",
            calidad_lectura="ok",
        )
        s_veh = AsyncMock()
        s_veh.stream = AsyncMock(return_value=_FakeStreamRes([fila_veh]))
        conteo_veh = [0]
        with (
            patch("app.core.database.AsyncSessionLocal", return_value=_Ctx(s_veh)),
            patch.object(VehicleService, "_build_vehicle_filters", new=AsyncMock(return_value=("1=1", {}))),
            patch("app.services.config_service.get_horarios_operacion", new=AsyncMock(return_value=[])),
            patch("app.services.config_service.es_horario_conforme", return_value=True),
        ):
            chunks_veh = [c async for c in VehicleService.stream_raw_csv(espacio_id=2, conteo_ref=conteo_veh)]
        csv_veh = "".join(chunks_veh)
        assert conteo_veh[0] == 1
        assert "PAT-11223344" in csv_veh
        assert "Conforme" in csv_veh
        assert "'=CMD('calc')" in csv_veh
        assert "'+entrada" in csv_veh
        assert "'-SUV" in csv_veh
        assert "'@Toyota" in csv_veh

    asyncio.run(_run())


def test_audit_service_record_e_historial():
    async def _run():
        sess = AsyncMock()
        sess.add = MagicMock()
        sess.commit = AsyncMock()

        class _Ctx:
            async def __aenter__(self):
                return sess

            async def __aexit__(self, *args):
                return False

        # record_download_audit exitoso y fallo silencioso
        with patch.object(audit_service, "AsyncSessionLocal", return_value=_Ctx()):
            await audit_service.record_download_audit(
                usuario_id=1,
                modulo="biblioteca",
                formato="XLSX",
                filtro_fecha_inicio="2026-10-01",
                filtro_fecha_fin="2026-10-14",
                filtro_detalle="Filtro test",
                total_registros=50,
                ip_origen="10.0.0.1",
            )
            sess.add.assert_called_once()
            sess.commit.assert_awaited_once()

        # get_download_audit_history con resultados paginados
        r_total = MagicMock()
        r_total.scalar.return_value = 1
        r_rows = MagicMock()
        r_rows.scalars.return_value.all.return_value = [
            SimpleNamespace(
                id=10,
                usuario_id=1,
                usuario=SimpleNamespace(email="admin@uct.cl", nombre_completo="Admin UCT"),
                modulo="biblioteca",
                formato="xlsx",
                filtro_fecha_inicio="2026-10-01",
                filtro_fecha_fin="2026-10-14",
                filtro_detalle="Detalle",
                total_registros=50,
                ip_origen="10.0.0.1",
                timestamp=datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc),
            )
        ]
        r_stats = MagicMock()
        r_stats.one.return_value = (1, 1, 0, 0)
        r_modulos = MagicMock()
        r_modulos.all.return_value = [("biblioteca", 1)]
        sess.execute = AsyncMock(side_effect=[r_total, r_rows, r_stats, r_modulos])

        with patch.object(audit_service, "AsyncSessionLocal", return_value=_Ctx()):
            hist = await audit_service.get_download_audit_history(page=1, page_size=15, modulo="biblioteca", formato="xlsx", search="admin")
        assert hist["total"] == 1
        assert hist["items"][0]["usuario_email"] == "admin@uct.cl"
        assert hist["stats"]["total_descargas"] == 1
        assert hist["stats"]["descargas_por_modulo"] == {"biblioteca": 1}

    asyncio.run(_run())

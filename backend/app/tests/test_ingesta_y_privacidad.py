"""Pruebas de ingesta, detección de cabeceras, colisiones, adaptadores y privacidad Ley 21.719."""
import asyncio
import io
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import openpyxl
import pandas as pd
import pytest
from fastapi import HTTPException

from app.adapters.csv_adapter import CsvIngestionAdapter
from app.services import ingestion_service
from app.services.ingestion_service import (
    _clasificar_sentido_tokens,
    _detect_header_row_csv,
    _detect_header_row_excel,
    _normalize_str,
    _parse_fast_dt,
    _procesar_lote_asistencia_sync,
    _procesar_lote_vehicular_sync,
    _sanitize_preview_value,
    calcular_hash_archivo,
    detectar_clave_enlace,
    es_archivo_institucional_uct,
    extraer_rango_fechas,
    inspect_uploaded_file,
    validar_archivo_ingesta,
)


def _crear_excel_bytes(hojas: dict[str, list[list]]) -> bytes:
    wb = openpyxl.Workbook()
    primera = True
    for nombre, filas in hojas.items():
        ws = wb.active if primera else wb.create_sheet(title=nombre)
        if primera:
            ws.title = nombre
            primera = False
        for f in filas:
            ws.append(f)
    buf = io.BytesIO()
    try:
        wb.save(buf)
        return buf.getvalue()
    finally:
        wb.close()
        buf.close()


def test_deteccion_cabeceras_csv_y_excel_y_esquema_uct():
    # CSV HikCentral con 3 filas de metadatos previos
    csv_raw = (
        "Reporte HikCentral\nGenerado: 2026-10-14\nCampus San Francisco\n"
        "Fecha,Persona,personId,Primera entrada,Última salida,Door entrada,Door salida\n"
        "2026-10-14,Juan Pérez,18456123-K,09:00:00,11:30:00,CSF02-T1 Entrada,CSF02-T1 Salida\n"
    ).encode("utf-8-sig")

    kw = ingestion_service._get_target_keywords_set("asistencia")
    hdr_idx, df_csv, total = _detect_header_row_csv(csv_raw, kw, max_rows=25)
    assert hdr_idx == 3
    assert "personId" in df_csv.columns
    assert total >= 1

    # Excel vehicular con 2 filas de ruido + hoja Notas descartada
    xls_bytes = _crear_excel_bytes(
        {
            "Notas": [["Documento informativo"]],
            "Vehicular": [
                ["Export HikCentral LPR"],
                ["Fecha: 2026-10-14"],
                ["Hora", "Número de matrícula", "Cámara", "Dirección de conducción", "Tipo de vehículo", "Marca", "Color del vehículo"],
                ["2026-10-14 08:30:00", "ABCD12", "CSF11-E1", "Avanzar", "SUV", "Toyota", "Blanco"],
            ],
        }
    )
    kw_veh = ingestion_service._get_target_keywords_set("vehicular")
    h_xls, df_xls, total_xls = _detect_header_row_excel(xls_bytes, kw_veh, max_rows=25)
    assert h_xls == 2
    assert len(df_xls) == 1
    assert total_xls >= 1
    assert "Número de matrícula" in df_xls.columns

    # Detección esquema institucional UCT
    uct_bytes = _crear_excel_bytes({"ESTUDIANTE": [["rut"]], "CAMPUS": [["nombre"]]})
    assert es_archivo_institucional_uct(uct_bytes) is True
    assert es_archivo_institucional_uct(xls_bytes) is False


def test_inspect_uploaded_file_y_sanitizacion_pii():
    csv_asist = (
        "Fecha,Persona,Correo,Telefono,personId,Primera entrada,Última salida,Door entrada,Door salida\n"
        "2026-10-14,Ana Rojas,ana@uct.cl,+56911112222,19111222-3,09:00:00,10:15:00,CSF02-T1,CSF02-T1\n"
    ).encode("utf-8")

    async def _run():
        res = await inspect_uploaded_file(csv_asist, "asistencia.csv", "asistencia", espacio_id=1)
        assert res.tipo == "asistencia"
        assert res.all_required_matched is True
        fila = res.preview_rows[0]
        assert fila["Persona"] == "[DATO PURGADO - LEY 21.719]"
        assert fila["Correo"] == "[DATO PURGADO - LEY 21.719]"
        assert fila["Telefono"] == "[DATO PURGADO - LEY 21.719]"
        assert "19111222-3" not in str(fila)
        assert fila["personId"].startswith("EST-***")

        # Autodetección marcajes_torniquete y custom
        csv_marc = (
            "Fecha,Hora,personId,Puerta,Sentido\n"
            "2026-10-14,09:00:00,19111222-3,CSF02-T1,Entrada\n"
        ).encode("utf-8")
        res_m = await inspect_uploaded_file(csv_marc, "marcajes.csv", "asistencia", espacio_id=1)
        assert res_m.tipo == "marcajes_torniquete"

        res_c = await inspect_uploaded_file(csv_asist, "custom.csv", "custom", espacio_id=1)
        clasif = {m.target_field: m.classification for m in res_c.schema_mapping}
        assert clasif["Correo"] == "purgar"
        assert clasif["Telefono"] == "purgar"
        assert clasif["personId"] == "seudonimizar"

        # Rechazo de formato inválido
        with pytest.raises(HTTPException) as exc:
            await inspect_uploaded_file(b"abc", "archivo.exe", "asistencia", espacio_id=1)
        assert exc.value.status_code == 400

    asyncio.run(_run())


def test_procesamiento_lotes_anonimizacion_hmac_fernet_y_purga_pii():
    df_asist = pd.DataFrame(
        [
            {
                "Fecha": "2026-10-14",
                "Persona": "María Soto",
                "Correo": "maria@uct.cl",
                "Teléfono": "987654321",
                "personId": "19222333-4",
                "Primera entrada": "08:30:00",
                "Última salida": "10:00:00",
                "Door entrada": "CSF02-T1",
                "Door salida": "CSF02-T1",
                "Marcajes": "2",
            }
        ]
    )
    dtos_a = _procesar_lote_asistencia_sync(
        df_asist.copy(),
        espacio_id=1,
        clave_enlace="rut",
        modo_enlace="rut",
        maestro_estudiantes={},
    )
    assert len(dtos_a) == 1
    dto_a = dtos_a[0]
    assert dto_a.person_id_hash != "19222333-4" and len(dto_a.person_id_hash) == 64
    assert "María" not in repr(dto_a) and "maria@uct.cl" not in repr(dto_a)

    df_veh = pd.DataFrame(
        [
            {
                "Hora": "2026-10-14 08:45:00",
                "Número de matrícula": "BBCC99",
                "Teléfono": "999888777",
                "Lista de vehículos": "Privado",
                "Cámara": "CSF11-E1",
                "Dirección de conducción": "Retroceder",
                "Tipo de vehículo": "SUV",
                "Marca": "Kia",
                "Color del vehículo": "Azul",
            },
            {
                "Hora": "2026-10-14 08:50:00",
                "Número de matrícula": "",
                "Cámara": "CSF11-E1",
                "Dirección de conducción": "Avanzar",
            },
        ]
    )
    dtos_v = _procesar_lote_vehicular_sync(df_veh.copy(), espacio_id=2)
    assert len(dtos_v) == 2
    assert dtos_v[0].direccion == "salida"
    assert dtos_v[0].patente_hash != "BBCC99"
    assert dtos_v[0].patente_cifrada.startswith("gAAAAAB")
    assert "999888777" not in repr(dtos_v[0])
    assert dtos_v[1].patente_hash == "unknown"
    assert dtos_v[1].calidad_lectura == "unknown"


def test_validar_archivo_ingesta_colisiones_y_hash_duplicado():
    csv_bytes = (
        "Fecha,personId,Primera entrada,Última salida,Door entrada,Door salida,Carrera\n"
        "2026-10-14,18111222-3,09:00:00,10:00:00,CSF02-T1,CSF02-T1,Ingeniería Civil Informática\n"
    ).encode("utf-8")

    async def _run():
        job_prev = SimpleNamespace(
            job_id="11111111-1111-1111-1111-111111111111",
            filename="asist_2026.csv",
            estado="completed",
            creado_en=datetime(2026, 10, 14, 12, 0, 0),
            registros_ok=100,
        )
        r_job = MagicMock()
        r_job.scalars.return_value.first.return_value = job_prev
        r_col = MagicMock()
        r_col.scalar.return_value = 50

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[r_job, r_col])

        res = await validar_archivo_ingesta(csv_bytes, "asist_2026-10-01_2026-10-14.csv", "asistencia", 1, db)
        assert res.hash_ya_procesado is True
        assert res.existe_colision is True
        assert res.registros_existentes == 50
        assert res.clave_enlace_detectada == "matricula"
        assert res.porcentaje_coincidencia_carreras == 100.0
        assert "Sobrescritura Atómica" in res.detalles_colision

    asyncio.run(_run())


def test_endpoint_upload_valida_extension_tamano_y_duplicado(app_client, admin_user, tmp_path):
    client = app_client(admin_user)

    # Extensión inválida -> 400
    r_ext = client.post(
        "/api/v1/ingestion/upload?tipo=asistencia&espacio_id=1",
        files={"file": ("malware.exe", b"MZ...", "application/octet-stream")},
    )
    assert r_ext.status_code == 400

    # Archivo válido que supera límite de tamaño -> 413
    with (
        patch("app.core.config.settings.DIRECTORIO_INGESTA", str(tmp_path)),
        patch("app.core.config.settings.TAMANO_MAXIMO_INGESTA_MB", 0),
    ):
        r_big = client.post(
            "/api/v1/ingestion/upload?tipo=asistencia&espacio_id=1",
            files={"file": ("datos.csv", b"Fecha,personId\n2026-10-14,123\n", "text/csv")},
        )
        assert r_big.status_code == 413

    # Upload válido en modo overwrite -> 202 y no expone PII en respuesta
    with (
        patch("app.core.config.settings.DIRECTORIO_INGESTA", str(tmp_path)),
        patch("app.core.recursos_http.crear_tarea_fondo") as mock_task,
    ):
        def _cerrar_coro(coro, **_kw):
            coro.close()
            return MagicMock()

        mock_task.side_effect = _cerrar_coro
        r_ok = client.post(
            "/api/v1/ingestion/upload?tipo=asistencia&espacio_id=1&modo_solapamiento=overwrite",
            files={"file": ("limpio.csv", b"Fecha,personId\n2026-10-14,19111222-3\n", "text/csv")},
        )
        assert r_ok.status_code == 202
        body = r_ok.json()
        assert body["status"] == "queued"
        assert "19111222-3" not in str(body)


def test_csv_ingestion_adapter_y_utilidades():
    assert _normalize_str("Número de Matrícula (Á)") == "numero de matricula a"
    assert _parse_fast_dt("2026-10-14", "09:15:30") == datetime(2026, 10, 14, 9, 15, 30)
    assert _parse_fast_dt("nan") is None
    assert _clasificar_sentido_tokens("Avanzar / Entrada") == "entrada"
    assert _clasificar_sentido_tokens("Retroceder") == "salida"
    assert detectar_clave_enlace(["RUT", "Matricula"]) == "crosswalk"
    assert _sanitize_preview_value("Patente", "BBCC12", "vehicular") == "VEH-***12"
    assert len(calcular_hash_archivo(b"uct")) == 64

    df_rng = pd.DataFrame({"Fecha": ["2026-10-01", "2026-10-05"], "Hora": ["08:00:00", "19:00:00"]})
    f_min, f_max = extraer_rango_fechas(df_rng)
    assert f_min == datetime(2026, 10, 1, 8, 0, 0)
    assert f_max == datetime(2026, 10, 5, 19, 0, 0)

    csv_asist = (
        "Fecha,Persona,Telefono,personId,Primera entrada,Ultima salida,Door entrada,Door salida,Dif. salida (min),Marcajes\n"
        "2026-10-14,Pedro,91234567,17888999-1,09:00:00,10:00:00,CSF02-T1,CSF02-T1,60,2\n"
    ).encode("utf-8")

    async def _run():
        adp = CsvIngestionAdapter(csv_asist, "datos.csv", espacio_id=1)
        evs = await adp.fetch_attendance_events(1)
        assert len(evs) == 1
        assert evs[0].person_id_hash != "17888999-1"
        assert "Pedro" not in repr(evs[0])

        # Vehicular Excel en CsvIngestionAdapter (6 líneas previas)
        buf = io.BytesIO()
        wb = openpyxl.Workbook()
        ws = wb.active
        for i in range(6):
            ws.append([f"Meta {i}"])
        ws.append(["Hora", "Numero de matricula", "Camara", "Direccion de conduccion", "Tipo de vehiculo", "Marca", "Color del vehiculo"])
        ws.append(["2026-10-14 10:00:00", "ZZXX88", "CSF11", "Entrada", "Auto", "Mazda", "Rojo"])
        wb.save(buf)
        wb.close()
        adp_v = CsvIngestionAdapter(buf.getvalue(), "veh.xlsx", espacio_id=2)
        buf.close()
        evs_v = await adp_v.fetch_vehicle_events(2)
        assert len(evs_v) == 1
        assert evs_v[0].patente_hash != "ZZXX88"

        # Calendario CSV en CsvIngestionAdapter
        csv_cal = b"fecha,is_holiday,descripcion\n2026-09-18,true,Fiestas Patrias\n"
        adp_c = CsvIngestionAdapter(csv_cal, "cal.csv", espacio_id=1)
        evs_c = await adp_c.fetch_calendar_events()
        assert len(evs_c) == 1 and evs_c[0].is_holiday is True

    asyncio.run(_run())

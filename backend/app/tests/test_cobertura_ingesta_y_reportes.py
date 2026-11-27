"""Pruebas extensivas de ingesta masiva, adaptadores, Smart Campus y reportes compartidos."""
import asyncio
import io
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
from fastapi import HTTPException

from app.adapters.anpr_adapter import CircuitBreaker, CircuitBreakerOpenException, HikCentralOpenAPIAdapter
from app.adapters.csv_adapter import CsvIngestionAdapter
from app.adapters.file_adapter import FileIngestionAdapter
from app.adapters.smart_campus_adapter import SmartCampusAdapter, SmartCampusAPIError
from app.core.security import create_access_token
from app.services import ingestion_service, servicio_smart_campus
from app.services.servicio_reportes_compartidos import ServicioReportesCompartidos
from app.tests.conftest import crear_usuario_mock
from app.tests.test_cobertura_analitica_y_herramientas import _SmartRow, _crear_db_analitica


def test_lotes_vehicular_y_marcajes_e_institucional():
    df_veh = pd.DataFrame(
        [
            {
                "Hora": "2026-10-14 09:00:00",
                "Número de matrícula": "AABB11",
                "Teléfono": "912345678",
                "Lista de vehículos": "Privado",
                "Cámara": "CSF11-E1",
                "Dirección de conducción": "Avanzar",
                "Tipo de vehículo": "SUV",
                "Marca": "Kia",
                "Color del vehículo": "Blanco",
            },
            {
                "Hora": "2026-10-14 10:00:00",
                "Número de matrícula": "",
                "Cámara": "CSF21-S1",
                "Dirección de conducción": "Retroceder",
            },
        ]
    )
    dtos_v = ingestion_service._procesar_lote_vehicular_sync(df_veh, espacio_id=2)
    assert len(dtos_v) == 2
    assert dtos_v[0].calidad_lectura == "ok" and dtos_v[0].direccion == "entrada"
    assert dtos_v[1].patente_hash == "unknown" and dtos_v[1].direccion == "salida"

    # Marcajes de torniquete en lotes
    df_marc = pd.DataFrame(
        [
            {"Fecha": "2026-10-14", "Hora": "08:30:00", "personId": "19111222-3", "Puerta": "CSF02-T1 IN", "Sentido": "Entrada"},
            {"Fecha": "2026-10-14", "Hora": "10:15:00", "personId": "19111222-3", "Puerta": "CSF02-T1 OUT", "Sentido": "Salida"},
        ]
    )
    if hasattr(ingestion_service, "_procesar_lote_marcajes_sync"):
        res_m = ingestion_service._procesar_lote_marcajes_sync(df_marc, espacio_id=1)
        assert isinstance(res_m, (list, tuple))

    assert ingestion_service.detectar_clave_enlace(["Fecha", "personId", "RUT"]) in ("crosswalk", "rut", "personId", "matricula")
    assert ingestion_service.detectar_clave_enlace(["Fecha", "Matricula"]) == "matricula"


def test_adaptadores_file_csv_anpr_y_smart_campus(tmp_path):
    async def _run():
        # CircuitBreaker transitions
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60.0)
        assert cb.can_execute() is True

        async def _fail():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await cb.execute(_fail)
        with pytest.raises(RuntimeError):
            await cb.execute(_fail)
        assert cb.state == "OPEN"
        with pytest.raises(CircuitBreakerOpenException):
            await cb.execute(AsyncMock())

        # HikCentralOpenAPIAdapter
        db_hk = _crear_db_analitica()
        hik = await HikCentralOpenAPIAdapter.crear_desde_bd_o_entorno(db_hk, espacio_id=2)
        assert hik.resolver_identificador_region(2) is not None

        # FileIngestionAdapter loaders y mappers
        base_dir = tmp_path / "datos_bases"
        base_dir.mkdir(parents=True)
        (base_dir / "asistencia_base.csv").write_text(
            "Fecha,personId,Primera entrada,Última salida,Door entrada,Door salida,Marcajes,Dif. salida (min)\n"
            "2026-10-14,19111222-3,2026-10-14 08:30:00,2026-10-14 09:30:00,CSF02-T1,CSF02-T1,2,60\n",
            encoding="utf-8",
        )
        fa = FileIngestionAdapter(tmp_path)
        ev_att = await fa.fetch_attendance_events(espacio_id=1)
        assert len(ev_att) == 1

        # CsvIngestionAdapter (asistencia)
        csv_bytes = (
            "Fecha,Persona,Telefono,personId,Primera entrada,Última salida,Door entrada,Door salida,Marcajes,Dif. salida (min)\n"
            "2026-10-14,Pedro,91111,19111222-3,09:00:00,10:00:00,CSF02-T1,CSF02-T1,2,60\n"
        ).encode("utf-8")
        ca = CsvIngestionAdapter(csv_bytes, "asistencia.csv", espacio_id=1)
        ca_ev = await ca.fetch_attendance_events(espacio_id=1)
        assert len(ca_ev) == 1 and ca_ev[0].permanencia_min == 60.0

        # SmartCampusAdapter HTTP mock
        sca = SmartCampusAdapter(base_url="https://integrasmartcampus.uct.cl/api/lectura", api_key="k-test")
        assert sca._obtener_cabeceras()["Authorization"] == "Bearer k-test"

        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {"registros": [{"fecha_hora": "2026-10-14T10:00:00-03:00", "puerta": "CSF02-T1", "sentido": "entrada"}]}
        fake_resp.raise_for_status = MagicMock()

        fake_http = AsyncMock()
        fake_http.get = AsyncMock(return_value=fake_resp)
        with patch("app.core.recursos_http.obtener_http_client", return_value=fake_http):
            regs = await sca._solicitar_con_reintento("/torniquetes", {"desde": "2026-10-14"})
            assert len(regs) == 1
            pts = await sca.obtener_puntos()
            assert "registros" in pts

        # Error 401 inmediato sin reintento
        fake_401 = MagicMock(status_code=401, text="Unauthorized")
        fake_401.json.return_value = {"error": "No autorizado"}
        fake_http.get = AsyncMock(return_value=fake_401)
        with (
            patch("app.core.recursos_http.obtener_http_client", return_value=fake_http),
            pytest.raises(SmartCampusAPIError),
        ):
            await sca._solicitar_con_reintento("/torniquetes", {})

    asyncio.run(_run())


def test_servicio_smart_campus_helpers_y_sincronizacion():
    assert servicio_smart_campus._clasificar_sentido_smart_campus("alejandose", vehiculo=True) == "salida"
    assert servicio_smart_campus._clasificar_sentido_smart_campus("entrada", vehiculo=False) == "entrada"
    assert servicio_smart_campus._parse_dt_chile_naive("2026-10-14T13:00:00Z") is not None

    async def _run():
        db = _crear_db_analitica(scalar_val=date(2026, 10, 14))
        fake_adapt = MagicMock()
        fake_adapt.obtener_marcajes_torniquetes = AsyncMock(return_value=[])
        fake_adapt.obtener_pasos_estacionamientos = AsyncMock(return_value=[])
        fake_adapt.obtener_puntos = AsyncMock(return_value={"torniquetes": [], "camaras": []})

        with (
            patch.object(servicio_smart_campus, "SmartCampusAdapter", return_value=fake_adapt),
            patch.object(servicio_smart_campus, "registrar_estado_sincronizacion", new=AsyncMock()),
        ):
            res = await servicio_smart_campus.sincronizar_aforo_vivo_horario(
                db, desde_manual=date(2026, 10, 14), hasta_manual=date(2026, 10, 14), fuente="todas"
            )
        assert isinstance(res, dict)

    asyncio.run(_run())


def test_servicio_reportes_compartidos_flujo_completo():
    async def _run():
        admin = crear_usuario_mock("admin@uct.cl", ["Admin_Sistema"], user_id=1)
        dir_bib = crear_usuario_mock("dir.bib@uct.cl", ["Director_Recinto"], espacio_id=1, allowed_datasets=["biblioteca"], user_id=2)
        consultor = crear_usuario_mock("dest@uct.cl", ["Consultor_Reporte"], user_id=20)
        ajeno = crear_usuario_mock("ajeno@uct.cl", ["Consultor_Reporte"], user_id=99)

        assert ServicioReportesCompartidos._es_admin(admin) is True
        assert ServicioReportesCompartidos._es_directivo(dir_bib) is True
        assert ServicioReportesCompartidos._espacios_autorizados(dir_bib) == [1]

        rep_obj = SimpleNamespace(
            id=uuid.uuid4(),
            codigo_corto="RPT-2026-009",
            titulo_reporte="Informe Ejecutivo Octubre",
            espacio_id=1,
            creado_por_id=2,
            destinatario_id=5,
            destinatario=SimpleNamespace(
                id=5,
                email="dest@uct.cl",
                nombre_completo="Destinatario UCT",
                cargo="Decano",
                unidad_academica="Ingeniería",
                token_portal="tok-portal",
                activo=True,
                ultimo_acceso_en=None,
            ),
            creador=SimpleNamespace(id=2, nombre_completo="Directora", email="dir.bib@uct.cl", roles=[SimpleNamespace(nombre="Director_Recinto")]),
            fecha_inicio=date(2026, 10, 1),
            fecha_fin=date(2026, 10, 14),
            filtros_json="{}",
            filtros_bloqueados_json="{}",
            graficos_visibles_json='["flujo_horario"]',
            indicadores_visibles_json='["afluencia_total"]',
            notas_items_json='[{"seccion": "general", "contenido": "Ok"}]',
            nota_general="Nota ejecutiva",
            finalidad_reporte="Evaluación mensual",
            modo_datos="instantanea_congelada",
            datos_instantanea_json=json.dumps(
                {
                    "indicadores_ejecutivos": {"afluencia_total": 300},
                    "indicadores_visibles": ["afluencia_total"],
                    "graficos_visibles": ["flujo_horario"],
                    "graficos": {"flujo_horario": [{"hora": "10:00", "entradas": 40}]},
                }
            ),
            datos_snapshot_json=json.dumps(
                {
                    "indicadores_ejecutivos": {"afluencia_total": 300},
                    "indicadores_visibles": ["afluencia_total"],
                    "graficos_visibles": ["flujo_horario"],
                    "graficos": {"flujo_horario": [{"hora": "10:00", "entradas": 40}]},
                }
            ),
            permitir_chat_ia=True,
            permitir_ia=True,
            permitir_exportacion=True,
            cuota_ia_max=20,
            cuota_ia_usada=2,
            activo=True,
            revocada_en=None,
            expira_en=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=5),
            creado_en=datetime.now(timezone.utc).replace(tzinfo=None),
            token_acceso="tok-rep",
            total_aperturas=1,
            total_accesos=1,
            ultima_apertura_en=None,
        )

        # Control de acceso por usuario (titular pasa, ajeno 403)
        ServicioReportesCompartidos._verificar_acceso_usuario_a_reporte(consultor, rep_obj)
        with pytest.raises(HTTPException) as exc_403:
            ServicioReportesCompartidos._verificar_acceso_usuario_a_reporte(ajeno, rep_obj)
        assert exc_403.value.status_code == 403

        # Indicadores ejecutivos biblioteca y estacionamiento + ensamblado
        db = _crear_db_analitica()
        with (
            patch("app.services.attendance_service.AttendanceService.get_kpis", new=AsyncMock(return_value={"total_registros": 100, "dias_operativos": 5})),
            patch("app.services.attendance_service.AttendanceService.get_occupancy_realtime", new=AsyncMock(return_value={"aforo_actual": 25})),
            patch("app.services.attendance_service.AttendanceService.get_realtime_presence_curve", new=AsyncMock(return_value=[{"personas_presentes": 50, "bucket": "10:00"}])),
            patch("app.services.attendance_service.AttendanceService.get_curricular_distribution", new=AsyncMock(return_value={"carreras": [{"carrera": "Informática", "eventos_asistencia": 50}]})),
            patch("app.services.attendance_service.AttendanceService.get_hourly_flow", new=AsyncMock(return_value=[{"hora": "10:00", "entradas": 20}])),
            patch("app.services.vehicle_service.VehicleService.get_kpis", new=AsyncMock(return_value={"total_eventos": 60, "dias_operativos": 5})),
            patch("app.services.vehicle_service.VehicleService.get_parking_occupancy", new=AsyncMock(return_value={"vehiculos_dentro": 15, "plazas_libres": 110})),
            patch("app.services.vehicle_service.VehicleService.get_realtime_presence_curve", new=AsyncMock(return_value=[{"vehiculos_presentes": 30, "bucket": "10:00"}])),
        ):
            ind_b = await ServicioReportesCompartidos.calcular_indicadores_ejecutivos_biblioteca(
                db, date(2026, 10, 1), date(2026, 10, 14), {}, {"total_registros": 100, "dias_operativos": 5}
            )
            assert ind_b["dias_operativos"] == 5
            ind_v = await ServicioReportesCompartidos.calcular_indicadores_ejecutivos_estacionamiento(
                db, date(2026, 10, 1), date(2026, 10, 14), {}, {"total_eventos": 60, "dias_operativos": 5}, []
            )
            assert ind_v["dias_operativos"] == 5

            ens = await ServicioReportesCompartidos.ensamblar_datos_reporte_confinado(
                db,
                espacio_id=1,
                fecha_inicio=date(2026, 10, 1),
                fecha_fin=date(2026, 10, 14),
                filtros={},
                graficos_visibles=["flujo_horario"],
                indicadores_visibles=["afluencia_total"],
            )
            assert "indicadores_ejecutivos" in ens

            # Vista pública anónima (sin datos ni tokens) vs autenticada (con datos)
            res_rep = MagicMock()
            res_rep.scalar_one_or_none.return_value = rep_obj
            db_pub = _crear_db_analitica(scalar_val=276)
            base_res = db.execute.return_value
            db_pub.execute = AsyncMock(
                side_effect=lambda stmt, *a, **kw: res_rep if "reportes_compartidos" in str(stmt) else base_res
            )

            out_anon = await ServicioReportesCompartidos.obtener_reporte_publico_por_token(
                db_pub, "tok-rep", usuario_actual=None
            )
            assert out_anon["requiere_login"] is True
            assert out_anon["datos"] is None

            out_auth = await ServicioReportesCompartidos.obtener_reporte_publico_por_token(
                db_pub, "tok-rep", usuario_actual=consultor
            )
            assert out_auth["requiere_login"] is False
            assert out_auth["datos"]["indicadores_ejecutivos"]["afluencia_total"] >= 100

    asyncio.run(_run())

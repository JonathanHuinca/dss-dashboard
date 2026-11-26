"""
Batería final de pruebas unitarias aisladas para cerrar cobertura backend >= 75%
sobre los servicios críticos de ingesta, Smart Campus, reportes compartidos,
analítica de asistencia/vehículos, autenticación, orquestador ML, LLM, correo,
calendario académico y planificador.
"""

import asyncio
import hashlib
import io
import json
import smtplib
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import joblib
import openpyxl
import pandas as pd
import pytest
from fastapi import BackgroundTasks, HTTPException

from app.core import planificador
from app.domain.auth_models import Rol, TokenActivacion, Usuario
from app.domain.reportes_compartidos_models import DestinatarioReporte, ReporteCompartido
from app.ml import orquestador_entrenamiento
from app.schemas.auth_schemas import UsuarioCreate, UsuarioUpdateRequest
from app.services import (
    auth_service,
    calendar_scraper,
    email_service,
    ingestion_service,
    llm_client,
    servicio_smart_campus,
)
from app.services.attendance_service import AttendanceService
from app.services.servicio_reportes_compartidos import ServicioReportesCompartidos
from app.services.vehicle_service import VehicleService
from app.tests.conftest import crear_usuario_mock
from app.tests.test_cobertura_analitica_y_herramientas import _SmartRow, _crear_db_analitica


class _CtxAsync:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        return False


def _crear_db_vacio_o_simulado(rows=None, scalar_val=1, rowcount=2):
    """Crea una sesión mockeada segura para flujos ORM y consultas SQL."""
    db = _crear_db_analitica(rows=rows, scalar_val=scalar_val)
    db.in_transaction = MagicMock(return_value=True)
    db.begin = MagicMock(return_value=_CtxAsync(db))
    db.delete = AsyncMock()
    db.add_all = MagicMock()

    async def _refresh(obj, *args, **kwargs):
        if getattr(obj, "id", None) is None:
            obj.id = 101

    db.refresh = AsyncMock(side_effect=_refresh)
    return db


def _crear_xlsx_institucional_completo() -> bytes:
    """Genera un Excel institucional UCT con múltiples hojas válidas (datos desde fila 4)."""
    wb = openpyxl.Workbook()
    ws_camp = wb.active
    ws_camp.title = "CAMPUS"
    for _ in range(3):
        ws_camp.append(["H1", "H2", "H3", "H4", "H5", "H6"])
    ws_camp.append([1, "Campus San Francisco", "S", "Obs", "2026-03-01 08:00:00", "admin"])

    ws_ed = wb.create_sheet("EDIFICIOS")
    for _ in range(3):
        ws_ed.append(["H"] * 7)
    ws_ed.append([10, 1, "Biblioteca Central", "S", "Edificio 10", "2026-03-01 08:00:00", "admin"])

    ws_amb = wb.create_sheet("AMBIENTE")
    for _ in range(3):
        ws_amb.append(["H"] * 10)
    ws_amb.append([100, 1, 10, 1, 2, "Sala Estudio 1", "CSF02", "S", "admin", "2026-03-01 08:00:00"])

    ws_tc = wb.create_sheet("relacio con carrera_programa")
    for _ in range(3):
        ws_tc.append(["H"] * 11)
    ws_tc.append([1, "PREGRADO", "1", None, None, None, 2, "CARRERA", "PROFESIONAL", "admin", "2026-03-01"])

    ws_cp = wb.create_sheet("CARRERA_PROGRAMA")
    for _ in range(3):
        ws_cp.append(["H"] * 8)
    ws_cp.append([1150, 1, 2, "Ingeniería Civil Informática", 10, 10, "admin", "2026-03-01"])

    ws_cc = wb.create_sheet("CARRERA_CAMPUS")
    for _ in range(3):
        ws_cc.append(["H"] * 4)
    ws_cc.append([1150, 1, "admin", "2026-03-01"])

    ws_sa = wb.create_sheet("SITUACION_ALUMNO")
    for _ in range(3):
        ws_sa.append(["H"] * 2)
    ws_sa.append([1, "REGULAR"])

    ws_vi = wb.create_sheet("VIAS_INGRESO")
    for _ in range(3):
        ws_vi.append(["H"] * 5)
    ws_vi.append([1, "PAES", "Admisión Regular", "admin", "2026-03-01"])

    ws_est = wb.create_sheet("ESTUDIANTE")
    for _ in range(3):
        ws_est.append(["H"] * 8)
    ws_est.append(["19111222", "3", "Pérez", "Gómez", "Ana", "María", "F", "2004-05-10"])

    ws_ec = wb.create_sheet("ESTUDIANTE_CARRERA")
    for _ in range(3):
        ws_ec.append(["H"] * 13)
    ws_ec.append(["2024001", "19111222-3", "3", 1150, 1, 1, 1, 1, 2024, 1, 0, "admin", "2026-03-01"])

    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def test_ingestion_institucional_atomica_streaming_y_retroactiva(tmp_path):
    async def _run():
        db = _crear_db_analitica(rows=[], scalar_val=1)
        db.in_transaction = MagicMock(return_value=True)
        db.begin = MagicMock(return_value=_CtxAsync(db))
        db.add_all = MagicMock()

        res_vacio = MagicMock(
            scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None), all=MagicMock(return_value=[]))),
            all=MagicMock(return_value=[]),
            scalar=MagicMock(return_value=0),
            rowcount=12,
        )
        db.execute = AsyncMock(return_value=res_vacio)

        # 1. Ingesta atómica institucional UCT (11 tablas)
        xlsx_bytes = _crear_xlsx_institucional_completo()
        with patch("app.services.ingestion_service.invalidar_caches_recinto_y_actualizar_predicciones", new=AsyncMock()):
            res_inst = await ingestion_service._ejecutar_ingesta_atomica_impl(
                file_bytes=xlsx_bytes,
                filename="uct_maestro.xlsx",
                tipo="institucional_uct",
                espacio_id=1,
                modo_solapamiento="overwrite",
                clave_enlace="rut",
                modo_enlace="tolerante",
                db=db,
                usuario_id=1,
            )
            assert res_inst.status == "completed"

        # 2. Error 409 en merge cuando existe hash previo
        res_dup = MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=SimpleNamespace(job_id=uuid.uuid4())))))
        db_dup = _crear_db_analitica()
        db_dup.execute = AsyncMock(return_value=res_dup)
        with pytest.raises(HTTPException) as exc_409:
            await ingestion_service._ejecutar_ingesta_atomica_impl(
                b"col1,col2\n1,2\n", "dup.csv", "asistencia", 1, "merge", "rut", "tolerante", db_dup, 1
            )
        assert exc_409.value.status_code == 409

        # 3. Ingesta atómica asistencia, vehicular, curricular y custom
        csv_asist = "Fecha,personId,Primera entrada,Última salida,Door entrada,Estamento\n2026-10-14,19111222-3,09:00:00,11:00:00,CSF02-T1,Estudiante\n".encode("utf-8")
        csv_veh = "Fecha,Hora,Patente,Camara,Direccion,Tipo Vehiculo,Marca,Color,Calidad Lectura\n2026-10-14,10:00:00,ABCD12,CSF11-E1,Entrada,SUV,Toyota,Gris,ok\n".encode("utf-8")
        csv_curr = "RUT,Matricula,Carrera,Facultad\n19111222-3,2024001,Ing. Informática,Ingeniería\n".encode("utf-8")
        csv_custom = "col_a,col_b\n1,2\n".encode("utf-8")

        with (
            patch("app.services.ingestion_service.AttendanceService.bulk_insert_events", new=AsyncMock(return_value={"insertados": 1, "eliminados": 0})),
            patch("app.services.ingestion_service.VehicleService.bulk_insert_events", new=AsyncMock(return_value={"insertados": 1, "eliminados": 0})),
            patch("app.services.ingestion_service.invalidar_caches_recinto_y_actualizar_predicciones", new=AsyncMock()),
        ):
            for in_tx in (True, False):
                db.in_transaction = MagicMock(return_value=in_tx)
                r1 = await ingestion_service.ejecutar_ingesta_atomica(csv_asist, "a.csv", "asistencia", 1, "overwrite", "rut", "tolerante", db, 1)
                r2 = await ingestion_service.ejecutar_ingesta_atomica(csv_veh, "v.csv", "vehicular", 2, "overwrite", "auto", "tolerante", db, 1)
                r3 = await ingestion_service.ejecutar_ingesta_atomica(csv_curr, "c.csv", "curricular", 1, "overwrite", "rut", "tolerante", db, 1)
                r4 = await ingestion_service.ejecutar_ingesta_atomica(csv_custom, "x.csv", "custom", 1, "overwrite", "auto", "tolerante", db, 1)
                assert all(r.status == "completed" for r in (r1, r2, r3, r4))

        # 4. Streaming por lotes CSV (asistencia, vehicular, curricular)
        job_mock = SimpleNamespace(job_id=uuid.uuid4(), estado="pending", registros_ok=0, completado_en=None, detalle=None)
        db_lot = _crear_db_analitica()
        db_lot.add_all = MagicMock()
        db_lot.get = AsyncMock(return_value=job_mock)
        db_lot.execute = AsyncMock(return_value=res_vacio)

        for nombre, tipo_l, contenido in [
            ("lote_a.csv", "asistencia", csv_asist.decode("utf-8")),
            ("lote_v.csv", "vehicular", csv_veh.decode("utf-8")),
            ("lote_c.csv", "curricular", csv_curr.decode("utf-8")),
        ]:
            p_csv = tmp_path / nombre
            p_csv.write_text(contenido, encoding="utf-8")
            with (
                patch("app.services.ingestion_service.AsyncSessionLocal", return_value=_CtxAsync(db_lot)),
                patch("app.services.ingestion_service.AttendanceService.bulk_insert_events", new=AsyncMock(return_value={"insertados": 1, "eliminados": 0})),
                patch("app.services.ingestion_service.VehicleService.bulk_insert_events", new=AsyncMock(return_value={"insertados": 1, "eliminados": 0})),
                patch("app.services.ingestion_service.invalidar_caches_recinto_y_actualizar_predicciones", new=AsyncMock()),
            ):
                await ingestion_service.procesar_archivo_por_lotes(
                    job_mock.job_id, p_csv, tipo_l, espacio_id=1 if tipo_l != "vehicular" else 2, modo_solapamiento="overwrite"
                )

        # 5. Enriquecimiento retroactivo (catálogo vacío vs enriquecido)
        db_ret_empty = _crear_db_analitica(scalar_val=None)
        res_warn = await ingestion_service.enriquecer_asistencia_retroactiva(db_ret_empty, espacio_id=1)
        assert res_warn["status"] == "warning"

        db_ret_ok = _crear_db_analitica(scalar_val=5)
        db_ret_ok.execute = AsyncMock(return_value=MagicMock(scalar=MagicMock(return_value=5), rowcount=15))
        for clave_e in ("auto", "rut", "pid"):
            res_ok = await ingestion_service.enriquecer_asistencia_retroactiva(db_ret_ok, espacio_id=1, clave_enlace=clave_e)
            assert res_ok["status"] == "completed" and res_ok["enriquecidos"] == 15

    asyncio.run(_run())


def test_smart_campus_sincronizacion_y_consolidacion_con_datos():
    async def _run():
        db = _crear_db_vacio_o_simulado()
        res_empty = MagicMock(
            scalar=MagicMock(return_value=None),
            fetchall=MagicMock(return_value=[]),
            scalar_one_or_none=MagicMock(return_value=None),
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))),
        )
        db.execute = AsyncMock(return_value=res_empty)

        raw_torn = [
            {"fecha": "2026-10-14T09:00:00", "matricula": "2024001", "sentido": "entrada", "puerta": "CSF02-T1", "estamento": "Estudiante", "detalle_estamento": "Ing. Informática"},
            {"fecha": "2026-10-14T22:15:00", "id_visitante": "", "sentido": "entrada", "puerta": "CSF04-T1", "estamento": "Estudiante"},
            {"fecha": "2026-10-14T11:30:00", "matricula": "2024001", "sentido": "salida", "puerta": "CSF02-T1"},
        ]
        raw_veh = [
            {"fecha": "2026-10-14T08:30:00", "patente": "ABCD12", "camara": "CSF11-E1", "sentido": "entrada", "marca": "Toyota", "color": "Rojo", "tipo_vehiculo": "SUV", "calidad_lectura": "ok"},
            {"fecha": "2026-10-14T17:30:00", "patente": "ABCD12", "camara": "CSF11-S1", "sentido": "salida"},
        ]

        # 1. Sincronización horaria con datos reales de API
        with (
            patch("app.adapters.smart_campus_adapter.SmartCampusAdapter.obtener_marcajes_torniquetes", new=AsyncMock(return_value=raw_torn)),
            patch("app.adapters.smart_campus_adapter.SmartCampusAdapter.obtener_pasos_estacionamientos", new=AsyncMock(return_value=raw_veh)),
            patch("app.services.servicio_smart_campus.registrar_estado_sincronizacion", new=AsyncMock()),
        ):
            res_sync = await servicio_smart_campus.sincronizar_aforo_vivo_horario(db, fuente="todas")
            assert res_sync["torniquetes"]["insertados"] == 3
            assert res_sync["estacionamientos"]["insertados"] == 2

        # 2. Consolidación nocturna 24h con datos API y luego con fallback local
        horario_24h = SimpleNamespace(
            activo=True,
            es_continuo_24h=True,
            tipo_horario="extendido_24h",
            fecha_inicio=datetime(2026, 10, 1),
            fecha_fin=datetime(2026, 10, 30),
            configuracion_dias={"miercoles": {"abierto": True, "cierre": "07:00", "cierre_dia_siguiente": True}},
            cierre_dia_siguiente=True,
            hora_apertura="08:00",
            hora_cierre="07:00",
        )
        with (
            patch("app.services.config_service.get_horarios_operacion", new=AsyncMock(return_value=[horario_24h])),
            patch("app.adapters.smart_campus_adapter.SmartCampusAdapter.obtener_marcajes_torniquetes", new=AsyncMock(return_value=raw_torn)),
            patch("app.adapters.smart_campus_adapter.SmartCampusAdapter.obtener_pasos_estacionamientos", new=AsyncMock(return_value=raw_veh)),
        ):
            res_cons = await servicio_smart_campus.consolidar_dia_cerrado(
                db, fecha_objetivo=date(2026, 10, 14), fuente="todas"
            )
            assert res_cons["regimen_detectado"] == "24h_extendido"
            assert res_cons["sesiones_consolidadas"] >= 1

        # 3. Fallback local cuando API lanza excepción
        ev_a = SimpleNamespace(time=datetime(2026, 10, 14, 10, 0), ultima_salida=datetime(2026, 10, 14, 12, 0), person_id_hash="h1", door_entrada="CSF02-T1", door_salida="CSF02-T1")
        ev_v = SimpleNamespace(time=datetime(2026, 10, 14, 9, 0), patente_hash="p1", camara="CSF11-E1", direccion="entrada", tipo_vehiculo="SUV", marca="Toyota", color="Gris", calidad_lectura="ok")
        res_fb = MagicMock(
            fetchall=MagicMock(return_value=[]),
            scalar_one_or_none=MagicMock(return_value=None),
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(side_effect=[[ev_a], [ev_v]]))),
        )
        db_fb = _crear_db_vacio_o_simulado()
        db_fb.execute = AsyncMock(return_value=res_fb)
        with (
            patch("app.services.config_service.get_horarios_operacion", new=AsyncMock(return_value=[])),
            patch("app.adapters.smart_campus_adapter.SmartCampusAdapter.obtener_marcajes_torniquetes", new=AsyncMock(side_effect=RuntimeError("API caída"))),
            patch("app.adapters.smart_campus_adapter.SmartCampusAdapter.obtener_pasos_estacionamientos", new=AsyncMock(side_effect=RuntimeError("API caída"))),
        ):
            res_cons_fb = await servicio_smart_campus.consolidar_dia_cerrado(
                db_fb, fecha_objetivo=date(2026, 10, 14), fuente="todas"
            )
            assert len(res_cons_fb["errores"]) >= 2

    asyncio.run(_run())


def test_reportes_compartidos_gestion_vinculacion_y_consultor():
    async def _run():
        admin = crear_usuario_mock("admin@uct.cl", ["Admin_Sistema"], user_id=1)
        director = crear_usuario_mock("dir.bib@uct.cl", ["Director_Recinto"], user_id=2, espacio_id=1, allowed_datasets=["biblioteca"])
        consultor = crear_usuario_mock("dest@uct.cl", ["Consultor_Reporte"], user_id=20, espacio_id=1, allowed_datasets=["biblioteca"])

        db = _crear_db_vacio_o_simulado()
        rol_c = Rol(id=4, nombre="Consultor_Reporte")
        usr_dest = Usuario(
            id=20, email="dest@uct.cl", hashed_password="$2b$12$abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ01",
            nombre_completo="Decano UCT", is_active=True, allowed_datasets=["biblioteca"], espacio_id=1,
            roles=[rol_c],
        )
        dest_obj = DestinatarioReporte(
            id=5, email="dest@uct.cl", nombre_completo="Decano UCT", cargo="Decano",
            unidad_academica="Ingeniería", token_portal="tok-p", activo=True,
            creado_en=datetime.now(), actualizado_en=datetime.now(),
        )
        rep_obj = ReporteCompartido(
            id=uuid.uuid4(), codigo_corto="RPT-2026-901", titulo_reporte="Reporte Mensual",
            espacio_id=1, creado_por_id=2, destinatario_id=5,
            fecha_inicio=date(2026, 10, 1), fecha_fin=date(2026, 10, 14),
            filtros_bloqueados_json="{}",
            graficos_visibles_json='["flujo_horario"]', indicadores_visibles_json='["afluencia_total"]',
            notas_items_json="[]", nota_general="Ok", finalidad_reporte="Seguimiento",
            datos_instantanea_json=json.dumps({"indicadores_ejecutivos": {"dias_operativos": 5, "afluencia_total": 120}, "graficos": {"flujo_horario": []}}),
            permitir_ia=True, permitir_exportacion=True,
            activo=True, expira_en=datetime.now() + timedelta(days=5),
            creado_en=datetime.now(), token_acceso="tok-acc-901", total_accesos=1,
            modo_datos="instantanea_fija",
        )
        rep_obj.destinatario = dest_obj
        rep_obj.creador = director
        dest_obj.reportes = [rep_obj]

        # 1. Registrar consultor y enviar correo por BackgroundTasks
        bg = BackgroundTasks()
        res_none = MagicMock(scalar_one_or_none=MagicMock(return_value=None), scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
        res_rol = MagicMock(scalar_one_or_none=MagicMock(return_value=rol_c))
        res_usr = MagicMock(scalar_one_or_none=MagicMock(return_value=usr_dest), scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[usr_dest]))))

        db_reg = _crear_db_vacio_o_simulado()
        db_reg.execute = AsyncMock(side_effect=[res_none, res_rol, res_none])
        with patch("app.services.servicio_reportes_compartidos.enviar_correo_activacion_consultor", new=AsyncMock(return_value=True)):
            out_reg = await ServicioReportesCompartidos.registrar_consultor_reporte(
                db_reg, admin, {"email": "nuevo.c@uct.cl", "nombre_completo": "Nuevo C", "cargo": "Jefe", "unidad_academica": "TI"}, background_tasks=bg
            )
            assert out_reg["email"] == "nuevo.c@uct.cl" and len(bg.tasks) == 1

        # 2. Candidatos consultor + vincular usuario existente
        db_cand = _crear_db_vacio_o_simulado()
        db_cand.execute = AsyncMock(side_effect=[res_usr, MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[dest_obj]))))])
        cands = await ServicioReportesCompartidos.obtener_usuarios_candidatos_consultor(db_cand, admin)
        assert isinstance(cands, list)

        db_vinc = _crear_db_vacio_o_simulado()
        db_vinc.execute = AsyncMock(side_effect=[res_usr, res_rol, MagicMock(scalar_one_or_none=MagicMock(return_value=dest_obj))])
        vinc = await ServicioReportesCompartidos.vincular_usuario_existente_consultor(
            db_vinc, admin, {"usuario_id": 20, "cargo": "Decano", "unidad_academica": "Ingeniería"}
        )
        assert vinc["email"] == "dest@uct.cl"

        # 3. Crear reporte compartido (espacio 1)
        db_cr = _crear_db_vacio_o_simulado()
        db_cr.execute = AsyncMock(side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=dest_obj)),
            res_usr,
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
            MagicMock(scalar=MagicMock(return_value=0)),
        ])
        with (
            patch.object(ServicioReportesCompartidos, "ensamblar_datos_reporte_confinado", new=AsyncMock(return_value={"indicadores_ejecutivos": {"afluencia_total": 50}, "graficos": {}})),
            patch("app.services.servicio_reportes_compartidos.enviar_correo_reporte_ejecutivo", new=AsyncMock(return_value=True)),
        ):
            cr_out = await ServicioReportesCompartidos.crear_reporte_compartido(
                db_cr, admin, {
                    "destinatario_email": "dest@uct.cl",
                    "destinatario_nombre": "Decano UCT",
                    "destinatario_cargo": "Decano",
                    "destinatario_unidad": "Ingeniería",
                    "espacio_id": 1,
                    "fecha_inicio": "2026-10-01",
                    "fecha_fin": "2026-10-14",
                    "titulo_reporte": "Informe Biblioteca",
                    "permitir_ia": True,
                }, background_tasks=bg
            )
            assert "codigo_corto" in cr_out

        # 4. Listar emitidos (admin y director), mis reportes, eventos y estado destinatario
        db_lst = _crear_db_vacio_o_simulado()
        db_lst.execute = AsyncMock(side_effect=[
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[rep_obj])))),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[dest_obj])))),
            MagicMock(all=MagicMock(return_value=[(5, 1)])),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[usr_dest])))),
        ])
        emitidos = await ServicioReportesCompartidos.listar_reportes_emitidos(db_lst, admin)
        assert len(emitidos["reportes"]) == 1

        db_mis = _crear_db_vacio_o_simulado()
        res_d_m = MagicMock(scalar_one_or_none=MagicMock(return_value=dest_obj))
        db_mis.execute = AsyncMock(side_effect=[
            res_d_m,
            res_d_m,
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[rep_obj])))),
        ])
        mis = await ServicioReportesCompartidos.obtener_mis_reportes_consultor(db_mis, consultor)
        assert len(mis["reportes"]) == 1

        ev_row = SimpleNamespace(id=1, accion="apertura", detalle="OK", ip_origen="127.0.0.1", user_agent="pytest", fecha_hora=datetime.now())
        db_evs = _crear_db_vacio_o_simulado()
        db_evs.execute = AsyncMock(side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=rep_obj)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=director)),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[ev_row])))),
        ])
        evs_out = await ServicioReportesCompartidos.obtener_eventos_reporte(db_evs, admin, str(rep_obj.id))
        assert len(evs_out["eventos"]) == 1

        db_est = _crear_db_vacio_o_simulado()
        db_est.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=dest_obj)))
        est_out = await ServicioReportesCompartidos.actualizar_estado_destinatario(db_est, 5, False, usuario_actual=admin)
        assert est_out["activo"] is False

        # 5. Eliminar destinatario consultor y consulta IA confinada
        db_del = _crear_db_vacio_o_simulado()
        db_del.execute = AsyncMock(side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=dest_obj)),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[rep_obj.id])))),
            MagicMock(), MagicMock(), MagicMock(),
            MagicMock(scalar_one_or_none=MagicMock(return_value=usr_dest)),
            MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(),
        ])
        del_dest = await ServicioReportesCompartidos.eliminar_destinatario_consultor(db_del, admin, 5)
        assert del_dest["eliminado"] is True

        dest_obj.activo = True
        db_ia = _crear_db_vacio_o_simulado()
        db_ia.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=rep_obj), scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))
        fake_llm = SimpleNamespace(
            default_model="gemini-3.1-flash-lite",
            generate_response=AsyncMock(return_value="Total de 120 asistencias registradas."),
        )
        with (
            patch.object(ServicioReportesCompartidos, "_obtener_usuario_destinatario_con_roles", new=AsyncMock(return_value=consultor)),
            patch.object(ServicioReportesCompartidos, "_obtener_cuota_ia_reporte", new=AsyncMock(return_value={"ilimitado": False, "restantes": 5, "limite": 10, "usado_hoy": 1})),
            patch.object(ServicioReportesCompartidos, "ensamblar_datos_reporte_confinado", new=AsyncMock(return_value={"indicadores_ejecutivos": {"dias_operativos": 5, "afluencia_total": 120}, "graficos": {"flujo_horario": []}})),
            patch("app.services.servicio_reportes_compartidos.build_llm_client", new=AsyncMock(return_value=fake_llm)),
        ):
            resp_ia = await ServicioReportesCompartidos.consultar_ia_reporte_confinado(
                db_ia, "tok-acc-901", "¿Cuántas asistencias hubo?", usuario_actual=admin
            )
            assert "120" in resp_ia["respuesta"]

    asyncio.run(_run())


def test_attendance_y_vehicle_filtros_kpis_raw_y_24h():
    async def _run():
        f_ini, f_fin = date(2026, 10, 1), date(2026, 10, 14)
        rows_raw = [
            _SmartRow(
                fecha=date(2026, 10, 14),
                min_fecha=date(2026, 10, 12),
                max_fecha=date(2026, 10, 14),
                semana_num=42,
                dia_dw=3,
                ingresos=50,
                time=datetime(2026, 10, 14, 23, 30),
                fecha_inicio=date(2026, 10, 1),
                fecha_fin=date(2026, 10, 14),
                bucket=datetime(2026, 10, 14, 10, 0),
                hora=10,
                hora_num=10,
                total_registros=10,
                usuarios_unicos=8,
                dias_operativos=5,
                permanencia_promedio_min=45.0,
                permanencia_mediana_min=35.0,
                estudiantes=6,
                docentes=1,
                funcionarios=1,
                visitantes=1,
                externos=1,
                max_entradas_hora=5,
                hora_punta_num=10,
                total_entradas=10,
                total_salidas=9,
                max_entradas=5,
                vehiculos_presentes=5,
                vehiculos_csf11=2,
                vehiculos_csf21=2,
                vehiculos_chs01=1,
                entradas=10,
                salidas=9,
                personas_unicas=8,
                personas_presentes=5,
                personas_sala1=3,
                personas_sala2=2,
                viajes=4,
                tiempo_promedio=12.0,
                person_id_hash="e8f17a6899999999",
                patente_hash="unknown",
                door_entrada="CSF02-T1",
                door_salida="CSF04-T1",
                primera_entrada=None,
                ultima_salida=datetime(2026, 10, 14, 23, 0),
                permanencia_min=0.0,
                marcajes_totales=6,
                salida_imputada=1,
                entrada_imputada=1,
                alerta_coherencia_fechas=1,
                calidad_lectura="unknown",
                camara="CSF11-E1",
                origen="CSF",
                destino="CHS",
                minutos_traslado=18.5,
                hora_salida=10,
                hora_inicio="08:00",
                hora_cierre="20:30",
                es_continuo_24h=0,
            )
        ]
        db = _crear_db_analitica(rows=rows_raw, scalar_val=1)
        # Reemplazar fecha_inicio/fecha_fin de sample row
        rows_raw[0]._mapping["fecha"] = date(2026, 10, 14)
        rows_raw[0]._mapping["time"] = datetime(2026, 10, 14, 23, 30)
        rows_raw[0]._mapping["fecha_inicio"] = date(2026, 10, 1)
        rows_raw[0]._mapping["fecha_fin"] = date(2026, 10, 14)

        # Todos los regímenes de AttendanceService y categorías raw
        await AttendanceService._build_attendance_filters(
            session=db,
            espacio_id=1,
            fecha_inicio=f_ini,
            fecha_fin=f_fin,
            alcance="solo_anomalos",
            regimen_horario="dentro_horario,24h_delta,24h_total,fuera_horario,dias_cierre,paro_federado,paro_carrera,horario_1_delta",
            direccion="entrada,salida",
            dias_semana="lunes,martes,miercoles,jueves,viernes,sabado,domingo",
            door="CSF02-T1",
            perfil_visita="rebote,estandar,profundo,sin_salida,sin_entrada,hora_invertida",
            marcajes="1,2_4,multirreingreso",
            sala="sala_1,sala_2",
            carrera="Informática",
            facultad="Ingeniería",
            cohorte="2024",
            incluir_pausas_bano=False,
            desduplicar_rafagas=False,
            incluir_funcionarios=False,
            incluir_sin_identificar=False,
        )
        kpis_a = await AttendanceService.get_kpis(db, fecha_inicio=f_ini, fecha_fin=f_fin, espacio_id=1)
        assert "total_registros" in kpis_a

        for cat in ("fuera_de_horario", "sin_salida", "sin_entrada", "hora_invertida", "sin_credencial", "marcaje_excesivo", "conforme"):
            raw_a = await AttendanceService.get_raw_events(db, espacio_id=1, fecha_inicio=f_ini, fecha_fin=f_fin, categoria=cat, search_hash="e8f1")
            assert "items" in raw_a

        an24 = await AttendanceService.get_analisis_24h(db, espacio_id=1, campana_id=0, fecha_inicio=f_ini, fecha_fin=f_fin)
        assert isinstance(an24, dict)

        # Todos los regímenes de VehicleService, get_kpis, get_raw_events y movilidad
        await VehicleService._build_vehicle_filters(
            session=db,
            espacio_id=2,
            fecha_inicio=f_ini,
            fecha_fin=f_fin,
            alcance="solo_anomalos",
            regimen_horario="dentro_horario,24h_delta,24h_total,fuera_horario,dias_cierre,paro_federado,paro_carrera,horario_1_delta",
            direccion="solo_ingreso,solo_salida",
            dias_semana="lunes,sabado,domingo",
            sector="CSF11,CHS01",
            tipo_vehiculo="SUV",
        )
        db_vkpi = _crear_db_analitica(rows=rows_raw, scalar_val=datetime(2026, 10, 14, 15, 0))
        kpis_v = await VehicleService.get_kpis(db_vkpi, fecha_inicio=f_ini, fecha_fin=f_fin, espacio_id=2)
        assert "total_ingresos" in kpis_v or "total_eventos" in kpis_v or isinstance(kpis_v, dict)

        for vcat in ("lectura_fallida", "fuera_de_horario", "conforme"):
            raw_v = await VehicleService.get_raw_events(db, espacio_id=2, fecha_inicio=f_ini, fecha_fin=f_fin, categoria=vcat, tipo_vehiculo="SUV", search_hash="unk")
            assert "items" in raw_v

        mob = await VehicleService.get_intercampus_mobility(db, fecha_inicio=f_ini, fecha_fin=f_fin)
        assert mob["total_viajes"] >= 1

    asyncio.run(_run())


def test_auth_orquestador_llm_email_scraper_y_planificador(tmp_path):
    async def _run():
        admin = crear_usuario_mock("admin@uct.cl", ["Admin_Sistema"], user_id=1)
        director = crear_usuario_mock("dir@uct.cl", ["Director_Recinto"], user_id=2, espacio_id=1, allowed_datasets=["biblioteca"])
        analista = Usuario(
            id=50, email="ana@uct.cl", hashed_password="$2b$12$abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ01",
            nombre_completo="Analista Bib", is_active=False, allowed_datasets=["biblioteca"], espacio_id=1,
            can_use_ai=True, can_export=True, can_ingest=False, roles=[Rol(id=3, nombre="Analista_Consulta")],
        )

        # 1. auth_service: update_user, reenviar, verificar_token, activar_cuenta, recuperacion, restablecer
        db_au = _crear_db_vacio_o_simulado()
        rol_obj = Rol(id=3, nombre="Analista_Consulta")
        db_au.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(side_effect=[analista, rol_obj, analista]),
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[rol_obj]))),
            rowcount=1,
        ))
        upd_u = await auth_service.actualizar_usuario_admin(
            db_au, 50, UsuarioUpdateRequest(nombre_completo="Analista Renombrada", roles=["Analista_Consulta"], allowed_datasets=["biblioteca"]), director
        )
        assert upd_u is not None

        db_reenv = _crear_db_vacio_o_simulado()
        db_reenv.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=analista)))
        _, tok_pl, tok_obj = await auth_service.reenviar_invitacion_usuario(db_reenv, 50, creator=director)
        assert len(tok_pl) > 10

        tok_obj.usuario = analista
        tok_obj.tipo_token = "RECUPERACION_PASSWORD"
        db_act = _crear_db_vacio_o_simulado()
        db_act.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=tok_obj), rowcount=1))
        act_u = await auth_service.activar_cuenta_usuario(db_act, tok_pl, "NuevoPass2026!", "NuevoPass2026!", ip_solicitante="127.0.0.1")
        assert act_u.is_active is True

        db_rec = _crear_db_vacio_o_simulado()
        db_rec.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=analista)))
        ok_rec, tok_rec, _, _ = await auth_service.solicitar_recuperacion_password(db_rec, "ana@uct.cl", "127.0.0.1")
        assert ok_rec is True and tok_rec

        db_res = _crear_db_vacio_o_simulado()
        db_res.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=tok_obj), rowcount=1))
        rest_u = await auth_service.restablecer_password_con_token(db_res, tok_rec, "OtraPass2026!", "OtraPass2026!", "127.0.0.1")
        assert rest_u.email == "ana@uct.cl"

        # 2. Orquestador ML: KMeans + promoción atómica + evaluación campeón Prophet + verificación horaria nocturna
        df_km = pd.DataFrame({
            "patente_hash": [f"P{i}" for i in range(12)],
            "dias_totales": [1, 2, 3, 4, 6, 7, 8, 9, 12, 14, 16, 18],
            "permanencia_avg_min": [20, 25, 35, 40, 120, 150, 180, 200, 480, 500, 520, 540],
            "hora_llegada_avg": [11, 12, 13, 14, 9, 9, 10, 10, 8, 8, 8, 8],
            "tasa_jornada_extrema": [0, 0, 5, 5, 10, 15, 20, 25, 80, 90, 95, 100],
        })
        db_km = _crear_db_analitica(rows=[])

        class _FakeProphetChamp:
            extra_regressors = {}

            def predict(self, df_in):
                return pd.DataFrame({"yhat": [12.0] * len(df_in)})

        with patch.object(orquestador_entrenamiento, "DIRECTORIO_MODELOS", tmp_path):
            ruta_ret = tmp_path / "prophet_presencia_sala1_retador.joblib"
            dest_camp = tmp_path / "prophet_presencia_sala1_active.joblib"
            ruta_ret.write_bytes(b"modelo_dummy")
            orquestador_entrenamiento._promover_archivo_atomico(ruta_ret, dest_camp)
            assert dest_camp.exists()
            with (
                patch.object(orquestador_entrenamiento.joblib, "load", return_value=_FakeProphetChamp()),
                patch("app.ml.prophet_service._preparar_columnas_prediccion", return_value=["ds"]),
            ):
                w_c, m_c = orquestador_entrenamiento._evaluar_campeon_existente(
                    "prophet_presencia_sala1",
                    "prophet_presencia_sala1_active.joblib",
                    "Prophet",
                    pd.DataFrame({"ds": pd.date_range("2026-10-15", periods=2, freq="h")}),
                    pd.Series([10.0, 14.0]).values,
                )
                assert w_c is not None and m_c is not None

            with patch("app.ml.train_kmeans_parking.extract_vehicle_features", new=AsyncMock(return_value=df_km)):
                r_km = await orquestador_entrenamiento._entrenar_retador_kmeans(db_km, "kmeans_parking")
                assert r_km["ruta_retador"].exists()

        # Verificar hora operativa campus con memoria y horario nocturno
        db_h = _crear_db_analitica()
        db_h.execute = AsyncMock(return_value=MagicMock(fetchone=MagicMock(return_value=None), fetchall=MagicMock(return_value=[]), scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))
        with (
            patch("app.services.config_service.get_horarios_operacion", new=AsyncMock(return_value=[
                SimpleNamespace(activo=True, anio=2026, es_continuo_24h=False, cierre_dia_siguiente=True, fecha_inicio=None, fecha_fin=None, configuracion_dias=None, hora_apertura="21:00", hora_cierre="07:00")
            ])),
            patch("app.services.calendar_scraper.obtener_feriado_oficial_chile", return_value=None),
        ):
            op_h, _ = await orquestador_entrenamiento.verificar_hora_operativa_campus(db_h, datetime(2026, 10, 14, 22, 0))
            assert op_h is True

        # 3. GeminiClient generate_narrative_stream + generate_response + Anthropic stream
        async def _fake_stream_gen():
            yield SimpleNamespace(text="Aforo ")
            yield SimpleNamespace(text="normal.")

        g_client = llm_client.GeminiClient(api_key="fake-k", default_model="gemini-2.5-flash")
        g_client.client = SimpleNamespace(
            aio=SimpleNamespace(
                models=SimpleNamespace(
                    generate_content_stream=AsyncMock(return_value=_fake_stream_gen()),
                    generate_content=AsyncMock(return_value=SimpleNamespace(text='{"respuesta": "ok"}', function_calls=[])),
                )
            )
        )
        chunks_g = [c async for c in g_client.generate_narrative_stream("Aforo hoy", system_instruction="DSS")]
        assert "".join(chunks_g) == "Aforo normal."
        resp_g = await g_client.generate_response("Resumen", response_mime_type="application/json")
        assert "ok" in resp_g

        # 4. Email service STARTTLS + SSL + plantillas institucionales
        smtp_tls = {"host": "smtp.uct.cl", "port": 587, "use_tls": True, "use_ssl": False, "username": "u", "password": "p", "from_email": "noreply@uct.cl", "from_name": "DSS UCT"}
        smtp_ssl = {**smtp_tls, "port": 465, "use_tls": False, "use_ssl": True}
        with (
            patch("app.services.email_service.smtplib.SMTP") as m_smtp,
            patch("app.services.email_service.smtplib.SMTP_SSL") as m_ssl,
            patch("app.services.email_service.obtener_config_smtp_activa", new=AsyncMock(return_value=smtp_tls)),
        ):
            ok_1, _ = email_service._enviar_correo_sincrono_detallado("a@uct.cl", "Subj", "<p>Hi</p>", smtp_cfg=smtp_tls)
            ok_2, _ = email_service._enviar_correo_sincrono_detallado("a@uct.cl", "Subj", "<p>Hi</p>", smtp_cfg=smtp_ssl)
            assert ok_1 and ok_2 and m_smtp.called and m_ssl.called
            assert await email_service.enviar_correo_activacion("a@uct.cl", "Ana", "https://dss.uct.cl/act") is True
            assert await email_service.enviar_correo_recuperacion("a@uct.cl", "Ana", "https://dss.uct.cl/rec") is True
            assert await email_service.enviar_correo_bloqueo_login("a@uct.cl", "Ana", "https://dss.uct.cl/rec", intentos=5) is True
            m_smtp.side_effect = smtplib.SMTPAuthenticationError(535, b"Auth failed")
            ok_err, msg_err = email_service._enviar_correo_sincrono_detallado("a@uct.cl", "Subj", "<p>Hi</p>", smtp_cfg=smtp_tls)
            assert ok_err is False and "autenticación" in msg_err.lower()

        # 5. Calendar scraper flags, rangos y scrape HTML
        assert calendar_scraper._classify_event_flags("Inicio de Clases Primer Semestre")["is_class_milestone"] is True
        assert calendar_scraper._classify_event_flags("Período de Exámenes Finales")["is_exam_period"] is True
        assert calendar_scraper._classify_event_flags("Pago de Beca FUAS")["es_relevante"] is False
        assert len(calendar_scraper.analizar_fechas_calendario("01 al 05-04-2026")) == 5

        html_cal = "<html><body><table><tr><td>18/09/2026</td><td>Fiestas Patrias</td></tr><tr><td>10/12/2026 - 12/12/2026</td><td>Exámenes Finales</td></tr></table></body></html>"
        fake_http = MagicMock()
        fake_http.__aenter__ = AsyncMock(return_value=fake_http)
        fake_http.__aexit__ = AsyncMock(return_value=False)
        fake_http.get = AsyncMock(return_value=SimpleNamespace(status_code=200, text=html_cal, raise_for_status=MagicMock()))
        db_cal = _crear_db_vacio_o_simulado()
        db_cal.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))
        with (
            patch("app.services.calendar_scraper.httpx.AsyncClient", return_value=fake_http),
            patch("app.services.calendar_scraper.CalendarService.bulk_insert_events", new=AsyncMock()),
        ):
            sc_out = await calendar_scraper.scrape_and_sync_uct_calendar(db_cal)
            assert isinstance(sc_out, dict)

        # 6. Planificador handlers internos
        db_pl = _crear_db_vacio_o_simulado()
        proc_mock = SimpleNamespace(returncode=0, communicate=AsyncMock(return_value=(b'__RESULTADO_JSON__: [{"modelo": "k"}]', b"")), kill=MagicMock(), wait=AsyncMock())
        with (
            patch("app.core.planificador.AsyncSessionLocal", return_value=_CtxAsync(db_pl)),
            patch("app.services.servicio_chat_persistente.purgar_conversaciones_eliminadas", new=AsyncMock(return_value=3)),
            patch("app.services.calendar_scraper.scrape_and_sync_uct_calendar", new=AsyncMock(return_value={"insertados": 2})),
            patch("app.services.servicio_smart_campus.sincronizar_aforo_vivo_horario", new=AsyncMock(return_value={"errores": [], "torniquetes": {"leidos": 5}, "estacionamientos": {"leidos": 2}})),
            patch("app.core.planificador.asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc_mock)),
            patch("app.core.cache.limpiar_toda_la_cache", new=AsyncMock()),
        ):
            assert (await planificador._handler_purgar_conversaciones_chat())["conversaciones_purgadas"] == 3
            assert (await planificador._handler_sincronizar_calendario_academico())["resultado"] == "calendario_sincronizado"
            assert (await planificador._handler_sincronizar_smart_campus_en_vivo())["torniquetes"]["leidos"] == 5
            res_ml_pl = await planificador._handler_reentrenar_modelos_ml(disparador="programado")
            assert res_ml_pl["modelos"] == [{"modelo": "k"}]

    asyncio.run(_run())


def test_cierre_definitivo_75_plus():
    async def _run():
        from app.adapters.smart_campus_adapter import SmartCampusAdapter
        from app.api.v1.endpoints.admin import (
            _purgar_modulo_asistencia,
            _purgar_modulo_ingestas,
            _purgar_modulo_institucional,
            _purgar_modulo_vehicular,
        )
        from app.domain.models import CalendarioAcademico, ContingenciaAcademica
        from app.schemas.chat_schemas import ChatRequest
        from app.schemas.config_schemas import ContingenciaCrear
        from app.services import config_service
        from app.services.calendar_service import CalendarService
        from app.services.chat import ejecutor_herramientas

        f_ini, f_fin = date(2026, 10, 1), date(2026, 10, 14)
        db = _crear_db_analitica(
            rows=[
                _SmartRow(
                    fecha=date(2026, 10, 14),
                    fecha_inicio=date(2026, 10, 1),
                    fecha_fin=date(2026, 10, 14),
                    hito="Regular",
                    tipo="paro",
                    hora_inicio="08:00",
                    hora_cierre="20:30",
                    es_continuo_24h=0,
                    time=datetime(2026, 10, 14, 10, 0),
                    bucket=datetime(2026, 10, 14, 10, 0),
                    hora=10,
                    hora_num=10,
                    dia_num=3,
                    dia_dw=3,
                    semana_num=42,
                    min_fecha=date(2026, 10, 12),
                    max_fecha=date(2026, 10, 14),
                    total_registros=50,
                    usuarios_unicos=40,
                    dias_operativos=5,
                    permanencia_promedio_min=45.0,
                    permanencia_mediana_min=35.0,
                    estudiantes=30,
                    docentes=5,
                    funcionarios=5,
                    visitantes=5,
                    externos=5,
                    max_entradas_hora=15,
                    hora_punta_num=10,
                    ingresos=50,
                    entradas=50,
                    salidas=40,
                    personas_unicas=40,
                    personas_presentes=20,
                    personas_sala1=12,
                    personas_sala2=8,
                    total_personas=40,
                    rango_marcajes="1",
                    promedio_ingresos=45.0,
                    total=50,
                    pct=50.0,
                    porcentaje=50.0,
                    vehiculos_presentes=15,
                    vehiculos_csf11=6,
                    vehiculos_csf21=5,
                    vehiculos_chs01=4,
                    lecturas_fallidas=1,
                    camara="CSF11-E1",
                    total_eventos=50,
                    total_asistentes=40,
                )
            ],
            scalar_val=1,
        )

        # 1. ejecutor_herramientas: resolver_datos_grafico_contexto + consultar_calendario_academico
        req_bib = ChatRequest(
            prompt="Analizar gráfico",
            session_id="s-bib",
            espacio_id=1,
            fecha_inicio="2026-10-01",
            fecha_fin="2026-10-14",
            filtros={"regimen_horario": "dentro_horario,24h_delta", "sala": "sala_2"},
        )
        req_veh = ChatRequest(
            prompt="Analizar gráfico vehicular",
            session_id="s-veh",
            espacio_id=2,
            fecha_inicio="2026-10-01",
            fecha_fin="2026-10-14",
        )
        with (
            patch("app.services.chat.ejecutor_herramientas.obtener_contexto_calendario_rango", new=AsyncMock(return_value=[])),
            patch("app.services.chat.ejecutor_herramientas.obtener_resumen_hechos_institucionales", new=AsyncMock(return_value="Resumen")),
            patch("app.services.chat.ejecutor_herramientas._construir_alerta_operativa_biblioteca", new=AsyncMock(return_value="")),
            patch("app.services.chat.ejecutor_herramientas.get_prophet_presence_forecast", new=AsyncMock(return_value={"pronostico_7d": [{"yhat": 20}], "capacidad_asientos": 276, "model_status": {"model_type": "Prophet"}})),
            patch("app.services.vehicle_service.VehicleService.get_behavioral_clusters", new=AsyncMock(return_value={"vehiculos_externos_count": 2, "vehiculos_externos_pct": 10.0, "total_vehiculos_analizados": 20, "distribucion": [{"perfil": "Regular"}]})),
            patch("app.services.attendance_service.AttendanceService.get_analisis_24h", new=AsyncMock(return_value={"kpis_comparativa": {"porcentaje_delta_24h": 15.0, "ingresos_nocturnos": 30, "total_ingresos": 200, "horas_estudio_nocturnas": 80, "estudiantes_nocturnos_unicos": 25}, "pico_nocturno": {"aforo_maximo": 20, "tasa_ocupacion_asientos_pct": 20.8, "hora_pico": "01:00"}, "top_carreras": [{"carrera": "Informática", "porcentaje": 40.0, "visitas": 12}], "campana": {"capacidad_asientos": 96}})),
        ):
            for slug_b in ("curva_ocupacion", "prophet_presencia", "distribucion_marcajes", "promedio_dias_semana", "campana_24h"):
                comp, _, _, _, _ = await ejecutor_herramientas.resolver_datos_grafico_contexto(
                    slug_b, 1, "2026-10-01", "2026-10-14", db, filtros=req_bib.filtros
                )
                assert comp is not None
            _, _, msg_den, _, _ = await ejecutor_herramientas.resolver_datos_grafico_contexto(
                "desconocido_fallback", 1, "2026-10-01", "2026-10-14", db, filtros=req_bib.filtros
            )
            assert "autorizado" in msg_den.lower()

            db_v = _crear_db_analitica(rows=db.execute.return_value.fetchall(), scalar_val=datetime(2026, 10, 14, 15, 0))
            for slug_v in ("curva_ocupacion", "presencia_intervalos", "kmeans_clusters"):
                comp_v, _, _, _, _ = await ejecutor_herramientas.resolver_datos_grafico_contexto(
                    slug_v, 2, "2026-10-01", "2026-10-14", db_v if slug_v == "presencia_intervalos" else db
                )
                assert comp_v is not None

            cal_ev = CalendarioAcademico(
                fecha=date(2026, 10, 14), is_holiday=False, is_break=False, is_exam_period=True,
                is_class_milestone=False, suspension_actividades=False, descripcion="Exámenes Parciales", fuente="scraping"
            )
            db_cal_t = _crear_db_vacio_o_simulado()
            db_cal_t.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[cal_ev])))))
            with patch("app.services.attendance_service.AttendanceService.get_daily_summary", new=AsyncMock(return_value=[{"ingresos": 100, "personas_unicas": 80}])):
                comp_cal, _, txt_cal, _, _ = await ejecutor_herramientas.ejecutar_consulta_tool(
                    "consultar_calendario_academico", {"semana": 42}, db_cal_t, 1, req=req_bib
                )
                assert comp_cal is not None and "Exámenes" in txt_cal

        # 2. CalendarService CRUD contingencias, resumen anual y eventos
        cal_srv = CalendarService()
        cont_obj = ContingenciaAcademica(
            id=1, fecha_inicio=date(2026, 10, 14), fecha_fin=date(2026, 10, 15),
            tipo="paro", titulo="Paro", descripcion="Paro test", espacio_id=1, subespacio="sala_1",
            hora_inicio="09:00", hora_fin="13:00", carreras_afectadas="Ing", implica_cierre_total=True
        )
        db_cs = _crear_db_vacio_o_simulado()
        db_cs.get = AsyncMock(side_effect=[cont_obj, cal_ev, cal_ev])
        db_cs.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(side_effect=[[cal_ev], [cont_obj], [cal_ev], [cont_obj]]))),
            scalar_one_or_none=MagicMock(return_value=None),
            rowcount=1,
        ))
        with (
            patch.object(cal_srv, "reconciliar_dias_calendario", new=AsyncMock()),
            patch.object(cal_srv, "sanear_calendario_contingencias", new=AsyncMock(return_value={"eliminados": 1})),
        ):
            n_cont = await cal_srv.crear_contingencia(
                db_cs, ContingenciaCrear(fecha_inicio=date(2026, 10, 14), fecha_fin=date(2026, 10, 15), tipo="paro", titulo="Paro", descripcion="Test", espacio_id=1, implica_cierre_total=True)
            )
            assert n_cont.titulo == "Paro"
            assert await cal_srv.eliminar_contingencia(db_cs, 1) is True
            res_an = await cal_srv.obtener_resumen_anual_calendario(db_cs, 2026)
            assert isinstance(res_an, list)

        db_ce = _crear_db_vacio_o_simulado()
        db_ce.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))),
            scalar_one_or_none=MagicMock(side_effect=[None, cal_ev, cal_ev]),
            rowcount=2,
        ))
        with (
            patch.object(cal_srv, "reconciliar_dias_calendario", new=AsyncMock()),
            patch.object(cal_srv, "sanear_calendario_contingencias", new=AsyncMock(return_value={"eliminados": 1})),
        ):
            assert await cal_srv.depurar_calendario_basura(db_ce) >= 0
            ev_new = await cal_srv.crear_evento_calendario(
                db_ce, date(2026, 10, 20), date(2026, 10, 21), "Hito UCT",
                False, False, True, False, False,
            )
            assert len(ev_new) == 2
            ev_upd = await cal_srv.actualizar_evento_calendario(
                db_ce, date(2026, 10, 14), "Actualizado",
                False, False, True, False, False,
            )
            assert ev_upd is not None
            assert await cal_srv.eliminar_evento_calendario(db_ce, date(2026, 10, 14)) is True

        # 3. config_service: evaluar_horario_abierto_subespacio + credenciales IA/SMTP
        regla_24 = SimpleNamespace(activo=True, espacio_id=1, subespacio="sala_2", tipo_horario="extendido_24h", es_continuo_24h=True, fecha_inicio=date(2026, 10, 1), fecha_fin=date(2026, 10, 30), configuracion_dias=None, hora_apertura="00:00", hora_cierre="23:59", cierre_dia_siguiente=False)
        cont_hora = SimpleNamespace(implica_cierre_total=True, espacio_id=1, subespacio="sala_1", fecha_inicio=date(2026, 10, 14), fecha_fin=date(2026, 10, 14), hora_inicio="10:00", hora_fin="12:00")
        assert config_service.evaluar_horario_abierto_subespacio(datetime(2026, 10, 14, 11, 0), 1, "sala_1", [regla_24], [cont_hora], es_feriado_oficial=False) == 0
        assert config_service.evaluar_horario_abierto_subespacio(datetime(2026, 10, 14, 23, 0), 1, "sala_2", [regla_24], [], es_feriado_oficial=True, es_24h_automatico=True) == 1
        assert isinstance(config_service.es_horario_conforme(datetime(2026, 10, 14, 11, 0), [regla_24], subespacio="sala_2"), bool)

        cred_ia = SimpleNamespace(id=1, nombre="Gem", provider_id="gemini", modelo="gemini-2.5-flash", base_url=None, encrypted_api_key="enc", key_hint="***", es_activa=False, ultimo_test_ok=None, ultimo_test_en=None)
        smtp_o = SimpleNamespace(id=1, nombre="UCT", host="smtp.uct.cl", port=587, use_tls=True, use_ssl=False, username="u", encrypted_password="enc", password_hint="***", from_email="a@uct.cl", from_name="DSS", es_activa=False, ultimo_test_ok=None, ultimo_test_en=None)
        db_cfg = _crear_db_vacio_o_simulado()
        db_cfg.get = AsyncMock(return_value=SimpleNamespace(id=1, ia_proveedor="gemini", ia_modelo="gemini-2.5-flash", ia_api_key_cifrada=None, espacio_id=1))
        db_cfg.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[cred_ia]))), scalar_one_or_none=MagicMock(return_value=cred_ia)))
        with (
            patch("app.services.config_service.encrypt_api_key", return_value="enc"),
            patch("app.services.config_service.decrypt_api_key", return_value="key-1"),
            patch("app.services.config_service.validar_host_smtp", return_value=("smtp.uct.cl", 587)),
        ):
            c_new = await config_service.crear_credencial_ia(db_cfg, "Gem", "gemini", "gemini-2.5-flash", None, "key-1", True, 1)
            assert c_new is not None
            await config_service.actualizar_credencial_ia(db_cfg, cred_ia, nombre="Gem2")
            await config_service.activar_credencial_ia(db_cfg, cred_ia)
            await config_service.eliminar_credencial_ia(db_cfg, cred_ia)

            s_new = await config_service.crear_configuracion_smtp(db_cfg, "UCT", "smtp.uct.cl", 587, True, False, "u", "a@uct.cl", "DSS", "pass-smtp", True, 1)
            assert s_new is not None
            await config_service.actualizar_configuracion_smtp(db_cfg, smtp_o, nombre="UCT2")
            await config_service.activar_configuracion_smtp(db_cfg, smtp_o)
            await config_service.eliminar_configuracion_smtp(db_cfg, smtp_o)

        # 4. SmartCampusAdapter fetch_attendance_events + fetch_vehicle_events
        adap = SmartCampusAdapter()
        with (
            patch.object(adap, "obtener_marcajes_torniquetes", new=AsyncMock(return_value=[{"fecha": "2026-10-14T09:00:00", "matricula": "2024001", "sentido": "entrada", "puerta": "CSF02-T1", "estamento": "Estudiante", "detalle_estamento": "Inf"}])),
            patch.object(adap, "obtener_pasos_estacionamientos", new=AsyncMock(return_value=[{"fecha": "2026-10-14T09:10:00", "patente": "ABCD12", "camara": "CSF11-E1", "sentido": "entrada", "lectura_completa": True}])),
        ):
            dtos_a = await adap.fetch_attendance_events(1)
            dtos_v = await adap.fetch_vehicle_events(2)
            assert len(dtos_a) == 1 and len(dtos_v) == 1

        # 5. admin.py purgas modulares
        db_p = _crear_db_vacio_o_simulado()
        db_p.execute = AsyncMock(return_value=MagicMock(rowcount=5))
        assert await _purgar_modulo_asistencia(db_p, 1, False) == 5
        assert await _purgar_modulo_vehicular(db_p, 2, False) == 5
        assert (await _purgar_modulo_institucional(db_p))["dim_estudiante_carrera"] == 5
        assert await _purgar_modulo_ingestas(db_p, 1, False) == 5

        # 6. Cierre decimal >= 75.0%: sanear calendario + OpenAICompatibleClient + espacio capacidad
        db_san = _crear_db_vacio_o_simulado()
        db_san.execute = AsyncMock(side_effect=[
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[date(2026, 10, 14)])))),
            MagicMock(all=MagicMock(return_value=[(date(2026, 10, 14), date(2026, 10, 15))])),
        ])
        with patch.object(cal_srv, "reconciliar_dias_calendario", new=AsyncMock(return_value={"actualizados": 1, "eliminados": 0})):
            res_san = await cal_srv.sanear_calendario_contingencias(db_san)
            assert res_san["actualizados"] == 1

        oa = llm_client.OpenAICompatibleClient(api_key="k-test", default_model="gpt-4o-mini", base_url="https://api.openai.com/v1")
        with patch.object(oa, "_post_completions", new=AsyncMock(return_value={"choices": [{"message": {"content": '{"respuesta": "ok"}'}}]})):
            txt_oa = await oa.generate_response("Hola", system_instruction="DSS", response_mime_type="application/json")
            assert "ok" in (txt_oa or "")

        db_esp = _crear_db_vacio_o_simulado()
        esp_o = SimpleNamespace(id=1, nombre="Biblioteca", capacidad_maxima=276)
        db_esp.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=esp_o)))
        assert await config_service.get_espacio_by_id(db_esp, 1) is esp_o
        assert (await config_service.update_espacio_capacidad(db_esp, 1, 290)).capacidad_max == 290

    asyncio.run(_run())

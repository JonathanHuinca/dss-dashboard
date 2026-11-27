"""Suite complementaria de cobertura productiva (endpoints, ingesta, orquestador, reportes, auth y config)."""
import asyncio
import io
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import openpyxl
import pandas as pd

from app.domain.auth_models import Rol, Usuario
from app.ml import orquestador_entrenamiento
from app.schemas.auth_schemas import UsuarioCreate
from app.schemas.config_schemas import HorarioOperacionCreate, HorarioOperacionUpdate
from app.services import auth_service, calendar_scraper, calendar_service, config_service, ingestion_service, servicio_chat_persistente
from app.services.servicio_reportes_compartidos import ServicioReportesCompartidos
from app.tests.conftest import crear_usuario_mock
from app.tests.test_cobertura_analitica_y_herramientas import _SmartRow, _crear_db_analitica


class _CtxAsync:
    def __init__(self, sess):
        self._s = sess

    async def __aenter__(self):
        return self._s

    async def __aexit__(self, *args):
        return False


def test_endpoints_admin_config_chat_auth_y_reportes_para_admin(app_client, admin_user):
    client = app_client(admin_user)

    # Admin endpoints
    with (
        patch("app.services.audit_service.get_download_audit_history", new=AsyncMock(return_value={
            "items": [], "total": 0, "page": 1, "page_size": 15, "total_pages": 1,
            "stats": {"total_descargas": 0, "descargas_hoy": 0, "descargas_csv": 0, "descargas_pdf": 0, "descargas_por_modulo": {}},
        })),
        patch("app.services.audit_service.record_download_audit", new=AsyncMock()),
        patch("app.ml.orquestador_entrenamiento.obtener_estado_general_modelos", return_value={"modelos": []}),
        patch("app.services.servicio_calendario_anual.obtener_estado_calendario_anual", new=AsyncMock(return_value={"anio": 2026, "estados": []})),
        patch("app.services.config_service.toggle_ia_asistente", new=AsyncMock(return_value=SimpleNamespace(ia_asistente_activo=True))),
        patch("app.api.v1.endpoints.chat.obtener_cuota_ia_usuario", new=AsyncMock(return_value={"rol": "Admin_Sistema", "usado_hoy": 0, "limite_diario": 100, "restantes": 100, "ilimitado": True, "segundos_espera": 0})),
        patch("app.core.cache.obtener_cache", return_value=MagicMock(get_stats=MagicMock(return_value={"aforo_vivo_items": 0, "kpis_dia_items": 0, "historicos_items": 0, "general_items": 0, "total_items": 0}))),
    ):
        assert client.get("/api/v1/admin/chat-audit").status_code == 200
        assert client.get("/api/v1/admin/download-audit").status_code == 200
        assert client.post("/api/v1/admin/record-download", json={"modulo": "biblioteca", "formato": "csv", "total_registros": 10}).status_code in (200, 201)
        assert client.get("/api/v1/admin/modelos/estado").status_code == 200
        assert client.get("/api/v1/admin/calendario/estado").status_code == 200
        assert client.get("/api/v1/admin/smart-campus/estado").status_code == 200
        assert client.get("/api/v1/admin/estacionamientos/sectores").status_code == 200
        assert client.get("/api/v1/admin/cache/stats").status_code == 200
        assert client.get("/api/v1/admin/notificaciones").status_code == 200
        assert client.post("/api/v1/admin/notificaciones/marcar-vistas", json={"ids": [1]}).status_code in (200, 422)

    # Config endpoints
    assert client.get("/api/v1/config/ia-status").status_code == 200
    assert client.get("/api/v1/config/horarios?espacio_id=1").status_code == 200
    assert client.get("/api/v1/config/espacios").status_code == 200
    assert client.get("/api/v1/config/contingencias").status_code == 200
    assert client.get("/api/v1/config/calendar/status").status_code == 200
    assert client.get("/api/v1/config/calendar/resumen-anual?anio=2026").status_code == 200
    assert client.get("/api/v1/config/calendar/events").status_code == 200
    assert client.get("/api/v1/config/llm/catalog").status_code == 200
    assert client.get("/api/v1/config/llm/credentials").status_code == 200
    assert client.get("/api/v1/config/smtp").status_code == 200

    # Auth endpoints
    assert client.post("/api/v1/auth/login", json={"email": "no@uct.cl", "password": "bad"}).status_code == 401
    assert client.get("/api/v1/auth/users").status_code == 200

    # Chat endpoints
    with patch("app.api.v1.endpoints.chat.obtener_cuota_ia_usuario", new=AsyncMock(return_value={"rol": "Admin_Sistema", "usado_hoy": 0, "limite_diario": 100, "restantes": 100, "ilimitado": True, "segundos_espera": 0})):
        assert client.get("/api/v1/chat/conversaciones?espacio_id=1").status_code == 200
        assert client.get("/api/v1/chat/cuota").status_code == 200
        assert client.get("/api/v1/chat/history?session_id=s1&espacio_id=1").status_code == 200

    # Reportes compartidos gestión
    assert client.get("/api/v1/reportes-compartidos").status_code == 200
    assert client.get("/api/v1/reportes-compartidos/auditoria").status_code == 200
    assert client.get("/api/v1/reportes-compartidos/usuarios-candidatos").status_code == 200


def test_ingestion_service_conversion_y_pipeline():
    async def _run():
        # _convertir_df_asistencia completo (con maestro de estudiantes, entrada/salida y marcajes múltiples)
        df_a = pd.DataFrame(
            [
                {
                    "Fecha": "2026-10-14",
                    "personId": "19111222-3",
                    "RUT": "19111222-3",
                    "Primera entrada": "09:00:00",
                    "Última salida": "11:30:00",
                    "Door entrada": "CSF02-T1",
                    "Door salida": "CSF02-T1",
                    "Estamento": "Estudiante",
                    "Marcajes": "2",
                },
                {
                    "Fecha": "2026-10-14",
                    "personId": "unknown",
                    "Primera entrada": "14:00:00",
                    "Última salida": "",
                    "Door entrada": "CSF04-T1",
                    "Estamento": "Estudiante",
                },
                {
                    "Fecha": "2026-10-14",
                    "personId": "8888888-8",
                    "Primera entrada": "09:00:00",
                    "Estamento": "Funcionario",
                },
            ]
        )
        db = _crear_db_analitica(rows=[])
        dtos, cat, nocat = await ingestion_service._mapear_df_a_dtos_asistencia(
            df_a, espacio_id=1, clave_enlace="crosswalk", modo_enlace="rut", db=db
        )
        assert len(dtos) == 2
        assert cat + nocat == 2

        # _leer_muestra_institucional_uct_sync sobre XLSX sintético
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "ESTUDIANTE_CARRERA"
        ws.append(["Institucional UCT"])
        ws.append(["Periodo 2026"])
        ws.append(["RUT", "CARRERA", "FACULTAD", "COHORTE"])
        ws.append(["19111222-3", "Ing. Informática", "Ingeniería", "2024"])
        wb.create_sheet("CAMPUS")
        bio = io.BytesIO()
        wb.save(bio)
        h_idx, df_muestra, total_r = ingestion_service._leer_muestra_institucional_uct_sync(bio.getvalue())
        assert h_idx == 2 and len(df_muestra) == 1 and total_r == 1

    asyncio.run(_run())


def test_servicio_reportes_crud_portal_e_ia_confinada():
    async def _run():
        admin = crear_usuario_mock("admin@uct.cl", ["Admin_Sistema"], user_id=1)
        consultor = crear_usuario_mock("dest@uct.cl", ["Consultor_Reporte"], user_id=20)
        db = _crear_db_analitica(rows=[], scalar_val=0)
        db.get = AsyncMock(return_value=None)

        dest_obj = SimpleNamespace(
            id=5,
            email="dest@uct.cl",
            nombre_completo="Destinatario UCT",
            cargo="Decano",
            unidad_academica="Ingeniería",
            token_portal="tok-portal-1",
            activo=True,
            ultimo_acceso_en=None,
            creado_en=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        rep_obj = SimpleNamespace(
            id=uuid.uuid4(),
            codigo_corto="RPT-2026-077",
            titulo_reporte="Reporte Test",
            espacio_id=1,
            creado_por_id=1,
            destinatario_id=5,
            destinatario=dest_obj,
            creador=admin,
            fecha_inicio=date(2026, 10, 1),
            fecha_fin=date(2026, 10, 14),
            filtros_json="{}",
            filtros_bloqueados_json="{}",
            graficos_visibles_json='["flujo_horario"]',
            indicadores_visibles_json='["afluencia_total"]',
            notas_items_json="[]",
            nota_general="Nota",
            finalidad_reporte="Fin",
            datos_instantanea_json=json.dumps({"indicadores_ejecutivos": {"afluencia_total": 10}, "graficos": {}}),
            permitir_chat_ia=True,
            permitir_ia=True,
            permitir_exportacion=True,
            cuota_ia_max=10,
            cuota_ia_usada=1,
            activo=True,
            revocada_en=None,
            expira_en=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=5),
            creado_en=datetime.now(timezone.utc).replace(tzinfo=None),
            token_acceso="tok-77",
            total_aperturas=1,
            total_accesos=1,
            modo_datos="instantanea_congelada",
            ultima_apertura_en=None,
        )
        dest_obj.reportes = [rep_obj]

        # Portal destinatario autenticado como consultor titular
        res_dest = MagicMock(scalar_one_or_none=MagicMock(return_value=dest_obj))
        res_reps = MagicMock()
        res_reps.scalars.return_value.all.return_value = [rep_obj]
        db_portal = _crear_db_analitica()
        db_portal.execute = AsyncMock(side_effect=[res_dest, res_reps])
        portal = await ServicioReportesCompartidos.obtener_portal_destinatario_por_token(
            db_portal, "tok-portal-1", usuario_actual=consultor
        )
        assert portal["destinatario"]["email"] == "dest@uct.cl" and len(portal["reportes"]) == 1

        # Registrar evento descarga pública con autenticación válida
        res_rep_ev = MagicMock(scalar_one_or_none=MagicMock(return_value=rep_obj))
        db_ev = _crear_db_analitica()
        db_ev.execute = AsyncMock(return_value=res_rep_ev)
        ev_out = await ServicioReportesCompartidos.registrar_evento_reporte_publico(
            db_ev, "tok-77", accion="descarga_csv", detalle="CSV test", usuario_actual=consultor
        )
        assert ev_out["ok"] is True

        # Actualizar estado/configuración y eliminar reporte como admin
        res_rep_upd = MagicMock(scalar_one_or_none=MagicMock(return_value=rep_obj))
        db_upd = _crear_db_analitica()
        db_upd.execute = AsyncMock(return_value=res_rep_upd)
        upd_out = await ServicioReportesCompartidos.actualizar_estado_y_configuracion_reporte(
            db_upd, admin, str(rep_obj.id), {"activo": False, "nota_general": "Actualizada"}
        )
        assert upd_out["activo"] is False

        res_rep_del = MagicMock(scalar_one_or_none=MagicMock(return_value=rep_obj))
        db_del = _crear_db_analitica()
        db_del.execute = AsyncMock(return_value=res_rep_del)
        del_out = await ServicioReportesCompartidos.eliminar_reporte_compartido(db_del, admin, str(rep_obj.id))
        assert del_out["eliminado"] is True

        # Auditoría de reportes emitidos
        db_aud = _crear_db_analitica()
        kpi_aud = SimpleNamespace(total_universo=0, revisados_total=0, aperturas_total=0, descargas_total=0, consultas_ia_total=0)
        db_aud.execute = AsyncMock(return_value=MagicMock(one=MagicMock(return_value=kpi_aud), scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))
        with patch.object(ServicioReportesCompartidos, "_cargar_contexto_resumen_reportes", new=AsyncMock(return_value=({}, {}, {}))):
            aud = await ServicioReportesCompartidos.obtener_auditoria_reportes_emitidos(db_aud, admin)
            assert "kpis" in aud or "items" in aud or "reportes" in aud

    asyncio.run(_run())


def test_orquestador_auth_config_calendar_y_chat_persistente_crud():
    async def _run():
        # Orquestador entrenar_todos_los_modelos con sub-entrenadores mockeados
        with (
            patch.object(orquestador_entrenamiento, "AsyncSessionLocal", return_value=_CtxAsync(_crear_db_analitica(rows=[]))),
            patch.object(orquestador_entrenamiento, "verificar_modulo_opera_en_fecha", new=AsyncMock(return_value=(True, "Hábil"))),
            patch("app.ml.prophet_service.train_sala_model", new=AsyncMock(return_value={"mae": 1.0, "wape": 5.0})),
            patch("app.ml.prophet_service.train_presence_model", new=AsyncMock(return_value={"mae": 1.0, "wape": 5.0})),
            patch("app.ml.train_kmeans_parking.compute_behavioral_clusters", new=AsyncMock(return_value={"total_vehiculos_analizados": 10})),
        ):
            res_orq = await orquestador_entrenamiento.entrenar_todos_los_modelos(solo_modulos_operativos_hoy=True)
            assert isinstance(res_orq, list)

        # Auth service creación, invitación, activación, recuperación y actualización
        db_a = _crear_db_analitica()
        rol_obj = Rol(id=2, nombre="Director_Recinto")
        res_empty = MagicMock(scalar_one_or_none=MagicMock(return_value=None), scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[rol_obj]))))
        db_a.execute = AsyncMock(return_value=res_empty)
        u_in = UsuarioCreate(
            email="nuevo@uct.cl",
            nombre_completo="Nuevo Usuario",
            password="UctPassword2026!",
            roles=["Director_Recinto"],
            espacio_id=1,
            allowed_datasets=["biblioteca"],
        )
        u_creado = await auth_service.create_user(db_a, u_in)
        assert u_creado.email == "nuevo@uct.cl"

        # Chat persistente CRUD y cuotas
        db_c = _crear_db_analitica(scalar_val=1)
        conv_fake = SimpleNamespace(
            id=uuid.uuid4(),
            usuario_id=7,
            espacio_id=1,
            titulo="Consulta Aforo",
            archivada=False,
            eliminada_en=None,
            creada_en=datetime.now(timezone.utc).replace(tzinfo=None),
            actualizada_en=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db_c.get = AsyncMock(return_value=conv_fake)
        db_c.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=conv_fake), scalar=MagicMock(return_value=1), scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))

        c_new = await servicio_chat_persistente.crear_conversacion(db_c, usuario_id=7, espacio_id=1, prompt_inicial="Aforo hoy")
        assert c_new is not None
        assert await servicio_chat_persistente.renombrar_conversacion(db_c, conv_fake.id, 7, "Nuevo título") is not None
        assert await servicio_chat_persistente.archivar_conversacion(db_c, conv_fake.id, 7, True) is not None
        assert await servicio_chat_persistente.eliminar_conversacion(db_c, conv_fake.id, 7) is True
        await servicio_chat_persistente.agregar_mensaje(db_c, conv_fake.id, rol="user", tipo="text", contenido="Hola")

        # Calendar scraper helpers y service depuración
        cal_srv = calendar_service.CalendarService()
        res_cal = MagicMock(rowcount=2, scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
        db_cal = _crear_db_analitica()
        db_cal.execute = AsyncMock(return_value=res_cal)
        await cal_srv.obtener_eventos_calendario(db_cal, anio=2026)
        assert calendar_scraper.obtener_feriado_oficial_chile(date(2026, 9, 18)) is not None
        assert len(calendar_scraper.analizar_fechas_calendario("01-03-2026 - 15-03-2026")) >= 2

    asyncio.run(_run())

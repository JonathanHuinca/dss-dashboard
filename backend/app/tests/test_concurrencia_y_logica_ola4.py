"""Pruebas de concurrencia, caché, tiempos/DST, lógica de negocio y ML (Ola 4)."""
import asyncio
import dataclasses
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.api.v1.endpoints.chat import _iso_utc_z
from app.core import cache as cache_mod
from app.core.cache import CacheEnMemoria, cachear_respuesta
from app.core.tiempo import ZONA_CHILE, inicio_dia_chile_en_utc_naive
from app.domain.auth_models import Rol, TokenActivacion, Usuario
from app.domain.config_models import HorarioOperacion
from app.ml import gestor_modelos, isolation_forest
from app.schemas.auth_schemas import UsuarioCreate
from app.schemas.config_schemas import ContingenciaCrear
from app.services import auth_service, prediction_service, servicio_chat_persistente
from app.services.chat.fechas_chat import extraer_o_normalizar_fechas
from app.services.config_service import evaluar_horario_abierto_subespacio
from app.services.ingestion_service import (
    _clasificar_sentido_tokens,
    _procesar_lote_asistencia_sync,
    _tiene_token_puerta_io,
)
from app.services.servicio_reportes_compartidos import ServicioReportesCompartidos


class _ScalarResult:
    def __init__(self, obj: Any = None, rowcount: int = 1):
        self._obj = obj
        self.rowcount = rowcount

    def scalar_one_or_none(self):
        return self._obj

    def scalar(self):
        return self._obj


def test_create_user_y_dto_inmutable_sesion():
    async def _run():
        auth_service.limpiar_cache_usuario()
        creator = Usuario(
            id=1,
            email="admin@uct.cl",
            nombre_completo="Admin",
            hashed_password="x",
            is_active=True,
            allowed_datasets=["biblioteca", "estacionamiento"],
            can_use_ai=True,
            can_export=True,
            can_ingest=True,
            espacio_id=1,
        )
        creator.roles = [Rol(id=1, nombre="Admin_Sistema")]

        rol_guardia = Rol(id=3, nombre="Guardia_Seguridad", rate_limit_quota="0/day", cooldown_segundos=10)
        usuario_creado = Usuario(
            id=42,
            email="guardia.ola4@uct.cl",
            nombre_completo="Guardia Test",
            hashed_password="hash",
            is_active=True,
            allowed_datasets=["biblioteca"],
            can_use_ai=False,
            can_export=False,
            can_ingest=False,
            espacio_id=1,
        )
        usuario_creado.roles = [rol_guardia]

        db = AsyncMock()
        agregados = []

        def _add(obj):
            agregados.append(obj)
            if isinstance(obj, Usuario) and getattr(obj, "id", None) is None:
                obj.id = 42

        db.add = MagicMock(side_effect=_add)
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _ScalarResult(rol_guardia),
                _ScalarResult(usuario_creado),
            ]
        )

        payload = UsuarioCreate(
            email="guardia.ola4@uct.cl",
            nombre_completo="Guardia Test",
            password="PasswordSegura123!",
            roles=["Guardia_Seguridad"],
            allowed_datasets=["biblioteca"],
        )

        res = await auth_service.create_user(db=db, user_in=payload, creator=creator)
        assert isinstance(res, auth_service.UsuarioSesionDTO)
        assert dataclasses.is_dataclass(res)
        assert res.id == 42
        assert res.email == "guardia.ola4@uct.cl"
        with pytest.raises(dataclasses.FrozenInstanceError):
            res.is_active = False  # type: ignore[misc]

        # Segunda llamada usa caché sin golpear BD y luego limpia caché correctamente
        db.execute.reset_mock()
        res_cache = await auth_service.get_user_by_id(db, 42)
        assert res_cache == res
        assert db.execute.call_count == 0

        auth_service.limpiar_cache_usuario(42)
        db.execute = AsyncMock(return_value=_ScalarResult(usuario_creado))
        res_post = await auth_service.get_user_by_id(db, 42)
        assert res_post == res
        assert db.execute.call_count == 1
        auth_service.limpiar_cache_usuario()

    asyncio.run(_run())


def test_activar_cuenta_canje_atomico_y_carrera():
    async def _run():
        auth_service.limpiar_cache_usuario()
        usuario = Usuario(
            id=88,
            email="nuevo@uct.cl",
            nombre_completo="Nuevo",
            hashed_password="PENDIENTE_ACTIVACION",
            is_active=False,
        )
        token_obj = TokenActivacion(id=10, usuario_id=88, token_hash="h", tipo_token="ACTIVACION", utilizado=False)

        # Caso 1: otra petición ya reclamó el token -> rowcount == 0 -> HTTP 400 + rollback
        db_carrera = AsyncMock()
        db_carrera.execute = AsyncMock(return_value=_ScalarResult(None, rowcount=0))
        db_carrera.rollback = AsyncMock()
        db_carrera.commit = AsyncMock()

        with patch.object(auth_service, "verificar_token_activacion", AsyncMock(return_value=(token_obj, usuario))):
            with pytest.raises(HTTPException) as exc_info:
                await auth_service.activar_cuenta_usuario(
                    db_carrera,
                    token="tok_test",
                    nueva_password="ClaveFuerte2026!",
                    confirmar_password="ClaveFuerte2026!",
                )
            assert exc_info.value.status_code == 400
            db_carrera.rollback.assert_awaited_once()

        # Caso 2: rowcount == 1 -> activa e invalida caché de usuario
        db_ok = AsyncMock()
        db_ok.execute = AsyncMock(return_value=_ScalarResult(None, rowcount=1))
        db_ok.commit = AsyncMock()
        db_ok.refresh = AsyncMock()

        with patch.object(auth_service, "verificar_token_activacion", AsyncMock(return_value=(token_obj, usuario))):
            with patch.object(auth_service, "limpiar_cache_usuario") as mock_clean:
                act = await auth_service.activar_cuenta_usuario(
                    db_ok,
                    token="tok_test",
                    nueva_password="ClaveFuerte2026!",
                    confirmar_password="ClaveFuerte2026!",
                )
                assert act.is_active is True
                mock_clean.assert_called_once_with(88)

    asyncio.run(_run())


def test_cuota_ia_fail_closed_y_reserva_sse():
    async def _run():
        usr = SimpleNamespace(
            id=55,
            roles=[SimpleNamespace(nombre="Analista_Consulta", rate_limit_quota="20/day", cooldown_segundos=5)],
        )

        # Error SQL durante lectura de cuota -> debe fallar cerrado (HTTP 503), no permitir acceso ilimitado
        db_fail = AsyncMock()
        db_fail.execute = AsyncMock(side_effect=RuntimeError("SQL timeout"))
        with pytest.raises(HTTPException) as exc_503:
            await servicio_chat_persistente.obtener_cuota_ia_usuario(db_fail, usr)
        assert exc_503.value.status_code == 503

        # Reserva + finalización actualiza el ChatAuditLog reservado (ej. 'error' o 'cancelado')
        executed_stmts = []

        class _FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def execute(self, stmt):
                executed_stmts.append(stmt)
                return _ScalarResult(None)

            async def commit(self):
                return None

        db_res = AsyncMock()
        db_res.add = MagicMock(side_effect=lambda obj: setattr(obj, "id", 777))
        db_res.commit = AsyncMock()
        db_res.refresh = AsyncMock()

        with patch.object(
            servicio_chat_persistente,
            "validar_cuota_ia_usuario",
            AsyncMock(return_value=None),
        ):
            audit_id = await servicio_chat_persistente.reservar_cuota_ia_usuario(
                db_res,
                usr,
                prompt_text="Consulta de prueba",
                dataset_tipo="biblioteca",
            )
            assert audit_id == 777

        with patch.object(servicio_chat_persistente, "AsyncSessionLocal", return_value=_FakeSession()):
            await servicio_chat_persistente.finalizar_reserva_cuota_ia(
                audit_id,
                status_final="error",
                response_time_ms=123.4,
                respuesta_text="Fallo simulado",
            )
            assert len(executed_stmts) == 1

    asyncio.run(_run())


def test_config_service_fecha_fin_medianoche_y_fallback_vehicular():
    regla_rango = HorarioOperacion(
        espacio_id=1,
        subespacio="sala_2",
        tipo_horario="extendido_24h",
        fecha_inicio=datetime(2026, 6, 1, 0, 0),
        fecha_fin=datetime(2026, 6, 10, 0, 0),
        hora_apertura="21:00",
        hora_cierre="07:00",
        cierre_dia_siguiente=False,  # cruce implícito cierre < apertura
        es_continuo_24h=False,
        activo=True,
    )
    # Vigente hasta el último minuto del día fecha_fin (10 de junio 23:30)
    assert evaluar_horario_abierto_subespacio(datetime(2026, 6, 10, 23, 30), 1, "sala_2", [regla_rango]) == 1
    # Madrugada del 11 de junio correspondiente al turno iniciado el día 10 (fecha_fin)
    assert evaluar_horario_abierto_subespacio(datetime(2026, 6, 11, 5, 30), 1, "sala_2", [regla_rango]) == 1
    # Tarde del 11 de junio fuera de vigencia
    assert evaluar_horario_abierto_subespacio(datetime(2026, 6, 11, 22, 0), 1, "sala_2", [regla_rango]) == 0

    # Fallback recinto vehicular (espacio_id == 2) sin reglas configuradas
    assert evaluar_horario_abierto_subespacio(datetime(2026, 5, 11, 10, 0), 2, "CSF11", []) == 1  # Lunes 10:00
    assert evaluar_horario_abierto_subespacio(datetime(2026, 5, 16, 13, 0), 2, "CSF11", []) == 1  # Sábado 13:00
    assert evaluar_horario_abierto_subespacio(datetime(2026, 5, 16, 18, 0), 2, "CSF11", []) == 0  # Sábado 18:00
    assert evaluar_horario_abierto_subespacio(datetime(2026, 5, 17, 10, 0), 2, "CSF11", []) == 0  # Domingo


def test_tiempo_dst_fechas_chat_y_calendario():
    # Verano Chile (-03:00) e invierno (-04:00) convertidos a UTC naive de inicio del día local
    ref_verano = datetime(2026, 1, 15, 23, 30, tzinfo=ZONA_CHILE)
    assert inicio_dia_chile_en_utc_naive(ref_verano) == datetime(2026, 1, 15, 3, 0)

    ref_invierno = datetime(2026, 6, 15, 22, 15, tzinfo=ZONA_CHILE)
    assert inicio_dia_chile_en_utc_naive(ref_invierno) == datetime(2026, 6, 15, 4, 0)

    # _iso_utc_z emite siempre marca UTC explícita con 'Z'
    assert _iso_utc_z(datetime(2026, 5, 1, 12, 0, 0)) == "2026-05-01T12:00:00Z"
    assert _iso_utc_z(datetime(2026, 5, 1, 12, 0, 0, tzinfo=ZONA_CHILE)).endswith("Z")

    # Multi-año sin mutar año y febrero bisiesto
    d_ini, d_fin = extraer_o_normalizar_fechas("2025-12-15", "2026-01-10", "compara el periodo")
    assert (d_ini, d_fin) == (date(2025, 12, 15), date(2026, 1, 10))

    d_feb_i, d_feb_f = extraer_o_normalizar_fechas(None, None, "afluencia de febrero 2024")
    assert (d_feb_i, d_feb_f) == (date(2024, 2, 1), date(2024, 2, 29))

    # Sin fallback silencioso a octubre cuando el mes es inválido
    d_bad_i, d_bad_f = extraer_o_normalizar_fechas(None, None, "del 10 al 15 de mesx 2026")
    assert d_bad_i is None and d_bad_f is None

    # Validación fecha_inicio <= fecha_fin en ContingenciaCrear
    with pytest.raises(ValidationError):
        ContingenciaCrear(
            fecha_inicio=date(2026, 5, 20),
            fecha_fin=date(2026, 5, 10),
            tipo="climatica",
            titulo="Rango inválido",
        )

    # Normalización de expira_en hacia Chile naive y comparación de expiración
    dt_cl = ServicioReportesCompartidos._normalizar_expira_en("2026-01-15T15:00:00Z")
    assert dt_cl == datetime(2026, 1, 15, 12, 0, 0)
    assert ServicioReportesCompartidos._es_expirado(datetime(2020, 1, 1, 0, 0)) is True
    assert ServicioReportesCompartidos._es_expirado(datetime(2099, 1, 1, 0, 0)) is False


def test_cache_single_flight_refcount_e_invalidate_prefix():
    async def _run():
        c = CacheEnMemoria(maxsize=100, default_ttl=60)
        await c.set("espacio:1:kpis", {"ok": 1}, ttl=60, tags=["espacio:1"])
        await c.set("espacio:10:kpis", {"ok": 10}, ttl=60, tags=["espacio:10"])

        # invalidate_prefix("espacio:1:") NO debe borrar "espacio:10:kpis" ni tag "espacio:10"
        borradas = await c.invalidate_prefix("espacio:1:")
        assert borradas == 1
        assert await c.get("espacio:1:kpis") is None
        assert await c.get("espacio:10:kpis") == {"ok": 10}

        # Single-flight refcount libera el diccionario _bloqueos_computo tras terminar concurrentes
        llamadas = 0
        await cache_mod.limpiar_toda_la_cache()
        cache_mod._bloqueos_computo.clear()

        @cachear_respuesta(categoria="kpis_dia", ttl_segundos=60)
        async def _fn_lenta(espacio_id: int = 1):
            nonlocal llamadas
            llamadas += 1
            await asyncio.sleep(0.02)
            return {"valor": espacio_id * 10}

        r1, r2, r3 = await asyncio.gather(_fn_lenta(espacio_id=99), _fn_lenta(espacio_id=99), _fn_lenta(espacio_id=99))
        assert r1 == r2 == r3 == {"valor": 990}
        assert llamadas == 1
        assert len(cache_mod._bloqueos_computo) == 0

    asyncio.run(_run())


def test_ingestion_tokens_sentido_y_preservacion_pe_us():
    # 'Main' no debe detectarse como token 'in'
    assert _tiene_token_puerta_io("Main") is False
    assert _tiene_token_puerta_io("Puerta Principal") is False
    assert _tiene_token_puerta_io("Turnstile-In") is True
    assert _tiene_token_puerta_io("Puerta_01_OUT") is True
    assert _clasificar_sentido_tokens("", "IN01") == "entrada"
    assert _clasificar_sentido_tokens("", "OUT2") == "salida"
    assert _clasificar_sentido_tokens("egreso", "Main") == "salida"

    # Cuando existen Primera Entrada y Ultima Salida, deben preservarse ambas
    df = pd.DataFrame([
        {
            "Fecha": "2026-05-10",
            "Primera Entrada": "09:00:00",
            "Ultima Salida": "11:30:00",
            "Puerta": "Main",
            "Matricula": "20260001",
            "Estamento": "Estudiante",
        }
    ])
    dtos = _procesar_lote_asistencia_sync(df, espacio_id=1, clave_enlace="matricula", modo_enlace="tolerante", maestro_estudiantes={})
    assert len(dtos) == 1
    assert dtos[0].primera_entrada == datetime(2026, 5, 10, 9, 0, 0)
    assert dtos[0].ultima_salida == datetime(2026, 5, 10, 11, 30, 0)
    assert dtos[0].permanencia_min == 150.0


def test_ml_isolation_forest_gbr_unavailable_y_lru(tmp_path: Path):
    # Isolation Forest: no muta DF original y soporta DF pequeño/vacío
    df_vacio = pd.DataFrame(columns=["hora_ingreso", "permanencia", "frecuencia"])
    res_vacio = isolation_forest.detect_vehicular_anomalies(df_vacio)
    assert res_vacio.empty
    assert "is_anomaly" not in df_vacio.columns

    df_small = pd.DataFrame([{"hora_ingreso": 8, "permanencia": 60, "frecuencia": 2}])
    res_small = isolation_forest.detect_vehicular_anomalies(df_small)
    assert res_small.empty
    assert "is_anomaly" not in df_small.columns

    # gestor_modelos: recarga cuando cambia el archivo e invalidación segura
    gestor_modelos._cache_modelos_memoria.clear()
    assert gestor_modelos.cargar_modelo_en_memoria(tmp_path / "ausente.joblib") is None

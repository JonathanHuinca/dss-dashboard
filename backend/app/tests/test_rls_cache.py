"""
test_rls_cache.py — Suite de pruebas automatizadas de Calidad y Ciberseguridad (AppSec).

Verifica el aislamiento Row-Level Security (RLS) y la inmunidad de la caché en DSS UCT:
1. Validar que un usuario 'Director_Recinto' del espacio 2 reciba HTTP 403 Forbidden al consultar
   endpoints del espacio 1, incluso cuando la entrada de caché ya haya sido previamente poblada por otro usuario.
2. Validar que las claves de caché sean matemáticamente distintas según el perfil de seguridad y roles asignados.
3. Validar determinismo, resistencia a colisiones y aislamiento criptográfico SHA-256 de TTLCache.
"""
import asyncio
import os
import sys
from typing import Any, List, Optional
import pytest
from fastapi import HTTPException, Response, status
from fastapi.testclient import TestClient

# Asegurar resolución del paquete app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.core.cache import (
    cachear_respuesta,
    _generar_clave_cache,
    _contexto_seguridad_usuario,
    obtener_cache,
    invalidar_cache_por_espacio,
    limpiar_toda_la_cache,
)
from app.core.security import validar_acceso_espacio, get_current_user
from app.domain.auth_models import Usuario, Rol
from app.main import app


def _crear_usuario_prueba(
    email: str,
    roles_nombres: List[str],
    espacio_id: Optional[int] = None,
    allowed_datasets: Optional[List[str]] = None,
) -> Usuario:
    """Instancia un modelo Usuario desacoplado de la base de datos para pruebas AppSec."""
    u = Usuario(
        id=hash(email) % 10000 + 1,
        email=email,
        nombre_completo=f"Test {email}",
        hashed_password="hash_simulado_bcrypt",
        is_active=True,
        espacio_id=espacio_id,
        allowed_datasets=allowed_datasets or ["biblioteca", "estacionamiento"],
    )
    u.roles = [Rol(id=i + 1, nombre=nom) for i, nom in enumerate(roles_nombres)]
    return u


# ==============================================================================
# 1. PRUEBAS DE AISLAMIENTO RLS Y PREVENCIÓN DE FUGAS EN CACHÉ (Requisito 1)
# ==============================================================================

def test_aislamiento_rls_cache_precalentada_retorna_403():
    """
    Escenario crítico AppSec:
    1. Usuario Admin_Sistema consulta y puebla la caché para espacio_id = 1.
    2. Usuario Director_Recinto (asignado a espacio_id = 2) intenta consultar espacio_id = 1.
    3. Debe lanzarse HTTP 403 Forbidden antes de acceder a la caché, sin filtración de datos.
    """
    async def _ejecutar():
        await limpiar_toda_la_cache()

        admin = _crear_usuario_prueba("admin@uct.cl", ["Admin_Sistema"], espacio_id=None)
        director_estacionamiento = _crear_usuario_prueba(
            "director.est@uct.cl",
            ["Director_Recinto"],
            espacio_id=2,
            allowed_datasets=["estacionamiento"],
        )

        conteo_ejecuciones_reales = 0

        @cachear_respuesta(ttl_segundos=300, categoria="kpis", por_espacio=True)
        async def endpoint_analitico_simulado(espacio_id: int, current_user: Any, response: Optional[Response] = None):
            nonlocal conteo_ejecuciones_reales
            conteo_ejecuciones_reales += 1
            return {
                "espacio_id": espacio_id,
                "afluencia_total": 4500,
                "secreto_institucional": "datos_restringidos_recinto_1",
            }

        # 1. Admin consulta espacio_id = 1 (Cold start / MISS)
        resp_admin_1 = Response()
        resultado_admin_1 = await endpoint_analitico_simulado(espacio_id=1, current_user=admin, response=resp_admin_1)
        assert resultado_admin_1["afluencia_total"] == 4500
        assert resp_admin_1.headers.get("X-Cache") == "MISS"
        assert conteo_ejecuciones_reales == 1

        # 2. Admin repite la consulta (HIT en caché)
        resp_admin_2 = Response()
        resultado_admin_2 = await endpoint_analitico_simulado(espacio_id=1, current_user=admin, response=resp_admin_2)
        assert resultado_admin_2["afluencia_total"] == 4500
        assert resp_admin_2.headers.get("X-Cache") == "HIT"
        assert conteo_ejecuciones_reales == 1

        # 3. Director de Recinto 2 intenta acceder a datos de Recinto 1 (ya calientes en caché)
        resp_dir = Response()
        with pytest.raises(HTTPException) as exc_info:
            await endpoint_analitico_simulado(espacio_id=1, current_user=director_estacionamiento, response=resp_dir)

        # Validaciones de ciberseguridad
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Acceso denegado: usuario asignado al recinto 2, no al recinto 1" in exc_info.value.detail
        # El conteo de ejecución no varió y nunca se entregó la información en caché
        assert conteo_ejecuciones_reales == 1

    asyncio.run(_ejecutar())


def test_aislamiento_rls_guardia_seguridad_recinto_cruzado():
    """Valida que Guardia_Seguridad del Recinto 1 no pueda acceder al Recinto 2."""
    guardia_bib = _crear_usuario_prueba(
        "guardia.bib@uct.cl",
        ["Guardia_Seguridad"],
        espacio_id=1,
        allowed_datasets=["biblioteca"],
    )

    with pytest.raises(HTTPException) as exc_info:
        validar_acceso_espacio(2, guardia_bib)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "Acceso denegado: usuario asignado al recinto 1, no al recinto 2" in exc_info.value.detail


def test_aislamiento_rls_dataset_no_autorizado():
    """Valida que un usuario sin el dataset en allowed_datasets reciba 403 Forbidden."""
    usuario_sin_bib = _crear_usuario_prueba(
        "investigador@uct.cl",
        ["Analista_Calidad"],
        espacio_id=None,
        allowed_datasets=["estacionamiento"],
    )

    with pytest.raises(HTTPException) as exc_info:
        validar_acceso_espacio(1, usuario_sin_bib)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "no cuenta con autorización para acceder al módulo 'biblioteca'" in exc_info.value.detail


# ==============================================================================
# 2. PRUEBAS DE DIVERSIFICACIÓN CRIPTOGRÁFICA DE CLAVES DE CACHÉ (Requisito 2)
# ==============================================================================

def test_claves_cache_matematicamente_distintas_por_perfil_seguridad():
    """
    Verifica que para la misma función y los mismos parámetros de entrada,
    los distintos perfiles de seguridad generen hashes SHA-256 matemáticamente distintos.
    """
    admin = _crear_usuario_prueba("admin@uct.cl", ["Admin_Sistema"], espacio_id=None, allowed_datasets=["biblioteca", "estacionamiento"])
    dir_bib = _crear_usuario_prueba("dir.bib@uct.cl", ["Director_Recinto"], espacio_id=1, allowed_datasets=["biblioteca"])
    dir_est = _crear_usuario_prueba("dir.est@uct.cl", ["Director_Recinto"], espacio_id=2, allowed_datasets=["estacionamiento"])
    guardia = _crear_usuario_prueba("guardia@uct.cl", ["Guardia_Seguridad"], espacio_id=1, allowed_datasets=["biblioteca"])
    general = _crear_usuario_prueba("estudiante@uct.cl", ["Usuario_General"], espacio_id=None, allowed_datasets=[])

    params = {"espacio_id": 1, "fecha_inicio": "2026-03-01", "fecha_fin": "2026-03-31"}

    clave_admin, _ = _generar_clave_cache("kpis", (), params, "kpis", 1, _contexto_seguridad_usuario(admin))
    clave_dir_bib, _ = _generar_clave_cache("kpis", (), params, "kpis", 1, _contexto_seguridad_usuario(dir_bib))
    clave_dir_est, _ = _generar_clave_cache("kpis", (), params, "kpis", 1, _contexto_seguridad_usuario(dir_est))
    clave_guardia, _ = _generar_clave_cache("kpis", (), params, "kpis", 1, _contexto_seguridad_usuario(guardia))
    clave_general, _ = _generar_clave_cache("kpis", (), params, "kpis", 1, _contexto_seguridad_usuario(general))

    claves = [clave_admin, clave_dir_bib, clave_dir_est, clave_guardia, clave_general]

    # Comprobar unicidad estricta (sin colisiones)
    assert len(set(claves)) == len(claves), "Colisión detectada: dos perfiles de seguridad distintos comparten clave de caché"

    # Comprobar estructura canónica del hash
    for c in claves:
        partes = c.split(":")
        assert len(partes) == 4
        assert partes[0] == "dss"
        assert partes[1] == "kpis"
        assert partes[2] == "kpis"
        assert len(partes[3]) == 64  # Longitud exacta de SHA-256 en hexadecimal


def test_determinismo_criptografico_claves_cache():
    """Valida que la clave de caché sea 100% determinista y reproducible para un mismo contexto."""
    usuario = _crear_usuario_prueba("dir.bib@uct.cl", ["Director_Recinto"], espacio_id=1, allowed_datasets=["biblioteca"])
    ctx = _contexto_seguridad_usuario(usuario)
    params = {"espacio_id": 1, "fecha_inicio": "2026-03-15", "filtro": "conformes"}

    claves_generadas = {
        _generar_clave_cache("heatmap", (), params, "kpis", 1, ctx)[0]
        for _ in range(50)
    }

    assert len(claves_generadas) == 1, "Inconsistencia de determinismo: la misma entrada generó hashes diferentes"


def test_variacion_espacio_id_altera_clave_cache():
    """Valida que consultas con distinto espacio_id generen claves distintas aun con el mismo usuario."""
    admin = _crear_usuario_prueba("admin@uct.cl", ["Admin_Sistema"], espacio_id=None)
    ctx = _contexto_seguridad_usuario(admin)

    clave_e1, tags_e1 = _generar_clave_cache("resumen", (), {"espacio_id": 1}, "kpis", 1, ctx)
    clave_e2, tags_e2 = _generar_clave_cache("resumen", (), {"espacio_id": 2}, "kpis", 2, ctx)

    assert clave_e1 != clave_e2
    assert "espacio:1" in tags_e1
    assert "espacio:2" in tags_e2


def test_invalidacion_selectiva_por_espacio():
    """Valida que purgar el espacio 1 no elimine las entradas pertenecientes al espacio 2."""
    async def _ejecutar():
        cache = obtener_cache()
        await cache.clear()

        await cache.set("dss:kpis:e1:hash1", {"data": "e1"}, ttl=300, tags=["espacio:1"])
        await cache.set("dss:kpis:e1:hash2", {"data": "e1_bis"}, ttl=300, tags=["espacio:1"])
        await cache.set("dss:kpis:e2:hash3", {"data": "e2"}, ttl=300, tags=["espacio:2"])

        invalidados = await invalidar_cache_por_espacio(1)
        assert invalidados >= 2

        # Espacio 1 debe ser None
        assert cache.get_nowait("dss:kpis:e1:hash1") is None
        assert cache.get_nowait("dss:kpis:e1:hash2") is None

        # Espacio 2 debe seguir existiendo intacto
        assert cache.get_nowait("dss:kpis:e2:hash3") == {"data": "e2"}

    asyncio.run(_ejecutar())


# ==============================================================================
# 3. PRUEBAS DE INTEGRACIÓN EN ENDPOINTS FASTAPI (Requisito 1 & 2)
# ==============================================================================

def test_endpoint_fastapi_director_recinto_espacio_cruzado_retorna_403():
    """
    Petición HTTP real a través de TestClient con dependency_overrides:
    Un Director_Recinto de Espacio 2 solicita /api/v1/attendance/kpis?espacio_id=1.
    Debe responder con código HTTP 403 Forbidden.
    """
    director_recinto_2 = _crear_usuario_prueba(
        "director.estacionamiento@uct.cl",
        ["Director_Recinto"],
        espacio_id=2,
        allowed_datasets=["estacionamiento"],
    )

    app.dependency_overrides[get_current_user] = lambda: director_recinto_2

    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/attendance/kpis",
                params={"espacio_id": 1, "fecha_inicio": "2026-03-01", "fecha_fin": "2026-03-31"},
            )
            assert response.status_code == status.HTTP_403_FORBIDDEN
            body = response.json()
            assert "Acceso denegado" in body.get("detail", "")
            assert "recinto 2, no al recinto 1" in body.get("detail", "")
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_endpoint_fastapi_admin_acceso_global_permitido():
    """Un Admin_Sistema puede consultar legítimamente tanto espacio_id=1 como espacio_id=2."""
    admin_global = _crear_usuario_prueba(
        "admin.global@uct.cl",
        ["Admin_Sistema"],
        espacio_id=None,
        allowed_datasets=["biblioteca", "estacionamiento"],
    )

    app.dependency_overrides[get_current_user] = lambda: admin_global

    try:
        with TestClient(app) as client:
            # Espacio 1
            resp_1 = client.get(
                "/api/v1/attendance/kpis",
                params={"espacio_id": 1, "fecha_inicio": "2026-03-01", "fecha_fin": "2026-03-31"},
            )
            assert resp_1.status_code == status.HTTP_200_OK

            # Espacio 2
            resp_2 = client.get(
                "/api/v1/vehicles/kpis",
                params={"espacio_id": 2, "fecha_inicio": "2026-03-01", "fecha_fin": "2026-03-31"},
            )
            assert resp_2.status_code == status.HTTP_200_OK
    finally:
        app.dependency_overrides.pop(get_current_user, None)


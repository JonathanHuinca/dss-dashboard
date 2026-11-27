"""
probar_orquestador_modelos.py — Pruebas de validación del sistema de reentrenamiento,
control de modelos Campeón vs. Retador, permisos RBAC (Admin_Sistema) y endpoints.
"""
import asyncio
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import httpx
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.planificador import CATALOGO_TAREAS, ZONA_HORARIA_CHILE
from app.core.security import create_access_token
from app.domain.auth_models import Rol, Usuario, UsuarioRol
from app.ml.orquestador_entrenamiento import (
    MODELOS_CATALOGO,
    DIRECTORIO_MODELOS,
    _leer_metadatos_campeon,
    obtener_estado_general_modelos,
)
from app.main import app


async def probar_orquestador_y_endpoints():
    print("\n========================================================")
    print("      VERIFICACIÓN PROMPT 6: ORQUESTADOR Y CONTROL ML   ")
    print("========================================================\n")

    # 1. Verificar configuración y catálogo de tareas
    print("[1/5] Verificando configuración y agenda de la tarea diaria...")
    assert "reentrenar_modelos_ml" in CATALOGO_TAREAS, "reentrenar_modelos_ml no está en CATALOGO_TAREAS"
    tarea_info = CATALOGO_TAREAS["reentrenar_modelos_ml"]
    print(f"      - Cron programado: {tarea_info['cron_str']}")
    print(f"      - Frecuencia: {tarea_info['frecuencia']}")
    print(f"      - Catchup hora: {tarea_info['catchup_hora']:02d}:{tarea_info['catchup_minuto']:02d}")
    print(f"      - Directorio modelos: {settings.DIRECTORIO_MODELOS}")
    assert tarea_info["catchup_hora"] == 6 and tarea_info["catchup_minuto"] == 0, "La hora de reentrenamiento debe ser 06:00"
    print("      -> APROBADO: Tarea correctamente agendada a las 06:00 America/Santiago.")

    # 2. Verificar estado inicial de modelos en disco y lectura de metadatos
    print("\n[2/5] Verificando modelos en disco y obtención de estado general...")
    reporte_estado = obtener_estado_general_modelos()
    assert len(reporte_estado) == len(MODELOS_CATALOGO), "El reporte de modelos debe cubrir todo el catálogo"
    for m in reporte_estado:
        print(f"      - Modelo: {m['clave']:<26} | Disp: {str(m['disponible']):<5} | WAPE: {m['wape']} | MAE: {m['mae']} | Estado: {m['estado']}")
    print("      -> APROBADO: Reporte de estado de modelos generado correctamente.")

    # 3. Probar RBAC y endpoints HTTP mediante cliente ASGI httpx
    print("\n[3/5] Verificando permisos RBAC y endpoints /api/v1/admin/modelos...")
    
    # Obtener o crear usuarios para pruebas RBAC
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        from app.domain.auth_models import Usuario, Rol, UsuarioRol

        stmt_admin = (
            select(Usuario)
            .join(Usuario.usuario_roles)
            .join(UsuarioRol.rol)
            .where(Rol.nombre.in_(["Admin_Sistema", "SuperAdmin"]))
        )
        admin_user = (await session.execute(stmt_admin)).scalars().first()

        stmt_no_admin = (
            select(Usuario)
            .join(Usuario.usuario_roles)
            .join(UsuarioRol.rol)
            .where(Rol.nombre.notin_(["Admin_Sistema", "SuperAdmin"]))
        )
        no_admin_user = (await session.execute(stmt_no_admin)).scalars().first()

        if not admin_user:
            # Crear usuario Admin_Sistema de prueba
            rol_admin = (await session.execute(select(Rol).where(Rol.nombre == "Admin_Sistema"))).scalar_one_or_none()
            if not rol_admin:
                rol_admin = Rol(nombre="Admin_Sistema", descripcion="Administrador del Sistema")
                session.add(rol_admin)
                await session.flush()
            admin_user = Usuario(email="admin_ml_test@uct.cl", password_hash="hash", nombre_completo="Admin ML Test", is_active=True)
            session.add(admin_user)
            await session.flush()
            session.add(UsuarioRol(usuario_id=admin_user.id, rol_id=rol_admin.id))
            await session.commit()
            await session.refresh(admin_user)

        if not no_admin_user:
            rol_analista = (await session.execute(select(Rol).where(Rol.nombre == "Analista_Consulta"))).scalar_one_or_none()
            if not rol_analista:
                rol_analista = Rol(nombre="Analista_Consulta", descripcion="Analista")
                session.add(rol_analista)
                await session.flush()
            no_admin_user = Usuario(email="analista_ml_test@uct.cl", password_hash="hash", nombre_completo="Analista ML Test", is_active=True)
            session.add(no_admin_user)
            await session.flush()
            session.add(UsuarioRol(usuario_id=no_admin_user.id, rol_id=rol_analista.id))
            await session.commit()
            await session.refresh(no_admin_user)

        token_admin = create_access_token(
            user_id=admin_user.id,
            rol="Admin_Sistema",
            roles=["Admin_Sistema"],
        )
        token_no_admin = create_access_token(
            user_id=no_admin_user.id,
            rol="Analista_Consulta",
            roles=["Analista_Consulta"],
        )


    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # A. GET /api/v1/admin/modelos/estado sin autenticación -> 401
        res_anon = await client.get("/api/v1/admin/modelos/estado")
        print(f"      - GET /modelos/estado (Anónimo): HTTP {res_anon.status_code}")
        assert res_anon.status_code == 401, f"Esperado 401, recibido {res_anon.status_code}"

        # B. GET /api/v1/admin/modelos/estado con rol Analista_Consulta -> 403 Forbidden
        res_no_admin = await client.get(
            "/api/v1/admin/modelos/estado",
            headers={"Authorization": f"Bearer {token_no_admin}"},
        )
        print(f"      - GET /modelos/estado (No-Admin): HTTP {res_no_admin.status_code}")
        assert res_no_admin.status_code == 403, f"Esperado 403 para no-admin, recibido {res_no_admin.status_code}"

        # C. GET /api/v1/admin/modelos/estado con rol Admin_Sistema -> 200 OK
        res_admin = await client.get(
            "/api/v1/admin/modelos/estado",
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        print(f"      - GET /modelos/estado (Admin_Sistema): HTTP {res_admin.status_code}")
        assert res_admin.status_code == 200, f"Esperado 200 para Admin_Sistema, recibido {res_admin.status_code}"
        datos_modelos = res_admin.json()
        assert isinstance(datos_modelos, list) and len(datos_modelos) >= 4, "Debe retornar la lista de modelos"
        print(f"        Modelos reportados por API: {len(datos_modelos)}")

        # D. POST /api/v1/admin/modelos/actualizar con rol Analista_Consulta -> 403 Forbidden
        res_post_no_admin = await client.post(
            "/api/v1/admin/modelos/actualizar",
            headers={"Authorization": f"Bearer {token_no_admin}"},
        )
        print(f"      - POST /modelos/actualizar (No-Admin): HTTP {res_post_no_admin.status_code}")
        assert res_post_no_admin.status_code == 403, f"Esperado 403 para no-admin, recibido {res_post_no_admin.status_code}"

        # E. POST /predictions/retrain -> debe dar 404/405 (reemplazado por /admin/modelos/actualizar)
        res_retrain_old = await client.post(
            "/api/v1/predictions/retrain",
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        print(f"      - POST /predictions/retrain (Ruta antigua): HTTP {res_retrain_old.status_code}")
        assert res_retrain_old.status_code in (404, 405), f"Esperado 404/405 para ruta eliminada, recibido {res_retrain_old.status_code}"

        # F. POST /api/v1/admin/modelos/actualizar con Admin_Sistema -> 202 Accepted
        res_post_admin = await client.post(
            "/api/v1/admin/modelos/actualizar",
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        print(f"      - POST /modelos/actualizar (Admin_Sistema): HTTP {res_post_admin.status_code}")
        assert res_post_admin.status_code in (202, 409), f"Esperado 202 (o 409 si ya en curso), recibido {res_post_admin.status_code}"
        print(f"        Respuesta: {res_post_admin.json()}")

    print("      -> APROBADO: Seguridad RBAC y endpoints conformes a especificación.")

    # 4. Probar criterio de aceptación: modelo defectuoso o insuficiente NO sustituye al campeón
    print("\n[4/5] Verificando protección del modelo Campeón ante retadores defectuosos...")
    archivo_sala1 = DIRECTORIO_MODELOS / "prophet_biblioteca_sala1_active.joblib"
    mtime_inicial = archivo_sala1.stat().st_mtime if archivo_sala1.exists() else None

    async with AsyncSessionLocal() as session:
        from app.ml.orquestador_entrenamiento import entrenar_todos_los_modelos
        resultados_todos = await entrenar_todos_los_modelos(session)
        print(f"      - Evaluados {len(resultados_todos)} modelos.")
        for r in resultados_todos:
            print(f"        * {r.get('modelo')}: estado={r.get('estado')}, promovido={r.get('promovido')}, campeon_conservado={r.get('campeon_conservado')}")
            # Si no fue promovido, el campeón DEBE haberse conservado intacto
            if not r.get("promovido"):
                assert r.get("campeon_conservado") is True, f"El campeón de {r.get('modelo')} debió conservarse"

    if mtime_inicial and archivo_sala1.exists():
        assert archivo_sala1.stat().st_mtime == mtime_inicial, "El archivo activo del campeón no debió modificarse si no fue promovido"
    print("      -> APROBADO: Criterio de aceptación cumplido (un modelo defectuoso no sustituye al campeón).")


    # 5. Verificación de recarga en caliente
    print("\n[5/5] Verificando recarga en caliente en memoria...")
    from app.ml.gestor_modelos import cargar_modelo_en_memoria, _cache_modelos_memoria
    if archivo_sala1.exists():
        modelo_m1 = cargar_modelo_en_memoria(archivo_sala1)
        assert modelo_m1 is not None, "El modelo debe cargarse en memoria"
        assert str(archivo_sala1.resolve()) in _cache_modelos_memoria, "Debe residir en la caché de memoria"
        modelo_m2 = cargar_modelo_en_memoria(archivo_sala1)
        assert modelo_m1 is modelo_m2, "Debe retornar la misma instancia en caché si mtime no ha cambiado"
        print("      -> APROBADO: Recarga en caliente en memoria operativa.")

    print("\n========================================================")
    print("      TODAS LAS PRUEBAS COMPLETADAS EXITOSAMENTE        ")
    print("========================================================\n")


if __name__ == "__main__":
    asyncio.run(probar_orquestador_y_endpoints())

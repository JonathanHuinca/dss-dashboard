"""test_rbac_hierarchy.py — Suite de pruebas de validación de la jerarquía RBAC de 4 roles,
permisos modulares por banderas y administración delegada (RF22).
"""
import asyncio
from typing import List
from fastapi import HTTPException
from sqlalchemy import select, text

from app.core.database import AsyncSessionLocal
from app.domain.auth_models import Rol, Usuario, UsuarioRol
from app.schemas.auth_schemas import UsuarioCreate
from app.services.auth_service import (
    DEFAULT_ROLES,
    create_access_token,
    create_user,
    decode_access_token,
    get_user_by_email,
    list_users,
    normalizar_rol,
    update_user_status,
)
from app.core.security import (
    require_roles,
    require_permission,
    validar_acceso_espacio,
)


async def run_tests():
    print("=====================================================================")
    print("INICIANDO PRUEBAS DE JERARQUÍA RBAC, PERMISOS Y DELEGACIÓN (RF22)")
    print("=====================================================================")

    async with AsyncSessionLocal() as db:
        # -------------------------------------------------------------------
        # TEST 1: Verificación de los 4 Roles Formales en Base de Datos
        # -------------------------------------------------------------------
        print("\n--- TEST 1: Verificación de Roles Formales Normalizados ---")
        stmt_roles = select(Rol)
        res_roles = await db.execute(stmt_roles)
        roles_bd = {r.nombre: r for r in res_roles.scalars().all()}
        print(f"Roles encontrados en base de datos: {list(roles_bd.keys())}")

        roles_esperados = [
            "Admin_Sistema",
            "Director_Recinto",
            "Analista_Consulta",
            "Guardia_Seguridad",
        ]
        for rol_req in roles_esperados:
            assert rol_req in roles_bd, f"El rol institucional '{rol_req}' debe existir en BD"
            print(f"  Rol '{rol_req}' verificado. Cuota: {roles_bd[rol_req].rate_limit_quota}")

        # Probar normalización de alias legados
        assert normalizar_rol("SuperAdmin") == "Admin_Sistema"
        assert normalizar_rol("Directivo") == "Director_Recinto"
        assert normalizar_rol("admin_sistema") == "Admin_Sistema"
        assert normalizar_rol("analista") == "Analista_Consulta"
        assert normalizar_rol("guardia") == "Guardia_Seguridad"
        print("Normalización de alias legados superada con éxito.")
        print("TEST 1 SUPERADO.")

        # -------------------------------------------------------------------
        # Preparación de Cuentas de Prueba para los 4 Roles
        # -------------------------------------------------------------------
        print("\n--- Preparando Cuentas de Prueba ---")
        # Limpieza previa de cuentas de prueba
        await db.execute(
            text("DELETE FROM usuarios WHERE email LIKE 'test_rbac_%@uct.cl'")
        )
        await db.commit()

        # 1. Admin_Sistema
        user_admin = await create_user(
            db=db,
            user_in=UsuarioCreate(
                email="test_rbac_admin@uct.cl",
                nombre_completo="Administrador Central de Pruebas",
                password="password123",
                roles=["Admin_Sistema"],
                can_use_ai=True,
                can_export=True,
                can_ingest=True,
            ),
        )

        # 2. Director_Recinto (asignado a espacio_id = 1 Biblioteca)
        user_director = await create_user(
            db=db,
            user_in=UsuarioCreate(
                email="test_rbac_director@uct.cl",
                nombre_completo="Director Biblioteca CSF",
                password="password123",
                roles=["Director_Recinto"],
                espacio_id=1,
            ),
            creator=user_admin,
        )

        # 3. Analista_Consulta (creado por Director de Recinto)
        user_analista = await create_user(
            db=db,
            user_in=UsuarioCreate(
                email="test_rbac_analista@uct.cl",
                nombre_completo="Analista Curricular Biblioteca",
                password="password123",
                roles=["Analista_Consulta"],
            ),
            creator=user_director,
        )

        # 4. Guardia_Seguridad (creado por Director de Recinto)
        user_guardia = await create_user(
            db=db,
            user_in=UsuarioCreate(
                email="test_rbac_guardia@uct.cl",
                nombre_completo="Guardia Acceso Norte",
                password="password123",
                roles=["Guardia_Seguridad"],
            ),
            creator=user_director,
        )

        print(f"Admin Creado: id={user_admin.id}, roles={[r.nombre for r in user_admin.roles]}, flags=({user_admin.can_use_ai}, {user_admin.can_export}, {user_admin.can_ingest})")
        print(f"Director Creado: id={user_director.id}, espacio={user_director.espacio_id}, creator={user_director.created_by_user_id}")
        print(f"Analista Creado: id={user_analista.id}, espacio={user_analista.espacio_id}, creator={user_analista.created_by_user_id}")
        print(f"Guardia Creado: id={user_guardia.id}, espacio={user_guardia.espacio_id}, creator={user_guardia.created_by_user_id}")

        # -------------------------------------------------------------------
        # TEST 2: Banderas de Permisos Modulares por Rol
        # -------------------------------------------------------------------
        print("\n--- TEST 2: Validación de Banderas de Permisos Modulares ---")
        assert user_admin.can_use_ai is True
        assert user_admin.can_export is True
        assert user_admin.can_ingest is True

        assert user_director.can_use_ai is True
        assert user_director.can_export is True
        assert user_director.can_ingest is True

        assert user_analista.can_use_ai is True
        assert user_analista.can_export is True
        assert user_analista.can_ingest is False

        assert user_guardia.can_use_ai is False
        assert user_guardia.can_export is False
        assert user_guardia.can_ingest is False

        # Probar función guard require_permission
        perm_ingest_guard = require_permission("can_ingest")
        # Admin debe pasar
        await perm_ingest_guard(current_user=user_admin)
        # Director debe pasar
        await perm_ingest_guard(current_user=user_director)
        # Analista debe fallar con HTTP 403
        try:
            await perm_ingest_guard(current_user=user_analista)
            assert False, "Analista no debió tener permiso can_ingest"
        except HTTPException as he:
            assert he.status_code == 403
            print(f"Rechazo esperado can_ingest en Analista: {he.detail}")

        # Guardia debe fallar can_use_ai con HTTP 403
        perm_ai_guard = require_permission("can_use_ai")
        try:
            await perm_ai_guard(current_user=user_guardia)
            assert False, "Guardia no debió tener permiso can_use_ai"
        except HTTPException as he:
            assert he.status_code == 403
            print(f"Rechazo esperado can_use_ai en Guardia: {he.detail}")

        print("TEST 2 SUPERADO CON ÉXITO.")

        # -------------------------------------------------------------------
        # TEST 3: Administración Delegada (Director_Recinto vs Admin_Sistema)
        # -------------------------------------------------------------------
        print("\n--- TEST 3: Administración Delegada de Usuarios ---")
        # 1. Director intenta crear un Admin_Sistema (Debe rechazar con HTTP 403)
        try:
            await create_user(
                db=db,
                user_in=UsuarioCreate(
                    email="test_rbac_escalation@uct.cl",
                    nombre_completo="Intento de Escalación",
                    password="password123",
                    roles=["Admin_Sistema"],
                ),
                creator=user_director,
            )
            assert False, "Director no debe poder crear Admin_Sistema"
        except HTTPException as he:
            assert he.status_code == 403
            print(f"Rechazo esperado de escalación por Director: {he.detail}")

        # 2. Director intenta crear otro Director_Recinto (Debe rechazar con HTTP 403)
        try:
            await create_user(
                db=db,
                user_in=UsuarioCreate(
                    email="test_rbac_director2@uct.cl",
                    nombre_completo="Segundo Director",
                    password="password123",
                    roles=["Director_Recinto"],
                ),
                creator=user_director,
            )
            assert False, "Director no debe poder crear Director_Recinto"
        except HTTPException as he:
            assert he.status_code == 403
            print(f"Rechazo esperado de creación de par por Director: {he.detail}")

        # 3. Analista o Guardia intentan crear un usuario (Debe rechazar con HTTP 403)
        try:
            await create_user(
                db=db,
                user_in=UsuarioCreate(
                    email="test_rbac_sub@uct.cl",
                    nombre_completo="Usuario Ilegal",
                    password="password123",
                    roles=["Guardia_Seguridad"],
                ),
                creator=user_guardia,
            )
            assert False, "Guardia no debe poder crear usuarios"
        except HTTPException as he:
            assert he.status_code == 403
            print(f"Rechazo esperado de creación por Guardia: {he.detail}")

        # 4. Listado delegado: Director solo ve usuarios de su espacio o creados por él
        usuarios_vistos_director = await list_users(db=db, current_user=user_director)
        director_visible_emails = [u.email for u in usuarios_vistos_director]
        print(f"Usuarios visibles para Director Recinto 1: {director_visible_emails}")
        # El analista y guardia creados por él deben estar presentes
        assert user_analista.email in director_visible_emails
        assert user_guardia.email in director_visible_emails

        # 5. Listado para Guardia o Analista debe fallar con HTTP 403
        try:
            await list_users(db=db, current_user=user_guardia)
            assert False, "Guardia no debe poder listar usuarios"
        except HTTPException as he:
            assert he.status_code == 403
            print(f"Rechazo esperado de listado por Guardia: {he.detail}")

        print("TEST 3 SUPERADO CON ÉXITO.")

        # -------------------------------------------------------------------
        # TEST 4: Restricción de Recinto (Espacio Asignado)
        # -------------------------------------------------------------------
        print("\n--- TEST 4: Validación de Aislamiento por Recinto (espacio_id) ---")
        # Director asignado a espacio 1 opera sobre espacio 1 -> OK
        validar_acceso_espacio(espacio_id=1, current_user=user_director)
        print("Director operando sobre espacio asignado (1): Permitido.")

        # Director asignado a espacio 1 intenta operar sobre espacio 2 -> HTTP 403
        try:
            validar_acceso_espacio(espacio_id=2, current_user=user_director)
            assert False, "Director de espacio 1 no debe acceder a espacio 2"
        except HTTPException as he:
            assert he.status_code == 403
            print(f"Rechazo esperado acceso cruzado de recinto: {he.detail}")

        # Admin_Sistema opera sobre cualquier espacio -> OK
        validar_acceso_espacio(espacio_id=1, current_user=user_admin)
        validar_acceso_espacio(espacio_id=2, current_user=user_admin)
        print("Admin_Sistema operando sobre recintos 1 y 2: Permitido globalmente.")
        print("TEST 4 SUPERADO CON ÉXITO.")

        # -------------------------------------------------------------------
        # TEST 5: Tokens JWT y Compatibilidad con Roles Legados
        # -------------------------------------------------------------------
        print("\n--- TEST 5: Tokens JWT y Compatibilidad de Roles ---")
        token_admin = create_access_token(
            user_id=user_admin.id,
            rol=user_admin.primary_role,
            can_use_ai=user_admin.can_use_ai,
            can_export=user_admin.can_export,
            can_ingest=user_admin.can_ingest,
        )
        payload = decode_access_token(token_admin)
        assert payload["rol"] == "Admin_Sistema"
        assert payload["can_use_ai"] is True
        assert payload["can_ingest"] is True

        # Verificar require_roles con alias legado 'SuperAdmin' y formal 'Admin_Sistema'
        guard_legacy_superadmin = require_roles(["SuperAdmin"])
        guard_formal_admin = require_roles(["Admin_Sistema"])
        await guard_legacy_superadmin(current_user=user_admin)
        await guard_formal_admin(current_user=user_admin)
        print("Guard require_roles valida tanto 'SuperAdmin' como 'Admin_Sistema' transparentemente.")

        # Limpieza final de cuentas de prueba
        await db.execute(
            text("DELETE FROM usuarios WHERE email LIKE 'test_rbac_%@uct.cl'")
        )
        await db.commit()

        print("\n=====================================================================")
        print("TODAS LAS PRUEBAS RBAC (TEST 1 A TEST 5) PASARON CON ÉXITO TOTAL")
        print("=====================================================================")


if __name__ == "__main__":
    asyncio.run(run_tests())

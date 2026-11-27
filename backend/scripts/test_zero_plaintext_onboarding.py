"""
Script de verificación de ciclo de vida seguro de onboarding, activación y validación Zero-Plaintext (RF27).
Verifica:
1. Creación inactiva y credencial 'PENDIENTE_ACTIVACION'
2. Generación de token efímero y persistencia de su hash SHA-256 (sin texto plano)
3. Bloqueo de login previo a la activación
4. Validación de vigencia y token vía verificar_token_activacion
5. Rechazo de contraseñas débiles por reglas de complejidad
6. Activación exitosa con contraseña robusta (bcrypt) y seteo is_active = True
7. Bloqueo estricto contra reutilización del mismo token
8. Autenticación exitosa y generación de JWT con la nueva credencial
"""
import asyncio
import hashlib
import sys
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionLocal
from app.domain.auth_models import Rol, TokenActivacion, Usuario, UsuarioRol
from app.schemas.auth_schemas import UsuarioInviteRequest
from app.services.auth_service import (
    activar_cuenta_usuario,
    authenticate_user,
    create_access_token,
    decode_access_token,
    invitar_usuario,
    verificar_token_activacion,
)


async def main():
    print("=====================================================================")
    print("INICIANDO PRUEBAS DE ONBOARDING ZERO-PLAINTEXT Y ACTIVACIÓN (RF27)")
    print("=====================================================================\n")

    email_prueba = "test_onboarding_rf27@uct.cl"
    pass_debil = "uct123"
    pass_robusta = "UctSanFrancisco2026!#"

    async with AsyncSessionLocal() as db:
        # Limpieza previa de entorno de prueba
        stmt_del_user = select(Usuario).where(Usuario.email == email_prueba)
        res_del = await db.execute(stmt_del_user)
        user_prev = res_del.scalar_one_or_none()
        if user_prev:
            await db.execute(delete(TokenActivacion).where(TokenActivacion.usuario_id == user_prev.id))
            await db.execute(delete(UsuarioRol).where(UsuarioRol.usuario_id == user_prev.id))
            await db.execute(delete(Usuario).where(Usuario.id == user_prev.id))
            await db.commit()

        # -------------------------------------------------------------
        # PASO 1: Creación inactiva e invitación Zero-Plaintext
        # -------------------------------------------------------------
        print("--- PASO 1: Invitación de usuario y persistencia Zero-Plaintext ---")
        invite_data = UsuarioInviteRequest(
            email=email_prueba,
            nombre_completo="Investigador Onboarding Test",
            roles=["Analista_Consulta"],
            espacio_id=1,
            can_use_ai=True,
            can_export=True,
            can_ingest=False,
        )

        usuario_creado, token_plano, token_obj = await invitar_usuario(
            db=db,
            invite_in=invite_data,
            creator=None,
        )

        assert usuario_creado.is_active is False, "El usuario debe crearse con is_active = False"
        assert usuario_creado.hashed_password == "PENDIENTE_ACTIVACION", "La contraseña provisoria debe ser PENDIENTE_ACTIVACION"
        assert token_obj.utilizado is False, "El token debe iniciar con utilizado = False"
        assert token_obj.token_hash == hashlib.sha256(token_plano.encode("utf-8")).hexdigest(), "El token_hash debe ser el SHA-256 del token plano"
        print(f"Usuario creado inactivo (id={usuario_creado.id}, is_active={usuario_creado.is_active})")
        print(f"Token efímero plano: {token_plano[:8]}... (longitud={len(token_plano)})")
        print(f"Hash SHA-256 persistido en BD: {token_obj.token_hash}")
        print("PASO 1 SUPERADO EXITOSAMENTE.\n")

        # -------------------------------------------------------------
        # PASO 2: Bloqueo de inicio de sesión previo a activación
        # -------------------------------------------------------------
        print("--- PASO 2: Verificación de bloqueo de login previo a activación ---")
        login_intento = await authenticate_user(db, email_prueba, "cualquier_password")
        assert login_intento is None, "El login no debe permitir acceso a usuarios pendientes de activación"
        print("Acceso denegado correctamente para cuenta inactiva / pendiente de activación.")
        print("PASO 2 SUPERADO EXITOSAMENTE.\n")

        # -------------------------------------------------------------
        # PASO 3: Validación criptográfica del token
        # -------------------------------------------------------------
        print("--- PASO 3: Validación de token efímero vía verificar_token_activacion ---")
        token_verificado, user_asociado = await verificar_token_activacion(db, token_plano)
        assert token_verificado.id == token_obj.id
        assert user_asociado.id == usuario_creado.id
        assert user_asociado.email == email_prueba
        print(f"Token válido asociado a: {user_asociado.email} (expira en: {token_verificado.expira_en})")
        print("PASO 3 SUPERADO EXITOSAMENTE.\n")

        # -------------------------------------------------------------
        # PASO 4: Rechazo de contraseñas débiles o dispares
        # -------------------------------------------------------------
        print("--- PASO 4: Evaluación de reglas de complejidad de contraseña ---")
        # Intento con contraseña corta/débil
        try:
            await activar_cuenta_usuario(
                db=db,
                token=token_plano,
                nueva_password=pass_debil,
                confirmar_password=pass_debil,
            )
            assert False, "Debe rechazar contraseñas que no cumplen complejidad"
        except HTTPException as e:
            assert e.status_code == 400
            print(f"Rechazo esperado por debilidad: {e.detail}")

        # Intento con contraseñas que no coinciden
        try:
            await activar_cuenta_usuario(
                db=db,
                token=token_plano,
                nueva_password=pass_robusta,
                confirmar_password="OtraPassword123!",
            )
            assert False, "Debe rechazar contraseñas que no coinciden"
        except HTTPException as e:
            assert e.status_code == 400
            print(f"Rechazo esperado por no coincidencia: {e.detail}")
        print("PASO 4 SUPERADO EXITOSAMENTE.\n")

        # -------------------------------------------------------------
        # PASO 5: Activación exitosa de la cuenta
        # -------------------------------------------------------------
        print("--- PASO 5: Activación exitosa con contraseña robusta ---")
        usuario_activado = await activar_cuenta_usuario(
            db=db,
            token=token_plano,
            nueva_password=pass_robusta,
            confirmar_password=pass_robusta,
            ip_solicitante="127.0.0.1",
        )
        assert usuario_activado.is_active is True, "El usuario debe quedar activo tras la activación"
        assert usuario_activado.hashed_password.startswith("$2"), "La contraseña debe quedar hasheada con bcrypt"

        # Verificar que el token quedó marcado como utilizado
        stmt_chk = select(TokenActivacion).where(TokenActivacion.id == token_obj.id)
        res_chk = await db.execute(stmt_chk)
        token_post = res_chk.scalar_one()
        assert token_post.utilizado is True, "El token debe quedar marcado como utilizado = True"
        assert token_post.fecha_utilizacion is not None, "Debe registrarse la fecha_utilizacion"
        assert token_post.ip_solicitante == "127.0.0.1", "Debe registrarse la IP solicitante"
        print(f"Usuario activado exitosamente (id={usuario_activado.id}, is_active={usuario_activado.is_active})")
        print(f"Nuevo hash bcrypt: {usuario_activado.hashed_password[:15]}...")
        print(f"Token {token_post.id} marcado como utilizado={token_post.utilizado} en {token_post.fecha_utilizacion}")
        print("PASO 5 SUPERADO EXITOSAMENTE.\n")

        # -------------------------------------------------------------
        # PASO 6: Bloqueo de reutilización del mismo token
        # -------------------------------------------------------------
        print("--- PASO 6: Verificación de bloqueo de reutilización de token (Zero-Plaintext) ---")
        try:
            await verificar_token_activacion(db, token_plano)
            assert False, "No debe permitir reutilizar un token ya consumido"
        except HTTPException as e:
            assert e.status_code == 400
            print(f"Rechazo esperado de reutilización: {e.detail}")

        try:
            await activar_cuenta_usuario(
                db=db,
                token=token_plano,
                nueva_password=pass_robusta,
                confirmar_password=pass_robusta,
            )
            assert False, "No debe permitir activar nuevamente con el mismo token"
        except HTTPException as e:
            assert e.status_code == 400
            print(f"Rechazo esperado en reactivación: {e.detail}")
        print("PASO 6 SUPERADO EXITOSAMENTE.\n")

        # -------------------------------------------------------------
        # PASO 7: Inicio de sesión exitoso con la nueva contraseña
        # -------------------------------------------------------------
        print("--- PASO 7: Autenticación exitosa y emisión de token JWT ---")
        usuario_auth = await authenticate_user(db, email_prueba, pass_robusta)
        assert usuario_auth is not None, "El usuario recién activado debe autenticarse exitosamente"
        assert usuario_auth.id == usuario_activado.id

        jwt_token = create_access_token(
            user_id=usuario_auth.id,
            rol=usuario_auth.primary_role,
            roles=[r.nombre for r in usuario_auth.roles],
            allowed_datasets=usuario_auth.allowed_datasets,
            can_use_ai=usuario_auth.can_use_ai,
            can_export=usuario_auth.can_export,
            can_ingest=usuario_auth.can_ingest,
            espacio_id=usuario_auth.espacio_id,
        )
        assert isinstance(jwt_token, str) and len(jwt_token) > 20
        payload = decode_access_token(jwt_token)
        assert payload["user_id"] == usuario_auth.id
        assert payload["rol"] == "Analista_Consulta"
        assert payload["can_use_ai"] is True
        print(f"Autenticación exitosa. JWT emitido para {usuario_auth.email} con rol {payload['rol']}")
        print("PASO 7 SUPERADO EXITOSAMENTE.\n")

        # Limpieza de registros de prueba
        await db.execute(delete(TokenActivacion).where(TokenActivacion.usuario_id == usuario_activado.id))
        await db.execute(delete(UsuarioRol).where(UsuarioRol.usuario_id == usuario_activado.id))
        await db.execute(delete(Usuario).where(Usuario.id == usuario_activado.id))
        await db.commit()
        print("Registros de prueba eliminados correctamente.")

    print("\n=====================================================================")
    print("TODAS LAS PRUEBAS ONBOARDING ZERO-PLAINTEXT (PASO 1 A 7) SUPERADAS")
    print("=====================================================================")


if __name__ == "__main__":
    asyncio.run(main())

from typing import Callable, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    get_current_user,
    require_role,
    require_roles,
    require_permission,
    validar_acceso_espacio,
    normalizar_rol,
)
from app.domain.auth_models import Usuario, Rol
from app.schemas.auth_schemas import (
    ActivarCuentaRequest,
    ActivarCuentaResponse,
    EliminarUsuarioResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    ResetPasswordRequest,
    ResetPasswordResponse,
    RolResponse,
    TokenPayload,
    TokenResponse,
    TokenVerifyResponse,
    UnlockUserResponse,
    UsuarioCreate,
    UsuarioInviteRequest,
    UsuarioInviteResponse,
    UsuarioResponse,
    UserStatusUpdate,
)
from app.services.auth_service import (
    activar_cuenta_usuario,
    authenticate_user,
    create_access_token,
    create_user,
    decode_access_token,
    desbloquear_cuenta_admin,
    eliminar_usuario_cuenta,
    get_user_by_email,
    get_user_by_id,
    invitar_usuario,
    list_users,
    reenviar_invitacion_usuario,
    restablecer_password_con_token,
    seed_default_roles,
    solicitar_recuperacion_password,
    update_user_status,
    verificar_token_activacion,
)
from app.services.email_service import enviar_correo_activacion, enviar_correo_recuperacion

router = APIRouter()


@router.post("/login", response_model=TokenResponse, summary="Autenticación y generación de JWT")
async def login(
    credentials: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    user = await authenticate_user(
        db=db,
        email=credentials.email,
        password=credentials.password,
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo electrónico o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta de usuario inactiva",
        )

    roles_list = [r.nombre for r in user.roles]
    primary_role = user.primary_role
    access_token = create_access_token(
        user_id=user.id,
        rol=primary_role,
        roles=roles_list,
        allowed_datasets=user.allowed_datasets,
        can_use_ai=user.can_use_ai,
        can_export=user.can_export,
        can_ingest=user.can_ingest,
        espacio_id=user.espacio_id,
    )

    try:
        import asyncio
        from app.core.cache import precalentar_cache_modulos
        asyncio.create_task(precalentar_cache_modulos())
    except Exception:
        pass

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user_id=user.id,
        rol=primary_role,
        roles=roles_list,
        allowed_datasets=user.allowed_datasets,
        can_use_ai=user.can_use_ai,
        can_export=user.can_export,
        can_ingest=user.can_ingest,
        espacio_id=user.espacio_id,
    )


def map_usuario_response(u: Usuario) -> UsuarioResponse:
    return UsuarioResponse(
        id=u.id,
        email=u.email,
        nombre_completo=u.nombre_completo,
        is_active=u.is_active,
        allowed_datasets=u.allowed_datasets,
        can_use_ai=u.can_use_ai,
        can_export=u.can_export,
        can_ingest=u.can_ingest,
        espacio_id=u.espacio_id,
        created_by_user_id=u.created_by_user_id,
        intentos_fallidos_login=u.intentos_fallidos_login or 0,
        bloqueado_hasta=u.bloqueado_hasta,
        created_at=u.created_at,
        roles=[
            RolResponse(id=r.id, nombre=r.nombre, descripcion=r.descripcion)
            for r in u.roles
        ],
    )


@router.get("/me", response_model=UsuarioResponse, summary="Perfil del usuario autenticado")
async def get_me(
    current_user: Usuario = Depends(get_current_user),
) -> UsuarioResponse:
    return map_usuario_response(current_user)


@router.post(
    "/seed-roles",
    response_model=List[RolResponse],
    summary="Inicialización de roles por defecto",
)
async def initialize_roles(
    db: AsyncSession = Depends(get_db),
) -> List[RolResponse]:
    created = await seed_default_roles(db)
    return [
        RolResponse(id=r.id, nombre=r.nombre, descripcion=r.descripcion)
        for r in created
    ]


@router.get(
    "/roles",
    response_model=List[RolResponse],
    summary="Listar roles institucionales definidos en el sistema",
)
async def list_roles_endpoint(
    current_user: Usuario = Depends(require_role("Admin_Sistema", "Director_Recinto")),
    db: AsyncSession = Depends(get_db),
) -> List[RolResponse]:
    stmt = select(Rol).order_by(Rol.id.asc())
    roles = (await db.execute(stmt)).scalars().all()
    if not roles:
        roles = await seed_default_roles(db)
    return [
        RolResponse(
            id=r.id,
            nombre=r.nombre,
            descripcion=r.descripcion,
            rate_limit_quota=r.rate_limit_quota or "30/day",
            cooldown_segundos=getattr(r, "cooldown_segundos", 10) or 10,
        )
        for r in roles
    ]


@router.post(
    "/register",
    response_model=UsuarioResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registro de nuevo usuario con administración delegada (RF22)",
)
async def register_user(
    user_in: UsuarioCreate,
    current_user: Usuario = Depends(require_role("Admin_Sistema", "Director_Recinto")),
    db: AsyncSession = Depends(get_db),
) -> UsuarioResponse:
    existing = await get_user_by_email(db, user_in.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El correo electrónico ya se encuentra registrado",
        )
    user = await create_user(db=db, user_in=user_in, creator=current_user)
    return map_usuario_response(user)


@router.get(
    "/users",
    response_model=List[UsuarioResponse],
    summary="Listar usuarios del sistema con filtrado delegado",
)
async def get_all_users(
    current_user: Usuario = Depends(require_role("Admin_Sistema", "Director_Recinto")),
    db: AsyncSession = Depends(get_db),
) -> List[UsuarioResponse]:
    users = await list_users(db, current_user=current_user)
    return [map_usuario_response(u) for u in users]


@router.patch(
    "/users/{user_id}/status",
    response_model=UsuarioResponse,
    summary="Actualizar estado activo/inactivo y permisos de un usuario",
)
async def update_user_status_endpoint(
    user_id: int,
    status_in: UserStatusUpdate,
    current_user: Usuario = Depends(require_role("Admin_Sistema", "Director_Recinto")),
    db: AsyncSession = Depends(get_db),
) -> UsuarioResponse:
    updated = await update_user_status(
        db,
        user_id=user_id,
        is_active=status_in.is_active,
        can_use_ai=status_in.can_use_ai,
        current_user=current_user,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )
    return map_usuario_response(updated)


@router.post(
    "/users/{user_id}/resend-invitation",
    response_model=UsuarioInviteResponse,
    summary="Reenviar token y enlace de activación o restablecimiento para un usuario",
)
async def resend_invitation_endpoint(
    user_id: int,
    background_tasks: BackgroundTasks,
    current_user: Usuario = Depends(require_role("Admin_Sistema", "Director_Recinto")),
    db: AsyncSession = Depends(get_db),
) -> UsuarioInviteResponse:
    user, token_plano, token_obj = await reenviar_invitacion_usuario(
        db=db,
        user_id=user_id,
        creator=current_user,
    )
    enlace_activacion = f"{settings.FRONTEND_URL}/activar-cuenta?token={token_plano}"

    background_tasks.add_task(
        enviar_correo_activacion,
        email_destinatario=user.email,
        nombre_usuario=user.nombre_completo,
        enlace_activacion=enlace_activacion,
        token_plano=token_plano,
    )

    return UsuarioInviteResponse(
        usuario=map_usuario_response(user),
        enlace_activacion=enlace_activacion,
        token_temporal=token_plano,
        expira_en=token_obj.expira_en,
    )


@router.post(
    "/invite",
    response_model=UsuarioInviteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Invitar usuario con alta inicial en estado inactivo y token efímero Zero-Plaintext (RF27)",
)
async def invite_user(
    invite_in: UsuarioInviteRequest,
    background_tasks: BackgroundTasks,
    current_user: Usuario = Depends(require_role("Admin_Sistema", "Director_Recinto")),
    db: AsyncSession = Depends(get_db),
) -> UsuarioInviteResponse:
    existing = await get_user_by_email(db, invite_in.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El correo electrónico ya se encuentra registrado en el sistema.",
        )

    user, token_plano, token_obj = await invitar_usuario(
        db=db,
        invite_in=invite_in,
        creator=current_user,
    )

    enlace = f"/activar-cuenta?token={token_plano}"
    enlace_completo = f"{settings.FRONTEND_URL}/activar-cuenta?token={token_plano}"
    user_resp = map_usuario_response(user)

    # Despacho en segundo plano del correo de activación institucional
    background_tasks.add_task(
        enviar_correo_activacion,
        user.email,
        user.nombre_completo or "",
        enlace_completo,
    )

    return UsuarioInviteResponse(
        usuario=user_resp,
        enlace_activacion=enlace,
        token_temporal=token_plano,
        expira_en=token_obj.expira_en,
        mensaje="Invitación generada exitosamente. Se ha despachado el enlace de activación al correo institucional.",
    )


@router.get(
    "/verify-token",
    response_model=TokenVerifyResponse,
    summary="Validación criptográfica de token de activación o recuperación (RF27)",
)
async def verify_token_endpoint(
    token: str = Query(..., min_length=10, description="Token efímero de activación"),
    db: AsyncSession = Depends(get_db),
) -> TokenVerifyResponse:
    token_obj, usuario = await verificar_token_activacion(db=db, token=token)
    return TokenVerifyResponse(
        es_valido=True,
        email=usuario.email,
        nombre_completo=usuario.nombre_completo,
        expira_en=token_obj.expira_en,
        tipo_token=token_obj.tipo_token,
    )


@router.post(
    "/activate",
    response_model=ActivarCuentaResponse,
    summary="Activación segura de cuenta mediante definición de contraseña en bcrypt (RF27)",
)
async def activate_account_endpoint(
    payload: ActivarCuentaRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ActivarCuentaResponse:
    ip_cliente = request.client.host if request.client else None
    usuario = await activar_cuenta_usuario(
        db=db,
        token=payload.token,
        nueva_password=payload.nueva_password,
        confirmar_password=payload.confirmar_password,
        ip_solicitante=ip_cliente,
    )
    return ActivarCuentaResponse(
        mensaje="Cuenta activada con éxito. Ya puede iniciar sesión con su nueva contraseña.",
        email=usuario.email,
        exito=True,
    )


@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
    summary="Solicitud pública de recuperación de contraseña con respuesta neutral anti-enumeración (RF27)",
)
async def forgot_password_endpoint(
    payload: ForgotPasswordRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> ForgotPasswordResponse:
    ip_cliente = request.client.host if request.client else None
    existe, token_plano, expira_en, nombre_completo = await solicitar_recuperacion_password(
        db=db,
        email=payload.email,
        ip_solicitante=ip_cliente,
    )

    if existe and token_plano:
        enlace_completo = f"{settings.FRONTEND_URL}/recuperar-password?token={token_plano}"
        background_tasks.add_task(
            enviar_correo_recuperacion,
            payload.email,
            nombre_completo or "",
            enlace_completo,
        )

    # Respuesta neutral OWASP ASVS: nunca revelar si el correo existe o no
    mensaje_neutral = (
        "Si el correo institucional se encuentra registrado en la plataforma DSS, "
        "recibirá un enlace con las instrucciones para restablecer su contraseña (validez: 15 minutos)."
    )

    enlace = f"/recuperar-password?token={token_plano}" if token_plano else None

    return ForgotPasswordResponse(
        mensaje=mensaje_neutral,
        enlace_recuperacion=enlace,
        token_temporal=token_plano,
        expira_en=expira_en,
    )


@router.post(
    "/reset-password",
    response_model=ResetPasswordResponse,
    summary="Restablecimiento autónomo de credenciales por token efímero y desbloqueo de cuenta (RF27)",
)
async def reset_password_endpoint(
    payload: ResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ResetPasswordResponse:
    ip_cliente = request.client.host if request.client else None
    usuario = await restablecer_password_con_token(
        db=db,
        token=payload.token,
        nueva_password=payload.nueva_password,
        confirmar_password=payload.confirmar_password,
        ip_solicitante=ip_cliente,
    )
    return ResetPasswordResponse(
        mensaje="Su contraseña ha sido restablecida exitosamente y su cuenta ha sido desbloqueada. Ya puede iniciar sesión.",
        email=usuario.email,
        exito=True,
    )


@router.post(
    "/users/{user_id}/unlock",
    response_model=UnlockUserResponse,
    summary="Desbloqueo administrativo de cuentas con control RBAC delegado (RF22, RF27)",
)
async def unlock_user_endpoint(
    user_id: int,
    current_user: Usuario = Depends(require_role("Admin_Sistema", "Director_Recinto")),
    db: AsyncSession = Depends(get_db),
) -> UnlockUserResponse:
    usuario = await desbloquear_cuenta_admin(
        db=db,
        user_id=user_id,
        current_user=current_user,
    )
    return UnlockUserResponse(
        mensaje=f"La cuenta del usuario {usuario.email} ha sido desbloqueada exitosamente.",
        user_id=usuario.id,
        desbloqueado=True,
    )


@router.delete(
    "/users/{user_id}",
    response_model=EliminarUsuarioResponse,
    summary="Eliminación permanente de cuenta de usuario por Super Administrador UCT (RF27)",
)
async def delete_user_endpoint(
    user_id: int,
    current_user: Usuario = Depends(require_role("Admin_Sistema")),
    db: AsyncSession = Depends(get_db),
) -> EliminarUsuarioResponse:
    await eliminar_usuario_cuenta(
        db=db,
        usuario_id=user_id,
        admin_solicitante=current_user,
    )
    return EliminarUsuarioResponse(
        mensaje="Cuenta de usuario y accesos eliminados permanentemente del sistema DSS.",
        usuario_id=user_id,
        exito=True,
    )




from typing import Callable, List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.domain.auth_models import Usuario
from app.schemas.auth_schemas import (
    LoginRequest,
    RolResponse,
    TokenResponse,
    UsuarioCreate,
    UsuarioResponse,
    UserStatusUpdate,
)
from app.services.auth_service import (
    authenticate_user,
    create_access_token,
    create_user,
    decode_access_token,
    get_user_by_email,
    get_user_by_id,
    list_users,
    seed_default_roles,
    update_user_status,
)

router = APIRouter()
bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Usuario:
    token = credentials.credentials
    payload = decode_access_token(token)
    user_id = payload.get("user_id")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales de autenticación no válidas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await get_user_by_id(db, user_id=int(user_id))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inactivo",
        )
    return user


def require_role(*allowed_roles: str) -> Callable:
    async def role_checker(
        current_user: Usuario = Depends(get_current_user),
    ) -> Usuario:
        user_roles = [r.nombre for r in current_user.roles]
        if not any(r in allowed_roles for r in user_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permisos insuficientes para realizar esta acción",
            )
        return current_user

    return role_checker


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
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user_id=user.id,
        rol=primary_role,
        roles=roles_list,
        allowed_datasets=user.allowed_datasets,
    )


@router.get("/me", response_model=UsuarioResponse, summary="Perfil del usuario autenticado")
async def get_me(
    current_user: Usuario = Depends(get_current_user),
) -> UsuarioResponse:
    return UsuarioResponse(
        id=current_user.id,
        email=current_user.email,
        nombre_completo=current_user.nombre_completo,
        is_active=current_user.is_active,
        allowed_datasets=current_user.allowed_datasets,
        created_at=current_user.created_at,
        roles=[
            RolResponse(id=r.id, nombre=r.nombre, descripcion=r.descripcion)
            for r in current_user.roles
        ],
    )


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


@router.post(
    "/register",
    response_model=UsuarioResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registro de nuevo usuario",
)
async def register_user(
    user_in: UsuarioCreate,
    db: AsyncSession = Depends(get_db),
) -> UsuarioResponse:
    existing = await get_user_by_email(db, user_in.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El correo electrónico ya se encuentra registrado",
        )
    user = await create_user(db, user_in)
    return UsuarioResponse(
        id=user.id,
        email=user.email,
        nombre_completo=user.nombre_completo,
        is_active=user.is_active,
        allowed_datasets=user.allowed_datasets,
        created_at=user.created_at,
        roles=[
            RolResponse(id=r.id, nombre=r.nombre, descripcion=r.descripcion)
            for r in user.roles
        ],
    )


@router.get(
    "/users",
    response_model=List[UsuarioResponse],
    summary="Listar usuarios del sistema",
)
async def get_all_users(
    _: Usuario = Depends(require_role("SuperAdmin")),
    db: AsyncSession = Depends(get_db),
) -> List[UsuarioResponse]:
    users = await list_users(db)
    return [
        UsuarioResponse(
            id=u.id,
            email=u.email,
            nombre_completo=u.nombre_completo,
            is_active=u.is_active,
            allowed_datasets=u.allowed_datasets,
            created_at=u.created_at,
            roles=[
                RolResponse(id=r.id, nombre=r.nombre, descripcion=r.descripcion)
                for r in u.roles
            ],
        )
        for u in users
    ]


@router.patch(
    "/users/{user_id}/status",
    response_model=UsuarioResponse,
    summary="Actualizar estado activo/inactivo de un usuario",
)
async def update_user_status_endpoint(
    user_id: int,
    status_in: UserStatusUpdate,
    _: Usuario = Depends(require_role("SuperAdmin")),
    db: AsyncSession = Depends(get_db),
) -> UsuarioResponse:
    updated = await update_user_status(db, user_id=user_id, is_active=status_in.is_active)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )
    return UsuarioResponse(
        id=updated.id,
        email=updated.email,
        nombre_completo=updated.nombre_completo,
        is_active=updated.is_active,
        allowed_datasets=updated.allowed_datasets,
        created_at=updated.created_at,
        roles=[
            RolResponse(id=r.id, nombre=r.nombre, descripcion=r.descripcion)
            for r in updated.roles
        ],
    )

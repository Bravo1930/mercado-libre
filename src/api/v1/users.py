"""API REST para Gestión de Usuarios y Control de Acceso."""

from datetime import datetime, timedelta, timezone
import uuid
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.audit import record_audit_event
from src.core.auth_context import UserContext, get_current_user
from src.core.config import get_settings
from src.core.database import get_db
from src.core.exceptions import (
    AuthenticationFailedException,
    EntityAlreadyExistsException,
    EntityNotFoundException,
    PermissionDeniedException,
)
from src.core.pagination import Page, PaginationParams
from src.core.permissions import RoleEnum, can_assign_role
from src.core.security import create_access_token, hash_password, verify_password
from src.models.user import User, UserSession
from src.repositories.base import BaseRepository
from src.schemas.user import TokenResponse, UserCreate, UserLogin, UserResponse, UserUpdate

router = APIRouter(prefix="/users", tags=["Usuarios"])
user_repo = BaseRepository[User](User)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    session: AsyncSession = Depends(get_db),
) -> User:
    """Registra un nuevo usuario con contraseña cifrada (bcrypt) y validación de unicidad."""
    stmt = select(User).where(User.email == payload.email)
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing:
        raise EntityAlreadyExistsException("Usuario", "email", payload.email)

    user_data = payload.model_dump()
    raw_password = user_data.pop("password")
    user_data["password_hash"] = hash_password(raw_password)
    user_data["role"] = payload.role.value if hasattr(payload.role, "value") else str(payload.role)

    user = await user_repo.create(session, user_data)

    await record_audit_event(
        session=session,
        action="CREATE_USER",
        entity_name="User",
        entity_id=str(user.id),
        changes={"email": user.email, "role": user.role},
    )
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: UserLogin,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Autentica a un usuario, genera su sesión activa en BD y emite el token JWT."""
    stmt = select(User).where(User.email == payload.email)
    user = (await session.execute(stmt)).scalar_one_or_none()

    if not user or not verify_password(payload.password, user.password_hash):
        raise AuthenticationFailedException("Correo electrónico o contraseña incorrectos.")

    if not user.is_active:
        raise AuthenticationFailedException("La cuenta de usuario se encuentra inactiva.")

    settings = get_settings()
    jti = str(uuid.uuid4())
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    user_session = UserSession(
        user_id=user.id,
        token_jti=jti,
        ip_address=client_ip,
        user_agent=user_agent[:255] if user_agent else None,
        device_info=user_agent[:100] if user_agent else "Cliente API",
        is_revoked=False,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
        last_activity_at=datetime.now(timezone.utc),
    )
    session.add(user_session)
    user.last_login_at = datetime.now(timezone.utc)
    await session.flush()

    token_claims = {
        "sub": str(user.id),
        "jti": jti,
        "email": user.email,
        "role": user.role,
        "tenant_id": str(user.tenant_id) if user.tenant_id else None,
    }
    jwt_token = create_access_token(token_claims)

    await record_audit_event(
        session=session,
        action="LOGIN_SUCCESS",
        entity_name="UserSession",
        entity_id=jti,
        user_id=user.id,
        changes={"ip": client_ip},
        ip_address=client_ip,
    )

    return TokenResponse(
        access_token=jwt_token,
        token_type="bearer",
        expires_in_minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
        user=user,
        authorized_companies=[],
    )


@router.get("", response_model=Page[UserResponse])
async def list_users(
    tenant_id: uuid.UUID | None = Query(None, description="Filtrar por Tenant ID"),
    params: PaginationParams = Depends(),
    session: AsyncSession = Depends(get_db),
) -> Page[User]:
    """Lista usuarios paginados con filtro opcional por organización."""
    filters = []
    if tenant_id:
        filters.append(User.tenant_id == tenant_id)
    return await user_repo.get_paginated(session, params, *filters)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> User:
    """Obtiene los detalles de un usuario por su UUID."""
    return await user_repo.get_or_fail(session, user_id)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    user_ctx: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Actualiza datos de un usuario con validación contra escalamiento de privilegios."""
    user = await user_repo.get_or_fail(session, user_id)

    if payload.role is not None:
        if not can_assign_role(user_ctx.role, payload.role.value):
            raise PermissionDeniedException(
                f"Escalamiento denegado: El rol '{user_ctx.role}' no puede asignar el rol '{payload.role.value}'."
            )
        user.role = payload.role.value

    if payload.full_name is not None:
        user.full_name = payload.full_name

    if payload.is_active is not None:
        user.is_active = payload.is_active

    await session.flush()

    await record_audit_event(
        session=session,
        action="UPDATE_USER",
        entity_name="User",
        entity_id=str(user.id),
        user_id=user_ctx.id,
        changes=payload.model_dump(exclude_unset=True),
    )
    return user

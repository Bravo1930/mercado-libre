"""API REST para Usuarios y Autenticación JWT."""

import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.database import get_db
from src.core.exceptions import AuthenticationFailedException, EntityAlreadyExistsException
from src.core.pagination import Page, PaginationParams
from src.core.security import create_access_token, hash_password, verify_password
from src.models.user import User
from src.repositories.base import BaseRepository
from src.schemas.user import TokenResponse, UserCreate, UserLogin, UserResponse

router = APIRouter(prefix="/users", tags=["Usuarios"])
user_repo = BaseRepository[User](User)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    session: AsyncSession = Depends(get_db),
) -> User:
    """Registra un nuevo usuario con contraseña cifrada (bcrypt)."""
    stmt = select(User).where(User.email == payload.email)
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing:
        raise EntityAlreadyExistsException("Usuario", "email", payload.email)

    user_data = payload.model_dump()
    raw_password = user_data.pop("password")
    user_data["password_hash"] = hash_password(raw_password)

    user = await user_repo.create(session, user_data)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: UserLogin,
    session: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Autentica a un usuario y genera su token JWT de sesión."""
    stmt = select(User).where(User.email == payload.email)
    user = (await session.execute(stmt)).scalar_one_or_none()

    if not user or not verify_password(payload.password, user.password_hash):
        raise AuthenticationFailedException("Correo electrónico o contraseña incorrectos.")

    if not user.is_active:
        raise AuthenticationFailedException("La cuenta de usuario se encuentra inactiva.")

    settings = get_settings()
    token_claims = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "tenant_id": str(user.tenant_id),
    }
    jwt_token = create_access_token(token_claims)

    return TokenResponse(
        access_token=jwt_token,
        token_type="bearer",
        expires_in_minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
        user_id=user.id,
        role=user.role,
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

"""API REST para Cuentas de Vendedor de Mercado Libre México."""

from datetime import datetime, timedelta, timezone
import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.audit import record_audit_event
from src.core.auth_context import CompanyContext, require_company_permission
from src.core.database import get_db
from src.core.exceptions import EntityAlreadyExistsException, PermissionDeniedException
from src.core.pagination import Page, PaginationParams
from src.core.permissions import ActionEnum, ModuleEnum
from src.core.security import encrypt_token
from src.models.meli_account import MeliAccount
from src.repositories.base import BaseRepository
from src.schemas.meli_account import MeliAccountCreate, MeliAccountResponse

router = APIRouter(prefix="/meli-accounts", tags=["Cuentas Mercado Libre"])
meli_account_repo = BaseRepository[MeliAccount](MeliAccount)


@router.post("", response_model=MeliAccountResponse, status_code=status.HTTP_201_CREATED)
async def register_meli_account(
    payload: MeliAccountCreate,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.MELI_ACCOUNTS, ActionEnum.CREATE)),
    session: AsyncSession = Depends(get_db),
) -> MeliAccount:
    """
    Vincula una cuenta de Mercado Libre a la empresa activa.
    Encripta de forma transparente los tokens de acceso y renovación con AES-256 (Fernet).
    """
    if payload.company_id != ctx.company_id:
        raise PermissionDeniedException("No se puede vincular una cuenta de Mercado Libre a una empresa distinta a la activa.")

    stmt = select(MeliAccount).where(MeliAccount.meli_user_id == payload.meli_user_id)
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing:
        raise EntityAlreadyExistsException("Cuenta Mercado Libre", "meli_user_id", payload.meli_user_id)

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=payload.expires_in_seconds)

    account = MeliAccount(
        company_id=payload.company_id,
        meli_user_id=payload.meli_user_id,
        nickname=payload.nickname,
        site_id="MLM",
        access_token_enc=encrypt_token(payload.access_token_plain),
        refresh_token_enc=encrypt_token(payload.refresh_token_plain),
        token_expires_at=expires_at,
        is_active=True,
    )
    session.add(account)
    await session.flush()

    await record_audit_event(
        session=session,
        company_id=account.company_id,
        action="LINK_MELI_ACCOUNT",
        entity_name="MeliAccount",
        entity_id=str(account.id),
        user_id=ctx.user.id,
        changes={"nickname": account.nickname, "meli_user_id": account.meli_user_id},
    )
    return account


@router.get("", response_model=Page[MeliAccountResponse])
async def list_meli_accounts(
    is_active: bool | None = Query(None),
    params: PaginationParams = Depends(),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.MELI_ACCOUNTS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> Page[MeliAccount]:
    """Lista las cuentas de Mercado Libre vinculadas a la empresa activa."""
    filters = [MeliAccount.company_id == ctx.company_id]
    if is_active is not None:
        filters.append(MeliAccount.is_active == is_active)
    return await meli_account_repo.get_paginated(session, params, *filters)


@router.get("/{account_id}", response_model=MeliAccountResponse)
async def get_meli_account(
    account_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.MELI_ACCOUNTS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> MeliAccount:
    """Obtiene los detalles de una cuenta de Mercado Libre validando la pertenencia a la empresa."""
    stmt = select(MeliAccount).where(
        MeliAccount.id == account_id,
        MeliAccount.company_id == ctx.company_id,
    )
    account = (await session.execute(stmt)).scalar_one_or_none()
    if not account:
        raise PermissionDeniedException("La cuenta de Mercado Libre solicitada no existe o no pertenece a tu empresa.")
    return account

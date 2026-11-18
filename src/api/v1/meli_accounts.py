"""API REST para Cuentas de Vendedor y Conector oficial de Mercado Libre México."""

from datetime import datetime, timedelta, timezone
import secrets
from typing import Any
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.connectors.meli import MercadoLibreConnector
from src.core.audit import record_audit_event
from src.core.auth_context import CompanyContext, require_company_permission
from src.core.config import get_settings
from src.core.database import get_db
from src.core.exceptions import (
    AppException,
    EntityAlreadyExistsException,
    EntityNotFoundException,
    PermissionDeniedException,
)
from src.core.pagination import Page, PaginationParams
from src.core.permissions import ActionEnum, ModuleEnum
from src.core.security import encrypt_token
from src.models.meli_account import MeliAccount
from src.repositories.base import BaseRepository
from src.schemas.meli_account import (
    MeliAccountCreate,
    MeliAccountReconnectRequest,
    MeliAccountResponse,
    MeliConnectionTestResponse,
    MeliOAuthCallbackRequest,
    MeliOAuthUrlResponse,
    MeliUpdatePriceRequest,
    MeliUpdateStockRequest,
)

router = APIRouter(prefix="/meli-accounts", tags=["Cuentas Mercado Libre"])
meli_account_repo = BaseRepository[MeliAccount](MeliAccount)


async def _get_account_and_verify_ownership(
    session: AsyncSession, account_id: uuid.UUID, company_id: uuid.UUID
) -> MeliAccount:
    """Verifica que la cuenta de Mercado Libre pertenezca a la empresa activa."""
    stmt = select(MeliAccount).where(
        MeliAccount.id == account_id,
        MeliAccount.company_id == company_id,
    )
    account = (await session.execute(stmt)).scalar_one_or_none()
    if not account:
        raise PermissionDeniedException("La cuenta de Mercado Libre solicitada no existe o no pertenece a tu empresa.")
    return account


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


@router.get("/auth-url", response_model=MeliOAuthUrlResponse)
async def get_meli_authorization_url(
    redirect_uri: str | None = Query(None, description="URI de redirección opcional si difiere de la default"),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.MELI_ACCOUNTS, ActionEnum.CREATE)),
) -> dict[str, str]:
    """
    Genera la URL oficial de autorización OAuth en Mercado Libre México (auth.mercadolibre.com.mx).
    Genera un 'state' seguro que vincula la sesión de la empresa para evitar ataques CSRF.
    """
    settings = get_settings()
    state_token = f"comp_{ctx.company_id}_{secrets.token_urlsafe(16)}"
    connector = MercadoLibreConnector()
    auth_url = connector.oauth.get_authorization_url(state=state_token, custom_redirect_uri=redirect_uri)

    return {
        "auth_url": auth_url,
        "app_id": settings.MELI_APP_ID,
        "redirect_uri": redirect_uri or settings.MELI_REDIRECT_URI,
        "state": state_token,
    }


@router.post("/oauth-callback", response_model=MeliAccountResponse, status_code=status.HTTP_201_CREATED)
async def process_oauth_callback(
    payload: MeliOAuthCallbackRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.MELI_ACCOUNTS, ActionEnum.CREATE)),
    session: AsyncSession = Depends(get_db),
) -> MeliAccount:
    """
    Procesa el authorization code recibido de Mercado Libre:
    1. Intercambia el código por access_token y refresh_token mediante POST /oauth/token.
    2. Consulta /users/me para obtener el meli_user_id y nickname oficiales del vendedor.
    3. Registra o actualiza la cuenta cifrando sus credenciales con AES-256.
    """
    connector = MercadoLibreConnector()
    token_data = await connector.oauth.exchange_code_for_token(
        code=payload.code, custom_redirect_uri=payload.redirect_uri
    )

    access_token = token_data["access_token"]
    refresh_token = token_data["refresh_token"]
    meli_user_id = token_data["user_id"]
    expires_in = token_data.get("expires_in", 21600)

    # Consultar perfil oficial del usuario en MeLi
    temp_connector = MercadoLibreConnector(app_id=connector.app_id, client_secret=connector.client_secret)
    temp_connector._cached_access_token = access_token
    user_info = await temp_connector.users.get_me()
    nickname = user_info.get("nickname") or f"Vendedor-{meli_user_id}"

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    # Verificar si la cuenta ya existía para actualizarla o crearla
    stmt = select(MeliAccount).where(MeliAccount.meli_user_id == meli_user_id)
    account = (await session.execute(stmt)).scalar_one_or_none()

    if account:
        if account.company_id != ctx.company_id:
            raise PermissionDeniedException("Esta cuenta de Mercado Libre ya está vinculada a otra empresa.")
        # Reactivar y actualizar tokens
        account.access_token_enc = encrypt_token(access_token)
        account.refresh_token_enc = encrypt_token(refresh_token)
        account.token_expires_at = expires_at
        account.nickname = nickname
        account.is_active = True
    else:
        account = MeliAccount(
            company_id=ctx.company_id,
            meli_user_id=meli_user_id,
            nickname=nickname,
            site_id="MLM",
            access_token_enc=encrypt_token(access_token),
            refresh_token_enc=encrypt_token(refresh_token),
            token_expires_at=expires_at,
            is_active=True,
        )
        session.add(account)

    await session.flush()

    await record_audit_event(
        session=session,
        company_id=account.company_id,
        action="OAUTH_LINK_MELI_ACCOUNT",
        entity_name="MeliAccount",
        entity_id=str(account.id),
        user_id=ctx.user.id,
        changes={"nickname": nickname, "meli_user_id": meli_user_id},
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
    return await _get_account_and_verify_ownership(session, account_id, ctx.company_id)


@router.post("/{account_id}/test-connection", response_model=MeliConnectionTestResponse)
async def test_meli_account_connection(
    account_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.MELI_ACCOUNTS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Ejecuta un diagnóstico en vivo sobre la conexión con Mercado Libre México.
    Consulta /users/me, mide la latencia de respuesta y valida la vigencia del token.
    """
    account = await _get_account_and_verify_ownership(session, account_id, ctx.company_id)
    connector = MercadoLibreConnector(account=account, db_session=session)
    return await connector.test_connection()


@router.post("/{account_id}/refresh-token", response_model=MeliAccountResponse)
async def refresh_account_token_manually(
    account_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.MELI_ACCOUNTS, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> MeliAccount:
    """Fuerza la renovación manual del Access Token de Mercado Libre usando el Refresh Token."""
    account = await _get_account_and_verify_ownership(session, account_id, ctx.company_id)
    connector = MercadoLibreConnector(account=account, db_session=session)
    await connector._auto_refresh_hook()
    await session.refresh(account)
    return account


@router.post("/{account_id}/disconnect", response_model=MeliAccountResponse)
async def disconnect_meli_account(
    account_id: uuid.UUID,
    revoke_remote: bool = Query(False, description="Si es True, revoca la autorización de la app en MeLi"),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.MELI_ACCOUNTS, ActionEnum.DELETE)),
    session: AsyncSession = Depends(get_db),
) -> MeliAccount:
    """Desconecta una cuenta de Mercado Libre marcándola como inactiva."""
    account = await _get_account_and_verify_ownership(session, account_id, ctx.company_id)
    connector = MercadoLibreConnector(account=account, db_session=session)
    await connector.disconnect_account(revoke_remote=revoke_remote)
    await session.refresh(account)
    return account


@router.post("/{account_id}/reconnect", response_model=MeliAccountResponse)
async def reconnect_meli_account(
    account_id: uuid.UUID,
    payload: MeliAccountReconnectRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.MELI_ACCOUNTS, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> MeliAccount:
    """Reconecta y reactiva una cuenta de Mercado Libre asignándole nuevos tokens válidos."""
    account = await _get_account_and_verify_ownership(session, account_id, ctx.company_id)
    connector = MercadoLibreConnector(account=account, db_session=session)
    await connector.reconnect_account(
        access_token_plain=payload.access_token_plain,
        refresh_token_plain=payload.refresh_token_plain,
        expires_in_seconds=payload.expires_in_seconds,
    )
    await session.refresh(account)
    return account


# ==============================================================================
# ENDPOINTS DE INTEGRACIÓN DEPOSITADOS MEDIANTE MERCADOLIBRECONNECTOR
# ==============================================================================


@router.get("/{account_id}/items", response_model=dict[str, Any])
async def search_account_items(
    account_id: uuid.UUID,
    status_filter: str | None = Query(None, description="active, paused, closed"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=50),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.MELI_ACCOUNTS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Consulta publicaciones del vendedor mediante el conector oficial."""
    account = await _get_account_and_verify_ownership(session, account_id, ctx.company_id)
    connector = MercadoLibreConnector(account=account, db_session=session)
    await connector.check_and_proactively_refresh()
    return await connector.items.search_items(
        user_id=account.meli_user_id, status=status_filter, offset=offset, limit=limit
    )


@router.get("/{account_id}/items/{item_id}", response_model=dict[str, Any])
async def get_item_detail(
    account_id: uuid.UUID,
    item_id: str,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.MELI_ACCOUNTS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Consulta detalle oficial de una publicación en Mercado Libre."""
    account = await _get_account_and_verify_ownership(session, account_id, ctx.company_id)
    connector = MercadoLibreConnector(account=account, db_session=session)
    await connector.check_and_proactively_refresh()
    return await connector.items.get_item(item_id=item_id)


@router.put("/{account_id}/items/{item_id}/stock", response_model=dict[str, Any])
async def update_item_stock(
    account_id: uuid.UUID,
    item_id: str,
    payload: MeliUpdateStockRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.MELI_ACCOUNTS, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Actualiza existencias de una publicación o variante directamente en Mercado Libre."""
    account = await _get_account_and_verify_ownership(session, account_id, ctx.company_id)
    connector = MercadoLibreConnector(account=account, db_session=session)
    await connector.check_and_proactively_refresh()

    if payload.variation_id:
        return await connector.inventory.update_variation_stock(
            item_id=item_id,
            variation_id=payload.variation_id,
            available_quantity=payload.available_quantity,
        )
    return await connector.inventory.update_stock(
        item_id=item_id, available_quantity=payload.available_quantity
    )


@router.put("/{account_id}/items/{item_id}/price", response_model=dict[str, Any])
async def update_item_price(
    account_id: uuid.UUID,
    item_id: str,
    payload: MeliUpdatePriceRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.MELI_ACCOUNTS, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Actualiza el precio de venta de una publicación o variante en Mercado Libre México."""
    account = await _get_account_and_verify_ownership(session, account_id, ctx.company_id)
    connector = MercadoLibreConnector(account=account, db_session=session)
    await connector.check_and_proactively_refresh()

    if payload.variation_id:
        return await connector.prices.update_variation_price(
            item_id=item_id,
            variation_id=payload.variation_id,
            new_price=payload.price,
        )
    return await connector.prices.update_price(item_id=item_id, new_price=payload.price)


@router.get("/{account_id}/orders", response_model=dict[str, Any])
async def search_account_orders(
    account_id: uuid.UUID,
    order_status: str | None = Query(None, description="paid, cancelled, confirmed"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=50),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.MELI_ACCOUNTS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Consulta órdenes de venta en Mercado Libre mediante el conector."""
    account = await _get_account_and_verify_ownership(session, account_id, ctx.company_id)
    connector = MercadoLibreConnector(account=account, db_session=session)
    await connector.check_and_proactively_refresh()
    return await connector.orders.search_orders(
        seller_id=account.meli_user_id, order_status=order_status, offset=offset, limit=limit
    )


@router.get("/{account_id}/shipments/{shipment_id}", response_model=dict[str, Any])
async def get_shipment_detail(
    account_id: uuid.UUID,
    shipment_id: str,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.MELI_ACCOUNTS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Consulta estado y rastreo oficial de un envío de Mercado Envíos."""
    account = await _get_account_and_verify_ownership(session, account_id, ctx.company_id)
    connector = MercadoLibreConnector(account=account, db_session=session)
    await connector.check_and_proactively_refresh()
    return await connector.shipments.get_shipment(shipment_id=shipment_id)


@router.get("/{account_id}/promotions", response_model=list[dict[str, Any]])
async def get_seller_promotions(
    account_id: uuid.UUID,
    promotion_type: str | None = Query(None, description="DEAL, LIGHTNING, etc."),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.MELI_ACCOUNTS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Consulta campañas comerciales y promociones oficiales disponibles para el vendedor."""
    account = await _get_account_and_verify_ownership(session, account_id, ctx.company_id)
    connector = MercadoLibreConnector(account=account, db_session=session)
    await connector.check_and_proactively_refresh()
    return await connector.promotions.get_seller_promotions(
        user_id=account.meli_user_id, promotion_type=promotion_type
    )

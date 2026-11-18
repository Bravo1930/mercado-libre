"""API REST para Ventas, Pedidos y Análisis de Rentabilidad Neta."""

from datetime import datetime
import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.auth_context import CompanyContext, require_company_permission
from src.core.database import get_db
from src.core.exceptions import EntityNotFoundException
from src.core.pagination import Page, PaginationParams, paginate_query
from src.core.permissions import ActionEnum, ModuleEnum
from src.models.meli_account import MeliAccount
from src.models.order import Order
from src.schemas.order import OrderResponse

router = APIRouter(prefix="/orders", tags=["Ventas & Pedidos"])


@router.get("", response_model=Page[OrderResponse])
async def list_orders(
    meli_account_id: uuid.UUID | None = Query(None, description="Filtrar por cuenta MeLi"),
    status: str | None = Query(None, description="Filtrar por estado (paid, cancelled, etc.)"),
    date_from: datetime | None = Query(None, description="Fecha de creación desde"),
    date_to: datetime | None = Query(None, description="Fecha de creación hasta"),
    params: PaginationParams = Depends(),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.ORDERS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> Page[Order]:
    """
    Lista pedidos y ventas con desglose financiero, pagos y guías asociadas.
    Aislado estrictamente a las cuentas de Mercado Libre pertenecientes a la empresa activa.
    """
    stmt = (
        select(Order)
        .join(MeliAccount, Order.meli_account_id == MeliAccount.id)
        .where(MeliAccount.company_id == ctx.company_id)
        .options(
            selectinload(Order.items),
            selectinload(Order.payments),
            selectinload(Order.shipments),
            selectinload(Order.profitability),
        )
    )
    if meli_account_id:
        stmt = stmt.where(Order.meli_account_id == meli_account_id)
    if status:
        stmt = stmt.where(Order.status == status)
    if date_from:
        stmt = stmt.where(Order.date_created_meli >= date_from)
    if date_to:
        stmt = stmt.where(Order.date_created_meli <= date_to)

    stmt = stmt.order_by(Order.date_created_meli.desc())
    items, total = await paginate_query(stmt, session, params)
    return Page.create(items, total, params)


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.ORDERS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> Order:
    """
    Obtiene el detalle completo de una orden por su UUID interno.
    Garantiza aislamiento estricto validando que pertenezca a la empresa del solicitante.
    """
    stmt = (
        select(Order)
        .join(MeliAccount, Order.meli_account_id == MeliAccount.id)
        .where(Order.id == order_id, MeliAccount.company_id == ctx.company_id)
        .options(
            selectinload(Order.items),
            selectinload(Order.payments),
            selectinload(Order.shipments),
            selectinload(Order.profitability),
        )
    )
    result = await session.execute(stmt)
    order = result.scalar_one_or_none()
    if not order:
        raise EntityNotFoundException("Orden de Venta", "id", str(order_id))
    return order

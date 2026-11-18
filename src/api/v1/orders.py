"""API REST para el Centro de Ventas, Pedidos, Trazabilidad, Cancelaciones, Devoluciones y Reportes."""

from datetime import datetime, timezone
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.auth_context import CompanyContext, require_company_permission
from src.core.database import get_db
from src.core.exceptions import EntityNotFoundException
from src.core.pagination import Page, PaginationParams, paginate_query
from src.core.permissions import ActionEnum, ModuleEnum
from src.models.meli_account import MeliAccount
from src.models.order import Order, OrderClaim, OrderItem
from src.schemas.order import (
    OrderCancelRequest,
    OrderClaimCreateRequest,
    OrderClaimResponse,
    OrderComparisonResponse,
    OrderResponse,
    OrderReturnRequest,
    SalesReportResponse,
)
from src.services.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["Ventas & Pedidos"])
order_service = OrderService()


@router.get("/reports/sales", response_model=SalesReportResponse)
async def get_sales_report(
    period: Literal["daily", "weekly", "monthly"] = Query("daily", description="Tipo de reporte comercial"),
    reference_date: datetime | None = Query(None, description="Fecha de referencia (por defecto hoy)"),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.ORDERS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> SalesReportResponse:
    """
    Genera reportes de ventas consolidados: diarios, semanales y mensuales.
    REGLA ESTRICTA: Excluye de forma terminante las órdenes canceladas de los ingresos y utilidades.
    """
    ref_dt = reference_date or datetime.now(timezone.utc)
    return await order_service.generate_sales_report(
        session=session,
        company_id=ctx.company_id,
        report_type=period,
        reference_date=ref_dt,
    )


@router.get("", response_model=Page[OrderResponse])
async def list_orders(
    search: str | None = Query(None, description="Buscar por número de orden, ID MeLi, comprador o SKU"),
    meli_account_id: uuid.UUID | None = Query(None, description="Filtrar por cuenta MeLi"),
    status: str | None = Query(None, description="Filtrar por estado general (paid, confirmed, cancelled, etc.)"),
    payment_status: str | None = Query(None, description="Filtrar por estado del pago (approved, pending, refunded)"),
    shipment_status: str | None = Query(None, description="Filtrar por estado logístico (ready_to_ship, shipped, delivered)"),
    claim_status: str | None = Query(None, description="Filtrar por estatus de reclamo (none, open, closed)"),
    return_status: str | None = Query(None, description="Filtrar por estatus de devolución (none, received_good, received_damaged)"),
    date_from: datetime | None = Query(None, description="Fecha de creación desde"),
    date_to: datetime | None = Query(None, description="Fecha de creación hasta"),
    params: PaginationParams = Depends(),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.ORDERS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> Page[Order]:
    """
    Lista pedidos y ventas con desglose financiero, comprador, partidas, pagos, envíos y rentabilidad.
    Aislado estrictamente a las cuentas de Mercado Libre pertenecientes a la empresa activa.
    """
    stmt = (
        select(Order)
        .join(MeliAccount, Order.meli_account_id == MeliAccount.id)
        .where(MeliAccount.company_id == ctx.company_id)
        .options(
            selectinload(Order.meli_account),
            selectinload(Order.items),
            selectinload(Order.payments),
            selectinload(Order.shipments),
            selectinload(Order.timelines),
            selectinload(Order.claims),
            selectinload(Order.profitability),
        )
    )

    if search:
        search_clean = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Order.order_number.ilike(search_clean),
                Order.buyer_nickname.ilike(search_clean),
                Order.buyer_name.ilike(search_clean),
                Order.id.in_(
                    select(OrderItem.order_id).where(
                        or_(
                            OrderItem.seller_sku.ilike(search_clean),
                            OrderItem.title.ilike(search_clean),
                            OrderItem.meli_item_id.ilike(search_clean),
                        )
                    )
                ),
            )
        )

    if meli_account_id:
        stmt = stmt.where(Order.meli_account_id == meli_account_id)
    if status:
        stmt = stmt.where(Order.status == status)
    if payment_status:
        stmt = stmt.where(Order.payment_status == payment_status)
    if shipment_status:
        stmt = stmt.where(Order.shipment_status == shipment_status)
    if claim_status:
        stmt = stmt.where(Order.claim_status == claim_status)
    if return_status:
        stmt = stmt.where(Order.return_status == return_status)
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
    Obtiene el detalle exhaustivo de una orden por su UUID interno.
    Incluye comprador, partidas con SKU, pagos, logística, rentabilidad SAT y línea de tiempo.
    """
    stmt = (
        select(Order)
        .join(MeliAccount, Order.meli_account_id == MeliAccount.id)
        .where(Order.id == order_id, MeliAccount.company_id == ctx.company_id)
        .options(
            selectinload(Order.meli_account),
            selectinload(Order.items),
            selectinload(Order.payments),
            selectinload(Order.shipments),
            selectinload(Order.timelines),
            selectinload(Order.claims),
            selectinload(Order.profitability),
        )
    )
    result = await session.execute(stmt)
    order = result.scalar_one_or_none()
    if not order:
        raise EntityNotFoundException("Orden de Venta", "id", str(order_id))
    return order


@router.get("/{order_id}/compare", response_model=OrderComparisonResponse)
async def compare_order(
    order_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.ORDERS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """
    Compara en tiempo real los datos de la orden en Mercado Libre vs la información interna en el ERP.
    Detecta diferencias de precios, comisiones, SKU mapeados y estado de entrega.
    """
    res = await order_service.compare_order_with_meli(session, order_id, ctx.company_id)
    await session.commit()
    return res


@router.post("/{order_id}/cancel", response_model=OrderResponse)
async def cancel_order_endpoint(
    order_id: uuid.UUID,
    payload: OrderCancelRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.ORDERS, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> Order:
    """
    Cancela una orden de venta y libera inmediatamente las existencias reservadas en almacén.
    Registra el motivo y responsable en la línea de tiempo.
    """
    order = await order_service.cancel_order(
        session=session,
        order_id=order_id,
        company_id=ctx.company_id,
        reason=payload.reason,
        responsible=payload.responsible,
    )
    await session.commit()
    return order


@router.post("/{order_id}/return", response_model=OrderResponse)
async def return_order_endpoint(
    order_id: uuid.UUID,
    payload: OrderReturnRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.ORDERS, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> Order:
    """
    Procesa la devolución física de mercancía:
    - Si la condición es 'good', reingresa al inventario disponible.
    - Si la condición es 'damaged', ingresa a inventario bloqueado / cuarentena.
    """
    order = await order_service.process_order_return(
        session=session,
        order_id=order_id,
        company_id=ctx.company_id,
        condition=payload.condition,
        warehouse_id=payload.warehouse_id,
        notes=payload.notes,
    )
    await session.commit()
    return order


@router.post("/{order_id}/claim", response_model=OrderClaimResponse)
async def create_order_claim_endpoint(
    order_id: uuid.UUID,
    payload: OrderClaimCreateRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.ORDERS, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> OrderClaim:
    """Registra una disputa o reclamo post-venta sobre la orden."""
    claim = await order_service.register_order_claim(
        session=session,
        order_id=order_id,
        company_id=ctx.company_id,
        meli_claim_id=payload.meli_claim_id,
        claim_type=payload.claim_type,
        disputed_amount=payload.disputed_amount,
        reason=payload.reason,
    )
    await session.commit()
    return claim

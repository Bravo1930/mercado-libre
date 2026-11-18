"""API REST para Proveedores y Órdenes de Compra."""

import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.audit import record_audit_event
from src.core.database import get_db
from src.core.pagination import Page, PaginationParams
from src.models.supplier import PurchaseOrder, PurchaseOrderItem, Supplier
from src.repositories.base import BaseRepository
from src.schemas.supplier import (
    PurchaseOrderCreate,
    PurchaseOrderResponse,
    SupplierCreate,
    SupplierResponse,
)

router = APIRouter(prefix="/suppliers", tags=["Proveedores & Compras"])
supplier_repo = BaseRepository[Supplier](Supplier)
po_repo = BaseRepository[PurchaseOrder](PurchaseOrder)


@router.post("", response_model=SupplierResponse, status_code=status.HTTP_201_CREATED)
async def create_supplier(
    payload: SupplierCreate,
    session: AsyncSession = Depends(get_db),
) -> Supplier:
    """Registra un nuevo proveedor de mercancía."""
    return await supplier_repo.create(session, payload.model_dump())


@router.get("", response_model=Page[SupplierResponse])
async def list_suppliers(
    company_id: uuid.UUID = Query(..., description="ID de la empresa"),
    params: PaginationParams = Depends(),
    session: AsyncSession = Depends(get_db),
) -> Page[Supplier]:
    """Lista proveedores registrados de una empresa."""
    return await supplier_repo.get_paginated(session, params, Supplier.company_id == company_id)


@router.post("/purchase-orders", response_model=PurchaseOrderResponse, status_code=status.HTTP_201_CREATED)
async def create_purchase_order(
    payload: PurchaseOrderCreate,
    session: AsyncSession = Depends(get_db),
) -> PurchaseOrder:
    """Crea una orden de compra con sus partidas de forma atómica."""
    po_data = payload.model_dump()
    items_data = po_data.pop("items")

    total_amount = sum(item["quantity_ordered"] * item["unit_cost"] for item in items_data)
    po_data["total_amount"] = total_amount

    po = PurchaseOrder(**po_data)
    session.add(po)
    await session.flush()

    for item_in in items_data:
        item_obj = PurchaseOrderItem(purchase_order_id=po.id, **item_in)
        session.add(item_obj)

    await session.flush()

    await record_audit_event(
        session=session,
        company_id=po.company_id,
        action="CREATE_PURCHASE_ORDER",
        entity_name="PurchaseOrder",
        entity_id=str(po.id),
        changes={"po_number": po.po_number, "total_amount": float(total_amount)},
    )
    return po

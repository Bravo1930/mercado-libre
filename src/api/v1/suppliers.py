"""API REST para Proveedores y Órdenes de Compra."""

import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.audit import record_audit_event
from src.core.auth_context import CompanyContext, require_company_permission
from src.core.database import get_db
from src.core.exceptions import PermissionDeniedException
from src.core.pagination import Page, PaginationParams
from src.core.permissions import ActionEnum, ModuleEnum
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
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SUPPLIERS, ActionEnum.CREATE)),
    session: AsyncSession = Depends(get_db),
) -> Supplier:
    """Registra un nuevo proveedor de mercancía para la empresa activa."""
    if payload.company_id != ctx.company_id:
        raise PermissionDeniedException("No se puede registrar un proveedor para una empresa distinta a la activa.")

    supplier = await supplier_repo.create(session, payload.model_dump())
    await record_audit_event(
        session=session,
        action="CREATE_SUPPLIER",
        entity_name="Supplier",
        entity_id=str(supplier.id),
        company_id=ctx.company_id,
        user_id=ctx.user.id,
        changes={"name": supplier.name, "rfc": supplier.rfc},
    )
    return supplier


@router.get("", response_model=Page[SupplierResponse])
async def list_suppliers(
    params: PaginationParams = Depends(),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SUPPLIERS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> Page[Supplier]:
    """Lista proveedores registrados de la empresa activa."""
    return await supplier_repo.get_paginated(session, params, Supplier.company_id == ctx.company_id)


@router.post("/purchase-orders", response_model=PurchaseOrderResponse, status_code=status.HTTP_201_CREATED)
async def create_purchase_order(
    payload: PurchaseOrderCreate,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SUPPLIERS, ActionEnum.CREATE)),
    session: AsyncSession = Depends(get_db),
) -> PurchaseOrder:
    """Crea una orden de compra con sus partidas de forma atómica para la empresa activa."""
    if payload.company_id != ctx.company_id:
        raise PermissionDeniedException("No se puede generar una orden de compra para una empresa distinta a la activa.")

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
        action="CREATE_PURCHASE_ORDER",
        entity_name="PurchaseOrder",
        entity_id=str(po.id),
        company_id=ctx.company_id,
        user_id=ctx.user.id,
        changes={"order_number": po.order_number, "total_amount": float(total_amount)},
    )
    return po

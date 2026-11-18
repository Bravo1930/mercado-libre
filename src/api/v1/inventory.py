"""API REST para Inventarios y Movimientos de Stock (Kardex)."""

import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_context import CompanyContext, require_company_permission
from src.core.database import get_db
from src.core.exceptions import EntityNotFoundException, PermissionDeniedException
from src.core.pagination import Page, PaginationParams
from src.core.permissions import ActionEnum, ModuleEnum
from src.models.warehouse import Inventory, InventoryMovement, Warehouse
from src.repositories.base import BaseRepository
from src.repositories.inventory import InventoryRepository
from src.schemas.warehouse import (
    InventoryAdjustRequest,
    InventoryMovementResponse,
    InventoryResponse,
)

router = APIRouter(prefix="/inventory", tags=["Inventario & Kardex"])
inventory_repo = InventoryRepository()
movement_repo = BaseRepository[InventoryMovement](InventoryMovement)


@router.post("/adjust", response_model=InventoryResponse, status_code=status.HTTP_200_OK)
async def adjust_inventory(
    payload: InventoryAdjustRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.INVENTORY, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> Inventory:
    """
    Ajuste transaccional de existencias.
    Aplica bloqueo pesimista, valida saldo no negativo y verifica que el almacén pertenezca a la empresa.
    """
    # 1. Validar que el almacén pertenezca a la empresa activa
    stmt_wh = select(Warehouse).where(
        Warehouse.id == payload.warehouse_id,
        Warehouse.company_id == ctx.company_id,
    )
    warehouse = (await session.execute(stmt_wh)).scalar_one_or_none()
    if not warehouse:
        raise PermissionDeniedException("No se puede ajustar existencias en un almacén de otra empresa.")

    inventory, _ = await inventory_repo.adjust_stock(
        session=session,
        warehouse_id=payload.warehouse_id,
        variant_id=payload.variant_id,
        quantity_delta=payload.quantity_delta,
        movement_type=payload.movement_type,
        notes=payload.notes,
    )
    return inventory


@router.get("", response_model=Page[InventoryResponse])
async def list_inventories(
    warehouse_id: uuid.UUID | None = Query(None, description="Filtrar por almacén"),
    variant_id: uuid.UUID | None = Query(None, description="Filtrar por variante"),
    params: PaginationParams = Depends(),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.INVENTORY, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> Page[Inventory]:
    """Consulta existencias de inventario pertenecientes a los almacenes de la empresa."""
    # Subconsulta de almacenes de la empresa
    stmt_wh_ids = select(Warehouse.id).where(Warehouse.company_id == ctx.company_id)
    company_wh_ids = (await session.execute(stmt_wh_ids)).scalars().all()

    filters = [Inventory.warehouse_id.in_(company_wh_ids)]
    if warehouse_id:
        if warehouse_id not in company_wh_ids:
            raise PermissionDeniedException("El almacén especificado no pertenece a la empresa activa.")
        filters.append(Inventory.warehouse_id == warehouse_id)
    if variant_id:
        filters.append(Inventory.variant_id == variant_id)

    return await inventory_repo.get_paginated(session, params, *filters)


@router.get("/movements", response_model=Page[InventoryMovementResponse])
async def list_movements(
    inventory_id: uuid.UUID | None = Query(None, description="Filtrar por inventario"),
    movement_type: str | None = Query(None, description="Filtrar por tipo de movimiento"),
    params: PaginationParams = Depends(),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.INVENTORY, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> Page[InventoryMovement]:
    """Consulta el Kardex de movimientos de inventario de la empresa."""
    filters = []
    if inventory_id:
        filters.append(InventoryMovement.inventory_id == inventory_id)
    if movement_type:
        filters.append(InventoryMovement.movement_type == movement_type)

    return await movement_repo.get_paginated(session, params, *filters)

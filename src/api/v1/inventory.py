"""API REST para Inventarios y Movimientos de Stock (Kardex)."""

import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.pagination import Page, PaginationParams
from src.models.warehouse import Inventory, InventoryMovement
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
    session: AsyncSession = Depends(get_db),
) -> Inventory:
    """
    Ajuste transaccional de existencias.
    Aplica bloqueo pesimista, valida saldo no negativo y genera el movimiento en el Kardex.
    """
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
    session: AsyncSession = Depends(get_db),
) -> Page[Inventory]:
    """Consulta existencias de inventario con filtros por almacén o producto."""
    filters = []
    if warehouse_id:
        filters.append(Inventory.warehouse_id == warehouse_id)
    if variant_id:
        filters.append(Inventory.variant_id == variant_id)

    return await inventory_repo.get_paginated(session, params, *filters)


@router.get("/movements", response_model=Page[InventoryMovementResponse])
async def list_movements(
    inventory_id: uuid.UUID | None = Query(None, description="Filtrar por inventario"),
    movement_type: str | None = Query(None, description="Filtrar por tipo de movimiento"),
    params: PaginationParams = Depends(),
    session: AsyncSession = Depends(get_db),
) -> Page[InventoryMovement]:
    """Consulta la pista inmutable del Kardex de movimientos de inventario."""
    filters = []
    if inventory_id:
        filters.append(InventoryMovement.inventory_id == inventory_id)
    if movement_type:
        filters.append(InventoryMovement.movement_type == movement_type)

    return await movement_repo.get_paginated(session, params, *filters)

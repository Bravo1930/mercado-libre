"""API REST profesional para Inventarios, Kardex, Reservas, Bloqueos y Sincronización con Mercado Libre."""

import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_context import CompanyContext, require_company_permission
from src.core.database import get_db
from src.core.exceptions import PermissionDeniedException
from src.core.pagination import Page, PaginationParams
from src.core.permissions import ActionEnum, ModuleEnum
from src.models.product import ProductVariant
from src.models.warehouse import Inventory, InventoryMovement, Warehouse
from src.repositories.base import BaseRepository
from src.repositories.inventory import InventoryRepository
from src.schemas.warehouse import (
    InventoryAdjustRequest,
    InventoryAlertResponse,
    InventoryBlockRequest,
    InventoryDispatchOrderRequest,
    InventoryLocationUpdateRequest,
    InventoryMovementResponse,
    InventoryOrderReturnRequest,
    InventoryReservationRequest,
    InventoryResponse,
    InventoryUnblockRequest,
    MeliSyncStockResponse,
)
from src.services.inventory_service import InventoryService

router = APIRouter(prefix="/inventory", tags=["Inventario & Kardex"])
inventory_service = InventoryService()
inventory_repo = InventoryRepository()
movement_repo = BaseRepository[InventoryMovement](InventoryMovement)


async def _verify_warehouse_belongs_to_company(
    session: AsyncSession, warehouse_id: uuid.UUID, company_id: uuid.UUID
) -> Warehouse:
    """Verifica estrictamente que el almacén pertenezca a la empresa activa."""
    stmt = select(Warehouse).where(
        Warehouse.id == warehouse_id,
        Warehouse.company_id == company_id,
    )
    warehouse = (await session.execute(stmt)).scalar_one_or_none()
    if not warehouse:
        raise PermissionDeniedException("El almacén especificado no pertenece a la empresa activa.")
    return warehouse


@router.post("/adjust", response_model=InventoryResponse, status_code=status.HTTP_200_OK)
async def adjust_inventory(
    payload: InventoryAdjustRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.INVENTORY, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> Inventory:
    """
    Ajuste transaccional de existencias (entradas, salidas, ajustes de merma o devoluciones).
    Aplica bloqueo pesimista y la fórmula: Stock disponible = físico - reservado - bloqueado.
    """
    await _verify_warehouse_belongs_to_company(session, payload.warehouse_id, ctx.company_id)

    inventory, _ = await inventory_service.adjust_stock(
        session=session,
        warehouse_id=payload.warehouse_id,
        variant_id=payload.variant_id,
        quantity_delta=payload.quantity_delta,
        movement_type=payload.movement_type,
        reference_id=payload.reference_id,
        reference_type=payload.reference_type or "manual",
        condition=payload.condition or "good",
        user_id=ctx.user.id,
        notes=payload.notes,
    )
    return inventory


@router.post("/block", response_model=InventoryResponse, status_code=status.HTTP_200_OK)
async def block_stock(
    payload: InventoryBlockRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.INVENTORY, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> Inventory:
    """Bloquea unidades por control de calidad o cuarentena, trasladándolas de disponible a bloqueado."""
    await _verify_warehouse_belongs_to_company(session, payload.warehouse_id, ctx.company_id)

    inventory, _ = await inventory_service.block_stock(
        session=session,
        warehouse_id=payload.warehouse_id,
        variant_id=payload.variant_id,
        quantity=payload.quantity,
        reason=payload.reason,
        user_id=ctx.user.id,
        notes=payload.notes,
    )
    return inventory


@router.post("/unblock", response_model=InventoryResponse, status_code=status.HTTP_200_OK)
async def unblock_stock(
    payload: InventoryUnblockRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.INVENTORY, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> Inventory:
    """Desbloquea unidades aprobadas de cuarentena y las reintegra al stock disponible para venta."""
    await _verify_warehouse_belongs_to_company(session, payload.warehouse_id, ctx.company_id)

    inventory, _ = await inventory_service.unblock_stock(
        session=session,
        warehouse_id=payload.warehouse_id,
        variant_id=payload.variant_id,
        quantity=payload.quantity,
        reason=payload.reason,
        user_id=ctx.user.id,
        notes=payload.notes,
    )
    return inventory


@router.post("/location", response_model=InventoryResponse, status_code=status.HTTP_200_OK)
async def update_location_and_limits(
    payload: InventoryLocationUpdateRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.INVENTORY, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> Inventory:
    """Actualiza la ubicación física en almacén (rack/gaveta) y umbrales mínimo y máximo de stock."""
    await _verify_warehouse_belongs_to_company(session, payload.warehouse_id, ctx.company_id)

    return await inventory_service.update_location_and_limits(
        session=session,
        warehouse_id=payload.warehouse_id,
        variant_id=payload.variant_id,
        location_bin=payload.location_bin,
        safety_stock=payload.safety_stock,
        max_stock=payload.max_stock,
    )


@router.post("/reserve", response_model=InventoryResponse, status_code=status.HTTP_200_OK)
async def reserve_stock_order(
    payload: InventoryReservationRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.INVENTORY, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> Inventory:
    """Reserva unidades ante una nueva orden pagada o confirmada. Operación idempotente."""
    await _verify_warehouse_belongs_to_company(session, payload.warehouse_id, ctx.company_id)

    inventory, _ = await inventory_service.reserve_stock_for_order(
        session=session,
        warehouse_id=payload.warehouse_id,
        variant_id=payload.variant_id,
        quantity=payload.quantity,
        order_id=payload.order_id,
        user_id=ctx.user.id,
        notes=payload.notes,
    )
    return inventory


@router.post("/release-reservation", response_model=InventoryResponse, status_code=status.HTTP_200_OK)
async def release_stock_reservation(
    payload: InventoryReservationRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.INVENTORY, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> Inventory:
    """Libera la reserva cuando un pedido es cancelado antes de despacharse."""
    await _verify_warehouse_belongs_to_company(session, payload.warehouse_id, ctx.company_id)

    inventory, _ = await inventory_service.release_order_reservation(
        session=session,
        warehouse_id=payload.warehouse_id,
        variant_id=payload.variant_id,
        quantity=payload.quantity,
        order_id=payload.order_id,
        user_id=ctx.user.id,
        notes=payload.notes,
    )
    return inventory


@router.post("/dispatch-order", response_model=InventoryResponse, status_code=status.HTTP_200_OK)
async def dispatch_order(
    payload: InventoryDispatchOrderRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.INVENTORY, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> Inventory:
    """
    Despacha un pedido de venta descontando stock físico y consumiendo la reserva.
    PROTECCIÓN CONTRA DOBLE DESCUENTO: Idempotente por reference_id y reference_type='order'.
    """
    await _verify_warehouse_belongs_to_company(session, payload.warehouse_id, ctx.company_id)

    inventory, _ = await inventory_service.commit_order_dispatch(
        session=session,
        warehouse_id=payload.warehouse_id,
        variant_id=payload.variant_id,
        quantity=payload.quantity,
        order_id=payload.order_id,
        user_id=ctx.user.id,
        notes=payload.notes,
    )
    return inventory


@router.post("/return-order", response_model=InventoryResponse, status_code=status.HTTP_200_OK)
async def return_order(
    payload: InventoryOrderReturnRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.INVENTORY, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> Inventory:
    """
    Procesa la devolución de una orden considerando su condición real:
    - 'good': reingresa a físico y queda disponible para reventa.
    - 'damaged': reingresa a físico y queda bloqueado/merma para inspección/baja.
    """
    await _verify_warehouse_belongs_to_company(session, payload.warehouse_id, ctx.company_id)

    inventory, _ = await inventory_service.process_order_return(
        session=session,
        warehouse_id=payload.warehouse_id,
        variant_id=payload.variant_id,
        quantity=payload.quantity,
        order_id=payload.order_id,
        condition=payload.condition,
        user_id=ctx.user.id,
        notes=payload.notes,
    )
    return inventory


@router.get("", response_model=Page[InventoryResponse])
async def list_inventories(
    warehouse_id: uuid.UUID | None = Query(None, description="Filtrar por almacén"),
    variant_id: uuid.UUID | None = Query(None, description="Filtrar por variante"),
    sku: str | None = Query(None, description="Filtrar por SKU exacto o parcial"),
    params: PaginationParams = Depends(),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.INVENTORY, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> Page[Inventory]:
    """Consulta existencias de inventario pertenecientes a los almacenes de la empresa activa."""
    stmt_wh_ids = select(Warehouse.id).where(Warehouse.company_id == ctx.company_id)
    company_wh_ids = (await session.execute(stmt_wh_ids)).scalars().all()

    filters = [Inventory.warehouse_id.in_(company_wh_ids)]
    if warehouse_id:
        if warehouse_id not in company_wh_ids:
            raise PermissionDeniedException("El almacén especificado no pertenece a la empresa activa.")
        filters.append(Inventory.warehouse_id == warehouse_id)
    if variant_id:
        filters.append(Inventory.variant_id == variant_id)
    if sku:
        stmt_var_ids = select(ProductVariant.id).where(ProductVariant.sku.ilike(f"%{sku.strip()}%"))
        var_ids = (await session.execute(stmt_var_ids)).scalars().all()
        filters.append(Inventory.variant_id.in_(var_ids))

    return await inventory_repo.get_paginated(session, params, *filters)


@router.get("/alerts", response_model=list[InventoryAlertResponse])
async def get_inventory_alerts(
    warehouse_id: uuid.UUID | None = Query(None, description="Filtrar alertas por almacén específico"),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.INVENTORY, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Lista de alertas de agotados, bajo stock (safety_stock) y sobre-inventario de la empresa."""
    if warehouse_id:
        await _verify_warehouse_belongs_to_company(session, warehouse_id, ctx.company_id)

    return await inventory_service.get_inventory_alerts(
        session=session, company_id=ctx.company_id, warehouse_id=warehouse_id
    )


@router.get("/meli-sync-stock/{variant_id}", response_model=MeliSyncStockResponse)
async def get_meli_syncable_stock(
    variant_id: uuid.UUID,
    safety_buffer: int = Query(0, ge=0, description="Margen de seguridad preventivo"),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.INVENTORY, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """
    Calcula el stock disponible a sincronizar con Mercado Libre.
    Segrega estrictamente las bodegas de Mercado Envíos Full para evitar colisiones con el inventario administrado por MeLi.
    """
    return await inventory_service.get_syncable_stock_for_meli(
        session=session,
        company_id=ctx.company_id,
        variant_id=variant_id,
        safety_buffer=safety_buffer,
    )


@router.get("/movements", response_model=Page[InventoryMovementResponse])
async def list_movements(
    inventory_id: uuid.UUID | None = Query(None, description="Filtrar por inventario"),
    movement_type: str | None = Query(None, description="Filtrar por tipo de movimiento"),
    reference_id: str | None = Query(None, description="Filtrar por referencia (ID de orden, etc.)"),
    reference_type: str | None = Query(None, description="Filtrar por tipo de referencia"),
    params: PaginationParams = Depends(),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.INVENTORY, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> Page[InventoryMovement]:
    """Consulta el Kardex de movimientos de inventario de la empresa."""
    stmt_wh_ids = select(Warehouse.id).where(Warehouse.company_id == ctx.company_id)
    company_wh_ids = (await session.execute(stmt_wh_ids)).scalars().all()

    stmt_inv_ids = select(Inventory.id).where(Inventory.warehouse_id.in_(company_wh_ids))
    company_inv_ids = (await session.execute(stmt_inv_ids)).scalars().all()

    filters = [InventoryMovement.inventory_id.in_(company_inv_ids)]
    if inventory_id:
        if inventory_id not in company_inv_ids:
            raise PermissionDeniedException("El inventario especificado no pertenece a la empresa activa.")
        filters.append(InventoryMovement.inventory_id == inventory_id)
    if movement_type:
        filters.append(InventoryMovement.movement_type == movement_type)
    if reference_id:
        filters.append(InventoryMovement.reference_id == reference_id)
    if reference_type:
        filters.append(InventoryMovement.reference_type == reference_type)

    return await movement_repo.get_paginated(session, params, *filters)

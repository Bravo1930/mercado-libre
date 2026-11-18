"""API REST para Almacenes, Transferencias entre Bodegas y Conteos Físicos."""

import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.auth_context import CompanyContext, require_company_permission
from src.core.database import get_db
from src.core.exceptions import EntityNotFoundException, PermissionDeniedException
from src.core.pagination import Page, PaginationParams
from src.core.permissions import ActionEnum, ModuleEnum
from src.models.warehouse import PhysicalCount, StockTransfer, Warehouse
from src.repositories.base import BaseRepository
from src.schemas.warehouse import (
    PhysicalCountCreate,
    PhysicalCountResponse,
    StockTransferCreate,
    StockTransferReceiveRequest,
    StockTransferResponse,
    WarehouseCreate,
    WarehouseResponse,
    WarehouseUpdate,
)
from src.services.inventory_service import InventoryService

router = APIRouter(prefix="/warehouses", tags=["Almacenes"])
warehouse_repo = BaseRepository[Warehouse](Warehouse)
transfer_repo = BaseRepository[StockTransfer](StockTransfer)
count_repo = BaseRepository[PhysicalCount](PhysicalCount)
inventory_service = InventoryService()


@router.post("", response_model=WarehouseResponse, status_code=status.HTTP_201_CREATED)
async def create_warehouse(
    payload: WarehouseCreate,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.INVENTORY, ActionEnum.CREATE)),
    session: AsyncSession = Depends(get_db),
) -> Warehouse:
    """Registra un nuevo almacén o centro logístico para la empresa activa."""
    if payload.company_id != ctx.company_id:
        raise PermissionDeniedException("No se puede crear un almacén para una empresa distinta a la activa.")

    # Si es tipo meli_fulfillment, forzar is_fulfillment = True
    data = payload.model_dump()
    if data.get("warehouse_type") == "meli_fulfillment":
        data["is_fulfillment"] = True

    return await warehouse_repo.create(session, data)


@router.get("", response_model=Page[WarehouseResponse])
async def list_warehouses(
    params: PaginationParams = Depends(),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.INVENTORY, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> Page[Warehouse]:
    """Lista los almacenes registrados de la empresa activa."""
    return await warehouse_repo.get_paginated(session, params, Warehouse.company_id == ctx.company_id)


@router.get("/{warehouse_id}", response_model=WarehouseResponse)
async def get_warehouse(
    warehouse_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.INVENTORY, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> Warehouse:
    """Obtiene los detalles de un almacén específico."""
    warehouse = await warehouse_repo.get_by_id(session, warehouse_id)
    if not warehouse or warehouse.company_id != ctx.company_id:
        raise EntityNotFoundException("Almacén", "id", str(warehouse_id))
    return warehouse


@router.patch("/{warehouse_id}", response_model=WarehouseResponse)
async def update_warehouse(
    warehouse_id: uuid.UUID,
    payload: WarehouseUpdate,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.INVENTORY, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> Warehouse:
    """Actualiza la configuración o estado de un almacén."""
    warehouse = await warehouse_repo.get_by_id(session, warehouse_id)
    if not warehouse or warehouse.company_id != ctx.company_id:
        raise EntityNotFoundException("Almacén", "id", str(warehouse_id))

    update_data = payload.model_dump(exclude_unset=True)
    if update_data.get("warehouse_type") == "meli_fulfillment":
        update_data["is_fulfillment"] = True

    return await warehouse_repo.update(session, warehouse, update_data)


# ==========================================
# TRANSFERENCIAS ENTRE ALMACENES
# ==========================================


@router.post("/transfers", response_model=StockTransferResponse, status_code=status.HTTP_201_CREATED)
async def create_stock_transfer(
    payload: StockTransferCreate,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.INVENTORY, ActionEnum.CREATE)),
    session: AsyncSession = Depends(get_db),
) -> StockTransfer:
    """Crea y despacha una transferencia de mercancía entre almacenes (e.g. Almacén Central -> MeLi Full)."""
    if payload.company_id != ctx.company_id:
        raise PermissionDeniedException("No se puede transferir mercancía para otra empresa.")

    transfer = await inventory_service.create_stock_transfer(
        session=session,
        company_id=ctx.company_id,
        source_warehouse_id=payload.source_warehouse_id,
        target_warehouse_id=payload.target_warehouse_id,
        items_payload=[item.model_dump() for item in payload.items],
        user_id=ctx.user.id,
        notes=payload.notes,
    )
    # Recargar con items
    stmt = select(StockTransfer).where(StockTransfer.id == transfer.id).options(selectinload(StockTransfer.items))
    return (await session.execute(stmt)).scalar_one()


@router.get("/transfers/list", response_model=Page[StockTransferResponse])
async def list_transfers(
    status_filter: str | None = Query(None, description="Filtrar por estatus: draft, in_transit, received, cancelled"),
    params: PaginationParams = Depends(),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.INVENTORY, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> Page[StockTransfer]:
    """Lista las transferencias de inventario de la empresa activa."""
    filters = [StockTransfer.company_id == ctx.company_id]
    if status_filter:
        filters.append(StockTransfer.status == status_filter)

    return await transfer_repo.get_paginated(
        session, params, *filters, options=[selectinload(StockTransfer.items)]
    )


@router.get("/transfers/{transfer_id}", response_model=StockTransferResponse)
async def get_transfer_detail(
    transfer_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.INVENTORY, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> StockTransfer:
    """Detalle completo de una transferencia y sus partidas."""
    stmt = (
        select(StockTransfer)
        .where(StockTransfer.id == transfer_id, StockTransfer.company_id == ctx.company_id)
        .options(selectinload(StockTransfer.items))
    )
    transfer = (await session.execute(stmt)).scalar_one_or_none()
    if not transfer:
        raise EntityNotFoundException("Transferencia", "id", str(transfer_id))
    return transfer


@router.post("/transfers/{transfer_id}/receive", response_model=StockTransferResponse)
async def receive_stock_transfer(
    transfer_id: uuid.UUID,
    payload: StockTransferReceiveRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.INVENTORY, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> StockTransfer:
    """Confirma la recepción física de mercancía en el almacén de destino ingresando el stock."""
    # Verificar pertenencia a la empresa
    stmt_check = select(StockTransfer).where(
        StockTransfer.id == transfer_id, StockTransfer.company_id == ctx.company_id
    )
    existing = (await session.execute(stmt_check)).scalar_one_or_none()
    if not existing:
        raise EntityNotFoundException("Transferencia", "id", str(transfer_id))

    transfer = await inventory_service.receive_stock_transfer(
        session=session,
        transfer_id=transfer_id,
        received_items=[item.model_dump() for item in payload.items],
        user_id=ctx.user.id,
        notes=payload.notes,
    )
    # Recargar con items
    stmt = select(StockTransfer).where(StockTransfer.id == transfer.id).options(selectinload(StockTransfer.items))
    return (await session.execute(stmt)).scalar_one()


# ==========================================
# CONTEOS FÍSICOS Y AUDITORÍA CÍCLICA
# ==========================================


@router.post("/counts", response_model=PhysicalCountResponse, status_code=status.HTTP_201_CREATED)
async def create_physical_count(
    payload: PhysicalCountCreate,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.INVENTORY, ActionEnum.CREATE)),
    session: AsyncSession = Depends(get_db),
) -> PhysicalCount:
    """Inicia una sesión de auditoría o conteo físico cíclico para un almacén."""
    if payload.company_id != ctx.company_id:
        raise PermissionDeniedException("No se puede crear un conteo físico para otra empresa.")

    count_obj = await inventory_service.create_physical_count(
        session=session,
        company_id=ctx.company_id,
        warehouse_id=payload.warehouse_id,
        items_payload=[item.model_dump() for item in payload.items],
        user_id=ctx.user.id,
        notes=payload.notes,
    )
    stmt = select(PhysicalCount).where(PhysicalCount.id == count_obj.id).options(selectinload(PhysicalCount.items))
    return (await session.execute(stmt)).scalar_one()


@router.get("/counts/list", response_model=Page[PhysicalCountResponse])
async def list_physical_counts(
    warehouse_id: uuid.UUID | None = Query(None, description="Filtrar por almacén"),
    status_filter: str | None = Query(None, description="draft, in_progress, applied, cancelled"),
    params: PaginationParams = Depends(),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.INVENTORY, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> Page[PhysicalCount]:
    """Lista las sesiones de conteo físico de la empresa activa."""
    filters = [PhysicalCount.company_id == ctx.company_id]
    if warehouse_id:
        filters.append(PhysicalCount.warehouse_id == warehouse_id)
    if status_filter:
        filters.append(PhysicalCount.status == status_filter)

    return await count_repo.get_paginated(
        session, params, *filters, options=[selectinload(PhysicalCount.items)]
    )


@router.get("/counts/{count_id}", response_model=PhysicalCountResponse)
async def get_physical_count_detail(
    count_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.INVENTORY, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> PhysicalCount:
    """Detalle completo de una sesión de conteo físico y sus discrepancias."""
    stmt = (
        select(PhysicalCount)
        .where(PhysicalCount.id == count_id, PhysicalCount.company_id == ctx.company_id)
        .options(selectinload(PhysicalCount.items))
    )
    count_obj = (await session.execute(stmt)).scalar_one_or_none()
    if not count_obj:
        raise EntityNotFoundException("Conteo Físico", "id", str(count_id))
    return count_obj


@router.post("/counts/{count_id}/apply", response_model=PhysicalCountResponse)
async def apply_physical_count(
    count_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.INVENTORY, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> PhysicalCount:
    """
    Aplica formalmente los ajustes por discrepancias físicas al Kardex (CYCLE_COUNT)
    y sincroniza el stock disponible del almacén.
    """
    stmt_check = select(PhysicalCount).where(
        PhysicalCount.id == count_id, PhysicalCount.company_id == ctx.company_id
    )
    existing = (await session.execute(stmt_check)).scalar_one_or_none()
    if not existing:
        raise EntityNotFoundException("Conteo Físico", "id", str(count_id))

    count_obj = await inventory_service.apply_physical_count(
        session=session, count_id=count_id, user_id=ctx.user.id
    )
    stmt = select(PhysicalCount).where(PhysicalCount.id == count_obj.id).options(selectinload(PhysicalCount.items))
    return (await session.execute(stmt)).scalar_one()

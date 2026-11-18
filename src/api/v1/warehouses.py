"""API REST para Almacenes y Ubicaciones de Inventario."""

import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_context import CompanyContext, require_company_permission
from src.core.database import get_db
from src.core.exceptions import PermissionDeniedException
from src.core.pagination import Page, PaginationParams
from src.core.permissions import ActionEnum, ModuleEnum
from src.models.warehouse import Warehouse
from src.repositories.base import BaseRepository
from src.schemas.warehouse import WarehouseCreate, WarehouseResponse

router = APIRouter(prefix="/warehouses", tags=["Almacenes"])
warehouse_repo = BaseRepository[Warehouse](Warehouse)


@router.post("", response_model=WarehouseResponse, status_code=status.HTTP_201_CREATED)
async def create_warehouse(
    payload: WarehouseCreate,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.INVENTORY, ActionEnum.MANAGE)),
    session: AsyncSession = Depends(get_db),
) -> Warehouse:
    """Registra un nuevo almacén o centro logístico para la empresa activa."""
    if payload.company_id != ctx.company_id:
        raise PermissionDeniedException("No se puede crear un almacén para una empresa distinta a la activa.")

    return await warehouse_repo.create(session, payload.model_dump())


@router.get("", response_model=Page[WarehouseResponse])
async def list_warehouses(
    params: PaginationParams = Depends(),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.INVENTORY, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> Page[Warehouse]:
    """Lista los almacenes registrados de la empresa activa."""
    return await warehouse_repo.get_paginated(session, params, Warehouse.company_id == ctx.company_id)

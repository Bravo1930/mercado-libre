"""API REST para Almacenes y Ubicaciones de Inventario."""

import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.pagination import Page, PaginationParams
from src.models.warehouse import Warehouse
from src.repositories.base import BaseRepository
from src.schemas.warehouse import WarehouseCreate, WarehouseResponse

router = APIRouter(prefix="/warehouses", tags=["Almacenes"])
warehouse_repo = BaseRepository[Warehouse](Warehouse)


@router.post("", response_model=WarehouseResponse, status_code=status.HTTP_201_CREATED)
async def create_warehouse(
    payload: WarehouseCreate,
    session: AsyncSession = Depends(get_db),
) -> Warehouse:
    """Registra un nuevo almacén o centro logístico (Interno, MeLi Full, etc.)."""
    return await warehouse_repo.create(session, payload.model_dump())


@router.get("", response_model=Page[WarehouseResponse])
async def list_warehouses(
    company_id: uuid.UUID = Query(..., description="ID de la empresa"),
    params: PaginationParams = Depends(),
    session: AsyncSession = Depends(get_db),
) -> Page[Warehouse]:
    """Lista los almacenes registrados de una empresa."""
    return await warehouse_repo.get_paginated(session, params, Warehouse.company_id == company_id)

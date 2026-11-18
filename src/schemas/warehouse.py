"""Esquemas para Almacenes, Inventarios y Movimientos de Stock (Kardex)."""

import uuid
from datetime import datetime
from pydantic import Field

from src.schemas.common import BaseSchema


class WarehouseCreate(BaseSchema):
    company_id: uuid.UUID
    name: str = Field(..., min_length=2, max_length=150)
    code: str = Field(..., min_length=2, max_length=50)
    warehouse_type: str = "internal"
    address: str | None = None


class WarehouseResponse(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    code: str
    warehouse_type: str
    address: str | None
    is_active: bool
    created_at: datetime


class InventoryAdjustRequest(BaseSchema):
    warehouse_id: uuid.UUID
    variant_id: uuid.UUID
    quantity_delta: int = Field(..., description="Cantidad a sumar (+) o restar (-)")
    movement_type: str = Field(default="ADJUSTMENT", description="ADJUSTMENT, PURCHASE_RECEIPT, DAMAGE, etc.")
    notes: str | None = None


class InventoryResponse(BaseSchema):
    id: uuid.UUID
    warehouse_id: uuid.UUID
    variant_id: uuid.UUID
    quantity_available: int
    quantity_reserved: int
    total_stock: int
    safety_stock: int
    updated_at: datetime


class InventoryMovementResponse(BaseSchema):
    id: uuid.UUID
    inventory_id: uuid.UUID
    movement_type: str
    quantity_delta: int
    quantity_before: int
    quantity_after: int
    reference_id: str | None
    notes: str | None
    created_at: datetime

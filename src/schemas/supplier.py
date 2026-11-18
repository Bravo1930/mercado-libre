"""Esquemas para Proveedores, Órdenes de Compra, Costos, Configuraciones y Auditoría."""

import uuid
from datetime import datetime
from pydantic import Field

from src.schemas.common import BaseSchema


# 1. Proveedores y Compras
class SupplierCreate(BaseSchema):
    company_id: uuid.UUID
    name: str = Field(..., min_length=2, max_length=200)
    rfc: str | None = None
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    lead_time_days: int = Field(default=7, ge=0)


class SupplierResponse(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    rfc: str | None
    contact_name: str | None
    email: str | None
    phone: str | None
    lead_time_days: int
    is_active: bool
    created_at: datetime


class PurchaseOrderItemCreate(BaseSchema):
    variant_id: uuid.UUID
    quantity_ordered: int = Field(..., gt=0)
    unit_cost: float = Field(..., ge=0.0)


class PurchaseOrderCreate(BaseSchema):
    company_id: uuid.UUID
    supplier_id: uuid.UUID
    po_number: str = Field(..., min_length=2, max_length=50)
    expected_delivery_date: datetime | None = None
    notes: str | None = None
    items: list[PurchaseOrderItemCreate] = Field(..., min_length=1)


class PurchaseOrderResponse(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    supplier_id: uuid.UUID
    po_number: str
    status: str
    total_amount: float
    expected_delivery_date: datetime | None
    notes: str | None
    created_at: datetime


# 2. Estructura de Costos
class CostStructureCreate(BaseSchema):
    company_id: uuid.UUID
    name: str = "Predeterminada"
    packaging_cost_fixed: float = 15.00
    labor_handling_cost: float = 10.00
    sat_iva_retention_rate: float = 0.0800
    sat_isr_retention_rate: float = 0.0100


class CostStructureResponse(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    packaging_cost_fixed: float
    labor_handling_cost: float
    sat_iva_retention_rate: float
    sat_isr_retention_rate: float
    is_default: bool


# 3. Configuraciones
class CompanySettingCreate(BaseSchema):
    company_id: uuid.UUID
    key: str = Field(..., min_length=2, max_length=100)
    value: str
    description: str | None = None


class CompanySettingResponse(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    key: str
    value: str
    description: str | None


# 4. Auditoría
class AuditLogResponse(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    user_id: uuid.UUID | None
    action: str
    entity_name: str
    entity_id: str
    changes_json: str | None
    ip_address: str | None
    created_at: datetime

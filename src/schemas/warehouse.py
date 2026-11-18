"""Esquemas Pydantic para Almacenes, Inventarios, Kardex, Transferencias, Conteos y Alertas."""

import uuid
from datetime import datetime
from pydantic import Field

from src.schemas.common import BaseSchema


class WarehouseCreate(BaseSchema):
    company_id: uuid.UUID
    name: str = Field(..., min_length=2, max_length=150)
    code: str = Field(..., min_length=2, max_length=50)
    warehouse_type: str = Field(
        default="internal",
        description="internal (propio), meli_fulfillment (Mercado Envíos Full), store, dropship",
    )
    is_fulfillment: bool = Field(
        default=False,
        description="Indica si este almacén es operado por Mercado Libre Full",
    )
    address: str | None = None


class WarehouseUpdate(BaseSchema):
    name: str | None = Field(None, min_length=2, max_length=150)
    warehouse_type: str | None = None
    is_fulfillment: bool | None = None
    address: str | None = None
    is_active: bool | None = None


class WarehouseResponse(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    code: str
    warehouse_type: str
    is_fulfillment: bool
    address: str | None
    is_active: bool
    created_at: datetime


class InventoryAdjustRequest(BaseSchema):
    warehouse_id: uuid.UUID
    variant_id: uuid.UUID
    quantity_delta: int = Field(..., description="Cantidad a sumar (+) o restar (-)")
    movement_type: str = Field(
        default="ADJUSTMENT",
        description="INBOUND, OUTBOUND, ADJUSTMENT, RETURN, DAMAGE, CYCLE_COUNT, etc.",
    )
    reference_id: str | None = Field(None, description="ID de referencia externa u orden")
    reference_type: str | None = Field(default="manual", description="order, purchase_order, transfer, count, manual")
    condition: str | None = Field(default="good", description="good (apto para venta) o damaged (merma/bloqueado)")
    notes: str | None = None


class InventoryBlockRequest(BaseSchema):
    warehouse_id: uuid.UUID
    variant_id: uuid.UUID
    quantity: int = Field(..., gt=0, description="Cantidad de unidades a bloquear (cuarentena o inspección)")
    reason: str = Field(..., min_length=3, description="Motivo del bloqueo (calidad, cuarentena, daño sospechoso)")
    notes: str | None = None


class InventoryUnblockRequest(BaseSchema):
    warehouse_id: uuid.UUID
    variant_id: uuid.UUID
    quantity: int = Field(..., gt=0, description="Cantidad de unidades a desbloquear y retornar a disponible")
    reason: str = Field(..., min_length=3, description="Motivo de desbloqueo (aprobado tras inspección)")
    notes: str | None = None


class InventoryReservationRequest(BaseSchema):
    warehouse_id: uuid.UUID
    variant_id: uuid.UUID
    quantity: int = Field(..., gt=0, description="Cantidad a reservar")
    order_id: str = Field(..., description="Identificador de la orden de venta")
    notes: str | None = None


class InventoryDispatchOrderRequest(BaseSchema):
    warehouse_id: uuid.UUID
    variant_id: uuid.UUID
    quantity: int = Field(..., gt=0, description="Cantidad despachada")
    order_id: str = Field(..., description="Identificador de la orden de venta despachada")
    notes: str | None = None


class InventoryOrderReturnRequest(BaseSchema):
    warehouse_id: uuid.UUID
    variant_id: uuid.UUID
    quantity: int = Field(..., gt=0, description="Cantidad devuelta")
    order_id: str = Field(..., description="Identificador de la orden de venta devuelta")
    condition: str = Field(default="good", description="'good' para regresar a disponible o 'damaged' para merma/bloqueado")
    notes: str | None = None


class InventoryLocationUpdateRequest(BaseSchema):
    warehouse_id: uuid.UUID
    variant_id: uuid.UUID
    location_bin: str | None = Field(None, max_length=50, description="Ubicación (Pasillo-Rack-Nivel-Bin)")
    safety_stock: int | None = Field(None, ge=0, description="Stock mínimo de seguridad")
    max_stock: int | None = Field(None, ge=0, description="Stock máximo de capacidad")


class InventoryResponse(BaseSchema):
    id: uuid.UUID
    warehouse_id: uuid.UUID
    variant_id: uuid.UUID
    quantity_on_hand: int = Field(description="Stock físico total presente en almacén")
    quantity_reserved: int = Field(description="Stock reservado por pedidos en proceso")
    quantity_blocked: int = Field(description="Stock bloqueado por cuarentena o daño")
    quantity_available: int = Field(description="Stock disponible calculado = físico - reservado - bloqueado")
    physical_stock: int
    reserved_stock: int
    blocked_stock: int
    available_stock: int
    total_stock: int
    safety_stock: int
    min_stock: int
    max_stock: int | None
    location_bin: str | None
    alert_status: str = Field(description="OK, LOW_STOCK, OUT_OF_STOCK, OVER_STOCK")
    updated_at: datetime


class InventoryMovementResponse(BaseSchema):
    id: uuid.UUID
    inventory_id: uuid.UUID
    movement_type: str
    quantity_delta: int
    quantity_before: int
    quantity_after: int
    reference_id: str | None
    reference_type: str | None
    notes: str | None
    created_at: datetime


class StockTransferItemCreate(BaseSchema):
    variant_id: uuid.UUID
    quantity_sent: int = Field(..., gt=0, description="Cantidad a transferir")


class StockTransferItemReceive(BaseSchema):
    variant_id: uuid.UUID
    quantity_received: int = Field(..., ge=0, description="Cantidad recibida físicamente en destino")


class StockTransferItemResponse(BaseSchema):
    id: uuid.UUID
    variant_id: uuid.UUID
    quantity_sent: int
    quantity_received: int


class StockTransferCreate(BaseSchema):
    company_id: uuid.UUID
    source_warehouse_id: uuid.UUID
    target_warehouse_id: uuid.UUID
    notes: str | None = None
    items: list[StockTransferItemCreate] = Field(..., min_length=1)


class StockTransferReceiveRequest(BaseSchema):
    items: list[StockTransferItemReceive] = Field(..., min_length=1)
    notes: str | None = None


class StockTransferResponse(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    source_warehouse_id: uuid.UUID
    target_warehouse_id: uuid.UUID
    transfer_number: str
    status: str
    notes: str | None
    shipped_at: datetime | None
    received_at: datetime | None
    created_at: datetime
    items: list[StockTransferItemResponse] = []


class PhysicalCountItemCreate(BaseSchema):
    variant_id: uuid.UUID
    counted_quantity: int = Field(..., ge=0, description="Cantidad física contada en sitio")
    location_bin: str | None = None


class PhysicalCountItemResponse(BaseSchema):
    id: uuid.UUID
    variant_id: uuid.UUID
    system_quantity: int
    counted_quantity: int
    difference: int
    location_bin: str | None


class PhysicalCountCreate(BaseSchema):
    company_id: uuid.UUID
    warehouse_id: uuid.UUID
    notes: str | None = None
    items: list[PhysicalCountItemCreate] = Field(..., min_length=1)


class PhysicalCountResponse(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    warehouse_id: uuid.UUID
    count_number: str
    status: str
    notes: str | None
    applied_at: datetime | None
    created_at: datetime
    items: list[PhysicalCountItemResponse] = []


class InventoryAlertResponse(BaseSchema):
    variant_id: uuid.UUID
    warehouse_id: uuid.UUID
    warehouse_name: str
    is_fulfillment: bool
    sku: str
    product_title: str
    quantity_on_hand: int
    quantity_reserved: int
    quantity_blocked: int
    quantity_available: int
    safety_stock: int
    max_stock: int | None
    location_bin: str | None
    alert_status: str


class MeliSyncStockResponse(BaseSchema):
    variant_id: uuid.UUID
    sku: str
    local_available_stock: int
    meli_full_stock: int
    syncable_stock_for_meli: int
    safety_buffer: int

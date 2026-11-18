"""Esquemas para Órdenes de Venta, Partidas, Pagos y Envíos."""

import uuid
from datetime import datetime
from pydantic import Field

from src.schemas.common import BaseSchema


class OrderItemResponse(BaseSchema):
    id: uuid.UUID
    meli_item_id: str
    meli_variation_id: str | None
    seller_sku: str | None
    title: str
    quantity: int
    unit_price: float
    sale_fee: float


class PaymentResponse(BaseSchema):
    id: uuid.UUID
    meli_payment_id: int
    status: str
    payment_type: str | None
    payment_method_id: str | None
    transaction_amount: float
    marketplace_fee: float
    date_approved: datetime | None


class ShipmentResponse(BaseSchema):
    id: uuid.UUID
    meli_shipment_id: int
    status: str
    substatus: str | None
    logistic_type: str
    tracking_number: str | None
    carrier_name: str | None
    shipping_cost_seller: float


class ProfitabilityAuditResponse(BaseSchema):
    gross_sale_price: float
    cogs_total: float
    meli_commission_fee: float
    shipping_cost_seller: float
    packaging_cost: float
    sat_iva_retention: float
    sat_isr_retention: float
    net_profit: float
    net_margin_pct: float


class OrderResponse(BaseSchema):
    id: uuid.UUID
    meli_account_id: uuid.UUID
    meli_order_id: int
    status: str
    buyer_nickname: str | None
    total_amount: float
    paid_amount: float
    currency_id: str
    date_created_meli: datetime
    items: list[OrderItemResponse] = Field(default_factory=list)
    payments: list[PaymentResponse] = Field(default_factory=list)
    shipments: list[ShipmentResponse] = Field(default_factory=list)
    profitability: ProfitabilityAuditResponse | None = None

"""Esquemas Pydantic v2 para el Centro de Ventas, Pedidos, Línea de Tiempo y Reportes."""

from datetime import datetime
from typing import Any, Literal
import uuid
from pydantic import Field

from src.schemas.common import BaseSchema


class OrderTimelineResponse(BaseSchema):
    id: uuid.UUID
    order_id: uuid.UUID
    event_type: str
    title: str
    description: str | None = None
    actor: str = "Sistema ERP"
    metadata_info: dict[str, Any] | None = None
    created_at: datetime


class OrderClaimResponse(BaseSchema):
    id: uuid.UUID
    order_id: uuid.UUID
    meli_claim_id: str
    claim_type: str
    stage: str
    status: str
    reason: str | None = None
    disputed_amount: float
    resolution: str | None = None
    opened_at: datetime
    closed_at: datetime | None = None


class OrderItemResponse(BaseSchema):
    id: uuid.UUID
    product_id: uuid.UUID | None = None
    variant_id: uuid.UUID | None = None
    meli_item_id: str
    meli_variation_id: str | None = None
    seller_sku: str | None = None
    variant_name: str | None = None
    title: str
    quantity: int
    unit_price: float
    discount_amount: float = 0.0
    sale_fee: float = 0.0
    cogs_unit: float = 0.0
    net_profit: float = 0.0


class PaymentResponse(BaseSchema):
    id: uuid.UUID
    meli_payment_id: int
    status: str
    status_detail: str | None = None
    payment_type: str | None = None
    payment_method_id: str | None = None
    transaction_amount: float
    marketplace_fee: float = 0.0
    date_approved: datetime | None = None


class ShipmentResponse(BaseSchema):
    id: uuid.UUID
    meli_shipment_id: int
    status: str
    substatus: str | None = None
    logistic_type: str
    tracking_number: str | None = None
    carrier_name: str | None = None
    shipping_cost_seller: float = 0.0
    label_local_path: str | None = None


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


class MeliAccountBriefResponse(BaseSchema):
    id: uuid.UUID
    meli_user_id: int
    nickname: str
    site_id: str


class OrderResponse(BaseSchema):
    id: uuid.UUID
    meli_account_id: uuid.UUID
    account: MeliAccountBriefResponse | None = None
    meli_order_id: int
    order_number: str | None = None
    status: str

    # Comprador
    buyer_id: int | None = None
    buyer_nickname: str | None = None
    buyer_name: str | None = None
    buyer_email: str | None = None
    buyer_phone: str | None = None
    buyer_document: str | None = None

    # Estados y Flujo
    payment_status: str
    shipment_status: str
    claim_status: str = "none"
    return_status: str = "none"

    # Desglose Financiero
    total_amount: float
    paid_amount: float
    discount_amount: float = 0.0
    currency_id: str = "MXN"
    date_created_meli: datetime

    # Comisiones, Costos y Ganancia Estimada
    meli_fee_amount: float = 0.0
    shipping_cost_seller: float = 0.0
    cogs_total: float = 0.0
    estimated_profit: float = 0.0
    net_margin_pct: float = 0.0

    # Cancelaciones
    cancel_reason: str | None = None
    cancel_responsible: str | None = None
    cancelled_at: datetime | None = None

    # Comparativa y Notas
    comparison_details: dict[str, Any] | None = None
    notes: str | None = None

    # Colecciones Relacionadas
    items: list[OrderItemResponse] = Field(default_factory=list)
    payments: list[PaymentResponse] = Field(default_factory=list)
    shipments: list[ShipmentResponse] = Field(default_factory=list)
    profitability: ProfitabilityAuditResponse | None = None
    timelines: list[OrderTimelineResponse] = Field(default_factory=list)
    claims: list[OrderClaimResponse] = Field(default_factory=list)


class OrderCancelRequest(BaseSchema):
    reason: str = Field(..., min_length=3, max_length=255, description="Motivo de la cancelación")
    responsible: Literal["buyer", "seller", "marketplace"] = Field(
        default="buyer", description="Parte responsable de la cancelación"
    )


class OrderReturnRequest(BaseSchema):
    condition: Literal["good", "damaged"] = Field(
        ..., description="Condición del producto retornado: good (disponible) o damaged (bloqueado/merma)"
    )
    warehouse_id: uuid.UUID | None = Field(
        None, description="Almacén de reingreso; si es None se toma el almacén predeterminado"
    )
    notes: str | None = Field(None, description="Observaciones del peritaje o motivo de devolución")


class OrderClaimCreateRequest(BaseSchema):
    meli_claim_id: str = Field(..., description="ID del reclamo en Mercado Libre")
    claim_type: str = Field(default="return", description="Tipo de reclamo (return, not_received, defective, etc.)")
    disputed_amount: float = Field(default=0.0, ge=0.0, description="Monto en disputa")
    reason: str | None = Field(None, description="Motivo o alegato del comprador")


class OrderComparisonResponse(BaseSchema):
    order_id: uuid.UUID
    meli_order_id: int
    is_matching: bool
    differences: list[str] = Field(default_factory=list)
    meli_data: dict[str, Any] = Field(default_factory=dict)
    internal_data: dict[str, Any] = Field(default_factory=dict)


class SalesReportMetricPeriod(BaseSchema):
    period: str  # e.g. "2026-11-18", "Semana 46", "Noviembre 2026"
    gross_sales: float = 0.0
    net_sales: float = 0.0
    total_orders: int = 0
    paid_orders: int = 0
    cancelled_orders: int = 0
    returned_orders: int = 0
    average_ticket: float = 0.0
    total_cogs: float = 0.0
    meli_commissions: float = 0.0
    shipping_costs: float = 0.0
    sat_tax_retentions: float = 0.0
    net_profit: float = 0.0
    profit_margin_pct: float = 0.0


class SalesReportResponse(BaseSchema):
    report_type: Literal["daily", "weekly", "monthly"]
    reference_date: datetime
    summary: SalesReportMetricPeriod
    breakdown: list[SalesReportMetricPeriod] = Field(default_factory=list)
    top_selling_skus: list[dict[str, Any]] = Field(default_factory=list)

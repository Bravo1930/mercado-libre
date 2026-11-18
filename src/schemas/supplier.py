"""
Esquemas Pydantic para el Módulo de Abastecimiento:
Proveedores, Catálogo de Suministro, Evaluación de Desempeño,
Órdenes de Compra con Autorización Previa, Recepciones Parciales,
Facturas de Compra, Gastos Asociados (Landed Cost) y Motor de Reposición.
"""

import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

from src.schemas.common import BaseSchema


# ===========================================================================
# 1. PROVEEDORES Y DATOS DE CONTACTO
# ===========================================================================

class SupplierCreate(BaseSchema):
    company_id: uuid.UUID
    code: str | None = Field(None, max_length=50)
    name: str = Field(..., min_length=2, max_length=200)
    commercial_name: str | None = Field(None, max_length=200)
    rfc: str | None = Field(None, max_length=13)
    contact_name: str | None = Field(None, max_length=100)
    email: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=30)
    website: str | None = Field(None, max_length=255)
    address_street: str | None = None
    address_exterior: str | None = None
    address_interior: str | None = None
    address_neighborhood: str | None = None
    address_city: str | None = None
    address_state: str | None = None
    address_zip: str | None = None
    address_country: str = "MEX"
    payment_terms_days: int = Field(default=30, ge=0)
    lead_time_days: int = Field(default=7, ge=0)
    credit_limit: float = Field(default=0.0, ge=0.0)
    currency: str = "MXN"
    bank_name: str | None = None
    bank_clabe: str | None = None
    notes: str | None = None


class SupplierUpdate(BaseSchema):
    code: str | None = None
    name: str | None = None
    commercial_name: str | None = None
    rfc: str | None = None
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    address_street: str | None = None
    address_exterior: str | None = None
    address_interior: str | None = None
    address_neighborhood: str | None = None
    address_city: str | None = None
    address_state: str | None = None
    address_zip: str | None = None
    address_country: str | None = None
    payment_terms_days: int | None = None
    lead_time_days: int | None = None
    credit_limit: float | None = None
    currency: str | None = None
    bank_name: str | None = None
    bank_clabe: str | None = None
    is_active: bool | None = None
    notes: str | None = None


class SupplierResponse(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    code: str | None
    name: str
    commercial_name: str | None
    rfc: str | None
    contact_name: str | None
    email: str | None
    phone: str | None
    website: str | None
    address_street: str | None
    address_exterior: str | None
    address_interior: str | None
    address_neighborhood: str | None
    address_city: str | None
    address_state: str | None
    address_zip: str | None
    address_country: str
    payment_terms_days: int
    lead_time_days: int
    credit_limit: float
    currency: str
    bank_name: str | None
    bank_clabe: str | None
    rating_score: float
    on_time_delivery_rate: float
    quality_rate: float
    fulfillment_accuracy_rate: float
    is_active: bool
    notes: str | None
    created_at: datetime


# ===========================================================================
# 2. CATÁLOGO DE PRODUCTOS SUMINISTRADOS POR PROVEEDOR
# ===========================================================================

class SupplierProductCreate(BaseSchema):
    supplier_id: uuid.UUID
    variant_id: uuid.UUID
    product_id: uuid.UUID | None = None
    supplier_sku: str | None = Field(None, max_length=100)
    supplier_product_name: str | None = Field(None, max_length=255)
    purchase_cost: float = Field(..., gt=0.0)
    currency: str = "MXN"
    tax_rate: float = Field(default=0.1600, ge=0.0, le=1.0)
    min_order_quantity: int = Field(default=1, ge=1)
    package_quantity: int = Field(default=1, ge=1)
    lead_time_days: int = Field(default=7, ge=0)
    is_preferred: bool = False


class SupplierProductUpdate(BaseSchema):
    supplier_sku: str | None = None
    supplier_product_name: str | None = None
    purchase_cost: float | None = Field(None, gt=0.0)
    currency: str | None = None
    tax_rate: float | None = None
    min_order_quantity: int | None = None
    package_quantity: int | None = None
    lead_time_days: int | None = None
    is_preferred: bool | None = None
    is_active: bool | None = None


class SupplierProductResponse(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    supplier_id: uuid.UUID
    product_id: uuid.UUID | None
    variant_id: uuid.UUID
    supplier_sku: str | None
    supplier_product_name: str | None
    purchase_cost: float
    currency: str
    tax_rate: float
    min_order_quantity: int
    package_quantity: int
    lead_time_days: int
    is_preferred: bool
    last_purchased_at: datetime | None
    last_purchase_price: float | None
    is_active: bool
    created_at: datetime


# ===========================================================================
# 3. EVALUACIÓN DE PROVEEDORES
# ===========================================================================

class SupplierEvaluationCreate(BaseSchema):
    purchase_order_id: uuid.UUID | None = None
    delivery_score: float = Field(..., ge=1.0, le=5.0, description="Puntualidad en entrega (1-5)")
    quality_score: float = Field(..., ge=1.0, le=5.0, description="Calidad de mercancía (1-5)")
    price_score: float = Field(..., ge=1.0, le=5.0, description="Competitividad de precios (1-5)")
    communication_score: float = Field(..., ge=1.0, le=5.0, description="Atención y servicio (1-5)")
    comments: str | None = None
    action_plan: str | None = None


class SupplierEvaluationResponse(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    supplier_id: uuid.UUID
    purchase_order_id: uuid.UUID | None
    evaluation_date: datetime
    evaluated_by_user_id: uuid.UUID | None
    evaluator_name: str
    delivery_score: float
    quality_score: float
    price_score: float
    communication_score: float
    overall_score: float
    comments: str | None
    action_plan: str | None
    created_at: datetime


# ===========================================================================
# 4. ÓRDENES DE COMPRA (WORKFLOW Y AUTORIZACIÓN ESTRICTA)
# ===========================================================================

class PurchaseOrderItemCreate(BaseSchema):
    variant_id: uuid.UUID
    product_id: uuid.UUID | None = None
    sku: str | None = None
    product_name: str | None = None
    quantity_ordered: int = Field(..., gt=0)
    unit_cost: float = Field(..., ge=0.0)
    tax_rate: float = Field(default=0.1600, ge=0.0, le=1.0)


class PurchaseOrderItemResponse(BaseSchema):
    id: uuid.UUID
    purchase_order_id: uuid.UUID
    product_id: uuid.UUID | None
    variant_id: uuid.UUID
    sku: str
    product_name: str
    quantity_ordered: int
    quantity_received: int
    quantity_pending: int
    unit_cost: float
    tax_rate: float
    total_cost: float
    status: str


class PurchaseOrderCreate(BaseSchema):
    company_id: uuid.UUID
    supplier_id: uuid.UUID
    warehouse_id: uuid.UUID | None = None
    po_number: str = Field(..., min_length=2, max_length=50)
    expected_delivery_date: datetime | None = None
    shipping_cost: float = Field(default=0.0, ge=0.0)
    other_expenses: float = Field(default=0.0, ge=0.0)
    notes: str | None = None
    items: list[PurchaseOrderItemCreate] = Field(..., min_length=1)


class PurchaseOrderUpdate(BaseSchema):
    warehouse_id: uuid.UUID | None = None
    expected_delivery_date: datetime | None = None
    shipping_cost: float | None = None
    other_expenses: float | None = None
    notes: str | None = None


class PurchaseOrderResponse(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    supplier_id: uuid.UUID
    warehouse_id: uuid.UUID | None
    po_number: str
    status: str
    order_date: datetime
    expected_delivery_date: datetime | None
    actual_delivery_date: datetime | None
    currency: str
    subtotal: float
    tax_amount: float
    shipping_cost: float
    other_expenses: float
    total_amount: float
    payment_terms_days: int
    payment_status: str
    approved_by_user_id: uuid.UUID | None
    approved_at: datetime | None
    payment_authorized: bool
    payment_authorized_by_user_id: uuid.UUID | None
    payment_authorized_at: datetime | None
    cancellation_reason: str | None
    notes: str | None
    created_at: datetime
    items: list[PurchaseOrderItemResponse] = []


class PurchaseOrderApproveRequest(BaseSchema):
    notes: str | None = None


class PurchaseOrderAuthorizePaymentRequest(BaseSchema):
    amount: float = Field(..., gt=0.0)
    notes: str | None = None


class PurchaseOrderCancelRequest(BaseSchema):
    reason: str = Field(..., min_length=5, max_length=500)


# ===========================================================================
# 5. RECEPCIONES DE MERCANCÍA (PARCIALES Y TOTALES)
# ===========================================================================

class GoodsReceiptItemCreate(BaseSchema):
    purchase_order_item_id: uuid.UUID
    variant_id: uuid.UUID
    sku: str | None = None
    quantity_received: int = Field(..., ge=0, description="Unidades en buen estado aceptadas")
    quantity_rejected: int = Field(default=0, ge=0, description="Unidades dañadas o rechazadas")
    rejection_reason: str | None = None
    unit_cost: float | None = None
    batch_number: str | None = None
    expiry_date: datetime | None = None
    location_bin: str | None = None


class GoodsReceiptItemResponse(BaseSchema):
    id: uuid.UUID
    receipt_id: uuid.UUID
    purchase_order_item_id: uuid.UUID
    variant_id: uuid.UUID
    sku: str
    quantity_received: int
    quantity_rejected: int
    rejection_reason: str | None
    unit_cost: float
    batch_number: str | None
    expiry_date: datetime | None
    location_bin: str | None


class GoodsReceiptCreate(BaseSchema):
    receipt_number: str = Field(..., min_length=2, max_length=50)
    warehouse_id: uuid.UUID
    receipt_date: datetime | None = None
    delivery_note_number: str | None = None
    carrier: str | None = None
    tracking_number: str | None = None
    notes: str | None = None
    items: list[GoodsReceiptItemCreate] = Field(..., min_length=1)


class GoodsReceiptResponse(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    purchase_order_id: uuid.UUID
    supplier_id: uuid.UUID
    warehouse_id: uuid.UUID
    receipt_number: str
    receipt_date: datetime
    delivery_note_number: str | None
    carrier: str | None
    tracking_number: str | None
    status: str
    received_by_user_id: uuid.UUID | None
    received_by_name: str
    notes: str | None
    created_at: datetime
    items: list[GoodsReceiptItemResponse] = []


# ===========================================================================
# 6. FACTURAS DE PROVEEDOR Y GASTOS ASOCIADOS (LANDED COST)
# ===========================================================================

class PurchaseInvoiceCreate(BaseSchema):
    invoice_series: str | None = None
    invoice_number: str = Field(..., min_length=1, max_length=50)
    uuid_sat: str | None = Field(None, max_length=36)
    invoice_date: datetime
    due_date: datetime
    currency: str = "MXN"
    exchange_rate: float = 1.0
    subtotal: float = Field(..., ge=0.0)
    tax_iva: float = Field(default=0.0, ge=0.0)
    tax_retention_iva: float = Field(default=0.0, ge=0.0)
    tax_retention_isr: float = Field(default=0.0, ge=0.0)
    total_amount: float = Field(..., gt=0.0)
    pdf_url: str | None = None
    xml_url: str | None = None
    notes: str | None = None


class PurchaseInvoiceResponse(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    purchase_order_id: uuid.UUID
    supplier_id: uuid.UUID
    invoice_series: str | None
    invoice_number: str
    uuid_sat: str | None
    invoice_date: datetime
    due_date: datetime
    currency: str
    exchange_rate: float
    subtotal: float
    tax_iva: float
    tax_retention_iva: float
    tax_retention_isr: float
    total_amount: float
    payment_status: str
    amount_paid: float
    pdf_url: str | None
    xml_url: str | None
    status: str
    notes: str | None
    created_at: datetime


class PurchaseExpenseCreate(BaseSchema):
    expense_type: Literal["freight", "customs", "insurance", "handling", "storage", "other"]
    amount: float = Field(..., gt=0.0)
    currency: str = "MXN"
    provider_name: str | None = None
    invoice_number: str | None = None
    expense_date: datetime | None = None
    allocation_method: Literal["by_value", "by_quantity", "by_weight"] = "by_value"
    notes: str | None = None


class PurchaseExpenseResponse(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    purchase_order_id: uuid.UUID
    expense_type: str
    amount: float
    currency: str
    provider_name: str | None
    invoice_number: str | None
    expense_date: datetime
    allocation_method: str
    notes: str | None
    created_at: datetime


class LandedCostItemResponse(BaseSchema):
    variant_id: uuid.UUID
    sku: str
    product_name: str
    quantity: int
    nominal_unit_cost: float
    allocated_freight: float
    allocated_other_expenses: float
    final_landed_unit_cost: float
    total_landed_cost: float


class LandedCostSummaryResponse(BaseSchema):
    purchase_order_id: uuid.UUID
    po_number: str
    total_merchandise_subtotal: float
    total_freight: float
    total_other_expenses: float
    total_landed_cost: float
    items: list[LandedCostItemResponse]


# ===========================================================================
# 7. MOTOR DE SUGERENCIAS Y ALERTAS DE REPOSICIÓN INTELIGENTE
# ===========================================================================

class ReplenishmentSuggestionItem(BaseSchema):
    variant_id: uuid.UUID
    product_id: uuid.UUID
    sku: str
    product_name: str
    category: str | None = None

    # Métricas de Existencias Actuales
    physical_stock: int
    reserved_stock: int
    blocked_stock: int
    available_stock: int
    stock_in_transit: int

    # Parámetros de Cadena de Suministro
    historical_sales_units: int
    days_analyzed: int
    sales_velocity_daily: float  # Unidades vendidas / día
    supplier_lead_time_days: int
    safety_stock: int
    estimated_demand_lead_time: float  # Demanda esperada durante lead time
    reorder_point: int  # Punto de Reorden (ROP)
    days_of_coverage: float  # Días de inventario disponible

    # Proveedor Preferido y Costo
    preferred_supplier_id: uuid.UUID | None = None
    preferred_supplier_name: str | None = None
    min_order_quantity: int = 1
    package_quantity: int = 1
    purchase_unit_cost: float

    # Diagnóstico y Sugerencia
    alert_status: Literal["OUT_OF_STOCK", "CRITICAL", "REORDER_POINT", "OVERSTOCK", "HEALTHY"]
    alert_message: str
    suggested_order_quantity: int  # Unidades recomendadas a comprar
    estimated_total_cost: float  # suggested_order_quantity * purchase_unit_cost


class ReplenishmentReportResponse(BaseSchema):
    company_id: uuid.UUID
    generated_at: datetime
    days_analyzed: int
    target_days_coverage: int
    total_skus_analyzed: int
    out_of_stock_count: int
    critical_count: int
    reorder_point_count: int
    healthy_count: int
    overstock_count: int
    total_suggested_investment: float
    items: list[ReplenishmentSuggestionItem]


class CreatePOFromSuggestionsItem(BaseSchema):
    variant_id: uuid.UUID
    quantity: int = Field(..., gt=0)
    unit_cost: float = Field(..., ge=0.0)


class CreatePOFromSuggestionsRequest(BaseSchema):
    supplier_id: uuid.UUID
    warehouse_id: uuid.UUID | None = None
    po_number: str | None = None
    items: list[CreatePOFromSuggestionsItem] = Field(..., min_length=1)
    notes: str | None = None


# ===========================================================================
# 8. ESTRUCTURA DE COSTOS Y COMPATIBILIDAD ANTERIOR
# ===========================================================================

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


class AuditLogResponse(BaseSchema):
    id: uuid.UUID

"""Esquemas Pydantic v2 para el Módulo Financiero, Transacciones, Liquidaciones y Conciliación."""

from datetime import datetime
from typing import Any, Literal
import uuid
from pydantic import Field

from src.schemas.common import BaseSchema


class FinancialKPIsResponse(BaseSchema):
    """
    Las 7 métricas financieras obligatorias claramente diferenciadas:
    1. Importe bruto (Facturación total sin descuentos)
    2. Importe neto estimado (Importe bruto - comisiones MeLi - fletes vendedor - retenciones SAT - empaque)
    3. Dinero acreditado (Pagos aprobados en Mercado Pago en proceso de liberación temporal)
    4. Dinero disponible (Saldo líquido liberado y listo para retiro a banco)
    5. Dinero retirado (Fondos transferidos a cuenta bancaria CLABE vía SPEI)
    6. Reembolsos (Montos devueltos al comprador por cancelaciones o reclamos)
    7. Cargos definitivos (Comisiones reales MeLi + fletes vendedor + retenciones SAT cobradas)
    """

    gross_amount: float = Field(default=0.0, description="Importe bruto cobrado")
    estimated_net_amount: float = Field(default=0.0, description="Importe neto estimado post-comisiones e impuestos")
    accredited_amount: float = Field(default=0.0, description="Dinero acreditado en Mercado Pago en espera de liberación")
    available_amount: float = Field(default=0.0, description="Dinero disponible y liberado en cuenta")
    withdrawn_amount: float = Field(default=0.0, description="Dinero retirado a cuentas bancarias externas")
    refund_amount: float = Field(default=0.0, description="Reembolsos aplicados por cancelaciones y devoluciones")
    definitive_charge_amount: float = Field(default=0.0, description="Cargos definitivos: comisiones MeLi + fletes + impuestos")

    # Métricas adicionales de auditoría y rentabilidad
    total_cogs: float = Field(default=0.0, description="Costo total de adquisición de mercancía (COGS)")
    external_expenses_total: float = Field(default=0.0, description="Gastos operativos y comerciales externos")
    real_net_profit: float = Field(default=0.0, description="Utilidad neta real (disponible - cogs - gastos)")
    profit_margin_pct: float = Field(default=0.0, description="Margen de utilidad neta porcentual")
    currency: str = "MXN"
    period: str = "Total histórico"


class FinancialTransactionResponse(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    meli_account_id: uuid.UUID | None = None
    order_id: uuid.UUID | None = None
    payment_id: uuid.UUID | None = None
    settlement_id: uuid.UUID | None = None
    external_expense_id: uuid.UUID | None = None

    transaction_type: str
    concept: str
    gross_amount: float
    fee_amount: float
    tax_amount: float
    net_amount: float
    currency: str = "MXN"

    status: str
    date_created: datetime
    date_accredited: datetime | None = None
    date_available: datetime | None = None
    date_withdrawn: datetime | None = None

    source: str
    external_reference: str | None = None
    notes: str | None = None


class SettlementCreateRequest(BaseSchema):
    meli_account_id: uuid.UUID = Field(..., description="Cuenta de Mercado Libre que recibe la liquidación")
    settlement_number: str = Field(..., min_length=3, max_length=50, description="Folio único de liquidación")
    meli_settlement_id: str | None = Field(None, description="ID oficial de liquidación / payout en Mercado Pago")
    period_start: datetime = Field(..., description="Inicio del periodo liquidado")
    period_end: datetime = Field(..., description="Fin del periodo liquidado")
    gross_amount: float = Field(..., description="Monto bruto procesado en el periodo")
    total_fees: float = Field(default=0.0, description="Comisiones de Mercado Libre deducidas")
    total_shipping_costs: float = Field(default=0.0, description="Cargos de envío Mercado Envíos deducidos")
    total_taxes: float = Field(default=0.0, description="Retenciones fiscales SAT deducidas (IVA + ISR)")
    total_refunds: float = Field(default=0.0, description="Reembolsos o contracargos descontados")
    total_adjustments: float = Field(default=0.0, description="Ajustes a favor o en contra")
    net_amount: float = Field(..., description="Importe neto transferido o liquidado")
    bank_name: str | None = Field(None, description="Banco receptor de los fondos")
    bank_account_clabe: str | None = Field(None, description="CLABE bancaria de destino (18 dígitos)")
    date_settled: datetime | None = Field(None, description="Fecha de transferencia bancaria efectiva")
    notes: str | None = None


class SettlementResponse(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    meli_account_id: uuid.UUID
    settlement_number: str
    meli_settlement_id: str | None = None
    period_start: datetime
    period_end: datetime
    status: str
    bank_name: str | None = None
    bank_account_clabe: str | None = None
    gross_amount: float
    total_fees: float
    total_shipping_costs: float
    total_taxes: float
    total_refunds: float
    total_adjustments: float
    net_amount: float
    date_settled: datetime | None = None
    notes: str | None = None
    created_at: datetime


class ExternalExpenseCreateRequest(BaseSchema):
    meli_account_id: uuid.UUID | None = Field(None, description="Cuenta MeLi asociada si el gasto aplica a una tienda específica")
    order_id: uuid.UUID | None = Field(None, description="Orden asociada si el gasto fue específico para una venta")
    product_id: uuid.UUID | None = Field(None, description="Producto asociado si es costo directo de catálogo")
    variant_id: uuid.UUID | None = Field(None, description="Variante o SKU específica")
    category: Literal[
        "advertising", "packaging", "shipping", "supplies", "software", "warehouse", "taxes", "other"
    ] = Field(..., description="Categoría del gasto externo")
    concept: str = Field(..., min_length=3, max_length=255, description="Concepto descriptivo del gasto")
    amount: float = Field(..., gt=0.0, description="Monto erogado en MXN")
    currency: str = "MXN"
    expense_date: datetime = Field(..., description="Fecha de emisión o pago del gasto")
    payment_method: Literal["bank_transfer", "credit_card", "debit_card", "cash", "other"] = Field(
        default="bank_transfer", description="Método de pago utilizado"
    )
    vendor_name: str | None = Field(None, max_length=150, description="Nombre o razón social del proveedor")
    invoice_folio: str | None = Field(None, max_length=100, description="Folio fiscal SAT (UUID) o factura")
    notes: str | None = None


class ExternalExpenseResponse(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    meli_account_id: uuid.UUID | None = None
    order_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    variant_id: uuid.UUID | None = None
    category: str
    concept: str
    amount: float
    currency: str
    expense_date: datetime
    payment_method: str
    vendor_name: str | None = None
    invoice_folio: str | None = None
    notes: str | None = None
    created_at: datetime


class FinancialDiscrepancyResponse(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    meli_account_id: uuid.UUID | None = None
    order_id: uuid.UUID | None = None
    payment_id: uuid.UUID | None = None
    settlement_id: uuid.UUID | None = None
    discrepancy_type: str
    severity: str
    status: str
    expected_amount: float
    actual_amount: float
    difference_amount: float
    description: str
    resolution_notes: str | None = None
    resolved_at: datetime | None = None
    detection_date: datetime


class DiscrepancyResolveRequest(BaseSchema):
    resolution_notes: str = Field(..., min_length=3, max_length=500, description="Explicación de cómo se resolvió o investigó")
    status: Literal["resolved", "investigating", "ignored"] = Field(
        default="resolved", description="Nuevo estatus de la discrepancia"
    )


class ReconciliationRunResponse(BaseSchema):
    total_orders_audited: int
    total_payments_audited: int
    total_settlements_audited: int
    matched_orders_count: int
    discrepancies_found_count: int
    total_difference_amount: float
    discrepancies: list[FinancialDiscrepancyResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Esquemas para Reportes Financieros Multidimensionales
# ---------------------------------------------------------------------------

class AccountFinancialReportItem(BaseSchema):
    account_id: uuid.UUID
    nickname: str
    site_id: str
    total_orders: int
    gross_sales: float
    commissions_meli: float
    shipping_charges: float
    sat_taxes: float
    refunds: float
    net_accredited: float
    withdrawn: float
    available_balance: float


class AccountFinancialReportResponse(BaseSchema):
    total_accounts: int
    accounts: list[AccountFinancialReportItem] = Field(default_factory=list)


class ProductFinancialReportItem(BaseSchema):
    product_id: uuid.UUID | None = None
    variant_id: uuid.UUID | None = None
    sku: str
    product_name: str
    units_sold: int
    gross_sales: float
    cogs_total: float
    commissions_meli: float
    shipping_costs: float
    sat_taxes: float
    external_expenses: float
    net_profit: float
    profit_margin_pct: float


class ProductFinancialReportResponse(BaseSchema):
    total_products: int
    products: list[ProductFinancialReportItem] = Field(default_factory=list)


class OrderFinancialReportResponse(BaseSchema):
    order_id: uuid.UUID
    meli_order_id: int
    order_number: str | None = None
    status: str
    date_created: datetime
    buyer_nickname: str | None = None
    total_amount: float
    paid_amount: float
    payments_count: int
    cogs_total: float
    meli_fee_amount: float
    shipping_cost_seller: float
    sat_iva_retention: float
    sat_isr_retention: float
    packaging_cost: float
    external_expenses: float
    net_profit: float
    profit_margin_pct: float
    is_reconciled: bool
    discrepancies_count: int
    transactions: list[FinancialTransactionResponse] = Field(default_factory=list)


class PeriodFinancialReportResponse(BaseSchema):
    period_type: Literal["daily", "weekly", "monthly", "yearly"]
    start_date: datetime
    end_date: datetime
    kpis: FinancialKPIsResponse
    subperiods: list[FinancialKPIsResponse] = Field(default_factory=list)

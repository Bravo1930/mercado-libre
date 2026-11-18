"""Esquemas Pydantic para el Motor Financiero de Rentabilidad, Historial de Costos, Alertas y Fiscalidad SAT."""

from datetime import datetime
from typing import Any, Literal
import uuid

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# CONFIGURACIÓN Y FÓRMULAS DE RENTABILIDAD
# ---------------------------------------------------------------------------

class ProfitabilityConfigCreateRequest(BaseModel):
    """Parámetros para crear o personalizar las fórmulas y umbrales de rentabilidad de la empresa."""
    name: str = Field(..., min_length=3, max_length=100)
    description: str | None = Field(None, max_length=255)
    gross_profit_formula: str = Field(
        "gross_revenue - discounts - cogs",
        description="Fórmula algebraica configurable para utilidad bruta",
    )
    net_profit_formula: str = Field(
        "gross_profit - commissions - fixed_charges - shipping - operational_expenses - taxes - refunds",
        description="Fórmula algebraica configurable para utilidad neta",
    )
    margin_base: Literal["revenue_after_discounts", "gross_revenue"] = Field(
        "revenue_after_discounts",
        description="Denominador para cálculo de margen porcentual (net_profit / base)",
    )
    default_packaging_cost: float = Field(15.00, ge=0.0)
    default_handling_cost: float = Field(10.00, ge=0.0)
    include_taxes_in_net: bool = Field(True, description="Si resta retenciones SAT en la ganancia neta")
    include_operational_in_net: bool = Field(True, description="Si resta empaque y manipulación en la ganancia neta")
    tax_regime: Literal["persona_fisica_con_rfc", "persona_moral_con_rfc", "sin_rfc"] = Field(
        "persona_fisica_con_rfc", description="Régimen fiscal verificado en MeLi / SAT"
    )
    sat_iva_retention_rate: float = Field(0.0800, ge=0.0, le=0.1600)
    sat_isr_retention_rate: float = Field(0.0100, ge=0.0, le=0.2000)
    loss_alert_threshold_margin_pct: float = Field(
        5.00, description="Umbral de margen porcentual por debajo del cual se disparan alertas de pérdida"
    )
    loss_alert_min_sales: int = Field(1, ge=1)


class ProfitabilityConfigUpdateRequest(BaseModel):
    """Actualización de fórmulas y umbrales de rentabilidad."""
    name: str | None = None
    description: str | None = None
    gross_profit_formula: str | None = None
    net_profit_formula: str | None = None
    margin_base: Literal["revenue_after_discounts", "gross_revenue"] | None = None
    default_packaging_cost: float | None = None
    default_handling_cost: float | None = None
    include_taxes_in_net: bool | None = None
    include_operational_in_net: bool | None = None
    tax_regime: Literal["persona_fisica_con_rfc", "persona_moral_con_rfc", "sin_rfc"] | None = None
    sat_iva_retention_rate: float | None = None
    sat_isr_retention_rate: float | None = None
    loss_alert_threshold_margin_pct: float | None = None
    loss_alert_min_sales: int | None = None
    is_active: bool | None = None


class ProfitabilityConfigResponse(BaseModel):
    """Configuración efectiva de rentabilidad."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    description: str | None = None
    gross_profit_formula: str
    net_profit_formula: str
    margin_base: str
    default_packaging_cost: float
    default_handling_cost: float
    include_taxes_in_net: bool
    include_operational_in_net: bool
    tax_regime: str
    sat_iva_retention_rate: float
    sat_isr_retention_rate: float
    loss_alert_threshold_margin_pct: float
    loss_alert_min_sales: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# DIFERENCIACIÓN DE COSTOS (REAL, ESTIMADO, PENDIENTE)
# ---------------------------------------------------------------------------

class CostBreakdownByStatus(BaseModel):
    """Desglose explícito de costos diferenciando reales, estimados y pendientes."""
    real: float = Field(0.0, description="Costos auditados y confirmados en liquidación/factura")
    estimated: float = Field(0.0, description="Costos proyectados teóricamente antes de conciliar")
    pending: float = Field(0.0, description="Costos devengados pendientes de liquidar o facturar")
    total: float = Field(0.0, description="Suma acumulada total")


# ---------------------------------------------------------------------------
# REPORTES DE RENTABILIDAD MULTIDIMENSIONAL
# ---------------------------------------------------------------------------

class ProfitabilityDimensionItem(BaseModel):
    """Resultado contable de rentabilidad para una entidad o periodo específico."""
    dimension_id: str = Field(..., description="ID de producto, SKU, publicación, pedido, cuenta o fecha")
    dimension_name: str = Field(..., description="Nombre descriptivo de la dimensión analizada")
    units_sold: int = Field(0, description="Unidades totales vendidas")
    sale_price_avg: float = Field(0.0, description="Precio de venta unitario promedio")
    gross_revenue: float = Field(0.0, description="Ingreso Bruto de Venta (PVP * Unidades)")
    discounts: float = Field(0.0, description="Descuentos promocionales absorbidos")
    net_revenue: float = Field(0.0, description="Ingreso efectivo (Gross Revenue - Discounts)")
    commissions: float = Field(0.0, description="Comisiones oficiales de Mercado Libre")
    fixed_charges: float = Field(0.0, description="Cargos fijos de plataforma (< $299 MXN)")
    shipping_costs: float = Field(0.0, description="Costo de fletes a cargo del vendedor")
    cogs_total: float = Field(0.0, description="Costo de adquisición/fabricación de la mercancía")
    operational_expenses: float = Field(0.0, description="Empaque, manipulación y gastos operativos")
    applicable_taxes: float = Field(0.0, description="Retenciones fiscales SAT (IVA 8% + ISR 1%)")
    refunds: float = Field(0.0, description="Reembolsos por cancelaciones o devoluciones")
    gross_profit: float = Field(0.0, description="Ganancia bruta contable")
    net_profit: float = Field(0.0, description="Ganancia neta final en mano")
    margin_pct: float = Field(0.0, description="Margen neto porcentual")
    cost_status_breakdown: CostBreakdownByStatus = Field(default_factory=CostBreakdownByStatus)
    is_loss: bool = Field(False, description="True si la dimensión opera en pérdida neta")


class ProfitabilityReportResponse(BaseModel):
    """Reporte agregado de rentabilidad en cualquiera de las 8 dimensiones oficiales."""
    dimension: Literal["product", "sku", "item", "order", "account", "daily", "weekly", "monthly"]
    total_units: int
    total_gross_revenue: float
    total_discounts: float
    total_net_revenue: float
    total_cogs: float
    total_commissions: float
    total_fixed_charges: float
    total_shipping: float
    total_operational: float
    total_taxes: float
    total_refunds: float
    total_gross_profit: float
    total_net_profit: float
    overall_margin_pct: float
    cost_status_summary: CostBreakdownByStatus
    loss_items_count: int
    items: list[ProfitabilityDimensionItem]


# ---------------------------------------------------------------------------
# ALERTAS DE PRODUCTOS EN PÉRDIDA
# ---------------------------------------------------------------------------

class ProfitabilityAlertResponse(BaseModel):
    """Alerta de un producto, SKU o publicación generando pérdida o margen crítico."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    product_id: uuid.UUID | None = None
    variant_id: uuid.UUID | None = None
    sku: str
    meli_item_id: str | None = None
    alert_type: str
    severity: str
    status: str
    current_price: float
    cogs: float
    net_profit: float
    net_margin_pct: float
    root_cause_analysis: str
    recommended_action: str
    recommended_price: float | None = None
    last_evaluated_at: datetime
    resolved_at: datetime | None = None
    resolution_notes: str | None = None


class ProfitabilityAlertResolveRequest(BaseModel):
    """Resolver o descartar una alerta de pérdida."""
    status: Literal["resolved", "dismissed", "acknowledged"] = "resolved"
    resolution_notes: str = Field(..., min_length=5, description="Acción tomada para solucionar la pérdida")


# ---------------------------------------------------------------------------
# SIMULADOR DE PRECIOS PARA MARGEN OBJETIVO
# ---------------------------------------------------------------------------

class TargetMarginSimulationRequest(BaseModel):
    """
    Parámetros para calcular mediante fórmula matemática inversa
    el precio de venta exacto requerido para obtener el margen objetivo.
    """
    cogs: float = Field(..., gt=0.0, description="Costo unitario de mercancía en MXN")
    target_margin_pct: float = Field(..., ge=1.0, le=80.0, description="Margen neto objetivo deseado (e.g. 25.0%)")
    commission_rate: float = Field(0.15, ge=0.0, le=0.40, description="Tasa de comisión MeLi (e.g. 0.15 para 15%)")
    shipping_cost: float = Field(85.00, ge=0.0, description="Flete estimado a cargo del vendedor")
    packaging_cost: float = Field(15.00, ge=0.0, description="Costo de caja, burbuja, etiquetas")
    handling_cost: float = Field(10.00, ge=0.0, description="Mano de obra y empaque")
    tax_regime: Literal["persona_fisica_con_rfc", "persona_moral_con_rfc", "sin_rfc"] = Field(
        "persona_fisica_con_rfc", description="Régimen fiscal SAT para retenciones"
    )
    discount_pct: float = Field(0.0, ge=0.0, le=70.0, description="Descuento promocional planificado")


class TargetMarginSimulationResponse(BaseModel):
    """Resultado del cálculo inverso de precio para margen objetivo."""
    suggested_price: float = Field(..., description="Precio de venta al público recomendado (PVP)")
    target_margin_pct: float = Field(..., description="Margen objetivo solicitado")
    achieved_margin_pct: float = Field(..., description="Margen neto exacto obtenido tras deducciones")
    net_profit: float = Field(..., description="Ganancia neta líquida en MXN")
    gross_revenue: float
    discounts: float
    cogs: float
    commission_fee: float
    fixed_fee: float = Field(..., description="Cargo fijo de $25 MXN si PVP < $299 MXN")
    shipping_cost: float
    operational_expenses: float
    sat_iva_retention: float
    sat_isr_retention: float
    total_taxes: float
    total_deductions: float
    tax_regime_used: str
    break_even_price: float = Field(..., description="Precio piso donde Net Profit = $0.00 MXN")
    formula_applied: str


# ---------------------------------------------------------------------------
# HISTORIAL INMUTABLE DE COSTOS
# ---------------------------------------------------------------------------

class CostHistoryCreateRequest(BaseModel):
    """Registro obligatorio de modificación de costo de adquisición."""
    sku: str = Field(..., min_length=2, max_length=100)
    new_cogs: float = Field(..., gt=0.0, description="Nuevo costo de adquisición en MXN")
    change_reason: Literal[
        "supplier_increase",
        "purchase_order",
        "currency_fluctuation",
        "audit_adjustment",
        "initial_setup",
        "manual_update",
    ] = Field("manual_update", description="Motivo obligatorio del cambio")
    notes: str | None = Field(None, max_length=255)
    product_id: uuid.UUID | None = None
    variant_id: uuid.UUID | None = None
    effective_date: datetime | None = None


class CostHistoryResponse(BaseModel):
    """Auditoría de un cambio de costo."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sku: str
    previous_cogs: float
    new_cogs: float
    change_reason: str
    notes: str | None = None
    effective_date: datetime
    created_at: datetime


# ---------------------------------------------------------------------------
# INTEGRACIÓN FISCAL MEXICANA (PAC / CFDI 4.0 / SAT)
# ---------------------------------------------------------------------------

class FiscalIntegrationConfigCreateRequest(BaseModel):
    """Configuración del proveedor PAC autorizado para timbrado fiscal CFDI 4.0."""
    pac_provider: Literal["facturapi", "finkok", "sovos", "sw_sapience", "folios_digitales"] = "facturapi"
    environment: Literal["sandbox", "production"] = "sandbox"
    api_key: str = Field(..., min_length=5, description="Token secreto o API key del PAC")
    rfc_emisor: str = Field(..., min_length=12, max_length=13, description="RFC del emisor registrado en SAT")
    razon_social: str = Field(..., min_length=3, max_length=200)
    regimen_fiscal_sat: str = Field("626", min_length=3, max_length=10, description="Clave de Régimen Fiscal SAT")
    postal_code: str = Field(..., min_length=5, max_length=5, description="Código Postal del domicilio fiscal emisor")
    default_cfdi_use: str = Field("G03", min_length=3, max_length=10)
    auto_invoice_delivered: bool = Field(False)
    auto_generate_retention: bool = Field(True)


class FiscalIntegrationConfigResponse(BaseModel):
    """Detalle de la configuración fiscal activa."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    pac_provider: str
    environment: str
    rfc_emisor: str
    razon_social: str
    regimen_fiscal_sat: str
    postal_code: str
    default_cfdi_use: str
    auto_invoice_delivered: bool
    auto_generate_retention: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class FiscalInvoiceGenerateRequest(BaseModel):
    """Solicitud de timbrado de CFDI 4.0 a partir de una orden de venta."""
    order_id: uuid.UUID
    rfc_receptor: str = Field("XAXX010101000", min_length=12, max_length=13)
    razon_social_receptor: str = Field("PÚBLICO EN GENERAL", min_length=3, max_length=200)
    cfdi_use: str = Field("S01", min_length=3, max_length=10)  # S01 Sin efectos fiscales


class FiscalInvoiceResponse(BaseModel):
    """CFDI 4.0 generado y timbrado con PAC oficial."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    order_id: uuid.UUID | None = None
    invoice_type: str
    status: str
    uuid_sat: str | None = None
    series: str | None = None
    folio: str | None = None
    pac_provider: str
    rfc_receptor: str
    razon_social_receptor: str
    subtotal: float
    discount_amount: float
    iva_transferred: float
    iva_retention: float
    isr_retention: float
    total: float
    xml_url: str | None = None
    pdf_url: str | None = None
    stamped_at: datetime | None = None
    created_at: datetime

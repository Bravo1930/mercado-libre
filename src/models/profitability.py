"""Modelos de Motor Financiero de Rentabilidad, Historial de Costos, Alertas de Pérdida y Fiscalidad SAT."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from src.models.base import GUID, Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.meli_account import MeliAccount
    from src.models.order import Order
    from src.models.product import Product, ProductVariant
    from src.models.tenant import Company
    from src.models.user import User


class ProfitabilityConfig(Base, TimestampMixin):
    """
    Configuración y fórmulas de rentabilidad personalizables por empresa.
    Permite parametrizar las reglas de cálculo de ganancia bruta, ganancia neta, base de margen y umbrales de alerta.
    """

    __tablename__ = "profitability_configs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), default="Configuración Estándar de Rentabilidad", nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Fórmulas configurables
    gross_profit_formula: Mapped[str] = mapped_column(
        String(100), default="gross_revenue - discounts - cogs", nullable=False
    )
    net_profit_formula: Mapped[str] = mapped_column(
        String(200),
        default="gross_profit - commissions - fixed_charges - shipping - operational_expenses - taxes - refunds",
        nullable=False,
    )
    margin_base: Mapped[str] = mapped_column(
        String(50), default="revenue_after_discounts", nullable=False
    )  # revenue_after_discounts, gross_revenue

    # Parámetros operativos y costos por defecto
    default_packaging_cost: Mapped[float] = mapped_column(Numeric(10, 2), default=15.00, nullable=False)
    default_handling_cost: Mapped[float] = mapped_column(Numeric(10, 2), default=10.00, nullable=False)
    include_taxes_in_net: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    include_operational_in_net: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Régimen fiscal aplicable en Mercado Libre México
    tax_regime: Mapped[str] = mapped_column(
        String(50), default="persona_fisica_con_rfc", nullable=False
    )  # persona_fisica_con_rfc, persona_moral_con_rfc, sin_rfc
    sat_iva_retention_rate: Mapped[float] = mapped_column(Numeric(5, 4), default=0.0800, nullable=False)  # 8%
    sat_isr_retention_rate: Mapped[float] = mapped_column(Numeric(5, 4), default=0.0100, nullable=False)  # 1%

    # Umbral de alerta para productos con pérdidas o margen crítico
    loss_alert_threshold_margin_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=5.00, nullable=False)
    loss_alert_min_sales: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    company: Mapped["Company"] = relationship("Company")


class CostHistory(Base, TimestampMixin):
    """
    Historial inmutable de costos de adquisición / producción (COGS).
    Garantiza trazabilidad y permite auditar la rentabilidad histórica con el costo exacto vigente en la fecha de venta.
    """

    __tablename__ = "cost_histories"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("products.id", ondelete="CASCADE"), nullable=True, index=True
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    sku: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    previous_cogs: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    new_cogs: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    change_reason: Mapped[str] = mapped_column(
        String(100), default="manual_update", nullable=False
    )  # supplier_increase, purchase_order, currency_fluctuation, audit_adjustment, initial_setup
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    effective_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    company: Mapped["Company"] = relationship("Company")
    product: Mapped["Product | None"] = relationship("Product")
    variant: Mapped["ProductVariant | None"] = relationship("ProductVariant")
    user: Mapped["User | None"] = relationship("User")


class ProfitabilityAlert(Base, TimestampMixin):
    """
    Alertas financieras generadas automáticamente para productos que generan pérdidas o márgenes críticos.
    Incluye análisis de causa raíz y recomendaciones comerciales correctivas.
    """

    __tablename__ = "profitability_alerts"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True, index=True
    )
    sku: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    meli_item_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    alert_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # net_loss, critical_margin, high_shipping_drag, fixed_fee_penalty, tax_drag
    severity: Mapped[str] = mapped_column(
        String(20), default="high", nullable=False, index=True
    )  # critical, high, medium, low
    status: Mapped[str] = mapped_column(
        String(30), default="active", nullable=False, index=True
    )  # active, acknowledged, resolved, dismissed

    current_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    cogs: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    net_profit: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    net_margin_pct: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)

    root_cause_analysis: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    last_evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    company: Mapped["Company"] = relationship("Company")
    product: Mapped["Product | None"] = relationship("Product")
    variant: Mapped["ProductVariant | None"] = relationship("ProductVariant")


class FiscalIntegrationConfig(Base, TimestampMixin):
    """
    Configuración de integración con Proveedores Autorizados de Certificación (PAC) del SAT en México.
    Prepara la emisión de CFDI 4.0 (Ingreso, Egreso y Retenciones e Información de Pagos).
    """

    __tablename__ = "fiscal_integration_configs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )

    pac_provider: Mapped[str] = mapped_column(
        String(50), default="facturapi", nullable=False
    )  # facturapi, finkok, sovos, sw_sapience, folios_digitales
    environment: Mapped[str] = mapped_column(String(20), default="sandbox", nullable=False)  # sandbox, production
    api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)  # Clave API cifrada AES-256

    # Datos fiscales del emisor
    rfc_emisor: Mapped[str] = mapped_column(String(20), nullable=False)
    razon_social: Mapped[str] = mapped_column(String(200), nullable=False)
    regimen_fiscal_sat: Mapped[str] = mapped_column(String(10), default="626", nullable=False)  # e.g. 626 RESICO, 601 General
    postal_code: Mapped[str] = mapped_column(String(10), nullable=False)

    default_cfdi_use: Mapped[str] = mapped_column(String(10), default="G03", nullable=False)  # Gastos en general
    auto_invoice_delivered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_generate_retention: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    company: Mapped["Company"] = relationship("Company")


class FiscalInvoice(Base, TimestampMixin):
    """
    Comprobante Fiscal Digital por Internet (CFDI 4.0) o Constancia de Retención SAT.
    Vinculado a órdenes de venta o liquidaciones bancarias.
    """

    __tablename__ = "fiscal_invoices"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )

    invoice_type: Mapped[str] = mapped_column(
        String(50), default="ingreso", nullable=False, index=True
    )  # ingreso, egreso_devolucion, retencion_plataformas
    status: Mapped[str] = mapped_column(
        String(30), default="draft", nullable=False, index=True
    )  # draft, stamped, cancelled, rejected

    uuid_sat: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True, index=True)  # Folio Fiscal UUID 36 chars
    series: Mapped[str | None] = mapped_column(String(10), nullable=True)
    folio: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pac_provider: Mapped[str] = mapped_column(String(50), nullable=False)

    # Datos Receptor
    rfc_receptor: Mapped[str] = mapped_column(String(20), default="XAXX010101000", nullable=False)
    razon_social_receptor: Mapped[str] = mapped_column(String(200), default="PÚBLICO EN GENERAL", nullable=False)

    # Desglose financiero
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    discount_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    iva_transferred: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    iva_retention: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    isr_retention: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    xml_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pdf_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    stamped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)

    company: Mapped["Company"] = relationship("Company")
    order: Mapped["Order | None"] = relationship("Order")

"""Modelos de Datos para la Comercialización del ERP como SaaS Multiempresa.

Garantiza:
1. Separación absoluta de la facturación y suscripciones del SaaS respecto a las finanzas de cada cliente.
2. Planes comerciales configurables (Básico, Profesional, Empresarial) sin fijar precios definitivos sin análisis comercial.
3. Límites estrictos por plan: usuarios, cuentas MeLi, almacenamiento MB, órdenes y sincronizaciones mensuales.
4. Ciclo de vida completo: trialing, active, past_due, suspended, cancelled, expired.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import GUID, Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.tenant import Tenant


class SaaSPlan(Base, TimestampMixin):
    """
    Planes comerciales configurables para la plataforma SaaS.
    Soporta precios sugeridos configurables y cotizaciones personalizadas tras análisis comercial.
    """

    __tablename__ = "saas_plans"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)  # basic, pro, enterprise
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # Básico, Profesional, Empresarial
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Precios base configurables en MXN (sujetos a análisis comercial y no fijados rígidamente)
    monthly_price_mxn: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    annual_price_mxn: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    is_custom_pricing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # True para Enterprise
    trial_days: Mapped[int] = mapped_column(Integer, default=14, nullable=False)  # Periodo de prueba gratuito

    # Límites operativos y de procesamiento permitidos por el plan (-1 representa ilimitado)
    max_users: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    max_meli_accounts: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_storage_mb: Mapped[int] = mapped_column(Integer, default=1024, nullable=False)  # 1 GB
    max_monthly_orders: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    max_monthly_syncs: Mapped[int] = mapped_column(Integer, default=5000, nullable=False)

    # Banderas de características comerciales (Feature Flags)
    has_automation_engine: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_ai_assistant: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_advanced_logistics: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    has_priority_support: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    features_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # Lista JSON de viñetas comerciales
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    subscriptions: Mapped[list["SaaSSubscription"]] = relationship("SaaSSubscription", back_populates="plan")


class SaaSSubscription(Base, TimestampMixin):
    """
    Suscripción activa de un Tenant (Organización cliente) al servicio SaaS.
    Gestiona el ciclo de vida, periodos de prueba, renovaciones, suspensiones y cuotas.
    """

    __tablename__ = "saas_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("saas_plans.id", ondelete="RESTRICT"), index=True, nullable=False
    )

    # Estados: trialing, active, past_due, suspended, cancelled, expired
    status: Mapped[str] = mapped_column(String(50), default="trialing", index=True, nullable=False)
    billing_cycle: Mapped[str] = mapped_column(String(20), default="monthly", nullable=False)  # monthly, annual

    current_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Fechas de ciclo de vida
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspension_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Precios personalizados pactados tras análisis comercial
    custom_price_mxn: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    discount_percent: Mapped[float] = mapped_column(Numeric(5, 2), default=0.0, nullable=False)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Integración con proveedores de pago autorizados (Stripe, Mercado Pago, SPEI)
    payment_provider: Mapped[str] = mapped_column(String(50), default="manual", nullable=False)  # stripe, mercadopago, spei, manual
    external_customer_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    external_subscription_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # Contadores de consumo en el periodo actual
    current_monthly_orders: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_monthly_syncs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_storage_mb: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)

    plan: Mapped["SaaSPlan"] = relationship("SaaSPlan", back_populates="subscriptions")
    tenant: Mapped["Tenant"] = relationship("Tenant")
    invoices: Mapped[list["SaaSInvoice"]] = relationship(
        "SaaSInvoice", back_populates="subscription", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_saas_subs_status_period", "status", "current_period_end"),
    )


class SaaSInvoice(Base, TimestampMixin):
    """
    Factura emitida por la plataforma SaaS al cliente por uso del software y licencias.
    Completamente separada de las finanzas y ventas en Mercado Libre de las empresas cliente.
    """

    __tablename__ = "saas_invoices"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("saas_subscriptions.id", ondelete="CASCADE"), index=True, nullable=False
    )

    invoice_number: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)  # e.g. "INV-SAAS-2026-0001"
    issue_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    tax_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)  # IVA 16%
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="MXN", nullable=False)

    # Estados: draft, issued, paid, overdue, void, refunded
    status: Mapped[str] = mapped_column(String(50), default="issued", index=True, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Comprobante fiscal digital por internet (CFDI México) emitido por la empresa SaaS
    sat_uuid: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pdf_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    subscription: Mapped["SaaSSubscription"] = relationship("SaaSSubscription", back_populates="invoices")
    payments: Mapped[list["SaaSPayment"]] = relationship("SaaSPayment", back_populates="invoice")

    __table_args__ = (
        Index("ix_saas_invoices_tenant_status", "tenant_id", "status"),
    )


class SaaSPayment(Base, TimestampMixin):
    """
    Transacción de pago recibida por la plataforma SaaS mediante pasarela autorizada o SPEI.
    """

    __tablename__ = "saas_payments"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("saas_invoices.id", ondelete="SET NULL"), index=True, nullable=True
    )

    payment_method: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # stripe, mercadopago, spei, manual_transfer
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="MXN", nullable=False)

    # Estados: pending, succeeded, failed, refunded
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True, nullable=False)
    gateway_transaction_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    gateway_fee: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)

    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    receipt_url: Mapped[str | None] = mapped_column(String(255), nullable=True)

    invoice: Mapped["SaaSInvoice | None"] = relationship("SaaSInvoice", back_populates="payments")


class SaaSUsageRecord(Base, TimestampMixin):
    """Bitácora de consumo métrico para control de cuotas y analítica de uso del SaaS."""

    __tablename__ = "saas_usage_records"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    metric_name: Mapped[str] = mapped_column(
        String(50), index=True, nullable=False
    )  # orders_processed, sync_events, storage_mb, meli_accounts, active_users
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    __table_args__ = (
        Index("ix_saas_usage_tenant_metric", "tenant_id", "metric_name", "recorded_at"),
    )

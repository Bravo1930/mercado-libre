"""Esquemas Pydantic para Comercialización SaaS, Planes, Suscripciones y Facturación."""

from datetime import datetime
from typing import Any, Literal
import uuid
from pydantic import BaseModel, Field


class SaaSPlanResponse(BaseModel):
    """Información pública y comercial de un plan SaaS."""

    id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    monthly_price_mxn: float
    annual_price_mxn: float
    is_custom_pricing: bool
    trial_days: int
    max_users: int
    max_meli_accounts: int
    max_storage_mb: int
    max_monthly_orders: int
    max_monthly_syncs: int
    has_automation_engine: bool
    has_ai_assistant: bool
    has_advanced_logistics: bool
    has_priority_support: bool
    features_json: str | None = None
    is_active: bool
    sort_order: int

    model_config = {"from_attributes": True}


class SaaSPlanCreate(BaseModel):
    """Creación o configuración de un nuevo plan comercial."""

    code: str = Field(..., max_length=50)
    name: str = Field(..., max_length=100)
    description: str | None = None
    monthly_price_mxn: float = Field(default=0.0, ge=0.0)
    annual_price_mxn: float = Field(default=0.0, ge=0.0)
    is_custom_pricing: bool = False
    trial_days: int = Field(default=14, ge=0)
    max_users: int = Field(default=3)
    max_meli_accounts: int = Field(default=1)
    max_storage_mb: int = Field(default=1024)
    max_monthly_orders: int = Field(default=1000)
    max_monthly_syncs: int = Field(default=5000)
    has_automation_engine: bool = False
    has_ai_assistant: bool = False
    has_advanced_logistics: bool = True
    has_priority_support: bool = False
    features_json: str | None = None
    sort_order: int = 1


class SaaSSubscriptionResponse(BaseModel):
    """Estado y detalle de la suscripción de un cliente."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    plan_code: str
    plan_name: str
    status: str  # trialing, active, past_due, suspended, cancelled, expired
    billing_cycle: str
    current_period_start: datetime
    current_period_end: datetime
    trial_ends_at: datetime | None = None
    is_trial_active: bool = False
    days_left_in_trial: int = 0
    effective_price_mxn: float
    discount_percent: float
    auto_renew: bool
    payment_provider: str
    # Consumo actual vs límites
    current_monthly_orders: int
    max_monthly_orders: int
    current_monthly_syncs: int
    max_monthly_syncs: int
    current_storage_mb: float
    max_storage_mb: int
    active_users_count: int
    max_users: int
    active_meli_accounts_count: int
    max_meli_accounts: int
    # Features
    has_automation_engine: bool
    has_ai_assistant: bool
    has_advanced_logistics: bool


class SaaSClientRegisterRequest(BaseModel):
    """Alta de nuevo cliente (Onboarding Self-Serve o Asistido)."""

    tenant_name: str = Field(..., min_length=3, max_length=200, description="Nombre de la Organización / Empresa")
    tenant_slug: str = Field(..., min_length=3, max_length=100, description="Identificador único en URL")
    company_legal_name: str = Field(..., min_length=3, max_length=255, description="Razón Social fiscal")
    company_rfc: str = Field(..., min_length=12, max_length=13, description="RFC mexicano")
    admin_email: str = Field(..., description="Correo del administrador principal")
    admin_password: str = Field(..., min_length=8, description="Contraseña de acceso")
    admin_full_name: str = Field(..., min_length=3, description="Nombre completo del administrador")
    plan_code: str = Field(default="basic", description="Plan inicial elegido (basic, pro, enterprise)")
    billing_cycle: Literal["monthly", "annual"] = "monthly"


class SaaSClientRegisterResponse(BaseModel):
    """Respuesta al completar el registro del cliente."""

    tenant_id: uuid.UUID
    tenant_name: str
    tenant_slug: str
    company_id: uuid.UUID
    company_legal_name: str
    user_id: uuid.UUID
    admin_email: str
    subscription_id: uuid.UUID
    plan_code: str
    status: str
    trial_ends_at: datetime | None = None
    message: str


class ChangePlanRequest(BaseModel):
    """Solicitud de cambio de plan (Upgrade / Downgrade)."""

    new_plan_code: str = Field(..., description="Código del nuevo plan (basic, pro, enterprise)")
    billing_cycle: Literal["monthly", "annual"] = "monthly"


class CancelSubscriptionRequest(BaseModel):
    """Solicitud de cancelación de suscripción."""

    reason: str | None = Field(default=None, description="Motivo de cancelación voluntaria")
    immediate: bool = Field(default=False, description="Si es inmediata o hasta fin de ciclo")


class SuspendTenantRequest(BaseModel):
    """Suspensión administrativa de un cliente."""

    reason: str = Field(..., min_length=5, description="Motivo de suspensión (falta de pago, violación de términos)")


class ExtendTrialRequest(BaseModel):
    """Extensión comercial de periodo de prueba."""

    extra_days: int = Field(..., ge=1, le=90, description="Días adicionales de prueba a conceder")


class CustomPricingRequest(BaseModel):
    """Fijación de precio o descuento personalizado tras análisis comercial."""

    custom_monthly_price_mxn: float | None = Field(default=None, ge=0.0, description="Precio mensual personalizado")
    discount_percent: float = Field(default=0.0, ge=0.0, le=100.0, description="Descuento en porcentaje")
    notes: str | None = Field(default=None, description="Justificación comercial del acuerdo")


class SaaSInvoiceResponse(BaseModel):
    """Factura emitida por el SaaS a la organización cliente."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    subscription_id: uuid.UUID
    invoice_number: str
    issue_date: datetime
    due_date: datetime
    subtotal: float
    tax_amount: float
    total_amount: float
    currency: str
    status: str  # draft, issued, paid, overdue, void
    paid_at: datetime | None = None
    pdf_url: str | None = None
    notes: str | None = None

    model_config = {"from_attributes": True}


class SaaSPaymentRecordRequest(BaseModel):
    """Registro de pago de factura SaaS (pasarela o manual)."""

    invoice_id: uuid.UUID
    payment_method: Literal["stripe", "mercadopago", "spei", "manual_transfer"]
    amount: float = Field(..., gt=0.0)
    gateway_transaction_id: str | None = None
    gateway_fee: float = Field(default=0.0, ge=0.0)
    receipt_url: str | None = None
    notes: str | None = None


class SaaSTenantSummaryResponse(BaseModel):
    """Ficha resumen de un cliente para el Panel Global SaaS."""

    tenant_id: uuid.UUID
    tenant_name: str
    tenant_slug: str
    companies_count: int
    admin_email: str
    plan_code: str
    plan_name: str
    status: str
    billing_cycle: str
    current_period_end: datetime
    trial_ends_at: datetime | None = None
    effective_mrr_mxn: float
    active_users: int
    meli_accounts_count: int
    created_at: datetime


class SaaSGlobalMetricsResponse(BaseModel):
    """Métricas ejecutivas de comercialización y negocio SaaS."""

    mrr_mxn: float = Field(..., description="Ingreso Recurrente Mensual")
    arr_mxn: float = Field(..., description="Ingreso Recurrente Anualizado")
    arpu_mxn: float = Field(..., description="Ingreso Promedio por Usuario/Cliente")
    total_tenants: int
    active_tenants: int
    trialing_tenants: int
    suspended_tenants: int
    cancelled_tenants: int
    churn_rate_percent: float
    plan_distribution: dict[str, int]
    evaluated_at: datetime

"""Esquemas Pydantic para el Administrador Comercial, Precios, Promociones, Simulación y Competencia."""

from datetime import datetime
from typing import Any, Literal
import uuid

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# REGLAS COMERCIALES CONFIGURABLES
# ---------------------------------------------------------------------------

class CommercialRuleCreateRequest(BaseModel):
    """Creación de regla comercial para salvaguardar precios y márgenes."""
    meli_account_id: uuid.UUID | None = None
    name: str = Field(..., min_length=3, max_length=120)
    description: str | None = None
    min_price: float = Field(0.0, ge=0.0, description="Precio mínimo piso absoluto")
    min_margin_pct: float = Field(15.0, ge=0.0, le=100.0, description="Margen neto mínimo exigido (e.g. 15%)")
    max_discount_pct: float = Field(30.0, ge=0.0, le=90.0, description="Descuento máximo permitido")
    target_price: float | None = Field(None, ge=0.0, description="Precio objetivo sugerido")
    max_daily_changes: int = Field(3, ge=1, le=24, description="Límite de cambios de precio por día")
    allowed_hours_start: int | None = Field(None, ge=0, le=23, description="Hora inicio ventana (0 a 23)")
    allowed_hours_end: int | None = Field(None, ge=0, le=23, description="Hora fin ventana (0 a 23)")
    excluded_skus: list[str] = Field(default_factory=list, description="Lista de SKUs excluidos de ajustes automáticos")
    promotional_budget: float | None = Field(None, ge=0.0, description="Presupuesto máximo para absorción de descuentos")


class CommercialRuleUpdateRequest(BaseModel):
    """Actualización de regla comercial."""
    name: str | None = None
    description: str | None = None
    min_price: float | None = None
    min_margin_pct: float | None = None
    max_discount_pct: float | None = None
    target_price: float | None = None
    max_daily_changes: int | None = None
    allowed_hours_start: int | None = None
    allowed_hours_end: int | None = None
    excluded_skus: list[str] | None = None
    promotional_budget: float | None = None
    is_active: bool | None = None


class CommercialRuleResponse(BaseModel):
    """Detalle de regla comercial configurada."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    meli_account_id: uuid.UUID | None = None
    name: str
    description: str | None = None
    min_price: float
    min_margin_pct: float
    max_discount_pct: float
    target_price: float | None = None
    max_daily_changes: int
    allowed_hours_start: int | None = None
    allowed_hours_end: int | None = None
    excluded_skus: list[str] = []
    promotional_budget: float | None = None
    budget_consumed: float
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# MODIFICACIÓN, AUDITORÍA Y PROGRAMACIÓN DE PRECIOS
# ---------------------------------------------------------------------------

class PriceUpdateRequest(BaseModel):
    """Solicitud de cambio de precio para una publicación de Mercado Libre."""
    new_price: float = Field(..., gt=0.0, description="Nuevo precio de venta en MXN")
    variation_id: str | None = Field(None, description="ID de variante si la publicación tiene múltiples opciones")
    reason: str = Field("manual", description="Motivo del cambio (manual, competitor_match, promotion)")
    bypass_rules: bool = Field(False, description="Forzar cambio omitiendo validación de reglas comerciales (solo admin)")


class PriceUpdateResponse(BaseModel):
    """Resultado oficial del cambio de precio en Mercado Libre."""
    meli_item_id: str
    previous_price: float
    new_price: float
    change_reason: str
    status: Literal["applied", "rejected", "restored"]
    confirmed_by_meli: bool
    history_id: uuid.UUID
    message: str


class PriceRestoreRequest(BaseModel):
    """Restauración de un precio anterior desde el historial de auditoría."""
    history_id: uuid.UUID = Field(..., description="UUID del registro de historial que se desea restaurar")
    reason: str = Field("Restauración manual de precio anterior", description="Motivo de la restauración")


class PriceHistoryResponse(BaseModel):
    """Auditoría de un cambio de precio."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    meli_item_id: str
    meli_variation_id: str | None = None
    previous_price: float
    new_price: float
    change_reason: str
    can_restore: bool
    restored_at: datetime | None = None
    notes: str | None = None
    created_at: datetime


class ScheduledPriceChangeCreateRequest(BaseModel):
    """Programar un ajuste de precio a futuro con opción de reversión."""
    meli_item_id: str = Field(..., min_length=5, max_length=30)
    target_price: float = Field(..., gt=0.0)
    scheduled_at: datetime = Field(..., description="Fecha y hora en que debe activarse el nuevo precio")
    revert_at: datetime | None = Field(None, description="Fecha y hora opcional para regresar al precio original")


class ScheduledPriceChangeResponse(BaseModel):
    """Detalle de un cambio de precio programado."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    meli_item_id: str
    original_price: float
    target_price: float
    scheduled_at: datetime
    revert_at: datetime | None = None
    status: str
    applied_at: datetime | None = None
    reverted_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# SIMULACIÓN DE RENTABILIDAD Y PROMOCIONES
# ---------------------------------------------------------------------------

class PromotionSimulationRequest(BaseModel):
    """
    Parámetros para simular con precisión fiscal y financiera el resultado
    de una oferta o campaña antes de postular la publicación.
    """
    regular_price: float = Field(..., gt=0.0, description="Precio normal de catálogo en MXN")
    discount_pct: float = Field(..., ge=1.0, le=90.0, description="Porcentaje de descuento ofrecido")
    cogs: float = Field(..., ge=0.0, description="Costo de la mercancía vendida (COGS)")
    shipping_cost: float = Field(0.0, ge=0.0, description="Flete a cargo del vendedor si ofrece envío gratis")
    packaging_cost: float = Field(15.0, ge=0.0, description="Costo de materiales de empaque")
    cofunded_by_meli_pct: float = Field(0.0, ge=0.0, le=100.0, description="% del descuento que absorbe Mercado Libre")
    meli_fee_rate: float = Field(0.15, ge=0.0, le=0.35, description="Tasa de comisión MeLi por categoría (e.g. 15%)")


class PromotionSimulationResponse(BaseModel):
    """Desglose financiero proyectado de una promoción."""
    regular_price: float
    discount_pct: float
    promotional_price: float
    discount_total_amount: float
    seller_discount_amount: float
    meli_cofunded_amount: float
    meli_commission_fee: float
    shipping_cost_seller: float
    packaging_cost: float
    sat_iva_retention: float  # 8% retención SAT plataforma digital
    sat_isr_retention: float  # 1% retención SAT plataforma digital
    total_deductions: float
    net_profit: float
    net_margin_pct: float
    is_viable: bool
    viability_alert: str | None = None


# ---------------------------------------------------------------------------
# POSTULACIÓN OFICIAL A PROMOCIONES Y CAMPAÑAS
# ---------------------------------------------------------------------------

class PromotionOptinRequest(BaseModel):
    """Solicitud de vinculación de un producto a una campaña oficial de Mercado Libre."""
    promotion_id: str = Field(..., description="ID oficial de la campaña en MeLi")
    promotion_type: str = Field(..., description="Tipo de campaña (DEAL, LIGHTNING, SMART, etc.)")
    deal_price: float = Field(..., gt=0.0, description="Precio de oferta acordado para la campaña")
    validate_viability: bool = Field(True, description="Verificar que el margen no viole reglas comerciales antes de postular")


class PromotionOptinResponse(BaseModel):
    """Confirmación oficial de activación en Mercado Libre."""
    meli_item_id: str
    promotion_id: str
    deal_price: float
    status: str
    confirmed_by_meli: bool
    message: str


# ---------------------------------------------------------------------------
# ANÁLISIS DE COMPETENCIA Y RECOMENDACIONES COMERCIALES
# ---------------------------------------------------------------------------

class CompetitorBenchmarkResponse(BaseModel):
    """Análisis comparativo de mercado y Buy Box."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    meli_item_id: str
    seller_sku: str
    catalog_product_id: str | None = None
    our_price: float
    buy_box_price: float | None = None
    min_competitor_price: float | None = None
    max_competitor_price: float | None = None
    competitor_count: int
    our_status: str  # winning, losing, tied, not_catalog
    suggested_price: float | None = None
    estimated_margin_at_suggested: float | None = None
    last_checked_at: datetime


class CommercialRecommendationResponse(BaseModel):
    """Oportunidad comercial detectada por el motor inteligente del ERP."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    meli_item_id: str
    sku: str
    recommendation_type: str
    title: str
    description: str
    current_price: float
    recommended_price: float
    projected_margin_pct: float
    projected_profit: float
    promotion_id: str | None = None
    promotion_name: str | None = None
    status: str
    created_at: datetime

"""Modelos del Administrador Comercial: Reglas de Precios, Historial, Programación, Competencia y Recomendaciones."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
import uuid

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import GUID, Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.meli_account import MeliAccount
    from src.models.product import Product, ProductVariant
    from src.models.tenant import Company


class CommercialRule(Base, TimestampMixin):
    """
    Reglas comerciales configurables para automatización y salvaguarda de precios y promociones.
    
    Protege la rentabilidad del negocio:
    - min_price: Precio piso absoluto (ninguna automatización o descuento puede bajar de aquí).
    - min_margin_pct: Margen neto mínimo porcentual exigido tras comisiones MeLi, flete y retenciones SAT.
    - max_discount_pct: Porcentaje máximo de descuento permitido.
    - target_price: Precio objetivo deseable para maximizar ventas.
    - max_daily_changes: Límite de modificaciones de precio al día para evitar rate limits o volatilidad.
    - allowed_hours_start / end: Ventana horaria permitida para aplicar ajustes automáticos.
    - excluded_skus: Lista de SKUs que quedan protegidos y exentos de rebajas automáticas.
    - promotional_budget: Presupuesto total asignado para absorción de descuentos.
    - budget_consumed: Monto acumulado de descuentos absorbidos.
    """

    __tablename__ = "commercial_rules"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meli_account_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("meli_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Restricciones de Precios y Rentabilidad
    min_price: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    min_margin_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=15.0, nullable=False)  # e.g. 15%
    max_discount_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=30.0, nullable=False)  # e.g. 30%
    target_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    # Control de Frecuencia y Horarios
    max_daily_changes: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    allowed_hours_start: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0 a 23 hrs
    allowed_hours_end: Mapped[int | None] = mapped_column(Integer, nullable=True)    # 0 a 23 hrs

    # Exclusiones y Presupuesto
    excluded_skus: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    promotional_budget: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    budget_consumed: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    company: Mapped["Company"] = relationship("Company")
    meli_account: Mapped["MeliAccount | None"] = relationship("MeliAccount")

    __table_args__ = (
        Index("ix_commercial_rules_company", "company_id", "is_active"),
    )


class PriceHistory(Base):
    """
    Registro histórico y de auditoría de cada cambio de precio.
    Conserva origen, fecha, precios anteriores y permite revertir cambios cuando sea técnicamente posible.
    """

    __tablename__ = "price_history"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True, index=True
    )
    meli_item_id: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    meli_variation_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    
    previous_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    new_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    change_reason: Mapped[str] = mapped_column(
        String(50), default="manual", nullable=False
    )  # manual, rule_auto, scheduled, competitor_match, promotion_optin, restored

    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("commercial_rules.id", ondelete="SET NULL"), nullable=True
    )
    can_restore: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )

    company: Mapped["Company"] = relationship("Company")
    product: Mapped["Product | None"] = relationship("Product")
    variant: Mapped["ProductVariant | None"] = relationship("ProductVariant")
    rule: Mapped["CommercialRule | None"] = relationship("CommercialRule")

    __table_args__ = (
        Index("ix_price_history_item_date", "meli_item_id", "created_at"),
        Index("ix_price_history_company_date", "company_id", "created_at"),
    )


class ScheduledPriceChange(Base, TimestampMixin):
    """
    Programación de precios a futuro con fecha de aplicación y fecha opcional de reversión automática.
    """

    __tablename__ = "scheduled_price_changes"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True, index=True
    )
    meli_item_id: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    meli_variation_id: Mapped[str | None] = mapped_column(String(30), nullable=True)

    original_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    target_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revert_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # pending, applied, reverted, cancelled, failed
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False, index=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reverted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    company: Mapped["Company"] = relationship("Company")
    product: Mapped["Product | None"] = relationship("Product")
    variant: Mapped["ProductVariant | None"] = relationship("ProductVariant")

    __table_args__ = (
        Index("ix_scheduled_prices_status_time", "status", "scheduled_at"),
    )


class CompetitorBenchmark(Base, TimestampMixin):
    """
    Análisis de competencia con datos autorizados de Mercado Libre México (Catálogo y Buy Box).
    """

    __tablename__ = "competitor_benchmarks"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    meli_item_id: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    seller_sku: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    catalog_product_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    our_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    buy_box_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    min_competitor_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    max_competitor_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    competitor_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # winning (Ganando Buy Box), losing (Perdiendo), tied (Empatado), not_catalog (Publicación normal)
    our_status: Mapped[str] = mapped_column(String(30), default="winning", nullable=False, index=True)
    suggested_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    estimated_margin_at_suggested: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    company: Mapped["Company"] = relationship("Company")
    product: Mapped["Product | None"] = relationship("Product")

    __table_args__ = (
        Index("ix_competitor_benchmarks_company_status", "company_id", "our_status"),
    )


class CommercialRecommendation(Base, TimestampMixin):
    """
    Detección de oportunidades comerciales y recomendaciones de rentabilidad.
    """

    __tablename__ = "commercial_recommendations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meli_item_id: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)

    # price_reduction (para ganar Buy Box), join_campaign (postular a campaña activa),
    # price_increase (oportunidad de captura de margen), protect_margin (alerta de margen bajo)
    recommendation_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    current_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    recommended_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    projected_margin_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    projected_profit: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    promotion_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    promotion_name: Mapped[str | None] = mapped_column(String(150), nullable=True)

    # pending, applied, dismissed
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False, index=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped["Company"] = relationship("Company")

    __table_args__ = (
        Index("ix_recommendations_company_status", "company_id", "status"),
    )

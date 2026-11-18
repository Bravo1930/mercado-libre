"""Modelos de Estructura de Costos, Auditoría Financiera y Retenciones Fiscales (SAT México)."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import GUID, Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.order import Order
    from src.models.tenant import Company


class CostStructure(Base, TimestampMixin):
    """Reglas de costos fijos, empaque y regímenes fiscales por empresa."""

    __tablename__ = "cost_structures"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), default="Predeterminada")
    packaging_cost_fixed: Mapped[float] = mapped_column(Numeric(10, 2), default=15.00)  # Caja, cinta, etiquetas
    labor_handling_cost: Mapped[float] = mapped_column(Numeric(10, 2), default=10.00)   # Mano de obra empaque
    sat_iva_retention_rate: Mapped[float] = mapped_column(Numeric(5, 4), default=0.0800)  # 8% retención IVA estándar
    sat_isr_retention_rate: Mapped[float] = mapped_column(Numeric(5, 4), default=0.0100)  # 1% retención ISR RESICO
    is_default: Mapped[bool] = mapped_column(Boolean, default=True)

    company: Mapped["Company"] = relationship("Company")


class ProfitabilityAudit(Base, TimestampMixin):
    """Auditoría financiera granular de cada orden vendida en Mercado Libre."""

    __tablename__ = "profitability_audits"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("orders.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    gross_sale_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    cogs_total: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    meli_commission_fee: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    shipping_cost_seller: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    packaging_cost: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)

    # Retenciones Fiscales Oficiales de Plataformas México (SAT)
    sat_iva_retention: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    sat_isr_retention: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)

    net_profit: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    net_margin_pct: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)

    order: Mapped["Order"] = relationship("Order", back_populates="profitability")

    __table_args__ = (
        Index("ix_profitability_audits_order_margin", "order_id", "net_margin_pct"),
    )

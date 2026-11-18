"""Modelos de Órdenes de Venta, Envíos y Auditoría de Rentabilidad Neta."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class Order(Base):
    """Órdenes de venta sincronizadas desde Mercado Libre."""

    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    meli_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meli_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meli_order_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # paid, cancelled, etc.
    buyer_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    buyer_nickname: Mapped[str] = mapped_column(String(100), nullable=True)
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    paid_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency_id: Mapped[str] = mapped_column(String(10), default="MXN")
    shipping_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    shipping_status: Mapped[str] = mapped_column(String(50), nullable=True)

    date_created_meli: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    meli_account: Mapped["MeliAccount"] = relationship("MeliAccount", back_populates="orders")
    profitability: Mapped["ProfitabilityAudit"] = relationship(
        "ProfitabilityAudit", back_populates="order", uselist=False, cascade="all, delete-orphan"
    )


class ProfitabilityAudit(Base):
    """Desglose financiero exacto de la venta (Rentabilidad Neta y Retenciones SAT México)."""

    __tablename__ = "profitability_audits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    gross_sale_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    cogs_total: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0)
    meli_commission_fee: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0)
    shipping_cost_seller: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0)

    # Retenciones Fiscales Oficiales de Plataformas Tecnológicas México
    sat_iva_retention: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0)  # 8% o 16%
    sat_isr_retention: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0)  # 1% o 20%

    net_profit: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    net_margin_pct: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)

    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    order: Mapped["Order"] = relationship("Order", back_populates="profitability")

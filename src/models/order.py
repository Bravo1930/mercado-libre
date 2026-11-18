"""Modelos de Ventas, Pedidos, Partidas, Línea de Tiempo y Reclamos de Mercado Libre México."""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from src.models.base import GUID, Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.cost import ProfitabilityAudit
    from src.models.meli_account import MeliAccount
    from src.models.payment import Payment
    from src.models.product import Product, ProductVariant
    from src.models.shipment import Shipment


class Order(Base, TimestampMixin):
    """
    Venta / Pedido oficial sincronizado desde Mercado Libre México.
    Centro neurálgico del ERP de ventas con trazabilidad completa de pagos,
    envíos, rentabilidad, línea de tiempo, cancelaciones y reclamos.
    """

    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    meli_account_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("meli_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meli_order_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    order_number: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    # Estado general del pedido: paid, confirmed, processing, shipped, delivered, cancelled, returned
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Datos del Comprador
    buyer_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    buyer_nickname: Mapped[str | None] = mapped_column(String(100), nullable=True)
    buyer_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    buyer_email: Mapped[str | None] = mapped_column(String(150), nullable=True)
    buyer_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    buyer_document: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Estados de Pago y Envío
    payment_status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False, index=True)
    shipment_status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False, index=True)

    # Desglose Financiero de la Venta
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)  # Importe Bruto
    paid_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    discount_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    currency_id: Mapped[str] = mapped_column(String(10), default="MXN", nullable=False)
    date_created_meli: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    # Comisiones, Costos y Ganancia Estimada
    meli_fee_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    shipping_cost_seller: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    cogs_total: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    estimated_profit: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    net_margin_pct: Mapped[float] = mapped_column(Numeric(6, 2), default=0.0, nullable=False)

    # Cancelaciones
    cancel_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cancel_responsible: Mapped[str | None] = mapped_column(String(50), nullable=True)  # buyer, seller, marketplace
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Reclamos y Devoluciones
    claim_status: Mapped[str] = mapped_column(String(50), default="none", nullable=False, index=True)  # none, open, in_review, closed
    return_status: Mapped[str] = mapped_column(String(50), default="none", nullable=False, index=True)  # none, pending, received_good, received_damaged

    # Comparativa MeLi vs ERP interno
    comparison_details: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relaciones
    meli_account: Mapped["MeliAccount"] = relationship("MeliAccount", back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(
        "Payment", back_populates="order", cascade="all, delete-orphan"
    )
    shipments: Mapped[list["Shipment"]] = relationship(
        "Shipment", back_populates="order", cascade="all, delete-orphan"
    )
    profitability: Mapped["ProfitabilityAudit"] = relationship(
        "ProfitabilityAudit", back_populates="order", uselist=False, cascade="all, delete-orphan"
    )
    timelines: Mapped[list["OrderTimeline"]] = relationship(
        "OrderTimeline", back_populates="order", cascade="all, delete-orphan", order_by="OrderTimeline.created_at.asc()"
    )
    claims: Mapped[list["OrderClaim"]] = relationship(
        "OrderClaim", back_populates="order", cascade="all, delete-orphan", order_by="OrderClaim.created_at.asc()"
    )

    __table_args__ = (
        Index("ix_orders_account_status_date", "meli_account_id", "status", "date_created_meli"),
        Index("ix_orders_pay_ship_status", "payment_status", "shipment_status"),
        Index("ix_orders_claims_returns", "claim_status", "return_status"),
    )


class OrderItem(Base, TimestampMixin):
    """Partida o producto individual dentro de una orden de venta."""

    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True, index=True
    )

    meli_item_id: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    meli_variation_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    seller_sku: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    variant_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    discount_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    sale_fee: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    cogs_unit: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    net_profit: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)

    order: Mapped["Order"] = relationship("Order", back_populates="items")
    product: Mapped["Product | None"] = relationship("Product")
    variant: Mapped["ProductVariant | None"] = relationship("ProductVariant")


class OrderTimeline(Base, TimestampMixin):
    """
    Línea de tiempo histórica y registro cronológico de eventos de la orden.
    Garantiza trazabilidad de cada cambio de estado, reserva, despacho o cancelación.
    """

    __tablename__ = "order_timelines"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # Tipos: ORDER_CREATED, PAYMENT_APPROVED, STOCK_RESERVED, LABEL_PRINTED, SHIPPED_CARRIER,
    # DELIVERED, ORDER_CANCELLED, STOCK_RELEASED, CLAIM_OPENED, RETURN_RECEIVED, REFUNDED
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    actor: Mapped[str] = mapped_column(String(100), default="Sistema ERP", nullable=False)
    metadata_info: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )

    order: Mapped["Order"] = relationship("Order", back_populates="timelines")

    __table_args__ = (
        Index("ix_order_timelines_order_created", "order_id", "created_at"),
    )


class OrderClaim(Base, TimestampMixin):
    """Registro de reclamos, mediaciones y disputas post-venta de Mercado Libre."""

    __tablename__ = "order_claims"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meli_claim_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    claim_type: Mapped[str] = mapped_column(String(50), default="return", nullable=False)  # return, not_received, defective, regret
    stage: Mapped[str] = mapped_column(String(50), default="claim", nullable=False)  # claim, dispute, resolution
    status: Mapped[str] = mapped_column(String(50), default="open", nullable=False, index=True)  # open, in_review, closed
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    disputed_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    resolution: Mapped[str | None] = mapped_column(String(255), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    order: Mapped["Order"] = relationship("Order", back_populates="claims")

"""Modelos de Ventas, Pedidos y Partidas de Mercado Libre México."""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import GUID, Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.cost import ProfitabilityAudit
    from src.models.meli_account import MeliAccount
    from src.models.payment import Payment
    from src.models.shipment import Shipment


class Order(Base, TimestampMixin):
    """Venta / Pedido oficial sincronizado desde Mercado Libre México."""

    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    meli_account_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("meli_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meli_order_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # paid, cancelled, etc.
    buyer_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    buyer_nickname: Mapped[str] = mapped_column(String(100), nullable=True)
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    paid_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency_id: Mapped[str] = mapped_column(String(10), default="MXN", nullable=False)
    date_created_meli: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

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

    __table_args__ = (
        Index("ix_orders_account_status_date", "meli_account_id", "status", "date_created_meli"),
    )


class OrderItem(Base, TimestampMixin):
    """Partida o producto individual dentro de una orden de venta."""

    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meli_item_id: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    meli_variation_id: Mapped[str] = mapped_column(String(30), nullable=True)
    seller_sku: Mapped[str] = mapped_column(String(100), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    sale_fee: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)

    order: Mapped["Order"] = relationship("Order", back_populates="items")

"""Modelo de Pagos y Transacciones de Mercado Pago / Mercado Libre."""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import GUID, Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.order import Order


class Payment(Base, TimestampMixin):
    """Detalle de pago de una orden procesado vía Mercado Pago."""

    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meli_payment_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # approved, in_process, rejected
    status_detail: Mapped[str] = mapped_column(String(100), nullable=True)  # accredited, etc.
    payment_type: Mapped[str] = mapped_column(String(50), nullable=True)  # credit_card, account_money, ticket
    payment_method_id: Mapped[str] = mapped_column(String(50), nullable=True)  # visa, master, oxxo
    transaction_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    marketplace_fee: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    date_approved: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    order: Mapped["Order"] = relationship("Order", back_populates="payments")

    __table_args__ = (
        Index("ix_payments_order_status", "order_id", "status"),
    )

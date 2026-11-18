"""Modelo de Envíos y Logística de Mercado Envíos México."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import GUID, Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.order import Order


class Shipment(Base, TimestampMixin):
    """Información logística y de despacho de una orden en Mercado Libre."""

    __tablename__ = "shipments"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meli_shipment_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # pending, ready_to_ship, shipped, delivered, not_delivered, cancelled
    substatus: Mapped[str] = mapped_column(String(50), nullable=True)  # waiting_for_carrier, printed, etc.
    logistic_type: Mapped[str] = mapped_column(
        String(50), default="fulfillment"
    )  # fulfillment (Full), drop_off, self_service (Flex), cross_docking
    tracking_number: Mapped[str] = mapped_column(String(100), nullable=True, index=True)
    carrier_name: Mapped[str] = mapped_column(String(100), nullable=True)  # DHL, FedEx, Estafeta, Mercado Envíos
    shipping_cost_total: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    shipping_cost_seller: Mapped[float] = mapped_column(
        Numeric(12, 2), default=0.0, nullable=False
    )  # Costo asumido por el vendedor
    label_local_path: Mapped[str] = mapped_column(String(255), nullable=True)  # Ruta local a la guía PDF o ZPL2

    order: Mapped["Order"] = relationship("Order", back_populates="shipments")

    __table_args__ = (
        Index("ix_shipments_status_logistic", "status", "logistic_type"),
    )

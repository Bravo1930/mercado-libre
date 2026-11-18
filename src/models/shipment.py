"""Modelo de Envíos, Despachos, Trazabilidad y Control de Etiquetas de Mercado Envíos México."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
import uuid

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import GUID, Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.order import Order
    from src.models.tenant import Company


class Shipment(Base, TimestampMixin):
    """
    Información logística, trazabilidad y control de despacho de una orden en Mercado Libre México.
    
    Permite clasificar operativamente los pedidos en:
    - pending: pendiente de preparación o empaque (etiqueta no impresa o lista para imprimir)
    - prepared: paquete preparado, empaquetado y con etiqueta oficial impresa
    - dispatched: recolectado o entregado en agencia de envíos / en tránsito hacia comprador
    - error: problemas de despacho, etiquetas expiradas, retención o demoras
    """

    __tablename__ = "shipments"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meli_shipment_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)

    # Estado oficial de Mercado Libre: pending, ready_to_ship, shipped, delivered, not_delivered, cancelled
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    substatus: Mapped[str | None] = mapped_column(String(50), nullable=True)  # waiting_for_carrier, printed, ready_to_print

    # Estado operativo interno del centro de logística
    dispatch_status: Mapped[str] = mapped_column(
        String(50), default="pending", nullable=False, index=True
    )  # pending, prepared, dispatched, error

    # Modalidad logística oficial de Mercado Envíos
    logistic_type: Mapped[str] = mapped_column(
        String(50), default="fulfillment", nullable=False, index=True
    )  # fulfillment (Full CEDIS MeLi), cross_docking (Colecta), drop_off (Agencias MeLi), self_service (Mercado Envíos Flex)

    # Paquetería y rastreo
    tracking_number: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    tracking_method: Mapped[str | None] = mapped_column(String(50), nullable=True)  # standard, express, same_day
    carrier_name: Mapped[str | None] = mapped_column(String(100), nullable=True)  # DHL, FedEx, Estafeta, Paquetexpress, MeLi Logistics

    # Desglose de costos de flete
    shipping_cost_total: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    shipping_cost_seller: Mapped[float] = mapped_column(
        Numeric(12, 2), default=0.0, nullable=False
    )  # Costo asumido por el vendedor (envío gratis)

    # Control de impresión de etiquetas oficiales
    print_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_printed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_printed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    label_local_path: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Almacenamiento local del PDF/ZPL2

    # Fechas de promesa y límite de despacho (SLA)
    estimated_delivery_limit: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Direcciones e información de entrega de MeLi
    sender_address: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    receiver_address: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    shipping_option: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Relaciones
    order: Mapped["Order"] = relationship("Order", back_populates="shipments")
    company: Mapped["Company | None"] = relationship("Company")
    print_logs: Mapped[list["ShipmentPrintLog"]] = relationship(
        "ShipmentPrintLog",
        back_populates="shipment",
        cascade="all, delete-orphan",
        order_by="ShipmentPrintLog.created_at.desc()",
    )

    __table_args__ = (
        Index("ix_shipments_status_logistic", "status", "logistic_type"),
        Index("ix_shipments_company_dispatch", "company_id", "dispatch_status"),
    )


class ShipmentPrintLog(Base):
    """
    Auditoría estricta de impresiones y reimpresiones de etiquetas de envío oficiales.
    Controla reimpresiones exigiendo el motivo para evitar duplicidad y extravío de paquetes.
    """

    __tablename__ = "shipment_print_logs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    shipment_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    
    print_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1: Primera impresión, >1: Reimpresión
    is_reprint: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reprint_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Motivo obligatorio si es_reprint
    format: Mapped[str] = mapped_column(String(20), default="pdf", nullable=False)  # pdf, zpl2
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relaciones
    shipment: Mapped["Shipment"] = relationship("Shipment", back_populates="print_logs")
    company: Mapped["Company"] = relationship("Company")

    __table_args__ = (
        Index("ix_shipment_print_logs_shipment", "shipment_id", "created_at"),
        Index("ix_shipment_print_logs_company", "company_id", "is_reprint"),
    )

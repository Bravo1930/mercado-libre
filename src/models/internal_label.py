"""Modelos para Plantillas y Lotes de Impresión de Etiquetas Internas de Almacén y Productos."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
import uuid

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import GUID, Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.order import Order
    from src.models.product import Product, ProductVariant
    from src.models.tenant import Company


class InternalLabelTemplate(Base, TimestampMixin):
    """
    Plantillas configurables para etiquetas internas de almacén, productos y surtido.
    Formatos compatibles con:
    - Impresoras térmicas de rollo continuo (Zebra, TSC, Xprinter, Honeywell) de 100x150 mm y 50x30 mm.
    - Impresoras convencionales de oficina (láser / inyección) en hojas carta o A4 (cuadrícula 3x10 tipo Avery).
    - Impresoras joyeras / de cables (40x20 mm).
    """

    __tablename__ = "internal_label_templates"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # thermal_4x6 (100x150 mm), thermal_50x30 (50x30 mm), sheet_letter_30 (Avery 30 por hoja), jewelry_mini (40x20 mm)
    template_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    width_mm: Mapped[float] = mapped_column(Float, nullable=False)
    height_mm: Mapped[float] = mapped_column(Float, nullable=False)
    columns: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    rows: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Elementos a incluir en la etiqueta interna
    include_barcode: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    barcode_type: Mapped[str] = mapped_column(String(20), default="code128", nullable=False)  # code128, ean13
    include_qr: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    include_sku: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    include_product_name: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    include_variant: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    include_location: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    include_price: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    company: Mapped["Company"] = relationship("Company")

    __table_args__ = (
        Index("ix_internal_templates_company_type", "company_id", "template_type"),
    )


class InternalLabelPrintBatch(Base, TimestampMixin):
    """
    Registro y trazabilidad de lotes de etiquetas internas impresas masivamente.
    Permite auditar reimpresiones de etiquetas de productos y de surtido de pedidos.
    """

    __tablename__ = "internal_label_batches"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    
    batch_name: Mapped[str] = mapped_column(String(150), nullable=False)
    template_type: Mapped[str] = mapped_column(String(50), nullable=False)
    total_labels: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    output_format: Mapped[str] = mapped_column(String(20), default="html", nullable=False)  # html, zpl, pdf
    
    # Detalle de los artículos impresos [{variant_id, sku, name, quantity, location, price}]
    items_payload: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)

    company: Mapped["Company"] = relationship("Company")
    order: Mapped["Order | None"] = relationship("Order")

    __table_args__ = (
        Index("ix_internal_batches_company_created", "company_id", "created_at"),
    )

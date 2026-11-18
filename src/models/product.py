"""Modelos para Catálogo Maestro de Productos, SKUs e Ítems de Mercado Libre."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class Product(Base):
    """Producto maestro interno (SKU) gestionado por la empresa."""

    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sku: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=True)

    # Costos e Inventario Central
    cogs_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0)  # Cost of Goods Sold en MXN
    current_stock: Mapped[int] = mapped_column(Integer, default=0)
    safety_stock: Mapped[int] = mapped_column(Integer, default=5)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    company: Mapped["Company"] = relationship("Company", back_populates="products")
    listings: Mapped[list["MeliListing"]] = relationship(
        "MeliListing", back_populates="product", cascade="all, delete-orphan"
    )


class MeliListing(Base):
    """Mapeo a una publicación oficial activa en Mercado Libre México (MLMxxxxxxxxx)."""

    __tablename__ = "meli_listings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    meli_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meli_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meli_item_id: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)  # e.g. MLM123456789
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency_id: Mapped[str] = mapped_column(String(10), default="MXN")
    available_quantity: Mapped[int] = mapped_column(Integer, default=0)
    listing_type_id: Mapped[str] = mapped_column(String(50), default="gold_special")  # gold_special (Clásica), gold_pro (Premium)
    status: Mapped[str] = mapped_column(String(30), default="active")  # active, paused, closed
    logistic_type: Mapped[str] = mapped_column(String(50), default="fulfillment")  # drop_off, cross_docking, fulfillment (Full), self_service (Flex)
    sync_stock_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    meli_account: Mapped["MeliAccount"] = relationship("MeliAccount", back_populates="listings")
    product: Mapped["Product"] = relationship("Product", back_populates="listings")

"""Modelos de Productos Maestros, Variantes y SKUs de Mercado Libre."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import GUID, Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.meli_account import MeliAccount
    from src.models.tenant import Company
    from src.models.warehouse import Inventory


class Product(Base, TimestampMixin):
    """Producto maestro en el catálogo interno de la empresa."""

    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    brand: Mapped[str] = mapped_column(String(100), nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    company: Mapped["Company"] = relationship("Company", back_populates="products")
    variants: Mapped[list["ProductVariant"]] = relationship(
        "ProductVariant", back_populates="product", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_products_company_name", "company_id", "name"),
    )


class ProductVariant(Base, TimestampMixin):
    """Variante específica de un producto (color, talla, modelo, código EAN)."""

    __tablename__ = "product_variants"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    variant_name: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "Negro / Talla M"
    sku: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    barcode_ean: Mapped[str] = mapped_column(String(50), nullable=True, index=True)
    cogs_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)  # Costo de adquisición

    product: Mapped["Product"] = relationship("Product", back_populates="variants")
    skus: Mapped[list["ProductSKU"]] = relationship(
        "ProductSKU", back_populates="variant", cascade="all, delete-orphan"
    )
    inventories: Mapped[list["Inventory"]] = relationship(
        "Inventory", back_populates="variant", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_product_variants_product_sku", "product_id", "sku", unique=True),
    )


class ProductSKU(Base, TimestampMixin):
    """Mapeo directo entre una variante interna y una publicación en Mercado Libre."""

    __tablename__ = "product_skus"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    meli_account_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("meli_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    variant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meli_item_id: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # MLM123456789
    meli_variation_id: Mapped[str] = mapped_column(String(30), nullable=True)  # Si tiene variación en MeLi
    seller_sku: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    listing_type_id: Mapped[str] = mapped_column(String(50), default="gold_special")  # Clásica / Premium
    logistic_type: Mapped[str] = mapped_column(String(50), default="fulfillment")  # fulfillment, drop_off, flex
    status: Mapped[str] = mapped_column(String(30), default="active")  # active, paused, closed
    sync_stock_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    meli_account: Mapped["MeliAccount"] = relationship("MeliAccount", back_populates="skus")
    variant: Mapped["ProductVariant"] = relationship("ProductVariant", back_populates="skus")

    __table_args__ = (
        Index("ix_product_skus_meli_item", "meli_account_id", "meli_item_id", "meli_variation_id", unique=True),
    )

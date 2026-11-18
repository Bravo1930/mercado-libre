"""Modelos de Productos Maestros, Variantes y SKUs de Mercado Libre."""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, ForeignKey, Index, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import GUID, Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.meli_account import MeliAccount
    from src.models.supplier import Supplier
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
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    category: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    category_code: Mapped[str | None] = mapped_column(String(50), nullable=True)  # Clave SAT o MeLi Category ID
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    short_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    unit_of_measure: Mapped[str] = mapped_column(String(20), default="H87")  # H87 = Pieza (SAT)

    # Precios y Costos
    cost_price: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    last_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    sale_price: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    wholesale_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    min_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    # Proveedor predeterminado de mercancía
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Dimensiones y Peso
    weight_kg: Mapped[float] = mapped_column(Numeric(8, 3), default=0.0, nullable=False)
    length_cm: Mapped[float] = mapped_column(Numeric(8, 2), default=0.0, nullable=False)
    width_cm: Mapped[float] = mapped_column(Numeric(8, 2), default=0.0, nullable=False)
    height_cm: Mapped[float] = mapped_column(Numeric(8, 2), default=0.0, nullable=False)

    # Ubicación física en almacén
    warehouse_location: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Fotografías / Galería (Lista de URLs o nombres de archivo)
    images: Mapped[list[str]] = mapped_column(JSON, default=list)

    # Estado (Activo / Desactivado)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    company: Mapped["Company"] = relationship("Company", back_populates="products")
    supplier: Mapped["Supplier | None"] = relationship("Supplier")
    variants: Mapped[list["ProductVariant"]] = relationship(
        "ProductVariant", back_populates="product", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_products_company_name", "company_id", "name"),
        Index("ix_products_company_brand", "company_id", "brand"),
        Index("ix_products_company_category", "company_id", "category"),
    )


class ProductVariant(Base, TimestampMixin):
    """Variante específica de un producto (color, talla, modelo, código EAN, SKU)."""

    __tablename__ = "product_variants"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    variant_name: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "Negro / Talla M"
    sku: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    barcode_ean: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    cogs_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)  # Costo de adquisición
    sale_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)  # Precio si varía del padre
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # {"color": "Negro", "talla": "M"}
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    product: Mapped["Product"] = relationship("Product", back_populates="variants")
    skus: Mapped[list["ProductSKU"]] = relationship(
        "ProductSKU", back_populates="variant", cascade="all, delete-orphan"
    )
    inventories: Mapped[list["Inventory"]] = relationship(
        "Inventory", back_populates="variant", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_product_variants_product_sku", "product_id", "sku", unique=True),
        Index("ix_product_variants_company_sku", "company_id", "sku"),
        Index("ix_product_variants_barcode", "barcode_ean"),
    )


class ProductSKU(Base, TimestampMixin):
    """Mapeo directo entre una variante interna y una publicación en Mercado Libre."""

    __tablename__ = "product_skus"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    meli_account_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("meli_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    variant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meli_item_id: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # MLM123456789
    meli_variation_id: Mapped[str | None] = mapped_column(String(30), nullable=True)  # Si tiene variación en MeLi
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

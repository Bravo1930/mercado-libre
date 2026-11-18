"""Esquemas para Catálogo Maestro de Productos, Variantes y SKUs MeLi."""

import uuid
from datetime import datetime
from pydantic import Field

from src.schemas.common import BaseSchema


class ProductVariantCreate(BaseSchema):
    variant_name: str = Field(..., min_length=1, max_length=100)
    sku: str = Field(..., min_length=1, max_length=100, description="SKU único interno")
    barcode_ean: str | None = None
    cogs_cost: float = Field(default=0.0, ge=0.0, description="Costo de adquisición en MXN")


class ProductVariantResponse(BaseSchema):
    id: uuid.UUID
    product_id: uuid.UUID
    variant_name: str
    sku: str
    barcode_ean: str | None
    cogs_cost: float
    created_at: datetime


class ProductCreate(BaseSchema):
    company_id: uuid.UUID
    name: str = Field(..., min_length=2, max_length=255)
    brand: str | None = None
    category: str | None = None
    description: str | None = None
    variants: list[ProductVariantCreate] = Field(default_factory=list)


class ProductResponse(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    brand: str | None
    category: str | None
    description: str | None
    is_active: bool
    created_at: datetime
    variants: list[ProductVariantResponse] = Field(default_factory=list)


class ProductSKUCreate(BaseSchema):
    meli_account_id: uuid.UUID
    variant_id: uuid.UUID
    meli_item_id: str = Field(..., pattern=r"^MLM\d+$", description="ID de publicación MeLi (e.g. MLM123456789)")
    meli_variation_id: str | None = None
    seller_sku: str
    price: float = Field(..., gt=0.0)
    listing_type_id: str = "gold_special"
    logistic_type: str = "fulfillment"


class ProductSKUResponse(BaseSchema):
    id: uuid.UUID
    meli_account_id: uuid.UUID
    variant_id: uuid.UUID
    meli_item_id: str
    meli_variation_id: str | None
    seller_sku: str
    price: float
    listing_type_id: str
    logistic_type: str
    status: str
    sync_stock_enabled: bool
    created_at: datetime

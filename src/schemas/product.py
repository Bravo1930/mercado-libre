"""Esquemas Pydantic para el Catálogo Maestro de Productos, Variantes y SKUs de Mercado Libre."""

import uuid
from datetime import datetime
from typing import Any
from pydantic import Field

from src.schemas.common import BaseSchema


# ------------------------------------------------------------------------------
# 1. ESQUEMAS DE VARIANTES
# ------------------------------------------------------------------------------
class ProductVariantCreate(BaseSchema):
    variant_name: str = Field(..., min_length=1, max_length=100, description="Nombre de la variante (e.g. Negro / M)")
    sku: str = Field(..., min_length=1, max_length=100, description="SKU único en la empresa")
    barcode_ean: str | None = Field(default=None, max_length=50, description="Código de barras EAN-13 o UPC")
    cogs_cost: float = Field(default=0.0, ge=0.0, description="Costo de adquisición en MXN")
    sale_price: float | None = Field(default=None, ge=0.0, description="Precio de venta si difiere del maestro")
    attributes: dict[str, Any] = Field(default_factory=dict, description="Atributos JSON (color, talla, capacidad)")
    is_active: bool = Field(default=True, description="Estado de la variante")


class ProductVariantUpdate(BaseSchema):
    variant_name: str | None = Field(default=None, min_length=1, max_length=100)
    sku: str | None = Field(default=None, min_length=1, max_length=100)
    barcode_ean: str | None = Field(default=None, max_length=50)
    cogs_cost: float | None = Field(default=None, ge=0.0)
    sale_price: float | None = Field(default=None, ge=0.0)
    attributes: dict[str, Any] | None = None
    is_active: bool | None = None


class ProductVariantResponse(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID | None = None
    product_id: uuid.UUID
    variant_name: str
    sku: str
    barcode_ean: str | None = None
    cogs_cost: float
    sale_price: float | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    is_active: bool
    created_at: datetime


# ------------------------------------------------------------------------------
# 2. ESQUEMAS DE PRODUCTO MAESTRO
# ------------------------------------------------------------------------------
class ProductCreate(BaseSchema):
    company_id: uuid.UUID
    name: str = Field(..., min_length=2, max_length=255, description="Nombre o título del producto maestro")
    brand: str | None = Field(default=None, max_length=100, description="Marca del producto")
    model: str | None = Field(default=None, max_length=100, description="Modelo del producto")
    category: str | None = Field(default=None, max_length=150, description="Categoría comercial o jerarquía")
    category_code: str | None = Field(default=None, max_length=50, description="Clave SAT o MeLi Category ID")
    description: str | None = Field(default=None, description="Descripción técnica o comercial completa")
    short_description: str | None = Field(default=None, max_length=500, description="Descripción corta o extracto")
    unit_of_measure: str = Field(default="H87", max_length=20, description="Clave de unidad SAT (H87 = Pieza)")

    # Precios y Costos
    cost_price: float = Field(default=0.0, ge=0.0, description="Costo base de adquisición en MXN")
    last_cost: float = Field(default=0.0, ge=0.0, description="Último costo de compra a proveedor en MXN")
    sale_price: float = Field(default=0.0, ge=0.0, description="Precio de venta sugerido al público en MXN")
    wholesale_price: float | None = Field(default=None, ge=0.0, description="Precio de mayoreo en MXN")
    min_price: float | None = Field(default=None, ge=0.0, description="Precio mínimo autorizado en MXN")

    # Proveedor
    supplier_id: uuid.UUID | None = Field(default=None, description="Proveedor predeterminado")

    # Dimensiones y Peso
    weight_kg: float = Field(default=0.0, ge=0.0, description="Peso bruto en kilogramos")
    length_cm: float = Field(default=0.0, ge=0.0, description="Largo en centímetros")
    width_cm: float = Field(default=0.0, ge=0.0, description="Ancho en centímetros")
    height_cm: float = Field(default=0.0, ge=0.0, description="Alto en centímetros")

    # Ubicación física en almacén
    warehouse_location: str | None = Field(default=None, max_length=100, description="Ubicación física (rack, pasillo, bin)")

    # Fotografías
    images: list[str] = Field(default_factory=list, description="Lista de URLs o nombres de archivos de fotos")

    # Estado
    is_active: bool = Field(default=True, description="Estatus activo/inactivo del producto")

    # Variantes anidadas opcionales
    variants: list[ProductVariantCreate] = Field(default_factory=list, description="Variantes iniciales a crear")


class ProductUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    brand: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=150)
    category_code: str | None = Field(default=None, max_length=50)
    description: str | None = None
    short_description: str | None = Field(default=None, max_length=500)
    unit_of_measure: str | None = Field(default=None, max_length=20)

    cost_price: float | None = Field(default=None, ge=0.0)
    last_cost: float | None = Field(default=None, ge=0.0)
    sale_price: float | None = Field(default=None, ge=0.0)
    wholesale_price: float | None = Field(default=None, ge=0.0)
    min_price: float | None = Field(default=None, ge=0.0)

    supplier_id: uuid.UUID | None = None

    weight_kg: float | None = Field(default=None, ge=0.0)
    length_cm: float | None = Field(default=None, ge=0.0)
    width_cm: float | None = Field(default=None, ge=0.0)
    height_cm: float | None = Field(default=None, ge=0.0)

    warehouse_location: str | None = Field(default=None, max_length=100)
    images: list[str] | None = None
    is_active: bool | None = None


class ProductResponse(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    brand: str | None = None
    model: str | None = None
    category: str | None = None
    category_code: str | None = None
    description: str | None = None
    short_description: str | None = None
    unit_of_measure: str = "H87"

    cost_price: float = 0.0
    last_cost: float = 0.0
    sale_price: float = 0.0
    wholesale_price: float | None = None
    min_price: float | None = None

    supplier_id: uuid.UUID | None = None

    weight_kg: float = 0.0
    length_cm: float = 0.0
    width_cm: float = 0.0
    height_cm: float = 0.0

    warehouse_location: str | None = None
    images: list[str] = Field(default_factory=list)
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    variants: list[ProductVariantResponse] = Field(default_factory=list)


# ------------------------------------------------------------------------------
# 3. ESQUEMAS DE MAPEO DE PUBLICACIONES MERCADO LIBRE (PRODUCT SKU)
# ------------------------------------------------------------------------------
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
    company_id: uuid.UUID | None = None
    meli_account_id: uuid.UUID
    variant_id: uuid.UUID
    meli_item_id: str
    meli_variation_id: str | None = None
    seller_sku: str
    price: float
    listing_type_id: str
    logistic_type: str
    status: str
    sync_stock_enabled: bool
    created_at: datetime


# ------------------------------------------------------------------------------
# 4. ESQUEMAS DE IMPORTACIÓN MERCADO LIBRE Y CSV
# ------------------------------------------------------------------------------
class MeliItemVariationPayload(BaseSchema):
    id: str | int | None = None
    seller_custom_field: str | None = None
    price: float | None = None
    attributes: list[dict[str, Any]] = Field(default_factory=list)


class MeliItemImportPayload(BaseSchema):
    id: str = Field(..., description="ID de publicación MeLi (e.g. MLM123456789)")
    title: str = Field(..., description="Título de la publicación")
    seller_custom_field: str | None = Field(default=None, description="SKU del vendedor en MeLi")
    price: float = Field(..., ge=0.0)
    category_id: str | None = None
    brand: str | None = None
    model: str | None = None
    barcode_ean: str | None = None
    pictures: list[str] = Field(default_factory=list)
    description: str | None = None
    dimensions: dict[str, Any] | None = None
    weight_kg: float | None = None
    variations: list[MeliItemVariationPayload] = Field(default_factory=list)


class MeliImportRequest(BaseSchema):
    meli_account_id: uuid.UUID
    items: list[MeliItemImportPayload] = Field(default_factory=list)


class ImportSummaryResponse(BaseSchema):
    total_processed: int
    created: int
    updated: int
    linked_mappings: int
    errors: list[str] = Field(default_factory=list)


# ------------------------------------------------------------------------------
# 5. ESQUEMAS DE DETECCIÓN DE DUPLICADOS
# ------------------------------------------------------------------------------
class DuplicateCandidate(BaseSchema):
    product_id: uuid.UUID
    product_name: str
    variant_id: uuid.UUID
    sku: str
    barcode_ean: str | None = None


class DuplicateGroup(BaseSchema):
    reason: str  # "Mismo Código de Barras (EAN)", "SKU Duplicado", "Nombre Idéntico"
    key_value: str
    candidates: list[DuplicateCandidate]


class DuplicatesReportResponse(BaseSchema):
    total_groups: int
    duplicate_groups: list[DuplicateGroup]

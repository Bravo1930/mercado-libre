"""Esquemas Pydantic para el Catálogo Maestro de Productos, Variantes y SKUs de Mercado Libre."""

import re
import uuid
from datetime import datetime
from typing import Any
from pydantic import Field, field_validator, model_validator

from src.schemas.common import BaseSchema


def normalize_meli_item_id(value: str | None) -> str | None:
    """Normaliza un ID de publicación MeLi a su forma canónica (MLM + dígitos).

    Acepta "MLM-6636763518", "mlm 6636763518" o "MLM6636763518" y devuelve
    "MLM6636763518". Sin esto, el mismo ítem guardado con y sin guion se
    trataba como dos publicaciones distintas (y el formulario de vinculación
    rechazaba el ID con guion con un 422 de validación).
    """
    if value is None:
        return None
    cleaned = re.sub(r"[\s\-_]", "", str(value)).upper()
    return cleaned or None


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

    # Código de barras de la VARIANTE PRINCIPAL del producto. El formulario
    # "Editar Producto" no tenía campo para el EAN y la única vía era agregar
    # otra variante; con esto el EAN se corrige desde la edición del producto
    # (lo aplica CatalogService.update_product sobre la variante primaria).
    barcode_ean: str | None = Field(default=None, max_length=50)


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

    @field_validator("meli_item_id", mode="before")
    @classmethod
    def _normalize_item_id(cls, value: Any) -> Any:
        # Aceptar "MLM-6636763518" además de "MLM6636763518" (antes el
        # patrón ^MLM\d+$ rechazaba el guion con un 422).
        return normalize_meli_item_id(value)


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
    # Título y precio son OPCIONALES: desde el fix 9 el backend obtiene los
    # datos REALES de la publicación con GET /items/{id} y los valores que
    # mandaba el frontend (precio fijo 699.00, EAN aleatorio, título
    # "Publicación MeLi Sincronizada") se ignoran. Se conservan los campos
    # solo por compatibilidad con clientes que aún manden el payload completo.
    title: str = Field(default="", description="Título de la publicación")
    seller_custom_field: str | None = Field(default=None, description="SKU del vendedor en MeLi")
    price: float | None = Field(default=None, ge=0.0)
    category_id: str | None = None
    brand: str | None = None
    model: str | None = None
    barcode_ean: str | None = None
    pictures: list[str] = Field(default_factory=list)
    description: str | None = None
    dimensions: dict[str, Any] | None = None
    weight_kg: float | None = None
    variations: list[MeliItemVariationPayload] = Field(default_factory=list)

    @field_validator("id", mode="before")
    @classmethod
    def _normalize_id(cls, value: Any) -> Any:
        return normalize_meli_item_id(value)


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
# 4b. ESQUEMAS DE PUBLICACIÓN EN MERCADO LIBRE (POST /items)
# ------------------------------------------------------------------------------
class MeliAttributePayload(BaseSchema):
    id: str = Field(..., min_length=1, description="ID oficial del atributo MeLi (e.g. BRAND, MODEL, GTIN, COLOR, CONNECTOR_TYPE)")
    # Para atributos de catálogo con valores predefinidos (e.g. CONNECTOR_TYPE
    # en MLM429747) MeLi acepta value_id (el ID del valor en el catálogo) y/o
    # value_name. Se pasan tal cual en el POST /items; MeLi valida. Al menos
    # uno de los dos debe venir (si no, el atributo no dice nada).
    value_id: str | None = Field(default=None, description="ID del valor en el catálogo MeLi (e.g. 2113108 = USB-C)")
    value_name: str | None = Field(default=None, description="Valor del atributo")

    @model_validator(mode="after")
    def _require_value(self):
        if not (self.value_id or "").strip() and not (self.value_name or "").strip():
            raise ValueError("El atributo debe traer value_id o value_name")
        return self


class MeliPublishRequest(BaseSchema):
    meli_account_id: uuid.UUID = Field(..., description="Cuenta de vendedor MeLi vinculada a la empresa")
    variant_id: uuid.UUID | None = Field(
        default=None, description="Variante a publicar. Por defecto, la primera variante activa del producto."
    )
    category_id: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="ID de categoría MeLi (e.g. MLM...). Se obtiene del predictor de categorías o del flujo web.",
    )
    title: str | None = Field(
        default=None, max_length=60, description="Título de la publicación (máx. 60 caracteres). Por defecto, el nombre del producto."
    )
    price: float | None = Field(default=None, gt=0.0, description="Precio en MXN. Por defecto, el de la variante o del producto.")
    available_quantity: int = Field(default=1, ge=1, description="Stock inicial a publicar")
    listing_type_id: str = Field(
        default="free", description="free = Gratuita (sin comisión), gold_special = Clásica, gold_pro = Premium"
    )
    pictures: list[str] = Field(
        default_factory=list, description="URLs públicas de las fotos. Por defecto, las imágenes del producto."
    )
    description: str | None = Field(
        default=None, description="Descripción en texto plano. Por defecto, la descripción del producto."
    )
    attributes: list[MeliAttributePayload] = Field(
        default_factory=list,
        description="Atributos extra; BRAND, MODEL, GTIN y COLOR se completan automáticamente cuando existen.",
    )
    warranty_type: str = Field(default="Garantía de fábrica", description="Tipo de garantía (sale_terms WARRANTY_TYPE)")
    warranty_time: str = Field(default="90 días", description="Duración de la garantía (sale_terms WARRANTY_TIME)")


class MeliPublishResponse(BaseSchema):
    meli_item_id: str = Field(..., description="ID de la publicación creada en MeLi (e.g. MLM123456789)")
    permalink: str | None = Field(default=None, description="URL pública de la publicación")
    title: str
    price: float
    listing_type_id: str
    status: str = Field(default="active")
    variant_id: uuid.UUID
    product_sku_id: uuid.UUID = Field(..., description="ID del mapeo interno variante <-> publicación MeLi")
    description_error: str | None = Field(
        default=None, description="Si la descripción no se pudo guardar, la publicación existe pero este campo explica el fallo."
    )


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

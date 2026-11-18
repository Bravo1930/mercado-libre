"""API REST para Productos Maestros, Variantes y SKUs de Mercado Libre."""

import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.audit import record_audit_event
from src.core.database import get_db
from src.core.pagination import Page, PaginationParams, paginate_query
from src.models.product import Product, ProductSKU, ProductVariant
from src.repositories.base import BaseRepository
from src.schemas.product import (
    ProductCreate,
    ProductResponse,
    ProductSKUCreate,
    ProductSKUResponse,
)

router = APIRouter(prefix="/products", tags=["Productos & Catálogo"])
product_repo = BaseRepository[Product](Product)
sku_repo = BaseRepository[ProductSKU](ProductSKU)


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product_with_variants(
    payload: ProductCreate,
    session: AsyncSession = Depends(get_db),
) -> Product:
    """Crea un producto maestro con sus variantes iniciales de forma atómica."""
    product = Product(
        company_id=payload.company_id,
        name=payload.name,
        brand=payload.brand,
        category=payload.category,
        description=payload.description,
    )
    session.add(product)
    await session.flush()

    for v_in in payload.variants:
        variant = ProductVariant(
            product_id=product.id,
            variant_name=v_in.variant_name,
            sku=v_in.sku,
            barcode_ean=v_in.barcode_ean,
            cogs_cost=v_in.cogs_cost,
        )
        session.add(variant)

    await session.flush()
    # Recargar con relaciones
    stmt = select(Product).where(Product.id == product.id).options(selectinload(Product.variants))
    loaded_product = (await session.execute(stmt)).scalar_one()

    await record_audit_event(
        session=session,
        company_id=product.company_id,
        action="CREATE_PRODUCT",
        entity_name="Product",
        entity_id=str(product.id),
        changes={"name": product.name, "variants_count": len(payload.variants)},
    )
    return loaded_product


@router.get("", response_model=Page[ProductResponse])
async def list_products(
    company_id: uuid.UUID = Query(..., description="ID de la empresa"),
    search: str | None = Query(None, description="Búsqueda por nombre o marca"),
    category: str | None = Query(None, description="Filtrar por categoría"),
    params: PaginationParams = Depends(),
    session: AsyncSession = Depends(get_db),
) -> Page[Product]:
    """Lista productos paginados con búsqueda y variantes precargadas."""
    stmt = (
        select(Product)
        .where(Product.company_id == company_id)
        .options(selectinload(Product.variants))
    )
    if search:
        search_pattern = f"%{search}%"
        stmt = stmt.where(or_(Product.name.ilike(search_pattern), Product.brand.ilike(search_pattern)))
    if category:
        stmt = stmt.where(Product.category == category)

    stmt = stmt.order_by(Product.created_at.desc())
    items, total = await paginate_query(stmt, session, params)
    return Page.create(items, total, params)


@router.post("/skus", response_model=ProductSKUResponse, status_code=status.HTTP_201_CREATED)
async def map_variant_to_meli_sku(
    payload: ProductSKUCreate,
    session: AsyncSession = Depends(get_db),
) -> ProductSKU:
    """Mapea una variante interna a una publicación oficial de Mercado Libre México."""
    sku_obj = ProductSKU(**payload.model_dump())
    session.add(sku_obj)
    await session.flush()
    return sku_obj

"""API REST para el Catálogo Maestro de Productos, Variantes y SKUs de Mercado Libre."""

import io
import uuid
from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.audit import record_audit_event
from src.core.auth_context import CompanyContext, require_company_permission
from src.core.database import get_db
from src.core.exceptions import EntityNotFoundException, PermissionDeniedException
from src.core.pagination import Page, PaginationParams, paginate_query
from src.core.permissions import ActionEnum, ModuleEnum
from src.models.product import Product, ProductSKU, ProductVariant
from src.repositories.base import BaseRepository
from src.schemas.product import (
    DuplicatesReportResponse,
    ImportSummaryResponse,
    MeliImportRequest,
    MeliPublishRequest,
    MeliPublishResponse,
    ProductCreate,
    ProductResponse,
    ProductSKUCreate,
    ProductSKUResponse,
    ProductUpdate,
    ProductVariantCreate,
    ProductVariantResponse,
    ProductVariantUpdate,
)
from src.services.catalog_service import CatalogService

router = APIRouter(prefix="/products", tags=["Productos & Catálogo Maestro"])
product_repo = BaseRepository[Product](Product)
variant_repo = BaseRepository[ProductVariant](ProductVariant)
sku_repo = BaseRepository[ProductSKU](ProductSKU)


# ------------------------------------------------------------------------------
# 1. ALTA Y LISTADO DE PRODUCTOS MAESTROS (CON BÚSQUEDA MULTICRITERIO)
# ------------------------------------------------------------------------------
@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.CATALOG, ActionEnum.CREATE)),
    session: AsyncSession = Depends(get_db),
) -> Product:
    """Crea un producto maestro con sus variantes iniciales asegurando SKU único por empresa."""
    if payload.company_id != ctx.company_id:
        raise PermissionDeniedException("No se puede crear un producto para una empresa distinta a la activa.")

    return await CatalogService.create_product(
        session=session,
        payload=payload,
        user_id=ctx.user.id,
    )


@router.get("", response_model=Page[ProductResponse])
async def list_products(
    q: str | None = Query(None, description="Búsqueda global por SKU, código de barras EAN, nombre, marca o modelo"),
    sku: str | None = Query(None, description="Filtrar por SKU específico"),
    barcode: str | None = Query(None, description="Filtrar por código de barras EAN/UPC"),
    category: str | None = Query(None, description="Filtrar por categoría"),
    brand: str | None = Query(None, description="Filtrar por marca"),
    is_active: bool | None = Query(None, description="Filtrar por estatus activo/inactivo"),
    params: PaginationParams = Depends(),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.CATALOG, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> Page[Product]:
    """Lista productos maestros paginados con variantes precargadas y filtros multicriterio."""
    stmt = (
        select(Product)
        .where(Product.company_id == ctx.company_id)
        .options(selectinload(Product.variants))
    )

    if is_active is not None:
        stmt = stmt.where(Product.is_active == is_active)

    if category:
        stmt = stmt.where(Product.category.ilike(f"%{category.strip()}%"))

    if brand:
        stmt = stmt.where(Product.brand.ilike(f"%{brand.strip()}%"))

    # Búsqueda específica por SKU o Barcode
    if sku or barcode:
        subq = select(ProductVariant.product_id)
        if sku:
            subq = subq.where(ProductVariant.sku.ilike(f"%{sku.strip()}%"))
        if barcode:
            subq = subq.where(ProductVariant.barcode_ean == barcode.strip())
        stmt = stmt.where(Product.id.in_(subq))

    # Búsqueda global (q)
    if q and q.strip():
        q_term = f"%{q.strip()}%"
        # Coincidencia directa en Producto
        prod_cond = or_(
            Product.name.ilike(q_term),
            Product.brand.ilike(q_term),
            Product.model.ilike(q_term),
            Product.warehouse_location.ilike(q_term),
        )
        # Coincidencia en Variantes (SKU o Código de barras)
        variant_subq = select(ProductVariant.product_id).where(
            or_(
                ProductVariant.sku.ilike(q_term),
                ProductVariant.barcode_ean.ilike(q_term),
                ProductVariant.variant_name.ilike(q_term),
            )
        )
        stmt = stmt.where(or_(prod_cond, Product.id.in_(variant_subq)))

    stmt = stmt.order_by(Product.name.asc())
    items, total = await paginate_query(stmt, session, params)
    return Page.create(items, total, params)


@router.get("/categories", response_model=list[str])
async def list_categories(
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.CATALOG, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> list[str]:
    """Obtiene la lista de categorías únicas registradas en los productos de la empresa activa."""
    stmt = (
        select(distinct(Product.category))
        .where(Product.company_id == ctx.company_id, Product.category.isnot(None))
        .order_by(Product.category.asc())
    )
    res = await session.execute(stmt)
    return [c for c in res.scalars().all() if c]


# ------------------------------------------------------------------------------
# 2. DETECCIÓN DE DUPLICADOS
# ------------------------------------------------------------------------------
@router.get("/duplicates", response_model=DuplicatesReportResponse)
async def check_duplicates(
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.CATALOG, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> DuplicatesReportResponse:
    """Escanea el catálogo para detectar duplicados por código de barras EAN, SKU o nombre idéntico."""
    return await CatalogService.detect_duplicates(session=session, company_id=ctx.company_id)


# ------------------------------------------------------------------------------
# 3. IMPORTACIÓN DESDE MERCADO LIBRE Y CSV
# ------------------------------------------------------------------------------
@router.post("/import-meli", response_model=ImportSummaryResponse)
async def import_from_meli(
    payload: MeliImportRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.CATALOG, ActionEnum.CREATE)),
    session: AsyncSession = Depends(get_db),
) -> ImportSummaryResponse:
    """Importa publicaciones desde Mercado Libre México evitando duplicar productos existentes."""
    return await CatalogService.import_from_meli(
        session=session,
        company_id=ctx.company_id,
        meli_account_id=payload.meli_account_id,
        items=payload.items,
        user_id=ctx.user.id,
    )


@router.post("/{product_id}/publish-meli", response_model=MeliPublishResponse, status_code=status.HTTP_201_CREATED)
async def publish_product_to_meli(
    product_id: uuid.UUID,
    payload: MeliPublishRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.CATALOG, ActionEnum.CREATE)),
    session: AsyncSession = Depends(get_db),
) -> MeliPublishResponse:
    """Publica una variante del catálogo en Mercado Libre México (API oficial POST /items).

    Crea la publicación como Gratuita por defecto (listing_type_id="free"),
    guarda la descripción y deja el mapeo variante <-> publicación (ProductSKU)
    para gestionar pedidos, stock y precios desde el ERP. Requiere el
    category_id de MeLi y al menos una foto. Si Mercado Libre rechaza la
    publicación (GTIN faltante, propiedad intelectual, etc.), el error oficial
    se devuelve tal cual en el detalle de la respuesta.
    """
    return await CatalogService.publish_to_meli(
        session=session,
        company_id=ctx.company_id,
        product_id=product_id,
        payload=payload,
        user_id=ctx.user.id,
    )


@router.post("/import-csv", response_model=ImportSummaryResponse)
async def import_from_csv(
    file: UploadFile = File(..., description="Archivo CSV con el catálogo maestro"),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.CATALOG, ActionEnum.CREATE)),
    session: AsyncSession = Depends(get_db),
) -> ImportSummaryResponse:
    """Importa productos desde un archivo CSV con actualización atómica de productos existentes."""
    content_bytes = await file.read()
    # Decodificar respetando posibles codificaciones
    try:
        csv_text = content_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        csv_text = content_bytes.decode("latin-1")

    return await CatalogService.import_from_csv(
        session=session,
        company_id=ctx.company_id,
        csv_content=csv_text,
        user_id=ctx.user.id,
    )


# ------------------------------------------------------------------------------
# 4. EXPORTACIÓN A CSV Y XLSX
# ------------------------------------------------------------------------------
@router.get("/export-csv")
async def export_csv(
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.CATALOG, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
):
    """Descarga el catálogo maestro completo en formato CSV (UTF-8 con BOM para Excel)."""
    csv_str = await CatalogService.export_to_csv(session=session, company_id=ctx.company_id)
    # \ufeff añade el Byte Order Mark para apertura directa en Microsoft Excel en español
    csv_bytes = ("\ufeff" + csv_str).encode("utf-8")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="catalogo_maestro_erp.csv"'},
    )


@router.get("/export-xlsx")
async def export_xlsx(
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.CATALOG, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
):
    """Descarga el catálogo maestro completo en formato Excel (.xlsx) con estilos profesionales."""
    stream = await CatalogService.export_to_xlsx(session=session, company_id=ctx.company_id)
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="catalogo_maestro_erp.xlsx"'},
    )


# ------------------------------------------------------------------------------
# 5. DETALLE, EDICIÓN Y DESACTIVACIÓN DE PRODUCTO INDIVIDUAL
# ------------------------------------------------------------------------------
@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.CATALOG, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> Product:
    """Obtiene el detalle completo de un producto maestro y sus variantes."""
    stmt = (
        select(Product)
        .where(Product.id == product_id, Product.company_id == ctx.company_id)
        .options(selectinload(Product.variants))
    )
    product = (await session.execute(stmt)).scalar_one_or_none()
    if not product:
        raise EntityNotFoundException("Producto Maestro", str(product_id))
    return product


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.CATALOG, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> Product:
    """Actualiza atributos de un producto maestro conservando historial de auditoría."""
    return await CatalogService.update_product(
        session=session,
        product_id=product_id,
        company_id=ctx.company_id,
        payload=payload,
        user_id=ctx.user.id,
    )


@router.patch("/{product_id}/toggle-status", response_model=ProductResponse)
async def toggle_product_status(
    product_id: uuid.UUID,
    is_active: bool | None = Query(None, description="Nuevo estado activo (omitir para invertir)"),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.CATALOG, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> Product:
    """Activa o desactiva (soft-delete) un producto maestro y sus variantes."""
    return await CatalogService.toggle_product_status(
        session=session,
        product_id=product_id,
        company_id=ctx.company_id,
        user_id=ctx.user.id,
        is_active=is_active,
    )


# ------------------------------------------------------------------------------
# 6. GESTIÓN DE VARIANTES Y SKU ÚNICO
# ------------------------------------------------------------------------------
@router.post("/{product_id}/variants", response_model=ProductVariantResponse, status_code=status.HTTP_201_CREATED)
async def create_variant(
    product_id: uuid.UUID,
    payload: ProductVariantCreate,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.CATALOG, ActionEnum.CREATE)),
    session: AsyncSession = Depends(get_db),
) -> ProductVariant:
    """Agrega una nueva variante a un producto existente garantizando SKU único por empresa."""
    stmt = select(Product).where(Product.id == product_id, Product.company_id == ctx.company_id)
    product = (await session.execute(stmt)).scalar_one_or_none()
    if not product:
        raise EntityNotFoundException("Producto Maestro", str(product_id))

    await CatalogService.validate_sku_uniqueness(session, ctx.company_id, payload.sku)

    variant = ProductVariant(
        company_id=ctx.company_id,
        product_id=product.id,
        variant_name=payload.variant_name.strip(),
        sku=payload.sku.strip(),
        barcode_ean=payload.barcode_ean.strip() if payload.barcode_ean else None,
        cogs_cost=payload.cogs_cost,
        sale_price=payload.sale_price or product.sale_price,
        attributes=payload.attributes or {},
        is_active=payload.is_active,
    )
    session.add(variant)
    await session.flush()

    await record_audit_event(
        session=session,
        company_id=ctx.company_id,
        action="CREATE_VARIANT",
        entity_name="ProductVariant",
        entity_id=str(variant.id),
        user_id=ctx.user.id,
        changes={"sku": variant.sku, "product_id": str(product.id)},
    )
    return variant


@router.put("/{product_id}/variants/{variant_id}", response_model=ProductVariantResponse)
async def update_variant(
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
    payload: ProductVariantUpdate,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.CATALOG, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> ProductVariant:
    """Actualiza una variante de producto verificando unicidad si se modifica el SKU."""
    stmt = (
        select(ProductVariant)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(
            ProductVariant.id == variant_id,
            ProductVariant.product_id == product_id,
            Product.company_id == ctx.company_id,
        )
    )
    variant = (await session.execute(stmt)).scalar_one_or_none()
    if not variant:
        raise EntityNotFoundException("Variante de Producto", str(variant_id))

    if payload.sku and payload.sku.strip().lower() != variant.sku.lower():
        await CatalogService.validate_sku_uniqueness(
            session=session,
            company_id=ctx.company_id,
            sku=payload.sku,
            exclude_variant_id=variant.id,
        )
        variant.sku = payload.sku.strip()

    if payload.variant_name is not None:
        variant.variant_name = payload.variant_name.strip()
    if payload.barcode_ean is not None:
        variant.barcode_ean = payload.barcode_ean.strip() if payload.barcode_ean else None
    if payload.cogs_cost is not None:
        variant.cogs_cost = payload.cogs_cost
    if payload.sale_price is not None:
        variant.sale_price = payload.sale_price
    if payload.attributes is not None:
        variant.attributes = payload.attributes
    if payload.is_active is not None:
        variant.is_active = payload.is_active

    await session.flush()

    await record_audit_event(
        session=session,
        company_id=ctx.company_id,
        action="UPDATE_VARIANT",
        entity_name="ProductVariant",
        entity_id=str(variant.id),
        user_id=ctx.user.id,
        changes={"sku": variant.sku, "barcode_ean": variant.barcode_ean},
    )
    return variant


# ------------------------------------------------------------------------------
# 7. ASOCIACIÓN DE PUBLICACIONES EXTERNAS MULTI-CUENTA (PRODUCT SKU)
# ------------------------------------------------------------------------------
@router.post("/mappings", response_model=ProductSKUResponse, status_code=status.HTTP_201_CREATED)
@router.post("/skus", response_model=ProductSKUResponse, status_code=status.HTTP_201_CREATED)
async def map_variant_to_meli_sku(
    payload: ProductSKUCreate,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.CATALOG, ActionEnum.CREATE)),
    session: AsyncSession = Depends(get_db),
) -> ProductSKU:
    """Asocia una variante interna a una publicación oficial de Mercado Libre (soporta multi-publicación y multi-cuenta)."""
    # Verificar que la variante pertenezca a la empresa activa
    stmt_v = (
        select(ProductVariant)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(ProductVariant.id == payload.variant_id, Product.company_id == ctx.company_id)
    )
    variant = (await session.execute(stmt_v)).scalar_one_or_none()
    if not variant:
        raise EntityNotFoundException("Variante de Producto", str(payload.variant_id))

    # Comprobar si ya existe el mapeo exacto (meli_account + item_id + variation)
    stmt_chk = select(ProductSKU).where(
        ProductSKU.meli_account_id == payload.meli_account_id,
        ProductSKU.meli_item_id == payload.meli_item_id,
        ProductSKU.meli_variation_id == payload.meli_variation_id,
    )
    existing_mapping = (await session.execute(stmt_chk)).scalar_one_or_none()
    if existing_mapping:
        existing_mapping.variant_id = payload.variant_id
        existing_mapping.price = payload.price
        existing_mapping.seller_sku = payload.seller_sku
        await session.flush()
        return existing_mapping

    sku_obj = ProductSKU(
        company_id=ctx.company_id,
        **payload.model_dump(),
    )
    session.add(sku_obj)
    await session.flush()

    await record_audit_event(
        session=session,
        company_id=ctx.company_id,
        action="MAP_MELI_PUBLICATION",
        entity_name="ProductSKU",
        entity_id=str(sku_obj.id),
        user_id=ctx.user.id,
        changes={"meli_item_id": sku_obj.meli_item_id, "variant_id": str(sku_obj.variant_id)},
    )
    return sku_obj


@router.get("/{product_id}/mappings", response_model=list[ProductSKUResponse])
async def list_product_meli_mappings(
    product_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.CATALOG, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> list[ProductSKU]:
    """Lista todas las publicaciones de Mercado Libre asociadas a las variantes de un producto maestro."""
    stmt = (
        select(ProductSKU)
        .join(ProductVariant, ProductVariant.id == ProductSKU.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(Product.id == product_id, Product.company_id == ctx.company_id)
        .order_by(ProductSKU.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


@router.delete("/mappings/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meli_mapping(
    mapping_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.CATALOG, ActionEnum.DELETE)),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Elimina la asociación entre una variante interna y una publicación externa de Mercado Libre."""
    stmt = (
        select(ProductSKU)
        .join(ProductVariant, ProductVariant.id == ProductSKU.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(ProductSKU.id == mapping_id, Product.company_id == ctx.company_id)
    )
    sku_obj = (await session.execute(stmt)).scalar_one_or_none()
    if not sku_obj:
        raise EntityNotFoundException("Mapeo de Publicación MeLi", str(mapping_id))

    item_id = sku_obj.meli_item_id
    await session.delete(sku_obj)
    await session.flush()

    await record_audit_event(
        session=session,
        company_id=ctx.company_id,
        action="UNMAP_MELI_PUBLICATION",
        entity_name="ProductSKU",
        entity_id=str(mapping_id),
        user_id=ctx.user.id,
        changes={"meli_item_id": item_id},
    )

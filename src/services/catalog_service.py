"""Servicio de Negocio para el Catálogo Maestro de Productos del ERP.

Gestiona:
- Alta, edición, desactivación y auditoría de productos y variantes.
- Garantía de SKU único por empresa.
- Importación desde Mercado Libre con prevención estricta de duplicados.
- Importación y exportación de archivos CSV y Excel (XLSX).
- Detección inteligente de duplicados (EAN, SKU, nombre).
- Mapeo multi-publicación y multi-cuenta para un mismo producto o variante.
"""

import csv
import io
import re
import uuid
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.audit import record_audit_event
from src.core.exceptions import DuplicateEntityException, EntityNotFoundException
from src.models.product import Product, ProductSKU, ProductVariant
from src.schemas.product import (
    DuplicateCandidate,
    DuplicateGroup,
    DuplicatesReportResponse,
    ImportSummaryResponse,
    MeliItemImportPayload,
    ProductCreate,
    ProductUpdate,
    ProductVariantCreate,
    ProductVariantUpdate,
)


def normalize_text(text: str | None) -> str:
    """Normaliza un texto para comparaciones de similitud y detección de duplicados."""
    if not text:
        return ""
    # Quitar acentos, puntuación y convertir a minúsculas
    s = text.lower().strip()
    s = re.sub(r"[áàäâ]", "a", s)
    s = re.sub(r"[éèëê]", "e", s)
    s = re.sub(r"[íìïî]", "i", s)
    s = re.sub(r"[óòöô]", "o", s)
    s = re.sub(r"[úùüû]", "u", s)
    s = re.sub(r"[^a-z0-9]", "", s)
    return s


class CatalogService:
    """Lógica integral del Catálogo Maestro de Productos."""

    @staticmethod
    async def validate_sku_uniqueness(
        session: AsyncSession,
        company_id: uuid.UUID,
        sku: str,
        exclude_variant_id: uuid.UUID | None = None,
    ) -> None:
        """Verifica que un SKU no exista previamente en ninguna variante de la misma empresa."""
        sku_clean = sku.strip()
        stmt = (
            select(ProductVariant)
            .join(Product, Product.id == ProductVariant.product_id)
            .where(
                Product.company_id == company_id,
                func.lower(ProductVariant.sku) == sku_clean.lower(),
            )
        )
        if exclude_variant_id:
            stmt = stmt.where(ProductVariant.id != exclude_variant_id)

        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing:
            raise DuplicateEntityException(
                f"El SKU '{sku_clean}' ya está registrado en esta empresa (Variante: {existing.variant_name})."
            )

    @classmethod
    async def create_product(
        cls,
        session: AsyncSession,
        payload: ProductCreate,
        user_id: uuid.UUID,
    ) -> Product:
        """Crea un producto maestro con sus variantes asegurando unicidad de SKU."""
        # 1. Validar unicidad de todos los SKUs de las variantes en el payload
        sku_set: set[str] = set()
        for v in payload.variants:
            v_sku = v.sku.strip().lower()
            if v_sku in sku_set:
                raise DuplicateEntityException(f"El SKU '{v.sku}' aparece duplicado en la misma petición.")
            sku_set.add(v_sku)
            await cls.validate_sku_uniqueness(session, payload.company_id, v.sku)

        # 2. Instanciar y persistir Producto Maestro
        product_data = payload.model_dump(exclude={"variants"})
        product = Product(**product_data)
        session.add(product)
        await session.flush()

        # 3. Si no se especificaron variantes, generar una variante primaria por defecto
        variants_to_create = payload.variants
        if not variants_to_create:
            default_sku = f"SKU-{product.name[:3].upper()}-{str(uuid.uuid4())[:6].upper()}"
            variants_to_create = [
                ProductVariantCreate(
                    variant_name="Principal / Estándar",
                    sku=default_sku,
                    cogs_cost=payload.cost_price,
                    sale_price=payload.sale_price,
                )
            ]

        # 4. Crear las variantes asociadas
        for v_in in variants_to_create:
            variant = ProductVariant(
                company_id=payload.company_id,
                product_id=product.id,
                variant_name=v_in.variant_name,
                sku=v_in.sku.strip(),
                barcode_ean=v_in.barcode_ean.strip() if v_in.barcode_ean else None,
                cogs_cost=v_in.cogs_cost,
                sale_price=v_in.sale_price or payload.sale_price,
                attributes=v_in.attributes or {},
                is_active=v_in.is_active,
            )
            session.add(variant)

        await session.flush()

        # 5. Registrar evento de auditoría
        await record_audit_event(
            session=session,
            company_id=payload.company_id,
            action="CREATE_PRODUCT",
            entity_name="Product",
            entity_id=str(product.id),
            user_id=user_id,
            changes={
                "name": product.name,
                "sku_count": len(variants_to_create),
                "sale_price": float(product.sale_price),
                "cost_price": float(product.cost_price),
            },
        )

        # 6. Recargar con variantes
        stmt = (
            select(Product)
            .where(Product.id == product.id)
            .options(selectinload(Product.variants))
        )
        return (await session.execute(stmt)).scalar_one()

    @classmethod
    async def update_product(
        cls,
        session: AsyncSession,
        product_id: uuid.UUID,
        company_id: uuid.UUID,
        payload: ProductUpdate,
        user_id: uuid.UUID,
    ) -> Product:
        """Actualiza un producto maestro conservando historial de auditoría de los campos modificados."""
        stmt = (
            select(Product)
            .where(Product.id == product_id, Product.company_id == company_id)
            .options(selectinload(Product.variants))
        )
        product = (await session.execute(stmt)).scalar_one_or_none()
        if not product:
            raise EntityNotFoundException("Producto Maestro", str(product_id))

        update_dict = payload.model_dump(exclude_unset=True)
        old_values: dict[str, Any] = {}
        new_values: dict[str, Any] = {}

        for key, new_val in update_dict.items():
            current_val = getattr(product, key)
            if current_val != new_val:
                old_values[key] = float(current_val) if hasattr(current_val, "as_tuple") else current_val
                new_values[key] = float(new_val) if hasattr(new_val, "as_tuple") else new_val
                setattr(product, key, new_val)

        await session.flush()

        if old_values:
            await record_audit_event(
                session=session,
                company_id=company_id,
                action="UPDATE_PRODUCT",
                entity_name="Product",
                entity_id=str(product.id),
                user_id=user_id,
                changes={"old": old_values, "new": new_values},
            )

        return product

    @classmethod
    async def toggle_product_status(
        cls,
        session: AsyncSession,
        product_id: uuid.UUID,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        is_active: bool | None = None,
    ) -> Product:
        """Activa o desactiva (soft-delete) un producto maestro y sus variantes asociadas."""
        stmt = (
            select(Product)
            .where(Product.id == product_id, Product.company_id == company_id)
            .options(selectinload(Product.variants))
        )
        product = (await session.execute(stmt)).scalar_one_or_none()
        if not product:
            raise EntityNotFoundException("Producto Maestro", str(product_id))

        new_status = not product.is_active if is_active is None else is_active
        old_status = product.is_active
        product.is_active = new_status

        # Actualizar también variantes
        for v in product.variants:
            v.is_active = new_status

        await session.flush()

        await record_audit_event(
            session=session,
            company_id=company_id,
            action="DEACTIVATE_PRODUCT" if not new_status else "ACTIVATE_PRODUCT",
            entity_name="Product",
            entity_id=str(product.id),
            user_id=user_id,
            changes={"old_status": old_status, "new_status": new_status},
        )
        return product

    @classmethod
    async def import_from_meli(
        cls,
        session: AsyncSession,
        company_id: uuid.UUID,
        meli_account_id: uuid.UUID,
        items: list[MeliItemImportPayload],
        user_id: uuid.UUID,
    ) -> ImportSummaryResponse:
        """Importa productos desde Mercado Libre evitando crear duplicados y vinculando publicaciones."""
        created_count = 0
        updated_count = 0
        linked_mappings = 0
        errors: list[str] = []

        for item in items:
            try:
                # 1. Determinar SKU prioritario
                primary_sku = (item.seller_custom_field or f"MELI-{item.id}").strip()
                ean = item.barcode_ean.strip() if item.barcode_ean else None

                # 2. Buscar si ya existe por SKU o por EAN en esta empresa
                existing_variant: ProductVariant | None = None

                # Buscar por SKU
                stmt_sku = (
                    select(ProductVariant)
                    .join(Product, Product.id == ProductVariant.product_id)
                    .where(
                        Product.company_id == company_id,
                        func.lower(ProductVariant.sku) == primary_sku.lower(),
                    )
                    .options(selectinload(ProductVariant.product))
                )
                existing_variant = (await session.execute(stmt_sku)).scalar_one_or_none()

                # Si no se halló por SKU, buscar por código de barras EAN si está disponible
                if not existing_variant and ean:
                    stmt_ean = (
                        select(ProductVariant)
                        .join(Product, Product.id == ProductVariant.product_id)
                        .where(
                            Product.company_id == company_id,
                            ProductVariant.barcode_ean == ean,
                        )
                        .options(selectinload(ProductVariant.product))
                    )
                    existing_variant = (await session.execute(stmt_ean)).scalar_one_or_none()

                # Si no se halló, buscar si ya existe la publicación MeLi mapeada
                if not existing_variant:
                    stmt_map = (
                        select(ProductSKU)
                        .where(
                            ProductSKU.meli_account_id == meli_account_id,
                            ProductSKU.meli_item_id == item.id,
                        )
                        .options(selectinload(ProductSKU.variant).selectinload(ProductVariant.product))
                    )
                    existing_sku_map = (await session.execute(stmt_map)).scalar_one_or_none()
                    if existing_sku_map:
                        existing_variant = existing_sku_map.variant

                # 3. Si ya existe, ACTUALIZAR para evitar duplicación
                if existing_variant:
                    product = existing_variant.product
                    product.sale_price = item.price
                    if item.brand and not product.brand:
                        product.brand = item.brand
                    if item.model and not product.model:
                        product.model = item.model
                    if item.pictures and not product.images:
                        product.images = item.pictures
                    if ean and not existing_variant.barcode_ean:
                        existing_variant.barcode_ean = ean

                    target_variant = existing_variant
                    updated_count += 1
                else:
                    # Crear nuevo producto maestro y variante
                    product = Product(
                        company_id=company_id,
                        name=item.title.strip(),
                        brand=item.brand,
                        model=item.model,
                        category=item.category_id,
                        category_code=item.category_id,
                        description=item.description,
                        sale_price=item.price,
                        cost_price=item.price * 0.50,  # Estimado inicial de costo
                        images=item.pictures,
                        weight_kg=item.weight_kg or 0.500,
                    )
                    session.add(product)
                    await session.flush()

                    target_variant = ProductVariant(
                        company_id=company_id,
                        product_id=product.id,
                        variant_name="Principal / MeLi",
                        sku=primary_sku,
                        barcode_ean=ean,
                        cogs_cost=product.cost_price,
                        sale_price=item.price,
                    )
                    session.add(target_variant)
                    await session.flush()
                    created_count += 1

                # 4. Vincular la publicación en ProductSKU (soporta multi-cuenta y multi-publicación)
                stmt_sku_link = select(ProductSKU).where(
                    ProductSKU.meli_account_id == meli_account_id,
                    ProductSKU.meli_item_id == item.id,
                )
                existing_link = (await session.execute(stmt_sku_link)).scalar_one_or_none()
                if not existing_link:
                    sku_mapping = ProductSKU(
                        company_id=company_id,
                        meli_account_id=meli_account_id,
                        variant_id=target_variant.id,
                        meli_item_id=item.id,
                        seller_sku=primary_sku,
                        price=item.price,
                        listing_type_id="gold_special",
                        logistic_type="fulfillment",
                        status="active",
                    )
                    session.add(sku_mapping)
                    linked_mappings += 1

            except Exception as e:
                errors.append(f"Error procesando publicación {item.id}: {str(e)}")

        await session.flush()

        await record_audit_event(
            session=session,
            company_id=company_id,
            action="IMPORT_MELI_PRODUCTS",
            entity_name="Product",
            entity_id=str(meli_account_id),
            user_id=user_id,
            changes={
                "created": created_count,
                "updated": updated_count,
                "linked_mappings": linked_mappings,
                "errors_count": len(errors),
            },
        )

        return ImportSummaryResponse(
            total_processed=len(items),
            created=created_count,
            updated=updated_count,
            linked_mappings=linked_mappings,
            errors=errors,
        )

    @classmethod
    async def import_from_csv(
        cls,
        session: AsyncSession,
        company_id: uuid.UUID,
        csv_content: str,
        user_id: uuid.UUID,
    ) -> ImportSummaryResponse:
        """Importa productos desde archivo CSV evitando duplicados y actualizando existentes."""
        created_count = 0
        updated_count = 0
        errors: list[str] = []

        # Detectar delimitador (coma o punto y coma)
        sample = csv_content[:1024]
        delimiter = ";" if sample.count(";") > sample.count(",") else ","
        reader = csv.DictReader(io.StringIO(csv_content), delimiter=delimiter)

        row_index = 1
        for row in reader:
            row_index += 1
            # Normalizar nombres de columnas a minúsculas sin espacios
            clean_row = {re.sub(r"[^a-zA-Z0-9_]", "", k.lower().strip()): v.strip() for k, v in row.items() if k}

            sku = clean_row.get("sku") or clean_row.get("clave") or clean_row.get("codigo")
            name = clean_row.get("nombre") or clean_row.get("name") or clean_row.get("titulo") or clean_row.get("title")

            if not sku or not name:
                errors.append(f"Fila {row_index}: SKU y Nombre son campos requeridos.")
                continue

            brand = clean_row.get("marca") or clean_row.get("brand")
            model = clean_row.get("modelo") or clean_row.get("model")
            category = clean_row.get("categoria") or clean_row.get("category")
            barcode = clean_row.get("codigobarras") or clean_row.get("codigo_barras") or clean_row.get("ean") or clean_row.get("barcode")
            location = clean_row.get("ubicacion") or clean_row.get("location") or clean_row.get("rack")

            try:
                cost = float(clean_row.get("costo") or clean_row.get("cogs") or 0.0)
                price = float(clean_row.get("precio") or clean_row.get("price") or clean_row.get("pvp") or 0.0)
                weight = float(clean_row.get("peso") or clean_row.get("peso_kg") or clean_row.get("weight") or 0.0)
                length = float(clean_row.get("largo") or clean_row.get("length") or 0.0)
                width = float(clean_row.get("ancho") or clean_row.get("width") or 0.0)
                height = float(clean_row.get("alto") or clean_row.get("height") or 0.0)
            except ValueError as ve:
                errors.append(f"Fila {row_index} ({sku}): Error de formato numérico ({ve}).")
                continue

            try:
                # Comprobar si ya existe el SKU en la empresa
                stmt = (
                    select(ProductVariant)
                    .join(Product, Product.id == ProductVariant.product_id)
                    .where(
                        Product.company_id == company_id,
                        func.lower(ProductVariant.sku) == sku.lower(),
                    )
                    .options(selectinload(ProductVariant.product))
                )
                existing_variant = (await session.execute(stmt)).scalar_one_or_none()

                if existing_variant:
                    # Actualizar existente
                    product = existing_variant.product
                    product.name = name
                    if brand: product.brand = brand
                    if model: product.model = model
                    if category: product.category = category
                    if location: product.warehouse_location = location
                    if cost > 0: product.cost_price = cost
                    if price > 0: product.sale_price = price
                    if weight > 0: product.weight_kg = weight
                    if length > 0: product.length_cm = length
                    if width > 0: product.width_cm = width
                    if height > 0: product.height_cm = height

                    existing_variant.cogs_cost = cost or existing_variant.cogs_cost
                    existing_variant.sale_price = price or existing_variant.sale_price
                    if barcode: existing_variant.barcode_ean = barcode
                    updated_count += 1
                else:
                    # Crear nuevo
                    product = Product(
                        company_id=company_id,
                        name=name,
                        brand=brand,
                        model=model,
                        category=category,
                        cost_price=cost,
                        sale_price=price,
                        weight_kg=weight,
                        length_cm=length,
                        width_cm=width,
                        height_cm=height,
                        warehouse_location=location,
                    )
                    session.add(product)
                    await session.flush()

                    variant = ProductVariant(
                        company_id=company_id,
                        product_id=product.id,
                        variant_name="Principal",
                        sku=sku,
                        barcode_ean=barcode,
                        cogs_cost=cost,
                        sale_price=price,
                    )
                    session.add(variant)
                    created_count += 1

            except Exception as row_exc:
                errors.append(f"Fila {row_index} ({sku}): {str(row_exc)}")

        await session.flush()

        await record_audit_event(
            session=session,
            company_id=company_id,
            action="IMPORT_CSV_PRODUCTS",
            entity_name="Product",
            entity_id=str(company_id),
            user_id=user_id,
            changes={"created": created_count, "updated": updated_count, "errors": len(errors)},
        )

        return ImportSummaryResponse(
            total_processed=created_count + updated_count + len(errors),
            created=created_count,
            updated=updated_count,
            linked_mappings=0,
            errors=errors,
        )

    @staticmethod
    async def export_to_csv(session: AsyncSession, company_id: uuid.UUID) -> str:
        """Exporta el catálogo maestro a formato CSV con codificación UTF-8 BOM."""
        stmt = (
            select(Product)
            .where(Product.company_id == company_id)
            .options(selectinload(Product.variants))
            .order_by(Product.name.asc())
        )
        products = (await session.execute(stmt)).scalars().all()

        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

        headers = [
            "ID Producto",
            "SKU",
            "Nombre",
            "Variante",
            "Marca",
            "Modelo",
            "Categoría",
            "Código EAN / Barras",
            "Costo (MXN)",
            "Precio Venta (MXN)",
            "Precio Mayoreo (MXN)",
            "Precio Mínimo (MXN)",
            "Unidad Medida",
            "Peso (kg)",
            "Largo (cm)",
            "Ancho (cm)",
            "Alto (cm)",
            "Ubicación Almacén",
            "Estado",
        ]
        writer.writerow(headers)

        for p in products:
            variants = p.variants or [None]
            for v in variants:
                sku_val = v.sku if v else "SIN-SKU"
                v_name = v.variant_name if v else "Estándar"
                barcode = (v.barcode_ean if v else "") or ""
                v_cost = (v.cogs_cost if v else p.cost_price) or 0.0
                v_price = (v.sale_price if (v and v.sale_price) else p.sale_price) or 0.0

                writer.writerow([
                    str(p.id),
                    sku_val,
                    p.name,
                    v_name,
                    p.brand or "",
                    p.model or "",
                    p.category or "",
                    barcode,
                    f"{float(v_cost):.2f}",
                    f"{float(v_price):.2f}",
                    f"{float(p.wholesale_price or 0.0):.2f}",
                    f"{float(p.min_price or 0.0):.2f}",
                    p.unit_of_measure,
                    f"{float(p.weight_kg):.3f}",
                    f"{float(p.length_cm):.2f}",
                    f"{float(p.width_cm):.2f}",
                    f"{float(p.height_cm):.2f}",
                    p.warehouse_location or "",
                    "Activo" if p.is_active else "Inactivo",
                ])

        return output.getvalue()

    @staticmethod
    async def export_to_xlsx(session: AsyncSession, company_id: uuid.UUID) -> io.BytesIO:
        """Exporta el catálogo maestro a formato nativo Excel (.xlsx) estilizado profesionalmente."""
        stmt = (
            select(Product)
            .where(Product.company_id == company_id)
            .options(selectinload(Product.variants))
            .order_by(Product.name.asc())
        )
        products = (await session.execute(stmt)).scalars().all()

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Catálogo Maestro ERP"

        headers = [
            "ID Producto",
            "SKU",
            "Nombre del Producto",
            "Variante",
            "Marca",
            "Modelo",
            "Categoría",
            "Código EAN / Barras",
            "Costo Base (MXN)",
            "Precio Venta (MXN)",
            "Precio Mayoreo (MXN)",
            "Precio Mínimo (MXN)",
            "Unidad",
            "Peso (kg)",
            "Largo (cm)",
            "Ancho (cm)",
            "Alto (cm)",
            "Ubicación en Almacén",
            "Estatus",
        ]
        ws.append(headers)

        # Estilo de encabezados
        header_fill = PatternFill(start_color="2D3277", end_color="2D3277", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")

        for col_num in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_num)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # Filas de datos
        row_idx = 2
        for p in products:
            variants = p.variants or [None]
            for v in variants:
                sku_val = v.sku if v else "SIN-SKU"
                v_name = v.variant_name if v else "Estándar"
                barcode = (v.barcode_ean if v else "") or ""
                v_cost = float(v.cogs_cost if v else p.cost_price or 0.0)
                v_price = float((v.sale_price if (v and v.sale_price) else p.sale_price) or 0.0)

                ws.append([
                    str(p.id)[:8] + "...",
                    sku_val,
                    p.name,
                    v_name,
                    p.brand or "-",
                    p.model or "-",
                    p.category or "-",
                    barcode or "-",
                    v_cost,
                    v_price,
                    float(p.wholesale_price or 0.0),
                    float(p.min_price or 0.0),
                    p.unit_of_measure,
                    float(p.weight_kg),
                    float(p.length_cm),
                    float(p.width_cm),
                    float(p.height_cm),
                    p.warehouse_location or "-",
                    "Activo" if p.is_active else "Inactivo",
                ])

                # Formatear celdas de moneda
                ws.cell(row=row_idx, column=9).number_format = "$#,##0.00"
                ws.cell(row=row_idx, column=10).number_format = "$#,##0.00"
                ws.cell(row=row_idx, column=11).number_format = "$#,##0.00"
                ws.cell(row=row_idx, column=12).number_format = "$#,##0.00"
                row_idx += 1

        # Autoajuste de columnas
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

        file_stream = io.BytesIO()
        wb.save(file_stream)
        file_stream.seek(0)
        return file_stream

    @staticmethod
    async def detect_duplicates(session: AsyncSession, company_id: uuid.UUID) -> DuplicatesReportResponse:
        """Detecta posibles duplicados en base a código de barras EAN, SKU o nombre similar."""
        stmt = (
            select(Product)
            .where(Product.company_id == company_id)
            .options(selectinload(Product.variants))
        )
        products = (await session.execute(stmt)).scalars().all()

        duplicate_groups: list[DuplicateGroup] = []

        # 1. Agrupar por Código de Barras (EAN-13)
        ean_map: dict[str, list[DuplicateCandidate]] = {}
        for p in products:
            for v in p.variants:
                if v.barcode_ean and v.barcode_ean.strip():
                    clean_ean = v.barcode_ean.strip()
                    cand = DuplicateCandidate(
                        product_id=p.id,
                        product_name=p.name,
                        variant_id=v.id,
                        sku=v.sku,
                        barcode_ean=clean_ean,
                    )
                    ean_map.setdefault(clean_ean, []).append(cand)

        for ean, cands in ean_map.items():
            if len(cands) > 1:
                duplicate_groups.append(
                    DuplicateGroup(
                        reason="Mismo Código de Barras (EAN)",
                        key_value=ean,
                        candidates=cands,
                    )
                )

        # 2. Agrupar por Nombre Normalizado
        name_map: dict[str, list[DuplicateCandidate]] = {}
        for p in products:
            norm_name = normalize_text(p.name)
            if norm_name and len(norm_name) >= 4:
                first_variant = p.variants[0] if p.variants else None
                cand = DuplicateCandidate(
                    product_id=p.id,
                    product_name=p.name,
                    variant_id=first_variant.id if first_variant else p.id,
                    sku=first_variant.sku if first_variant else "SIN-SKU",
                    barcode_ean=first_variant.barcode_ean if first_variant else None,
                )
                name_map.setdefault(norm_name, []).append(cand)

        for norm_name, cands in name_map.items():
            if len(cands) > 1:
                duplicate_groups.append(
                    DuplicateGroup(
                        reason="Nombre o Título Idéntico",
                        key_value=cands[0].product_name,
                        candidates=cands,
                    )
                )

        return DuplicatesReportResponse(
            total_groups=len(duplicate_groups),
            duplicate_groups=duplicate_groups,
        )

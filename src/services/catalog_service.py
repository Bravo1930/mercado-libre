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

from src.connectors.meli.connector import MercadoLibreConnector
from src.connectors.meli.exceptions import MeliAPIException, MeliAuthException, MeliRateLimitException
from src.core.audit import record_audit_event
from src.core.exceptions import AppException, DuplicateEntityException, EntityNotFoundException
from src.models.meli_account import MeliAccount
from src.models.product import Product, ProductSKU, ProductVariant
from src.schemas.product import (
    DuplicateCandidate,
    DuplicateGroup,
    DuplicatesReportResponse,
    ImportSummaryResponse,
    MeliAttributePayload,
    MeliItemImportPayload,
    MeliPublishRequest,
    MeliPublishResponse,
    ProductCreate,
    ProductUpdate,
    ProductVariantCreate,
    ProductVariantUpdate,
    normalize_meli_item_id,
)


def _format_meli_cause(cause: list | None) -> str:
    """Resume el 'cause' oficial de MeLi en una línea legible.

    Las entradas suelen ser dicts con 'description' o 'message' (y a veces
    solo 'code'); también se aceptan cadenas sueltas. Se recorta para que el
    mensaje quepa en el cuadro de error del modal.
    """
    if not cause:
        return ""
    parts: list[str] = []
    for entry in cause if isinstance(cause, list) else [cause]:
        if isinstance(entry, dict):
            text = (
                entry.get("description")
                or entry.get("message")
                or entry.get("code")
                or str(entry)
            )
        else:
            text = str(entry)
        text = str(text).strip()
        if text and text not in parts:
            parts.append(text)
    return "; ".join(parts)[:500]


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

        # El código de barras vive en la VARIANTE primaria, no en el producto
        # maestro: se saca del dict antes del bucle (Product no tiene ese
        # atributo) y se aplica aparte, con validación de unicidad.
        barcode_sent = "barcode_ean" in update_dict
        barcode_ean = update_dict.pop("barcode_ean", None)

        for key, new_val in update_dict.items():
            current_val = getattr(product, key)
            if current_val != new_val:
                old_values[key] = float(current_val) if hasattr(current_val, "as_tuple") else current_val
                new_values[key] = float(new_val) if hasattr(new_val, "as_tuple") else new_val
                setattr(product, key, new_val)

        if barcode_sent:
            primary_variant = next(
                (v for v in product.variants if v.is_active), None
            ) or (product.variants[0] if product.variants else None)
            if primary_variant is not None:
                new_barcode = (barcode_ean.strip() if barcode_ean else None) or None
                if new_barcode and new_barcode != primary_variant.barcode_ean:
                    stmt_dup = (
                        select(ProductVariant)
                        .join(Product, Product.id == ProductVariant.product_id)
                        .where(
                            Product.company_id == company_id,
                            ProductVariant.barcode_ean == new_barcode,
                            ProductVariant.id != primary_variant.id,
                        )
                    )
                    if (await session.execute(stmt_dup)).scalar_one_or_none():
                        raise DuplicateEntityException(
                            f"El código de barras '{new_barcode}' ya está registrado en otro producto."
                        )
                if primary_variant.barcode_ean != new_barcode:
                    old_values["barcode_ean"] = primary_variant.barcode_ean
                    new_values["barcode_ean"] = new_barcode
                    primary_variant.barcode_ean = new_barcode

        # Fix 9 ítem 5: al editar el producto, el "Precio MeLi" guardado en
        # sus publicaciones vinculadas se refresca con el precio vigente del
        # producto (no con el de la variante, que puede traer un valor viejo).
        if product.variants and product.sale_price and float(product.sale_price) > 0:
            await cls.refresh_meli_mapping_prices(
                session,
                {v.id: float(product.sale_price) for v in product.variants},
            )

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

    @staticmethod
    def _parse_meli_item_data(item_data: dict[str, Any]) -> dict[str, Any]:
        """Extrae los datos reales de una publicación del detalle oficial
        GET /items/{id} de MeLi (título, precio, SKU del vendedor, marca,
        modelo, GTIN y fotos)."""
        attributes: dict[str, str] = {}
        for attr in item_data.get("attributes") or []:
            if not isinstance(attr, dict):
                continue
            attr_id = str(attr.get("id") or "").upper()
            value = attr.get("value_name")
            if attr_id and value:
                attributes[attr_id] = str(value)

        pictures: list[str] = []
        for pic in item_data.get("pictures") or []:
            if isinstance(pic, dict):
                url = pic.get("secure_url") or pic.get("url")
                if url:
                    pictures.append(str(url))

        shipping = item_data.get("shipping") or {}
        return {
            "title": (item_data.get("title") or "").strip(),
            "price": float(item_data.get("price") or 0),
            "seller_custom_field": item_data.get("seller_custom_field") or None,
            "category_id": item_data.get("category_id"),
            "brand": attributes.get("BRAND"),
            "model": attributes.get("MODEL"),
            "barcode_ean": attributes.get("GTIN"),
            "pictures": pictures,
            "listing_type_id": item_data.get("listing_type_id"),
            "logistic_type": shipping.get("logistic_type") if isinstance(shipping, dict) else None,
            "status": item_data.get("status"),
        }

    @classmethod
    async def _resolve_import_sku(
        cls,
        session: AsyncSession,
        company_id: uuid.UUID,
        seller_custom_field: str | None,
        item_id: str,
    ) -> str:
        """SKU para un producto recién importado, sin colisionar con los SKUs
        ya registrados en la empresa (el SKU es único por empresa)."""
        candidates: list[str] = []
        if seller_custom_field and seller_custom_field.strip():
            candidates.append(seller_custom_field.strip())
        candidates.append(f"MELI-{item_id}")
        for candidate in candidates:
            stmt = (
                select(ProductVariant)
                .join(Product, Product.id == ProductVariant.product_id)
                .where(
                    Product.company_id == company_id,
                    func.lower(ProductVariant.sku) == candidate.lower(),
                )
            )
            if not (await session.execute(stmt)).scalar_one_or_none():
                return candidate
        return f"MELI-{item_id}-{uuid.uuid4().hex[:6].upper()}"

    @staticmethod
    async def refresh_meli_mapping_prices(
        session: AsyncSession,
        prices_by_variant_id: dict[uuid.UUID, float],
    ) -> None:
        """Refresca el "Precio MeLi" guardado en las publicaciones vinculadas
        con el precio vigente que se le pase por variante (fix 9, ítem 5).

        Sin esto, el registro vinculado seguía mostrando el precio viejo
        (p. ej. $699.00) aunque el precio del producto ya se hubiera
        corregido en el catálogo.
        """
        if not prices_by_variant_id:
            return
        stmt = select(ProductSKU).where(
            ProductSKU.variant_id.in_(list(prices_by_variant_id.keys()))
        )
        for mapping in (await session.execute(stmt)).scalars().all():
            new_price = prices_by_variant_id.get(mapping.variant_id)
            if new_price is not None and float(new_price) > 0:
                mapping.price = float(new_price)

    @classmethod
    async def import_from_meli(
        cls,
        session: AsyncSession,
        company_id: uuid.UUID,
        meli_account_id: uuid.UUID,
        items: list[MeliItemImportPayload],
        user_id: uuid.UUID,
        connector: MercadoLibreConnector | None = None,
    ) -> ImportSummaryResponse:
        """Importa publicaciones desde Mercado Libre con los datos REALES del ítem.

        Fix 9 — causa raíz del desastre del 2026-11-23: el frontend NUNCA
        consultaba MeLi; fabricaba el payload en el navegador (precio fijo
        699.00, EAN aleatorio "750" + 10 dígitos, seller_custom_field
        "SKU-" + id[3:8], que para MLM-6636669962 y MLM-6636763518 daba el
        MISMO "SKU--6636"). El backend confiaba en esos valores: creaba el
        producto con precio 699 y costo 699*0.50 = 349.50, emparejaba por SKU
        y fusionaba dos publicaciones distintas en un solo producto, y al
        re-importar sobrescribía el precio corregido a mano de vuelta a 699.

        Ahora, por cada ID se consulta GET /items/{id} con el conector
        oficial y se usan título, precio, GTIN, marca, modelo y fotos
        reales. El emparejamiento es POR ID DE PUBLICACIÓN: si ya existe
        un mapeo para ese item_id exacto se actualiza ese producto (sin
        tocar precio ni costo); si no existe, SIEMPRE se crea un producto
        nuevo — nunca se cuelga un ítem distinto de un producto existente.
        """
        created_count = 0
        updated_count = 0
        linked_mappings = 0
        errors: list[str] = []

        # La cuenta MeLi (token y propiedad) es obligatoria: sin ella no hay
        # forma de consultar los datos reales de la publicación.
        stmt_account = select(MeliAccount).where(
            MeliAccount.id == meli_account_id,
            MeliAccount.company_id == company_id,
        )
        account = (await session.execute(stmt_account)).scalar_one_or_none()
        if not account:
            raise EntityNotFoundException("Cuenta de Mercado Libre", str(meli_account_id))
        if not account.is_active:
            raise AppException(
                "La cuenta de Mercado Libre está desconectada. Reconéctala antes de importar.",
                status_code=400,
                code="VALIDATION_ERROR",
            )

        meli = connector or MercadoLibreConnector(account=account, db_session=session)
        try:
            await meli.check_and_proactively_refresh()
        except (MeliAuthException, MeliAPIException) as exc:
            raise AppException(
                f"No se pudo autenticar con Mercado Libre para importar: {exc.message}",
                status_code=401,
                code="MELI_AUTH_ERROR",
            ) from exc

        for item in items:
            try:
                item_id = normalize_meli_item_id(item.id)
                if not item_id:
                    errors.append("ID de publicación vacío.")
                    continue
                # Forma con guion ("MLM-6636669962") que guardaron las
                # importaciones viejas: también hay que encontrarla.
                legacy_id = f"MLM-{item_id[3:]}" if item_id.startswith("MLM") else item_id

                # 1. Datos REALES desde MeLi (nunca del payload del frontend).
                try:
                    item_data = await meli.items.get_item(item_id)
                except Exception as exc:
                    errors.append(f"Error consultando publicación {item_id} en MeLi: {exc}")
                    continue
                real = cls._parse_meli_item_data(item_data)
                live_price = real["price"]
                if not live_price or live_price <= 0:
                    errors.append(f"La publicación {item_id} no trae un precio válido en MeLi.")
                    continue
                ean = real["barcode_ean"]

                # 2. Emparejar POR ID DE PUBLICACIÓN (el mapeo exacto manda).
                stmt_map = (
                    select(ProductSKU)
                    .where(
                        ProductSKU.meli_account_id == meli_account_id,
                        or_(
                            ProductSKU.meli_item_id == item_id,
                            ProductSKU.meli_item_id == legacy_id,
                        ),
                    )
                    .options(selectinload(ProductSKU.variant).selectinload(ProductVariant.product))
                )
                existing_map = (await session.execute(stmt_map)).scalar_one_or_none()

                if existing_map is not None and existing_map.variant is not None:
                    product = existing_map.variant.product
                    target_variant = existing_map.variant
                    # Normalizar el ID guardado a la forma canónica y
                    # refrescar el precio guardado con el precio REAL de
                    # MeLi (esto cura el "$699.00" de los registros viejos).
                    existing_map.meli_item_id = item_id
                    existing_map.price = live_price
                    # NUNCA sobrescribir precio ni costo del producto: solo
                    # rellenar campos que estén vacíos.
                    if real["brand"] and not product.brand:
                        product.brand = real["brand"]
                    if real["model"] and not product.model:
                        product.model = real["model"]
                    if real["pictures"] and not product.images:
                        product.images = real["pictures"]
                    if ean and not target_variant.barcode_ean:
                        target_variant.barcode_ean = ean
                    updated_count += 1
                else:
                    # Sin mapeo para este item_id: SIEMPRE crear un producto
                    # nuevo. Antes se emparejaba por SKU/EAN y dos ítems
                    # distintos con el mismo SKU fabricado se fusionaban.
                    sku = await cls._resolve_import_sku(
                        session, company_id, real["seller_custom_field"], item_id
                    )
                    product = Product(
                        company_id=company_id,
                        name=real["title"] or f"Publicación MeLi {item_id}",
                        brand=real["brand"],
                        model=real["model"],
                        category=real["category_id"],
                        category_code=real["category_id"],
                        sale_price=live_price,
                        cost_price=live_price * 0.50,  # Estimado inicial de costo
                        images=real["pictures"],
                        weight_kg=0.500,
                    )
                    session.add(product)
                    await session.flush()

                    target_variant = ProductVariant(
                        company_id=company_id,
                        product_id=product.id,
                        variant_name="Principal / MeLi",
                        sku=sku,
                        barcode_ean=ean,
                        cogs_cost=product.cost_price,
                        sale_price=live_price,
                    )
                    session.add(target_variant)
                    await session.flush()
                    created_count += 1

                # 3. Vincular la publicación en ProductSKU (si aún no existe
                # el mapeo para este item_id en esta cuenta).
                stmt_link = select(ProductSKU).where(
                    ProductSKU.meli_account_id == meli_account_id,
                    ProductSKU.meli_item_id == item_id,
                )
                if not (await session.execute(stmt_link)).scalar_one_or_none():
                    sku_mapping = ProductSKU(
                        company_id=company_id,
                        meli_account_id=meli_account_id,
                        variant_id=target_variant.id,
                        meli_item_id=item_id,
                        seller_sku=target_variant.sku,
                        price=live_price,
                        listing_type_id=real["listing_type_id"] or "gold_special",
                        logistic_type=real["logistic_type"] or "fulfillment",
                        status=real["status"] or "active",
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

    # ------------------------------------------------------------------
    # PUBLICACIÓN EN MERCADO LIBRE (POST /items)
    # ------------------------------------------------------------------
    @classmethod
    def _build_meli_item_payload(
        cls,
        *,
        product: Product,
        variant: ProductVariant,
        payload: MeliPublishRequest,
    ) -> tuple[dict[str, Any], str, float, list[str]]:
        """Arma el payload oficial de POST /items y valida lo que MeLi exige.

        Devuelve (payload_meli, título_final, precio_final, fotos_finales).
        Lanza AppException 400 con un mensaje claro cuando falta un dato
        que Mercado Libre rechazaría de todos modos.
        """
        title = (payload.title or product.name or "").strip()
        if not title:
            raise AppException(
                "El producto necesita un título para publicarse en Mercado Libre.",
                status_code=400,
                code="VALIDATION_ERROR",
            )
        if len(title) > 60:
            raise AppException(
                f"El título tiene {len(title)} caracteres y Mercado Libre acepta máximo 60: '{title}'",
                status_code=400,
                code="VALIDATION_ERROR",
            )

        price = payload.price or variant.sale_price or product.sale_price
        if not price or float(price) <= 0:
            raise AppException(
                "El producto necesita un precio mayor a 0 para publicarse en Mercado Libre.",
                status_code=400,
                code="VALIDATION_ERROR",
            )
        price = float(price)

        pictures = list(payload.pictures or product.images or [])
        if not pictures:
            raise AppException(
                "Se requiere al menos una foto (URL pública) para publicar en Mercado Libre.",
                status_code=400,
                code="VALIDATION_ERROR",
            )

        # Atributos: BRAND / MODEL / GTIN / COLOR se completan solos cuando
        # existen; los extras del request prevalecen si repiten un mismo id y
        # viajan TAL CUAL (con value_id y/o value_name) en el POST /items —
        # MeLi los valida. Esto es lo que permite mandar atributos de catálogo
        # obligatorios como CONNECTOR_TYPE ("Tipo de conector") en MLM429747:
        # sin él MeLi responde 400 ("The attributes [CONNECTOR_TYPE] are
        # required for category MLM429747..."). Antes los extras se reducían
        # a value_name y se perdía el value_id del catálogo.
        attributes: dict[str, dict] = {}
        if product.brand:
            attributes["BRAND"] = {"id": "BRAND", "value_name": product.brand}
        if product.model:
            attributes["MODEL"] = {"id": "MODEL", "value_name": product.model}
        if variant.barcode_ean:
            attributes["GTIN"] = {"id": "GTIN", "value_name": variant.barcode_ean}
        variant_color = (variant.attributes or {}).get("color")
        if variant_color:
            attributes["COLOR"] = {"id": "COLOR", "value_name": str(variant_color)}
        for extra in payload.attributes or []:
            attr: dict[str, str] = {"id": extra.id}
            if extra.value_id:
                attr["value_id"] = extra.value_id
            if extra.value_name:
                attr["value_name"] = extra.value_name
            attributes[extra.id] = attr

        meli_payload: dict[str, Any] = {
            # NO se manda "title": en el modelo User Products de MeLi (el que
            # rige las categorías con dominio de catálogo, como MLM7533) el
            # título lo completa Mercado Libre solo a partir de family_name +
            # atributos; mandar "title" hace que POST /items responda 400
            # body.invalid_fields "The fields [title] are invalid for
            # requested call." (visto 2026-11-23 con dos títulos distintos,
            # con y sin marca+modelo). Doc oficial: developers.mercadolibre
            # .com.mx/en_us/user-products — "it will not be possible to
            # publish with the previous model (using title and variations
            # array)"; family_name debe ser <= max_title_length del dominio.
            "family_name": title,
            "category_id": payload.category_id,
            "price": price,
            "currency_id": "MXN",
            "available_quantity": payload.available_quantity,
            "buying_mode": "buy_it_now",
            "listing_type_id": payload.listing_type_id,
            "condition": "new",
            "pictures": [{"source": url} for url in pictures],
            "sale_terms": [
                {"id": "WARRANTY_TYPE", "value_name": payload.warranty_type},
                {"id": "WARRANTY_TIME", "value_name": payload.warranty_time},
            ],
            "shipping": {"mode": "me2", "local_pick_up": False, "free_shipping": False},
        }
        if attributes:
            meli_payload["attributes"] = list(attributes.values())
        return meli_payload, title, price, pictures

    @classmethod
    async def publish_to_meli(
        cls,
        session: AsyncSession,
        company_id: uuid.UUID,
        product_id: uuid.UUID,
        payload: MeliPublishRequest,
        user_id: uuid.UUID,
        connector: MercadoLibreConnector | None = None,
    ) -> MeliPublishResponse:
        """Publica una variante del catálogo en Mercado Libre México.

        1. Valida producto, variante y cuenta MeLi (todas de la empresa activa).
        2. Crea la publicación con POST /items (conector oficial).
        3. Guarda la descripción con PUT /items/{id}/description (best-effort:
           si falla, la publicación ya existe y el fallo se reporta sin abortar).
        4. Crea el mapeo interno variante <-> publicación (ProductSKU) para que
           pedidos, stock y precios se gestionen desde el ERP.
        El parámetro `connector` existe solo para pruebas (inyección del conector).
        """
        stmt_product = (
            select(Product)
            .where(Product.id == product_id, Product.company_id == company_id)
            .options(selectinload(Product.variants))
        )
        product = (await session.execute(stmt_product)).scalar_one_or_none()
        if not product:
            raise EntityNotFoundException("Producto", str(product_id))

        variant: ProductVariant | None = None
        if payload.variant_id:
            variant = next((v for v in product.variants if v.id == payload.variant_id), None)
            if not variant:
                raise EntityNotFoundException("Variante de Producto", str(payload.variant_id))
        else:
            variant = next((v for v in product.variants if v.is_active), None) or (
                product.variants[0] if product.variants else None
            )
        if not variant:
            raise AppException(
                "El producto no tiene variantes para publicar en Mercado Libre.",
                status_code=400,
                code="VALIDATION_ERROR",
            )

        stmt_account = select(MeliAccount).where(
            MeliAccount.id == payload.meli_account_id,
            MeliAccount.company_id == company_id,
        )
        account = (await session.execute(stmt_account)).scalar_one_or_none()
        if not account:
            raise EntityNotFoundException("Cuenta de Mercado Libre", str(payload.meli_account_id))
        if not account.is_active:
            raise AppException(
                "La cuenta de Mercado Libre está desconectada. Reconéctala antes de publicar.",
                status_code=400,
                code="VALIDATION_ERROR",
            )

        meli_payload, title, price, _pictures = cls._build_meli_item_payload(
            product=product, variant=variant, payload=payload
        )

        meli = connector or MercadoLibreConnector(account=account, db_session=session)
        try:
            await meli.check_and_proactively_refresh()
            created = await meli.items.create_item(meli_payload)
        except MeliAuthException as exc:
            raise AppException(
                f"Mercado Libre rechazó las credenciales de la cuenta: {exc.message}",
                status_code=401,
                code="MELI_AUTH_ERROR",
                details={"meli_error": exc.error_code, "cause": exc.cause},
            ) from exc
        except MeliRateLimitException as exc:
            raise AppException(
                "Mercado Libre limitó las llamadas (HTTP 429). Inténtalo de nuevo en unos minutos.",
                status_code=429,
                code="MELI_RATE_LIMIT",
            ) from exc
        except MeliAPIException as exc:
            # El "cause" oficial de MeLi es lo que nombra el campo faltante
            # (p. ej. body.required_fields); sin él el mensaje es solo un código.
            # Pero en algunos errores (p. ej. body.invalid_fields) el "cause"
            # viene VACÍO y el detalle vive en "error" (p. ej. "The fields
            # [title] are invalid for requested call."): sin surfacerlo, el
            # cuadro rojo del modal no dice qué campo falló.
            cause_detail = _format_meli_cause(exc.cause)
            if not cause_detail:
                _generic = {
                    "validation_error",
                    "bad_request",
                    "unknown_error",
                    "meli_api_error",
                }
                if exc.error_code and exc.error_code not in _generic and exc.error_code != exc.message:
                    cause_detail = exc.error_code
            message = f"Mercado Libre rechazó la publicación: {exc.message}"
            if cause_detail:
                message += f" ({cause_detail})"
            raise AppException(
                message,
                status_code=400,
                code="MELI_PUBLISH_ERROR",
                details={"meli_error": exc.error_code, "cause": exc.cause},
            ) from exc

        meli_item_id = str(created.get("id", ""))
        if not meli_item_id:
            raise AppException(
                "Mercado Libre no devolvió el ID de la publicación creada.",
                status_code=502,
                code="MELI_PUBLISH_ERROR",
                details={"meli_response": created},
            )
        permalink = created.get("permalink")

        # Mapeo interno variante <-> publicación (nunca perder el vínculo).
        stmt_map = select(ProductSKU).where(
            ProductSKU.meli_account_id == account.id,
            ProductSKU.meli_item_id == meli_item_id,
        )
        existing_map = (await session.execute(stmt_map)).scalar_one_or_none()
        if existing_map:
            existing_map.variant_id = variant.id
            existing_map.price = price
            existing_map.listing_type_id = payload.listing_type_id
            existing_map.status = "active"
            sku_mapping = existing_map
        else:
            sku_mapping = ProductSKU(
                company_id=company_id,
                meli_account_id=account.id,
                variant_id=variant.id,
                meli_item_id=meli_item_id,
                seller_sku=variant.sku,
                price=price,
                listing_type_id=payload.listing_type_id,
                logistic_type="fulfillment",
                status="active",
            )
            session.add(sku_mapping)
        await session.flush()

        # Descripción: endpoint separado en MeLi; si falla, la publicación
        # ya existe y solo se reporta el fallo, no se aborta nada.
        description_error: str | None = None
        description = (payload.description or product.description or product.short_description or "").strip()
        if description:
            try:
                await meli.items.update_description(meli_item_id, description)
            except MeliAPIException as exc:
                description_error = f"No se pudo guardar la descripción: {exc.message}"

        await record_audit_event(
            session=session,
            company_id=company_id,
            action="PUBLISH_MELI_ITEM",
            entity_name="ProductSKU",
            entity_id=str(sku_mapping.id),
            user_id=user_id,
            changes={
                "meli_item_id": meli_item_id,
                "variant_id": str(variant.id),
                "price": price,
                "listing_type_id": payload.listing_type_id,
                "permalink": permalink,
            },
        )

        return MeliPublishResponse(
            meli_item_id=meli_item_id,
            permalink=permalink,
            title=title,
            price=price,
            listing_type_id=payload.listing_type_id,
            status=str(created.get("status", "active")),
            variant_id=variant.id,
            product_sku_id=sku_mapping.id,
            description_error=description_error,
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

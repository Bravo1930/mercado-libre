"""
Servicio Empresarial de Abastecimiento, Proveedores, Órdenes de Compra,
Recepciones Parciales, Actualización Transaccional de Inventario,
Facturas, Gastos Asociados (Landed Cost) y Motor Inteligente de Reposición.
"""

import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.audit import record_audit_event
from src.core.exceptions import AppException, EntityNotFoundException, ValidationException
from src.core.logging import get_logger
from src.models.order import Order, OrderItem
from src.models.product import Product, ProductVariant
from src.models.profitability import CostHistory
from src.models.supplier import (
    GoodsReceipt,
    GoodsReceiptItem,
    PurchaseExpense,
    PurchaseInvoice,
    PurchaseOrder,
    PurchaseOrderItem,
    Supplier,
    SupplierEvaluation,
    SupplierProduct,
)
from src.models.warehouse import Inventory, InventoryMovement, Warehouse
from src.schemas.supplier import (
    CreatePOFromSuggestionsRequest,
    GoodsReceiptCreate,
    LandedCostItemResponse,
    LandedCostSummaryResponse,
    PurchaseExpenseCreate,
    PurchaseInvoiceCreate,
    PurchaseOrderCreate,
    PurchaseOrderItemCreate,
    PurchaseOrderUpdate,
    ReplenishmentReportResponse,
    ReplenishmentSuggestionItem,
    SupplierCreate,
    SupplierEvaluationCreate,
    SupplierProductCreate,
    SupplierProductUpdate,
    SupplierUpdate,
)
from src.schemas.profitability import CostHistoryCreateRequest
from src.services.inventory_service import InventoryService
from src.services.profitability_service import ProfitabilityService

logger = get_logger("procurement_service")


def _norm_dt(dt: datetime | None) -> datetime:
    """Asegura datetime con timezone UTC."""
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class ProcurementService:
    def __init__(self):
        self.inventory_service = InventoryService()
        self.profitability_service = ProfitabilityService()

    # ===========================================================================
    # 1. GESTIÓN DE PROVEEDORES (DIRECTORIO Y CONTACTO)
    # ===========================================================================

    async def create_supplier(
        self, session: AsyncSession, company_id: uuid.UUID, payload: SupplierCreate, user_id: uuid.UUID | None = None
    ) -> Supplier:
        """Registra un nuevo proveedor asegurando código único y auditoría."""
        code = payload.code
        if not code:
            # Generar código automático incremental (PROV-0001)
            count_stmt = select(func.count(Supplier.id)).where(Supplier.company_id == company_id)
            total = (await session.execute(count_stmt)).scalar() or 0
            code = f"PROV-{total + 1:04d}"

        supplier = Supplier(
            company_id=company_id,
            code=code,
            name=payload.name,
            commercial_name=payload.commercial_name,
            rfc=payload.rfc.upper() if payload.rfc else None,
            contact_name=payload.contact_name,
            email=payload.email,
            phone=payload.phone,
            website=payload.website,
            address_street=payload.address_street,
            address_exterior=payload.address_exterior,
            address_interior=payload.address_interior,
            address_neighborhood=payload.address_neighborhood,
            address_city=payload.address_city,
            address_state=payload.address_state,
            address_zip=payload.address_zip,
            address_country=payload.address_country or "MEX",
            payment_terms_days=payload.payment_terms_days,
            lead_time_days=payload.lead_time_days,
            credit_limit=payload.credit_limit,
            currency=payload.currency or "MXN",
            bank_name=payload.bank_name,
            bank_clabe=payload.bank_clabe,
            notes=payload.notes,
            is_active=True,
        )
        session.add(supplier)
        await session.flush()

        if user_id:
            await record_audit_event(
                session=session,
                action="CREATE_SUPPLIER",
                entity_name="Supplier",
                entity_id=str(supplier.id),
                company_id=company_id,
                user_id=user_id,
                changes={"name": supplier.name, "code": supplier.code, "rfc": supplier.rfc},
            )

        return supplier

    async def update_supplier(
        self, session: AsyncSession, company_id: uuid.UUID, supplier_id: uuid.UUID, payload: SupplierUpdate, user_id: uuid.UUID | None = None
    ) -> Supplier:
        """Actualiza la información de un proveedor existente."""
        supplier = await self.get_supplier(session, company_id, supplier_id)
        update_data = payload.model_dump(exclude_unset=True)

        for key, val in update_data.items():
            if hasattr(supplier, key) and val is not None:
                if key == "rfc" and val:
                    val = val.upper()
                setattr(supplier, key, val)

        await session.flush()

        if user_id:
            await record_audit_event(
                session=session,
                action="UPDATE_SUPPLIER",
                entity_name="Supplier",
                entity_id=str(supplier.id),
                company_id=company_id,
                user_id=user_id,
                changes=update_data,
            )

        return supplier

    async def get_supplier(
        self, session: AsyncSession, company_id: uuid.UUID, supplier_id: uuid.UUID
    ) -> Supplier:
        """Obtiene un proveedor por ID verificando aislamiento de empresa."""
        stmt = (
            select(Supplier)
            .where(Supplier.id == supplier_id, Supplier.company_id == company_id)
            .options(
                selectinload(Supplier.supplied_products).selectinload(SupplierProduct.variant),
                selectinload(Supplier.evaluations),
            )
        )
        supplier = (await session.execute(stmt)).scalar_one_or_none()
        if not supplier:
            raise EntityNotFoundException("Supplier", str(supplier_id))
        return supplier

    async def list_suppliers(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        search: str | None = None,
        is_active: bool | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Supplier], int]:
        """Lista proveedores paginados con filtros de búsqueda."""
        stmt = select(Supplier).where(Supplier.company_id == company_id)

        if is_active is not None:
            stmt = stmt.where(Supplier.is_active == is_active)

        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    Supplier.name.ilike(pattern),
                    Supplier.commercial_name.ilike(pattern),
                    Supplier.code.ilike(pattern),
                    Supplier.rfc.ilike(pattern),
                    Supplier.contact_name.ilike(pattern),
                )
            )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await session.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(Supplier.name.asc()).offset(offset).limit(limit)
        items = (await session.execute(stmt)).scalars().all()
        return list(items), total

    async def delete_supplier(
        self, session: AsyncSession, company_id: uuid.UUID, supplier_id: uuid.UUID
    ) -> None:
        """Desactiva o elimina un proveedor."""
        supplier = await self.get_supplier(session, company_id, supplier_id)
        supplier.is_active = False
        await session.flush()

    # ===========================================================================
    # 2. CATÁLOGO DE PRODUCTOS SUMINISTRADOS POR PROVEEDOR
    # ===========================================================================

    async def link_supplier_product(
        self, session: AsyncSession, company_id: uuid.UUID, supplier_id: uuid.UUID, payload: SupplierProductCreate
    ) -> SupplierProduct:
        """Asocia un producto/variante al catálogo de un proveedor."""
        # Verificar proveedor
        await self.get_supplier(session, company_id, supplier_id)

        # Verificar variante
        var_stmt = select(ProductVariant).where(ProductVariant.id == payload.variant_id)
        variant = (await session.execute(var_stmt)).scalar_one_or_none()
        if not variant:
            raise EntityNotFoundException("ProductVariant", str(payload.variant_id))

        product_id = payload.product_id or variant.product_id

        # Si ya existe asociación, actualizar
        stmt = select(SupplierProduct).where(
            SupplierProduct.company_id == company_id,
            SupplierProduct.supplier_id == supplier_id,
            SupplierProduct.variant_id == payload.variant_id,
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()

        if existing:
            existing.purchase_cost = payload.purchase_cost
            existing.currency = payload.currency
            existing.tax_rate = payload.tax_rate
            existing.min_order_quantity = payload.min_order_quantity
            existing.package_quantity = payload.package_quantity
            existing.lead_time_days = payload.lead_time_days
            existing.is_preferred = payload.is_preferred
            existing.supplier_sku = payload.supplier_sku or existing.supplier_sku
            existing.supplier_product_name = payload.supplier_product_name or existing.supplier_product_name
            existing.is_active = True
            await session.flush()
            return existing

        # Si se marca como preferido, desmarcar otros proveedores preferidos para esta variante
        if payload.is_preferred:
            await self._unset_preferred_supplier(session, company_id, payload.variant_id)

        supp_prod = SupplierProduct(
            company_id=company_id,
            supplier_id=supplier_id,
            product_id=product_id,
            variant_id=payload.variant_id,
            supplier_sku=payload.supplier_sku,
            supplier_product_name=payload.supplier_product_name,
            purchase_cost=payload.purchase_cost,
            currency=payload.currency,
            tax_rate=payload.tax_rate,
            min_order_quantity=payload.min_order_quantity,
            package_quantity=payload.package_quantity,
            lead_time_days=payload.lead_time_days,
            is_preferred=payload.is_preferred,
            is_active=True,
        )
        session.add(supp_prod)
        await session.flush()
        return supp_prod

    async def _unset_preferred_supplier(self, session: AsyncSession, company_id: uuid.UUID, variant_id: uuid.UUID):
        stmt = (
            select(SupplierProduct)
            .where(SupplierProduct.company_id == company_id, SupplierProduct.variant_id == variant_id, SupplierProduct.is_preferred == True)
        )
        others = (await session.execute(stmt)).scalars().all()
        for o in others:
            o.is_preferred = False
        await session.flush()

    async def list_supplier_products(
        self, session: AsyncSession, company_id: uuid.UUID, supplier_id: uuid.UUID
    ) -> list[SupplierProduct]:
        """Lista los productos y variantes que suministra un proveedor."""
        stmt = (
            select(SupplierProduct)
            .where(SupplierProduct.company_id == company_id, SupplierProduct.supplier_id == supplier_id, SupplierProduct.is_active == True)
            .options(
                selectinload(SupplierProduct.variant),
                selectinload(SupplierProduct.product),
            )
            .order_by(SupplierProduct.created_at.desc())
        )
        return list((await session.execute(stmt)).scalars().all())

    async def remove_supplier_product(
        self, session: AsyncSession, company_id: uuid.UUID, supplier_id: uuid.UUID, variant_id: uuid.UUID
    ) -> None:
        """Desasocia un producto del catálogo del proveedor."""
        stmt = select(SupplierProduct).where(
            SupplierProduct.company_id == company_id,
            SupplierProduct.supplier_id == supplier_id,
            SupplierProduct.variant_id == variant_id,
        )
        sp = (await session.execute(stmt)).scalar_one_or_none()
        if sp:
            sp.is_active = False
            await session.flush()

    # ===========================================================================
    # 3. EVALUACIÓN Y RENDIMIENTO DE PROVEEDORES
    # ===========================================================================

    async def create_evaluation(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        supplier_id: uuid.UUID,
        payload: SupplierEvaluationCreate,
        user_id: uuid.UUID | None = None,
        evaluator_name: str = "Auditor Compras",
    ) -> SupplierEvaluation:
        """Registra una evaluación de proveedor y recalcula el puntaje general."""
        supplier = await self.get_supplier(session, company_id, supplier_id)

        # Cálculo de promedio ponderado: puntualidad 35%, calidad 35%, precio 15%, comunicación 15%
        overall = round(
            (payload.delivery_score * 0.35)
            + (payload.quality_score * 0.35)
            + (payload.price_score * 0.15)
            + (payload.communication_score * 0.15),
            2,
        )

        evaluation = SupplierEvaluation(
            company_id=company_id,
            supplier_id=supplier_id,
            purchase_order_id=payload.purchase_order_id,
            evaluation_date=datetime.now(timezone.utc),
            evaluated_by_user_id=user_id,
            evaluator_name=evaluator_name,
            delivery_score=payload.delivery_score,
            quality_score=payload.quality_score,
            price_score=payload.price_score,
            communication_score=payload.communication_score,
            overall_score=overall,
            comments=payload.comments,
            action_plan=payload.action_plan,
        )
        session.add(evaluation)
        await session.flush()

        # Recalcular score promedio del proveedor
        avg_stmt = select(func.avg(SupplierEvaluation.overall_score)).where(
            SupplierEvaluation.company_id == company_id, SupplierEvaluation.supplier_id == supplier_id
        )
        new_rating = (await session.execute(avg_stmt)).scalar()
        if new_rating:
            supplier.rating_score = round(float(new_rating), 2)
            await session.flush()

        return evaluation

    async def list_evaluations(
        self, session: AsyncSession, company_id: uuid.UUID, supplier_id: uuid.UUID
    ) -> list[SupplierEvaluation]:
        """Lista el historial de evaluaciones de un proveedor."""
        stmt = (
            select(SupplierEvaluation)
            .where(SupplierEvaluation.company_id == company_id, SupplierEvaluation.supplier_id == supplier_id)
            .order_by(SupplierEvaluation.evaluation_date.desc())
        )
        return list((await session.execute(stmt)).scalars().all())

    # ===========================================================================
    # 4. ÓRDENES DE COMPRA (WORKFLOW Y AUTORIZACIÓN ESTRICTA)
    # ===========================================================================

    async def create_purchase_order(
        self, session: AsyncSession, company_id: uuid.UUID, payload: PurchaseOrderCreate, user_id: uuid.UUID | None = None
    ) -> PurchaseOrder:
        """
        Crea una orden de compra en estado borrador (draft).
        Garantiza: 'No generar compras ni pagos reales sin autorización'.
        """
        # Verificar proveedor
        supplier = await self.get_supplier(session, company_id, payload.supplier_id)

        # Verificar unicidad de número de orden
        exist_stmt = select(PurchaseOrder).where(
            PurchaseOrder.company_id == company_id, PurchaseOrder.po_number == payload.po_number
        )
        if (await session.execute(exist_stmt)).scalar_one_or_none():
            raise ValidationException(f"Ya existe una orden de compra con el folio {payload.po_number}")

        # Calcular partidas y montos
        subtotal = 0.0
        tax_total = 0.0
        items_to_create = []

        for item_in in payload.items:
            var_stmt = select(ProductVariant).where(ProductVariant.id == item_in.variant_id)
            variant = (await session.execute(var_stmt)).scalar_one_or_none()
            if not variant:
                raise EntityNotFoundException("ProductVariant", str(item_in.variant_id))

            sku = item_in.sku or variant.sku
            prod_name = item_in.product_name or variant.variant_name
            tax_rate = item_in.tax_rate or 0.1600
            line_cost = round(item_in.quantity_ordered * item_in.unit_cost, 2)
            line_tax = round(line_cost * tax_rate, 2)

            subtotal += line_cost
            tax_total += line_tax

            items_to_create.append(
                PurchaseOrderItem(
                    product_id=variant.product_id,
                    variant_id=variant.id,
                    sku=sku,
                    product_name=prod_name,
                    quantity_ordered=item_in.quantity_ordered,
                    quantity_received=0,
                    quantity_pending=item_in.quantity_ordered,
                    unit_cost=item_in.unit_cost,
                    tax_rate=tax_rate,
                    total_cost=line_cost,
                    status="pending",
                )
            )

        total_amount = round(subtotal + tax_total + payload.shipping_cost + payload.other_expenses, 2)

        po = PurchaseOrder(
            company_id=company_id,
            supplier_id=payload.supplier_id,
            warehouse_id=payload.warehouse_id,
            po_number=payload.po_number,
            status="draft",  # Borrador no autorizado
            order_date=datetime.now(timezone.utc),
            expected_delivery_date=payload.expected_delivery_date or (datetime.now(timezone.utc) + timedelta(days=supplier.lead_time_days)),
            currency=supplier.currency or "MXN",
            subtotal=round(subtotal, 2),
            tax_amount=round(tax_total, 2),
            shipping_cost=payload.shipping_cost,
            other_expenses=payload.other_expenses,
            total_amount=total_amount,
            payment_terms_days=supplier.payment_terms_days,
            payment_status="unpaid",
            payment_authorized=False,
            notes=payload.notes,
            items=items_to_create,
        )
        session.add(po)
        await session.flush()

        if user_id:
            await record_audit_event(
                session=session,
                action="CREATE_PURCHASE_ORDER",
                entity_name="PurchaseOrder",
                entity_id=str(po.id),
                company_id=company_id,
                user_id=user_id,
                changes={"po_number": po.po_number, "status": po.status, "total_amount": float(total_amount)},
            )

        return po

    async def get_purchase_order(
        self, session: AsyncSession, company_id: uuid.UUID, po_id: uuid.UUID
    ) -> PurchaseOrder:
        """Obtiene una orden de compra con sus partidas, recepciones y facturas."""
        stmt = (
            select(PurchaseOrder)
            .where(PurchaseOrder.id == po_id, PurchaseOrder.company_id == company_id)
            .options(
                selectinload(PurchaseOrder.supplier),
                selectinload(PurchaseOrder.warehouse),
                selectinload(PurchaseOrder.items).selectinload(PurchaseOrderItem.variant),
                selectinload(PurchaseOrder.receipts).selectinload(GoodsReceipt.items),
                selectinload(PurchaseOrder.invoices),
                selectinload(PurchaseOrder.expenses),
            )
        )
        po = (await session.execute(stmt)).scalar_one_or_none()
        if not po:
            raise EntityNotFoundException("PurchaseOrder", str(po_id))
        return po

    async def list_purchase_orders(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        supplier_id: uuid.UUID | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[PurchaseOrder], int]:
        """Lista órdenes de compra con filtros por proveedor o estado."""
        stmt = (
            select(PurchaseOrder)
            .where(PurchaseOrder.company_id == company_id)
            .options(
                selectinload(PurchaseOrder.supplier),
                selectinload(PurchaseOrder.items),
            )
        )
        if supplier_id:
            stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)
        if status:
            stmt = stmt.where(PurchaseOrder.status == status)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await session.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(PurchaseOrder.created_at.desc()).offset(offset).limit(limit)
        items = (await session.execute(stmt)).scalars().all()
        return list(items), total

    async def approve_purchase_order(
        self, session: AsyncSession, company_id: uuid.UUID, po_id: uuid.UUID, user_id: uuid.UUID, notes: str | None = None
    ) -> PurchaseOrder:
        """
        Autorización obligatoria de compra por parte de un usuario facultado.
        Garantiza: 'No generar compras ni pagos reales sin autorización'.
        """
        po = await self.get_purchase_order(session, company_id, po_id)
        if po.status not in ["draft", "pending_approval"]:
            raise ValidationException(f"No se puede autorizar una orden en estado '{po.status}' (debe estar en borrador o pendiente).")

        po.status = "approved"
        po.approved_by_user_id = user_id
        po.approved_at = datetime.now(timezone.utc)
        if notes:
            po.notes = f"{po.notes or ''}\n[Autorización {datetime.now(timezone.utc).strftime('%Y-%m-%d')}]: {notes}".strip()

        await session.flush()
        await record_audit_event(
            session=session,
            action="APPROVE_PURCHASE_ORDER",
            entity_name="PurchaseOrder",
            entity_id=str(po.id),
            company_id=company_id,
            user_id=user_id,
            changes={"status": "approved", "approved_at": po.approved_at.isoformat()},
        )
        return po

    async def issue_purchase_order(
        self, session: AsyncSession, company_id: uuid.UUID, po_id: uuid.UUID, user_id: uuid.UUID
    ) -> PurchaseOrder:
        """Emite formalmente la orden de compra al proveedor tras haber sido autorizada."""
        po = await self.get_purchase_order(session, company_id, po_id)
        if po.status != "approved":
            raise ValidationException("La orden debe ser autorizada formalmente antes de emitirse al proveedor.")

        po.status = "issued"
        await session.flush()
        await record_audit_event(
            session=session,
            action="ISSUE_PURCHASE_ORDER",
            entity_name="PurchaseOrder",
            entity_id=str(po.id),
            company_id=company_id,
            user_id=user_id,
            changes={"status": "issued"},
        )
        return po

    async def cancel_purchase_order(
        self, session: AsyncSession, company_id: uuid.UUID, po_id: uuid.UUID, reason: str, user_id: uuid.UUID
    ) -> PurchaseOrder:
        """Cancela una orden de compra con motivo auditado si no ha sido recibida."""
        po = await self.get_purchase_order(session, company_id, po_id)
        if po.status in ["received", "closed"]:
            raise ValidationException("No se puede cancelar una orden de compra que ya ha sido recibida por completo.")

        po.status = "cancelled"
        po.cancellation_reason = reason
        await session.flush()

        await record_audit_event(
            session=session,
            action="CANCEL_PURCHASE_ORDER",
            entity_name="PurchaseOrder",
            entity_id=str(po.id),
            company_id=company_id,
            user_id=user_id,
            changes={"status": "cancelled", "reason": reason},
        )
        return po

    async def authorize_payment(
        self, session: AsyncSession, company_id: uuid.UUID, po_id: uuid.UUID, user_id: uuid.UUID, notes: str | None = None
    ) -> PurchaseOrder:
        """Autoriza el desembolso financiero y pago formal a proveedor."""
        po = await self.get_purchase_order(session, company_id, po_id)
        po.payment_authorized = True
        po.payment_authorized_by_user_id = user_id
        po.payment_authorized_at = datetime.now(timezone.utc)
        if notes:
            po.notes = f"{po.notes or ''}\n[Pago Autorizado]: {notes}".strip()

        await session.flush()
        await record_audit_event(
            session=session,
            action="AUTHORIZE_PURCHASE_PAYMENT",
            entity_name="PurchaseOrder",
            entity_id=str(po.id),
            company_id=company_id,
            user_id=user_id,
            changes={"payment_authorized": True, "total_amount": float(po.total_amount)},
        )
        return po

    # ===========================================================================
    # 5. RECEPCIÓN DE MERCANCÍA (PARCIALES/TOTALES) Y ACTUALIZACIÓN AUDITABLE
    # ===========================================================================

    async def create_goods_receipt(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        po_id: uuid.UUID,
        payload: GoodsReceiptCreate,
        user_id: uuid.UUID | None = None,
        user_name: str = "Encargado Almacén",
    ) -> GoodsReceipt:
        """
        Registra la recepción física de mercancía en almacén (Goods Receipt Note).
        - Soporta recepciones parciales y rechazos por daño.
        - Actualiza el inventario transaccionalmente creando movimientos de tipo INBOUND en el Kardex.
        - Actualiza el costo COGS en el catálogo y registra el historial inmutable de costos.
        - Actualiza el estado de la Orden de Compra (partially_received o received).
        """
        po = await self.get_purchase_order(session, company_id, po_id)
        if po.status not in ["approved", "issued", "partially_received"]:
            raise ValidationException(
                f"No se puede recibir mercancía de una orden en estado '{po.status}' (debe estar autorizada, emitida o parcialmente recibida)."
            )

        # Almacén destino
        warehouse_id = payload.warehouse_id or po.warehouse_id
        if not warehouse_id:
            # Buscar primer almacén activo de la empresa
            wh_stmt = select(Warehouse).where(Warehouse.company_id == company_id, Warehouse.is_active == True)
            first_wh = (await session.execute(wh_stmt)).scalar_one_or_none()
            if not first_wh:
                raise ValidationException("No existe ningún almacén activo configurado para recibir mercancía.")
            warehouse_id = first_wh.id

        # Mapear partidas de la OC
        po_items_map = {item.id: item for item in po.items}

        receipt_items_to_create = []
        total_accepted_units = 0

        for it in payload.items:
            po_item = po_items_map.get(it.purchase_order_item_id)
            if not po_item:
                raise ValidationException(f"La partida de OC {it.purchase_order_item_id} no pertenece a esta orden.")

            accepted_qty = it.quantity_received
            rejected_qty = it.quantity_rejected

            if accepted_qty + rejected_qty <= 0:
                continue

            # Validar que no se reciba más de lo pendiente
            if accepted_qty > po_item.quantity_pending:
                raise ValidationException(
                    f"Cantidad recibida ({accepted_qty}) supera la cantidad pendiente ({po_item.quantity_pending}) para el SKU {po_item.sku}"
                )

            unit_cost = it.unit_cost if it.unit_cost is not None else float(po_item.unit_cost)

            receipt_item = GoodsReceiptItem(
                purchase_order_item_id=po_item.id,
                variant_id=po_item.variant_id,
                sku=po_item.sku,
                quantity_received=accepted_qty,
                quantity_rejected=rejected_qty,
                rejection_reason=it.rejection_reason,
                unit_cost=unit_cost,
                batch_number=it.batch_number,
                expiry_date=it.expiry_date,
                location_bin=it.location_bin,
            )
            receipt_items_to_create.append(receipt_item)

            # 1. Actualizar partida de la Orden de Compra
            po_item.quantity_received += accepted_qty
            po_item.quantity_pending = max(0, po_item.quantity_ordered - po_item.quantity_received)
            if po_item.quantity_pending == 0:
                po_item.status = "completed"
            else:
                po_item.status = "partially_received"

            # 2. Actualizar Inventario Físico Transaccionalmente mediante InventoryService
            if accepted_qty > 0:
                total_accepted_units += accepted_qty
                await self.inventory_service.adjust_stock(
                    session=session,
                    warehouse_id=warehouse_id,
                    variant_id=po_item.variant_id,
                    quantity_delta=accepted_qty,
                    movement_type="INBOUND",
                    reference_id=str(payload.receipt_number),
                    reference_type="purchase_order",
                    condition="good",
                    user_id=user_id,
                    notes=f"Recepción #{payload.receipt_number} de OC #{po.po_number}",
                )

                # 3. Actualizar COGS en ProductVariant y registrar trazabilidad inmutable en CostHistory
                var_stmt = select(ProductVariant).where(ProductVariant.id == po_item.variant_id)
                variant = (await session.execute(var_stmt)).scalar_one_or_none()
                if variant:
                    variant.cogs_cost = unit_cost
                    # Registrar en historial inmutable de costos de rentabilidad
                    await self.profitability_service.record_cost_change(
                        session=session,
                        company_id=company_id,
                        payload=CostHistoryCreateRequest(
                            sku=po_item.sku,
                            new_cogs=unit_cost,
                            change_reason="purchase_order",
                            notes=f"Actualización por recepción #{payload.receipt_number} de OC #{po.po_number} ({accepted_qty} unidades)",
                            variant_id=po_item.variant_id,
                            product_id=po_item.product_id,
                        ),
                        user_id=user_id,
                    )

        if not receipt_items_to_create:
            raise ValidationException("Debe especificar al menos una partida con unidades recibidas o rechazadas.")

        receipt = GoodsReceipt(
            company_id=company_id,
            purchase_order_id=po.id,
            supplier_id=po.supplier_id,
            warehouse_id=warehouse_id,
            receipt_number=payload.receipt_number,
            receipt_date=_norm_dt(payload.receipt_date),
            delivery_note_number=payload.delivery_note_number,
            carrier=payload.carrier,
            tracking_number=payload.tracking_number,
            status="confirmed",
            received_by_user_id=user_id,
            received_by_name=user_name,
            notes=payload.notes,
            items=receipt_items_to_create,
        )
        session.add(receipt)
        await session.flush()

        # Actualizar estado de la Orden de Compra global
        all_completed = all(it.quantity_pending == 0 for it in po.items)
        if all_completed:
            po.status = "received"
        else:
            po.status = "partially_received"

        po.actual_delivery_date = receipt.receipt_date
        await session.flush()

        # Recalcular métricas de proveedor (Puntualidad y Cumplimiento)
        await self._update_supplier_fulfillment_metrics(session, company_id, po.supplier_id)

        if user_id:
            await record_audit_event(
                session=session,
                action="CONFIRM_GOODS_RECEIPT",
                entity_name="GoodsReceipt",
                entity_id=str(receipt.id),
                company_id=company_id,
                user_id=user_id,
                changes={
                    "receipt_number": receipt.receipt_number,
                    "po_number": po.po_number,
                    "units_received": total_accepted_units,
                    "po_status": po.status,
                },
            )

        return receipt

    async def _update_supplier_fulfillment_metrics(
        self, session: AsyncSession, company_id: uuid.UUID, supplier_id: uuid.UUID
    ):
        """Calcula on_time_delivery_rate y fulfillment_accuracy_rate del proveedor."""
        stmt = (
            select(PurchaseOrder)
            .where(
                PurchaseOrder.company_id == company_id,
                PurchaseOrder.supplier_id == supplier_id,
                PurchaseOrder.status.in_(["partially_received", "received", "closed"]),
            )
            .options(selectinload(PurchaseOrder.items))
        )
        orders = (await session.execute(stmt)).scalars().all()
        if not orders:
            return

        total_orders = len(orders)
        on_time_count = 0
        total_ordered_units = 0
        total_received_units = 0

        for o in orders:
            if o.expected_delivery_date and o.actual_delivery_date:
                if _norm_dt(o.actual_delivery_date) <= _norm_dt(o.expected_delivery_date) + timedelta(days=1):
                    on_time_count += 1
            else:
                on_time_count += 1

            for it in o.items:
                total_ordered_units += it.quantity_ordered
                total_received_units += it.quantity_received

        supp = await self.get_supplier(session, company_id, supplier_id)
        if total_orders > 0:
            supp.on_time_delivery_rate = round((on_time_count / total_orders) * 100.0, 2)
        if total_ordered_units > 0:
            supp.fulfillment_accuracy_rate = round((total_received_units / total_ordered_units) * 100.0, 2)

        await session.flush()

    async def list_goods_receipts(
        self, session: AsyncSession, company_id: uuid.UUID, po_id: uuid.UUID | None = None
    ) -> list[GoodsReceipt]:
        """Consulta recepciones de mercancía."""
        stmt = (
            select(GoodsReceipt)
            .where(GoodsReceipt.company_id == company_id)
            .options(
                selectinload(GoodsReceipt.items),
                selectinload(GoodsReceipt.supplier),
                selectinload(GoodsReceipt.warehouse),
            )
            .order_by(GoodsReceipt.receipt_date.desc())
        )
        if po_id:
            stmt = stmt.where(GoodsReceipt.purchase_order_id == po_id)
        return list((await session.execute(stmt)).scalars().all())

    # ===========================================================================
    # 6. FACTURAS DE COMPRA Y GASTOS ASOCIADOS (LANDED COST)
    # ===========================================================================

    async def register_invoice(
        self, session: AsyncSession, company_id: uuid.UUID, po_id: uuid.UUID, payload: PurchaseInvoiceCreate
    ) -> PurchaseInvoice:
        """Registra una factura comercial / CFDI 4.0 emitida por el proveedor."""
        po = await self.get_purchase_order(session, company_id, po_id)

        invoice = PurchaseInvoice(
            company_id=company_id,
            purchase_order_id=po.id,
            supplier_id=po.supplier_id,
            invoice_series=payload.invoice_series,
            invoice_number=payload.invoice_number,
            uuid_sat=payload.uuid_sat,
            invoice_date=_norm_dt(payload.invoice_date),
            due_date=_norm_dt(payload.due_date),
            currency=payload.currency or po.currency,
            exchange_rate=payload.exchange_rate,
            subtotal=payload.subtotal,
            tax_iva=payload.tax_iva,
            tax_retention_iva=payload.tax_retention_iva,
            tax_retention_isr=payload.tax_retention_isr,
            total_amount=payload.total_amount,
            payment_status="unpaid",
            pdf_url=payload.pdf_url,
            xml_url=payload.xml_url,
            notes=payload.notes,
        )
        session.add(invoice)
        await session.flush()
        return invoice

    async def list_invoices(
        self, session: AsyncSession, company_id: uuid.UUID, po_id: uuid.UUID | None = None
    ) -> list[PurchaseInvoice]:
        """Consulta facturas de compra registradas."""
        stmt = (
            select(PurchaseInvoice)
            .where(PurchaseInvoice.company_id == company_id)
            .options(selectinload(PurchaseInvoice.supplier))
            .order_by(PurchaseInvoice.invoice_date.desc())
        )
        if po_id:
            stmt = stmt.where(PurchaseInvoice.purchase_order_id == po_id)
        return list((await session.execute(stmt)).scalars().all())

    async def register_expense(
        self, session: AsyncSession, company_id: uuid.UUID, po_id: uuid.UUID, payload: PurchaseExpenseCreate
    ) -> PurchaseExpense:
        """Registra un gasto adicional de abastecimiento (flete, aduana, maniobra, seguro)."""
        po = await self.get_purchase_order(session, company_id, po_id)

        expense = PurchaseExpense(
            company_id=company_id,
            purchase_order_id=po.id,
            expense_type=payload.expense_type,
            amount=payload.amount,
            currency=payload.currency,
            provider_name=payload.provider_name,
            invoice_number=payload.invoice_number,
            expense_date=_norm_dt(payload.expense_date),
            allocation_method=payload.allocation_method,
            notes=payload.notes,
        )
        session.add(expense)

        # Actualizar gastos asociados en la cabecera de la orden
        if payload.expense_type == "freight":
            po.shipping_cost = float(po.shipping_cost or 0.0) + float(payload.amount)
        else:
            po.other_expenses = float(po.other_expenses or 0.0) + float(payload.amount)
        po.total_amount = round(
            float(po.subtotal or 0.0)
            + float(po.tax_amount or 0.0)
            + float(po.shipping_cost or 0.0)
            + float(po.other_expenses or 0.0),
            2,
        )

        await session.flush()
        return expense

    async def list_expenses(
        self, session: AsyncSession, company_id: uuid.UUID, po_id: uuid.UUID
    ) -> list[PurchaseExpense]:
        """Consulta los gastos adicionales asociados a una orden de compra."""
        stmt = (
            select(PurchaseExpense)
            .where(PurchaseExpense.company_id == company_id, PurchaseExpense.purchase_order_id == po_id)
            .order_by(PurchaseExpense.expense_date.asc())
        )
        return list((await session.execute(stmt)).scalars().all())

    async def calculate_landed_cost(
        self, session: AsyncSession, company_id: uuid.UUID, po_id: uuid.UUID
    ) -> LandedCostSummaryResponse:
        """
        Calcula el costo puesto en almacén (Landed Cost) por partida.
        Prorratea fletes, seguros y aranceles sobre el valor de la mercancía.
        """
        po = await self.get_purchase_order(session, company_id, po_id)
        expenses = await self.list_expenses(session, company_id, po_id)

        total_freight = float(po.shipping_cost)
        total_other_expenses = float(po.other_expenses)

        merch_subtotal = float(po.subtotal) if float(po.subtotal) > 0 else 1.0

        landed_items = []
        accum_landed_total = 0.0

        for it in po.items:
            nominal_unit = float(it.unit_cost)
            item_line_total = float(it.total_cost)
            qty = it.quantity_ordered

            # Proporción del valor de esta partida sobre el subtotal de la compra
            share = item_line_total / merch_subtotal

            alloc_freight = (total_freight * share) / qty if qty > 0 else 0.0
            alloc_other = (total_other_expenses * share) / qty if qty > 0 else 0.0
            final_unit = round(nominal_unit + alloc_freight + alloc_other, 2)
            item_landed_total = round(final_unit * qty, 2)
            accum_landed_total += item_landed_total

            landed_items.append(
                LandedCostItemResponse(
                    variant_id=it.variant_id,
                    sku=it.sku,
                    product_name=it.product_name,
                    quantity=qty,
                    nominal_unit_cost=round(nominal_unit, 2),
                    allocated_freight=round(alloc_freight, 2),
                    allocated_other_expenses=round(alloc_other, 2),
                    final_landed_unit_cost=final_unit,
                    total_landed_cost=item_landed_total,
                )
            )

        return LandedCostSummaryResponse(
            purchase_order_id=po.id,
            po_number=po.po_number,
            total_merchandise_subtotal=round(float(po.subtotal), 2),
            total_freight=round(total_freight, 2),
            total_other_expenses=round(total_other_expenses, 2),
            total_landed_cost=round(accum_landed_total, 2),
            items=landed_items,
        )

    # ===========================================================================
    # 7. MOTOR INTELIGENTE DE REPOSICIÓN Y ALERTAS DE STOCK
    # ===========================================================================

    async def analyze_replenishment(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        days_history: int = 30,
        target_days_coverage: int = 30,
    ) -> ReplenishmentReportResponse:
        """
        Algoritmo avanzado de Reposición y Cadena de Suministro:
        Calcula para cada SKU:
        1. Ventas históricas en los últimos N días.
        2. Velocidad de rotación diaria (D = Unidades / días).
        3. Stock disponible (físico - reservado - bloqueado).
        4. Stock reservado por pedidos confirmados.
        5. Stock en tránsito (órdenes de compra emitidas pendientes de recibir).
        6. Tiempo de entrega del proveedor (L, Lead Time en días).
        7. Stock de seguridad (SS).
        8. Demanda estimada durante el tiempo de entrega (D * L).
        9. Punto de Reorden (ROP = (D * L) + SS).
        10. Días de cobertura actuales (Stock Disponible / D).
        11. Alerta de reposición: OUT_OF_STOCK, CRITICAL, REORDER_POINT, HEALTHY, OVERSTOCK.
        12. Cantidad sugerida de compra y costo total estimado.
        """
        now = datetime.now(timezone.utc)
        start_date = now - timedelta(days=days_history)

        # 1. Consultar todos los productos y variantes activos de la empresa
        stmt_variants = (
            select(ProductVariant)
            .join(Product, ProductVariant.product_id == Product.id)
            .where(Product.company_id == company_id, ProductVariant.is_active == True)
            .options(
                selectinload(ProductVariant.product),
                selectinload(ProductVariant.inventories),
            )
        )
        variants = (await session.execute(stmt_variants)).scalars().all()

        # 2. Consultar ventas históricas por variante en el periodo
        stmt_sales = (
            select(OrderItem.variant_id, func.sum(OrderItem.quantity).label("units_sold"))
            .join(Order, OrderItem.order_id == Order.id)
            .where(
                Order.status.in_(["paid", "confirmed", "shipped", "delivered"]),
                Order.date_created_meli >= start_date,
            )
            .group_by(OrderItem.variant_id)
        )
        sales_map = {row.variant_id: int(row.units_sold) for row in (await session.execute(stmt_sales)).all()}

        # 3. Consultar stock en tránsito en órdenes de compra abiertas
        stmt_transit = (
            select(PurchaseOrderItem.variant_id, func.sum(PurchaseOrderItem.quantity_pending).label("transit_units"))
            .join(PurchaseOrder, PurchaseOrderItem.purchase_order_id == PurchaseOrder.id)
            .where(
                PurchaseOrder.company_id == company_id,
                PurchaseOrder.status.in_(["approved", "issued", "partially_received"]),
            )
            .group_by(PurchaseOrderItem.variant_id)
        )
        transit_map = {row.variant_id: int(row.transit_units) for row in (await session.execute(stmt_transit)).all()}

        # 4. Consultar catálogo de proveedores para obtener el proveedor preferido y costo
        stmt_supp_prod = (
            select(SupplierProduct)
            .where(SupplierProduct.company_id == company_id, SupplierProduct.is_active == True)
            .options(selectinload(SupplierProduct.supplier))
        )
        all_supp_prods = (await session.execute(stmt_supp_prod)).scalars().all()
        supp_prod_map: dict[uuid.UUID, list[SupplierProduct]] = {}
        for sp in all_supp_prods:
            supp_prod_map.setdefault(sp.variant_id, []).append(sp)

        # Procesar cada variante
        suggestion_items: list[ReplenishmentSuggestionItem] = []
        out_of_stock_count = 0
        critical_count = 0
        reorder_point_count = 0
        healthy_count = 0
        overstock_count = 0
        total_investment = 0.0

        for var in variants:
            sales_units = sales_map.get(var.id, 0)
            velocity = round(sales_units / float(days_history), 2)
            stock_transit = transit_map.get(var.id, 0)

            # Acumular existencias en todos los almacenes de la empresa
            phys_stock = sum(inv.quantity_on_hand for inv in var.inventories)
            res_stock = sum(inv.quantity_reserved for inv in var.inventories)
            block_stock = sum(inv.quantity_blocked for inv in var.inventories)
            avail_stock = max(0, phys_stock - res_stock - block_stock)

            # Stock de seguridad de inventarios o colchón por defecto
            configured_ss = max([inv.safety_stock for inv in var.inventories], default=5)
            safety_stock = configured_ss if configured_ss > 0 else max(5, math.ceil(velocity * 7))

            # Proveedor preferido
            supp_list = supp_prod_map.get(var.id, [])
            pref_sp = next((s for s in supp_list if s.is_preferred), None) or (supp_list[0] if supp_list else None)

            lead_time = pref_sp.lead_time_days if pref_sp else 7
            moq = pref_sp.min_order_quantity if pref_sp else 1
            package_qty = pref_sp.package_quantity if pref_sp else 1
            unit_cost = float(pref_sp.purchase_cost) if pref_sp else float(var.cogs_cost)

            pref_supp_id = pref_sp.supplier_id if pref_sp else None
            pref_supp_name = pref_sp.supplier.name if (pref_sp and pref_sp.supplier) else None

            # Demanda estimada durante el tiempo de entrega
            est_demand_lead = round(velocity * lead_time, 2)

            # Punto de Reorden (ROP = Demanda durante Lead Time + Stock de Seguridad)
            rop = math.ceil(est_demand_lead + safety_stock)

            # Días de cobertura de inventario actual
            coverage_days = round(avail_stock / velocity, 1) if velocity > 0 else (999.0 if avail_stock > 0 else 0.0)

            # Clasificación de Alertas y Diagnóstico
            alert_status = "HEALTHY"
            alert_msg = "Nivel de existencias saludable para el ritmo de ventas actual."
            suggested_order = 0

            # 1. Agotado
            if avail_stock <= 0:
                alert_status = "OUT_OF_STOCK"
                alert_msg = f"¡AGOTADO! 0 unidades disponibles. Se requieren compras inmediatas para abastecer ventas."
                out_of_stock_count += 1
            # 2. Crítico (Se agotará antes de que llegue un nuevo pedido)
            elif coverage_days <= lead_time:
                alert_status = "CRITICAL"
                alert_msg = f"¡CRÍTICO! Cobertura de sólo {coverage_days} días es menor o igual al tiempo de entrega del proveedor ({lead_time} días)."
                critical_count += 1
            # 3. Punto de Reorden alcanzado
            elif (avail_stock + stock_transit) <= rop:
                alert_status = "REORDER_POINT"
                alert_msg = f"Existencias ({avail_stock} disp + {stock_transit} en tránsito) alcanzaron el Punto de Reorden ({rop} unidades)."
                reorder_point_count += 1
            # 4. Sobre-inventario
            elif coverage_days > 120 and avail_stock > 50:
                alert_status = "OVERSTOCK"
                alert_msg = f"Sobre-inventario: {coverage_days} días de cobertura superan el límite de rotación deseable (120 días)."
                overstock_count += 1
            else:
                healthy_count += 1

            # Calcular Cantidad Sugerida de Compra
            if alert_status in ["OUT_OF_STOCK", "CRITICAL", "REORDER_POINT"]:
                target_level = rop + math.ceil(velocity * target_days_coverage)
                deficit = target_level - (avail_stock + stock_transit)
                raw_qty = max(deficit, moq)
                # Redondear al múltiplo de paquete/caja del proveedor
                if package_qty > 1:
                    suggested_order = math.ceil(raw_qty / package_qty) * package_qty
                else:
                    suggested_order = raw_qty

            est_cost = round(suggested_order * unit_cost, 2)
            total_investment += est_cost

            item_rep = ReplenishmentSuggestionItem(
                variant_id=var.id,
                product_id=var.product_id,
                sku=var.sku,
                product_name=var.variant_name if var.variant_name else (var.product.name if var.product else var.sku),
                category=var.product.category if var.product else None,
                physical_stock=phys_stock,
                reserved_stock=res_stock,
                blocked_stock=block_stock,
                available_stock=avail_stock,
                stock_in_transit=stock_transit,
                historical_sales_units=sales_units,
                days_analyzed=days_history,
                sales_velocity_daily=velocity,
                supplier_lead_time_days=lead_time,
                safety_stock=safety_stock,
                estimated_demand_lead_time=est_demand_lead,
                reorder_point=rop,
                days_of_coverage=coverage_days,
                preferred_supplier_id=pref_supp_id,
                preferred_supplier_name=pref_supp_name,
                min_order_quantity=moq,
                package_quantity=package_qty,
                purchase_unit_cost=unit_cost,
                alert_status=alert_status,  # type: ignore
                alert_message=alert_msg,
                suggested_order_quantity=suggested_order,
                estimated_total_cost=est_cost,
            )
            suggestion_items.append(item_rep)

        # Ordenar: primero agotados, luego críticos, luego reorden
        status_priority = {"OUT_OF_STOCK": 0, "CRITICAL": 1, "REORDER_POINT": 2, "OVERSTOCK": 3, "HEALTHY": 4}
        suggestion_items.sort(key=lambda x: (status_priority.get(x.alert_status, 5), -x.estimated_total_cost))

        return ReplenishmentReportResponse(
            company_id=company_id,
            generated_at=now,
            days_analyzed=days_history,
            target_days_coverage=target_days_coverage,
            total_skus_analyzed=len(variants),
            out_of_stock_count=out_of_stock_count,
            critical_count=critical_count,
            reorder_point_count=reorder_point_count,
            healthy_count=healthy_count,
            overstock_count=overstock_count,
            total_suggested_investment=round(total_investment, 2),
            items=suggestion_items,
        )

    async def create_po_from_suggestions(
        self, session: AsyncSession, company_id: uuid.UUID, payload: CreatePOFromSuggestionsRequest, user_id: uuid.UUID | None = None
    ) -> PurchaseOrder:
        """Convierte una o varias sugerencias de reposición en un borrador de Orden de Compra."""
        po_number = payload.po_number
        if not po_number:
            count_stmt = select(func.count(PurchaseOrder.id)).where(PurchaseOrder.company_id == company_id)
            total = (await session.execute(count_stmt)).scalar() or 0
            po_number = f"OC-REP-{datetime.now(timezone.utc).year}-{total + 1:04d}"

        items_create = [
            PurchaseOrderItemCreate(
                variant_id=it.variant_id,
                quantity_ordered=it.quantity,
                unit_cost=it.unit_cost,
            )
            for it in payload.items
        ]

        po_in = PurchaseOrderCreate(
            company_id=company_id,
            supplier_id=payload.supplier_id,
            warehouse_id=payload.warehouse_id,
            po_number=po_number,
            notes=f"Generada automáticamente desde sugerencias de reposición.\n{payload.notes or ''}".strip(),
            items=items_create,
        )

        return await self.create_purchase_order(session, company_id, po_in, user_id=user_id)

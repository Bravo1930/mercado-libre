"""Servicio Central de Ventas, Pedidos, Rentabilidad, Trazabilidad e Inteligencia Comercial."""

from datetime import datetime, timedelta, timezone
from typing import Any, Literal
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.connectors.meli import MercadoLibreConnector
from src.core.exceptions import AppException, EntityNotFoundException
from src.core.logging import get_logger
from src.models.cost import CostStructure, ProfitabilityAudit
from src.models.meli_account import MeliAccount
from src.models.order import Order, OrderClaim, OrderItem, OrderTimeline
from src.models.payment import Payment
from src.models.product import ProductSKU, ProductVariant
from src.models.shipment import Shipment
from src.models.warehouse import Inventory, InventoryMovement, Warehouse
from src.schemas.order import SalesReportMetricPeriod, SalesReportResponse
from src.services.finance_service import FinanceService
from src.services.inventory_service import InventoryService

logger = get_logger("order_service")


class OrderService:
    """
    Servicio integral del Centro de Ventas del ERP.
    Administra el ciclo completo de pedidos:
    - Registro detallado de comprador, productos, SKUs, variantes, comisiones y rentabilidad SAT.
    - Reserva transaccional y liberación de stock en bodegas físicas.
    - Prevención estricta de contabilizar cancelaciones como ventas definitivas.
    - Gestión de cancelaciones, devoluciones y reclamos.
    - Comparación MeLi vs ERP interno.
    - Reportes comerciales diarios, semanales y mensuales.
    """

    def __init__(self):
        self.inventory_service = InventoryService()
        self.finance_service = FinanceService()

    async def create_or_update_order(
        self, session: AsyncSession, account: MeliAccount, order_data: dict[str, Any]
    ) -> Order:
        """
        Crea o actualiza una orden de venta con desglose financiero exhaustivo,
        asociación de variantes internas y reservas de inventario.
        """
        meli_order_id = int(order_data.get("id"))
        order_status = order_data.get("status", "pending")
        total_amount = float(order_data.get("total_amount", 0.0))
        paid_amount = float(order_data.get("paid_amount", 0.0))
        currency_id = order_data.get("currency_id", "MXN")

        date_created = datetime.now(timezone.utc)
        date_raw = order_data.get("date_created")
        if date_raw:
            try:
                date_created = datetime.fromisoformat(date_raw.replace("Z", "+00:00"))
            except Exception:
                pass

        # Datos del comprador
        buyer_data = order_data.get("buyer", {})
        buyer_id = buyer_data.get("id")
        buyer_nickname = buyer_data.get("nickname")
        buyer_name = f"{buyer_data.get('first_name', '')} {buyer_data.get('last_name', '')}".strip() or None
        buyer_email = buyer_data.get("email")
        buyer_phone = buyer_data.get("phone", {}).get("number")
        buyer_doc = buyer_data.get("billing_info", {}).get("doc_number")

        # Estados iniciales de pago y envío
        payments_data = order_data.get("payments", [])
        payment_status = "approved" if order_status == "paid" else "pending"
        if payments_data:
            payment_status = payments_data[0].get("status", payment_status)

        shipping_data = order_data.get("shipping", {})
        shipment_status = shipping_data.get("status", "pending")
        logistic_type = shipping_data.get("logistic_type", "cross_docking")
        shipping_cost_seller = float(shipping_data.get("cost", 0.0))

        # Buscar orden existente
        stmt = (
            select(Order)
            .where(Order.meli_order_id == meli_order_id)
            .options(
                selectinload(Order.items),
                selectinload(Order.payments),
                selectinload(Order.shipments),
                selectinload(Order.timelines),
                selectinload(Order.claims),
                selectinload(Order.profitability),
            )
        )
        order = (await session.execute(stmt)).scalar_one_or_none()
        is_new = False

        if not order:
            is_new = True
            order = Order(
                meli_account_id=account.id,
                meli_order_id=meli_order_id,
                order_number=f"VTA-{str(meli_order_id)[-8:]}",
                status=order_status,
                buyer_id=buyer_id,
                buyer_nickname=buyer_nickname,
                buyer_name=buyer_name,
                buyer_email=buyer_email,
                buyer_phone=buyer_phone,
                buyer_document=buyer_doc,
                payment_status=payment_status,
                shipment_status=shipment_status,
                total_amount=total_amount,
                paid_amount=paid_amount,
                currency_id=currency_id,
                date_created_meli=date_created,
                shipping_cost_seller=shipping_cost_seller,
            )
            session.add(order)
            await session.flush()

            # Evento inicial en línea de tiempo
            timeline_init = OrderTimeline(
                order_id=order.id,
                event_type="ORDER_CREATED",
                title="Venta Registrada",
                description=f"Pedido #{meli_order_id} sincronizado desde Mercado Libre México ({account.nickname})",
                actor="Mercado Libre Push",
                metadata_info={"channel": "marketplace_meli", "site": account.site_id},
            )
            session.add(timeline_init)
        else:
            order.status = order_status
            order.paid_amount = paid_amount
            order.payment_status = payment_status
            order.shipment_status = shipment_status
            if buyer_name and not order.buyer_name:
                order.buyer_name = buyer_name

        # Procesar partidas (OrderItems)
        order_items_data = order_data.get("order_items", [])
        total_cogs = 0.0
        total_meli_fee = 0.0

        if is_new:
            for it in order_items_data:
                item_obj = it.get("item", {})
                meli_item_id = item_obj.get("id", "")
                meli_variation_id = str(item_obj.get("variation_id")) if item_obj.get("variation_id") else None
                seller_sku = item_obj.get("seller_sku") or item_obj.get("seller_custom_field")
                title = item_obj.get("title", "Producto MeLi")
                quantity = int(it.get("quantity", 1))
                unit_price = float(it.get("unit_price", 0.0))
                sale_fee = float(it.get("sale_fee", 0.0))
                total_meli_fee += sale_fee

                # Vincular con catálogo interno
                variant_id = None
                product_id = None
                variant_name = None
                cogs_unit = 0.0

                if seller_sku and account.company_id:
                    stmt_v = (
                        select(ProductVariant)
                        .where(
                            (ProductVariant.sku == seller_sku) |
                            (ProductVariant.id.in_(select(ProductSKU.variant_id).where(ProductSKU.seller_sku == seller_sku))),
                            ProductVariant.company_id == account.company_id,
                        )
                    )
                    var_obj = (await session.execute(stmt_v)).scalars().first()
                    if var_obj:
                        variant_id = var_obj.id
                        product_id = var_obj.product_id
                        variant_name = var_obj.variant_name
                        cogs_unit = float(var_obj.cogs_cost)

                total_cogs += cogs_unit * quantity
                net_profit_item = round((unit_price * quantity) - (cogs_unit * quantity) - sale_fee, 2)

                order_item = OrderItem(
                    order_id=order.id,
                    product_id=product_id,
                    variant_id=variant_id,
                    meli_item_id=meli_item_id,
                    meli_variation_id=meli_variation_id,
                    seller_sku=seller_sku,
                    variant_name=variant_name,
                    title=title,
                    quantity=quantity,
                    unit_price=unit_price,
                    sale_fee=sale_fee,
                    cogs_unit=cogs_unit,
                    net_profit=net_profit_item,
                )
                session.add(order_item)
            await session.flush()

        # Procesar pagos de Mercado Pago asociados
        payments_data = order_data.get("payments", [])
        if payments_data:
            stmt_p = select(Payment).where(Payment.order_id == order.id)
            existing_payments = {p.meli_payment_id: p for p in (await session.execute(stmt_p)).scalars().all()}
            for p_data in payments_data:
                p_meli_id = int(p_data.get("id") or 0)
                if not p_meli_id:
                    continue
                p_status = p_data.get("status", "approved")
                p_tx_amount = float(p_data.get("transaction_amount") or 0.0)
                p_fee = float(p_data.get("marketplace_fee") or 0.0)
                p_type = p_data.get("payment_type")
                p_method = p_data.get("payment_method_id")
                dt_app_str = p_data.get("date_approved")
                dt_approved = None
                if dt_app_str:
                    try:
                        dt_approved = datetime.fromisoformat(str(dt_app_str).replace("Z", "+00:00"))
                    except Exception:
                        dt_approved = None

                if p_meli_id in existing_payments:
                    p_obj = existing_payments[p_meli_id]
                    p_obj.status = p_status
                    p_obj.transaction_amount = p_tx_amount
                    p_obj.marketplace_fee = p_fee
                    p_obj.date_approved = dt_approved
                else:
                    new_p = Payment(
                        order_id=order.id,
                        meli_payment_id=p_meli_id,
                        status=p_status,
                        payment_type=p_type,
                        payment_method_id=p_method,
                        transaction_amount=p_tx_amount,
                        marketplace_fee=p_fee,
                        date_approved=dt_approved,
                    )
                    session.add(new_p)
            await session.flush()

        # Procesar información de Envío y Despacho (Shipment)
        shipping_id = int(shipping_data.get("id") or 0)
        if shipping_id:
            stmt_s = select(Shipment).where(Shipment.meli_shipment_id == shipping_id)
            shipment_obj = (await session.execute(stmt_s)).scalar_one_or_none()

            # Clasificar dispatch_status operativo inicial
            if shipment_status in ["shipped", "delivered"]:
                init_dispatch = "dispatched"
            elif shipment_status == "cancelled":
                init_dispatch = "error"
            elif shipping_data.get("substatus") == "printed":
                init_dispatch = "prepared"
            else:
                init_dispatch = "pending"

            receiver_addr = shipping_data.get("receiver_address")
            sender_addr = shipping_data.get("sender_address")
            tracking_num = str(shipping_data.get("tracking_number") or "") or None
            carrier = shipping_data.get("carrier_name") or (shipping_data.get("shipping_option") or {}).get("name")
            tracking_meth = shipping_data.get("tracking_method")
            est_limit_raw = (
                shipping_data.get("estimated_delivery_limit", {}).get("date")
                if isinstance(shipping_data.get("estimated_delivery_limit"), dict)
                else None
            )
            est_limit = None
            if est_limit_raw:
                try:
                    est_limit = datetime.fromisoformat(str(est_limit_raw).replace("Z", "+00:00"))
                except Exception:
                    pass

            if shipment_obj:
                shipment_obj.status = shipment_status
                shipment_obj.substatus = shipping_data.get("substatus")
                shipment_obj.logistic_type = logistic_type
                if tracking_num:
                    shipment_obj.tracking_number = tracking_num
                if carrier:
                    shipment_obj.carrier_name = carrier
                if receiver_addr:
                    shipment_obj.receiver_address = receiver_addr
                if sender_addr:
                    shipment_obj.sender_address = sender_addr
                shipment_obj.shipping_cost_seller = shipping_cost_seller
            else:
                new_shipment = Shipment(
                    company_id=account.company_id,
                    order_id=order.id,
                    meli_shipment_id=shipping_id,
                    status=shipment_status,
                    substatus=shipping_data.get("substatus"),
                    dispatch_status=init_dispatch,
                    logistic_type=logistic_type,
                    tracking_number=tracking_num,
                    tracking_method=tracking_meth,
                    carrier_name=carrier,
                    shipping_cost_total=float(shipping_data.get("cost_total", shipping_cost_seller)),
                    shipping_cost_seller=shipping_cost_seller,
                    receiver_address=receiver_addr,
                    sender_address=sender_addr,
                    shipping_option=shipping_data.get("shipping_option"),
                    estimated_delivery_limit=est_limit,
                )
                session.add(new_shipment)
            await session.flush()

        # Calcular Rentabilidad Financiera Neta y Retenciones SAT
        stmt_cost = select(CostStructure).where(CostStructure.company_id == account.company_id, CostStructure.is_default == True)
        cost_struct = (await session.execute(stmt_cost)).scalar_one_or_none()

        packaging_cost = float(cost_struct.packaging_cost_fixed) if cost_struct else 15.00
        iva_rate = float(cost_struct.sat_iva_retention_rate) if cost_struct else 0.08
        isr_rate = float(cost_struct.sat_isr_retention_rate) if cost_struct else 0.01

        sat_iva = round(total_amount * iva_rate, 2)
        sat_isr = round(total_amount * isr_rate, 2)
        total_taxes = sat_iva + sat_isr

        net_profit = round(
            total_amount - total_cogs - total_meli_fee - shipping_cost_seller - packaging_cost - total_taxes, 2
        )
        net_margin = round((net_profit / total_amount) * 100, 2) if total_amount > 0 else 0.0

        order.cogs_total = total_cogs
        order.meli_fee_amount = total_meli_fee
        order.estimated_profit = net_profit
        order.net_margin_pct = net_margin

        # Registrar o actualizar ProfitabilityAudit
        if is_new:
            audit = ProfitabilityAudit(
                order_id=order.id,
                gross_sale_price=total_amount,
                cogs_total=total_cogs,
                meli_commission_fee=total_meli_fee,
                shipping_cost_seller=shipping_cost_seller,
                packaging_cost=packaging_cost,
                sat_iva_retention=sat_iva,
                sat_isr_retention=sat_isr,
                net_profit=net_profit,
                net_margin_pct=net_margin,
            )
            session.add(audit)
        else:
            stmt_audit = select(ProfitabilityAudit).where(ProfitabilityAudit.order_id == order.id)
            audit = (await session.execute(stmt_audit)).scalar_one_or_none()
            if audit:
                audit.gross_sale_price = total_amount
                audit.cogs_total = total_cogs
                audit.meli_commission_fee = total_meli_fee
                audit.shipping_cost_seller = shipping_cost_seller
                audit.packaging_cost = packaging_cost
                audit.sat_iva_retention = sat_iva
                audit.sat_isr_retention = sat_isr
                audit.net_profit = net_profit
                audit.net_margin_pct = net_margin
            else:
                audit = ProfitabilityAudit(
                    order_id=order.id,
                    gross_sale_price=total_amount,
                    cogs_total=total_cogs,
                    meli_commission_fee=total_meli_fee,
                    shipping_cost_seller=shipping_cost_seller,
                    packaging_cost=packaging_cost,
                    sat_iva_retention=sat_iva,
                    sat_isr_retention=sat_isr,
                    net_profit=net_profit,
                    net_margin_pct=net_margin,
                )
                session.add(audit)

        # 4. Manejo de Inventario y Movimientos de Stock
        # Si no es Full, reservar existencias en almacén local
        is_full = logistic_type == "fulfillment"
        if not is_full and account.company_id:
            stmt_wh = (
                select(Warehouse)
                .where(Warehouse.company_id == account.company_id, Warehouse.is_fulfillment == False, Warehouse.is_active == True)
                .order_by(Warehouse.created_at.asc())
            )
            local_wh = (await session.execute(stmt_wh)).scalars().first()

            if local_wh:
                for it in order_items_data:
                    it_obj = it.get("item", {})
                    seller_sku = it_obj.get("seller_sku") or it_obj.get("seller_custom_field")
                    qty = int(it.get("quantity", 1))

                    if seller_sku:
                        stmt_v = select(ProductVariant).where(
                            (ProductVariant.sku == seller_sku) |
                            (ProductVariant.id.in_(select(ProductSKU.variant_id).where(ProductSKU.seller_sku == seller_sku))),
                            ProductVariant.company_id == account.company_id,
                        )
                        variant = (await session.execute(stmt_v)).scalars().first()

                        if variant:
                            try:
                                if order_status in ["paid", "confirmed"]:
                                    await self.inventory_service.reserve_stock_for_order(
                                        session=session,
                                        warehouse_id=local_wh.id,
                                        variant_id=variant.id,
                                        quantity=qty,
                                        order_id=str(meli_order_id),
                                        notes=f"Reserva por venta MeLi #{meli_order_id}",
                                    )
                                    # Registro en línea de tiempo
                                    tl_res = OrderTimeline(
                                        order_id=order.id,
                                        event_type="STOCK_RESERVED",
                                        title="Inventario Reservado",
                                        description=f"Se reservaron {qty} unidad(es) de '{variant.sku}' en almacén '{local_wh.name}'",
                                        actor="Motor de Inventario",
                                    )
                                    session.add(tl_res)
                                elif order_status == "cancelled":
                                    await self.inventory_service.release_order_reservation(
                                        session=session,
                                        warehouse_id=local_wh.id,
                                        variant_id=variant.id,
                                        quantity=qty,
                                        order_id=str(meli_order_id),
                                        notes=f"Liberación por cancelación MeLi #{meli_order_id}",
                                    )
                                    tl_rel = OrderTimeline(
                                        order_id=order.id,
                                        event_type="STOCK_RELEASED",
                                        title="Reserva de Inventario Liberada",
                                        description=f"Se liberaron {qty} unidad(es) de '{variant.sku}' por cancelación",
                                        actor="Motor de Inventario",
                                    )
                                    session.add(tl_rel)
                            except Exception as inv_err:
                                logger.warning(f"Aviso de inventario para orden #{meli_order_id}: {inv_err}")

        try:
            await self.finance_service.record_transactions_for_order(session, order, account, audit)
        except Exception as e:
            logger.warning(f"Aviso al registrar partidas financieras para orden #{meli_order_id}: {e}")

        await session.flush()
        return order

    async def cancel_order(
        self,
        session: AsyncSession,
        order_id: uuid.UUID,
        company_id: uuid.UUID,
        reason: str,
        responsible: str = "buyer",
    ) -> Order:
        """
        Cancela un pedido, libera inmediatamente cualquier reserva de stock asociada
        y asegura que no se contabilice como venta definitiva.
        """
        stmt = (
            select(Order)
            .join(MeliAccount, Order.meli_account_id == MeliAccount.id)
            .where(Order.id == order_id, MeliAccount.company_id == company_id)
            .options(
                selectinload(Order.meli_account),
                selectinload(Order.items),
                selectinload(Order.payments),
                selectinload(Order.shipments),
                selectinload(Order.timelines),
                selectinload(Order.claims),
                selectinload(Order.profitability),
            )
        )
        order = (await session.execute(stmt)).scalar_one_or_none()
        if not order:
            raise EntityNotFoundException("Orden de Venta", str(order_id))

        if order.status == "cancelled":
            return order

        # Liberar reservas en inventario local
        stmt_wh = (
            select(Warehouse)
            .where(Warehouse.company_id == company_id, Warehouse.is_fulfillment == False, Warehouse.is_active == True)
            .order_by(Warehouse.created_at.asc())
        )
        local_wh = (await session.execute(stmt_wh)).scalars().first()

        if local_wh:
            for item in order.items:
                if item.variant_id:
                    try:
                        await self.inventory_service.release_order_reservation(
                            session=session,
                            warehouse_id=local_wh.id,
                            variant_id=item.variant_id,
                            quantity=item.quantity,
                            order_id=str(order.meli_order_id),
                            notes=f"Liberación por cancelación manual: {reason}",
                        )
                    except Exception as e:
                        logger.warning(f"Aviso al liberar reserva en cancelación de orden {order.id}: {e}")

        order.status = "cancelled"
        order.cancel_reason = reason
        order.cancel_responsible = responsible
        order.cancelled_at = datetime.now(timezone.utc)

        # Registrar en la línea de tiempo
        tl_cancel = OrderTimeline(
            order_id=order.id,
            event_type="ORDER_CANCELLED",
            title="Pedido Cancelado",
            description=f"Cancelado por {responsible.upper()}. Motivo: {reason}",
            actor="Operador ERP",
            metadata_info={"responsible": responsible, "reason": reason},
        )
        order.timelines.append(tl_cancel)
        try:
            account = order.meli_account or await session.get(MeliAccount, order.meli_account_id)
            if account:
                await self.finance_service.record_transactions_for_order(session, order, account)
        except Exception as e:
            logger.warning(f"Aviso al registrar partidas financieras para orden #{order.meli_order_id}: {e}")

        await session.flush()
        return order

    async def process_order_return(
        self,
        session: AsyncSession,
        order_id: uuid.UUID,
        company_id: uuid.UUID,
        condition: Literal["good", "damaged"],
        warehouse_id: uuid.UUID | None = None,
        notes: str | None = None,
    ) -> Order:
        """
        Procesa la devolución física de mercancía retornada por el comprador.
        - condition == 'good': reingresa al inventario disponible (quantity_on_hand += qty).
        - condition == 'damaged': ingresa a cuarentena/bloqueado (quantity_blocked += qty).
        """
        stmt = (
            select(Order)
            .join(MeliAccount, Order.meli_account_id == MeliAccount.id)
            .where(Order.id == order_id, MeliAccount.company_id == company_id)
            .options(
                selectinload(Order.meli_account),
                selectinload(Order.items),
                selectinload(Order.payments),
                selectinload(Order.shipments),
                selectinload(Order.timelines),
                selectinload(Order.claims),
                selectinload(Order.profitability),
            )
        )
        order = (await session.execute(stmt)).scalar_one_or_none()
        if not order:
            raise EntityNotFoundException("Orden de Venta", str(order_id))

        # Determinar almacén de destino
        if warehouse_id:
            target_wh = await session.get(Warehouse, warehouse_id)
            if not target_wh or target_wh.company_id != company_id:
                raise EntityNotFoundException("Almacén", "id", str(warehouse_id))
        else:
            stmt_wh = (
                select(Warehouse)
                .where(Warehouse.company_id == company_id, Warehouse.is_fulfillment == False, Warehouse.is_active == True)
                .order_by(Warehouse.created_at.asc())
            )
            target_wh = (await session.execute(stmt_wh)).scalars().first()

        if target_wh:
            for item in order.items:
                if item.variant_id:
                    inv = await self.inventory_service.repo.get_or_create(session, target_wh.id, item.variant_id)
                    before_hand = inv.quantity_on_hand
                    before_blocked = inv.quantity_blocked

                    if condition == "good":
                        # Reingresa a existencias disponibles
                        inv.quantity_on_hand += item.quantity
                        inv.sync_available()
                        mov = InventoryMovement(
                            inventory_id=inv.id,
                            movement_type="RETURN_RESTOCK",
                            quantity_delta=item.quantity,
                            quantity_before=before_hand,
                            quantity_after=inv.quantity_on_hand,
                            reference_id=str(order.meli_order_id),
                            reference_type="order_return",
                            notes=notes or f"Devolución en buen estado orden #{order.meli_order_id}",
                        )
                        session.add(mov)
                    else:
                        # Entra a cuarentena / bloqueado por daño
                        inv.quantity_on_hand += item.quantity
                        inv.quantity_blocked += item.quantity
                        inv.sync_available()
                        mov = InventoryMovement(
                            inventory_id=inv.id,
                            movement_type="RETURN_DAMAGED_QUARANTINE",
                            quantity_delta=item.quantity,
                            quantity_before=before_blocked,
                            quantity_after=inv.quantity_blocked,
                            reference_id=str(order.meli_order_id),
                            reference_type="order_return_damaged",
                            notes=notes or f"Devolución dañada enviada a cuarentena #{order.meli_order_id}",
                        )
                        session.add(mov)

        order.status = "returned"
        order.return_status = "received_good" if condition == "good" else "received_damaged"

        tl_ret = OrderTimeline(
            order_id=order.id,
            event_type="RETURN_RECEIVED",
            title=f"Devolución Procesada ({'Buen Estado' if condition == 'good' else 'Mercancía Dañada'})",
            description=f"Condición de inspección: {condition}. Almacén destino: {target_wh.name if target_wh else 'Central'}. {notes or ''}",
            actor="Control de Calidad Almacén",
        )
        order.timelines.append(tl_ret)
        try:
            account = order.meli_account or await session.get(MeliAccount, order.meli_account_id)
            if account:
                await self.finance_service.record_transactions_for_order(session, order, account)
        except Exception as e:
            logger.warning(f"Aviso al registrar partidas financieras para orden #{order.meli_order_id}: {e}")

        await session.flush()
        return order

    async def register_order_claim(
        self,
        session: AsyncSession,
        order_id: uuid.UUID,
        company_id: uuid.UUID,
        meli_claim_id: str,
        claim_type: str,
        disputed_amount: float,
        reason: str | None = None,
    ) -> OrderClaim:
        """Registra un reclamo o disputa post-venta asociada a la orden."""
        stmt = (
            select(Order)
            .join(MeliAccount, Order.meli_account_id == MeliAccount.id)
            .where(Order.id == order_id, MeliAccount.company_id == company_id)
            .options(selectinload(Order.claims), selectinload(Order.timelines))
        )
        order = (await session.execute(stmt)).scalar_one_or_none()
        if not order:
            raise EntityNotFoundException("Orden de Venta", str(order_id))

        claim = OrderClaim(
            order_id=order.id,
            meli_claim_id=meli_claim_id,
            claim_type=claim_type,
            stage="claim",
            status="open",
            reason=reason,
            disputed_amount=disputed_amount,
        )
        order.claims.append(claim)

        order.claim_status = "open"

        tl_claim = OrderTimeline(
            order_id=order.id,
            event_type="CLAIM_OPENED",
            title=f"Reclamo MeLi Registrado #{meli_claim_id}",
            description=f"Tipo: {claim_type}. Monto disputado: ${disputed_amount:.2f}. {reason or ''}",
            actor="Mediación Mercado Libre",
        )
        order.timelines.append(tl_claim)
        await session.flush()
        return claim

    async def compare_order_with_meli(
        self, session: AsyncSession, order_id: uuid.UUID, company_id: uuid.UUID
    ) -> dict[str, Any]:
        """
        Compara en tiempo real la información oficial de Mercado Libre con los datos internos del ERP.
        Detecta discrepancias de precios, comisiones, SKU mapeados y estado de entrega.
        """
        stmt = (
            select(Order)
            .join(MeliAccount, Order.meli_account_id == MeliAccount.id)
            .where(Order.id == order_id, MeliAccount.company_id == company_id)
            .options(
                selectinload(Order.items),
                selectinload(Order.meli_account),
                selectinload(Order.payments),
                selectinload(Order.shipments),
            )
        )
        order = (await session.execute(stmt)).scalar_one_or_none()
        if not order:
            raise EntityNotFoundException("Orden de Venta", "id", str(order_id))

        connector = MercadoLibreConnector(account=order.meli_account, db_session=session)
        await connector.check_and_proactively_refresh()

        meli_data = await connector.orders.get_order(order.meli_order_id)
        differences = []

        # 1. Comparar Importe Total
        meli_total = float(meli_data.get("total_amount", 0.0))
        if abs(meli_total - float(order.total_amount)) > 0.01:
            differences.append(f"Importe Total: MeLi reporta ${meli_total:.2f} vs ERP ${float(order.total_amount):.2f}")

        # 2. Comparar Estado General
        meli_status = meli_data.get("status")
        if meli_status != order.status:
            differences.append(f"Estado de la Orden: MeLi está '{meli_status}' vs ERP '{order.status}'")

        # 3. Comparar Partidas y SKUs
        meli_items = meli_data.get("order_items", [])
        if len(meli_items) != len(order.items):
            differences.append(f"Número de partidas: MeLi tiene {len(meli_items)} vs ERP {len(order.items)}")

        # 4. Comparar Pagos
        meli_paid = float(meli_data.get("paid_amount", 0.0))
        if abs(meli_paid - float(order.paid_amount)) > 0.01:
            differences.append(f"Monto Pagado: MeLi reporta ${meli_paid:.2f} vs ERP ${float(order.paid_amount):.2f}")

        internal_dict = {
            "order_number": order.order_number,
            "status": order.status,
            "total_amount": float(order.total_amount),
            "paid_amount": float(order.paid_amount),
            "payment_status": order.payment_status,
            "shipment_status": order.shipment_status,
            "items_count": len(order.items),
            "cogs_total": float(order.cogs_total),
            "estimated_profit": float(order.estimated_profit),
            "net_margin_pct": float(order.net_margin_pct),
        }

        comparison_res = {
            "order_id": str(order.id),
            "meli_order_id": order.meli_order_id,
            "is_matching": len(differences) == 0,
            "differences": differences,
            "meli_data": {
                "status": meli_status,
                "total_amount": meli_total,
                "paid_amount": meli_paid,
                "date_created": meli_data.get("date_created"),
                "shipping_type": meli_data.get("shipping", {}).get("logistic_type"),
            },
            "internal_data": internal_dict,
        }

        order.comparison_details = comparison_res
        await session.flush()
        return comparison_res

    async def generate_sales_report(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        report_type: Literal["daily", "weekly", "monthly"],
        reference_date: datetime,
    ) -> SalesReportResponse:
        """
        Genera reportes de ventas consolidados y auditados.
        REGLA CRÍTICA: Excluye de forma terminante los pedidos cancelados ('cancelled')
        de los ingresos brutos, netos y ganancias.
        """
        # Definir rango de fechas según report_type
        ref_tz = reference_date.replace(tzinfo=timezone.utc) if reference_date.tzinfo is None else reference_date

        if report_type == "daily":
            start_date = ref_tz.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=1)
            period_label = start_date.strftime("%Y-%m-%d")
        elif report_type == "weekly":
            # Iniciar en lunes de la semana de referencia
            start_date = (ref_tz - timedelta(days=ref_tz.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=7)
            period_label = f"Semana {start_date.strftime('%U')} ({start_date.strftime('%d/%b')} - {end_date.strftime('%d/%b')})"
        else:  # monthly
            start_date = ref_tz.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            # Calcular primer día del mes siguiente
            next_month = start_date.month + 1 if start_date.month < 12 else 1
            next_year = start_date.year if start_date.month < 12 else start_date.year + 1
            end_date = start_date.replace(year=next_year, month=next_month, day=1)
            period_label = start_date.strftime("%B %Y")

        # Cargar todas las órdenes de la empresa en el rango de fechas
        stmt = (
            select(Order)
            .join(MeliAccount, Order.meli_account_id == MeliAccount.id)
            .where(
                MeliAccount.company_id == company_id,
                Order.date_created_meli >= start_date,
                Order.date_created_meli < end_date,
            )
            .options(
                selectinload(Order.items),
                selectinload(Order.profitability),
            )
            .order_by(Order.date_created_meli.asc())
        )
        orders = (await session.execute(stmt)).scalars().all()

        # Calcular métricas consolidadas del periodo excluyendo cancelaciones
        total_orders = len(orders)
        cancelled_orders = sum(1 for o in orders if o.status == "cancelled")
        returned_orders = sum(1 for o in orders if o.status == "returned" or o.return_status != "none")

        # Solo órdenes NO canceladas
        valid_orders = [o for o in orders if o.status != "cancelled"]
        paid_orders = len(valid_orders)

        gross_sales = sum(float(o.total_amount) for o in valid_orders)
        discounts = sum(float(o.discount_amount) for o in valid_orders)
        net_sales = gross_sales - discounts

        cogs = sum(float(o.cogs_total) for o in valid_orders)
        commissions = sum(float(o.meli_fee_amount) for o in valid_orders)
        shipping = sum(float(o.shipping_cost_seller) for o in valid_orders)
        taxes = sum(
            float(o.profitability.sat_iva_retention + o.profitability.sat_isr_retention)
            for o in valid_orders if o.profitability
        )
        net_profit = sum(float(o.estimated_profit) for o in valid_orders)
        avg_ticket = round(net_sales / paid_orders, 2) if paid_orders > 0 else 0.0
        profit_margin = round((net_profit / net_sales) * 100, 2) if net_sales > 0 else 0.0

        summary = SalesReportMetricPeriod(
            period=period_label,
            gross_sales=round(gross_sales, 2),
            net_sales=round(net_sales, 2),
            total_orders=total_orders,
            paid_orders=paid_orders,
            cancelled_orders=cancelled_orders,
            returned_orders=returned_orders,
            average_ticket=avg_ticket,
            total_cogs=round(cogs, 2),
            meli_commissions=round(commissions, 2),
            shipping_costs=round(shipping, 2),
            sat_tax_retentions=round(taxes, 2),
            net_profit=round(net_profit, 2),
            profit_margin_pct=profit_margin,
        )

        # Desglose en sub-intervalos
        breakdown: list[SalesReportMetricPeriod] = []

        def _norm_dt(dt: datetime) -> datetime:
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)

        if report_type == "daily":
            # Desglose por 4 turnos del día
            turnos = [
                ("00:00 - 06:00 (Madrugada)", 0, 6),
                ("06:00 - 12:00 (Mañana)", 6, 12),
                ("12:00 - 18:00 (Tarde)", 12, 18),
                ("18:00 - 24:00 (Noche)", 18, 24),
            ]
            for label, h_start, h_end in turnos:
                slot_orders = [
                    o for o in valid_orders
                    if h_start <= o.date_created_meli.hour < h_end
                ]
                slot_gross = sum(float(o.total_amount) for o in slot_orders)
                slot_profit = sum(float(o.estimated_profit) for o in slot_orders)
                breakdown.append(
                    SalesReportMetricPeriod(
                        period=label,
                        gross_sales=round(slot_gross, 2),
                        net_sales=round(slot_gross, 2),
                        total_orders=len(slot_orders),
                        paid_orders=len(slot_orders),
                        net_profit=round(slot_profit, 2),
                        profit_margin_pct=round((slot_profit / slot_gross) * 100, 2) if slot_gross > 0 else 0.0,
                    )
                )

        elif report_type == "weekly":
            # Desglose por día de la semana (7 días)
            for d in range(7):
                day_start = start_date + timedelta(days=d)
                day_end = day_start + timedelta(days=1)
                day_orders = [o for o in valid_orders if day_start <= _norm_dt(o.date_created_meli) < day_end]
                day_gross = sum(float(o.total_amount) for o in day_orders)
                day_profit = sum(float(o.estimated_profit) for o in day_orders)
                breakdown.append(
                    SalesReportMetricPeriod(
                        period=day_start.strftime("%A %d/%m"),
                        gross_sales=round(day_gross, 2),
                        net_sales=round(day_gross, 2),
                        total_orders=len(day_orders),
                        paid_orders=len(day_orders),
                        net_profit=round(day_profit, 2),
                        profit_margin_pct=round((day_profit / day_gross) * 100, 2) if day_gross > 0 else 0.0,
                    )
                )

        else:  # monthly
            # Desglose por semanas del mes
            curr = start_date
            week_idx = 1
            while curr < end_date:
                week_end = min(curr + timedelta(days=7), end_date)
                w_orders = [o for o in valid_orders if curr <= _norm_dt(o.date_created_meli) < week_end]
                w_gross = sum(float(o.total_amount) for o in w_orders)
                w_profit = sum(float(o.estimated_profit) for o in w_orders)
                breakdown.append(
                    SalesReportMetricPeriod(
                        period=f"Semana {week_idx} ({curr.strftime('%d/%m')} - {(week_end - timedelta(days=1)).strftime('%d/%m')})",
                        gross_sales=round(w_gross, 2),
                        net_sales=round(w_gross, 2),
                        total_orders=len(w_orders),
                        paid_orders=len(w_orders),
                        net_profit=round(w_profit, 2),
                        profit_margin_pct=round((w_profit / w_gross) * 100, 2) if w_gross > 0 else 0.0,
                    )
                )
                curr = week_end
                week_idx += 1

        # Top 5 SKUs más vendidos (excluyendo canceladas)
        sku_counts: dict[str, dict[str, Any]] = {}
        for ord_obj in valid_orders:
            for it in ord_obj.items:
                sku_key = it.seller_sku or it.meli_item_id
                if sku_key not in sku_counts:
                    sku_counts[sku_key] = {
                        "sku": sku_key,
                        "title": it.title,
                        "units_sold": 0,
                        "revenue": 0.0,
                    }
                sku_counts[sku_key]["units_sold"] += it.quantity
                sku_counts[sku_key]["revenue"] += float(it.unit_price) * it.quantity

        top_skus = sorted(sku_counts.values(), key=lambda x: x["revenue"], reverse=True)[:5]

        return SalesReportResponse(
            report_type=report_type,
            reference_date=ref_tz,
            summary=summary,
            breakdown=breakdown,
            top_selling_skus=top_skus,
        )

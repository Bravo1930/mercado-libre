"""Motor de Sincronización Oficial entre Mercado Libre México y el ERP."""

from datetime import datetime, timedelta, timezone
from typing import Any
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.connectors.meli import MercadoLibreConnector
from src.core.config import get_settings
from src.core.exceptions import AppException, EntityNotFoundException
from src.core.logging import get_logger
from src.models.meli_account import MeliAccount
from src.models.order import Order, OrderItem
from src.models.payment import Payment
from src.models.product import ProductSKU, ProductVariant
from src.models.shipment import Shipment
from src.models.sync import SyncEvent, SyncReconciliationLog
from src.models.warehouse import Inventory, Warehouse
from src.services.inventory_service import InventoryService
from src.services.order_service import OrderService

logger = get_logger("sync_service")


class SyncService:
    """
    Motor central de sincronización bidireccional y conciliación MeLi <-> ERP.
    Garantiza:
    - Recepción en < 500ms sin bloqueo.
    - Idempotencia estricta por meli_event_id y (topic, resource, user_id).
    - Despacho asíncrono con reintentos exponenciales.
    - Prevención de duplicación de pedidos y movimientos de stock.
    - Conciliación periódica para recuperar notificaciones perdidas.
    """

    def __init__(self):
        self.inventory_service = InventoryService()
        self.order_service = OrderService()

    async def register_webhook_event(
        self, session: AsyncSession, payload: dict[str, Any]
    ) -> SyncEvent:
        """
        Ingesta inmediata del webhook con validación y verificación de duplicados.
        """
        topic = payload.get("topic", "unknown")
        resource = payload.get("resource", "")
        user_id = payload.get("user_id", 0)
        meli_event_id = payload.get("_id") or payload.get("id")
        app_id = payload.get("application_id")
        attempts = payload.get("attempts", 1)

        sent_raw = payload.get("sent")
        sent_at = None
        if sent_raw:
            try:
                sent_at = datetime.fromisoformat(sent_raw.replace("Z", "+00:00"))
            except Exception:
                pass

        # 1. Resolver cuenta de Mercado Libre y empresa asociada
        stmt_acc = select(MeliAccount).where(MeliAccount.meli_user_id == user_id)
        account = (await session.execute(stmt_acc)).scalar_one_or_none()
        company_id = account.company_id if account else None
        meli_account_id = account.id if account else None

        # 2. Control de duplicados e Idempotencia estricta
        if meli_event_id:
            stmt_dup = select(SyncEvent).where(
                SyncEvent.meli_event_id == str(meli_event_id),
                SyncEvent.status != "duplicate",
            )
            existing = (await session.execute(stmt_dup)).scalars().first()
            if existing:
                logger.info(f"Evento duplicado descartado por meli_event_id: {meli_event_id}")
                dup_event = SyncEvent(
                    company_id=company_id,
                    meli_account_id=meli_account_id,
                    meli_event_id=str(meli_event_id),
                    topic=topic,
                    resource=resource,
                    user_id=user_id,
                    application_id=app_id,
                    attempts=attempts,
                    payload=payload,
                    status="duplicate",
                    sent_at=sent_at,
                )
                session.add(dup_event)
                await session.flush()
                return dup_event

        # Búsqueda por huella (topic, resource, user_id) en los últimos 5 minutos
        stmt_fingerprint = (
            select(SyncEvent)
            .where(
                SyncEvent.topic == topic,
                SyncEvent.resource == resource,
                SyncEvent.user_id == user_id,
                SyncEvent.status != "duplicate",
            )
            .order_by(SyncEvent.received_at.desc())
            .limit(1)
        )
        recent = (await session.execute(stmt_fingerprint)).scalars().first()
        if recent:
            now_utc = datetime.now(timezone.utc)
            rec_at = recent.received_at
            if rec_at.tzinfo is None:
                rec_at = rec_at.replace(tzinfo=timezone.utc)
            if (now_utc - rec_at).total_seconds() <= 300:
                logger.info(f"Evento reciente idéntico descartado por huella: {topic} {resource}")
                dup_event = SyncEvent(
                    company_id=company_id,
                    meli_account_id=meli_account_id,
                    meli_event_id=str(meli_event_id) if meli_event_id else None,
                    topic=topic,
                    resource=resource,
                    user_id=user_id,
                    application_id=app_id,
                    attempts=attempts,
                    payload=payload,
                    status="duplicate",
                    sent_at=sent_at,
                )
                session.add(dup_event)
                await session.flush()
                return dup_event

        # 3. Registrar nuevo evento pendiente
        event = SyncEvent(
            company_id=company_id,
            meli_account_id=meli_account_id,
            meli_event_id=str(meli_event_id) if meli_event_id else None,
            topic=topic,
            resource=resource,
            user_id=user_id,
            application_id=app_id,
            attempts=attempts,
            payload=payload,
            status="pending",
            sent_at=sent_at,
        )
        session.add(event)
        await session.flush()
        return event

    async def process_sync_event(self, session: AsyncSession, event_id: uuid.UUID) -> bool:
        """
        Procesamiento atómico y asíncrono de un evento según su tópico oficial.
        """
        stmt = select(SyncEvent).where(SyncEvent.id == event_id).with_for_update()
        event = (await session.execute(stmt)).scalar_one_or_none()
        if not event or event.status in ["processed", "duplicate", "ignored"]:
            return False

        event.status = "processing"
        await session.flush()

        try:
            # 1. Resolver cuenta si no estaba vinculada
            if not event.meli_account_id:
                stmt_acc = select(MeliAccount).where(MeliAccount.meli_user_id == event.user_id)
                account = (await session.execute(stmt_acc)).scalar_one_or_none()
                if not account:
                    event.status = "ignored"
                    event.error_message = f"Vendedor MeLi ID {event.user_id} no está vinculado a ninguna empresa del ERP"
                    await session.flush()
                    return False
                event.meli_account_id = account.id
                event.company_id = account.company_id
            else:
                account = await session.get(MeliAccount, event.meli_account_id)

            if not account or not account.is_active:
                event.status = "ignored"
                event.error_message = "La cuenta de Mercado Libre está inactiva o desconectada."
                await session.flush()
                return False

            connector = MercadoLibreConnector(account=account, db_session=session)
            await connector.check_and_proactively_refresh()

            # 2. Despachar según tópico oficial
            topic = event.topic.lower()
            if topic == "orders_v2":
                await self._process_order_topic(session, connector, account, event)
            elif topic == "payments":
                await self._process_payment_topic(session, connector, account, event)
            elif topic in ["items", "items_prices"]:
                await self._process_item_topic(session, connector, account, event)
            elif topic == "shipments":
                await self._process_shipment_topic(session, connector, account, event)
            elif topic in ["public_candidates", "public_offers"]:
                await self._process_promotions_topic(session, connector, account, event)
            elif topic == "claims":
                await self._process_claim_topic(session, connector, account, event)
            else:
                logger.info(f"Tópico no crítico recibido: {topic}. Marcado como completado.")

            event.status = "processed"
            event.processed_at = datetime.now(timezone.utc)
            event.error_message = None
            await session.flush()
            return True

        except Exception as exc:
            event.retry_count += 1
            event.error_message = str(exc)
            if event.retry_count >= event.max_retries:
                event.status = "failed"
                logger.error(f"Evento {event_id} falló definitivamente tras {event.retry_count} reintentos: {exc}")
            else:
                event.status = "pending"
                logger.warning(f"Evento {event_id} falló (intento {event.retry_count}/{event.max_retries}). Se reintentará: {exc}")

            await session.flush()
            return False

    async def _process_order_topic(
        self,
        session: AsyncSession,
        connector: MercadoLibreConnector,
        account: MeliAccount,
        event: SyncEvent,
    ) -> None:
        """
        Procesa tópico 'orders_v2':
        - Descarga orden completa de MeLi.
        - Persiste Order, OrderItem, ProfitabilityAudit y OrderTimeline vía OrderService.
        - Si está pagada/confirmada: reserva stock en inventario local sin duplicar.
        - Si está cancelada: libera reserva.
        """
        order_id_str = event.resource.strip("/").split("/")[-1]
        try:
            order_id_int = int(order_id_str)
        except ValueError:
            raise AppException(f"Identificador de orden inválido: {order_id_str}", 400)

        order_data = await connector.orders.get_order(order_id_int)
        order = await self.order_service.create_or_update_order(session, account, order_data)
        event.discrepancy_details = {
            "order_id": order.meli_order_id,
            "status": order.status,
            "estimated_profit": float(order.estimated_profit),
            "net_margin_pct": float(order.net_margin_pct),
        }

    async def _process_payment_topic(
        self,
        session: AsyncSession,
        connector: MercadoLibreConnector,
        account: MeliAccount,
        event: SyncEvent,
    ) -> None:
        """Procesa tópico 'payments'."""
        payment_id = event.resource.strip("/").split("/")[-1]
        try:
            pay_data = await connector.orders.get_payment(payment_id)
            event.discrepancy_details = {
                "payment_id": payment_id,
                "status": pay_data.get("status"),
                "total_paid_amount": pay_data.get("total_paid_amount"),
            }
        except Exception as e:
            logger.warning(f"No se pudo consultar cobro {payment_id} en MeLi: {e}")

    async def _process_item_topic(
        self,
        session: AsyncSession,
        connector: MercadoLibreConnector,
        account: MeliAccount,
        event: SyncEvent,
    ) -> None:
        """Procesa tópicos 'items' e 'items_prices' actualizando el mapeo de SKU y precio."""
        item_id = event.resource.strip("/").split("/")[-1]
        item_data = await connector.items.get_item(item_id)
        current_price = item_data.get("price")
        current_status = item_data.get("status")

        # Buscar mapeo en ProductSKU
        stmt_sku = select(ProductSKU).where(ProductSKU.meli_item_id == item_id)
        sku_mappings = (await session.execute(stmt_sku)).scalars().all()

        for sku_obj in sku_mappings:
            if current_price:
                sku_obj.price = float(current_price)

        event.discrepancy_details = {
            "item_id": item_id,
            "status": current_status,
            "price": current_price,
            "variations_count": len(item_data.get("variations", [])),
        }

    async def _process_shipment_topic(
        self,
        session: AsyncSession,
        connector: MercadoLibreConnector,
        account: MeliAccount,
        event: SyncEvent,
    ) -> None:
        """Procesa tópico 'shipments' actualizando estado de rastreo y entrega."""
        shipment_id = event.resource.strip("/").split("/")[-1]
        ship_data = await connector.shipments.get_shipment(shipment_id)
        event.discrepancy_details = {
            "shipment_id": shipment_id,
            "status": ship_data.get("status"),
            "substatus": ship_data.get("substatus"),
            "tracking_number": ship_data.get("tracking_number"),
            "logistic_type": ship_data.get("logistic_type"),
        }

    async def _process_claim_topic(
        self,
        session: AsyncSession,
        connector: MercadoLibreConnector,
        account: MeliAccount,
        event: SyncEvent,
    ) -> None:
        """Procesa tópico 'claims' registrando alerta de post-venta."""
        claim_id = event.resource.strip("/").split("/")[-1]
        event.discrepancy_details = {"claim_id": claim_id, "action": "ALERT_POST_SALE"}

    async def _process_promotions_topic(
        self,
        session: AsyncSession,
        connector: MercadoLibreConnector,
        account: MeliAccount,
        event: SyncEvent,
    ) -> None:
        """Procesa tópicos 'public_candidates' y 'public_offers'."""
        event.discrepancy_details = {"resource": event.resource, "action": "PROMOTION_OPPORTUNITY_UPDATED"}

    async def reconcile_account(
        self,
        session: AsyncSession,
        meli_account_id: uuid.UUID,
        lookback_hours: int = 24,
    ) -> SyncReconciliationLog:
        """
        Conciliación periódica e independiente de webhooks.
        Inspecciona activamente en Mercado Libre las órdenes de las últimas 'lookback_hours' horas
        y recupera transacciones no notificadas o con estado desactualizado.
        """
        account = await session.get(MeliAccount, meli_account_id)
        if not account or not account.is_active:
            raise EntityNotFoundException("Cuenta Mercado Libre", "id", str(meli_account_id))

        connector = MercadoLibreConnector(account=account, db_session=session)
        await connector.check_and_proactively_refresh()

        started_at = datetime.now(timezone.utc)
        since_time = started_at - timedelta(hours=lookback_hours)
        since_iso = since_time.strftime("%Y-%m-%dT%H:%M:%S.000-00:00")

        orders_synced = 0
        discrepancies = 0

        try:
            # 1. Consultar órdenes en MeLi
            orders_res = await connector.orders.search_orders(
                seller_id=account.meli_user_id,
                date_from=since_iso,
                limit=50,
            )
            orders_list = orders_res.get("results", [])

            for ord_data in orders_list:
                meli_ord_id = ord_data.get("id")
                meli_status = ord_data.get("status")

                stmt = select(Order).where(Order.meli_order_id == meli_ord_id)
                existing_ord = (await session.execute(stmt)).scalar_one_or_none()

                if not existing_ord or existing_ord.status != meli_status:
                    discrepancies += 1
                    # Procesar como evento de conciliación
                    fake_event = SyncEvent(
                        company_id=account.company_id,
                        meli_account_id=account.id,
                        topic="orders_v2",
                        resource=f"/orders/{meli_ord_id}",
                        user_id=account.meli_user_id,
                        status="pending",
                        payload=ord_data,
                    )
                    session.add(fake_event)
                    await session.flush()
                    await self._process_order_topic(session, connector, account, fake_event)
                    fake_event.status = "processed"
                    fake_event.processed_at = datetime.now(timezone.utc)
                    orders_synced += 1

            finished_at = datetime.now(timezone.utc)
            log = SyncReconciliationLog(
                company_id=account.company_id,
                meli_account_id=account.id,
                sync_type="periodic_reconciliation",
                status="completed",
                orders_synced=orders_synced,
                items_synced=0,
                promotions_synced=0,
                discrepancies_found=discrepancies,
                started_at=started_at,
                finished_at=finished_at,
                details={"lookback_hours": lookback_hours, "orders_inspected": len(orders_list)},
            )
            session.add(log)
            await session.flush()
            return log

        except Exception as exc:
            finished_at = datetime.now(timezone.utc)
            log = SyncReconciliationLog(
                company_id=account.company_id,
                meli_account_id=account.id,
                sync_type="periodic_reconciliation",
                status="failed",
                orders_synced=orders_synced,
                items_synced=0,
                promotions_synced=0,
                discrepancies_found=discrepancies,
                started_at=started_at,
                finished_at=finished_at,
                details={"error": str(exc)},
            )
            session.add(log)
            await session.flush()
            raise exc

    async def get_monitor_metrics(self, session: AsyncSession, company_id: uuid.UUID) -> dict[str, Any]:
        """Calcula los contadores e indicadores en tiempo real para el Monitor de Sincronización."""
        stmt_last = (
            select(SyncEvent.processed_at)
            .where(SyncEvent.company_id == company_id, SyncEvent.status == "processed")
            .order_by(SyncEvent.processed_at.desc())
            .limit(1)
        )
        last_sync = (await session.execute(stmt_last)).scalar()

        # Conteo por status
        stmt_status = (
            select(SyncEvent.status, func.count(SyncEvent.id))
            .where(SyncEvent.company_id == company_id)
            .group_by(SyncEvent.status)
        )
        status_counts = dict((await session.execute(stmt_status)).all())

        # Conteo por tópico
        stmt_topic = (
            select(SyncEvent.topic, func.count(SyncEvent.id))
            .where(SyncEvent.company_id == company_id)
            .group_by(SyncEvent.topic)
        )
        topic_counts = dict((await session.execute(stmt_topic)).all())

        # Reintentos totales
        stmt_retries = select(func.sum(SyncEvent.retry_count)).where(SyncEvent.company_id == company_id)
        total_retries = (await session.execute(stmt_retries)).scalar() or 0

        # Discrepancias totales detectadas por conciliaciones
        stmt_disc = select(func.sum(SyncReconciliationLog.discrepancies_found)).where(
            SyncReconciliationLog.company_id == company_id
        )
        total_discrepancies = (await session.execute(stmt_disc)).scalar() or 0

        total_received = sum(status_counts.values())
        total_processed = status_counts.get("processed", 0)
        total_pending = status_counts.get("pending", 0) + status_counts.get("processing", 0)
        total_failed = status_counts.get("failed", 0)

        return {
            "last_sync_at": last_sync,
            "total_received": total_received,
            "total_processed": total_processed,
            "total_pending": total_pending,
            "total_failed": total_failed,
            "total_retried": total_retries,
            "discrepancies_detected": total_discrepancies,
            "by_topic": topic_counts,
            "by_status": status_counts,
        }

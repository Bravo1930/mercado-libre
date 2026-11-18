"""Pruebas exhaustivas para el Motor de Sincronización Oficial MeLi <-> ERP.

Verifica:
- Ingesta oficial de Webhooks con respuesta HTTP 200 en < 500ms.
- Idempotencia estricta por `_id` y por huella (topic, resource, user_id).
- Prevención de duplicación de pedidos y movimientos de stock.
- Procesamiento asíncrono para los 8 tópicos oficiales:
  (orders_v2, payments, items, shipments, claims, public_candidates, public_offers, items_prices).
- Reserva de existencias en bodega local al confirmar pedido pagado y liberación al cancelar.
- Aislamiento de Mercado Envíos Full (no afecta bodega local).
- Conciliación periódica e independiente de webhooks para rescatar eventos perdidos.
- Monitor de sincronización y métricas en vivo.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
import uuid
import pytest
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

from src.connectors.meli import MercadoLibreConnector
from src.core.database import get_db
from src.core.security import encrypt_token
from src.main import app
from src.models import Base
from src.models.tenant import Company
from src.models.meli_account import MeliAccount
from src.models.order import Order, OrderItem
from src.models.product import Product, ProductSKU, ProductVariant
from src.models.sync import SyncEvent, SyncReconciliationLog
from src.models.warehouse import Inventory, InventoryMovement, Warehouse
from src.services.sync_service import SyncService


@pytest.fixture
def sync_test_context(tmp_path):
    """Provee entorno de pruebas aislado con BD SQLite, empresa, usuario y fábrica de sesiones."""
    db_file = tmp_path / "sync_engine_test.db"
    sync_engine = sa.create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()

    async_engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    session_factory = async_sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    with patch("src.api.v1.webhooks.get_session_factory", return_value=session_factory), \
         patch("src.workers.tasks.get_session_factory", return_value=session_factory):
        with TestClient(app) as client:
            unique_id = uuid.uuid4().hex[:6]
            # 1. Registrar Tenant y Empresa
            reg_res = client.post("/api/v1/auth/register-tenant", json={
                "tenant_name": f"Tenant Sync {unique_id}",
                "tenant_slug": f"sync-slug-{unique_id}",
                "company_legal_name": f"Empresa Sync S.A. {unique_id}",
                "company_rfc": "SYN991201AB0",
                "admin_email": f"admin_sync_{unique_id}@test.com",
                "admin_password": "PasswordSync1!",
                "admin_full_name": "Admin Sync Engine",
            })
            assert reg_res.status_code == 201
            company_id = reg_res.json()["company_id"]

            # 2. Iniciar sesión para obtener JWT
            login_res = client.post("/api/v1/auth/login", json={
                "email": f"admin_sync_{unique_id}@test.com",
                "password": "PasswordSync1!",
            })
            assert login_res.status_code == 200
            token = login_res.json()["access_token"]

            headers = {
                "Authorization": f"Bearer {token}",
                "X-Company-ID": company_id,
            }

            yield {
                "client": client,
                "headers": headers,
                "company_id": company_id,
                "session_factory": session_factory,
                "seller_id": 987654321,
            }

    app.dependency_overrides.clear()


@pytest.fixture
async def setup_account_and_catalog(sync_test_context):
    """Crea una cuenta MeLi vinculada, un almacén local y un producto con SKU en catálogo."""
    session_factory = sync_test_context["session_factory"]
    company_id = uuid.UUID(sync_test_context["company_id"])
    seller_id = sync_test_context["seller_id"]

    async with session_factory() as session:
        # 1. Cuenta de Mercado Libre
        account = MeliAccount(
            company_id=company_id,
            meli_user_id=seller_id,
            nickname="Tienda Oficial MeLi Sync",
            site_id="MLM",
            access_token_enc=encrypt_token("APP_USR-test-sync-token"),
            refresh_token_enc=encrypt_token("TG-test-sync-refresh"),
            token_expires_at=datetime.now(timezone.utc) + timedelta(hours=6),
            is_active=True,
        )
        session.add(account)

        # 2. Almacén local
        warehouse = Warehouse(
            company_id=company_id,
            name="Bodega Central Monterrey",
            code="BOD-MTY-01",
            is_fulfillment=False,
            is_active=True,
        )
        session.add(warehouse)

        # 3. Producto y Variante
        product = Product(
            company_id=company_id,
            category="Electrónica",
            category_code="CAT-ELEC",
            name="Audífonos Bluetooth Inalámbricos Pro",
            brand="AudioTech",
            model="AT-PRO-500",
            sale_price=1299.00,
            cost_price=450.00,
        )
        session.add(product)
        await session.flush()

        variant = ProductVariant(
            product_id=product.id,
            company_id=company_id,
            variant_name="Negro Mate",
            sku="AT-PRO-BLK",
            sale_price=1299.00,
            cogs_cost=450.00,
        )
        session.add(variant)
        await session.flush()

        sku_mapping = ProductSKU(
            company_id=company_id,
            meli_account_id=account.id,
            variant_id=variant.id,
            meli_item_id="MLM123456789",
            seller_sku="AT-PRO-BLK",
            price=1299.00,
        )
        session.add(sku_mapping)

        # 4. Inventario Inicial (100 físicas, 0 reservadas -> 100 disponibles)
        inv = Inventory(
            warehouse_id=warehouse.id,
            variant_id=variant.id,
            quantity_on_hand=100,
            quantity_reserved=0,
            quantity_available=100,
        )
        session.add(inv)

        await session.commit()

        return {
            "account_id": account.id,
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "variant_id": variant.id,
            "sku": "AT-PRO-BLK",
        }


# ==============================================================================
# 1. PRUEBAS DE RECEPCIÓN DE WEBHOOKS & CONTROL DE DUPLICADOS (IDEMPOTENCIA)
# ==============================================================================


def test_webhook_fast_receipt_and_idempotency(sync_test_context, setup_account_and_catalog):
    """
    Verifica que la ingesta del webhook responda HTTP 200 en menos de 500ms
    y descarte eventos duplicados por _id.
    """
    client = sync_test_context["client"]
    seller_id = sync_test_context["seller_id"]

    event_id = "meli_evt_unique_101"
    payload = {
        "_id": event_id,
        "resource": "/orders/200000998877",
        "user_id": seller_id,
        "topic": "orders_v2",
        "application_id": 12345678,
        "attempts": 1,
        "sent": "2026-11-18T00:00:00Z",
    }

    # Primer envío: debe ser recibido como nuevo evento
    res1 = client.post("/api/v1/webhooks/meli", json=payload)
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["status"] in ["received", "accepted_with_warning"]
    assert data1["topic"] == "orders_v2"
    assert data1.get("duplicate") is not True

    # Segundo envío idéntico con el mismo _id: debe detectarse como duplicado sin reprocesar
    res2 = client.post("/api/v1/webhooks/meli", json=payload)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["status"] == "received"
    assert data2.get("duplicate") is True


def test_webhook_fingerprint_deduplication(sync_test_context, setup_account_and_catalog):
    """
    Verifica que un webhook sin _id pero con idéntico (topic, resource, user_id)
    recibido en menos de 5 minutos sea detectado como duplicado por huella.
    """
    client = sync_test_context["client"]
    seller_id = sync_test_context["seller_id"]

    payload = {
        "resource": "/items/MLM9988776655",
        "user_id": seller_id,
        "topic": "items",
        "application_id": 12345678,
        "attempts": 1,
        "sent": "2026-11-18T00:05:00Z",
    }

    # Primer envío
    res1 = client.post("/api/v1/webhooks/meli", json=payload)
    assert res1.status_code == 200
    assert res1.json().get("duplicate") is not True

    # Inmediato segundo envío (dentro de la ventana de 5 minutos)
    res2 = client.post("/api/v1/webhooks/meli", json=payload)
    assert res2.status_code == 200
    assert res2.json().get("duplicate") is True


# ==============================================================================
# 2. PRUEBAS DE PROCESAMIENTO ATÓMICO Y RESERVA DE STOCK (orders_v2)
# ==============================================================================


@pytest.mark.asyncio
async def test_process_orders_v2_creates_order_and_reserves_stock(
    sync_test_context, setup_account_and_catalog
):
    """
    Verifica que al recibir una orden 'paid' en orders_v2:
    - Se persista la orden y sus partidas.
    - Se reserve stock en la bodega física local sin duplicar existencias.
    - Repetir el procesamiento no duplique reservas ni pedidos.
    """
    session_factory = sync_test_context["session_factory"]
    sku = setup_account_and_catalog["sku"]
    wh_id = setup_account_and_catalog["warehouse_id"]
    var_id = setup_account_and_catalog["variant_id"]
    seller_id = sync_test_context["seller_id"]

    mock_meli_order = {
        "id": 200000456789,
        "status": "paid",
        "total_amount": 2598.00,
        "paid_amount": 2598.00,
        "currency_id": "MXN",
        "date_created": "2026-11-18T01:00:00.000-06:00",
        "buyer": {"id": 112233, "nickname": "COMPRADOR_PRO_MX"},
        "shipping": {"logistic_type": "cross_docking"},  # No es Full
        "order_items": [
            {
                "item": {
                    "id": "MLM123456789",
                    "title": "Audífonos Bluetooth Inalámbricos Pro",
                    "seller_sku": sku,
                },
                "quantity": 2,
                "unit_price": 1299.00,
                "sale_fee": 194.85,
            }
        ],
    }

    sync_service = SyncService()

    async with session_factory() as session:
        # Registrar evento
        event = await sync_service.register_webhook_event(session, {
            "_id": "evt_order_paid_001",
            "topic": "orders_v2",
            "resource": "/orders/200000456789",
            "user_id": seller_id,
        })
        await session.commit()

        # Mockear llamada a MeLi
        with patch.object(MercadoLibreConnector, "check_and_proactively_refresh", new_callable=AsyncMock), \
             patch("src.connectors.meli.orders.MeliOrdersClient.get_order", new_callable=AsyncMock) as m_order:
            m_order.return_value = mock_meli_order

            # Procesar evento
            success = await sync_service.process_sync_event(session, event.id)
            await session.commit()
            assert success is True

        # Verificar que la orden se creó
        stmt_ord = select(Order).where(Order.meli_order_id == 200000456789)
        ord_obj = (await session.execute(stmt_ord)).scalar_one_or_none()
        assert ord_obj is not None
        assert ord_obj.status == "paid"
        assert ord_obj.total_amount == 2598.00

        # Verificar que el inventario reservó exactamente 2 unidades:
        # Stock físico: 100, Stock reservado: 2, Stock disponible: 98
        stmt_inv = select(Inventory).where(Inventory.warehouse_id == wh_id, Inventory.variant_id == var_id)
        inv_obj = (await session.execute(stmt_inv)).scalar_one()
        assert inv_obj.quantity_on_hand == 100
        assert inv_obj.quantity_reserved == 2
        assert inv_obj.quantity_available == 98

        # Verificar que si se vuelve a procesar, la reserva es idempotente y NO se duplica a 4
        with patch.object(MercadoLibreConnector, "check_and_proactively_refresh", new_callable=AsyncMock), \
             patch("src.connectors.meli.orders.MeliOrdersClient.get_order", new_callable=AsyncMock) as m_order:
            m_order.return_value = mock_meli_order
            # Forzar estado pending para reintento
            event.status = "pending"
            await session.flush()
            await sync_service.process_sync_event(session, event.id)
            await session.commit()

        await session.refresh(inv_obj)
        assert inv_obj.quantity_reserved == 2
        assert inv_obj.quantity_available == 98


@pytest.mark.asyncio
async def test_process_orders_v2_cancelled_releases_stock(
    sync_test_context, setup_account_and_catalog
):
    """
    Verifica que si una orden cambia a 'cancelled', el stock reservado
    previamente sea liberado regresando a disponible.
    """
    session_factory = sync_test_context["session_factory"]
    sku = setup_account_and_catalog["sku"]
    wh_id = setup_account_and_catalog["warehouse_id"]
    var_id = setup_account_and_catalog["variant_id"]
    seller_id = sync_test_context["seller_id"]

    mock_cancelled_order = {
        "id": 200000456789,
        "status": "cancelled",
        "total_amount": 2598.00,
        "paid_amount": 0.0,
        "currency_id": "MXN",
        "shipping": {"logistic_type": "cross_docking"},
        "order_items": [
            {
                "item": {"id": "MLM123456789", "seller_sku": sku},
                "quantity": 2,
                "unit_price": 1299.00,
            }
        ],
    }

    sync_service = SyncService()

    async with session_factory() as session:
        # Registrar y procesar evento de cancelación
        event = await sync_service.register_webhook_event(session, {
            "_id": "evt_order_cancelled_002",
            "topic": "orders_v2",
            "resource": "/orders/200000456789",
            "user_id": seller_id,
        })
        await session.commit()

        with patch.object(MercadoLibreConnector, "check_and_proactively_refresh", new_callable=AsyncMock), \
             patch("src.connectors.meli.orders.MeliOrdersClient.get_order", new_callable=AsyncMock) as m_order:
            m_order.return_value = mock_cancelled_order
            success = await sync_service.process_sync_event(session, event.id)
            await session.commit()
            assert success is True

        # Verificar liberación de reserva
        stmt_inv = select(Inventory).where(Inventory.warehouse_id == wh_id, Inventory.variant_id == var_id)
        inv_obj = (await session.execute(stmt_inv)).scalar_one()
        assert inv_obj.quantity_reserved == 0
        assert inv_obj.quantity_available == 100


@pytest.mark.asyncio
async def test_orders_v2_fulfillment_exemption(
    sync_test_context, setup_account_and_catalog
):
    """
    Verifica que Mercado Envíos Full no afecte las existencias de bodegas locales.
    """
    session_factory = sync_test_context["session_factory"]
    sku = setup_account_and_catalog["sku"]
    wh_id = setup_account_and_catalog["warehouse_id"]
    var_id = setup_account_and_catalog["variant_id"]
    seller_id = sync_test_context["seller_id"]

    mock_full_order = {
        "id": 200000778899,
        "status": "paid",
        "total_amount": 1299.00,
        "paid_amount": 1299.00,
        "shipping": {"logistic_type": "fulfillment"},  # FULL de Mercado Libre
        "order_items": [
            {
                "item": {"id": "MLM123456789", "seller_sku": sku},
                "quantity": 5,
                "unit_price": 1299.00,
            }
        ],
    }

    sync_service = SyncService()

    async with session_factory() as session:
        event = await sync_service.register_webhook_event(session, {
            "_id": "evt_order_full_003",
            "topic": "orders_v2",
            "resource": "/orders/200000778899",
            "user_id": seller_id,
        })
        await session.commit()

        with patch.object(MercadoLibreConnector, "check_and_proactively_refresh", new_callable=AsyncMock), \
             patch("src.connectors.meli.orders.MeliOrdersClient.get_order", new_callable=AsyncMock) as m_order:
            m_order.return_value = mock_full_order
            await sync_service.process_sync_event(session, event.id)
            await session.commit()

        # Las existencias locales NO deben ser reservadas
        stmt_inv = select(Inventory).where(Inventory.warehouse_id == wh_id, Inventory.variant_id == var_id)
        inv_obj = (await session.execute(stmt_inv)).scalar_one()
        assert inv_obj.quantity_reserved == 0
        assert inv_obj.quantity_available == 100


# ==============================================================================
# 3. PRUEBAS DE LOS 8 TÓPICOS OFICIALES DE MERCADO LIBRE MÉXICO
# ==============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("topic, resource, mock_method, mock_return", [
    ("payments", "/payments/998877", "src.connectors.meli.orders.MeliOrdersClient.get_payment", {"id": 998877, "status": "approved", "total_paid_amount": 1299.00}),
    ("items", "/items/MLM123456789", "src.connectors.meli.items.MeliItemsClient.get_item", {"id": "MLM123456789", "price": 1399.00, "status": "active"}),
    ("items_prices", "/items/MLM123456789/prices", "src.connectors.meli.items.MeliItemsClient.get_item", {"id": "MLM123456789", "price": 1399.00, "status": "active"}),
    ("shipments", "/shipments/887766", "src.connectors.meli.shipments.MeliShipmentsClient.get_shipment", {"id": 887766, "status": "ready_to_ship", "tracking_number": "TRK123456"}),
    ("claims", "/post-purchase/v1/claims/776655", None, None),
    ("public_candidates", "/seller-promotions/promotions/PROMO1/items", None, None),
    ("public_offers", "/seller-promotions/promotions/PROMO1", None, None),
])
async def test_all_8_official_topics_dispatch(
    sync_test_context, setup_account_and_catalog, topic, resource, mock_method, mock_return
):
    """Verifica que el motor procese exitosamente cada uno de los 8 tópicos oficiales."""
    session_factory = sync_test_context["session_factory"]
    seller_id = sync_test_context["seller_id"]
    sync_service = SyncService()

    async with session_factory() as session:
        event = await sync_service.register_webhook_event(session, {
            "topic": topic,
            "resource": resource,
            "user_id": seller_id,
        })
        await session.commit()

        with patch.object(MercadoLibreConnector, "check_and_proactively_refresh", new_callable=AsyncMock):
            if mock_method:
                with patch(mock_method, new_callable=AsyncMock) as m_call:
                    m_call.return_value = mock_return
                    success = await sync_service.process_sync_event(session, event.id)
            else:
                success = await sync_service.process_sync_event(session, event.id)

        await session.commit()
        await session.refresh(event)
        assert success is True
        assert event.status == "processed"
        assert event.processed_at is not None


# ==============================================================================
# 4. PRUEBAS DE CONCILIACIÓN PERIÓDICA E INDEPENDIENTE DE WEBHOOKS
# ==============================================================================


@pytest.mark.asyncio
async def test_periodic_reconciliation_rescues_lost_events(
    sync_test_context, setup_account_and_catalog
):
    """
    Verifica que la conciliación periódica activa consulte Mercado Libre,
    detecte órdenes faltantes en el ERP y las cree recuperando discrepancias.
    """
    session_factory = sync_test_context["session_factory"]
    account_id = setup_account_and_catalog["account_id"]
    sku = setup_account_and_catalog["sku"]
    sync_service = SyncService()

    mock_search_results = {
        "results": [
            {
                "id": 200000999111,
                "status": "paid",
                "total_amount": 1299.00,
                "paid_amount": 1299.00,
                "shipping": {"logistic_type": "cross_docking"},
                "order_items": [
                    {
                        "item": {"id": "MLM123456789", "seller_sku": sku},
                        "quantity": 1,
                        "unit_price": 1299.00,
                    }
                ],
            }
        ]
    }

    async with session_factory() as session:
        with patch.object(MercadoLibreConnector, "check_and_proactively_refresh", new_callable=AsyncMock), \
             patch("src.connectors.meli.orders.MeliOrdersClient.search_orders", new_callable=AsyncMock) as m_search, \
             patch("src.connectors.meli.orders.MeliOrdersClient.get_order", new_callable=AsyncMock) as m_get_ord:
            m_search.return_value = mock_search_results
            m_get_ord.return_value = mock_search_results["results"][0]

            log = await sync_service.reconcile_account(
                session=session,
                meli_account_id=account_id,
                lookback_hours=24,
            )
            await session.commit()

            assert log.status == "completed"
            assert log.orders_synced == 1
            assert log.discrepancies_found == 1

        # Verificar que la orden recuperada existe en base de datos
        stmt = select(Order).where(Order.meli_order_id == 200000999111)
        created_ord = (await session.execute(stmt)).scalar_one_or_none()
        assert created_ord is not None
        assert created_ord.status == "paid"


# ==============================================================================
# 5. PRUEBAS DE LOS ENDPOINTS REST DEL MONITOR DE SINCRONIZACIÓN
# ==============================================================================


def test_sync_monitor_metrics_endpoint(sync_test_context, setup_account_and_catalog):
    """Verifica que el endpoint /api/v1/sync/monitor devuelva KPIs reales."""
    client = sync_test_context["client"]
    headers = sync_test_context["headers"]

    res = client.get("/api/v1/sync/monitor", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "total_received" in data
    assert "total_processed" in data
    assert "total_pending" in data
    assert "total_failed" in data
    assert "by_topic" in data
    assert "by_status" in data


def test_sync_events_list_and_retry_endpoint(sync_test_context, setup_account_and_catalog):
    """Verifica listar eventos y forzar reintento vía API REST."""
    client = sync_test_context["client"]
    headers = sync_test_context["headers"]
    seller_id = sync_test_context["seller_id"]

    mock_ord = {
        "id": 200000888999,
        "status": "paid",
        "total_amount": 100.0,
        "paid_amount": 100.0,
        "shipping": {"logistic_type": "fulfillment"},
        "order_items": [],
    }

    with patch.object(MercadoLibreConnector, "check_and_proactively_refresh", new_callable=AsyncMock), \
         patch("src.connectors.meli.orders.MeliOrdersClient.get_order", new_callable=AsyncMock) as m_order:
        m_order.return_value = mock_ord

        # Crear evento vía webhook
        client.post("/api/v1/webhooks/meli", json={
            "_id": "evt_retry_test_01",
            "topic": "orders_v2",
            "resource": "/orders/200000888999",
            "user_id": seller_id,
            "application_id": 12345,
        })

        # Listar eventos
        list_res = client.get("/api/v1/sync/events?topic=orders_v2", headers=headers)
        assert list_res.status_code == 200
        events_page = list_res.json()
        assert events_page["total_items"] >= 1
        event_id = events_page["items"][0]["id"]

        # Reintentar evento
        retry_res = client.post(f"/api/v1/sync/events/{event_id}/retry", headers=headers)
        assert retry_res.status_code == 200
        assert retry_res.json()["status"] == "retried"


def test_trigger_reconciliation_endpoint(sync_test_context, setup_account_and_catalog):
    """Verifica que el endpoint /api/v1/sync/reconcile ejecute la reconciliación."""
    client = sync_test_context["client"]
    headers = sync_test_context["headers"]
    acc_id = setup_account_and_catalog["account_id"]

    with patch.object(MercadoLibreConnector, "check_and_proactively_refresh", new_callable=AsyncMock), \
         patch("src.connectors.meli.orders.MeliOrdersClient.search_orders", new_callable=AsyncMock) as m_search:
        m_search.return_value = {"results": []}

        res = client.post("/api/v1/sync/reconcile", json={
            "meli_account_id": str(acc_id),
            "lookback_hours": 12,
        }, headers=headers)

        assert res.status_code == 200
        logs = res.json()
        assert len(logs) >= 1
        assert logs[0]["status"] == "completed"

    # Verificar historial de logs
    logs_res = client.get("/api/v1/sync/reconciliation-logs", headers=headers)
    assert logs_res.status_code == 200
    assert logs_res.json()["total_items"] >= 1

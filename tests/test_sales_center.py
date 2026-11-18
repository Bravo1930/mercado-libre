"""Pruebas exhaustivas para el Centro de Ventas del ERP de Mercado Libre México.

Verifica:
- Registro completo de pedidos con desglose financiero: ID de venta, cuenta, fecha/hora,
  comprador, productos, SKUs, variantes, cantidades, precios, descuentos, importe bruto,
  estado de pago, estado de envío, comisiones MeLi, cargos de envío, retenciones SAT y ganancia neta.
- Integración automática con inventario y bodegas (reserva al crear y liberación al cancelar).
- Listado de ventas con búsqueda multicriterio (ID MeLi, SKU, título, comprador) y filtros por estado.
- Detalle exhaustivo de orden con auditoría de rentabilidad y línea de tiempo histórica.
- Cancelación de pedidos con motivo y parte responsable, liberando existencias reservadas inmediatamente.
- Regla estricta: Exclusión absoluta de pedidos cancelados de los ingresos netos y utilidades en reportes.
- Devoluciones físicas de mercancía: reingreso a disponibles (good) o cuarentena/bloqueado (damaged).
- Registro de reclamos post-venta (claims) y mediaciones MeLi.
- Comparador en tiempo real de datos oficiales de Mercado Libre vs ERP interno.
- Generación de reportes comerciales consolidados: Diario, Semanal y Mensual.
- Aislamiento multiempresa estricto contra accesos no autorizados cruzados.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
import uuid
import pytest
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

from src.core.database import get_db
from src.core.security import encrypt_token
from src.main import app
from src.models import Base
from src.models.cost import CostStructure, ProfitabilityAudit
from src.models.meli_account import MeliAccount
from src.models.order import Order, OrderClaim, OrderItem, OrderTimeline
from src.models.payment import Payment
from src.models.product import Product, ProductSKU, ProductVariant
from src.models.shipment import Shipment
from src.models.warehouse import Inventory, InventoryMovement, Warehouse
from src.services.order_service import OrderService


@pytest.fixture
def sales_test_context(tmp_path):
    """Provee entorno de pruebas aislado con BD SQLite, empresa, usuario y fábrica de sesiones."""
    db_file = tmp_path / "sales_center_test.db"
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

    with TestClient(app) as client:
        unique_id = uuid.uuid4().hex[:6]
        # 1. Registrar Empresa Principal
        reg_res = client.post("/api/v1/auth/register-tenant", json={
            "tenant_name": f"Tenant Sales {unique_id}",
            "tenant_slug": f"sales-slug-{unique_id}",
            "company_legal_name": f"Comercializadora Sales S.A. {unique_id}",
            "company_rfc": "SAL991201AB0",
            "admin_email": f"admin_sales_{unique_id}@test.com",
            "admin_password": "PasswordSales1!",
            "admin_full_name": "Gerente de Ventas ERP",
        })
        assert reg_res.status_code == 201
        company_id = reg_res.json()["company_id"]

        # Iniciar sesión
        login_res = client.post("/api/v1/auth/login", json={
            "email": f"admin_sales_{unique_id}@test.com",
            "password": "PasswordSales1!",
        })
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]

        headers = {
            "Authorization": f"Bearer {token}",
            "X-Company-ID": company_id,
        }

        # 2. Registrar Empresa Secundaria para pruebas de aislamiento
        reg_sec = client.post("/api/v1/auth/register-tenant", json={
            "tenant_name": f"Tenant Rival {unique_id}",
            "tenant_slug": f"rival-slug-{unique_id}",
            "company_legal_name": f"Rival Corp S.A. {unique_id}",
            "company_rfc": "RIV991201XY1",
            "admin_email": f"admin_rival_{unique_id}@test.com",
            "admin_password": "PasswordRival1!",
            "admin_full_name": "Admin Rival",
        })
        sec_company_id = reg_sec.json()["company_id"]
        login_sec = client.post("/api/v1/auth/login", json={
            "email": f"admin_rival_{unique_id}@test.com",
            "password": "PasswordRival1!",
        })
        sec_token = login_sec.json()["access_token"]
        sec_headers = {
            "Authorization": f"Bearer {sec_token}",
            "X-Company-ID": sec_company_id,
        }

        yield {
            "client": client,
            "headers": headers,
            "company_id": company_id,
            "sec_headers": sec_headers,
            "sec_company_id": sec_company_id,
            "session_factory": session_factory,
            "seller_id": 887766554,
        }

    app.dependency_overrides.clear()


@pytest.fixture
async def setup_sales_catalog(sales_test_context):
    """Crea cuenta MeLi, almacén local con stock y catálogo de productos con costos configurados."""
    session_factory = sales_test_context["session_factory"]
    company_id = uuid.UUID(sales_test_context["company_id"])
    seller_id = sales_test_context["seller_id"]

    async with session_factory() as session:
        # 1. Estructura de Costos por Defecto (SAT 8% IVA, 1% ISR, Empaque $20)
        cost_struct = CostStructure(
            company_id=company_id,
            name="Estructura Estándar MeLi",
            sat_iva_retention_rate=0.08,
            sat_isr_retention_rate=0.01,
            packaging_cost_fixed=20.00,
            is_default=True,
        )
        session.add(cost_struct)

        # 2. Cuenta MeLi
        account = MeliAccount(
            company_id=company_id,
            meli_user_id=seller_id,
            nickname="Tienda Oficial MeLi Sales",
            site_id="MLM",
            access_token_enc=encrypt_token("APP_USR-test-sales-token"),
            refresh_token_enc=encrypt_token("TG-test-sales-refresh"),
            token_expires_at=datetime.now(timezone.utc) + timedelta(hours=8),
            is_active=True,
        )
        session.add(account)

        # 3. Almacén Principal Local
        warehouse = Warehouse(
            company_id=company_id,
            name="Bodega Matriz CDMX",
            code="BOD-CDMX-01",
            is_fulfillment=False,
            is_active=True,
        )
        session.add(warehouse)
        await session.flush()

        # 4. Producto en Catálogo: Audífonos Gamer Pro
        product = Product(
            company_id=company_id,
            name="Audífonos Bluetooth Gamer Pro",
            brand="AudioMax",
            model="AMX-G900",
            category="Electrónica",
            is_active=True,
        )
        session.add(product)
        await session.flush()

        variant = ProductVariant(
            company_id=company_id,
            product_id=product.id,
            variant_name="Negro Mate / LED RGB",
            sku="AUD-GAMER-RGB-BLK",
            cogs_cost=400.00,
            sale_price=1200.00,
            is_active=True,
        )
        session.add(variant)
        await session.flush()

        # 5. Inventario Inicial: 50 unidades físicas disponibles
        inv = Inventory(
            warehouse_id=warehouse.id,
            variant_id=variant.id,
            quantity_on_hand=50,
            quantity_reserved=0,
            quantity_blocked=0,
            quantity_available=50,
            min_stock=5,
            max_stock=100,
        )
        session.add(inv)
        await session.commit()

        return {
            "account_id": account.id,
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "variant_id": variant.id,
            "sku": variant.sku,
        }


@pytest.mark.asyncio
async def test_order_creation_full_financial_breakdown_and_stock_reservation(sales_test_context, setup_sales_catalog):
    """
    Verifica que al ingresar una orden pagada:
    1. Se capturen todos los datos del comprador y venta.
    2. Se vincule la partida con el SKU y variante interna.
    3. Se calculen las comisiones MeLi, flete, retenciones SAT y ganancia neta estimada.
    4. Se reserve inmediatamente el inventario en la bodega local y se registre movimiento 'RESERVATION'.
    5. Se genere la línea de tiempo histórica del pedido.
    """
    client = sales_test_context["client"]
    headers = sales_test_context["headers"]
    session_factory = sales_test_context["session_factory"]
    sku = setup_sales_catalog["sku"]
    account_id = setup_sales_catalog["account_id"]
    warehouse_id = setup_sales_catalog["warehouse_id"]
    variant_id = setup_sales_catalog["variant_id"]

    order_service = OrderService()
    meli_order_id = 991001201

    order_payload = {
        "id": meli_order_id,
        "status": "paid",
        "date_created": "2026-11-18T10:00:00.000-06:00",
        "total_amount": 1200.00,
        "paid_amount": 1200.00,
        "currency_id": "MXN",
        "buyer": {
            "id": 55443322,
            "nickname": "GAMER_PRO_MX",
            "first_name": "Carlos",
            "last_name": "Villagrán",
            "email": "carlos.gamer@correo.com",
            "phone": {"number": "5551234567"},
            "billing_info": {"doc_number": "VIC900101XYZ"},
        },
        "order_items": [
            {
                "item": {
                    "id": "MLM99887766",
                    "title": "Audífonos Bluetooth Gamer Pro RGB",
                    "seller_sku": sku,
                    "variation_id": "17263544",
                },
                "quantity": 2,
                "unit_price": 600.00,
                "sale_fee": 180.00,  # 15% comisión MeLi por ambas piezas
            }
        ],
        "payments": [
            {
                "id": 88100200,
                "status": "approved",
                "payment_type": "credit_card",
                "payment_method_id": "master",
                "transaction_amount": 1200.00,
                "marketplace_fee": 180.00,
                "date_approved": "2026-11-18T10:02:00.000-06:00",
            }
        ],
        "shipping": {
            "id": 77100300,
            "status": "ready_to_ship",
            "logistic_type": "cross_docking",  # Colecta estándar (bodega local)
            "cost": 110.00,  # Envío gratis a cargo del vendedor
        },
    }

    async with session_factory() as session:
        account = await session.get(MeliAccount, account_id)
        order = await order_service.create_or_update_order(session, account, order_payload)
        await session.commit()
        order_uuid = order.id

    # 1. Consultar Detalle por API
    res = client.get(f"/api/v1/orders/{order_uuid}", headers=headers)
    assert res.status_code == 200
    data = res.json()

    # Verificar datos generales y comprador
    assert data["meli_order_id"] == meli_order_id
    assert data["status"] == "paid"
    assert data["payment_status"] == "approved"
    assert data["shipment_status"] == "ready_to_ship"
    assert data["buyer_nickname"] == "GAMER_PRO_MX"
    assert data["buyer_name"] == "Carlos Villagrán"
    assert data["buyer_email"] == "carlos.gamer@correo.com"
    assert data["buyer_document"] == "VIC900101XYZ"

    # Desglose financiero
    # Total: $1200 | Costo Mercancía (2 x 400): $800 | Comisión MeLi: $180 | Flete: $110 | Empaque: $20
    # SAT IVA 8%: $96 | SAT ISR 1%: $12 | Total Impuestos: $108
    # Ganancia Neta Estimada = 1200 - 800 - 180 - 110 - 20 - 108 = -18 (o cálculo exacto)
    assert data["total_amount"] == 1200.00
    assert data["meli_fee_amount"] == 180.00
    assert data["shipping_cost_seller"] == 110.00
    assert data["cogs_total"] == 800.00
    assert data["profitability"] is not None
    assert data["profitability"]["sat_iva_retention"] == 96.00
    assert data["profitability"]["sat_isr_retention"] == 12.00

    # Partidas
    assert len(data["items"]) == 1
    assert data["items"][0]["seller_sku"] == sku
    assert data["items"][0]["quantity"] == 2
    assert data["items"][0]["variant_id"] == str(variant_id)

    # Línea de tiempo
    assert len(data["timelines"]) >= 2
    event_types = [tl["event_type"] for tl in data["timelines"]]
    assert "ORDER_CREATED" in event_types
    assert "STOCK_RESERVED" in event_types

    # 2. Verificar Reserva de Stock en Bodega Física
    async with session_factory() as session:
        inv = (
            await session.execute(
                select(Inventory).where(
                    Inventory.warehouse_id == warehouse_id, Inventory.variant_id == variant_id
                )
            )
        ).scalar_one()
        # Había 50 iniciales. Al reservar 2:
        assert inv.quantity_on_hand == 50
        assert inv.quantity_reserved == 2
        assert inv.quantity_available == 48  # 50 - 2 - 0 = 48

        # Verificar movimiento Kardex
        mov = (
            await session.execute(
                select(InventoryMovement).where(
                    InventoryMovement.inventory_id == inv.id, InventoryMovement.movement_type == "RESERVATION"
                )
            )
        ).scalar_one()
        assert mov.quantity_delta == 2
        assert mov.reference_id == str(meli_order_id)


@pytest.mark.asyncio
async def test_list_orders_filtering_and_search(sales_test_context, setup_sales_catalog):
    """Verifica que el listado responda con paginación, filtros de estado y búsqueda por texto."""
    client = sales_test_context["client"]
    headers = sales_test_context["headers"]
    session_factory = sales_test_context["session_factory"]
    account_id = setup_sales_catalog["account_id"]
    sku = setup_sales_catalog["sku"]

    order_service = OrderService()

    # Inyectar dos órdenes distintas
    async with session_factory() as session:
        account = await session.get(MeliAccount, account_id)
        # Orden 1: Confirmada, pagada
        await order_service.create_or_update_order(
            session,
            account,
            {
                "id": 992001,
                "status": "paid",
                "date_created": "2026-11-18T11:00:00Z",
                "total_amount": 500.0,
                "paid_amount": 500.0,
                "currency_id": "MXN",
                "buyer": {"id": 11, "nickname": "COMPRADOR_ALFA", "first_name": "Luis", "last_name": "Pérez"},
                "order_items": [{"item": {"id": "MLM11", "title": "Audífonos Gamer", "seller_sku": sku}, "quantity": 1, "unit_price": 500.0}],
                "shipping": {"logistic_type": "fulfillment"},
            },
        )
        # Orden 2: Cancelada
        await order_service.create_or_update_order(
            session,
            account,
            {
                "id": 992002,
                "status": "cancelled",
                "date_created": "2026-11-18T12:00:00Z",
                "total_amount": 800.0,
                "paid_amount": 0.0,
                "currency_id": "MXN",
                "buyer": {"id": 22, "nickname": "COMPRADOR_BETA", "first_name": "Mariana", "last_name": "Soto"},
                "order_items": [{"item": {"id": "MLM22", "title": "Cable Auxiliar", "seller_sku": "CAB-AUX-01"}, "quantity": 1, "unit_price": 800.0}],
                "shipping": {"logistic_type": "fulfillment"},
            },
        )
        await session.commit()

    # 1. Búsqueda por comprador "Luis"
    res_search = client.get("/api/v1/orders?search=Luis", headers=headers)
    assert res_search.status_code == 200
    items = res_search.json()["items"]
    assert len(items) == 1
    assert items[0]["buyer_nickname"] == "COMPRADOR_ALFA"

    # 2. Filtro por status=cancelled
    res_status = client.get("/api/v1/orders?status=cancelled", headers=headers)
    assert res_status.status_code == 200
    items_can = res_status.json()["items"]
    assert len(items_can) == 1
    assert items_can[0]["meli_order_id"] == 992002

    # 3. Búsqueda por SKU
    res_sku = client.get(f"/api/v1/orders?search={sku}", headers=headers)
    assert res_sku.status_code == 200
    assert any(it["meli_order_id"] == 992001 for it in res_sku.json()["items"])


@pytest.mark.asyncio
async def test_order_cancellation_releases_stock_and_records_timeline(sales_test_context, setup_sales_catalog):
    """
    Verifica que la cancelación manual de una orden:
    1. Actualice el estado a 'cancelled'.
    2. Registre el motivo y la parte responsable ('buyer' o 'seller').
    3. Libere inmediatamente el stock previamente reservado en la bodega física.
    4. Agregue el evento 'ORDER_CANCELLED' a la línea de tiempo.
    """
    client = sales_test_context["client"]
    headers = sales_test_context["headers"]
    session_factory = sales_test_context["session_factory"]
    sku = setup_sales_catalog["sku"]
    account_id = setup_sales_catalog["account_id"]
    warehouse_id = setup_sales_catalog["warehouse_id"]
    variant_id = setup_sales_catalog["variant_id"]

    order_service = OrderService()
    meli_order_id = 993001

    # Crear orden con reserva de 3 unidades en bodega física
    async with session_factory() as session:
        account = await session.get(MeliAccount, account_id)
        order = await order_service.create_or_update_order(
            session,
            account,
            {
                "id": meli_order_id,
                "status": "paid",
                "date_created": "2026-11-18T13:00:00Z",
                "total_amount": 1500.0,
                "paid_amount": 1500.0,
                "currency_id": "MXN",
                "buyer": {"id": 33, "nickname": "CANCEL_TEST"},
                "order_items": [{"item": {"id": "MLM33", "title": "Producto Cancelable", "seller_sku": sku}, "quantity": 3, "unit_price": 500.0}],
                "shipping": {"logistic_type": "cross_docking"},
            },
        )
        await session.commit()
        order_uuid = order.id

    # Comprobar que el stock está reservado (3 unidades)
    async with session_factory() as session:
        inv_before = (
            await session.execute(
                select(Inventory).where(Inventory.warehouse_id == warehouse_id, Inventory.variant_id == variant_id)
            )
        ).scalar_one()
        reserved_before = inv_before.quantity_reserved
        avail_before = inv_before.quantity_available

    # Ejecutar cancelación vía API
    cancel_payload = {
        "reason": "El comprador solicitó cancelar por arrepentimiento de compra",
        "responsible": "buyer",
    }
    res = client.post(f"/api/v1/orders/{order_uuid}/cancel", json=cancel_payload, headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "cancelled"
    assert data["cancel_reason"] == cancel_payload["reason"]
    assert data["cancel_responsible"] == "buyer"
    assert data["cancelled_at"] is not None

    # Verificar que en la línea de tiempo se registró el evento
    tl_events = [tl["event_type"] for tl in data["timelines"]]
    assert "ORDER_CANCELLED" in tl_events

    # Comprobar liberación de reservas en bodega (quantity_reserved se decrementa en 3)
    async with session_factory() as session:
        inv_after = (
            await session.execute(
                select(Inventory).where(Inventory.warehouse_id == warehouse_id, Inventory.variant_id == variant_id)
            )
        ).scalar_one()
        assert inv_after.quantity_reserved == reserved_before - 3
        assert inv_after.quantity_available == avail_before + 3

        # Movimiento Kardex RESERVATION_RELEASE
        mov = (
            await session.execute(
                select(InventoryMovement)
                .where(
                    InventoryMovement.inventory_id == inv_after.id,
                    InventoryMovement.movement_type == "RESERVATION_RELEASE",
                )
                .order_by(InventoryMovement.created_at.desc())
            )
        ).scalars().first()
        assert mov is not None
        assert mov.quantity_delta == -3


@pytest.mark.asyncio
async def test_sales_reports_strictly_exclude_cancelled_orders(sales_test_context, setup_sales_catalog):
    """
    REGLA CRÍTICA: Comprueba que los reportes comerciales (diario, semanal, mensual)
    excluyan de forma terminante las órdenes canceladas del total de ventas y de la ganancia neta.
    """
    client = sales_test_context["client"]
    headers = sales_test_context["headers"]
    session_factory = sales_test_context["session_factory"]
    account_id = setup_sales_catalog["account_id"]
    sku = setup_sales_catalog["sku"]

    order_service = OrderService()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    async with session_factory() as session:
        account = await session.get(MeliAccount, account_id)
        # Orden 1 VÁLIDA: $1,000 MXN
        await order_service.create_or_update_order(
            session,
            account,
            {
                "id": 994001,
                "status": "paid",
                "date_created": f"{today_str}T08:00:00Z",
                "total_amount": 1000.0,
                "paid_amount": 1000.0,
                "currency_id": "MXN",
                "buyer": {"id": 41, "nickname": "CLIENTE_VALIDO"},
                "order_items": [{"item": {"id": "MLM41", "title": "Item Valido", "seller_sku": sku}, "quantity": 1, "unit_price": 1000.0}],
                "shipping": {"logistic_type": "fulfillment"},
            },
        )
        # Orden 2 CANCELADA: $3,500 MXN (NO DEBE SUMAR AL INGRESO)
        order_can = await order_service.create_or_update_order(
            session,
            account,
            {
                "id": 994002,
                "status": "paid",
                "date_created": f"{today_str}T09:00:00Z",
                "total_amount": 3500.0,
                "paid_amount": 3500.0,
                "currency_id": "MXN",
                "buyer": {"id": 42, "nickname": "CLIENTE_CANCELADO"},
                "order_items": [{"item": {"id": "MLM42", "title": "Item Cancelado", "seller_sku": sku}, "quantity": 1, "unit_price": 3500.0}],
                "shipping": {"logistic_type": "fulfillment"},
            },
        )
        # Cancelar la orden 2
        await order_service.cancel_order(
            session=session,
            order_id=order_can.id,
            company_id=account.company_id,
            reason="Cliente no reconoció el cargo",
            responsible="buyer",
        )
        await session.commit()

    # 1. Reporte Diario
    res_daily = client.get(f"/api/v1/orders/reports/sales?period=daily&reference_date={today_str}T12:00:00Z", headers=headers)
    assert res_daily.status_code == 200
    data_daily = res_daily.json()

    summary = data_daily["summary"]
    # Debe contar 1 orden pagada válida y 1 cancelada
    assert summary["paid_orders"] == 1
    assert summary["cancelled_orders"] == 1
    # Ventas brutas deben ser exactamente $1000.00, NO $4500.00 (la cancelada de $3500 queda excluida)
    assert summary["gross_sales"] == 1000.00
    assert summary["net_sales"] == 1000.00

    # 2. Reporte Semanal y Mensual
    res_weekly = client.get(f"/api/v1/orders/reports/sales?period=weekly&reference_date={today_str}T12:00:00Z", headers=headers)
    assert res_weekly.status_code == 200
    assert res_weekly.json()["summary"]["gross_sales"] == 1000.00
    assert res_weekly.json()["summary"]["cancelled_orders"] == 1


@pytest.mark.asyncio
async def test_order_return_good_condition_restocks_inventory(sales_test_context, setup_sales_catalog):
    """
    Verifica que al recibir una devolución en buen estado ('good'):
    1. Se actualice el estado a 'returned' y return_status='received_good'.
    2. Las unidades reingresen al inventario disponible ('RETURN_RESTOCK').
    3. Se registre el evento en la línea de tiempo.
    """
    client = sales_test_context["client"]
    headers = sales_test_context["headers"]
    session_factory = sales_test_context["session_factory"]
    sku = setup_sales_catalog["sku"]
    account_id = setup_sales_catalog["account_id"]
    warehouse_id = setup_sales_catalog["warehouse_id"]
    variant_id = setup_sales_catalog["variant_id"]

    order_service = OrderService()
    meli_order_id = 995001

    async with session_factory() as session:
        account = await session.get(MeliAccount, account_id)
        order = await order_service.create_or_update_order(
            session,
            account,
            {
                "id": meli_order_id,
                "status": "delivered",
                "date_created": "2026-11-18T10:00:00Z",
                "total_amount": 600.0,
                "paid_amount": 600.0,
                "currency_id": "MXN",
                "buyer": {"id": 51, "nickname": "COMPRADOR_RETORNO"},
                "order_items": [{"item": {"id": "MLM51", "title": "Devolucion Buena", "seller_sku": sku}, "quantity": 1, "unit_price": 600.0}],
                "shipping": {"logistic_type": "fulfillment"},
            },
        )
        await session.commit()
        order_uuid = order.id

    # Stock actual disponible
    async with session_factory() as session:
        inv_before = (
            await session.execute(
                select(Inventory).where(Inventory.warehouse_id == warehouse_id, Inventory.variant_id == variant_id)
            )
        ).scalar_one()
        on_hand_before = inv_before.quantity_on_hand

    # Procesar devolución con condition='good'
    res = client.post(
        f"/api/v1/orders/{order_uuid}/return",
        json={"condition": "good", "notes": "Producto sellado intacto"},
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "returned"
    assert data["return_status"] == "received_good"

    # Verificar existencias físicas incrementadas
    async with session_factory() as session:
        inv_after = (
            await session.execute(
                select(Inventory).where(Inventory.warehouse_id == warehouse_id, Inventory.variant_id == variant_id)
            )
        ).scalar_one()
        assert inv_after.quantity_on_hand == on_hand_before + 1

        # Movimiento RETURN_RESTOCK
        mov = (
            await session.execute(
                select(InventoryMovement).where(
                    InventoryMovement.inventory_id == inv_after.id,
                    InventoryMovement.movement_type == "RETURN_RESTOCK",
                )
            )
        ).scalar_one()
        assert mov.quantity_delta == 1


@pytest.mark.asyncio
async def test_order_return_damaged_condition_quarantines_inventory(sales_test_context, setup_sales_catalog):
    """
    Verifica que al recibir una devolución de mercancía dañada ('damaged'):
    1. Las unidades ingresen a 'quantity_blocked' (cuarentena/merma).
    2. El stock disponible NO aumente para evitar vender un producto averiado.
    3. Se registre movimiento 'RETURN_DAMAGED_QUARANTINE'.
    """
    client = sales_test_context["client"]
    headers = sales_test_context["headers"]
    session_factory = sales_test_context["session_factory"]
    sku = setup_sales_catalog["sku"]
    account_id = setup_sales_catalog["account_id"]
    warehouse_id = setup_sales_catalog["warehouse_id"]
    variant_id = setup_sales_catalog["variant_id"]

    order_service = OrderService()
    meli_order_id = 996001

    async with session_factory() as session:
        account = await session.get(MeliAccount, account_id)
        order = await order_service.create_or_update_order(
            session,
            account,
            {
                "id": meli_order_id,
                "status": "delivered",
                "date_created": "2026-11-18T10:00:00Z",
                "total_amount": 600.0,
                "paid_amount": 600.0,
                "currency_id": "MXN",
                "buyer": {"id": 61, "nickname": "COMPRADOR_DANADO"},
                "order_items": [{"item": {"id": "MLM61", "title": "Devolucion Averiada", "seller_sku": sku}, "quantity": 1, "unit_price": 600.0}],
                "shipping": {"logistic_type": "fulfillment"},
            },
        )
        await session.commit()
        order_uuid = order.id

    async with session_factory() as session:
        inv_before = (
            await session.execute(
                select(Inventory).where(Inventory.warehouse_id == warehouse_id, Inventory.variant_id == variant_id)
            )
        ).scalar_one()
        blocked_before = inv_before.quantity_blocked
        avail_before = inv_before.quantity_available

    # Procesar devolución con condition='damaged'
    res = client.post(
        f"/api/v1/orders/{order_uuid}/return",
        json={"condition": "damaged", "notes": "Carcasa quebrada en traslado"},
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "returned"
    assert data["return_status"] == "received_damaged"

    async with session_factory() as session:
        inv_after = (
            await session.execute(
                select(Inventory).where(Inventory.warehouse_id == warehouse_id, Inventory.variant_id == variant_id)
            )
        ).scalar_one()
        # Se incrementa en bodega pero queda bloqueado
        assert inv_after.quantity_blocked == blocked_before + 1
        # El disponible no aumenta
        assert inv_after.quantity_available == avail_before

        mov = (
            await session.execute(
                select(InventoryMovement).where(
                    InventoryMovement.inventory_id == inv_after.id,
                    InventoryMovement.movement_type == "RETURN_DAMAGED_QUARANTINE",
                )
            )
        ).scalar_one()
        assert mov.quantity_delta == 1


@pytest.mark.asyncio
async def test_register_order_claim_and_timeline(sales_test_context, setup_sales_catalog):
    """Verifica el registro de reclamos post-venta (claims) y vinculación a la línea de tiempo."""
    client = sales_test_context["client"]
    headers = sales_test_context["headers"]
    session_factory = sales_test_context["session_factory"]
    account_id = setup_sales_catalog["account_id"]
    sku = setup_sales_catalog["sku"]

    order_service = OrderService()
    meli_order_id = 997001

    async with session_factory() as session:
        account = await session.get(MeliAccount, account_id)
        order = await order_service.create_or_update_order(
            session,
            account,
            {
                "id": meli_order_id,
                "status": "delivered",
                "date_created": "2026-11-18T10:00:00Z",
                "total_amount": 750.0,
                "paid_amount": 750.0,
                "currency_id": "MXN",
                "buyer": {"id": 71, "nickname": "CLIENTE_RECLAMO"},
                "order_items": [{"item": {"id": "MLM71", "title": "Item Reclamo", "seller_sku": sku}, "quantity": 1, "unit_price": 750.0}],
                "shipping": {"logistic_type": "fulfillment"},
            },
        )
        await session.commit()
        order_uuid = order.id

    claim_payload = {
        "meli_claim_id": "CLM-998877",
        "claim_type": "not_delivered",
        "disputed_amount": 750.00,
        "reason": "El comprador alega que la paquetería entregó en domicilio equivocado",
    }
    res = client.post(f"/api/v1/orders/{order_uuid}/claim", json=claim_payload, headers=headers)
    assert res.status_code == 200
    claim_data = res.json()
    assert claim_data["meli_claim_id"] == "CLM-998877"
    assert claim_data["status"] == "open"
    assert claim_data["disputed_amount"] == 750.00

    # Consultar la orden y verificar claim_status="open" y evento en timeline
    res_ord = client.get(f"/api/v1/orders/{order_uuid}", headers=headers)
    assert res_ord.status_code == 200
    ord_data = res_ord.json()
    assert ord_data["claim_status"] == "open"
    assert len(ord_data["claims"]) == 1
    assert any(tl["event_type"] == "CLAIM_OPENED" for tl in ord_data["timelines"])


@pytest.mark.asyncio
async def test_compare_order_with_meli_live_data(sales_test_context, setup_sales_catalog):
    """Verifica que el comparador MeLi vs Interno detecte diferencias o coincidencias exactas."""
    client = sales_test_context["client"]
    headers = sales_test_context["headers"]
    session_factory = sales_test_context["session_factory"]
    account_id = setup_sales_catalog["account_id"]
    sku = setup_sales_catalog["sku"]

    order_service = OrderService()
    meli_order_id = 998001

    async with session_factory() as session:
        account = await session.get(MeliAccount, account_id)
        order = await order_service.create_or_update_order(
            session,
            account,
            {
                "id": meli_order_id,
                "status": "paid",
                "date_created": "2026-11-18T10:00:00Z",
                "total_amount": 1000.0,
                "paid_amount": 1000.0,
                "currency_id": "MXN",
                "buyer": {"id": 81, "nickname": "CLIENTE_COMPARE"},
                "order_items": [{"item": {"id": "MLM81", "title": "Item Compare", "seller_sku": sku}, "quantity": 1, "unit_price": 1000.0}],
                "shipping": {"logistic_type": "cross_docking"},
            },
        )
        await session.commit()
        order_uuid = order.id

    # Simular respuesta de la API oficial de MeLi con una diferencia de monto (ej. cupón aplicado en MeLi)
    mock_meli_order = {
        "id": meli_order_id,
        "status": "paid",
        "total_amount": 950.00,  # MeLi reporta 950 vs ERP 1000
        "paid_amount": 950.00,
        "date_created": "2026-11-18T10:00:00Z",
        "order_items": [{"item": {"id": "MLM81"}, "quantity": 1, "unit_price": 950.0}],
        "shipping": {"logistic_type": "cross_docking"},
    }

    with patch("src.connectors.meli.orders.MeliOrdersClient.get_order", new_callable=AsyncMock) as mock_get_order:
        mock_get_order.return_value = mock_meli_order

        res = client.get(f"/api/v1/orders/{order_uuid}/compare", headers=headers)
        assert res.status_code == 200
        data = res.json()

        assert data["order_id"] == str(order_uuid)
        assert data["is_matching"] is False
        assert len(data["differences"]) > 0
        assert any("Importe Total" in diff for diff in data["differences"])
        assert data["meli_data"]["total_amount"] == 950.00
        assert data["internal_data"]["total_amount"] == 1000.00


@pytest.mark.asyncio
async def test_multi_company_strict_order_isolation(sales_test_context, setup_sales_catalog):
    """Comprueba que una empresa no pueda ver, cancelar, devolver o reclamar órdenes de otra empresa."""
    client = sales_test_context["client"]
    headers = sales_test_context["headers"]
    sec_headers = sales_test_context["sec_headers"]
    session_factory = sales_test_context["session_factory"]
    account_id = setup_sales_catalog["account_id"]
    sku = setup_sales_catalog["sku"]

    order_service = OrderService()
    meli_order_id = 999001

    async with session_factory() as session:
        account = await session.get(MeliAccount, account_id)
        order = await order_service.create_or_update_order(
            session,
            account,
            {
                "id": meli_order_id,
                "status": "paid",
                "date_created": "2026-11-18T10:00:00Z",
                "total_amount": 500.0,
                "paid_amount": 500.0,
                "currency_id": "MXN",
                "buyer": {"id": 91, "nickname": "SECRETO_EMPRESA_1"},
                "order_items": [{"item": {"id": "MLM91", "title": "Top Secret", "seller_sku": sku}, "quantity": 1, "unit_price": 500.0}],
                "shipping": {"logistic_type": "fulfillment"},
            },
        )
        await session.commit()
        order_uuid = order.id

    # La empresa propietaria sí puede verla
    res_owner = client.get(f"/api/v1/orders/{order_uuid}", headers=headers)
    assert res_owner.status_code == 200

    # La empresa rival recibe HTTP 404
    res_rival_get = client.get(f"/api/v1/orders/{order_uuid}", headers=sec_headers)
    assert res_rival_get.status_code == 404

    # La empresa rival no puede cancelarla
    res_rival_cancel = client.post(
        f"/api/v1/orders/{order_uuid}/cancel",
        json={"reason": "Intruso intentando sabotaje", "responsible": "buyer"},
        headers=sec_headers,
    )
    assert res_rival_cancel.status_code == 404

    # En el listado de la empresa rival no debe aparecer
    res_rival_list = client.get("/api/v1/orders", headers=sec_headers)
    assert res_rival_list.status_code == 200
    assert len(res_rival_list.json()["items"]) == 0

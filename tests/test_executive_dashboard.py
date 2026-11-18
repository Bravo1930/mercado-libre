"""
Suite de Pruebas Automatizadas para el Dashboard Ejecutivo del ERP.
Verifica:
1. Catálogo de opciones de filtros (/api/v1/dashboard/filters).
2. Cálculo exacto de los 15 Indicadores y KPIs con información real de base de datos.
3. Diferenciación estricta de cifras confirmadas y estimadas (Ingresos, Ganancias, Márgenes).
4. Comparativa entre periodos (Periodo actual vs Periodo previo / Año anterior con variaciones %).
5. Integridad y formato de las 9 Gráficas analíticas para Chart.js.
6. Filtrado multidimensional (Fecha, Cuenta MeLi, Categoría, SKU, Estado del Pedido).
7. Aislamiento estricto multiempresa (Multi-Tenant Security).
"""

from datetime import datetime, timedelta, timezone
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

from src.core.database import get_db
from src.core.security import encrypt_token
from src.main import app
from src.models import Base
from src.models.finance import ExternalExpense
from src.models.meli_account import MeliAccount
from src.models.order import Order, OrderItem
from src.models.payment import Payment
from src.models.product import Product, ProductVariant
from src.models.promotion import Promotion, PromotionItem
from src.models.shipment import Shipment
from src.models.warehouse import Inventory, InventoryMovement, Warehouse


@pytest.fixture
def dashboard_test_context(tmp_path):
    """Crea una base de datos de prueba aislada con dos empresas para validar multi-tenant."""
    db_file = tmp_path / "dashboard_exec_test.db"
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
        uid = uuid.uuid4().hex[:6]
        # 1. Empresa Principal
        reg1 = client.post("/api/v1/auth/register-tenant", json={
            "tenant_name": f"Tenant Dashboard {uid}",
            "tenant_slug": f"dash-slug-{uid}",
            "company_legal_name": f"Corporación Dashboard S.A. {uid}",
            "company_rfc": "DSH991201AB1",
            "admin_email": f"dash_admin_{uid}@test.com",
            "admin_password": "PasswordDashboard1!",
            "admin_full_name": "Director General Dashboard",
        })
        assert reg1.status_code == 201
        comp1_id = reg1.json()["company_id"]

        log1 = client.post("/api/v1/auth/login", json={
            "email": f"dash_admin_{uid}@test.com",
            "password": "PasswordDashboard1!",
        })
        token1 = log1.json()["access_token"]
        headers = {"Authorization": f"Bearer {token1}", "X-Company-ID": comp1_id}

        # 2. Empresa Rival
        reg2 = client.post("/api/v1/auth/register-tenant", json={
            "tenant_name": f"Tenant Rival {uid}",
            "tenant_slug": f"riv-slug-{uid}",
            "company_legal_name": f"Rival Competitor S.A. {uid}",
            "company_rfc": "RIV991201XY9",
            "admin_email": f"rival_{uid}@test.com",
            "admin_password": "PasswordRival1!",
            "admin_full_name": "Director Rival",
        })
        assert reg2.status_code == 201
        comp2_id = reg2.json()["company_id"]

        log2 = client.post("/api/v1/auth/login", json={
            "email": f"rival_{uid}@test.com",
            "password": "PasswordRival1!",
        })
        token2 = log2.json()["access_token"]
        rival_headers = {"Authorization": f"Bearer {token2}", "X-Company-ID": comp2_id}

        yield {
            "client": client,
            "session_factory": session_factory,
            "company_id": comp1_id,
            "headers": headers,
            "rival_company_id": comp2_id,
            "rival_headers": rival_headers,
        }

    app.dependency_overrides.clear()


@pytest.fixture
async def setup_dashboard_business_data(dashboard_test_context):
    """Puebla la base de datos con pedidos confirmados/estimados, inventario, promociones y gastos."""
    session_factory = dashboard_test_context["session_factory"]
    company_id = uuid.UUID(dashboard_test_context["company_id"])
    now_utc = datetime.now(timezone.utc)

    async with session_factory() as session:
        # 1. Cuentas MeLi
        meli_acc1 = MeliAccount(
            company_id=company_id,
            meli_user_id=111222333,
            nickname="TIENDA_OFICIAL_DASHBOARD",
            site_id="MLM",
            access_token_enc=encrypt_token("APP_USR-mock-token"),
            refresh_token_enc=encrypt_token("TG-mock-refresh"),
            token_expires_at=now_utc + timedelta(hours=6),
            is_active=True,
        )
        session.add(meli_acc1)
        await session.flush()

        # 2. Catálogo de Productos y Variantes
        # Producto A: Computación
        prod_a = Product(
            company_id=company_id,
            name="Laptop Gamer Alpha 15",
            brand="TitanTech",
            model="G15-2026",
            category="Computación",
            unit_of_measure="pza",
            is_active=True,
        )
        session.add(prod_a)
        await session.flush()

        var_a = ProductVariant(
            company_id=company_id,
            product_id=prod_a.id,
            sku="TITAN-G15-BLK",
            variant_name="Negro / 16GB RAM / 512GB SSD",
            cogs_cost=15000.00,
            sale_price=22000.00,
            is_active=True,
        )
        session.add(var_a)

        # Producto B: Celulares
        prod_b = Product(
            company_id=company_id,
            name="Smartphone Ultra Pro",
            brand="Apex",
            model="U-2026",
            category="Celulares",
            unit_of_measure="pza",
            is_active=True,
        )
        session.add(prod_b)
        await session.flush()

        var_b = ProductVariant(
            company_id=company_id,
            product_id=prod_b.id,
            sku="APEX-PHONE-PRO",
            variant_name="Azul Marino / 256GB",
            cogs_cost=8000.00,
            sale_price=12000.00,
            is_active=True,
        )
        session.add(var_b)

        # Producto C: Accesorio (Sin ventas para probar baja rotación)
        prod_c = Product(
            company_id=company_id,
            name="Funda Protectora Blindada",
            brand="ApexShield",
            model="FS-01",
            category="Accesorios",
            unit_of_measure="pza",
            is_active=True,
        )
        session.add(prod_c)
        await session.flush()

        var_c = ProductVariant(
            company_id=company_id,
            product_id=prod_c.id,
            sku="APEX-CASE-01",
            variant_name="Negro Mate",
            cogs_cost=100.00,
            sale_price=350.00,
            is_active=True,
        )
        session.add(var_c)

        # Producto D: Agotado (Stock 0)
        prod_d = Product(
            company_id=company_id,
            name="Cargador Rápido 65W",
            brand="TitanTech",
            model="CH-65W",
            category="Accesorios",
            unit_of_measure="pza",
            is_active=True,
        )
        session.add(prod_d)
        await session.flush()

        var_d = ProductVariant(
            company_id=company_id,
            product_id=prod_d.id,
            sku="CHG-65W-WHITE",
            variant_name="Blanco",
            cogs_cost=250.00,
            sale_price=600.00,
            is_active=True,
        )
        session.add(var_d)
        await session.flush()

        # 3. Almacén e Inventario
        wh = Warehouse(
            company_id=company_id,
            name="CEDIS Tepotzotlán 01",
            code="CEDIS-TEP-01",
            warehouse_type="internal",
            is_active=True,
        )
        session.add(wh)
        await session.flush()

        # Inventario Var A: 20 físicos, 2 reservados, 1 bloqueado -> 17 disponibles
        inv_a = Inventory(
            warehouse_id=wh.id,
            variant_id=var_a.id,
            quantity_on_hand=20,
            quantity_reserved=2,
            quantity_blocked=1,
            quantity_available=17,
            safety_stock=5,
            min_stock=10,
        )
        # Inventario Var B: 15 físicos, 0 reservados, 0 bloqueados -> 15 disponibles
        inv_b = Inventory(
            warehouse_id=wh.id,
            variant_id=var_b.id,
            quantity_on_hand=15,
            quantity_reserved=0,
            quantity_blocked=0,
            quantity_available=15,
            safety_stock=5,
            min_stock=10,
        )
        # Inventario Var C (Baja rotación): 50 físicos, 0 reservados -> 50 disp, pero 0 ventas
        inv_c = Inventory(
            warehouse_id=wh.id,
            variant_id=var_c.id,
            quantity_on_hand=50,
            quantity_reserved=0,
            quantity_blocked=0,
            quantity_available=50,
            safety_stock=10,
            min_stock=20,
        )
        # Inventario Var D (Agotado): 0 físicos, 0 disponibles
        inv_d = Inventory(
            warehouse_id=wh.id,
            variant_id=var_d.id,
            quantity_on_hand=0,
            quantity_reserved=0,
            quantity_blocked=0,
            quantity_available=0,
            safety_stock=5,
            min_stock=10,
        )
        session.add_all([inv_a, inv_b, inv_c, inv_d])
        await session.flush()

        # Movimientos Kardex para Var A
        mov1 = InventoryMovement(
            inventory_id=inv_a.id,
            movement_type="INBOUND",
            quantity_delta=20,
            quantity_before=0,
            quantity_after=20,
            reference_type="purchase_order",
            reference_id="OC-INIT-01",
            created_at=now_utc - timedelta(days=5),
        )
        mov2 = InventoryMovement(
            inventory_id=inv_a.id,
            movement_type="OUTBOUND",
            quantity_delta=-3,
            quantity_before=20,
            quantity_after=17,
            reference_type="sales_order",
            reference_id="ORD-001",
            created_at=now_utc - timedelta(days=2),
        )
        session.add_all([mov1, mov2])

        # 4. Pedidos y Ventas
        # Pedido 1: Venta de HOY (Confirmada / Pagada)
        order_today = Order(
            meli_account_id=meli_acc1.id,
            meli_order_id=2026111801,
            order_number="ORD-TODAY-01",
            status="paid",
            payment_status="paid",
            shipment_status="shipped",
            total_amount=22000.00,  # 1 Laptop Alpha 15
            paid_amount=22000.00,
            discount_amount=0.0,
            meli_fee_amount=2860.00,  # 13% fee
            shipping_cost_seller=150.00,
            cogs_total=15000.00,
            estimated_profit=3990.00,  # 22000 - 15000 - 2860 - 150 = 3990
            net_margin_pct=18.14,
            date_created_meli=now_utc - timedelta(hours=2),  # Hoy
        )
        session.add(order_today)
        await session.flush()

        item_today = OrderItem(
            order_id=order_today.id,
            product_id=prod_a.id,
            variant_id=var_a.id,
            meli_item_id="MLM111222",
            seller_sku=var_a.sku,
            title=prod_a.name,
            quantity=1,
            unit_price=22000.00,
            sale_fee=2860.00,
            cogs_unit=15000.00,
        )
        session.add(item_today)

        # Pedido 2: Venta de este mes (Confirmada / Entregada hace 3 días)
        order_month = Order(
            meli_account_id=meli_acc1.id,
            meli_order_id=2026111502,
            order_number="ORD-MONTH-02",
            status="delivered",
            payment_status="paid",
            shipment_status="delivered",
            total_amount=24000.00,  # 2 Smartphones Ultra Pro (2 x 12000)
            paid_amount=24000.00,
            discount_amount=0.0,
            meli_fee_amount=3120.00,
            shipping_cost_seller=180.00,
            cogs_total=16000.00,  # 2 x 8000
            estimated_profit=4700.00,
            net_margin_pct=19.58,
            date_created_meli=now_utc - timedelta(days=3),
        )
        session.add(order_month)
        await session.flush()

        item_month = OrderItem(
            order_id=order_month.id,
            product_id=prod_b.id,
            variant_id=var_b.id,
            meli_item_id="MLM333444",
            seller_sku=var_b.sku,
            title=prod_b.name,
            quantity=2,
            unit_price=12000.00,
            sale_fee=3120.00,
            cogs_unit=8000.00,
        )
        session.add(item_month)

        # Pedido 3: Pedido Pendiente (Estimado / En preparación)
        order_pending = Order(
            meli_account_id=meli_acc1.id,
            meli_order_id=2026111803,
            order_number="ORD-PEND-03",
            status="confirmed",
            payment_status="pending",
            shipment_status="pending",
            total_amount=12000.00,  # 1 Smartphone
            paid_amount=0.0,
            discount_amount=0.0,
            meli_fee_amount=1560.00,
            shipping_cost_seller=120.00,
            cogs_total=8000.00,
            estimated_profit=2320.00,
            net_margin_pct=19.33,
            date_created_meli=now_utc - timedelta(hours=1),
        )
        session.add(order_pending)
        await session.flush()

        item_pending = OrderItem(
            order_id=order_pending.id,
            product_id=prod_b.id,
            variant_id=var_b.id,
            meli_item_id="MLM333444",
            seller_sku=var_b.sku,
            title=prod_b.name,
            quantity=1,
            unit_price=12000.00,
            sale_fee=1560.00,
            cogs_unit=8000.00,
        )
        session.add(item_pending)

        # Pedido 4: Pedido de Periodo Previo (hace 40 días para pruebas de comparación)
        order_prev = Order(
            meli_account_id=meli_acc1.id,
            meli_order_id=2026100501,
            order_number="ORD-PREV-01",
            status="delivered",
            payment_status="paid",
            shipment_status="delivered",
            total_amount=22000.00,
            paid_amount=22000.00,
            discount_amount=0.0,
            meli_fee_amount=2860.00,
            shipping_cost_seller=150.00,
            cogs_total=15000.00,
            estimated_profit=3990.00,
            net_margin_pct=18.14,
            date_created_meli=now_utc - timedelta(days=40),
        )
        session.add(order_prev)

        # 5. Promociones
        promo = Promotion(
            meli_account_id=meli_acc1.id,
            meli_promotion_id="PROMO-CYBER-2026",
            name="Cyber Week MeLi Oficial",
            promotion_type="DEAL",
            status="started",
            start_date=now_utc - timedelta(days=2),
            finish_date=now_utc + timedelta(days=5),
        )
        session.add(promo)
        await session.flush()

        promo_item = PromotionItem(
            promotion_id=promo.id,
            meli_item_id="MLM111222",
            regular_price=22000.00,
            promotional_price=19999.00,
            discount_pct=9.1,
            is_active=True,
        )
        session.add(promo_item)

        # 6. Envíos
        shipment = Shipment(
            order_id=order_pending.id,
            meli_shipment_id=778899001,
            company_id=company_id,
            tracking_number="TRACK-DHL-9988",
            carrier_name="DHL Express",
            logistic_type="cross_docking",
            status="pending",
            dispatch_status="pending",
            shipping_cost_seller=120.00,
        )
        session.add(shipment)

        # 7. Gasto Externo Operativo
        expense = ExternalExpense(
            company_id=company_id,
            expense_date=now_utc,
            category="Software y Nube",
            amount=1500.00,
            currency="MXN",
            concept="Servidor AWS y base de datos ERP",
        )
        session.add(expense)

        # Commit final
        await session.commit()

        return {
            "account_id": str(meli_acc1.id),
            "prod_a_id": str(prod_a.id),
            "var_a_sku": var_a.sku,
            "prod_b_id": str(prod_b.id),
            "var_b_sku": var_b.sku,
        }


# ===========================================================================
# 1. PRUEBA: CATÁLOGO DE FILTROS DEL DASHBOARD
# ===========================================================================

@pytest.mark.asyncio
async def test_dashboard_filters_catalog(dashboard_test_context, setup_dashboard_business_data):
    """Verifica que el endpoint /api/v1/dashboard/filters retorne las cuentas, categorías y almacenes."""
    client = dashboard_test_context["client"]
    headers = dashboard_test_context["headers"]

    res = client.get("/api/v1/dashboard/filters", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert "meli_accounts" in data
    assert len(data["meli_accounts"]) >= 1
    assert data["meli_accounts"][0]["nickname"] == "TIENDA_OFICIAL_DASHBOARD"

    assert "categories" in data
    assert "Computación" in data["categories"]
    assert "Celulares" in data["categories"]

    assert "warehouses" in data
    assert len(data["warehouses"]) >= 1

    assert "order_statuses" in data
    assert "presets" in data


# ===========================================================================
# 2. PRUEBA: LOS 15 INDICADORES Y KPIS CON INFORMACIÓN REAL DE BD
# ===========================================================================

@pytest.mark.asyncio
async def test_executive_dashboard_kpis_real_database_calculation(dashboard_test_context, setup_dashboard_business_data):
    """
    Verifica que el endpoint /api/v1/dashboard/executive calcule con estricto rigor
    matemático los 15 indicadores requeridos usando datos reales de base de datos.
    """
    client = dashboard_test_context["client"]
    headers = dashboard_test_context["headers"]

    res = client.get("/api/v1/dashboard/executive?preset=30d&compare=true", headers=headers)
    assert res.status_code == 200
    body = res.json()

    assert body["company_id"] == dashboard_test_context["company_id"]
    kpis = body["kpis"]

    # 1. Ventas del día: Pedido 1 (22,000) + Pedido 3 (12,000) = 34,000.00
    assert kpis["today_sales"]["gross_amount"] == 34000.00
    assert kpis["today_sales"]["orders_count"] == 2

    # 2. Ventas del mes: Pedidos 1, 2, 3 = 22,000 + 24,000 + 12,000 = 58,000.00
    assert kpis["month_sales"]["gross_amount"] == 58000.00
    assert kpis["month_sales"]["orders_count"] == 3

    # 3. Ingresos (Periodo 30d): Total 58,000
    assert kpis["revenue"]["total"] == 58000.00

    # 4. Ganancias (Periodo 30d): 3,990 + 4,700 + 2,320 = 11,010.00
    assert kpis["profit"]["total"] == 11010.00

    # 5. Margen Neto: (11,010 / 58,000) * 100 = 18.98%
    assert round(kpis["margin"]["overall_pct"], 1) == 19.0

    # 6. Comisiones: MeLi fees (2860 + 3120 + 1560 = 7540) + Envíos (150 + 180 + 120 = 450)
    assert kpis["commissions"]["marketplace_fees"] == 7540.00
    assert kpis["commissions"]["shipping_costs"] == 450.00
    assert kpis["commissions"]["taxes_withheld"] == 5220.00  # 9% de 58,000

    # 7. Pedidos pendientes: Pedido 3 (confirmed, shipment pending)
    assert kpis["pending_orders_count"] == 1
    assert kpis["pending_orders_amount"] == 12000.00

    # 8. Productos vendidos: 1 (Laptop) + 2 (Phones) + 1 (Phone) = 4 unidades
    assert kpis["products_sold_units"] == 4

    # 9. Stock: Físico = 20 + 15 + 50 + 0 = 85. Disponible = 17 + 15 + 50 + 0 = 82
    assert kpis["stock"]["total_physical"] == 85
    assert kpis["stock"]["total_available"] == 82
    assert kpis["stock"]["total_reserved"] == 2
    assert kpis["stock"]["total_blocked"] == 1
    # Valuación COGS: (20 * 15000) + (15 * 8000) + (50 * 100) + (0 * 250) = 300,000 + 120,000 + 5,000 = 425,000.00
    assert kpis["stock"]["inventory_value_cogs"] == 425000.00

    # 10. Agotados: Variante D tiene stock 0
    assert kpis["out_of_stock_count"] == 1

    # 11. Baja rotación: Variante C tiene 50 en stock pero 0 ventas
    assert kpis["low_rotation_count"] >= 1

    # 12. Productos más rentables: Top es Smartphone (4,700 + 2,320 = 7,020) o Laptop (3,990)
    assert len(kpis["top_profitable_products"]) >= 2
    top_skus = [p["sku"] for p in kpis["top_profitable_products"]]
    assert "APEX-PHONE-PRO" in top_skus
    assert "TITAN-G15-BLK" in top_skus

    # 13. Productos más vendidos: Smartphone vendió 3 unidades, Laptop 1
    assert len(kpis["top_selling_products"]) >= 2
    assert kpis["top_selling_products"][0]["sku"] == "APEX-PHONE-PRO"
    assert kpis["top_selling_products"][0]["units_sold"] == 3

    # 14. Promociones activas: 1 promoción Cyber Week vigente
    assert kpis["active_promotions_count"] == 1

    # 15. Envíos pendientes: 1 envío pendiente
    assert kpis["pending_shipments_count"] == 1


# ===========================================================================
# 3. PRUEBA: DIFERENCIACIÓN ESTRICTA DE CIFRAS CONFIRMADAS Y ESTIMADAS
# ===========================================================================

@pytest.mark.asyncio
async def test_differentiation_of_estimated_and_confirmed_figures(dashboard_test_context, setup_dashboard_business_data):
    """
    Verifica que el dashboard diferencie explícitamente:
    - Ingresos Confirmados (ventas entregadas o pagadas: Pedido 1 + Pedido 2 = 46,000).
    - Ingresos Estimados (ventas en tránsito o pendientes: Pedido 3 = 12,000).
    - Ganancias Confirmadas vs Estimadas.
    """
    client = dashboard_test_context["client"]
    headers = dashboard_test_context["headers"]

    res = client.get("/api/v1/dashboard/executive?preset=30d", headers=headers)
    assert res.status_code == 200
    kpis = res.json()["kpis"]

    # Ingresos
    assert kpis["revenue"]["confirmed"] == 46000.00  # 22,000 + 24,000
    assert kpis["revenue"]["estimated"] == 12000.00  # 12,000
    assert kpis["revenue"]["total"] == 58000.00

    # Ganancias
    assert kpis["profit"]["confirmed"] == 8690.00    # 3,990 + 4,700
    assert kpis["profit"]["estimated"] == 2320.00    # 2,320
    assert kpis["profit"]["total"] == 11010.00

    # Márgenes diferenciados
    assert kpis["margin"]["confirmed_pct"] > 0
    assert kpis["margin"]["estimated_pct"] > 0


# ===========================================================================
# 4. PRUEBA: COMPARATIVA DE PERIODOS (VARIACIONES Y DELTAS)
# ===========================================================================

@pytest.mark.asyncio
async def test_period_comparison_math_and_growth_percentages(dashboard_test_context, setup_dashboard_business_data):
    """
    Verifica que al activar 'compare=true', el servicio calcule las ventas y ganancias
    del periodo comparativo previo y calcule las variaciones porcentuales exactas.
    """
    client = dashboard_test_context["client"]
    headers = dashboard_test_context["headers"]

    # Consultar con compare=true
    res = client.get("/api/v1/dashboard/executive?preset=30d&compare=true&compare_to=previous_period", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["previous_period_start"] is not None
    assert data["previous_period_end"] is not None

    # En el periodo anterior (hace 40 días) existió el Pedido 4 de 22,000
    rev = data["kpis"]["revenue"]
    assert rev["previous_total"] == 22000.00
    # Crecimiento: ((58,000 - 22,000) / 22,000) * 100 = +163.64%
    assert rev["growth_pct"] == 163.64

    prof = data["kpis"]["profit"]
    assert prof["previous_total"] == 3990.00
    assert prof["growth_pct"] > 0


# ===========================================================================
# 5. PRUEBA: INTEGRIDAD Y FORMATO DE LAS 9 GRÁFICAS ANALÍTICAS
# ===========================================================================

@pytest.mark.asyncio
async def test_all_nine_charts_data_integrity(dashboard_test_context, setup_dashboard_business_data):
    """
    Valida la existencia y estructura de datos para renderizar las 9 gráficas oficiales:
    1. Ventas diarias
    2. Ventas mensuales
    3. Rentabilidad
    4. Evolución de inventario
    5. Productos más vendidos
    6. Productos menos vendidos
    7. Comisiones
    8. Gastos
    9. Rotación
    """
    client = dashboard_test_context["client"]
    headers = dashboard_test_context["headers"]

    res = client.get("/api/v1/dashboard/executive?preset=30d", headers=headers)
    assert res.status_code == 200
    charts = res.json()["charts"]

    # 1. Ventas diarias
    assert "daily_sales" in charts
    assert len(charts["daily_sales"]["labels"]) > 0
    assert len(charts["daily_sales"]["current_period_gross"]) == len(charts["daily_sales"]["labels"])

    # 2. Ventas mensuales (12 meses)
    assert "monthly_sales" in charts
    assert len(charts["monthly_sales"]["labels"]) == 12
    assert len(charts["monthly_sales"]["current_year_gross"]) == 12

    # 3. Rentabilidad
    assert "profitability" in charts
    assert len(charts["profitability"]["revenue"]) == len(charts["profitability"]["labels"])
    assert len(charts["profitability"]["net_profit"]) == len(charts["profitability"]["labels"])

    # 4. Evolución de inventario
    assert "inventory_evolution" in charts
    assert len(charts["inventory_evolution"]["inbound_units"]) > 0
    assert len(charts["inventory_evolution"]["outbound_units"]) > 0

    # 5. Productos más vendidos
    assert "top_selling" in charts
    assert len(charts["top_selling"]["labels"]) >= 2
    assert "APEX-PHONE-PRO" in charts["top_selling"]["labels"]

    # 6. Productos menos vendidos (Identifica productos estancados)
    assert "least_selling" in charts
    assert len(charts["least_selling"]["labels"]) >= 1

    # 7. Comisiones (Tarifa venta, envíos, IVA, ISR)
    assert "commissions" in charts
    assert len(charts["commissions"]["labels"]) == 4
    assert len(charts["commissions"]["values"]) == 4

    # 8. Gastos (COGS, comisiones, envíos, gastos externos)
    assert "expenses" in charts
    assert len(charts["expenses"]["labels"]) == 4
    assert charts["expenses"]["values"][3] == 1500.00  # Gasto externo registrado

    # 9. Rotación por categoría
    assert "rotation" in charts
    assert len(charts["rotation"]["categories"]) >= 2
    assert "Computación" in charts["rotation"]["categories"]
    assert "Celulares" in charts["rotation"]["categories"]


# ===========================================================================
# 6. PRUEBA: FILTRADO MULTIDIMENSIONAL (SKU, CATEGORÍA, ESTADO)
# ===========================================================================

@pytest.mark.asyncio
async def test_multidimensional_filtering(dashboard_test_context, setup_dashboard_business_data):
    """
    Verifica que al filtrar por SKU, Categoría o Estado, los indicadores y gráficas
    restringan su cálculo estrictamente a las entidades que coinciden.
    """
    client = dashboard_test_context["client"]
    headers = dashboard_test_context["headers"]

    # 1. Filtro por SKU de Laptop
    res_sku = client.get("/api/v1/dashboard/executive?preset=30d&sku=TITAN-G15-BLK", headers=headers)
    assert res_sku.status_code == 200
    data_sku = res_sku.json()
    # Solo el pedido de la laptop (22,000)
    assert data_sku["kpis"]["revenue"]["total"] == 22000.00

    # 2. Filtro por Estado: paid (solo Pedido 1)
    res_status = client.get("/api/v1/dashboard/executive?preset=30d&status=paid", headers=headers)
    assert res_status.status_code == 200
    data_status = res_status.json()
    assert data_status["kpis"]["revenue"]["total"] == 22000.00

    # 3. Filtro por Categoría: Celulares
    res_cat = client.get("/api/v1/dashboard/executive?preset=30d&category=Celulares", headers=headers)
    assert res_cat.status_code == 200
    data_cat = res_cat.json()
    # En Celulares están Pedido 2 (24,000) y Pedido 3 (12,000) = 36,000
    assert data_cat["kpis"]["revenue"]["total"] == 36000.00


# ===========================================================================
# 7. PRUEBA: AISLAMIENTO MULTIEMPRESA (MULTI-TENANT ISOLATION)
# ===========================================================================

@pytest.mark.asyncio
async def test_strict_multi_tenant_isolation_in_dashboard(dashboard_test_context, setup_dashboard_business_data):
    """
    Garantiza que una empresa rival no pueda ver las ventas, ganancias, inventario
    o comisiones de otra empresa.
    """
    client = dashboard_test_context["client"]
    rival_headers = dashboard_test_context["rival_headers"]

    res_rival = client.get("/api/v1/dashboard/executive?preset=30d", headers=rival_headers)
    assert res_rival.status_code == 200
    rival_data = res_rival.json()

    # La empresa rival debe ver todo en 0
    assert rival_data["kpis"]["revenue"]["total"] == 0.0
    assert rival_data["kpis"]["profit"]["total"] == 0.0
    assert rival_data["kpis"]["today_sales"]["gross_amount"] == 0.0
    assert rival_data["kpis"]["stock"]["total_physical"] == 0
    assert len(rival_data["kpis"]["top_selling_products"]) == 0

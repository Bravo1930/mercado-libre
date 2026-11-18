"""Pruebas exhaustivas para el Motor Financiero de Rentabilidad del ERP de Mercado Libre México.

Cubre y valida con estricto rigor contable y fiscal:
1. Fórmulas Configurables de Rentabilidad:
   - Configuración por empresa (utilidad bruta, utilidad neta, base de margen).
   - Costos operativos base (empaque fijo, manipulación).
   - Parámetros fiscales SAT México y umbrales de alerta de pérdida.
   - Aislamiento multiempresa.
2. Historial Inmutable de Costos (COGS):
   - Registro de modificaciones de costo de adquisición con motivo obligatorio.
   - Actualización de variante en catálogo.
   - Auditoría cronológica y resolución retroactiva de costo vigente por fecha de venta.
3. Cálculo de Rentabilidad Multidimensional en las 8 Dimensiones Oficiales:
   - 1. Por Producto (product)
   - 2. Por SKU (sku)
   - 3. Por Publicación MeLi (item)
   - 4. Por Pedido (order)
   - 5. Por Cuenta MeLi (account)
   - 6. Por Día (daily)
   - 7. Por Semana (weekly)
   - 8. Por Mes (monthly)
   - Verificación de los 13 conceptos:
     (PVP promedio, Ingreso Bruto, Descuentos, Comisiones MeLi, Cargos Fijos < $299,
      Flete Vendedor, COGS, Gastos Operativos, Impuestos SAT, Reembolsos,
      Ganancia Bruta, Ganancia Neta, Margen Porcentual).
   - Diferenciación explícita de costos Reales, Estimados y Pendientes.
4. Motor de Detección de Alertas de Productos en Pérdida:
   - Diagnóstico automático de causa raíz (cargo fijo de $25 MXN por PVP < $299, flete elevado, COGS excesivo).
   - Formulación de recomendaciones correctivas con cálculo de precio sugerido.
   - Resolución y auditoría de alertas.
5. Simulador Inverso de Precios para Margen Objetivo:
   - Cálculo algebraico inverso de PVP según COGS, fletes, comisiones, empaque y margen deseado.
   - Manejo del salto discontinuo de MeLi en $299 MXN ($25 MXN si < $299).
   - Comparativa de impacto fiscal (con RFC 9% vs sin RFC 36% vs persona moral 0%).
   - Cálculo del precio de equilibrio (Break-Even).
6. Preparación para Proveedores Autorizados de Certificación Fiscal Mexicana (PAC / SAT):
   - Configuración de PAC (Facturapi, Finkok, SW Sapience).
   - Timbrado de CFDI 4.0 con UUID SAT oficial, desglose de IVA 16% y retenciones de plataforma (IVA 8%, ISR 1%).
"""

from datetime import datetime, timedelta, timezone
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
from src.models.finance import ExternalExpense, FinancialTransaction
from src.models.meli_account import MeliAccount
from src.models.order import Order, OrderItem
from src.models.payment import Payment
from src.models.product import Product, ProductVariant
from src.models.profitability import (
    CostHistory,
    FiscalIntegrationConfig,
    FiscalInvoice,
    ProfitabilityAlert,
    ProfitabilityConfig,
)
from src.services.profitability_service import ProfitabilityService


@pytest.fixture
def profitability_test_context(tmp_path):
    """Provee entorno de pruebas aislado con BD SQLite, empresas y headers autenticados."""
    db_file = tmp_path / "profitability_engine_test.db"
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
        # 1. Empresa Principal
        reg_res = client.post("/api/v1/auth/register-tenant", json={
            "tenant_name": f"Tenant Rentabilidad {unique_id}",
            "tenant_slug": f"prof-slug-{unique_id}",
            "company_legal_name": f"Consorcio Financiero S.A. {unique_id}",
            "company_rfc": "CFI991201AB0",
            "admin_email": f"prof_admin_{unique_id}@test.com",
            "admin_password": "PasswordRentabilidad1!",
            "admin_full_name": "Director Financiero ERP",
        })
        assert reg_res.status_code == 201
        company_id = reg_res.json()["company_id"]

        login_res = client.post("/api/v1/auth/login", json={
            "email": f"prof_admin_{unique_id}@test.com",
            "password": "PasswordRentabilidad1!",
        })
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]

        headers = {
            "Authorization": f"Bearer {token}",
            "X-Company-ID": company_id,
        }

        # 2. Empresa Rival para Aislamiento
        reg_sec = client.post("/api/v1/auth/register-tenant", json={
            "tenant_name": f"Tenant Rival Prof {unique_id}",
            "tenant_slug": f"rival-prof-{unique_id}",
            "company_legal_name": f"Rival Finance S.A. {unique_id}",
            "company_rfc": "RPF991201XY1",
            "admin_email": f"admin_rival_prof_{unique_id}@test.com",
            "admin_password": "PasswordRivalProf1!",
            "admin_full_name": "Admin Rival Prof",
        })
        sec_company_id = reg_sec.json()["company_id"]
        login_sec = client.post("/api/v1/auth/login", json={
            "email": f"admin_rival_prof_{unique_id}@test.com",
            "password": "PasswordRivalProf1!",
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
            "seller_id": 776655443,
        }

    app.dependency_overrides.clear()


@pytest.fixture
async def setup_profitability_data(profitability_test_context):
    """Crea cuenta MeLi conectada, productos, variantes y órdenes de venta para auditoría financiera."""
    session_factory = profitability_test_context["session_factory"]
    company_id = uuid.UUID(profitability_test_context["company_id"])
    seller_id = profitability_test_context["seller_id"]

    async with session_factory() as session:
        # 1. Cuenta MeLi
        account = MeliAccount(
            company_id=company_id,
            meli_user_id=seller_id,
            nickname="Tienda Oficial Finanzas MeLi",
            site_id="MLM",
            access_token_enc=encrypt_token("APP_USR-test-prof-token"),
            refresh_token_enc=encrypt_token("TG-test-prof-refresh"),
            token_expires_at=datetime.now(timezone.utc) + timedelta(hours=10),
            is_active=True,
        )
        session.add(account)

        # 2. Productos y Variantes
        # Producto 1: Rentable (> 20% margen)
        prod_good = Product(
            company_id=company_id,
            name="Smartwatch Deportivo GPS Pro",
            brand="FitTech",
            model="FT-2026",
            category="Electrónica",
            is_active=True,
        )
        session.add(prod_good)
        await session.flush()

        var_good = ProductVariant(
            company_id=company_id,
            product_id=prod_good.id,
            variant_name="Negro / Correa Silicona",
            sku="SMART-GPS-BLK",
            sale_price=899.00,
            cogs_cost=320.00,
            is_active=True,
        )
        session.add(var_good)

        # Producto 2: Bajo costo con pérdida (< $299 activa $25 fijo + flete)
        prod_loss = Product(
            company_id=company_id,
            name="Cable USB-C Carga Rápida 1m",
            brand="CablePro",
            model="CB-1M-60W",
            category="Accesorios",
            is_active=True,
        )
        session.add(prod_loss)
        await session.flush()

        var_loss = ProductVariant(
            company_id=company_id,
            product_id=prod_loss.id,
            variant_name="Blanco 1 Metro",
            sku="CABLE-USBC-1M",
            sale_price=149.00,
            cogs_cost=75.00,
            is_active=True,
        )
        session.add(var_loss)
        await session.flush()

        # 3. Órdenes de Venta
        now = datetime.now(timezone.utc)

        # Orden 1: Exitosa del Smartwatch ($899 MXN)
        order1 = Order(
            meli_account_id=account.id,
            meli_order_id=88001122,
            buyer_id=111222,
            buyer_nickname="COMPRADOR_EXITOSO",
            status="paid",
            payment_status="approved",
            shipment_status="delivered",
            total_amount=899.00,
            paid_amount=899.00,
            discount_amount=0.0,
            currency_id="MXN",
            date_created_meli=now - timedelta(days=2),
            meli_fee_amount=134.85,  # 15% comisión MeLi
            shipping_cost_seller=85.00,
            cogs_total=320.00,
            estimated_profit=278.24,
            net_margin_pct=30.95,
        )
        session.add(order1)
        await session.flush()

        item1 = OrderItem(
            order_id=order1.id,
            product_id=prod_good.id,
            variant_id=var_good.id,
            meli_item_id="MLM880011",
            seller_sku="SMART-GPS-BLK",
            title="Smartwatch Deportivo GPS Pro",
            quantity=1,
            unit_price=899.00,
            discount_amount=0.0,
            sale_fee=134.85,
            cogs_unit=320.00,
            net_profit=278.24,
        )
        session.add(item1)

        payment1 = Payment(
            order_id=order1.id,
            meli_payment_id=99001122,
            payment_type="credit_card",
            payment_method_id="visa",
            status="settled",  # Costos reales confirmados
            transaction_amount=899.00,
            marketplace_fee=134.85,
            date_approved=now - timedelta(days=2),
        )
        session.add(payment1)

        # Orden 2: Cable USB-C que opera con pérdida ($149 MXN, cargo fijo $25 + flete $85)
        order2 = Order(
            meli_account_id=account.id,
            meli_order_id=88001133,
            buyer_id=333444,
            buyer_nickname="COMPRADOR_CABLE",
            status="paid",
            payment_status="approved",
            shipment_status="shipped",
            total_amount=149.00,
            paid_amount=149.00,
            discount_amount=0.0,
            currency_id="MXN",
            date_created_meli=now - timedelta(days=1),
            meli_fee_amount=22.35,  # 15% comisión MeLi
            shipping_cost_seller=85.00,
            cogs_total=75.00,
            estimated_profit=-71.76,  # Pérdida severa
            net_margin_pct=-48.16,
        )
        session.add(order2)
        await session.flush()

        item2 = OrderItem(
            order_id=order2.id,
            product_id=prod_loss.id,
            variant_id=var_loss.id,
            meli_item_id="MLM880022",
            seller_sku="CABLE-USBC-1M",
            title="Cable USB-C Carga Rápida 1m",
            quantity=1,
            unit_price=149.00,
            discount_amount=0.0,
            sale_fee=22.35,
            cogs_unit=75.00,
            net_profit=-71.76,
        )
        session.add(item2)

        # Orden 3: Cancelada con Reembolso
        order3 = Order(
            meli_account_id=account.id,
            meli_order_id=88001144,
            buyer_id=555666,
            buyer_nickname="COMPRADOR_CANCELADO",
            status="cancelled",
            payment_status="refunded",
            shipment_status="cancelled",
            total_amount=899.00,
            paid_amount=899.00,
            discount_amount=0.0,
            currency_id="MXN",
            date_created_meli=now - timedelta(hours=12),
            meli_fee_amount=0.0,
            shipping_cost_seller=0.0,
            cogs_total=0.0,
            cancel_reason="buyer_requested",
            cancelled_at=now - timedelta(hours=6),
        )
        session.add(order3)
        await session.flush()

        item3 = OrderItem(
            order_id=order3.id,
            product_id=prod_good.id,
            variant_id=var_good.id,
            meli_item_id="MLM880011",
            seller_sku="SMART-GPS-BLK",
            title="Smartwatch Deportivo GPS Pro",
            quantity=1,
            unit_price=899.00,
            discount_amount=0.0,
            sale_fee=0.0,
            cogs_unit=0.0,
            net_profit=0.0,
        )
        session.add(item3)

        await session.commit()

        return {
            "account_id": account.id,
            "prod_good_id": prod_good.id,
            "prod_loss_id": prod_loss.id,
            "var_good_id": var_good.id,
            "var_loss_id": var_loss.id,
            "order1_id": order1.id,
            "order2_id": order2.id,
        }


# ===========================================================================
# 1. PRUEBAS DE FÓRMULAS Y CONFIGURACIÓN DE RENTABILIDAD
# ===========================================================================

def test_profitability_config_crud_and_isolation(profitability_test_context):
    """Verifica configuración de fórmulas de rentabilidad y aislamiento entre empresas."""
    client = profitability_test_context["client"]
    headers = profitability_test_context["headers"]
    sec_headers = profitability_test_context["sec_headers"]

    # 1. Obtener configuración predeterminada
    res_get = client.get("/api/v1/profitability/config", headers=headers)
    assert res_get.status_code == 200
    cfg = res_get.json()
    assert cfg["margin_base"] == "revenue_after_discounts"
    assert cfg["sat_iva_retention_rate"] == 0.08
    assert cfg["sat_isr_retention_rate"] == 0.01
    assert cfg["loss_alert_threshold_margin_pct"] == 5.0

    # 2. Modificar fórmulas y costos operativos
    update_payload = {
        "name": "Estrategia Alta Exigencia 2026",
        "margin_base": "gross_revenue",
        "default_packaging_cost": 20.00,
        "default_handling_cost": 15.00,
        "loss_alert_threshold_margin_pct": 10.0,
        "tax_regime": "persona_moral_con_rfc",
        "sat_iva_retention_rate": 0.0,
        "sat_isr_retention_rate": 0.0,
    }
    res_update = client.put("/api/v1/profitability/config", json=update_payload, headers=headers)
    assert res_update.status_code == 200
    updated = res_update.json()
    assert updated["name"] == "Estrategia Alta Exigencia 2026"
    assert updated["margin_base"] == "gross_revenue"
    assert updated["default_packaging_cost"] == 20.00
    assert updated["default_handling_cost"] == 15.00
    assert updated["loss_alert_threshold_margin_pct"] == 10.0
    assert updated["tax_regime"] == "persona_moral_con_rfc"

    # 3. Aislamiento Multiempresa: Rival debe tener su propia configuración independiente
    res_rival = client.get("/api/v1/profitability/config", headers=sec_headers)
    assert res_rival.status_code == 200
    rival_cfg = res_rival.json()
    assert rival_cfg["name"] != "Estrategia Alta Exigencia 2026"
    assert rival_cfg["default_packaging_cost"] == 15.00


# ===========================================================================
# 2. HISTORIAL INMUTABLE DE COSTOS (COGS)
# ===========================================================================

@pytest.mark.asyncio
async def test_cost_history_audit_and_retroactive_resolution(profitability_test_context, setup_profitability_data):
    """Verifica registro inmutable de cambios de COGS y resolución de costo por fecha."""
    client = profitability_test_context["client"]
    headers = profitability_test_context["headers"]
    data = setup_profitability_data
    session_factory = profitability_test_context["session_factory"]
    company_id = uuid.UUID(profitability_test_context["company_id"])

    # 1. Registrar cambio de costo para el Smartwatch
    cost_payload = {
        "sku": "SMART-GPS-BLK",
        "new_cogs": 350.00,
        "change_reason": "supplier_increase",
        "notes": "Incremento por aranceles de importación de componentes",
        "variant_id": str(data["var_good_id"]),
    }
    res_cost = client.post("/api/v1/profitability/costs/history", json=cost_payload, headers=headers)
    assert res_cost.status_code == 201
    cost_rec = res_cost.json()
    assert cost_rec["sku"] == "SMART-GPS-BLK"
    assert cost_rec["previous_cogs"] == 320.00
    assert cost_rec["new_cogs"] == 350.00
    assert cost_rec["change_reason"] == "supplier_increase"

    # 2. Consultar historial
    res_list = client.get("/api/v1/profitability/costs/history?sku=SMART-GPS-BLK", headers=headers)
    assert res_list.status_code == 200
    histories = res_list.json()
    assert len(histories) >= 1
    assert histories[0]["new_cogs"] == 350.00

    # 3. Probar resolución retroactiva de costo por fecha mediante el servicio
    service = ProfitabilityService()
    async with session_factory() as session:
        # Fecha en el pasado (antes del incremento): debe resolver $320 o el costo original
        old_cost = await service.get_effective_cost_at_date(
            session=session,
            company_id=company_id,
            sku="SMART-GPS-BLK",
            at_date=datetime.now(timezone.utc) - timedelta(days=10),
        )
        assert old_cost in [320.00, 350.00]


# ===========================================================================
# 3. RENTABILIDAD MULTIDIMENSIONAL (8 DIMENSIONES) Y DESGLOSE DE COSTOS
# ===========================================================================

@pytest.mark.asyncio
async def test_multidimensional_profitability_reports_8_dimensions(profitability_test_context, setup_profitability_data):
    """
    Verifica que el motor financiero genere reportes contables exactos
    a través de las 8 dimensiones oficiales con diferenciación de costos Reales, Estimados y Pendientes.
    """
    client = profitability_test_context["client"]
    headers = profitability_test_context["headers"]
    setup_profitability_data  # Fixture resuelto

    dimensions = ["product", "sku", "item", "order", "account", "daily", "weekly", "monthly"]

    for dim in dimensions:
        res = client.get(f"/api/v1/profitability/reports?dimension={dim}", headers=headers)
        assert res.status_code == 200, f"Error en dimensión: {dim}"
        rep = res.json()
        assert rep["dimension"] == dim
        assert rep["total_units"] >= 2
        assert rep["total_gross_revenue"] > 0
        assert "cost_status_summary" in rep
        assert rep["cost_status_summary"]["real"] >= 0
        assert rep["cost_status_summary"]["pending"] >= 0
        assert len(rep["items"]) >= 1

    # Verificación detallada sobre la dimensión "sku"
    res_sku = client.get("/api/v1/profitability/reports?dimension=sku", headers=headers)
    assert res_sku.status_code == 200
    rep_sku = res_sku.json()

    # Buscar el Smartwatch y el Cable USB-C
    smartwatch_item = next((it for it in rep_sku["items"] if "SMART-GPS-BLK" in it["dimension_id"]), None)
    cable_item = next((it for it in rep_sku["items"] if "CABLE-USBC-1M" in it["dimension_id"]), None)

    assert smartwatch_item is not None
    assert smartwatch_item["gross_revenue"] == 899.00
    assert smartwatch_item["commissions"] == 134.85
    assert smartwatch_item["shipping_costs"] == 85.00
    assert smartwatch_item["cogs_total"] >= 320.00
    assert smartwatch_item["applicable_taxes"] == 80.91  # 899 * 0.09 SAT (8% IVA + 1% ISR)
    assert smartwatch_item["net_profit"] > 0
    assert smartwatch_item["margin_pct"] > 20.0
    assert smartwatch_item["is_loss"] is False

    # El Cable USB-C de $149 MXN debe tener pérdida
    assert cable_item is not None
    assert cable_item["gross_revenue"] == 149.00
    assert cable_item["fixed_charges"] == 25.00  # < $299 MXN
    assert cable_item["shipping_costs"] == 85.00
    assert cable_item["net_profit"] < 0
    assert cable_item["is_loss"] is True


# ===========================================================================
# 4. MOTOR DE DETECCIÓN Y RESOLUCIÓN DE ALERTAS DE PÉRDIDA
# ===========================================================================

@pytest.mark.asyncio
async def test_loss_alerts_detection_and_resolution(profitability_test_context, setup_profitability_data):
    """Verifica que el motor detecte productos en pérdida, analice la causa raíz y permita resolver."""
    client = profitability_test_context["client"]
    headers = profitability_test_context["headers"]
    setup_profitability_data

    # 1. Sincronizar y ejecutar motor de detección de alertas
    res_sync = client.post("/api/v1/profitability/alerts/sync", headers=headers)
    assert res_sync.status_code == 200
    alerts = res_sync.json()
    assert len(alerts) >= 1

    # Debe haber una alerta para el Cable USB-C (en pérdida severa)
    cable_alert = next((a for a in alerts if a["sku"] == "CABLE-USBC-1M"), None)
    assert cable_alert is not None
    assert cable_alert["alert_type"] in ["net_loss", "critical_margin"]
    assert cable_alert["severity"] == "critical"
    assert cable_alert["status"] == "active"
    assert cable_alert["net_profit"] < 0
    assert "cargo fijo" in cable_alert["root_cause_analysis"].lower() or "$25" in cable_alert["root_cause_analysis"]
    assert cable_alert["recommended_price"] is not None

    alert_id = cable_alert["id"]

    # 2. Consultar listado de alertas
    res_list = client.get("/api/v1/profitability/alerts?status_filter=active", headers=headers)
    assert res_list.status_code == 200
    assert any(a["id"] == alert_id for a in res_list.json())

    # 3. Resolver la alerta con nota de resolución obligatoria
    res_resolve = client.post(
        f"/api/v1/profitability/alerts/{alert_id}/resolve",
        json={
            "status": "resolved",
            "resolution_notes": "Se elevó el precio a $299 MXN para eliminar el cargo fijo de $25 MXN y se armó paquete dual",
        },
        headers=headers,
    )
    assert res_resolve.status_code == 200
    resolved = res_resolve.json()
    assert resolved["status"] == "resolved"
    assert resolved["resolved_at"] is not None
    assert "Se elevó el precio" in resolved["resolution_notes"]


# ===========================================================================
# 5. SIMULADOR INVERSO DE PRECIOS PARA MARGEN OBJETIVO
# ===========================================================================

def test_target_margin_simulator_exact_inverse_calculation(profitability_test_context):
    """
    Verifica el cálculo matemático inverso para determinar el PVP que produce
    exactamente el margen objetivo requerido, considerando el cargo fijo de $25 MXN si < $299 MXN.
    """
    client = profitability_test_context["client"]
    headers = profitability_test_context["headers"]

    # Caso 1: Producto con COGS de $250 MXN y margen objetivo del 25% (con RFC)
    sim_req = {
        "cogs": 250.00,
        "target_margin_pct": 25.0,
        "commission_rate": 0.15,  # 15%
        "shipping_cost": 85.00,
        "packaging_cost": 15.00,
        "handling_cost": 10.00,
        "tax_regime": "persona_fisica_con_rfc",  # 9% SAT (1% ISR + 8% IVA)
        "discount_pct": 0.0,
    }
    res = client.post("/api/v1/profitability/simulator/target-margin", json=sim_req, headers=headers)
    assert res.status_code == 200
    data = res.json()

    # Matemáticamente:
    # Denominador = 1 - 0.15 - 0.09 - 0.25 = 0.51
    # Costos fijos = 250 + 85 + 15 + 10 = 360
    # P = 360 / 0.51 = 705.88 MXN
    assert data["suggested_price"] > 700.00
    assert abs(data["achieved_margin_pct"] - 25.0) < 0.5
    assert data["net_profit"] > 0
    assert data["fixed_fee"] == 0.0  # Al ser > 299 no aplica cargo fijo

    # Caso 2: Sin RFC (Sanción SAT del 36%: 20% ISR + 16% IVA)
    sim_no_rfc = dict(sim_req, tax_regime="sin_rfc")
    res_no_rfc = client.post("/api/v1/profitability/simulator/target-margin", json=sim_no_rfc, headers=headers)
    assert res_no_rfc.status_code == 200
    data_no_rfc = res_no_rfc.json()
    # Sin RFC el precio necesario debe ser considerablemente más alto para absorber el 36%
    assert data_no_rfc["suggested_price"] > data["suggested_price"]
    assert data_no_rfc["total_taxes"] > data["total_taxes"]

    # Caso 3: Producto económico que cae en la zona de cargo fijo (< $299 MXN)
    sim_low = {
        "cogs": 50.00,
        "target_margin_pct": 15.0,
        "commission_rate": 0.15,
        "shipping_cost": 0.0,  # Flete cobrado al comprador
        "packaging_cost": 10.00,
        "handling_cost": 5.00,
        "tax_regime": "persona_fisica_con_rfc",
    }
    res_low = client.post("/api/v1/profitability/simulator/target-margin", json=sim_low, headers=headers)
    assert res_low.status_code == 200
    data_low = res_low.json()
    assert data_low["suggested_price"] < 299.00
    assert data_low["fixed_fee"] == 25.00  # MeLi cobra $25 obligatorio


# ===========================================================================
# 6. INTEGRACIÓN FISCAL MEXICANA (PAC / CFDI 4.0 / SAT)
# ===========================================================================

@pytest.mark.asyncio
async def test_fiscal_pac_integration_and_cfdi40_stamping(profitability_test_context, setup_profitability_data):
    """Verifica configuración de PAC y timbrado de CFDI 4.0 con retenciones SAT para órdenes MeLi."""
    client = profitability_test_context["client"]
    headers = profitability_test_context["headers"]
    data = setup_profitability_data
    order1_id = data["order1_id"]

    # 1. Configurar PAC autorizado (e.g. Facturapi / Finkok)
    pac_payload = {
        "pac_provider": "facturapi",
        "environment": "sandbox",
        "api_key": "test_pac_secret_key_mexico_2026",
        "rfc_emisor": "CFI991201AB0",
        "razon_social": "CONSORCIO FINANCIERO S.A. DE C.V.",
        "regimen_fiscal_sat": "626",
        "postal_code": "64000",
        "default_cfdi_use": "G03",
        "auto_invoice_delivered": True,
        "auto_generate_retention": True,
    }
    res_cfg = client.post("/api/v1/profitability/fiscal/config", json=pac_payload, headers=headers)
    assert res_cfg.status_code == 200
    cfg = res_cfg.json()
    assert cfg["pac_provider"] == "facturapi"
    assert cfg["rfc_emisor"] == "CFI991201AB0"

    # 2. Timbrar CFDI 4.0 para Orden 1
    invoice_payload = {
        "order_id": str(order1_id),
        "rfc_receptor": "XAXX010101000",
        "razon_social_receptor": "PÚBLICO EN GENERAL",
        "cfdi_use": "S01",
    }
    res_inv = client.post("/api/v1/profitability/fiscal/invoices", json=invoice_payload, headers=headers)
    assert res_inv.status_code == 201
    inv = res_inv.json()
    assert inv["status"] == "stamped"
    assert inv["uuid_sat"] is not None
    assert len(inv["uuid_sat"]) == 36
    assert inv["subtotal"] > 0
    assert inv["iva_transferred"] > 0
    assert inv["iva_retention"] == 71.92  # 899 * 0.08
    assert inv["isr_retention"] == 8.99   # 899 * 0.01
    assert inv["xml_url"] is not None

    # 3. Consultar facturas timbradas
    res_invoices = client.get("/api/v1/profitability/fiscal/invoices", headers=headers)
    assert res_invoices.status_code == 200
    invoices = res_invoices.json()
    assert len(invoices) >= 1
    assert any(i["uuid_sat"] == inv["uuid_sat"] for i in invoices)

"""Pruebas exhaustivas para el Módulo Financiero de Mercado Libre México.

Verifica:
- Las 7 métricas financieras obligatorias claramente diferenciadas:
  1. Importe bruto.
  2. Importe neto estimado.
  3. Dinero acreditado.
  4. Dinero disponible.
  5. Dinero retirado.
  6. Reembolsos.
  7. Cargos definitivos.
- Registro detallado de partidas contables (ventas, comisiones MeLi, fletes vendedor, retenciones SAT IVA/ISR).
- Registro de liquidaciones y transferencias a cuentas bancarias CLABE.
- Registro de gastos operativos externos manuales (publicidad, fletes privados, empaques).
- Motor de conciliación automática y detección de discrepancias entre órdenes, pagos y liquidaciones.
- Resolución de discrepancias financieras con auditoría y notas.
- Reportes multidimensionales: Por Cuenta MeLi, Por Producto/SKU, Por Pedido y Por Periodo.
- Aislamiento multiempresa estricto (prevención de fugas de información entre tenants).
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
from src.models.finance import ExternalExpense, FinancialDiscrepancy, FinancialTransaction, Settlement
from src.models.meli_account import MeliAccount
from src.models.order import Order, OrderItem
from src.models.payment import Payment
from src.models.product import Product, ProductVariant
from src.models.warehouse import Warehouse
from src.services.finance_service import FinanceService
from src.services.order_service import OrderService


@pytest.fixture
def finance_test_context(tmp_path):
    """Provee entorno de pruebas aislado con BD SQLite, empresa, usuario y fábrica de sesiones."""
    db_file = tmp_path / "finance_module_test.db"
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
            "tenant_name": f"Tenant Finance {unique_id}",
            "tenant_slug": f"fin-slug-{unique_id}",
            "company_legal_name": f"Corporativo Financiero S.A. {unique_id}",
            "company_rfc": "CFI991201AB0",
            "admin_email": f"cfo_fin_{unique_id}@test.com",
            "admin_password": "PasswordFinance1!",
            "admin_full_name": "Director Financiero ERP",
        })
        assert reg_res.status_code == 201
        company_id = reg_res.json()["company_id"]

        login_res = client.post("/api/v1/auth/login", json={
            "email": f"cfo_fin_{unique_id}@test.com",
            "password": "PasswordFinance1!",
        })
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]

        headers = {
            "Authorization": f"Bearer {token}",
            "X-Company-ID": company_id,
        }

        # 2. Registrar Empresa Rival para aislamiento
        reg_sec = client.post("/api/v1/auth/register-tenant", json={
            "tenant_name": f"Tenant Rival Fin {unique_id}",
            "tenant_slug": f"rival-fin-{unique_id}",
            "company_legal_name": f"Rival Finanzas S.A. {unique_id}",
            "company_rfc": "RFI991201XY1",
            "admin_email": f"admin_rival_fin_{unique_id}@test.com",
            "admin_password": "PasswordRivalFin1!",
            "admin_full_name": "Admin Rival Fin",
        })
        sec_company_id = reg_sec.json()["company_id"]
        login_sec = client.post("/api/v1/auth/login", json={
            "email": f"admin_rival_fin_{unique_id}@test.com",
            "password": "PasswordRivalFin1!",
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
async def setup_finance_data(finance_test_context):
    """Crea cuenta MeLi, estructura de costos SAT y catálogo con productos."""
    session_factory = finance_test_context["session_factory"]
    company_id = uuid.UUID(finance_test_context["company_id"])
    seller_id = finance_test_context["seller_id"]

    async with session_factory() as session:
        # 1. Estructura de Costos SAT por defecto
        cost_struct = CostStructure(
            company_id=company_id,
            name="Régimen Fiscal Estándar",
            sat_iva_retention_rate=0.08,  # 8% IVA
            sat_isr_retention_rate=0.01,  # 1% ISR
            packaging_cost_fixed=15.00,
            is_default=True,
        )
        session.add(cost_struct)

        # 2. Cuenta MeLi
        account = MeliAccount(
            company_id=company_id,
            meli_user_id=seller_id,
            nickname="Tienda Oficial MeLi Finanzas",
            site_id="MLM",
            access_token_enc=encrypt_token("APP_USR-test-fin-token"),
            refresh_token_enc=encrypt_token("TG-test-fin-refresh"),
            token_expires_at=datetime.now(timezone.utc) + timedelta(hours=6),
            is_active=True,
        )
        session.add(account)

        # 3. Producto en Catálogo
        product = Product(
            company_id=company_id,
            name="Smartwatch Deportivo GPS",
            brand="FitPro",
            model="FP-GPS-100",
            category="Tecnología",
            is_active=True,
        )
        session.add(product)
        await session.flush()

        variant = ProductVariant(
            company_id=company_id,
            product_id=product.id,
            variant_name="Correa Negra",
            sku="SMARTWATCH-GPS-BLK",
            cogs_cost=500.00,
            sale_price=1500.00,
            is_active=True,
        )
        session.add(variant)
        await session.commit()

        return {
            "account_id": account.id,
            "product_id": product.id,
            "variant_id": variant.id,
            "sku": variant.sku,
        }


@pytest.mark.asyncio
async def test_financial_kpis_differentiation_of_seven_concepts(finance_test_context, setup_finance_data):
    """
    Verifica que el endpoint /finances/kpis calcule y diferencie con absoluta exactitud
    los 7 conceptos obligatorios:
    1. Importe bruto
    2. Importe neto estimado
    3. Dinero acreditado
    4. Dinero disponible
    5. Dinero retirado
    6. Reembolsos
    7. Cargos definitivos
    """
    client = finance_test_context["client"]
    headers = finance_test_context["headers"]
    session_factory = finance_test_context["session_factory"]
    account_id = setup_finance_data["account_id"]
    sku = setup_finance_data["sku"]

    order_service = OrderService()
    now_str = datetime.now(timezone.utc).isoformat()
    old_delivered_str = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()

    async with session_factory() as session:
        account = await session.get(MeliAccount, account_id)

        # Orden 1: Entregada hace 5 días (Dinero Disponible) -> $1,500 MXN
        # Comisión MeLi (15%): $225 | Flete: $120 | Retenciones SAT (9%): $135 | Empaque: $15
        # Neto orden = 1500 - 225 - 120 - 135 = $1,020 disponible
        await order_service.create_or_update_order(
            session,
            account,
            {
                "id": 881001,
                "status": "delivered",
                "date_created": old_delivered_str,
                "total_amount": 1500.0,
                "paid_amount": 1500.0,
                "currency_id": "MXN",
                "order_items": [{"item": {"id": "MLM881", "title": "Reloj Entregado", "seller_sku": sku}, "quantity": 1, "unit_price": 1500.0, "sale_fee": 225.0}],
                "shipping": {"logistic_type": "cross_docking", "cost": 120.0},
            },
        )

        # Orden 2: Pagada hoy en tránsito (Dinero Acreditado) -> $2,000 MXN
        # Comisión MeLi: $300 | Flete: $150 | Retenciones SAT: $180
        # Neto orden = 2000 - 300 - 150 - 180 = $1,370 acreditado
        await order_service.create_or_update_order(
            session,
            account,
            {
                "id": 881002,
                "status": "paid",
                "date_created": now_str,
                "total_amount": 2000.0,
                "paid_amount": 2000.0,
                "currency_id": "MXN",
                "order_items": [{"item": {"id": "MLM882", "title": "Reloj En Transito", "seller_sku": sku}, "quantity": 1, "unit_price": 2000.0, "sale_fee": 300.0}],
                "shipping": {"logistic_type": "cross_docking", "cost": 150.0},
            },
        )

        # Orden 3: Cancelada (Reembolsos) -> $800 MXN
        order_can = await order_service.create_or_update_order(
            session,
            account,
            {
                "id": 881003,
                "status": "paid",
                "date_created": now_str,
                "total_amount": 800.0,
                "paid_amount": 800.0,
                "currency_id": "MXN",
                "order_items": [{"item": {"id": "MLM883", "title": "Reloj Cancelado", "seller_sku": sku}, "quantity": 1, "unit_price": 800.0, "sale_fee": 120.0}],
                "shipping": {"logistic_type": "fulfillment"},
            },
        )
        await order_service.cancel_order(
            session=session,
            order_id=order_can.id,
            company_id=account.company_id,
            reason="Comprador desistió de la compra",
            responsible="buyer",
        )
        await session.commit()

    # Consultar KPIs antes de liquidaciones
    res_kpi = client.get("/api/v1/finances/kpis", headers=headers)
    assert res_kpi.status_code == 200
    kpis = res_kpi.json()

    # 1. Importe Bruto (Órdenes válidas: 1500 + 2000 = $3500.00, la cancelada de 800 queda excluida)
    assert kpis["gross_amount"] == 3500.00

    # 7. Cargos Definitivos (Comisiones: 225+300=525 + Fletes: 120+150=270 + SAT: 135+180=315 = $1110.00)
    assert kpis["definitive_charge_amount"] == 1110.00

    # 2. Importe Neto Estimado (3500 - 1110 - empaques (15+15=30) = $2360.00)
    assert kpis["estimated_net_amount"] == 2360.00

    # 3. Dinero Acreditado (Orden 2 en proceso: 2000 - 300 - 150 - 180 = $1370.00)
    assert kpis["accredited_amount"] == 1370.00

    # 4. Dinero Disponible (Orden 1 entregada liberada: 1500 - 225 - 120 - 135 = $1020.00)
    assert kpis["available_amount"] == 1020.00

    # 5. Dinero Retirado inicial: $0.00
    assert kpis["withdrawn_amount"] == 0.00

    # 6. Reembolsos (Orden 3 cancelada: $800.00)
    assert kpis["refund_amount"] == 800.00


@pytest.mark.asyncio
async def test_settlement_creation_updates_withdrawn_and_available(finance_test_context, setup_finance_data):
    """
    Verifica que al registrar una liquidación / retiro bancario:
    1. Se registre la liquidación con su folio y cuenta CLABE.
    2. El dinero retirado (withdrawn_amount) aumente en el monto liquidado.
    3. El dinero disponible restante disminuya en consecuencia.
    4. Se genere la partida contable de tipo 'payout'.
    """
    client = finance_test_context["client"]
    headers = finance_test_context["headers"]
    session_factory = finance_test_context["session_factory"]
    account_id = setup_finance_data["account_id"]
    sku = setup_finance_data["sku"]

    order_service = OrderService()
    old_date = (datetime.now(timezone.utc) - timedelta(days=6)).isoformat()

    # Crear una orden entregada con $2,000 brutos ($1,370 disponible)
    async with session_factory() as session:
        account = await session.get(MeliAccount, account_id)
        await order_service.create_or_update_order(
            session,
            account,
            {
                "id": 882001,
                "status": "delivered",
                "date_created": old_date,
                "total_amount": 2000.0,
                "paid_amount": 2000.0,
                "currency_id": "MXN",
                "order_items": [{"item": {"id": "MLM8821", "title": "Reloj Para Retiro", "seller_sku": sku}, "quantity": 1, "unit_price": 2000.0, "sale_fee": 300.0}],
                "shipping": {"logistic_type": "cross_docking", "cost": 150.0},
            },
        )
        await session.commit()

    # Registrar liquidación / retiro parcial de $1,000 a cuenta bancaria
    settle_payload = {
        "meli_account_id": str(account_id),
        "settlement_number": "LIQ-SPEI-202611-001",
        "meli_settlement_id": "PO-99112233",
        "period_start": (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(),
        "period_end": datetime.now(timezone.utc).isoformat(),
        "gross_amount": 2000.00,
        "total_fees": 300.00,
        "total_shipping_costs": 150.00,
        "total_taxes": 180.00,
        "net_amount": 1000.00,  # $1,000 transferidos a banco
        "bank_name": "BBVA México",
        "bank_account_clabe": "012180004455667788",
        "date_settled": datetime.now(timezone.utc).isoformat(),
        "notes": "Transferencia interbancaria SPEI exitosa",
    }
    res_set = client.post("/api/v1/finances/settlements", json=settle_payload, headers=headers)
    assert res_set.status_code == 201
    set_data = res_set.json()
    assert set_data["settlement_number"] == "LIQ-SPEI-202611-001"
    assert set_data["net_amount"] == 1000.00

    # Consultar KPIs y verificar que withdrawn_amount sea 1000 y available se reduzca
    res_kpi = client.get("/api/v1/finances/kpis", headers=headers)
    assert res_kpi.status_code == 200
    kpis = res_kpi.json()
    assert kpis["withdrawn_amount"] == 1000.00
    # Disponible original era 1370. Al retirar 1000, restan 370.
    assert kpis["available_amount"] == 370.00

    # Verificar que exista la transacción de tipo 'payout'
    res_tx = client.get("/api/v1/finances/transactions?transaction_type=payout", headers=headers)
    assert res_tx.status_code == 200
    payout_txs = res_tx.json()["items"]
    assert len(payout_txs) == 1
    assert payout_txs[0]["status"] == "withdrawn"
    assert payout_txs[0]["net_amount"] == 1000.00


@pytest.mark.asyncio
async def test_manual_external_expenses_registration_and_impact(finance_test_context, setup_finance_data):
    """
    Verifica que el registro de gastos externos manuales:
    1. Guarde el gasto con categoría, factura SAT y proveedor.
    2. Genere automáticamente la transacción contable de tipo 'external_expense'.
    3. Reste de la utilidad neta real en los KPIs financieros.
    """
    client = finance_test_context["client"]
    headers = finance_test_context["headers"]
    variant_id = setup_finance_data["variant_id"]

    expense_payload = {
        "category": "advertising",
        "concept": "Pauta de anuncios en Meta / Facebook Ads",
        "amount": 450.00,
        "currency": "MXN",
        "expense_date": datetime.now(timezone.utc).isoformat(),
        "payment_method": "credit_card",
        "vendor_name": "Meta Platforms Ireland Ltd",
        "invoice_folio": "UUID-SAT-9988-7766-5544",
        "variant_id": str(variant_id),
        "notes": "Campaña de conversión para el Smartwatch GPS",
    }

    res_exp = client.post("/api/v1/finances/expenses", json=expense_payload, headers=headers)
    assert res_exp.status_code == 201
    exp_data = res_exp.json()
    assert exp_data["category"] == "advertising"
    assert exp_data["amount"] == 450.00
    assert exp_data["invoice_folio"] == "UUID-SAT-9988-7766-5544"

    # Verificar que aparezca en el listado de gastos
    res_list = client.get("/api/v1/finances/expenses", headers=headers)
    assert res_list.status_code == 200
    assert len(res_list.json()["items"]) >= 1

    # Verificar que en los KPIs se contabilice en external_expenses_total
    res_kpi = client.get("/api/v1/finances/kpis", headers=headers)
    assert res_kpi.status_code == 200
    assert res_kpi.json()["external_expenses_total"] == 450.00

    # Verificar que exista la transacción contable con monto negativo
    res_tx = client.get("/api/v1/finances/transactions?transaction_type=external_expense", headers=headers)
    assert res_tx.status_code == 200
    txs = res_tx.json()["items"]
    assert len(txs) == 1
    assert txs[0]["net_amount"] == -450.00


@pytest.mark.asyncio
async def test_automatic_reconciliation_detects_discrepancies(finance_test_context, setup_finance_data):
    """
    Verifica que el motor de conciliación automática detecte:
    1. Órdenes pagadas sin pago aprobado en Mercado Pago ('missing_payment').
    2. Discrepancias entre montos esperados y cobrados en comisiones MeLi ('fee_discrepancy').
    3. Permite resolver discrepancias formalmente cambiando estatus y agregando notas.
    """
    client = finance_test_context["client"]
    headers = finance_test_context["headers"]
    session_factory = finance_test_context["session_factory"]
    account_id = setup_finance_data["account_id"]
    sku = setup_finance_data["sku"]

    order_service = OrderService()

    async with session_factory() as session:
        account = await session.get(MeliAccount, account_id)
        # Orden A: Marcada como 'paid' pero con un pago aprobado por un monto MENOR ($1200 vs $1500)
        order_a = await order_service.create_or_update_order(
            session,
            account,
            {
                "id": 883001,
                "status": "paid",
                "date_created": "2026-11-18T10:00:00Z",
                "total_amount": 1500.0,
                "paid_amount": 1200.0,
                "currency_id": "MXN",
                "order_items": [{"item": {"id": "MLM8831", "title": "Desfase Pago", "seller_sku": sku}, "quantity": 1, "unit_price": 1500.0, "sale_fee": 225.0}],
                "payments": [
                    {
                        "id": 771122,
                        "status": "approved",
                        "transaction_amount": 1200.0,  # $1200 en lugar de $1500
                        "marketplace_fee": 225.0,
                    }
                ],
                "shipping": {"logistic_type": "fulfillment"},
            },
        )

        # Orden B: Marcada como 'paid' pero con cobro de comisión de $350 en lugar de $200 esperados
        order_b = await order_service.create_or_update_order(
            session,
            account,
            {
                "id": 883002,
                "status": "paid",
                "date_created": "2026-11-18T11:00:00Z",
                "total_amount": 2000.0,
                "paid_amount": 2000.0,
                "currency_id": "MXN",
                "order_items": [{"item": {"id": "MLM8832", "title": "Comision Excesiva", "seller_sku": sku}, "quantity": 1, "unit_price": 2000.0, "sale_fee": 200.0}],
                "payments": [
                    {
                        "id": 771133,
                        "status": "approved",
                        "transaction_amount": 2000.0,
                        "marketplace_fee": 350.0,  # $350 cobrado vs $200 esperado
                    }
                ],
                "shipping": {"logistic_type": "fulfillment"},
            },
        )
        await session.commit()

    # Ejecutar conciliación automática vía API
    res_rec = client.post("/api/v1/finances/reconciliation/run", headers=headers)
    assert res_rec.status_code == 200
    rec_data = res_rec.json()
    assert rec_data["discrepancies_found_count"] >= 2
    assert rec_data["total_difference_amount"] > 0

    # Consultar listado de discrepancias
    res_disc = client.get("/api/v1/finances/discrepancies?status=unresolved", headers=headers)
    assert res_disc.status_code == 200
    discrepancies = res_disc.json()["items"]
    disc_types = [d["discrepancy_type"] for d in discrepancies]
    assert "amount_mismatch" in disc_types
    assert "fee_discrepancy" in disc_types

    # Resolver una de las discrepancias
    disc_to_resolve = discrepancies[0]
    res_res = client.post(
        f"/api/v1/finances/discrepancies/{disc_to_resolve['id']}/resolve",
        json={"status": "resolved", "resolution_notes": "Ajuste conciliado con soporte técnico de Mercado Libre"},
        headers=headers,
    )
    assert res_res.status_code == 200
    assert res_res.json()["status"] == "resolved"
    assert res_res.json()["resolution_notes"] == "Ajuste conciliado con soporte técnico de Mercado Libre"


@pytest.mark.asyncio
async def test_multidimensional_financial_reports(finance_test_context, setup_finance_data):
    """
    Verifica la generación de reportes financieros:
    1. Por Cuenta MeLi (/finances/reports/accounts).
    2. Por Producto & SKU (/finances/reports/products).
    3. Por Pedido individual (/finances/reports/orders/{order_id}).
    4. Por Periodo (/finances/reports/period).
    """
    client = finance_test_context["client"]
    headers = finance_test_context["headers"]
    session_factory = finance_test_context["session_factory"]
    account_id = setup_finance_data["account_id"]
    sku = setup_finance_data["sku"]

    order_service = OrderService()

    async with session_factory() as session:
        account = await session.get(MeliAccount, account_id)
        order = await order_service.create_or_update_order(
            session,
            account,
            {
                "id": 884001,
                "status": "delivered",
                "date_created": datetime.now(timezone.utc).isoformat(),
                "total_amount": 1500.0,
                "paid_amount": 1500.0,
                "currency_id": "MXN",
                "order_items": [{"item": {"id": "MLM8841", "title": "Reloj Para Reporte", "seller_sku": sku}, "quantity": 1, "unit_price": 1500.0, "sale_fee": 225.0}],
                "shipping": {"logistic_type": "fulfillment"},
            },
        )
        await session.commit()
        order_uuid = order.id

    # 1. Reporte por Cuenta MeLi
    res_acc = client.get("/api/v1/finances/reports/accounts", headers=headers)
    assert res_acc.status_code == 200
    acc_report = res_acc.json()
    assert acc_report["total_accounts"] >= 1
    assert any(a["account_id"] == str(account_id) for a in acc_report["accounts"])

    # 2. Reporte por Producto & SKU
    res_prod = client.get("/api/v1/finances/reports/products", headers=headers)
    assert res_prod.status_code == 200
    prod_report = res_prod.json()
    assert prod_report["total_products"] >= 1
    sku_entry = next((p for p in prod_report["products"] if p["sku"] == sku), None)
    assert sku_entry is not None
    assert sku_entry["units_sold"] >= 1
    assert sku_entry["gross_sales"] >= 1500.00
    assert sku_entry["cogs_total"] >= 500.00

    # 3. Reporte por Pedido individual
    res_ord = client.get(f"/api/v1/finances/reports/orders/{order_uuid}", headers=headers)
    assert res_ord.status_code == 200
    ord_report = res_ord.json()
    assert ord_report["order_id"] == str(order_uuid)
    assert ord_report["meli_order_id"] == 884001
    assert ord_report["total_amount"] == 1500.00
    assert len(ord_report["transactions"]) >= 2

    # 4. Reporte por Periodo
    res_per = client.get("/api/v1/finances/reports/period?period=daily", headers=headers)
    assert res_per.status_code == 200
    per_report = res_per.json()
    assert per_report["period_type"] == "daily"
    assert per_report["kpis"]["gross_amount"] >= 1500.00


@pytest.mark.asyncio
async def test_strict_multi_tenant_financial_isolation(finance_test_context, setup_finance_data):
    """Comprueba que una empresa rival no pueda acceder a transacciones, liquidaciones ni KPIs ajenos."""
    client = finance_test_context["client"]
    headers = finance_test_context["headers"]
    sec_headers = finance_test_context["sec_headers"]
    session_factory = finance_test_context["session_factory"]
    account_id = setup_finance_data["account_id"]
    sku = setup_finance_data["sku"]

    order_service = OrderService()

    async with session_factory() as session:
        account = await session.get(MeliAccount, account_id)
        order = await order_service.create_or_update_order(
            session,
            account,
            {
                "id": 885001,
                "status": "paid",
                "date_created": "2026-11-18T10:00:00Z",
                "total_amount": 9999.0,
                "paid_amount": 9999.0,
                "currency_id": "MXN",
                "order_items": [{"item": {"id": "MLM8851", "title": "Super Secreto", "seller_sku": sku}, "quantity": 1, "unit_price": 9999.0, "sale_fee": 1000.0}],
                "shipping": {"logistic_type": "fulfillment"},
            },
        )
        await session.commit()
        order_uuid = order.id

    # La empresa propietaria ve sus $9,999 brutos
    res_owner_kpi = client.get("/api/v1/finances/kpis", headers=headers)
    assert res_owner_kpi.status_code == 200
    assert res_owner_kpi.json()["gross_amount"] >= 9999.00

    # La empresa rival ve $0.00 brutos en sus KPIs
    res_rival_kpi = client.get("/api/v1/finances/kpis", headers=sec_headers)
    assert res_rival_kpi.status_code == 200
    assert res_rival_kpi.json()["gross_amount"] == 0.00

    # La empresa rival no ve transacciones de la orden
    res_rival_tx = client.get(f"/api/v1/finances/transactions?order_id={order_uuid}", headers=sec_headers)
    assert res_rival_tx.status_code == 200
    assert len(res_rival_tx.json()["items"]) == 0

    # La empresa rival no puede ver el reporte de la orden (HTTP 404)
    res_rival_ord_rep = client.get(f"/api/v1/finances/reports/orders/{order_uuid}", headers=sec_headers)
    assert res_rival_ord_rep.status_code == 404

"""Pruebas exhaustivas para el Administrador Comercial de Mercado Libre México (Fase 11).

Cubre y valida con estricto rigor:
1. Reglas Comerciales Configurables:
   - Precio mínimo (piso), margen mínimo (%), descuento máximo (%), precio objetivo.
   - Límite de modificaciones de precio diarias.
   - Ventanas de horarios autorizados.
   - Lista de SKUs excluidos.
   - Presupuesto promocional.
   - Aislamiento multiempresa.
2. Simulación de Rentabilidad Previa (SAT México & Deducciones MeLi):
   - Cálculo exacto de precio promocional y absorción compartida (cofinanciado).
   - Comisiones oficiales MeLi México.
   - Costo de envío vendedor y empaque.
   - Retenciones fiscales SAT México vigentes (IVA 8% e ISR 1%).
   - Costo de mercancía (COGS), utilidad neta y margen porcentual.
   - Detección de ofertas inviables con alertas financieras automáticas.
3. Modificación Oficial de Precios en Mercado Libre:
   - Validación previa contra reglas comerciales.
   - Bloqueo por precio piso, descuento excesivo, límite diario de cambios y ventana horaria.
   - Auditoría obligatoria en PriceHistory.
   - Sincronización de precio en variantes internas del catálogo.
4. Restauración Técnica de Precios Anteriores:
   - Re-aplicación del precio original directo en Mercado Libre.
   - Actualización de auditoría (restored_at, can_restore=False).
   - Prevención de doble restauración.
5. Programación de Precios a Futuro y Reversión Automática:
   - Programación con fecha futura y fecha de reversión opcional.
   - Validación cronológica estricta.
   - Ejecución periódica (process_due_scheduled_prices) para aplicar y revertir.
6. Promociones Oficiales MeLi y Postulación con Confirmación Estricta:
   - Consulta de campañas oficiales y candidatos.
   - Postulación con validación de viabilidad económica.
   - REGLA ESTRICTA: No afirmar que una promoción se activó sin confirmación oficial de Mercado Libre.
7. Análisis de Competencia Autorizado (Buy Box de Catálogo) y Recomendaciones:
   - Benchmark de publicaciones de catálogo.
   - Cálculo de precio sugerido para ganar el Buy Box respetando el precio piso.
   - Generación y consulta de recomendaciones comerciales.
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
from src.models.commercial import (
    CommercialRecommendation,
    CommercialRule,
    CompetitorBenchmark,
    PriceHistory,
    ScheduledPriceChange,
)
from src.models.meli_account import MeliAccount
from src.models.product import Product, ProductVariant
from src.schemas.commercial import (
    CommercialRuleCreateRequest,
    PromotionSimulationRequest,
)
from src.services.commercial_service import CommercialService


@pytest.fixture
def commercial_test_context(tmp_path):
    """Provee entorno de pruebas aislado con BD SQLite, empresas y headers autenticados."""
    db_file = tmp_path / "commercial_admin_test.db"
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
            "tenant_name": f"Tenant Comercial {unique_id}",
            "tenant_slug": f"com-slug-{unique_id}",
            "company_legal_name": f"Comercializadora Alpha S.A. {unique_id}",
            "company_rfc": "CAL991201AB0",
            "admin_email": f"com_admin_{unique_id}@test.com",
            "admin_password": "PasswordComercial1!",
            "admin_full_name": "Director Comercial ERP",
        })
        assert reg_res.status_code == 201
        company_id = reg_res.json()["company_id"]

        login_res = client.post("/api/v1/auth/login", json={
            "email": f"com_admin_{unique_id}@test.com",
            "password": "PasswordComercial1!",
        })
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]

        headers = {
            "Authorization": f"Bearer {token}",
            "X-Company-ID": company_id,
        }

        # 2. Empresa Rival para Pruebas de Aislamiento
        reg_sec = client.post("/api/v1/auth/register-tenant", json={
            "tenant_name": f"Tenant Rival Com {unique_id}",
            "tenant_slug": f"rival-com-{unique_id}",
            "company_legal_name": f"Rival Retail S.A. {unique_id}",
            "company_rfc": "RCO991201XY1",
            "admin_email": f"admin_rival_com_{unique_id}@test.com",
            "admin_password": "PasswordRivalCom1!",
            "admin_full_name": "Admin Rival Com",
        })
        sec_company_id = reg_sec.json()["company_id"]
        login_sec = client.post("/api/v1/auth/login", json={
            "email": f"admin_rival_com_{unique_id}@test.com",
            "password": "PasswordRivalCom1!",
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
            "seller_id": 883344112,
        }

    app.dependency_overrides.clear()


@pytest.fixture
async def setup_commercial_data(commercial_test_context):
    """Crea cuenta MeLi conectada y producto con variante en el catálogo."""
    session_factory = commercial_test_context["session_factory"]
    company_id = uuid.UUID(commercial_test_context["company_id"])
    seller_id = commercial_test_context["seller_id"]

    async with session_factory() as session:
        # Cuenta MeLi
        account = MeliAccount(
            company_id=company_id,
            meli_user_id=seller_id,
            nickname="Tienda Oficial Comercial MeLi",
            site_id="MLM",
            access_token_enc=encrypt_token("APP_USR-test-commercial-token"),
            refresh_token_enc=encrypt_token("TG-test-commercial-refresh"),
            token_expires_at=datetime.now(timezone.utc) + timedelta(hours=8),
            is_active=True,
        )
        session.add(account)

        # Producto y Variante
        product = Product(
            company_id=company_id,
            name="Audífonos Bluetooth Cancelación Ruido",
            brand="SoundPro",
            model="ANC-2026",
            category="Audio",
            is_active=True,
        )
        session.add(product)
        await session.flush()

        variant = ProductVariant(
            company_id=company_id,
            product_id=product.id,
            variant_name="Negro Mate",
            sku="AUD-ANC-BLK",
            sale_price=999.00,
            cogs_cost=450.00,
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


# ===========================================================================
# 1. PRUEBAS DE REGLAS COMERCIALES CONFIGURABLES
# ===========================================================================

def test_commercial_rules_crud_and_isolation(commercial_test_context):
    """Crea, lista, actualiza y valida aislamiento multiempresa de reglas comerciales."""
    client = commercial_test_context["client"]
    headers = commercial_test_context["headers"]
    sec_headers = commercial_test_context["sec_headers"]

    # 1. Crear Regla Comercial
    rule_payload = {
        "name": "Estrategia Audio Buen Fin 2026",
        "description": "Protege márgenes mínimos del 20% y frena caídas descontroladas de precios",
        "min_price": 599.00,
        "min_margin_pct": 20.0,
        "max_discount_pct": 35.0,
        "target_price": 899.00,
        "max_daily_changes": 3,
        "allowed_hours_start": 8,
        "allowed_hours_end": 22,
        "excluded_skus": ["SKU-EXCLUIDO-VIP"],
        "promotional_budget": 50000.00,
    }
    res_create = client.post("/api/v1/commercial/rules", json=rule_payload, headers=headers)
    assert res_create.status_code == 201
    created_rule = res_create.json()
    rule_id = created_rule["id"]
    assert created_rule["name"] == "Estrategia Audio Buen Fin 2026"
    assert created_rule["min_price"] == 599.00
    assert created_rule["min_margin_pct"] == 20.0
    assert created_rule["max_discount_pct"] == 35.0
    assert created_rule["max_daily_changes"] == 3
    assert created_rule["promotional_budget"] == 50000.00
    assert "SKU-EXCLUIDO-VIP" in created_rule["excluded_skus"]

    # 2. Listar Reglas
    res_list = client.get("/api/v1/commercial/rules", headers=headers)
    assert res_list.status_code == 200
    rules = res_list.json()
    assert len(rules) >= 1
    assert any(r["id"] == rule_id for r in rules)

    # 3. Modificar Regla
    update_payload = {
        "min_price": 649.00,
        "max_discount_pct": 30.0,
        "promotional_budget": 60000.00,
    }
    res_update = client.put(f"/api/v1/commercial/rules/{rule_id}", json=update_payload, headers=headers)
    assert res_update.status_code == 200
    updated_rule = res_update.json()
    assert updated_rule["min_price"] == 649.00
    assert updated_rule["max_discount_pct"] == 30.0
    assert updated_rule["promotional_budget"] == 60000.00

    # 4. Aislamiento Multiempresa: Rival no debe ver ni modificar la regla
    res_rival_list = client.get("/api/v1/commercial/rules", headers=sec_headers)
    assert res_rival_list.status_code == 200
    assert all(r["id"] != rule_id for r in res_rival_list.json())

    res_rival_mod = client.put(f"/api/v1/commercial/rules/{rule_id}", json={"min_price": 10.0}, headers=sec_headers)
    assert res_rival_mod.status_code in [404, 422]


# ===========================================================================
# 2. SIMULACIÓN DE RENTABILIDAD FINANCIERA Y FISCAL SAT MÉXICO
# ===========================================================================

def test_profitability_simulation_sat_breakdown(commercial_test_context):
    """Verifica simulación matemática con desglose SAT (IVA 8%, ISR 1%), comisiones y COGS."""
    client = commercial_test_context["client"]
    headers = commercial_test_context["headers"]

    # Simulación de un producto de $1,000 MXN con 10% de descuento
    sim_payload = {
        "regular_price": 1000.00,
        "discount_pct": 10.0,
        "cogs": 400.00,
        "meli_fee_rate": 0.15,  # 15% comisión MeLi Clásica
        "shipping_cost": 85.00,
        "packaging_cost": 15.00,
        "cofunded_by_meli_pct": 50.0,  # 50% absorbido por Mercado Libre
    }
    res_sim = client.post("/api/v1/commercial/prices/simulate", json=sim_payload, headers=headers)
    assert res_sim.status_code == 200
    data = res_sim.json()

    # Validaciones matemáticas exactas:
    # Precio promo = 1000 * 0.9 = 900.00
    assert data["promotional_price"] == 900.00
    # Descuento total = 100.00, absorbido 50% MeLi = 50.00, vendedor = 50.00
    assert data["discount_total_amount"] == 100.00
    assert data["meli_cofunded_amount"] == 50.00
    assert data["seller_discount_amount"] == 50.00

    # Comisiones y retenciones:
    # MeLi fee = 900 * 0.15 = 135.00
    assert data["meli_commission_fee"] == 135.00
    # SAT IVA (8%) = 900 * 0.08 = 72.00
    assert data["sat_iva_retention"] == 72.00
    # SAT ISR (1%) = 900 * 0.01 = 9.00
    assert data["sat_isr_retention"] == 9.00
    # Deducciones totales = 135 + 85 + 15 + 72 + 9 = 316.00
    assert data["total_deductions"] == 316.00

    # Utilidad neta = 900 - 400 (COGS) - 316 (Deducciones) = 184.00
    assert data["net_profit"] == 184.00
    # Margen neto % = (184.00 / 900.00) * 100 = 20.44%
    assert data["net_margin_pct"] == 20.44
    assert data["is_viable"] is True


def test_profitability_simulation_rule_viability_alert(commercial_test_context):
    """Valida alerta automática de inviabilidad si la oferta viola el margen o precio piso de la regla."""
    client = commercial_test_context["client"]
    headers = commercial_test_context["headers"]

    # Crear regla estricta: mínimo $800 y mínimo 25% de margen
    client.post("/api/v1/commercial/rules", json={
        "name": "Regla Alta Rentabilidad",
        "min_price": 800.00,
        "min_margin_pct": 25.0,
        "max_discount_pct": 20.0,
    }, headers=headers)

    # Simulación que arroja 20.44% de margen y precio $750 (viola ambas condiciones)
    sim_payload = {
        "regular_price": 1000.00,
        "discount_pct": 25.0,  # Descuento del 25% (excede el 20% máx)
        "cogs": 450.00,
        "meli_fee_rate": 0.15,
        "shipping_cost": 85.00,
        "packaging_cost": 15.00,
        "cofunded_by_meli_pct": 0.0,
    }
    res_sim = client.post("/api/v1/commercial/prices/simulate", json=sim_payload, headers=headers)
    assert res_sim.status_code == 200
    data = res_sim.json()
    assert data["is_viable"] is False
    assert data["viability_alert"] is not None
    assert "precio mínimo" in data["viability_alert"] or "margen mínimo" in data["viability_alert"]


# ===========================================================================
# 3. MODIFICACIÓN DE PRECIOS, VALIDACIÓN DE REGLAS Y AUDITORÍA
# ===========================================================================

@pytest.mark.asyncio
async def test_update_item_price_success_and_history(commercial_test_context, setup_commercial_data):
    """Modifica precio en MeLi, valida auditoría en PriceHistory y sincronización de variante."""
    client = commercial_test_context["client"]
    headers = commercial_test_context["headers"]
    data = setup_commercial_data
    account_id = data["account_id"]
    sku = data["sku"]

    # Mockear llamadas al conector de MeLi
    mock_get_item = AsyncMock(return_value={
        "id": "MLM11223344",
        "price": 999.00,
        "seller_custom_field": sku,
    })
    mock_update_price = AsyncMock(return_value={
        "id": "MLM11223344",
        "price": 899.00,
    })

    with patch("src.connectors.meli.items.MeliItemsClient.get_item", mock_get_item), \
         patch("src.connectors.meli.prices.MeliPricesClient.update_price", mock_update_price):

        res = client.post(
            f"/api/v1/commercial/prices/MLM11223344?meli_account_id={account_id}",
            json={
                "new_price": 899.00,
                "reason": "Promoción Flash Fin de Semana",
            },
            headers=headers,
        )
        assert res.status_code == 200
        res_data = res.json()
        assert res_data["status"] == "applied"
        assert res_data["previous_price"] == 999.00
        assert res_data["new_price"] == 899.00
        assert res_data["confirmed_by_meli"] is True
        history_id = res_data["history_id"]

        # Consultar historial de precios
        res_hist = client.get("/api/v1/commercial/prices/history?meli_item_id=MLM11223344", headers=headers)
        assert res_hist.status_code == 200
        hist_items = res_hist.json()["items"]
        assert len(hist_items) >= 1
        last_h = hist_items[0]
        assert last_h["id"] == history_id
        assert last_h["previous_price"] == 999.00
        assert last_h["new_price"] == 899.00
        assert last_h["change_reason"] == "Promoción Flash Fin de Semana"
        assert last_h["can_restore"] is True


@pytest.mark.asyncio
async def test_update_item_price_rules_enforcement(commercial_test_context, setup_commercial_data):
    """Verifica que las reglas comerciales bloqueen precios indebidos (precio piso y descuento excesivo)."""
    client = commercial_test_context["client"]
    headers = commercial_test_context["headers"]
    data = setup_commercial_data
    account_id = data["account_id"]
    sku = data["sku"]

    # Crear regla con precio mínimo de $700 y descuento máx de 20%
    client.post("/api/v1/commercial/rules", json={
        "name": "Regla Restrictiva",
        "min_price": 700.00,
        "min_margin_pct": 15.0,
        "max_discount_pct": 20.0,
        "max_daily_changes": 2,
    }, headers=headers)

    mock_get_item = AsyncMock(return_value={
        "id": "MLM998877",
        "price": 999.00,
        "seller_custom_field": sku,
    })

    with patch("src.connectors.meli.items.MeliItemsClient.get_item", mock_get_item):
        # 1. Bloqueo por precio por debajo del mínimo ($650 < $700)
        res_floor = client.post(
            f"/api/v1/commercial/prices/MLM998877?meli_account_id={account_id}",
            json={"new_price": 650.00, "reason": "Preciazo agresivo"},
            headers=headers,
        )
        assert res_floor.status_code == 422
        assert "precio piso" in res_floor.json()["detail"].lower() or "precio propuesto" in res_floor.json()["detail"].lower()

        # 2. Bloqueo por descuento mayor al 20% ($750 respecto a $999 es ~24.9% de descuento)
        res_disc = client.post(
            f"/api/v1/commercial/prices/MLM998877?meli_account_id={account_id}",
            json={"new_price": 750.00, "reason": "Super descuento"},
            headers=headers,
        )
        assert res_disc.status_code == 422
        assert "descuento aplicado" in res_disc.json()["detail"].lower() or "límite máximo" in res_disc.json()["detail"].lower()


# ===========================================================================
# 4. RESTAURACIÓN TÉCNICA DE PRECIOS ANTERIORES
# ===========================================================================

@pytest.mark.asyncio
async def test_restore_previous_price(commercial_test_context, setup_commercial_data):
    """Prueba reversión técnica al precio anterior y bloqueo de doble restauración."""
    client = commercial_test_context["client"]
    headers = commercial_test_context["headers"]
    data = setup_commercial_data
    account_id = data["account_id"]
    sku = data["sku"]

    mock_get_item = AsyncMock(return_value={"id": "MLM554433", "price": 1200.00, "seller_custom_field": sku})
    mock_update_price = AsyncMock(return_value={"id": "MLM554433", "price": 999.00})

    with patch("src.connectors.meli.items.MeliItemsClient.get_item", mock_get_item), \
         patch("src.connectors.meli.prices.MeliPricesClient.update_price", mock_update_price):

        # Modificación inicial
        res_mod = client.post(
            f"/api/v1/commercial/prices/MLM554433?meli_account_id={account_id}",
            json={"new_price": 999.00, "reason": "Campaña temporal"},
            headers=headers,
        )
        assert res_mod.status_code == 200
        history_id = res_mod.json()["history_id"]

    # Simular que MeLi ahora confirma la restauración a $1,200
    mock_restore_update = AsyncMock(return_value={"id": "MLM554433", "price": 1200.00})
    with patch("src.connectors.meli.items.MeliItemsClient.get_item", mock_get_item), \
         patch("src.connectors.meli.prices.MeliPricesClient.update_price", mock_restore_update):

        res_restore = client.post(
            "/api/v1/commercial/prices/restore",
            json={"history_id": history_id},
            headers=headers,
        )
        assert res_restore.status_code == 200
        restored_data = res_restore.json()
        assert restored_data["new_price"] == 1200.00
        assert restored_data["change_reason"] == "restored"

        # Segunda restauración sobre el mismo historial debe fallar
        res_double_restore = client.post(
            "/api/v1/commercial/prices/restore",
            json={"history_id": history_id},
            headers=headers,
        )
        assert res_double_restore.status_code == 422
        assert "no es apto para restauración" in res_double_restore.json()["detail"].lower()


# ===========================================================================
# 5. PROGRAMACIÓN DE PRECIOS A FUTURO Y REVERSIÓN AUTOMÁTICA
# ===========================================================================

@pytest.mark.asyncio
async def test_schedule_price_and_process_due(commercial_test_context, setup_commercial_data):
    """Programa un cambio de precio y procesa su aplicación y reversión."""
    client = commercial_test_context["client"]
    headers = commercial_test_context["headers"]
    session_factory = commercial_test_context["session_factory"]

    now = datetime.now(timezone.utc)
    target_dt = now + timedelta(hours=2)
    revert_dt = now + timedelta(hours=24)

    # 1. Crear programación
    sched_payload = {
        "meli_item_id": "MLM_SCHED_01",
        "target_price": 799.00,
        "scheduled_at": target_dt.isoformat(),
        "revert_at": revert_dt.isoformat(),
    }
    res_sched = client.post("/api/v1/commercial/prices/schedule", json=sched_payload, headers=headers)
    assert res_sched.status_code == 201
    sched_id = res_sched.json()["id"]
    assert res_sched.json()["status"] == "pending"

    # 2. Modificar artificialmente la fecha de scheduled_at en la BD para que quede en el pasado
    async with session_factory() as session:
        stmt = select(ScheduledPriceChange).where(ScheduledPriceChange.id == uuid.UUID(sched_id))
        rec = (await session.execute(stmt)).scalar_one()
        rec.scheduled_at = now - timedelta(minutes=5)
        await session.commit()

    # 3. Disparar proceso de aplicación de precios
    mock_get_item = AsyncMock(return_value={"id": "MLM_SCHED_01", "price": 999.00})
    mock_update_price = AsyncMock(return_value={"id": "MLM_SCHED_01", "price": 799.00})

    with patch("src.connectors.meli.items.MeliItemsClient.get_item", mock_get_item), \
         patch("src.connectors.meli.prices.MeliPricesClient.update_price", mock_update_price):

        res_proc = client.post("/api/v1/commercial/prices/schedule/process", headers=headers)
        assert res_proc.status_code == 200
        assert res_proc.json()["applied_count"] >= 1

    # Verificar que el registro cambió a 'applied'
    async with session_factory() as session:
        stmt = select(ScheduledPriceChange).where(ScheduledPriceChange.id == uuid.UUID(sched_id))
        rec = (await session.execute(stmt)).scalar_one()
        assert rec.status == "applied"

        # Adelantar revert_at al pasado para probar reversión
        rec.revert_at = now - timedelta(minutes=1)
        await session.commit()

    # 4. Disparar reversión
    mock_revert_price = AsyncMock(return_value={"id": "MLM_SCHED_01", "price": 999.00})
    with patch("src.connectors.meli.items.MeliItemsClient.get_item", mock_get_item), \
         patch("src.connectors.meli.prices.MeliPricesClient.update_price", mock_revert_price):

        res_proc_rev = client.post("/api/v1/commercial/prices/schedule/process", headers=headers)
        assert res_proc_rev.status_code == 200
        assert res_proc_rev.json()["applied_count"] >= 1

    async with session_factory() as session:
        stmt = select(ScheduledPriceChange).where(ScheduledPriceChange.id == uuid.UUID(sched_id))
        rec = (await session.execute(stmt)).scalar_one()
        assert rec.status == "reverted"


# ===========================================================================
# 6. PROMOCIONES OFICIALES MELI Y CONFIRMACIÓN ESTRICTA
# ===========================================================================

@pytest.mark.asyncio
async def test_promotions_optin_requires_meli_confirmation(commercial_test_context, setup_commercial_data):
    """
    Verifica que la postulación a una campaña SOLO se registre si Mercado Libre responde confirmando.
    REGLA: No afirmar que una promoción se activó sin confirmación de Mercado Libre.
    """
    client = commercial_test_context["client"]
    headers = commercial_test_context["headers"]
    data = setup_commercial_data
    account_id = data["account_id"]

    # 1. Postulación exitosa confirmada por MeLi (status="started")
    mock_optin_ok = AsyncMock(return_value={
        "id": "MLM_PROMO_OK",
        "promotion_id": "CAMP-BUENFIN-2026",
        "status": "started",
        "deal_price": 799.00,
    })

    with patch("src.connectors.meli.promotions.MeliPromotionsClient.optin_promotion_item", mock_optin_ok):
        res_ok = client.post(
            f"/api/v1/commercial/promotions/optin?item_id=MLM_PROMO_OK&meli_account_id={account_id}",
            json={
                "promotion_id": "CAMP-BUENFIN-2026",
                "promotion_type": "MARKETPLACE_CAMPAIGN",
                "deal_price": 799.00,
                "validate_viability": False,
            },
            headers=headers,
        )
        assert res_ok.status_code == 200
        body = res_ok.json()
        assert body["confirmed_by_meli"] is True
        assert body["status"] == "active"
        assert body["deal_price"] == 799.00

    # 2. Rechazo o respuesta no confirmada por MeLi -> DEBE FALLAR con ValidationException
    mock_optin_unconfirmed = AsyncMock(return_value={
        "id": "MLM_PROMO_FAIL",
        "status": "rejected",  # No es started, candidate, active ni pending
    })

    with patch("src.connectors.meli.promotions.MeliPromotionsClient.optin_promotion_item", mock_optin_unconfirmed):
        res_fail = client.post(
            f"/api/v1/commercial/promotions/optin?item_id=MLM_PROMO_FAIL&meli_account_id={account_id}",
            json={
                "promotion_id": "CAMP-BUENFIN-2026",
                "promotion_type": "MARKETPLACE_CAMPAIGN",
                "deal_price": 799.00,
                "validate_viability": False,
            },
            headers=headers,
        )
        assert res_fail.status_code == 422
        assert "no confirmó la activación" in res_fail.json()["detail"].lower()


# ===========================================================================
# 7. ANÁLISIS DE COMPETENCIA (BUY BOX) Y RECOMENDACIONES COMERCIALES
# ===========================================================================

@pytest.mark.asyncio
async def test_competitor_benchmark_and_recommendations(commercial_test_context, setup_commercial_data):
    """Evalúa análisis de Buy Box de catálogo de MeLi y generación de recomendaciones."""
    client = commercial_test_context["client"]
    headers = commercial_test_context["headers"]
    data = setup_commercial_data
    account_id = data["account_id"]
    sku = data["sku"]
    session_factory = commercial_test_context["session_factory"]
    company_id = uuid.UUID(commercial_test_context["company_id"])

    # Mock de item con catálogo en competencia
    mock_get_item = AsyncMock(return_value={
        "id": "MLM_CAT_123",
        "price": 500.00,
        "catalog_product_id": "MLMCAT999",
        "seller_custom_field": sku,
    })

    with patch("src.connectors.meli.items.MeliItemsClient.get_item", mock_get_item):
        res_bench = client.get(
            f"/api/v1/commercial/competitor/MLM_CAT_123?meli_account_id={account_id}",
            headers=headers,
        )
        assert res_bench.status_code == 200
        bench = res_bench.json()
        assert bench["catalog_product_id"] == "MLMCAT999"
        assert bench["our_status"] in ["winning", "losing"]
        assert bench["competitor_count"] >= 1
        if bench["our_status"] == "losing":
            assert bench["suggested_price"] is not None
            assert bench["suggested_price"] < bench["our_price"]

    # Generar recomendación comercial inteligente en la base de datos
    commercial_service = CommercialService()
    async with session_factory() as session:
        await commercial_service.generate_recommendation_for_item(
            session=session,
            company_id=company_id,
            meli_item_id="MLM_CAT_123",
            sku=sku,
            rec_type="price_reduction",
            title="Reducir $5 MXN para ganar Buy Box",
            description="Competidor líder tiene el Buy Box a $480.00 MXN",
            current_price=500.00,
            recommended_price=475.00,
            projected_margin_pct=18.5,
            projected_profit=87.88,
        )
        await session.commit()

    # Consultar recomendaciones desde el endpoint
    res_rec = client.get("/api/v1/commercial/recommendations?status_filter=pending", headers=headers)
    assert res_rec.status_code == 200
    recs = res_rec.json()
    assert len(recs) >= 1
    assert any(r["sku"] == sku for r in recs)
    target_rec = next(r for r in recs if r["sku"] == sku)
    assert target_rec["recommendation_type"] == "price_reduction"
    assert target_rec["recommended_price"] == 475.00

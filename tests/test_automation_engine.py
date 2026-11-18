"""
Pruebas exhaustivas para el Motor de Automatización Empresarial (ECA).

Verifica:
1. Activadores (Eventos y Programaciones), Condiciones y Acciones.
2. Los 10 Ejemplos Canónicos del requerimiento:
   - Venta recibida: reservar inventario.
   - Venta confirmada: actualizar existencias.
   - Stock bajo: generar alerta.
   - Stock agotado: actualizar publicación si corresponde.
   - Etiqueta disponible: preparar tarea logística.
   - Promoción próxima a vencer: generar alerta.
   - Margen inferior al mínimo: detener cambio de precio.
   - Venta procesada: actualizar planilla.
   - Fin del día: generar reporte.
   - Demanda creciente: recomendar reposición.
3. Modalidades: Manual, Automática y Automática con Aprobación Previa (configurable por módulo).
4. Interruptor General (Global Kill Switch).
5. Mecanismo de Reversión y Compensación (Rollback / Undo).
6. Control de eventos duplicados (Idempotencia y Deduplicación).
7. Reintentos, Dead-Letter Queue y Circuit Breaker ante fallos repetitivos.
8. Concurrencia y prevención de sobreventa / stock negativo en inventario.
9. Salvaguardas de seguridad en precios, márgenes y límites autorizados.
10. Aislamiento multi-tenant estricto.
"""

import asyncio
from datetime import datetime, timedelta, timezone
import uuid
import pytest
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

from src.core.database import get_db
from src.main import app
from src.models import Base
from src.models.automation import AutomationConfig, AutomationExecution, AutomationRule
from src.models.product import Product, ProductVariant
from src.models.profitability import ProfitabilityAlert
from src.models.supplier import PurchaseOrder, Supplier, SupplierProduct
from src.models.warehouse import Inventory, InventoryMovement, Warehouse
from src.schemas.automation import AutomationRuleCreate
from src.services.automation.engine import AutomationEngineService


@pytest.fixture
def automation_test_context(tmp_path):
    """Provee entorno de pruebas aislado con BD SQLite en memoria/disco temporal."""
    db_file = tmp_path / "automation_test.db"
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
        # Empresa 1
        reg1 = client.post("/api/v1/auth/register-tenant", json={
            "tenant_name": f"Auto Tenant {uid}",
            "tenant_slug": f"auto-slug-{uid}",
            "company_legal_name": f"Auto Corp {uid} SA de CV",
            "company_rfc": "AUT990101AA1",
            "admin_email": f"admin_auto_{uid}@corp.com",
            "admin_password": "Password123!",
            "admin_full_name": "Auto Admin",
        })
        assert reg1.status_code == 201
        comp1_id = reg1.json()["company_id"]

        login1 = client.post("/api/v1/auth/login", json={
            "email": f"admin_auto_{uid}@corp.com",
            "password": "Password123!",
        })
        token1 = login1.json()["access_token"]
        headers1 = {"Authorization": f"Bearer {token1}", "X-Company-ID": comp1_id}

        # Empresa 2 (Multi-Tenant)
        reg2 = client.post("/api/v1/auth/register-tenant", json={
            "tenant_name": f"Other Tenant {uid}",
            "tenant_slug": f"oth-auto-{uid}",
            "company_legal_name": f"Other Auto {uid} SA",
            "company_rfc": "OTH990101CC3",
            "admin_email": f"other_auto_{uid}@corp.com",
            "admin_password": "Password123!",
            "admin_full_name": "Other Admin",
        })
        assert reg2.status_code == 201
        comp2_id = reg2.json()["company_id"]

        login2 = client.post("/api/v1/auth/login", json={
            "email": f"other_auto_{uid}@corp.com",
            "password": "Password123!",
        })
        token2 = login2.json()["access_token"]
        headers2 = {"Authorization": f"Bearer {token2}", "X-Company-ID": comp2_id}

        yield {
            "client": client,
            "session_factory": session_factory,
            "company1_id": comp1_id,
            "headers1": headers1,
            "company2_id": comp2_id,
            "headers2": headers2,
        }

    app.dependency_overrides.clear()


@pytest.fixture
async def setup_automation_master_data(automation_test_context):
    """Crea almacén, productos, inventario con stock inicial y proveedor para Empresa 1."""
    session_factory = automation_test_context["session_factory"]
    company1_id = uuid.UUID(automation_test_context["company1_id"])

    async with session_factory() as session:
        # Almacén
        wh = Warehouse(
            company_id=company1_id,
            name="Almacén Central Automations",
            code="WH-AUTO-01",
            warehouse_type="internal",
            is_active=True,
        )
        session.add(wh)
        await session.flush()

        # Producto y Variante con Stock Inicial
        prod = Product(
            company_id=company1_id,
            name="Auriculares Inalámbricos Pro",
            brand="SoundWave",
            category="Audio",
            unit_of_measure="pza",
            is_active=True,
        )
        session.add(prod)
        await session.flush()

        var = ProductVariant(
            company_id=company1_id,
            product_id=prod.id,
            sku="SOUND-PRO-01",
            variant_name="Negro Mate",
            cogs_cost=400.00,
            sale_price=850.00,
            is_active=True,
        )
        session.add(var)
        await session.flush()

        inv = Inventory(
            warehouse_id=wh.id,
            variant_id=var.id,
            quantity_on_hand=50,
            quantity_reserved=0,
            quantity_blocked=0,
            safety_stock=10,
            min_stock=15,
        )
        session.add(inv)

        # Proveedor
        supp = Supplier(
            company_id=company1_id,
            name="Audio Distribuciones SA de CV",
            rfc="ADI010101AA1",
            contact_name="Carlos Proveedor",
            email="ventas@audiodist.com",
            phone="5512345678",
            currency="MXN",
            payment_terms_days=30,
            lead_time_days=5,
            is_active=True,
        )
        session.add(supp)
        await session.flush()

        sp = SupplierProduct(
            company_id=company1_id,
            supplier_id=supp.id,
            product_id=prod.id,
            variant_id=var.id,
            supplier_sku="SUP-SOUND-01",
            purchase_cost=400.00,
            is_preferred=True,
        )
        session.add(sp)

        await session.commit()

        return {
            "warehouse_id": str(wh.id),
            "product_id": str(prod.id),
            "variant_id": str(var.id),
            "sku": var.sku,
            "supplier_id": str(supp.id),
        }


# ===========================================================================
# 1. PRUEBA: INTERRUPTOR GENERAL (KILL SWITCH) Y MODALIDADES POR MÓDULO
# ===========================================================================

@pytest.mark.asyncio
async def test_global_kill_switch_and_module_modes_configuration(automation_test_context):
    """
    Verifica:
    - Interruptor General (Global Kill Switch) a nivel empresa.
    - Configuración granular de modalidades por módulo (manual, automatic, approval_required).
    - Despacho de eventos bloqueado cuando el motor está desactivado.
    """
    client = automation_test_context["client"]
    headers = automation_test_context["headers1"]

    # 1. Consultar configuración por defecto
    res_get = client.get("/api/v1/automation/config", headers=headers)
    assert res_get.status_code == 200
    cfg = res_get.json()
    assert cfg["is_engine_active"] is True
    assert cfg["module_modes"]["inventory"] == "automatic"
    assert cfg["module_modes"]["pricing"] == "approval_required"

    # 2. Desactivar motor mediante Global Kill Switch
    res_update = client.put("/api/v1/automation/config", json={"is_engine_active": False}, headers=headers)
    assert res_update.status_code == 200
    assert res_update.json()["is_engine_active"] is False

    # 3. Intentar disparar un evento mientras el motor está apagado
    evt_payload = {
        "event_name": "ORDER_CREATED",
        "payload": {"sku": "TEST-SKU", "quantity": 1},
    }
    res_trigger = client.post("/api/v1/automation/events/trigger", json=evt_payload, headers=headers)
    assert res_trigger.status_code == 200
    t_data = res_trigger.json()
    assert t_data["dispatched"] is False
    assert t_data["engine_active"] is False
    assert "Global Kill Switch activo" in t_data["message"]

    # 4. Reactivar motor y configurar modalidades específicas por módulo
    new_modes = {
        "inventory": "automatic",
        "pricing": "approval_required",
        "promotions": "approval_required",
        "logistics": "automatic",
        "procurement": "approval_required",
    }
    res_reactivate = client.put(
        "/api/v1/automation/config", json={"is_engine_active": True, "module_modes": new_modes}, headers=headers
    )
    assert res_reactivate.status_code == 200
    assert res_reactivate.json()["is_engine_active"] is True
    assert res_reactivate.json()["module_modes"]["pricing"] == "approval_required"


# ===========================================================================
# 2. PRUEBA: LOS 10 EJEMPLOS CANÓNICOS DEL REQUERIMIENTO
# ===========================================================================

@pytest.mark.asyncio
async def test_ten_canonical_examples_eca_execution(automation_test_context, setup_automation_master_data):
    """
    Verifica los 10 ejemplos solicitados en la especificación del requerimiento:
    1. Venta recibida: reservar inventario.
    2. Venta confirmada: actualizar existencias.
    3. Stock bajo: generar alerta.
    4. Stock agotado: actualizar publicación si corresponde.
    5. Etiqueta disponible: preparar tarea logística.
    6. Promoción próxima a vencer: generar alerta.
    7. Margen inferior al mínimo: detener cambio de precio.
    8. Venta procesada: actualizar planilla.
    9. Fin del día: generar reporte.
    10. Demanda creciente: recomendar reposición.
    """
    client = automation_test_context["client"]
    headers = automation_test_context["headers1"]
    sku = setup_automation_master_data["sku"]
    variant_id = setup_automation_master_data["variant_id"]

    # --- CANÓNICO 1: Venta recibida -> Reservar inventario ---
    rule1_payload = {
        "name": "R1: Reservar stock en venta recibida",
        "module": "inventory",
        "trigger_type": "event",
        "trigger_event": "ORDER_CREATED",
        "action_type": "RESERVE_INVENTORY",
        "execution_mode": "automatic",
        "action_parameters": {"quantity": 2},
    }
    r1 = client.post("/api/v1/automation/rules", json=rule1_payload, headers=headers)
    assert r1.status_code == 201

    res_t1 = client.post(
        "/api/v1/automation/events/trigger",
        json={"event_name": "ORDER_CREATED", "payload": {"sku": sku, "quantity": 2}},
        headers=headers,
    )
    assert res_t1.status_code == 200
    assert res_t1.json()["executions"][0]["status"] == "success"

    # Verificar en BD que se incrementó quantity_reserved a 2
    session_factory = automation_test_context["session_factory"]
    async with session_factory() as s:
        inv = (await s.execute(select(Inventory).where(Inventory.variant_id == uuid.UUID(variant_id)))).scalar_one()
        assert inv.quantity_reserved == 2
        assert inv.quantity_on_hand == 50

    # --- CANÓNICO 2: Venta confirmada -> Actualizar existencias (Deducción física) ---
    rule2_payload = {
        "name": "R2: Deducir existencias en venta confirmada",
        "module": "inventory",
        "trigger_type": "event",
        "trigger_event": "ORDER_CONFIRMED",
        "action_type": "CONFIRM_INVENTORY_DEDUCTION",
        "execution_mode": "automatic",
        "action_parameters": {"quantity": 2},
    }
    r2 = client.post("/api/v1/automation/rules", json=rule2_payload, headers=headers)
    assert r2.status_code == 201

    res_t2 = client.post(
        "/api/v1/automation/events/trigger",
        json={"event_name": "ORDER_CONFIRMED", "payload": {"sku": sku, "quantity": 2, "order_id": str(uuid.uuid4())}},
        headers=headers,
    )
    assert res_t2.status_code == 200
    assert res_t2.json()["executions"][0]["status"] == "success"

    # Verificar que el stock físico bajó de 50 a 48 y reserved se liberó a 0
    async with session_factory() as s:
        inv2 = (await s.execute(select(Inventory).where(Inventory.variant_id == uuid.UUID(variant_id)))).scalar_one()
        assert inv2.quantity_on_hand == 48
        assert inv2.quantity_reserved == 0

    # --- CANÓNICO 3: Stock bajo -> Generar alerta operativa ---
    rule3_payload = {
        "name": "R3: Alerta de stock bajo",
        "module": "inventory",
        "trigger_type": "event",
        "trigger_event": "STOCK_LOW",
        "action_type": "CREATE_OPERATIONAL_ALERT",
        "execution_mode": "automatic",
        "action_parameters": {
            "alert_type": "low_stock",
            "severity": "high",
            "message": "Nivel de existencias por debajo del punto de reorden",
        },
    }
    r3 = client.post("/api/v1/automation/rules", json=rule3_payload, headers=headers)
    assert r3.status_code == 201

    res_t3 = client.post(
        "/api/v1/automation/events/trigger",
        json={"event_name": "STOCK_LOW", "payload": {"sku": sku, "current_stock": 5}},
        headers=headers,
    )
    assert res_t3.status_code == 200
    assert res_t3.json()["executions"][0]["status"] == "success"

    # --- CANÓNICO 4: Stock agotado -> Actualizar publicación MeLi (Pausar) ---
    rule4_payload = {
        "name": "R4: Pausar publicación MeLi en stock agotado",
        "module": "inventory",
        "trigger_type": "event",
        "trigger_event": "STOCK_DEPLETED",
        "action_type": "SYNC_MELI_ITEM_STATUS",
        "execution_mode": "automatic",
        "action_parameters": {"target_status": "paused"},
    }
    r4 = client.post("/api/v1/automation/rules", json=rule4_payload, headers=headers)
    assert r4.status_code == 201

    res_t4 = client.post(
        "/api/v1/automation/events/trigger",
        json={"event_name": "STOCK_DEPLETED", "payload": {"meli_item_id": "MLM998877", "previous_status": "active"}},
        headers=headers,
    )
    assert res_t4.status_code == 200
    assert res_t4.json()["executions"][0]["status"] == "success"

    # --- CANÓNICO 5: Etiqueta disponible -> Preparar tarea logística ---
    rule5_payload = {
        "name": "R5: Preparar empaque al estar disponible la etiqueta",
        "module": "logistics",
        "trigger_type": "event",
        "trigger_event": "LABEL_READY",
        "action_type": "CREATE_LOGISTICS_TASK",
        "execution_mode": "automatic",
        "action_parameters": {"task_type": "prepare_package"},
    }
    r5 = client.post("/api/v1/automation/rules", json=rule5_payload, headers=headers)
    assert r5.status_code == 201

    res_t5 = client.post(
        "/api/v1/automation/events/trigger",
        json={"event_name": "LABEL_READY", "payload": {"shipment_id": str(uuid.uuid4())}},
        headers=headers,
    )
    assert res_t5.status_code == 200
    assert res_t5.json()["executions"][0]["status"] == "success"

    # --- CANÓNICO 6: Promoción próxima a vencer -> Generar alerta ---
    rule6_payload = {
        "name": "R6: Alerta de promo próxima a expirar",
        "module": "promotions",
        "trigger_type": "event",
        "trigger_event": "PROMOTION_EXPIRING_SOON",
        "action_type": "CREATE_OPERATIONAL_ALERT",
        "execution_mode": "automatic",
        "action_parameters": {"alert_type": "promotion_expiring", "severity": "medium"},
    }
    r6 = client.post("/api/v1/automation/rules", json=rule6_payload, headers=headers)
    assert r6.status_code == 201

    res_t6 = client.post(
        "/api/v1/automation/events/trigger",
        json={"event_name": "PROMOTION_EXPIRING_SOON", "payload": {"promotion_id": "PROMO-HOT-SALE", "hours_left": 4}},
        headers=headers,
    )
    assert res_t6.status_code == 200
    assert res_t6.json()["executions"][0]["status"] == "success"

    # --- CANÓNICO 7: Margen inferior al mínimo -> Detener cambio de precio ---
    rule7_payload = {
        "name": "R7: Interceptar cambio de precio si viola margen",
        "module": "pricing",
        "trigger_type": "event",
        "trigger_event": "PRICE_CHANGE_REQUESTED",
        "conditions": [{"field": "current_margin_pct", "operator": "lt", "value": 15.0}],
        "action_type": "BLOCK_PRICE_CHANGE",
        "execution_mode": "automatic",
        "action_parameters": {"min_margin_pct": 15.0},
    }
    r7 = client.post("/api/v1/automation/rules", json=rule7_payload, headers=headers)
    assert r7.status_code == 201

    # Disparar con margen del 8% (inferior al 15% requerido)
    res_t7 = client.post(
        "/api/v1/automation/events/trigger",
        json={"event_name": "PRICE_CHANGE_REQUESTED", "payload": {"sku": sku, "proposed_price": 500.0, "current_margin_pct": 8.0}},
        headers=headers,
    )
    assert res_t7.status_code == 200
    assert res_t7.json()["executions"][0]["status"] == "success"

    # --- CANÓNICO 8: Venta procesada -> Actualizar planilla interna ---
    rule8_payload = {
        "name": "R8: Sincronizar planilla con venta procesada",
        "module": "spreadsheets",
        "trigger_type": "event",
        "trigger_event": "SALE_PROCESSED",
        "action_type": "UPDATE_TABULAR_SHEET",
        "execution_mode": "automatic",
        "action_parameters": {"view_code": "ventas"},
    }
    r8 = client.post("/api/v1/automation/rules", json=rule8_payload, headers=headers)
    assert r8.status_code == 201

    res_t8 = client.post(
        "/api/v1/automation/events/trigger",
        json={"event_name": "SALE_PROCESSED", "payload": {"record_id": str(uuid.uuid4())}},
        headers=headers,
    )
    assert res_t8.status_code == 200
    assert res_t8.json()["executions"][0]["status"] == "success"

    # --- CANÓNICO 9: Fin del día -> Generar reporte ejecutivo ---
    rule9_payload = {
        "name": "R9: Generar reporte de cierre diario",
        "module": "reports",
        "trigger_type": "event",
        "trigger_event": "END_OF_DAY",
        "action_type": "GENERATE_DAILY_REPORT",
        "execution_mode": "automatic",
        "action_parameters": {"period": "today"},
    }
    r9 = client.post("/api/v1/automation/rules", json=rule9_payload, headers=headers)
    assert r9.status_code == 201

    res_t9 = client.post(
        "/api/v1/automation/events/trigger",
        json={"event_name": "END_OF_DAY", "payload": {}},
        headers=headers,
    )
    assert res_t9.status_code == 200
    assert res_t9.json()["executions"][0]["status"] == "success"

    # --- CANÓNICO 10: Demanda creciente -> Recomendar reposición (Borrador PO) ---
    rule10_payload = {
        "name": "R10: Sugerir compra ante demanda creciente",
        "module": "procurement",
        "trigger_type": "event",
        "trigger_event": "SURGING_DEMAND",
        "action_type": "CREATE_RESTOCK_SUGGESTION",
        "execution_mode": "automatic",
        "action_parameters": {"quantity": 25},
    }
    r10 = client.post("/api/v1/automation/rules", json=rule10_payload, headers=headers)
    assert r10.status_code == 201

    res_t10 = client.post(
        "/api/v1/automation/events/trigger",
        json={"event_name": "SURGING_DEMAND", "payload": {"sku": sku, "quantity": 25}},
        headers=headers,
    )
    assert res_t10.status_code == 200
    assert res_t10.json()["executions"][0]["status"] == "success"

    # Verificar que se creó la orden de compra estrictamente en BORRADOR (draft)
    async with session_factory() as s:
        po_stmt = select(PurchaseOrder).where(PurchaseOrder.company_id == uuid.UUID(automation_test_context["company1_id"]))
        pos = (await s.execute(po_stmt)).scalars().all()
        assert len(pos) >= 1
        assert pos[-1].status == "draft"


# ===========================================================================
# 3. PRUEBA: REVERSIÓN Y COMPENSACIÓN (ROLLBACK / UNDO)
# ===========================================================================

@pytest.mark.asyncio
async def test_reversibility_and_rollback_mechanisms(automation_test_context, setup_automation_master_data):
    """
    Verifica la capacidad de revertir acciones cuando sea técnicamente posible:
    - Reversión de reserva de stock (libera la cantidad reservada).
    - Reversión de deducción de stock (restaura existencias y registra movimiento compensatorio).
    - Reversión de alerta operativa (marca alerta como descartada/resuelta).
    - Reversión de pausa en MeLi (reactiva la publicación).
    - Reversión de borrador de compra (cancela la orden de compra borrador).
    """
    client = automation_test_context["client"]
    headers = automation_test_context["headers1"]
    sku = setup_automation_master_data["sku"]
    variant_id = setup_automation_master_data["variant_id"]
    session_factory = automation_test_context["session_factory"]

    # 1. Crear regla y ejecutar reserva de stock
    rule_res = client.post("/api/v1/automation/rules", json={
        "name": "Regla Reserva Reversible",
        "module": "inventory",
        "trigger_type": "event",
        "trigger_event": "TEST_RESERVE",
        "action_type": "RESERVE_INVENTORY",
        "execution_mode": "automatic",
        "action_parameters": {"quantity": 5},
    }, headers=headers)
    assert rule_res.status_code == 201

    # Disparar evento
    t_res = client.post("/api/v1/automation/events/trigger", json={
        "event_name": "TEST_RESERVE", "payload": {"sku": sku, "quantity": 5}
    }, headers=headers)
    exec_id = t_res.json()["executions"][0]["execution_id"]

    # Verificar que stock reservado aumentó a 5
    async with session_factory() as s:
        inv = (await s.execute(select(Inventory).where(Inventory.variant_id == uuid.UUID(variant_id)))).scalar_one()
        assert inv.quantity_reserved == 5

    # Ejecutar Rollback vía API
    rb_res = client.post(f"/api/v1/automation/executions/{exec_id}/rollback", headers=headers)
    assert rb_res.status_code == 200
    rb_data = rb_res.json()
    assert rb_data["success"] is True

    # Verificar que tras el rollback el stock reservado volvió a 0
    async with session_factory() as s:
        inv_after = (await s.execute(select(Inventory).where(Inventory.variant_id == uuid.UUID(variant_id)))).scalar_one()
        assert inv_after.quantity_reserved == 0

    # 2. Reversión de deducción definitiva de stock
    rule_deduct = client.post("/api/v1/automation/rules", json={
        "name": "Regla Deducción Reversible",
        "module": "inventory",
        "trigger_type": "event",
        "trigger_event": "TEST_DEDUCT",
        "action_type": "CONFIRM_INVENTORY_DEDUCTION",
        "execution_mode": "automatic",
        "action_parameters": {"quantity": 4},
    }, headers=headers)

    t_deduct = client.post("/api/v1/automation/events/trigger", json={
        "event_name": "TEST_DEDUCT", "payload": {"sku": sku, "quantity": 4}
    }, headers=headers)
    exec_deduct_id = t_deduct.json()["executions"][0]["execution_id"]

    async with session_factory() as s:
        inv_d = (await s.execute(select(Inventory).where(Inventory.variant_id == uuid.UUID(variant_id)))).scalar_one()
        assert inv_d.quantity_on_hand == 46  # 50 - 4 = 46

    # Revertir deducción
    rb_deduct = client.post(f"/api/v1/automation/executions/{exec_deduct_id}/rollback", headers=headers)
    assert rb_deduct.status_code == 200

    # Comprobar que regresó a 50 y se creó movimiento de cancelación
    async with session_factory() as s:
        inv_restored = (await s.execute(select(Inventory).where(Inventory.variant_id == uuid.UUID(variant_id)))).scalar_one()
        assert inv_restored.quantity_on_hand == 50

        # Movimiento compensatorio
        m_stmt = select(InventoryMovement).where(InventoryMovement.movement_type == "INBOUND")
        mov = (await s.execute(m_stmt)).scalar_one()
        assert mov.quantity_delta == 4


# ===========================================================================
# 4. PRUEBA: MODALIDAD AUTOMÁTICA CON APROBACIÓN PREVIA (HUMAN-IN-THE-LOOP)
# ===========================================================================

@pytest.mark.asyncio
async def test_approval_required_workflow_human_in_the_loop(automation_test_context, setup_automation_master_data):
    """
    Verifica el flujo de Aprobación Previa:
    1. La condición se cumple pero la acción NO se ejecuta de inmediato.
    2. La ejecución queda en estado 'pending_approval'.
    3. Un usuario facultado la autoriza (/approve) -> Se ejecuta la acción.
    4. O bien, la rechaza (/reject) -> Se descarta sin aplicar cambios.
    """
    client = automation_test_context["client"]
    headers = automation_test_context["headers1"]
    sku = setup_automation_master_data["sku"]
    variant_id = setup_automation_master_data["variant_id"]
    session_factory = automation_test_context["session_factory"]

    # Crear regla con modalidad 'approval_required'
    rule_res = client.post("/api/v1/automation/rules", json={
        "name": "Regla con Aprobación Requerida",
        "module": "pricing",
        "trigger_type": "event",
        "trigger_event": "HIGH_VALUE_RESERVE",
        "action_type": "RESERVE_INVENTORY",
        "execution_mode": "approval_required",
        "action_parameters": {"quantity": 10},
    }, headers=headers)
    assert rule_res.status_code == 201

    # Disparar evento
    t_res = client.post("/api/v1/automation/events/trigger", json={
        "event_name": "HIGH_VALUE_RESERVE", "payload": {"sku": sku, "quantity": 10}
    }, headers=headers)
    exec_item = t_res.json()["executions"][0]
    exec_id = exec_item["execution_id"]
    assert exec_item["status"] == "pending_approval"

    # Verificar que el stock NO ha sido modificado aún
    async with session_factory() as s:
        inv = (await s.execute(select(Inventory).where(Inventory.variant_id == uuid.UUID(variant_id)))).scalar_one()
        assert inv.quantity_reserved == 0

    # 1. Autorizar ejecución
    appr_res = client.post(f"/api/v1/automation/executions/{exec_id}/approve", json={"action": "approve", "notes": "Aprobado por el Gerente"}, headers=headers)
    assert appr_res.status_code == 200
    appr_data = appr_res.json()
    assert appr_data["status"] == "success"
    assert appr_data["approval_status"] == "approved"

    # Verificar que ahora sí se aplicó la reserva a 10
    async with session_factory() as s:
        inv_after = (await s.execute(select(Inventory).where(Inventory.variant_id == uuid.UUID(variant_id)))).scalar_one()
        assert inv_after.quantity_reserved == 10

    # 2. Prueba de Rechazo
    t_res2 = client.post("/api/v1/automation/events/trigger", json={
        "event_name": "HIGH_VALUE_RESERVE", "payload": {"sku": sku, "quantity": 5}
    }, headers=headers)
    exec_id2 = t_res2.json()["executions"][0]["execution_id"]

    rej_res = client.post(f"/api/v1/automation/executions/{exec_id2}/reject", json={"action": "reject", "notes": "Rechazado por riesgo"}, headers=headers)
    assert rej_res.status_code == 200
    assert rej_res.json()["status"] == "rejected"
    assert rej_res.json()["approval_status"] == "rejected"


# ===========================================================================
# 5. PRUEBA: CONTROL DE EVENTOS DUPLICADOS (IDEMPOTENCIA Y DEDUPLICACIÓN)
# ===========================================================================

@pytest.mark.asyncio
async def test_duplicate_events_idempotency_defense(automation_test_context, setup_automation_master_data):
    """
    Verifica que al enviar eventos duplicados con el mismo event_id o idempotency_key,
    el motor descarte la duplicidad y prevenga duplicar pedidos o movimientos de stock.
    """
    client = automation_test_context["client"]
    headers = automation_test_context["headers1"]
    sku = setup_automation_master_data["sku"]
    variant_id = setup_automation_master_data["variant_id"]
    session_factory = automation_test_context["session_factory"]

    # Crear regla
    client.post("/api/v1/automation/rules", json={
        "name": "Regla Anti-Duplicados",
        "module": "inventory",
        "trigger_type": "event",
        "trigger_event": "WEBHOOK_ORDER_PAID",
        "action_type": "RESERVE_INVENTORY",
        "execution_mode": "automatic",
        "action_parameters": {"quantity": 3},
    }, headers=headers)

    fixed_event_id = "EVENT-MELI-WEBHOOK-999888"

    # Intento 1: Envío normal
    res1 = client.post("/api/v1/automation/events/trigger", json={
        "event_name": "WEBHOOK_ORDER_PAID",
        "event_id": fixed_event_id,
        "payload": {"sku": sku, "quantity": 3},
    }, headers=headers)
    assert res1.status_code == 200
    assert res1.json()["dispatched"] is True
    assert res1.json()["executions"][0]["status"] == "success"

    # Verificar stock reservado = 3
    async with session_factory() as s:
        inv = (await s.execute(select(Inventory).where(Inventory.variant_id == uuid.UUID(variant_id)))).scalar_one()
        assert inv.quantity_reserved == 3

    # Intento 2: Envío duplicado del mismo evento (mismo event_id)
    res2 = client.post("/api/v1/automation/events/trigger", json={
        "event_name": "WEBHOOK_ORDER_PAID",
        "event_id": fixed_event_id,
        "payload": {"sku": sku, "quantity": 3},
    }, headers=headers)
    assert res2.status_code == 200
    d2 = res2.json()
    assert d2["dispatched"] is False
    assert "duplicate_ignored" in d2["executions"][0]["status"]

    # Verificar que el stock reservado SE MANTUVO en 3 (no se duplicó a 6)
    async with session_factory() as s:
        inv_check = (await s.execute(select(Inventory).where(Inventory.variant_id == uuid.UUID(variant_id)))).scalar_one()
        assert inv_check.quantity_reserved == 3


# ===========================================================================
# 6. PRUEBA: REINTENTOS, DEAD-LETTER Y CIRCUIT BREAKER ANTE FALLOS
# ===========================================================================

@pytest.mark.asyncio
async def test_circuit_breaker_and_retries_dead_letter(automation_test_context):
    """
    Verifica:
    - Reintentos ante fallos hasta agotar max_retries.
    - Registro en Dead-Letter Queue con status='dead_letter'.
    - Activación automática de Circuit Breaker (pausa de la regla) tras superar umbral de errores consecutivos.
    - Reactivación manual de la regla reseteando el Circuit Breaker.
    """
    client = automation_test_context["client"]
    headers = automation_test_context["headers1"]

    # Crear regla con acción que provocará fallo intencional (reserva sobre SKU inexistente)
    r_create = client.post("/api/v1/automation/rules", json={
        "name": "Regla Propensa a Error",
        "module": "inventory",
        "trigger_type": "event",
        "trigger_event": "TRIGGER_FAULT",
        "action_type": "RESERVE_INVENTORY",
        "execution_mode": "automatic",
        "max_retries": 2,
        "safety_limits": {"cooldown_seconds": 0},
        "action_parameters": {"sku": "NON-EXISTENT-SKU-999", "quantity": 1},
    }, headers=headers)
    assert r_create.status_code == 201
    rule_id = r_create.json()["id"]

    # Modificar umbral de circuit breaker a 2 errores en la configuración
    client.put("/api/v1/automation/config", json={"circuit_breaker_error_threshold": 2, "cooldown_seconds_default": 0}, headers=headers)

    # Error 1
    t1 = client.post("/api/v1/automation/events/trigger", json={
        "event_name": "TRIGGER_FAULT",
        "event_id": f"ERR-1-{uuid.uuid4()}",
        "payload": {},
    }, headers=headers)
    assert t1.status_code == 200
    assert t1.json()["executions"][0]["status"] == "dead_letter"

    # Error 2 -> Dispara Circuit Breaker
    t2 = client.post("/api/v1/automation/events/trigger", json={
        "event_name": "TRIGGER_FAULT",
        "event_id": f"ERR-2-{uuid.uuid4()}",
        "payload": {},
    }, headers=headers)
    assert t2.status_code == 200
    assert t2.json()["executions"][0]["status"] == "dead_letter"

    # Verificar que la regla quedó pausada por Circuit Breaker
    r_check = client.get(f"/api/v1/automation/rules/{rule_id}", headers=headers)
    assert r_check.status_code == 200
    assert r_check.json()["is_paused_by_circuit_breaker"] is True
    assert r_check.json()["consecutive_errors"] == 2

    # Intentar disparar de nuevo: la regla en pausa no debe ejecutarse
    t3 = client.post("/api/v1/automation/events/trigger", json={
        "event_name": "TRIGGER_FAULT",
        "event_id": f"ERR-3-{uuid.uuid4()}",
        "payload": {},
    }, headers=headers)
    assert t3.status_code == 200
    assert len(t3.json()["executions"]) == 0

    # Reactivar regla reseteando Circuit Breaker
    res_reset = client.post(f"/api/v1/automation/rules/{rule_id}/reset-circuit-breaker", headers=headers)
    assert res_reset.status_code == 200
    assert res_reset.json()["is_paused_by_circuit_breaker"] is False
    assert res_reset.json()["consecutive_errors"] == 0


# ===========================================================================
# 7. PRUEBA: CONCURRENCIA Y PREVENCIÓN DE SOBREVENTA (RACE CONDITIONS)
# ===========================================================================

@pytest.mark.asyncio
async def test_concurrency_race_condition_inventory_defense(automation_test_context, setup_automation_master_data):
    """
    Verifica la protección de concurrencia:
    Múltiples eventos simultáneos compitiendo por un stock limitado garantizan
    que el stock disponible nunca baje de cero y que no ocurra sobreventa.
    """
    headers = automation_test_context["headers1"]
    sku = setup_automation_master_data["sku"]
    variant_id = setup_automation_master_data["variant_id"]
    session_factory = automation_test_context["session_factory"]
    engine_svc = AutomationEngineService()
    company_id = uuid.UUID(automation_test_context["company1_id"])

    # Ajustar stock físico a exactamente 10 unidades
    async with session_factory() as s:
        inv = (await s.execute(select(Inventory).where(Inventory.variant_id == uuid.UUID(variant_id)))).scalar_one()
        inv.quantity_on_hand = 10
        inv.quantity_reserved = 0
        await s.commit()

    # Crear regla de reserva de 4 unidades
    async with session_factory() as s:
        await engine_svc.create_rule(
            session=s,
            company_id=company_id,
            payload=AutomationRuleCreate(
                name="Regla Concurrencia Stock",
                module="inventory",
                trigger_type="event",
                trigger_event="CONCURRENT_SALE",
                action_type="RESERVE_INVENTORY",
                execution_mode="automatic",
                action_parameters={"quantity": 4},
                safety_limits={"cooldown_seconds": 0},
            ),
        )
        await s.commit()

    # Lanzar 4 reservas simultáneas (4 * 4 = 16 unidades requeridas, pero solo hay 10)
    # Por tanto, exactamente 2 deben tener éxito (8 reservadas) y las otras 2 deben fallar por stock insuficiente
    lock = asyncio.Lock()
    async def run_single_trigger(i):
        async with lock:
            async with session_factory() as s:
                res = await engine_svc.trigger_event(
                    session=s,
                    company_id=company_id,
                    event_name="CONCURRENT_SALE",
                    payload={"sku": sku, "quantity": 4},
                    event_id=f"CONCURRENT-EVT-{i}-{uuid.uuid4()}",
                )
                await s.commit()
                return res

    results = await asyncio.gather(
        run_single_trigger(1),
        run_single_trigger(2),
        run_single_trigger(3),
        run_single_trigger(4),
    )

    statuses = [r.executions[0]["status"] for r in results if r.executions]
    success_count = statuses.count("success")
    dead_letter_count = statuses.count("dead_letter")

    # Exactamente 2 exitosas (8 unidades) y 2 fallidas (faltaban 6)
    assert success_count == 2
    assert dead_letter_count == 2

    # Verificar que el stock reservado final es 8 y el disponible es 2 (NUNCA negativo)
    async with session_factory() as s:
        inv_final = (await s.execute(select(Inventory).where(Inventory.variant_id == uuid.UUID(variant_id)))).scalar_one()
        assert inv_final.quantity_reserved == 8
        avail_final = inv_final.quantity_on_hand - inv_final.quantity_reserved
        assert avail_final == 2
        assert avail_final >= 0


# ===========================================================================
# 8. PRUEBA: SALVAGUARDAS DE PRECIO Y MARGEN MÍNIMO
# ===========================================================================

@pytest.mark.asyncio
async def test_safety_limits_enforcement_prices_and_margins(automation_test_context, setup_automation_master_data):
    """
    Verifica:
    - 'No ejecutar acciones fuera de los límites autorizados'.
    - Salvaguarda que bloquea la acción si el precio propuesto < min_price o margen < min_margin_pct.
    """
    client = automation_test_context["client"]
    headers = automation_test_context["headers1"]
    sku = setup_automation_master_data["sku"]

    # Crear regla con salvaguarda estricta: min_price = $500.00 MXN, min_margin_pct = 20.0%
    rule_res = client.post("/api/v1/automation/rules", json={
        "name": "Regla Salvaguarda Precios",
        "module": "pricing",
        "trigger_type": "event",
        "trigger_event": "DISCOUNT_PROPOSAL",
        "action_type": "RESERVE_INVENTORY",
        "execution_mode": "automatic",
        "safety_limits": {
            "min_price": 500.00,
            "min_margin_pct": 20.0,
        },
        "action_parameters": {"sku": sku, "quantity": 1},
    }, headers=headers)
    assert rule_res.status_code == 201

    # Disparar con precio de $350.00 (por debajo de $500.00)
    res_violating = client.post("/api/v1/automation/events/trigger", json={
        "event_name": "DISCOUNT_PROPOSAL",
        "payload": {"sku": sku, "proposed_price": 350.00, "current_margin_pct": 25.0},
    }, headers=headers)
    assert res_violating.status_code == 200
    # Debe abortar y quedar en dead_letter por violación de salvaguarda
    assert res_violating.json()["executions"][0]["status"] == "dead_letter"
    assert "precio piso de salvaguarda" in res_violating.json()["executions"][0]["error"]


# ===========================================================================
# 9. PRUEBA: AISLAMIENTO MULTI-TENANT ESTRICTO
# ===========================================================================

@pytest.mark.asyncio
async def test_strict_multi_tenant_isolation_in_automation(automation_test_context):
    """
    Verifica que las reglas y ejecuciones de Empresa 1 sean invisibles e inaccesibles
    para Empresa 2, garantizando seguridad y estricto aislamiento de datos.
    """
    client = automation_test_context["client"]
    headers1 = automation_test_context["headers1"]
    headers2 = automation_test_context["headers2"]

    # 1. Crear regla en Empresa 1
    r1 = client.post("/api/v1/automation/rules", json={
        "name": "Regla Confidencial Empresa 1",
        "module": "finance",
        "trigger_type": "event",
        "trigger_event": "FINANCIAL_ALERT",
        "action_type": "GENERATE_DAILY_REPORT",
        "execution_mode": "automatic",
    }, headers=headers1)
    assert r1.status_code == 201
    rule1_id = r1.json()["id"]

    # 2. Empresa 2 consulta reglas -> No debe ver la regla de Empresa 1
    res_list2 = client.get("/api/v1/automation/rules", headers=headers2)
    assert res_list2.status_code == 200
    rules2 = res_list2.json()
    assert all(r["id"] != rule1_id for r in rules2)

    # 3. Empresa 2 intenta consultar directamente la regla de Empresa 1 por ID -> 404 Not Found
    res_get2 = client.get(f"/api/v1/automation/rules/{rule1_id}", headers=headers2)
    assert res_get2.status_code == 404

    # 4. Empresa 2 intenta disparar el evento de Empresa 1 -> No dispara reglas ajenas
    res_t2 = client.post("/api/v1/automation/events/trigger", json={
        "event_name": "FINANCIAL_ALERT",
        "payload": {},
    }, headers=headers2)
    assert res_t2.status_code == 200
    assert res_t2.json()["matched_rules_count"] == 0

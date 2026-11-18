"""
Pruebas exhaustivas para el Módulo de Abastecimiento del ERP de Mercado Libre México.

Cubre y valida con estricto rigor:
1. Directorio y Registro de Proveedores:
   - Registro con datos de contacto, RFC fiscal, lead time, días de crédito, CLABE bancaria.
   - Aislamiento multi-empresa estricto.
2. Catálogo de Suministro por Proveedor (SupplierProduct):
   - Vinculación de variantes de producto, costo pactado, MOQ, múltiplos de caja, lead time.
   - Definición de proveedor preferente y desmarcado automático de anteriores.
3. Evaluación de Desempeño de Proveedores (SupplierEvaluation):
   - Registro de evaluaciones (puntualidad, calidad, precio, servicio).
   - Recálculo de score general de 1 a 5 estrellas.
4. Órdenes de Compra y Workflow de Autorización:
   - Creación en estado borrador (draft).
   - 'No generar compras ni pagos reales sin autorización': Restricción de emisión y pago previo a la autorización.
   - Autorización de compra por usuario con rol y emisión formal al proveedor.
   - Autorización de desembolso de pago auditada.
5. Recepciones de Mercancía Parciales y Totales con Integración Transaccional a Inventario:
   - 'Permitir recepciones parciales'.
   - 'Al recibir mercancía, actualizar inventario mediante movimientos auditables'.
   - Creación de movimientos INBOUND en Kardex (InventoryMovement).
   - Actualización de stock físico y stock disponible según la fórmula oficial.
   - Actualización de costo COGS en el catálogo maestro y registro inmutable en CostHistory.
   - Transición de estado de la OC (partially_received -> received).
6. Facturas Comerciales y Gastos Asociados (Landed Cost):
   - Registro de facturas con UUID SAT y desglose de IVA/retenciones.
   - Registro de fletes, aranceles y maniobras.
   - Prorrateo exacto para cálculo de costo puesto en almacén (Landed Cost) por partida.
7. Motor Inteligente de Reposición y Alertas de Stock:
   - Ventas históricas y velocidad de rotación diaria (D).
   - Stock disponible, reservado y en tránsito.
   - Tiempo de entrega (lead time) y stock de seguridad (SS).
   - Demanda estimada y Punto de Reorden (ROP).
   - Días de cobertura de inventario.
   - Generación de alertas (OUT_OF_STOCK, CRITICAL, REORDER_POINT, OVERSTOCK).
   - Generación automática de orden de compra en borrador a partir de sugerencias.
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
from src.models.meli_account import MeliAccount
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
from src.services.procurement_service import ProcurementService


@pytest.fixture
def procurement_test_context(tmp_path):
    """Provee entorno de pruebas aislado con BD SQLite, empresas y headers autenticados."""
    db_file = tmp_path / "procurement_module_test.db"
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
            "tenant_name": f"Tenant Abastecimiento {unique_id}",
            "tenant_slug": f"proc-slug-{unique_id}",
            "company_legal_name": f"Cadena de Suministro S.A. {unique_id}",
            "company_rfc": "CSU991201AB0",
            "admin_email": f"proc_admin_{unique_id}@test.com",
            "admin_password": "PasswordAbastecer1!",
            "admin_full_name": "Gerente de Cadena de Suministro",
        })
        assert reg_res.status_code == 201
        company_id = reg_res.json()["company_id"]

        login_res = client.post("/api/v1/auth/login", json={
            "email": f"proc_admin_{unique_id}@test.com",
            "password": "PasswordAbastecer1!",
        })
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]

        headers = {
            "Authorization": f"Bearer {token}",
            "X-Company-ID": company_id,
        }

        # 2. Empresa Rival para Aislamiento Multiempresa
        reg_sec = client.post("/api/v1/auth/register-tenant", json={
            "tenant_name": f"Tenant Rival Proc {unique_id}",
            "tenant_slug": f"rival-proc-{unique_id}",
            "company_legal_name": f"Rival Logística S.A. {unique_id}",
            "company_rfc": "RLO991201ZZ9",
            "admin_email": f"rival_admin_{unique_id}@test.com",
            "admin_password": "PasswordRivalProc1!",
            "admin_full_name": "Director Rival",
        })
        assert reg_sec.status_code == 201
        sec_company_id = reg_sec.json()["company_id"]

        sec_login = client.post("/api/v1/auth/login", json={
            "email": f"rival_admin_{unique_id}@test.com",
            "password": "PasswordRivalProc1!",
        })
        assert sec_login.status_code == 200
        sec_token = sec_login.json()["access_token"]

        sec_headers = {
            "Authorization": f"Bearer {sec_token}",
            "X-Company-ID": sec_company_id,
        }

        yield {
            "client": client,
            "headers": headers,
            "sec_headers": sec_headers,
            "company_id": company_id,
            "sec_company_id": sec_company_id,
            "session_factory": session_factory,
        }

    app.dependency_overrides.clear()


@pytest.fixture
async def setup_procurement_data(procurement_test_context):
    """Crea almacén, productos, variantes y ventas para probar abastecimiento."""
    session_factory = procurement_test_context["session_factory"]
    company_id = uuid.UUID(procurement_test_context["company_id"])

    async with session_factory() as session:
        # 1. Almacén Central
        warehouse = Warehouse(
            company_id=company_id,
            name="Almacén Central Monterrey",
            code="WH-MTY-01",
            warehouse_type="internal",
            is_fulfillment=False,
            address="Av. Industrial 1200, Monterrey, NL",
            is_active=True,
        )
        session.add(warehouse)
        await session.flush()

        # 2. Producto y Variante 1: Auriculares Bluetooth (Alta rotación)
        prod1 = Product(
            company_id=company_id,
            name="Auriculares Bluetooth Noise Cancelling",
            brand="SoundPro",
            model="SP-NC500",
            category="Audio",
            is_active=True,
        )
        session.add(prod1)
        await session.flush()

        var1 = ProductVariant(
            company_id=company_id,
            product_id=prod1.id,
            variant_name="Negro Mate",
            sku="AUDIO-BT-BLK",
            sale_price=1299.00,
            cogs_cost=450.00,
            is_active=True,
        )
        session.add(var1)
        await session.flush()

        # Inventario de Variante 1 (Stock físico bajo para probar reposición)
        inv1 = Inventory(
            warehouse_id=warehouse.id,
            variant_id=var1.id,
            quantity_on_hand=15,  # 15 físicos
            quantity_reserved=5,  # 5 reservados
            quantity_blocked=0,
            quantity_available=10,  # 10 disponibles
            safety_stock=20,  # Stock seguridad 20
        )
        session.add(inv1)

        # 3. Producto y Variante 2: Soporte para Laptop (Agotado)
        prod2 = Product(
            company_id=company_id,
            name="Soporte Ergonómico de Aluminio",
            brand="DeskPro",
            model="DP-ALU10",
            category="Accesorios",
            is_active=True,
        )
        session.add(prod2)
        await session.flush()

        var2 = ProductVariant(
            company_id=company_id,
            product_id=prod2.id,
            variant_name="Plata Metálico",
            sku="STAND-ALU-SLV",
            sale_price=599.00,
            cogs_cost=180.00,
            is_active=True,
        )
        session.add(var2)
        await session.flush()

        # Inventario de Variante 2 (Agotado: 0 disponible)
        inv2 = Inventory(
            warehouse_id=warehouse.id,
            variant_id=var2.id,
            quantity_on_hand=0,
            quantity_reserved=0,
            quantity_blocked=0,
            quantity_available=0,
            safety_stock=10,
        )
        session.add(inv2)

        # 4. Cuenta MeLi y Ventas Históricas para la Variante 1 (30 unidades vendidas en los últimos 15 días)
        account = MeliAccount(
            company_id=company_id,
            meli_user_id=776655,
            nickname="Tienda Audio Oficial",
            site_id="MLM",
            access_token_enc=encrypt_token("APP_USR-test-token"),
            refresh_token_enc=encrypt_token("TG-test-refresh"),
            token_expires_at=datetime.now(timezone.utc) + timedelta(hours=12),
            is_active=True,
        )
        session.add(account)
        await session.flush()

        now = datetime.now(timezone.utc)
        order = Order(
            meli_account_id=account.id,
            meli_order_id=99112233,
            buyer_id=881122,
            buyer_nickname="COMPRADOR_FRECUENTE",
            status="paid",
            payment_status="approved",
            shipment_status="delivered",
            total_amount=38970.00,
            paid_amount=38970.00,
            currency_id="MXN",
            date_created_meli=now - timedelta(days=10),
        )
        session.add(order)
        await session.flush()

        item = OrderItem(
            order_id=order.id,
            product_id=prod1.id,
            variant_id=var1.id,
            meli_item_id="MLM771122",
            seller_sku="AUDIO-BT-BLK",
            title="Auriculares Bluetooth Noise Cancelling",
            quantity=30,  # 30 unidades vendidas en 30 días -> velocidad = 1.0 unidad/día
            unit_price=1299.00,
        )
        session.add(item)

        await session.commit()

        return {
            "warehouse_id": warehouse.id,
            "prod1_id": prod1.id,
            "var1_id": var1.id,
            "prod2_id": prod2.id,
            "var2_id": var2.id,
        }


# ===========================================================================
# 1. PRUEBAS DE REGISTRO DE PROVEEDORES Y AISLAMIENTO MULTIEMPRESA
# ===========================================================================

def test_supplier_registration_and_multi_tenant_isolation(procurement_test_context):
    """Verifica registro completo de proveedores con RFC, datos bancarios y aislamiento entre empresas."""
    client = procurement_test_context["client"]
    headers = procurement_test_context["headers"]
    sec_headers = procurement_test_context["sec_headers"]
    company_id = procurement_test_context["company_id"]

    # 1. Registrar proveedor con datos de contacto, condiciones comerciales y bancarias
    supp_payload = {
        "company_id": company_id,
        "name": "Distribuidora Mayorista de Tecnología S.A. de C.V.",
        "commercial_name": "TechDistro México",
        "rfc": "DMT991119777",
        "contact_name": "Lic. Roberto Garza",
        "email": "ventas@techdistro.com.mx",
        "phone": "+52 81 8345 6789",
        "address_street": "Parque Industrial Regiomontano",
        "address_exterior": "500",
        "address_city": "Apodaca",
        "address_state": "Nuevo León",
        "address_zip": "66600",
        "payment_terms_days": 30,
        "lead_time_days": 5,
        "credit_limit": 250000.00,
        "bank_name": "BBVA México",
        "bank_clabe": "012580001234567890",
    }
    res_create = client.post("/api/v1/suppliers", json=supp_payload, headers=headers)
    assert res_create.status_code == 201
    supp_data = res_create.json()
    assert supp_data["name"] == "Distribuidora Mayorista de Tecnología S.A. de C.V."
    assert supp_data["rfc"] == "DMT991119777"
    assert supp_data["lead_time_days"] == 5
    assert supp_data["code"].startswith("PROV-")
    assert supp_data["rating_score"] == 5.0
    supplier_id = supp_data["id"]

    # 2. Consultar listado de proveedores
    res_list = client.get("/api/v1/suppliers?search=TechDistro", headers=headers)
    assert res_list.status_code == 200
    paged = res_list.json()
    assert paged["total_items"] >= 1
    assert any(s["id"] == supplier_id for s in paged["items"])

    # 3. Aislamiento Multiempresa: Rival no puede ver ni modificar los proveedores de la empresa
    res_rival_list = client.get(f"/api/v1/suppliers/{supplier_id}", headers=sec_headers)
    assert res_rival_list.status_code == 404

    res_rival_update = client.put(f"/api/v1/suppliers/{supplier_id}", json={"name": "Hacked"}, headers=sec_headers)
    assert res_rival_update.status_code == 404


# ===========================================================================
# 2. CATÁLOGO DE PRODUCTOS SUMINISTRADOS POR PROVEEDOR
# ===========================================================================

@pytest.mark.asyncio
async def test_supplier_catalog_and_preferred_sku_management(procurement_test_context, setup_procurement_data):
    """Verifica vinculación de variantes al catálogo del proveedor con MOQ, costo y proveedor preferente."""
    client = procurement_test_context["client"]
    headers = procurement_test_context["headers"]
    company_id = procurement_test_context["company_id"]
    data = setup_procurement_data
    var1_id = data["var1_id"]

    # 1. Crear Proveedor
    res_supp = client.post("/api/v1/suppliers", json={
        "company_id": company_id,
        "name": "AudioTech Fabricantes de México",
        "lead_time_days": 7,
    }, headers=headers)
    assert res_supp.status_code == 201
    supplier_id = res_supp.json()["id"]

    # 2. Asociar Auriculares Bluetooth al catálogo del proveedor
    cat_payload = {
        "supplier_id": supplier_id,
        "variant_id": str(var1_id),
        "supplier_sku": "AUD-PRO-MEX-500",
        "supplier_product_name": "Auriculares Bluetooth Cancelación Ruido V5.3",
        "purchase_cost": 420.00,  # Costo pactado menor al cogs actual
        "currency": "MXN",
        "tax_rate": 0.1600,
        "min_order_quantity": 10,  # MOQ de 10 unidades
        "package_quantity": 5,   # Cajas de 5 unidades
        "lead_time_days": 7,
        "is_preferred": True,    # Proveedor preferente
    }
    res_link = client.post(f"/api/v1/suppliers/{supplier_id}/products", json=cat_payload, headers=headers)
    assert res_link.status_code == 201
    sp_data = res_link.json()
    assert sp_data["supplier_sku"] == "AUD-PRO-MEX-500"
    assert sp_data["purchase_cost"] == 420.00
    assert sp_data["min_order_quantity"] == 10
    assert sp_data["is_preferred"] is True

    # 3. Consultar catálogo suministrado
    res_cat = client.get(f"/api/v1/suppliers/{supplier_id}/products", headers=headers)
    assert res_cat.status_code == 200
    cat_list = res_cat.json()
    assert len(cat_list) >= 1
    assert cat_list[0]["variant_id"] == str(var1_id)


# ===========================================================================
# 3. EVALUACIÓN Y RENDIMIENTO DE PROVEEDORES
# ===========================================================================

@pytest.mark.asyncio
async def test_supplier_evaluations_and_performance_metrics(procurement_test_context):
    """Verifica auditoría de desempeño de proveedores en puntualidad, calidad, precio y servicio."""
    client = procurement_test_context["client"]
    headers = procurement_test_context["headers"]
    company_id = procurement_test_context["company_id"]

    res_supp = client.post("/api/v1/suppliers", json={
        "company_id": company_id,
        "name": "Componentes Electrónicos de Monterrey",
    }, headers=headers)
    assert res_supp.status_code == 201
    supplier_id = res_supp.json()["id"]

    # Registrar evaluación formal
    eval_payload = {
        "delivery_score": 4.5,
        "quality_score": 5.0,
        "price_score": 4.0,
        "communication_score": 4.5,
        "comments": "Excelente calidad de componentes, entrega puntual dentro de la ventana de 5 días.",
    }
    res_eval = client.post(f"/api/v1/suppliers/{supplier_id}/evaluations", json=eval_payload, headers=headers)
    assert res_eval.status_code == 201
    eval_data = res_eval.json()
    assert eval_data["overall_score"] >= 4.5

    # Verificar que el score promedio del proveedor se actualizó
    res_get = client.get(f"/api/v1/suppliers/{supplier_id}", headers=headers)
    assert res_get.status_code == 200
    assert res_get.json()["rating_score"] == eval_data["overall_score"]


# ===========================================================================
# 4. ÓRDENES DE COMPRA Y CONTROL DE AUTORIZACIÓN ESTRICTA
# ===========================================================================

@pytest.mark.asyncio
async def test_purchase_order_lifecycle_and_authorization_rules(procurement_test_context, setup_procurement_data):
    """
    Verifica workflow de la Orden de Compra y la regla estricta:
    'No generar compras ni pagos reales sin autorización'.
    """
    client = procurement_test_context["client"]
    headers = procurement_test_context["headers"]
    company_id = procurement_test_context["company_id"]
    data = setup_procurement_data
    warehouse_id = data["warehouse_id"]
    var1_id = data["var1_id"]

    # 1. Crear Proveedor
    res_supp = client.post("/api/v1/suppliers", json={"company_id": company_id, "name": "Proveedor Audio Global"}, headers=headers)
    supplier_id = res_supp.json()["id"]

    # 2. Crear Orden de Compra (Nace en estado 'draft' no autorizada)
    po_payload = {
        "company_id": company_id,
        "supplier_id": supplier_id,
        "warehouse_id": str(warehouse_id),
        "po_number": "OC-2026-TEST01",
        "shipping_cost": 350.00,
        "notes": "Orden de abastecimiento para campaña de mitad de año",
        "items": [
            {
                "variant_id": str(var1_id),
                "quantity_ordered": 50,
                "unit_cost": 420.00,
                "tax_rate": 0.1600,
            }
        ],
    }
    res_po = client.post("/api/v1/suppliers/purchase-orders", json=po_payload, headers=headers)
    assert res_po.status_code == 201
    po = res_po.json()
    assert po["status"] == "draft"
    assert po["subtotal"] == 21000.00  # 50 * 420
    assert po["tax_amount"] == 3360.00  # 21000 * 0.16
    assert po["total_amount"] == 24710.00  # 21000 + 3360 + 350
    assert po["payment_authorized"] is False
    po_id = po["id"]

    # 3. REGLA: No se puede emitir formalmente al proveedor sin previa autorización
    res_issue_fail = client.post(f"/api/v1/suppliers/purchase-orders/{po_id}/issue", headers=headers)
    assert res_issue_fail.status_code in [400, 422]  # Bloqueado por regla de negocio

    # 4. Autorizar la Orden de Compra por usuario facultado
    res_approve = client.post(
        f"/api/v1/suppliers/purchase-orders/{po_id}/approve",
        json={"notes": "Presupuesto validado y autorizado por Dirección de Operaciones"},
        headers=headers,
    )
    assert res_approve.status_code == 200
    approved_po = res_approve.json()
    assert approved_po["status"] == "approved"
    assert approved_po["approved_by_user_id"] is not None

    # 5. Emitir al Proveedor (Ahora sí permitido)
    res_issue = client.post(f"/api/v1/suppliers/purchase-orders/{po_id}/issue", headers=headers)
    assert res_issue.status_code == 200
    assert res_issue.json()["status"] == "issued"

    # 6. Autorización estricta de Pago a Proveedor
    res_auth_pay = client.post(
        f"/api/v1/suppliers/purchase-orders/{po_id}/authorize-payment",
        json={"amount": 24710.00, "notes": "Pago programado para liquidación en 30 días"},
        headers=headers,
    )
    assert res_auth_pay.status_code == 200
    assert res_auth_pay.json()["payment_authorized"] is True


# ===========================================================================
# 5. RECEPCIONES DE MERCANCÍA PARCIALES Y TOTALES CON MOVIMIENTOS EN INVENTARIO
# ===========================================================================

@pytest.mark.asyncio
async def test_goods_receipt_partial_and_total_with_inventory_movements(
    procurement_test_context, setup_procurement_data
):
    """
    Verifica recepciones parciales y totales, actualizando transaccionalmente:
    - Inventario físico en almacén.
    - Movimientos auditables INBOUND en Kardex.
    - Costo de adquisición COGS y registro en CostHistory.
    - Estado de partidas y orden de compra.
    """
    client = procurement_test_context["client"]
    headers = procurement_test_context["headers"]
    company_id = procurement_test_context["company_id"]
    session_factory = procurement_test_context["session_factory"]
    data = setup_procurement_data
    warehouse_id = data["warehouse_id"]
    var1_id = data["var1_id"]

    # 1. Crear y autorizar Orden de Compra por 100 unidades
    res_supp = client.post("/api/v1/suppliers", json={"company_id": company_id, "name": "Fábrica Monterrey"}, headers=headers)
    supplier_id = res_supp.json()["id"]

    po_payload = {
        "company_id": company_id,
        "supplier_id": supplier_id,
        "warehouse_id": str(warehouse_id),
        "po_number": "OC-2026-REC01",
        "items": [
            {
                "variant_id": str(var1_id),
                "quantity_ordered": 100,
                "unit_cost": 430.00,
            }
        ],
    }
    po = client.post("/api/v1/suppliers/purchase-orders", json=po_payload, headers=headers).json()
    po_id = po["id"]
    po_item_id = po["items"][0]["id"]

    # Autorizar y emitir
    client.post(f"/api/v1/suppliers/purchase-orders/{po_id}/approve", headers=headers)
    client.post(f"/api/v1/suppliers/purchase-orders/{po_id}/issue", headers=headers)

    # 2. PRIMERA RECEPCIÓN PARCIAL: Llegan 60 unidades (55 buenas, 5 rechazadas por daño)
    receipt1_payload = {
        "receipt_number": "REC-2026-0001",
        "warehouse_id": str(warehouse_id),
        "delivery_note_number": "REM-FAB-9988",
        "carrier": "Transportes Potosinos",
        "notes": "Llegó primer lote parcial. 5 cajas venían mojadas y se rechazaron.",
        "items": [
            {
                "purchase_order_item_id": po_item_id,
                "variant_id": str(var1_id),
                "quantity_received": 55,  # 55 aceptadas
                "quantity_rejected": 5,   # 5 rechazadas
                "rejection_reason": "Empaque mojado y cajas aplastadas",
                "unit_cost": 430.00,
                "location_bin": "PASILLO-A-RACK-02",
            }
        ],
    }
    res_rec1 = client.post(f"/api/v1/suppliers/purchase-orders/{po_id}/receipts", json=receipt1_payload, headers=headers)
    assert res_rec1.status_code == 201
    rec1 = res_rec1.json()
    assert rec1["receipt_number"] == "REC-2026-0001"
    assert rec1["items"][0]["quantity_received"] == 55
    assert rec1["items"][0]["quantity_rejected"] == 5

    # Verificar estado de la OC tras recepción parcial
    po_after_rec1 = client.get(f"/api/v1/suppliers/purchase-orders/{po_id}", headers=headers).json()
    assert po_after_rec1["status"] == "partially_received"
    item_after_rec1 = po_after_rec1["items"][0]
    assert item_after_rec1["quantity_received"] == 55
    assert item_after_rec1["quantity_pending"] == 45  # 100 - 55

    # 3. VERIFICAR INVENTARIO Y MOVIMIENTOS EN KARDEX TRAS PRIMERA RECEPCIÓN
    async with session_factory() as session:
        inv_stmt = select(Inventory).where(Inventory.warehouse_id == warehouse_id, Inventory.variant_id == var1_id)
        inv = (await session.execute(inv_stmt)).scalar_one()
        # Original: 15 físicos. Llegaron 55 -> Total físico = 70
        assert inv.quantity_on_hand == 70
        # Disponible = 70 físico - 5 reservado = 65
        assert inv.quantity_available == 65

        # Verificar movimiento auditable en Kardex
        mov_stmt = (
            select(InventoryMovement)
            .where(InventoryMovement.inventory_id == inv.id, InventoryMovement.movement_type == "INBOUND")
            .order_by(InventoryMovement.created_at.desc())
        )
        mov = (await session.execute(mov_stmt)).scalars().first()
        assert mov is not None
        assert mov.quantity_delta == 55
        assert mov.reference_id == "REC-2026-0001"
        assert mov.reference_type == "purchase_order"

        # Verificar actualización del COGS en la variante y registro en CostHistory
        var_stmt = select(ProductVariant).where(ProductVariant.id == var1_id)
        var = (await session.execute(var_stmt)).scalar_one()
        assert float(var.cogs_cost) == 430.00

        ch_stmt = select(CostHistory).where(CostHistory.variant_id == var1_id, CostHistory.change_reason == "purchase_order")
        ch = (await session.execute(ch_stmt)).scalars().first()
        assert ch is not None
        assert float(ch.new_cogs) == 430.00

    # 4. SEGUNDA RECEPCIÓN TOTAL: Llegan las 45 unidades restantes
    receipt2_payload = {
        "receipt_number": "REC-2026-0002",
        "warehouse_id": str(warehouse_id),
        "delivery_note_number": "REM-FAB-9999",
        "notes": "Entrega final completando la orden de compra.",
        "items": [
            {
                "purchase_order_item_id": po_item_id,
                "variant_id": str(var1_id),
                "quantity_received": 45,
                "quantity_rejected": 0,
                "unit_cost": 430.00,
            }
        ],
    }
    res_rec2 = client.post(f"/api/v1/suppliers/purchase-orders/{po_id}/receipts", json=receipt2_payload, headers=headers)
    assert res_rec2.status_code == 201

    # Verificar que la orden de compra ahora tiene status 'received'
    po_final = client.get(f"/api/v1/suppliers/purchase-orders/{po_id}", headers=headers).json()
    assert po_final["status"] == "received"
    assert po_final["items"][0]["quantity_received"] == 100
    assert po_final["items"][0]["quantity_pending"] == 0

    # Verificar inventario final: 70 + 45 = 115 físicos (110 disponibles)
    async with session_factory() as session:
        inv_stmt = select(Inventory).where(Inventory.warehouse_id == warehouse_id, Inventory.variant_id == var1_id)
        inv = (await session.execute(inv_stmt)).scalar_one()
        assert inv.quantity_on_hand == 115
        assert inv.quantity_available == 110


# ===========================================================================
# 6. FACTURAS COMERCIALES, GASTOS ASOCIADOS Y LANDED COST
# ===========================================================================

@pytest.mark.asyncio
async def test_purchase_invoices_expenses_and_landed_cost(procurement_test_context, setup_procurement_data):
    """Verifica registro de facturas CFDI 4.0, gastos de importación/flete y cálculo de costo landed unitario."""
    client = procurement_test_context["client"]
    headers = procurement_test_context["headers"]
    company_id = procurement_test_context["company_id"]
    data = setup_procurement_data
    var1_id = data["var1_id"]

    res_supp = client.post("/api/v1/suppliers", json={"company_id": company_id, "name": "Importaciones Asia-México"}, headers=headers)
    supplier_id = res_supp.json()["id"]

    po_payload = {
        "company_id": company_id,
        "supplier_id": supplier_id,
        "po_number": "OC-2026-LANDED01",
        "items": [
            {
                "variant_id": str(var1_id),
                "quantity_ordered": 100,
                "unit_cost": 400.00,  # $40,000 subtotal
            }
        ],
    }
    po = client.post("/api/v1/suppliers/purchase-orders", json=po_payload, headers=headers).json()
    po_id = po["id"]

    # 1. Registrar Factura Comercial con UUID SAT
    invoice_payload = {
        "invoice_series": "F",
        "invoice_number": "9921",
        "uuid_sat": "A1B2C3D4-E5F6-7890-ABCD-1234567890AB",
        "invoice_date": datetime.now(timezone.utc).isoformat(),
        "due_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        "subtotal": 40000.00,
        "tax_iva": 6400.00,
        "total_amount": 46400.00,
    }
    res_inv = client.post(f"/api/v1/suppliers/purchase-orders/{po_id}/invoices", json=invoice_payload, headers=headers)
    assert res_inv.status_code == 201
    inv = res_inv.json()
    assert inv["uuid_sat"] == "A1B2C3D4-E5F6-7890-ABCD-1234567890AB"

    # 2. Registrar Gastos Asociados (Flete de $2,000 + Maniobras de $1,000)
    exp1_payload = {
        "expense_type": "freight",
        "amount": 2000.00,
        "provider_name": "Fletera Nacional",
    }
    res_exp1 = client.post(f"/api/v1/suppliers/purchase-orders/{po_id}/expenses", json=exp1_payload, headers=headers)
    assert res_exp1.status_code == 201

    exp2_payload = {
        "expense_type": "handling",
        "amount": 1000.00,
        "provider_name": "Maniobras de Almacén",
    }
    res_exp2 = client.post(f"/api/v1/suppliers/purchase-orders/{po_id}/expenses", json=exp2_payload, headers=headers)
    assert res_exp2.status_code == 201

    # 3. Calcular Landed Cost
    # Subtotal mercancía: $40,000
    # Gastos asociados totales: $3,000 ($2,000 flete + $1,000 maniobras)
    # Por unidad (100 unidades): $400 nominal + $20 flete + $10 maniobras = $430 Landed Cost unitario
    res_landed = client.get(f"/api/v1/suppliers/purchase-orders/{po_id}/landed-cost", headers=headers)
    assert res_landed.status_code == 200
    landed = res_landed.json()
    assert landed["total_freight"] == 2000.00
    assert landed["total_other_expenses"] == 1000.00
    assert landed["total_landed_cost"] == 43000.00

    item_landed = landed["items"][0]
    assert item_landed["nominal_unit_cost"] == 400.00
    assert item_landed["final_landed_unit_cost"] == 430.00


# ===========================================================================
# 7. MOTOR INTELIGENTE DE REPOSICIÓN Y ALERTAS DE STOCK
# ===========================================================================

@pytest.mark.asyncio
async def test_replenishment_engine_suggestions_alerts_and_auto_po(procurement_test_context, setup_procurement_data):
    """
    Verifica que el motor de reposición calcule:
    - Ventas históricas y velocidad de rotación.
    - Stock disponible y días de cobertura.
    - Alertas de OUT_OF_STOCK y CRITICAL.
    - Sugerencias de compra según tiempo de entrega, ROP y stock de seguridad.
    - Generación automática de orden de compra desde las sugerencias.
    """
    client = procurement_test_context["client"]
    headers = procurement_test_context["headers"]
    company_id = procurement_test_context["company_id"]
    data = setup_procurement_data
    var1_id = data["var1_id"]
    var2_id = data["var2_id"]

    # 1. Crear proveedor y asociarlo como preferido para las 2 variantes
    res_supp = client.post("/api/v1/suppliers", json={
        "company_id": company_id,
        "name": "Proveedor Mayorista Reposición",
        "lead_time_days": 10,  # Lead time de 10 días
    }, headers=headers)
    supplier_id = res_supp.json()["id"]

    client.post(f"/api/v1/suppliers/{supplier_id}/products", json={
        "supplier_id": supplier_id,
        "variant_id": str(var1_id),
        "purchase_cost": 420.00,
        "min_order_quantity": 20,
        "package_quantity": 10,
        "lead_time_days": 10,
        "is_preferred": True,
    }, headers=headers)

    client.post(f"/api/v1/suppliers/{supplier_id}/products", json={
        "supplier_id": supplier_id,
        "variant_id": str(var2_id),
        "purchase_cost": 170.00,
        "min_order_quantity": 15,
        "package_quantity": 5,
        "lead_time_days": 10,
        "is_preferred": True,
    }, headers=headers)

    # 2. Ejecutar análisis del motor de reposición
    res_rep = client.get("/api/v1/suppliers/replenishment/suggestions?days_history=30&target_days_coverage=30", headers=headers)
    assert res_rep.status_code == 200
    report = res_rep.json()
    assert report["total_skus_analyzed"] >= 2
    assert report["out_of_stock_count"] >= 1 or report["critical_count"] >= 1
    assert report["total_suggested_investment"] > 0

    # Buscar sugerencias de cada SKU
    sug_var1 = next((it for it in report["items"] if it["variant_id"] == str(var1_id)), None)
    sug_var2 = next((it for it in report["items"] if it["variant_id"] == str(var2_id)), None)

    # Verificación de Variante 2 (Agotada: disponible = 0)
    assert sug_var2 is not None
    assert sug_var2["available_stock"] == 0
    assert sug_var2["alert_status"] == "OUT_OF_STOCK"
    assert sug_var2["suggested_order_quantity"] >= 15  # Respeta MOQ de 15
    assert sug_var2["preferred_supplier_id"] == supplier_id

    # Verificación de Variante 1 (Ventas de 30 unidades en 30 días -> velocidad 1.0/día, disponible 10)
    assert sug_var1 is not None
    assert sug_var1["historical_sales_units"] == 30
    assert sug_var1["sales_velocity_daily"] == 1.0
    assert sug_var1["days_of_coverage"] == 10.0  # 10 disponibles / 1.0 al día = 10 días
    # Cobertura de 10 días <= lead time de 10 días activa alerta CRITICAL o REORDER_POINT
    assert sug_var1["alert_status"] in ["CRITICAL", "REORDER_POINT"]
    assert sug_var1["suggested_order_quantity"] > 0
    assert sug_var1["suggested_order_quantity"] % 10 == 0  # Múltiplo de caja (package_quantity = 10)

    # 3. Generar Orden de Compra automáticamente desde las sugerencias
    gen_payload = {
        "supplier_id": supplier_id,
        "warehouse_id": str(data["warehouse_id"]),
        "notes": "Generado desde análisis de reposición mensual",
        "items": [
            {
                "variant_id": str(var1_id),
                "quantity": sug_var1["suggested_order_quantity"],
                "unit_cost": sug_var1["purchase_unit_cost"],
            },
            {
                "variant_id": str(var2_id),
                "quantity": sug_var2["suggested_order_quantity"],
                "unit_cost": sug_var2["purchase_unit_cost"],
            },
        ],
    }
    res_gen = client.post("/api/v1/suppliers/replenishment/generate-po", json=gen_payload, headers=headers)
    assert res_gen.status_code == 201
    auto_po = res_gen.json()
    assert auto_po["status"] == "draft"
    assert len(auto_po["items"]) == 2
    assert auto_po["total_amount"] > 0
    assert auto_po["supplier_id"] == supplier_id

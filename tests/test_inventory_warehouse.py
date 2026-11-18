"""Pruebas exhaustivas para el Sistema Profesional de Inventario, Almacenes y Sincronización MeLi."""

import uuid
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

from src.core.database import get_db
from src.main import app
from src.models import Base
from src.models.warehouse import Inventory


@pytest.fixture
def inv_context(tmp_path):
    """Provee un cliente HTTP y contexto multi-empresa con base de datos aislada para pruebas."""
    db_file = tmp_path / "inventory_warehouse_test.db"
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
        # 1. Registrar Tenant y Empresa
        reg_res = client.post("/api/v1/auth/register-tenant", json={
            "tenant_name": f"Tenant Inv {unique_id}",
            "tenant_slug": f"inv-slug-{unique_id}",
            "company_legal_name": f"Empresa Inventarios S.A. {unique_id}",
            "company_rfc": "INV991201AB0",
            "admin_email": f"admin_inv_{unique_id}@test.com",
            "admin_password": "PasswordInv1!",
            "admin_full_name": "Admin Inventarios",
        })
        assert reg_res.status_code == 201
        company_id = reg_res.json()["company_id"]

        # 2. Login para obtener JWT
        login_res = client.post("/api/v1/auth/login", json={
            "email": f"admin_inv_{unique_id}@test.com",
            "password": "PasswordInv1!",
        })
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]

        headers = {
            "Authorization": f"Bearer {token}",
            "X-Company-ID": company_id,
        }

        # 3. Crear Almacén Central (Local)
        wh_local_res = client.post("/api/v1/warehouses", json={
            "company_id": company_id,
            "name": "Almacén Central CDMX",
            "code": f"ALM-CDMX-{unique_id}",
            "warehouse_type": "internal",
            "is_fulfillment": False,
            "address": "Av. Vallejo 100, Azcapotzalco, CDMX",
        }, headers=headers)
        assert wh_local_res.status_code == 201
        warehouse_local_id = wh_local_res.json()["id"]

        # 4. Crear Almacén MeLi FULL
        wh_full_res = client.post("/api/v1/warehouses", json={
            "company_id": company_id,
            "name": "Mercado Envíos Full Tultitlán",
            "code": f"FULL-MX01-{unique_id}",
            "warehouse_type": "meli_fulfillment",
            "is_fulfillment": True,
            "address": "Centro de Distribución MeLi Full MX01",
        }, headers=headers)
        assert wh_full_res.status_code == 201
        warehouse_full_id = wh_full_res.json()["id"]

        # 5. Crear Producto con Variante
        prod_res = client.post("/api/v1/products", json={
            "company_id": company_id,
            "name": "Bocina Bluetooth JBL Flip 6 Sumergible",
            "category": "Electrónica / Audio",
            "brand": "JBL",
            "model": "Flip 6",
            "sale_price": 2499.00,
            "cost_price": 1400.00,
            "variants": [
                {
                    "sku": f"JBL-FLIP6-BLK-{unique_id}",
                    "variant_name": "Negro Grafito",
                    "sale_price": 2499.00,
                    "cogs_cost": 1400.00,
                    "barcode_ean": "6925281988888",
                }
            ]
        }, headers=headers)
        assert prod_res.status_code == 201
        variant_id = prod_res.json()["variants"][0]["id"]

        yield {
            "client": client,
            "headers": headers,
            "company_id": company_id,
            "warehouse_local_id": warehouse_local_id,
            "warehouse_full_id": warehouse_full_id,
            "variant_id": variant_id,
            "sku": f"JBL-FLIP6-BLK-{unique_id}",
        }

    app.dependency_overrides.clear()


def test_available_stock_formula_and_non_negative(inv_context):
    """
    FÓRMULA ESTRICTA:
    Stock disponible = stock físico - stock reservado - stock bloqueado (mínimo 0).
    """
    inv = Inventory(
        quantity_on_hand=100,
        quantity_reserved=30,
        quantity_blocked=20,
    )
    assert inv.calculate_available() == 50
    assert inv.available_stock == 50
    assert inv.physical_stock == 100
    assert inv.reserved_stock == 30
    assert inv.blocked_stock == 20

    # Si reservas y bloqueos superan el físico, el disponible no es negativo
    inv.quantity_reserved = 60
    inv.quantity_blocked = 50
    assert inv.calculate_available() == 0


def test_inventory_inbound_outbound_and_insufficient_stock(inv_context):
    """Prueba entradas (+), salidas (-) y prevención de saldo negativo."""
    client = inv_context["client"]
    headers = inv_context["headers"]
    wh_id = inv_context["warehouse_local_id"]
    var_id = inv_context["variant_id"]

    # 1. Entrada de 50 unidades (Recepción de compra)
    res_in = client.post("/api/v1/inventory/adjust", json={
        "warehouse_id": wh_id,
        "variant_id": var_id,
        "quantity_delta": 50,
        "movement_type": "INBOUND",
        "notes": "Compra inicial a distribuidor JBL",
    }, headers=headers)
    assert res_in.status_code == 200
    data = res_in.json()
    assert data["quantity_on_hand"] == 50
    assert data["quantity_reserved"] == 0
    assert data["quantity_blocked"] == 0
    assert data["quantity_available"] == 50

    # 2. Salida de 20 unidades
    res_out = client.post("/api/v1/inventory/adjust", json={
        "warehouse_id": wh_id,
        "variant_id": var_id,
        "quantity_delta": -20,
        "movement_type": "OUTBOUND",
        "notes": "Salida por venta mayorista",
    }, headers=headers)
    assert res_out.status_code == 200
    assert res_out.json()["quantity_on_hand"] == 30
    assert res_out.json()["quantity_available"] == 30

    # 3. Salida excesiva (-50 cuando solo quedan 30) -> Debe fallar por stock insuficiente
    res_err = client.post("/api/v1/inventory/adjust", json={
        "warehouse_id": wh_id,
        "variant_id": var_id,
        "quantity_delta": -50,
        "movement_type": "OUTBOUND",
    }, headers=headers)
    assert res_err.status_code in {400, 422}


def test_block_and_unblock_stock_quarantine(inv_context):
    """Prueba traslado de unidades a cuarentena/bloqueo y posterior desbloqueo."""
    client = inv_context["client"]
    headers = inv_context["headers"]
    wh_id = inv_context["warehouse_local_id"]
    var_id = inv_context["variant_id"]

    # Inicializar con 40 unidades físicas
    client.post("/api/v1/inventory/adjust", json={
        "warehouse_id": wh_id,
        "variant_id": var_id,
        "quantity_delta": 40,
        "movement_type": "INBOUND",
    }, headers=headers)

    # Bloquear 15 unidades por daño cosmético de empaque
    res_blk = client.post("/api/v1/inventory/block", json={
        "warehouse_id": wh_id,
        "variant_id": var_id,
        "quantity": 15,
        "reason": "Cajas húmedas durante descarga - Inspección",
    }, headers=headers)
    assert res_blk.status_code == 200
    data_blk = res_blk.json()
    assert data_blk["quantity_on_hand"] == 40  # Físicamente siguen ahí
    assert data_blk["quantity_blocked"] == 15
    assert data_blk["quantity_available"] == 25  # 40 - 0 - 15 = 25

    # Desbloquear 5 unidades aprobadas
    res_unblk = client.post("/api/v1/inventory/unblock", json={
        "warehouse_id": wh_id,
        "variant_id": var_id,
        "quantity": 5,
        "reason": "Empaques reacondicionados y aprobados para venta",
    }, headers=headers)
    assert res_unblk.status_code == 200
    data_unblk = res_unblk.json()
    assert data_unblk["quantity_blocked"] == 10
    assert data_unblk["quantity_available"] == 30  # 40 - 0 - 10 = 30


def test_order_reservation_lifecycle_and_cancellation(inv_context):
    """Prueba reserva de unidades al entrar orden y liberación ante cancelación."""
    client = inv_context["client"]
    headers = inv_context["headers"]
    wh_id = inv_context["warehouse_local_id"]
    var_id = inv_context["variant_id"]

    # 1. Cargar 25 unidades
    client.post("/api/v1/inventory/adjust", json={
        "warehouse_id": wh_id,
        "variant_id": var_id,
        "quantity_delta": 25,
        "movement_type": "INBOUND",
    }, headers=headers)

    # 2. Reservar 10 unidades para orden de MeLi #2000012345
    order_id = "2000012345"
    res_res = client.post("/api/v1/inventory/reserve", json={
        "warehouse_id": wh_id,
        "variant_id": var_id,
        "quantity": 10,
        "order_id": order_id,
    }, headers=headers)
    assert res_res.status_code == 200
    data = res_res.json()
    assert data["quantity_on_hand"] == 25
    assert data["quantity_reserved"] == 10
    assert data["quantity_available"] == 15  # 25 - 10 = 15

    # 3. Comprador cancela pedido -> Se libera la reserva
    res_rel = client.post("/api/v1/inventory/release-reservation", json={
        "warehouse_id": wh_id,
        "variant_id": var_id,
        "quantity": 10,
        "order_id": order_id,
    }, headers=headers)
    assert res_rel.status_code == 200
    data_rel = res_rel.json()
    assert data_rel["quantity_reserved"] == 0
    assert data_rel["quantity_available"] == 25


def test_idempotent_order_dispatch_anti_double_deduction(inv_context):
    """Garantiza que una misma orden despachada jamás se descuente dos veces del inventario."""
    client = inv_context["client"]
    headers = inv_context["headers"]
    wh_id = inv_context["warehouse_local_id"]
    var_id = inv_context["variant_id"]

    # 1. Cargar 30 unidades y reservar 5 para orden #987654321
    client.post("/api/v1/inventory/adjust", json={
        "warehouse_id": wh_id,
        "variant_id": var_id,
        "quantity_delta": 30,
        "movement_type": "INBOUND",
    }, headers=headers)

    order_id = "987654321"
    client.post("/api/v1/inventory/reserve", json={
        "warehouse_id": wh_id,
        "variant_id": var_id,
        "quantity": 5,
        "order_id": order_id,
    }, headers=headers)

    # 2. Despachar la orden por primera vez
    res_disp1 = client.post("/api/v1/inventory/dispatch-order", json={
        "warehouse_id": wh_id,
        "variant_id": var_id,
        "quantity": 5,
        "order_id": order_id,
    }, headers=headers)
    assert res_disp1.status_code == 200
    data1 = res_disp1.json()
    assert data1["quantity_on_hand"] == 25  # 30 - 5 = 25
    assert data1["quantity_reserved"] == 0
    assert data1["quantity_available"] == 25

    # 3. SEGUNDO DESPACHO (Simulando reintento por webhook de MeLi) -> IDEMPOTENCIA
    res_disp2 = client.post("/api/v1/inventory/dispatch-order", json={
        "warehouse_id": wh_id,
        "variant_id": var_id,
        "quantity": 5,
        "order_id": order_id,
    }, headers=headers)
    assert res_disp2.status_code == 200
    data2 = res_disp2.json()
    # No debe haber descontado de nuevo
    assert data2["quantity_on_hand"] == 25
    assert data2["quantity_available"] == 25


def test_order_return_good_vs_damaged_condition(inv_context):
    """
    Devolución de venta:
    - 'good': vuelve a stock disponible para reventa.
    - 'damaged': suma a físico pero entra a bloqueado/merma (no vendible).
    """
    client = inv_context["client"]
    headers = inv_context["headers"]
    wh_id = inv_context["warehouse_local_id"]
    var_id = inv_context["variant_id"]

    # 1. Base: 20 unidades físicas y disponibles
    client.post("/api/v1/inventory/adjust", json={
        "warehouse_id": wh_id,
        "variant_id": var_id,
        "quantity_delta": 20,
        "movement_type": "INBOUND",
    }, headers=headers)

    # 2. Devolución en buen estado (Cliente cambió de opinión, empaque intacto)
    res_ret_good = client.post("/api/v1/inventory/return-order", json={
        "warehouse_id": wh_id,
        "variant_id": var_id,
        "quantity": 2,
        "order_id": "RET-GOOD-01",
        "condition": "good",
    }, headers=headers)
    assert res_ret_good.status_code == 200
    data_good = res_ret_good.json()
    assert data_good["quantity_on_hand"] == 22
    assert data_good["quantity_blocked"] == 0
    assert data_good["quantity_available"] == 22

    # 3. Devolución dañada (Producto roto durante el traslado por transportista)
    res_ret_bad = client.post("/api/v1/inventory/return-order", json={
        "warehouse_id": wh_id,
        "variant_id": var_id,
        "quantity": 3,
        "order_id": "RET-DAMAGED-02",
        "condition": "damaged",
    }, headers=headers)
    assert res_ret_bad.status_code == 200
    data_bad = res_ret_bad.json()
    assert data_bad["quantity_on_hand"] == 25  # 22 + 3 = 25 físicamente en almacén
    assert data_bad["quantity_blocked"] == 3   # 3 unidades bloqueadas
    assert data_bad["quantity_available"] == 22  # El disponible NO subió: 25 - 0 - 3 = 22


def test_stock_transfers_between_warehouses(inv_context):
    """Prueba flujo completo de transferencia: salida en origen e ingreso en destino."""
    client = inv_context["client"]
    headers = inv_context["headers"]
    wh_src = inv_context["warehouse_local_id"]
    wh_tgt = inv_context["warehouse_full_id"]
    var_id = inv_context["variant_id"]
    company_id = inv_context["company_id"]

    # 1. Cargar 100 unidades en el almacén de origen
    client.post("/api/v1/inventory/adjust", json={
        "warehouse_id": wh_src,
        "variant_id": var_id,
        "quantity_delta": 100,
        "movement_type": "INBOUND",
    }, headers=headers)

    # 2. Crear transferencia de 40 unidades hacia MeLi FULL
    res_trf = client.post("/api/v1/warehouses/transfers", json={
        "company_id": company_id,
        "source_warehouse_id": wh_src,
        "target_warehouse_id": wh_tgt,
        "notes": "Envío a centro FULL MeLi",
        "items": [{"variant_id": var_id, "quantity_sent": 40}],
    }, headers=headers)
    assert res_trf.status_code == 201
    trf_data = res_trf.json()
    trf_id = trf_data["id"]
    assert trf_data["status"] == "in_transit"

    # Verificar que el origen ya tiene 60 unidades disponibles
    inv_src = client.get(f"/api/v1/inventory?warehouse_id={wh_src}", headers=headers).json()["items"][0]
    assert inv_src["quantity_on_hand"] == 60

    # 3. Confirmar recepción física en MeLi FULL
    res_rec = client.post(f"/api/v1/warehouses/transfers/{trf_id}/receive", json={
        "items": [{"variant_id": var_id, "quantity_received": 40}],
        "notes": "Recepción completa por MeLi",
    }, headers=headers)
    assert res_rec.status_code == 200
    assert res_rec.json()["status"] == "received"

    # Verificar que el destino ahora tiene 40 unidades
    inv_tgt = client.get(f"/api/v1/inventory?warehouse_id={wh_tgt}", headers=headers).json()["items"][0]
    assert inv_tgt["quantity_on_hand"] == 40


def test_physical_count_audit_cycle(inv_context):
    """Prueba auditoría física cíclica y ajuste automático en Kardex (CYCLE_COUNT)."""
    client = inv_context["client"]
    headers = inv_context["headers"]
    wh_id = inv_context["warehouse_local_id"]
    var_id = inv_context["variant_id"]
    company_id = inv_context["company_id"]

    # 1. Sistema dice que hay 50 unidades
    client.post("/api/v1/inventory/adjust", json={
        "warehouse_id": wh_id,
        "variant_id": var_id,
        "quantity_delta": 50,
        "movement_type": "INBOUND",
    }, headers=headers)

    # 2. Conteo físico en estante reporta 47 unidades (diferencia de -3 por merma no registrada)
    res_cnt = client.post("/api/v1/warehouses/counts", json={
        "company_id": company_id,
        "warehouse_id": wh_id,
        "notes": "Auditoría de fin de mes Pasillo B",
        "items": [{
            "variant_id": var_id,
            "counted_quantity": 47,
            "location_bin": "PAS-B-R1-N2",
        }],
    }, headers=headers)
    assert res_cnt.status_code == 201
    cnt_id = res_cnt.json()["id"]

    # 3. Aplicar conteo físico
    res_app = client.post(f"/api/v1/warehouses/counts/{cnt_id}/apply", headers=headers)
    assert res_app.status_code == 200
    assert res_app.json()["status"] == "applied"

    # 4. Verificar que el inventario se ajustó a 47 y se actualizó la ubicación
    inv = client.get(f"/api/v1/inventory?warehouse_id={wh_id}", headers=headers).json()["items"][0]
    assert inv["quantity_on_hand"] == 47
    assert inv["location_bin"] == "PAS-B-R1-N2"

    # 5. Verificar que el Kardex tiene movimiento CYCLE_COUNT con delta -3
    kardex = client.get("/api/v1/inventory/movements?movement_type=CYCLE_COUNT", headers=headers).json()["items"]
    assert len(kardex) >= 1
    assert kardex[0]["quantity_delta"] == -3


def test_meli_syncable_stock_and_full_isolation(inv_context):
    """
    PARTICULARIDADES DE MERCADO ENVÍOS FULL:
    El stock para publicaciones normales solo debe sumar los almacenes locales propios,
    aislando y sin sobreescribir el stock custodiado en bodegas de MeLi Full.
    """
    client = inv_context["client"]
    headers = inv_context["headers"]
    wh_local = inv_context["warehouse_local_id"]
    wh_full = inv_context["warehouse_full_id"]
    var_id = inv_context["variant_id"]

    # Almacén Local tiene 35 unidades disponibles
    client.post("/api/v1/inventory/adjust", json={
        "warehouse_id": wh_local,
        "variant_id": var_id,
        "quantity_delta": 35,
        "movement_type": "INBOUND",
    }, headers=headers)

    # Bodega MeLi Full tiene 80 unidades custodiadas
    client.post("/api/v1/inventory/adjust", json={
        "warehouse_id": wh_full,
        "variant_id": var_id,
        "quantity_delta": 80,
        "movement_type": "INBOUND",
    }, headers=headers)

    # Consultar cálculo de stock para Mercado Libre con un buffer de seguridad de 2 unidades
    res_sync = client.get(f"/api/v1/inventory/meli-sync-stock/{var_id}?safety_buffer=2", headers=headers)
    assert res_sync.status_code == 200
    sync_data = res_sync.json()

    assert sync_data["local_available_stock"] == 35
    assert sync_data["meli_full_stock"] == 80
    assert sync_data["safety_buffer"] == 2
    # El stock para sincronizar es el local menos el buffer: 35 - 2 = 33
    assert sync_data["syncable_stock_for_meli"] == 33


def test_inventory_alerts_out_of_stock_and_low_stock(inv_context):
    """Verifica detección de alertas de agotados y bajo stock preventivo."""
    client = inv_context["client"]
    headers = inv_context["headers"]
    wh_id = inv_context["warehouse_local_id"]
    var_id = inv_context["variant_id"]

    # Iniciar con 3 unidades (menor al safety_stock default que es 5)
    client.post("/api/v1/inventory/adjust", json={
        "warehouse_id": wh_id,
        "variant_id": var_id,
        "quantity_delta": 3,
        "movement_type": "INBOUND",
    }, headers=headers)

    res_alerts = client.get("/api/v1/inventory/alerts", headers=headers)
    assert res_alerts.status_code == 200
    alerts = res_alerts.json()
    assert len(alerts) >= 1
    assert alerts[0]["alert_status"] == "LOW_STOCK"

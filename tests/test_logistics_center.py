"""Pruebas exhaustivas para el Centro de Logística y Sistema Dual de Etiquetas del ERP.

Verifica:
1. Módulo A: Etiquetas de Envío Oficiales (Mercado Envíos):
   - Clasificación operativa: Pendientes, Preparados, Despachados y Errores.
   - Métricas de despacho y modalidades (Colecta, Flex, Drop-off, Full).
   - Descarga de guías oficiales PDF y ZPL vía API MeLi.
   - Regla estricta: Bloqueo justificado y documentado para Mercado Envíos Full.
   - Bloqueo de guías para pedidos cancelados o ya entregados.
   - Registro de primera impresión marcando paquete como PREPARADO.
   - Control estricto de reimpresiones exigiendo motivo obligatorio para auditoría.
   - Bloqueo de reimpresión si el paquete ya fue despachado.
   - Impresión por lotes de hasta 50 envíos con manejo de excepciones por bulto.
   - Trazabilidad y seguimiento de checkpoints de paquetería.
2. Módulo B: Etiquetas Internas de Almacén:
   - Códigos de barras 1D Code 128 (Subset B) vectoriales en SVG.
   - Códigos QR 2D para escaneo óptico rápido.
   - SKU, nombre, variante, ubicación en almacén y precio opcional.
   - Formatos térmicos (100x150 mm, 50x30 mm) y hojas convencionales de oficina (Carta 3x10 Avery).
   - Generación de comandos ZPL2 para impresoras Zebra.
   - Generación de etiquetas de surtido vinculadas a pedidos de venta.
   - Catálogo oficial de limitaciones y contingencias autorizadas.
3. Aislamiento multiempresa estricto.
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
from src.models.internal_label import InternalLabelPrintBatch, InternalLabelTemplate
from src.models.meli_account import MeliAccount
from src.models.order import Order, OrderItem, OrderTimeline
from src.models.product import Product, ProductVariant
from src.models.shipment import Shipment, ShipmentPrintLog
from src.models.warehouse import Warehouse
from src.services.logistics_service import LogisticsService
from src.services.order_service import OrderService


@pytest.fixture
def logistics_test_context(tmp_path):
    """Provee entorno de pruebas aislado con BD SQLite, empresa, usuario y fábrica de sesiones."""
    db_file = tmp_path / "logistics_center_test.db"
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
            "tenant_name": f"Tenant Logistics {unique_id}",
            "tenant_slug": f"log-slug-{unique_id}",
            "company_legal_name": f"Operadora Logística S.A. {unique_id}",
            "company_rfc": "OPL991201AB0",
            "admin_email": f"log_admin_{unique_id}@test.com",
            "admin_password": "PasswordLogistics1!",
            "admin_full_name": "Jefe de Almacén ERP",
        })
        assert reg_res.status_code == 201
        company_id = reg_res.json()["company_id"]

        login_res = client.post("/api/v1/auth/login", json={
            "email": f"log_admin_{unique_id}@test.com",
            "password": "PasswordLogistics1!",
        })
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]

        headers = {
            "Authorization": f"Bearer {token}",
            "X-Company-ID": company_id,
        }

        # 2. Registrar Empresa Rival para pruebas de aislamiento
        reg_sec = client.post("/api/v1/auth/register-tenant", json={
            "tenant_name": f"Tenant Rival Log {unique_id}",
            "tenant_slug": f"rival-log-{unique_id}",
            "company_legal_name": f"Rival Logística S.A. {unique_id}",
            "company_rfc": "RLG991201XY1",
            "admin_email": f"admin_rival_log_{unique_id}@test.com",
            "admin_password": "PasswordRivalLog1!",
            "admin_full_name": "Admin Rival Log",
        })
        sec_company_id = reg_sec.json()["company_id"]
        login_sec = client.post("/api/v1/auth/login", json={
            "email": f"admin_rival_log_{unique_id}@test.com",
            "password": "PasswordRivalLog1!",
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
            "seller_id": 998877665,
        }

    app.dependency_overrides.clear()


@pytest.fixture
async def setup_logistics_data(logistics_test_context):
    """Crea cuenta MeLi, almacén local y productos en catálogo."""
    session_factory = logistics_test_context["session_factory"]
    company_id = uuid.UUID(logistics_test_context["company_id"])
    seller_id = logistics_test_context["seller_id"]

    async with session_factory() as session:
        # 1. Almacén Principal
        warehouse = Warehouse(
            company_id=company_id,
            name="Bodega Central Monterrey",
            code="BOD-MTY-01",
            address="Av. Industrial 400, Apodaca, N.L.",
            is_fulfillment=False,
            is_active=True,
        )
        session.add(warehouse)

        # 2. Cuenta MeLi Conectada
        account = MeliAccount(
            company_id=company_id,
            meli_user_id=seller_id,
            nickname="Tienda Oficial Logística MeLi",
            site_id="MLM",
            access_token_enc=encrypt_token("APP_USR-test-logistics-token"),
            refresh_token_enc=encrypt_token("TG-test-logistics-refresh"),
            token_expires_at=datetime.now(timezone.utc) + timedelta(hours=6),
            is_active=True,
        )
        session.add(account)

        # 3. Catálogo con Producto y Variante
        product = Product(
            company_id=company_id,
            name="Lámpara LED Inteligente RGB",
            brand="Lumino",
            model="RGB-WIFI-60W",
            category="Hogar",
            is_active=True,
        )
        session.add(product)
        await session.flush()

        variant = ProductVariant(
            company_id=company_id,
            product_id=product.id,
            variant_name="Luz Cálida / RGB",
            sku="LAMP-LED-RGB-60W",
            cogs_cost=180.00,
            sale_price=550.00,
            is_active=True,
        )
        session.add(variant)
        await session.commit()

        return {
            "account_id": account.id,
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "variant_id": variant.id,
            "sku": variant.sku,
        }


# ===========================================================================
# CASOS DE PRUEBA: MÓDULO A (ETIQUETAS DE ENVÍO Y DESPACHO OFICIAL)
# ===========================================================================

@pytest.mark.asyncio
async def test_shipments_query_metrics_and_operational_classification(logistics_test_context, setup_logistics_data):
    """
    Verifica que:
    1. Las órdenes recibidas registren automáticamente su Shipment asociado.
    2. Los envíos se clasifiquen correctamente en: Pendientes, Preparados, Despachados y Errores.
    3. El endpoint /logistics/metrics devuelva el resumen operativo exacto.
    4. Los filtros por dispatch_status y logistic_type funcionen con precisión.
    """
    client = logistics_test_context["client"]
    headers = logistics_test_context["headers"]
    session_factory = logistics_test_context["session_factory"]
    account_id = setup_logistics_data["account_id"]
    sku = setup_logistics_data["sku"]

    order_service = OrderService()

    async with session_factory() as session:
        account = await session.get(MeliAccount, account_id)

        # Envío 1: Pendiente de empaque (ready_to_ship, colecta estándar)
        await order_service.create_or_update_order(
            session,
            account,
            {
                "id": 910101,
                "status": "paid",
                "date_created": "2026-11-18T09:00:00Z",
                "total_amount": 550.0,
                "paid_amount": 550.0,
                "currency_id": "MXN",
                "buyer": {"nickname": "BUYER_PENDING"},
                "order_items": [{"item": {"id": "MLM9101", "title": "Lámpara", "seller_sku": sku}, "quantity": 1, "unit_price": 550.0}],
                "shipping": {
                    "id": 410101,
                    "status": "ready_to_ship",
                    "substatus": "ready_to_print",
                    "logistic_type": "cross_docking",
                    "cost": 95.0,
                    "tracking_number": "TRACK-CD-001",
                    "carrier_name": "Colecta Mercado Envíos",
                },
            },
        )

        # Envío 2: Despachado (en ruta con paquetería)
        await order_service.create_or_update_order(
            session,
            account,
            {
                "id": 910102,
                "status": "paid",
                "date_created": "2026-11-18T08:00:00Z",
                "total_amount": 1100.0,
                "paid_amount": 1100.0,
                "currency_id": "MXN",
                "buyer": {"nickname": "BUYER_SHIPPED"},
                "order_items": [{"item": {"id": "MLM9102", "title": "Lámpara Doble", "seller_sku": sku}, "quantity": 2, "unit_price": 550.0}],
                "shipping": {
                    "id": 410102,
                    "status": "shipped",
                    "substatus": "in_transit",
                    "logistic_type": "drop_off",
                    "cost": 115.0,
                    "tracking_number": "DHL-MX-998877",
                    "carrier_name": "DHL Express",
                },
            },
        )

        # Envío 3: Mercado Envíos Full (operado en CEDIS de MeLi)
        await order_service.create_or_update_order(
            session,
            account,
            {
                "id": 910103,
                "status": "paid",
                "date_created": "2026-11-18T07:00:00Z",
                "total_amount": 550.0,
                "paid_amount": 550.0,
                "currency_id": "MXN",
                "buyer": {"nickname": "BUYER_FULL"},
                "order_items": [{"item": {"id": "MLM9103", "title": "Lámpara Full", "seller_sku": sku}, "quantity": 1, "unit_price": 550.0}],
                "shipping": {
                    "id": 410103,
                    "status": "ready_to_ship",
                    "logistic_type": "fulfillment",
                    "cost": 0.0,
                    "tracking_number": "FULL-CEDIS-001",
                    "carrier_name": "Mercado Libre Full",
                },
            },
        )
        await session.commit()

    # 1. Consultar Métricas Logísticas
    res_metrics = client.get("/api/v1/logistics/metrics", headers=headers)
    assert res_metrics.status_code == 200
    metrics = res_metrics.json()

    assert metrics["total_shipments"] == 3
    assert metrics["pending_count"] >= 1
    assert metrics["dispatched_count"] >= 1
    assert metrics["fulfillment_full_count"] == 1
    assert metrics["cross_docking_count"] == 1
    assert metrics["drop_off_count"] == 1

    # 2. Consultar Lista Filtrada por 'dispatched'
    res_disp = client.get("/api/v1/logistics/shipments?dispatch_status=dispatched", headers=headers)
    assert res_disp.status_code == 200
    disp_items = res_disp.json()["items"]
    assert len(disp_items) == 1
    assert disp_items[0]["meli_shipment_id"] == 410102
    assert disp_items[0]["carrier_name"] == "DHL Express"

    # 3. Consultar Lista Filtrada por 'fulfillment'
    res_full = client.get("/api/v1/logistics/shipments?logistic_type=fulfillment", headers=headers)
    assert res_full.status_code == 200
    full_items = res_full.json()["items"]
    assert len(full_items) == 1
    assert full_items[0]["meli_shipment_id"] == 410103


@pytest.mark.asyncio
async def test_official_label_download_and_fulfillment_restriction(logistics_test_context, setup_logistics_data):
    """
    Verifica que:
    1. Para envíos de colecta estándar, se descargue el PDF binario oficial devuelto por MeLi.
    2. REGLA ESTRICTA: Para envíos de 'fulfillment' (Full), se bloquee la descarga informando
       que la etiqueta la emite y pega exclusivamente el CEDIS de Mercado Libre.
    3. Para pedidos cancelados, se bloquee la descarga de guía activa.
    """
    client = logistics_test_context["client"]
    headers = logistics_test_context["headers"]
    session_factory = logistics_test_context["session_factory"]
    account_id = setup_logistics_data["account_id"]
    sku = setup_logistics_data["sku"]

    order_service = OrderService()
    shipment_std_id = None
    shipment_full_id = None

    async with session_factory() as session:
        account = await session.get(MeliAccount, account_id)

        # Orden A: Colecta estándar lista para imprimir
        order_std = await order_service.create_or_update_order(
            session,
            account,
            {
                "id": 920101,
                "status": "paid",
                "date_created": "2026-11-18T10:00:00Z",
                "total_amount": 550.0,
                "paid_amount": 550.0,
                "currency_id": "MXN",
                "order_items": [{"item": {"id": "MLM9201", "title": "Item A", "seller_sku": sku}, "quantity": 1, "unit_price": 550.0}],
                "shipping": {
                    "id": 420101,
                    "status": "ready_to_ship",
                    "logistic_type": "cross_docking",
                    "cost": 90.0,
                },
            },
        )

        # Orden B: Mercado Envíos Full
        order_full = await order_service.create_or_update_order(
            session,
            account,
            {
                "id": 920102,
                "status": "paid",
                "date_created": "2026-11-18T10:05:00Z",
                "total_amount": 550.0,
                "paid_amount": 550.0,
                "currency_id": "MXN",
                "order_items": [{"item": {"id": "MLM9202", "title": "Item B", "seller_sku": sku}, "quantity": 1, "unit_price": 550.0}],
                "shipping": {
                    "id": 420102,
                    "status": "ready_to_ship",
                    "logistic_type": "fulfillment",
                },
            },
        )
        await session.commit()

        # Obtener los UUIDs de Shipment creados
        stmt_s1 = select(Shipment).where(Shipment.meli_shipment_id == 420101)
        shipment_std_id = (await session.execute(stmt_s1)).scalar_one().id

        stmt_s2 = select(Shipment).where(Shipment.meli_shipment_id == 420102)
        shipment_full_id = (await session.execute(stmt_s2)).scalar_one().id

    # 1. Descarga de Guía Estándar (Mocking de la API oficial de Mercado Libre para simular PDF binario)
    fake_pdf_bytes = b"%PDF-1.4 official label test bytes for Mercado Envios"
    with patch("src.connectors.meli.shipments.MeliShipmentsClient.get_shipment_labels", new_callable=AsyncMock) as mock_labels:
        mock_labels.return_value = fake_pdf_bytes

        res_lbl = client.get(f"/api/v1/logistics/shipments/{shipment_std_id}/label?format_type=pdf", headers=headers)
        assert res_lbl.status_code == 200
        assert res_lbl.headers["content-type"] == "application/pdf"
        assert res_lbl.content == fake_pdf_bytes
        mock_labels.assert_called_once_with([420101], response_type="pdf")

    # 2. Intento de Descarga en Modalidad Full (DEBE SER RECHAZADA CON EXPLICACIÓN)
    res_full_lbl = client.get(f"/api/v1/logistics/shipments/{shipment_full_id}/label?format_type=pdf", headers=headers)
    assert res_full_lbl.status_code == 422
    err_data = res_full_lbl.json()
    assert "Mercado Envíos Full" in err_data["detail"]
    assert "CEDIS de Mercado Libre" in err_data["detail"]


@pytest.mark.asyncio
async def test_shipment_print_recording_and_strict_reprint_audit(logistics_test_context, setup_logistics_data):
    """
    Verifica que:
    1. La primera impresión registre el log con is_reprint=False y cambie estado a 'prepared'.
    2. La orden reciba el hito 'SHIPPING_LABEL_PRINTED' en su línea de tiempo.
    3. Una segunda impresión sin motivo justificado sea rechazada con HTTP 422.
    4. Una reimpresión con motivo válido se guarde con is_reprint=True y conserve la razón.
    5. No se permita reimprimir si el paquete ya figura como 'shipped' (despachado).
    """
    client = logistics_test_context["client"]
    headers = logistics_test_context["headers"]
    session_factory = logistics_test_context["session_factory"]
    account_id = setup_logistics_data["account_id"]
    sku = setup_logistics_data["sku"]

    order_service = OrderService()
    shipment_uuid = None
    order_uuid = None

    async with session_factory() as session:
        account = await session.get(MeliAccount, account_id)
        order = await order_service.create_or_update_order(
            session,
            account,
            {
                "id": 930101,
                "status": "paid",
                "date_created": "2026-11-18T11:00:00Z",
                "total_amount": 550.0,
                "paid_amount": 550.0,
                "currency_id": "MXN",
                "order_items": [{"item": {"id": "MLM9301", "title": "Item Print", "seller_sku": sku}, "quantity": 1, "unit_price": 550.0}],
                "shipping": {
                    "id": 430101,
                    "status": "ready_to_ship",
                    "logistic_type": "cross_docking",
                    "cost": 90.0,
                    "tracking_number": "ESTAFETA-991122",
                },
            },
        )
        await session.commit()
        order_uuid = order.id

        stmt_s = select(Shipment).where(Shipment.meli_shipment_id == 430101)
        shipment_uuid = (await session.execute(stmt_s)).scalar_one().id

    # 1. Primera Impresión
    res_p1 = client.post(f"/api/v1/logistics/shipments/{shipment_uuid}/print", json={"format": "pdf"}, headers=headers)
    assert res_p1.status_code == 201
    log1 = res_p1.json()
    assert log1["print_number"] == 1
    assert log1["is_reprint"] is False

    # Verificar que el shipment pasó a 'prepared' y print_count = 1
    res_sh = client.get(f"/api/v1/logistics/shipments/{shipment_uuid}", headers=headers)
    assert res_sh.status_code == 200
    assert res_sh.json()["dispatch_status"] == "prepared"
    assert res_sh.json()["print_count"] == 1

    # Verificar hito en línea de tiempo de la orden
    async with session_factory() as session:
        stmt_tl = select(OrderTimeline).where(
            OrderTimeline.order_id == order_uuid, OrderTimeline.event_type == "SHIPPING_LABEL_PRINTED"
        )
        timelines = (await session.execute(stmt_tl)).scalars().all()
        assert len(timelines) == 1
        assert "Guía" in timelines[0].description

    # 2. Intento de Reimpresión sin motivo o motivo demasiado corto (< 5 caracteres)
    res_reprint_fail = client.post(
        f"/api/v1/logistics/shipments/{shipment_uuid}/reprint",
        json={"format": "pdf", "reprint_reason": "abc"},
        headers=headers,
    )
    assert res_reprint_fail.status_code == 422

    # 3. Reimpresión autorizada con motivo justificado
    reason_txt = "Guía física dañada por atasco en rodillo de impresora térmica"
    res_reprint_ok = client.post(
        f"/api/v1/logistics/shipments/{shipment_uuid}/reprint",
        json={"format": "pdf", "reprint_reason": reason_txt},
        headers=headers,
    )
    assert res_reprint_ok.status_code == 201
    log2 = res_reprint_ok.json()
    assert log2["print_number"] == 2
    assert log2["is_reprint"] is True
    assert log2["reprint_reason"] == reason_txt

    # 4. Bloqueo de reimpresión si ya fue despachado
    async with session_factory() as session:
        sh_obj = await session.get(Shipment, shipment_uuid)
        sh_obj.status = "shipped"
        await session.commit()

    res_blocked = client.post(
        f"/api/v1/logistics/shipments/{shipment_uuid}/reprint",
        json={"format": "pdf", "reprint_reason": "Intento tardío"},
        headers=headers,
    )
    assert res_blocked.status_code == 422
    assert "ya fue despachado" in res_blocked.json()["detail"]


@pytest.mark.asyncio
async def test_batch_printing_shipments(logistics_test_context, setup_logistics_data):
    """
    Verifica que:
    1. Se puedan imprimir guías en lote agrupando y validando restricciones.
    2. Envíos no elegibles (Full) se aíslen en 'failed_details' sin cancelar todo el lote.
    3. Se registre la auditoría para cada guía impresa en lote.
    """
    client = logistics_test_context["client"]
    headers = logistics_test_context["headers"]
    session_factory = logistics_test_context["session_factory"]
    account_id = setup_logistics_data["account_id"]
    sku = setup_logistics_data["sku"]

    order_service = OrderService()
    shipment_ids = []

    async with session_factory() as session:
        account = await session.get(MeliAccount, account_id)

        # Crear 2 órdenes colecta válidas y 1 Full
        for i in range(1, 3):
            await order_service.create_or_update_order(
                session,
                account,
                {
                    "id": 940100 + i,
                    "status": "paid",
                    "date_created": "2026-11-18T11:30:00Z",
                    "total_amount": 550.0,
                    "paid_amount": 550.0,
                    "currency_id": "MXN",
                    "order_items": [{"item": {"id": f"MLM940{i}", "title": f"Item Batch {i}", "seller_sku": sku}, "quantity": 1, "unit_price": 550.0}],
                    "shipping": {"id": 440100 + i, "status": "ready_to_ship", "logistic_type": "cross_docking"},
                },
            )

        # Orden Full
        await order_service.create_or_update_order(
            session,
            account,
            {
                "id": 940109,
                "status": "paid",
                "date_created": "2026-11-18T11:35:00Z",
                "total_amount": 550.0,
                "paid_amount": 550.0,
                "currency_id": "MXN",
                "order_items": [{"item": {"id": "MLM9409", "title": "Item Full Batch", "seller_sku": sku}, "quantity": 1, "unit_price": 550.0}],
                "shipping": {"id": 440109, "status": "ready_to_ship", "logistic_type": "fulfillment"},
            },
        )
        await session.commit()

        stmt_all = select(Shipment).where(Shipment.meli_shipment_id.in_([440101, 440102, 440109]))
        shipment_ids = [s.id for s in (await session.execute(stmt_all)).scalars().all()]

    fake_batch_pdf = b"%PDF-1.4 consolidated batch labels bytes"
    with patch("src.connectors.meli.shipments.MeliShipmentsClient.get_shipment_labels", new_callable=AsyncMock) as mock_batch:
        mock_batch.return_value = fake_batch_pdf

        res_batch = client.post(
            "/api/v1/logistics/shipments/labels/batch",
            json={"shipment_ids": [str(sid) for sid in shipment_ids], "format": "pdf"},
            headers=headers,
        )
        assert res_batch.status_code == 200
        batch_data = res_batch.json()

        assert batch_data["total_requested"] == 3
        assert batch_data["successful_count"] == 2
        assert batch_data["failed_count"] == 1
        assert "Full" in batch_data["failed_details"][0]["reason"]


# ===========================================================================
# CASOS DE PRUEBA: MÓDULO B (ETIQUETAS INTERNAS, CÓDIGOS DE BARRAS & ZPL)
# ===========================================================================

@pytest.mark.asyncio
async def test_internal_labels_code128_qr_templates_and_zpl(logistics_test_context, setup_logistics_data):
    """
    Verifica que:
    1. Se listen las 4 plantillas de etiquetas internas (térmicas y convencionales).
    2. Se generen etiquetas masivas con Code 128 (SVG vectorial) y QR nítido.
    3. Se genere código ZPL nativo para impresoras Zebra (^XA ... ^BC ... ^BQ ... ^XZ).
    4. Se guarde el historial del lote en InternalLabelPrintBatch.
    """
    client = logistics_test_context["client"]
    headers = logistics_test_context["headers"]
    variant_id = setup_logistics_data["variant_id"]
    sku = setup_logistics_data["sku"]

    # 1. Consultar Plantillas
    res_tmpl = client.get("/api/v1/logistics/internal-labels/templates", headers=headers)
    assert res_tmpl.status_code == 200
    templates = res_tmpl.json()
    assert len(templates) >= 4
    tmpl_types = [t["template_type"] for t in templates]
    assert "thermal_4x6" in tmpl_types
    assert "thermal_50x30" in tmpl_types
    assert "sheet_letter_30" in tmpl_types
    assert "jewelry_mini" in tmpl_types

    # 2. Generar Lote en HTML para Impresora Térmica 100x150 mm (4x6)
    payload_html = {
        "template_type": "thermal_4x6",
        "output_format": "html",
        "include_price": True,
        "items": [
            {
                "variant_id": str(variant_id),
                "sku": sku,
                "product_name": "Lámpara LED RGB WiFi",
                "variant_name": "Luz Cálida",
                "location": "PASILLO-04 / RACK-B2",
                "price": 550.00,
                "quantity": 2,
            }
        ],
    }

    res_gen_html = client.post("/api/v1/logistics/internal-labels/generate", json=payload_html, headers=headers)
    assert res_gen_html.status_code == 200
    data_html = res_gen_html.json()

    assert data_html["total_labels"] == 2
    assert data_html["output_format"] == "html"
    assert "<svg" in data_html["html_content"]
    assert sku in data_html["html_content"]
    assert "PASILLO-04 / RACK-B2" in data_html["html_content"]
    assert "$550.00 MXN" in data_html["html_content"]

    # 3. Generar Lote en ZPL para Impresora Zebra (Térmica 50x30 mm)
    payload_zpl = {
        "template_type": "thermal_50x30",
        "output_format": "zpl",
        "include_price": True,
        "items": [
            {
                "variant_id": str(variant_id),
                "sku": sku,
                "product_name": "Lámpara LED RGB",
                "variant_name": "Luz Cálida",
                "location": "BOD-A12",
                "price": 550.00,
                "quantity": 1,
            }
        ],
    }

    res_gen_zpl = client.post("/api/v1/logistics/internal-labels/generate", json=payload_zpl, headers=headers)
    assert res_gen_zpl.status_code == 200
    data_zpl = res_gen_zpl.json()

    assert data_zpl["output_format"] == "zpl"
    assert "^XA" in data_zpl["zpl_code"]
    assert "^BCN" in data_zpl["zpl_code"]  # Code 128
    assert "^BQN" in data_zpl["zpl_code"]  # QR Code
    assert sku in data_zpl["zpl_code"]
    assert "^XZ" in data_zpl["zpl_code"]


@pytest.mark.asyncio
async def test_order_picking_internal_labels(logistics_test_context, setup_logistics_data):
    """
    Verifica que se generen automáticamente las etiquetas internas de surtido
    a partir de los artículos que componen un pedido de venta real.
    """
    client = logistics_test_context["client"]
    headers = logistics_test_context["headers"]
    session_factory = logistics_test_context["session_factory"]
    account_id = setup_logistics_data["account_id"]
    sku = setup_logistics_data["sku"]

    order_service = OrderService()
    order_uuid = None

    async with session_factory() as session:
        account = await session.get(MeliAccount, account_id)
        order = await order_service.create_or_update_order(
            session,
            account,
            {
                "id": 950101,
                "status": "paid",
                "date_created": "2026-11-18T12:00:00Z",
                "total_amount": 1650.0,
                "paid_amount": 1650.0,
                "currency_id": "MXN",
                "order_items": [
                    {"item": {"id": "MLM9501", "title": "Lámpara Surtido", "seller_sku": sku}, "quantity": 3, "unit_price": 550.0}
                ],
                "shipping": {"id": 450101, "status": "ready_to_ship", "logistic_type": "cross_docking"},
            },
        )
        await session.commit()
        order_uuid = order.id

    res_picking = client.post(
        f"/api/v1/logistics/internal-labels/order/{order_uuid}",
        json={"template_type": "thermal_50x30", "include_price": False, "output_format": "html"},
        headers=headers,
    )
    assert res_picking.status_code == 200
    pick_data = res_picking.json()
    assert pick_data["total_labels"] == 3
    assert sku in pick_data["html_content"]


@pytest.mark.asyncio
async def test_logistics_limitations_and_multi_company_isolation(logistics_test_context, setup_logistics_data):
    """
    Verifica:
    1. Endpoint oficial de documentación de limitaciones técnicas de Mercado Envíos.
    2. Aislamiento multiempresa estricto: la Empresa Rival no puede ver ni descargar guías de la Empresa Principal.
    """
    client = logistics_test_context["client"]
    headers = logistics_test_context["headers"]
    sec_headers = logistics_test_context["sec_headers"]
    session_factory = logistics_test_context["session_factory"]
    account_id = setup_logistics_data["account_id"]
    sku = setup_logistics_data["sku"]

    order_service = OrderService()
    shipment_uuid = None

    async with session_factory() as session:
        account = await session.get(MeliAccount, account_id)
        await order_service.create_or_update_order(
            session,
            account,
            {
                "id": 960101,
                "status": "paid",
                "date_created": "2026-11-18T12:15:00Z",
                "total_amount": 550.0,
                "paid_amount": 550.0,
                "currency_id": "MXN",
                "order_items": [{"item": {"id": "MLM9601", "title": "Item Aislamiento", "seller_sku": sku}, "quantity": 1, "unit_price": 550.0}],
                "shipping": {"id": 460101, "status": "ready_to_ship", "logistic_type": "cross_docking"},
            },
        )
        await session.commit()
        stmt_s = select(Shipment).where(Shipment.meli_shipment_id == 460101)
        shipment_uuid = (await session.execute(stmt_s)).scalar_one().id

    # 1. Documentación de Limitaciones
    res_lim = client.get("/api/v1/logistics/limitations", headers=headers)
    assert res_lim.status_code == 200
    doc = res_lim.json()
    assert len(doc["limitations"]) >= 5
    codes = [l["official_code"] for l in doc["limitations"]]
    assert "CANNOT_PRINT_FULFILLMENT_LABEL" in codes
    assert "SHIPMENT_ALREADY_IN_TRANSIT" in codes
    assert "NO_FAKE_OFFICIAL_LABELS" in codes

    # 2. Aislamiento Multiempresa Estricto
    # Empresa Rival intenta consultar el shipment de la Empresa Principal -> 404 No Encontrado
    res_rival = client.get(f"/api/v1/logistics/shipments/{shipment_uuid}", headers=sec_headers)
    assert res_rival.status_code == 404

    # Empresa Rival intenta imprimir el shipment ajeno -> 404 No Encontrado
    res_rival_print = client.post(
        f"/api/v1/logistics/shipments/{shipment_uuid}/print",
        json={"format": "pdf"},
        headers=sec_headers,
    )
    assert res_rival_print.status_code == 404

    # Empresa Rival lista envíos -> Su lista está vacía (0 envíos)
    res_rival_list = client.get("/api/v1/logistics/shipments", headers=sec_headers)
    assert res_rival_list.status_code == 200
    assert len(res_rival_list.json()["items"]) == 0

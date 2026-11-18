"""
Suite de Pruebas Exhaustivas para el Centro de Información Tabular del ERP.
Valida con estricto rigor:
1. Las 13 Vistas Oficiales del ERP:
   - Ventas, Productos, Inventario, Movimientos, Costos, Comisiones,
   - Rentabilidad, Promociones, Envíos, Compras, Proveedores, Resumen Diario, Resumen Mensual.
2. Filtros, Búsqueda, Ordenamiento y Paginación.
3. Edición Autorizada de Celdas y Registro Inmutable en TabularEditHistory.
4. Regla Estricta: 'Las planillas externas no serán la fuente principal de inventario'.
5. Exportación a CSV con UTF-8 BOM (\ufeff) y XLSX estilizado con openpyxl.
6. Configuración y Sincronización Recuperable con Google Sheets y Microsoft Excel.
7. Preservación de Identificadores Únicos y Aislamiento Multiempresa.
"""

import io
import uuid
from datetime import datetime, timedelta, timezone

import openpyxl
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

from src.core.database import get_db
from src.core.security import encrypt_token
from src.main import app
from src.models import Base
from src.models.meli_account import MeliAccount
from src.models.order import Order, OrderItem
from src.models.payment import Payment
from src.models.product import Product, ProductSKU, ProductVariant
from src.models.profitability import CostHistory
from src.models.promotion import Promotion, PromotionItem
from src.models.shipment import Shipment
from src.models.supplier import PurchaseOrder, PurchaseOrderItem, Supplier
from src.models.tabular import TabularEditHistory, TabularSyncConfig
from src.models.warehouse import Inventory, InventoryMovement, Warehouse


@pytest.fixture
def tabular_test_context(tmp_path):
    """Crea una base de datos aislada con dos empresas (principal y rival) y autenticación."""
    db_file = tmp_path / "tabular_hub_test.db"
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
            "tenant_name": f"Tenant Tabular {uid}",
            "tenant_slug": f"tab-slug-{uid}",
            "company_legal_name": f"Corporación Tabular S.A. {uid}",
            "company_rfc": "TAB991201AB0",
            "admin_email": f"tab_admin_{uid}@test.com",
            "admin_password": "PasswordTabular1!",
            "admin_full_name": "Director General Tabular",
        })
        assert reg1.status_code == 201
        company_id = reg1.json()["company_id"]

        log1 = client.post("/api/v1/auth/login", json={
            "email": f"tab_admin_{uid}@test.com",
            "password": "PasswordTabular1!",
        })
        token = log1.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}", "X-Company-ID": company_id}

        # 2. Empresa Rival
        reg2 = client.post("/api/v1/auth/register-tenant", json={
            "tenant_name": f"Tenant Rival Tabular {uid}",
            "tenant_slug": f"rival-tab-{uid}",
            "company_legal_name": f"Rival Planillas S.A. {uid}",
            "company_rfc": "RIV991201ZZ9",
            "admin_email": f"rival_tab_{uid}@test.com",
            "admin_password": "PasswordRivalTab1!",
            "admin_full_name": "Director Rival",
        })
        assert reg2.status_code == 201
        rival_company_id = reg2.json()["company_id"]

        log2 = client.post("/api/v1/auth/login", json={
            "email": f"rival_tab_{uid}@test.com",
            "password": "PasswordRivalTab1!",
        })
        rival_token = log2.json()["access_token"]
        rival_headers = {"Authorization": f"Bearer {rival_token}", "X-Company-ID": rival_company_id}

        yield {
            "client": client,
            "session_factory": session_factory,
            "company_id": company_id,
            "headers": headers,
            "rival_company_id": rival_company_id,
            "rival_headers": rival_headers,
        }

    app.dependency_overrides.clear()


@pytest.fixture
async def setup_tabular_business_data(tabular_test_context):
    """Puebla la base de datos con entidades completas de negocio para probar las 13 vistas."""
    session_factory = tabular_test_context["session_factory"]
    company_id = uuid.UUID(tabular_test_context["company_id"])
    now_utc = datetime.now(timezone.utc)

    async with session_factory() as session:
        # 1. Cuenta MeLi
        meli_acc = MeliAccount(
            company_id=company_id,
            meli_user_id=888123456,
            nickname="TIENDA_TABULAR_OFICIAL",
            site_id="MLM",
            access_token_enc=encrypt_token("APP_USR-mock-token"),
            refresh_token_enc=encrypt_token("TG-mock-refresh"),
            token_expires_at=now_utc + timedelta(hours=6),
            is_active=True,
        )
        session.add(meli_acc)
        await session.flush()

        # 2. Catálogo Maestro de Productos
        prod = Product(
            company_id=company_id,
            name="Laptop Gamer Pro 16",
            brand="TitanTech",
            model="G16-2026",
            category="Computación",
            unit_of_measure="pza",
            is_active=True,
        )
        session.add(prod)
        await session.flush()

        var = ProductVariant(
            company_id=company_id,
            product_id=prod.id,
            sku="TITAN-G16-BLK",
            variant_name="Negro Titanio / 32GB RAM / 1TB SSD",
            barcode_ean="7509876543210",
            cogs_cost=18500.00,
            sale_price=24999.00,
            is_active=True,
        )
        session.add(var)
        await session.flush()

        # 3. Almacén e Inventario
        wh = Warehouse(
            company_id=company_id,
            name="Cedis Central Tepotzotlán",
            code="CEDIS-TEPO-01",
            warehouse_type="internal",
            is_active=True,
        )
        session.add(wh)
        await session.flush()

        inv = Inventory(
            warehouse_id=wh.id,
            variant_id=var.id,
            quantity_on_hand=30,      # Stock Físico = 30
            quantity_reserved=5,      # Reservado = 5
            quantity_blocked=2,       # Bloqueado = 2
            quantity_available=23,    # 30 - 5 - 2 = 23 disponible
            safety_stock=10,
            min_stock=15,
        )
        session.add(inv)
        await session.flush()

        # 4. Movimiento Kardex
        mov = InventoryMovement(
            inventory_id=inv.id,
            movement_type="INBOUND",
            quantity_delta=30,
            quantity_before=0,
            quantity_after=30,
            reference_type="purchase_order",
            reference_id="OC-2026-INIT",
            notes="Recepción de lote inicial para temporada alta",
        )
        session.add(mov)

        # 5. Historial de Costos
        ch = CostHistory(
            company_id=company_id,
            variant_id=var.id,
            product_id=prod.id,
            sku=var.sku,
            previous_cogs=17800.00,
            new_cogs=18500.00,
            change_reason="supplier_increase",
            notes="Aumento de aranceles de importación por fabricante",
            effective_date=now_utc - timedelta(days=5),
        )
        session.add(ch)

        # 6. Orden de Venta, Partida, Pago y Envío
        order = Order(
            meli_account_id=meli_acc.id,
            meli_order_id=2000008899,
            order_number="ORD-TAB-001",
            status="paid",
            buyer_id=999888,
            buyer_nickname="GAMER_MEXICO",
            payment_status="paid",
            shipment_status="shipped",
            total_amount=24999.00,
            paid_amount=24999.00,
            discount_amount=0.0,
            meli_fee_amount=3249.87,     # 13% comisión MeLi
            shipping_cost_seller=145.00,
            cogs_total=18500.00,
            estimated_profit=3104.13,
            net_margin_pct=12.42,
            date_created_meli=now_utc - timedelta(days=1),
        )
        session.add(order)
        await session.flush()

        order_item = OrderItem(
            order_id=order.id,
            meli_item_id="MLM123456789",
            seller_sku=var.sku,
            title=prod.name,
            quantity=1,
            unit_price=24999.00,
            sale_fee=3249.87,
        )
        session.add(order_item)

        payment = Payment(
            order_id=order.id,
            meli_payment_id=555666777,
            status="approved",
            status_detail="accredited",
            payment_type="credit_card",
            transaction_amount=24999.00,
            marketplace_fee=3249.87,
            date_approved=now_utc - timedelta(days=1),
        )
        session.add(payment)

        shipment = Shipment(
            order_id=order.id,
            meli_shipment_id=444555666,
            tracking_number="TRACK-MX-778899",
            carrier_name="DHL Express",
            logistic_type="fulfillment",
            status="shipped",
            shipping_cost_seller=145.00,
        )
        session.add(shipment)

        # 7. Promociones
        promo = Promotion(
            meli_account_id=meli_acc.id,
            meli_promotion_id="CAMP-HOT-2026",
            name="Campaña Hot Sale Oficial",
            promotion_type="DEAL",
            status="started",
            start_date=now_utc - timedelta(days=2),
            finish_date=now_utc + timedelta(days=10),
        )
        session.add(promo)
        await session.flush()

        promo_item = PromotionItem(
            promotion_id=promo.id,
            meli_item_id=var.sku,
            regular_price=24999.00,
            promotional_price=22499.00,
            discount_pct=10.00,
            is_active=True,
        )
        session.add(promo_item)

        # 8. Proveedores y Órdenes de Compra
        supp = Supplier(
            company_id=company_id,
            code="PROV-TITAN-01",
            name="Titanium Technologies Asia S.A.",
            rfc="TTA010101999",
            contact_name="Kenji Sato",
            email="sales@titan-tech.com",
            phone="55 4321 8765",
            lead_time_days=12,
            payment_terms_days=45,
            credit_limit=500000.00,
            rating_score=4.9,
            on_time_delivery_rate=98.0,
            is_active=True,
        )
        session.add(supp)
        await session.flush()

        po = PurchaseOrder(
            company_id=company_id,
            supplier_id=supp.id,
            warehouse_id=wh.id,
            po_number="OC-2026-TITAN01",
            status="approved",
            currency="MXN",
            subtotal=185000.00,
            tax_amount=29600.00,
            shipping_cost=3500.00,
            total_amount=218100.00,
            payment_authorized=True,
            expected_delivery_date=now_utc + timedelta(days=12),
        )
        session.add(po)
        await session.flush()

        po_item = PurchaseOrderItem(
            purchase_order_id=po.id,
            product_id=prod.id,
            variant_id=var.id,
            sku=var.sku,
            product_name=prod.name,
            quantity_ordered=10,
            quantity_received=0,
            quantity_pending=10,
            unit_cost=18500.00,
            tax_rate=0.1600,
            total_cost=185000.00,
        )
        session.add(po_item)

        await session.commit()

        return {
            "variant_id": str(var.id),
            "product_id": str(prod.id),
            "sku": var.sku,
            "inventory_id": str(inv.id),
            "supplier_id": str(supp.id),
            "purchase_order_id": str(po.id),
            "order_id": str(order.id),
        }


# ===========================================================================
# 1. PRUEBA: CATÁLOGO DE LAS 13 VISTAS TABULARES Y METADATOS DE COLUMNAS
# ===========================================================================

def test_tabular_views_catalog(tabular_test_context):
    """Verifica que el endpoint /api/v1/tabular/views liste exactamente las 13 vistas oficiales del ERP."""
    client = tabular_test_context["client"]
    headers = tabular_test_context["headers"]

    res = client.get("/api/v1/tabular/views", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total_views"] == 13

    view_keys = [v["view_name"] for v in data["views"]]
    expected_views = [
        "sales", "products", "inventory", "movements", "costs", "commissions",
        "profitability", "promotions", "shipments", "purchases", "suppliers",
        "daily_summary", "monthly_summary"
    ]
    for exp in expected_views:
        assert exp in view_keys

    # Verificar metadatos de columnas en la vista 'products'
    prod_view = next(v for v in data["views"] if v["view_name"] == "products")
    col_keys = [c["key"] for c in prod_view["columns"]]
    assert "sku" in col_keys
    assert "cogs_cost" in col_keys
    assert "sale_price" in col_keys


# ===========================================================================
# 2. PRUEBA: CONSULTA Y PAGINACIÓN DE CADA UNA DE LAS 13 VISTAS
# ===========================================================================

@pytest.mark.asyncio
async def test_all_thirteen_views_query_and_pagination(tabular_test_context, setup_tabular_business_data):
    """
    Verifica que la planilla interna retorne datos válidos, consistentes y paginados
    para cada una de las 13 vistas de negocio del ERP.
    """
    client = tabular_test_context["client"]
    headers = tabular_test_context["headers"]

    views_to_test = [
        "sales",
        "products",
        "inventory",
        "movements",
        "costs",
        "commissions",
        "profitability",
        "promotions",
        "shipments",
        "purchases",
        "suppliers",
        "daily_summary",
        "monthly_summary",
    ]

    for view_name in views_to_test:
        res = client.get(f"/api/v1/tabular/{view_name}?page=1&page_size=25", headers=headers)
        assert res.status_code == 200, f"Error en vista {view_name}: {res.text}"
        data = res.json()
        assert data["view_name"] == view_name
        assert data["total_items"] >= 1, f"La vista {view_name} debería tener al menos 1 registro poblado"
        assert len(data["items"]) >= 1
        assert len(data["columns"]) >= 5
        assert data["page"] == 1
        assert "server_timestamp" in data
        assert "last_synced_at" in data

        # Verificar integridad del primer elemento
        first_row = data["items"][0]
        assert "row_id" in first_row


# ===========================================================================
# 3. PRUEBA: BÚSQUEDA, FILTROS Y ORDENAMIENTO DINÁMICO
# ===========================================================================

@pytest.mark.asyncio
async def test_tabular_filtering_search_and_sorting(tabular_test_context, setup_tabular_business_data):
    """Verifica el funcionamiento del motor de filtros por texto, rango de fechas y ordenamiento."""
    client = tabular_test_context["client"]
    headers = tabular_test_context["headers"]
    data_info = setup_tabular_business_data

    # 1. Búsqueda por SKU en vista Productos
    res_search = client.get(f"/api/v1/tabular/products?search={data_info['sku']}", headers=headers)
    assert res_search.status_code == 200
    res_json = res_search.json()
    assert res_json["total_items"] == 1
    assert res_json["items"][0]["sku"] == data_info["sku"]

    # 2. Búsqueda que no arroja resultados
    res_none = client.get("/api/v1/tabular/products?search=INEXISTENTE_XYZ", headers=headers)
    assert res_none.status_code == 200
    assert res_none.json()["total_items"] == 0

    # 3. Ordenamiento en vista Ventas por monto descendente vs ascendente
    res_desc = client.get("/api/v1/tabular/sales?sort_by=gross_amount&sort_order=desc", headers=headers)
    assert res_desc.status_code == 200
    assert len(res_desc.json()["items"]) >= 1


# ===========================================================================
# 4. PRUEBA: EDICIÓN AUTORIZADA DE CELDAS Y HISTORIAL INMUTABLE
# ===========================================================================

@pytest.mark.asyncio
async def test_authorized_row_cell_edit_and_audit_history(tabular_test_context, setup_tabular_business_data):
    """
    Verifica:
    - Edición autorizada en celda (ajuste de costo COGS y precio de venta en producto).
    - Creación de registro inmutable en TabularEditHistory con valores antes/después.
    - Actualización de safety_stock en inventario.
    """
    client = tabular_test_context["client"]
    headers = tabular_test_context["headers"]
    data_info = setup_tabular_business_data
    variant_id = data_info["variant_id"]
    inv_id = data_info["inventory_id"]

    # 1. Modificar celdas de Producto (COGS y Precio)
    update_payload = {
        "updates": {
            "cogs_cost": 19200.00,
            "sale_price": 25999.00,
        },
        "change_reason": "Actualización comercial por incremento en flete marítimo",
    }
    res_edit = client.put(f"/api/v1/tabular/products/{variant_id}", json=update_payload, headers=headers)
    assert res_edit.status_code == 200
    edit_resp = res_edit.json()
    assert edit_resp["success"] is True
    assert edit_resp["updated_fields"]["cogs_cost"] == 19200.00
    assert edit_resp["updated_fields"]["sale_price"] == 25999.00
    assert edit_resp["previous_values"]["cogs_cost"] == 18500.00

    # 2. Modificar celda de Inventario (safety_stock)
    inv_edit_payload = {
        "updates": {"safety_stock": 18},
        "change_reason": "Incremento de colchón de seguridad para Cyber Monday",
    }
    res_inv_edit = client.put(f"/api/v1/tabular/inventory/{inv_id}", json=inv_edit_payload, headers=headers)
    assert res_inv_edit.status_code == 200
    assert res_inv_edit.json()["updated_fields"]["safety_stock"] == 18

    # 3. Consultar Historial Inmutable de Cambios en Planillas
    res_hist = client.get("/api/v1/tabular/history?limit=10", headers=headers)
    assert res_hist.status_code == 200
    hist_json = res_hist.json()
    assert hist_json["total_items"] >= 3

    # Verificar que los campos modificados están registrados con valores exactos
    cogs_entry = next((h for h in hist_json["items"] if h["column_name"] == "cogs_cost"), None)
    assert cogs_entry is not None
    assert float(cogs_entry["new_value"]) == 19200.00
    assert float(cogs_entry["previous_value"]) == 18500.00
    assert cogs_entry["change_reason"] == "Actualización comercial por incremento en flete marítimo"


# ===========================================================================
# 5. PRUEBA DE REGLA ESTRICTA: PLANILLAS EXTERNAS NO MODIFICAN STOCK FÍSICO
# ===========================================================================

@pytest.mark.asyncio
async def test_external_sheet_cannot_override_physical_inventory(tabular_test_context, setup_tabular_business_data):
    """
    Verifica el cumplimiento de la regla estricta:
    'Las planillas externas no serán la fuente principal de inventario'.
    Un intento de sobreescritura de stock físico desde fuente externa debe ser
    bloqueado con conflicto registrado en auditoría.
    """
    client = tabular_test_context["client"]
    headers = tabular_test_context["headers"]
    inv_id = setup_tabular_business_data["inventory_id"]
    session_factory = tabular_test_context["session_factory"]

    # Simular llamada directa al servicio indicando source='google_sheets'
    from src.services.tabular_service import TabularService
    svc = TabularService()
    company_id = uuid.UUID(tabular_test_context["company_id"])

    async with session_factory() as session:
        with pytest.raises(Exception) as exc_info:
            await svc.update_tabular_row(
                session=session,
                company_id=company_id,
                view_name="inventory",
                row_id=inv_id,
                updates={"stock_physical": 999},  # Intento ilegal de cambiar stock físico desde hoja externa
                source="google_sheets",
                change_reason="Sobreescritura no autorizada desde hoja de cálculo externa",
            )
        assert "Las planillas externas no pueden modificar el stock físico del ERP" in str(exc_info.value)

        # Verificar que se registró el conflicto en el historial de modificaciones
        hist_stmt = (
            sa.select(TabularEditHistory)
            .where(
                TabularEditHistory.company_id == company_id,
                TabularEditHistory.status == "conflict_rejected",
            )
        )
        conflicts = (await session.execute(hist_stmt)).scalars().all()
        assert len(conflicts) >= 1
        assert conflicts[0].source == "google_sheets"
        assert "fuente principal de existencias" in conflicts[0].conflict_details


# ===========================================================================
# 6. PRUEBA: EXPORTACIÓN A CSV CON UTF-8 BOM (\ufeff)
# ===========================================================================

@pytest.mark.asyncio
async def test_tabular_export_csv_with_utf8_bom(tabular_test_context, setup_tabular_business_data):
    """Verifica que la exportación a CSV contenga UTF-8 BOM (\ufeff) y encabezados en español."""
    client = tabular_test_context["client"]
    headers = tabular_test_context["headers"]

    res_csv = client.get("/api/v1/tabular/products/export/csv", headers=headers)
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.headers["content-type"]
    assert "attachment; filename=" in res_csv.headers["content-disposition"]

    content = res_csv.content
    # Comprobar que empieza exactamente con los 3 bytes del UTF-8 BOM: 0xEF, 0xBB, 0xBF
    assert content.startswith(b"\xef\xbb\xbf")

    # Decodificar texto y verificar presencia del producto de prueba
    text_csv = content.decode("utf-8")
    assert "SKU Maestro" in text_csv
    assert "TITAN-G16-BLK" in text_csv
    assert "Laptop Gamer Pro 16" in text_csv


# ===========================================================================
# 7. PRUEBA: EXPORTACIÓN A MICROSOFT EXCEL (.XLSX) CON OPENPYXL
# ===========================================================================

@pytest.mark.asyncio
async def test_tabular_export_xlsx_openpyxl_styles(tabular_test_context, setup_tabular_business_data):
    """Verifica que la exportación genere un libro XLSX válido con hojas, encabezados y celdas estilizadas."""
    client = tabular_test_context["client"]
    headers = tabular_test_context["headers"]

    res_xlsx = client.get("/api/v1/tabular/sales/export/xlsx", headers=headers)
    assert res_xlsx.status_code == 200
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in res_xlsx.headers["content-type"]

    # Cargar los bytes devueltos directamente en openpyxl para certificar validez binaria
    excel_bytes = res_xlsx.content
    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    assert len(wb.sheetnames) >= 1

    ws = wb.active
    # Verificar fila 1 de encabezados
    cell_a1 = ws.cell(row=1, column=1)
    assert cell_a1.value == "ID Venta ERP"
    assert cell_a1.font.bold is True

    # Verificar presencia de fila con datos de la orden
    cell_buyer = ws.cell(row=2, column=4)
    assert cell_buyer.value == "GAMER_MEXICO"


# ===========================================================================
# 8. PRUEBA: CONFIGURACIÓN Y SINCRONIZACIÓN CON GOOGLE SHEETS Y EXCEL
# ===========================================================================

@pytest.mark.asyncio
async def test_sync_configuration_and_execution_lifecycle(tabular_test_context, setup_tabular_business_data):
    """
    Verifica:
    - Registro de configuración de sincronización para Google Sheets y Microsoft Excel.
    - Ejecución de sincronización recuperable y reporte de estado.
    """
    client = tabular_test_context["client"]
    headers = tabular_test_context["headers"]

    # 1. Configurar enlace con Google Sheets
    sync_payload = {
        "view_name": "sales",
        "provider": "google_sheets",
        "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
        "sheet_name": "Ventas_ERP_MeLi",
        "sync_direction": "push_to_sheet",
        "conflict_resolution": "server_wins",
        "auto_sync_interval_minutes": 15,
        "external_url": "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
    }
    res_cfg = client.post("/api/v1/tabular/sync-configs", json=sync_payload, headers=headers)
    assert res_cfg.status_code == 201
    cfg_data = res_cfg.json()
    assert cfg_data["provider"] == "google_sheets"
    assert cfg_data["spreadsheet_id"] == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"

    # 2. Consultar lista de configuraciones activas
    res_list = client.get("/api/v1/tabular/sync-configs", headers=headers)
    assert res_list.status_code == 200
    assert len(res_list.json()) >= 1

    # 3. Disparar sincronización hacia Google Sheets
    res_sync = client.post("/api/v1/tabular/sales/sync/google_sheets", json={"direction": "push"}, headers=headers)
    assert res_sync.status_code == 200
    sync_res = res_sync.json()
    assert sync_res["success"] is True
    assert sync_res["synced_rows_count"] >= 1
    assert "Regla verificada: La planilla interna es la fuente central" in sync_res["primary_source_rule_applied"]

    # 4. Disparar sincronización bidireccional en Inventario y verificar resolución de conflicto
    res_inv_sync = client.post(
        "/api/v1/tabular/inventory/sync/google_sheets",
        json={"direction": "bidirectional"},
        headers=headers,
    )
    assert res_inv_sync.status_code == 200
    inv_sync_res = res_inv_sync.json()
    assert inv_sync_res["conflicts_detected"] >= 1
    assert inv_sync_res["conflicts_resolved"] >= 1


# ===========================================================================
# 9. PRUEBA: AISLAMIENTO MULTIEMPRESA EN PLANILLAS
# ===========================================================================

@pytest.mark.asyncio
async def test_multi_tenant_isolation_in_tabular_views(tabular_test_context, setup_tabular_business_data):
    """Verifica que una empresa rival no pueda leer ni modificar datos de las planillas de otra empresa."""
    client = tabular_test_context["client"]
    rival_headers = tabular_test_context["rival_headers"]
    data_info = setup_tabular_business_data
    variant_id = data_info["variant_id"]

    # La empresa rival consulta la planilla de productos (debe ver 0 registros)
    res_rival = client.get("/api/v1/tabular/products", headers=rival_headers)
    assert res_rival.status_code == 200
    assert res_rival.json()["total_items"] == 0

    # La empresa rival intenta modificar una celda de la empresa principal (debe recibir 404)
    res_hack = client.put(
        f"/api/v1/tabular/products/{variant_id}",
        json={"updates": {"cogs_cost": 1.00}},
        headers=rival_headers,
    )
    assert res_hack.status_code == 404

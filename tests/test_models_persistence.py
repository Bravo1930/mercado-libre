"""Pruebas de persistencia, integridad referencial, transacciones y modelos del ERP."""

import uuid
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from src.core.exceptions import InsufficientStockException
from src.core.security import decrypt_token, encrypt_token, hash_password, verify_password
from src.models import (
    AuditLog,
    Base,
    Company,
    CompanySetting,
    CostStructure,
    Inventory,
    InventoryMovement,
    MeliAccount,
    Order,
    OrderItem,
    Payment,
    Product,
    ProductSKU,
    ProductVariant,
    ProfitabilityAudit,
    PurchaseOrder,
    PurchaseOrderItem,
    Shipment,
    Supplier,
    Tenant,
    User,
    Warehouse,
)


@pytest.fixture(scope="module")
def sync_db_session():
    """Crea una base de datos SQLite en memoria con todas las 24 tablas del ERP."""
    engine = sa.create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


def test_full_business_lifecycle_persistence(sync_db_session):
    """
    Prueba de persistencia integral:
    Verifica inserción, integridad de llaves foráneas y navegación de relaciones
    a lo largo de todo el ciclo de vida del negocio:
    Tenant -> Company -> User -> Warehouse -> Product -> Variant -> MeLi SKU ->
    Inventario -> Movimiento -> Orden -> Pago -> Envío -> Auditoría SAT -> Proveedor -> Compra.
    """
    session = sync_db_session

    # 1. Tenant y Empresa con RFC Mexicano
    tenant = Tenant(name="Grupo Comercial Andina", slug=f"andina-{uuid.uuid4().hex[:6]}")
    session.add(tenant)
    session.flush()

    company = Company(
        tenant_id=tenant.id,
        legal_name="Comercializadora Andina S.A. de C.V.",
        rfc="CAN180512AB3",
        fiscal_regime="601",
    )
    session.add(company)
    session.flush()

    assert company.id is not None
    assert company.tenant.name == "Grupo Comercial Andina"

    # 2. Usuario con contraseña cifrada (bcrypt)
    user = User(
        tenant_id=tenant.id,
        email=f"admin-{uuid.uuid4().hex[:4]}@andina.com",
        password_hash=hash_password("Empresarial2026!"),
        full_name="Director de Operaciones",
        role="admin",
    )
    session.add(user)
    session.flush()
    assert verify_password("Empresarial2026!", user.password_hash) is True
    assert verify_password("PasswordErroneo!", user.password_hash) is False

    # 3. Cuenta de Mercado Libre con tokens cifrados en reposo (AES-256 Fernet)
    plain_refresh_token = "TG-672a912e5ab-123456789-mock-token"
    meli_account = MeliAccount(
        company_id=company.id,
        meli_user_id=123450000 + int(uuid.uuid4().int % 100000),
        nickname="TIENDA_OFICIAL_ANDINA",
        site_id="MLM",
        access_token_enc=encrypt_token("APP_USR-mock-access-token"),
        refresh_token_enc=encrypt_token(plain_refresh_token),
        token_expires_at=company.created_at,
    )
    session.add(meli_account)
    session.flush()

    # Garantizar que ningún token se almacena en texto plano
    assert meli_account.refresh_token_enc != plain_refresh_token
    assert decrypt_token(meli_account.refresh_token_enc) == plain_refresh_token

    # 4. Almacén Central
    warehouse = Warehouse(
        company_id=company.id,
        name="Bodega Central CDMX",
        code="BOD-CDMX-01",
        warehouse_type="internal",
    )
    session.add(warehouse)
    session.flush()

    # 5. Producto Maestro y Variante
    product = Product(
        company_id=company.id,
        name="Audífonos Bluetooth Noise Cancelling Pro",
        brand="AudioTech",
        category="Electrónica",
    )
    session.add(product)
    session.flush()

    variant = ProductVariant(
        product_id=product.id,
        variant_name="Negro Mate / Edición Especial",
        sku="AT-NC-PRO-BLK",
        barcode_ean="7501234567890",
        cogs_cost=450.00,  # Costo de adquisición $450 MXN
    )
    session.add(variant)
    session.flush()

    # 6. Publicación SKU oficial en Mercado Libre México
    sku_meli = ProductSKU(
        meli_account_id=meli_account.id,
        variant_id=variant.id,
        meli_item_id="MLM987654321",
        seller_sku="AT-NC-PRO-BLK",
        price=1299.00,  # Precio de venta $1,299 MXN
        listing_type_id="gold_special",
        logistic_type="fulfillment",
    )
    session.add(sku_meli)
    session.flush()

    # 7. Inventario y Movimiento en Kardex
    inventory = Inventory(
        warehouse_id=warehouse.id,
        variant_id=variant.id,
        quantity_available=100,
        quantity_reserved=0,
        safety_stock=5,
    )
    session.add(inventory)
    session.flush()

    movement = InventoryMovement(
        inventory_id=inventory.id,
        movement_type="PURCHASE_RECEIPT",
        quantity_delta=100,
        quantity_before=0,
        quantity_after=100,
        reference_id="OC-2026-0001",
        user_id=user.id,
        notes="Recepción de embarque inicial",
    )
    session.add(movement)
    session.flush()

    assert inventory.quantity_available == 100
    assert len(inventory.movements) == 1

    # 8. Orden de Venta en Mercado Libre
    order = Order(
        meli_account_id=meli_account.id,
        meli_order_id=2000000000 + int(uuid.uuid4().int % 10000000),
        status="paid",
        buyer_id=888999111,
        buyer_nickname="COMPRADOR_CDMX",
        total_amount=1299.00,
        paid_amount=1299.00,
        currency_id="MXN",
        date_created_meli=company.created_at,
    )
    session.add(order)
    session.flush()

    item = OrderItem(
        order_id=order.id,
        meli_item_id=sku_meli.meli_item_id,
        seller_sku=sku_meli.seller_sku,
        title=product.name,
        quantity=1,
        unit_price=1299.00,
        sale_fee=194.85,
    )
    session.add(item)

    payment = Payment(
        order_id=order.id,
        meli_payment_id=777888999 + int(uuid.uuid4().int % 1000000),
        status="approved",
        status_detail="accredited",
        payment_type="credit_card",
        payment_method_id="visa",
        transaction_amount=1299.00,
        marketplace_fee=194.85,
        date_approved=company.created_at,
    )
    session.add(payment)

    shipment = Shipment(
        order_id=order.id,
        meli_shipment_id=666555444 + int(uuid.uuid4().int % 1000000),
        status="ready_to_ship",
        logistic_type="fulfillment",
        tracking_number="MLMX-9988776655",
        carrier_name="Mercado Envíos Full",
        shipping_cost_seller=85.00,
    )
    session.add(shipment)

    # 9. Auditoría de Rentabilidad Neta y Retenciones SAT México
    cogs = 450.00
    commission = 194.85
    shipping = 85.00
    packaging = 15.00
    sat_iva = 89.58   # 8% retención IVA oficial
    sat_isr = 12.99   # 1% retención ISR RESICO
    net_profit = round(1299.00 - (cogs + commission + shipping + packaging + sat_iva + sat_isr), 2)
    net_margin = round((net_profit / 1299.00) * 100, 2)

    audit = ProfitabilityAudit(
        order_id=order.id,
        gross_sale_price=1299.00,
        cogs_total=cogs,
        meli_commission_fee=commission,
        shipping_cost_seller=shipping,
        packaging_cost=packaging,
        sat_iva_retention=sat_iva,
        sat_isr_retention=sat_isr,
        net_profit=net_profit,
        net_margin_pct=net_margin,
    )
    session.add(audit)

    # 10. Proveedor y Orden de Compra
    supplier = Supplier(
        company_id=company.id,
        name="Shenzhen Audio Electronics Ltd.",
        rfc=None,
        contact_name="Wang Wei",
        lead_time_days=14,
    )
    session.add(supplier)
    session.flush()

    po = PurchaseOrder(
        company_id=company.id,
        supplier_id=supplier.id,
        po_number="PO-2026-0001",
        status="submitted",
        total_amount=45000.00,
    )
    session.add(po)
    session.flush()

    po_item = PurchaseOrderItem(
        purchase_order_id=po.id,
        variant_id=variant.id,
        quantity_ordered=100,
        unit_cost=450.00,
    )
    session.add(po_item)

    # 11. Configuración y Auditoría
    setting = CompanySetting(
        company_id=company.id,
        key="auto_sync_interval_minutes",
        value="15",
        description="Frecuencia de sincronización periódica de órdenes MeLi",
    )
    session.add(setting)

    audit_log = AuditLog(
        company_id=company.id,
        user_id=user.id,
        action="CREATE_INITIAL_CATALOG",
        entity_name="Product",
        entity_id=str(product.id),
        changes_json='{"action": "initial_setup"}',
        ip_address="127.0.0.1",
    )
    session.add(audit_log)

    session.commit()

    # Comprobación de integridad relacional
    reloaded_company = session.get(Company, company.id)
    assert len(reloaded_company.products) == 1
    assert len(reloaded_company.warehouses) == 1
    assert len(reloaded_company.meli_accounts) == 1
    assert len(reloaded_company.suppliers) == 1
    assert len(reloaded_company.settings) == 1

    reloaded_order = session.get(Order, order.id)
    assert len(reloaded_order.items) == 1
    assert len(reloaded_order.payments) == 1
    assert len(reloaded_order.shipments) == 1
    assert float(reloaded_order.profitability.net_profit) == net_profit
    assert float(reloaded_order.profitability.net_margin_pct) == net_margin


def test_unique_rfc_per_tenant_constraint(sync_db_session):
    """Verifica que la base de datos impida registrar dos empresas con el mismo RFC dentro de un mismo Tenant."""
    session = sync_db_session

    tenant = Tenant(name="Tenant Aislamiento", slug=f"aisla-{uuid.uuid4().hex[:4]}")
    session.add(tenant)
    session.flush()

    c1 = Company(tenant_id=tenant.id, legal_name="Empresa 1", rfc="AAA010101AAA")
    session.add(c1)
    session.flush()

    # Intentar duplicar RFC en el mismo tenant debe fallar
    c2 = Company(tenant_id=tenant.id, legal_name="Empresa 2", rfc="AAA010101AAA")
    session.add(c2)
    with pytest.raises(Exception):
        session.flush()
    session.rollback()

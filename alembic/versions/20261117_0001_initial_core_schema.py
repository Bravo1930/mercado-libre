"""Esquema inicial del núcleo ERP: 17 modelos relacionales y multi-empresa.

Revision ID: 20261117_0001
Revises: 
Create Date: 2026-11-17 23:55:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '20261117_0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Tenants (Organizaciones SaaS)
    op.create_table(
        'tenants',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('plan_tier', sa.String(length=50), server_default='standard', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_tenants'))
    )
    op.create_index(op.f('ix_tenants_slug'), 'tenants', ['slug'], unique=True)

    # 2. Companies (Empresas / RFC México)
    op.create_table(
        'companies',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('legal_name', sa.String(length=255), nullable=False),
        sa.Column('rfc', sa.String(length=13), nullable=False),
        sa.Column('fiscal_regime', sa.String(length=100), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=30), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_companies_tenant_id_tenants'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_companies'))
    )
    op.create_index('ix_companies_tenant_rfc', 'companies', ['tenant_id', 'rfc'], unique=True)
    op.create_index(op.f('ix_companies_rfc'), 'companies', ['rfc'], unique=False)

    # 3. Users
    op.create_table(
        'users',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=150), nullable=False),
        sa.Column('role', sa.String(length=50), server_default='operator', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('is_superuser', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_users_tenant_id_tenants'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_users'))
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index('ix_users_tenant_role', 'users', ['tenant_id', 'role'], unique=False)

    # 4. Cuentas Mercado Libre
    op.create_table(
        'meli_accounts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('meli_user_id', sa.BigInteger(), nullable=False),
        sa.Column('nickname', sa.String(length=100), nullable=False),
        sa.Column('site_id', sa.String(length=10), server_default='MLM', nullable=False),
        sa.Column('access_token_enc', sa.Text(), nullable=False),
        sa.Column('refresh_token_enc', sa.Text(), nullable=False),
        sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('sync_orders', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('sync_stock', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('sync_prices', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], name=op.f('fk_meli_accounts_company_id_companies'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_meli_accounts'))
    )
    op.create_index(op.f('ix_meli_accounts_meli_user_id'), 'meli_accounts', ['meli_user_id'], unique=True)
    op.create_index('ix_meli_accounts_company_active', 'meli_accounts', ['company_id', 'is_active'], unique=False)

    # 5. Productos Maestros
    op.create_table(
        'products',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('brand', sa.String(length=100), nullable=True),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], name=op.f('fk_products_company_id_companies'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_products'))
    )
    op.create_index('ix_products_company_name', 'products', ['company_id', 'name'], unique=False)

    # 6. Variantes de Producto
    op.create_table(
        'product_variants',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('product_id', sa.UUID(), nullable=False),
        sa.Column('variant_name', sa.String(length=100), nullable=False),
        sa.Column('sku', sa.String(length=100), nullable=False),
        sa.Column('barcode_ean', sa.String(length=50), nullable=True),
        sa.Column('cogs_cost', sa.Numeric(precision=12, scale=2), server_default='0.00', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_product_variants_product_id_products'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_product_variants'))
    )
    op.create_index('ix_product_variants_product_sku', 'product_variants', ['product_id', 'sku'], unique=True)
    op.create_index(op.f('ix_product_variants_sku'), 'product_variants', ['sku'], unique=False)

    # 7. SKUs Mapeados con Mercado Libre
    op.create_table(
        'product_skus',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('meli_account_id', sa.UUID(), nullable=False),
        sa.Column('variant_id', sa.UUID(), nullable=False),
        sa.Column('meli_item_id', sa.String(length=30), nullable=False),
        sa.Column('meli_variation_id', sa.String(length=30), nullable=True),
        sa.Column('seller_sku', sa.String(length=100), nullable=False),
        sa.Column('price', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('listing_type_id', sa.String(length=50), server_default='gold_special', nullable=False),
        sa.Column('logistic_type', sa.String(length=50), server_default='fulfillment', nullable=False),
        sa.Column('status', sa.String(length=30), server_default='active', nullable=False),
        sa.Column('sync_stock_enabled', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['meli_account_id'], ['meli_accounts.id'], name=op.f('fk_product_skus_meli_account_id_meli_accounts'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['variant_id'], ['product_variants.id'], name=op.f('fk_product_skus_variant_id_product_variants'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_product_skus'))
    )
    op.create_index('ix_product_skus_meli_item', 'product_skus', ['meli_account_id', 'meli_item_id', 'meli_variation_id'], unique=True)

    # 8. Almacenes
    op.create_table(
        'warehouses',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('warehouse_type', sa.String(length=50), server_default='internal', nullable=False),
        sa.Column('address', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], name=op.f('fk_warehouses_company_id_companies'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_warehouses'))
    )
    op.create_index('ix_warehouses_company_code', 'warehouses', ['company_id', 'code'], unique=True)

    # 9. Inventarios
    op.create_table(
        'inventories',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('warehouse_id', sa.UUID(), nullable=False),
        sa.Column('variant_id', sa.UUID(), nullable=False),
        sa.Column('quantity_available', sa.Integer(), server_default='0', nullable=False),
        sa.Column('quantity_reserved', sa.Integer(), server_default='0', nullable=False),
        sa.Column('safety_stock', sa.Integer(), server_default='5', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['variant_id'], ['product_variants.id'], name=op.f('fk_inventories_variant_id_product_variants'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['warehouse_id'], ['warehouses.id'], name=op.f('fk_inventories_warehouse_id_warehouses'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_inventories'))
    )
    op.create_index('ix_inventories_warehouse_variant', 'inventories', ['warehouse_id', 'variant_id'], unique=True)

    # 10. Movimientos de Inventario (Kardex)
    op.create_table(
        'inventory_movements',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('inventory_id', sa.UUID(), nullable=False),
        sa.Column('movement_type', sa.String(length=50), nullable=False),
        sa.Column('quantity_delta', sa.Integer(), nullable=False),
        sa.Column('quantity_before', sa.Integer(), nullable=False),
        sa.Column('quantity_after', sa.Integer(), nullable=False),
        sa.Column('reference_id', sa.String(length=100), nullable=True),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['inventory_id'], ['inventories.id'], name=op.f('fk_inventory_movements_inventory_id_inventories'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_inventory_movements'))
    )
    op.create_index('ix_inventory_movements_type_date', 'inventory_movements', ['movement_type', 'created_at'], unique=False)

    # 11. Ventas / Órdenes
    op.create_table(
        'orders',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('meli_account_id', sa.UUID(), nullable=False),
        sa.Column('meli_order_id', sa.BigInteger(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('buyer_id', sa.BigInteger(), nullable=True),
        sa.Column('buyer_nickname', sa.String(length=100), nullable=True),
        sa.Column('total_amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('paid_amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('currency_id', sa.String(length=10), server_default='MXN', nullable=False),
        sa.Column('date_created_meli', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['meli_account_id'], ['meli_accounts.id'], name=op.f('fk_orders_meli_account_id_meli_accounts'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_orders'))
    )
    op.create_index(op.f('ix_orders_meli_order_id'), 'orders', ['meli_order_id'], unique=True)
    op.create_index('ix_orders_account_status_date', 'orders', ['meli_account_id', 'status', 'date_created_meli'], unique=False)

    # 12. Partidas de Orden (Order Items)
    op.create_table(
        'order_items',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('order_id', sa.UUID(), nullable=False),
        sa.Column('meli_item_id', sa.String(length=30), nullable=False),
        sa.Column('meli_variation_id', sa.String(length=30), nullable=True),
        sa.Column('seller_sku', sa.String(length=100), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('unit_price', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('sale_fee', sa.Numeric(precision=12, scale=2), server_default='0.00', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_order_items_order_id_orders'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_order_items'))
    )

    # 13. Pagos
    op.create_table(
        'payments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('order_id', sa.UUID(), nullable=False),
        sa.Column('meli_payment_id', sa.BigInteger(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('status_detail', sa.String(length=100), nullable=True),
        sa.Column('payment_type', sa.String(length=50), nullable=True),
        sa.Column('payment_method_id', sa.String(length=50), nullable=True),
        sa.Column('transaction_amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('marketplace_fee', sa.Numeric(precision=12, scale=2), server_default='0.00', nullable=False),
        sa.Column('date_approved', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_payments_order_id_orders'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_payments'))
    )
    op.create_index(op.f('ix_payments_meli_payment_id'), 'payments', ['meli_payment_id'], unique=True)

    # 14. Envíos
    op.create_table(
        'shipments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('order_id', sa.UUID(), nullable=False),
        sa.Column('meli_shipment_id', sa.BigInteger(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('substatus', sa.String(length=50), nullable=True),
        sa.Column('logistic_type', sa.String(length=50), server_default='fulfillment', nullable=False),
        sa.Column('tracking_number', sa.String(length=100), nullable=True),
        sa.Column('carrier_name', sa.String(length=100), nullable=True),
        sa.Column('shipping_cost_total', sa.Numeric(precision=12, scale=2), server_default='0.00', nullable=False),
        sa.Column('shipping_cost_seller', sa.Numeric(precision=12, scale=2), server_default='0.00', nullable=False),
        sa.Column('label_local_path', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_shipments_order_id_orders'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_shipments'))
    )
    op.create_index(op.f('ix_shipments_meli_shipment_id'), 'shipments', ['meli_shipment_id'], unique=True)

    # 15. Auditoría de Rentabilidad Neta
    op.create_table(
        'profitability_audits',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('order_id', sa.UUID(), nullable=False),
        sa.Column('gross_sale_price', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('cogs_total', sa.Numeric(precision=12, scale=2), server_default='0.00', nullable=False),
        sa.Column('meli_commission_fee', sa.Numeric(precision=12, scale=2), server_default='0.00', nullable=False),
        sa.Column('shipping_cost_seller', sa.Numeric(precision=12, scale=2), server_default='0.00', nullable=False),
        sa.Column('packaging_cost', sa.Numeric(precision=10, scale=2), server_default='0.00', nullable=False),
        sa.Column('sat_iva_retention', sa.Numeric(precision=12, scale=2), server_default='0.00', nullable=False),
        sa.Column('sat_isr_retention', sa.Numeric(precision=12, scale=2), server_default='0.00', nullable=False),
        sa.Column('net_profit', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('net_margin_pct', sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_profitability_audits_order_id_orders'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_profitability_audits'))
    )
    op.create_index('ix_profitability_audits_order_margin', 'profitability_audits', ['order_id', 'net_margin_pct'], unique=False)

    # 16. Proveedores y Órdenes de Compra
    op.create_table(
        'suppliers',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('rfc', sa.String(length=13), nullable=True),
        sa.Column('contact_name', sa.String(length=100), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=30), nullable=True),
        sa.Column('lead_time_days', sa.Integer(), server_default='7', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], name=op.f('fk_suppliers_company_id_companies'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_suppliers'))
    )
    op.create_index('ix_suppliers_company_name', 'suppliers', ['company_id', 'name'], unique=False)

    op.create_table(
        'purchase_orders',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('supplier_id', sa.UUID(), nullable=False),
        sa.Column('po_number', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=50), server_default='draft', nullable=False),
        sa.Column('total_amount', sa.Numeric(precision=12, scale=2), server_default='0.00', nullable=False),
        sa.Column('expected_delivery_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], name=op.f('fk_purchase_orders_company_id_companies'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], name=op.f('fk_purchase_orders_supplier_id_suppliers'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_purchase_orders'))
    )
    op.create_index('ix_purchase_orders_company_number', 'purchase_orders', ['company_id', 'po_number'], unique=True)

    op.create_table(
        'purchase_order_items',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('purchase_order_id', sa.UUID(), nullable=False),
        sa.Column('variant_id', sa.UUID(), nullable=False),
        sa.Column('quantity_ordered', sa.Integer(), nullable=False),
        sa.Column('quantity_received', sa.Integer(), server_default='0', nullable=False),
        sa.Column('unit_cost', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['purchase_order_id'], ['purchase_orders.id'], name=op.f('fk_purchase_order_items_purchase_order_id_purchase_orders'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['variant_id'], ['product_variants.id'], name=op.f('fk_purchase_order_items_variant_id_product_variants'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_purchase_order_items'))
    )

    # 17. Configuraciones y Auditoría
    op.create_table(
        'company_settings',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], name=op.f('fk_company_settings_company_id_companies'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_company_settings'))
    )
    op.create_index('ix_company_settings_key', 'company_settings', ['company_id', 'key'], unique=True)

    op.create_table(
        'audit_logs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('entity_name', sa.String(length=100), nullable=False),
        sa.Column('entity_id', sa.String(length=100), nullable=False),
        sa.Column('changes_json', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], name=op.f('fk_audit_logs_company_id_companies'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_logs'))
    )
    op.create_index('ix_audit_logs_company_action_date', 'audit_logs', ['company_id', 'action', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_table('audit_logs')
    op.drop_table('company_settings')
    op.drop_table('purchase_order_items')
    op.drop_table('purchase_orders')
    op.drop_table('suppliers')
    op.drop_table('profitability_audits')
    op.drop_table('shipments')
    op.drop_table('payments')
    op.drop_table('order_items')
    op.drop_table('orders')
    op.drop_table('inventory_movements')
    op.drop_table('inventories')
    op.drop_table('warehouses')
    op.drop_table('product_skus')
    op.drop_table('product_variants')
    op.drop_table('products')
    op.drop_table('meli_accounts')
    op.drop_table('users')
    op.drop_table('companies')
    op.drop_table('tenants')

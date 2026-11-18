"""
Modelos de Abastecimiento, Proveedores, Catálogo de Suministro,
Evaluación de Proveedores, Órdenes de Compra, Recepciones Parciales,
Facturas de Compra y Gastos Asociados (Landed Cost).
"""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import GUID, Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.product import Product, ProductVariant
    from src.models.tenant import Company
    from src.models.warehouse import Warehouse


class Supplier(Base, TimestampMixin):
    """
    Proveedor oficial de mercancía, materias primas o insumos.
    Almacena datos de contacto, condiciones comerciales, bancarias y métricas de desempeño.
    """

    __tablename__ = "suppliers"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)  # e.g. "PROV-001"
    name: Mapped[str] = mapped_column(String(200), nullable=False)  # Razón Social
    commercial_name: Mapped[str | None] = mapped_column(String(200), nullable=True)  # Nombre Comercial
    rfc: Mapped[str | None] = mapped_column(String(13), nullable=True, index=True)  # RFC Fiscal SAT

    # Datos de Contacto
    contact_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Domicilio Fiscal / Almacén
    address_street: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_exterior: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address_interior: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address_neighborhood: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address_state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address_zip: Mapped[str | None] = mapped_column(String(10), nullable=True)
    address_country: Mapped[str] = mapped_column(String(10), default="MEX", nullable=False)

    # Condiciones Comerciales
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)  # 0 = Contado, 15, 30, 60
    lead_time_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)  # Plazo habitual de entrega
    credit_limit: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="MXN", nullable=False)

    # Datos Bancarios para Pagos
    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bank_clabe: Mapped[str | None] = mapped_column(String(18), nullable=True)  # CLABE Interbancaria (18 dígitos)

    # Evaluación y Desempeño Histórico
    rating_score: Mapped[float] = mapped_column(Numeric(3, 2), default=5.00, nullable=False)  # 1.00 a 5.00 estrellas
    on_time_delivery_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=100.00, nullable=False)  # % a tiempo
    quality_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=100.00, nullable=False)  # % sin defectos
    fulfillment_accuracy_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=100.00, nullable=False)  # % piezas

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relaciones
    company: Mapped["Company"] = relationship("Company", back_populates="suppliers")
    purchase_orders: Mapped[list["PurchaseOrder"]] = relationship(
        "PurchaseOrder", back_populates="supplier", cascade="all, delete-orphan"
    )
    supplied_products: Mapped[list["SupplierProduct"]] = relationship(
        "SupplierProduct", back_populates="supplier", cascade="all, delete-orphan"
    )
    evaluations: Mapped[list["SupplierEvaluation"]] = relationship(
        "SupplierEvaluation", back_populates="supplier", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_suppliers_company_name", "company_id", "name"),
        Index("ix_suppliers_company_rfc", "company_id", "rfc"),
        Index("ix_suppliers_company_code", "company_id", "code"),
    )


class SupplierProduct(Base, TimestampMixin):
    """
    Catálogo de productos suministrados por un proveedor.
    Asocia variantes internas con SKUs, costos y plazos del proveedor.
    """

    __tablename__ = "supplier_products"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("products.id", ondelete="CASCADE"), nullable=True, index=True
    )
    variant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=False, index=True
    )

    supplier_sku: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    supplier_product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    purchase_cost: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)  # Precio neto de compra
    currency: Mapped[str] = mapped_column(String(10), default="MXN", nullable=False)
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 4), default=0.1600, nullable=False)  # IVA 16%

    min_order_quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # MOQ
    package_quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # Unidades por caja
    lead_time_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)  # Días de entrega específicos
    is_preferred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # Proveedor preferente

    last_purchased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_purchase_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    supplier: Mapped["Supplier"] = relationship("Supplier", back_populates="supplied_products")
    variant: Mapped["ProductVariant"] = relationship("ProductVariant")
    product: Mapped["Product | None"] = relationship("Product")

    __table_args__ = (
        Index("ix_supp_prod_company_supp_var", "company_id", "supplier_id", "variant_id", unique=True),
    )


class SupplierEvaluation(Base, TimestampMixin):
    """
    Evaluación formal de desempeño de un proveedor.
    Audita cumplimiento en plazos de entrega, calidad de mercancía, precios y servicio.
    """

    __tablename__ = "supplier_evaluations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("purchase_orders.id", ondelete="SET NULL"), nullable=True, index=True
    )

    evaluation_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    evaluated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    evaluator_name: Mapped[str] = mapped_column(String(100), default="Auditor Compras", nullable=False)

    delivery_score: Mapped[float] = mapped_column(Numeric(3, 2), default=5.00, nullable=False)  # 1.00 a 5.00
    quality_score: Mapped[float] = mapped_column(Numeric(3, 2), default=5.00, nullable=False)  # 1.00 a 5.00
    price_score: Mapped[float] = mapped_column(Numeric(3, 2), default=5.00, nullable=False)  # 1.00 a 5.00
    communication_score: Mapped[float] = mapped_column(Numeric(3, 2), default=5.00, nullable=False)  # 1.00 a 5.00
    overall_score: Mapped[float] = mapped_column(Numeric(3, 2), default=5.00, nullable=False)

    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_plan: Mapped[str | None] = mapped_column(Text, nullable=True)

    supplier: Mapped["Supplier"] = relationship("Supplier", back_populates="evaluations")
    purchase_order: Mapped["PurchaseOrder | None"] = relationship("PurchaseOrder", back_populates="evaluations")

    __table_args__ = (
        Index("ix_supp_eval_company_supplier", "company_id", "supplier_id"),
    )


class PurchaseOrder(Base, TimestampMixin):
    """
    Orden de compra formal para abastecimiento de inventario.
    Incorpora workflow estricto de aprobación:
    draft -> pending_approval -> approved -> issued -> partially_received / received -> closed.
    Garantiza: 'No generar compras ni pagos reales sin autorización'.
    """

    __tablename__ = "purchase_orders"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True, index=True
    )

    po_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # e.g. "OC-2026-0001"
    # Estados: draft, pending_approval, approved, issued, partially_received, received, cancelled, closed
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False, index=True)

    order_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    expected_delivery_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_delivery_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    currency: Mapped[str] = mapped_column(String(10), default="MXN", nullable=False)
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    tax_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    shipping_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    other_expenses: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)

    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    payment_status: Mapped[str] = mapped_column(
        String(50), default="unpaid", nullable=False, index=True
    )  # unpaid, partially_paid, paid

    # Control de Autorización Previa de Compra y Pago
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    payment_authorized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    payment_authorized_by_user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    payment_authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relaciones
    supplier: Mapped["Supplier"] = relationship("Supplier", back_populates="purchase_orders")
    warehouse: Mapped["Warehouse | None"] = relationship("Warehouse")
    items: Mapped[list["PurchaseOrderItem"]] = relationship(
        "PurchaseOrderItem", back_populates="purchase_order", cascade="all, delete-orphan"
    )
    receipts: Mapped[list["GoodsReceipt"]] = relationship(
        "GoodsReceipt", back_populates="purchase_order", cascade="all, delete-orphan"
    )
    invoices: Mapped[list["PurchaseInvoice"]] = relationship(
        "PurchaseInvoice", back_populates="purchase_order", cascade="all, delete-orphan"
    )
    expenses: Mapped[list["PurchaseExpense"]] = relationship(
        "PurchaseExpense", back_populates="purchase_order", cascade="all, delete-orphan"
    )
    evaluations: Mapped[list["SupplierEvaluation"]] = relationship(
        "SupplierEvaluation", back_populates="purchase_order"
    )

    __table_args__ = (
        Index("ix_purchase_orders_company_number", "company_id", "po_number", unique=True),
        Index("ix_purchase_orders_company_status", "company_id", "status"),
    )


class PurchaseOrderItem(Base, TimestampMixin):
    """Partida individual de mercancía solicitada en una orden de compra."""

    __tablename__ = "purchase_order_items"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    variant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=False, index=True
    )

    sku: Mapped[str | None] = mapped_column(String(100), nullable=True, default="", index=True)
    product_name: Mapped[str | None] = mapped_column(String(255), nullable=True, default="")
    quantity_ordered: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quantity_pending: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    unit_cost: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 4), default=0.1600, nullable=False)
    total_cost: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True, default=0.0)

    # Estado de la partida: pending, partially_received, completed, cancelled
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)

    purchase_order: Mapped["PurchaseOrder"] = relationship("PurchaseOrder", back_populates="items")
    variant: Mapped["ProductVariant"] = relationship("ProductVariant")
    product: Mapped["Product | None"] = relationship("Product")


class GoodsReceipt(Base, TimestampMixin):
    """
    Recepción física de mercancía en almacén (Goods Receipt Note / Albarán de Entrada).
    Audita entradas de inventario y recepciones parciales.
    """

    __tablename__ = "goods_receipts"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True
    )

    receipt_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # e.g. "REC-2026-0001"
    receipt_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    delivery_note_number: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Remisión proveedor
    carrier: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    status: Mapped[str] = mapped_column(String(50), default="confirmed", nullable=False)  # draft, confirmed, cancelled
    received_by_user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    received_by_name: Mapped[str] = mapped_column(String(100), default="Encargado Almacén", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    purchase_order: Mapped["PurchaseOrder"] = relationship("PurchaseOrder", back_populates="receipts")
    supplier: Mapped["Supplier"] = relationship("Supplier")
    warehouse: Mapped["Warehouse"] = relationship("Warehouse")
    items: Mapped[list["GoodsReceiptItem"]] = relationship(
        "GoodsReceiptItem", back_populates="receipt", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_goods_receipts_company_number", "company_id", "receipt_number", unique=True),
    )


class GoodsReceiptItem(Base, TimestampMixin):
    """Partida individual recibida físicamente en almacén con soporte de rechazo parcial."""

    __tablename__ = "goods_receipt_items"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    receipt_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("goods_receipts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purchase_order_item_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("purchase_order_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    variant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=False, index=True
    )

    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity_received: Mapped[int] = mapped_column(Integer, nullable=False)  # Unidades aceptadas e ingresadas
    quantity_rejected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # Unidades rechazadas
    rejection_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unit_cost: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    batch_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expiry_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    location_bin: Mapped[str | None] = mapped_column(String(50), nullable=True)  # Ubicación en almacén

    receipt: Mapped["GoodsReceipt"] = relationship("GoodsReceipt", back_populates="items")
    po_item: Mapped["PurchaseOrderItem"] = relationship("PurchaseOrderItem")
    variant: Mapped["ProductVariant"] = relationship("ProductVariant")


class PurchaseInvoice(Base, TimestampMixin):
    """
    Factura de proveedor (CFDI 4.0 o comprobante fiscal de adquisición).
    Relaciona la compra formal con las cuentas por pagar y deducciones fiscales.
    """

    __tablename__ = "purchase_invoices"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True
    )

    invoice_series: Mapped[str | None] = mapped_column(String(20), nullable=True)
    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    uuid_sat: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)  # Folio Fiscal Digital SAT

    invoice_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="MXN", nullable=False)
    exchange_rate: Mapped[float] = mapped_column(Numeric(8, 4), default=1.0000, nullable=False)

    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    tax_iva: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    tax_retention_iva: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    tax_retention_isr: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    payment_status: Mapped[str] = mapped_column(
        String(50), default="unpaid", nullable=False, index=True
    )  # unpaid, partially_paid, paid
    amount_paid: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)

    pdf_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    xml_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="valid", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    purchase_order: Mapped["PurchaseOrder"] = relationship("PurchaseOrder", back_populates="invoices")
    supplier: Mapped["Supplier"] = relationship("Supplier")

    __table_args__ = (
        Index("ix_purchase_invoices_company_number", "company_id", "invoice_number"),
    )


class PurchaseExpense(Base, TimestampMixin):
    """
    Gastos adicionales asociados al abastecimiento para costeo integral (Landed Cost).
    Incluye fletes de proveedor, aranceles, seguros y maniobras.
    """

    __tablename__ = "purchase_expenses"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )

    expense_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # freight, customs, insurance, handling, storage, other
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="MXN", nullable=False)
    provider_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expense_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    allocation_method: Mapped[str] = mapped_column(
        String(50), default="by_value", nullable=False
    )  # by_value, by_quantity, by_weight
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    purchase_order: Mapped["PurchaseOrder"] = relationship("PurchaseOrder", back_populates="expenses")

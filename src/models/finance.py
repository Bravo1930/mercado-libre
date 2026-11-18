"""Modelos Financieros, Transacciones, Liquidaciones, Gastos Externos y Conciliación."""

from datetime import datetime
from typing import TYPE_CHECKING, Any
import uuid

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from src.models.base import GUID, Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.meli_account import MeliAccount
    from src.models.order import Order
    from src.models.payment import Payment
    from src.models.product import Product, ProductVariant
    from src.models.tenant import Company


class Settlement(Base, TimestampMixin):
    """
    Liquidación o transferencia de fondos desde Mercado Pago hacia la cuenta bancaria del vendedor.
    Agrupa transacciones acreditadas, deducciones de comisiones, fletes, retenciones e impuestos.
    """

    __tablename__ = "settlements"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meli_account_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("meli_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    settlement_number: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    meli_settlement_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="completed", nullable=False, index=True)  # pending, completed, cancelled

    # Información de acreditación / transferencia bancaria (SPEI / CLABE)
    bank_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bank_account_clabe: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Desglose de totales de la liquidación
    gross_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    total_fees: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    total_shipping_costs: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    total_taxes: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    total_refunds: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    total_adjustments: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    net_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)

    date_settled: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relaciones
    company: Mapped["Company"] = relationship("Company")
    meli_account: Mapped["MeliAccount"] = relationship("MeliAccount")
    transactions: Mapped[list["FinancialTransaction"]] = relationship(
        "FinancialTransaction", back_populates="settlement"
    )

    __table_args__ = (
        Index("ix_settlements_company_period", "company_id", "period_start", "period_end"),
    )


class ExternalExpense(Base, TimestampMixin):
    """
    Gasto operativo, logístico o comercial externo registrado manualmente por la empresa.
    Permite auditar costos reales fuera de la plataforma (publicidad externa, empaque, nómina, fletes).
    """

    __tablename__ = "external_expenses"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meli_account_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("meli_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Clasificación del gasto
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # advertising, packaging, shipping, supplies, software, warehouse, taxes, other
    concept: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="MXN", nullable=False)
    expense_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    payment_method: Mapped[str] = mapped_column(String(50), default="bank_transfer", nullable=False)
    vendor_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    invoice_folio: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)  # Folio Fiscal / UUID SAT
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)

    # Relaciones
    company: Mapped["Company"] = relationship("Company")
    meli_account: Mapped["MeliAccount | None"] = relationship("MeliAccount")
    order: Mapped["Order | None"] = relationship("Order")
    product: Mapped["Product | None"] = relationship("Product")
    variant: Mapped["ProductVariant | None"] = relationship("ProductVariant")
    transaction: Mapped["FinancialTransaction | None"] = relationship(
        "FinancialTransaction", back_populates="external_expense", uselist=False
    )

    __table_args__ = (
        Index("ix_external_expenses_company_date", "company_id", "expense_date"),
    )


class FinancialTransaction(Base, TimestampMixin):
    """
    Partida contable individual y granular.
    Conserva origen, fecha, montos brutos, deducciones, retenciones y estado de disponibilidad en Mercado Pago.
    """

    __tablename__ = "financial_transactions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meli_account_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("meli_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("payments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    settlement_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("settlements.id", ondelete="SET NULL"), nullable=True, index=True
    )
    external_expense_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("external_expenses.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Tipo de movimiento contable
    transaction_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # Valores: sale, marketplace_fee, shipping_fee, tax_retention_iva, tax_retention_isr, refund, payout, adjustment, external_expense

    concept: Mapped[str] = mapped_column(String(255), nullable=False)

    # Desglose monetario
    gross_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    fee_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    tax_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    net_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="MXN", nullable=False)

    # Estados del ciclo del dinero en Mercado Pago
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # Valores: pending, accredited, available, settled, withdrawn, refunded, cancelled

    date_created: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    date_accredited: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    date_available: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    date_withdrawn: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    source: Mapped[str] = mapped_column(String(50), nullable=False)  # meli_order, meli_payment, mercado_pago, manual_expense, reconciliation
    external_reference: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_info: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Relaciones
    company: Mapped["Company"] = relationship("Company")
    meli_account: Mapped["MeliAccount | None"] = relationship("MeliAccount")
    order: Mapped["Order | None"] = relationship("Order")
    payment: Mapped["Payment | None"] = relationship("Payment")
    settlement: Mapped["Settlement | None"] = relationship("Settlement", back_populates="transactions")
    external_expense: Mapped["ExternalExpense | None"] = relationship(
        "ExternalExpense", back_populates="transaction"
    )

    __table_args__ = (
        Index("ix_financial_transactions_company_type", "company_id", "transaction_type"),
        Index("ix_financial_transactions_company_status_date", "company_id", "status", "date_created"),
    )


class FinancialDiscrepancy(Base, TimestampMixin):
    """
    Diferencia o discrepancia detectada por el motor de conciliación automática.
    Compara ventas vs pagos acreditados vs liquidaciones y cargos oficiales.
    """

    __tablename__ = "financial_discrepancies"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meli_account_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("meli_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("payments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    settlement_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("settlements.id", ondelete="SET NULL"), nullable=True, index=True
    )

    discrepancy_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # Valores: amount_mismatch, fee_discrepancy, tax_discrepancy, missing_payment, unreconciled_settlement, unexpected_charge, unaccounted_refund

    severity: Mapped[str] = mapped_column(String(20), default="medium", nullable=False, index=True)  # low, medium, high, critical
    status: Mapped[str] = mapped_column(String(30), default="unresolved", nullable=False, index=True)  # unresolved, investigating, resolved, ignored

    expected_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    actual_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    difference_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)  # actual - expected

    description: Mapped[str] = mapped_column(Text, nullable=False)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detection_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    # Relaciones
    company: Mapped["Company"] = relationship("Company")
    meli_account: Mapped["MeliAccount | None"] = relationship("MeliAccount")
    order: Mapped["Order | None"] = relationship("Order")

    __table_args__ = (
        Index("ix_discrepancies_company_status", "company_id", "status"),
        Index("ix_discrepancies_type_severity", "discrepancy_type", "severity"),
    )

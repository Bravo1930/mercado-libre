"""Servicio Central de Finanzas, Mercado Pago, Liquidaciones, Gastos Externos y Conciliación."""

from datetime import datetime, timedelta, timezone
from typing import Any, Literal
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.connectors.meli import MercadoLibreConnector
from src.core.exceptions import AppException, EntityNotFoundException
from src.core.logging import get_logger
from src.models.cost import CostStructure, ProfitabilityAudit
from src.models.finance import ExternalExpense, FinancialDiscrepancy, FinancialTransaction, Settlement
from src.models.meli_account import MeliAccount
from src.models.order import Order, OrderItem
from src.models.payment import Payment
from src.models.product import Product, ProductVariant
from src.schemas.finance import (
    AccountFinancialReportItem,
    AccountFinancialReportResponse,
    DiscrepancyResolveRequest,
    ExternalExpenseCreateRequest,
    FinancialDiscrepancyResponse,
    FinancialKPIsResponse,
    FinancialTransactionResponse,
    OrderFinancialReportResponse,
    PeriodFinancialReportResponse,
    ProductFinancialReportItem,
    ProductFinancialReportResponse,
    ReconciliationRunResponse,
    SettlementCreateRequest,
)

logger = get_logger("finance_service")


def _norm_dt(dt: datetime) -> datetime:
    """Normaliza un objeto datetime a UTC con tzinfo para comparaciones seguras."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class FinanceService:
    """
    Motor financiero central del ERP para Mercado Libre México.
    
    Gestiona:
    - Las 7 métricas clave: Bruto, Neto Estimado, Acreditado, Disponible, Retirado, Reembolsos y Cargos Definitivos.
    - Partidas contables de pagos, comisiones, fletes y retenciones SAT (IVA 8%, ISR 1%).
    - Liquidaciones y transferencias bancarias (SPEI / CLABE).
    - Registro de gastos operativos externos manuales.
    - Motor de conciliación automática y detección de discrepancias.
    - Reportes multidimensionales por cuenta, producto, pedido y periodo.
    """

    async def record_transactions_for_order(
        self,
        session: AsyncSession,
        order: Order,
        meli_account: MeliAccount,
        profitability_audit: Any = None,
    ) -> list[FinancialTransaction]:
        """
        Genera y asocia las partidas contables oficiales de una orden de venta:
        1. Venta Bruta (sale)
        2. Comisión de Mercado Libre (marketplace_fee)
        3. Cargo de flete a cargo del vendedor (shipping_fee)
        4. Retenciones fiscales SAT (IVA 8% e ISR 1%)
        5. Reembolso si la orden fue cancelada (refund)
        """
        # Eliminar transacciones previas asociadas a esta orden para evitar duplicidad al actualizar
        stmt_prev = select(FinancialTransaction).where(FinancialTransaction.order_id == order.id)
        prev_txs = (await session.execute(stmt_prev)).scalars().all()
        for p in prev_txs:
            await session.delete(p)
        await session.flush()

        txs: list[FinancialTransaction] = []
        is_paid = order.status in ["paid", "confirmed", "delivered"]
        is_cancelled = order.status == "cancelled"

        # Obtener auditoría de rentabilidad de manera segura sin disparar lazy loads
        if profitability_audit is None:
            if hasattr(order, "__dict__") and "profitability" in order.__dict__ and order.__dict__["profitability"]:
                profitability_audit = order.__dict__["profitability"]
            elif order.id:
                stmt_p = select(ProfitabilityAudit).where(ProfitabilityAudit.order_id == order.id)
                profitability_audit = (await session.execute(stmt_p)).scalars().first()

        # 1. Transacción de Venta Bruta
        sale_status = "refunded" if is_cancelled else ("accredited" if is_paid else "pending")
        tx_sale = FinancialTransaction(
            company_id=meli_account.company_id,
            meli_account_id=meli_account.id,
            order_id=order.id,
            transaction_type="sale",
            concept=f"Cobro de venta orden MeLi #{order.meli_order_id}",
            gross_amount=float(order.total_amount),
            fee_amount=0.0,
            tax_amount=0.0,
            net_amount=float(order.total_amount),
            currency=order.currency_id or "MXN",
            status=sale_status,
            date_created=_norm_dt(order.date_created_meli),
            date_accredited=_norm_dt(order.date_created_meli) if is_paid else None,
            date_available=_norm_dt(order.date_created_meli + timedelta(days=2)) if is_paid else None,
            source="meli_order",
            external_reference=str(order.meli_order_id),
            notes=f"Venta en tienda {meli_account.nickname}. Comprador: {order.buyer_nickname or 'Anónimo'}",
        )
        session.add(tx_sale)
        txs.append(tx_sale)

        # 2. Transacción de Comisión de Mercado Libre
        if float(order.meli_fee_amount) > 0:
            tx_fee = FinancialTransaction(
                company_id=meli_account.company_id,
                meli_account_id=meli_account.id,
                order_id=order.id,
                transaction_type="marketplace_fee",
                concept=f"Comisión por venta MeLi #{order.meli_order_id}",
                gross_amount=0.0,
                fee_amount=float(order.meli_fee_amount),
                tax_amount=0.0,
                net_amount=-float(order.meli_fee_amount),
                currency=order.currency_id or "MXN",
                status="cancelled" if is_cancelled else "settled",
                date_created=_norm_dt(order.date_created_meli),
                source="meli_order",
                external_reference=str(order.meli_order_id),
            )
            session.add(tx_fee)
            txs.append(tx_fee)

        # 3. Transacción de Cargo de Envío a cargo del vendedor
        if float(order.shipping_cost_seller) > 0:
            tx_ship = FinancialTransaction(
                company_id=meli_account.company_id,
                meli_account_id=meli_account.id,
                order_id=order.id,
                transaction_type="shipping_fee",
                concept=f"Cargo de flete Mercado Envíos orden #{order.meli_order_id}",
                gross_amount=0.0,
                fee_amount=float(order.shipping_cost_seller),
                tax_amount=0.0,
                net_amount=-float(order.shipping_cost_seller),
                currency=order.currency_id or "MXN",
                status="cancelled" if is_cancelled else "settled",
                date_created=_norm_dt(order.date_created_meli),
                source="meli_order",
                external_reference=str(order.meli_order_id),
            )
            session.add(tx_ship)
            txs.append(tx_ship)

        # 4. Transacciones de Retención Fiscal SAT México (IVA 8% e ISR 1%)
        if profitability_audit:
            iva_retention = float(getattr(profitability_audit, "sat_iva_retention", 0.0) or 0.0)
            if iva_retention > 0:
                tx_iva = FinancialTransaction(
                    company_id=meli_account.company_id,
                    meli_account_id=meli_account.id,
                    order_id=order.id,
                    transaction_type="tax_retention_iva",
                    concept=f"Retención SAT IVA 8% plataforma digital orden #{order.meli_order_id}",
                    gross_amount=0.0,
                    fee_amount=0.0,
                    tax_amount=iva_retention,
                    net_amount=-iva_retention,
                    currency="MXN",
                    status="cancelled" if is_cancelled else "settled",
                    date_created=_norm_dt(order.date_created_meli),
                    source="meli_order",
                    external_reference=str(order.meli_order_id),
                )
                session.add(tx_iva)
                txs.append(tx_iva)

            isr_retention = float(getattr(profitability_audit, "sat_isr_retention", 0.0) or 0.0)
            if isr_retention > 0:
                tx_isr = FinancialTransaction(
                    company_id=meli_account.company_id,
                    meli_account_id=meli_account.id,
                    order_id=order.id,
                    transaction_type="tax_retention_isr",
                    concept=f"Retención SAT ISR 1% plataforma digital orden #{order.meli_order_id}",
                    gross_amount=0.0,
                    fee_amount=0.0,
                    tax_amount=isr_retention,
                    net_amount=-isr_retention,
                    currency="MXN",
                    status="cancelled" if is_cancelled else "settled",
                    date_created=_norm_dt(order.date_created_meli),
                    source="meli_order",
                    external_reference=str(order.meli_order_id),
                )
                session.add(tx_isr)
                txs.append(tx_isr)

        # 5. Transacción de Reembolso si la orden fue cancelada
        if is_cancelled:
            tx_refund = FinancialTransaction(
                company_id=meli_account.company_id,
                meli_account_id=meli_account.id,
                order_id=order.id,
                transaction_type="refund",
                concept=f"Reembolso por pedido cancelado #{order.meli_order_id}",
                gross_amount=-float(order.total_amount),
                fee_amount=0.0,
                tax_amount=0.0,
                net_amount=-float(order.total_amount),
                currency=order.currency_id or "MXN",
                status="refunded",
                date_created=_norm_dt(order.cancelled_at or datetime.now(timezone.utc)),
                source="meli_order",
                external_reference=str(order.meli_order_id),
                notes=f"Cancelado por {order.cancel_responsible or 'desconocido'}: {order.cancel_reason or 'Sin motivo'}",
            )
            session.add(tx_refund)
            txs.append(tx_refund)

        await session.flush()
        return txs

    async def register_external_expense(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        payload: ExternalExpenseCreateRequest,
        created_by_user_id: uuid.UUID | None = None,
    ) -> ExternalExpense:
        """
        Permite registrar gastos operativos externos manualmente (publicidad externa, empaques,
        nómina, fletes privados) e impacta de inmediato la contabilidad y utilidad neta real.
        """
        # Validar pertenencia de la cuenta MeLi si se proporcionó
        if payload.meli_account_id:
            account = await session.get(MeliAccount, payload.meli_account_id)
            if not account or account.company_id != company_id:
                raise EntityNotFoundException("Cuenta de Mercado Libre", str(payload.meli_account_id))

        expense = ExternalExpense(
            company_id=company_id,
            meli_account_id=payload.meli_account_id,
            order_id=payload.order_id,
            product_id=payload.product_id,
            variant_id=payload.variant_id,
            category=payload.category,
            concept=payload.concept,
            amount=payload.amount,
            currency=payload.currency,
            expense_date=_norm_dt(payload.expense_date),
            payment_method=payload.payment_method,
            vendor_name=payload.vendor_name,
            invoice_folio=payload.invoice_folio,
            notes=payload.notes,
            created_by_user_id=created_by_user_id,
        )
        session.add(expense)
        await session.flush()

        # Generar partida contable correspondiente
        tx = FinancialTransaction(
            company_id=company_id,
            meli_account_id=payload.meli_account_id,
            order_id=payload.order_id,
            external_expense_id=expense.id,
            transaction_type="external_expense",
            concept=f"Gasto Externo [{payload.category.upper()}]: {payload.concept}",
            gross_amount=0.0,
            fee_amount=payload.amount,
            tax_amount=0.0,
            net_amount=-payload.amount,
            currency=payload.currency,
            status="settled",
            date_created=_norm_dt(payload.expense_date),
            source="manual_expense",
            external_reference=payload.invoice_folio,
            notes=payload.notes,
        )
        session.add(tx)
        await session.flush()
        return expense

    async def record_settlement(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        payload: SettlementCreateRequest,
    ) -> Settlement:
        """
        Registra una liquidación y transferencia de fondos desde Mercado Pago hacia la cuenta bancaria.
        Actualiza el dinero retirado y lo vincula con transacciones.
        """
        account = await session.get(MeliAccount, payload.meli_account_id)
        if not account or account.company_id != company_id:
            raise EntityNotFoundException("Cuenta de Mercado Libre", str(payload.meli_account_id))

        settlement = Settlement(
            company_id=company_id,
            meli_account_id=payload.meli_account_id,
            settlement_number=payload.settlement_number,
            meli_settlement_id=payload.meli_settlement_id,
            period_start=_norm_dt(payload.period_start),
            period_end=_norm_dt(payload.period_end),
            status="completed",
            bank_name=payload.bank_name,
            bank_account_clabe=payload.bank_account_clabe,
            gross_amount=payload.gross_amount,
            total_fees=payload.total_fees,
            total_shipping_costs=payload.total_shipping_costs,
            total_taxes=payload.total_taxes,
            total_refunds=payload.total_refunds,
            total_adjustments=payload.total_adjustments,
            net_amount=payload.net_amount,
            date_settled=_norm_dt(payload.date_settled or datetime.now(timezone.utc)),
            notes=payload.notes,
        )
        session.add(settlement)
        await session.flush()

        # Registrar transacción contable de retiro bancario (payout)
        tx_payout = FinancialTransaction(
            company_id=company_id,
            meli_account_id=payload.meli_account_id,
            settlement_id=settlement.id,
            transaction_type="payout",
            concept=f"Retiro bancario liquidación #{payload.settlement_number} a {payload.bank_name or 'Banco'}",
            gross_amount=0.0,
            fee_amount=0.0,
            tax_amount=0.0,
            net_amount=payload.net_amount,
            currency="MXN",
            status="withdrawn",
            date_created=_norm_dt(payload.date_settled or datetime.now(timezone.utc)),
            date_withdrawn=_norm_dt(payload.date_settled or datetime.now(timezone.utc)),
            source="mercado_pago",
            external_reference=payload.settlement_number,
            notes=f"Transferido a cuenta CLABE {payload.bank_account_clabe or 'N/A'}",
        )
        session.add(tx_payout)
        await session.flush()
        return settlement

    async def get_financial_kpis(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        meli_account_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> FinancialKPIsResponse:
        """
        Calcula las 7 métricas financieras obligatorias claramente diferenciadas:
        1. Importe bruto: Ventas brutas cobradas (órdenes no canceladas).
        2. Importe neto estimado: Bruto - comisiones - fletes - retenciones SAT - empaques.
        3. Dinero acreditado: Pagos aprobados en MP pendientes de cumplir plazo de liberación.
        4. Dinero disponible: Fondos líquidos liberados listos para retiro menos retiros ejecutados.
        5. Dinero retirado: Total transferido exitosamente a cuentas bancarias CLABE.
        6. Reembolsos: Devoluciones por cancelaciones o reclamos.
        7. Cargos definitivos: Comisiones reales MeLi + fletes vendedor + retenciones SAT cobradas.
        """
        # Filtros base
        order_stmt = (
            select(Order)
            .join(MeliAccount, Order.meli_account_id == MeliAccount.id)
            .where(MeliAccount.company_id == company_id)
            .options(
                selectinload(Order.profitability),
                selectinload(Order.payments),
            )
        )
        if meli_account_id:
            order_stmt = order_stmt.where(Order.meli_account_id == meli_account_id)
        if date_from:
            order_stmt = order_stmt.where(Order.date_created_meli >= _norm_dt(date_from))
        if date_to:
            order_stmt = order_stmt.where(Order.date_created_meli <= _norm_dt(date_to))

        orders = (await session.execute(order_stmt)).scalars().all()

        # Filtrar órdenes por estado
        valid_orders = [o for o in orders if o.status != "cancelled"]
        cancelled_orders = [o for o in orders if o.status == "cancelled"]

        # 1. Importe Bruto (Ventas totales no canceladas)
        gross_amount = round(sum(float(o.total_amount) for o in valid_orders), 2)

        # 7. Cargos Definitivos (Comisiones MeLi + fletes vendedor + retenciones SAT)
        total_commissions = round(sum(float(o.meli_fee_amount) for o in valid_orders), 2)
        total_shipping_costs = round(sum(float(o.shipping_cost_seller) for o in valid_orders), 2)
        total_sat_taxes = round(
            sum(
                float(o.profitability.sat_iva_retention + o.profitability.sat_isr_retention)
                for o in valid_orders if o.profitability
            ),
            2,
        )
        total_packaging = round(
            sum(float(o.profitability.packaging_cost) for o in valid_orders if o.profitability), 2
        )
        total_cogs = round(sum(float(o.cogs_total) for o in valid_orders), 2)

        definitive_charge_amount = round(total_commissions + total_shipping_costs + total_sat_taxes, 2)

        # 2. Importe Neto Estimado
        estimated_net_amount = round(
            gross_amount - definitive_charge_amount - total_packaging, 2
        )

        # 6. Reembolsos
        refund_amount = round(sum(float(o.total_amount) for o in cancelled_orders), 2)

        # 5. Dinero Retirado (Liquidaciones ejecutadas a cuenta bancaria)
        settle_stmt = select(Settlement).where(Settlement.company_id == company_id, Settlement.status == "completed")
        if meli_account_id:
            settle_stmt = settle_stmt.where(Settlement.meli_account_id == meli_account_id)
        settlements = (await session.execute(settle_stmt)).scalars().all()
        withdrawn_amount = round(sum(float(s.net_amount) for s in settlements), 2)

        # 3. Dinero Acreditado vs 4. Dinero Disponible
        # Dinero acreditado: órdenes pagadas en tránsito o en periodo de garantía (ej. delivered hace < 2 días o en tránsito)
        # Dinero disponible: órdenes entregadas y liberadas que aún no han sido retiradas
        now_utc = datetime.now(timezone.utc)
        accredited_amount = 0.0
        available_accum = 0.0

        for o in valid_orders:
            # Neto de esta orden que entra a MP
            order_mp_net = float(o.total_amount) - float(o.meli_fee_amount) - float(o.shipping_cost_seller)
            if o.profitability:
                order_mp_net -= float(o.profitability.sat_iva_retention + o.profitability.sat_isr_retention)
            order_mp_net = max(0.0, order_mp_net)

            # Si ya fue entregada y tiene más de 2 días de entregada, el dinero está disponible
            order_date = _norm_dt(o.date_created_meli)
            is_released = o.status == "delivered" or (now_utc - order_date).days >= 2

            if is_released:
                available_accum += order_mp_net
            else:
                accredited_amount += order_mp_net

        accredited_amount = round(accredited_amount, 2)
        # Dinero disponible es lo liberado menos lo que ya se retiró a banco
        available_amount = round(max(0.0, available_accum - withdrawn_amount), 2)

        # Gastos externos manuales
        exp_stmt = select(ExternalExpense).where(ExternalExpense.company_id == company_id)
        if meli_account_id:
            exp_stmt = exp_stmt.where(
                or_(ExternalExpense.meli_account_id == meli_account_id, ExternalExpense.meli_account_id == None)
            )
        expenses = (await session.execute(exp_stmt)).scalars().all()
        external_expenses_total = round(sum(float(e.amount) for e in expenses), 2)

        # Utilidad Neta Real = Importe Bruto - Cargos Definitivos - Empaque - COGS - Gastos Externos
        real_net_profit = round(
            gross_amount - definitive_charge_amount - total_packaging - total_cogs - external_expenses_total, 2
        )
        profit_margin_pct = round((real_net_profit / gross_amount) * 100, 2) if gross_amount > 0 else 0.0

        return FinancialKPIsResponse(
            gross_amount=gross_amount,
            estimated_net_amount=estimated_net_amount,
            accredited_amount=accredited_amount,
            available_amount=available_amount,
            withdrawn_amount=withdrawn_amount,
            refund_amount=refund_amount,
            definitive_charge_amount=definitive_charge_amount,
            total_cogs=total_cogs,
            external_expenses_total=external_expenses_total,
            real_net_profit=real_net_profit,
            profit_margin_pct=profit_margin_pct,
            currency="MXN",
            period="Consolidado de la empresa",
        )

    async def run_automatic_reconciliation(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        meli_account_id: uuid.UUID | None = None,
    ) -> ReconciliationRunResponse:
        """
        Motor de conciliación automática entre Ventas, Pagos de Mercado Pago y Liquidaciones:
        1. Comprueba si los montos cobrados en órdenes coinciden con los pagos aprobados.
        2. Detecta discrepancias entre comisiones estimadas y cobros reales de Mercado Libre.
        3. Comprueba que las retenciones SAT cumplan con las tasas vigentes (IVA 8%, ISR 1%).
        4. Detecta órdenes canceladas donde el dinero no haya sido reembolsado debidamente.
        5. Detecta liquidaciones bancarias con desajustes frente a las ventas netas.
        """
        # Cargar órdenes
        order_stmt = (
            select(Order)
            .join(MeliAccount, Order.meli_account_id == MeliAccount.id)
            .where(MeliAccount.company_id == company_id)
            .options(
                selectinload(Order.payments),
                selectinload(Order.profitability),
                selectinload(Order.meli_account),
            )
        )
        if meli_account_id:
            order_stmt = order_stmt.where(Order.meli_account_id == meli_account_id)

        orders = (await session.execute(order_stmt)).scalars().all()

        # Cargar liquidaciones
        settle_stmt = select(Settlement).where(Settlement.company_id == company_id)
        if meli_account_id:
            settle_stmt = settle_stmt.where(Settlement.meli_account_id == meli_account_id)
        settlements = (await session.execute(settle_stmt)).scalars().all()

        discrepancies: list[FinancialDiscrepancy] = []
        matched_orders_count = 0
        total_difference_amount = 0.0
        now_utc = datetime.now(timezone.utc)

        # 1. Auditar órdenes vs pagos de Mercado Pago
        for o in orders:
            is_matched = True
            total_paid = sum(float(p.transaction_amount) for p in o.payments if p.status == "approved")

            # REGLA A: Órdenes pagadas sin pago aprobado o con diferencia de monto
            if o.status in ["paid", "confirmed", "delivered"]:
                if len(o.payments) == 0 and float(o.paid_amount) > 0:
                    diff = round(float(o.total_amount), 2)
                    disc = FinancialDiscrepancy(
                        company_id=company_id,
                        meli_account_id=o.meli_account_id,
                        order_id=o.id,
                        discrepancy_type="missing_payment",
                        severity="high",
                        status="unresolved",
                        expected_amount=float(o.total_amount),
                        actual_amount=0.0,
                        difference_amount=-diff,
                        description=(
                            f"Orden #{o.meli_order_id} figura como pagada por ${float(o.total_amount):.2f} "
                            "pero no cuenta con registro de pago aprobado en Mercado Pago."
                        ),
                        detection_date=now_utc,
                    )
                    session.add(disc)
                    discrepancies.append(disc)
                    total_difference_amount += abs(diff)
                    is_matched = False

                elif len(o.payments) > 0 and abs(total_paid - float(o.total_amount)) > 0.05:
                    diff = round(total_paid - float(o.total_amount), 2)
                    disc = FinancialDiscrepancy(
                        company_id=company_id,
                        meli_account_id=o.meli_account_id,
                        order_id=o.id,
                        discrepancy_type="amount_mismatch",
                        severity="high",
                        status="unresolved",
                        expected_amount=float(o.total_amount),
                        actual_amount=total_paid,
                        difference_amount=diff,
                        description=(
                            f"Desfase en orden #{o.meli_order_id}: importe de orden ${float(o.total_amount):.2f} "
                            f"difiere del total pagado en Mercado Pago ${total_paid:.2f}."
                        ),
                        detection_date=now_utc,
                    )
                    session.add(disc)
                    discrepancies.append(disc)
                    total_difference_amount += abs(diff)
                    is_matched = False

            # REGLA B: Órdenes canceladas con dinero aún sin reembolsar
            elif o.status == "cancelled":
                if total_paid > 0:
                    # Comprobar si hay contracargo/reembolso registrado
                    refunded_tx = (
                        await session.execute(
                            select(FinancialTransaction).where(
                                FinancialTransaction.order_id == o.id,
                                FinancialTransaction.transaction_type == "refund",
                            )
                        )
                    ).scalars().first()

                    if not refunded_tx:
                        diff = round(total_paid, 2)
                        disc = FinancialDiscrepancy(
                            company_id=company_id,
                            meli_account_id=o.meli_account_id,
                            order_id=o.id,
                            discrepancy_type="unaccounted_refund",
                            severity="critical",
                            status="unresolved",
                            expected_amount=0.0,
                            actual_amount=total_paid,
                            difference_amount=diff,
                            description=(
                                f"Orden cancelada #{o.meli_order_id} mantiene cobro de ${total_paid:.2f} "
                                "sin partida de reembolso formal acreditada en Mercado Pago."
                            ),
                            detection_date=now_utc,
                        )
                        session.add(disc)
                        discrepancies.append(disc)
                        total_difference_amount += abs(diff)
                        is_matched = False

            # REGLA C: Discrepancia en comisiones de Mercado Libre
            if o.payments:
                reported_fee = sum(float(p.marketplace_fee) for p in o.payments)
                expected_fee = float(o.meli_fee_amount)
                if reported_fee > 0 and expected_fee > 0 and abs(reported_fee - expected_fee) > 1.00:
                    diff = round(reported_fee - expected_fee, 2)
                    disc = FinancialDiscrepancy(
                        company_id=company_id,
                        meli_account_id=o.meli_account_id,
                        order_id=o.id,
                        discrepancy_type="fee_discrepancy",
                        severity="medium",
                        status="unresolved",
                        expected_amount=expected_fee,
                        actual_amount=reported_fee,
                        difference_amount=diff,
                        description=(
                            f"Comisión MeLi en orden #{o.meli_order_id}: esperada ${expected_fee:.2f} "
                            f"vs cobrada en Mercado Pago ${reported_fee:.2f}."
                        ),
                        detection_date=now_utc,
                    )
                    session.add(disc)
                    discrepancies.append(disc)
                    total_difference_amount += abs(diff)
                    is_matched = False

            if is_matched:
                matched_orders_count += 1

        await session.flush()

        return ReconciliationRunResponse(
            total_orders_audited=len(orders),
            total_payments_audited=sum(len(o.payments) for o in orders),
            total_settlements_audited=len(settlements),
            matched_orders_count=matched_orders_count,
            discrepancies_found_count=len(discrepancies),
            total_difference_amount=round(total_difference_amount, 2),
            discrepancies=[FinancialDiscrepancyResponse.model_validate(d) for d in discrepancies],
        )

    async def generate_account_financial_report(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> AccountFinancialReportResponse:
        """Genera un reporte financiero auditado por cada cuenta de Mercado Libre conectada."""
        accounts = (
            await session.execute(
                select(MeliAccount).where(MeliAccount.company_id == company_id, MeliAccount.is_active == True)
            )
        ).scalars().all()

        report_items: list[AccountFinancialReportItem] = []

        for acc in accounts:
            kpis = await self.get_financial_kpis(
                session=session,
                company_id=company_id,
                meli_account_id=acc.id,
                date_from=date_from,
                date_to=date_to,
            )

            # Contar órdenes de la cuenta
            stmt_cnt = select(func.count(Order.id)).where(
                Order.meli_account_id == acc.id, Order.status != "cancelled"
            )
            total_orders = (await session.execute(stmt_cnt)).scalar() or 0

            # Desglose de comisiones y fletes
            stmt_fees = select(
                func.sum(Order.meli_fee_amount),
                func.sum(Order.shipping_cost_seller),
            ).where(Order.meli_account_id == acc.id, Order.status != "cancelled")
            fee_res = (await session.execute(stmt_fees)).first()
            commissions = float(fee_res[0] or 0.0) if fee_res else 0.0
            shipping = float(fee_res[1] or 0.0) if fee_res else 0.0

            # Retenciones SAT
            stmt_tax = (
                select(
                    func.sum(ProfitabilityAudit.sat_iva_retention + ProfitabilityAudit.sat_isr_retention)
                )
                .join(Order, ProfitabilityAudit.order_id == Order.id)
                .where(Order.meli_account_id == acc.id, Order.status != "cancelled")
            )
            sat_taxes = float((await session.execute(stmt_tax)).scalar() or 0.0)

            report_items.append(
                AccountFinancialReportItem(
                    account_id=acc.id,
                    nickname=acc.nickname,
                    site_id=acc.site_id,
                    total_orders=total_orders,
                    gross_sales=kpis.gross_amount,
                    commissions_meli=round(commissions, 2),
                    shipping_charges=round(shipping, 2),
                    sat_taxes=round(sat_taxes, 2),
                    refunds=kpis.refund_amount,
                    net_accredited=kpis.accredited_amount,
                    withdrawn=kpis.withdrawn_amount,
                    available_balance=kpis.available_amount,
                )
            )

        return AccountFinancialReportResponse(
            total_accounts=len(report_items),
            accounts=report_items,
        )

    async def generate_product_financial_report(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> ProductFinancialReportResponse:
        """
        Genera el reporte de rentabilidad real por producto y SKU, incluyendo
        ventas brutas, costo de adquisición (COGS), comisiones MeLi, retenciones y margen neto.
        """
        # Cargar partidas vendidas de órdenes válidas
        stmt = (
            select(OrderItem)
            .join(Order, OrderItem.order_id == Order.id)
            .join(MeliAccount, Order.meli_account_id == MeliAccount.id)
            .where(MeliAccount.company_id == company_id, Order.status != "cancelled")
            .options(
                selectinload(OrderItem.product),
                selectinload(OrderItem.variant),
                selectinload(OrderItem.order).selectinload(Order.profitability),
            )
        )
        if date_from:
            stmt = stmt.where(Order.date_created_meli >= _norm_dt(date_from))
        if date_to:
            stmt = stmt.where(Order.date_created_meli <= _norm_dt(date_to))

        items = (await session.execute(stmt)).scalars().all()

        sku_data: dict[str, dict[str, Any]] = {}

        for it in items:
            sku = it.seller_sku or "SIN-SKU"
            if sku not in sku_data:
                sku_data[sku] = {
                    "product_id": it.product_id,
                    "variant_id": it.variant_id,
                    "sku": sku,
                    "product_name": it.title,
                    "units_sold": 0,
                    "gross_sales": 0.0,
                    "cogs_total": 0.0,
                    "commissions_meli": 0.0,
                    "shipping_costs": 0.0,
                    "sat_taxes": 0.0,
                    "external_expenses": 0.0,
                }

            qty = it.quantity
            item_gross = float(it.unit_price) * qty
            item_cogs = float(it.cogs_unit) * qty
            item_fee = float(it.sale_fee)

            sku_data[sku]["units_sold"] += qty
            sku_data[sku]["gross_sales"] += item_gross
            sku_data[sku]["cogs_total"] += item_cogs
            sku_data[sku]["commissions_meli"] += item_fee

            # Prorratear retención fiscal y flete si la orden tiene profitability
            if it.order and it.order.profitability:
                order_total = float(it.order.total_amount) or 1.0
                ratio = min(1.0, item_gross / order_total)
                taxes = float(it.order.profitability.sat_iva_retention + it.order.profitability.sat_isr_retention)
                shipping = float(it.order.shipping_cost_seller)
                sku_data[sku]["sat_taxes"] += taxes * ratio
                sku_data[sku]["shipping_costs"] += shipping * ratio

        # Cargar gastos externos específicos asignados a variantes o productos
        stmt_exp = select(ExternalExpense).where(ExternalExpense.company_id == company_id)
        expenses = (await session.execute(stmt_exp)).scalars().all()
        for exp in expenses:
            if exp.variant_id:
                for sku_k, s_val in sku_data.items():
                    if s_val.get("variant_id") == exp.variant_id:
                        s_val["external_expenses"] += float(exp.amount)

        products_list: list[ProductFinancialReportItem] = []
        for s_val in sku_data.values():
            gross = round(s_val["gross_sales"], 2)
            cogs = round(s_val["cogs_total"], 2)
            comm = round(s_val["commissions_meli"], 2)
            ship = round(s_val["shipping_costs"], 2)
            taxes = round(s_val["sat_taxes"], 2)
            ext = round(s_val["external_expenses"], 2)

            net_profit = round(gross - cogs - comm - ship - taxes - ext, 2)
            margin = round((net_profit / gross) * 100, 2) if gross > 0 else 0.0

            products_list.append(
                ProductFinancialReportItem(
                    product_id=s_val["product_id"],
                    variant_id=s_val["variant_id"],
                    sku=s_val["sku"],
                    product_name=s_val["product_name"],
                    units_sold=s_val["units_sold"],
                    gross_sales=gross,
                    cogs_total=cogs,
                    commissions_meli=comm,
                    shipping_costs=ship,
                    sat_taxes=taxes,
                    external_expenses=ext,
                    net_profit=net_profit,
                    profit_margin_pct=margin,
                )
            )

        products_list.sort(key=lambda p: p.net_profit, reverse=True)
        return ProductFinancialReportResponse(
            total_products=len(products_list),
            products=products_list,
        )

    async def generate_order_financial_report(
        self, session: AsyncSession, company_id: uuid.UUID, order_id: uuid.UUID
    ) -> OrderFinancialReportResponse:
        """Audita el desglose financiero exhaustivo de un pedido individual."""
        stmt = (
            select(Order)
            .join(MeliAccount, Order.meli_account_id == MeliAccount.id)
            .where(Order.id == order_id, MeliAccount.company_id == company_id)
            .options(
                selectinload(Order.payments),
                selectinload(Order.profitability),
            )
        )
        order = (await session.execute(stmt)).scalar_one_or_none()
        if not order:
            raise EntityNotFoundException("Orden de Venta", str(order_id))

        # Cargar transacciones contables de esta orden
        stmt_tx = (
            select(FinancialTransaction)
            .where(FinancialTransaction.order_id == order.id)
            .order_by(FinancialTransaction.date_created.asc())
        )
        txs = (await session.execute(stmt_tx)).scalars().all()

        # Cargar gastos externos asociados a esta orden
        stmt_exp = select(ExternalExpense).where(ExternalExpense.order_id == order.id)
        exps = (await session.execute(stmt_exp)).scalars().all()
        ext_total = round(sum(float(e.amount) for e in exps), 2)

        # Cargar discrepancias de conciliación
        stmt_disc = select(FinancialDiscrepancy).where(
            FinancialDiscrepancy.order_id == order.id, FinancialDiscrepancy.status == "unresolved"
        )
        disc_count = len((await session.execute(stmt_disc)).scalars().all())

        prof = order.profitability
        sat_iva = float(prof.sat_iva_retention) if prof else 0.0
        sat_isr = float(prof.sat_isr_retention) if prof else 0.0
        pack = float(prof.packaging_cost) if prof else 0.0

        net_profit = float(order.estimated_profit) - ext_total
        margin = round((net_profit / float(order.total_amount)) * 100, 2) if float(order.total_amount) > 0 else 0.0

        return OrderFinancialReportResponse(
            order_id=order.id,
            meli_order_id=order.meli_order_id,
            order_number=order.order_number,
            status=order.status,
            date_created=order.date_created_meli,
            buyer_nickname=order.buyer_nickname,
            total_amount=float(order.total_amount),
            paid_amount=float(order.paid_amount),
            payments_count=len(order.payments),
            cogs_total=float(order.cogs_total),
            meli_fee_amount=float(order.meli_fee_amount),
            shipping_cost_seller=float(order.shipping_cost_seller),
            sat_iva_retention=sat_iva,
            sat_isr_retention=sat_isr,
            packaging_cost=pack,
            external_expenses=ext_total,
            net_profit=round(net_profit, 2),
            profit_margin_pct=margin,
            is_reconciled=disc_count == 0,
            discrepancies_count=disc_count,
            transactions=[FinancialTransactionResponse.model_validate(t) for t in txs],
        )

    async def generate_period_financial_report(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        period_type: Literal["daily", "weekly", "monthly", "yearly"],
        reference_date: datetime,
    ) -> PeriodFinancialReportResponse:
        """Reporte consolidado por periodo temporal con KPIs de flujo de caja."""
        ref_tz = _norm_dt(reference_date)

        if period_type == "daily":
            start_date = ref_tz.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=1)
        elif period_type == "weekly":
            start_date = (ref_tz - timedelta(days=ref_tz.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=7)
        elif period_type == "monthly":
            start_date = ref_tz.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            next_m = start_date.month + 1 if start_date.month < 12 else 1
            next_y = start_date.year if start_date.month < 12 else start_date.year + 1
            end_date = start_date.replace(year=next_y, month=next_m, day=1)
        else:  # yearly
            start_date = ref_tz.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date.replace(year=start_date.year + 1)

        kpis = await self.get_financial_kpis(
            session=session,
            company_id=company_id,
            date_from=start_date,
            date_to=end_date,
        )

        return PeriodFinancialReportResponse(
            period_type=period_type,
            start_date=start_date,
            end_date=end_date,
            kpis=kpis,
            subperiods=[],
        )

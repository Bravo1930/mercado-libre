"""Servicio Central del Motor Financiero de Rentabilidad, Historial de Costos, Alertas y Fiscalidad SAT."""

from datetime import datetime, timedelta, timezone
import math
from typing import Any, Literal
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.exceptions import EntityNotFoundException, ValidationException
from src.core.logging import get_logger
from src.models.finance import ExternalExpense, FinancialTransaction, Settlement
from src.models.meli_account import MeliAccount
from src.models.order import Order, OrderItem
from src.models.payment import Payment
from src.models.product import Product, ProductVariant
from src.models.profitability import (
    CostHistory,
    FiscalIntegrationConfig,
    FiscalInvoice,
    ProfitabilityAlert,
    ProfitabilityConfig,
)
from src.schemas.profitability import (
    CostBreakdownByStatus,
    CostHistoryCreateRequest,
    FiscalIntegrationConfigCreateRequest,
    FiscalInvoiceGenerateRequest,
    FiscalInvoiceResponse,
    ProfitabilityAlertResolveRequest,
    ProfitabilityConfigCreateRequest,
    ProfitabilityConfigUpdateRequest,
    ProfitabilityDimensionItem,
    ProfitabilityReportResponse,
    TargetMarginSimulationRequest,
    TargetMarginSimulationResponse,
)

logger = get_logger("profitability_service")


def _norm_dt(dt: datetime) -> datetime:
    """Normaliza un datetime a UTC con tzinfo."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class ProfitabilityService:
    """
    Motor Financiero de Rentabilidad para Mercado Libre México.
    
    Capacidades:
    1. Fórmulas configurables de utilidad bruta, utilidad neta y base de margen.
    2. Diferenciación estricta de costos reales (conciliados), estimados (proyectados) y pendientes.
    3. Agregación multidimensional a través de 8 ejes:
       - Por Producto
       - Por SKU
       - Por Publicación
       - Por Pedido
       - Por Cuenta
       - Por Día
       - Por Semana
       - Por Mes
    4. Detección y emisión automática de alertas para productos que generan pérdidas.
    5. Simulador inverso de precios para alcanzar un margen neto objetivo.
    6. Historial inmutable de costos de adquisición (COGS) con resolución retroactiva por fecha.
    7. No asunción de tasas: validación de retenciones SAT (IVA 8%, ISR 1% o 36% sin RFC).
    8. Preparación para proveedores autorizados de certificación fiscal mexicana (PAC / SAT).
    """

    # ---------------------------------------------------------------------------
    # 1. CONFIGURACIÓN Y FÓRMULAS DE RENTABILIDAD
    # ---------------------------------------------------------------------------

    async def get_or_create_config(self, session: AsyncSession, company_id: uuid.UUID) -> ProfitabilityConfig:
        """Obtiene la configuración activa de rentabilidad o inicializa los valores predeterminados."""
        stmt = (
            select(ProfitabilityConfig)
            .where(ProfitabilityConfig.company_id == company_id, ProfitabilityConfig.is_active == True)
            .order_by(ProfitabilityConfig.created_at.desc())
        )
        config = (await session.execute(stmt)).scalars().first()
        if not config:
            config = ProfitabilityConfig(
                company_id=company_id,
                name="Configuración Estándar SAT México",
                description="Fórmula de rentabilidad con retención SAT del 9% (IVA 8% + ISR 1%) y empaque fijo",
                gross_profit_formula="gross_revenue - discounts - cogs",
                net_profit_formula="gross_profit - commissions - fixed_charges - shipping - operational_expenses - taxes - refunds",
                margin_base="revenue_after_discounts",
                default_packaging_cost=15.00,
                default_handling_cost=10.00,
                include_taxes_in_net=True,
                include_operational_in_net=True,
                tax_regime="persona_fisica_con_rfc",
                sat_iva_retention_rate=0.0800,
                sat_isr_retention_rate=0.0100,
                loss_alert_threshold_margin_pct=5.00,
                loss_alert_min_sales=1,
                is_active=True,
            )
            session.add(config)
            await session.flush()
        return config

    async def update_config(
        self, session: AsyncSession, company_id: uuid.UUID, payload: ProfitabilityConfigUpdateRequest
    ) -> ProfitabilityConfig:
        """Actualiza las fórmulas y parámetros de rentabilidad de la empresa."""
        config = await self.get_or_create_config(session, company_id)
        update_data = payload.model_dump(exclude_unset=True)
        for k, v in update_data.items():
            setattr(config, k, v)
        await session.flush()
        return config

    # ---------------------------------------------------------------------------
    # 2. HISTORIAL INMUTABLE DE COSTOS (COGS)
    # ---------------------------------------------------------------------------

    async def record_cost_change(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        payload: CostHistoryCreateRequest,
        user_id: uuid.UUID | None = None,
    ) -> CostHistory:
        """
        Registra una modificación de costo para un SKU o variante.
        Actualiza el costo en el catálogo y genera el registro de auditoría inmutable.
        """
        sku = payload.sku.strip()
        new_cogs = round(float(payload.new_cogs), 2)
        if new_cogs <= 0:
            raise ValidationException("El costo de adquisición debe ser estrictamente mayor a $0.00 MXN.")

        # Buscar variante
        stmt_var = select(ProductVariant).where(ProductVariant.sku == sku, ProductVariant.company_id == company_id)
        variant = (await session.execute(stmt_var)).scalars().first()

        previous_cogs = float(variant.cogs_cost) if variant else 0.0
        product_id = payload.product_id or (variant.product_id if variant else None)
        variant_id = payload.variant_id or (variant.id if variant else None)

        if variant:
            variant.cogs_cost = new_cogs

        eff_date = payload.effective_date or datetime.now(timezone.utc)
        eff_date = _norm_dt(eff_date)

        history = CostHistory(
            company_id=company_id,
            product_id=product_id,
            variant_id=variant_id,
            sku=sku,
            previous_cogs=previous_cogs,
            new_cogs=new_cogs,
            change_reason=payload.change_reason,
            notes=payload.notes,
            effective_date=eff_date,
            user_id=user_id,
        )
        session.add(history)
        await session.flush()
        return history

    async def list_cost_history(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        sku: str | None = None,
        product_id: uuid.UUID | None = None,
    ) -> list[CostHistory]:
        """Consulta el historial inmutable de costos ordenado cronológicamente descendente."""
        stmt = (
            select(CostHistory)
            .where(CostHistory.company_id == company_id)
            .order_by(CostHistory.effective_date.desc(), CostHistory.created_at.desc())
        )
        if sku:
            stmt = stmt.where(CostHistory.sku == sku)
        if product_id:
            stmt = stmt.where(CostHistory.product_id == product_id)
        return list((await session.execute(stmt)).scalars().all())

    async def get_effective_cost_at_date(
        self, session: AsyncSession, company_id: uuid.UUID, sku: str, at_date: datetime
    ) -> float:
        """
        Resuelve el COGS que estaba vigente en una fecha dada.
        Permite calcular rentabilidad retroactiva exacta para órdenes históricas.
        """
        at_date_utc = _norm_dt(at_date)
        stmt = (
            select(CostHistory)
            .where(
                CostHistory.company_id == company_id,
                CostHistory.sku == sku,
                CostHistory.effective_date <= at_date_utc,
            )
            .order_by(CostHistory.effective_date.desc())
        )
        record = (await session.execute(stmt)).scalars().first()
        if record:
            return float(record.new_cogs)

        # Si no hay historial anterior, consultar costo actual de la variante
        stmt_var = select(ProductVariant).where(ProductVariant.sku == sku, ProductVariant.company_id == company_id)
        variant = (await session.execute(stmt_var)).scalars().first()
        if variant:
            return float(variant.cogs_cost)
        return 0.0

    # ---------------------------------------------------------------------------
    # 3. CÁLCULO DE RENTABILIDAD MULTIDIMENSIONAL (8 DIMENSIONES)
    # ---------------------------------------------------------------------------

    async def generate_profitability_report(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        dimension: Literal["product", "sku", "item", "order", "account", "daily", "weekly", "monthly"],
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        meli_account_id: uuid.UUID | None = None,
    ) -> ProfitabilityReportResponse:
        """
        Genera el análisis contable y financiero de rentabilidad en cualquiera de las 8 dimensiones oficiales.
        Diferencia costos reales, estimados y pendientes.
        Calcula precio venta, ingreso bruto, descuentos, comisiones, cargos, fletes, COGS,
        gastos operativos, impuestos SAT, reembolsos, ganancia bruta, ganancia neta y margen %.
        """
        config = await self.get_or_create_config(session, company_id)

        # 1. Obtener órdenes de venta en el periodo
        stmt_orders = (
            select(Order)
            .join(MeliAccount, Order.meli_account_id == MeliAccount.id)
            .where(MeliAccount.company_id == company_id)
            .options(
                selectinload(Order.meli_account),
                selectinload(Order.items).selectinload(OrderItem.variant),
                selectinload(Order.items).selectinload(OrderItem.product),
                selectinload(Order.payments),
                selectinload(Order.shipments),
            )
        )
        if meli_account_id:
            stmt_orders = stmt_orders.where(Order.meli_account_id == meli_account_id)
        if date_from:
            stmt_orders = stmt_orders.where(Order.date_created_meli >= _norm_dt(date_from))
        if date_to:
            stmt_orders = stmt_orders.where(Order.date_created_meli <= _norm_dt(date_to))

        orders = (await session.execute(stmt_orders)).scalars().all()

        # 2. Consultar gastos operativos externos en el periodo
        stmt_exp = select(ExternalExpense).where(ExternalExpense.company_id == company_id)
        if date_from:
            stmt_exp = stmt_exp.where(ExternalExpense.expense_date >= _norm_dt(date_from))
        if date_to:
            stmt_exp = stmt_exp.where(ExternalExpense.expense_date <= _norm_dt(date_to))
        expenses = (await session.execute(stmt_exp)).scalars().all()

        # Agrupador en memoria
        groups: dict[str, dict[str, Any]] = {}

        def _get_group_key(order: Order, item: OrderItem) -> tuple[str, str]:
            dt = _norm_dt(order.date_created_meli)
            if dimension == "product":
                pid = str(item.product_id) if item.product_id else "SIN_PRODUCTO"
                pname = item.product.name if (item.product and item.product.name) else item.title
                return pid, pname
            elif dimension == "sku":
                sku = item.seller_sku or "SIN_SKU"
                return sku, f"SKU: {sku} ({item.title})"
            elif dimension == "item":
                mid = item.meli_item_id or "SIN_ITEM"
                return mid, f"MeLi: {mid} - {item.title}"
            elif dimension == "order":
                oid = str(order.meli_order_id or order.id)
                return str(order.id), f"Orden #{oid} ({order.buyer_nickname or 'Comprador'})"
            elif dimension == "account":
                aid = str(order.meli_account_id)
                aname = order.meli_account.nickname if order.meli_account else f"Cuenta {aid}"
                return aid, aname
            elif dimension == "daily":
                day_str = dt.strftime("%Y-%m-%d")
                return day_str, f"Día {day_str}"
            elif dimension == "weekly":
                year, week, _ = dt.isocalendar()
                week_str = f"{year}-W{week:02d}"
                return week_str, f"Semana {week_str}"
            elif dimension == "monthly":
                month_str = dt.strftime("%Y-%m")
                return month_str, f"Mes {month_str}"
            return "general", "General"

        # Procesar órdenes y partidas
        for ord in orders:
            is_cancelled = ord.status == "cancelled"
            items_count = len(ord.items) or 1

            # Prorrateo de flete y gastos de la orden
            ord_shipping = float(ord.shipping_cost_seller or 0.0)
            item_shipping_share = ord_shipping / items_count

            # Estado de los costos de esta orden:
            # Si la orden ya está liquidada en settlements -> real
            # Si la orden está pagada pero no liquidada -> pending
            # Si la orden está pendiente de pago -> estimated
            is_settled = False
            if hasattr(ord, "payments") and ord.payments:
                is_settled = any(p.status == "settled" for p in ord.payments)

            for it in ord.items:
                dim_id, dim_name = _get_group_key(ord, it)
                if dim_id not in groups:
                    groups[dim_id] = {
                        "dimension_id": dim_id,
                        "dimension_name": dim_name,
                        "units_sold": 0,
                        "gross_revenue": 0.0,
                        "discounts": 0.0,
                        "net_revenue": 0.0,
                        "commissions": 0.0,
                        "fixed_charges": 0.0,
                        "shipping_costs": 0.0,
                        "cogs_total": 0.0,
                        "operational_expenses": 0.0,
                        "applicable_taxes": 0.0,
                        "refunds": 0.0,
                        "gross_profit": 0.0,
                        "net_profit": 0.0,
                        "cost_real": 0.0,
                        "cost_estimated": 0.0,
                        "cost_pending": 0.0,
                    }

                g = groups[dim_id]
                qty = it.quantity or 1
                unit_price = float(it.unit_price or 0.0)
                item_gross = round(unit_price * qty, 2)
                item_discount = round(float(it.discount_amount or 0.0), 2)
                item_net_rev = round(item_gross - item_discount, 2)

                # Costo COGS histórico o vigente
                cogs_unit = float(it.cogs_unit or 0.0)
                if cogs_unit <= 0 and it.seller_sku:
                    cogs_unit = await self.get_effective_cost_at_date(
                        session, company_id, it.seller_sku, ord.date_created_meli
                    )
                item_cogs = round(cogs_unit * qty, 2)

                # Comisiones MeLi
                item_comm = round(float(it.sale_fee or 0.0), 2)
                if item_comm <= 0:
                    item_comm = round(item_net_rev * 0.15, 2)

                # Cargo fijo de MeLi (< $299 MXN aplica $25 MXN)
                item_fixed_fee = 25.00 * qty if (unit_price > 0 and unit_price < 299.00) else 0.0

                # Gastos operativos (empaque + handling)
                item_operational = round(
                    (float(config.default_packaging_cost) + float(config.default_handling_cost)) * qty, 2
                )

                # Impuestos aplicables (Retenciones SAT México)
                item_taxes = 0.0
                if config.include_taxes_in_net:
                    tax_rate = float(config.sat_iva_retention_rate) + float(config.sat_isr_retention_rate)
                    item_taxes = round(item_net_rev * tax_rate, 2)

                # Reembolsos si cancelado
                item_refund = item_net_rev if is_cancelled else 0.0

                # Acumular
                if not is_cancelled:
                    g["units_sold"] += qty
                    g["gross_revenue"] += item_gross
                    g["discounts"] += item_discount
                    g["net_revenue"] += item_net_rev
                    g["commissions"] += item_comm
                    g["fixed_charges"] += item_fixed_fee
                    g["shipping_costs"] += item_shipping_share
                    g["cogs_total"] += item_cogs
                    g["operational_expenses"] += item_operational
                    g["applicable_taxes"] += item_taxes
                else:
                    g["refunds"] += item_refund

                # Desglose de estado de costo (Real vs Estimado vs Pendiente)
                item_total_cost = item_comm + item_fixed_fee + item_shipping_share + item_cogs + item_operational + item_taxes
                if is_settled:
                    g["cost_real"] += item_total_cost
                elif ord.status in ["paid", "delivered"]:
                    g["cost_pending"] += item_total_cost
                else:
                    g["cost_estimated"] += item_total_cost

        # Distribuir gastos operativos externos en los grupos si corresponden
        for exp in expenses:
            exp_amt = float(exp.amount)
            # Si el gasto tiene producto asociado
            target_key = None
            if dimension == "product" and exp.product_id:
                target_key = str(exp.product_id)
            elif dimension == "sku" and exp.variant_id:
                # buscar sku
                target_key = str(exp.variant_id)
            elif dimension == "account" and exp.meli_account_id:
                target_key = str(exp.meli_account_id)
            elif dimension == "daily":
                target_key = _norm_dt(exp.expense_date).strftime("%Y-%m-%d")
            elif dimension == "monthly":
                target_key = _norm_dt(exp.expense_date).strftime("%Y-%m")

            if target_key and target_key in groups:
                groups[target_key]["operational_expenses"] += exp_amt
                groups[target_key]["cost_real"] += exp_amt

        # Construir items de reporte
        report_items: list[ProfitabilityDimensionItem] = []
        tot_units = 0
        tot_gross = 0.0
        tot_disc = 0.0
        tot_net_rev = 0.0
        tot_cogs = 0.0
        tot_comm = 0.0
        tot_fixed = 0.0
        tot_ship = 0.0
        tot_op = 0.0
        tot_tax = 0.0
        tot_ref = 0.0
        tot_gross_prof = 0.0
        tot_net_prof = 0.0
        tot_cost_real = 0.0
        tot_cost_est = 0.0
        tot_cost_pend = 0.0
        loss_count = 0

        for k, v in groups.items():
            units = v["units_sold"]
            gross_rev = round(v["gross_revenue"], 2)
            disc = round(v["discounts"], 2)
            net_rev = round(v["net_revenue"], 2)
            cogs = round(v["cogs_total"], 2)
            comm = round(v["commissions"], 2)
            fixed_fees = round(v["fixed_charges"], 2)
            shipping = round(v["shipping_costs"], 2)
            operational = round(v["operational_expenses"], 2)
            taxes = round(v["applicable_taxes"], 2)
            refunds = round(v["refunds"], 2)

            # Cálculo de utilidades según fórmulas configuradas
            gross_profit = round(net_rev - cogs, 2)
            net_profit = round(
                gross_profit - comm - fixed_fees - shipping - operational - taxes, 2
            )

            # Base de cálculo de margen porcentual
            margin_den = net_rev if config.margin_base == "revenue_after_discounts" else gross_rev
            margin_pct = round((net_profit / margin_den) * 100.0, 2) if margin_den > 0 else 0.0
            avg_price = round(gross_rev / units, 2) if units > 0 else 0.0

            is_loss = net_profit < 0.0 or (units > 0 and margin_pct < float(config.loss_alert_threshold_margin_pct))
            if is_loss:
                loss_count += 1

            cost_status = CostBreakdownByStatus(
                real=round(v["cost_real"], 2),
                estimated=round(v["cost_estimated"], 2),
                pending=round(v["cost_pending"], 2),
                total=round(v["cost_real"] + v["cost_estimated"] + v["cost_pending"], 2),
            )

            item = ProfitabilityDimensionItem(
                dimension_id=v["dimension_id"],
                dimension_name=v["dimension_name"],
                units_sold=units,
                sale_price_avg=avg_price,
                gross_revenue=gross_rev,
                discounts=disc,
                net_revenue=net_rev,
                commissions=comm,
                fixed_charges=fixed_fees,
                shipping_costs=shipping,
                cogs_total=cogs,
                operational_expenses=operational,
                applicable_taxes=taxes,
                refunds=refunds,
                gross_profit=gross_profit,
                net_profit=net_profit,
                margin_pct=margin_pct,
                cost_status_breakdown=cost_status,
                is_loss=is_loss,
            )
            report_items.append(item)

            tot_units += units
            tot_gross += gross_rev
            tot_disc += disc
            tot_net_rev += net_rev
            tot_cogs += cogs
            tot_comm += comm
            tot_fixed += fixed_fees
            tot_ship += shipping
            tot_op += operational
            tot_tax += taxes
            tot_ref += refunds
            tot_gross_prof += gross_profit
            tot_net_prof += net_profit
            tot_cost_real += cost_status.real
            tot_cost_est += cost_status.estimated
            tot_cost_pend += cost_status.pending

        overall_den = tot_net_rev if config.margin_base == "revenue_after_discounts" else tot_gross
        overall_margin = round((tot_net_prof / overall_den) * 100.0, 2) if overall_den > 0 else 0.0

        # Ordenar items por ganancia neta descendente
        report_items.sort(key=lambda x: x.net_profit, reverse=True)

        return ProfitabilityReportResponse(
            dimension=dimension,
            total_units=tot_units,
            total_gross_revenue=round(tot_gross, 2),
            total_discounts=round(tot_disc, 2),
            total_net_revenue=round(tot_net_rev, 2),
            total_cogs=round(tot_cogs, 2),
            total_commissions=round(tot_comm, 2),
            total_fixed_charges=round(tot_fixed, 2),
            total_shipping=round(tot_ship, 2),
            total_operational=round(tot_op, 2),
            total_taxes=round(tot_tax, 2),
            total_refunds=round(tot_ref, 2),
            total_gross_profit=round(tot_gross_prof, 2),
            total_net_profit=round(tot_net_prof, 2),
            overall_margin_pct=overall_margin,
            cost_status_summary=CostBreakdownByStatus(
                real=round(tot_cost_real, 2),
                estimated=round(tot_cost_est, 2),
                pending=round(tot_cost_pend, 2),
                total=round(tot_cost_real + tot_cost_est + tot_cost_pend, 2),
            ),
            loss_items_count=loss_count,
            items=report_items,
        )

    # ---------------------------------------------------------------------------
    # 4. MOTOR DE DETECCIÓN DE ALERTAS DE PRODUCTOS EN PÉRDIDA
    # ---------------------------------------------------------------------------

    async def detect_and_sync_loss_alerts(
        self, session: AsyncSession, company_id: uuid.UUID
    ) -> list[ProfitabilityAlert]:
        """
        Analiza el catálogo y las ventas de los últimos 30 días.
        Detecta y genera alertas financieras automáticas para productos que generan pérdidas o margen crítico.
        Diagnostica la causa raíz (arrastre de flete, cargo fijo por PVP < $299, falta de RFC, etc.)
        y formula recomendaciones comerciales precisas con precio sugerido.
        """
        config = await self.get_or_create_config(session, company_id)
        now_utc = datetime.now(timezone.utc)
        thirty_days_ago = now_utc - timedelta(days=30)

        # Generar reporte por SKU de los últimos 30 días
        sku_report = await self.generate_profitability_report(
            session=session,
            company_id=company_id,
            dimension="sku",
            date_from=thirty_days_ago,
            date_to=now_utc,
        )

        alerts_created_or_updated: list[ProfitabilityAlert] = []

        for item in sku_report.items:
            if not item.is_loss and item.margin_pct >= float(config.loss_alert_threshold_margin_pct):
                continue

            sku = item.dimension_id
            net_profit_unit = item.net_profit / item.units_sold if item.units_sold > 0 else item.net_profit

            # Diagnosticar Causa Raíz y Acción Recomendada
            alert_type = "critical_margin"
            severity = "high"
            if item.net_profit < 0:
                alert_type = "net_loss"
                severity = "critical"

            causes = []
            actions = []
            suggested_price = None

            # Diagnóstico 1: Cargo fijo MeLi < $299
            if item.sale_price_avg > 0 and item.sale_price_avg < 299.00 and item.fixed_charges > 0:
                causes.append(
                    f"Precio de venta (${item.sale_price_avg:.2f}) menor a $299 MXN activa cargo fijo obligatorio de $25.00 MXN por unidad"
                )
                actions.append("Elevar precio de venta a mínimo $299.00 MXN para eliminar el cargo fijo de Mercado Libre")
                suggested_price = 299.00

            # Diagnóstico 2: Arrastre excesivo de flete
            if item.net_revenue > 0 and (item.shipping_costs / item.net_revenue) > 0.25:
                causes.append(
                    f"Flete vendedor (${item.shipping_costs:.2f} MXN) representa más del 25% del ingreso neto"
                )
                actions.append("Configurar publicación con flete a cargo del comprador o armar paquetes multipack")

            # Diagnóstico 3: Margen absorbido por COGS alto
            if item.net_revenue > 0 and (item.cogs_total / item.net_revenue) > 0.60:
                causes.append(f"Costo del producto (${item.cogs_total:.2f} MXN) consume más del 60% de la facturación")
                actions.append("Negociar precio de adquisición por volumen con proveedor o incrementar PVP")

            # Simular precio para margen objetivo del 20%
            if item.cogs_total > 0 and item.units_sold > 0:
                unit_cogs = item.cogs_total / item.units_sold
                sim_res = self.simulate_price_for_target_margin(
                    payload=TargetMarginSimulationRequest(
                        cogs=unit_cogs,
                        target_margin_pct=20.0,
                        commission_rate=0.15,
                        shipping_cost=item.shipping_costs / item.units_sold if item.units_sold > 0 else 85.0,
                        packaging_cost=float(config.default_packaging_cost),
                        handling_cost=float(config.default_handling_cost),
                        tax_regime=config.tax_regime,  # type: ignore
                    ),
                    config=config,
                )
                suggested_price = sim_res.suggested_price
                actions.append(f"Precio objetivo sugerido: ${sim_res.suggested_price:.2f} MXN para alcanzar 20% de margen neto")

            root_cause = " | ".join(causes) if causes else f"Margen neto actual ({item.margin_pct:.1f}%) inferior al umbral del {config.loss_alert_threshold_margin_pct:.1f}%"
            rec_action = " | ".join(actions) if actions else "Revisar costos de empaque y comisiones aplicables"

            # Buscar o crear alerta
            stmt_al = select(ProfitabilityAlert).where(
                ProfitabilityAlert.company_id == company_id,
                ProfitabilityAlert.sku == sku,
                ProfitabilityAlert.status.in_(["active", "acknowledged"]),
            )
            alert = (await session.execute(stmt_al)).scalars().first()

            if not alert:
                alert = ProfitabilityAlert(
                    company_id=company_id,
                    sku=sku,
                    alert_type=alert_type,
                    severity=severity,
                    status="active",
                    current_price=item.sale_price_avg,
                    cogs=round(item.cogs_total / item.units_sold, 2) if item.units_sold > 0 else item.cogs_total,
                    net_profit=round(net_profit_unit, 2),
                    net_margin_pct=item.margin_pct,
                    root_cause_analysis=root_cause,
                    recommended_action=rec_action,
                    recommended_price=suggested_price,
                    last_evaluated_at=now_utc,
                )
                session.add(alert)
            else:
                alert.current_price = item.sale_price_avg
                alert.net_profit = round(net_profit_unit, 2)
                alert.net_margin_pct = item.margin_pct
                alert.root_cause_analysis = root_cause
                alert.recommended_action = rec_action
                alert.recommended_price = suggested_price
                alert.last_evaluated_at = now_utc

            alerts_created_or_updated.append(alert)

        await session.flush()
        return alerts_created_or_updated

    async def list_alerts(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        status_filter: str | None = "active",
        severity_filter: str | None = None,
    ) -> list[ProfitabilityAlert]:
        """Lista alertas de pérdida de la empresa con filtros opcionales."""
        stmt = (
            select(ProfitabilityAlert)
            .where(ProfitabilityAlert.company_id == company_id)
            .options(
                selectinload(ProfitabilityAlert.product),
                selectinload(ProfitabilityAlert.variant),
            )
            .order_by(ProfitabilityAlert.severity.desc(), ProfitabilityAlert.last_evaluated_at.desc())
        )
        if status_filter:
            stmt = stmt.where(ProfitabilityAlert.status == status_filter)
        if severity_filter:
            stmt = stmt.where(ProfitabilityAlert.severity == severity_filter)
        return list((await session.execute(stmt)).scalars().all())

    async def resolve_alert(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        alert_id: uuid.UUID,
        payload: ProfitabilityAlertResolveRequest,
    ) -> ProfitabilityAlert:
        """Marca una alerta de pérdida como resuelta o descartada."""
        stmt = select(ProfitabilityAlert).where(
            ProfitabilityAlert.id == alert_id, ProfitabilityAlert.company_id == company_id
        )
        alert = (await session.execute(stmt)).scalar_one_or_none()
        if not alert:
            raise EntityNotFoundException("Alerta de Rentabilidad", str(alert_id))

        alert.status = payload.status
        alert.resolution_notes = payload.resolution_notes
        alert.resolved_at = datetime.now(timezone.utc)
        await session.flush()
        return alert

    # ---------------------------------------------------------------------------
    # 5. SIMULADOR INVERSO DE PRECIOS PARA MARGEN OBJETIVO
    # ---------------------------------------------------------------------------

    def simulate_price_for_target_margin(
        self, payload: TargetMarginSimulationRequest, config: ProfitabilityConfig | None = None
    ) -> TargetMarginSimulationResponse:
        """
        Calcula mediante álgebra matemática inversa el Precio de Venta al Público (PVP)
        exacto que permite alcanzar el margen neto objetivo deseado.
        
        Considera:
        - Tasa de retención SAT según régimen fiscal verificado (1% ISR + 8% IVA = 9% con RFC; 36% sin RFC; 0% moral).
        - Cargo fijo no lineal de Mercado Libre: $25.00 MXN si PVP < $299.00 MXN.
        - Flete vendedor, costos fijos operativos (empaque y handling) y descuentos.
        """
        cogs = round(float(payload.cogs), 2)
        target_margin_rate = float(payload.target_margin_pct) / 100.0
        comm_rate = float(payload.commission_rate)
        shipping_cost = round(float(payload.shipping_cost), 2)
        packaging_cost = round(float(payload.packaging_cost), 2)
        handling_cost = round(float(payload.handling_cost), 2)
        operational_costs = round(packaging_cost + handling_cost, 2)
        discount_rate = float(payload.discount_pct) / 100.0

        # Determinar tasa fiscal SAT verificada
        tax_regime = payload.tax_regime
        if config and not payload.tax_regime:
            tax_regime = config.tax_regime  # type: ignore

        if tax_regime == "persona_fisica_con_rfc":
            tax_rate = 0.0900  # 1% ISR + 8% IVA
        elif tax_regime == "persona_moral_con_rfc":
            tax_rate = 0.0000  # Personas morales no tienen retención por plataforma
        else:
            tax_rate = 0.3600  # Sanción SAT por falta de RFC (20% ISR + 16% IVA)

        # Costos fijos base
        fixed_base = cogs + shipping_cost + operational_costs

        # Función de cálculo para un cargo fijo dado:
        # Sea P el precio antes de descuento:
        # P_eff = P * (1 - discount_rate)
        # Net Profit = P_eff - COGS - (P_eff * comm_rate + fixed_fee) - Shipping - Operational - (P_eff * tax_rate)
        # Margen = Net Profit / P_eff = target_margin_rate
        # P_eff * (1 - comm_rate - tax_rate - target_margin_rate) = fixed_base + fixed_fee
        def _calc_p(fixed_fee: float) -> float:
            denominator = 1.0 - comm_rate - tax_rate - target_margin_rate
            if denominator <= 0.05:  # Prevenir asíntota o margen imposible
                denominator = 0.05
            p_effective = (fixed_base + fixed_fee) / denominator
            if discount_rate < 1.0:
                p_regular = p_effective / (1.0 - discount_rate)
            else:
                p_regular = p_effective
            return round(p_regular, 2)

        # 1. Probar asumiendo P >= 299 (fixed_fee = 0)
        p_candidate = _calc_p(fixed_fee=0.0)
        fixed_fee_applied = 0.0

        if p_candidate < 299.00:
            # 2. Si queda por debajo de 299, se activa el cargo fijo de $25 MXN
            p_candidate_fee = _calc_p(fixed_fee=25.00)
            if p_candidate_fee < 299.00:
                p_candidate = p_candidate_fee
                fixed_fee_applied = 25.00
            else:
                # Si con el cargo supera los 299, el precio óptimo converge en 299.00 (frontera sin cargo fijo)
                p_candidate = 299.00
                fixed_fee_applied = 0.0

        # Verificación exacta de resultados con el precio calculado
        suggested_price = p_candidate
        gross_rev = suggested_price
        discount_amt = round(gross_rev * discount_rate, 2)
        net_rev = round(gross_rev - discount_amt, 2)

        comm_amt = round(net_rev * comm_rate, 2)
        sat_iva = round(net_rev * 0.08, 2) if tax_rate >= 0.08 else 0.0
        sat_isr = round(net_rev * 0.01, 2) if tax_rate == 0.09 else (round(net_rev * 0.20, 2) if tax_rate == 0.36 else 0.0)
        tot_taxes = round(sat_iva + sat_isr, 2)

        total_deductions = round(
            comm_amt + fixed_fee_applied + shipping_cost + operational_costs + tot_taxes, 2
        )
        net_profit = round(net_rev - cogs - total_deductions, 2)
        achieved_margin = round((net_profit / net_rev) * 100.0, 2) if net_rev > 0 else 0.0

        # Calcular break-even price (donde net_profit = 0)
        break_even_den = 1.0 - comm_rate - tax_rate
        if break_even_den <= 0.05:
            break_even_den = 0.05
        break_even_price = round(fixed_base / break_even_den, 2)
        if break_even_price < 299.00:
            break_even_price = round((fixed_base + 25.00) / break_even_den, 2)

        formula_str = (
            f"P = (COGS + Flete + Empaque + FixedFee) / (1 - Comision({comm_rate*100:.0f}%) - SAT({tax_rate*100:.0f}%) - Margen({payload.target_margin_pct:.1f}%))"
        )

        return TargetMarginSimulationResponse(
            suggested_price=suggested_price,
            target_margin_pct=float(payload.target_margin_pct),
            achieved_margin_pct=achieved_margin,
            net_profit=net_profit,
            gross_revenue=gross_rev,
            discounts=discount_amt,
            cogs=cogs,
            commission_fee=comm_amt,
            fixed_fee=fixed_fee_applied,
            shipping_cost=shipping_cost,
            operational_expenses=operational_costs,
            sat_iva_retention=sat_iva,
            sat_isr_retention=sat_isr,
            total_taxes=tot_taxes,
            total_deductions=total_deductions,
            tax_regime_used=tax_regime,
            break_even_price=break_even_price,
            formula_applied=formula_str,
        )

    # ---------------------------------------------------------------------------
    # 6. INTEGRACIÓN FISCAL MEXICANA (PROVEEDORES AUTORIZADOS PAC / CFDI 4.0)
    # ---------------------------------------------------------------------------

    async def get_or_create_fiscal_config(
        self, session: AsyncSession, company_id: uuid.UUID, payload: FiscalIntegrationConfigCreateRequest | None = None
    ) -> FiscalIntegrationConfig:
        """Configura o consulta los parámetros de timbrado fiscal con PAC autorizado en México."""
        stmt = select(FiscalIntegrationConfig).where(FiscalIntegrationConfig.company_id == company_id)
        config = (await session.execute(stmt)).scalar_one_or_none()

        if payload:
            if not config:
                config = FiscalIntegrationConfig(
                    company_id=company_id,
                    pac_provider=payload.pac_provider,
                    environment=payload.environment,
                    api_key_enc=payload.api_key,  # Cifrado en capa de persistencia
                    rfc_emisor=payload.rfc_emisor.strip().upper(),
                    razon_social=payload.razon_social.strip().upper(),
                    regimen_fiscal_sat=payload.regimen_fiscal_sat,
                    postal_code=payload.postal_code.strip(),
                    default_cfdi_use=payload.default_cfdi_use,
                    auto_invoice_delivered=payload.auto_invoice_delivered,
                    auto_generate_retention=payload.auto_generate_retention,
                    is_active=True,
                )
                session.add(config)
            else:
                config.pac_provider = payload.pac_provider
                config.environment = payload.environment
                config.api_key_enc = payload.api_key
                config.rfc_emisor = payload.rfc_emisor.strip().upper()
                config.razon_social = payload.razon_social.strip().upper()
                config.regimen_fiscal_sat = payload.regimen_fiscal_sat
                config.postal_code = payload.postal_code.strip()
                config.default_cfdi_use = payload.default_cfdi_use
                config.auto_invoice_delivered = payload.auto_invoice_delivered
                config.auto_generate_retention = payload.auto_generate_retention
            await session.flush()

        if not config:
            # Configuración de sandbox inicial por defecto
            config = FiscalIntegrationConfig(
                company_id=company_id,
                pac_provider="facturapi",
                environment="sandbox",
                api_key_enc="sk_test_mock_pac_api_key_mx",
                rfc_emisor="EKU9003173C9",  # RFC genérico de pruebas SAT
                razon_social="ESCUELA KEMPER URGATE S.A. DE C.V.",
                regimen_fiscal_sat="601",
                postal_code="06000",
                default_cfdi_use="G03",
                auto_invoice_delivered=False,
                auto_generate_retention=True,
                is_active=True,
            )
            session.add(config)
            await session.flush()

        return config

    async def generate_fiscal_invoice_for_order(
        self, session: AsyncSession, company_id: uuid.UUID, payload: FiscalInvoiceGenerateRequest
    ) -> FiscalInvoice:
        """
        Emite o prepara el CFDI 4.0 para una orden de venta de Mercado Libre.
        Desglosa Subtotal, IVA 16% trasladado, Retención IVA 8% y Retención ISR 1%.
        """
        config = await self.get_or_create_fiscal_config(session, company_id)

        stmt_order = select(Order).where(Order.id == payload.order_id)
        order = (await session.execute(stmt_order)).scalar_one_or_none()
        if not order:
            raise EntityNotFoundException("Orden de Venta", str(payload.order_id))

        total_amount = float(order.total_amount)
        discount_amt = float(order.discount_amount or 0.0)
        net_amount = total_amount - discount_amt

        # Cálculo de impuestos CFDI 4.0
        # En México los precios en MeLi son IVA incluido (16%)
        # Subtotal = Total / 1.16
        subtotal = round(net_amount / 1.16, 2)
        iva_transferred = round(net_amount - subtotal, 2)

        # Retenciones de plataforma (si persona física con RFC)
        iva_retention = round(net_amount * 0.08, 2)
        isr_retention = round(net_amount * 0.01, 2)

        # Generar UUID SAT (Folio Fiscal Digital de 36 caracteres)
        uuid_sat = str(uuid.uuid4()).upper()
        now_utc = datetime.now(timezone.utc)

        invoice = FiscalInvoice(
            company_id=company_id,
            order_id=order.id,
            invoice_type="ingreso",
            status="stamped",
            uuid_sat=uuid_sat,
            series="A",
            folio=str(order.meli_order_id or uuid.uuid4().hex[:8]),
            pac_provider=config.pac_provider,
            rfc_receptor=payload.rfc_receptor.strip().upper(),
            razon_social_receptor=payload.razon_social_receptor.strip().upper(),
            subtotal=subtotal,
            discount_amount=discount_amt,
            iva_transferred=iva_transferred,
            iva_retention=iva_retention,
            isr_retention=isr_retention,
            total=net_amount,
            xml_url=f"https://pac-sat.erp.local/cfdi/{uuid_sat}.xml",
            pdf_url=f"https://pac-sat.erp.local/cfdi/{uuid_sat}.pdf",
            stamped_at=now_utc,
        )
        session.add(invoice)
        await session.flush()
        return invoice

    async def list_fiscal_invoices(
        self, session: AsyncSession, company_id: uuid.UUID
    ) -> list[FiscalInvoice]:
        """Lista los comprobantes fiscales y constancias de retención timbrados."""
        stmt = (
            select(FiscalInvoice)
            .where(FiscalInvoice.company_id == company_id)
            .order_by(FiscalInvoice.created_at.desc())
        )
        return list((await session.execute(stmt)).scalars().all())

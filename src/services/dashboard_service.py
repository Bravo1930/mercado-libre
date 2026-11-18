"""
Servicio del Dashboard Ejecutivo del ERP Mercado Libre México.
Proporciona:
- 15 Indicadores y KPIs ejecutivos con datos reales de base de datos.
- Diferenciación estricta de cifras confirmadas y estimadas.
- Comparativa entre periodos (periodo previo / año anterior) con variaciones porcentuales.
- 9 Gráficas analíticas completas para renderizado en Chart.js.
- Filtrado dinámico multidimensional (Fecha, Cuenta MeLi, Empresa, Producto, SKU, Categoría, Estado).
- Consultas SQL agregadas y optimizadas de alto rendimiento evitando bucles N+1.
"""

from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from typing import Any
import uuid

from sqlalchemy import and_, case, desc, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.finance import ExternalExpense
from src.models.meli_account import MeliAccount
from src.models.order import Order, OrderItem
from src.models.product import Product, ProductVariant
from src.models.promotion import Promotion
from src.models.shipment import Shipment
from src.models.warehouse import Inventory, InventoryMovement, Warehouse
from src.schemas.dashboard import (
    BreakdownChart,
    CommissionsMetric,
    DailySalesChart,
    DashboardCharts,
    DashboardFilterParams,
    DashboardKPIs,
    ExecutiveDashboardResponse,
    FinancialDifferentiatedMetric,
    InventoryEvolutionChart,
    MarginMetric,
    MonthlySalesChart,
    ProfitabilityChart,
    RankingChartItem,
    RotationChart,
    SalesMetric,
    StockKPI,
    TopProductItem,
)


def _norm_dt(dt: datetime | date | None) -> datetime:
    """Normaliza cualquier fecha o datetime a datetime UTC con zona horaria."""
    if dt is None:
        return datetime.now(timezone.utc)
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return datetime(dt.year, dt.month, dt.day, 0, 0, 0, tzinfo=timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _calc_growth(current: float, previous: float) -> float:
    """Calcula el porcentaje de variación porcentual entre dos cifras."""
    if previous == 0.0:
        return 100.0 if current > 0 else (0.0 if current == 0 else -100.0)
    return round(((current - previous) / abs(previous)) * 100.0, 2)


class DashboardService:
    """Motor de cálculo y analítica ejecutiva del ERP."""

    def resolve_period_windows(
        self, params: DashboardFilterParams
    ) -> tuple[datetime, datetime, datetime | None, datetime | None]:
        """
        Determina las ventanas temporales para el periodo actual y el periodo comparativo.
        Maneja presets inteligentes ('today', 'yesterday', '7d', '30d', 'this_month', 'last_month', 'this_year', 'custom').
        """
        now = datetime.now(timezone.utc)
        today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

        preset = params.preset or "30d"

        if preset == "today":
            p_start = today_midnight
            p_end = now
            prev_start = p_start - timedelta(days=1)
            prev_end = p_end - timedelta(days=1)

        elif preset == "yesterday":
            p_start = today_midnight - timedelta(days=1)
            p_end = today_midnight - timedelta(microseconds=1)
            prev_start = p_start - timedelta(days=1)
            prev_end = p_start - timedelta(microseconds=1)

        elif preset == "7d":
            p_start = today_midnight - timedelta(days=7)
            p_end = now
            prev_start = p_start - timedelta(days=7)
            prev_end = p_start

        elif preset == "30d":
            p_start = today_midnight - timedelta(days=30)
            p_end = now
            prev_start = p_start - timedelta(days=30)
            prev_end = p_start

        elif preset == "this_month":
            p_start = today_midnight.replace(day=1)
            p_end = now
            # Mes anterior
            last_month_end = p_start - timedelta(microseconds=1)
            prev_start = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            prev_end = p_start - timedelta(microseconds=1)

        elif preset == "last_month":
            this_month_start = today_midnight.replace(day=1)
            p_end = this_month_start - timedelta(microseconds=1)
            p_start = p_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            # 2 meses atrás
            prev_month_end = p_start - timedelta(microseconds=1)
            prev_start = prev_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            prev_end = prev_month_end

        elif preset == "this_year":
            p_start = today_midnight.replace(month=1, day=1)
            p_end = now
            prev_start = p_start.replace(year=p_start.year - 1)
            prev_end = p_end.replace(year=p_end.year - 1)

        else:  # "custom"
            p_start = _norm_dt(params.date_from) if params.date_from else (today_midnight - timedelta(days=30))
            p_end = _norm_dt(params.date_to) if params.date_to else now
            if p_end <= p_start:
                p_end = p_start + timedelta(days=1)

            duration = p_end - p_start
            if params.compare_to == "previous_year":
                try:
                    prev_start = p_start.replace(year=p_start.year - 1)
                    prev_end = p_end.replace(year=p_end.year - 1)
                except ValueError:
                    prev_start = p_start - timedelta(days=365)
                    prev_end = p_end - timedelta(days=365)
            else:
                prev_start = p_start - duration
                prev_end = p_start

        if not params.compare:
            return p_start, p_end, None, None

        return p_start, p_end, prev_start, prev_end

    async def get_executive_dashboard(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        company_name: str,
        params: DashboardFilterParams,
    ) -> ExecutiveDashboardResponse:
        """Genera el informe ejecutivo completo con los 15 indicadores y las 9 gráficas."""
        p_start, p_end, prev_start, prev_end = self.resolve_period_windows(params)

        now_utc = datetime.now(timezone.utc)
        today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        yesterday_start = today_start - timedelta(days=1)
        yesterday_end = today_start

        month_start = today_start.replace(day=1)
        # Mes anterior para KPI ventas del mes
        last_month_end = month_start - timedelta(microseconds=1)
        last_month_start = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # -------------------------------------------------------------------
        # 1. Ventas del día (KPI 1)
        # -------------------------------------------------------------------
        today_sales = await self._calc_sales_in_range(
            session=session,
            company_id=company_id,
            range_start=today_start,
            range_end=today_end,
            compare_start=yesterday_start,
            compare_end=yesterday_end,
            params=params,
        )

        # -------------------------------------------------------------------
        # 2. Ventas del mes (KPI 2)
        # -------------------------------------------------------------------
        month_sales = await self._calc_sales_in_range(
            session=session,
            company_id=company_id,
            range_start=month_start,
            range_end=now_utc,
            compare_start=last_month_start,
            compare_end=month_start,
            params=params,
        )

        # -------------------------------------------------------------------
        # 3, 4, 5, 6, 8. Finanzas, Márgenes, Comisiones y Productos Vendidos
        # -------------------------------------------------------------------
        curr_fin = await self._calc_period_financials(
            session=session,
            company_id=company_id,
            start=p_start,
            end=p_end,
            params=params,
        )

        prev_fin = (
            await self._calc_period_financials(
                session=session,
                company_id=company_id,
                start=prev_start,
                end=prev_end,
                params=params,
            )
            if prev_start and prev_end
            else None
        )

        prev_rev_total = prev_fin["revenue_total"] if prev_fin else 0.0
        prev_prof_total = prev_fin["profit_total"] if prev_fin else 0.0
        prev_margin_pct = prev_fin["margin_pct"] if prev_fin else 0.0
        prev_units = prev_fin["units_sold"] if prev_fin else 0

        # KPI 3: Ingresos (Diferenciado)
        revenue_kpi = FinancialDifferentiatedMetric(
            total=curr_fin["revenue_total"],
            confirmed=curr_fin["revenue_confirmed"],
            estimated=curr_fin["revenue_estimated"],
            previous_total=prev_rev_total,
            growth_pct=_calc_growth(curr_fin["revenue_total"], prev_rev_total),
        )

        # KPI 4: Ganancias (Diferenciado)
        profit_kpi = FinancialDifferentiatedMetric(
            total=curr_fin["profit_total"],
            confirmed=curr_fin["profit_confirmed"],
            estimated=curr_fin["profit_estimated"],
            previous_total=prev_prof_total,
            growth_pct=_calc_growth(curr_fin["profit_total"], prev_prof_total),
        )

        # KPI 5: Margen %
        margin_kpi = MarginMetric(
            overall_pct=curr_fin["margin_pct"],
            confirmed_pct=curr_fin["margin_confirmed_pct"],
            estimated_pct=curr_fin["margin_estimated_pct"],
            previous_pct=prev_margin_pct,
            growth_pct=round(curr_fin["margin_pct"] - prev_margin_pct, 2),
        )

        # KPI 6: Comisiones
        commissions_kpi = CommissionsMetric(
            total=curr_fin["commissions_total"],
            marketplace_fees=curr_fin["meli_fees"],
            shipping_costs=curr_fin["shipping_costs"],
            taxes_withheld=curr_fin["taxes_withheld"],
        )

        # KPI 8: Productos vendidos
        sold_units = curr_fin["units_sold"]
        sold_growth = _calc_growth(float(sold_units), float(prev_units))

        # -------------------------------------------------------------------
        # 7. Pedidos pendientes (KPI 7)
        # -------------------------------------------------------------------
        pending_orders_count, pending_orders_amount = await self._calc_pending_orders(
            session=session, company_id=company_id, params=params
        )

        # -------------------------------------------------------------------
        # 9, 10, 11. Stock, Agotados y Baja Rotación
        # -------------------------------------------------------------------
        stock_kpi, out_of_stock_count, low_rotation_count = await self._calc_stock_metrics(
            session=session, company_id=company_id, params=params
        )

        # -------------------------------------------------------------------
        # 12 & 13. Rankings de Productos Más Rentables y Más Vendidos
        # -------------------------------------------------------------------
        top_profitable, top_selling, least_selling = await self._calc_product_rankings(
            session=session,
            company_id=company_id,
            start=p_start,
            end=p_end,
            params=params,
        )

        # -------------------------------------------------------------------
        # 14. Promociones Activas
        # -------------------------------------------------------------------
        active_promos_count = await self._calc_active_promotions(
            session=session, company_id=company_id, params=params
        )

        # -------------------------------------------------------------------
        # 15. Envíos Pendientes
        # -------------------------------------------------------------------
        pending_shipments_count = await self._calc_pending_shipments(
            session=session, company_id=company_id, params=params
        )

        # Consolidar KPIs
        kpis = DashboardKPIs(
            today_sales=today_sales,
            month_sales=month_sales,
            revenue=revenue_kpi,
            profit=profit_kpi,
            margin=margin_kpi,
            commissions=commissions_kpi,
            pending_orders_count=pending_orders_count,
            pending_orders_amount=pending_orders_amount,
            products_sold_units=sold_units,
            previous_products_sold_units=prev_units,
            products_sold_growth_pct=sold_growth,
            stock=stock_kpi,
            out_of_stock_count=out_of_stock_count,
            low_rotation_count=low_rotation_count,
            top_profitable_products=top_profitable[:5],
            top_selling_products=top_selling[:5],
            active_promotions_count=active_promos_count,
            pending_shipments_count=pending_shipments_count,
        )

        # -------------------------------------------------------------------
        # GENERACIÓN DE LAS 9 GRÁFICAS EJECUTIVAS
        # -------------------------------------------------------------------
        charts = await self._generate_dashboard_charts(
            session=session,
            company_id=company_id,
            p_start=p_start,
            p_end=p_end,
            prev_start=prev_start,
            prev_end=prev_end,
            curr_fin=curr_fin,
            top_selling=top_selling,
            least_selling=least_selling,
            params=params,
        )

        return ExecutiveDashboardResponse(
            company_id=str(company_id),
            company_name=company_name,
            currency="MXN",
            period_start=p_start,
            period_end=p_end,
            previous_period_start=prev_start,
            previous_period_end=prev_end,
            filters_applied={
                "preset": params.preset,
                "meli_account_id": str(params.meli_account_id) if params.meli_account_id else None,
                "product_id": str(params.product_id) if params.product_id else None,
                "sku": params.sku,
                "category": params.category,
                "status": params.status,
                "compare": params.compare,
                "compare_to": params.compare_to,
            },
            kpis=kpis,
            charts=charts,
        )

    # =======================================================================
    # MÉTODOS INTERNOS DE CÁLCULO DE KPIS
    # =======================================================================

    async def _calc_sales_in_range(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        range_start: datetime,
        range_end: datetime,
        compare_start: datetime,
        compare_end: datetime,
        params: DashboardFilterParams,
    ) -> SalesMetric:
        """Calcula ventas brutas y conteo en un rango dado comparado con un rango previo."""
        curr_stmt = (
            select(
                func.coalesce(func.sum(Order.total_amount), 0.0).label("gross"),
                func.count(Order.id).label("count"),
            )
            .join(MeliAccount, Order.meli_account_id == MeliAccount.id)
            .where(
                MeliAccount.company_id == company_id,
                Order.status != "cancelled",
                Order.date_created_meli >= range_start,
                Order.date_created_meli <= range_end,
            )
        )
        if params.meli_account_id:
            curr_stmt = curr_stmt.where(Order.meli_account_id == params.meli_account_id)
        if params.status:
            curr_stmt = curr_stmt.where(Order.status == params.status)
        if params.sku or params.product_id or params.category:
            sub = select(OrderItem.order_id)
            if params.sku:
                sub = sub.where(OrderItem.seller_sku.ilike(f"%{params.sku}%"))
            if params.product_id:
                sub = sub.where(OrderItem.product_id == params.product_id)
            if params.category:
                sub = sub.join(Product, OrderItem.product_id == Product.id)
                sub = sub.where(Product.category.ilike(f"%{params.category}%"))
            curr_stmt = curr_stmt.where(Order.id.in_(sub))

        curr_res = (await session.execute(curr_stmt)).one()
        curr_gross = float(curr_res.gross or 0.0)
        curr_count = int(curr_res.count or 0)

        prev_stmt = (
            select(func.coalesce(func.sum(Order.total_amount), 0.0).label("gross"))
            .join(MeliAccount, Order.meli_account_id == MeliAccount.id)
            .where(
                MeliAccount.company_id == company_id,
                Order.status != "cancelled",
                Order.date_created_meli >= compare_start,
                Order.date_created_meli <= compare_end,
            )
        )
        if params.meli_account_id:
            prev_stmt = prev_stmt.where(Order.meli_account_id == params.meli_account_id)
        if params.status:
            prev_stmt = prev_stmt.where(Order.status == params.status)
        if params.sku or params.product_id or params.category:
            sub_prev = select(OrderItem.order_id)
            if params.sku:
                sub_prev = sub_prev.where(OrderItem.seller_sku.ilike(f"%{params.sku}%"))
            if params.product_id:
                sub_prev = sub_prev.where(OrderItem.product_id == params.product_id)
            if params.category:
                sub_prev = sub_prev.join(Product, OrderItem.product_id == Product.id)
                sub_prev = sub_prev.where(Product.category.ilike(f"%{params.category}%"))
            prev_stmt = prev_stmt.where(Order.id.in_(sub_prev))

        prev_gross = float((await session.execute(prev_stmt)).scalar() or 0.0)

        return SalesMetric(
            gross_amount=round(curr_gross, 2),
            orders_count=curr_count,
            previous_gross_amount=round(prev_gross, 2),
            growth_pct=_calc_growth(curr_gross, prev_gross),
        )

    async def _calc_period_financials(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        start: datetime,
        end: datetime,
        params: DashboardFilterParams,
    ) -> dict[str, Any]:
        """Calcula ingresos, COGS, comisiones y rentabilidad desglosada confirmada vs estimada."""
        stmt = (
            select(Order)
            .join(MeliAccount, Order.meli_account_id == MeliAccount.id)
            .where(
                MeliAccount.company_id == company_id,
                Order.status != "cancelled",
                Order.date_created_meli >= start,
                Order.date_created_meli <= end,
            )
            .options(
                selectinload(Order.items).selectinload(OrderItem.product),
                selectinload(Order.items).selectinload(OrderItem.variant),
            )
        )

        if params.meli_account_id:
            stmt = stmt.where(Order.meli_account_id == params.meli_account_id)
        if params.status:
            stmt = stmt.where(Order.status == params.status)

        if params.sku or params.product_id or params.category:
            sub_fin = select(OrderItem.order_id)
            if params.sku:
                sub_fin = sub_fin.where(OrderItem.seller_sku.ilike(f"%{params.sku}%"))
            if params.product_id:
                sub_fin = sub_fin.where(OrderItem.product_id == params.product_id)
            if params.category:
                sub_fin = sub_fin.join(Product, OrderItem.product_id == Product.id)
                sub_fin = sub_fin.where(Product.category.ilike(f"%{params.category}%"))
            stmt = stmt.where(Order.id.in_(sub_fin))

        filtered_orders = list((await session.execute(stmt)).scalars().all())

        rev_total = 0.0
        rev_conf = 0.0
        rev_est = 0.0

        prof_total = 0.0
        prof_conf = 0.0
        prof_est = 0.0

        cogs_total = 0.0
        meli_fees = 0.0
        shipping_costs = 0.0
        units_sold = 0

        for o in filtered_orders:
            gross = float(o.total_amount or 0.0)
            profit = float(o.estimated_profit or 0.0)
            cogs = float(o.cogs_total or 0.0)
            fee = float(o.meli_fee_amount or 0.0)
            ship = float(o.shipping_cost_seller or 0.0)
            u_count = sum(it.quantity for it in o.items)

            rev_total += gross
            prof_total += profit
            cogs_total += cogs
            meli_fees += fee
            shipping_costs += ship
            units_sold += u_count

            # Confirmado: Pedido pagado y acreditado o entregado
            is_confirmed = (
                o.payment_status in ["paid", "accredited"]
                or o.status in ["paid", "delivered", "shipped"]
            )
            if is_confirmed:
                rev_conf += gross
                prof_conf += profit
            else:
                rev_est += gross
                prof_est += profit

        taxes_withheld = round(rev_total * 0.09, 2)  # 8% IVA + 1% ISR promedio SAT
        commissions_total = round(meli_fees + shipping_costs + taxes_withheld, 2)

        margin_pct = round((prof_total / rev_total) * 100, 2) if rev_total > 0 else 0.0
        margin_conf_pct = round((prof_conf / rev_conf) * 100, 2) if rev_conf > 0 else 0.0
        margin_est_pct = round((prof_est / rev_est) * 100, 2) if rev_est > 0 else 0.0

        return {
            "orders_count": len(filtered_orders),
            "units_sold": units_sold,
            "revenue_total": round(rev_total, 2),
            "revenue_confirmed": round(rev_conf, 2),
            "revenue_estimated": round(rev_est, 2),
            "profit_total": round(prof_total, 2),
            "profit_confirmed": round(prof_conf, 2),
            "profit_estimated": round(prof_est, 2),
            "margin_pct": margin_pct,
            "margin_confirmed_pct": margin_conf_pct,
            "margin_estimated_pct": margin_est_pct,
            "cogs_total": round(cogs_total, 2),
            "meli_fees": round(meli_fees, 2),
            "shipping_costs": round(shipping_costs, 2),
            "taxes_withheld": taxes_withheld,
            "commissions_total": commissions_total,
            "orders_list": filtered_orders,
        }

    async def _calc_pending_orders(
        self, session: AsyncSession, company_id: uuid.UUID, params: DashboardFilterParams
    ) -> tuple[int, float]:
        """Calcula el número e importe de pedidos pendientes de despacho o recolección."""
        stmt = (
            select(
                func.count(Order.id).label("count"),
                func.coalesce(func.sum(Order.total_amount), 0.0).label("amount"),
            )
            .join(MeliAccount, Order.meli_account_id == MeliAccount.id)
            .where(
                MeliAccount.company_id == company_id,
                Order.status.in_(["confirmed", "paid", "processing"]),
                Order.shipment_status.in_(["pending", "handling", "ready_to_ship"]),
            )
        )
        if params.meli_account_id:
            stmt = stmt.where(Order.meli_account_id == params.meli_account_id)
        if params.sku or params.product_id or params.category:
            sub_pend = select(OrderItem.order_id)
            if params.sku:
                sub_pend = sub_pend.where(OrderItem.seller_sku.ilike(f"%{params.sku}%"))
            if params.product_id:
                sub_pend = sub_pend.where(OrderItem.product_id == params.product_id)
            if params.category:
                sub_pend = sub_pend.join(Product, OrderItem.product_id == Product.id)
                sub_pend = sub_pend.where(Product.category.ilike(f"%{params.category}%"))
            stmt = stmt.where(Order.id.in_(sub_pend))

        res = (await session.execute(stmt)).one()
        return int(res.count or 0), round(float(res.amount or 0.0), 2)

    async def _calc_stock_metrics(
        self, session: AsyncSession, company_id: uuid.UUID, params: DashboardFilterParams
    ) -> tuple[StockKPI, int, int]:
        """Calcula totales de stock, valuación en COGS, SKUs agotados y SKUs con baja rotación."""
        stmt = (
            select(
                Inventory,
                ProductVariant,
                Product,
            )
            .join(Warehouse, Inventory.warehouse_id == Warehouse.id)
            .join(ProductVariant, Inventory.variant_id == ProductVariant.id)
            .join(Product, ProductVariant.product_id == Product.id)
            .where(Warehouse.company_id == company_id)
        )

        if params.sku:
            stmt = stmt.where(ProductVariant.sku.ilike(f"%{params.sku.strip()}%"))
        if params.category:
            stmt = stmt.where(Product.category == params.category)
        if params.product_id:
            stmt = stmt.where(Product.id == params.product_id)

        results = (await session.execute(stmt)).all()

        total_physical = 0
        total_reserved = 0
        total_blocked = 0
        total_available = 0
        total_cogs_value = 0.0
        out_of_stock_count = 0

        # Para baja rotación: calcular ventas en los últimos 30 días por variante
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        recent_sales_stmt = (
            select(
                OrderItem.variant_id,
                func.coalesce(func.sum(OrderItem.quantity), 0).label("sold_qty"),
            )
            .join(Order, OrderItem.order_id == Order.id)
            .join(MeliAccount, Order.meli_account_id == MeliAccount.id)
            .where(
                MeliAccount.company_id == company_id,
                Order.status != "cancelled",
                Order.date_created_meli >= thirty_days_ago,
            )
            .group_by(OrderItem.variant_id)
        )
        recent_sales_res = (await session.execute(recent_sales_stmt)).all()
        recent_sales_map = {row.variant_id: int(row.sold_qty) for row in recent_sales_res}

        low_rotation_count = 0

        for inv, var, prod in results:
            phys = int(inv.quantity_on_hand)
            res = int(inv.quantity_reserved)
            blk = int(inv.quantity_blocked)
            avail = max(0, phys - res - blk)
            cogs = float(var.cogs_cost or 0.0)

            total_physical += phys
            total_reserved += res
            total_blocked += blk
            total_available += avail
            total_cogs_value += phys * cogs

            if avail <= 0 or phys <= 0:
                out_of_stock_count += 1

            # Baja rotación: tiene stock físico pero 0 ventas en los últimos 30 días
            if phys > 0:
                sold_30d = recent_sales_map.get(var.id, 0)
                if sold_30d == 0:
                    low_rotation_count += 1

        stock_kpi = StockKPI(
            total_physical=total_physical,
            total_available=total_available,
            total_reserved=total_reserved,
            total_blocked=total_blocked,
            inventory_value_cogs=round(total_cogs_value, 2),
        )

        return stock_kpi, out_of_stock_count, low_rotation_count

    async def _calc_product_rankings(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        start: datetime,
        end: datetime,
        params: DashboardFilterParams,
    ) -> tuple[list[TopProductItem], list[TopProductItem], list[TopProductItem]]:
        """Calcula listas ordenadas de productos más rentables, más vendidos y menos vendidos."""
        stmt = (
            select(
                OrderItem.variant_id,
                OrderItem.seller_sku,
                OrderItem.title,
                func.sum(OrderItem.quantity).label("total_units"),
                func.sum(OrderItem.quantity * OrderItem.unit_price).label("total_revenue"),
                func.sum(
                    (OrderItem.quantity * OrderItem.unit_price)
                    - (OrderItem.quantity * OrderItem.cogs_unit)
                    - OrderItem.sale_fee
                ).label("total_profit"),
            )
            .join(Order, OrderItem.order_id == Order.id)
            .join(MeliAccount, Order.meli_account_id == MeliAccount.id)
            .where(
                MeliAccount.company_id == company_id,
                Order.status != "cancelled",
                Order.date_created_meli >= start,
                Order.date_created_meli <= end,
            )
            .group_by(OrderItem.variant_id, OrderItem.seller_sku, OrderItem.title)
        )

        if params.meli_account_id:
            stmt = stmt.where(Order.meli_account_id == params.meli_account_id)
        if params.status:
            stmt = stmt.where(Order.status == params.status)
        if params.sku:
            stmt = stmt.where(OrderItem.seller_sku.ilike(f"%{params.sku}%"))
        if params.product_id:
            stmt = stmt.where(OrderItem.product_id == params.product_id)
        if params.category:
            stmt = stmt.join(Product, OrderItem.product_id == Product.id)
            stmt = stmt.where(Product.category.ilike(f"%{params.category}%"))

        rows = (await session.execute(stmt)).all()

        items: list[TopProductItem] = []
        for r in rows:
            rev = round(float(r.total_revenue or 0.0), 2)
            prof = round(float(r.total_profit or 0.0), 2)
            m_pct = round((prof / rev) * 100, 2) if rev > 0 else 0.0
            items.append(
                TopProductItem(
                    variant_id=str(r.variant_id) if r.variant_id else None,
                    sku=r.seller_sku or "SIN-SKU",
                    name=r.title or "Producto",
                    units_sold=int(r.total_units or 0),
                    revenue=rev,
                    profit=prof,
                    margin_pct=m_pct,
                )
            )

        # Más rentables (por utilidad neta descendente)
        top_profitable = sorted(items, key=lambda x: x.profit, reverse=True)

        # Más vendidos (por unidades vendidas descendente)
        top_selling = sorted(items, key=lambda x: x.units_sold, reverse=True)

        # Menos vendidos: además de los que vendieron poco, incluir variantes en catálogo con 0 ventas
        all_variants_stmt = (
            select(ProductVariant, Product)
            .join(Product, ProductVariant.product_id == Product.id)
            .where(ProductVariant.company_id == company_id, ProductVariant.is_active.is_(True))
        )
        all_vars = (await session.execute(all_variants_stmt)).all()
        sold_variant_ids = {i.variant_id for i in items if i.variant_id}

        zero_sold_items: list[TopProductItem] = []
        for v, p in all_vars:
            if str(v.id) not in sold_variant_ids:
                zero_sold_items.append(
                    TopProductItem(
                        product_id=str(p.id),
                        variant_id=str(v.id),
                        sku=v.sku,
                        name=f"{p.name} - {v.variant_name}",
                        category=p.category,
                        units_sold=0,
                        revenue=0.0,
                        profit=0.0,
                        margin_pct=0.0,
                    )
                )

        # Combinar 0 ventas primero, luego los de menor venta
        least_selling = sorted(zero_sold_items + items, key=lambda x: (x.units_sold, x.revenue))[:10]

        return top_profitable, top_selling, least_selling

    async def _calc_active_promotions(
        self, session: AsyncSession, company_id: uuid.UUID, params: DashboardFilterParams
    ) -> int:
        """Cuenta las campañas y ofertas actualmente vigentes."""
        now = datetime.now(timezone.utc)
        stmt = (
            select(func.count(distinct(Promotion.id)))
            .join(MeliAccount, Promotion.meli_account_id == MeliAccount.id)
            .where(
                MeliAccount.company_id == company_id,
                Promotion.status.in_(["started", "active"]),
                Promotion.finish_date >= now,
            )
        )
        if params.meli_account_id:
            stmt = stmt.where(Promotion.meli_account_id == params.meli_account_id)

        count = (await session.execute(stmt)).scalar() or 0
        return int(count)

    async def _calc_pending_shipments(
        self, session: AsyncSession, company_id: uuid.UUID, params: DashboardFilterParams
    ) -> int:
        """Cuenta los envíos pendientes de despacho, recolección o preparación."""
        stmt = (
            select(func.count(Shipment.id))
            .join(Order, Shipment.order_id == Order.id)
            .join(MeliAccount, Order.meli_account_id == MeliAccount.id)
            .where(
                MeliAccount.company_id == company_id,
                Order.status != "cancelled",
                or_(
                    Shipment.status.in_(["pending", "handling", "ready_to_ship"]),
                    Shipment.dispatch_status.in_(["pending", "prepared"]),
                ),
            )
        )
        if params.meli_account_id:
            stmt = stmt.where(Order.meli_account_id == params.meli_account_id)

        count = (await session.execute(stmt)).scalar() or 0
        return int(count)

    # =======================================================================
    # GENERACIÓN DE LAS 9 GRÁFICAS EJECUTIVAS
    # =======================================================================

    async def _generate_dashboard_charts(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        p_start: datetime,
        p_end: datetime,
        prev_start: datetime | None,
        prev_end: datetime | None,
        curr_fin: dict[str, Any],
        top_selling: list[TopProductItem],
        least_selling: list[TopProductItem],
        params: DashboardFilterParams,
    ) -> DashboardCharts:
        """Genera las estructuras de datos completas para las 9 gráficas del dashboard."""
        # 1. Gráfica de Ventas Diarias
        daily_sales = self._build_daily_sales_chart(curr_fin["orders_list"], p_start, p_end)

        # Si hay periodo previo, consultar y superponer ventas previas
        if prev_start and prev_end:
            prev_orders_stmt = (
                select(Order)
                .join(MeliAccount, Order.meli_account_id == MeliAccount.id)
                .where(
                    MeliAccount.company_id == company_id,
                    Order.status != "cancelled",
                    Order.date_created_meli >= prev_start,
                    Order.date_created_meli <= prev_end,
                )
            )
            prev_orders = (await session.execute(prev_orders_stmt)).scalars().all()
            prev_daily = self._build_daily_sales_chart(prev_orders, prev_start, prev_end)
            # Alinear serie comparativa en tamaño
            daily_sales.previous_period_gross = (
                prev_daily.current_period_gross[: len(daily_sales.labels)]
                if len(prev_daily.current_period_gross) >= len(daily_sales.labels)
                else prev_daily.current_period_gross
                + [0.0] * (len(daily_sales.labels) - len(prev_daily.current_period_gross))
            )

        # 2. Gráfica de Ventas Mensuales (Año en curso vs Año anterior)
        monthly_sales = await self._build_monthly_sales_chart(session, company_id, params)

        # 3. Gráfica de Rentabilidad (Ingreso vs COGS vs Comisiones vs Utilidad)
        profitability = self._build_profitability_chart(curr_fin["orders_list"], p_start, p_end)

        # 4. Gráfica de Evolución de Inventario (Entradas vs Salidas Kardex)
        inventory_evolution = await self._build_inventory_evolution_chart(
            session, company_id, p_start, p_end
        )

        # 5. Top 10 Productos Más Vendidos
        top_selling_chart = RankingChartItem(
            labels=[p.sku for p in top_selling[:10]],
            units=[p.units_sold for p in top_selling[:10]],
            values=[p.revenue for p in top_selling[:10]],
        )

        # 6. Top 10 Productos Menos Vendidos
        least_selling_chart = RankingChartItem(
            labels=[p.sku for p in least_selling[:10]],
            units=[p.units_sold for p in least_selling[:10]],
            values=[p.revenue for p in least_selling[:10]],
        )

        # 7. Gráfica de Distribución de Comisiones
        commissions_chart = BreakdownChart(
            labels=["Comisión de Venta MeLi", "Costo Envíos Vendedor", "Retención IVA SAT", "Retención ISR SAT"],
            values=[
                curr_fin["meli_fees"],
                curr_fin["shipping_costs"],
                round(curr_fin["revenue_total"] * 0.08, 2),  # 8% IVA retenido SAT
                round(curr_fin["revenue_total"] * 0.01, 2),  # 1% ISR retenido SAT
            ],
        )

        # 8. Gráfica de Estructura de Gastos Totales
        ext_expenses_stmt = select(func.coalesce(func.sum(ExternalExpense.amount), 0.0)).where(
            ExternalExpense.company_id == company_id,
            ExternalExpense.expense_date >= _norm_dt(p_start),
            ExternalExpense.expense_date <= _norm_dt(p_end),
        )
        ext_expenses_total = float((await session.execute(ext_expenses_stmt)).scalar() or 0.0)

        expenses_chart = BreakdownChart(
            labels=["Costo Mercancía (COGS)", "Comisiones Marketplace", "Logística y Envíos", "Gastos Operativos Externos"],
            values=[
                curr_fin["cogs_total"],
                curr_fin["meli_fees"],
                curr_fin["shipping_costs"],
                round(ext_expenses_total, 2),
            ],
        )

        # 9. Gráfica de Rotación de Inventario por Categoría
        rotation_chart = await self._build_rotation_chart(session, company_id, p_start, p_end)

        return DashboardCharts(
            daily_sales=daily_sales,
            monthly_sales=monthly_sales,
            profitability=profitability,
            inventory_evolution=inventory_evolution,
            top_selling=top_selling_chart,
            least_selling=least_selling_chart,
            commissions=commissions_chart,
            expenses=expenses_chart,
            rotation=rotation_chart,
        )

    def _build_daily_sales_chart(
        self, orders: list[Order], p_start: datetime, p_end: datetime
    ) -> DailySalesChart:
        """Construye serie temporal diaria de ingresos brutos y número de órdenes."""
        delta_days = max(1, (p_end.date() - p_start.date()).days + 1)
        # Limitar número de etiquetas a 31 días máximo para legibilidad
        date_keys = [
            (p_start.date() + timedelta(days=i)).isoformat()
            for i in range(min(delta_days, 60))
        ]

        gross_map = {k: 0.0 for k in date_keys}
        count_map = {k: 0 for k in date_keys}

        for o in orders:
            d_str = _norm_dt(o.date_created_meli).date().isoformat()
            if d_str in gross_map:
                gross_map[d_str] += float(o.total_amount or 0.0)
                count_map[d_str] += 1

        return DailySalesChart(
            labels=date_keys,
            current_period_gross=[round(gross_map[k], 2) for k in date_keys],
            current_period_orders=[count_map[k] for k in date_keys],
            previous_period_gross=[],
        )

    async def _build_monthly_sales_chart(
        self, session: AsyncSession, company_id: uuid.UUID, params: DashboardFilterParams
    ) -> MonthlySalesChart:
        """Construye serie mensual de los 12 meses del año en curso vs año anterior."""
        now = datetime.now(timezone.utc)
        curr_year = now.year
        prev_year = curr_year - 1

        curr_year_start = datetime(curr_year, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        curr_year_end = datetime(curr_year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        prev_year_start = datetime(prev_year, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        prev_year_end = datetime(prev_year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

        # Consulta órdenes año actual
        curr_stmt = (
            select(Order)
            .join(MeliAccount, Order.meli_account_id == MeliAccount.id)
            .where(
                MeliAccount.company_id == company_id,
                Order.status != "cancelled",
                Order.date_created_meli >= curr_year_start,
                Order.date_created_meli <= curr_year_end,
            )
        )
        if params.meli_account_id:
            curr_stmt = curr_stmt.where(Order.meli_account_id == params.meli_account_id)

        curr_orders = (await session.execute(curr_stmt)).scalars().all()

        # Consulta órdenes año previo
        prev_stmt = (
            select(Order)
            .join(MeliAccount, Order.meli_account_id == MeliAccount.id)
            .where(
                MeliAccount.company_id == company_id,
                Order.status != "cancelled",
                Order.date_created_meli >= prev_year_start,
                Order.date_created_meli <= prev_year_end,
            )
        )
        if params.meli_account_id:
            prev_stmt = prev_stmt.where(Order.meli_account_id == params.meli_account_id)

        prev_orders = (await session.execute(prev_stmt)).scalars().all()

        month_labels = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
        curr_monthly = [0.0] * 12
        prev_monthly = [0.0] * 12

        for o in curr_orders:
            m = _norm_dt(o.date_created_meli).month - 1
            if 0 <= m < 12:
                curr_monthly[m] += float(o.total_amount or 0.0)

        for o in prev_orders:
            m = _norm_dt(o.date_created_meli).month - 1
            if 0 <= m < 12:
                prev_monthly[m] += float(o.total_amount or 0.0)

        return MonthlySalesChart(
            labels=month_labels,
            current_year_gross=[round(v, 2) for v in curr_monthly],
            previous_year_gross=[round(v, 2) for v in prev_monthly],
        )

    def _build_profitability_chart(
        self, orders: list[Order], p_start: datetime, p_end: datetime
    ) -> ProfitabilityChart:
        """Construye serie temporal de Ingreso, COGS, Comisiones y Utilidad Neta."""
        delta_days = max(1, (p_end.date() - p_start.date()).days + 1)
        date_keys = [
            (p_start.date() + timedelta(days=i)).isoformat()
            for i in range(min(delta_days, 60))
        ]

        rev_map = {k: 0.0 for k in date_keys}
        cogs_map = {k: 0.0 for k in date_keys}
        comm_map = {k: 0.0 for k in date_keys}
        prof_map = {k: 0.0 for k in date_keys}

        for o in orders:
            d_str = _norm_dt(o.date_created_meli).date().isoformat()
            if d_str in rev_map:
                rev = float(o.total_amount or 0.0)
                cg = float(o.cogs_total or 0.0)
                fee = float(o.meli_fee_amount or 0.0) + float(o.shipping_cost_seller or 0.0)
                pr = float(o.estimated_profit or 0.0)

                rev_map[d_str] += rev
                cogs_map[d_str] += cg
                comm_map[d_str] += fee
                prof_map[d_str] += pr

        return ProfitabilityChart(
            labels=date_keys,
            revenue=[round(rev_map[k], 2) for k in date_keys],
            cogs=[round(cogs_map[k], 2) for k in date_keys],
            commissions=[round(comm_map[k], 2) for k in date_keys],
            net_profit=[round(prof_map[k], 2) for k in date_keys],
        )

    async def _build_inventory_evolution_chart(
        self, session: AsyncSession, company_id: uuid.UUID, p_start: datetime, p_end: datetime
    ) -> InventoryEvolutionChart:
        """Construye serie temporal de entradas (INBOUND) vs salidas (OUTBOUND) de inventario."""
        stmt = (
            select(InventoryMovement)
            .join(Inventory, InventoryMovement.inventory_id == Inventory.id)
            .join(Warehouse, Inventory.warehouse_id == Warehouse.id)
            .where(
                Warehouse.company_id == company_id,
                InventoryMovement.created_at >= p_start,
                InventoryMovement.created_at <= p_end,
            )
            .order_by(InventoryMovement.created_at.asc())
        )
        movements = (await session.execute(stmt)).scalars().all()

        delta_days = max(1, (p_end.date() - p_start.date()).days + 1)
        date_keys = [
            (p_start.date() + timedelta(days=i)).isoformat()
            for i in range(min(delta_days, 60))
        ]

        inbound_map = {k: 0 for k in date_keys}
        outbound_map = {k: 0 for k in date_keys}

        for m in movements:
            d_str = _norm_dt(m.created_at).date().isoformat()
            if d_str in inbound_map:
                delta = int(m.quantity_delta)
                if delta > 0:
                    inbound_map[d_str] += delta
                else:
                    outbound_map[d_str] += abs(delta)

        net_running = 0
        balance_list = []
        for k in date_keys:
            net_running += inbound_map[k] - outbound_map[k]
            balance_list.append(net_running)

        return InventoryEvolutionChart(
            labels=date_keys,
            inbound_units=[inbound_map[k] for k in date_keys],
            outbound_units=[outbound_map[k] for k in date_keys],
            net_balance=balance_list,
        )

    async def _build_rotation_chart(
        self, session: AsyncSession, company_id: uuid.UUID, p_start: datetime, p_end: datetime
    ) -> RotationChart:
        """Calcula ratio de rotación de inventario (Ventas / Stock) agrupado por categoría."""
        # 1. Stock por categoría
        stock_stmt = (
            select(
                Product.category,
                func.coalesce(func.sum(Inventory.quantity_on_hand), 0).label("stock"),
            )
            .join(ProductVariant, Inventory.variant_id == ProductVariant.id)
            .join(Product, ProductVariant.product_id == Product.id)
            .join(Warehouse, Inventory.warehouse_id == Warehouse.id)
            .where(Warehouse.company_id == company_id)
            .group_by(Product.category)
        )
        stock_res = (await session.execute(stock_stmt)).all()
        cat_stock = {row.category or "Sin Categoría": int(row.stock) for row in stock_res}

        # 2. Ventas por categoría
        sales_stmt = (
            select(
                Product.category,
                func.coalesce(func.sum(OrderItem.quantity), 0).label("sold"),
            )
            .join(ProductVariant, OrderItem.variant_id == ProductVariant.id)
            .join(Product, ProductVariant.product_id == Product.id)
            .join(Order, OrderItem.order_id == Order.id)
            .join(MeliAccount, Order.meli_account_id == MeliAccount.id)
            .where(
                MeliAccount.company_id == company_id,
                Order.status != "cancelled",
                Order.date_created_meli >= p_start,
                Order.date_created_meli <= p_end,
            )
            .group_by(Product.category)
        )
        sales_res = (await session.execute(sales_stmt)).all()
        cat_sales = {row.category or "Sin Categoría": int(row.sold) for row in sales_res}

        all_cats = sorted(set(list(cat_stock.keys()) + list(cat_sales.keys())))
        if not all_cats:
            all_cats = ["General"]
            cat_stock["General"] = 0
            cat_sales["General"] = 0

        categories = []
        turnover_ratios = []
        stock_list = []
        sold_list = []

        for c in all_cats:
            stk = cat_stock.get(c, 0)
            sld = cat_sales.get(c, 0)
            ratio = round(sld / stk, 2) if stk > 0 else (round(float(sld), 2) if sld > 0 else 0.0)
            categories.append(c)
            turnover_ratios.append(ratio)
            stock_list.append(stk)
            sold_list.append(sld)

        return RotationChart(
            categories=categories,
            turnover_ratio=turnover_ratios,
            stock_units=stock_list,
            sold_units=sold_list,
        )

    # =======================================================================
    # METADATOS Y CATÁLOGOS DE FILTRO
    # =======================================================================

    async def get_filter_options(
        self, session: AsyncSession, company_id: uuid.UUID
    ) -> dict[str, Any]:
        """Retorna las cuentas de Mercado Libre, categorías y almacenes para poblar los filtros del UI."""
        acc_stmt = select(MeliAccount).where(
            MeliAccount.company_id == company_id, MeliAccount.is_active.is_(True)
        )
        accounts = (await session.execute(acc_stmt)).scalars().all()

        cat_stmt = (
            select(Product.category)
            .where(Product.company_id == company_id, Product.category.is_not(None))
            .distinct()
        )
        categories = (await session.execute(cat_stmt)).scalars().all()

        wh_stmt = select(Warehouse).where(
            Warehouse.company_id == company_id, Warehouse.is_active.is_(True)
        )
        warehouses = (await session.execute(wh_stmt)).scalars().all()

        return {
            "meli_accounts": [{"id": str(a.id), "nickname": a.nickname} for a in accounts],
            "categories": [c for c in categories if c],
            "warehouses": [{"id": str(w.id), "name": w.name, "code": w.code} for w in warehouses],
            "order_statuses": [
                {"value": "paid", "label": "Pagado"},
                {"value": "confirmed", "label": "Confirmado"},
                {"value": "processing", "label": "En Preparación"},
                {"value": "shipped", "label": "Enviado"},
                {"value": "delivered", "label": "Entregado"},
                {"value": "cancelled", "label": "Cancelado"},
                {"value": "returned", "label": "Devuelto"},
            ],
            "presets": [
                {"value": "today", "label": "Hoy"},
                {"value": "yesterday", "label": "Ayer"},
                {"value": "7d", "label": "Últimos 7 días"},
                {"value": "30d", "label": "Últimos 30 días"},
                {"value": "this_month", "label": "Este mes"},
                {"value": "last_month", "label": "Mes anterior"},
                {"value": "this_year", "label": "Año actual"},
                {"value": "custom", "label": "Personalizado"},
            ],
        }

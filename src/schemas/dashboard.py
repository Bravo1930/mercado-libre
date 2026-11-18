"""Esquemas Pydantic para el Dashboard Ejecutivo del ERP Mercado Libre México."""

from datetime import date, datetime
from typing import Any, Literal
import uuid

from pydantic import BaseModel, Field


# ===========================================================================
# 1. PARÁMETROS DE FILTRADO
# ===========================================================================

DashboardPresetType = Literal[
    "today",
    "yesterday",
    "7d",
    "30d",
    "this_month",
    "last_month",
    "this_year",
    "custom",
]

CompareToType = Literal["previous_period", "previous_year"]


class DashboardFilterParams(BaseModel):
    """Parámetros de consulta y filtrado para el dashboard ejecutivo."""

    date_from: datetime | date | None = Field(None, description="Fecha inicial del periodo de análisis")
    date_to: datetime | date | None = Field(None, description="Fecha final del periodo de análisis")
    preset: DashboardPresetType = Field("30d", description="Rango de fecha preconfigurado")
    meli_account_id: uuid.UUID | None = Field(None, description="Filtrar por cuenta oficial de Mercado Libre")
    product_id: uuid.UUID | None = Field(None, description="Filtrar por producto maestro")
    sku: str | None = Field(None, description="Filtrar por SKU específico o término parcial")
    category: str | None = Field(None, description="Filtrar por categoría del producto")
    status: str | None = Field(None, description="Filtrar por estado del pedido (paid, confirmed, delivered, etc.)")
    compare: bool = Field(True, description="Indica si se debe calcular la comparación con el periodo previo")
    compare_to: CompareToType = Field("previous_period", description="Base de comparación: periodo inmediatamente anterior o año anterior")


# ===========================================================================
# 2. INDICADORES Y KPIS
# ===========================================================================

class SalesMetric(BaseModel):
    """Métrica de ventas agrupada con desglose monetario y conteo."""

    gross_amount: float = Field(0.0, description="Monto bruto de ventas ($ MXN)")
    orders_count: int = Field(0, description="Número de pedidos generados")
    previous_gross_amount: float = Field(0.0, description="Monto en el periodo comparativo anterior")
    growth_pct: float = Field(0.0, description="Variación porcentual respecto al periodo previo")


class FinancialDifferentiatedMetric(BaseModel):
    """Métrica financiera con estricta diferenciación de cifras confirmadas y estimadas."""

    total: float = Field(0.0, description="Monto total consolidado ($ MXN)")
    confirmed: float = Field(0.0, description="Cifra confirmada (pedidos pagados, entregados o acreditados)")
    estimated: float = Field(0.0, description="Cifra estimada (pedidos activos en tránsito o pendientes)")
    previous_total: float = Field(0.0, description="Total en el periodo comparativo anterior")
    growth_pct: float = Field(0.0, description="Variación porcentual respecto al periodo previo")


class MarginMetric(BaseModel):
    """Margen neto porcentual con desglose confirmado y estimado."""

    overall_pct: float = Field(0.0, description="Margen neto total porcentual")
    confirmed_pct: float = Field(0.0, description="Margen neto confirmado %")
    estimated_pct: float = Field(0.0, description="Margen neto estimado %")
    previous_pct: float = Field(0.0, description="Margen neto en periodo anterior %")
    growth_pct: float = Field(0.0, description="Diferencia en puntos porcentuales vs periodo previo")


class CommissionsMetric(BaseModel):
    """Desglose de comisiones marketplace, costos de flete y retenciones SAT."""

    total: float = Field(0.0, description="Total comisiones y costos deducidos ($ MXN)")
    marketplace_fees: float = Field(0.0, description="Tarifa por venta y cobro Mercado Libre")
    shipping_costs: float = Field(0.0, description="Costos de flete y envíos asumidos por el vendedor")
    taxes_withheld: float = Field(0.0, description="Retenciones estimadas SAT (IVA 8% + ISR 1%)")


class StockKPI(BaseModel):
    """Estado general y valuación monetaria del inventario."""

    total_physical: int = Field(0, description="Total existencias físicas en almacenes")
    total_available: int = Field(0, description="Stock disponible (Físico - Reservado - Bloqueado)")
    total_reserved: int = Field(0, description="Stock reservado por pedidos activos")
    total_blocked: int = Field(0, description="Stock bloqueado en cuarentena o inspección")
    inventory_value_cogs: float = Field(0.0, description="Valuación monetaria total a costo de adquisición ($ MXN)")


class TopProductItem(BaseModel):
    """Ficha resumen de producto en rankings de ventas y rentabilidad."""

    product_id: str | None = None
    variant_id: str | None = None
    sku: str
    name: str
    category: str | None = None
    units_sold: int = 0
    revenue: float = 0.0
    profit: float = 0.0
    margin_pct: float = 0.0


class DashboardKPIs(BaseModel):
    """Los 15 Indicadores Ejecutivos requeridos para el negocio."""

    # 1. Ventas del día
    today_sales: SalesMetric
    # 2. Ventas del mes
    month_sales: SalesMetric
    # 3. Ingresos
    revenue: FinancialDifferentiatedMetric
    # 4. Ganancias
    profit: FinancialDifferentiatedMetric
    # 5. Margen
    margin: MarginMetric
    # 6. Comisiones
    commissions: CommissionsMetric
    # 7. Pedidos pendientes
    pending_orders_count: int
    pending_orders_amount: float
    # 8. Productos vendidos (unidades)
    products_sold_units: int
    previous_products_sold_units: int
    products_sold_growth_pct: float
    # 9. Stock
    stock: StockKPI
    # 10. Agotados
    out_of_stock_count: int
    # 11. Baja rotación
    low_rotation_count: int
    # 12. Productos más rentables
    top_profitable_products: list[TopProductItem]
    # 13. Productos más vendidos
    top_selling_products: list[TopProductItem]
    # 14. Promociones activas
    active_promotions_count: int
    # 15. Envíos pendientes
    pending_shipments_count: int


# ===========================================================================
# 3. DATOS PARA LAS 9 GRÁFICAS EJECUTIVAS
# ===========================================================================

class DailySalesChart(BaseModel):
    """Gráfica 1: Ventas diarias con comparativa de curva previa."""

    labels: list[str] = Field(default_factory=list, description="Etiquetas de fechas (YYYY-MM-DD)")
    current_period_gross: list[float] = Field(default_factory=list, description="Ventas periodo actual ($ MXN)")
    current_period_orders: list[int] = Field(default_factory=list, description="Pedidos periodo actual")
    previous_period_gross: list[float] = Field(default_factory=list, description="Ventas periodo comparativo ($ MXN)")


class MonthlySalesChart(BaseModel):
    """Gráfica 2: Ventas mensuales del año en curso vs año anterior."""

    labels: list[str] = Field(default_factory=list, description="Meses (Ene, Feb, Mar...)")
    current_year_gross: list[float] = Field(default_factory=list, description="Ventas año actual ($ MXN)")
    previous_year_gross: list[float] = Field(default_factory=list, description="Ventas año anterior ($ MXN)")


class ProfitabilityChart(BaseModel):
    """Gráfica 3: Rentabilidad multidimensional (Ingresos, COGS, Comisiones y Ganancia Neta)."""

    labels: list[str] = Field(default_factory=list, description="Fechas o agrupaciones")
    revenue: list[float] = Field(default_factory=list, description="Ingreso Bruto")
    cogs: list[float] = Field(default_factory=list, description="Costo de Mercancía")
    commissions: list[float] = Field(default_factory=list, description="Comisiones MeLi y Fletes")
    net_profit: list[float] = Field(default_factory=list, description="Utilidad Neta Real")


class InventoryEvolutionChart(BaseModel):
    """Gráfica 4: Evolución de inventario (Entradas vs Salidas de stock)."""

    labels: list[str] = Field(default_factory=list, description="Fechas")
    inbound_units: list[int] = Field(default_factory=list, description="Piezas ingresadas (Compras/Devoluciones)")
    outbound_units: list[int] = Field(default_factory=list, description="Piezas despachadas (Ventas/Mermas)")
    net_balance: list[int] = Field(default_factory=list, description="Balance neto acumulado")


class RankingChartItem(BaseModel):
    """Elemento para gráficas de barras de productos."""

    labels: list[str] = Field(default_factory=list, description="Nombre o SKU del producto")
    units: list[int] = Field(default_factory=list, description="Unidades vendidas")
    values: list[float] = Field(default_factory=list, description="Monto en $ MXN")


class BreakdownChart(BaseModel):
    """Gráfica de pastel o dona para distribución porcentual."""

    labels: list[str] = Field(default_factory=list)
    values: list[float] = Field(default_factory=list)


class RotationChart(BaseModel):
    """Gráfica 9: Rotación de inventario clasificada por categoría."""

    categories: list[str] = Field(default_factory=list)
    turnover_ratio: list[float] = Field(default_factory=list, description="Ratio de rotación: Ventas / Stock")
    stock_units: list[int] = Field(default_factory=list, description="Unidades físicas en stock")
    sold_units: list[int] = Field(default_factory=list, description="Unidades vendidas en periodo")


class DashboardCharts(BaseModel):
    """Las 9 Gráficas Oficiales requeridas para el dashboard ejecutivo."""

    # 1. Ventas diarias
    daily_sales: DailySalesChart
    # 2. Ventas mensuales
    monthly_sales: MonthlySalesChart
    # 3. Rentabilidad
    profitability: ProfitabilityChart
    # 4. Evolución de inventario
    inventory_evolution: InventoryEvolutionChart
    # 5. Productos más vendidos
    top_selling: RankingChartItem
    # 6. Productos menos vendidos
    least_selling: RankingChartItem
    # 7. Comisiones
    commissions: BreakdownChart
    # 8. Gastos
    expenses: BreakdownChart
    # 9. Rotación
    rotation: RotationChart


# ===========================================================================
# 4. RESPUESTA MAESTRA CONSOLIDADA
# ===========================================================================

class ExecutiveDashboardResponse(BaseModel):
    """Respuesta consolidada completa del Dashboard Ejecutivo."""

    company_id: str
    company_name: str
    currency: str = "MXN"
    period_start: datetime
    period_end: datetime
    previous_period_start: datetime | None = None
    previous_period_end: datetime | None = None
    filters_applied: dict[str, Any]
    kpis: DashboardKPIs
    charts: DashboardCharts

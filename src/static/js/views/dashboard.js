/**
 * Vista Ejecutiva: Panel de Control y Analítica del ERP Mercado Libre México.
 * Proporciona:
 * - 15 Indicadores Ejecutivos (Ventas día/mes, Ingresos, Ganancias, Margen, Comisiones, Stock, Agotados, Rotación, etc.).
 * - Cifras diferenciadas: Confirmadas vs Estimadas.
 * - Comparativa automática con periodo previo o año anterior (variaciones % y deltas).
 * - 9 Gráficas analíticas con Chart.js (Ventas diarias, mensuales, rentabilidad, inventario, rankings, gastos, etc.).
 * - Filtros dinámicos (Preset, Fechas, Cuenta MeLi, Categoría, SKU, Estado, Comparar periodos).
 */

import { api } from "../api.js";
import { state } from "../state.js";
import { icons } from "../icons.js";
import { showToast } from "../components/toast.js";

let activeCharts = {};
let currentFilterOptions = null;

export function renderDashboardView() {
  const container = document.createElement("div");
  container.className = "space-y-6 animate-fade-in";

  container.innerHTML = `
    <!-- Header Ejecutivo con Info de Empresa y Acciones -->
    <div class="flex flex-col lg:flex-row lg:items-center justify-between p-6 bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 rounded-3xl text-white shadow-xl gap-4">
      <div>
        <div class="flex items-center space-x-2 text-[#FFE600] text-xs font-bold uppercase tracking-wider mb-1">
          <span class="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
          <span>Mercado Libre México · Dashboard Ejecutivo</span>
          <span>·</span>
          <span>RFC ${state.currentCompany ? state.currentCompany.rfc : 'N/A'}</span>
        </div>
        <h2 class="text-2xl sm:text-3xl font-black tracking-tight flex items-center gap-3">
          <span>${state.currentCompany ? state.currentCompany.legal_name : 'Panel Corporativo'}</span>
          <span class="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-white/10 text-slate-200 border border-white/10">Multiempresa</span>
        </h2>
        <p class="text-xs sm:text-sm text-slate-300 mt-1 max-w-2xl">
          Consolidado en tiempo real de ventas, rentabilidad neta, comisiones MeLi, inventario multi-almacén y proyecciones financieras.
        </p>
      </div>

      <div class="flex flex-wrap items-center gap-2.5">
        <button id="btn-refresh-dashboard" class="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl transition-all shadow-md flex items-center space-x-2 touch-target">
          ${icons.refresh("w-4 h-4")}
          <span>Actualizar Datos</span>
        </button>
        <a href="#tabular" class="px-4 py-2.5 bg-white/10 hover:bg-white/20 text-white text-xs font-bold rounded-xl transition-all border border-white/20 flex items-center space-x-2 touch-target">
          ${icons.tabular ? icons.tabular("w-4 h-4") : icons.orders("w-4 h-4")}
          <span>13 Vistas Tabulares</span>
        </a>
      </div>
    </div>

    <!-- Barra de Filtros y Comparación de Periodos -->
    <div class="p-5 bg-white rounded-2xl border border-slate-200 shadow-sm space-y-4">
      <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3">
        <div class="flex items-center space-x-2 text-xs font-bold text-slate-700 uppercase tracking-wider">
          ${icons.filter ? icons.filter("w-4 h-4 text-blue-600") : ""}
          <span>Filtros y Periodo de Análisis</span>
        </div>
        <!-- Selector de Presets de Fecha -->
        <div class="flex flex-wrap gap-1.5" id="preset-buttons-container">
          <button data-preset="today" class="btn-preset px-3 py-1.5 text-xs font-bold rounded-lg bg-slate-100 text-slate-700 hover:bg-slate-200 transition-all">Hoy</button>
          <button data-preset="yesterday" class="btn-preset px-3 py-1.5 text-xs font-bold rounded-lg bg-slate-100 text-slate-700 hover:bg-slate-200 transition-all">Ayer</button>
          <button data-preset="7d" class="btn-preset px-3 py-1.5 text-xs font-bold rounded-lg bg-slate-100 text-slate-700 hover:bg-slate-200 transition-all">7 Días</button>
          <button data-preset="30d" class="btn-preset px-3 py-1.5 text-xs font-bold rounded-lg bg-blue-600 text-white shadow-sm transition-all active-preset">30 Días</button>
          <button data-preset="this_month" class="btn-preset px-3 py-1.5 text-xs font-bold rounded-lg bg-slate-100 text-slate-700 hover:bg-slate-200 transition-all">Este Mes</button>
          <button data-preset="last_month" class="btn-preset px-3 py-1.5 text-xs font-bold rounded-lg bg-slate-100 text-slate-700 hover:bg-slate-200 transition-all">Mes Anterior</button>
          <button data-preset="this_year" class="btn-preset px-3 py-1.5 text-xs font-bold rounded-lg bg-slate-100 text-slate-700 hover:bg-slate-200 transition-all">Año Actual</button>
          <button data-preset="custom" class="btn-preset px-3 py-1.5 text-xs font-bold rounded-lg bg-slate-100 text-slate-700 hover:bg-slate-200 transition-all">Personalizado</button>
        </div>
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-3">
        <!-- Fecha Desde -->
        <div>
          <label class="block text-[11px] font-bold text-slate-600 mb-1">Fecha Desde</label>
          <input type="date" id="filter-date-from" class="w-full px-3 py-2 text-xs border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:outline-none">
        </div>

        <!-- Fecha Hasta -->
        <div>
          <label class="block text-[11px] font-bold text-slate-600 mb-1">Fecha Hasta</label>
          <input type="date" id="filter-date-to" class="w-full px-3 py-2 text-xs border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:outline-none">
        </div>

        <!-- Cuenta MeLi -->
        <div>
          <label class="block text-[11px] font-bold text-slate-600 mb-1">Cuenta Mercado Libre</label>
          <select id="filter-account" class="w-full px-3 py-2 text-xs border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:outline-none">
            <option value="">Todas las Cuentas</option>
          </select>
        </div>

        <!-- Categoría -->
        <div>
          <label class="block text-[11px] font-bold text-slate-600 mb-1">Categoría</label>
          <select id="filter-category" class="w-full px-3 py-2 text-xs border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:outline-none">
            <option value="">Todas las Categorías</option>
          </select>
        </div>

        <!-- SKU o Producto -->
        <div>
          <label class="block text-[11px] font-bold text-slate-600 mb-1">SKU / Producto</label>
          <input type="text" id="filter-sku" placeholder="Buscar por SKU..." class="w-full px-3 py-2 text-xs border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:outline-none">
        </div>

        <!-- Estado del Pedido -->
        <div>
          <label class="block text-[11px] font-bold text-slate-600 mb-1">Estado de Venta</label>
          <select id="filter-status" class="w-full px-3 py-2 text-xs border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:outline-none">
            <option value="">Todos los Estados</option>
            <option value="paid">Pagado</option>
            <option value="confirmed">Confirmado</option>
            <option value="delivered">Entregado</option>
            <option value="shipped">En Camino</option>
          </select>
        </div>
      </div>

      <!-- Barra Inferior de Filtro: Comparativa y Botón de Aplicar -->
      <div class="flex flex-wrap items-center justify-between gap-3 pt-2">
        <div class="flex items-center space-x-4">
          <label class="flex items-center space-x-2 text-xs font-semibold text-slate-700 cursor-pointer">
            <input type="checkbox" id="filter-compare" checked class="w-4 h-4 text-blue-600 rounded focus:ring-blue-500">
            <span>Comparar con periodo anterior</span>
          </label>
          <select id="filter-compare-to" class="px-2.5 py-1 text-xs border border-slate-200 rounded-lg text-slate-600 bg-slate-50">
            <option value="previous_period">Periodo inmediatamente anterior</option>
            <option value="previous_year">Mismo periodo del año anterior</option>
          </select>
        </div>

        <button id="btn-apply-filters" class="px-5 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-all shadow flex items-center space-x-2">
          ${icons.check ? icons.check("w-3.5 h-3.5") : ""}
          <span>Aplicar Filtros</span>
        </button>
      </div>
    </div>

    <!-- SECCIÓN 1: LOS 15 INDICADORES EJECUTIVOS (KPI CARDS) -->
    <div class="space-y-4">
      <div class="flex items-center justify-between">
        <h3 class="text-sm font-bold uppercase tracking-wider text-slate-500 flex items-center gap-2">
          <span>Resumen de Indicadores Clave (KPIs)</span>
          <span id="period-badge-indicator" class="text-[11px] normal-case px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 font-medium border border-blue-200">Periodo: Últimos 30 días</span>
        </h3>
        <div class="text-[11px] text-slate-500 flex items-center gap-3">
          <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-emerald-500 inline-block"></span> Confirmado</span>
          <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-amber-500 inline-block"></span> Estimado</span>
        </div>
      </div>

      <!-- Fila 1: Finanzas Principales (6 KPIs) -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3.5">
        <!-- 1. Ventas del Día -->
        <div class="p-4 rounded-2xl bg-white border border-slate-200 shadow-sm transition-all hover:shadow-md">
          <div class="text-[11px] font-bold uppercase text-slate-500 mb-1">Ventas del Día</div>
          <div class="text-xl font-black text-slate-900" id="kpi-today-sales">$ 0.00</div>
          <div class="flex items-center justify-between text-[11px] mt-1.5" id="kpi-today-orders">
            <span class="text-slate-500">0 pedidos hoy</span>
            <span class="font-bold text-slate-400" id="kpi-today-growth">0.0% vs ayer</span>
          </div>
        </div>

        <!-- 2. Ventas del Mes -->
        <div class="p-4 rounded-2xl bg-white border border-slate-200 shadow-sm transition-all hover:shadow-md">
          <div class="text-[11px] font-bold uppercase text-slate-500 mb-1">Ventas del Mes</div>
          <div class="text-xl font-black text-slate-900" id="kpi-month-sales">$ 0.00</div>
          <div class="flex items-center justify-between text-[11px] mt-1.5">
            <span class="text-slate-500" id="kpi-month-orders">0 pedidos</span>
            <span class="font-bold text-slate-400" id="kpi-month-growth">0.0% vs mes ant.</span>
          </div>
        </div>

        <!-- 3. Ingresos (Periodo) -->
        <div class="p-4 rounded-2xl bg-white border border-slate-200 shadow-sm transition-all hover:shadow-md">
          <div class="text-[11px] font-bold uppercase text-slate-500 mb-1">Ingresos Periodo</div>
          <div class="text-xl font-black text-blue-700" id="kpi-revenue-total">$ 0.00</div>
          <div class="text-[10px] text-slate-500 mt-1 flex justify-between">
            <span>Conf: <b id="kpi-rev-conf" class="text-emerald-700">$0</b></span>
            <span>Est: <b id="kpi-rev-est" class="text-amber-700">$0</b></span>
          </div>
          <div class="text-[11px] font-bold text-slate-500 mt-1" id="kpi-revenue-growth">0.0% vs previo</div>
        </div>

        <!-- 4. Ganancias (Utilidad Neta) -->
        <div class="p-4 rounded-2xl bg-white border border-slate-200 shadow-sm transition-all hover:shadow-md">
          <div class="text-[11px] font-bold uppercase text-slate-500 mb-1">Ganancias Netas</div>
          <div class="text-xl font-black text-emerald-600" id="kpi-profit-total">$ 0.00</div>
          <div class="text-[10px] text-slate-500 mt-1 flex justify-between">
            <span>Conf: <b id="kpi-prof-conf" class="text-emerald-700">$0</b></span>
            <span>Est: <b id="kpi-prof-est" class="text-amber-700">$0</b></span>
          </div>
          <div class="text-[11px] font-bold text-slate-500 mt-1" id="kpi-profit-growth">0.0% vs previo</div>
        </div>

        <!-- 5. Margen Neto % -->
        <div class="p-4 rounded-2xl bg-white border border-slate-200 shadow-sm transition-all hover:shadow-md">
          <div class="text-[11px] font-bold uppercase text-slate-500 mb-1">Margen Neto %</div>
          <div class="text-xl font-black text-purple-700" id="kpi-margin-total">0.0%</div>
          <div class="text-[10px] text-slate-500 mt-1 flex justify-between">
            <span>Conf: <b id="kpi-margin-conf">0%</b></span>
            <span>Est: <b id="kpi-margin-est">0%</b></span>
          </div>
          <div class="text-[11px] font-bold text-slate-500 mt-1" id="kpi-margin-growth">0.0 pp delta</div>
        </div>

        <!-- 6. Comisiones MeLi & SAT -->
        <div class="p-4 rounded-2xl bg-white border border-slate-200 shadow-sm transition-all hover:shadow-md">
          <div class="text-[11px] font-bold uppercase text-slate-500 mb-1">Comisiones & Deducc.</div>
          <div class="text-xl font-black text-rose-600" id="kpi-commissions-total">$ 0.00</div>
          <div class="text-[10px] text-slate-500 mt-1 flex justify-between">
            <span>MeLi: <b id="kpi-comm-fee">$0</b></span>
            <span>SAT: <b id="kpi-comm-sat">$0</b></span>
          </div>
          <div class="text-[10px] text-slate-400 mt-1" id="kpi-comm-ship">Flete: $0.00</div>
        </div>
      </div>

      <!-- Fila 2: Operaciones, Inventario y Logística (9 KPIs) -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3.5">
        <!-- 7. Pedidos Pendientes -->
        <div class="p-4 rounded-2xl bg-white border border-slate-200 shadow-sm">
          <div class="text-[11px] font-bold uppercase text-slate-500 mb-1">Pedidos Pendientes</div>
          <div class="text-xl font-black text-amber-600" id="kpi-pending-orders">0</div>
          <div class="text-[11px] text-slate-500 mt-1" id="kpi-pending-amount">$ 0.00 acumulado</div>
        </div>

        <!-- 8. Productos Vendidos -->
        <div class="p-4 rounded-2xl bg-white border border-slate-200 shadow-sm">
          <div class="text-[11px] font-bold uppercase text-slate-500 mb-1">Productos Vendidos</div>
          <div class="text-xl font-black text-slate-900" id="kpi-sold-units">0 uds</div>
          <div class="text-[11px] font-bold text-slate-500 mt-1" id="kpi-sold-growth">0.0% vs previo</div>
        </div>

        <!-- 9. Stock en Almacenes -->
        <div class="p-4 rounded-2xl bg-white border border-slate-200 shadow-sm">
          <div class="text-[11px] font-bold uppercase text-slate-500 mb-1">Stock Físico / Disp.</div>
          <div class="text-xl font-black text-slate-900">
            <span id="kpi-stock-physical">0</span> / <span id="kpi-stock-available" class="text-blue-600">0</span>
          </div>
          <div class="text-[11px] text-slate-500 mt-1" id="kpi-stock-value">Valuación COGS: $0.00</div>
        </div>

        <!-- 10. Agotados -->
        <div class="p-4 rounded-2xl bg-white border border-slate-200 shadow-sm">
          <div class="text-[11px] font-bold uppercase text-slate-500 mb-1">SKUs Agotados</div>
          <div class="text-xl font-black text-rose-600" id="kpi-out-of-stock">0</div>
          <div class="text-[11px] text-slate-400 mt-1">Disp. en almacén = 0</div>
        </div>

        <!-- 11. Baja Rotación -->
        <div class="p-4 rounded-2xl bg-white border border-slate-200 shadow-sm">
          <div class="text-[11px] font-bold uppercase text-slate-500 mb-1">Baja Rotación</div>
          <div class="text-xl font-black text-amber-600" id="kpi-low-rotation">0</div>
          <div class="text-[11px] text-slate-400 mt-1">Stock con 0 vtas (30d)</div>
        </div>

        <!-- 14 & 15. Promos y Envíos Pendientes -->
        <div class="p-4 rounded-2xl bg-white border border-slate-200 shadow-sm">
          <div class="text-[11px] font-bold uppercase text-slate-500 mb-1">Promociones & Envíos</div>
          <div class="text-base font-bold text-slate-900 flex justify-between items-center mt-1">
            <span>Promos: <b id="kpi-promos-active" class="text-emerald-600 font-black">0</b></span>
            <span>Envíos: <b id="kpi-shipments-pending" class="text-blue-600 font-black">0</b></span>
          </div>
          <div class="text-[10px] text-slate-400 mt-1">Activas / Por despachar</div>
        </div>
      </div>
    </div>

    <!-- SECCIÓN 2: PESTAÑAS DE LAS 9 GRÁFICAS EJECUTIVAS -->
    <div class="p-6 bg-white rounded-3xl border border-slate-200 shadow-sm space-y-6">
      <div class="flex flex-col sm:flex-row sm:items-center justify-between border-b border-slate-100 pb-4 gap-3">
        <div>
          <h3 class="text-lg font-black text-slate-900">Analítica Gráfica Ejecutiva</h3>
          <p class="text-xs text-slate-500">Visualización interactiva de ventas, rentabilidad, rotación de inventario y estructura de costos.</p>
        </div>

        <!-- Tabs de Navegación Gráfica -->
        <div class="flex flex-wrap gap-1.5 p-1 bg-slate-100 rounded-xl" id="charts-tab-container">
          <button data-tab="tab-sales" class="chart-tab px-3 py-1.5 text-xs font-bold rounded-lg bg-white text-slate-900 shadow-sm transition-all active-tab">Ventas y Tendencias</button>
          <button data-tab="tab-profit" class="chart-tab px-3 py-1.5 text-xs font-bold rounded-lg text-slate-600 hover:text-slate-900 transition-all">Rentabilidad y Gastos</button>
          <button data-tab="tab-inventory" class="chart-tab px-3 py-1.5 text-xs font-bold rounded-lg text-slate-600 hover:text-slate-900 transition-all">Inventario y Rotación</button>
          <button data-tab="tab-products" class="chart-tab px-3 py-1.5 text-xs font-bold rounded-lg text-slate-600 hover:text-slate-900 transition-all">Rankings de Productos</button>
        </div>
      </div>

      <!-- TAB 1: VENTAS Y TENDENCIAS (Gráficas 1 y 2) -->
      <div id="tab-sales" class="chart-tab-content space-y-6">
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <!-- Gráfica 1: Ventas Diarias con Comparativa de Periodo -->
          <div class="p-4 rounded-2xl bg-slate-50 border border-slate-100">
            <div class="flex items-center justify-between mb-3">
              <div>
                <h4 class="text-sm font-bold text-slate-800">1. Ventas Diarias (Tendencia y Comparativa)</h4>
                <p class="text-[11px] text-slate-500">Ingresos brutos por fecha vs periodo de comparación</p>
              </div>
              <span class="badge badge-meli text-[10px]">Día a Día</span>
            </div>
            <div class="h-64 sm:h-72">
              <canvas id="chart-daily-sales"></canvas>
            </div>
          </div>

          <!-- Gráfica 2: Ventas Mensuales (Año actual vs Año anterior) -->
          <div class="p-4 rounded-2xl bg-slate-50 border border-slate-100">
            <div class="flex items-center justify-between mb-3">
              <div>
                <h4 class="text-sm font-bold text-slate-800">2. Ventas Mensuales (Año en Curso vs Año Previo)</h4>
                <p class="text-[11px] text-slate-500">Facturación mensual consolidada (Enero a Diciembre)</p>
              </div>
              <span class="badge badge-info text-[10px]">Anual</span>
            </div>
            <div class="h-64 sm:h-72">
              <canvas id="chart-monthly-sales"></canvas>
            </div>
          </div>
        </div>
      </div>

      <!-- TAB 2: RENTABILIDAD Y GASTOS (Gráficas 3, 7 y 8) -->
      <div id="tab-profit" class="chart-tab-content hidden space-y-6">
        <!-- Gráfica 3: Rentabilidad Multidimensional -->
        <div class="p-4 rounded-2xl bg-slate-50 border border-slate-100">
          <div class="flex items-center justify-between mb-3">
            <div>
              <h4 class="text-sm font-bold text-slate-800">3. Curva de Rentabilidad Financiera</h4>
              <p class="text-[11px] text-slate-500">Ingreso Bruto vs Costo COGS vs Comisiones MeLi vs Ganancia Neta</p>
            </div>
            <span class="badge badge-success text-[10px]">Salud Financiera</span>
          </div>
          <div class="h-72">
            <canvas id="chart-profitability"></canvas>
          </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <!-- Gráfica 7: Comisiones MeLi & Retenciones SAT -->
          <div class="p-4 rounded-2xl bg-slate-50 border border-slate-100">
            <div class="flex items-center justify-between mb-3">
              <div>
                <h4 class="text-sm font-bold text-slate-800">7. Desglose de Comisiones y Retenciones</h4>
                <p class="text-[11px] text-slate-500">Tarifas MeLi, Envíos vendedor y retenciones SAT</p>
              </div>
            </div>
            <div class="h-64 flex justify-center">
              <canvas id="chart-commissions"></canvas>
            </div>
          </div>

          <!-- Gráfica 8: Estructura de Gastos Totales -->
          <div class="p-4 rounded-2xl bg-slate-50 border border-slate-100">
            <div class="flex items-center justify-between mb-3">
              <div>
                <h4 class="text-sm font-bold text-slate-800">8. Estructura de Egresos Operativos</h4>
                <p class="text-[11px] text-slate-500">COGS, Comisiones, Logística y Gastos Externos</p>
              </div>
            </div>
            <div class="h-64 flex justify-center">
              <canvas id="chart-expenses"></canvas>
            </div>
          </div>
        </div>
      </div>

      <!-- TAB 3: INVENTARIO Y ROTACIÓN (Gráficas 4 y 9) -->
      <div id="tab-inventory" class="chart-tab-content hidden space-y-6">
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <!-- Gráfica 4: Evolución de Inventario -->
          <div class="p-4 rounded-2xl bg-slate-50 border border-slate-100">
            <div class="flex items-center justify-between mb-3">
              <div>
                <h4 class="text-sm font-bold text-slate-800">4. Evolución de Inventario (Entradas vs Salidas)</h4>
                <p class="text-[11px] text-slate-500">Flujo de mercancía en unidades y balance acumulado</p>
              </div>
              <span class="badge badge-meli text-[10px]">Kardex</span>
            </div>
            <div class="h-64 sm:h-72">
              <canvas id="chart-inventory-evolution"></canvas>
            </div>
          </div>

          <!-- Gráfica 9: Rotación de Inventario por Categoría -->
          <div class="p-4 rounded-2xl bg-slate-50 border border-slate-100">
            <div class="flex items-center justify-between mb-3">
              <div>
                <h4 class="text-sm font-bold text-slate-800">9. Ratio de Rotación por Categoría</h4>
                <p class="text-[11px] text-slate-500">Velocidad de rotación (Ventas / Stock)</p>
              </div>
              <span class="badge badge-warning text-[10px]">Velocidad</span>
            </div>
            <div class="h-64 sm:h-72">
              <canvas id="chart-rotation"></canvas>
            </div>
          </div>
        </div>
      </div>

      <!-- TAB 4: RANKINGS DE PRODUCTOS (Gráficas 5 y 6 + Tablas Top) -->
      <div id="tab-products" class="chart-tab-content hidden space-y-6">
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <!-- Gráfica 5: Top 10 Productos Más Vendidos -->
          <div class="p-4 rounded-2xl bg-slate-50 border border-slate-100">
            <div class="flex items-center justify-between mb-3">
              <div>
                <h4 class="text-sm font-bold text-slate-800">5. Top 10 Productos Más Vendidos</h4>
                <p class="text-[11px] text-slate-500">Por volumen de unidades vendidas en el periodo</p>
              </div>
              <span class="badge badge-success text-[10px]">Bestsellers</span>
            </div>
            <div class="h-72">
              <canvas id="chart-top-selling"></canvas>
            </div>
          </div>

          <!-- Gráfica 6: Top 10 Productos Menos Vendidos -->
          <div class="p-4 rounded-2xl bg-slate-50 border border-slate-100">
            <div class="flex items-center justify-between mb-3">
              <div>
                <h4 class="text-sm font-bold text-slate-800">6. Productos Menos Vendidos / Sin Movimiento</h4>
                <p class="text-[11px] text-slate-500">Identificación de inventario estancado o nula rotación</p>
              </div>
              <span class="badge badge-danger text-[10px]">Alerta Estancado</span>
            </div>
            <div class="h-72">
              <canvas id="chart-least-selling"></canvas>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- SECCIÓN 3: TABLAS DE PRODUCTOS MÁS RENTABLES Y MÁS VENDIDOS (KPIs 12 & 13) -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- 12. Top Productos Más Rentables -->
      <div class="p-5 bg-white rounded-2xl border border-slate-200 shadow-sm">
        <div class="flex items-center justify-between mb-3">
          <h4 class="text-sm font-bold text-slate-900 flex items-center gap-2">
            <span class="p-1.5 rounded-lg bg-emerald-50 text-emerald-600">${icons.finances("w-4 h-4")}</span>
            <span>12. Top 5 Productos Más Rentables</span>
          </h4>
          <span class="text-xs text-slate-500">Por Ganancia Neta</span>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-xs text-left">
            <thead class="text-[11px] font-bold text-slate-400 border-b border-slate-100 uppercase">
              <tr>
                <th class="py-2.5 px-3">SKU</th>
                <th class="py-2.5 px-3">Producto</th>
                <th class="py-2.5 px-3 text-right">Uds</th>
                <th class="py-2.5 px-3 text-right">Utilidad Neta</th>
                <th class="py-2.5 px-3 text-right">Margen</th>
              </tr>
            </thead>
            <tbody id="top-profitable-tbody" class="divide-y divide-slate-100 text-slate-700">
              <tr><td colspan="5" class="py-4 text-center text-slate-400">Cargando datos...</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 13. Top Productos Más Vendidos -->
      <div class="p-5 bg-white rounded-2xl border border-slate-200 shadow-sm">
        <div class="flex items-center justify-between mb-3">
          <h4 class="text-sm font-bold text-slate-900 flex items-center gap-2">
            <span class="p-1.5 rounded-lg bg-blue-50 text-blue-600">${icons.orders("w-4 h-4")}</span>
            <span>13. Top 5 Productos Más Vendidos</span>
          </h4>
          <span class="text-xs text-slate-500">Por Volumen de Piezas</span>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-xs text-left">
            <thead class="text-[11px] font-bold text-slate-400 border-b border-slate-100 uppercase">
              <tr>
                <th class="py-2.5 px-3">SKU</th>
                <th class="py-2.5 px-3">Producto</th>
                <th class="py-2.5 px-3 text-right">Uds</th>
                <th class="py-2.5 px-3 text-right">Ingreso Bruto</th>
                <th class="py-2.5 px-3 text-right">Ganancia</th>
              </tr>
            </thead>
            <tbody id="top-selling-tbody" class="divide-y divide-slate-100 text-slate-700">
              <tr><td colspan="5" class="py-4 text-center text-slate-400">Cargando datos...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  // Inicializar eventos de filtros, tabs y carga de datos
  setupDashboardEvents(container);
  loadDashboardData(container);

  return container;
}

// ===========================================================================
// CONTROLADOR DE EVENTOS Y FILTROS
// ===========================================================================

function setupDashboardEvents(root) {
  // Manejador de Tabs de Gráficas
  const tabButtons = root.querySelectorAll(".chart-tab");
  const tabContents = root.querySelectorAll(".chart-tab-content");

  tabButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetTab = btn.getAttribute("data-tab");

      tabButtons.forEach(b => {
        b.classList.remove("bg-white", "text-slate-900", "shadow-sm", "active-tab");
        b.classList.add("text-slate-600");
      });
      btn.classList.add("bg-white", "text-slate-900", "shadow-sm", "active-tab");
      btn.classList.remove("text-slate-600");

      tabContents.forEach(c => {
        if (c.id === targetTab) {
          c.classList.remove("hidden");
        } else {
          c.classList.add("hidden");
        }
      });
    });
  });

  // Manejador de Presets de Fecha
  const presetButtons = root.querySelectorAll(".btn-preset");
  presetButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      presetButtons.forEach(b => {
        b.classList.remove("bg-blue-600", "text-white", "shadow-sm", "active-preset");
        b.classList.add("bg-slate-100", "text-slate-700");
      });
      btn.classList.add("bg-blue-600", "text-white", "shadow-sm", "active-preset");
      btn.classList.remove("bg-slate-100", "text-slate-700");

      const preset = btn.getAttribute("data-preset");
      if (preset !== "custom") {
        root.querySelector("#filter-date-from").value = "";
        root.querySelector("#filter-date-to").value = "";
      }
      loadDashboardData(root);
    });
  });

  // Botón Aplicar Filtros
  const btnApply = root.querySelector("#btn-apply-filters");
  if (btnApply) {
    btnApply.addEventListener("click", () => loadDashboardData(root));
  }

  // Botón Actualizar
  const btnRefresh = root.querySelector("#btn-refresh-dashboard");
  if (btnRefresh) {
    btnRefresh.addEventListener("click", () => {
      showToast("Actualizando datos del dashboard...", "info");
      loadDashboardData(root);
    });
  }
}

// ===========================================================================
// CARGA ASÍNCRONA DE DATOS Y RENDERIZADO
// ===========================================================================

async function loadDashboardData(root) {
  try {
    // 1. Cargar opciones de filtros si no se han cargado
    if (!currentFilterOptions) {
      try {
        currentFilterOptions = await api.get("/dashboard/filters");
        populateFilterDropdowns(root, currentFilterOptions);
      } catch (e) {
        console.warn("No se pudieron cargar opciones de filtro:", e);
      }
    }

    // 2. Construir parámetros de consulta
    const activePresetBtn = root.querySelector(".btn-preset.active-preset");
    const preset = activePresetBtn ? activePresetBtn.getAttribute("data-preset") : "30d";

    const dateFrom = root.querySelector("#filter-date-from").value || null;
    const dateTo = root.querySelector("#filter-date-to").value || null;
    const meliAccountId = root.querySelector("#filter-account").value || null;
    const category = root.querySelector("#filter-category").value || null;
    const sku = root.querySelector("#filter-sku").value.trim() || null;
    const status = root.querySelector("#filter-status").value || null;
    const compare = root.querySelector("#filter-compare").checked;
    const compareTo = root.querySelector("#filter-compare-to").value;

    const queryParams = {
      preset: (dateFrom || dateTo) ? "custom" : preset,
      compare: compare,
      compare_to: compareTo,
    };
    if (dateFrom) queryParams.date_from = dateFrom;
    if (dateTo) queryParams.date_to = dateTo;
    if (meliAccountId) queryParams.meli_account_id = meliAccountId;
    if (category) queryParams.category = category;
    if (sku) queryParams.sku = sku;
    if (status) queryParams.status = status;

    // 3. Consultar endpoint ejecutivo
    const data = await api.get("/dashboard/executive", queryParams);

    // 4. Actualizar Badge de Periodo
    const pBadge = root.querySelector("#period-badge-indicator");
    if (pBadge) {
      const pStart = new Date(data.period_start).toLocaleDateString('es-MX', { month: 'short', day: 'numeric' });
      const pEnd = new Date(data.period_end).toLocaleDateString('es-MX', { month: 'short', day: 'numeric', year: 'numeric' });
      pBadge.textContent = `Periodo: ${pStart} - ${pEnd}`;
    }

    // 5. Renderizar los 15 KPIs
    renderKPIs(root, data.kpis);

    // 6. Renderizar las 9 Gráficas con Chart.js
    renderAllCharts(root, data.charts);

    // 7. Renderizar Tablas Top
    renderTopTables(root, data.kpis);

  } catch (err) {
    console.error("Error al cargar dashboard ejecutivo:", err);
    showToast("Error al cargar los datos del dashboard: " + (err.message || err), "error");
  }
}

function populateFilterDropdowns(root, options) {
  const accSelect = root.querySelector("#filter-account");
  if (accSelect && options.meli_accounts) {
    accSelect.innerHTML = `<option value="">Todas las Cuentas (${options.meli_accounts.length})</option>` +
      options.meli_accounts.map(a => `<option value="${a.id}">${a.nickname}</option>`).join("");
  }

  const catSelect = root.querySelector("#filter-category");
  if (catSelect && options.categories) {
    catSelect.innerHTML = `<option value="">Todas las Categorías (${options.categories.length})</option>` +
      options.categories.map(c => `<option value="${c}">${c}</option>`).join("");
  }
}

// ===========================================================================
// RENDERIZADO DE LOS 15 KPIS
// ===========================================================================

function renderKPIs(root, kpis) {
  const fmtMoney = v => `$ ${Number(v || 0).toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  const fmtGrowth = g => {
    const num = Number(g || 0);
    const isPos = num >= 0;
    const sign = isPos ? "▲ +" : "▼ ";
    const color = isPos ? "text-emerald-600 font-bold" : "text-rose-600 font-bold";
    return `<span class="${color}">${sign}${num.toFixed(1)}% vs previo</span>`;
  };

  // 1. Ventas del Día
  root.querySelector("#kpi-today-sales").textContent = fmtMoney(kpis.today_sales.gross_amount);
  root.querySelector("#kpi-today-orders").innerHTML = `
    <span class="text-slate-500">${kpis.today_sales.orders_count} pedidos</span>
    ${fmtGrowth(kpis.today_sales.growth_pct)}
  `;

  // 2. Ventas del Mes
  root.querySelector("#kpi-month-sales").textContent = fmtMoney(kpis.month_sales.gross_amount);
  root.querySelector("#kpi-month-orders").textContent = `${kpis.month_sales.orders_count} pedidos`;
  root.querySelector("#kpi-month-growth").innerHTML = fmtGrowth(kpis.month_sales.growth_pct);

  // 3. Ingresos Periodo (Diferenciado)
  root.querySelector("#kpi-revenue-total").textContent = fmtMoney(kpis.revenue.total);
  root.querySelector("#kpi-rev-conf").textContent = fmtMoney(kpis.revenue.confirmed);
  root.querySelector("#kpi-rev-est").textContent = fmtMoney(kpis.revenue.estimated);
  root.querySelector("#kpi-revenue-growth").innerHTML = fmtGrowth(kpis.revenue.growth_pct);

  // 4. Ganancias Netas (Diferenciado)
  root.querySelector("#kpi-profit-total").textContent = fmtMoney(kpis.profit.total);
  root.querySelector("#kpi-prof-conf").textContent = fmtMoney(kpis.profit.confirmed);
  root.querySelector("#kpi-prof-est").textContent = fmtMoney(kpis.profit.estimated);
  root.querySelector("#kpi-profit-growth").innerHTML = fmtGrowth(kpis.profit.growth_pct);

  // 5. Margen Neto %
  root.querySelector("#kpi-margin-total").textContent = `${kpis.margin.overall_pct.toFixed(1)}%`;
  root.querySelector("#kpi-margin-conf").textContent = `${kpis.margin.confirmed_pct.toFixed(1)}%`;
  root.querySelector("#kpi-margin-est").textContent = `${kpis.margin.estimated_pct.toFixed(1)}%`;
  const mGrowth = kpis.margin.growth_pct;
  const mColor = mGrowth >= 0 ? "text-emerald-600 font-bold" : "text-rose-600 font-bold";
  root.querySelector("#kpi-margin-growth").innerHTML = `<span class="${mColor}">${mGrowth >= 0 ? '+' : ''}${mGrowth.toFixed(1)} pp vs previo</span>`;

  // 6. Comisiones
  root.querySelector("#kpi-commissions-total").textContent = fmtMoney(kpis.commissions.total);
  root.querySelector("#kpi-comm-fee").textContent = fmtMoney(kpis.commissions.marketplace_fees);
  root.querySelector("#kpi-comm-sat").textContent = fmtMoney(kpis.commissions.taxes_withheld);
  root.querySelector("#kpi-comm-ship").textContent = `Flete Vendedor: ${fmtMoney(kpis.commissions.shipping_costs)}`;

  // 7. Pedidos Pendientes
  root.querySelector("#kpi-pending-orders").textContent = String(kpis.pending_orders_count);
  root.querySelector("#kpi-pending-amount").textContent = `${fmtMoney(kpis.pending_orders_amount)} acumulado`;

  // 8. Productos Vendidos
  root.querySelector("#kpi-sold-units").textContent = `${kpis.products_sold_units} uds`;
  root.querySelector("#kpi-sold-growth").innerHTML = fmtGrowth(kpis.products_sold_growth_pct);

  // 9. Stock en Almacenes
  root.querySelector("#kpi-stock-physical").textContent = String(kpis.stock.total_physical);
  root.querySelector("#kpi-stock-available").textContent = String(kpis.stock.total_available);
  root.querySelector("#kpi-stock-value").textContent = `Valuación COGS: ${fmtMoney(kpis.stock.inventory_value_cogs)}`;

  // 10. Agotados
  root.querySelector("#kpi-out-of-stock").textContent = String(kpis.out_of_stock_count);

  // 11. Baja Rotación
  root.querySelector("#kpi-low-rotation").textContent = String(kpis.low_rotation_count);

  // 14 & 15. Promos y Envíos Pendientes
  root.querySelector("#kpi-promos-active").textContent = String(kpis.active_promotions_count);
  root.querySelector("#kpi-shipments-pending").textContent = String(kpis.pending_shipments_count);
}

// ===========================================================================
// RENDERIZADO DE LAS 9 GRÁFICAS CON CHART.JS
// ===========================================================================

function renderAllCharts(root, charts) {
  if (typeof Chart === "undefined") {
    console.warn("Chart.js no está disponible en la ventana global.");
    return;
  }

  // Destruir instancias previas para evitar memory leaks o overlapping
  Object.values(activeCharts).forEach(c => {
    if (c && typeof c.destroy === "function") c.destroy();
  });
  activeCharts = {};

  // 1. Gráfica de Ventas Diarias
  const canvas1 = root.querySelector("#chart-daily-sales");
  if (canvas1) {
    activeCharts.daily = new Chart(canvas1, {
      type: "line",
      data: {
        labels: charts.daily_sales.labels,
        datasets: [
          {
            label: "Periodo Actual ($ MXN)",
            data: charts.daily_sales.current_period_gross,
            borderColor: "#2563EB",
            backgroundColor: "rgba(37, 99, 235, 0.12)",
            fill: true,
            tension: 0.3,
            borderWidth: 2.5,
          },
          {
            label: "Periodo Previo ($ MXN)",
            data: charts.daily_sales.previous_period_gross,
            borderColor: "#94A3B8",
            borderDash: [5, 5],
            fill: false,
            tension: 0.3,
            borderWidth: 1.5,
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: "top", labels: { boxWidth: 12, font: { size: 10 } } } },
        scales: {
          x: { grid: { display: false }, ticks: { font: { size: 10 } } },
          y: { grid: { color: "#F1F5F9" }, ticks: { callback: v => `$ ${v}` } }
        }
      }
    });
  }

  // 2. Gráfica de Ventas Mensuales
  const canvas2 = root.querySelector("#chart-monthly-sales");
  if (canvas2) {
    activeCharts.monthly = new Chart(canvas2, {
      type: "bar",
      data: {
        labels: charts.monthly_sales.labels,
        datasets: [
          {
            label: "Año en Curso ($ MXN)",
            data: charts.monthly_sales.current_year_gross,
            backgroundColor: "#3B82F6",
            borderRadius: 6,
          },
          {
            label: "Año Anterior ($ MXN)",
            data: charts.monthly_sales.previous_year_gross,
            backgroundColor: "#CBD5E1",
            borderRadius: 6,
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: "top", labels: { boxWidth: 12, font: { size: 10 } } } },
        scales: {
          x: { grid: { display: false } },
          y: { grid: { color: "#F1F5F9" }, ticks: { callback: v => `$ ${v}` } }
        }
      }
    });
  }

  // 3. Gráfica de Rentabilidad
  const canvas3 = root.querySelector("#chart-profitability");
  if (canvas3) {
    activeCharts.profitability = new Chart(canvas3, {
      type: "line",
      data: {
        labels: charts.profitability.labels,
        datasets: [
          {
            label: "Ingreso Bruto",
            data: charts.profitability.revenue,
            borderColor: "#2563EB",
            tension: 0.25,
            borderWidth: 2,
          },
          {
            label: "Costo COGS",
            data: charts.profitability.cogs,
            borderColor: "#F59E0B",
            tension: 0.25,
            borderWidth: 1.5,
          },
          {
            label: "Comisiones MeLi",
            data: charts.profitability.commissions,
            borderColor: "#EF4444",
            tension: 0.25,
            borderWidth: 1.5,
          },
          {
            label: "Ganancia Neta",
            data: charts.profitability.net_profit,
            borderColor: "#10B981",
            backgroundColor: "rgba(16, 185, 129, 0.15)",
            fill: true,
            tension: 0.25,
            borderWidth: 2.5,
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: "top", labels: { boxWidth: 12, font: { size: 11 } } } },
        scales: {
          x: { grid: { display: false } },
          y: { grid: { color: "#F1F5F9" }, ticks: { callback: v => `$ ${v}` } }
        }
      }
    });
  }

  // 4. Gráfica de Evolución de Inventario
  const canvas4 = root.querySelector("#chart-inventory-evolution");
  if (canvas4) {
    activeCharts.inventory = new Chart(canvas4, {
      type: "bar",
      data: {
        labels: charts.inventory_evolution.labels,
        datasets: [
          {
            label: "Entradas (Inbound)",
            data: charts.inventory_evolution.inbound_units,
            backgroundColor: "#10B981",
            borderRadius: 4,
          },
          {
            label: "Salidas (Outbound)",
            data: charts.inventory_evolution.outbound_units,
            backgroundColor: "#EF4444",
            borderRadius: 4,
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: "top", labels: { boxWidth: 12, font: { size: 10 } } } },
        scales: {
          x: { grid: { display: false } },
          y: { grid: { color: "#F1F5F9" } }
        }
      }
    });
  }

  // 5. Top 10 Productos Más Vendidos
  const canvas5 = root.querySelector("#chart-top-selling");
  if (canvas5) {
    activeCharts.topSelling = new Chart(canvas5, {
      type: "bar",
      data: {
        labels: charts.top_selling.labels,
        datasets: [
          {
            label: "Unidades Vendidas",
            data: charts.top_selling.units,
            backgroundColor: "#0284C7",
            borderRadius: 6,
          }
        ]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: "#F1F5F9" } },
          y: { grid: { display: false } }
        }
      }
    });
  }

  // 6. Top 10 Productos Menos Vendidos
  const canvas6 = root.querySelector("#chart-least-selling");
  if (canvas6) {
    activeCharts.leastSelling = new Chart(canvas6, {
      type: "bar",
      data: {
        labels: charts.least_selling.labels,
        datasets: [
          {
            label: "Unidades Vendidas",
            data: charts.least_selling.units,
            backgroundColor: "#F43F5E",
            borderRadius: 6,
          }
        ]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: "#F1F5F9" } },
          y: { grid: { display: false } }
        }
      }
    });
  }

  // 7. Gráfica de Comisiones MeLi & Retenciones
  const canvas7 = root.querySelector("#chart-commissions");
  if (canvas7) {
    activeCharts.commissions = new Chart(canvas7, {
      type: "doughnut",
      data: {
        labels: charts.commissions.labels,
        datasets: [
          {
            data: charts.commissions.values,
            backgroundColor: ["#E11D48", "#F97316", "#8B5CF6", "#6366F1"],
            borderWidth: 2,
            borderColor: "#FFFFFF",
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: "right", labels: { boxWidth: 10, font: { size: 10 } } } }
      }
    });
  }

  // 8. Gráfica de Gastos Totales
  const canvas8 = root.querySelector("#chart-expenses");
  if (canvas8) {
    activeCharts.expenses = new Chart(canvas8, {
      type: "doughnut",
      data: {
        labels: charts.expenses.labels,
        datasets: [
          {
            data: charts.expenses.values,
            backgroundColor: ["#F59E0B", "#EF4444", "#3B82F6", "#64748B"],
            borderWidth: 2,
            borderColor: "#FFFFFF",
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: "right", labels: { boxWidth: 10, font: { size: 10 } } } }
      }
    });
  }

  // 9. Gráfica de Rotación de Inventario por Categoría
  const canvas9 = root.querySelector("#chart-rotation");
  if (canvas9) {
    activeCharts.rotation = new Chart(canvas9, {
      type: "bar",
      data: {
        labels: charts.rotation.categories,
        datasets: [
          {
            label: "Ratio de Rotación (Ventas / Stock)",
            data: charts.rotation.turnover_ratio,
            backgroundColor: "#8B5CF6",
            borderRadius: 6,
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: "top", labels: { boxWidth: 12, font: { size: 10 } } } },
        scales: {
          x: { grid: { display: false } },
          y: { grid: { color: "#F1F5F9" }, ticks: { callback: v => `${v}x` } }
        }
      }
    });
  }
}

// ===========================================================================
// RENDERIZADO DE TABLAS TOP
// ===========================================================================

function renderTopTables(root, kpis) {
  const fmtMoney = v => `$ ${Number(v || 0).toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  // Tabla Top Rentables
  const profTbody = root.querySelector("#top-profitable-tbody");
  if (profTbody) {
    if (!kpis.top_profitable_products || kpis.top_profitable_products.length === 0) {
      profTbody.innerHTML = `<tr><td colspan="5" class="py-4 text-center text-slate-400">Sin datos en el periodo</td></tr>`;
    } else {
      profTbody.innerHTML = kpis.top_profitable_products.map(p => `
        <tr class="hover:bg-slate-50 transition-colors">
          <td class="py-2.5 px-3 font-mono font-bold text-slate-900">${p.sku}</td>
          <td class="py-2.5 px-3 max-w-[180px] truncate text-slate-700 font-medium" title="${p.name}">${p.name}</td>
          <td class="py-2.5 px-3 text-right font-bold text-slate-900">${p.units_sold}</td>
          <td class="py-2.5 px-3 text-right font-black text-emerald-600">${fmtMoney(p.profit)}</td>
          <td class="py-2.5 px-3 text-right font-bold text-purple-700">${p.margin_pct.toFixed(1)}%</td>
        </tr>
      `).join("");
    }
  }

  // Tabla Top Vendidos
  const sellTbody = root.querySelector("#top-selling-tbody");
  if (sellTbody) {
    if (!kpis.top_selling_products || kpis.top_selling_products.length === 0) {
      sellTbody.innerHTML = `<tr><td colspan="5" class="py-4 text-center text-slate-400">Sin datos en el periodo</td></tr>`;
    } else {
      sellTbody.innerHTML = kpis.top_selling_products.map(p => `
        <tr class="hover:bg-slate-50 transition-colors">
          <td class="py-2.5 px-3 font-mono font-bold text-slate-900">${p.sku}</td>
          <td class="py-2.5 px-3 max-w-[180px] truncate text-slate-700 font-medium" title="${p.name}">${p.name}</td>
          <td class="py-2.5 px-3 text-right font-black text-blue-700">${p.units_sold}</td>
          <td class="py-2.5 px-3 text-right font-bold text-slate-900">${fmtMoney(p.revenue)}</td>
          <td class="py-2.5 px-3 text-right font-bold text-emerald-600">${fmtMoney(p.profit)}</td>
        </tr>
      `).join("");
    }
  }
}


// Adaptador para app.js: la app espera renderDashboard(contenedor) y descarta el
// valor de retorno; renderDashboardView() no recibe argumentos y devuelve el elemento.
export function renderDashboard(container) {
  const el = renderDashboardView();
  if (container) container.appendChild(el);
  return el;
}

/**
 * Centro de Ventas del ERP (Mercado Libre México).
 * Administra el ciclo completo de pedidos:
 * - Listado de ventas con comprador, SKU, variantes, comisiones, retenciones y ganancia neta.
 * - Detalle de pedido con desglose SAT y línea de tiempo histórica.
 * - Comparación en tiempo real MeLi vs ERP interno.
 * - Gestión de cancelaciones con liberación de reservas.
 * - Gestión de devoluciones con clasificación de mercancía (buen estado vs dañada/cuarentena).
 * - Reclamos y disputas post-venta.
 * - Reportes comerciales diarios, semanales y mensuales.
 */

import { api } from "../api.js";
import { state } from "../state.js";
import { icons } from "../icons.js";
import { openModal, closeModal } from "../components/modal.js";
import { showToast } from "../components/toast.js";

export function renderOrdersView() {
  const container = document.createElement("div");
  container.className = "space-y-5 animate-fade-in";

  let activeTab = "sales"; // sales, cancelled, claims, reports
  let currentPage = 1;
  let currentStatus = "";
  let currentPaymentStatus = "";
  let currentShipmentStatus = "";
  let searchFilter = "";
  let reportPeriod = "daily"; // daily, weekly, monthly
  let reportDate = new Date().toISOString().split("T")[0];

  function renderSkeleton() {
    return Array.from({ length: 6 }).map(() => `
      <tr class="animate-pulse">
        <td class="py-3.5 px-3"><div class="h-4 bg-slate-200 rounded w-20"></div></td>
        <td class="py-3.5 px-3"><div class="h-4 bg-slate-200 rounded w-28"></div></td>
        <td class="py-3.5 px-3"><div class="h-4 bg-slate-200 rounded w-24"></div></td>
        <td class="py-3.5 px-3"><div class="h-4 bg-slate-200 rounded w-32"></div></td>
        <td class="py-3.5 px-3"><div class="h-4 bg-slate-200 rounded w-20"></div></td>
        <td class="py-3.5 px-3"><div class="h-4 bg-slate-200 rounded w-16"></div></td>
        <td class="py-3.5 px-3"><div class="h-4 bg-slate-200 rounded w-16"></div></td>
        <td class="py-3.5 px-3"><div class="h-4 bg-slate-200 rounded w-16"></div></td>
        <td class="py-3.5 px-3"><div class="h-4 bg-slate-200 rounded w-16"></div></td>
        <td class="py-3.5 px-3"><div class="h-4 bg-slate-200 rounded w-20"></div></td>
        <td class="py-3.5 px-3 text-right"><div class="h-4 bg-slate-200 rounded w-16 ml-auto"></div></td>
      </tr>
    `).join("");
  }

  container.innerHTML = `
    <!-- Encabezado de Sección y KPIs -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
      <div>
        <h2 class="text-2xl font-black text-slate-900 tracking-tight flex items-center gap-2">
          ${icons.shoppingBag || icons.box} Centro de Ventas & Pedidos MeLi
        </h2>
        <p class="text-xs text-slate-500 mt-0.5">
          Control omnicanal de pedidos, rentabilidad neta SAT, inventario reservado, trazabilidad y reclamos.
        </p>
      </div>

      <div class="flex items-center gap-2">
        <button id="btn-refresh-orders" class="p-2.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 rounded-xl transition-smooth shadow-sm touch-target" title="Recargar">
          ${icons.refresh}
        </button>
      </div>
    </div>

    <!-- Pestañas de Navegación del Centro de Ventas -->
    <div class="flex border-b border-slate-200 gap-1 text-xs font-bold overflow-x-auto">
      <button id="tab-sales" class="tab-btn px-4 py-2.5 border-b-2 border-blue-600 text-blue-600 flex items-center gap-1.5 transition-smooth">
        ${icons.list || icons.tag} Todas las Ventas
      </button>
      <button id="tab-cancelled" class="tab-btn px-4 py-2.5 border-b-2 border-transparent text-slate-500 hover:text-slate-800 flex items-center gap-1.5 transition-smooth">
        ${icons.alert || icons.shield} Cancelaciones & Devoluciones
      </button>
      <button id="tab-claims" class="tab-btn px-4 py-2.5 border-b-2 border-transparent text-slate-500 hover:text-slate-800 flex items-center gap-1.5 transition-smooth">
        ${icons.flag || icons.users} Reclamos Post-Venta
      </button>
      <button id="tab-reports" class="tab-btn px-4 py-2.5 border-b-2 border-transparent text-slate-500 hover:text-slate-800 flex items-center gap-1.5 transition-smooth">
        ${icons.chart || icons.check} Reportes Comerciales
      </button>
    </div>

    <!-- SECCIÓN: VISTA DE VENTAS (TABLAS Y FILTROS) -->
    <div id="section-sales-content" class="space-y-4">
      <!-- Barra de Filtros y Búsqueda -->
      <div class="p-4 bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3">
        <div class="flex-1 max-w-sm relative">
          <span class="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
            ${icons.search}
          </span>
          <input 
            id="orders-search-input" 
            type="text" 
            placeholder="Buscar por ID MeLi, SKU, título o comprador..." 
            class="w-full pl-9 pr-3.5 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:ring-2 focus:ring-blue-600 focus:outline-none transition-smooth"
          />
        </div>

        <div class="flex items-center space-x-2 overflow-x-auto text-xs">
          <select id="orders-status-filter" class="px-3 py-2 font-semibold bg-slate-50 border border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-600">
            <option value="">Estado General</option>
            <option value="paid">Pagado (paid)</option>
            <option value="confirmed">Confirmado (confirmed)</option>
            <option value="shipped">Enviado (shipped)</option>
            <option value="delivered">Entregado (delivered)</option>
            <option value="cancelled">Cancelado (cancelled)</option>
            <option value="returned">Devuelto (returned)</option>
          </select>

          <select id="orders-payment-filter" class="px-3 py-2 font-semibold bg-slate-50 border border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-600">
            <option value="">Estado Pago</option>
            <option value="approved">Aprobado</option>
            <option value="pending">Pendiente</option>
            <option value="refunded">Reembolsado</option>
          </select>

          <select id="orders-shipment-filter" class="px-3 py-2 font-semibold bg-slate-50 border border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-600">
            <option value="">Estado Envío</option>
            <option value="ready_to_ship">Listo para despacho</option>
            <option value="shipped">En camino</option>
            <option value="delivered">Entregado</option>
            <option value="cancelled">Cancelado</option>
          </select>
        </div>
      </div>

      <!-- Tabla Principal de Órdenes -->
      <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="table-container">
          <table class="w-full text-left text-xs border-collapse">
            <thead>
              <tr class="border-b border-slate-200 bg-slate-50/70 text-slate-500 font-bold uppercase tracking-wider text-[10px]">
                <th class="py-3 px-3">Venta / MeLi</th>
                <th class="py-3 px-3">Fecha</th>
                <th class="py-3 px-3">Comprador</th>
                <th class="py-3 px-3">Productos & SKU</th>
                <th class="py-3 px-3">Bruto / Desc.</th>
                <th class="py-3 px-3">Pago</th>
                <th class="py-3 px-3">Envío</th>
                <th class="py-3 px-3">Comisión MeLi</th>
                <th class="py-3 px-3">Ganancia Est.</th>
                <th class="py-3 px-3">Estado</th>
                <th class="py-3 px-3 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody id="orders-table-tbody" class="divide-y divide-slate-100 text-slate-700">
              ${renderSkeleton()}
            </tbody>
          </table>
        </div>

        <!-- Paginación -->
        <div class="flex items-center justify-between px-4 py-3 bg-slate-50/50 border-t border-slate-100 text-xs">
          <span id="orders-pagination-info" class="text-slate-500 font-medium">Mostrando 0 de 0 pedidos</span>
          <div class="flex items-center space-x-1.5" id="orders-pagination-controls">
            <button id="btn-prev-page" class="px-3 py-1.5 border border-slate-200 rounded-lg text-slate-600 bg-white hover:bg-slate-50 disabled:opacity-40 transition-smooth font-semibold" disabled>
              Anterior
            </button>
            <button id="btn-next-page" class="px-3 py-1.5 border border-slate-200 rounded-lg text-slate-600 bg-white hover:bg-slate-50 disabled:opacity-40 transition-smooth font-semibold" disabled>
              Siguiente
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- SECCIÓN: REPORTES COMERCIALES (DIARIO / SEMANAL / MENSUAL) -->
    <div id="section-reports-content" class="hidden space-y-5">
      <div class="p-4 bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col sm:flex-row items-center justify-between gap-3">
        <div class="flex items-center gap-2">
          <span class="text-xs font-bold text-slate-700 uppercase">Periodo:</span>
          <div class="inline-flex rounded-xl p-1 bg-slate-100 text-xs font-bold">
            <button id="btn-report-daily" class="px-3 py-1.5 rounded-lg bg-white text-blue-600 shadow-sm transition-smooth">Diario</button>
            <button id="btn-report-weekly" class="px-3 py-1.5 rounded-lg text-slate-600 hover:text-slate-900 transition-smooth">Semanal</button>
            <button id="btn-report-monthly" class="px-3 py-1.5 rounded-lg text-slate-600 hover:text-slate-900 transition-smooth">Mensual</button>
          </div>
        </div>

        <div class="flex items-center gap-2">
          <label class="text-xs font-bold text-slate-700">Fecha:</label>
          <input type="date" id="report-date-picker" class="px-3 py-1.5 text-xs border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-600" value="${reportDate}">
          <button id="btn-generate-report" class="btn-primary text-xs px-3.5 py-1.5">Generar Reporte</button>
        </div>
      </div>

      <!-- Tarjetas Resumen de Reportes -->
      <div id="report-summary-cards" class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 text-center">
        <div class="card p-3">
          <div class="text-[10px] uppercase font-bold text-slate-400">Ventas Netas</div>
          <div id="rep-net-sales" class="text-lg font-black text-slate-900 mt-1">$ 0.00</div>
          <div class="text-[10px] text-slate-500">Sin cancelaciones</div>
        </div>
        <div class="card p-3">
          <div class="text-[10px] uppercase font-bold text-slate-400">Pedidos Pagados</div>
          <div id="rep-paid-orders" class="text-lg font-black text-slate-900 mt-1">0</div>
          <div id="rep-avg-ticket" class="text-[10px] text-slate-500">Ticket: $ 0.00</div>
        </div>
        <div class="card p-3 bg-emerald-50 border-emerald-200">
          <div class="text-[10px] uppercase font-bold text-emerald-600">Ganancia Neta</div>
          <div id="rep-net-profit" class="text-lg font-black text-emerald-700 mt-1">$ 0.00</div>
          <div id="rep-margin" class="text-[10px] text-emerald-600 font-bold">Margen: 0%</div>
        </div>
        <div class="card p-3">
          <div class="text-[10px] uppercase font-bold text-slate-400">Comisiones MeLi</div>
          <div id="rep-commissions" class="text-lg font-black text-slate-900 mt-1">$ 0.00</div>
        </div>
        <div class="card p-3">
          <div class="text-[10px] uppercase font-bold text-slate-400">Retenciones SAT</div>
          <div id="rep-taxes" class="text-lg font-black text-slate-900 mt-1">$ 0.00</div>
          <div class="text-[10px] text-slate-500">IVA 8% + ISR 1%</div>
        </div>
        <div class="card p-3 bg-rose-50 border-rose-200">
          <div class="text-[10px] uppercase font-bold text-rose-600">Cancelaciones</div>
          <div id="rep-cancelled" class="text-lg font-black text-rose-700 mt-1">0</div>
          <div class="text-[10px] text-rose-600 font-semibold">Excluidas de ingresos</div>
        </div>
      </div>

      <!-- Tabla de Desglose Temporal y Top SKUs -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div class="lg:col-span-2 card p-4 space-y-3">
          <h3 class="text-xs font-bold text-slate-800 uppercase tracking-wider">Desglose del Periodo</h3>
          <div class="overflow-x-auto rounded-xl border border-slate-200">
            <table class="w-full text-left text-xs">
              <thead class="bg-slate-50 text-[10px] uppercase font-bold text-slate-500 border-b border-slate-200">
                <tr>
                  <th class="py-2.5 px-3">Sub-Periodo</th>
                  <th class="py-2.5 px-3">Venta Neta</th>
                  <th class="py-2.5 px-3">Pedidos</th>
                  <th class="py-2.5 px-3">Utilidad</th>
                  <th class="py-2.5 px-3">Margen %</th>
                </tr>
              </thead>
              <tbody id="report-breakdown-tbody" class="divide-y divide-slate-100">
                <tr><td colspan="5" class="py-4 text-center text-slate-400">Cargando desglose...</td></tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="card p-4 space-y-3">
          <h3 class="text-xs font-bold text-slate-800 uppercase tracking-wider">Top SKUs Vendidos</h3>
          <div id="report-top-skus" class="space-y-2 text-xs">
            <div class="text-slate-400 text-center py-4">Consultando catálogo...</div>
          </div>
        </div>
      </div>
    </div>
  `;

  // Controladores de Elementos
  const tabSales = container.querySelector("#tab-sales");
  const tabCancelled = container.querySelector("#tab-cancelled");
  const tabClaims = container.querySelector("#tab-claims");
  const tabReports = container.querySelector("#tab-reports");

  const sectionSales = container.querySelector("#section-sales-content");
  const sectionReports = container.querySelector("#section-reports-content");

  const searchInput = container.querySelector("#orders-search-input");
  const statusSelect = container.querySelector("#orders-status-filter");
  const paySelect = container.querySelector("#orders-payment-filter");
  const shipSelect = container.querySelector("#orders-shipment-filter");
  const btnRefresh = container.querySelector("#btn-refresh-orders");
  const btnPrev = container.querySelector("#btn-prev-page");
  const btnNext = container.querySelector("#btn-next-page");

  // Tab switching
  function switchTab(newTab) {
    activeTab = newTab;
    [tabSales, tabCancelled, tabClaims, tabReports].forEach(b => {
      b.className = "tab-btn px-4 py-2.5 border-b-2 border-transparent text-slate-500 hover:text-slate-800 flex items-center gap-1.5 transition-smooth";
    });

    if (newTab === "sales") {
      tabSales.className = "tab-btn px-4 py-2.5 border-b-2 border-blue-600 text-blue-600 flex items-center gap-1.5 transition-smooth";
      sectionSales.classList.remove("hidden");
      sectionReports.classList.add("hidden");
      currentStatus = "";
      currentPage = 1;
      fetchOrders();
    } else if (newTab === "cancelled") {
      tabCancelled.className = "tab-btn px-4 py-2.5 border-b-2 border-blue-600 text-blue-600 flex items-center gap-1.5 transition-smooth";
      sectionSales.classList.remove("hidden");
      sectionReports.classList.add("hidden");
      currentStatus = "cancelled";
      currentPage = 1;
      fetchOrders();
    } else if (newTab === "claims") {
      tabClaims.className = "tab-btn px-4 py-2.5 border-b-2 border-blue-600 text-blue-600 flex items-center gap-1.5 transition-smooth";
      sectionSales.classList.remove("hidden");
      sectionReports.classList.add("hidden");
      currentStatus = "";
      currentPage = 1;
      fetchOrders("open_claims");
    } else if (newTab === "reports") {
      tabReports.className = "tab-btn px-4 py-2.5 border-b-2 border-blue-600 text-blue-600 flex items-center gap-1.5 transition-smooth";
      sectionSales.classList.add("hidden");
      sectionReports.classList.remove("hidden");
      loadSalesReport();
    }
  }

  if (tabSales) tabSales.addEventListener("click", () => switchTab("sales"));
  if (tabCancelled) tabCancelled.addEventListener("click", () => switchTab("cancelled"));
  if (tabClaims) tabClaims.addEventListener("click", () => switchTab("claims"));
  if (tabReports) tabReports.addEventListener("click", () => switchTab("reports"));

  // Filtros
  if (searchInput) {
    let debounce;
    searchInput.addEventListener("input", (e) => {
      clearTimeout(debounce);
      debounce = setTimeout(() => {
        searchFilter = e.target.value.trim();
        currentPage = 1;
        fetchOrders();
      }, 300);
    });
  }

  if (statusSelect) {
    statusSelect.addEventListener("change", (e) => {
      currentStatus = e.target.value;
      currentPage = 1;
      fetchOrders();
    });
  }

  if (paySelect) {
    paySelect.addEventListener("change", (e) => {
      currentPaymentStatus = e.target.value;
      currentPage = 1;
      fetchOrders();
    });
  }

  if (shipSelect) {
    shipSelect.addEventListener("change", (e) => {
      currentShipmentStatus = e.target.value;
      currentPage = 1;
      fetchOrders();
    });
  }

  if (btnRefresh) {
    btnRefresh.addEventListener("click", () => {
      if (activeTab === "reports") {
        loadSalesReport();
      } else {
        fetchOrders();
      }
      showToast("Datos actualizados", "info");
    });
  }

  if (btnPrev) {
    btnPrev.addEventListener("click", () => {
      if (currentPage > 1) {
        currentPage--;
        fetchOrders();
      }
    });
  }

  if (btnNext) {
    btnNext.addEventListener("click", () => {
      currentPage++;
      fetchOrders();
    });
  }

  // Report Period buttons
  const btnRepDaily = container.querySelector("#btn-report-daily");
  const btnRepWeekly = container.querySelector("#btn-report-weekly");
  const btnRepMonthly = container.querySelector("#btn-report-monthly");
  const datePicker = container.querySelector("#report-date-picker");
  const btnGenReport = container.querySelector("#btn-generate-report");

  function setReportPeriod(period) {
    reportPeriod = period;
    [btnRepDaily, btnRepWeekly, btnRepMonthly].forEach(b => {
      b.className = "px-3 py-1.5 rounded-lg text-slate-600 hover:text-slate-900 transition-smooth";
    });
    if (period === "daily") btnRepDaily.className = "px-3 py-1.5 rounded-lg bg-white text-blue-600 shadow-sm transition-smooth";
    if (period === "weekly") btnRepWeekly.className = "px-3 py-1.5 rounded-lg bg-white text-blue-600 shadow-sm transition-smooth";
    if (period === "monthly") btnRepMonthly.className = "px-3 py-1.5 rounded-lg bg-white text-blue-600 shadow-sm transition-smooth";
    loadSalesReport();
  }

  if (btnRepDaily) btnRepDaily.addEventListener("click", () => setReportPeriod("daily"));
  if (btnRepWeekly) btnRepWeekly.addEventListener("click", () => setReportPeriod("weekly"));
  if (btnRepMonthly) btnRepMonthly.addEventListener("click", () => setReportPeriod("monthly"));
  if (btnGenReport) btnGenReport.addEventListener("click", () => {
    reportDate = datePicker.value;
    loadSalesReport();
  });

  async function fetchOrders(specialFilter = "") {
    const tbody = container.querySelector("#orders-table-tbody");
    tbody.innerHTML = renderSkeleton();

    try {
      const params = {
        page: currentPage,
        page_size: 15,
      };
      if (searchFilter) params.search = searchFilter;
      if (currentStatus) params.status = currentStatus;
      if (currentPaymentStatus) params.payment_status = currentPaymentStatus;
      if (currentShipmentStatus) params.shipment_status = currentShipmentStatus;
      if (specialFilter === "open_claims") params.claim_status = "open";

      const data = await api.get("/orders", params);
      const items = data.items || [];

      if (items.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="11" class="py-12 text-center text-slate-400">
              No se encontraron ventas con los criterios aplicados.
            </td>
          </tr>
        `;
      } else {
        tbody.innerHTML = items.map(o => {
          const profit = Number(o.estimated_profit || 0);
          const margin = Number(o.net_margin_pct || 0);
          const gross = Number(o.total_amount || 0);
          const discount = Number(o.discount_amount || 0);
          const meliFee = Number(o.meli_fee_amount || 0);

          let statusClass = "bg-slate-100 text-slate-700";
          if (o.status === "paid" || o.status === "delivered") statusClass = "bg-emerald-100 text-emerald-800";
          else if (o.status === "cancelled") statusClass = "bg-rose-100 text-rose-800";
          else if (o.status === "shipped") statusClass = "bg-blue-100 text-blue-800";
          else if (o.status === "returned") statusClass = "bg-purple-100 text-purple-800";

          // Items summary
          const itemsSummary = (o.items || []).map(it => `
            <div class="truncate max-w-[180px]" title="${it.title}">
              <span class="font-bold text-slate-900">${it.quantity}x</span>
              <span class="font-mono text-slate-600">[${it.seller_sku || 'S/SKU'}]</span>
              ${it.variant_name ? `<span class="text-slate-500">(${it.variant_name})</span>` : ''}
            </div>
          `).join("");

          const buyerDisplay = o.buyer_nickname || o.buyer_name || `ID ${o.buyer_id || 'N/A'}`;

          return `
            <tr class="hover:bg-slate-50/80 transition-smooth">
              <td class="py-3 px-3">
                <div class="font-mono font-bold text-slate-900">#${o.meli_order_id}</div>
                <div class="text-[10px] text-slate-400">${o.order_number || ''}</div>
              </td>
              <td class="py-3 px-3 text-slate-500 whitespace-nowrap">
                ${new Date(o.date_created_meli).toLocaleString('es-MX', { dateStyle: 'short', timeStyle: 'short' })}
              </td>
              <td class="py-3 px-3">
                <div class="font-semibold text-slate-800 truncate max-w-[130px]" title="${buyerDisplay}">${buyerDisplay}</div>
                ${o.buyer_document ? `<div class="font-mono text-[10px] text-slate-400">${o.buyer_document}</div>` : ''}
              </td>
              <td class="py-3 px-3 text-[11px]">
                ${itemsSummary || '<span class="text-slate-400">Sin partidas</span>'}
              </td>
              <td class="py-3 px-3 whitespace-nowrap">
                <div class="font-bold text-slate-900">$ ${gross.toFixed(2)}</div>
                ${discount > 0 ? `<div class="text-[10px] text-rose-600 font-semibold">-$ ${discount.toFixed(2)}</div>` : ''}
              </td>
              <td class="py-3 px-3">
                <span class="inline-flex px-1.5 py-0.5 rounded text-[10px] font-bold ${o.payment_status === 'approved' ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-600'}">
                  ${o.payment_status}
                </span>
              </td>
              <td class="py-3 px-3">
                <span class="inline-flex px-1.5 py-0.5 rounded text-[10px] font-bold ${o.shipment_status === 'delivered' ? 'bg-emerald-50 text-emerald-700' : (o.shipment_status === 'shipped' ? 'bg-blue-50 text-blue-700' : 'bg-slate-100 text-slate-600')}">
                  ${o.shipment_status}
                </span>
              </td>
              <td class="py-3 px-3 font-mono text-slate-600 whitespace-nowrap">
                $ ${meliFee.toFixed(2)}
              </td>
              <td class="py-3 px-3 whitespace-nowrap">
                <div class="font-bold ${profit >= 0 ? 'text-emerald-700' : 'text-rose-700'}">$ ${profit.toFixed(2)}</div>
                <div class="text-[10px] text-slate-400 font-mono">${margin.toFixed(1)}%</div>
              </td>
              <td class="py-3 px-3">
                <span class="inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold ${statusClass}">
                  ${o.status}
                </span>
              </td>
              <td class="py-3 px-3 text-right whitespace-nowrap space-x-1">
                <button data-order-id="${o.id}" class="btn-detail px-2 py-1 text-[11px] font-semibold text-blue-700 bg-blue-50 hover:bg-blue-100 rounded transition-smooth">
                  Detalle
                </button>
                <button data-order-id="${o.id}" class="btn-compare px-2 py-1 text-[11px] font-semibold text-purple-700 bg-purple-50 hover:bg-purple-100 rounded transition-smooth">
                  Comparar
                </button>
                ${o.status !== 'cancelled' ? `
                  <button data-order-id="${o.id}" class="btn-cancel px-2 py-1 text-[11px] font-semibold text-rose-700 bg-rose-50 hover:bg-rose-100 rounded transition-smooth">
                    Cancelar
                  </button>
                  <button data-order-id="${o.id}" class="btn-return px-2 py-1 text-[11px] font-semibold text-amber-700 bg-amber-50 hover:bg-amber-100 rounded transition-smooth">
                    Devolución
                  </button>
                ` : ''}
              </td>
            </tr>
          `;
        }).join("");

        // Bind clicks
        tbody.querySelectorAll(".btn-detail").forEach(btn => {
          btn.addEventListener("click", () => openOrderDetailModal(btn.dataset.orderId));
        });
        tbody.querySelectorAll(".btn-compare").forEach(btn => {
          btn.addEventListener("click", () => openCompareModal(btn.dataset.orderId));
        });
        tbody.querySelectorAll(".btn-cancel").forEach(btn => {
          btn.addEventListener("click", () => openCancelModal(btn.dataset.orderId));
        });
        tbody.querySelectorAll(".btn-return").forEach(btn => {
          btn.addEventListener("click", () => openReturnModal(btn.dataset.orderId));
        });
      }

      // Actualizar Paginación
      const infoEl = container.querySelector("#orders-pagination-info");
      if (infoEl) infoEl.textContent = `Página ${data.page} de ${data.total_pages || 1} (${data.total_items} pedidos en total)`;

      if (btnPrev) btnPrev.disabled = !data.has_prev;
      if (btnNext) btnNext.disabled = !data.has_next;

    } catch (err) {
      tbody.innerHTML = `
        <tr>
          <td colspan="11" class="py-8 text-center text-rose-600 font-semibold">
            Error al consultar ventas: ${err.message}
          </td>
        </tr>
      `;
    }
  }

  async function openOrderDetailModal(orderId) {
    try {
      const o = await api.get(`/orders/${orderId}`);
      const prof = o.profitability || {};

      const itemsHtml = (o.items || []).map(it => `
        <div class="p-3 bg-slate-50 border border-slate-200 rounded-xl flex items-center justify-between text-xs">
          <div>
            <div class="font-bold text-slate-900">${it.title}</div>
            <div class="font-mono text-[11px] text-slate-500 mt-0.5">
              SKU: <span class="font-bold text-slate-700">${it.seller_sku || 'S/SKU'}</span> · 
              Item: ${it.meli_item_id} · Cantidad: ${it.quantity}
            </div>
            ${it.variant_name ? `<div class="text-[11px] text-blue-700">Variante: ${it.variant_name}</div>` : ''}
          </div>
          <div class="text-right whitespace-nowrap">
            <div class="font-bold text-slate-900">$ ${(it.unit_price * it.quantity).toFixed(2)}</div>
            <div class="text-[10px] text-slate-500 font-mono">Costo unitario: $ ${Number(it.cogs_unit || 0).toFixed(2)}</div>
            <div class="text-[10px] text-amber-700 font-mono">Comisión MeLi: -$ ${Number(it.sale_fee || 0).toFixed(2)}</div>
          </div>
        </div>
      `).join("");

      const timelinesHtml = (o.timelines || []).map(tl => `
        <div class="flex items-start gap-3 text-xs">
          <div class="w-2.5 h-2.5 rounded-full bg-blue-600 mt-1 flex-shrink-0"></div>
          <div>
            <div class="font-bold text-slate-900 flex items-center gap-2">
              <span>${tl.title}</span>
              <span class="text-[10px] font-normal text-slate-400">${new Date(tl.created_at).toLocaleString('es-MX')}</span>
            </div>
            ${tl.description ? `<p class="text-slate-600 mt-0.5">${tl.description}</p>` : ''}
            <span class="text-[10px] font-mono text-slate-400">Actor: ${tl.actor}</span>
          </div>
        </div>
      `).join("");

      openModal({
        title: `Detalle del Pedido MeLi #${o.meli_order_id} (${o.status.toUpperCase()})`,
        size: "lg",
        content: `
          <div class="space-y-4 text-xs">
            <!-- Desglose Financiero y SAT -->
            <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
              <div class="p-2.5 bg-slate-50 border border-slate-200 rounded-xl">
                <div class="text-[10px] uppercase font-bold text-slate-400">Total Venta</div>
                <div class="text-sm font-bold text-slate-900">$ ${Number(o.total_amount).toFixed(2)}</div>
              </div>
              <div class="p-2.5 bg-slate-50 border border-slate-200 rounded-xl">
                <div class="text-[10px] uppercase font-bold text-slate-400">Costo Mercancía (COGS)</div>
                <div class="text-sm font-bold text-slate-900">$ ${Number(prof.cogs_total || o.cogs_total || 0).toFixed(2)}</div>
              </div>
              <div class="p-2.5 bg-slate-50 border border-slate-200 rounded-xl">
                <div class="text-[10px] uppercase font-bold text-slate-400">Comisión MeLi</div>
                <div class="text-sm font-bold text-amber-700">-$ ${Number(prof.meli_commission_fee || o.meli_fee_amount || 0).toFixed(2)}</div>
              </div>
              <div class="p-2.5 bg-emerald-50 border border-emerald-200 rounded-xl">
                <div class="text-[10px] uppercase font-bold text-emerald-600">Ganancia Neta</div>
                <div class="text-sm font-black text-emerald-800">$ ${Number(prof.net_profit || o.estimated_profit || 0).toFixed(2)} (${Number(prof.net_margin_pct || o.net_margin_pct || 0).toFixed(1)}%)</div>
              </div>
            </div>

            <!-- Retenciones SAT México -->
            <div class="p-3 bg-amber-50/70 border border-amber-200 rounded-xl space-y-1">
              <div class="font-bold text-amber-900 flex justify-between">
                <span>Auditoría de Retenciones Fiscales (SAT México)</span>
                <span>Total Impuestos: $ ${(Number(prof.sat_iva_retention || 0) + Number(prof.sat_isr_retention || 0)).toFixed(2)}</span>
              </div>
              <div class="grid grid-cols-3 gap-2 text-[11px] text-amber-800 pt-1 font-mono">
                <div>Retención IVA (8%): $ ${Number(prof.sat_iva_retention || 0).toFixed(2)}</div>
                <div>Retención ISR (1%): $ ${Number(prof.sat_isr_retention || 0).toFixed(2)}</div>
                <div>Costo Empaque: $ ${Number(prof.packaging_cost || 0).toFixed(2)}</div>
              </div>
            </div>

            <!-- Datos del Comprador y Envío -->
            <div class="grid grid-cols-2 gap-3 p-3 bg-slate-50 border border-slate-200 rounded-xl">
              <div>
                <div class="font-bold text-slate-800 mb-1">Comprador</div>
                <div>Nickname: <span class="font-semibold text-slate-900">${o.buyer_nickname || 'N/A'}</span></div>
                <div>Nombre: <span class="text-slate-700">${o.buyer_name || 'N/A'}</span></div>
                <div>Email: <span class="text-slate-700">${o.buyer_email || 'N/A'}</span></div>
              </div>
              <div>
                <div class="font-bold text-slate-800 mb-1">Envío & Despacho</div>
                <div>Estado: <span class="font-semibold text-blue-700">${o.shipment_status}</span></div>
                <div>Tipo Logístico: <span class="text-slate-700">${(o.shipments && o.shipments[0]) ? o.shipments[0].logistic_type : 'cross_docking'}</span></div>
                <div>Rastreo: <span class="font-mono text-slate-900">${(o.shipments && o.shipments[0] && o.shipments[0].tracking_number) || 'Pendiente'}</span></div>
              </div>
            </div>

            <!-- Partidas de la Orden -->
            <div class="space-y-2">
              <div class="font-bold text-slate-800 uppercase tracking-wider text-[11px]">Productos de la Orden</div>
              <div class="space-y-2 max-h-48 overflow-y-auto">${itemsHtml}</div>
            </div>

            <!-- Línea de Tiempo Histórica -->
            <div class="space-y-2 pt-2 border-t border-slate-200">
              <div class="font-bold text-slate-800 uppercase tracking-wider text-[11px]">Línea de Tiempo del Pedido</div>
              <div class="space-y-3 pl-2 border-l-2 border-blue-200 max-h-48 overflow-y-auto">
                ${timelinesHtml || '<div class="text-slate-400">Sin eventos cronológicos registrados</div>'}
              </div>
            </div>
          </div>
        `,
        confirmText: "Cerrar",
        onConfirm: () => {},
      });
    } catch (err) {
      showToast(err.message, "error");
    }
  }

  async function openCompareModal(orderId) {
    try {
      showToast("Consultando API oficial de Mercado Libre para comparar...", "info");
      const comp = await api.get(`/orders/${orderId}/compare`);

      const diffsHtml = comp.is_matching
        ? `<div class="p-3 bg-emerald-50 text-emerald-800 border border-emerald-200 rounded-xl font-bold">✔ 100% Coincidencia: Todos los importes, estados y partidas en MeLi coinciden con el ERP.</div>`
        : `
          <div class="p-3 bg-rose-50 text-rose-900 border border-rose-200 rounded-xl space-y-1">
            <div class="font-bold">⚠ Se detectaron ${comp.differences.length} discrepancia(s):</div>
            <ul class="list-disc list-inside text-[11px] space-y-0.5 font-mono">
              ${comp.differences.map(d => `<li>${d}</li>`).join('')}
            </ul>
          </div>
        `;

      openModal({
        title: `Comparativa MeLi vs ERP Interno (Orden #${comp.meli_order_id})`,
        size: "md",
        content: `
          <div class="space-y-3 text-xs">
            ${diffsHtml}
            <div class="grid grid-cols-2 gap-3 pt-2">
              <div class="p-3 bg-slate-50 border border-slate-200 rounded-xl space-y-1 font-mono text-[11px]">
                <div class="font-bold text-slate-900 text-xs mb-1 font-sans">Datos Mercado Libre (API)</div>
                <div>Estado: ${comp.meli_data.status}</div>
                <div>Total: $ ${Number(comp.meli_data.total_amount).toFixed(2)}</div>
                <div>Pagado: $ ${Number(comp.meli_data.paid_amount).toFixed(2)}</div>
                <div>Logística: ${comp.meli_data.shipping_type || 'N/A'}</div>
              </div>

              <div class="p-3 bg-slate-50 border border-slate-200 rounded-xl space-y-1 font-mono text-[11px]">
                <div class="font-bold text-slate-900 text-xs mb-1 font-sans">Datos ERP Interno</div>
                <div>Estado: ${comp.internal_data.status}</div>
                <div>Total: $ ${Number(comp.internal_data.total_amount).toFixed(2)}</div>
                <div>Pagado: $ ${Number(comp.internal_data.paid_amount).toFixed(2)}</div>
                <div>Ganancia Est.: $ ${Number(comp.internal_data.estimated_profit).toFixed(2)}</div>
              </div>
            </div>
          </div>
        `,
        confirmText: "Entendido",
        onConfirm: () => {},
      });
    } catch (err) {
      showToast(err.message, "error");
    }
  }

  function openCancelModal(orderId) {
    openModal({
      title: "Cancelar Pedido & Liberar Stock",
      size: "md",
      content: `
        <div class="space-y-3 text-xs">
          <p class="text-slate-600">
            Al cancelar el pedido, las unidades reservadas en bodega serán liberadas inmediatamente y la orden será excluida de las ventas definitivas.
          </p>
          <div>
            <label class="block font-bold text-slate-700 mb-1">Motivo de Cancelación *</label>
            <input type="text" id="cancel-reason" placeholder="e.g. Comprador se arrepintió de la compra" class="w-full px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-rose-600" />
          </div>
          <div>
            <label class="block font-bold text-slate-700 mb-1">Parte Responsable *</label>
            <select id="cancel-responsible" class="w-full px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-rose-600">
              <option value="buyer" selected>Comprador (buyer)</option>
              <option value="seller">Vendedor / Tienda (seller)</option>
              <option value="marketplace">Mercado Libre (marketplace)</option>
            </select>
          </div>
        </div>
      `,
      confirmText: "Confirmar Cancelación",
      onConfirm: async () => {
        const reason = document.getElementById("cancel-reason").value.trim();
        const resp = document.getElementById("cancel-responsible").value;
        if (!reason) throw new Error("Debes especificar el motivo de cancelación.");

        await api.post(`/orders/${orderId}/cancel`, {
          reason: reason,
          responsible: resp,
        });

        showToast("Pedido cancelado y stock liberado con éxito.", "success");
        fetchOrders();
      },
    });
  }

  function openReturnModal(orderId) {
    openModal({
      title: "Registrar Devolución de Mercancía",
      size: "md",
      content: `
        <div class="space-y-3 text-xs">
          <p class="text-slate-600">
            Evalúa el estado físico de los productos retornados para actualizar el Kardex de inventario correspondiente:
          </p>
          <div>
            <label class="block font-bold text-slate-700 mb-1">Condición del Producto *</label>
            <select id="return-condition" class="w-full px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-600">
              <option value="good" selected>Buen Estado (Reingreso a Stock Disponible)</option>
              <option value="damaged">Dañado / Defectuoso (Ingreso a Cuarentena/Bloqueado)</option>
            </select>
          </div>
          <div>
            <label class="block font-bold text-slate-700 mb-1">Notas de Peritaje o Inspección</label>
            <textarea id="return-notes" rows="2" placeholder="Empaque abierto, producto intacto..." class="w-full px-3 py-2 border border-slate-200 rounded-xl"></textarea>
          </div>
        </div>
      `,
      confirmText: "Procesar Devolución",
      onConfirm: async () => {
        const cond = document.getElementById("return-condition").value;
        const notes = document.getElementById("return-notes").value.trim();

        await api.post(`/orders/${orderId}/return`, {
          condition: cond,
          notes: notes,
        });

        showToast("Devolución registrada e inventario actualizado.", "success");
        fetchOrders();
      },
    });
  }

  async function loadSalesReport() {
    try {
      const data = await api.get(`/orders/reports/sales?period=${reportPeriod}&reference_date=${reportDate}`);
      const sum = data.summary || {};

      const netSalesEl = container.querySelector("#rep-net-sales");
      const paidOrdersEl = container.querySelector("#rep-paid-orders");
      const avgTicketEl = container.querySelector("#rep-avg-ticket");
      const netProfitEl = container.querySelector("#rep-net-profit");
      const marginEl = container.querySelector("#rep-margin");
      const commEl = container.querySelector("#rep-commissions");
      const taxesEl = container.querySelector("#rep-taxes");
      const cancEl = container.querySelector("#rep-cancelled");

      if (netSalesEl) netSalesEl.textContent = `$ ${Number(sum.net_sales || 0).toFixed(2)}`;
      if (paidOrdersEl) paidOrdersEl.textContent = sum.paid_orders || 0;
      if (avgTicketEl) avgTicketEl.textContent = `Ticket: $ ${Number(sum.average_ticket || 0).toFixed(2)}`;
      if (netProfitEl) netProfitEl.textContent = `$ ${Number(sum.net_profit || 0).toFixed(2)}`;
      if (marginEl) marginEl.textContent = `Margen: ${Number(sum.profit_margin_pct || 0).toFixed(1)}%`;
      if (commEl) commEl.textContent = `$ ${Number(sum.meli_commissions || 0).toFixed(2)}`;
      if (taxesEl) taxesEl.textContent = `$ ${Number(sum.sat_tax_retentions || 0).toFixed(2)}`;
      if (cancEl) cancEl.textContent = sum.cancelled_orders || 0;

      // Desglose
      const bTbody = container.querySelector("#report-breakdown-tbody");
      if (bTbody) {
        const bItems = data.breakdown || [];
        if (bItems.length === 0) {
          bTbody.innerHTML = `<tr><td colspan="5" class="py-4 text-center text-slate-400">Sin ventas en este intervalo</td></tr>`;
        } else {
          bTbody.innerHTML = bItems.map(b => `
            <tr class="hover:bg-slate-50">
              <td class="py-2.5 px-3 font-semibold text-slate-900">${b.period}</td>
              <td class="py-2.5 px-3 font-bold text-slate-800">$ ${Number(b.net_sales || 0).toFixed(2)}</td>
              <td class="py-2.5 px-3 text-slate-600">${b.paid_orders || 0}</td>
              <td class="py-2.5 px-3 font-bold text-emerald-700">$ ${Number(b.net_profit || 0).toFixed(2)}</td>
              <td class="py-2.5 px-3 font-mono text-slate-500">${Number(b.profit_margin_pct || 0).toFixed(1)}%</td>
            </tr>
          `).join("");
        }
      }

      // Top SKUs
      const topDiv = container.querySelector("#report-top-skus");
      if (topDiv) {
        const topSkus = data.top_selling_skus || [];
        if (topSkus.length === 0) {
          topDiv.innerHTML = `<div class="text-slate-400 text-center py-4">No hay ventas registradas en el periodo</div>`;
        } else {
          topDiv.innerHTML = topSkus.map((s, idx) => `
            <div class="p-2.5 bg-slate-50 border border-slate-200 rounded-xl flex items-center justify-between">
              <div>
                <div class="font-bold text-slate-900 text-[11px]">${idx + 1}. ${s.sku}</div>
                <div class="text-[10px] text-slate-500 truncate max-w-[150px]">${s.title}</div>
              </div>
              <div class="text-right">
                <div class="font-bold text-slate-800">$ ${Number(s.revenue).toFixed(2)}</div>
                <div class="text-[10px] text-slate-500">${s.units_sold} uds</div>
              </div>
            </div>
          `).join("");
        }
      }

    } catch (err) {
      showToast(err.message, "error");
    }
  }

  // Carga inicial
  fetchOrders();

  return container;
}


// Adaptador para app.js: la app espera renderOrders(contenedor) y descarta el
// valor de retorno; renderOrdersView() no recibe argumentos y devuelve el elemento.
export function renderOrders(container) {
  const el = renderOrdersView();
  if (container) container.appendChild(el);
  return el;
}

/**
 * Módulo Financiero Profesional de Mercado Libre México.
 * 
 * Gestiona y diferencia de forma rigurosa:
 * 1. Importe Bruto (Total facturación)
 * 2. Importe Neto Estimado (Post comisiones y retenciones SAT)
 * 3. Dinero Acreditado (Fondos en proceso de liberación en Mercado Pago)
 * 4. Dinero Disponible (Saldo líquido liberado para retiro)
 * 5. Dinero Retirado (Transferencias a cuentas bancarias CLABE vía SPEI)
 * 6. Reembolsos (Cancelaciones y devoluciones)
 * 7. Cargos Definitivos (Comisiones MeLi + fletes vendedor + retenciones SAT 8% / 1%)
 * 
 * Funciones:
 * - Registro y consulta de transacciones contables con fecha y origen.
 * - Registro de liquidaciones y transferencias a bancos.
 * - Registro manual de gastos externos (publicidad, fletes, empaque).
 * - Motor de conciliación automática y resolución de discrepancias.
 * - Reportes multidimensionales: Por Cuenta, Por Producto/SKU y Por Periodo.
 */

import { api } from "../api.js";
import { icons } from "../icons.js";
import { showToast } from "../components/toast.js";
import { openModal, closeModal } from "../components/modal.js";

let currentTab = "transactions";
let accountsCache = [];

export async function renderFinances(container) {
  container.innerHTML = `
    <div class="space-y-6">
      <!-- Encabezado Principal y Acciones -->
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 class="text-2xl font-black text-slate-900 tracking-tight flex items-center gap-2">
            ${icons.finances("w-6 h-6 text-slate-700")} Módulo Financiero & Conciliación MeLi
          </h1>
          <p class="text-xs text-slate-500 mt-1">
            Auditoría de Mercado Pago, retenciones fiscales SAT (IVA 8%, ISR 1%), flujo de caja y liquidaciones bancarias.
          </p>
        </div>

        <div class="flex items-center gap-2.5">
          <button id="btn-run-reconciliation" class="flex items-center gap-3 px-5 py-3 bg-gradient-to-r from-purple-600 to-violet-600 hover:from-purple-700 hover:to-violet-700 text-white rounded-2xl shadow-lg shadow-purple-600/30 hover:shadow-xl hover:shadow-purple-600/40 hover:-translate-y-0.5 transition-all touch-target text-left">
            <span class="flex items-center justify-center w-10 h-10 rounded-xl bg-white/20 shrink-0">${icons.refresh("w-6 h-6")}</span>
            <span class="flex flex-col items-start leading-tight">
              <span class="text-sm font-extrabold">Conciliación Automática</span>
              <span class="text-[11px] font-medium text-purple-100">Cruza tus ventas de MeLi con el banco en un clic</span>
            </span>
          </button>
          <button id="btn-add-expense" class="flex items-center gap-3 px-5 py-3 bg-gradient-to-r from-blue-600 to-sky-600 hover:from-blue-700 hover:to-sky-700 text-white rounded-2xl shadow-lg shadow-blue-600/30 hover:shadow-xl hover:shadow-blue-600/40 hover:-translate-y-0.5 transition-all touch-target text-left">
            <span class="flex items-center justify-center w-10 h-10 rounded-xl bg-white/20 shrink-0">${icons.plus("w-6 h-6")}</span>
            <span class="flex flex-col items-start leading-tight">
              <span class="text-sm font-extrabold">Registrar Gasto Externo</span>
              <span class="text-[11px] font-medium text-blue-100">Anota un gasto fuera de Mercado Libre</span>
            </span>
          </button>
          <button id="btn-refresh-finances" class="flex items-center gap-2 px-4 py-3 bg-white border-2 border-slate-200 hover:border-slate-300 hover:bg-slate-50 text-slate-700 rounded-2xl shadow-sm hover:shadow transition-all touch-target text-sm font-bold" title="Actualizar datos financieros">
            ${icons.refresh("w-5 h-5")}
            <span>Actualizar</span>
          </button>
        </div>
      </div>

      <!-- LAS 7 MÉTRICAS FINANCIERAS CLARAMENTE DIFERENCIADAS -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7 gap-3">
        <!-- 1. Importe Bruto -->
        <div class="p-4 bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col justify-between">
          <div class="text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center justify-between">
            <span>1. Importe Bruto</span>
            <span class="text-slate-300">#01</span>
          </div>
          <div id="kpi-gross-amount" class="text-xl font-black text-slate-900 mt-2 font-mono">...</div>
          <div class="text-[10px] text-slate-400 mt-1">Ventas totales sin deducciones</div>
        </div>

        <!-- 2. Importe Neto Estimado -->
        <div class="p-4 bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col justify-between">
          <div class="text-[10px] font-bold text-blue-600 uppercase tracking-wider flex items-center justify-between">
            <span>2. Neto Estimado</span>
            <span class="text-blue-300">#02</span>
          </div>
          <div id="kpi-estimated-net" class="text-xl font-black text-blue-700 mt-2 font-mono">...</div>
          <div class="text-[10px] text-slate-400 mt-1">Post comisiones e impuestos</div>
        </div>

        <!-- 3. Dinero Acreditado -->
        <div class="p-4 bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col justify-between">
          <div class="text-[10px] font-bold text-amber-600 uppercase tracking-wider flex items-center justify-between">
            <span>3. Dinero Acreditado</span>
            <span class="text-amber-300">#03</span>
          </div>
          <div id="kpi-accredited-funds" class="text-xl font-black text-amber-600 mt-2 font-mono">...</div>
          <div class="text-[10px] text-slate-400 mt-1">En proceso de liberación MP</div>
        </div>

        <!-- 4. Dinero Disponible -->
        <div class="p-4 bg-emerald-50 rounded-2xl border border-emerald-200 shadow-sm flex flex-col justify-between">
          <div class="text-[10px] font-bold text-emerald-800 uppercase tracking-wider flex items-center justify-between">
            <span>4. Dinero Disponible</span>
            <span class="text-emerald-400">#04</span>
          </div>
          <div id="kpi-available-funds" class="text-xl font-black text-emerald-700 mt-2 font-mono">...</div>
          <div class="text-[10px] text-emerald-800 font-semibold mt-1">Listo para retiro bancario</div>
        </div>

        <!-- 5. Dinero Retirado -->
        <div class="p-4 bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col justify-between">
          <div class="text-[10px] font-bold text-indigo-600 uppercase tracking-wider flex items-center justify-between">
            <span>5. Dinero Retirado</span>
            <span class="text-indigo-300">#05</span>
          </div>
          <div id="kpi-withdrawn-funds" class="text-xl font-black text-indigo-700 mt-2 font-mono">...</div>
          <div class="text-[10px] text-slate-400 mt-1">Transferido a CLABE bancaria</div>
        </div>

        <!-- 6. Reembolsos -->
        <div class="p-4 bg-rose-50 rounded-2xl border border-rose-200 shadow-sm flex flex-col justify-between">
          <div class="text-[10px] font-bold text-rose-800 uppercase tracking-wider flex items-center justify-between">
            <span>6. Reembolsos</span>
            <span class="text-rose-400">#06</span>
          </div>
          <div id="kpi-refunds-amount" class="text-xl font-black text-rose-700 mt-2 font-mono">...</div>
          <div class="text-[10px] text-rose-800 font-semibold mt-1">Cancelaciones y devoluciones</div>
        </div>

        <!-- 7. Cargos Definitivos -->
        <div class="p-4 bg-slate-50 rounded-2xl border border-slate-200 shadow-sm flex flex-col justify-between">
          <div class="text-[10px] font-bold text-slate-600 uppercase tracking-wider flex items-center justify-between">
            <span>7. Cargos Definitivos</span>
            <span class="text-slate-400">#07</span>
          </div>
          <div id="kpi-definitive-charges" class="text-xl font-black text-slate-700 mt-2 font-mono">...</div>
          <div class="text-[10px] text-slate-500 mt-1">Comisiones + fletes + SAT</div>
        </div>
      </div>

      <!-- Pestañas de Navegación del Módulo Financiero -->
      <div class="flex border-b border-slate-200 gap-1 text-xs font-bold overflow-x-auto">
        <button id="tab-btn-transactions" class="fin-tab-btn px-4 py-2.5 border-b-2 border-blue-600 text-blue-600 flex items-center gap-1.5 transition-smooth whitespace-nowrap">
          ${icons.tabular("w-4 h-4")} Partidas & Transacciones
        </button>
        <button id="tab-btn-settlements" class="fin-tab-btn px-4 py-2.5 border-b-2 border-transparent text-slate-500 hover:text-slate-800 flex items-center gap-1.5 transition-smooth whitespace-nowrap">
          ${icons.check("w-4 h-4")} Liquidaciones & Retiros
        </button>
        <button id="tab-btn-expenses" class="fin-tab-btn px-4 py-2.5 border-b-2 border-transparent text-slate-500 hover:text-slate-800 flex items-center gap-1.5 transition-smooth whitespace-nowrap">
          ${icons.inventory("w-4 h-4")} Gastos Externos Manuales
        </button>
        <button id="tab-btn-reconciliation" class="fin-tab-btn px-4 py-2.5 border-b-2 border-transparent text-slate-500 hover:text-slate-800 flex items-center gap-1.5 transition-smooth whitespace-nowrap">
          ${icons.shield("w-4 h-4")} Conciliación & Discrepancias
        </button>
        <button id="tab-btn-reports" class="fin-tab-btn px-4 py-2.5 border-b-2 border-transparent text-slate-500 hover:text-slate-800 flex items-center gap-1.5 transition-smooth whitespace-nowrap">
          ${icons.reports("w-4 h-4")} Reportes Financieros
        </button>
        <button id="tab-btn-profitability" class="fin-tab-btn px-4 py-2.5 border-b-2 border-transparent text-slate-500 hover:text-slate-800 flex items-center gap-1.5 transition-smooth whitespace-nowrap">
          ${icons.finances("w-4 h-4")} Rentabilidad (8D)
        </button>
        <button id="tab-btn-loss-alerts" class="fin-tab-btn px-4 py-2.5 border-b-2 border-transparent text-slate-500 hover:text-slate-800 flex items-center gap-1.5 transition-smooth whitespace-nowrap">
          ${icons.alertTriangle("w-4 h-4")} Alertas de Pérdida
        </button>
        <button id="tab-btn-simulator" class="fin-tab-btn px-4 py-2.5 border-b-2 border-transparent text-slate-500 hover:text-slate-800 flex items-center gap-1.5 transition-smooth whitespace-nowrap">
          ${icons.labels("w-4 h-4")} Simulador Margen
        </button>
        <button id="tab-btn-cost-history" class="fin-tab-btn px-4 py-2.5 border-b-2 border-transparent text-slate-500 hover:text-slate-800 flex items-center gap-1.5 transition-smooth whitespace-nowrap">
          ${icons.tabular("w-4 h-4")} Historial Costos (COGS)
        </button>
        <button id="tab-btn-fiscal-pac" class="fin-tab-btn px-4 py-2.5 border-b-2 border-transparent text-slate-500 hover:text-slate-800 flex items-center gap-1.5 transition-smooth whitespace-nowrap">
          ${icons.shield("w-4 h-4")} PAC SAT (CFDI 4.0)
        </button>
      </div>

      <!-- CONTENEDOR DINÁMICO DE PESTAÑAS -->
      <div id="finances-tab-content" class="space-y-4">
        <!-- Contenido inyectado dinámicamente -->
      </div>
    </div>
  `;

  // Eventos de Pestañas
  const tabBtns = container.querySelectorAll(".fin-tab-btn");
  tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      tabBtns.forEach((b) => {
        b.classList.remove("border-blue-600", "text-blue-600");
        b.classList.add("border-transparent", "text-slate-500");
      });
      btn.classList.add("border-blue-600", "text-blue-600");
      btn.classList.remove("border-transparent", "text-slate-500");

      if (btn.id === "tab-btn-transactions") currentTab = "transactions";
      else if (btn.id === "tab-btn-settlements") currentTab = "settlements";
      else if (btn.id === "tab-btn-expenses") currentTab = "expenses";
      else if (btn.id === "tab-btn-reconciliation") currentTab = "reconciliation";
      else if (btn.id === "tab-btn-reports") currentTab = "reports";
      else if (btn.id === "tab-btn-profitability") currentTab = "profitability";
      else if (btn.id === "tab-btn-loss-alerts") currentTab = "loss_alerts";
      else if (btn.id === "tab-btn-simulator") currentTab = "simulator";
      else if (btn.id === "tab-btn-cost-history") currentTab = "cost_history";
      else if (btn.id === "tab-btn-fiscal-pac") currentTab = "fiscal_pac";

      renderCurrentTabContent();
    });
  });

  // Eventos globales
  document.getElementById("btn-refresh-finances")?.addEventListener("click", () => {
    loadKPIs();
    renderCurrentTabContent();
  });

  document.getElementById("btn-run-reconciliation")?.addEventListener("click", executeAutomaticReconciliation);
  document.getElementById("btn-add-expense")?.addEventListener("click", openAddExpenseModal);

  // Cargar cuentas y KPIs iniciales
  await loadAccountsCache();
  await loadKPIs();
  await renderCurrentTabContent();
}

async function loadAccountsCache() {
  try {
    const res = await api.get("/meli-accounts");
    accountsCache = res.items || res || [];
  } catch (err) {
    accountsCache = [];
  }
}

async function loadKPIs() {
  try {
    const kpis = await api.get("/finances/kpis");
    document.getElementById("kpi-gross-amount").textContent = `$${kpis.gross_amount.toLocaleString("es-MX", { minimumFractionDigits: 2 })} MXN`;
    document.getElementById("kpi-estimated-net").textContent = `$${kpis.estimated_net_amount.toLocaleString("es-MX", { minimumFractionDigits: 2 })} MXN`;
    document.getElementById("kpi-accredited-funds").textContent = `$${kpis.accredited_amount.toLocaleString("es-MX", { minimumFractionDigits: 2 })} MXN`;
    document.getElementById("kpi-available-funds").textContent = `$${kpis.available_amount.toLocaleString("es-MX", { minimumFractionDigits: 2 })} MXN`;
    document.getElementById("kpi-withdrawn-funds").textContent = `$${kpis.withdrawn_amount.toLocaleString("es-MX", { minimumFractionDigits: 2 })} MXN`;
    document.getElementById("kpi-refunds-amount").textContent = `-$${kpis.refund_amount.toLocaleString("es-MX", { minimumFractionDigits: 2 })} MXN`;
    document.getElementById("kpi-definitive-charges").textContent = `-$${kpis.definitive_charge_amount.toLocaleString("es-MX", { minimumFractionDigits: 2 })} MXN`;
  } catch (err) {
    showToast("Error al cargar KPIs financieros", "error");
  }
}

async function renderCurrentTabContent() {
  const content = document.getElementById("finances-tab-content");
  if (!content) return;

  if (currentTab === "transactions") {
    await renderTransactionsTab(content);
  } else if (currentTab === "settlements") {
    await renderSettlementsTab(content);
  } else if (currentTab === "expenses") {
    await renderExpensesTab(content);
  } else if (currentTab === "reconciliation") {
    await renderReconciliationTab(content);
  } else if (currentTab === "reports") {
    await renderReportsTab(content);
  } else if (currentTab === "profitability") {
    await renderProfitabilityTab(content);
  } else if (currentTab === "loss_alerts") {
    await renderLossAlertsTab(content);
  } else if (currentTab === "simulator") {
    await renderSimulatorTab(content);
  } else if (currentTab === "cost_history") {
    await renderCostHistoryTab(content);
  } else if (currentTab === "fiscal_pac") {
    await renderFiscalPacTab(content);
  }
}

// ---------------------------------------------------------------------------
// TAB 1: TRANSACCIONES CONTABLES
// ---------------------------------------------------------------------------

async function renderTransactionsTab(content) {
  content.innerHTML = `
    <div class="space-y-4">
      <!-- Filtros de Transacciones -->
      <div class="p-4 bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3">
        <div class="flex-1 max-w-sm relative">
          <input 
            id="tx-search-input" 
            type="text" 
            placeholder="Buscar por concepto o folio..." 
            class="w-full px-3.5 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:ring-2 focus:ring-blue-600 focus:outline-none transition-smooth"
          />
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <select id="tx-type-filter" class="px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl font-bold text-slate-700 focus:outline-none">
            <option value="">Todos los Tipos</option>
            <option value="sale">Venta Bruta (sale)</option>
            <option value="marketplace_fee">Comisión MeLi</option>
            <option value="shipping_fee">Flete Mercado Envíos</option>
            <option value="tax_retention_iva">Retención SAT IVA</option>
            <option value="tax_retention_isr">Retención SAT ISR</option>
            <option value="refund">Reembolso</option>
            <option value="payout">Retiro / Payout</option>
            <option value="external_expense">Gasto Externo</option>
          </select>

          <select id="tx-status-filter" class="px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl font-bold text-slate-700 focus:outline-none">
            <option value="">Todos los Estados</option>
            <option value="accredited">Acreditado</option>
            <option value="available">Disponible</option>
            <option value="settled">Liquidado</option>
            <option value="withdrawn">Retirado</option>
            <option value="refunded">Reembolsado</option>
          </select>
        </div>
      </div>

      <!-- Tabla de Partidas -->
      <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-left border-collapse">
            <thead>
              <tr class="bg-slate-50 border-b border-slate-200 text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                <th class="p-3">Fecha & Origen</th>
                <th class="p-3">Tipo & Concepto</th>
                <th class="p-3">Importe Bruto</th>
                <th class="p-3">Comisiones MeLi</th>
                <th class="p-3">Impuestos SAT</th>
                <th class="p-3">Importe Neto</th>
                <th class="p-3 text-right">Estatus</th>
              </tr>
            </thead>
            <tbody id="tx-table-body" class="divide-y divide-slate-100 text-xs">
              <tr><td colspan="7" class="p-6 text-center text-slate-400">Cargando transacciones contables...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  async function loadTransactions() {
    const search = document.getElementById("tx-search-input")?.value || "";
    const type = document.getElementById("tx-type-filter")?.value || "";
    const status = document.getElementById("tx-status-filter")?.value || "";

    const params = { limit: 50 };
    if (search) params.search = search;
    if (type) params.transaction_type = type;
    if (status) params.status = status;

    const tbody = document.getElementById("tx-table-body");
    try {
      const res = await api.get("/finances/transactions", { params });
      const items = res.items || [];

      if (items.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="p-8 text-center text-slate-400 font-sans">No hay transacciones contables registradas para este criterio.</td></tr>`;
        return;
      }

      tbody.innerHTML = items.map((tx) => {
        const netColor = tx.net_amount >= 0 ? "text-emerald-700 font-bold" : "text-slate-700 font-semibold";
        const badgeColor = {
          accredited: "bg-amber-100 text-amber-800",
          available: "bg-emerald-100 text-emerald-800",
          settled: "bg-blue-100 text-blue-800",
          withdrawn: "bg-indigo-100 text-indigo-800",
          refunded: "bg-rose-100 text-rose-800",
          cancelled: "bg-slate-100 text-slate-700",
        }[tx.status] || "bg-slate-100 text-slate-700";

        return `
          <tr class="hover:bg-slate-50 transition-colors">
            <td class="p-3">
              <div class="font-bold text-slate-800">${new Date(tx.date_created).toLocaleDateString("es-MX")}</div>
              <div class="text-[10px] text-slate-400 font-mono">${new Date(tx.date_created).toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" })} • ${tx.source}</div>
            </td>
            <td class="p-3">
              <div class="font-bold text-slate-900">${tx.concept}</div>
              <div class="text-[10px] text-slate-400 font-mono">${tx.external_reference ? `Ref: #${tx.external_reference}` : tx.transaction_type}</div>
            </td>
            <td class="p-3 font-mono font-bold text-slate-900">$${tx.gross_amount.toFixed(2)}</td>
            <td class="p-3 font-mono text-amber-700">${tx.fee_amount > 0 ? `-$${tx.fee_amount.toFixed(2)}` : "$0.00"}</td>
            <td class="p-3 font-mono text-purple-700">${tx.tax_amount > 0 ? `-$${tx.tax_amount.toFixed(2)}` : "$0.00"}</td>
            <td class="p-3 font-mono ${netColor}">$${tx.net_amount.toFixed(2)}</td>
            <td class="p-3 text-right">
              <span class="inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold ${badgeColor}">
                ${tx.status.toUpperCase()}
              </span>
            </td>
          </tr>
        `;
      }).join("");
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="7" class="p-6 text-center text-rose-500">Error al consultar transacciones financieras.</td></tr>`;
    }
  }

  document.getElementById("tx-search-input")?.addEventListener("input", debounce(loadTransactions, 300));
  document.getElementById("tx-type-filter")?.addEventListener("change", loadTransactions);
  document.getElementById("tx-status-filter")?.addEventListener("change", loadTransactions);

  await loadTransactions();
}

// ---------------------------------------------------------------------------
// TAB 2: LIQUIDACIONES & RETIROS BANCARIOS
// ---------------------------------------------------------------------------

async function renderSettlementsTab(content) {
  content.innerHTML = `
    <div class="space-y-4">
      <div class="p-4 bg-white rounded-2xl border border-slate-200 shadow-sm flex items-center justify-between">
        <div>
          <h2 class="text-sm font-bold text-slate-900">Transferencias & Liquidaciones Mercado Pago</h2>
          <p class="text-xs text-slate-500 mt-0.5">Control de retiros de dinero disponible hacia cuentas bancarias CLABE.</p>
        </div>
        <button id="btn-create-settlement" class="px-3.5 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-bold transition-smooth shadow-sm flex items-center gap-1.5">
          ${icons.plus("w-4 h-4")} Registrar Liquidación
        </button>
      </div>

      <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-left border-collapse">
            <thead>
              <tr class="bg-slate-50 border-b border-slate-200 text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                <th class="p-3">Folio Liquidación</th>
                <th class="p-3">Periodo Liquidado</th>
                <th class="p-3">Banco / CLABE</th>
                <th class="p-3">Bruto Procesado</th>
                <th class="p-3">Deducciones (Comisión+SAT)</th>
                <th class="p-3 font-bold text-emerald-700">Neto Transferido</th>
                <th class="p-3 text-right">Estatus</th>
              </tr>
            </thead>
            <tbody id="settlements-table-body" class="divide-y divide-slate-100 text-xs font-mono">
              <tr><td colspan="7" class="p-6 text-center text-slate-400 font-sans">Cargando liquidaciones...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  document.getElementById("btn-create-settlement")?.addEventListener("click", openCreateSettlementModal);

  const tbody = document.getElementById("settlements-table-body");
  try {
    const res = await api.get("/finances/settlements");
    const items = res.items || [];

    if (items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="p-8 text-center text-slate-400 font-sans">No hay liquidaciones o transferencias registradas aún.</td></tr>`;
      return;
    }

    tbody.innerHTML = items.map((s) => {
      const deductions = s.total_fees + s.total_shipping_costs + s.total_taxes + s.total_refunds;
      return `
        <tr class="hover:bg-slate-50 transition-colors">
          <td class="p-3">
            <div class="font-bold text-slate-900">${s.settlement_number}</div>
            <div class="text-[10px] text-slate-400 font-sans">${s.meli_settlement_id || "Directo MP"}</div>
          </td>
          <td class="p-3 font-sans">
            <div class="font-medium text-slate-800">${new Date(s.period_start).toLocaleDateString("es-MX")} - ${new Date(s.period_end).toLocaleDateString("es-MX")}</div>
            <div class="text-[10px] text-slate-400">Transferido: ${s.date_settled ? new Date(s.date_settled).toLocaleDateString("es-MX") : "Pendiente"}</div>
          </td>
          <td class="p-3 font-sans">
            <div class="font-bold text-slate-800">${s.bank_name || "Cuenta Principal"}</div>
            <div class="text-[10px] text-slate-500 font-mono">${s.bank_account_clabe || "CLABE no registrada"}</div>
          </td>
          <td class="p-3 font-bold text-slate-900">$${s.gross_amount.toFixed(2)}</td>
          <td class="p-3 text-rose-700">-$${deductions.toFixed(2)}</td>
          <td class="p-3 font-bold text-emerald-700 text-sm">$${s.net_amount.toFixed(2)}</td>
          <td class="p-3 text-right">
            <span class="inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800">
              ${s.status.toUpperCase()}
            </span>
          </td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" class="p-6 text-center text-rose-500 font-sans">Error al consultar liquidaciones.</td></tr>`;
  }
}

// ---------------------------------------------------------------------------
// TAB 3: GASTOS EXTERNOS MANUALES
// ---------------------------------------------------------------------------

async function renderExpensesTab(content) {
  content.innerHTML = `
    <div class="space-y-4">
      <div class="p-4 bg-white rounded-2xl border border-slate-200 shadow-sm flex items-center justify-between">
        <div>
          <h2 class="text-sm font-bold text-slate-900">Gastos Operativos Externos</h2>
          <p class="text-xs text-slate-500 mt-0.5">Erogaciones manuales (Facebook Ads, empaque, software, nómina, fletes particulares).</p>
        </div>
        <button id="btn-add-expense-tab" class="px-3.5 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-bold transition-smooth shadow-sm flex items-center gap-1.5">
          ${icons.plus("w-4 h-4")} Registrar Gasto
        </button>
      </div>

      <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-left border-collapse">
            <thead>
              <tr class="bg-slate-50 border-b border-slate-200 text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                <th class="p-3">Fecha</th>
                <th class="p-3">Categoría</th>
                <th class="p-3">Concepto & Proveedor</th>
                <th class="p-3">Factura / Folio SAT</th>
                <th class="p-3">Método de Pago</th>
                <th class="p-3 text-right font-bold text-rose-700">Monto</th>
              </tr>
            </thead>
            <tbody id="expenses-table-body" class="divide-y divide-slate-100 text-xs">
              <tr><td colspan="6" class="p-6 text-center text-slate-400">Cargando gastos externos...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  document.getElementById("btn-add-expense-tab")?.addEventListener("click", openAddExpenseModal);

  const tbody = document.getElementById("expenses-table-body");
  try {
    const res = await api.get("/finances/expenses");
    const items = res.items || [];

    if (items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="p-8 text-center text-slate-400 font-sans">No hay gastos operativos registrados aún.</td></tr>`;
      return;
    }

    tbody.innerHTML = items.map((e) => `
      <tr class="hover:bg-slate-50 transition-colors">
        <td class="p-3 font-mono font-bold text-slate-800">${new Date(e.expense_date).toLocaleDateString("es-MX")}</td>
        <td class="p-3">
          <span class="inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-700 uppercase">
            ${e.category}
          </span>
        </td>
        <td class="p-3">
          <div class="font-bold text-slate-900">${e.concept}</div>
          <div class="text-[10px] text-slate-400">${e.vendor_name || "Proveedor no especificado"}</div>
        </td>
        <td class="p-3 font-mono text-slate-600">${e.invoice_folio || "Sin CFDI"}</td>
        <td class="p-3 capitalize text-slate-600">${e.payment_method.replace("_", " ")}</td>
        <td class="p-3 text-right font-mono font-black text-rose-700 text-sm">-$${e.amount.toFixed(2)}</td>
      </tr>
    `).join("");
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" class="p-6 text-center text-rose-500">Error al consultar gastos externos.</td></tr>`;
  }
}

// ---------------------------------------------------------------------------
// TAB 4: CONCILIACIÓN & DISCREPANCIAS
// ---------------------------------------------------------------------------

async function renderReconciliationTab(content) {
  content.innerHTML = `
    <div class="space-y-4">
      <div class="p-4 bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h2 class="text-sm font-bold text-slate-900">Motor de Conciliación Automática</h2>
          <p class="text-xs text-slate-500 mt-0.5">Compara ventas de órdenes vs cobros en Mercado Pago vs liquidaciones y retenciones SAT.</p>
        </div>
        <button id="btn-run-reconciliation-tab" class="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-xl text-xs font-bold transition-smooth shadow-sm flex items-center gap-1.5">
          ${icons.refresh("w-4 h-4")} Ejecutar Conciliación en Vivo
        </button>
      </div>

      <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-left border-collapse">
            <thead>
              <tr class="bg-slate-50 border-b border-slate-200 text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                <th class="p-3">Severidad & Tipo</th>
                <th class="p-3">Descripción de la Diferencia</th>
                <th class="p-3 font-mono">Esperado</th>
                <th class="p-3 font-mono">Real MeLi</th>
                <th class="p-3 font-mono">Diferencia</th>
                <th class="p-3">Estatus</th>
                <th class="p-3 text-right">Acción</th>
              </tr>
            </thead>
            <tbody id="discrepancies-table-body" class="divide-y divide-slate-100 text-xs">
              <tr><td colspan="7" class="p-6 text-center text-slate-400">Cargando discrepancias financieras...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  document.getElementById("btn-run-reconciliation-tab")?.addEventListener("click", executeAutomaticReconciliation);

  const tbody = document.getElementById("discrepancies-table-body");
  try {
    const res = await api.get("/finances/discrepancies");
    const items = res.items || [];

    if (items.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="7" class="p-8 text-center text-emerald-700 font-sans font-bold">
            🎉 ¡Felicidades! No se han detectado discrepancias financieras. 100% conciliado con Mercado Pago.
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = items.map((d) => {
      const sevBadge = {
        critical: "bg-rose-100 text-rose-800 border-rose-300",
        high: "bg-amber-100 text-amber-800 border-amber-300",
        medium: "bg-blue-100 text-blue-800 border-blue-300",
        low: "bg-slate-100 text-slate-700 border-slate-300",
      }[d.severity] || "bg-slate-100 text-slate-700";

      return `
        <tr class="hover:bg-slate-50 transition-colors">
          <td class="p-3">
            <span class="inline-flex px-2 py-0.5 rounded-full text-[10px] font-extrabold border ${sevBadge} uppercase">
              ${d.severity} • ${d.discrepancy_type.replace("_", " ")}
            </span>
            <div class="text-[10px] text-slate-400 font-mono mt-0.5">${new Date(d.detection_date).toLocaleDateString("es-MX")}</div>
          </td>
          <td class="p-3 font-medium text-slate-800 max-w-md">${d.description}</td>
          <td class="p-3 font-mono font-bold text-slate-700">$${d.expected_amount.toFixed(2)}</td>
          <td class="p-3 font-mono font-bold text-slate-900">$${d.actual_amount.toFixed(2)}</td>
          <td class="p-3 font-mono font-black text-rose-600">$${d.difference_amount.toFixed(2)}</td>
          <td class="p-3">
            <span class="inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold ${d.status === 'resolved' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'} uppercase">
              ${d.status}
            </span>
          </td>
          <td class="p-3 text-right">
            ${
              d.status !== "resolved"
                ? `<button onclick="window.resolveDiscrepancyModal('${d.id}')" class="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-[11px] font-bold transition-smooth">
                    Resolver
                   </button>`
                : `<span class="text-xs text-emerald-600 font-bold">Resuelto</span>`
            }
          </td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" class="p-6 text-center text-rose-500">Error al consultar discrepancias.</td></tr>`;
  }
}

// ---------------------------------------------------------------------------
// TAB 5: REPORTES FINANCIEROS (Por Cuenta, Por Producto, Por Periodo)
// ---------------------------------------------------------------------------

async function renderReportsTab(content) {
  content.innerHTML = `
    <div class="space-y-4">
      <div class="p-4 bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-wrap items-center justify-between gap-3">
        <div class="flex items-center gap-2">
          <button id="rep-subtab-accounts" class="px-3.5 py-1.5 rounded-xl text-xs font-bold bg-blue-600 text-white transition-smooth">
            Por Cuenta MeLi
          </button>
          <button id="rep-subtab-products" class="px-3.5 py-1.5 rounded-xl text-xs font-bold bg-slate-100 text-slate-600 hover:bg-slate-200 transition-smooth">
            Por Producto & SKU
          </button>
        </div>
        <div class="text-xs text-slate-400 font-medium">Rentabilidad real y auditoría contable</div>
      </div>

      <div id="report-view-container" class="space-y-4">
        <!-- Render dinámico del reporte seleccionado -->
      </div>
    </div>
  `;

  const btnAccounts = document.getElementById("rep-subtab-accounts");
  const btnProducts = document.getElementById("rep-subtab-products");
  const repContainer = document.getElementById("report-view-container");

  btnAccounts?.addEventListener("click", () => {
    btnAccounts.className = "px-3.5 py-1.5 rounded-xl text-xs font-bold bg-blue-600 text-white transition-smooth";
    btnProducts.className = "px-3.5 py-1.5 rounded-xl text-xs font-bold bg-slate-100 text-slate-600 hover:bg-slate-200 transition-smooth";
    loadAccountsReport(repContainer);
  });

  btnProducts?.addEventListener("click", () => {
    btnProducts.className = "px-3.5 py-1.5 rounded-xl text-xs font-bold bg-blue-600 text-white transition-smooth";
    btnAccounts.className = "px-3.5 py-1.5 rounded-xl text-xs font-bold bg-slate-100 text-slate-600 hover:bg-slate-200 transition-smooth";
    loadProductsReport(repContainer);
  });

  await loadAccountsReport(repContainer);
}

async function loadAccountsReport(container) {
  container.innerHTML = `<div class="p-8 text-center text-slate-400 font-sans">Generando reporte de cuentas MeLi...</div>`;
  try {
    const res = await api.get("/finances/reports/accounts");
    const accounts = res.accounts || [];

    if (accounts.length === 0) {
      container.innerHTML = `<div class="card p-8 text-center text-slate-400 font-sans">No hay cuentas de Mercado Libre vinculadas aún.</div>`;
      return;
    }

    container.innerHTML = `
      <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-left border-collapse">
            <thead>
              <tr class="bg-slate-50 border-b border-slate-200 text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                <th class="p-3">Tienda / Cuenta</th>
                <th class="p-3 text-right">Pedidos</th>
                <th class="p-3 text-right">Venta Bruta</th>
                <th class="p-3 text-right">Comisión MeLi</th>
                <th class="p-3 text-right">Fletes Vendedor</th>
                <th class="p-3 text-right">Retenciones SAT</th>
                <th class="p-3 text-right font-bold text-emerald-700">Saldo Disponible</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 text-xs font-mono">
              ${accounts.map((a) => `
                <tr class="hover:bg-slate-50 transition-colors">
                  <td class="p-3 font-sans font-bold text-slate-900">${a.nickname} (${a.site_id})</td>
                  <td class="p-3 text-right">${a.total_orders}</td>
                  <td class="p-3 text-right font-bold text-slate-900">$${a.gross_sales.toFixed(2)}</td>
                  <td class="p-3 text-right text-amber-700">-$${a.commissions_meli.toFixed(2)}</td>
                  <td class="p-3 text-right text-blue-700">-$${a.shipping_charges.toFixed(2)}</td>
                  <td class="p-3 text-right text-purple-700">-$${a.sat_taxes.toFixed(2)}</td>
                  <td class="p-3 text-right font-black text-emerald-700 text-sm">$${a.available_balance.toFixed(2)}</td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      </div>
    `;
  } catch (err) {
    container.innerHTML = `<div class="card p-6 text-center text-rose-500">Error al cargar reporte por cuentas.</div>`;
  }
}

async function loadProductsReport(container) {
  container.innerHTML = `<div class="p-8 text-center text-slate-400 font-sans">Generando reporte de rentabilidad por producto...</div>`;
  try {
    const res = await api.get("/finances/reports/products");
    const products = res.products || [];

    if (products.length === 0) {
      container.innerHTML = `<div class="card p-8 text-center text-slate-400 font-sans">No hay productos vendidos para calcular rentabilidad.</div>`;
      return;
    }

    container.innerHTML = `
      <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-left border-collapse">
            <thead>
              <tr class="bg-slate-50 border-b border-slate-200 text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                <th class="p-3">SKU & Producto</th>
                <th class="p-3 text-right">Uds.</th>
                <th class="p-3 text-right">Ventas Brutas</th>
                <th class="p-3 text-right">COGS (Costo)</th>
                <th class="p-3 text-right">Comisión MeLi</th>
                <th class="p-3 text-right">Fletes</th>
                <th class="p-3 text-right font-bold text-emerald-700">Utilidad Neta</th>
                <th class="p-3 text-right font-bold text-blue-700">Margen %</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 text-xs font-mono">
              ${products.map((p) => `
                <tr class="hover:bg-slate-50 transition-colors">
                  <td class="p-3 font-sans">
                    <div class="font-bold text-slate-900">${p.sku}</div>
                    <div class="text-[10px] text-slate-500 truncate max-w-xs">${p.product_name}</div>
                  </td>
                  <td class="p-3 text-right">${p.units_sold}</td>
                  <td class="p-3 text-right font-bold text-slate-900">$${p.gross_sales.toFixed(2)}</td>
                  <td class="p-3 text-right text-slate-600">-$${p.cogs_total.toFixed(2)}</td>
                  <td class="p-3 text-right text-amber-700">-$${p.commissions_meli.toFixed(2)}</td>
                  <td class="p-3 text-right text-blue-700">-$${p.shipping_costs.toFixed(2)}</td>
                  <td class="p-3 text-right font-black ${p.net_profit >= 0 ? 'text-emerald-700' : 'text-rose-700'}">$${p.net_profit.toFixed(2)}</td>
                  <td class="p-3 text-right font-black text-blue-700">${p.profit_margin_pct.toFixed(1)}%</td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      </div>
    `;
  } catch (err) {
    container.innerHTML = `<div class="card p-6 text-center text-rose-500">Error al cargar reporte por productos.</div>`;
  }
}

// ---------------------------------------------------------------------------
// MODALES Y ACCIONES
// ---------------------------------------------------------------------------

function openAddExpenseModal() {
  const content = `
    <form id="form-add-expense" class="space-y-4 text-xs">
      <div>
        <label class="block font-bold text-slate-700 mb-1">Concepto del Gasto *</label>
        <input id="exp-concept" type="text" required placeholder="Ej. Pauta en Facebook Ads Noviembre" class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none" />
      </div>

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="block font-bold text-slate-700 mb-1">Categoría *</label>
          <select id="exp-category" class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-bold">
            <option value="advertising">Publicidad & Marketing</option>
            <option value="packaging">Cajas & Material de Empaque</option>
            <option value="shipping">Fletes Externos</option>
            <option value="supplies">Insumos de Almacén</option>
            <option value="software">Software & Servicios</option>
            <option value="warehouse">Renta / Almacenaje</option>
            <option value="taxes">Impuestos / Contador</option>
            <option value="other">Otro Gasto</option>
          </select>
        </div>
        <div>
          <label class="block font-bold text-slate-700 mb-1">Monto en MXN *</label>
          <input id="exp-amount" type="number" step="0.01" min="0.01" required placeholder="0.00" class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-mono font-bold focus:bg-white focus:outline-none" />
        </div>
      </div>

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="block font-bold text-slate-700 mb-1">Fecha del Gasto *</label>
          <input id="exp-date" type="date" required value="${new Date().toISOString().split("T")[0]}" class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-mono" />
        </div>
        <div>
          <label class="block font-bold text-slate-700 mb-1">Método de Pago</label>
          <select id="exp-payment-method" class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl">
            <option value="bank_transfer">Transferencia SPEI</option>
            <option value="credit_card">Tarjeta de Crédito</option>
            <option value="debit_card">Tarjeta de Débito</option>
            <option value="cash">Efectivo</option>
            <option value="other">Otro</option>
          </select>
        </div>
      </div>

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="block font-bold text-slate-700 mb-1">Proveedor / Beneficiario</label>
          <input id="exp-vendor" type="text" placeholder="Ej. Meta Platforms Inc." class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none" />
        </div>
        <div>
          <label class="block font-bold text-slate-700 mb-1">Folio Fiscal SAT (UUID CFDI)</label>
          <input id="exp-invoice" type="text" placeholder="Folio o UUID de factura" class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-mono focus:bg-white focus:outline-none" />
        </div>
      </div>

      <div>
        <label class="block font-bold text-slate-700 mb-1">Notas u Observaciones</label>
        <textarea id="exp-notes" rows="2" placeholder="Detalles contables adicionales..." class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none"></textarea>
      </div>
    </form>
  `;

  openModal({
    title: "Registrar Gasto Operativo Externo",
    content,
    confirmText: "Guardar Gasto",
    size: "md",
    onConfirm: async () => {
      const concept = document.getElementById("exp-concept")?.value.trim();
      const category = document.getElementById("exp-category")?.value;
      const amount = parseFloat(document.getElementById("exp-amount")?.value);
      const dateVal = document.getElementById("exp-date")?.value;
      const paymentMethod = document.getElementById("exp-payment-method")?.value;
      const vendorName = document.getElementById("exp-vendor")?.value.trim() || null;
      const invoiceFolio = document.getElementById("exp-invoice")?.value.trim() || null;
      const notes = document.getElementById("exp-notes")?.value.trim() || null;

      if (!concept || isNaN(amount) || amount <= 0 || !dateVal) {
        showToast("Por favor complete los campos obligatorios.", "warning");
        return;
      }

      try {
        await api.post("/finances/expenses", {
          concept,
          category,
          amount,
          expense_date: new Date(dateVal).toISOString(),
          payment_method: paymentMethod,
          vendor_name: vendorName,
          invoice_folio: invoiceFolio,
          notes,
        });

        showToast("Gasto externo registrado con éxito.", "success");
        closeModal();
        await loadKPIs();
        renderCurrentTabContent();
      } catch (err) {
        showToast("Error al registrar gasto", "error");
      }
    },
  });
}

function openCreateSettlementModal() {
  const content = `
    <form id="form-add-settlement" class="space-y-4 text-xs">
      <div>
        <label class="block font-bold text-slate-700 mb-1">Cuenta Mercado Libre *</label>
        <select id="set-account" class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-bold">
          ${accountsCache.map((a) => `<option value="${a.id}">${a.nickname} (${a.site_id})</option>`).join("")}
        </select>
      </div>

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="block font-bold text-slate-700 mb-1">Folio de Liquidación *</label>
          <input id="set-folio" type="text" required placeholder="Ej. LIQ-${new Date().toISOString().slice(0, 10).replace(/-/g, "")}-001" class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-mono focus:bg-white focus:outline-none" />
        </div>
        <div>
          <label class="block font-bold text-slate-700 mb-1">ID Mercado Pago (Opcional)</label>
          <input id="set-meli-id" type="text" placeholder="Ej. PO-8839210" class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-mono focus:bg-white focus:outline-none" />
        </div>
      </div>

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="block font-bold text-slate-700 mb-1">Inicio Periodo *</label>
          <input id="set-start" type="date" required value="${new Date(Date.now() - 7 * 86400000).toISOString().split("T")[0]}" class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-mono" />
        </div>
        <div>
          <label class="block font-bold text-slate-700 mb-1">Fin Periodo *</label>
          <input id="set-end" type="date" required value="${new Date().toISOString().split("T")[0]}" class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-mono" />
        </div>
      </div>

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="block font-bold text-slate-700 mb-1">Monto Bruto Procesado *</label>
          <input id="set-gross" type="number" step="0.01" min="0" required placeholder="0.00" class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-mono focus:bg-white focus:outline-none" />
        </div>
        <div>
          <label class="block font-bold text-slate-700 mb-1">Neto Transferido a Banco *</label>
          <input id="set-net" type="number" step="0.01" min="0" required placeholder="0.00" class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-mono font-bold text-emerald-700 focus:bg-white focus:outline-none" />
        </div>
      </div>

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="block font-bold text-slate-700 mb-1">Banco Receptor</label>
          <input id="set-bank" type="text" placeholder="Ej. BBVA México" class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none" />
        </div>
        <div>
          <label class="block font-bold text-slate-700 mb-1">CLABE Bancaria (18 Dígitos)</label>
          <input id="set-clabe" type="text" maxlength="18" placeholder="0121800..." class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-mono focus:bg-white focus:outline-none" />
        </div>
      </div>
    </form>
  `;

  openModal({
    title: "Registrar Liquidación de Mercado Pago",
    content,
    confirmText: "Registrar Liquidación",
    size: "md",
    onConfirm: async () => {
      const accountId = document.getElementById("set-account")?.value;
      const folio = document.getElementById("set-folio")?.value.trim();
      const meliId = document.getElementById("set-meli-id")?.value.trim() || null;
      const start = document.getElementById("set-start")?.value;
      const end = document.getElementById("set-end")?.value;
      const gross = parseFloat(document.getElementById("set-gross")?.value);
      const net = parseFloat(document.getElementById("set-net")?.value);
      const bank = document.getElementById("set-bank")?.value.trim() || null;
      const clabe = document.getElementById("set-clabe")?.value.trim() || null;

      if (!accountId || !folio || !start || !end || isNaN(gross) || isNaN(net)) {
        showToast("Complete los campos obligatorios.", "warning");
        return;
      }

      try {
        await api.post("/finances/settlements", {
          meli_account_id: accountId,
          settlement_number: folio,
          meli_settlement_id: meliId,
          period_start: new Date(start).toISOString(),
          period_end: new Date(end).toISOString(),
          gross_amount: gross,
          net_amount: net,
          bank_name: bank,
          bank_account_clabe: clabe,
          date_settled: new Date().toISOString(),
        });

        showToast("Liquidación registrada exitosamente.", "success");
        closeModal();
        await loadKPIs();
        renderCurrentTabContent();
      } catch (err) {
        showToast("Error al registrar liquidación", "error");
      }
    },
  });
}

async function executeAutomaticReconciliation() {
  showToast("Ejecutando conciliación automática entre órdenes, pagos y liquidaciones...", "info");
  try {
    const res = await api.post("/finances/reconciliation/run");
    showToast(
      `Conciliación completada: ${res.matched_orders_count} órdenes cuadradas, ${res.discrepancies_found_count} diferencias detectadas.`,
      res.discrepancies_found_count === 0 ? "success" : "warning"
    );
    await loadKPIs();
    if (currentTab === "reconciliation") {
      renderCurrentTabContent();
    }
  } catch (err) {
    showToast("Error ejecutando conciliación", "error");
  }
}

window.resolveDiscrepancyModal = function (discId) {
  const content = `
    <div class="space-y-3 text-xs">
      <p class="text-slate-600">
        Indique el motivo o la acción correctiva que resuelve esta discrepancia contable:
      </p>
      <div>
        <label class="block font-bold text-slate-700 mb-1">Estatus</label>
        <select id="res-disc-status" class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-bold">
          <option value="resolved">Resuelta (Ajuste o comprobación realizada)</option>
          <option value="investigating">En Investigación (Con soporte de MeLi)</option>
          <option value="ignored">Ignorada (Diferencia aceptada / redondeo)</option>
        </select>
      </div>
      <div>
        <label class="block font-bold text-slate-700 mb-1">Notas de Resolución *</label>
        <textarea id="res-disc-notes" rows="3" required placeholder="Explicación detallada..." class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none"></textarea>
      </div>
    </div>
  `;

  openModal({
    title: "Resolver Discrepancia Financiera",
    content,
    confirmText: "Guardar Resolución",
    size: "sm",
    onConfirm: async () => {
      const statusVal = document.getElementById("res-disc-status")?.value;
      const notesVal = document.getElementById("res-disc-notes")?.value.trim();

      if (!notesVal) {
        showToast("Las notas de resolución son requeridas.", "warning");
        return;
      }

      try {
        await api.post(`/finances/discrepancies/${discId}/resolve`, {
          status: statusVal,
          resolution_notes: notesVal,
        });

        showToast("Discrepancia actualizada con éxito.", "success");
        closeModal();
        renderCurrentTabContent();
      } catch (err) {
        showToast("Error al resolver discrepancia", "error");
      }
    },
  });
};

function debounce(fn, delay) {
  let timer;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}

// ---------------------------------------------------------------------------
// TAB 6: MOTOR DE RENTABILIDAD MULTIDIMENSIONAL (8 DIMENSIONES)
// ---------------------------------------------------------------------------

async function renderProfitabilityTab(content) {
  content.innerHTML = `
    <div class="space-y-4">
      <!-- Filtros y Selector de Dimensión -->
      <div class="p-4 bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-3">
        <div class="flex flex-wrap items-center gap-2">
          <div>
            <label class="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Dimensión Analizada</label>
            <select id="prof-dimension-select" class="px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl font-bold text-slate-800 focus:bg-white focus:outline-none">
              <option value="product">1. Por Producto Maestro</option>
              <option value="sku" selected>2. Por SKU / Variante</option>
              <option value="item">3. Por Publicación MeLi (#MLM)</option>
              <option value="order">4. Por Pedido / Venta</option>
              <option value="account">5. Por Cuenta Mercado Libre</option>
              <option value="daily">6. Por Día (Línea de Tiempo)</option>
              <option value="weekly">7. Por Semana (ISO Semanal)</option>
              <option value="monthly">8. Por Mes Contable</option>
            </select>
          </div>

          <div>
            <label class="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Cuenta MeLi</label>
            <select id="prof-account-select" class="px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl font-medium text-slate-700 focus:bg-white focus:outline-none">
              <option value="">Todas las cuentas</option>
              ${accountsCache.map((acc) => `<option value="${acc.id}">${acc.nickname || acc.meli_user_id}</option>`).join("")}
            </select>
          </div>

          <div>
            <label class="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Fecha Desde</label>
            <input id="prof-date-from" type="date" class="px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl font-mono text-slate-700 focus:bg-white focus:outline-none" />
          </div>

          <div>
            <label class="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Fecha Hasta</label>
            <input id="prof-date-to" type="date" class="px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl font-mono text-slate-700 focus:bg-white focus:outline-none" />
          </div>
        </div>

        <div class="flex items-end gap-2">
          <button id="btn-run-profit-query" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-bold transition-smooth shadow-sm flex items-center gap-1.5 touch-target">
            ${icons.search ? icons.search("w-4 h-4") : ""} Calcular Rentabilidad
          </button>
        </div>
      </div>

      <!-- Resumen de Métricas Agregadas -->
      <div id="prof-summary-cards" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <div class="p-4 bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col justify-between">
          <div class="text-[10px] font-bold text-slate-400 uppercase">Facturación Neta Efectiva</div>
          <div id="prof-sum-net-revenue" class="text-xl font-black text-slate-900 mt-2 font-mono">...</div>
          <div id="prof-sum-gross-disc" class="text-[10px] text-slate-500 mt-1">Bruto: ... | Dctos: ...</div>
        </div>

        <div class="p-4 bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col justify-between">
          <div class="text-[10px] font-bold text-slate-400 uppercase">Costos Directos (COGS + Flete)</div>
          <div id="prof-sum-cogs-ship" class="text-xl font-black text-amber-700 mt-2 font-mono">...</div>
          <div id="prof-sum-cogs-detail" class="text-[10px] text-slate-500 mt-1">COGS: ... | Fletes: ...</div>
        </div>

        <div class="p-4 bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col justify-between">
          <div class="text-[10px] font-bold text-slate-400 uppercase">Comisiones & Retenciones SAT</div>
          <div id="prof-sum-fees-tax" class="text-xl font-black text-purple-700 mt-2 font-mono">...</div>
          <div id="prof-sum-fees-detail" class="text-[10px] text-slate-500 mt-1">MeLi: ... | SAT (IVA/ISR): ...</div>
        </div>

        <div class="p-4 bg-emerald-50 rounded-2xl border border-emerald-200 shadow-sm flex flex-col justify-between">
          <div class="text-[10px] font-bold text-emerald-800 uppercase flex items-center justify-between">
            <span>Utilidad Neta & Margen</span>
            <span id="prof-sum-margin-badge" class="px-2 py-0.5 bg-emerald-200 text-emerald-900 rounded-full font-mono text-[10px]">0.0%</span>
          </div>
          <div id="prof-sum-net-profit" class="text-xl font-black text-emerald-800 mt-2 font-mono">...</div>
          <div id="prof-sum-profit-status" class="text-[10px] text-emerald-700 mt-1 font-semibold">Estado de costos: ...</div>
        </div>
      </div>

      <!-- Diferenciación Explícita de Costos (Real vs Estimado vs Pendiente) -->
      <div class="p-4 bg-slate-50 rounded-2xl border border-slate-200 shadow-sm flex flex-col sm:flex-row items-center justify-between gap-3 text-xs">
        <div class="font-bold text-slate-700">Diferenciación de Costos del Periodo:</div>
        <div class="flex items-center gap-4 font-mono">
          <div class="flex items-center gap-1.5 text-blue-700">
            <span class="w-2.5 h-2.5 rounded-full bg-blue-600"></span>
            <span>Real (Auditado/Liquidado): <strong id="cost-status-real">$0.00</strong></span>
          </div>
          <div class="flex items-center gap-1.5 text-amber-700">
            <span class="w-2.5 h-2.5 rounded-full bg-amber-500"></span>
            <span>Pendiente (Devengado MeLi): <strong id="cost-status-pending">$0.00</strong></span>
          </div>
          <div class="flex items-center gap-1.5 text-slate-500">
            <span class="w-2.5 h-2.5 rounded-full bg-slate-400"></span>
            <span>Estimado (Proyectado): <strong id="cost-status-estimated">$0.00</strong></span>
          </div>
        </div>
      </div>

      <!-- Tabla Contable de 13 Conceptos -->
      <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-left border-collapse">
            <thead>
              <tr class="bg-slate-50 border-b border-slate-200 text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                <th class="p-3">Dimensión</th>
                <th class="p-3 text-right">Unidades</th>
                <th class="p-3 text-right">PVP Prom</th>
                <th class="p-3 text-right">Ingreso Bruto</th>
                <th class="p-3 text-right">Descuentos</th>
                <th class="p-3 text-right">Comisión MeLi</th>
                <th class="p-3 text-right">Cargo &lt;$299</th>
                <th class="p-3 text-right">Flete</th>
                <th class="p-3 text-right">COGS</th>
                <th class="p-3 text-right">Operativos</th>
                <th class="p-3 text-right">SAT (IVA/ISR)</th>
                <th class="p-3 text-right">Ganancia Neta</th>
                <th class="p-3 text-right">Margen %</th>
                <th class="p-3 text-center">Estado</th>
              </tr>
            </thead>
            <tbody id="prof-table-body" class="divide-y divide-slate-100 text-xs">
              <tr><td colspan="14" class="p-8 text-center text-slate-400">Cargando reporte de rentabilidad...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  document.getElementById("btn-run-profit-query")?.addEventListener("click", loadProfitabilityReport);
  document.getElementById("prof-dimension-select")?.addEventListener("change", loadProfitabilityReport);

  await loadProfitabilityReport();
}

async function loadProfitabilityReport() {
  const dim = document.getElementById("prof-dimension-select")?.value || "sku";
  const accountId = document.getElementById("prof-account-select")?.value || "";
  const dateFrom = document.getElementById("prof-date-from")?.value || "";
  const dateTo = document.getElementById("prof-date-to")?.value || "";

  const params = { dimension: dim };
  if (accountId) params.meli_account_id = accountId;
  if (dateFrom) params.date_from = dateFrom;
  if (dateTo) params.date_to = dateTo;

  const tbody = document.getElementById("prof-table-body");
  if (!tbody) return;

  try {
    const rep = await api.get("/profitability/reports", { params });

    // Actualizar Tarjetas Resumen
    document.getElementById("prof-sum-net-revenue").textContent = `$${rep.total_net_revenue.toLocaleString("es-MX", { minimumFractionDigits: 2 })} MXN`;
    document.getElementById("prof-sum-gross-disc").textContent = `Bruto: $${rep.total_gross_revenue.toFixed(2)} | Dctos: -$${rep.total_discounts.toFixed(2)}`;
    document.getElementById("prof-sum-cogs-ship").textContent = `$${(rep.total_cogs + rep.total_shipping).toLocaleString("es-MX", { minimumFractionDigits: 2 })} MXN`;
    document.getElementById("prof-sum-cogs-detail").textContent = `COGS: $${rep.total_cogs.toFixed(2)} | Fletes: $${rep.total_shipping.toFixed(2)}`;
    document.getElementById("prof-sum-fees-tax").textContent = `$${(rep.total_commissions + rep.total_fixed_charges + rep.total_taxes).toLocaleString("es-MX", { minimumFractionDigits: 2 })} MXN`;
    document.getElementById("prof-sum-fees-detail").textContent = `MeLi: $${(rep.total_commissions + rep.total_fixed_charges).toFixed(2)} | SAT: $${rep.total_taxes.toFixed(2)}`;
    document.getElementById("prof-sum-net-profit").textContent = `$${rep.total_net_profit.toLocaleString("es-MX", { minimumFractionDigits: 2 })} MXN`;
    document.getElementById("prof-sum-margin-badge").textContent = `${rep.overall_margin_pct.toFixed(1)}%`;

    // Diferenciación de costos
    if (rep.cost_status_summary) {
      document.getElementById("cost-status-real").textContent = `$${rep.cost_status_summary.real.toFixed(2)}`;
      document.getElementById("cost-status-pending").textContent = `$${rep.cost_status_summary.pending.toFixed(2)}`;
      document.getElementById("cost-status-estimated").textContent = `$${rep.cost_status_summary.estimated.toFixed(2)}`;
    }

    if (!rep.items || rep.items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="14" class="p-8 text-center text-slate-400 font-sans">No se encontraron movimientos contables para esta dimensión y rango de fechas.</td></tr>`;
      return;
    }

    tbody.innerHTML = rep.items.map((it) => {
      const isLoss = it.is_loss || it.net_profit < 0;
      const profitClass = isLoss ? "text-rose-700 font-bold" : "text-emerald-700 font-bold";
      const marginBadge = isLoss
        ? `<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-100 text-rose-800">${it.margin_pct.toFixed(1)}%</span>`
        : `<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800">${it.margin_pct.toFixed(1)}%</span>`;

      return `
        <tr class="hover:bg-slate-50 transition-colors ${isLoss ? "bg-rose-50/30" : ""}">
          <td class="p-3">
            <div class="font-bold text-slate-900">${it.dimension_name}</div>
            <div class="text-[10px] text-slate-400 font-mono">${it.dimension_id}</div>
          </td>
          <td class="p-3 text-right font-mono font-semibold text-slate-700">${it.units_sold}</td>
          <td class="p-3 text-right font-mono text-slate-700">$${it.sale_price_avg.toFixed(2)}</td>
          <td class="p-3 text-right font-mono font-bold text-slate-900">$${it.gross_revenue.toFixed(2)}</td>
          <td class="p-3 text-right font-mono text-slate-500">${it.discounts > 0 ? `-$${it.discounts.toFixed(2)}` : "$0.00"}</td>
          <td class="p-3 text-right font-mono text-amber-700">-$${it.commissions.toFixed(2)}</td>
          <td class="p-3 text-right font-mono ${it.fixed_charges > 0 ? "text-rose-600 font-bold" : "text-slate-400"}">${it.fixed_charges > 0 ? `-$${it.fixed_charges.toFixed(2)}` : "$0.00"}</td>
          <td class="p-3 text-right font-mono text-slate-600">-$${it.shipping_costs.toFixed(2)}</td>
          <td class="p-3 text-right font-mono text-slate-800 font-semibold">$${it.cogs_total.toFixed(2)}</td>
          <td class="p-3 text-right font-mono text-slate-500">-$${it.operational_expenses.toFixed(2)}</td>
          <td class="p-3 text-right font-mono text-purple-700">-$${it.applicable_taxes.toFixed(2)}</td>
          <td class="p-3 text-right font-mono ${profitClass}">$${it.net_profit.toFixed(2)}</td>
          <td class="p-3 text-right">${marginBadge}</td>
          <td class="p-3 text-center">
            ${isLoss ? `<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-600 text-white animate-pulse">PÉRDIDA</span>` : `<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-700">OK</span>`}
          </td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    showToast("Error al cargar reporte de rentabilidad", "error");
  }
}

// ---------------------------------------------------------------------------
// TAB 7: ALERTAS DE PRODUCTOS EN PÉRDIDA Y ANÁLISIS DE CAUSA RAÍZ
// ---------------------------------------------------------------------------

async function renderLossAlertsTab(content) {
  content.innerHTML = `
    <div class="space-y-4">
      <!-- Acciones de Detección -->
      <div class="p-4 bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h2 class="text-sm font-bold text-slate-900 flex items-center gap-2">
            ${icons.alert ? icons.alert("w-4 h-4 text-rose-600") : ""} Auditoría Financiera de Pérdidas & Margen Crítico
          </h2>
          <p class="text-xs text-slate-500 mt-0.5">
            Diagnostica productos donde el cargo fijo de $25 MXN (PVP &lt; $299), fletes altos o COGS generan rentabilidad negativa.
          </p>
        </div>

        <div class="flex items-center gap-2">
          <select id="loss-alert-status-filter" class="px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl font-bold text-slate-700">
            <option value="active">Alertas Activas</option>
            <option value="resolved">Resueltas</option>
            <option value="all">Todas</option>
          </select>
          <button id="btn-sync-loss-alerts" class="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-xl text-xs font-bold transition-smooth shadow-sm flex items-center gap-1.5 touch-target">
            ${icons.refresh ? icons.refresh("w-4 h-4") : ""} Sincronizar & Detectar
          </button>
        </div>
      </div>

      <!-- Contenedor de Tarjetas de Alerta -->
      <div id="loss-alerts-grid" class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div class="p-8 text-center text-slate-400 bg-white rounded-2xl border border-slate-200 col-span-2">
          Cargando alertas financieras...
        </div>
      </div>
    </div>
  `;

  document.getElementById("btn-sync-loss-alerts")?.addEventListener("click", async () => {
    showToast("Ejecutando motor de detección de pérdidas y causa raíz...", "info");
    try {
      const res = await api.post("/profitability/alerts/sync");
      showToast(`Auditoría completada: ${res.length} alertas identificadas.`, "success");
      await loadLossAlerts();
    } catch (err) {
      showToast("Error al sincronizar alertas de pérdida", "error");
    }
  });

  document.getElementById("loss-alert-status-filter")?.addEventListener("change", loadLossAlerts);

  await loadLossAlerts();
}

async function loadLossAlerts() {
  const statusFilter = document.getElementById("loss-alert-status-filter")?.value || "active";
  const grid = document.getElementById("loss-alerts-grid");
  if (!grid) return;

  try {
    const alerts = await api.get("/profitability/alerts", { params: { status_filter: statusFilter } });
    if (!alerts || alerts.length === 0) {
      grid.innerHTML = `
        <div class="p-8 text-center text-slate-400 bg-white rounded-2xl border border-slate-200 col-span-2">
          ¡Excelente! No hay alertas de pérdidas para este filtro. Todo el catálogo opera con margen saludable.
        </div>
      `;
      return;
    }

    grid.innerHTML = alerts.map((a) => {
      const isCritical = a.severity === "critical";
      const cardBorder = isCritical ? "border-rose-300 bg-rose-50/20" : "border-amber-300 bg-amber-50/20";
      const badgeColor = isCritical ? "bg-rose-600 text-white" : "bg-amber-500 text-white";

      return `
        <div class="p-5 rounded-2xl border ${cardBorder} shadow-sm bg-white flex flex-col justify-between space-y-3">
          <div class="flex items-start justify-between gap-2">
            <div>
              <span class="inline-flex px-2 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider ${badgeColor}">
                ${a.alert_type.toUpperCase()} • ${a.severity.toUpperCase()}
              </span>
              <h3 class="font-black text-slate-900 text-sm mt-1.5">${a.sku}</h3>
              <div class="text-xs text-slate-500 font-mono">Margen: ${a.current_margin_pct.toFixed(2)}% | Pérdida: -$${Math.abs(a.net_profit).toFixed(2)} MXN</div>
            </div>
            <div class="text-right">
              ${a.recommended_price ? `<div class="text-[10px] text-slate-400 font-bold uppercase">PVP Sugerido</div><div class="text-sm font-black text-emerald-700 font-mono">$${a.recommended_price.toFixed(2)}</div>` : ""}
            </div>
          </div>

          <div class="p-3 bg-slate-50 rounded-xl border border-slate-200 text-xs space-y-1.5">
            <div class="font-bold text-slate-800 flex items-center gap-1.5">
              ${icons.alert ? icons.alert("w-3.5 h-3.5 text-rose-600") : ""} Causa Raíz Detectada:
            </div>
            <p class="text-slate-600 leading-relaxed text-[11px]">${a.root_cause_analysis}</p>
          </div>

          <div class="p-3 bg-blue-50/50 rounded-xl border border-blue-100 text-xs space-y-1">
            <div class="font-bold text-blue-900 flex items-center gap-1.5">
              ${icons.check ? icons.check("w-3.5 h-3.5 text-blue-600") : ""} Acción Comercial Sugerida:
            </div>
            <p class="text-blue-800 leading-relaxed text-[11px]">${a.recommended_action}</p>
          </div>

          <div class="flex items-center justify-between pt-2 border-t border-slate-100 text-xs">
            <span class="text-slate-400 text-[10px] font-mono">Detectada: ${new Date(a.detected_at).toLocaleDateString("es-MX")}</span>
            ${a.status === "active" ? `
              <button onclick="resolveLossAlertModal('${a.id}')" class="px-3 py-1.5 bg-slate-900 hover:bg-slate-800 text-white rounded-lg text-xs font-bold transition-smooth">
                Resolver Alerta
              </button>
            ` : `
              <span class="text-emerald-700 font-bold text-[11px] flex items-center gap-1">
                ${icons.check ? icons.check("w-3.5 h-3.5") : ""} Resuelta: ${a.resolution_notes || "Sin nota"}
              </span>
            `}
          </div>
        </div>
      `;
    }).join("");
  } catch (err) {
    showToast("Error al consultar alertas", "error");
  }
}

window.resolveLossAlertModal = function (alertId) {
  const content = `
    <div class="space-y-3 text-xs">
      <p class="text-slate-600">
        Indique la estrategia comercial aplicada para eliminar la pérdida de este producto:
      </p>
      <div>
        <label class="block font-bold text-slate-700 mb-1">Notas de Resolución *</label>
        <textarea id="loss-res-notes" rows="3" required placeholder="Ej. Se elevó el precio a $299 MXN para eliminar el cargo fijo de $25 MXN y se armó paquete dual..." class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none"></textarea>
      </div>
    </div>
  `;

  openModal({
    title: "Resolver Alerta de Pérdida Financiera",
    content,
    confirmText: "Registrar Resolución",
    size: "sm",
    onConfirm: async () => {
      const notes = document.getElementById("loss-res-notes")?.value.trim();
      if (!notes) {
        showToast("Las notas de resolución son requeridas.", "warning");
        return;
      }

      try {
        await api.post(`/profitability/alerts/${alertId}/resolve`, {
          status: "resolved",
          resolution_notes: notes,
        });

        showToast("Alerta resuelta exitosamente.", "success");
        closeModal();
        await loadLossAlerts();
      } catch (err) {
        showToast("Error al resolver alerta", "error");
      }
    },
  });
};

// ---------------------------------------------------------------------------
// TAB 8: SIMULADOR DE PRECIOS PARA MARGEN OBJETIVO
// ---------------------------------------------------------------------------

async function renderSimulatorTab(content) {
  content.innerHTML = `
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
      <!-- Formulario de Parámetros de Entrada -->
      <div class="lg:col-span-5 p-5 bg-white rounded-2xl border border-slate-200 shadow-sm space-y-4">
        <div>
          <h2 class="text-sm font-black text-slate-900 flex items-center gap-2">
            ${icons.tag ? icons.tag("w-4 h-4 text-blue-600") : ""} Simulador Inverso de Precios
          </h2>
          <p class="text-xs text-slate-500 mt-0.5">
            Calcula algebraicamente el precio de venta exacto requerido para lograr el margen neto deseado, considerando saltos discontinuos ($25 si &lt; $299) y SAT.
          </p>
        </div>

        <form id="sim-form" class="space-y-3 text-xs">
          <div>
            <label class="block font-bold text-slate-700 mb-1">Costo Unitario de Adquisición (COGS) *</label>
            <input id="sim-cogs" type="number" step="0.01" min="1" required value="250.00" class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-mono font-bold text-slate-900 focus:bg-white focus:outline-none" />
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block font-bold text-slate-700 mb-1">Margen Neto Objetivo (%) *</label>
              <input id="sim-target-margin" type="number" step="0.5" min="1" max="90" required value="20.0" class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-mono font-bold text-emerald-700 focus:bg-white focus:outline-none" />
            </div>
            <div>
              <label class="block font-bold text-slate-700 mb-1">Comisión MeLi (%)</label>
              <input id="sim-commission" type="number" step="0.5" min="0" max="40" required value="15.0" class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-mono focus:bg-white focus:outline-none" />
            </div>
          </div>

          <div class="grid grid-cols-3 gap-3">
            <div>
              <label class="block font-bold text-slate-700 mb-1">Flete Vendedor ($)</label>
              <input id="sim-shipping" type="number" step="0.01" min="0" required value="85.00" class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-mono focus:bg-white focus:outline-none" />
            </div>
            <div>
              <label class="block font-bold text-slate-700 mb-1">Empaque ($)</label>
              <input id="sim-packaging" type="number" step="0.01" min="0" required value="15.00" class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-mono focus:bg-white focus:outline-none" />
            </div>
            <div>
              <label class="block font-bold text-slate-700 mb-1">Manipulación ($)</label>
              <input id="sim-handling" type="number" step="0.01" min="0" required value="10.00" class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-mono focus:bg-white focus:outline-none" />
            </div>
          </div>

          <div>
            <label class="block font-bold text-slate-700 mb-1">Régimen Fiscal SAT México *</label>
            <select id="sim-tax-regime" class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-bold text-slate-800 focus:bg-white focus:outline-none">
              <option value="persona_fisica_con_rfc">Persona Física con RFC (9% Retención: 8% IVA + 1% ISR)</option>
              <option value="persona_moral_con_rfc">Persona Moral con RFC (0% Retención por plataforma)</option>
              <option value="sin_rfc">Sin RFC (Sanción SAT del 36%: 16% IVA + 20% ISR)</option>
            </select>
          </div>

          <div>
            <label class="block font-bold text-slate-700 mb-1">Descuento Promocional ofrecido (%)</label>
            <input id="sim-discount" type="number" step="0.5" min="0" max="50" value="0.0" class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-mono focus:bg-white focus:outline-none" />
          </div>

          <button type="submit" class="w-full py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-bold transition-smooth shadow-sm flex items-center justify-center gap-2 touch-target mt-2">
            ${icons.search ? icons.search("w-4 h-4") : ""} Calcular Precio Objetivo
          </button>
        </form>
      </div>

      <!-- Resultados y Desglose Matemático -->
      <div class="lg:col-span-7 space-y-4">
        <div id="sim-result-card" class="p-6 bg-white rounded-2xl border border-slate-200 shadow-sm space-y-5">
          <div class="flex items-center justify-between border-b border-slate-100 pb-4">
            <div>
              <div class="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Precio Sugerido de Venta (PVP)</div>
              <div id="sim-res-price" class="text-3xl font-black text-slate-900 font-mono mt-1">$0.00 MXN</div>
            </div>
            <div class="text-right">
              <div class="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Margen Logrado</div>
              <div id="sim-res-margin" class="text-2xl font-black text-emerald-700 font-mono mt-1">0.0%</div>
            </div>
          </div>

          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
            <div class="p-3 bg-slate-50 rounded-xl">
              <div class="text-[10px] text-slate-400 uppercase font-bold">Ganancia Neta</div>
              <div id="sim-res-profit" class="font-mono font-black text-emerald-700 mt-1">$0.00</div>
            </div>
            <div class="p-3 bg-slate-50 rounded-xl">
              <div class="text-[10px] text-slate-400 uppercase font-bold">Comisión MeLi</div>
              <div id="sim-res-comm" class="font-mono font-bold text-amber-700 mt-1">$0.00</div>
            </div>
            <div class="p-3 bg-slate-50 rounded-xl">
              <div class="text-[10px] text-slate-400 uppercase font-bold">Cargo &lt;$299</div>
              <div id="sim-res-fixed" class="font-mono font-bold text-rose-600 mt-1">$0.00</div>
            </div>
            <div class="p-3 bg-slate-50 rounded-xl">
              <div class="text-[10px] text-slate-400 uppercase font-bold">Retención SAT</div>
              <div id="sim-res-taxes" class="font-mono font-bold text-purple-700 mt-1">$0.00</div>
            </div>
          </div>

          <div class="p-4 bg-emerald-50 rounded-xl border border-emerald-100 text-xs space-y-1">
            <div class="font-bold text-emerald-900 flex items-center justify-between">
              <span>Punto de Equilibrio (Break-Even Price):</span>
              <strong id="sim-res-breakeven" class="font-mono text-emerald-800">$0.00 MXN</strong>
            </div>
            <p class="text-emerald-700 text-[11px]">
              Precio mínimo para cubrir todos los costos y comisiones con margen 0.0%. Vender por debajo de este valor genera pérdida directa.
            </p>
          </div>
        </div>
      </div>
    </div>
  `;

  document.getElementById("sim-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const cogs = parseFloat(document.getElementById("sim-cogs").value);
    const targetMargin = parseFloat(document.getElementById("sim-target-margin").value);
    const comm = parseFloat(document.getElementById("sim-commission").value) / 100.0;
    const ship = parseFloat(document.getElementById("sim-shipping").value);
    const pack = parseFloat(document.getElementById("sim-packaging").value);
    const hand = parseFloat(document.getElementById("sim-handling").value);
    const regime = document.getElementById("sim-tax-regime").value;
    const disc = parseFloat(document.getElementById("sim-discount").value) / 100.0;

    try {
      const res = await api.post("/profitability/simulator/target-margin", {
        cogs,
        target_margin_pct: targetMargin,
        commission_rate: comm,
        shipping_cost: ship,
        packaging_cost: pack,
        handling_cost: hand,
        tax_regime: regime,
        discount_pct: disc,
      });

      document.getElementById("sim-res-price").textContent = `$${res.suggested_price.toFixed(2)} MXN`;
      document.getElementById("sim-res-margin").textContent = `${res.achieved_margin_pct.toFixed(2)}%`;
      document.getElementById("sim-res-profit").textContent = `$${res.net_profit.toFixed(2)}`;
      document.getElementById("sim-res-comm").textContent = `$${res.marketplace_fee.toFixed(2)}`;
      document.getElementById("sim-res-fixed").textContent = `$${res.fixed_fee.toFixed(2)}`;
      document.getElementById("sim-res-taxes").textContent = `$${res.total_taxes.toFixed(2)}`;
      document.getElementById("sim-res-breakeven").textContent = `$${res.break_even_price.toFixed(2)} MXN`;
    } catch (err) {
      showToast("Error ejecutando simulación de margen", "error");
    }
  });

  // Ejecutar primera simulación automática
  document.getElementById("sim-form")?.dispatchEvent(new Event("submit"));
}

// ---------------------------------------------------------------------------
// TAB 9: HISTORIAL INMUTABLE DE COSTOS (COGS)
// ---------------------------------------------------------------------------

async function renderCostHistoryTab(content) {
  content.innerHTML = `
    <div class="space-y-4">
      <div class="p-4 bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h2 class="text-sm font-bold text-slate-900 flex items-center gap-2">
            ${icons.list ? icons.list("w-4 h-4 text-blue-600") : ""} Trazabilidad e Historial Inmutable de Costos (COGS)
          </h2>
          <p class="text-xs text-slate-500 mt-0.5">
            Conserva el histórico de cada variación de costo con motivo justificado, permitiendo auditoría retroactiva de ganancias por fecha de venta.
          </p>
        </div>

        <div class="flex items-center gap-2">
          <input id="cost-hist-sku-filter" type="text" placeholder="Filtrar por SKU..." class="px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none" />
          <button id="btn-add-cost-record" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-bold transition-smooth shadow-sm flex items-center gap-1.5 touch-target">
            ${icons.plus ? icons.plus("w-4 h-4") : ""} Registrar Cambio de Costo
          </button>
        </div>
      </div>

      <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-left border-collapse">
            <thead>
              <tr class="bg-slate-50 border-b border-slate-200 text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                <th class="p-3">Fecha & Vigencia</th>
                <th class="p-3">SKU</th>
                <th class="p-3 text-right">Costo Anterior</th>
                <th class="p-3 text-right">Nuevo Costo</th>
                <th class="p-3 text-right">Variación (%)</th>
                <th class="p-3">Motivo del Cambio</th>
                <th class="p-3">Notas de Auditoría</th>
              </tr>
            </thead>
            <tbody id="cost-hist-table-body" class="divide-y divide-slate-100 text-xs">
              <tr><td colspan="7" class="p-6 text-center text-slate-400">Cargando historial de costos...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  document.getElementById("btn-add-cost-record")?.addEventListener("click", openAddCostRecordModal);
  document.getElementById("cost-hist-sku-filter")?.addEventListener("input", debounce(loadCostHistory, 300));

  await loadCostHistory();
}

async function loadCostHistory() {
  const sku = document.getElementById("cost-hist-sku-filter")?.value.trim() || "";
  const tbody = document.getElementById("cost-hist-table-body");
  if (!tbody) return;

  const params = {};
  if (sku) params.sku = sku;

  try {
    const list = await api.get("/profitability/costs/history", { params });
    if (!list || list.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="p-8 text-center text-slate-400">No hay registros de cambios de costo en el historial.</td></tr>`;
      return;
    }

    tbody.innerHTML = list.map((c) => {
      const varPct = c.previous_cogs > 0 ? (((c.new_cogs - c.previous_cogs) / c.previous_cogs) * 100.0).toFixed(1) : "0.0";
      const varColor = parseFloat(varPct) > 0 ? "text-rose-600 font-bold" : "text-emerald-600 font-bold";

      return `
        <tr class="hover:bg-slate-50 transition-colors">
          <td class="p-3">
            <div class="font-bold text-slate-900">${new Date(c.effective_from).toLocaleDateString("es-MX")}</div>
            <div class="text-[10px] text-slate-400 font-mono">${new Date(c.created_at).toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" })}</div>
          </td>
          <td class="p-3 font-mono font-bold text-slate-800">${c.sku}</td>
          <td class="p-3 text-right font-mono text-slate-500">$${c.previous_cogs.toFixed(2)}</td>
          <td class="p-3 text-right font-mono font-black text-slate-900">$${c.new_cogs.toFixed(2)}</td>
          <td class="p-3 text-right font-mono ${varColor}">${parseFloat(varPct) > 0 ? `+${varPct}%` : `${varPct}%`}</td>
          <td class="p-3">
            <span class="inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-700">
              ${c.change_reason}
            </span>
          </td>
          <td class="p-3 text-slate-600 text-[11px]">${c.notes || "Sin observaciones"}</td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    showToast("Error al cargar historial de costos", "error");
  }
}

function openAddCostRecordModal() {
  const content = `
    <form id="form-add-cost" class="space-y-3 text-xs">
      <div>
        <label class="block font-bold text-slate-700 mb-1">SKU del Producto *</label>
        <input id="add-cost-sku" type="text" required placeholder="Ej. SMART-GPS-BLK" class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-mono focus:bg-white focus:outline-none" />
      </div>

      <div>
        <label class="block font-bold text-slate-700 mb-1">Nuevo Costo de Adquisición (COGS) *</label>
        <input id="add-cost-value" type="number" step="0.01" min="0.01" required placeholder="0.00" class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-mono font-bold text-slate-900 focus:bg-white focus:outline-none" />
      </div>

      <div>
        <label class="block font-bold text-slate-700 mb-1">Motivo Obligatorio del Cambio *</label>
        <select id="add-cost-reason" class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-bold text-slate-800">
          <option value="supplier_increase">Incremento de Proveedor</option>
          <option value="purchase_order">Nueva Orden de Compra (Lote)</option>
          <option value="currency_devaluation">Ajuste Cambiario (USD / MXN)</option>
          <option value="manufacturing_cost">Variación en Costo de Fabricación</option>
          <option value="audit_adjustment">Ajuste de Auditoría Interna</option>
        </select>
      </div>

      <div>
        <label class="block font-bold text-slate-700 mb-1">Notas Explicativas / Factura Proveedor</label>
        <textarea id="add-cost-notes" rows="2" placeholder="Detalles de la compra o número de factura..." class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none"></textarea>
      </div>
    </form>
  `;

  openModal({
    title: "Registrar Cambio Inmutable de Costo COGS",
    content,
    confirmText: "Registrar Costo",
    size: "sm",
    onConfirm: async () => {
      const sku = document.getElementById("add-cost-sku")?.value.trim();
      const newCogs = parseFloat(document.getElementById("add-cost-value")?.value);
      const reason = document.getElementById("add-cost-reason")?.value;
      const notes = document.getElementById("add-cost-notes")?.value.trim();

      if (!sku || isNaN(newCogs) || !reason) {
        showToast("Complete los campos requeridos.", "warning");
        return;
      }

      try {
        await api.post("/profitability/costs/history", {
          sku,
          new_cogs: newCogs,
          change_reason: reason,
          notes,
        });

        showToast("Costo registrado exitosamente.", "success");
        closeModal();
        await loadCostHistory();
      } catch (err) {
        showToast("Error al registrar costo", "error");
      }
    },
  });
}

// ---------------------------------------------------------------------------
// TAB 10: INTEGRACIÓN FISCAL MEXICANA (PAC / CFDI 4.0 / SAT)
// ---------------------------------------------------------------------------

async function renderFiscalPacTab(content) {
  content.innerHTML = `
    <div class="space-y-6">
      <!-- Configuración del PAC SAT -->
      <div class="p-5 bg-white rounded-2xl border border-slate-200 shadow-sm space-y-4">
        <div class="flex items-center justify-between border-b border-slate-100 pb-3">
          <div>
            <h2 class="text-sm font-black text-slate-900 flex items-center gap-2">
              ${icons.shield ? icons.shield("w-4 h-4 text-purple-600") : ""} Conector de Proveedor Autorizado de Certificación (PAC SAT)
            </h2>
            <p class="text-xs text-slate-500 mt-0.5">
              Preparado para Facturapi, Finkok o SW Sapience. Emisión y timbrado oficial de CFDI 4.0 con retenciones MeLi (IVA 8% + ISR 1%).
            </p>
          </div>
          <button id="btn-save-pac-config" class="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-xl text-xs font-bold transition-smooth shadow-sm">
            Guardar Configuración PAC
          </button>
        </div>

        <form id="pac-config-form" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 text-xs">
          <div>
            <label class="block font-bold text-slate-700 mb-1">Proveedor PAC Autorizado *</label>
            <select id="pac-provider" class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-bold">
              <option value="facturapi">Facturapi (API CFDI 4.0)</option>
              <option value="finkok">Finkok PAC</option>
              <option value="sw_sapience">SW Sapience</option>
            </select>
          </div>

          <div>
            <label class="block font-bold text-slate-700 mb-1">Entorno de Timbrado *</label>
            <select id="pac-env" class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-bold">
              <option value="sandbox">Sandbox (Pruebas SAT)</option>
              <option value="production">Producción (Fiscal Real)</option>
            </select>
          </div>

          <div>
            <label class="block font-bold text-slate-700 mb-1">Clave API Secreta PAC *</label>
            <input id="pac-key" type="password" placeholder="sk_test_..." class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-mono focus:bg-white focus:outline-none" />
          </div>

          <div>
            <label class="block font-bold text-slate-700 mb-1">RFC Emisor Oficial *</label>
            <input id="pac-rfc" type="text" placeholder="AAA010101AAA" maxlength="13" class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-mono uppercase focus:bg-white focus:outline-none" />
          </div>

          <div>
            <label class="block font-bold text-slate-700 mb-1">Razón Social Emisor *</label>
            <input id="pac-razon" type="text" placeholder="Mi Empresa S.A. de C.V." class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none" />
          </div>

          <div>
            <label class="block font-bold text-slate-700 mb-1">Régimen Fiscal SAT *</label>
            <select id="pac-regimen" class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl font-bold">
              <option value="601">601 - General de Ley Personas Morales</option>
              <option value="612">612 - Personas Físicas con Actividades Empresariales</option>
              <option value="626">626 - Régimen Simplificado de Confianza (RESICO)</option>
              <option value="625">625 - Régimen de las Actividades Empresariales con Plataformas Tecnológicas</option>
            </select>
          </div>
        </form>
      </div>

      <!-- Facturas Timbradas -->
      <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="p-4 border-b border-slate-100 flex items-center justify-between">
          <h3 class="font-black text-slate-900 text-sm">Registro de Facturas Timbradas (CFDI 4.0)</h3>
          <span class="text-xs text-slate-400 font-mono">Retenciones SAT Oficiales</span>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-left border-collapse">
            <thead>
              <tr class="bg-slate-50 border-b border-slate-200 text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                <th class="p-3">Fecha & Folio</th>
                <th class="p-3">UUID Fiscal SAT</th>
                <th class="p-3">Receptor</th>
                <th class="p-3 text-right">Subtotal</th>
                <th class="p-3 text-right">Retención IVA (8%)</th>
                <th class="p-3 text-right">Retención ISR (1%)</th>
                <th class="p-3 text-right">Total Factura</th>
                <th class="p-3 text-center">Estatus</th>
              </tr>
            </thead>
            <tbody id="fiscal-invoices-body" class="divide-y divide-slate-100 text-xs">
              <tr><td colspan="8" class="p-6 text-center text-slate-400">Cargando facturas fiscales...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  document.getElementById("btn-save-pac-config")?.addEventListener("click", savePacConfig);

  await loadPacConfig();
  await loadFiscalInvoices();
}

async function loadPacConfig() {
  try {
    const cfg = await api.get("/profitability/fiscal/config");
    if (cfg) {
      document.getElementById("pac-provider").value = cfg.pac_provider || "facturapi";
      document.getElementById("pac-env").value = cfg.environment || "sandbox";
      document.getElementById("pac-rfc").value = cfg.rfc_emisor || "";
      document.getElementById("pac-razon").value = cfg.razon_social || "";
      document.getElementById("pac-regimen").value = cfg.regimen_fiscal_sat || "626";
    }
  } catch (err) {
    // Configuración inicial no creada
  }
}

async function savePacConfig() {
  const provider = document.getElementById("pac-provider")?.value;
  const env = document.getElementById("pac-env")?.value;
  const apiKey = document.getElementById("pac-key")?.value.trim();
  const rfc = document.getElementById("pac-rfc")?.value.trim();
  const razon = document.getElementById("pac-razon")?.value.trim();
  const regimen = document.getElementById("pac-regimen")?.value;

  if (!rfc || !razon) {
    showToast("RFC y Razón Social son requeridos.", "warning");
    return;
  }

  try {
    await api.post("/profitability/fiscal/config", {
      pac_provider: provider,
      environment: env,
      api_key: apiKey || "sandbox_test_key",
      rfc_emisor: rfc,
      razon_social: razon,
      regimen_fiscal_sat: regimen,
    });

    showToast("Configuración fiscal PAC guardada exitosamente.", "success");
  } catch (err) {
    showToast("Error al guardar configuración PAC", "error");
  }
}

async function loadFiscalInvoices() {
  const tbody = document.getElementById("fiscal-invoices-body");
  if (!tbody) return;

  try {
    const invoices = await api.get("/profitability/fiscal/invoices");
    if (!invoices || invoices.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="p-8 text-center text-slate-400">No hay comprobantes fiscales timbrados todavía.</td></tr>`;
      return;
    }

    tbody.innerHTML = invoices.map((inv) => `
      <tr class="hover:bg-slate-50 transition-colors">
        <td class="p-3">
          <div class="font-bold text-slate-900">${new Date(inv.date_stamped || inv.created_at).toLocaleDateString("es-MX")}</div>
          <div class="text-[10px] text-slate-400 font-mono">${inv.invoice_series || "F"}-${inv.invoice_number || "1"}</div>
        </td>
        <td class="p-3 font-mono text-[11px] text-slate-700">${inv.uuid_sat || "PENDIENTE"}</td>
        <td class="p-3">
          <div class="font-bold text-slate-900">${inv.razon_social_receptor || "PÚBLICO EN GENERAL"}</div>
          <div class="text-[10px] text-slate-400 font-mono">${inv.rfc_receptor}</div>
        </td>
        <td class="p-3 text-right font-mono text-slate-700">$${inv.subtotal.toFixed(2)}</td>
        <td class="p-3 text-right font-mono text-purple-700">-$${inv.iva_retention.toFixed(2)}</td>
        <td class="p-3 text-right font-mono text-purple-700">-$${inv.isr_retention.toFixed(2)}</td>
        <td class="p-3 text-right font-mono font-black text-slate-900">$${inv.total.toFixed(2)}</td>
        <td class="p-3 text-center">
          <span class="inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 uppercase">
            ${inv.status}
          </span>
        </td>
      </tr>
    `).join("");
  } catch (err) {
    showToast("Error al cargar facturas fiscales", "error");
  }
}

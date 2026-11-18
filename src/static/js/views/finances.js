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
            ${icons.cash} Módulo Financiero & Conciliación MeLi
          </h1>
          <p class="text-xs text-slate-500 mt-1">
            Auditoría de Mercado Pago, retenciones fiscales SAT (IVA 8%, ISR 1%), flujo de caja y liquidaciones bancarias.
          </p>
        </div>

        <div class="flex items-center gap-2">
          <button id="btn-run-reconciliation" class="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-xl text-xs font-bold transition-smooth shadow-sm flex items-center gap-1.5 touch-target">
            ${icons.refresh} Conciliación Automática
          </button>
          <button id="btn-add-expense" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-bold transition-smooth shadow-sm flex items-center gap-1.5 touch-target">
            ${icons.plus} Registrar Gasto Externo
          </button>
          <button id="btn-refresh-finances" class="p-2 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 rounded-xl transition-smooth shadow-sm touch-target" title="Recargar">
            ${icons.refresh}
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
        <button id="tab-btn-transactions" class="fin-tab-btn px-4 py-2.5 border-b-2 border-blue-600 text-blue-600 flex items-center gap-1.5 transition-smooth">
          ${icons.list || icons.tag} Partidas & Transacciones
        </button>
        <button id="tab-btn-settlements" class="fin-tab-btn px-4 py-2.5 border-b-2 border-transparent text-slate-500 hover:text-slate-800 flex items-center gap-1.5 transition-smooth">
          ${icons.cash || icons.check} Liquidaciones & Retiros
        </button>
        <button id="tab-btn-expenses" class="fin-tab-btn px-4 py-2.5 border-b-2 border-transparent text-slate-500 hover:text-slate-800 flex items-center gap-1.5 transition-smooth">
          ${icons.box || icons.tag} Gastos Externos Manuales
        </button>
        <button id="tab-btn-reconciliation" class="fin-tab-btn px-4 py-2.5 border-b-2 border-transparent text-slate-500 hover:text-slate-800 flex items-center gap-1.5 transition-smooth">
          ${icons.shield || icons.alert} Conciliación & Discrepancias
        </button>
        <button id="tab-btn-reports" class="fin-tab-btn px-4 py-2.5 border-b-2 border-transparent text-slate-500 hover:text-slate-800 flex items-center gap-1.5 transition-smooth">
          ${icons.chart} Reportes Financieros
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
          ${icons.plus} Registrar Liquidación
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
          ${icons.plus} Registrar Gasto
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
          ${icons.refresh} Ejecutar Conciliación en Vivo
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

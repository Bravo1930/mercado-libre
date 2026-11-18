/**
 * Vista 2: Ventas (Pedidos de Mercado Libre México).
 * Incluye filtros por estatus y fecha, tabla de órdenes, paginación y modal con desglose de rentabilidad SAT.
 */

import { api } from "../api.js";
import { state } from "../state.js";
import { icons } from "../icons.js";
import { openModal } from "../components/modal.js";
import { showToast } from "../components/toast.js";

export function renderOrdersView() {
  const container = document.createElement("div");
  container.className = "space-y-5 animate-fade-in";

  let currentPage = 1;
  let currentStatus = "";
  let searchFilter = "";

  function renderSkeleton() {
    return Array.from({ length: 5 }).map(() => `
      <tr class="animate-pulse">
        <td class="py-4 px-4"><div class="h-4 bg-slate-200 rounded w-24"></div></td>
        <td class="py-4 px-4"><div class="h-4 bg-slate-200 rounded w-32"></div></td>
        <td class="py-4 px-4"><div class="h-4 bg-slate-200 rounded w-16"></div></td>
        <td class="py-4 px-4"><div class="h-4 bg-slate-200 rounded w-20"></div></td>
        <td class="py-4 px-4"><div class="h-4 bg-slate-200 rounded w-20"></div></td>
        <td class="py-4 px-4"><div class="h-4 bg-slate-200 rounded w-16 ml-auto"></div></td>
      </tr>
    `).join("");
  }

  container.innerHTML = `
    <!-- Encabezado de Sección -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
      <div>
        <h2 class="text-2xl font-black text-slate-900 tracking-tight">Ventas & Pedidos</h2>
        <p class="text-xs text-slate-500 mt-0.5">Gestión de órdenes sincronizadas de Mercado Libre México y rentabilidad SAT</p>
      </div>

      <div class="flex items-center space-x-2">
        <button id="btn-refresh-orders" class="p-2.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 rounded-xl transition-smooth shadow-sm touch-target" title="Recargar">
          ${icons.refresh("w-4 h-4")}
        </button>
      </div>
    </div>

    <!-- Barra de Filtros y Búsqueda -->
    <div class="p-4 bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3">
      <div class="flex-1 max-w-sm relative">
        <span class="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
          ${icons.search("w-4 h-4")}
        </span>
        <input 
          id="orders-search-input" 
          type="text" 
          placeholder="Buscar por ID de orden MeLi..." 
          class="w-full pl-9 pr-3.5 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:ring-2 focus:ring-blue-600 focus:outline-none transition-smooth"
        />
      </div>

      <div class="flex items-center space-x-2 overflow-x-auto">
        <select id="orders-status-filter" class="px-3 py-2 text-xs font-semibold bg-slate-50 border border-slate-200 rounded-xl text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-600">
          <option value="">Todos los Estatus</option>
          <option value="paid">Pagado (paid)</option>
          <option value="pending">Pendiente (pending)</option>
          <option value="cancelled">Cancelado (cancelled)</option>
        </select>
      </div>
    </div>

    <!-- Tabla Principal de Órdenes -->
    <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <div class="table-container">
        <table class="w-full text-left text-xs border-collapse">
          <thead>
            <tr class="border-b border-slate-200 bg-slate-50/70 text-slate-500 font-bold uppercase tracking-wider text-[10px]">
              <th class="py-3 px-4">Orden MeLi</th>
              <th class="py-3 px-4">Fecha Creación</th>
              <th class="py-3 px-4">Estatus</th>
              <th class="py-3 px-4">Partidas</th>
              <th class="py-3 px-4">Total Venta</th>
              <th class="py-3 px-4">Utilidad Neta</th>
              <th class="py-3 px-4 text-right">Acciones</th>
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
  `;

  // Controladores de eventos
  const searchInput = container.querySelector("#orders-search-input");
  const statusSelect = container.querySelector("#orders-status-filter");
  const btnRefresh = container.querySelector("#btn-refresh-orders");
  const btnPrev = container.querySelector("#btn-prev-page");
  const btnNext = container.querySelector("#btn-next-page");

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

  if (btnRefresh) {
    btnRefresh.addEventListener("click", () => fetchOrders());
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

  async function fetchOrders() {
    const tbody = container.querySelector("#orders-table-tbody");
    tbody.innerHTML = renderSkeleton();

    try {
      const params = {
        page: currentPage,
        size: 15,
      };
      if (currentStatus) params.status = currentStatus;

      const data = await api.get("/orders", params);
      const items = data.items || [];

      // Filtrado local por ID si se escribe en el buscador
      const filtered = searchFilter
        ? items.filter(o => String(o.meli_order_id).includes(searchFilter))
        : items;

      if (filtered.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="7" class="py-12 text-center text-slate-400">
              No se encontraron ventas con los criterios aplicados.
            </td>
          </tr>
        `;
      } else {
        tbody.innerHTML = filtered.map(o => {
          const profit = o.profitability ? Number(o.profitability.net_profit || 0) : 0;
          const statusClass = o.status === 'paid' ? 'badge-success' : (o.status === 'cancelled' ? 'badge-danger' : 'badge-warning');
          const itemsCount = (o.items || []).length;

          return `
            <tr class="hover:bg-slate-50/80 transition-smooth">
              <td class="py-3.5 px-4 font-mono font-bold text-slate-900">#${o.meli_order_id}</td>
              <td class="py-3.5 px-4 text-slate-500">${new Date(o.date_created_meli).toLocaleString('es-MX', { dateStyle: 'short', timeStyle: 'short' })}</td>
              <td class="py-3.5 px-4"><span class="badge ${statusClass} uppercase text-[10px]">${o.status}</span></td>
              <td class="py-3.5 px-4 font-semibold text-slate-700">${itemsCount} producto(s)</td>
              <td class="py-3.5 px-4 font-bold text-slate-900">$ ${Number(o.total_amount).toFixed(2)}</td>
              <td class="py-3.5 px-4 font-bold text-emerald-600">$ ${profit.toFixed(2)}</td>
              <td class="py-3.5 px-4 text-right">
                <button data-order-id="${o.id}" class="btn-view-order px-2.5 py-1.5 text-xs font-semibold text-blue-600 hover:text-blue-800 bg-blue-50 hover:bg-blue-100 rounded-lg transition-smooth">
                  Ver Auditoría
                </button>
              </td>
            </tr>
          `;
        }).join("");

        // Bind clicks para detalle
        tbody.querySelectorAll(".btn-view-order").forEach(btn => {
          btn.addEventListener("click", () => {
            const orderId = btn.getAttribute("data-order-id");
            openOrderDetailModal(orderId);
          });
        });
      }

      // Actualizar Paginación
      const infoEl = container.querySelector("#orders-pagination-info");
      if (infoEl) infoEl.textContent = `Página ${data.page} de ${data.pages || 1} (${data.total} pedidos en total)`;

      if (btnPrev) btnPrev.disabled = !data.has_prev;
      if (btnNext) btnNext.disabled = !data.has_next;

    } catch (err) {
      tbody.innerHTML = `
        <tr>
          <td colspan="7" class="py-8 text-center text-red-600 font-semibold">
            Error al consultar ventas: ${err.message}
          </td>
        </tr>
      `;
    }
  }

  async function openOrderDetailModal(orderId) {
    try {
      const order = await api.get(`/orders/${orderId}`);
      const prof = order.profitability || {};

      const itemsHtml = (order.items || []).map(it => `
        <div class="flex items-center justify-between p-3 rounded-xl bg-slate-50 border border-slate-100 text-xs">
          <div>
            <p class="font-bold text-slate-900">${it.title}</p>
            <p class="text-[11px] font-mono text-slate-500">MLM Item: ${it.meli_item_id} · Cantidad: ${it.quantity}</p>
          </div>
          <div class="text-right">
            <span class="block font-bold text-slate-900">$ ${(it.unit_price * it.quantity).toFixed(2)}</span>
            <span class="block text-[10px] text-amber-700">Comisión MeLi: -$ ${Number(it.sale_fee || 0).toFixed(2)}</span>
          </div>
        </div>
      `).join("");

      openModal({
        title: `Auditoría Financiera SAT · Orden #${order.meli_order_id}`,
        size: "lg",
        content: `
          <div class="space-y-5">
            <!-- Resumen de Partidas -->
            <div>
              <h4 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Partidas del Pedido</h4>
              <div class="space-y-2">
                ${itemsHtml || '<p class="text-xs text-slate-400">Sin partidas registradas.</p>'}
              </div>
            </div>

            <!-- Desglose Financiero SAT Oficial -->
            <div class="p-4 rounded-2xl bg-gradient-to-br from-slate-900 to-slate-800 text-white shadow-lg space-y-3">
              <div class="flex items-center justify-between border-b border-slate-700 pb-2">
                <span class="text-xs font-bold uppercase tracking-wider text-[#FFE600]">Desglose de Liquidación Fiscal SAT</span>
                <span class="badge badge-success text-[10px]">${prof.net_margin_percentage ? prof.net_margin_percentage.toFixed(1) : 0}% Margen Neto</span>
              </div>

              <div class="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <span class="text-slate-400 block">Venta Bruta Cobrada:</span>
                  <span class="font-bold text-base text-white">$ ${Number(prof.gross_sale_price || order.total_amount).toFixed(2)}</span>
                </div>
                <div>
                  <span class="text-slate-400 block">Costo de Mercancía (COGS):</span>
                  <span class="font-bold text-base text-red-400">-$ ${Number(prof.cogs_total || 0).toFixed(2)}</span>
                </div>
                <div>
                  <span class="text-slate-400 block">Comisión Mercado Libre:</span>
                  <span class="font-bold text-red-400">-$ ${Number(prof.meli_commission_fee || 0).toFixed(2)}</span>
                </div>
                <div>
                  <span class="text-slate-400 block">Flete Mercado Envíos:</span>
                  <span class="font-bold text-red-400">-$ ${Number(prof.shipping_cost_seller || 0).toFixed(2)}</span>
                </div>
                <div>
                  <span class="text-slate-400 block">Retención SAT IVA:</span>
                  <span class="font-bold text-amber-400">-$ ${Number(prof.sat_iva_retention || 0).toFixed(2)}</span>
                </div>
                <div>
                  <span class="text-slate-400 block">Retención SAT ISR:</span>
                  <span class="font-bold text-amber-400">-$ ${Number(prof.sat_isr_retention || 0).toFixed(2)}</span>
                </div>
              </div>

              <div class="pt-3 border-t border-slate-700 flex items-center justify-between">
                <div>
                  <span class="text-[11px] text-slate-300 font-medium">Utilidad Neta Real Depositada:</span>
                  <p class="text-xs text-slate-400">Ya libre de comisiones, fletes e impuestos</p>
                </div>
                <div class="text-right">
                  <span class="text-xl font-black text-emerald-400">$ ${Number(prof.net_profit || 0).toFixed(2)} MXN</span>
                </div>
              </div>
            </div>
          </div>
        `,
        confirmText: "Entendido",
      });
    } catch (err) {
      showToast(`Error al abrir orden: ${err.message}`, "error");
    }
  }

  fetchOrders();
  return container;
}

/**
 * Vista 4: Inventario & Kardex Transaccional.
 * Control de existencias disponibles y reservadas, ajuste transaccional y pista de auditoría de movimientos.
 */

import { api } from "../api.js";
import { state } from "../state.js";
import { icons } from "../icons.js";
import { openModal } from "../components/modal.js";
import { showToast } from "../components/toast.js";

export function renderInventoryView() {
  const container = document.createElement("div");
  container.className = "space-y-5 animate-fade-in";

  let currentPage = 1;

  container.innerHTML = `
    <!-- Encabezado de Sección -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
      <div>
        <h2 class="text-2xl font-black text-slate-900 tracking-tight">Inventario & Kardex</h2>
        <p class="text-xs text-slate-500 mt-0.5">Control de existencias multi-almacén, bloqueo pesimista contra sobreventa y trazabilidad</p>
      </div>

      <div class="flex items-center space-x-2">
        <button id="btn-view-kardex" class="px-3.5 py-2.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-bold rounded-xl transition-smooth shadow-sm flex items-center space-x-2 touch-target">
          ${icons.reports("w-4 h-4 text-slate-500")}
          <span>Historial Kardex</span>
        </button>

        <button id="btn-adjust-stock" class="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl transition-smooth shadow-md shadow-blue-600/30 flex items-center space-x-2 touch-target">
          ${icons.plus("w-4 h-4")}
          <span>Ajustar Stock</span>
        </button>
      </div>
    </div>

    <!-- Tabla de Existencias -->
    <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <div class="p-4 border-b border-slate-100 flex items-center justify-between">
        <span class="text-xs font-bold text-slate-800 uppercase tracking-wider">Existencias por Almacén</span>
        <button id="btn-refresh-inv" class="p-2 border border-slate-200 rounded-xl hover:bg-slate-50 text-slate-600 transition-smooth touch-target">
          ${icons.refresh("w-4 h-4")}
        </button>
      </div>

      <div class="table-container">
        <table class="w-full text-left text-xs border-collapse">
          <thead>
            <tr class="border-b border-slate-200 bg-slate-50/70 text-slate-500 font-bold uppercase tracking-wider text-[10px]">
              <th class="py-3 px-4">Almacén ID</th>
              <th class="py-3 px-4">Variante ID</th>
              <th class="py-3 px-4">Disponible</th>
              <th class="py-3 px-4">Reservado</th>
              <th class="py-3 px-4">Total Físico</th>
              <th class="py-3 px-4">Estatus Stock</th>
              <th class="py-3 px-4 text-right">Último Movimiento</th>
            </tr>
          </thead>
          <tbody id="inventory-table-tbody" class="divide-y divide-slate-100 text-slate-700">
            <tr>
              <td colspan="7" class="py-8 text-center text-slate-400">
                ${icons.spinner("w-5 h-5 inline-block mr-2")} Cargando existencias...
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Paginación -->
      <div class="flex items-center justify-between px-4 py-3 bg-slate-50/50 border-t border-slate-100 text-xs">
        <span id="inv-pagination-info" class="text-slate-500 font-medium">Mostrando 0 registros</span>
        <div class="flex items-center space-x-1.5">
          <button id="btn-inv-prev" class="px-3 py-1.5 border border-slate-200 rounded-lg text-slate-600 bg-white hover:bg-slate-50 disabled:opacity-40 transition-smooth font-semibold" disabled>
            Anterior
          </button>
          <button id="btn-inv-next" class="px-3 py-1.5 border border-slate-200 rounded-lg text-slate-600 bg-white hover:bg-slate-50 disabled:opacity-40 transition-smooth font-semibold" disabled>
            Siguiente
          </button>
        </div>
      </div>
    </div>
  `;

  const btnAdjust = container.querySelector("#btn-adjust-stock");
  const btnKardex = container.querySelector("#btn-view-kardex");
  const btnRefresh = container.querySelector("#btn-refresh-inv");
  const btnPrev = container.querySelector("#btn-inv-prev");
  const btnNext = container.querySelector("#btn-inv-next");

  if (btnAdjust) btnAdjust.addEventListener("click", () => openAdjustStockModal());
  if (btnKardex) btnKardex.addEventListener("click", () => openKardexModal());
  if (btnRefresh) btnRefresh.addEventListener("click", () => fetchInventory());

  if (btnPrev) {
    btnPrev.addEventListener("click", () => {
      if (currentPage > 1) {
        currentPage--;
        fetchInventory();
      }
    });
  }

  if (btnNext) {
    btnNext.addEventListener("click", () => {
      currentPage++;
      fetchInventory();
    });
  }

  async function fetchInventory() {
    const tbody = container.querySelector("#inventory-table-tbody");

    try {
      const data = await api.get("/inventory", { page: currentPage, size: 10 });
      const items = data.items || [];

      if (items.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="7" class="py-12 text-center text-slate-400">
              No se han registrado inventarios. Realiza una compra o un ajuste inicial para ingresar existencias.
            </td>
          </tr>
        `;
      } else {
        tbody.innerHTML = items.map(inv => {
          const isLow = inv.quantity_available <= 5;
          const statusBadge = isLow
            ? '<span class="badge badge-danger text-[10px]">Stock Crítico (&lt;=5)</span>'
            : '<span class="badge badge-success text-[10px]">Disponible</span>';

          return `
            <tr class="hover:bg-slate-50/80 transition-smooth">
              <td class="py-3.5 px-4 font-mono font-medium text-slate-900 truncate max-w-[120px]">${inv.warehouse_id}</td>
              <td class="py-3.5 px-4 font-mono text-slate-600 truncate max-w-[120px]">${inv.variant_id}</td>
              <td class="py-3.5 px-4 font-bold text-slate-900">${inv.quantity_available} u.</td>
              <td class="py-3.5 px-4 text-slate-500">${inv.quantity_reserved} u.</td>
              <td class="py-3.5 px-4 font-bold text-blue-700">${inv.quantity_total} u.</td>
              <td class="py-3.5 px-4">${statusBadge}</td>
              <td class="py-3.5 px-4 text-right text-slate-400 font-mono text-[11px]">
                ${new Date(inv.updated_at).toLocaleTimeString('es-MX')}
              </td>
            </tr>
          `;
        }).join("");
      }

      const infoEl = container.querySelector("#inv-pagination-info");
      if (infoEl) infoEl.textContent = `Página ${data.page} de ${data.pages || 1} (${data.total} inventarios en total)`;

      if (btnPrev) btnPrev.disabled = !data.has_prev;
      if (btnNext) btnNext.disabled = !data.has_next;

    } catch (err) {
      tbody.innerHTML = `
        <tr>
          <td colspan="7" class="py-8 text-center text-red-600 font-semibold">
            Error al consultar existencias: ${err.message}
          </td>
        </tr>
      `;
    }
  }

  async function openAdjustStockModal() {
    try {
      // Obtener almacenes y productos para llenar selects
      const [whData, prodData] = await Promise.all([
        api.get("/warehouses"),
        api.get("/products", { size: 50 }),
      ]);

      const warehouses = whData.items || [];
      const products = prodData.items || [];

      if (warehouses.length === 0) {
        showToast("Primero debes dar de alta un almacén en la sección Almacenes.", "warning");
        return;
      }

      const variants = [];
      products.forEach(p => {
        (p.variants || []).forEach(v => variants.push({ ...v, prodName: p.name }));
      });

      if (variants.length === 0) {
        showToast("Primero debes dar de alta al menos un producto con variantes.", "warning");
        return;
      }

      openModal({
        title: "Ajuste Transaccional de Stock (Bloqueo Pesimista)",
        size: "md",
        content: `
          <div class="space-y-4">
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Almacén de Destino</label>
              <select id="adj-wh-select" class="w-full px-3 py-2 text-xs border border-slate-200 rounded-xl bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600">
                ${warehouses.map(w => `<option value="${w.id}">${w.name} (${w.warehouse_type})</option>`).join("")}
              </select>
            </div>

            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Producto & Variante</label>
              <select id="adj-var-select" class="w-full px-3 py-2 text-xs border border-slate-200 rounded-xl bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600">
                ${variants.map(v => `<option value="${v.id}">${v.prodName} - ${v.variant_name} (SKU: ${v.sku})</option>`).join("")}
              </select>
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-xs font-bold text-slate-700 mb-1">Tipo de Movimiento</label>
                <select id="adj-type-select" class="w-full px-3 py-2 text-xs border border-slate-200 rounded-xl bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600">
                  <option value="PURCHASE">Entrada por Compra (PURCHASE)</option>
                  <option value="ADJUSTMENT">Ajuste de Conteo Físico</option>
                  <option value="RETURN">Devolución de Cliente</option>
                  <option value="TRANSFER">Transferencia entre Almacenes</option>
                </select>
              </div>

              <div>
                <label class="block text-xs font-bold text-slate-700 mb-1">Delta / Cantidad (+ ó -)</label>
                <input id="adj-delta-input" type="number" step="1" value="10" placeholder="+10 o -5" class="w-full px-3 py-2 text-xs font-mono border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-600 focus:outline-none" />
              </div>
            </div>

            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Notas / Justificación de Auditoría</label>
              <input id="adj-notes-input" type="text" placeholder="Recepción de factura / Conteo físico cíclico" class="w-full px-3 py-2 text-xs border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-600 focus:outline-none" />
            </div>
          </div>
        `,
        confirmText: "Aplicar Ajuste de Stock",
        onConfirm: async () => {
          const warehouseId = document.getElementById("adj-wh-select").value;
          const variantId = document.getElementById("adj-var-select").value;
          const movementType = document.getElementById("adj-type-select").value;
          const delta = parseInt(document.getElementById("adj-delta-input").value);
          const notes = document.getElementById("adj-notes-input").value.trim();

          if (isNaN(delta) || delta === 0) throw new Error("La cantidad debe ser un número entero distinto de cero.");

          const payload = {
            warehouse_id: warehouseId,
            variant_id: variantId,
            quantity_delta: delta,
            movement_type: movementType,
            notes: notes || "Ajuste manual vía ERP",
          };

          await api.post("/inventory/adjust", payload);
          showToast("Ajuste de inventario aplicado y registrado en el Kardex.", "success");
          fetchInventory();
        }
      });
    } catch (err) {
      showToast(`Error al preparar ajuste: ${err.message}`, "error");
    }
  }

  async function openKardexModal() {
    try {
      const data = await api.get("/inventory/movements", { size: 20 });
      const movements = data.items || [];

      const rowsHtml = movements.map(m => `
        <tr class="hover:bg-slate-50/70 border-b border-slate-100 text-xs">
          <td class="py-2.5 px-3 font-mono text-slate-500">${new Date(m.created_at).toLocaleString('es-MX')}</td>
          <td class="py-2.5 px-3"><span class="badge badge-info text-[9px] uppercase">${m.movement_type}</span></td>
          <td class="py-2.5 px-3 font-bold ${m.quantity_delta > 0 ? 'text-emerald-600' : 'text-red-600'}">
            ${m.quantity_delta > 0 ? `+${m.quantity_delta}` : m.quantity_delta}
          </td>
          <td class="py-2.5 px-3 font-semibold text-slate-700">${m.quantity_before} → ${m.quantity_after}</td>
          <td class="py-2.5 px-3 text-slate-500 truncate max-w-xs">${m.notes || '-'}</td>
        </tr>
      `).join("") || '<tr><td colspan="5" class="py-8 text-center text-slate-400">Sin movimientos en el Kardex aún.</td></tr>';

      openModal({
        title: "Pista Inmutable del Kardex de Movimientos",
        size: "xl",
        content: `
          <div class="table-container max-h-96">
            <table class="w-full text-left text-xs border-collapse">
              <thead>
                <tr class="bg-slate-50 text-slate-500 uppercase text-[10px] font-bold">
                  <th class="py-2 px-3">Fecha</th>
                  <th class="py-2 px-3">Tipo</th>
                  <th class="py-2 px-3">Delta</th>
                  <th class="py-2 px-3">Saldo</th>
                  <th class="py-2 px-3">Notas</th>
                </tr>
              </thead>
              <tbody>
                ${rowsHtml}
              </tbody>
            </table>
          </div>
        `,
        confirmText: "Cerrar",
      });
    } catch (err) {
      showToast(`Error al consultar Kardex: ${err.message}`, "error");
    }
  }

  fetchInventory();
  return container;
}

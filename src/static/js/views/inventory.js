/**
 * Vista 4: Inventario Profesional & Kardex Transaccional.
 * Control exhaustivo de:
 * - Stock Físico, Reservado, Bloqueado (cuarentena) y Disponible.
 * - FÓRMULA OFICIAL: Stock disponible = Físico - Reservado - Bloqueado.
 * - Ubicaciones en almacén (Pasillo-Rack-Nivel-Bin) y Stock Mínimo/Máximo.
 * - Bloqueo y Desbloqueo de unidades.
 * - Sincronización con Mercado Libre (sin colisión con MeLi FULL).
 * - Kardex de trazabilidad completa.
 */

import { api } from "../api.js";
import { state } from "../state.js";
import { icons } from "../icons.js";
import { openModal } from "../components/modal.js";
import { showToast } from "../components/toast.js";

export function renderInventoryView() {
  const container = document.createElement("div");
  container.className = "space-y-6 animate-fade-in";

  let currentPage = 1;
  let selectedWarehouseId = "";
  let searchSku = "";

  container.innerHTML = `
    <!-- Encabezado de Sección -->
    <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
      <div>
        <h2 class="text-2xl font-black text-slate-900 tracking-tight">Inventario & Kardex Transaccional</h2>
        <p class="text-xs text-slate-500 mt-0.5">
          Fuente de verdad de existencias internas • Stock Disponible = Físico - Reservado - Bloqueado
        </p>
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <button id="btn-view-alerts" class="px-3.5 py-2.5 bg-amber-50 hover:bg-amber-100 text-amber-800 border border-amber-200 text-xs font-bold rounded-xl transition-smooth shadow-sm flex items-center space-x-1.5 touch-target">
          ${icons.alertTriangle ? icons.alertTriangle("w-4 h-4 text-amber-600") : icons.reports("w-4 h-4 text-amber-600")}
          <span>Alertas de Stock</span>
        </button>

        <button id="btn-sync-meli-info" class="px-3.5 py-2.5 bg-yellow-50 hover:bg-yellow-100 text-yellow-900 border border-yellow-300 text-xs font-bold rounded-xl transition-smooth shadow-sm flex items-center space-x-1.5 touch-target">
          ${icons.refresh("w-4 h-4 text-yellow-700")}
          <span>Sincronización MeLi</span>
        </button>

        <button id="btn-view-kardex" class="px-3.5 py-2.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-bold rounded-xl transition-smooth shadow-sm flex items-center space-x-1.5 touch-target">
          ${icons.reports("w-4 h-4 text-slate-500")}
          <span>Kardex General</span>
        </button>

        <button id="btn-adjust-stock" class="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl transition-smooth shadow-md shadow-blue-600/30 flex items-center space-x-2 touch-target">
          ${icons.plus("w-4 h-4")}
          <span>Ajuste / Entrada / Salida</span>
        </button>
      </div>
    </div>

    <!-- Tarjetas KPI de Estado de Existencias -->
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-4" id="inv-kpi-grid">
      <div class="p-4 bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col justify-between">
        <span class="text-[11px] font-bold uppercase tracking-wider text-slate-500">Stock Físico Total</span>
        <div class="mt-2 flex items-baseline justify-between">
          <span id="kpi-physical-total" class="text-2xl font-black text-slate-900">0</span>
          <span class="text-xs text-slate-400 font-medium">unidades</span>
        </div>
      </div>

      <div class="p-4 bg-white rounded-2xl border border-amber-200 shadow-sm flex flex-col justify-between bg-amber-50/20">
        <span class="text-[11px] font-bold uppercase tracking-wider text-amber-700">Stock Reservado</span>
        <div class="mt-2 flex items-baseline justify-between">
          <span id="kpi-reserved-total" class="text-2xl font-black text-amber-600">0</span>
          <span class="text-xs text-amber-600/70 font-medium">pedidos en proceso</span>
        </div>
      </div>

      <div class="p-4 bg-white rounded-2xl border border-rose-200 shadow-sm flex flex-col justify-between bg-rose-50/20">
        <span class="text-[11px] font-bold uppercase tracking-wider text-rose-700">Stock Bloqueado</span>
        <div class="mt-2 flex items-baseline justify-between">
          <span id="kpi-blocked-total" class="text-2xl font-black text-rose-600">0</span>
          <span class="text-xs text-rose-600/70 font-medium">cuarentena / daño</span>
        </div>
      </div>

      <div class="p-4 bg-white rounded-2xl border border-emerald-200 shadow-sm flex flex-col justify-between bg-emerald-50/30">
        <span class="text-[11px] font-bold uppercase tracking-wider text-emerald-800">Stock Disponible</span>
        <div class="mt-2 flex items-baseline justify-between">
          <span id="kpi-available-total" class="text-2xl font-black text-emerald-600">0</span>
          <span class="text-xs text-emerald-600/80 font-medium">apto para venta</span>
        </div>
      </div>
    </div>

    <!-- Barra de Filtros y Búsqueda -->
    <div class="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
      <div class="flex flex-1 items-center space-x-2">
        <div class="relative flex-1 max-w-sm">
          <input
            id="inv-search-sku"
            type="text"
            placeholder="Buscar por SKU..."
            class="w-full pl-9 pr-3 py-2 text-xs border border-slate-200 rounded-xl bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600 font-mono"
          />
          <span class="absolute left-3 top-2.5 text-slate-400">
            ${icons.search ? icons.search("w-4 h-4") : ""}
          </span>
        </div>

        <select id="inv-filter-warehouse" class="px-3 py-2 text-xs border border-slate-200 rounded-xl bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600">
          <option value="">Todos los almacenes</option>
        </select>
      </div>

      <button id="btn-refresh-inv" class="px-3.5 py-2 border border-slate-200 rounded-xl hover:bg-slate-50 text-slate-600 text-xs font-semibold flex items-center justify-center space-x-1.5 touch-target">
        ${icons.refresh("w-4 h-4")}
        <span>Actualizar</span>
      </button>
    </div>

    <!-- Tabla de Existencias -->
    <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <div class="table-container">
        <table class="w-full text-left text-xs border-collapse">
          <thead>
            <tr class="border-b border-slate-200 bg-slate-50/70 text-slate-500 font-bold uppercase tracking-wider text-[10px]">
              <th class="py-3 px-4">Almacén</th>
              <th class="py-3 px-4">Variante / SKU</th>
              <th class="py-3 px-4">Ubicación</th>
              <th class="py-3 px-4 text-center">Físico</th>
              <th class="py-3 px-4 text-center text-amber-700">Reservado</th>
              <th class="py-3 px-4 text-center text-rose-700">Bloqueado</th>
              <th class="py-3 px-4 text-center text-emerald-700">Disponible</th>
              <th class="py-3 px-4">Límites (Mín/Máx)</th>
              <th class="py-3 px-4">Estatus</th>
              <th class="py-3 px-4 text-right">Acciones</th>
            </tr>
          </thead>
          <tbody id="inventory-table-tbody" class="divide-y divide-slate-100 text-slate-700">
            <tr>
              <td colspan="10" class="py-10 text-center text-slate-400">
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

  // Referencias a elementos interactivos
  const btnAdjust = container.querySelector("#btn-adjust-stock");
  const btnKardex = container.querySelector("#btn-view-kardex");
  const btnAlerts = container.querySelector("#btn-view-alerts");
  const btnSyncMeli = container.querySelector("#btn-sync-meli-info");
  const btnRefresh = container.querySelector("#btn-refresh-inv");
  const btnPrev = container.querySelector("#btn-inv-prev");
  const btnNext = container.querySelector("#btn-inv-next");
  const searchInput = container.querySelector("#inv-search-sku");
  const whFilter = container.querySelector("#inv-filter-warehouse");

  let warehousesCache = [];
  let variantsCache = [];

  // Inicialización
  loadWarehousesFilter();
  fetchInventory();

  if (btnAdjust) btnAdjust.addEventListener("click", () => openAdjustStockModal());
  if (btnKardex) btnKardex.addEventListener("click", () => openKardexModal());
  if (btnAlerts) btnAlerts.addEventListener("click", () => openAlertsModal());
  if (btnSyncMeli) btnSyncMeli.addEventListener("click", () => openMeliSyncModal());
  if (btnRefresh) btnRefresh.addEventListener("click", () => fetchInventory());

  if (searchInput) {
    let debounceTimer;
    searchInput.addEventListener("input", (e) => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        searchSku = e.target.value.trim();
        currentPage = 1;
        fetchInventory();
      }, 400);
    });
  }

  if (whFilter) {
    whFilter.addEventListener("change", (e) => {
      selectedWarehouseId = e.target.value;
      currentPage = 1;
      fetchInventory();
    });
  }

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

  async function loadWarehousesFilter() {
    try {
      const res = await api.get("/warehouses");
      warehousesCache = res.items || [];
      if (whFilter) {
        whFilter.innerHTML = '<option value="">Todos los almacenes</option>' +
          warehousesCache.map(w => `<option value="${w.id}">${w.name} (${w.warehouse_type}${w.is_fulfillment ? ' - FULL' : ''})</option>`).join("");
      }
    } catch (e) {
      console.error("Error al cargar almacenes para filtro", e);
    }
  }

  async function fetchInventory() {
    const tbody = container.querySelector("#inventory-table-tbody");
    try {
      const queryParams = { page: currentPage, size: 10 };
      if (selectedWarehouseId) queryParams.warehouse_id = selectedWarehouseId;
      if (searchSku) queryParams.sku = searchSku;

      const data = await api.get("/inventory", queryParams);
      const items = data.items || [];

      // Calcular totales para KPIs
      let totalPhysical = 0;
      let totalReserved = 0;
      let totalBlocked = 0;
      let totalAvailable = 0;

      items.forEach(inv => {
        totalPhysical += inv.quantity_on_hand;
        totalReserved += inv.quantity_reserved;
        totalBlocked += inv.quantity_blocked;
        totalAvailable += inv.quantity_available;
      });

      const elPhys = container.querySelector("#kpi-physical-total");
      const elRes = container.querySelector("#kpi-reserved-total");
      const elBlk = container.querySelector("#kpi-blocked-total");
      const elAvail = container.querySelector("#kpi-available-total");
      if (elPhys) elPhys.textContent = totalPhysical.toLocaleString();
      if (elRes) elRes.textContent = totalReserved.toLocaleString();
      if (elBlk) elBlk.textContent = totalBlocked.toLocaleString();
      if (elAvail) elAvail.textContent = totalAvailable.toLocaleString();

      if (items.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="10" class="py-12 text-center text-slate-400">
              No se encontraron registros de inventario. Realiza un ajuste de entrada para inicializar existencias.
            </td>
          </tr>
        `;
      } else {
        tbody.innerHTML = items.map(inv => {
          let statusBadge = '<span class="badge badge-success text-[10px]">Normal</span>';
          if (inv.alert_status === "OUT_OF_STOCK") {
            statusBadge = '<span class="badge badge-danger text-[10px]">Agotado</span>';
          } else if (inv.alert_status === "LOW_STOCK") {
            statusBadge = '<span class="badge badge-warning text-[10px]">Bajo Stock</span>';
          } else if (inv.alert_status === "OVER_STOCK") {
            statusBadge = '<span class="badge badge-info text-[10px]">Sobre-stock</span>';
          }

          const wh = warehousesCache.find(w => w.id === inv.warehouse_id);
          const whName = wh ? wh.name : inv.warehouse_id.slice(0, 8);
          const whBadge = wh && wh.is_fulfillment ? ' <span class="text-[9px] px-1 py-0.5 bg-amber-100 text-amber-800 rounded font-bold">FULL</span>' : '';

          return `
            <tr class="hover:bg-slate-50/80 transition-smooth">
              <td class="py-3 px-4 font-medium text-slate-900">${whName}${whBadge}</td>
              <td class="py-3 px-4 font-mono text-slate-700">
                <span class="font-bold">${inv.variant_id.slice(0, 8)}...</span>
              </td>
              <td class="py-3 px-4 font-mono text-slate-600 text-[11px]">
                ${inv.location_bin || '<span class="text-slate-400 italic">Sin asignar</span>'}
              </td>
              <td class="py-3 px-4 text-center font-bold text-slate-800">${inv.quantity_on_hand}</td>
              <td class="py-3 px-4 text-center font-bold text-amber-600">${inv.quantity_reserved}</td>
              <td class="py-3 px-4 text-center font-bold text-rose-600">${inv.quantity_blocked}</td>
              <td class="py-3 px-4 text-center font-black text-emerald-600 bg-emerald-50/40 rounded-lg">${inv.quantity_available}</td>
              <td class="py-3 px-4 text-[11px] text-slate-500">
                Mín: <span class="font-bold text-slate-700">${inv.safety_stock}</span> / Máx: <span class="font-bold text-slate-700">${inv.max_stock ?? '∞'}</span>
              </td>
              <td class="py-3 px-4">${statusBadge}</td>
              <td class="py-3 px-4 text-right">
                <div class="flex items-center justify-end space-x-1">
                  <button class="btn-item-adjust p-1.5 hover:bg-slate-100 rounded-lg text-slate-600 transition-smooth" data-wh="${inv.warehouse_id}" data-var="${inv.variant_id}" title="Ajuste rápido">
                    ${icons.plus("w-3.5 h-3.5")}
                  </button>
                  <button class="btn-item-block p-1.5 hover:bg-rose-50 rounded-lg text-rose-600 transition-smooth" data-wh="${inv.warehouse_id}" data-var="${inv.variant_id}" data-avail="${inv.quantity_available}" data-blk="${inv.quantity_blocked}" title="Bloquear / Desbloquear">
                    ${icons.shield ? icons.shield("w-3.5 h-3.5") : icons.settings("w-3.5 h-3.5")}
                  </button>
                  <button class="btn-item-loc p-1.5 hover:bg-blue-50 rounded-lg text-blue-600 transition-smooth" data-wh="${inv.warehouse_id}" data-var="${inv.variant_id}" data-bin="${inv.location_bin || ''}" data-min="${inv.safety_stock}" data-max="${inv.max_stock ?? ''}" title="Editar Ubicación / Mínimos">
                    ${icons.check ? icons.check("w-3.5 h-3.5") : icons.settings("w-3.5 h-3.5")}
                  </button>
                </div>
              </td>
            </tr>
          `;
        }).join("");

        // Attach action handlers
        tbody.querySelectorAll(".btn-item-adjust").forEach(btn => {
          btn.addEventListener("click", () => {
            openAdjustStockModal(btn.dataset.wh, btn.dataset.var);
          });
        });

        tbody.querySelectorAll(".btn-item-block").forEach(btn => {
          btn.addEventListener("click", () => {
            openBlockUnblockModal(btn.dataset.wh, btn.dataset.var, parseInt(btn.dataset.avail), parseInt(btn.dataset.blk));
          });
        });

        tbody.querySelectorAll(".btn-item-loc").forEach(btn => {
          btn.addEventListener("click", () => {
            openLocationModal(btn.dataset.wh, btn.dataset.var, btn.dataset.bin, btn.dataset.min, btn.dataset.max);
          });
        });
      }

      const infoEl = container.querySelector("#inv-pagination-info");
      if (infoEl) infoEl.textContent = `Página ${data.page} de ${data.pages || 1} (${data.total} registros)`;

      if (btnPrev) btnPrev.disabled = !data.has_prev;
      if (btnNext) btnNext.disabled = !data.has_next;
    } catch (err) {
      tbody.innerHTML = `
        <tr>
          <td colspan="10" class="py-8 text-center text-red-600 font-semibold">
            Error al consultar inventarios: ${err.message}
          </td>
        </tr>
      `;
    }
  }

  async function openAdjustStockModal(defaultWhId = "", defaultVarId = "") {
    try {
      const [whData, prodData] = await Promise.all([
        api.get("/warehouses"),
        api.get("/products", { size: 50 }),
      ]);

      const warehouses = whData.items || [];
      const products = prodData.items || [];

      if (warehouses.length === 0) {
        showToast("Primero debes registrar un almacén.", "warning");
        return;
      }

      const variants = [];
      products.forEach(p => {
        (p.variants || []).forEach(v => variants.push({ ...v, prodTitle: p.title }));
      });

      if (variants.length === 0) {
        showToast("Primero debes crear un producto con variantes en el Catálogo.", "warning");
        return;
      }

      openModal({
        title: "Ajuste Transaccional de Existencias (Kardex)",
        size: "md",
        content: `
          <div class="space-y-4">
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Almacén</label>
              <select id="adj-wh-select" class="w-full px-3 py-2 text-xs border border-slate-200 rounded-xl bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600">
                ${warehouses.map(w => `<option value="${w.id}" ${w.id === defaultWhId ? 'selected' : ''}>${w.name} (${w.warehouse_type}${w.is_fulfillment ? ' - FULL' : ''})</option>`).join("")}
              </select>
            </div>

            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Variante / SKU</label>
              <select id="adj-var-select" class="w-full px-3 py-2 text-xs border border-slate-200 rounded-xl bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600 font-mono">
                ${variants.map(v => `<option value="${v.id}" ${v.id === defaultVarId ? 'selected' : ''}>SKU: ${v.sku} - ${v.prodTitle}</option>`).join("")}
              </select>
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-xs font-bold text-slate-700 mb-1">Tipo de Movimiento</label>
                <select id="adj-type-select" class="w-full px-3 py-2 text-xs border border-slate-200 rounded-xl bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600">
                  <option value="INBOUND">Entrada / Recepción de Compra (+)</option>
                  <option value="OUTBOUND">Salida de Venta / Despacho (-)</option>
                  <option value="ADJUSTMENT">Ajuste Manual de Inventario (+ / -)</option>
                  <option value="RETURN">Devolución de Cliente</option>
                  <option value="DAMAGE">Merma o Daño (-)</option>
                </select>
              </div>

              <div>
                <label class="block text-xs font-bold text-slate-700 mb-1">Cantidad / Delta</label>
                <input id="adj-delta-input" type="number" step="1" value="10" placeholder="Ej. 10 o -5" class="w-full px-3 py-2 text-xs font-mono border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-600 focus:outline-none" />
              </div>
            </div>

            <div id="adj-condition-group" class="hidden">
              <label class="block text-xs font-bold text-slate-700 mb-1">Condición de la Devolución</label>
              <select id="adj-cond-select" class="w-full px-3 py-2 text-xs border border-slate-200 rounded-xl bg-slate-50 focus:bg-white focus:outline-none">
                <option value="good">Buen Estado (Apto para reventa / Disponible)</option>
                <option value="damaged">Dañado / Defectuoso (Pasa directo a Bloqueado/Merma)</option>
              </select>
            </div>

            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Referencia Externa (Opcional)</label>
              <input id="adj-ref-input" type="text" placeholder="ID de Orden MeLi, Factura de Proveedor..." class="w-full px-3 py-2 text-xs border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-600 focus:outline-none" />
            </div>

            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Notas / Justificación de Auditoría</label>
              <input id="adj-notes-input" type="text" placeholder="Motivo del ajuste..." class="w-full px-3 py-2 text-xs border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-600 focus:outline-none" />
            </div>
          </div>
        `,
        confirmText: "Aplicar Movimiento",
        onConfirm: async () => {
          const warehouseId = document.getElementById("adj-wh-select").value;
          const variantId = document.getElementById("adj-var-select").value;
          const movementType = document.getElementById("adj-type-select").value;
          let delta = parseInt(document.getElementById("adj-delta-input").value);
          const condition = document.getElementById("adj-cond-select").value;
          const referenceId = document.getElementById("adj-ref-input").value.trim();
          const notes = document.getElementById("adj-notes-input").value.trim();

          if (isNaN(delta) || delta === 0) throw new Error("La cantidad debe ser distinta de cero.");

          // Si es salida o merma y el usuario puso positivo, convertir a negativo
          if ((movementType === "OUTBOUND" || movementType === "DAMAGE") && delta > 0) {
            delta = -delta;
          }

          await api.post("/inventory/adjust", {
            warehouse_id: warehouseId,
            variant_id: variantId,
            quantity_delta: delta,
            movement_type: movementType,
            condition: condition,
            reference_id: referenceId || null,
            reference_type: referenceId ? "order" : "manual",
            notes: notes || "Ajuste manual desde vista de inventario",
          });

          showToast("Ajuste de inventario aplicado exitosamente.", "success");
          fetchInventory();
        },
      });

      // Mostrar selector de condición solo si es RETURN
      setTimeout(() => {
        const typeSelect = document.getElementById("adj-type-select");
        const condGroup = document.getElementById("adj-condition-group");
        if (typeSelect && condGroup) {
          typeSelect.addEventListener("change", (e) => {
            if (e.target.value === "RETURN") {
              condGroup.classList.remove("hidden");
            } else {
              condGroup.classList.add("hidden");
            }
          });
        }
      }, 50);

    } catch (err) {
      showToast(err.message, "error");
    }
  }

  function openBlockUnblockModal(warehouseId, variantId, available, blocked) {
    openModal({
      title: "Control de Cuarentena (Bloqueo / Desbloqueo)",
      size: "md",
      content: `
        <div class="space-y-4">
          <div class="p-3 bg-slate-50 rounded-xl border border-slate-200 text-xs flex justify-between">
            <div>Stock Disponible: <span class="font-bold text-emerald-600">${available} u.</span></div>
            <div>Stock Bloqueado: <span class="font-bold text-rose-600">${blocked} u.</span></div>
          </div>

          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1">Acción</label>
            <select id="blk-action-select" class="w-full px-3 py-2 text-xs border border-slate-200 rounded-xl bg-slate-50 focus:bg-white focus:outline-none">
              <option value="block">Bloquear a Cuarentena (Retirar de Disponible)</option>
              <option value="unblock">Desbloquear de Cuarentena (Reintegrar a Disponible)</option>
            </select>
          </div>

          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1">Cantidad</label>
            <input id="blk-qty-input" type="number" min="1" value="1" class="w-full px-3 py-2 text-xs font-mono border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-600" />
          </div>

          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1">Motivo / Razón</label>
            <input id="blk-reason-input" type="text" placeholder="Ej. Daño estético en caja, lote en revisión de calidad..." class="w-full px-3 py-2 text-xs border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-600" />
          </div>
        </div>
      `,
      confirmText: "Procesar",
      onConfirm: async () => {
        const action = document.getElementById("blk-action-select").value;
        const qty = parseInt(document.getElementById("blk-qty-input").value);
        const reason = document.getElementById("blk-reason-input").value.trim();

        if (isNaN(qty) || qty <= 0) throw new Error("La cantidad debe ser mayor a 0.");
        if (!reason) throw new Error("Debe ingresar un motivo para auditoría.");

        if (action === "block") {
          await api.post("/inventory/block", {
            warehouse_id: warehouseId,
            variant_id: variantId,
            quantity: qty,
            reason: reason,
          });
          showToast(`Se bloquearon ${qty} unidades hacia cuarentena.`, "success");
        } else {
          await api.post("/inventory/unblock", {
            warehouse_id: warehouseId,
            variant_id: variantId,
            quantity: qty,
            reason: reason,
          });
          showToast(`Se desbloquearon ${qty} unidades reintegrándolas a disponible.`, "success");
        }
        fetchInventory();
      },
    });
  }

  function openLocationModal(warehouseId, variantId, currentBin, currentMin, currentMax) {
    openModal({
      title: "Ubicación en Almacén & Umbrales de Stock",
      size: "md",
      content: `
        <div class="space-y-4">
          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1">Ubicación Física (Pasillo-Rack-Nivel-Bin)</label>
            <input id="loc-bin-input" type="text" value="${currentBin}" placeholder="Ej. A-03-R2-P1" class="w-full px-3 py-2 text-xs font-mono uppercase border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-600" />
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Stock Mínimo (Punto de Alerta)</label>
              <input id="loc-min-input" type="number" min="0" value="${currentMin}" class="w-full px-3 py-2 text-xs font-mono border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-600" />
            </div>

            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Stock Máximo (Capacidad)</label>
              <input id="loc-max-input" type="number" min="0" value="${currentMax}" placeholder="Opcional" class="w-full px-3 py-2 text-xs font-mono border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-600" />
            </div>
          </div>
        </div>
      `,
      confirmText: "Guardar Configuración",
      onConfirm: async () => {
        const bin = document.getElementById("loc-bin-input").value.trim();
        const minVal = parseInt(document.getElementById("loc-min-input").value);
        const maxInput = document.getElementById("loc-max-input").value.trim();
        const maxVal = maxInput ? parseInt(maxInput) : null;

        await api.post("/inventory/location", {
          warehouse_id: warehouseId,
          variant_id: variantId,
          location_bin: bin || null,
          safety_stock: isNaN(minVal) ? 5 : minVal,
          max_stock: maxVal,
        });

        showToast("Ubicación y umbrales actualizados.", "success");
        fetchInventory();
      },
    });
  }

  async function openAlertsModal() {
    try {
      const alerts = await api.get("/inventory/alerts");
      openModal({
        title: "Panel de Alertas de Inventario",
        size: "lg",
        content: `
          <div class="space-y-4">
            <p class="text-xs text-slate-500">
              Productos que requieren atención inmediata por agotamiento, stock crítico o saturación.
            </p>

            ${alerts.length === 0 ? `
              <div class="py-8 text-center text-slate-400 text-xs">
                🎉 No hay alertas activas. Todos los niveles de stock se encuentran en rango óptimo.
              </div>
            ` : `
              <div class="table-container max-h-96 overflow-y-auto">
                <table class="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr class="border-b border-slate-200 bg-slate-50 text-slate-500 font-bold uppercase text-[10px]">
                      <th class="py-2.5 px-3">Estatus</th>
                      <th class="py-2.5 px-3">Almacén</th>
                      <th class="py-2.5 px-3">SKU / Producto</th>
                      <th class="py-2.5 px-3 text-center">Físico</th>
                      <th class="py-2.5 px-3 text-center">Disponible</th>
                      <th class="py-2.5 px-3 text-center">Mínimo</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-slate-100 text-slate-700">
                    ${alerts.map(a => {
                      const badge = a.alert_status === 'OUT_OF_STOCK'
                        ? '<span class="badge badge-danger text-[10px]">Agotado</span>'
                        : (a.alert_status === 'LOW_STOCK'
                            ? '<span class="badge badge-warning text-[10px]">Stock Bajo</span>'
                            : '<span class="badge badge-info text-[10px]">Sobre-stock</span>');
                      return `
                        <tr>
                          <td class="py-2.5 px-3">${badge}</td>
                          <td class="py-2.5 px-3 font-medium">${a.warehouse_name}</td>
                          <td class="py-2.5 px-3"><span class="font-mono font-bold">${a.sku}</span> - ${a.product_title}</td>
                          <td class="py-2.5 px-3 text-center font-bold">${a.quantity_on_hand}</td>
                          <td class="py-2.5 px-3 text-center font-black ${a.quantity_available === 0 ? 'text-red-600' : 'text-amber-600'}">${a.quantity_available}</td>
                          <td class="py-2.5 px-3 text-center text-slate-500">${a.safety_stock}</td>
                        </tr>
                      `;
                    }).join("")}
                  </tbody>
                </table>
              </div>
            `}
          </div>
        `,
        confirmText: "Cerrar",
      });
    } catch (err) {
      showToast(err.message, "error");
    }
  }

  async function openMeliSyncModal() {
    try {
      const prodRes = await api.get("/products", { size: 50 });
      const products = prodRes.items || [];
      const variants = [];
      products.forEach(p => {
        (p.variants || []).forEach(v => variants.push({ ...v, prodTitle: p.title }));
      });

      if (variants.length === 0) {
        showToast("No hay variantes registradas.", "warning");
        return;
      }

      openModal({
        title: "Regla de Sincronización con Mercado Libre & MeLi Full",
        size: "md",
        content: `
          <div class="space-y-4">
            <div class="p-3 bg-blue-50 border border-blue-200 rounded-xl text-xs text-blue-900 space-y-1">
              <p class="font-bold">Aislamiento de Mercado Envíos FULL:</p>
              <p>El ERP calcula el stock a enviar a Mercado Libre sumando únicamente los almacenes locales propios, garantizando que el stock custodiado en bodegas de MeLi Full no se sobreescriba ni entre en conflicto.</p>
            </div>

            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Seleccionar Variante</label>
              <select id="meli-sync-var-select" class="w-full px-3 py-2 text-xs border border-slate-200 rounded-xl bg-slate-50 focus:bg-white focus:outline-none font-mono">
                ${variants.map(v => `<option value="${v.id}">SKU: ${v.sku} - ${v.prodTitle}</option>`).join("")}
              </select>
            </div>

            <div id="meli-sync-results" class="p-4 bg-slate-50 rounded-xl border border-slate-200 text-xs space-y-2">
              <p class="text-slate-400 text-center py-2">Calculando balance de existencias...</p>
            </div>
          </div>
        `,
        confirmText: "Entendido",
      });

      const selectEl = document.getElementById("meli-sync-var-select");
      const resultsEl = document.getElementById("meli-sync-results");

      async function refreshSyncCalc(varId) {
        try {
          const res = await api.get(`/inventory/meli-sync-stock/${varId}`);
          resultsEl.innerHTML = `
            <div class="flex justify-between py-1 border-b border-slate-200">
              <span class="text-slate-600">Stock Disponible Local (Flex / Bodega):</span>
              <span class="font-bold text-slate-900">${res.local_available_stock} u.</span>
            </div>
            <div class="flex justify-between py-1 border-b border-slate-200">
              <span class="text-slate-600">Stock en Bodega MeLi Full (FULL_MLM):</span>
              <span class="font-bold text-amber-700">${res.meli_full_stock} u.</span>
            </div>
            <div class="flex justify-between py-1 border-b border-slate-200">
              <span class="text-slate-600">Buffer de Seguridad Aplicado:</span>
              <span class="font-bold text-slate-500">${res.safety_buffer} u.</span>
            </div>
            <div class="flex justify-between py-1 pt-2">
              <span class="font-bold text-emerald-800">Stock a Sincronizar en Publicación:</span>
              <span class="font-black text-emerald-600 text-sm">${res.syncable_stock_for_meli} u.</span>
            </div>
          `;
        } catch (e) {
          resultsEl.innerHTML = `<p class="text-red-600 text-center py-2">${e.message}</p>`;
        }
      }

      if (selectEl) {
        selectEl.addEventListener("change", (e) => refreshSyncCalc(e.target.value));
        refreshSyncCalc(variants[0].id);
      }
    } catch (err) {
      showToast(err.message, "error");
    }
  }

  async function openKardexModal() {
    try {
      const data = await api.get("/inventory/movements", { page: 1, size: 20 });
      const items = data.items || [];

      openModal({
        title: "Kardex de Movimientos (Pista de Auditoría)",
        size: "lg",
        content: `
          <div class="space-y-4">
            <p class="text-xs text-slate-500">
              Registro inmutable de entradas, salidas, reservas, liberaciones, ajustes y devoluciones.
            </p>

            ${items.length === 0 ? `
              <div class="py-8 text-center text-slate-400 text-xs">No hay movimientos registrados en el Kardex.</div>
            ` : `
              <div class="table-container max-h-96 overflow-y-auto">
                <table class="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr class="border-b border-slate-200 bg-slate-50 text-slate-500 font-bold uppercase text-[10px]">
                      <th class="py-2.5 px-3">Fecha</th>
                      <th class="py-2.5 px-3">Tipo</th>
                      <th class="py-2.5 px-3 text-center">Delta</th>
                      <th class="py-2.5 px-3 text-center">Antes &rarr; Después</th>
                      <th class="py-2.5 px-3">Referencia</th>
                      <th class="py-2.5 px-3">Notas</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-slate-100 text-slate-700">
                    ${items.map(m => {
                      const isPositive = m.quantity_delta > 0;
                      return `
                        <tr>
                          <td class="py-2 px-3 font-mono text-[11px] text-slate-500 whitespace-nowrap">
                            ${new Date(m.created_at).toLocaleString('es-MX')}
                          </td>
                          <td class="py-2 px-3 font-bold font-mono text-[11px]">${m.movement_type}</td>
                          <td class="py-2 px-3 text-center font-bold ${isPositive ? 'text-emerald-600' : 'text-rose-600'}">
                            ${isPositive ? '+' : ''}${m.quantity_delta}
                          </td>
                          <td class="py-2 px-3 text-center font-mono text-[11px] text-slate-500">
                            ${m.quantity_before} &rarr; <span class="font-bold text-slate-800">${m.quantity_after}</span>
                          </td>
                          <td class="py-2 px-3 font-mono text-[11px] text-slate-600">${m.reference_id || '-'}</td>
                          <td class="py-2 px-3 text-slate-600 text-[11px]">${m.notes || '-'}</td>
                        </tr>
                      `;
                    }).join("")}
                  </tbody>
                </table>
              </div>
            `}
          </div>
        `,
        confirmText: "Cerrar",
      });
    } catch (err) {
      showToast(err.message, "error");
    }
  }

  return container;
}


// Adaptador para app.js: la app espera renderInventory(contenedor) y descarta el
// valor de retorno; renderInventoryView() no recibe argumentos y devuelve el elemento.
export function renderInventory(container) {
  const el = renderInventoryView();
  if (container) container.appendChild(el);
  return el;
}

/**
 * Vista 5: Almacenes & Centros Logísticos (Físicos, Sucursales y Mercado Envíos FULL).
 * Incluye gestión de bodegas, transferencias entre almacenes y auditoría de conteos físicos cíclicos.
 */

import { api } from "../api.js";
import { state } from "../state.js";
import { icons } from "../icons.js";
import { openModal } from "../components/modal.js";
import { showToast } from "../components/toast.js";

export function renderWarehousesView() {
  const container = document.createElement("div");
  container.className = "space-y-6 animate-fade-in";

  let activeTab = "warehouses"; // "warehouses" | "transfers" | "counts"

  container.innerHTML = `
    <!-- Encabezado de Sección -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
      <div>
        <h2 class="text-2xl font-black text-slate-900 tracking-tight">Almacenes & Logística Interna</h2>
        <p class="text-xs text-slate-500 mt-0.5">
          Gestión de almacenes propios, bodegas MeLi Full (FULL_MLM), transferencias y conteos cíclicos
        </p>
      </div>

      <div class="flex items-center space-x-2" id="warehouse-header-actions">
        <button id="btn-create-warehouse" class="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl transition-smooth shadow-md shadow-blue-600/30 flex items-center space-x-2 touch-target">
          ${icons.plus("w-4 h-4")}
          <span>Nuevo Almacén</span>
        </button>
      </div>
    </div>

    <!-- Navegación por Pestañas -->
    <div class="flex border-b border-slate-200 space-x-6 text-xs font-bold">
      <button id="tab-btn-warehouses" class="py-2.5 border-b-2 border-blue-600 text-blue-600 transition-smooth">
        Centros & Bodegas
      </button>
      <button id="tab-btn-transfers" class="py-2.5 border-b-2 border-transparent text-slate-500 hover:text-slate-800 transition-smooth">
        Transferencias de Mercancía
      </button>
      <button id="tab-btn-counts" class="py-2.5 border-b-2 border-transparent text-slate-500 hover:text-slate-800 transition-smooth">
        Conteos Físicos & Auditoría
      </button>
    </div>

    <!-- Contenido Dinámico según Pestaña -->
    <div id="tab-content-container">
      <!-- Se carga dinámicamente -->
    </div>
  `;

  const tabBtnWh = container.querySelector("#tab-btn-warehouses");
  const tabBtnTrf = container.querySelector("#tab-btn-transfers");
  const tabBtnCnt = container.querySelector("#tab-btn-counts");
  const actionsContainer = container.querySelector("#warehouse-header-actions");
  const contentContainer = container.querySelector("#tab-content-container");

  function setTab(tab) {
    activeTab = tab;
    [tabBtnWh, tabBtnTrf, tabBtnCnt].forEach(b => {
      b.className = "py-2.5 border-b-2 border-transparent text-slate-500 hover:text-slate-800 transition-smooth";
    });

    if (tab === "warehouses") {
      tabBtnWh.className = "py-2.5 border-b-2 border-blue-600 text-blue-600 transition-smooth";
      actionsContainer.innerHTML = `
        <button id="btn-create-warehouse" class="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl transition-smooth shadow-md shadow-blue-600/30 flex items-center space-x-2 touch-target">
          ${icons.plus("w-4 h-4")}
          <span>Nuevo Almacén</span>
        </button>
      `;
      actionsContainer.querySelector("#btn-create-warehouse").addEventListener("click", openCreateWarehouseModal);
      renderWarehousesTab();
    } else if (tab === "transfers") {
      tabBtnTrf.className = "py-2.5 border-b-2 border-blue-600 text-blue-600 transition-smooth";
      actionsContainer.innerHTML = `
        <button id="btn-new-transfer" class="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl transition-smooth shadow-md shadow-blue-600/30 flex items-center space-x-2 touch-target">
          ${icons.plus("w-4 h-4")}
          <span>Nueva Transferencia</span>
        </button>
      `;
      actionsContainer.querySelector("#btn-new-transfer").addEventListener("click", openNewTransferModal);
      renderTransfersTab();
    } else if (tab === "counts") {
      tabBtnCnt.className = "py-2.5 border-b-2 border-blue-600 text-blue-600 transition-smooth";
      actionsContainer.innerHTML = `
        <button id="btn-new-count" class="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl transition-smooth shadow-md shadow-blue-600/30 flex items-center space-x-2 touch-target">
          ${icons.plus("w-4 h-4")}
          <span>Nuevo Conteo Físico</span>
        </button>
      `;
      actionsContainer.querySelector("#btn-new-count").addEventListener("click", openNewCountModal);
      renderCountsTab();
    }
  }

  tabBtnWh.addEventListener("click", () => setTab("warehouses"));
  tabBtnTrf.addEventListener("click", () => setTab("transfers"));
  tabBtnCnt.addEventListener("click", () => setTab("counts"));

  setTab("warehouses");

  // ==========================================
  // PESTAÑA 1: ALMACENES
  // ==========================================
  async function renderWarehousesTab() {
    contentContainer.innerHTML = `
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" id="warehouses-cards-grid">
        <div class="col-span-full py-12 text-center text-slate-400">
          ${icons.spinner("w-5 h-5 inline-block mr-2")} Cargando almacenes...
        </div>
      </div>
    `;

    try {
      const data = await api.get("/warehouses");
      const items = data.items || [];
      const grid = contentContainer.querySelector("#warehouses-cards-grid");

      if (items.length === 0) {
        grid.innerHTML = `
          <div class="col-span-full p-12 bg-white rounded-3xl border border-dashed border-slate-300 text-center text-slate-500 space-y-3">
            <div class="mx-auto w-12 h-12 rounded-2xl bg-blue-50 text-blue-600 flex items-center justify-center">
              ${icons.warehouses("w-6 h-6")}
            </div>
            <p class="text-sm font-bold text-slate-800">No hay almacenes registrados</p>
            <p class="text-xs text-slate-400 max-w-sm mx-auto">
              Crea tu almacén físico central o vincula el centro logístico de Mercado Libre Full.
            </p>
          </div>
        `;
        return;
      }

      grid.innerHTML = items.map(wh => {
        const isFull = wh.is_fulfillment || wh.warehouse_type === "meli_fulfillment";
        const typeBadge = isFull
          ? '<span class="badge badge-meli text-[10px]">Mercado Libre FULL</span>'
          : '<span class="badge badge-info text-[10px]">Almacén Propio</span>';

        return `
          <div class="p-5 bg-white rounded-3xl border border-slate-200 shadow-sm hover:shadow-md transition-smooth flex flex-col justify-between space-y-4">
            <div>
              <div class="flex items-start justify-between">
                <div class="p-2.5 rounded-2xl ${isFull ? 'bg-amber-50 text-amber-700' : 'bg-blue-50 text-blue-700'}">
                  ${icons.warehouses("w-6 h-6")}
                </div>
                ${typeBadge}
              </div>

              <div class="mt-4">
                <h3 class="text-base font-bold text-slate-900">${wh.name}</h3>
                <p class="text-xs font-mono font-medium text-slate-500">Código: ${wh.code}</p>
                <p class="text-xs text-slate-600 mt-2 line-clamp-2">${wh.address || 'Sin dirección física especificada.'}</p>
              </div>
            </div>

            <div class="pt-3 border-t border-slate-100 flex items-center justify-between text-xs font-semibold">
              <span class="text-emerald-600 flex items-center space-x-1">
                <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
                <span>Operativo</span>
              </span>
              <span class="text-slate-400 font-mono text-[10px]">ID: ${wh.id.slice(0, 8)}...</span>
            </div>
          </div>
        `;
      }).join("");

    } catch (err) {
      contentContainer.innerHTML = `<div class="p-8 text-center text-red-600 font-semibold">${err.message}</div>`;
    }
  }

  function openCreateWarehouseModal() {
    openModal({
      title: "Alta de Almacén o Centro Logístico",
      size: "md",
      content: `
        <div class="space-y-4">
          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1">Nombre del Almacén</label>
            <input id="wh-name-input" type="text" placeholder="Ej. Almacén Central CDMX o Bodega MeLi Full" class="w-full px-3 py-2 text-xs border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-600 focus:outline-none" />
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Código Único</label>
              <input id="wh-code-input" type="text" placeholder="Ej. ALM-01 o FULL-MX" class="w-full px-3 py-2 text-xs font-mono uppercase border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-600 focus:outline-none" />
            </div>

            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Tipo de Almacén</label>
              <select id="wh-type-select" class="w-full px-3 py-2 text-xs border border-slate-200 rounded-xl bg-slate-50 focus:bg-white focus:outline-none">
                <option value="internal">Almacén Propio / CEDIS</option>
                <option value="meli_fulfillment">Mercado Libre Full (FULL_MLM)</option>
                <option value="store">Sucursal / Tienda Física</option>
                <option value="dropship">Dropshipping</option>
              </select>
            </div>
          </div>

          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1">Dirección Física (Opcional)</label>
            <input id="wh-address-input" type="text" placeholder="Calle, Número, Colonia, C.P., Ciudad" class="w-full px-3 py-2 text-xs border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-600 focus:outline-none" />
          </div>
        </div>
      `,
      confirmText: "Registrar Almacén",
      onConfirm: async () => {
        const name = document.getElementById("wh-name-input").value.trim();
        const code = document.getElementById("wh-code-input").value.trim().toUpperCase();
        const type = document.getElementById("wh-type-select").value;
        const address = document.getElementById("wh-address-input").value.trim();

        if (!name || !code) throw new Error("El nombre y código de almacén son obligatorios.");

        const activeCompany = state.getActiveCompany();
        if (!activeCompany) throw new Error("No hay empresa activa seleccionada.");

        await api.post("/warehouses", {
          company_id: activeCompany.id,
          name: name,
          code: code,
          warehouse_type: type,
          is_fulfillment: type === "meli_fulfillment",
          address: address || null,
        });

        showToast("Almacén registrado exitosamente.", "success");
        renderWarehousesTab();
      },
    });
  }

  // ==========================================
  // PESTAÑA 2: TRANSFERENCIAS ENTRE ALMACENES
  // ==========================================
  async function renderTransfersTab() {
    contentContainer.innerHTML = `
      <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="p-4 border-b border-slate-100 flex items-center justify-between">
          <span class="text-xs font-bold text-slate-800 uppercase tracking-wider">Historial de Transferencias</span>
        </div>
        <div class="table-container">
          <table class="w-full text-left text-xs border-collapse">
            <thead>
              <tr class="border-b border-slate-200 bg-slate-50/70 text-slate-500 font-bold uppercase text-[10px]">
                <th class="py-3 px-4">Folio</th>
                <th class="py-3 px-4">Origen &rarr; Destino</th>
                <th class="py-3 px-4 text-center">Partidas</th>
                <th class="py-3 px-4">Estatus</th>
                <th class="py-3 px-4">Fecha de Envío</th>
                <th class="py-3 px-4 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody id="transfers-table-tbody" class="divide-y divide-slate-100 text-slate-700">
              <tr>
                <td colspan="6" class="py-10 text-center text-slate-400">
                  ${icons.spinner("w-5 h-5 inline-block mr-2")} Cargando transferencias...
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    `;

    try {
      const data = await api.get("/warehouses/transfers/list");
      const items = data.items || [];
      const tbody = contentContainer.querySelector("#transfers-table-tbody");

      if (items.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="6" class="py-10 text-center text-slate-400">
              No hay transferencias registradas. Pulsa en "Nueva Transferencia" para enviar mercancía entre almacenes o a MeLi Full.
            </td>
          </tr>
        `;
        return;
      }

      tbody.innerHTML = items.map(trf => {
        let badge = '<span class="badge badge-info text-[10px]">En Tránsito</span>';
        if (trf.status === "received") badge = '<span class="badge badge-success text-[10px]">Recibido</span>';
        if (trf.status === "cancelled") badge = '<span class="badge badge-danger text-[10px]">Cancelado</span>';

        return `
          <tr class="hover:bg-slate-50/80 transition-smooth">
            <td class="py-3 px-4 font-mono font-bold text-slate-900">${trf.transfer_number}</td>
            <td class="py-3 px-4 font-mono text-slate-600 text-[11px]">
              ${trf.source_warehouse_id.slice(0, 8)}... &rarr; <span class="font-bold text-slate-800">${trf.target_warehouse_id.slice(0, 8)}...</span>
            </td>
            <td class="py-3 px-4 text-center font-bold text-slate-800">${(trf.items || []).length}</td>
            <td class="py-3 px-4">${badge}</td>
            <td class="py-3 px-4 text-slate-500 font-mono text-[11px]">
              ${trf.shipped_at ? new Date(trf.shipped_at).toLocaleString('es-MX') : '-'}
            </td>
            <td class="py-3 px-4 text-right">
              ${trf.status === 'in_transit' ? `
                <button class="btn-receive-trf px-2.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg font-bold text-[11px] transition-smooth" data-id="${trf.id}">
                  Confirmar Recepción
                </button>
              ` : `
                <span class="text-slate-400 text-[11px] italic">Completada</span>
              `}
            </td>
          </tr>
        `;
      }).join("");

      tbody.querySelectorAll(".btn-receive-trf").forEach(btn => {
        btn.addEventListener("click", () => openReceiveTransferModal(btn.dataset.id));
      });

    } catch (err) {
      contentContainer.innerHTML = `<div class="p-8 text-center text-red-600 font-semibold">${err.message}</div>`;
    }
  }

  async function openNewTransferModal() {
    try {
      const [whData, prodData] = await Promise.all([
        api.get("/warehouses"),
        api.get("/products", { size: 50 }),
      ]);
      const warehouses = whData.items || [];
      const products = prodData.items || [];

      if (warehouses.length < 2) {
        showToast("Debes tener al menos dos almacenes registrados para realizar una transferencia.", "warning");
        return;
      }

      const variants = [];
      products.forEach(p => {
        (p.variants || []).forEach(v => variants.push({ ...v, prodTitle: p.title }));
      });

      if (variants.length === 0) {
        showToast("No hay variantes de producto disponibles.", "warning");
        return;
      }

      openModal({
        title: "Nueva Transferencia entre Almacenes",
        size: "md",
        content: `
          <div class="space-y-4">
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Almacén de Origen</label>
              <select id="trf-src-select" class="w-full px-3 py-2 text-xs border border-slate-200 rounded-xl bg-slate-50 focus:bg-white focus:outline-none">
                ${warehouses.map(w => `<option value="${w.id}">${w.name} (${w.code})</option>`).join("")}
              </select>
            </div>

            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Almacén de Destino (o MeLi Full)</label>
              <select id="trf-tgt-select" class="w-full px-3 py-2 text-xs border border-slate-200 rounded-xl bg-slate-50 focus:bg-white focus:outline-none">
                ${warehouses.map((w, idx) => `<option value="${w.id}" ${idx === 1 ? 'selected' : ''}>${w.name} (${w.code}${w.is_fulfillment ? ' - FULL' : ''})</option>`).join("")}
              </select>
            </div>

            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Producto / Variante a Transferir</label>
              <select id="trf-var-select" class="w-full px-3 py-2 text-xs border border-slate-200 rounded-xl bg-slate-50 focus:bg-white focus:outline-none font-mono">
                ${variants.map(v => `<option value="${v.id}">SKU: ${v.sku} - ${v.prodTitle}</option>`).join("")}
              </select>
            </div>

            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Cantidad a Transferir</label>
              <input id="trf-qty-input" type="number" min="1" value="10" class="w-full px-3 py-2 text-xs font-mono border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-600 focus:outline-none" />
            </div>

            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Notas de Envío / Guía</label>
              <input id="trf-notes-input" type="text" placeholder="Ej. Envío a bodega Tultitlán MeLi Full" class="w-full px-3 py-2 text-xs border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-600 focus:outline-none" />
            </div>
          </div>
        `,
        confirmText: "Despachar Transferencia",
        onConfirm: async () => {
          const srcId = document.getElementById("trf-src-select").value;
          const tgtId = document.getElementById("trf-tgt-select").value;
          const varId = document.getElementById("trf-var-select").value;
          const qty = parseInt(document.getElementById("trf-qty-input").value);
          const notes = document.getElementById("trf-notes-input").value.trim();

          if (srcId === tgtId) throw new Error("El almacén de origen y destino deben ser diferentes.");
          if (isNaN(qty) || qty <= 0) throw new Error("La cantidad debe ser mayor a 0.");

          const activeCompany = state.getActiveCompany();
          await api.post("/warehouses/transfers", {
            company_id: activeCompany.id,
            source_warehouse_id: srcId,
            target_warehouse_id: tgtId,
            notes: notes || null,
            items: [{ variant_id: varId, quantity_sent: qty }],
          });

          showToast("Transferencia creada y despachada.", "success");
          renderTransfersTab();
        },
      });
    } catch (err) {
      showToast(err.message, "error");
    }
  }

  async function openReceiveTransferModal(transferId) {
    try {
      const trf = await api.get(`/warehouses/transfers/${transferId}`);
      openModal({
        title: `Recepción de Transferencia #${trf.transfer_number}`,
        size: "md",
        content: `
          <div class="space-y-4">
            <p class="text-xs text-slate-600">
              Confirma las cantidades efectivamente recibidas en el almacén de destino para ingresar el inventario físico.
            </p>

            <div class="space-y-2">
              ${(trf.items || []).map((it, idx) => `
                <div class="p-3 bg-slate-50 border border-slate-200 rounded-xl flex items-center justify-between">
                  <div class="text-xs">
                    <span class="font-mono font-bold text-slate-800">Variante: ${it.variant_id.slice(0, 8)}...</span>
                    <p class="text-slate-500">Cantidad enviada: <span class="font-bold">${it.quantity_sent}</span> u.</p>
                  </div>
                  <div>
                    <label class="block text-[10px] font-bold text-slate-500 mb-1">Recibido:</label>
                    <input id="rec-qty-${idx}" type="number" min="0" value="${it.quantity_sent}" data-var="${it.variant_id}" class="w-20 px-2 py-1 text-xs font-mono font-bold text-center border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-600 focus:outline-none" />
                  </div>
                </div>
              `).join("")}
            </div>
          </div>
        `,
        confirmText: "Confirmar Ingreso a Inventario",
        onConfirm: async () => {
          const receivedItems = [];
          (trf.items || []).forEach((it, idx) => {
            const input = document.getElementById(`rec-qty-${idx}`);
            const qty = parseInt(input.value) || 0;
            receivedItems.push({ variant_id: it.variant_id, quantity_received: qty });
          });

          await api.post(`/warehouses/transfers/${transferId}/receive`, {
            items: receivedItems,
            notes: "Recepción confirmada en destino.",
          });

          showToast("Mercancía ingresada al inventario de destino.", "success");
          renderTransfersTab();
        },
      });
    } catch (err) {
      showToast(err.message, "error");
    }
  }

  // ==========================================
  // PESTAÑA 3: CONTEOS FÍSICOS Y AUDITORÍA
  // ==========================================
  async function renderCountsTab() {
    contentContainer.innerHTML = `
      <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="p-4 border-b border-slate-100 flex items-center justify-between">
          <span class="text-xs font-bold text-slate-800 uppercase tracking-wider">Sesiones de Conteo Físico Cíclico</span>
        </div>
        <div class="table-container">
          <table class="w-full text-left text-xs border-collapse">
            <thead>
              <tr class="border-b border-slate-200 bg-slate-50/70 text-slate-500 font-bold uppercase text-[10px]">
                <th class="py-3 px-4">Folio de Conteo</th>
                <th class="py-3 px-4">Almacén</th>
                <th class="py-3 px-4 text-center">Partidas Auditadas</th>
                <th class="py-3 px-4">Estatus</th>
                <th class="py-3 px-4">Fecha de Aplicación</th>
                <th class="py-3 px-4 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody id="counts-table-tbody" class="divide-y divide-slate-100 text-slate-700">
              <tr>
                <td colspan="6" class="py-10 text-center text-slate-400">
                  ${icons.spinner("w-5 h-5 inline-block mr-2")} Cargando auditorías...
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    `;

    try {
      const data = await api.get("/warehouses/counts/list");
      const items = data.items || [];
      const tbody = contentContainer.querySelector("#counts-table-tbody");

      if (items.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="6" class="py-10 text-center text-slate-400">
              No hay conteos físicos registrados. Pulsa en "Nuevo Conteo Físico" para auditar estanterías.
            </td>
          </tr>
        `;
        return;
      }

      tbody.innerHTML = items.map(cnt => {
        let badge = '<span class="badge badge-warning text-[10px]">En Progreso</span>';
        if (cnt.status === "applied") badge = '<span class="badge badge-success text-[10px]">Aplicado en Kardex</span>';

        return `
          <tr class="hover:bg-slate-50/80 transition-smooth">
            <td class="py-3 px-4 font-mono font-bold text-slate-900">${cnt.count_number}</td>
            <td class="py-3 px-4 font-mono text-slate-600 text-[11px]">${cnt.warehouse_id.slice(0, 8)}...</td>
            <td class="py-3 px-4 text-center font-bold text-slate-800">${(cnt.items || []).length}</td>
            <td class="py-3 px-4">${badge}</td>
            <td class="py-3 px-4 text-slate-500 font-mono text-[11px]">
              ${cnt.applied_at ? new Date(cnt.applied_at).toLocaleString('es-MX') : '-'}
            </td>
            <td class="py-3 px-4 text-right">
              ${cnt.status === 'in_progress' ? `
                <button class="btn-apply-cnt px-2.5 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-bold text-[11px] transition-smooth" data-id="${cnt.id}">
                  Aplicar Ajustes
                </button>
              ` : `
                <span class="text-slate-400 text-[11px] italic">Conciliado</span>
              `}
            </td>
          </tr>
        `;
      }).join("");

      tbody.querySelectorAll(".btn-apply-cnt").forEach(btn => {
        btn.addEventListener("click", () => applyPhysicalCount(btn.dataset.id));
      });

    } catch (err) {
      contentContainer.innerHTML = `<div class="p-8 text-center text-red-600 font-semibold">${err.message}</div>`;
    }
  }

  async function openNewCountModal() {
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
        showToast("No hay variantes disponibles para auditar.", "warning");
        return;
      }

      openModal({
        title: "Nuevo Conteo Físico Cíclico",
        size: "md",
        content: `
          <div class="space-y-4">
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Almacén a Auditar</label>
              <select id="cnt-wh-select" class="w-full px-3 py-2 text-xs border border-slate-200 rounded-xl bg-slate-50 focus:bg-white focus:outline-none">
                ${warehouses.map(w => `<option value="${w.id}">${w.name} (${w.code})</option>`).join("")}
              </select>
            </div>

            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Variante a Contar</label>
              <select id="cnt-var-select" class="w-full px-3 py-2 text-xs border border-slate-200 rounded-xl bg-slate-50 focus:bg-white focus:outline-none font-mono">
                ${variants.map(v => `<option value="${v.id}">SKU: ${v.sku} - ${v.prodTitle}</option>`).join("")}
              </select>
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-xs font-bold text-slate-700 mb-1">Cantidad Física Contada</label>
                <input id="cnt-qty-input" type="number" min="0" value="0" class="w-full px-3 py-2 text-xs font-mono font-bold border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-600 focus:outline-none" />
              </div>

              <div>
                <label class="block text-xs font-bold text-slate-700 mb-1">Ubicación (Bin)</label>
                <input id="cnt-bin-input" type="text" placeholder="Ej. A-01-R1" class="w-full px-3 py-2 text-xs font-mono uppercase border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-600 focus:outline-none" />
              </div>
            </div>

            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Notas de Auditoría</label>
              <input id="cnt-notes-input" type="text" placeholder="Conteo cíclico mensual de pasillo A" class="w-full px-3 py-2 text-xs border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-600 focus:outline-none" />
            </div>
          </div>
        `,
        confirmText: "Iniciar Conteo",
        onConfirm: async () => {
          const whId = document.getElementById("cnt-wh-select").value;
          const varId = document.getElementById("cnt-var-select").value;
          const qty = parseInt(document.getElementById("cnt-qty-input").value) || 0;
          const bin = document.getElementById("cnt-bin-input").value.trim();
          const notes = document.getElementById("cnt-notes-input").value.trim();

          const activeCompany = state.getActiveCompany();
          await api.post("/warehouses/counts", {
            company_id: activeCompany.id,
            warehouse_id: whId,
            notes: notes || null,
            items: [{
              variant_id: varId,
              counted_quantity: qty,
              location_bin: bin || null,
            }],
          });

          showToast("Sesión de conteo físico creada.", "success");
          renderCountsTab();
        },
      });
    } catch (err) {
      showToast(err.message, "error");
    }
  }

  async function applyPhysicalCount(countId) {
    try {
      await api.post(`/warehouses/counts/${countId}/apply`, {});
      showToast("Conteo aplicado con éxito en Kardex (CYCLE_COUNT).", "success");
      renderCountsTab();
    } catch (err) {
      showToast(err.message, "error");
    }
  }

  return container;
}

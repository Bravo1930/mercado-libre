/**
 * Vista 5: Almacenes y Centros Logísticos (Físicos y MeLi Fulfillment FULL).
 */

import { api } from "../api.js";
import { state } from "../state.js";
import { icons } from "../icons.js";
import { openModal } from "../components/modal.js";
import { showToast } from "../components/toast.js";

export function renderWarehousesView() {
  const container = document.createElement("div");
  container.className = "space-y-5 animate-fade-in";

  container.innerHTML = `
    <!-- Encabezado de Sección -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
      <div>
        <h2 class="text-2xl font-black text-slate-900 tracking-tight">Almacenes & Centros Logísticos</h2>
        <p class="text-xs text-slate-500 mt-0.5">Gestión de bodegas internas, CEDIS y centros de Mercado Libre Full (FULL_MLM)</p>
      </div>

      <button id="btn-create-warehouse" class="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl transition-smooth shadow-md shadow-blue-600/30 flex items-center space-x-2 touch-target">
        ${icons.plus("w-4 h-4")}
        <span>Nuevo Almacén</span>
      </button>
    </div>

    <!-- Lista de Almacenes en Cards -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" id="warehouses-cards-grid">
      <div class="col-span-full py-12 text-center text-slate-400">
        ${icons.spinner("w-5 h-5 inline-block mr-2")} Cargando centros logísticos...
      </div>
    </div>
  `;

  const btnCreate = container.querySelector("#btn-create-warehouse");
  if (btnCreate) btnCreate.addEventListener("click", () => openCreateWarehouseModal());

  async function fetchWarehouses() {
    const grid = container.querySelector("#warehouses-cards-grid");

    try {
      const data = await api.get("/warehouses");
      const items = data.items || [];

      if (items.length === 0) {
        grid.innerHTML = `
          <div class="col-span-full p-12 bg-white rounded-3xl border border-dashed border-slate-300 text-center text-slate-500 space-y-3">
            <div class="mx-auto w-12 h-12 rounded-2xl bg-blue-50 text-blue-600 flex items-center justify-center">
              ${icons.warehouses("w-6 h-6")}
            </div>
            <p class="text-sm font-bold text-slate-800">No hay almacenes registrados</p>
            <p class="text-xs text-slate-400 max-w-sm mx-auto">Agrega tu primer almacén físico o vincula el centro logístico de Mercado Libre Full para comenzar a gestionar inventarios.</p>
          </div>
        `;
      } else {
        grid.innerHTML = items.map(wh => {
          const isFull = wh.warehouse_type === 'fulfillment_meli' || wh.code.includes('FULL');
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
      }
    } catch (err) {
      grid.innerHTML = `<div class="col-span-full py-8 text-center text-red-600 font-semibold">Error al cargar almacenes: ${err.message}</div>`;
    }
  }

  function openCreateWarehouseModal() {
    openModal({
      title: "Alta de Centro Logístico / Almacén",
      size: "md",
      content: `
        <div class="space-y-4">
          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1">Nombre del Almacén</label>
            <input id="wh-name-input" type="text" placeholder="CEDIS Central CDMX" class="w-full px-3 py-2 text-xs border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-600 focus:outline-none" />
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Código Único</label>
              <input id="wh-code-input" type="text" placeholder="CEDIS-CDMX" class="w-full px-3 py-2 text-xs font-mono uppercase border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-600 focus:outline-none" />
            </div>
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Tipo de Centro</label>
              <select id="wh-type-input" class="w-full px-3 py-2 text-xs border border-slate-200 rounded-xl bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600">
                <option value="physical">Almacén Físico Propio</option>
                <option value="fulfillment_meli">Mercado Libre Full (Fulfillment)</option>
              </select>
            </div>
          </div>

          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1">Dirección de Ubicación</label>
            <input id="wh-address-input" type="text" placeholder="Av. Insurgentes Sur 1602, Benito Juárez, CDMX" class="w-full px-3 py-2 text-xs border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-600 focus:outline-none" />
          </div>
        </div>
      `,
      confirmText: "Registrar Almacén",
      onConfirm: async () => {
        const name = document.getElementById("wh-name-input").value.trim();
        const code = document.getElementById("wh-code-input").value.trim().toUpperCase();
        const type = document.getElementById("wh-type-input").value;
        const address = document.getElementById("wh-address-input").value.trim();

        if (!name || !code) throw new Error("Nombre y código son obligatorios.");
        if (!state.currentCompany) throw new Error("Selecciona una empresa activa.");

        const payload = {
          company_id: state.currentCompany.company_id,
          name,
          code,
          warehouse_type: type,
          address,
          is_active: true,
        };

        await api.post("/warehouses", payload);
        showToast("Almacén registrado exitosamente.", "success");
        fetchWarehouses();
      }
    });
  }

  fetchWarehouses();
  return container;
}

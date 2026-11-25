/**
 * Vista de Catálogo Maestro de Productos del ERP
 * Alta, edición, desactivación, variantes, SKU único, código de barras, fotos,
 * importación desde Mercado Libre, importación CSV, exportación CSV/XLSX,
 * asociación de publicaciones externas multi-cuenta y detector de duplicados.
 */

import { api } from "../api.js";
import { state } from "../state.js";
import { icons } from "../icons.js";
import { openModal, closeModal, showConfirmDialog } from "../components/modal.js";
import { showToast } from "../components/toast.js";

let productsList = [];
let categoriesList = [];
let currentSearch = "";
let currentCategory = "";
let currentStatusFilter = "all";
let currentPage = 1;
let totalPages = 1;

export async function renderProducts(container) {
  container.innerHTML = `
    <div class="space-y-6">
      <!-- Encabezado y Acciones Principales -->
      <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
        <div>
          <h1 class="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            ${icons.cube} Catálogo Maestro de Productos
          </h1>
          <p class="text-sm text-slate-500 mt-1">
            Gestión integral de productos, variantes, códigos EAN, costos, publicaciones MeLi multi-cuenta y exportación contable.
          </p>
        </div>

        <!-- Botonera de Acciones -->
        <div class="flex flex-wrap items-center gap-2">
          <button id="btn-check-duplicates" class="btn-secondary text-xs flex items-center gap-1.5 py-2 px-3 border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100">
            ${icons.alert} Detector de Duplicados
          </button>
          <button id="btn-import-meli" class="btn-secondary text-xs flex items-center gap-1.5 py-2 px-3 bg-yellow-400 hover:bg-yellow-500 text-slate-900 font-bold border-none">
            ${icons.refresh} Importar de MeLi
          </button>
          <button id="btn-import-csv" class="btn-secondary text-xs flex items-center gap-1.5 py-2 px-3">
            ${icons.download} Importar CSV
          </button>
          <div class="inline-flex rounded-xl shadow-sm">
            <button id="btn-export-csv" class="btn-secondary text-xs rounded-r-none border-r-0 py-2 px-3" title="Descargar CSV">
              CSV
            </button>
            <button id="btn-export-xlsx" class="btn-secondary text-xs rounded-l-none py-2 px-3 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border-emerald-300 font-bold" title="Descargar Excel XLSX">
              Excel (.xlsx)
            </button>
          </div>
          <button id="btn-create-product" class="btn-primary flex items-center gap-1.5 text-xs py-2 px-3.5">
            ${icons.plus} Nuevo Producto
          </button>
        </div>
      </div>

      <!-- Filtros y Búsqueda Multicriterio -->
      <div class="card p-4 space-y-3">
        <div class="grid grid-cols-1 sm:grid-cols-12 gap-3">
          <!-- Búsqueda global -->
          <div class="sm:col-span-5 relative">
            <span class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
              ${icons.search}
            </span>
            <input
              type="text"
              id="products-search-input"
              class="input-field pl-9 text-xs"
              placeholder="Buscar por SKU, código de barras EAN, nombre, marca o modelo..."
            />
          </div>

          <!-- Filtro por Categoría -->
          <div class="sm:col-span-4">
            <select id="products-category-select" class="input-field text-xs py-2">
              <option value="">Todas las Categorías</option>
            </select>
          </div>

          <!-- Filtro por Estatus -->
          <div class="sm:col-span-3">
            <select id="products-status-select" class="input-field text-xs py-2">
              <option value="all">Todos los Estatus</option>
              <option value="true">Solo Activos</option>
              <option value="false">Solo Inactivos / Desactivados</option>
            </select>
          </div>
        </div>
      </div>

      <!-- Tabla del Catálogo Maestro -->
      <div class="card overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-left border-collapse text-xs">
            <thead>
              <tr class="bg-slate-50 border-b border-slate-200 text-slate-600 font-bold uppercase tracking-wider text-[11px]">
                <th class="p-3">Producto / Marca / Modelo</th>
                <th class="p-3">SKU & Código EAN</th>
                <th class="p-3">Categoría</th>
                <th class="p-3">Costos & Precios (MXN)</th>
                <th class="p-3">Dimensiones / Ubicación</th>
                <th class="p-3 text-center">Publicaciones MeLi</th>
                <th class="p-3">Estatus</th>
                <th class="p-3 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody id="products-table-body" class="divide-y divide-slate-100">
              <tr>
                <td colspan="8" class="p-8 text-center text-slate-400">Cargando catálogo maestro de productos...</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Paginación -->
        <div class="flex items-center justify-between p-3.5 bg-slate-50/50 border-t border-slate-100 text-xs text-slate-600">
          <span id="products-count-label">Cargando...</span>
          <div class="flex items-center gap-1.5">
            <button id="btn-products-prev-page" class="btn-secondary text-xs py-1 px-2.5" disabled>Anterior</button>
            <span id="products-page-label" class="font-bold px-2">1</span>
            <button id="btn-products-next-page" class="btn-secondary text-xs py-1 px-2.5" disabled>Siguiente</button>
          </div>
        </div>
      </div>
    </div>
  `;

  // Bind Main Toolbar Events
  container.querySelector("#btn-create-product").addEventListener("click", () => openProductFormModal(null));
  container.querySelector("#btn-import-meli").addEventListener("click", openMeliImportModal);
  container.querySelector("#btn-import-csv").addEventListener("click", openCsvImportModal);
  container.querySelector("#btn-export-csv").addEventListener("click", handleExportCsv);
  container.querySelector("#btn-export-xlsx").addEventListener("click", handleExportXlsx);
  container.querySelector("#btn-check-duplicates").addEventListener("click", openDuplicatesModal);

  // Search & Filter Events
  const searchInput = container.querySelector("#products-search-input");
  const catSelect = container.querySelector("#products-category-select");
  const statusSelect = container.querySelector("#products-status-select");

  let debounceTimer;
  searchInput.addEventListener("input", (e) => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      currentSearch = e.target.value.trim();
      currentPage = 1;
      fetchProducts();
    }, 300);
  });

  catSelect.addEventListener("change", (e) => {
    currentCategory = e.target.value;
    currentPage = 1;
    fetchProducts();
  });

  statusSelect.addEventListener("change", (e) => {
    currentStatusFilter = e.target.value;
    currentPage = 1;
    fetchProducts();
  });

  container.querySelector("#btn-products-prev-page").addEventListener("click", () => {
    if (currentPage > 1) {
      currentPage--;
      fetchProducts();
    }
  });

  container.querySelector("#btn-products-next-page").addEventListener("click", () => {
    if (currentPage < totalPages) {
      currentPage++;
      fetchProducts();
    }
  });

  await loadCategories();
  await fetchProducts();
}

export function renderProductsView() {
  const wrapper = document.createElement("div");
  renderProducts(wrapper);
  return wrapper;
}

// -----------------------------------------------------------------------------
// CARGA Y RENDERIZADO DE DATOS
// -----------------------------------------------------------------------------
async function loadCategories() {
  try {
    const res = await api.get("/products/categories");
    categoriesList = Array.isArray(res) ? res : [];
    const select = document.getElementById("products-category-select");
    if (select) {
      select.innerHTML = '<option value="">Todas las Categorías</option>' +
        categoriesList.map(c => `<option value="${c}">${c}</option>`).join("");
    }
  } catch (err) {
    console.error("Error cargando categorías", err);
  }
}

async function fetchProducts() {
  const tbody = document.getElementById("products-table-body");
  if (!tbody) return;

  try {
    let queryParams = `page=${currentPage}&limit=20`;
    if (currentSearch) queryParams += `&q=${encodeURIComponent(currentSearch)}`;
    if (currentCategory) queryParams += `&category=${encodeURIComponent(currentCategory)}`;
    if (currentStatusFilter !== "all") queryParams += `&is_active=${currentStatusFilter}`;

    const res = await api.get(`/products?${queryParams}`);
    productsList = res.items || [];
    totalPages = res.pages || 1;

    renderProductsTable();
    updatePaginationControls(res.total || 0);
  } catch (err) {
    showToast(err.message || "Error al obtener productos del catálogo", "error");
    tbody.innerHTML = `<tr><td colspan="8" class="p-8 text-center text-rose-500">${err.message}</td></tr>`;
  }
}

function updatePaginationControls(total) {
  const countLbl = document.getElementById("products-count-label");
  const pageLbl = document.getElementById("products-page-label");
  const btnPrev = document.getElementById("btn-products-prev-page");
  const btnNext = document.getElementById("btn-products-next-page");

  if (countLbl) countLbl.textContent = `Total: ${total} productos maestros`;
  if (pageLbl) pageLbl.textContent = `${currentPage} / ${totalPages}`;
  if (btnPrev) btnPrev.disabled = currentPage <= 1;
  if (btnNext) btnNext.disabled = currentPage >= totalPages;
}

function renderProductsTable() {
  const tbody = document.getElementById("products-table-body");
  if (!tbody) return;

  if (productsList.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" class="p-8 text-center text-slate-400">
          No se encontraron productos que coincidan con los criterios de búsqueda.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = productsList.map((p) => {
    const firstVar = p.variants && p.variants.length > 0 ? p.variants[0] : null;
    const variantsCount = p.variants ? p.variants.length : 0;
    const primarySku = firstVar ? firstVar.sku : "SIN-SKU";
    const primaryBarcode = firstVar && firstVar.barcode_ean ? firstVar.barcode_ean : "-";

    const imgUrl = p.images && p.images.length > 0
      ? p.images[0]
      : "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%2394A3B8'><rect width='24' height='24' rx='4'/></svg>";

    return `
      <tr class="hover:bg-slate-50/80 transition-colors ${!p.is_active ? 'opacity-60 bg-slate-50/40' : ''}">
        <!-- Producto / Marca / Modelo -->
        <td class="p-3">
          <div class="flex items-center gap-3">
            <img src="${imgUrl}" alt="${p.name}" class="w-10 h-10 object-cover rounded-lg border border-slate-200 bg-white flex-shrink-0" onerror="this.src='data:image/svg+xml,<svg xmlns=\\'http://www.w3.org/2000/svg\\' viewBox=\\'0 0 24 24\\' fill=\\'%23CBD5E1\\'><rect width=\\'24\\' height=\\'24\\' rx=\\'4\\'/></svg>'" />
            <div class="min-w-0">
              <div class="font-bold text-slate-900 truncate max-w-xs" title="${p.name}">${p.name}</div>
              <div class="text-[11px] text-slate-500">
                ${p.brand ? `<strong class="text-slate-700">${p.brand}</strong>` : 'Sin Marca'}
                ${p.model ? `· Mod: ${p.model}` : ''}
              </div>
            </div>
          </div>
        </td>

        <!-- SKU & EAN -->
        <td class="p-3">
          <div class="font-mono font-bold text-slate-800">${primarySku}</div>
          <div class="font-mono text-[11px] text-slate-500 flex items-center gap-1">
            ${icons.tag} ${primaryBarcode}
          </div>
          ${variantsCount > 1 ? `<span class="inline-flex text-[10px] font-bold text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded mt-0.5">+${variantsCount - 1} variantes</span>` : ''}
        </td>

        <!-- Categoría -->
        <td class="p-3">
          <span class="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium bg-slate-100 text-slate-700 max-w-[150px] truncate" title="${p.category || 'General'}">
            ${p.category || 'Sin Categoría'}
          </span>
          <div class="text-[10px] text-slate-400 mt-0.5">Unidad: ${p.unit_of_measure || 'H87'}</div>
        </td>

        <!-- Precios & Costos -->
        <td class="p-3">
          <div class="font-bold text-slate-900 text-xs">$${(parseFloat(p.sale_price) || 0).toFixed(2)} MXN</div>
          <div class="text-[11px] text-slate-500">Costo: $${(parseFloat(p.cost_price) || 0).toFixed(2)}</div>
          ${p.wholesale_price ? `<div class="text-[10px] text-blue-600">Mayoreo: $${parseFloat(p.wholesale_price).toFixed(2)}</div>` : ''}
        </td>

        <!-- Dimensiones / Ubicación -->
        <td class="p-3 text-[11px] text-slate-600">
          <div>${p.weight_kg ? `${p.weight_kg} kg` : '-'} · ${p.length_cm || 0}x${p.width_cm || 0}x${p.height_cm || 0} cm</div>
          <div class="text-slate-500 font-mono text-[10px] mt-0.5">${p.warehouse_location || 'Sin ubicación'}</div>
        </td>

        <!-- Publicaciones MeLi Asociadas -->
        <td class="p-3 text-center">
          <button
            data-mappings-id="${p.id}"
            class="btn-view-mappings inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-bold rounded-lg bg-yellow-50 hover:bg-yellow-100 text-yellow-900 border border-yellow-200 transition-colors"
          >
            ${icons.truck} Ver MeLi
          </button>
          <button
            data-publish-id="${p.id}"
            class="btn-publish-meli inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-bold rounded-lg bg-emerald-50 hover:bg-emerald-100 text-emerald-900 border border-emerald-200 transition-colors mt-1"
            title="Crear la publicación en Mercado Libre desde el ERP"
          >
            Publicar en MeLi
          </button>
        </td>

        <!-- Estatus -->
        <td class="p-3">
          <button
            data-toggle-id="${p.id}"
            data-is-active="${p.is_active}"
            class="btn-toggle-status inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold cursor-pointer transition-colors ${
              p.is_active ? 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100' : 'bg-slate-200 text-slate-600 hover:bg-slate-300'
            }"
            title="Clic para cambiar estatus"
          >
            <span class="w-1.5 h-1.5 rounded-full ${p.is_active ? 'bg-emerald-500' : 'bg-slate-400'}"></span>
            ${p.is_active ? 'Activo' : 'Inactivo'}
          </button>
        </td>

        <!-- Acciones -->
        <td class="p-3 text-right whitespace-nowrap">
          <div class="inline-flex items-center gap-1">
            <button
              data-edit-id="${p.id}"
              class="btn-edit-prod p-1.5 text-slate-600 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
              title="Editar Producto"
            >
              ${icons.edit}
            </button>
            <button
              data-add-variant-id="${p.id}"
              class="btn-add-variant p-1.5 text-slate-600 hover:text-emerald-600 hover:bg-emerald-50 rounded-lg transition-colors"
              title="Agregar Variante"
            >
              ${icons.plus}
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join("");

  // Attach Table Action Handlers
  tbody.querySelectorAll(".btn-edit-prod").forEach(btn => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.editId;
      const product = productsList.find(p => p.id === id);
      if (product) openProductFormModal(product);
    });
  });

  tbody.querySelectorAll(".btn-toggle-status").forEach(btn => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.toggleId;
      const currentActive = btn.dataset.isActive === "true";
      const actionTxt = currentActive ? "desactivar" : "activar";

      showConfirmDialog(
        `¿Deseas ${actionTxt} este producto?`,
        currentActive ? "El producto y sus variantes quedarán inactivos en el catálogo." : "El producto volverá a estar disponible en el catálogo.",
        async () => {
          try {
            await api.patch(`/products/${id}/toggle-status`);
            showToast(`Producto ${actionTxt === "activar" ? "activado" : "desactivado"} con éxito`, "success");
            fetchProducts();
          } catch (err) {
            showToast(err.message || "Error al cambiar estatus", "error");
          }
        }
      );
    });
  });

  tbody.querySelectorAll(".btn-view-mappings").forEach(btn => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.mappingsId;
      const product = productsList.find(p => p.id === id);
      if (product) openMappingsModal(product);
    });
  });

  tbody.querySelectorAll(".btn-publish-meli").forEach(btn => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.publishId;
      const product = productsList.find(p => p.id === id);
      if (product) openPublishModal(product);
    });
  });

  tbody.querySelectorAll(".btn-add-variant").forEach(btn => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.addVariantId;
      const product = productsList.find(p => p.id === id);
      if (product) openAddVariantModal(product);
    });
  });
}

// -----------------------------------------------------------------------------
// MODAL: ALTA Y EDICIÓN COMPLETA DE PRODUCTO
// -----------------------------------------------------------------------------
function openProductFormModal(product = null) {
  const isEdit = !!product;
  // Variante primaria (para editar su código de barras desde este formulario).
  const primaryVariant = product?.variants?.find(v => v.is_active) || product?.variants?.[0] || null;
  const currentCompany = state.currentCompany;
  if (!currentCompany) {
    showToast("Selecciona una empresa primero", "error");
    return;
  }

  const content = `
    <form id="product-master-form" class="space-y-4 max-h-[80vh] overflow-y-auto pr-1">
      <!-- Datos Generales -->
      <div class="border-b border-slate-100 pb-3">
        <h3 class="text-xs font-bold text-slate-700 uppercase tracking-wider mb-2">1. Información General</h3>
        <div class="space-y-3">
          <div>
            <label class="block text-xs font-semibold text-slate-700 mb-1">Nombre o Título del Producto *</label>
            <input type="text" id="prod-name" class="input-field text-sm font-semibold" value="${product?.name || ''}" required placeholder="e.g. Audífonos Bluetooth Noise Cancelling Pro" />
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-semibold text-slate-700 mb-1">Marca</label>
              <input type="text" id="prod-brand" class="input-field text-xs" value="${product?.brand || ''}" placeholder="e.g. Sony, Apple, Genérico" />
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-700 mb-1">Modelo</label>
              <input type="text" id="prod-model" class="input-field text-xs" value="${product?.model || ''}" placeholder="e.g. WH-1000XM5" />
            </div>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-semibold text-slate-700 mb-1">Categoría</label>
              <input type="text" id="prod-category" class="input-field text-xs" value="${product?.category || ''}" placeholder="e.g. Audio > Auriculares" />
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-700 mb-1">Clave de Unidad SAT</label>
              <input type="text" id="prod-uom" class="input-field text-xs font-mono" value="${product?.unit_of_measure || 'H87'}" placeholder="H87 (Pieza)" />
            </div>
          </div>
        </div>
      </div>

      <!-- Precios y Costos -->
      <div class="border-b border-slate-100 pb-3">
        <h3 class="text-xs font-bold text-slate-700 uppercase tracking-wider mb-2">2. Precios y Costos (MXN)</h3>
        <div class="grid grid-cols-3 gap-3">
          <div>
            <label class="block text-xs font-semibold text-slate-700 mb-1">Costo Base (COGS) *</label>
            <input type="number" id="prod-cost" step="0.50" min="0" class="input-field text-xs font-mono font-bold" value="${product?.cost_price || 0.0}" required />
          </div>
          <div>
            <label class="block text-xs font-semibold text-slate-700 mb-1">Precio Venta (PVP) *</label>
            <input type="number" id="prod-sale-price" step="0.50" min="0" class="input-field text-xs font-mono font-bold text-blue-700" value="${product?.sale_price || 0.0}" required />
          </div>
          <div>
            <label class="block text-xs font-semibold text-slate-700 mb-1">Precio Mayoreo</label>
            <input type="number" id="prod-wholesale-price" step="0.50" min="0" class="input-field text-xs font-mono" value="${product?.wholesale_price || ''}" placeholder="Opcional" />
          </div>
        </div>
      </div>

      <!-- Logística y Dimensiones -->
      <div class="border-b border-slate-100 pb-3">
        <h3 class="text-xs font-bold text-slate-700 uppercase tracking-wider mb-2">3. Peso, Dimensiones y Ubicación</h3>
        <div class="grid grid-cols-4 gap-2">
          <div>
            <label class="block text-[11px] font-semibold text-slate-700 mb-1">Peso (kg)</label>
            <input type="number" id="prod-weight" step="0.05" min="0" class="input-field text-xs font-mono" value="${product?.weight_kg || 0.0}" />
          </div>
          <div>
            <label class="block text-[11px] font-semibold text-slate-700 mb-1">Largo (cm)</label>
            <input type="number" id="prod-length" step="0.5" min="0" class="input-field text-xs font-mono" value="${product?.length_cm || 0.0}" />
          </div>
          <div>
            <label class="block text-[11px] font-semibold text-slate-700 mb-1">Ancho (cm)</label>
            <input type="number" id="prod-width" step="0.5" min="0" class="input-field text-xs font-mono" value="${product?.width_cm || 0.0}" />
          </div>
          <div>
            <label class="block text-[11px] font-semibold text-slate-700 mb-1">Alto (cm)</label>
            <input type="number" id="prod-height" step="0.5" min="0" class="input-field text-xs font-mono" value="${product?.height_cm || 0.0}" />
          </div>
        </div>
        <div class="mt-2">
          <label class="block text-xs font-semibold text-slate-700 mb-1">Ubicación en Almacén</label>
          <input type="text" id="prod-location" class="input-field text-xs font-mono" value="${product?.warehouse_location || ''}" placeholder="e.g. Pasillo 3 - Rack B - Nivel 2" />
        </div>
      </div>

      <!-- Descripción y Fotografías -->
      <div class="space-y-3">
        <div>
          <label class="block text-xs font-semibold text-slate-700 mb-1">Descripción del Producto</label>
          <textarea id="prod-description" rows="2" class="input-field text-xs" placeholder="Especificaciones técnicas y descripción comercial...">${product?.description || ''}</textarea>
        </div>
        <div>
          <label class="block text-xs font-semibold text-slate-700 mb-1">URLs de Fotografías (separadas por coma o salto de línea)</label>
          <textarea id="prod-images" rows="2" class="input-field text-xs font-mono" placeholder="https://dominio.com/foto1.jpg, https://dominio.com/foto2.jpg">${product?.images ? product.images.join(", ") : ''}</textarea>
        </div>
      </div>

      ${!isEdit ? `
        <!-- Variante Primaria para Nuevo Producto -->
        <div class="p-3 bg-blue-50 border border-blue-200 rounded-xl space-y-2">
          <div class="text-xs font-bold text-blue-900 uppercase">Variante Primaria (SKU Obligatorio)</div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-[11px] font-semibold text-slate-700 mb-1">SKU Único *</label>
              <input type="text" id="variant-sku-input" class="input-field text-xs font-mono font-bold uppercase" required placeholder="e.g. PROD-001-BLK" />
            </div>
            <div>
              <label class="block text-[11px] font-semibold text-slate-700 mb-1">Código de Barras (EAN-13)</label>
              <input type="text" id="variant-barcode-input" class="input-field text-xs font-mono" placeholder="e.g. 7501234567890" />
            </div>
          </div>
        </div>
      ` : `
        <!-- Código de Barras de la Variante Primaria (solo edición) -->
        <div class="p-3 bg-blue-50 border border-blue-200 rounded-xl space-y-2">
          <div class="text-xs font-bold text-blue-900 uppercase">Variante Primaria</div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-[11px] font-semibold text-slate-700 mb-1">SKU (no editable aquí)</label>
              <input type="text" class="input-field text-xs font-mono font-bold uppercase bg-slate-100" value="${(primaryVariant?.sku || '').replace(/"/g, "&quot;")}" disabled />
            </div>
            <div>
              <label class="block text-[11px] font-semibold text-slate-700 mb-1">Código de Barras (EAN-13 / UPC)</label>
              <input type="text" id="variant-barcode-input" class="input-field text-xs font-mono" value="${(primaryVariant?.barcode_ean || '').replace(/"/g, "&quot;")}" placeholder="e.g. 7501234567890" />
            </div>
          </div>
          <div class="text-[11px] text-slate-500">Si el EAN que trajo la importación está mal, corrígelo aquí: se guarda en la variante primaria del producto.</div>
        </div>
      `}

      <div class="flex justify-end gap-2 pt-3 border-t border-slate-100">
        <button type="button" id="btn-cancel-prod-form" class="btn-secondary">Cancelar</button>
        <button type="submit" id="btn-submit-prod-form" class="btn-primary flex items-center gap-1.5">
          ${icons.check} ${isEdit ? 'Actualizar Producto' : 'Guardar Producto'}
        </button>
      </div>
    </form>
  `;

  openModal(isEdit ? `Editar Producto · ${product.name}` : "Nuevo Producto Maestro", content);
  document.getElementById("btn-cancel-prod-form")?.addEventListener("click", closeModal);

  const form = document.getElementById("product-master-form");
  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = document.getElementById("btn-submit-prod-form");
    btn.disabled = true;
    btn.innerHTML = "Guardando...";

    const name = document.getElementById("prod-name").value.trim();
    const brand = document.getElementById("prod-brand").value.trim() || null;
    const model = document.getElementById("prod-model").value.trim() || null;
    const category = document.getElementById("prod-category").value.trim() || null;
    const unitOfMeasure = document.getElementById("prod-uom").value.trim() || "H87";
    const costPrice = parseFloat(document.getElementById("prod-cost").value) || 0.0;
    const salePrice = parseFloat(document.getElementById("prod-sale-price").value) || 0.0;
    const wholesaleVal = document.getElementById("prod-wholesale-price").value;
    const wholesalePrice = wholesaleVal ? parseFloat(wholesaleVal) : null;
    const weightKg = parseFloat(document.getElementById("prod-weight").value) || 0.0;
    const lengthCm = parseFloat(document.getElementById("prod-length").value) || 0.0;
    const widthCm = parseFloat(document.getElementById("prod-width").value) || 0.0;
    const heightCm = parseFloat(document.getElementById("prod-height").value) || 0.0;
    const location = document.getElementById("prod-location").value.trim() || null;
    const description = document.getElementById("prod-description").value.trim() || null;
    const rawImages = document.getElementById("prod-images").value.trim();
    const images = rawImages ? rawImages.split(/[\n,]+/).map(s => s.trim()).filter(Boolean) : [];

    try {
      if (isEdit) {
        const barcodeInput = document.getElementById("variant-barcode-input");
        const updatePayload = {
          name, brand, model, category, unit_of_measure: unitOfMeasure,
          cost_price: costPrice, sale_price: salePrice, wholesale_price: wholesalePrice,
          weight_kg: weightKg, length_cm: lengthCm, width_cm: widthCm, height_cm: heightCm,
          warehouse_location: location, description, images,
          // Código de barras de la variante primaria (se guarda con el producto).
          ...(barcodeInput ? { barcode_ean: barcodeInput.value.trim() || null } : {}),
        };
        await api.put(`/products/${product.id}`, updatePayload);
        showToast("Producto actualizado exitosamente", "success");
      } else {
        const skuVal = document.getElementById("variant-sku-input").value.trim().toUpperCase();
        const barcodeVal = document.getElementById("variant-barcode-input").value.trim() || null;

        const createPayload = {
          // La empresa viene como CompanyBriefResponse: el campo es
          // company_id, no id (igual que el fallback de api.js). Sin esto
          // el company_id llegaba undefined y la API devolvía 422.
          company_id: currentCompany.id || currentCompany.company_id,
          name, brand, model, category, unit_of_measure: unitOfMeasure,
          cost_price: costPrice, sale_price: salePrice, wholesale_price: wholesalePrice,
          weight_kg: weightKg, length_cm: lengthCm, width_cm: widthCm, height_cm: heightCm,
          warehouse_location: location, description, images,
          variants: [
            {
              variant_name: "Principal",
              sku: skuVal,
              barcode_ean: barcodeVal,
              cogs_cost: costPrice,
              sale_price: salePrice
            }
          ]
        };
        await api.post("/products", createPayload);
        showToast("Producto y variante primaria creados exitosamente", "success");
      }
      closeModal();
      await fetchProducts();
    } catch (err) {
      showToast(err.message || "Error al procesar producto", "error");
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `${icons.check} ${isEdit ? 'Actualizar Producto' : 'Guardar Producto'}`;
      }
    }
  });
}

// -----------------------------------------------------------------------------
// MODAL: AGREGAR VARIANTE CON VALIDACIÓN DE SKU ÚNICO
// -----------------------------------------------------------------------------
function openAddVariantModal(product) {
  const content = `
    <form id="add-variant-form" class="space-y-4">
      <div class="text-xs text-slate-500">
        Producto: <strong class="text-slate-800">${product.name}</strong>
      </div>

      <div>
        <label class="block text-xs font-semibold text-slate-700 mb-1">Nombre de la Variante *</label>
        <input type="text" id="new-var-name" class="input-field text-sm" placeholder="e.g. Blanco / Talla G / 256GB" required />
      </div>

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="block text-xs font-semibold text-slate-700 mb-1">SKU Único en la Empresa *</label>
          <input type="text" id="new-var-sku" class="input-field text-xs font-mono uppercase font-bold" placeholder="e.g. ${product.name.slice(0, 3).toUpperCase()}-VAR-02" required />
        </div>
        <div>
          <label class="block text-xs font-semibold text-slate-700 mb-1">Código de Barras EAN</label>
          <input type="text" id="new-var-barcode" class="input-field text-xs font-mono" placeholder="7501234567890" />
        </div>
      </div>

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="block text-xs font-semibold text-slate-700 mb-1">Costo Unitario (COGS)</label>
          <input type="number" id="new-var-cost" step="0.50" min="0" class="input-field text-xs font-mono" value="${product.cost_price || 0.0}" />
        </div>
        <div>
          <label class="block text-xs font-semibold text-slate-700 mb-1">Precio de Venta</label>
          <input type="number" id="new-var-price" step="0.50" min="0" class="input-field text-xs font-mono" value="${product.sale_price || 0.0}" />
        </div>
      </div>

      <div class="flex justify-end gap-2 pt-2 border-t border-slate-100">
        <button type="button" id="btn-cancel-var" class="btn-secondary">Cancelar</button>
        <button type="submit" id="btn-submit-var" class="btn-primary flex items-center gap-1.5">
          ${icons.plus} Agregar Variante
        </button>
      </div>
    </form>
  `;

  openModal(`Nueva Variante · ${product.name}`, content);
  document.getElementById("btn-cancel-var")?.addEventListener("click", closeModal);

  const form = document.getElementById("add-variant-form");
  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = document.getElementById("btn-submit-var");
    btn.disabled = true;
    btn.innerHTML = "Guardando...";

    const variantName = document.getElementById("new-var-name").value.trim();
    const sku = document.getElementById("new-var-sku").value.trim().toUpperCase();
    const barcode = document.getElementById("new-var-barcode").value.trim() || null;
    const cost = parseFloat(document.getElementById("new-var-cost").value) || 0.0;
    const price = parseFloat(document.getElementById("new-var-price").value) || null;

    try {
      await api.post(`/products/${product.id}/variants`, {
        variant_name: variantName,
        sku,
        barcode_ean: barcode,
        cogs_cost: cost,
        sale_price: price,
      });
      closeModal();
      showToast("Variante agregada exitosamente", "success");
      await fetchProducts();
    } catch (err) {
      showToast(err.message || "Error al agregar variante", "error");
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `${icons.plus} Agregar Variante`;
      }
    }
  });
}

// -----------------------------------------------------------------------------
// MODAL: ASOCIAR Y VER PUBLICACIONES EXTERNAS ME-LI (MULTI-CUENTA)
// -----------------------------------------------------------------------------
async function openMappingsModal(product) {
  let mappings = [];
  try {
    mappings = await api.get(`/products/${product.id}/mappings`);
  } catch (err) {
    showToast("Error al consultar publicaciones asociadas", "error");
  }

  const variantsOptions = product.variants && product.variants.length > 0
    ? product.variants.map(v => `<option value="${v.id}">${v.variant_name} (SKU: ${v.sku})</option>`).join("")
    : `<option value="">Sin variantes</option>`;

  const content = `
    <div class="space-y-4 max-h-[80vh] overflow-y-auto">
      <div class="bg-yellow-50 border border-yellow-200 text-yellow-900 p-3 rounded-xl text-xs leading-relaxed">
        <strong>Publicaciones de Mercado Libre Vinculadas</strong><br />
        Un producto interno puede estar relacionado con múltiples publicaciones y cuentas (por ejemplo, publicación clásica y premium simultáneamente).
      </div>

      <!-- Formulario para Vincular Nueva Publicación -->
      <form id="link-meli-item-form" class="p-3 bg-slate-50 border border-slate-200 rounded-xl space-y-3">
        <div class="text-xs font-bold text-slate-800 uppercase tracking-wider">Asociar Nueva Publicación Externa</div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-[11px] font-semibold text-slate-700 mb-1">Variante Interna *</label>
            <select id="map-variant-select" class="input-field text-xs" required>
              ${variantsOptions}
            </select>
          </div>
          <div>
            <label class="block text-[11px] font-semibold text-slate-700 mb-1">ID Publicación MeLi (MLM) *</label>
            <input type="text" id="map-meli-id" class="input-field text-xs font-mono uppercase font-bold" placeholder="MLM123456789" required />
          </div>
        </div>

        <div class="grid grid-cols-3 gap-2">
          <div>
            <label class="block text-[11px] font-semibold text-slate-700 mb-1">Precio en MeLi *</label>
            <input type="number" id="map-meli-price" step="0.50" min="1" class="input-field text-xs font-mono font-bold" value="${product.sale_price || 0.0}" required />
          </div>
          <div>
            <label class="block text-[11px] font-semibold text-slate-700 mb-1">Tipo Publicación</label>
            <select id="map-listing-type" class="input-field text-xs">
              <option value="gold_special">Clásica (13% MeLi)</option>
              <option value="gold_pro">Premium (Cuotas)</option>
            </select>
          </div>
          <div>
            <label class="block text-[11px] font-semibold text-slate-700 mb-1">Logística</label>
            <select id="map-logistic-type" class="input-field text-xs">
              <option value="fulfillment">Mercado Envíos FULL</option>
              <option value="drop_off">Colecta / Agencia</option>
              <option value="flex">Mercado Envíos Flex</option>
            </select>
          </div>
        </div>

        <div class="flex justify-end pt-1">
          <button type="submit" id="btn-save-mapping" class="btn-primary text-xs py-1.5 px-3 flex items-center gap-1.5">
            ${icons.plus} Vincular Publicación
          </button>
        </div>
      </form>

      <!-- Tabla de Publicaciones Mapeadas -->
      <div class="border border-slate-200 rounded-xl overflow-hidden">
        <table class="w-full text-left text-xs border-collapse">
          <thead>
            <tr class="bg-slate-100 text-slate-600 font-bold uppercase text-[10px]">
              <th class="p-2.5">ID Publicación</th>
              <th class="p-2.5">SKU Vendedor</th>
              <th class="p-2.5">Precio MeLi</th>
              <th class="p-2.5">Logística</th>
              <th class="p-2.5 text-right">Acción</th>
            </tr>
          </thead>
          <tbody id="mappings-tbody" class="divide-y divide-slate-100">
            ${mappings.length === 0 ? `
              <tr><td colspan="5" class="p-4 text-center text-slate-400">No hay publicaciones de Mercado Libre vinculadas a este producto aún.</td></tr>
            ` : mappings.map(m => `
              <tr class="hover:bg-slate-50">
                <td class="p-2.5 font-mono font-bold text-blue-600">${m.meli_item_id}</td>
                <td class="p-2.5 font-mono text-slate-700">${m.seller_sku}</td>
                <td class="p-2.5 font-mono font-semibold text-slate-900">$${(parseFloat(m.price) || 0).toFixed(2)}</td>
                <td class="p-2.5"><span class="badge-meli text-[10px]">${m.logistic_type}</span></td>
                <td class="p-2.5 text-right">
                  <button data-unmap-id="${m.id}" class="btn-unmap text-xs font-semibold text-rose-600 hover:text-rose-800">
                    Desvincular
                  </button>
                </td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;

  openModal(`Publicaciones MeLi · ${product.name}`, content);

  // Vincular form handler
  const form = document.getElementById("link-meli-item-form");
  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = document.getElementById("btn-save-mapping");
    btn.disabled = true;

    const variantId = document.getElementById("map-variant-select").value;
    const meliItemId = document.getElementById("map-meli-id").value.trim().replace(/[\s\-_]/g, "").toUpperCase();
    const price = parseFloat(document.getElementById("map-meli-price").value);
    const listingType = document.getElementById("map-listing-type").value;
    const logisticType = document.getElementById("map-logistic-type").value;

    // Obtener primera cuenta MeLi disponible
    try {
      const accRes = await api.get("/meli-accounts?limit=10");
      const accounts = accRes.items || [];
      if (accounts.length === 0) {
        throw new Error("No hay cuentas de Mercado Libre vinculadas. Ve a Integraciones primero.");
      }

      await api.post("/products/mappings", {
        meli_account_id: accounts[0].id,
        variant_id: variantId,
        meli_item_id: meliItemId,
        seller_sku: product.variants?.[0]?.sku || "SKU-AUTO",
        price,
        listing_type_id: listingType,
        logistic_type: logisticType,
      });

      showToast("Publicación de Mercado Libre vinculada con éxito", "success");
      closeModal();
      openMappingsModal(product);
    } catch (err) {
      showToast(err.message || "Error al vincular publicación", "error");
    } finally {
      if (btn) btn.disabled = false;
    }
  });

  // Desvincular handler
  document.querySelectorAll(".btn-unmap").forEach(btn => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.unmapId;
      try {
        await api.delete(`/products/mappings/${id}`);
        showToast("Publicación desvinculada", "success");
        closeModal();
        openMappingsModal(product);
      } catch (err) {
        showToast(err.message || "Error al desvincular", "error");
      }
    });
  });
}

// -----------------------------------------------------------------------------
// MODAL: IMPORTAR PRODUCTOS DESDE MERCADO LIBRE (CON PREVENCIÓN DE DUPLICADOS)
// -----------------------------------------------------------------------------
async function openMeliImportModal() {
  let accounts = [];
  try {
    const accRes = await api.get("/meli-accounts?limit=20");
    accounts = accRes.items || [];
  } catch (err) {
    showToast("Error al obtener cuentas de Mercado Libre", "error");
    return;
  }

  if (accounts.length === 0) {
    showToast("Debes vincular primero una cuenta de Mercado Libre en la sección de Integraciones.", "warning");
    return;
  }

  const accOptions = accounts.map(a => `<option value="${a.id}">${a.nickname} (Seller ID: ${a.meli_user_id || a.seller_id})</option>`).join("");

  const content = `
    <form id="meli-import-form" class="space-y-4">
      <div class="bg-yellow-50 border border-yellow-200 text-yellow-900 p-3 rounded-xl text-xs leading-relaxed">
        <strong>Importador Oficial de Mercado Libre México</strong><br />
        El ERP consulta cada publicación en Mercado Libre y trae sus datos reales: título, marca, modelo, EAN, precio, fotografías y dimensiones.
        <div class="mt-1 font-semibold text-emerald-800">
          ✔ Protección Anti-Duplicados activa: si la publicación ya está vinculada, se actualiza sin duplicar y sin sobrescribir tus precios ni costos. Cada publicación crea su propio producto.
        </div>
      </div>

      <div>
        <label class="block text-xs font-semibold text-slate-700 mb-1">Seleccionar Cuenta de Mercado Libre *</label>
        <select id="import-account-select" class="input-field text-sm font-semibold" required>
          ${accOptions}
        </select>
      </div>

      <div>
        <label class="block text-xs font-semibold text-slate-700 mb-1">IDs de Publicación Específicos (Opcional, separados por coma)</label>
        <input type="text" id="import-specific-items" class="input-field text-xs font-mono" placeholder="e.g. MLM123456789, MLM987654321 (Dejar vacío para sincronizar lote)" />
      </div>

      <div class="flex justify-end gap-2 pt-2 border-t border-slate-100">
        <button type="button" id="btn-cancel-meli-imp" class="btn-secondary">Cancelar</button>
        <button type="submit" id="btn-submit-meli-imp" class="btn-primary flex items-center gap-1.5 bg-yellow-400 hover:bg-yellow-500 text-slate-900 border-none font-bold">
          ${icons.refresh} Iniciar Importación MeLi
        </button>
      </div>
    </form>
  `;

  openModal("Importar Productos desde Mercado Libre", content);
  document.getElementById("btn-cancel-meli-imp")?.addEventListener("click", closeModal);

  const form = document.getElementById("meli-import-form");
  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = document.getElementById("btn-submit-meli-imp");
    btn.disabled = true;
    btn.innerHTML = "Sincronizando con MeLi...";

    const accountId = document.getElementById("import-account-select").value;
    const itemsInput = document.getElementById("import-specific-items").value.trim();

    // Solo se mandan los IDs: el backend consulta los datos REALES de cada
    // publicación en MeLi (GET /items/{id}). Antes el navegador inventaba el
    // payload (precio fijo 699.00, EAN aleatorio y SKU "SKU-"+id[3:8]), y eso
    // creó productos con precio $699 y fusionó publicaciones distintas.
    const itemIds = itemsInput
      ? itemsInput.split(/[\s,]+/).filter(Boolean).map(id => id.replace(/[\s\-_]/g, "").toUpperCase())
      : [];
    if (itemIds.length === 0) {
      showToast("Ingresa al menos un ID de publicación MeLi (MLM...).", "warning");
      btn.disabled = false;
      btn.innerHTML = `${icons.refresh} Iniciar Importación MeLi`;
      return;
    }
    const itemsPayload = itemIds.map(id => ({ id }));

    try {
      const res = await api.post("/products/import-meli", {
        meli_account_id: accountId,
        items: itemsPayload,
      });

      closeModal();
      showToast(`Importación completada: ${res.created} creados, ${res.updated} actualizados, ${res.linked_mappings} vinculados.`, "success");
      await fetchProducts();
    } catch (err) {
      showToast(err.message || "Error al importar de MeLi", "error");
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `${icons.refresh} Iniciar Importación MeLi`;
      }
    }
  });
}

// -----------------------------------------------------------------------------
// MODAL: PUBLICAR EN MERCADO LIBRE (POST /items desde el ERP)
// -----------------------------------------------------------------------------
async function openPublishModal(product) {
  let accounts = [];
  try {
    const accRes = await api.get("/meli-accounts?limit=20");
    accounts = accRes.items || [];
  } catch (err) {
    showToast("Error al obtener cuentas de Mercado Libre", "error");
    return;
  }

  if (accounts.length === 0) {
    showToast("Debes vincular primero una cuenta de Mercado Libre en la sección de Integraciones.", "warning");
    return;
  }

  const accOptions = accounts.map(a => `<option value="${a.id}">${a.nickname} (Seller ID: ${a.meli_user_id || a.seller_id})</option>`).join("");

  const variantsOptions = product.variants && product.variants.length > 0
    ? product.variants.map(v => `<option value="${v.id}">${v.variant_name} (SKU: ${v.sku}${v.barcode_ean ? ` · GTIN ${v.barcode_ean}` : ""})</option>`).join("")
    : `<option value="">Sin variantes</option>`;

  const content = `
    <form id="meli-publish-form" class="space-y-4">
      <div class="bg-emerald-50 border border-emerald-200 text-emerald-900 p-3 rounded-xl text-xs leading-relaxed">
        <strong>Publicar en Mercado Libre desde el ERP</strong><br />
        Crea la publicación con la API oficial (POST /items), guarda la descripción y deja la publicación
        vinculada a esta variante para gestionar pedidos, stock y precios desde aquí.
        <div class="mt-1 font-semibold">
          ✔ Gratuita por defecto (sin comisión). La marca, el modelo, el GTIN y el color se toman solos del producto y su variante.
        </div>
      </div>

      <div id="meli-publish-error" class="hidden bg-red-50 border border-red-200 text-red-900 p-3 rounded-xl text-xs leading-relaxed font-semibold"></div>

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="block text-xs font-semibold text-slate-700 mb-1">Cuenta de Mercado Libre *</label>
          <select id="publish-account-select" class="input-field text-sm font-semibold" required>
            ${accOptions}
          </select>
        </div>
        <div>
          <label class="block text-xs font-semibold text-slate-700 mb-1">Variante *</label>
          <select id="publish-variant-select" class="input-field text-sm" required>
            ${variantsOptions}
          </select>
        </div>
      </div>

      <div>
        <label class="block text-xs font-semibold text-slate-700 mb-1">Nombre del producto (máx. 60 caracteres) *</label>
        <input type="text" id="publish-title" class="input-field text-sm" maxlength="60" value="${(product.name || "").replace(/"/g, "&quot;")}" required />
        <div class="text-[11px] text-slate-400 mt-1">Mercado Libre arma el título de la publicación a partir de este nombre + marca y modelo. No incluyas color ni condición.</div>
      </div>

      <div class="grid grid-cols-3 gap-3">
        <div>
          <label class="block text-xs font-semibold text-slate-700 mb-1">ID de Categoría MeLi *</label>
          <input type="text" id="publish-category-id" class="input-field text-sm font-mono" placeholder="MLM..." value="${(product.category_code || "").replace(/"/g, "&quot;")}" required />
          <div class="text-[11px] text-slate-400 mt-1">Se obtiene del predictor de categorías de MeLi con el título del producto.</div>
        </div>
        <div>
          <label class="block text-xs font-semibold text-slate-700 mb-1">Precio (MXN) *</label>
          <input type="number" id="publish-price" step="0.50" min="1" class="input-field text-sm font-mono font-bold" value="${product.sale_price || 0.0}" required />
        </div>
        <div>
          <label class="block text-xs font-semibold text-slate-700 mb-1">Stock inicial *</label>
          <input type="number" id="publish-quantity" step="1" min="1" class="input-field text-sm font-mono" value="1" required />
        </div>
      </div>

      <!-- Atributos requeridos por la categoría (se rellenan solos según el ID
           de categoría; p. ej. "Tipo de conector" en MLM429747). -->
      <div id="publish-required-attrs" class="space-y-3"></div>

      <div>
        <label class="block text-xs font-semibold text-slate-700 mb-1">Tipo de publicación</label>
        <select id="publish-listing-type" class="input-field text-sm">
          <option value="free" selected>Gratuita (sin comisión)</option>
          <option value="gold_special">Clásica</option>
          <option value="gold_pro">Premium</option>
        </select>
      </div>

      <div>
        <label class="block text-xs font-semibold text-slate-700 mb-1">Descripción</label>
        <textarea id="publish-description" rows="3" class="input-field text-sm">${product.description || ""}</textarea>
      </div>

      <div class="flex justify-end gap-2 pt-2 border-t border-slate-100">
        <button type="button" id="btn-cancel-meli-pub" class="btn-secondary">Cancelar</button>
        <button type="submit" id="btn-submit-meli-pub" class="btn-primary flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-700 text-white border-none font-bold">
          Publicar en MeLi
        </button>
      </div>
    </form>
  `;

  openModal(`Publicar en Mercado Libre · ${product.name}`, content);
  document.getElementById("btn-cancel-meli-pub")?.addEventListener("click", closeModal);

  // Atributos que Mercado Libre exige según la categoría (hardcodeado).
  // MeLi los marca required + catalog_required por categoría y sin ellos el
  // POST /items responde 400 (caso real 2026-11-23: CONNECTOR_TYPE en
  // MLM429747, "The attributes [CONNECTOR_TYPE] are required..."). Para
  // agregar otro atributo requerido de otra categoría: añadir una entrada
  // aquí con sus valores de catálogo (value_id = ID oficial de MeLi).
  const MELI_REQUIRED_ATTRIBUTES = {
    MLM429747: [
      {
        id: "CONNECTOR_TYPE",
        label: "Tipo de conector",
        required: true,
        values: [
          { value_id: "82230", value_name: "USB" },
          { value_id: "10787099", value_name: "Micro-USB" },
          { value_id: "2113108", value_name: "USB-C" },
          { value_id: "22106244", value_name: "USB/USB-C" },
          { value_id: "18439714", value_name: "Usb/micro-usb" },
        ],
      },
    ],
    // Fix 12 (2026-11-25): MLM5107 (Cables) exige INPUT_CONNECTOR y
    // OUTPUT_CONNECTOR ("The attributes [INPUT_CONNECTOR, OUTPUT_CONNECTOR]
    // are required..."). value_ids oficiales de MeLi, verificados en vivo en
    // GET /categories/MLM5107/attributes. Ambos son de valor único (sin
    // tag multivalued): un cable 3 en 1 como el WI.164 (Lightning + Tipo-C
    // + Micro-USB) no tiene valor Lightning en MeLi — se elige USB-C como
    // salida (una de sus tres puntas reales) y el "3 en 1" queda en el
    // título/descripción.
    MLM5107: [
      {
        id: "INPUT_CONNECTOR",
        label: "Conector de entrada",
        required: true,
        values: [
          { value_id: "4027341", value_name: "USB-A" },
          { value_id: "17291935", value_name: "USB-C" },
          { value_id: "13814108", value_name: "Micro USB" },
          { value_id: "17606340", value_name: "USB-B" },
          { value_id: "13843109", value_name: "Mini Usb" },
        ],
      },
      {
        id: "OUTPUT_CONNECTOR",
        label: "Conector de salida",
        required: true,
        values: [
          { value_id: "6778102", value_name: "USB-C" },
          { value_id: "9824272", value_name: "USB-A" },
          { value_id: "10803095", value_name: "Micro-USB" },
          { value_id: "4027343", value_name: "USB-B" },
          { value_id: "16485475", value_name: "Mini USB" },
        ],
      },
    ],
  };

  // Muestra los selects de atributos requeridos solo cuando la categoría
  // escrita coincide con una entrada de MELI_REQUIRED_ATTRIBUTES.
  function renderRequiredAttrs() {
    const container = document.getElementById("publish-required-attrs");
    if (!container) return;
    const categoryId = (document.getElementById("publish-category-id")?.value || "").trim().toUpperCase();
    const defs = MELI_REQUIRED_ATTRIBUTES[categoryId] || [];
    if (defs.length === 0) {
      container.innerHTML = "";
      return;
    }
    container.innerHTML = defs.map(def => `
      <div>
        <label class="block text-xs font-semibold text-slate-700 mb-1">${def.label} *</label>
        <select id="publish-attr-${def.id}" class="input-field text-sm" data-attr-id="${def.id}" required>
          <option value="">Selecciona ${def.label.toLowerCase()}...</option>
          ${def.values.map(v => `<option value="${v.value_id}" data-value-name="${v.value_name}">${v.value_name}</option>`).join("")}
        </select>
        <div class="text-[11px] text-slate-400 mt-1">Mercado Libre lo exige para esta categoría; sin él rechaza la publicación.</div>
      </div>
    `).join("");
  }

  document.getElementById("publish-category-id")?.addEventListener("input", renderRequiredAttrs);
  renderRequiredAttrs();

  const form = document.getElementById("meli-publish-form");
  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = document.getElementById("btn-submit-meli-pub");
    document.getElementById("meli-publish-error")?.classList.add("hidden");
    btn.disabled = true;
    btn.innerHTML = "Publicando en MeLi...";

    const errBoxEarly = document.getElementById("meli-publish-error");

    // Atributos requeridos por la categoría (e.g. CONNECTOR_TYPE en
    // MLM429747): si falta el obligatorio, se bloquea la publicación con un
    // mensaje claro en lugar de mandar el POST y que MeLi lo rechace.
    const requiredAttrs = [];
    const categoryId = (document.getElementById("publish-category-id").value || "").trim().toUpperCase();
    for (const def of MELI_REQUIRED_ATTRIBUTES[categoryId] || []) {
      const select = document.getElementById(`publish-attr-${def.id}`);
      const valueId = select?.value || "";
      if (def.required && !valueId) {
        const msg = `Mercado Libre exige el campo "${def.label}" para la categoría ${categoryId}: selecciónalo antes de publicar.`;
        if (errBoxEarly) {
          errBoxEarly.textContent = msg;
          errBoxEarly.classList.remove("hidden");
        }
        showToast(msg, "error");
        btn.disabled = false;
        btn.innerHTML = "Publicar en MeLi";
        return;
      }
      if (valueId) {
        const valueName = select.options[select.selectedIndex]?.dataset.valueName || undefined;
        requiredAttrs.push({ id: def.id, value_id: valueId, ...(valueName ? { value_name: valueName } : {}) });
      }
    }

    const body = {
      meli_account_id: document.getElementById("publish-account-select").value,
      variant_id: document.getElementById("publish-variant-select").value || undefined,
      category_id: document.getElementById("publish-category-id").value.trim(),
      title: document.getElementById("publish-title").value.trim(),
      price: parseFloat(document.getElementById("publish-price").value),
      available_quantity: parseInt(document.getElementById("publish-quantity").value, 10),
      listing_type_id: document.getElementById("publish-listing-type").value,
      description: document.getElementById("publish-description").value.trim() || undefined,
      // Atributos extra del catálogo (p. ej. CONNECTOR_TYPE): el backend los
      // pasa tal cual en el "attributes" del POST /items.
      ...(requiredAttrs.length ? { attributes: requiredAttrs } : {}),
    };

    try {
      const res = await api.post(`/products/${product.id}/publish-meli`, body);
      closeModal();
      showToast(`Publicado en MeLi: ${res.meli_item_id} · ${res.permalink || ""}`, "success");
      await fetchProducts();
    } catch (err) {
      // El mensaje queda fijo dentro del modal (además del toast, que desaparece
      // en segundos) para poder leer el error exacto que devolvió Mercado Libre.
      const msg = err.message || "Error al publicar en MeLi";
      const errBox = document.getElementById("meli-publish-error");
      if (errBox) {
        errBox.textContent = msg;
        errBox.classList.remove("hidden");
      }
      showToast(msg, "error");
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = "Publicar en MeLi";
      }
    }
  });
}

// -----------------------------------------------------------------------------
// MODAL: IMPORTAR CSV
// -----------------------------------------------------------------------------
function openCsvImportModal() {
  const content = `
    <form id="csv-import-form" class="space-y-4">
      <div class="bg-blue-50 border border-blue-200 text-blue-900 p-3 rounded-xl text-xs leading-relaxed">
        <strong>Plantilla Estándar de Importación CSV</strong><br />
        Encabezados admitidos: <code>sku, nombre, marca, modelo, categoria, codigobarras, costo, precio, peso_kg, largo, ancho, alto, ubicacion</code>.
        <div class="mt-1 font-semibold text-blue-800">
          ✔ Si un SKU ya existe en la empresa, sus datos serán actualizados automáticamente sin generar duplicados.
        </div>
      </div>

      <div class="border-2 border-dashed border-slate-300 rounded-2xl p-6 text-center hover:border-blue-500 transition-colors bg-slate-50/50">
        <input type="file" id="csv-file-input" accept=".csv" class="hidden" required />
        <label for="csv-file-input" class="cursor-pointer space-y-2 block">
          <div class="w-12 h-12 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center mx-auto">
            ${icons.download}
          </div>
          <div class="text-xs font-bold text-slate-800" id="csv-file-name">Selecciona o arrastra tu archivo CSV aquí</div>
          <div class="text-[11px] text-slate-400">Archivos .csv delimitados por comas o punto y coma (UTF-8)</div>
        </label>
      </div>

      <div class="flex justify-end gap-2 pt-2 border-t border-slate-100">
        <button type="button" id="btn-cancel-csv" class="btn-secondary">Cancelar</button>
        <button type="submit" id="btn-submit-csv" class="btn-primary flex items-center gap-1.5">
          ${icons.check} Procesar Archivo CSV
        </button>
      </div>
    </form>
  `;

  openModal("Importar Catálogo desde Archivo CSV", content);
  document.getElementById("btn-cancel-csv")?.addEventListener("click", closeModal);

  const fileInput = document.getElementById("csv-file-input");
  const fileNameLbl = document.getElementById("csv-file-name");
  fileInput?.addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (file && fileNameLbl) {
      fileNameLbl.textContent = `Archivo seleccionado: ${file.name} (${Math.round(file.size / 1024)} KB)`;
    }
  });

  const form = document.getElementById("csv-import-form");
  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const file = fileInput.files[0];
    if (!file) {
      showToast("Debes seleccionar un archivo CSV", "warning");
      return;
    }

    const btn = document.getElementById("btn-submit-csv");
    btn.disabled = true;
    btn.innerHTML = "Importando...";

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await api.upload("/products/import-csv", formData);
      closeModal();
      showToast(`CSV procesado: ${res.created} creados, ${res.updated} actualizados.`, "success");
      await fetchProducts();
    } catch (err) {
      showToast(err.message || "Error al importar CSV", "error");
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `${icons.check} Procesar Archivo CSV`;
      }
    }
  });
}

// -----------------------------------------------------------------------------
// EXPORTACIÓN A CSV Y XLSX
// -----------------------------------------------------------------------------
async function handleExportCsv() {
  try {
    showToast("Generando archivo CSV...", "info");
    const blob = await api.downloadBlob("/products/export-csv");
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `catalogo_maestro_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast("Catálogo descargado en formato CSV con éxito", "success");
  } catch (err) {
    showToast(err.message || "Error al exportar CSV", "error");
  }
}

async function handleExportXlsx() {
  try {
    showToast("Generando libro Excel (.xlsx)...", "info");
    const blob = await api.downloadBlob("/products/export-xlsx");
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `catalogo_maestro_${new Date().toISOString().slice(0, 10)}.xlsx`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast("Catálogo descargado en formato Excel (.xlsx) con éxito", "success");
  } catch (err) {
    showToast(err.message || "Error al exportar XLSX", "error");
  }
}

// -----------------------------------------------------------------------------
// MODAL: DETECTOR DE DUPLICADOS (AUDITORÍA EAN & NOMBRES)
// -----------------------------------------------------------------------------
async function openDuplicatesModal() {
  let rep = { total_groups: 0, duplicate_groups: [] };
  try {
    rep = await api.get("/products/duplicates");
  } catch (err) {
    showToast("Error al escanear duplicados", "error");
  }

  const content = `
    <div class="space-y-4 max-h-[80vh] overflow-y-auto">
      <div class="flex items-center justify-between pb-2 border-b border-slate-100">
        <div>
          <h3 class="text-sm font-bold text-slate-900">Auditoría de Duplicados en Catálogo</h3>
          <p class="text-xs text-slate-500">Detecta códigos de barras EAN repetidos o publicaciones con nombres idénticos.</p>
        </div>
        <span class="px-2.5 py-1 rounded-full text-xs font-bold ${rep.total_groups > 0 ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'}">
          ${rep.total_groups} Conflictos Encontrados
        </span>
      </div>

      ${rep.total_groups === 0 ? `
        <div class="p-8 text-center bg-slate-50 rounded-xl space-y-2">
          <div class="text-emerald-600 font-bold text-base">✔ ¡Catálogo Impecable!</div>
          <p class="text-xs text-slate-500">No se detectaron códigos de barras repetidos ni nombres idénticos en esta empresa.</p>
        </div>
      ` : `
        <div class="space-y-3">
          ${rep.duplicate_groups.map(g => `
            <div class="p-3 bg-amber-50/60 border border-amber-200 rounded-xl space-y-2 text-xs">
              <div class="flex items-center justify-between font-bold text-amber-900">
                <span>Motivo: ${g.reason}</span>
                <span class="font-mono bg-amber-100 px-2 py-0.5 rounded text-[11px]">${g.key_value}</span>
              </div>
              <div class="bg-white rounded-lg p-2 border border-amber-200 space-y-1">
                ${g.candidates.map(c => `
                  <div class="flex items-center justify-between py-1 border-b border-slate-100 last:border-b-0 text-[11px]">
                    <span class="font-bold text-slate-900">${c.product_name}</span>
                    <span class="font-mono text-slate-600">SKU: ${c.sku} ${c.barcode_ean ? `· EAN: ${c.barcode_ean}` : ''}</span>
                  </div>
                `).join("")}
              </div>
            </div>
          `).join("")}
        </div>
      `}
    </div>
  `;

  openModal("Detector de Duplicados", content);
}

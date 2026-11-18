/**
 * Vista 3: Productos (Catálogo Maestro, Variantes, EAN-13 y SKUs MeLi).
 */

import { api } from "../api.js";
import { state } from "../state.js";
import { icons } from "../icons.js";
import { openModal } from "../components/modal.js";
import { showToast } from "../components/toast.js";

export function renderProductsView() {
  const container = document.createElement("div");
  container.className = "space-y-5 animate-fade-in";

  let currentPage = 1;
  let searchFilter = "";

  container.innerHTML = `
    <!-- Encabezado de Sección -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
      <div>
        <h2 class="text-2xl font-black text-slate-900 tracking-tight">Catálogo de Productos</h2>
        <p class="text-xs text-slate-500 mt-0.5">Gestión de productos maestros, variantes, código EAN-13 y costos de adquisición (COGS)</p>
      </div>

      <div class="flex items-center space-x-2">
        <button id="btn-create-product" class="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl transition-smooth shadow-md shadow-blue-600/30 flex items-center space-x-2 touch-target">
          ${icons.plus("w-4 h-4")}
          <span>Nuevo Producto</span>
        </button>
      </div>
    </div>

    <!-- Barra de Búsqueda -->
    <div class="p-4 bg-white rounded-2xl border border-slate-200 shadow-sm flex items-center justify-between gap-3">
      <div class="flex-1 max-w-sm relative">
        <span class="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
          ${icons.search("w-4 h-4")}
        </span>
        <input 
          id="products-search-input" 
          type="text" 
          placeholder="Buscar por nombre, marca o modelo..." 
          class="w-full pl-9 pr-3.5 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:ring-2 focus:ring-blue-600 focus:outline-none transition-smooth"
        />
      </div>
      <button id="btn-refresh-products" class="p-2 border border-slate-200 rounded-xl hover:bg-slate-50 text-slate-600 transition-smooth touch-target">
        ${icons.refresh("w-4 h-4")}
      </button>
    </div>

    <!-- Tabla de Productos -->
    <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <div class="table-container">
        <table class="w-full text-left text-xs border-collapse">
          <thead>
            <tr class="border-b border-slate-200 bg-slate-50/70 text-slate-500 font-bold uppercase tracking-wider text-[10px]">
              <th class="py-3 px-4">Producto Maestro</th>
              <th class="py-3 px-4">Marca</th>
              <th class="py-3 px-4">Categoría</th>
              <th class="py-3 px-4">Variantes & EAN</th>
              <th class="py-3 px-4">Costo COGS</th>
              <th class="py-3 px-4 text-right">Acciones</th>
            </tr>
          </thead>
          <tbody id="products-table-tbody" class="divide-y divide-slate-100 text-slate-700">
            <tr>
              <td colspan="6" class="py-8 text-center text-slate-400">
                ${icons.spinner("w-5 h-5 inline-block mr-2")} Cargando catálogo...
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Paginación -->
      <div class="flex items-center justify-between px-4 py-3 bg-slate-50/50 border-t border-slate-100 text-xs">
        <span id="products-pagination-info" class="text-slate-500 font-medium">Mostrando 0 productos</span>
        <div class="flex items-center space-x-1.5">
          <button id="btn-products-prev" class="px-3 py-1.5 border border-slate-200 rounded-lg text-slate-600 bg-white hover:bg-slate-50 disabled:opacity-40 transition-smooth font-semibold" disabled>
            Anterior
          </button>
          <button id="btn-products-next" class="px-3 py-1.5 border border-slate-200 rounded-lg text-slate-600 bg-white hover:bg-slate-50 disabled:opacity-40 transition-smooth font-semibold" disabled>
            Siguiente
          </button>
        </div>
      </div>
    </div>
  `;

  // Listeners
  const searchInput = container.querySelector("#products-search-input");
  const btnRefresh = container.querySelector("#btn-refresh-products");
  const btnCreate = container.querySelector("#btn-create-product");
  const btnPrev = container.querySelector("#btn-products-prev");
  const btnNext = container.querySelector("#btn-products-next");

  if (searchInput) {
    let debounce;
    searchInput.addEventListener("input", (e) => {
      clearTimeout(debounce);
      debounce = setTimeout(() => {
        searchFilter = e.target.value.trim();
        currentPage = 1;
        fetchProducts();
      }, 300);
    });
  }

  if (btnRefresh) btnRefresh.addEventListener("click", () => fetchProducts());
  if (btnCreate) btnCreate.addEventListener("click", () => openCreateProductModal());

  if (btnPrev) {
    btnPrev.addEventListener("click", () => {
      if (currentPage > 1) {
        currentPage--;
        fetchProducts();
      }
    });
  }

  if (btnNext) {
    btnNext.addEventListener("click", () => {
      currentPage++;
      fetchProducts();
    });
  }

  async function fetchProducts() {
    const tbody = container.querySelector("#products-table-tbody");

    try {
      const params = { page: currentPage, size: 10 };
      if (searchFilter) params.search = searchFilter;

      const data = await api.get("/products", params);
      const items = data.items || [];

      if (items.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="6" class="py-12 text-center text-slate-400">
              No hay productos registrados en el catálogo. Haz clic en "Nuevo Producto" para dar de alta tu primer artículo.
            </td>
          </tr>
        `;
      } else {
        tbody.innerHTML = items.map(p => {
          const variants = p.variants || [];
          const variantsHtml = variants.map(v => `
            <div class="py-0.5 font-mono text-[11px] text-slate-600">
              <strong class="text-slate-800">${v.variant_name}</strong> · SKU: ${v.sku} · EAN: ${v.barcode_ean || 'S/N'}
            </div>
          `).join("") || '<span class="text-slate-400">Sin variantes</span>';

          const minCogs = variants.length > 0 ? Math.min(...variants.map(v => Number(v.cogs_cost || 0))) : 0;

          return `
            <tr class="hover:bg-slate-50/80 transition-smooth">
              <td class="py-3.5 px-4 font-bold text-slate-900">${p.name}</td>
              <td class="py-3.5 px-4 text-slate-600">${p.brand || 'Genérico'}</td>
              <td class="py-3.5 px-4"><span class="badge badge-info text-[10px]">${p.category || 'General'}</span></td>
              <td class="py-3.5 px-4">${variantsHtml}</td>
              <td class="py-3.5 px-4 font-bold text-slate-900">$ ${minCogs.toFixed(2)}</td>
              <td class="py-3.5 px-4 text-right">
                <button data-product-id="${p.id}" class="btn-link-meli-sku px-2.5 py-1 text-xs font-semibold text-blue-600 hover:text-blue-800 bg-blue-50 hover:bg-blue-100 rounded-lg transition-smooth">
                  Mapear MeLi
                </button>
              </td>
            </tr>
          `;
        }).join("");

        tbody.querySelectorAll(".btn-link-meli-sku").forEach(btn => {
          btn.addEventListener("click", () => {
            const prodId = btn.getAttribute("data-product-id");
            const prod = items.find(x => x.id === prodId);
            openMapSkuModal(prod);
          });
        });
      }

      const infoEl = container.querySelector("#products-pagination-info");
      if (infoEl) infoEl.textContent = `Página ${data.page} de ${data.pages || 1} (${data.total} productos en total)`;

      if (btnPrev) btnPrev.disabled = !data.has_prev;
      if (btnNext) btnNext.disabled = !data.has_next;

    } catch (err) {
      tbody.innerHTML = `
        <tr>
          <td colspan="6" class="py-8 text-center text-red-600 font-semibold">
            Error al consultar catálogo: ${err.message}
          </td>
        </tr>
      `;
    }
  }

  function openCreateProductModal() {
    openModal({
      title: "Alta de Producto Maestro & Variantes",
      size: "lg",
      content: `
        <div class="space-y-4">
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Nombre del Producto</label>
              <input id="new-prod-name" type="text" placeholder="Termo Inteligente Acero 500ml" class="w-full px-3 py-2 text-xs border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-600 focus:outline-none" />
            </div>
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Marca</label>
              <input id="new-prod-brand" type="text" placeholder="ThermoTech" class="w-full px-3 py-2 text-xs border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-600 focus:outline-none" />
            </div>
          </div>

          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1">Categoría</label>
            <input id="new-prod-cat" type="text" placeholder="Hogar y Cocina" class="w-full px-3 py-2 text-xs border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-600 focus:outline-none" />
          </div>

          <!-- Variantes Iniciales -->
          <div class="pt-2 border-t border-slate-100">
            <h4 class="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Variante Inicial</h4>
            <div class="grid grid-cols-1 sm:grid-cols-4 gap-2">
              <input id="new-var-name" type="text" placeholder="Nombre (ej. Negro Mate)" class="px-2.5 py-1.5 text-xs border border-slate-200 rounded-lg" />
              <input id="new-var-sku" type="text" placeholder="SKU Interno" class="px-2.5 py-1.5 text-xs border border-slate-200 rounded-lg font-mono" />
              <input id="new-var-ean" type="text" placeholder="EAN-13 (13 dígitos)" maxlength="13" class="px-2.5 py-1.5 text-xs border border-slate-200 rounded-lg font-mono" />
              <input id="new-var-cogs" type="number" step="0.01" placeholder="Costo COGS ($)" class="px-2.5 py-1.5 text-xs border border-slate-200 rounded-lg font-mono" />
            </div>
          </div>
        </div>
      `,
      confirmText: "Guardar Producto",
      onConfirm: async () => {
        const name = document.getElementById("new-prod-name").value.trim();
        const brand = document.getElementById("new-prod-brand").value.trim();
        const category = document.getElementById("new-prod-cat").value.trim();

        const varName = document.getElementById("new-var-name").value.trim() || "Estándar";
        const varSku = document.getElementById("new-var-sku").value.trim() || `SKU-${Date.now().toString().slice(-6)}`;
        const varEan = document.getElementById("new-var-ean").value.trim() || null;
        const varCogs = parseFloat(document.getElementById("new-var-cogs").value) || 0;

        if (!name) throw new Error("El nombre del producto es obligatorio.");
        if (!state.currentCompany) throw new Error("No hay una empresa activa seleccionada.");

        const payload = {
          company_id: state.currentCompany.company_id,
          name,
          brand,
          category,
          variants: [
            {
              variant_name: varName,
              sku: varSku,
              barcode_ean: varEan,
              cogs_cost: varCogs,
            }
          ]
        };

        await api.post("/products", payload);
        showToast("Producto creado exitosamente con sus variantes.", "success");
        fetchProducts();
      }
    });
  }

  function openMapSkuModal(product) {
    if (!product || !product.variants || product.variants.length === 0) {
      showToast("El producto no cuenta con variantes disponibles.", "warning");
      return;
    }

    const firstVar = product.variants[0];

    openModal({
      title: `Vincular Publicación MeLi · ${product.name}`,
      size: "md",
      content: `
        <div class="space-y-4">
          <p class="text-xs text-slate-600">
            Mapea la variante interna <strong>${firstVar.variant_name}</strong> (SKU: ${firstVar.sku}) a un ID de publicación oficial de Mercado Libre México.
          </p>

          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1">ID de Publicación Mercado Libre (MLM)</label>
            <input id="meli-item-id-input" type="text" placeholder="MLM1234567890" class="w-full px-3 py-2 text-xs font-mono border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-600 focus:outline-none" />
          </div>

          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1">ID de Variación en MeLi (opcional)</label>
            <input id="meli-var-id-input" type="number" placeholder="17892348921" class="w-full px-3 py-2 text-xs font-mono border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-600 focus:outline-none" />
          </div>
        </div>
      `,
      confirmText: "Vincular Publicación",
      onConfirm: async () => {
        const meliItemId = document.getElementById("meli-item-id-input").value.trim().toUpperCase();
        const meliVarId = document.getElementById("meli-var-id-input").value.trim();

        if (!meliItemId) throw new Error("Debes proporcionar el ID MLM de Mercado Libre.");

        // Consultar cuentas MeLi para obtener el meli_account_id
        const accountsData = await api.get("/meli-accounts");
        const accounts = accountsData.items || [];
        if (accounts.length === 0) {
          throw new Error("No hay cuentas de Mercado Libre vinculadas en esta empresa. Ve a Integraciones primero.");
        }

        const payload = {
          meli_account_id: accounts[0].id,
          variant_id: firstVar.id,
          meli_item_id: meliItemId,
          meli_variation_id: meliVarId ? parseInt(meliVarId) : null,
          seller_sku: firstVar.sku,
          sync_stock: true,
          sync_price: true,
        };

        await api.post("/products/skus", payload);
        showToast("Publicación de Mercado Libre vinculada exitosamente.", "success");
      }
    });
  }

  fetchProducts();
  return container;
}

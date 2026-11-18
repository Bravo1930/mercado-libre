/**
 * Buscador Global Rápido (Command Palette / Cmd+K).
 * Permite buscar vistas de navegación, productos, órdenes y acciones rápidas con teclado.
 */

import { state } from "../state.js";
import { icons } from "../icons.js";
import { NAV_ITEMS } from "./sidebar.js";

let searchOverlay = null;

export function openSearchModal() {
  closeSearchModal();

  const overlay = document.createElement("div");
  overlay.id = "global-search-overlay";
  overlay.className = "fixed inset-0 z-50 flex items-start justify-center pt-20 p-4 bg-slate-900/60 backdrop-blur-sm animate-fade-in";

  overlay.innerHTML = `
    <div class="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-xl overflow-hidden animate-fade-in">
      <div class="flex items-center px-4 border-b border-slate-100">
        <span class="text-slate-400 mr-3">${icons.search("w-5 h-5")}</span>
        <input 
          id="cmd-palette-input" 
          type="text" 
          placeholder="Buscar secciones, órdenes, productos o configuraciones..." 
          class="w-full py-4 text-sm font-medium text-slate-800 placeholder-slate-400 bg-transparent focus:outline-none"
          autofocus
        />
        <kbd class="px-2 py-0.5 text-[10px] font-semibold text-slate-400 bg-slate-100 border border-slate-200 rounded">ESC</kbd>
      </div>

      <div id="cmd-palette-results" class="max-h-80 overflow-y-auto p-2 space-y-1 text-sm">
        <div class="px-3 py-1.5 text-[10px] font-bold text-slate-400 uppercase tracking-wider">
          Módulos del Sistema
        </div>
        ${
          NAV_ITEMS.map((item, idx) => `
            <button data-route="${item.id}" class="cmd-item w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-semibold text-slate-700 hover:bg-blue-50 hover:text-blue-700 transition-smooth">
              <div class="flex items-center space-x-3">
                ${icons[item.icon] ? icons[item.icon]("w-4 h-4 text-slate-400") : ""}
                <span>${idx + 1}. ${item.label}</span>
              </div>
              <span class="text-[10px] text-slate-400 font-mono">Ir a #${item.id}</span>
            </button>
          `).join("")
        }
      </div>
    </div>
  `;

  document.body.appendChild(overlay);
  searchOverlay = overlay;
  document.body.style.overflow = "hidden";

  const input = overlay.querySelector("#cmd-palette-input");
  const resultsContainer = overlay.querySelector("#cmd-palette-results");
  if (input) input.focus();

  // Filtrado dinámico
  if (input && resultsContainer) {
    input.addEventListener("input", (e) => {
      const q = e.target.value.toLowerCase().trim();
      const filtered = NAV_ITEMS.filter(it => it.label.toLowerCase().includes(q) || it.id.includes(q));

      if (filtered.length === 0) {
        resultsContainer.innerHTML = `
          <div class="p-8 text-center text-xs text-slate-400">
            No se encontraron módulos coincidentes con "${q}".
          </div>
        `;
      } else {
        resultsContainer.innerHTML = `
          <div class="px-3 py-1.5 text-[10px] font-bold text-slate-400 uppercase tracking-wider">
            Resultados (${filtered.length})
          </div>
          ${filtered.map((item, idx) => `
            <button data-route="${item.id}" class="cmd-item w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-semibold text-slate-700 hover:bg-blue-50 hover:text-blue-700 transition-smooth">
              <div class="flex items-center space-x-3">
                ${icons[item.icon] ? icons[item.icon]("w-4 h-4 text-slate-400") : ""}
                <span>${item.label}</span>
              </div>
              <span class="text-[10px] text-slate-400 font-mono">Ir a #${item.id}</span>
            </button>
          `).join("")}
        `;

        bindItems();
      }
    });
  }

  function bindItems() {
    resultsContainer.querySelectorAll(".cmd-item").forEach(btn => {
      btn.addEventListener("click", () => {
        const route = btn.getAttribute("data-route");
        state.setRoute(route);
        closeSearchModal();
      });
    });
  }
  bindItems();

  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) closeSearchModal();
  });

  const escHandler = (e) => {
    if (e.key === "Escape") {
      closeSearchModal();
      window.removeEventListener("keydown", escHandler);
    }
  };
  window.addEventListener("keydown", escHandler);
}

export function closeSearchModal() {
  if (searchOverlay) {
    searchOverlay.remove();
    searchOverlay = null;
    document.body.style.overflow = "";
  }
}

// Atajo global Ctrl+K / Cmd+K
window.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    openSearchModal();
  }
});

/**
 * Menú Lateral de Navegación (Sidebar) con las 17 Secciones Oficiales.
 * Soporta modo colapsado en escritorio y drawer off-canvas en tablet/móvil.
 */

import { state } from "../state.js";
import { icons } from "../icons.js";

export const NAV_ITEMS = [
  { id: "dashboard", label: "Inicio", icon: "home" },
  { id: "orders", label: "Ventas", icon: "orders" },
  { id: "products", label: "Productos", icon: "products" },
  { id: "inventory", label: "Inventario", icon: "inventory" },
  { id: "warehouses", label: "Almacenes", icon: "warehouses" },
  { id: "labels", label: "Etiquetas", icon: "labels" },
  { id: "shipments", label: "Envíos", icon: "shipments" },
  { id: "promotions", label: "Promociones", icon: "promotions" },
  { id: "pricing", label: "Precios", icon: "pricing" },
  { id: "finances", label: "Finanzas", icon: "finances" },
  { id: "purchases", label: "Compras", icon: "purchases" },
  { id: "suppliers", label: "Proveedores", icon: "suppliers" },
  { id: "tabular", label: "Planillas ERP", icon: "tabular", badge: "13 Vistas" },
  { id: "reports", label: "Reportes", icon: "reports" },
  { id: "ai", label: "Inteligencia artificial", icon: "ai", badge: "AI" },
  { id: "automations", label: "Automatizaciones", icon: "automations" },
  { id: "security", label: "Ciberseguridad", icon: "shield", badge: "SOC" },
  { id: "saas", label: "Panel SaaS", icon: "integrations", badge: "MRR" },
  { id: "integrations", label: "Integraciones", icon: "integrations" },
  { id: "settings", label: "Configuración", icon: "settings" },
];

export function renderSidebar() {
  const isCollapsed = state.sidebarCollapsed;
  const isMobileOpen = state.mobileMenuOpen;
  const activeRoute = state.currentRoute;

  const sidebarEl = document.createElement("aside");
  sidebarEl.id = "app-sidebar";

  // Clases responsivas: fijo en móvil/tablet con overlay, relativo/sticky en escritorio
  const widthClass = isCollapsed ? "lg:w-20" : "lg:w-64";
  const mobileTranslateClass = isMobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0";

  sidebarEl.className = `fixed lg:sticky top-0 left-0 z-40 h-screen ${widthClass} bg-slate-900 text-slate-300 flex flex-col border-r border-slate-800 transition-all duration-300 ease-in-out ${mobileTranslateClass}`;

  sidebarEl.innerHTML = `
    <!-- Encabezado del Menú / Logo -->
    <div class="flex items-center justify-between h-16 px-4 bg-slate-950/60 border-b border-slate-800 shrink-0">
      <div class="flex items-center space-x-3 overflow-hidden">
        <!-- Logo Mercado Libre / ERP -->
        <div class="w-9 h-9 rounded-xl bg-[#FFE600] flex items-center justify-center shrink-0 shadow-md">
          <svg class="w-5 h-5 text-[#2D3277]" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"></path>
          </svg>
        </div>
        ${
          !isCollapsed
            ? `<div class="truncate">
                <span class="block text-sm font-extrabold text-white tracking-tight">ERP MeLi México</span>
                <span class="block text-[10px] font-mono text-[#FFE600] font-semibold">EMPRESARIAL 2026</span>
              </div>`
            : ""
        }
      </div>

      <!-- Botón cerrar en móvil -->
      <button id="btn-close-sidebar-mobile" class="lg:hidden p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 touch-target flex items-center justify-center" aria-label="Cerrar menú">
        ${icons.close("w-5 h-5")}
      </button>
    </div>

    <!-- Lista de Navegación de 17 Ítems -->
    <nav class="flex-1 overflow-y-auto px-3 py-4 space-y-1">
      ${
        NAV_ITEMS.map((item, idx) => {
          const isActive = activeRoute === item.id;
          const iconFn = icons[item.icon] || icons.home;
          const activeClass = isActive
            ? "bg-blue-600 text-white font-bold shadow-md shadow-blue-600/30 ring-1 ring-blue-500"
            : "text-slate-400 hover:bg-slate-800/80 hover:text-slate-100 font-medium";

          return `
            <a href="#${item.id}" data-route="${item.id}" class="nav-item group flex items-center ${isCollapsed ? 'justify-center px-2' : 'justify-between px-3.5'} py-2.5 rounded-xl text-xs transition-smooth touch-target ${activeClass}" title="${item.label}">
              <div class="flex items-center space-x-3 truncate">
                <span class="shrink-0 transition-transform duration-200 group-hover:scale-110 ${isActive ? 'text-white' : 'text-slate-400 group-hover:text-slate-200'}">
                  ${iconFn("w-5 h-5")}
                </span>
                ${!isCollapsed ? `<span class="truncate">${idx + 1}. ${item.label}</span>` : ""}
              </div>
              ${
                !isCollapsed && item.badge
                  ? `<span class="px-1.5 py-0.5 text-[9px] font-extrabold uppercase rounded bg-[#FFE600] text-[#2D3277] shadow-sm">${item.badge}</span>`
                  : ""
              }
            </a>
          `;
        }).join("")
      }
    </nav>

    <!-- Footer del Sidebar con botón de Colapsar (Escritorio) -->
    <div class="p-3 bg-slate-950/60 border-t border-slate-800 shrink-0 hidden lg:block">
      <button id="btn-toggle-collapse" class="w-full flex items-center justify-center p-2 rounded-xl text-xs font-semibold text-slate-400 hover:bg-slate-800 hover:text-white transition-smooth touch-target">
        <svg class="w-5 h-5 transition-transform duration-200 ${isCollapsed ? 'rotate-180' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 19l-7-7 7-7m8 14l-7-7 7-7"></path>
        </svg>
        ${!isCollapsed ? '<span class="ml-2">Colapsar menú</span>' : ''}
      </button>
    </div>
  `;

  // Listeners
  sidebarEl.querySelectorAll(".nav-item").forEach(link => {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      const route = link.getAttribute("data-route");
      state.setRoute(route);
    });
  });

  const btnMobileClose = sidebarEl.querySelector("#btn-close-sidebar-mobile");
  if (btnMobileClose) {
    btnMobileClose.addEventListener("click", () => state.toggleMobileMenu());
  }

  const btnCollapse = sidebarEl.querySelector("#btn-toggle-collapse");
  if (btnCollapse) {
    btnCollapse.addEventListener("click", () => state.toggleSidebar());
  }

  return sidebarEl;
}

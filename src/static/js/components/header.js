/**
 * Componente de Encabezado Superior (Header).
 * Incluye selector de empresa activa, buscador global Cmd+K, centro de notificaciones y menú de perfil.
 */

import { state } from "../state.js";
import { icons } from "../icons.js";
import { openSearchModal } from "./search_modal.js";
import { openProfileModal } from "../views/profile.js";

export function renderHeader() {
  const user = state.user;
  const currentCo = state.currentCompany;
  const companies = state.companies || [];

  const headerEl = document.createElement("header");
  headerEl.className = "sticky top-0 z-30 flex items-center justify-between h-16 px-4 md:px-6 bg-white border-b border-slate-200 shadow-sm transition-smooth";

  headerEl.innerHTML = `
    <!-- Lado Izquierdo: Botón Hamburguesa + Selector de Empresa -->
    <div class="flex items-center space-x-3 md:space-x-4">
      <button id="btn-toggle-mobile" class="p-2 -ml-2 text-slate-500 rounded-lg lg:hidden hover:bg-slate-100 touch-target flex items-center justify-center" aria-label="Abrir menú de navegación">
        ${icons.menu("w-6 h-6")}
      </button>

      <!-- Selector de Empresa Activa (Multi-RFC) -->
      <div class="relative" id="company-dropdown-wrapper">
        <button id="btn-company-dropdown" class="flex items-center space-x-2 px-3 py-1.5 rounded-xl border border-slate-200 bg-slate-50 hover:bg-slate-100 text-slate-900 transition-smooth touch-target">
          <div class="w-2.5 h-2.5 rounded-full bg-emerald-500 ring-2 ring-emerald-200"></div>
          <div class="text-left">
            <span class="block text-xs font-bold leading-tight max-w-[130px] sm:max-w-[180px] md:max-w-[220px] truncate">
              ${currentCo ? currentCo.legal_name : "Sin Empresa"}
            </span>
            <span class="block text-[10px] font-mono font-medium text-slate-500">
              ${currentCo ? currentCo.rfc : "Seleccionar"}
            </span>
          </div>
          ${icons.chevronDown("w-4 h-4 text-slate-400")}
        </button>

        <!-- Dropdown de Empresas -->
        <div id="company-dropdown-menu" class="hidden absolute left-0 mt-2 w-72 bg-white rounded-xl shadow-xl border border-slate-200 py-1.5 z-40 animate-fade-in">
          <div class="px-3 py-2 border-b border-slate-100 text-[11px] font-bold text-slate-400 uppercase tracking-wider">
            Tus Empresas Autorizadas
          </div>
          <div class="max-h-60 overflow-y-auto">
            ${
              companies.map(c => `
                <button data-company-id="${c.company_id}" class="btn-select-company w-full text-left px-3.5 py-2.5 flex items-start justify-between hover:bg-blue-50/70 transition-smooth ${currentCo && c.company_id === currentCo.company_id ? 'bg-blue-50/50' : ''}">
                  <div>
                    <span class="block text-xs font-bold text-slate-900 leading-tight">${c.legal_name}</span>
                    <span class="block text-[10px] font-mono text-slate-500">${c.rfc} · Rol: <strong class="text-blue-700 capitalize">${c.role}</strong></span>
                  </div>
                  ${currentCo && c.company_id === currentCo.company_id ? `<span class="text-blue-600 mt-0.5">${icons.check("w-4 h-4")}</span>` : ""}
                </button>
              `).join("")
            }
          </div>
        </div>
      </div>
    </div>

    <!-- Centro: Buscador Global (Trigger Cmd+K) -->
    <div class="hidden md:flex flex-1 max-w-md mx-6">
      <button id="btn-trigger-search" class="w-full flex items-center justify-between px-3.5 py-2 text-sm text-slate-400 bg-slate-50 border border-slate-200 rounded-xl hover:border-slate-300 hover:bg-slate-100/70 transition-smooth">
        <div class="flex items-center space-x-2.5">
          ${icons.search("w-4 h-4 text-slate-400")}
          <span>Buscar pedidos, SKU, publicaciones...</span>
        </div>
        <kbd class="px-2 py-0.5 text-[10px] font-semibold text-slate-500 bg-white border border-slate-200 rounded shadow-sm">Ctrl+K</kbd>
      </button>
    </div>

    <!-- Lado Derecho: Buscador móvil + Notificaciones + Perfil -->
    <div class="flex items-center space-x-2 md:space-x-3">
      <!-- Icono de búsqueda para móvil -->
      <button id="btn-search-mobile" class="md:hidden p-2 text-slate-500 hover:bg-slate-100 rounded-lg touch-target flex items-center justify-center" aria-label="Buscar">
        ${icons.search("w-5 h-5")}
      </button>

      <!-- Campana de Notificaciones -->
      <div class="relative" id="notifications-wrapper">
        <button id="btn-notifications" class="relative p-2 text-slate-600 hover:bg-slate-100 rounded-xl touch-target transition-smooth flex items-center justify-center" aria-label="Ver notificaciones">
          ${icons.bell("w-5 h-5")}
          <span class="absolute top-1.5 right-1.5 w-2 h-2 bg-blue-600 rounded-full ring-2 ring-white"></span>
        </button>

        <!-- Dropdown de Notificaciones -->
        <div id="notifications-dropdown" class="hidden absolute right-0 mt-2 w-80 bg-white rounded-xl shadow-xl border border-slate-200 overflow-hidden z-40 animate-fade-in">
          <div class="flex items-center justify-between px-4 py-3 bg-slate-50 border-b border-slate-100">
            <span class="text-xs font-bold text-slate-900">Notificaciones del Sistema</span>
            <span class="badge badge-meli text-[10px]">Mercado Libre</span>
          </div>
          <div class="p-3 text-xs text-slate-600 space-y-2.5 max-h-72 overflow-y-auto">
            <div class="p-2.5 rounded-lg bg-emerald-50/70 border border-emerald-100 flex items-start space-x-2">
              <span class="text-emerald-600 mt-0.5">${icons.check("w-4 h-4")}</span>
              <div>
                <p class="font-semibold text-emerald-950">Webhooks MeLi Conectados</p>
                <p class="text-[11px] text-emerald-800">Canal de eventos en tiempo real activo en Redis.</p>
              </div>
            </div>
            <div class="p-2.5 rounded-lg bg-blue-50/70 border border-blue-100 flex items-start space-x-2">
              <span class="text-blue-600 mt-0.5">${icons.shield("w-4 h-4")}</span>
              <div>
                <p class="font-semibold text-blue-950">Aislamiento Multi-Empresa Activo</p>
                <p class="text-[11px] text-blue-800">Cero confianza en frontend habilitado para RFC ${currentCo ? currentCo.rfc : ''}.</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Menú de Usuario / Perfil -->
      <div class="relative" id="user-menu-wrapper">
        <button id="btn-user-menu" class="flex items-center space-x-2.5 p-1.5 pr-2.5 rounded-xl hover:bg-slate-100 transition-smooth touch-target">
          <div class="w-8 h-8 rounded-full bg-blue-600 text-white font-bold flex items-center justify-center text-xs shadow-sm">
            ${user ? user.full_name.charAt(0).toUpperCase() : "U"}
          </div>
          <div class="hidden sm:block text-left">
            <span class="block text-xs font-bold text-slate-900 leading-tight">${user ? user.full_name : "Usuario"}</span>
            <span class="block text-[10px] text-slate-500 font-medium capitalize">${state.getActiveRole()}</span>
          </div>
          ${icons.chevronDown("w-3.5 h-3.5 text-slate-400 hidden sm:block")}
        </button>

        <!-- Dropdown Usuario -->
        <div id="user-menu-dropdown" class="hidden absolute right-0 mt-2 w-56 bg-white rounded-xl shadow-xl border border-slate-200 py-1.5 z-40 animate-fade-in">
          <div class="px-3.5 py-2 border-b border-slate-100">
            <p class="text-xs font-bold text-slate-900">${user ? user.full_name : ''}</p>
            <p class="text-[11px] text-slate-500 truncate">${user ? user.email : ''}</p>
            <div class="mt-1.5">
              <span class="badge badge-info text-[10px] capitalize">${state.getActiveRole()}</span>
            </div>
          </div>
          <div class="py-1">
            <button id="btn-open-profile" class="w-full text-left px-3.5 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 flex items-center space-x-2 transition-smooth">
              ${icons.user("w-4 h-4 text-slate-400")}
              <span>Mi Perfil & Sesiones</span>
            </button>
            <button id="btn-header-settings" class="w-full text-left px-3.5 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 flex items-center space-x-2 transition-smooth">
              ${icons.settings("w-4 h-4 text-slate-400")}
              <span>Configuración</span>
            </button>
          </div>
          <div class="border-t border-slate-100 pt-1">
            <button id="btn-logout" class="w-full text-left px-3.5 py-2 text-xs font-medium text-red-600 hover:bg-red-50 flex items-center space-x-2 transition-smooth">
              ${icons.close("w-4 h-4 text-red-500")}
              <span>Cerrar Sesión</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  `;

  // Listeners
  const mobileToggle = headerEl.querySelector("#btn-toggle-mobile");
  if (mobileToggle) mobileToggle.addEventListener("click", () => state.toggleMobileMenu());

  // Dropdown de Empresas
  const btnCompany = headerEl.querySelector("#btn-company-dropdown");
  const menuCompany = headerEl.querySelector("#company-dropdown-menu");
  if (btnCompany && menuCompany) {
    btnCompany.addEventListener("click", (e) => {
      e.stopPropagation();
      menuCompany.classList.toggle("hidden");
    });
  }

  // Cambio de Empresa Activa
  headerEl.querySelectorAll(".btn-select-company").forEach(btn => {
    btn.addEventListener("click", () => {
      const companyId = btn.getAttribute("data-company-id");
      const target = companies.find(c => c.company_id === companyId);
      if (target) {
        state.setCompany(target);
        if (menuCompany) menuCompany.classList.add("hidden");
      }
    });
  });

  // Buscador
  const btnSearch = headerEl.querySelector("#btn-trigger-search");
  const btnSearchMobile = headerEl.querySelector("#btn-search-mobile");
  if (btnSearch) btnSearch.addEventListener("click", openSearchModal);
  if (btnSearchMobile) btnSearchMobile.addEventListener("click", openSearchModal);

  // Notificaciones
  const btnNotif = headerEl.querySelector("#btn-notifications");
  const menuNotif = headerEl.querySelector("#notifications-dropdown");
  if (btnNotif && menuNotif) {
    btnNotif.addEventListener("click", (e) => {
      e.stopPropagation();
      menuNotif.classList.toggle("hidden");
    });
  }

  // Menú Usuario
  const btnUser = headerEl.querySelector("#btn-user-menu");
  const menuUser = headerEl.querySelector("#user-menu-dropdown");
  if (btnUser && menuUser) {
    btnUser.addEventListener("click", (e) => {
      e.stopPropagation();
      menuUser.classList.toggle("hidden");
    });
  }

  // Perfil
  const btnProfile = headerEl.querySelector("#btn-open-profile");
  if (btnProfile) {
    btnProfile.addEventListener("click", () => {
      if (menuUser) menuUser.classList.add("hidden");
      openProfileModal();
    });
  }

  // Configuración
  const btnSettings = headerEl.querySelector("#btn-header-settings");
  if (btnSettings) {
    btnSettings.addEventListener("click", () => {
      if (menuUser) menuUser.classList.add("hidden");
      state.setRoute("settings");
    });
  }

  // Logout
  const btnLogout = headerEl.querySelector("#btn-logout");
  if (btnLogout) {
    btnLogout.addEventListener("click", async () => {
      try {
        await import("../api.js").then(m => m.api.post("/auth/logout"));
      } catch (err) {
        // En caso de fallo de red, se procede localmente
      }
      state.logout();
    });
  }

  // Cerrar dropdowns al hacer clic fuera
  window.addEventListener("click", () => {
    if (menuCompany) menuCompany.classList.add("hidden");
    if (menuNotif) menuNotif.classList.add("hidden");
    if (menuUser) menuUser.classList.add("hidden");
  });

  return headerEl;
}

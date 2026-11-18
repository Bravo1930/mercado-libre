/**
 * Aplicación SPA Principal del ERP Mercado Libre México
 * Enrutador Hash, Guards de Autenticación, Disposición Responsiva y Coordinación de Vistas.
 */

import { state } from './state.js';
import { api } from './api.js';
import { renderHeader } from './components/header.js';
import { renderSidebar } from './components/sidebar.js';
import { initSearchModal } from './components/search_modal.js';

// Vistas
import { renderLogin } from './views/login.js';
import { renderDashboard } from './views/dashboard.js';
import { renderOrders } from './views/orders.js';
import { renderProducts } from './views/products.js';
import { renderInventory } from './views/inventory.js';
import { renderWarehouses } from './views/warehouses.js';
import { renderLabels } from './views/labels.js';
import { renderShipments } from './views/shipments.js';
import { renderPromotions } from './views/promotions.js';
import { renderPricing } from './views/pricing.js';
import { renderFinances } from './views/finances.js';
import { renderPurchases } from './views/purchases.js';
import { renderSuppliers } from './views/suppliers.js';
import { renderReports } from './views/reports.js';
import { renderAI } from './views/ai.js';
import { renderAutomations } from './views/automations.js';
import { renderIntegrations } from './views/integrations.js';
import { renderSettings } from './views/settings.js';
import { renderProfile } from './views/profile.js';

const routes = {
  login: renderLogin,
  dashboard: renderDashboard,
  orders: renderOrders,
  products: renderProducts,
  inventory: renderInventory,
  warehouses: renderWarehouses,
  labels: renderLabels,
  shipments: renderShipments,
  promotions: renderPromotions,
  pricing: renderPricing,
  finances: renderFinances,
  purchases: renderPurchases,
  suppliers: renderSuppliers,
  reports: renderReports,
  ai: renderAI,
  automations: renderAutomations,
  integrations: renderIntegrations,
  settings: renderSettings,
  profile: renderProfile,
};

async function initApp() {
  initSearchModal();

  // Escuchar cambios de estado para actualizar vistas si cambia la empresa activa
  state.subscribe((prop, val) => {
    if (prop === 'currentCompany') {
      const route = getRouteFromHash();
      if (route !== 'login') {
        loadView(route);
      }
    }
  });

  // Validar sesión contra el backend
  if (state.token) {
    try {
      const meData = await api.get('/auth/me');
      if (meData.user) state.user = meData.user;
      if (meData.companies) {
        state.companies = meData.companies;
        if (!state.currentCompany && meData.companies.length > 0) {
          state.currentCompany = meData.companies[0];
        }
      }
    } catch (err) {
      console.warn('Sesión no válida o expirada en backend:', err);
      state.clearAuth();
    }
  }

  // Escuchar cambios en la URL (Hash routing)
  window.addEventListener('hashchange', handleRouting);
  handleRouting();
}

function getRouteFromHash() {
  const hash = window.location.hash.replace('#', '').trim();
  return hash || (state.token ? 'dashboard' : 'login');
}

function handleRouting() {
  let route = getRouteFromHash();

  // Guard de autenticación
  if (!state.token && route !== 'login') {
    window.location.hash = '#login';
    return;
  }

  if (state.token && route === 'login') {
    window.location.hash = '#dashboard';
    return;
  }

  state.currentRoute = route;
  loadView(route);
}

function loadView(route) {
  const appRoot = document.getElementById('app-root');
  if (!appRoot) return;

  const renderViewFn = routes[route] || renderDashboard;

  if (route === 'login') {
    appRoot.innerHTML = '<div id="login-container"></div>';
    const container = document.getElementById('login-container');
    renderViewFn(container);
    return;
  }

  // Layout Autenticado: Sidebar + Header + Main Container
  let layoutContainer = document.getElementById('authenticated-layout');
  if (!layoutContainer) {
    appRoot.innerHTML = `
      <div id="authenticated-layout" class="min-h-screen flex bg-slate-50 text-slate-800 antialiased font-sans">
        <!-- Sidebar Navigation -->
        <aside id="sidebar-container" class="transition-all duration-200 z-30"></aside>

        <!-- Main Column -->
        <div class="flex-1 flex flex-col min-w-0 overflow-hidden">
          <!-- Header -->
          <header id="header-container" class="sticky top-0 z-20"></header>

          <!-- Main Scrollable Area -->
          <main class="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">
            <div id="main-view-container" class="max-w-7xl mx-auto pb-12"></div>
          </main>
        </div>
      </div>
    `;

    renderSidebar(document.getElementById('sidebar-container'));
    renderHeader(document.getElementById('header-container'));
  }

  const viewContainer = document.getElementById('main-view-container');
  if (viewContainer) {
    viewContainer.innerHTML = `
      <div class="flex items-center justify-center p-12 text-slate-400">
        <svg class="animate-spin h-6 w-6 mr-3 text-blue-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
        </svg>
        <span>Cargando módulo...</span>
      </div>
    `;
    renderViewFn(viewContainer);
  }
}

// Inicializar la aplicación cuando el DOM esté listo
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  initApp();
}

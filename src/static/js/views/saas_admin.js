/**
 * Panel Global de Administración y Comercialización SaaS (Multiempresa).
 * Control de Suscripciones, Métricas de Negocio (MRR, ARR, Churn), Facturación y Límites.
 */

import { api } from '../api.js';
import { showToast } from '../components/toast.js';
import { escapeHtml } from '../security.js';

export async function renderSaaSAdmin(container) {
  container.innerHTML = `
    <div class="space-y-6">
      <!-- Encabezado del Panel SaaS -->
      <div class="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
        <div>
          <div class="flex items-center gap-3">
            <span class="p-2.5 bg-blue-100 text-blue-800 rounded-lg">
              <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"/></svg>
            </span>
            <div>
              <h1 class="text-2xl font-bold text-slate-900 tracking-tight">Panel Global SaaS & Suscripciones</h1>
              <p class="text-sm text-slate-500">Administración de clientes multiempresa, control de planes comerciales, facturación recurrente y métricas.</p>
            </div>
          </div>
        </div>
        <div class="flex items-center gap-3">
          <button id="btn-refresh-saas" class="px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-sm font-medium transition-colors">
            Refrescar Datos
          </button>
        </div>
      </div>

      <!-- KPIs Financieros y Comerciales del SaaS -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4" id="saas-metrics-cards">
        <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <p class="text-xs font-semibold uppercase text-slate-500 tracking-wider">MRR (Ingreso Mensual)</p>
          <p id="kpi-mrr" class="text-2xl font-bold text-emerald-600 mt-2">$0.00 MXN</p>
          <p class="text-xs text-slate-500 mt-1">Ingresos recurrentes activos</p>
        </div>
        <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <p class="text-xs font-semibold uppercase text-slate-500 tracking-wider">ARR (Anual Proyectado)</p>
          <p id="kpi-arr" class="text-2xl font-bold text-blue-600 mt-2">$0.00 MXN</p>
          <p class="text-xs text-slate-500 mt-1">Base anualizada</p>
        </div>
        <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <p class="text-xs font-semibold uppercase text-slate-500 tracking-wider">Clientes Activos / Trial</p>
          <p id="kpi-clients" class="text-2xl font-bold text-slate-900 mt-2">0 / 0</p>
          <p class="text-xs text-emerald-600 font-medium mt-1">Organizaciones en plataforma</p>
        </div>
        <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <p class="text-xs font-semibold uppercase text-slate-500 tracking-wider">Tasa de Churn</p>
          <p id="kpi-churn" class="text-2xl font-bold text-purple-600 mt-2">0.0%</p>
          <p class="text-xs text-slate-500 mt-1">Cancelaciones sobre total</p>
        </div>
      </div>

      <!-- Cuadrícula de Planes Comerciales Configurables -->
      <div>
        <h2 class="text-lg font-bold text-slate-900 mb-3">Planes Comerciales Disponibles</h2>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6" id="saas-plans-grid">
          <div class="p-8 text-center text-slate-400 bg-white rounded-xl border border-slate-200">Cargando planes...</div>
        </div>
      </div>

      <!-- Tabla de Clientes y Suscripciones Multiempresa -->
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="p-5 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h2 class="text-lg font-bold text-slate-900">Directorio de Organizaciones Clientes</h2>
            <p class="text-xs text-slate-500 mt-0.5">Control de acceso, suspensión por morosidad, cotizaciones especiales y facturación.</p>
          </div>
          <div class="w-full sm:w-64">
            <input type="text" id="input-search-tenant" placeholder="Buscar por nombre, slug o correo..." class="w-full px-3 py-1.5 text-xs rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500">
          </div>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-left border-collapse text-sm">
            <thead>
              <tr class="bg-slate-50 text-slate-600 text-xs font-semibold uppercase border-b border-slate-200">
                <th class="py-3 px-4">Organización</th>
                <th class="py-3 px-4">Administrador</th>
                <th class="py-3 px-4">Plan Actual</th>
                <th class="py-3 px-4">Estado</th>
                <th class="py-3 px-4">Vencimiento / Trial</th>
                <th class="py-3 px-4">Usuarios</th>
                <th class="py-3 px-4 text-right">Acciones de Control</th>
              </tr>
            </thead>
            <tbody id="tenants-tbody" class="divide-y divide-slate-100">
              <tr><td colspan="7" class="py-8 text-center text-slate-400">Cargando organizaciones clientes...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  let cachedTenants = [];

  async function loadData() {
    try {
      // 1. Cargar Métricas Globales
      const metrics = await api.get('/saas/admin/metrics');
      document.getElementById('kpi-mrr').textContent = `$${Number(metrics.mrr_mxn).toLocaleString('es-MX', { minimumFractionDigits: 2 })} MXN`;
      document.getElementById('kpi-arr').textContent = `$${Number(metrics.arr_mxn).toLocaleString('es-MX', { minimumFractionDigits: 2 })} MXN`;
      document.getElementById('kpi-clients').textContent = `${metrics.active_tenants} / ${metrics.trialing_tenants} en trial`;
      document.getElementById('kpi-churn').textContent = `${metrics.churn_rate_percent}%`;

      // 2. Cargar Planes Comerciales
      const plans = await api.get('/saas/plans');
      renderPlans(plans);

      // 3. Cargar Clientes
      cachedTenants = await api.get('/saas/admin/tenants');
      renderTenants(cachedTenants);
    } catch (err) {
      showToast('Error cargando información del SaaS: ' + err.message, 'error');
    }
  }

  function renderPlans(plans) {
    const grid = document.getElementById('saas-plans-grid');
    if (!grid) return;
    grid.innerHTML = plans.map(p => {
      const isCustom = p.is_custom_pricing;
      const isPro = p.code === 'pro';
      return `
        <div class="bg-white rounded-xl border ${isPro ? 'border-blue-500 ring-2 ring-blue-500/20 shadow-md' : 'border-slate-200 shadow-sm'} p-6 flex flex-col justify-between relative overflow-hidden">
          ${isPro ? '<span class="absolute top-3 right-3 px-2 py-0.5 text-[10px] font-bold uppercase bg-blue-100 text-blue-700 rounded-full">Recomendado</span>' : ''}
          <div>
            <h3 class="text-xl font-bold text-slate-900">${escapeHtml(p.name)}</h3>
            <p class="text-xs text-slate-500 mt-1 min-h-[32px]">${escapeHtml(p.description || '')}</p>
            
            <div class="mt-4 mb-5">
              ${isCustom 
                ? '<span class="text-2xl font-bold text-slate-900">A la Medida</span><span class="text-xs text-slate-500 block">Cotización tras análisis comercial</span>'
                : `<span class="text-3xl font-extrabold text-slate-900">$${Number(p.monthly_price_mxn).toLocaleString('es-MX')}</span><span class="text-xs text-slate-500"> MXN / mes</span>
                   <span class="block text-[11px] text-emerald-600 font-medium mt-0.5">$${Number(p.annual_price_mxn).toLocaleString('es-MX')} MXN anual (-2 meses)</span>`
              }
            </div>

            <ul class="space-y-2.5 text-xs text-slate-600 border-t border-slate-100 pt-4">
              <li class="flex items-center gap-2">
                <svg class="w-4 h-4 text-emerald-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
                <span><strong>${p.max_users === -1 ? 'Ilimitados' : p.max_users}</strong> usuarios permitidos</span>
              </li>
              <li class="flex items-center gap-2">
                <svg class="w-4 h-4 text-emerald-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
                <span><strong>${p.max_meli_accounts === -1 ? 'Ilimitadas' : p.max_meli_accounts}</strong> cuentas de Mercado Libre</span>
              </li>
              <li class="flex items-center gap-2">
                <svg class="w-4 h-4 text-emerald-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
                <span><strong>${p.max_storage_mb >= 1024 ? Math.round(p.max_storage_mb / 1024) + ' GB' : p.max_storage_mb + ' MB'}</strong> almacenamiento</span>
              </li>
              <li class="flex items-center gap-2">
                <svg class="w-4 h-4 ${p.has_automation_engine ? 'text-emerald-500' : 'text-slate-300'} shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="${p.has_automation_engine ? 'M5 13l4 4L19 7' : 'M6 18L18 6M6 6l12 12'}"/></svg>
                <span class="${p.has_automation_engine ? 'text-slate-800 font-medium' : 'text-slate-400'}">Motor de Automatizaciones (ECA)</span>
              </li>
              <li class="flex items-center gap-2">
                <svg class="w-4 h-4 ${p.has_ai_assistant ? 'text-emerald-500' : 'text-slate-300'} shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="${p.has_ai_assistant ? 'M5 13l4 4L19 7' : 'M6 18L18 6M6 6l12 12'}"/></svg>
                <span class="${p.has_ai_assistant ? 'text-slate-800 font-medium' : 'text-slate-400'}">Asistente IA Comercial</span>
              </li>
            </ul>
          </div>
          <div class="mt-6 pt-4 border-t border-slate-100">
            <span class="inline-block w-full py-2 bg-slate-50 text-slate-600 rounded-lg text-center text-xs font-semibold">
              ${p.trial_days} días de prueba gratis
            </span>
          </div>
        </div>
      `;
    }).join('');
  }

  function renderTenants(tenants) {
    const tbody = document.getElementById('tenants-tbody');
    if (!tbody) return;
    if (tenants.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="py-8 text-center text-slate-400">No se encontraron clientes registrados.</td></tr>`;
      return;
    }
    tbody.innerHTML = tenants.map(t => {
      const isSuspended = t.status === 'suspended';
      const isTrial = t.status === 'trialing';
      const statusBadge = isSuspended
        ? '<span class="px-2.5 py-0.5 text-xs font-semibold bg-red-100 text-red-800 rounded-full border border-red-200">Suspendido</span>'
        : isTrial
        ? '<span class="px-2.5 py-0.5 text-xs font-semibold bg-amber-100 text-amber-800 rounded-full border border-amber-200">En Prueba</span>'
        : '<span class="px-2.5 py-0.5 text-xs font-semibold bg-emerald-100 text-emerald-800 rounded-full border border-emerald-200">Activo</span>';

      return `
        <tr class="hover:bg-slate-50/80 transition-colors">
          <td class="py-3 px-4">
            <span class="block font-semibold text-slate-900">${escapeHtml(t.tenant_name)}</span>
            <span class="block text-xs text-slate-400 font-mono">/${escapeHtml(t.tenant_slug)}</span>
          </td>
          <td class="py-3 px-4 text-xs text-slate-700">${escapeHtml(t.admin_email)}</td>
          <td class="py-3 px-4">
            <span class="px-2 py-0.5 text-xs font-semibold rounded bg-slate-100 text-slate-800 border border-slate-200">
              ${escapeHtml(t.plan_name)}
            </span>
          </td>
          <td class="py-3 px-4">${statusBadge}</td>
          <td class="py-3 px-4 text-xs text-slate-500">
            ${isTrial && t.trial_ends_at ? `Trial: ${new Date(t.trial_ends_at).toLocaleDateString()}` : new Date(t.current_period_end).toLocaleDateString()}
          </td>
          <td class="py-3 px-4 text-xs font-medium text-slate-700">${t.active_users}</td>
          <td class="py-3 px-4 text-right space-x-1.5">
            ${isSuspended
              ? `<button data-reactivate-id="${escapeHtml(t.tenant_id)}" class="btn-reactivate px-2.5 py-1 text-xs font-medium text-emerald-700 bg-emerald-50 hover:bg-emerald-100 rounded border border-emerald-200">Reactivar</button>`
              : `<button data-suspend-id="${escapeHtml(t.tenant_id)}" class="btn-suspend px-2.5 py-1 text-xs font-medium text-red-700 bg-red-50 hover:bg-red-100 rounded border border-red-200">Suspender</button>`
            }
            <button data-extend-id="${escapeHtml(t.tenant_id)}" class="btn-extend px-2.5 py-1 text-xs font-medium text-blue-700 bg-blue-50 hover:bg-blue-100 rounded border border-blue-200">+14 Días</button>
            <button data-invoice-id="${escapeHtml(t.tenant_id)}" class="btn-invoice px-2.5 py-1 text-xs font-medium text-purple-700 bg-purple-50 hover:bg-purple-100 rounded border border-purple-200">Facturar</button>
          </td>
        </tr>
      `;
    }).join('');

    // Eventos de botones
    tbody.querySelectorAll('.btn-suspend').forEach(btn => {
      btn.addEventListener('click', async () => {
        const id = btn.getAttribute('data-suspend-id');
        const reason = prompt('Ingrese el motivo de la suspensión administrativa:');
        if (!reason) return;
        try {
          await api.post(`/saas/admin/tenants/${id}/suspend`, { reason });
          showToast('Organización suspendida exitosamente.', 'info');
          loadData();
        } catch (err) {
          showToast('Error al suspender: ' + err.message, 'error');
        }
      });
    });

    tbody.querySelectorAll('.btn-reactivate').forEach(btn => {
      btn.addEventListener('click', async () => {
        const id = btn.getAttribute('data-reactivate-id');
        try {
          await api.post(`/saas/admin/tenants/${id}/reactivate`);
          showToast('Organización reactivada exitosamente.', 'success');
          loadData();
        } catch (err) {
          showToast('Error al reactivar: ' + err.message, 'error');
        }
      });
    });

    tbody.querySelectorAll('.btn-extend').forEach(btn => {
      btn.addEventListener('click', async () => {
        const id = btn.getAttribute('data-extend-id');
        try {
          await api.post(`/saas/admin/tenants/${id}/extend-trial`, { extra_days: 14 });
          showToast('Periodo de prueba extendido en 14 días.', 'success');
          loadData();
        } catch (err) {
          showToast('Error al extender prueba: ' + err.message, 'error');
        }
      });
    });

    tbody.querySelectorAll('.btn-invoice').forEach(btn => {
      btn.addEventListener('click', async () => {
        const id = btn.getAttribute('data-invoice-id');
        try {
          const res = await api.post(`/saas/admin/invoices/create?tenant_id=${id}`);
          showToast(`Factura SaaS emitida: ${res.invoice_number} por $${res.total_amount} MXN`, 'success');
        } catch (err) {
          showToast('Error al emitir factura: ' + err.message, 'error');
        }
      });
    });
  }

  document.getElementById('input-search-tenant')?.addEventListener('input', (e) => {
    const q = e.target.value.toLowerCase().trim();
    if (!q) {
      renderTenants(cachedTenants);
      return;
    }
    const filtered = cachedTenants.filter(t => 
      t.tenant_name.toLowerCase().includes(q) ||
      t.tenant_slug.toLowerCase().includes(q) ||
      t.admin_email.toLowerCase().includes(q)
    );
    renderTenants(filtered);
  });

  document.getElementById('btn-refresh-saas')?.addEventListener('click', loadData);

  loadData();
}

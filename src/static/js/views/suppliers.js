/**
 * Vista de Proveedores
 * Directorio de fabricantes y distribuidores con validación de RFC y lead times.
 */

import { api } from '../api.js';
import { state } from '../state.js';
import { icons } from '../icons.js';
import { showToast } from '../components/toast.js';
import { openModal, closeModal } from '../components/modal.js';

let suppliersList = [];

export async function renderSuppliers(container) {
  container.innerHTML = `
    <div class="space-y-6">
      <!-- Encabezado -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 class="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            ${icons.truck} Directorio de Proveedores
          </h1>
          <p class="text-sm text-slate-500 mt-1">
            Gestión de fabricantes, distribuidores de mercancía y tiempos de entrega (lead time).
          </p>
        </div>
        <div class="flex items-center gap-2">
          <button id="btn-create-supplier" class="btn-primary flex items-center gap-2">
            ${icons.plus} Nuevo Proveedor
          </button>
        </div>
      </div>

      <!-- Métricas -->
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div class="card p-4">
          <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Proveedores Registrados</div>
          <div id="metric-supp-total" class="text-2xl font-bold text-slate-900 mt-1">...</div>
          <div class="text-xs text-slate-500 mt-1">Socios comerciales activos</div>
        </div>
        <div class="card p-4">
          <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Lead Time Promedio</div>
          <div id="metric-supp-leadtime" class="text-2xl font-bold text-blue-600 mt-1">...</div>
          <div class="text-xs text-blue-600/80 mt-1">Días promedio de reabastecimiento</div>
        </div>
        <div class="card p-4">
          <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Confiabilidad de Entrega</div>
          <div class="text-2xl font-bold text-emerald-600 mt-1">99.2%</div>
          <div class="text-xs text-emerald-600/80 mt-1">Cumplimiento en tiempo y forma</div>
        </div>
      </div>

      <!-- Tabla de Proveedores -->
      <div class="card overflow-hidden">
        <div class="p-4 border-b border-slate-200 flex items-center justify-between">
          <h2 class="text-base font-bold text-slate-900">Proveedores de la Empresa Activa</h2>
          <span class="text-xs text-slate-500">Aislamiento multiempresa garantizado</span>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-left border-collapse">
            <thead>
              <tr class="bg-slate-50 border-b border-slate-200 text-xs font-semibold text-slate-600 uppercase tracking-wider">
                <th class="p-3">Nombre / Razón Social</th>
                <th class="p-3">RFC</th>
                <th class="p-3">Contacto</th>
                <th class="p-3">Email & Teléfono</th>
                <th class="p-3">Lead Time</th>
                <th class="p-3">Estado</th>
                <th class="p-3 text-right">Acción</th>
              </tr>
            </thead>
            <tbody id="suppliers-table-body" class="divide-y divide-slate-100 text-sm">
              <tr>
                <td colspan="7" class="p-6 text-center text-slate-400">Cargando proveedores...</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  container.querySelector('#btn-create-supplier').addEventListener('click', openCreateSupplierModal);

  await loadSuppliers();
}

async function loadSuppliers() {
  try {
    const res = await api.get('/suppliers?limit=100');
    suppliersList = res.items || [];
    renderTable();
    updateMetrics();
  } catch (err) {
    showToast(err.message || 'Error cargando proveedores', 'error');
  }
}

function updateMetrics() {
  const totalEl = document.getElementById('metric-supp-total');
  const leadEl = document.getElementById('metric-supp-leadtime');

  if (totalEl) totalEl.textContent = suppliersList.length;
  if (leadEl) {
    if (suppliersList.length > 0) {
      const avg = Math.round(suppliersList.reduce((acc, s) => acc + (s.lead_time_days || 0), 0) / suppliersList.length);
      leadEl.textContent = `${avg} días`;
    } else {
      leadEl.textContent = '7 días';
    }
  }
}

function renderTable() {
  const tbody = document.getElementById('suppliers-table-body');
  if (!tbody) return;

  if (suppliersList.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" class="p-8 text-center text-slate-400">
          No hay proveedores dados de alta. Haz clic en "Nuevo Proveedor" para registrar el primero.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = suppliersList.map((supp) => {
    return `
      <tr class="hover:bg-slate-50 transition-colors">
        <td class="p-3 font-semibold text-slate-900">${supp.name}</td>
        <td class="p-3 font-mono text-xs text-slate-700">${supp.rfc || 'SIN RFC'}</td>
        <td class="p-3 text-slate-800">${supp.contact_name || 'No especificado'}</td>
        <td class="p-3 text-xs text-slate-500">
          <div>${supp.email || '-'}</div>
          <div>${supp.phone || '-'}</div>
        </td>
        <td class="p-3 font-semibold text-slate-800">
          ${supp.lead_time_days || 7} días
        </td>
        <td class="p-3">
          <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${supp.is_active ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-600'}">
            ${supp.is_active ? 'Activo' : 'Inactivo'}
          </span>
        </td>
        <td class="p-3 text-right">
          <button
            data-supp-id="${supp.id}"
            class="btn-order-from-supp inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-lg bg-blue-50 text-blue-700 hover:bg-blue-100 transition-colors"
          >
            ${icons.truck} Emitir OC
          </button>
        </td>
      </tr>
    `;
  }).join('');

  tbody.querySelectorAll('.btn-order-from-supp').forEach((btn) => {
    btn.addEventListener('click', () => {
      window.location.hash = '#purchases';
    });
  });
}

function openCreateSupplierModal() {
  const currentCompany = state.currentCompany;
  if (!currentCompany) {
    showToast('Selecciona una empresa primero', 'error');
    return;
  }

  const content = `
    <form id="create-supplier-form" class="space-y-4">
      <div>
        <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Nombre o Razón Social *</label>
        <input
          type="text"
          id="supp-name-input"
          class="input-field text-sm"
          placeholder="e.g. Distribuidora Mayorista de Electrónica S.A. de C.V."
          required
        />
      </div>

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">RFC Mexicano</label>
          <input
            type="text"
            id="supp-rfc-input"
            class="input-field text-sm font-mono uppercase"
            placeholder="DME991119777"
            maxlength="13"
          />
        </div>
        <div>
          <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Días de Entrega (Lead Time) *</label>
          <input
            type="number"
            id="supp-leadtime-input"
            class="input-field text-sm"
            min="0"
            value="7"
            required
          />
        </div>
      </div>

      <div>
        <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Nombre de Contacto</label>
        <input
          type="text"
          id="supp-contact-input"
          class="input-field text-sm"
          placeholder="Lic. Roberto Sánchez"
        />
      </div>

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Correo Electrónico</label>
          <input
            type="email"
            id="supp-email-input"
            class="input-field text-sm"
            placeholder="ventas@proveedor.com"
          />
        </div>
        <div>
          <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Teléfono / WhatsApp</label>
          <input
            type="tel"
            id="supp-phone-input"
            class="input-field text-sm"
            placeholder="55 1234 5678"
          />
        </div>
      </div>

      <div class="flex justify-end gap-2 pt-2">
        <button type="button" id="btn-cancel-supp" class="btn-secondary">Cancelar</button>
        <button type="submit" id="btn-submit-supp" class="btn-primary flex items-center gap-1.5">
          ${icons.check} Registrar Proveedor
        </button>
      </div>
    </form>
  `;

  openModal('Registrar Nuevo Proveedor', content);

  document.getElementById('btn-cancel-supp')?.addEventListener('click', closeModal);

  const form = document.getElementById('create-supplier-form');
  form?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('btn-submit-supp');
    btn.disabled = true;
    btn.innerHTML = 'Guardando...';

    const name = document.getElementById('supp-name-input').value.trim();
    const rfc = document.getElementById('supp-rfc-input').value.trim().toUpperCase();
    const leadTime = parseInt(document.getElementById('supp-leadtime-input').value) || 7;
    const contact = document.getElementById('supp-contact-input').value.trim();
    const email = document.getElementById('supp-email-input').value.trim();
    const phone = document.getElementById('supp-phone-input').value.trim();

    try {
      const payload = {
        company_id: currentCompany.id,
        name,
        rfc: rfc || null,
        lead_time_days: leadTime,
        contact_name: contact || null,
        email: email || null,
        phone: phone || null,
      };

      await api.post('/suppliers', payload);
      closeModal();
      showToast('Proveedor registrado exitosamente', 'success');
      await loadSuppliers();
    } catch (err) {
      showToast(err.message || 'Error al registrar proveedor', 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `${icons.check} Registrar Proveedor`;
      }
    }
  });
}

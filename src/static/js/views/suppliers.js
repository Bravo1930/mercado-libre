/**
 * Vista de Proveedores
 * Directorio de fabricantes y distribuidores con validación de RFC, lead times,
 * condiciones crediticias, catálogo suministrado y evaluaciones de desempeño.
 */

import { api } from '../api.js';
import { state } from '../state.js';
import { icons } from '../icons.js';
import { showToast } from '../components/toast.js';
import { openModal, closeModal } from '../components/modal.js';

let suppliersList = [];
let activeTab = 'suppliers'; // 'suppliers' | 'evaluations'

export async function renderSuppliers(container) {
  container.innerHTML = `
    <div class="space-y-6">
      <!-- Encabezado -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 class="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            ${icons.truck} Abastecimiento · Directorio de Proveedores
          </h1>
          <p class="text-sm text-slate-500 mt-1">
            Gestión integral de socios comerciales, catálogo de suministro, evaluación de desempeño y condiciones bancarias.
          </p>
        </div>
        <div class="flex items-center gap-2">
          <button id="btn-create-supplier" class="btn-primary flex items-center gap-2">
            ${icons.plus} Nuevo Proveedor
          </button>
        </div>
      </div>

      <!-- Métricas -->
      <div class="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <div class="card p-4">
          <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Proveedores Registrados</div>
          <div id="metric-supp-total" class="text-2xl font-bold text-slate-900 mt-1">...</div>
          <div class="text-xs text-slate-500 mt-1">Socios comerciales activos</div>
        </div>
        <div class="card p-4">
          <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Lead Time Promedio</div>
          <div id="metric-supp-leadtime" class="text-2xl font-bold text-blue-600 mt-1">...</div>
          <div class="text-xs text-blue-600/80 mt-1">Días de entrega a almacén</div>
        </div>
        <div class="card p-4">
          <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Puntualidad Global</div>
          <div id="metric-supp-ontime" class="text-2xl font-bold text-emerald-600 mt-1">98.5%</div>
          <div class="text-xs text-emerald-600/80 mt-1">On-Time Delivery Rate</div>
        </div>
        <div class="card p-4">
          <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Evaluación Promedio</div>
          <div id="metric-supp-rating" class="text-2xl font-bold text-amber-500 mt-1">4.8 / 5.0 ★</div>
          <div class="text-xs text-amber-600/80 mt-1">Calidad, precio y servicio</div>
        </div>
      </div>

      <!-- Tabla de Proveedores -->
      <div class="card overflow-hidden">
        <div class="p-4 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h2 class="text-base font-bold text-slate-900">Directorio de Proveedores y Desempeño</h2>
            <p class="text-xs text-slate-500">Aislamiento multiempresa con control estricto de RFC SAT y plazos de crédito</p>
          </div>
          <div class="flex items-center gap-2">
            <input
              type="text"
              id="search-supplier-input"
              class="input-field text-xs py-1.5 px-3 w-64"
              placeholder="Buscar por nombre o RFC..."
            />
          </div>
        </div>

        <div class="overflow-x-auto">
          <table class="w-full text-left border-collapse">
            <thead>
              <tr class="bg-slate-50 border-b border-slate-200 text-xs font-semibold text-slate-600 uppercase tracking-wider">
                <th class="p-3">Código / Proveedor</th>
                <th class="p-3">RFC</th>
                <th class="p-3">Contacto & Teléfono</th>
                <th class="p-3">Lead Time</th>
                <th class="p-3">Plazo Crédito</th>
                <th class="p-3">Evaluación</th>
                <th class="p-3">Estado</th>
                <th class="p-3 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody id="suppliers-table-body" class="divide-y divide-slate-100 text-sm">
              <tr>
                <td colspan="8" class="p-6 text-center text-slate-400">Cargando proveedores...</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  container.querySelector('#btn-create-supplier').addEventListener('click', openCreateSupplierModal);
  container.querySelector('#search-supplier-input')?.addEventListener('input', (e) => {
    const q = e.target.value.toLowerCase().trim();
    renderTable(q);
  });

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
  const ratingEl = document.getElementById('metric-supp-rating');
  const onTimeEl = document.getElementById('metric-supp-ontime');

  if (totalEl) totalEl.textContent = suppliersList.length;
  if (leadEl) {
    if (suppliersList.length > 0) {
      const avg = Math.round(suppliersList.reduce((acc, s) => acc + (s.lead_time_days || 0), 0) / suppliersList.length);
      leadEl.textContent = `${avg} días`;
    } else {
      leadEl.textContent = '7 días';
    }
  }
  if (ratingEl && suppliersList.length > 0) {
    const avgScore = (suppliersList.reduce((acc, s) => acc + (s.rating_score || 5.0), 0) / suppliersList.length).toFixed(1);
    ratingEl.textContent = `${avgScore} / 5.0 ★`;
  }
  if (onTimeEl && suppliersList.length > 0) {
    const avgOnTime = (suppliersList.reduce((acc, s) => acc + (s.on_time_delivery_rate || 99.0), 0) / suppliersList.length).toFixed(1);
    onTimeEl.textContent = `${avgOnTime}%`;
  }
}

function renderTable(filterQuery = '') {
  const tbody = document.getElementById('suppliers-table-body');
  if (!tbody) return;

  let filtered = suppliersList;
  if (filterQuery) {
    filtered = suppliersList.filter(
      (s) =>
        (s.name && s.name.toLowerCase().includes(filterQuery)) ||
        (s.rfc && s.rfc.toLowerCase().includes(filterQuery)) ||
        (s.code && s.code.toLowerCase().includes(filterQuery))
    );
  }

  if (filtered.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" class="p-8 text-center text-slate-400">
          No se encontraron proveedores que coincidan con la búsqueda.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = filtered.map((supp) => {
    const rating = supp.rating_score ? Number(supp.rating_score).toFixed(1) : '5.0';
    return `
      <tr class="hover:bg-slate-50 transition-colors">
        <td class="p-3">
          <div class="font-semibold text-slate-900">${supp.name}</div>
          <div class="font-mono text-xs text-slate-500">${supp.code || 'PROV'}</div>
        </td>
        <td class="p-3 font-mono text-xs text-slate-700">${supp.rfc || 'SIN RFC'}</td>
        <td class="p-3 text-xs text-slate-600">
          <div class="font-medium text-slate-800">${supp.contact_name || 'No especificado'}</div>
          <div>${supp.email || '-'} · ${supp.phone || '-'}</div>
        </td>
        <td class="p-3 font-semibold text-slate-800">
          ${supp.lead_time_days || 7} días
        </td>
        <td class="p-3 text-xs text-slate-700">
          <div>${supp.payment_terms_days || 30} días</div>
          ${supp.credit_limit ? `<div class="text-slate-400">$${Number(supp.credit_limit).toLocaleString('es-MX')}</div>` : ''}
        </td>
        <td class="p-3">
          <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-amber-50 text-amber-700">
            ★ ${rating}
          </span>
        </td>
        <td class="p-3">
          <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${supp.is_active ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-600'}">
            ${supp.is_active ? 'Activo' : 'Inactivo'}
          </span>
        </td>
        <td class="p-3 text-right space-x-1">
          <button
            data-supp-eval="${supp.id}"
            class="btn-supp-eval inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-lg bg-amber-50 text-amber-800 hover:bg-amber-100 transition-colors"
            title="Evaluar desempeño"
          >
            ★ Evaluar
          </button>
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

  tbody.querySelectorAll('.btn-supp-eval').forEach((btn) => {
    btn.addEventListener('click', () => {
      const suppId = btn.dataset.suppEval;
      const supp = suppliersList.find((s) => s.id === suppId);
      if (supp) openEvaluateSupplierModal(supp);
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

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Días de Crédito</label>
          <input
            type="number"
            id="supp-credit-days-input"
            class="input-field text-sm"
            min="0"
            value="30"
          />
        </div>
        <div>
          <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Límite de Crédito (MXN)</label>
          <input
            type="number"
            id="supp-credit-limit-input"
            class="input-field text-sm"
            min="0"
            step="1000"
            placeholder="150000"
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

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Banco Receptor</label>
          <input
            type="text"
            id="supp-bank-name"
            class="input-field text-sm"
            placeholder="BBVA México / Banorte"
          />
        </div>
        <div>
          <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">CLABE Interbancaria (18 dígitos)</label>
          <input
            type="text"
            id="supp-bank-clabe"
            class="input-field text-sm font-mono"
            maxlength="18"
            placeholder="012180001234567890"
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
    const creditDays = parseInt(document.getElementById('supp-credit-days-input').value) || 30;
    const creditLimit = parseFloat(document.getElementById('supp-credit-limit-input').value) || null;
    const contact = document.getElementById('supp-contact-input').value.trim();
    const email = document.getElementById('supp-email-input').value.trim();
    const phone = document.getElementById('supp-phone-input').value.trim();
    const bankName = document.getElementById('supp-bank-name').value.trim();
    const bankClabe = document.getElementById('supp-bank-clabe').value.trim();

    try {
      const payload = {
        company_id: currentCompany.id,
        name,
        rfc: rfc || null,
        lead_time_days: leadTime,
        payment_terms_days: creditDays,
        credit_limit: creditLimit,
        contact_name: contact || null,
        email: email || null,
        phone: phone || null,
        bank_name: bankName || null,
        bank_clabe: bankClabe || null,
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

function openEvaluateSupplierModal(supplier) {
  const content = `
    <form id="eval-supplier-form" class="space-y-4">
      <div class="bg-slate-50 p-3 rounded-lg border border-slate-200 text-xs">
        <span class="text-slate-500">Proveedor evaluado:</span>
        <div class="font-bold text-slate-900 text-sm">${supplier.name}</div>
        <div class="text-slate-500 font-mono">${supplier.rfc || 'Sin RFC'} · Lead Time pactado: ${supplier.lead_time_days} días</div>
      </div>

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Puntualidad de Entrega (1 a 5)</label>
          <select id="eval-ontime" class="input-field text-sm">
            <option value="5">5 - Excelente (En fecha o anticipado)</option>
            <option value="4">4 - Bueno (Máx. 1 día de desfase)</option>
            <option value="3">3 - Regular (2-3 días de retraso)</option>
            <option value="2">2 - Malo (Retrasos frecuentes)</option>
            <option value="1">1 - Crítico (Entregas fuera de plazo)</option>
          </select>
        </div>
        <div>
          <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Calidad de Mercancía (1 a 5)</label>
          <select id="eval-quality" class="input-field text-sm">
            <option value="5">5 - Sin defectos / Excelente empaque</option>
            <option value="4">4 - Defectos menores (< 1%)</option>
            <option value="3">3 - Defectos tolerables (1-3%)</option>
            <option value="2">2 - Daños frecuentes (3-5%)</option>
            <option value="1">1 - Alto rechazo en recepción (> 5%)</option>
          </select>
        </div>
      </div>

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Competitividad de Precio (1 a 5)</label>
          <select id="eval-pricing" class="input-field text-sm">
            <option value="5">5 - Muy competitivo / Descuentos por volumen</option>
            <option value="4">4 - Precio acorde al mercado</option>
            <option value="3">3 - Precio regular</option>
            <option value="2">2 - Precio elevado sin justificación</option>
            <option value="1">1 - Muy costoso</option>
          </select>
        </div>
        <div>
          <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Servicio y Soporte (1 a 5)</label>
          <select id="eval-service" class="input-field text-sm">
            <option value="5">5 - Respuesta inmediata y proactiva</option>
            <option value="4">4 - Buena atención comercial</option>
            <option value="3">3 - Atención regular</option>
            <option value="2">2 - Lenta resolución de incidencias</option>
            <option value="1">1 - Sin soporte ni respuesta</option>
          </select>
        </div>
      </div>

      <div>
        <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Observaciones / Auditoría de Calidad</label>
        <textarea id="eval-notes" class="input-field text-xs" rows="2" placeholder="Detalle de incidencias, entregas o acuerdos comerciales pactados..."></textarea>
      </div>

      <div class="flex justify-end gap-2 pt-2">
        <button type="button" id="btn-cancel-eval" class="btn-secondary">Cancelar</button>
        <button type="submit" id="btn-submit-eval" class="btn-primary flex items-center gap-1.5">
          ${icons.check} Registrar Evaluación
        </button>
      </div>
    </form>
  `;

  openModal(`Evaluar Desempeño · ${supplier.name}`, content);
  document.getElementById('btn-cancel-eval')?.addEventListener('click', closeModal);

  const form = document.getElementById('eval-supplier-form');
  form?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const ontime = parseFloat(document.getElementById('eval-ontime').value);
    const quality = parseFloat(document.getElementById('eval-quality').value);
    const pricing = parseFloat(document.getElementById('eval-pricing').value);
    const service = parseFloat(document.getElementById('eval-service').value);
    const notes = document.getElementById('eval-notes').value.trim();

    try {
      await api.post(`/suppliers/${supplier.id}/evaluations`, {
        supplier_id: supplier.id,
        on_time_delivery_score: ontime,
        quality_score: quality,
        pricing_score: pricing,
        service_score: service,
        notes: notes || null,
      });
      closeModal();
      showToast('Evaluación registrada y score recalculado exitosamente', 'success');
      await loadSuppliers();
    } catch (err) {
      showToast(err.message || 'Error al guardar evaluación', 'error');
    }
  });
}

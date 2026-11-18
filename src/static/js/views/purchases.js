/**
 * Vista de Compras y Abastecimiento
 * Gestión de Órdenes de Compra a Proveedores con cálculo automático y seguimiento de recepción.
 */

import { api } from '../api.js';
import { state } from '../state.js';
import { icons } from '../icons.js';
import { showToast } from '../components/toast.js';
import { openModal, closeModal } from '../components/modal.js';

let purchaseOrders = [];
let suppliersList = [];
let productsList = [];

export async function renderPurchases(container) {
  container.innerHTML = `
    <div class="space-y-6">
      <!-- Encabezado -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 class="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            ${icons.truck} Órdenes de Compra y Abastecimiento
          </h1>
          <p class="text-sm text-slate-500 mt-1">
            Gestión de compras a proveedores de inventario para almacenes locales y envíos a Mercado Envíos FULL.
          </p>
        </div>
        <div class="flex items-center gap-2">
          <button id="btn-create-po" class="btn-primary flex items-center gap-2">
            ${icons.plus} Nueva Orden de Compra
          </button>
        </div>
      </div>

      <!-- Tarjetas de Métricas -->
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div class="card p-4">
          <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Órdenes Emitidas</div>
          <div id="metric-po-total" class="text-2xl font-bold text-slate-900 mt-1">...</div>
          <div class="text-xs text-slate-500 mt-1">Abastecimiento en curso</div>
        </div>
        <div class="card p-4">
          <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Inversión Comprometida</div>
          <div id="metric-po-amount" class="text-2xl font-bold text-blue-600 mt-1">...</div>
          <div class="text-xs text-blue-600/80 mt-1">Total mercancía adquirida</div>
        </div>
        <div class="card p-4">
          <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Estatus Promedio</div>
          <div class="text-2xl font-bold text-emerald-600 mt-1">Abastecido</div>
          <div class="text-xs text-emerald-600/80 mt-1">Cadena de suministro estable</div>
        </div>
      </div>

      <!-- Tabla de Órdenes de Compra -->
      <div class="card overflow-hidden">
        <div class="p-4 border-b border-slate-200 flex items-center justify-between">
          <h2 class="text-base font-bold text-slate-900">Historial de Órdenes de Compra</h2>
          <span class="text-xs text-slate-500">Registros persistentes en base de datos</span>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-left border-collapse">
            <thead>
              <tr class="bg-slate-50 border-b border-slate-200 text-xs font-semibold text-slate-600 uppercase tracking-wider">
                <th class="p-3">No. Orden</th>
                <th class="p-3">Proveedor ID</th>
                <th class="p-3">Estado</th>
                <th class="p-3">Monto Total</th>
                <th class="p-3">Fecha de Creación</th>
                <th class="p-3 text-right">Detalle</th>
              </tr>
            </thead>
            <tbody id="po-table-body" class="divide-y divide-slate-100 text-sm">
              <tr>
                <td colspan="6" class="p-6 text-center text-slate-400">Cargando órdenes de compra...</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  container.querySelector('#btn-create-po').addEventListener('click', openCreatePoModal);

  await loadSuppliersAndProducts();
  await loadPurchaseOrders();
}

async function loadSuppliersAndProducts() {
  try {
    const [suppRes, prodRes] = await Promise.all([
      api.get('/suppliers?limit=100'),
      api.get('/products?limit=100'),
    ]);
    suppliersList = suppRes.items || [];
    productsList = prodRes.items || [];
  } catch (err) {
    console.error('Error cargando proveedores o productos', err);
  }
}

async function loadPurchaseOrders() {
  try {
    const res = await api.get('/suppliers/purchase-orders?limit=50');
    purchaseOrders = res.items || [];
    renderTable();
    updateMetrics();
  } catch (err) {
    showToast('Error cargando órdenes de compra', 'error');
  }
}

function updateMetrics() {
  const totalEl = document.getElementById('metric-po-total');
  const amountEl = document.getElementById('metric-po-amount');

  if (totalEl) totalEl.textContent = purchaseOrders.length;
  if (amountEl) {
    const sum = purchaseOrders.reduce((acc, po) => acc + (parseFloat(po.total_amount) || 0), 0);
    amountEl.textContent = `$${sum.toLocaleString('es-MX', { minimumFractionDigits: 2 })} MXN`;
  }
}

function renderTable() {
  const tbody = document.getElementById('po-table-body');
  if (!tbody) return;

  if (purchaseOrders.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" class="p-8 text-center text-slate-400">
          No hay órdenes de compra registradas. Haz clic en "Nueva Orden de Compra" para generar la primera.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = purchaseOrders.map((po) => {
    let statusBadge = '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-blue-700">Emitida</span>';
    if (po.status === 'received') {
      statusBadge = '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700">Recibida</span>';
    } else if (po.status === 'draft') {
      statusBadge = '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700">Borrador</span>';
    }

    return `
      <tr class="hover:bg-slate-50 transition-colors">
        <td class="p-3 font-mono font-bold text-slate-900">${po.po_number}</td>
        <td class="p-3 font-mono text-xs text-slate-500">${po.supplier_id ? po.supplier_id.slice(0, 8) + '...' : 'Proveedor'}</td>
        <td class="p-3">${statusBadge}</td>
        <td class="p-3 font-mono font-bold text-slate-900">$${(parseFloat(po.total_amount) || 0).toFixed(2)} MXN</td>
        <td class="p-3 text-xs text-slate-500">${new Date(po.created_at).toLocaleDateString('es-MX')}</td>
        <td class="p-3 text-right">
          <button
            data-po-id="${po.id}"
            class="btn-view-po-details text-xs font-medium text-blue-600 hover:text-blue-800"
          >
            Ver Detalle
          </button>
        </td>
      </tr>
    `;
  }).join('');

  tbody.querySelectorAll('.btn-view-po-details').forEach((btn) => {
    btn.addEventListener('click', () => {
      const id = btn.dataset.poId;
      const po = purchaseOrders.find((p) => p.id === id);
      if (po) {
        openModal(
          `Orden de Compra · ${po.po_number}`,
          `
          <div class="space-y-4">
            <div class="grid grid-cols-2 gap-4 bg-slate-50 p-4 rounded-xl border border-slate-200 text-xs">
              <div>
                <span class="text-slate-500">Número de Orden:</span>
                <div class="font-mono font-bold text-slate-900 text-sm">${po.po_number}</div>
              </div>
              <div>
                <span class="text-slate-500">Monto Total:</span>
                <div class="font-mono font-bold text-emerald-700 text-sm">$${(parseFloat(po.total_amount) || 0).toFixed(2)} MXN</div>
              </div>
              <div>
                <span class="text-slate-500">Estado:</span>
                <div class="font-bold text-slate-800 uppercase">${po.status}</div>
              </div>
              <div>
                <span class="text-slate-500">Fecha de Creación:</span>
                <div class="text-slate-800">${new Date(po.created_at).toLocaleString('es-MX')}</div>
              </div>
            </div>
            ${po.notes ? `<div class="text-xs text-slate-600"><strong>Notas:</strong> ${po.notes}</div>` : ''}
          </div>
        `
        );
      }
    });
  });
}

function openCreatePoModal() {
  const currentCompany = state.currentCompany;
  if (!currentCompany) {
    showToast('Selecciona una empresa primero', 'error');
    return;
  }

  if (suppliersList.length === 0) {
    showToast('Debes registrar al menos un proveedor en el módulo de Proveedores antes de emitir una orden de compra.', 'warning');
    return;
  }

  const supplierOptions = suppliersList
    .map((s) => `<option value="${s.id}">${s.name} (RFC: ${s.rfc || 'S/N'})</option>`)
    .join('');

  // Collect available variants or placeholder variant
  const content = `
    <form id="create-po-form" class="space-y-4">
      <div>
        <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Proveedor *</label>
        <select id="po-supplier-select" class="input-field text-sm" required>
          ${supplierOptions}
        </select>
      </div>

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Folio Orden de Compra *</label>
          <input
            type="text"
            id="po-number-input"
            class="input-field text-sm font-mono"
            value="OC-${new Date().getFullYear()}-${Math.floor(1000 + Math.random() * 9000)}"
            required
          />
        </div>
        <div>
          <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Fecha de Entrega Esperada</label>
          <input
            type="date"
            id="po-expected-date"
            class="input-field text-sm"
          />
        </div>
      </div>

      <!-- Partidas de Compra -->
      <div class="border border-slate-200 rounded-xl p-3 bg-slate-50 space-y-3">
        <div class="flex items-center justify-between">
          <span class="text-xs font-bold text-slate-700 uppercase">Partida de Mercancía</span>
          <span class="text-xs text-slate-400">ID de Variante Requerido</span>
        </div>

        <div>
          <label class="block text-xs text-slate-600 mb-1">UUID de Variante de Producto *</label>
          <input
            type="text"
            id="po-item-variant-id"
            class="input-field text-xs font-mono"
            placeholder="00000000-0000-0000-0000-000000000000"
            value="a0000000-0000-0000-0000-000000000001"
            required
          />
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-xs text-slate-600 mb-1">Cantidad a Solicitar *</label>
            <input
              type="number"
              id="po-item-qty"
              class="input-field text-sm"
              min="1"
              value="50"
              required
            />
          </div>
          <div>
            <label class="block text-xs text-slate-600 mb-1">Costo Unitario (MXN) *</label>
            <input
              type="number"
              id="po-item-cost"
              class="input-field text-sm"
              min="0.01"
              step="0.50"
              value="150.00"
              required
            />
          </div>
        </div>

        <div class="flex justify-between items-center pt-2 border-t border-slate-200 text-xs">
          <span class="text-slate-600 font-semibold">Subtotal Calculado:</span>
          <span id="po-calculated-total" class="font-mono font-bold text-slate-900">$7,500.00 MXN</span>
        </div>
      </div>

      <div>
        <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Notas / Condiciones Comerciales</label>
        <textarea id="po-notes" class="input-field text-xs" rows="2" placeholder="Condiciones de pago, entrega en andén 3, etc."></textarea>
      </div>

      <div class="flex justify-end gap-2 pt-2">
        <button type="button" id="btn-cancel-po" class="btn-secondary">Cancelar</button>
        <button type="submit" id="btn-submit-po" class="btn-primary flex items-center gap-1.5">
          ${icons.check} Emitir Orden de Compra
        </button>
      </div>
    </form>
  `;

  openModal('Nueva Orden de Compra', content);

  document.getElementById('btn-cancel-po')?.addEventListener('click', closeModal);

  const qtyInput = document.getElementById('po-item-qty');
  const costInput = document.getElementById('po-item-cost');
  const totalSpan = document.getElementById('po-calculated-total');

  function updateTotal() {
    const qty = parseInt(qtyInput?.value) || 0;
    const cost = parseFloat(costInput?.value) || 0;
    const total = qty * cost;
    if (totalSpan) totalSpan.textContent = `$${total.toLocaleString('es-MX', { minimumFractionDigits: 2 })} MXN`;
  }

  qtyInput?.addEventListener('input', updateTotal);
  costInput?.addEventListener('input', updateTotal);

  const form = document.getElementById('create-po-form');
  form?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('btn-submit-po');
    btn.disabled = true;
    btn.innerHTML = 'Emitiendo...';

    const supplierId = document.getElementById('po-supplier-select').value;
    const poNumber = document.getElementById('po-number-input').value.trim();
    const expDateVal = document.getElementById('po-expected-date').value;
    const variantId = document.getElementById('po-item-variant-id').value.trim();
    const qty = parseInt(document.getElementById('po-item-qty').value);
    const cost = parseFloat(document.getElementById('po-item-cost').value);
    const notes = document.getElementById('po-notes').value.trim();

    try {
      const payload = {
        company_id: currentCompany.id,
        supplier_id: supplierId,
        po_number: poNumber,
        expected_delivery_date: expDateVal ? new Date(expDateVal).toISOString() : null,
        notes: notes || null,
        items: [
          {
            variant_id: variantId,
            quantity_ordered: qty,
            unit_cost: cost,
          },
        ],
      };

      await api.post('/suppliers/purchase-orders', payload);
      closeModal();
      showToast('Orden de compra emitida y registrada exitosamente', 'success');
      await loadPurchaseOrders();
    } catch (err) {
      showToast(err.message || 'Error al emitir orden de compra', 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `${icons.check} Emitir Orden de Compra`;
      }
    }
  });
}

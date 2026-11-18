/**
 * Vista Integral de Abastecimiento y Compras
 * Gestión de Órdenes de Compra (PO), Autorizaciones estrictas,
 * Recepciones parciales auditables en Kardex, Facturas SAT (CFDI 4.0),
 * Prorrateo de Landed Cost y Motor Inteligente de Reposición.
 */

import { api } from '../api.js';
import { state } from '../state.js';
import { icons } from '../icons.js';
import { showToast } from '../components/toast.js';
import { openModal, closeModal } from '../components/modal.js';

let purchaseOrders = [];
let goodsReceipts = [];
let replenishmentReport = null;
let suppliersList = [];
let warehousesList = [];
let currentTab = 'orders'; // 'orders' | 'receipts' | 'replenishment' | 'landed'

export async function renderPurchases(container) {
  container.innerHTML = `
    <div class="space-y-6">
      <!-- Encabezado Principal -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 class="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            ${icons.truck} Centro de Abastecimiento y Compras
          </h1>
          <p class="text-sm text-slate-500 mt-1">
            Control de órdenes de compra, recepciones parciales en almacén, prorrateo de costos landed y cálculo de reposición.
          </p>
        </div>
        <div class="flex items-center gap-2">
          <button id="btn-create-po" class="btn-primary flex items-center gap-2">
            ${icons.plus} Nueva Orden de Compra
          </button>
        </div>
      </div>

      <!-- Tarjetas de Métricas Ejecutivas -->
      <div class="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <div class="card p-4">
          <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Órdenes de Compra</div>
          <div id="metric-po-total" class="text-2xl font-bold text-slate-900 mt-1">...</div>
          <div class="text-xs text-slate-500 mt-1">Total emitidas y en curso</div>
        </div>
        <div class="card p-4">
          <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Inversión Comprometida</div>
          <div id="metric-po-amount" class="text-2xl font-bold text-blue-600 mt-1">...</div>
          <div class="text-xs text-blue-600/80 mt-1">Mercancía + fletes asociados</div>
        </div>
        <div class="card p-4">
          <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Alertas de Reposición</div>
          <div id="metric-rep-alerts" class="text-2xl font-bold text-rose-600 mt-1">...</div>
          <div class="text-xs text-rose-600/80 mt-1">SKUs agotados o en reorden</div>
        </div>
        <div class="card p-4">
          <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Inversión Sugerida</div>
          <div id="metric-rep-investment" class="text-2xl font-bold text-emerald-600 mt-1">...</div>
          <div class="text-xs text-emerald-600/80 mt-1">Para cobertura de 30 días</div>
        </div>
      </div>

      <!-- Navegación por Pestañas -->
      <div class="border-b border-slate-200">
        <nav class="flex space-x-6" aria-label="Tabs">
          <button id="tab-orders" class="tab-btn pb-3 text-sm font-semibold border-b-2 border-blue-600 text-blue-600 flex items-center gap-2">
            ${icons.truck} Órdenes de Compra
          </button>
          <button id="tab-receipts" class="tab-btn pb-3 text-sm font-semibold border-b-2 border-transparent text-slate-500 hover:text-slate-800 flex items-center gap-2">
            ${icons.package} Recepciones de Mercancía
          </button>
          <button id="tab-replenishment" class="tab-btn pb-3 text-sm font-semibold border-b-2 border-transparent text-slate-500 hover:text-slate-800 flex items-center gap-2">
            ${icons.activity} Motor de Reposición Inteligente
          </button>
        </nav>
      </div>

      <!-- Contenedor Dinámico de Pestañas -->
      <div id="tab-content" class="space-y-4">
        <!-- Renderizado dinámico vía JS -->
      </div>
    </div>
  `;

  // Event Listeners Pestañas
  container.querySelector('#tab-orders').addEventListener('click', () => switchTab('orders'));
  container.querySelector('#tab-receipts').addEventListener('click', () => switchTab('receipts'));
  container.querySelector('#tab-replenishment').addEventListener('click', () => switchTab('replenishment'));
  container.querySelector('#btn-create-po').addEventListener('click', openCreatePoModal);

  await loadInitialData();
  switchTab('orders');
}

async function loadInitialData() {
  try {
    const [suppRes, whRes, poRes, recRes] = await Promise.all([
      api.get('/suppliers?limit=100'),
      api.get('/warehouses'),
      api.get('/suppliers/purchase-orders?limit=50'),
      api.get('/suppliers/receipts'),
    ]);
    suppliersList = suppRes.items || [];
    warehousesList = whRes || [];
    purchaseOrders = poRes.items || [];
    goodsReceipts = recRes || [];
    updateMetrics();
  } catch (err) {
    console.error('Error cargando datos de abastecimiento', err);
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

function switchTab(tab) {
  currentTab = tab;
  const tabs = ['orders', 'receipts', 'replenishment'];
  tabs.forEach((t) => {
    const btn = document.getElementById(`tab-${t}`);
    if (btn) {
      if (t === tab) {
        btn.className = 'tab-btn pb-3 text-sm font-semibold border-b-2 border-blue-600 text-blue-600 flex items-center gap-2';
      } else {
        btn.className = 'tab-btn pb-3 text-sm font-semibold border-b-2 border-transparent text-slate-500 hover:text-slate-800 flex items-center gap-2';
      }
    }
  });

  const content = document.getElementById('tab-content');
  if (!content) return;

  if (tab === 'orders') {
    renderOrdersTab(content);
  } else if (tab === 'receipts') {
    renderReceiptsTab(content);
  } else if (tab === 'replenishment') {
    renderReplenishmentTab(content);
  }
}

// ===========================================================================
// 1. PESTAÑA: ÓRDENES DE COMPRA (WORKFLOW & AUTORIZACIÓN)
// ===========================================================================

function renderOrdersTab(container) {
  container.innerHTML = `
    <div class="card overflow-hidden">
      <div class="p-4 border-b border-slate-200 flex items-center justify-between">
        <div>
          <h2 class="text-base font-bold text-slate-900">Listado de Órdenes de Compra</h2>
          <p class="text-xs text-slate-500">Regla estricta: No generar compras ni pagos reales sin autorización</p>
        </div>
        <span class="text-xs text-slate-500 font-mono">${purchaseOrders.length} registros</span>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-left border-collapse">
          <thead>
            <tr class="bg-slate-50 border-b border-slate-200 text-xs font-semibold text-slate-600 uppercase tracking-wider">
              <th class="p-3">No. Orden</th>
              <th class="p-3">Proveedor</th>
              <th class="p-3">Estado</th>
              <th class="p-3">Monto Total</th>
              <th class="p-3">Pago Autorizado</th>
              <th class="p-3">Fecha</th>
              <th class="p-3 text-right">Acciones</th>
            </tr>
          </thead>
          <tbody id="po-table-body" class="divide-y divide-slate-100 text-sm">
            ${renderPoRows()}
          </tbody>
        </table>
      </div>
    </div>
  `;

  bindOrderEvents(container);
}

function renderPoRows() {
  if (purchaseOrders.length === 0) {
    return `
      <tr>
        <td colspan="7" class="p-8 text-center text-slate-400">
          No hay órdenes de compra registradas. Haz clic en "Nueva Orden de Compra" para emitir la primera.
        </td>
      </tr>
    `;
  }

  return purchaseOrders.map((po) => {
    let statusBadge = '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700">Borrador</span>';
    if (po.status === 'approved') {
      statusBadge = '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-blue-700">Autorizada</span>';
    } else if (po.status === 'issued') {
      statusBadge = '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700">Emitida al Proveedor</span>';
    } else if (po.status === 'partially_received') {
      statusBadge = '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700">Parcialmente Recibida</span>';
    } else if (po.status === 'received') {
      statusBadge = '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700">Recibida Total</span>';
    }

    const payBadge = po.payment_authorized
      ? '<span class="inline-flex items-center text-xs font-medium text-emerald-600">✓ Autorizado</span>'
      : '<span class="inline-flex items-center text-xs font-medium text-slate-400">Pendiente</span>';

    const suppName = po.supplier ? po.supplier.name : (po.supplier_id ? po.supplier_id.slice(0, 8) + '...' : 'Proveedor');

    return `
      <tr class="hover:bg-slate-50 transition-colors">
        <td class="p-3 font-mono font-bold text-slate-900">${po.po_number}</td>
        <td class="p-3 text-slate-800 text-xs font-medium">${suppName}</td>
        <td class="p-3">${statusBadge}</td>
        <td class="p-3 font-mono font-bold text-slate-900">$${(parseFloat(po.total_amount) || 0).toLocaleString('es-MX', { minimumFractionDigits: 2 })} MXN</td>
        <td class="p-3">${payBadge}</td>
        <td class="p-3 text-xs text-slate-500">${new Date(po.created_at).toLocaleDateString('es-MX')}</td>
        <td class="p-3 text-right space-x-1">
          ${po.status === 'draft' ? `
            <button data-po-approve="${po.id}" class="btn-po-approve text-xs px-2 py-1 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 rounded font-medium">
              Aprobar
            </button>
          ` : ''}
          ${po.status === 'approved' ? `
            <button data-po-issue="${po.id}" class="btn-po-issue text-xs px-2 py-1 bg-indigo-50 text-indigo-700 hover:bg-indigo-100 rounded font-medium">
              Emitir
            </button>
          ` : ''}
          ${['approved', 'issued', 'partially_received'].includes(po.status) ? `
            <button data-po-receipt="${po.id}" class="btn-po-receipt text-xs px-2 py-1 bg-blue-50 text-blue-700 hover:bg-blue-100 rounded font-medium">
              Recibir
            </button>
          ` : ''}
          <button data-po-id="${po.id}" class="btn-view-po-details text-xs px-2 py-1 bg-slate-100 hover:bg-slate-200 rounded font-medium text-slate-700">
            Detalle
          </button>
        </td>
      </tr>
    `;
  }).join('');
}

function bindOrderEvents(container) {
  // Ver Detalle
  container.querySelectorAll('.btn-view-po-details').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const id = btn.dataset.poId;
      try {
        const [po, landed] = await Promise.all([
          api.get(`/suppliers/purchase-orders/${id}`),
          api.get(`/suppliers/purchase-orders/${id}/landed-cost`).catch(() => null),
        ]);
        openPoDetailModal(po, landed);
      } catch (err) {
        showToast(err.message || 'Error cargando orden', 'error');
      }
    });
  });

  // Aprobar OC
  container.querySelectorAll('.btn-po-approve').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const id = btn.dataset.poApprove;
      if (!confirm('¿Confirma la autorización de esta Orden de Compra para proceder con el suministro?')) return;
      try {
        await api.post(`/suppliers/purchase-orders/${id}/approve`, { notes: 'Aprobado desde panel web' });
        showToast('Orden de compra autorizada exitosamente', 'success');
        await loadInitialData();
        renderOrdersTab(document.getElementById('tab-content'));
      } catch (err) {
        showToast(err.message || 'Error al aprobar orden', 'error');
      }
    });
  });

  // Emitir OC
  container.querySelectorAll('.btn-po-issue').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const id = btn.dataset.poIssue;
      try {
        await api.post(`/suppliers/purchase-orders/${id}/issue`);
        showToast('Orden de compra emitida formalmente al proveedor', 'success');
        await loadInitialData();
        renderOrdersTab(document.getElementById('tab-content'));
      } catch (err) {
        showToast(err.message || 'Error al emitir orden', 'error');
      }
    });
  });

  // Recibir Mercancía
  container.querySelectorAll('.btn-po-receipt').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const id = btn.dataset.poReceipt;
      const po = await api.get(`/suppliers/purchase-orders/${id}`);
      openCreateReceiptModal(po);
    });
  });
}

function openPoDetailModal(po, landed) {
  const itemsHtml = (po.items || []).map((it) => `
    <tr class="border-b border-slate-100 text-xs">
      <td class="p-2 font-mono">${it.sku}</td>
      <td class="p-2">${it.product_name}</td>
      <td class="p-2 font-semibold text-center">${it.quantity_ordered}</td>
      <td class="p-2 text-emerald-700 font-semibold text-center">${it.quantity_received}</td>
      <td class="p-2 text-amber-700 font-semibold text-center">${it.quantity_pending}</td>
      <td class="p-2 text-right font-mono">$${Number(it.unit_cost).toFixed(2)}</td>
      <td class="p-2 text-right font-mono font-bold">$${Number(it.total_cost).toFixed(2)}</td>
    </tr>
  `).join('');

  let landedHtml = '';
  if (landed && landed.items) {
    landedHtml = `
      <div class="mt-4 pt-4 border-t border-slate-200">
        <h4 class="text-xs font-bold text-slate-800 uppercase mb-2">Costo Puesto en Almacén (Landed Cost Prorrateado)</h4>
        <div class="grid grid-cols-3 gap-2 bg-slate-50 p-3 rounded-lg text-xs mb-2">
          <div><span class="text-slate-500">Mercancía:</span> <strong class="font-mono">$${landed.total_merchandise_subtotal.toFixed(2)}</strong></div>
          <div><span class="text-slate-500">Flete:</span> <strong class="font-mono">$${landed.total_freight.toFixed(2)}</strong></div>
          <div><span class="text-slate-500">Otros Gastos:</span> <strong class="font-mono">$${landed.total_other_expenses.toFixed(2)}</strong></div>
        </div>
        <table class="w-full text-xs">
          <thead>
            <tr class="bg-slate-100 text-slate-600">
              <th class="p-1.5 text-left">SKU</th>
              <th class="p-1.5 text-right">Costo Nominal</th>
              <th class="p-1.5 text-right">Flete Unit.</th>
              <th class="p-1.5 text-right">Otros Gastos</th>
              <th class="p-1.5 text-right font-bold text-blue-700">Landed Unitario</th>
            </tr>
          </thead>
          <tbody>
            ${landed.items.map((li) => `
              <tr class="border-b border-slate-100">
                <td class="p-1.5 font-mono">${li.sku}</td>
                <td class="p-1.5 text-right font-mono">$${li.nominal_unit_cost.toFixed(2)}</td>
                <td class="p-1.5 text-right font-mono text-slate-600">+$${li.allocated_freight.toFixed(2)}</td>
                <td class="p-1.5 text-right font-mono text-slate-600">+$${li.allocated_other_expenses.toFixed(2)}</td>
                <td class="p-1.5 text-right font-mono font-bold text-blue-700">$${li.final_landed_unit_cost.toFixed(2)}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;
  }

  const content = `
    <div class="space-y-4">
      <div class="grid grid-cols-2 gap-4 bg-slate-50 p-3 rounded-xl border border-slate-200 text-xs">
        <div>
          <span class="text-slate-500">Número de Orden:</span>
          <div class="font-mono font-bold text-slate-900 text-base">${po.po_number}</div>
        </div>
        <div>
          <span class="text-slate-500">Monto Total:</span>
          <div class="font-mono font-bold text-emerald-700 text-base">$${Number(po.total_amount).toFixed(2)} MXN</div>
        </div>
        <div>
          <span class="text-slate-500">Estado de la Orden:</span>
          <div class="font-bold text-slate-800 uppercase">${po.status}</div>
        </div>
        <div>
          <span class="text-slate-500">Autorización de Pago:</span>
          <div class="font-bold ${po.payment_authorized ? 'text-emerald-700' : 'text-amber-700'}">
            ${po.payment_authorized ? '✓ Autorizado para Pago' : 'Requiere Autorización'}
          </div>
        </div>
      </div>

      <div>
        <h4 class="text-xs font-bold text-slate-800 uppercase mb-2">Partidas de la Orden</h4>
        <div class="overflow-x-auto border border-slate-200 rounded-lg">
          <table class="w-full text-left">
            <thead>
              <tr class="bg-slate-50 text-slate-600 text-xs border-b border-slate-200">
                <th class="p-2">SKU</th>
                <th class="p-2">Producto</th>
                <th class="p-2 text-center">Sol.</th>
                <th class="p-2 text-center">Rec.</th>
                <th class="p-2 text-center">Pend.</th>
                <th class="p-2 text-right">Costo Unit.</th>
                <th class="p-2 text-right">Total</th>
              </tr>
            </thead>
            <tbody>
              ${itemsHtml}
            </tbody>
          </table>
        </div>
      </div>

      ${landedHtml}

      ${!po.payment_authorized ? `
        <div class="pt-3 border-t border-slate-200 flex justify-end gap-2">
          <button id="btn-modal-auth-pay" class="btn-primary text-xs flex items-center gap-1">
            ${icons.check} Autorizar Pago a Proveedor
          </button>
        </div>
      ` : ''}
    </div>
  `;

  openModal(`Detalle de Orden de Compra · ${po.po_number}`, content);

  document.getElementById('btn-modal-auth-pay')?.addEventListener('click', async () => {
    try {
      await api.post(`/suppliers/purchase-orders/${po.id}/authorize-payment`, {
        amount: Number(po.total_amount),
        notes: 'Pago validado y autorizado por administración',
      });
      closeModal();
      showToast('Pago autorizado con éxito', 'success');
      await loadInitialData();
      renderOrdersTab(document.getElementById('tab-content'));
    } catch (err) {
      showToast(err.message || 'Error al autorizar pago', 'error');
    }
  });
}

// ===========================================================================
// 2. PESTAÑA: RECEPCIONES DE MERCANCÍA (KARDEX & PARCIALES)
// ===========================================================================

function renderReceiptsTab(container) {
  container.innerHTML = `
    <div class="card overflow-hidden">
      <div class="p-4 border-b border-slate-200 flex items-center justify-between">
        <div>
          <h2 class="text-base font-bold text-slate-900">Recepciones Físicas en Almacén (Kardex INBOUND)</h2>
          <p class="text-xs text-slate-500">Entradas transaccionales con actualización inmediata de stock físico y disponible</p>
        </div>
        <span class="text-xs text-slate-500 font-mono">${goodsReceipts.length} recepciones registradas</span>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-left border-collapse">
          <thead>
            <tr class="bg-slate-50 border-b border-slate-200 text-xs font-semibold text-slate-600 uppercase tracking-wider">
              <th class="p-3">Folio Recepción</th>
              <th class="p-3">Remisión / Guía</th>
              <th class="p-3">Transportista</th>
              <th class="p-3 text-center">Unidades Recibidas</th>
              <th class="p-3 text-center">Rechazadas</th>
              <th class="p-3">Fecha Recepción</th>
              <th class="p-3">Recibido Por</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 text-sm">
            ${renderReceiptRows()}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function renderReceiptRows() {
  if (goodsReceipts.length === 0) {
    return `
      <tr>
        <td colspan="7" class="p-8 text-center text-slate-400">
          No hay recepciones físicas registradas aún.
        </td>
      </tr>
    `;
  }

  return goodsReceipts.map((gr) => {
    let totRec = 0;
    let totRej = 0;
    (gr.items || []).forEach((it) => {
      totRec += it.quantity_received || 0;
      totRej += it.quantity_rejected || 0;
    });

    return `
      <tr class="hover:bg-slate-50 transition-colors">
        <td class="p-3 font-mono font-bold text-slate-900">${gr.receipt_number}</td>
        <td class="p-3 font-mono text-xs text-slate-700">${gr.delivery_note_number || 'S/N'}</td>
        <td class="p-3 text-xs text-slate-800">${gr.carrier || 'Entrega local'}</td>
        <td class="p-3 text-center font-bold text-emerald-700">${totRec}</td>
        <td class="p-3 text-center font-bold ${totRej > 0 ? 'text-rose-600' : 'text-slate-400'}">${totRej}</td>
        <td class="p-3 text-xs text-slate-500">${new Date(gr.receipt_date).toLocaleString('es-MX')}</td>
        <td class="p-3 text-xs text-slate-600">${gr.received_by_name || 'Almacén'}</td>
      </tr>
    `;
  }).join('');
}

function openCreateReceiptModal(po) {
  const itemsInputs = (po.items || []).map((it) => `
    <div class="p-3 bg-slate-50 rounded-lg border border-slate-200 space-y-2 text-xs">
      <div class="flex justify-between items-center">
        <div>
          <span class="font-mono font-bold text-slate-900">${it.sku}</span>
          <span class="text-slate-600 ml-2">${it.product_name}</span>
        </div>
        <div class="text-slate-500">
          Ordenado: <strong>${it.quantity_ordered}</strong> · Pendiente: <strong class="text-amber-700">${it.quantity_pending}</strong>
        </div>
      </div>
      <div class="grid grid-cols-3 gap-2">
        <div>
          <label class="block text-slate-600 mb-0.5">Unidades Aceptadas *</label>
          <input type="number" data-item-id="${it.id}" class="rec-qty-input input-field text-xs py-1" min="0" max="${it.quantity_pending}" value="${it.quantity_pending}" />
        </div>
        <div>
          <label class="block text-slate-600 mb-0.5">Rechazadas (Daño)</label>
          <input type="number" data-rej-id="${it.id}" class="rej-qty-input input-field text-xs py-1" min="0" value="0" />
        </div>
        <div>
          <label class="block text-slate-600 mb-0.5">Motivo Rechazo</label>
          <input type="text" data-reason-id="${it.id}" class="rec-reason-input input-field text-xs py-1" placeholder="Caja mojada / rota" />
        </div>
      </div>
    </div>
  `).join('');

  const whOptions = warehousesList.map((w) => `<option value="${w.id}">${w.name} (${w.code})</option>`).join('');

  const content = `
    <form id="create-receipt-form" class="space-y-4">
      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Folio Recepción *</label>
          <input type="text" id="rec-number" class="input-field text-xs font-mono" value="REC-${new Date().getFullYear()}-${Math.floor(1000 + Math.random() * 9000)}" required />
        </div>
        <div>
          <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Almacén Destino *</label>
          <select id="rec-warehouse" class="input-field text-xs" required>
            ${whOptions}
          </select>
        </div>
      </div>

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">No. Remisión / Factura Proveedor</label>
          <input type="text" id="rec-delivery-note" class="input-field text-xs font-mono" placeholder="REM-10294" />
        </div>
        <div>
          <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Transportista / Fletera</label>
          <input type="text" id="rec-carrier" class="input-field text-xs" placeholder="Transportes Castores / DHL" />
        </div>
      </div>

      <div class="space-y-2">
        <label class="block text-xs font-semibold text-slate-700 uppercase">Partidas Recibidas</label>
        ${itemsInputs}
      </div>

      <div>
        <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Notas de Recepción</label>
        <textarea id="rec-notes" class="input-field text-xs" rows="2" placeholder="Observaciones de descarga en andén..."></textarea>
      </div>

      <div class="flex justify-end gap-2 pt-2">
        <button type="button" id="btn-cancel-rec" class="btn-secondary">Cancelar</button>
        <button type="submit" id="btn-submit-rec" class="btn-primary flex items-center gap-1.5">
          ${icons.check} Confirmar Entrada al Kardex
        </button>
      </div>
    </form>
  `;

  openModal(`Recepción Física de Mercancía · OC ${po.po_number}`, content);
  document.getElementById('btn-cancel-rec')?.addEventListener('click', closeModal);

  const form = document.getElementById('create-receipt-form');
  form?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const recNumber = document.getElementById('rec-number').value.trim();
    const whId = document.getElementById('rec-warehouse').value;
    const note = document.getElementById('rec-delivery-note').value.trim();
    const carrier = document.getElementById('rec-carrier').value.trim();
    const notes = document.getElementById('rec-notes').value.trim();

    const items = [];
    (po.items || []).forEach((it) => {
      const qInput = form.querySelector(`.rec-qty-input[data-item-id="${it.id}"]`);
      const rInput = form.querySelector(`.rej-qty-input[data-rej-id="${it.id}"]`);
      const reasonInput = form.querySelector(`.rec-reason-input[data-reason-id="${it.id}"]`);

      const qty = parseInt(qInput?.value) || 0;
      const rej = parseInt(rInput?.value) || 0;
      const reason = reasonInput?.value.trim() || null;

      if (qty > 0 || rej > 0) {
        items.push({
          purchase_order_item_id: it.id,
          variant_id: it.variant_id,
          quantity_received: qty,
          quantity_rejected: rej,
          rejection_reason: reason,
          unit_cost: Number(it.unit_cost),
        });
      }
    });

    if (items.length === 0) {
      showToast('Debes indicar al menos una partida con unidades recibidas o rechazadas.', 'warning');
      return;
    }

    try {
      await api.post(`/suppliers/purchase-orders/${po.id}/receipts`, {
        receipt_number: recNumber,
        warehouse_id: whId,
        delivery_note_number: note || null,
        carrier: carrier || null,
        notes: notes || null,
        items,
      });
      closeModal();
      showToast('Entrada registrada exitosamente en almacén y Kardex actualizado', 'success');
      await loadInitialData();
      renderReceiptsTab(document.getElementById('tab-content'));
    } catch (err) {
      showToast(err.message || 'Error registrando entrada', 'error');
    }
  });
}

// ===========================================================================
// 3. PESTAÑA: MOTOR DE REPOSICIÓN INTELIGENTE
// ===========================================================================

async function renderReplenishmentTab(container) {
  container.innerHTML = `
    <div class="space-y-4">
      <div class="card p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 class="text-base font-bold text-slate-900">Motor de Cálculo y Alertas de Reposición</h2>
          <p class="text-xs text-slate-500">
            Fórmulas: Demanda diaria ($D$), Punto de Reorden ($ROP = (D \times L) + SS$) y Cobertura proyectada.
          </p>
        </div>
        <div class="flex items-center gap-3">
          <label class="text-xs text-slate-600 font-semibold">Historial:</label>
          <select id="rep-days-history" class="input-field text-xs py-1 px-2">
            <option value="15">Últimos 15 días</option>
            <option value="30" selected>Últimos 30 días</option>
            <option value="60">Últimos 60 días</option>
          </select>
          <label class="text-xs text-slate-600 font-semibold">Objetivo:</label>
          <select id="rep-target-coverage" class="input-field text-xs py-1 px-2">
            <option value="15">15 días</option>
            <option value="30" selected>30 días de stock</option>
            <option value="45">45 días de stock</option>
          </select>
          <button id="btn-calc-replenishment" class="btn-primary text-xs py-1.5 px-3">
            Calcular Sugerencias
          </button>
        </div>
      </div>

      <div id="rep-table-container">
        <div class="p-8 text-center text-slate-400 card">
          Cargando análisis de reposición inteligente...
        </div>
      </div>
    </div>
  `;

  container.querySelector('#btn-calc-replenishment').addEventListener('click', () => fetchReplenishmentData());
  await fetchReplenishmentData();
}

async function fetchReplenishmentData() {
  const container = document.getElementById('rep-table-container');
  if (!container) return;

  const daysHistory = document.getElementById('rep-days-history')?.value || 30;
  const targetCoverage = document.getElementById('rep-target-coverage')?.value || 30;

  try {
    replenishmentReport = await api.get(`/suppliers/replenishment/suggestions?days_history=${daysHistory}&target_days_coverage=${targetCoverage}`);

    // Update Header metrics
    const alertMetric = document.getElementById('metric-rep-alerts');
    const investMetric = document.getElementById('metric-rep-investment');
    if (alertMetric) {
      alertMetric.textContent = (replenishmentReport.out_of_stock_count || 0) + (replenishmentReport.critical_count || 0);
    }
    if (investMetric) {
      investMetric.textContent = `$${Number(replenishmentReport.total_suggested_investment || 0).toLocaleString('es-MX', { maximumFractionDigits: 0 })} MXN`;
    }

    renderReplenishmentTable(container);
  } catch (err) {
    container.innerHTML = `<div class="card p-6 text-center text-rose-600 text-xs">${err.message || 'Error calculando reposición'}</div>`;
  }
}

function renderReplenishmentTable(container) {
  if (!replenishmentReport || !replenishmentReport.items || replenishmentReport.items.length === 0) {
    container.innerHTML = `
      <div class="card p-8 text-center text-slate-400">
        No se encontraron sugerencias de compra para los parámetros configurados.
      </div>
    `;
    return;
  }

  const rows = replenishmentReport.items.map((item) => {
    let alertBadge = '<span class="inline-flex px-2 py-0.5 rounded text-xs font-semibold bg-emerald-50 text-emerald-700">SALUDABLE</span>';
    if (item.alert_status === 'OUT_OF_STOCK') {
      alertBadge = '<span class="inline-flex px-2 py-0.5 rounded text-xs font-semibold bg-rose-100 text-rose-800 animate-pulse">AGOTADO</span>';
    } else if (item.alert_status === 'CRITICAL') {
      alertBadge = '<span class="inline-flex px-2 py-0.5 rounded text-xs font-semibold bg-amber-100 text-amber-800">CRÍTICO</span>';
    } else if (item.alert_status === 'REORDER_POINT') {
      alertBadge = '<span class="inline-flex px-2 py-0.5 rounded text-xs font-semibold bg-blue-100 text-blue-800">PUNTO REORDEN</span>';
    } else if (item.alert_status === 'OVERSTOCK') {
      alertBadge = '<span class="inline-flex px-2 py-0.5 rounded text-xs font-semibold bg-purple-100 text-purple-800">SOBRESTOCK</span>';
    }

    return `
      <tr class="hover:bg-slate-50 transition-colors">
        <td class="p-3">
          <div class="font-mono font-bold text-slate-900">${item.sku}</div>
          <div class="text-xs text-slate-500">${item.product_name}</div>
        </td>
        <td class="p-3 text-center">${alertBadge}</td>
        <td class="p-3 text-center font-bold text-slate-800">${item.available_stock}</td>
        <td class="p-3 text-center text-xs font-semibold text-slate-600">${item.days_of_coverage.toFixed(1)} d</td>
        <td class="p-3 text-center text-xs font-mono">${item.sales_velocity_per_day.toFixed(2)}/d</td>
        <td class="p-3 text-center text-xs font-mono text-slate-600">${item.reorder_point}</td>
        <td class="p-3 text-center text-xs font-mono text-slate-600">${item.safety_stock}</td>
        <td class="p-3 text-center font-bold text-blue-700 text-sm">${item.suggested_order_quantity}</td>
        <td class="p-3 text-right font-mono font-bold text-slate-900">$${item.estimated_investment.toLocaleString('es-MX', { minimumFractionDigits: 2 })}</td>
        <td class="p-3 text-right">
          ${item.suggested_order_quantity > 0 && item.preferred_supplier_id ? `
            <button
              data-gen-sku="${item.sku}"
              data-gen-supp="${item.preferred_supplier_id}"
              data-gen-var="${item.variant_id}"
              data-gen-qty="${item.suggested_order_quantity}"
              data-gen-cost="${item.unit_cost}"
              class="btn-gen-auto-po text-xs px-2.5 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded font-medium inline-flex items-center gap-1"
            >
              ${icons.plus} Generar OC
            </button>
          ` : '<span class="text-xs text-slate-400">Sin proveedor</span>'}
        </td>
      </tr>
    `;
  }).join('');

  container.innerHTML = `
    <div class="card overflow-hidden">
      <div class="p-3 bg-slate-50 border-b border-slate-200 flex items-center justify-between text-xs">
        <span class="text-slate-600">Total SKUs evaluados: <strong>${replenishmentReport.total_skus_analyzed}</strong></span>
        <span class="text-slate-600">Agotados: <strong class="text-rose-600">${replenishmentReport.out_of_stock_count}</strong> | Críticos: <strong class="text-amber-600">${replenishmentReport.critical_count}</strong></span>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-left border-collapse">
          <thead>
            <tr class="bg-slate-100 border-b border-slate-200 text-xs font-semibold text-slate-600 uppercase tracking-wider">
              <th class="p-3">SKU / Producto</th>
              <th class="p-3 text-center">Alerta</th>
              <th class="p-3 text-center">Disponible</th>
              <th class="p-3 text-center">Cobertura</th>
              <th class="p-3 text-center">Velocidad</th>
              <th class="p-3 text-center">ROP</th>
              <th class="p-3 text-center">SS</th>
              <th class="p-3 text-center text-blue-700">Sugerido</th>
              <th class="p-3 text-right">Inversión</th>
              <th class="p-3 text-right">Acción</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 text-sm">
            ${rows}
          </tbody>
        </table>
      </div>
    </div>
  `;

  container.querySelectorAll('.btn-gen-auto-po').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const suppId = btn.dataset.genSupp;
      const varId = btn.dataset.genVar;
      const qty = parseInt(btn.dataset.genQty);
      const sku = btn.dataset.genSku;

      if (!confirm(`¿Desea generar automáticamente una Orden de Compra para ${qty} unidades de SKU ${sku}?`)) return;

      try {
        const payload = {
          supplier_id: suppId,
          variant_ids: [varId],
          target_days_coverage: 30,
          notes: 'Generada automáticamente desde sugerencias del motor de reposición',
        };
        const po = await api.post('/suppliers/replenishment/generate-po', payload);
        showToast(`Orden ${po.po_number} generada en estado borrador con éxito`, 'success');
        await loadInitialData();
        switchTab('orders');
      } catch (err) {
        showToast(err.message || 'Error al generar orden', 'error');
      }
    });
  });
}

// ===========================================================================
// MODAL: NUEVA ORDEN DE COMPRA
// ===========================================================================

function openCreatePoModal() {
  const currentCompany = state.currentCompany;
  if (!currentCompany) {
    showToast('Selecciona una empresa primero', 'error');
    return;
  }

  if (suppliersList.length === 0) {
    showToast('Debes registrar al menos un proveedor en el directorio antes de emitir una orden de compra.', 'warning');
    return;
  }

  const supplierOptions = suppliersList
    .map((s) => `<option value="${s.id}">${s.name} (RFC: ${s.rfc || 'S/N'})</option>`)
    .join('');

  const whOptions = warehousesList
    .map((w) => `<option value="${w.id}">${w.name} (${w.code})</option>`)
    .join('');

  const content = `
    <form id="create-po-form" class="space-y-4">
      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Proveedor *</label>
          <select id="po-supplier-select" class="input-field text-sm" required>
            ${supplierOptions}
          </select>
        </div>
        <div>
          <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Almacén Destino</label>
          <select id="po-wh-select" class="input-field text-sm">
            ${whOptions}
          </select>
        </div>
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

      <!-- Partida de Compra -->
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

        <div class="grid grid-cols-3 gap-3">
          <div>
            <label class="block text-xs text-slate-600 mb-1">Cantidad *</label>
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
            <label class="block text-xs text-slate-600 mb-1">Costo Unit. (MXN) *</label>
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
          <div>
            <label class="block text-xs text-slate-600 mb-1">IVA (Tasa)</label>
            <select id="po-item-tax" class="input-field text-sm">
              <option value="0.16" selected>16% IVA</option>
              <option value="0.00">0% Exento</option>
            </select>
          </div>
        </div>

        <div class="flex justify-between items-center pt-2 border-t border-slate-200 text-xs">
          <span class="text-slate-600 font-semibold">Subtotal + IVA Calculado:</span>
          <span id="po-calculated-total" class="font-mono font-bold text-slate-900">$8,700.00 MXN</span>
        </div>
      </div>

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Costo Estimado de Flete (MXN)</label>
          <input type="number" id="po-shipping-cost" class="input-field text-sm" value="0.00" step="50.00" />
        </div>
        <div>
          <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Términos de Pago</label>
          <select id="po-payment-terms" class="input-field text-sm">
            <option value="30_days">Crédito a 30 días</option>
            <option value="immediate">Contado / Transferencia previa</option>
            <option value="60_days">Crédito a 60 días</option>
          </select>
        </div>
      </div>

      <div>
        <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Notas / Condiciones Comerciales</label>
        <textarea id="po-notes" class="input-field text-xs" rows="2" placeholder="Condiciones de entrega en andén, maniobras de descarga, etc."></textarea>
      </div>

      <div class="flex justify-end gap-2 pt-2">
        <button type="button" id="btn-cancel-po" class="btn-secondary">Cancelar</button>
        <button type="submit" id="btn-submit-po" class="btn-primary flex items-center gap-1.5">
          ${icons.check} Crear Orden de Compra (Borrador)
        </button>
      </div>
    </form>
  `;

  openModal('Nueva Orden de Compra', content);
  document.getElementById('btn-cancel-po')?.addEventListener('click', closeModal);

  const qtyInput = document.getElementById('po-item-qty');
  const costInput = document.getElementById('po-item-cost');
  const taxInput = document.getElementById('po-item-tax');
  const totalSpan = document.getElementById('po-calculated-total');

  function updateTotal() {
    const qty = parseInt(qtyInput?.value) || 0;
    const cost = parseFloat(costInput?.value) || 0;
    const taxRate = parseFloat(taxInput?.value) || 0;
    const subtotal = qty * cost;
    const total = subtotal * (1 + taxRate);
    if (totalSpan) totalSpan.textContent = `$${total.toLocaleString('es-MX', { minimumFractionDigits: 2 })} MXN`;
  }

  qtyInput?.addEventListener('input', updateTotal);
  costInput?.addEventListener('input', updateTotal);
  taxInput?.addEventListener('change', updateTotal);

  const form = document.getElementById('create-po-form');
  form?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('btn-submit-po');
    btn.disabled = true;
    btn.innerHTML = 'Guardando...';

    const supplierId = document.getElementById('po-supplier-select').value;
    const whId = document.getElementById('po-wh-select').value;
    const poNumber = document.getElementById('po-number-input').value.trim();
    const expDateVal = document.getElementById('po-expected-date').value;
    const variantId = document.getElementById('po-item-variant-id').value.trim();
    const qty = parseInt(document.getElementById('po-item-qty').value);
    const cost = parseFloat(document.getElementById('po-item-cost').value);
    const taxRate = parseFloat(document.getElementById('po-item-tax').value);
    const shipping = parseFloat(document.getElementById('po-shipping-cost').value) || 0;
    const notes = document.getElementById('po-notes').value.trim();

    try {
      const payload = {
        company_id: currentCompany.id,
        supplier_id: supplierId,
        warehouse_id: whId || null,
        po_number: poNumber,
        shipping_cost: shipping,
        expected_delivery_date: expDateVal ? new Date(expDateVal).toISOString() : null,
        notes: notes || null,
        items: [
          {
            variant_id: variantId,
            quantity_ordered: qty,
            unit_cost: cost,
            tax_rate: taxRate,
          },
        ],
      };

      await api.post('/suppliers/purchase-orders', payload);
      closeModal();
      showToast('Orden de compra creada exitosamente en estado borrador', 'success');
      await loadInitialData();
      renderOrdersTab(document.getElementById('tab-content'));
    } catch (err) {
      showToast(err.message || 'Error al crear orden de compra', 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `${icons.check} Crear Orden de Compra (Borrador)`;
      }
    }
  });
}

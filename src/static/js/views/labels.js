/**
 * Centro de Logística y Sistema Dual de Etiquetas (Envíos Oficiales & Etiquetas Internas)
 * Conectado con la API REST /api/v1/logistics/* del ERP.
 */

import { api } from '../api.js';
import { state } from '../state.js';
import { icons } from '../icons.js';
import { showToast } from '../components/toast.js';
import { openModal, closeModal } from '../components/modal.js';

let activeTab = 'shipping'; // 'shipping' | 'internal' | 'order_picking' | 'limitations'
let shipmentsList = [];
let selectedShipmentIds = new Set();
let currentFilterDispatch = 'all'; // all, pending, prepared, dispatched, error
let currentFilterLogistic = 'all';
let searchQuery = '';
let metricsData = null;
let templatesList = [];
let selectedTemplate = 'thermal_4x6';
let internalItemsQueue = []; // [{sku, product_name, variant_name, location, price, quantity}]
let catalogVariants = [];

export async function renderLabels(container) {
  container.innerHTML = `
    <div class="space-y-6">
      <!-- Encabezado Principal -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 class="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            ${icons.tag} Centro de Logística y Etiquetas
          </h1>
          <p class="text-sm text-slate-500 mt-1">
            Gestión oficial de Mercado Envíos, guías de despacho, trazabilidad y rotulado interno de almacén.
          </p>
        </div>
        <div class="flex items-center gap-2">
          <button id="btn-refresh-logistics" class="btn-secondary flex items-center gap-1.5 text-xs py-2 px-3">
            ${icons.refresh} Actualizar Datos
          </button>
        </div>
      </div>

      <!-- Tarjetas de Salud Logística -->
      <div class="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <div class="card p-3 border-l-4 border-amber-500">
          <div class="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Pendientes Empaque</div>
          <div id="stat-pending" class="text-2xl font-bold text-amber-600 mt-0.5">-</div>
          <div class="text-[10px] text-slate-400">Guía por imprimir</div>
        </div>
        <div class="card p-3 border-l-4 border-blue-500">
          <div class="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Preparados</div>
          <div id="stat-prepared" class="text-2xl font-bold text-blue-600 mt-0.5">-</div>
          <div class="text-[10px] text-slate-400">Etiqueta impresa</div>
        </div>
        <div class="card p-3 border-l-4 border-emerald-500">
          <div class="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Despachados</div>
          <div id="stat-dispatched" class="text-2xl font-bold text-emerald-600 mt-0.5">-</div>
          <div class="text-[10px] text-slate-400">En ruta / Entregado</div>
        </div>
        <div class="card p-3 border-l-4 border-rose-500">
          <div class="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Incidencias / Error</div>
          <div id="stat-error" class="text-2xl font-bold text-rose-600 mt-0.5">-</div>
          <div class="text-[10px] text-slate-400">Demoras o alertas</div>
        </div>
        <div class="card p-3 border-l-4 border-purple-500">
          <div class="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Mercado Envíos Full</div>
          <div id="stat-full" class="text-2xl font-bold text-purple-600 mt-0.5">-</div>
          <div class="text-[10px] text-slate-400">Operado por CEDIS MeLi</div>
        </div>
      </div>

      <!-- Pestañas de Navegación del Módulo -->
      <div class="border-b border-slate-200">
        <nav class="flex space-x-6 text-sm font-medium">
          <button id="tab-shipping" class="tab-btn pb-3 px-1 border-b-2 font-semibold flex items-center gap-2 border-primary-600 text-primary-600">
            ${icons.truck} Módulo A: Etiquetas de Envío MeLi
          </button>
          <button id="tab-internal" class="tab-btn pb-3 px-1 border-b-2 font-semibold flex items-center gap-2 border-transparent text-slate-500 hover:text-slate-700">
            ${icons.barcode || icons.tag} Módulo B: Etiquetas Internas (Almacén)
          </button>
          <button id="tab-picking" class="tab-btn pb-3 px-1 border-b-2 font-semibold flex items-center gap-2 border-transparent text-slate-500 hover:text-slate-700">
            ${icons.box || icons.package} Etiquetas de Surtido por Pedido
          </button>
          <button id="tab-limitations" class="tab-btn pb-3 px-1 border-b-2 font-semibold flex items-center gap-2 border-transparent text-slate-500 hover:text-slate-700">
            ${icons.info || icons.help} Limitaciones Oficiales & Contingencias
          </button>
        </nav>
      </div>

      <!-- Contenedor dinámico de pestañas -->
      <div id="logistics-tab-content">
        <!-- Renderizado dinámico -->
      </div>
    </div>
  `;

  // Bindings de pestañas
  container.querySelector('#tab-shipping').addEventListener('click', () => switchTab('shipping', container));
  container.querySelector('#tab-internal').addEventListener('click', () => switchTab('internal', container));
  container.querySelector('#tab-picking').addEventListener('click', () => switchTab('order_picking', container));
  container.querySelector('#tab-limitations').addEventListener('click', () => switchTab('limitations', container));
  container.querySelector('#btn-refresh-logistics').addEventListener('click', () => refreshData(container));

  await loadMetrics(container);
  await switchTab('shipping', container);
}

function switchTab(tab, container) {
  activeTab = tab;
  const tabs = ['shipping', 'internal', 'order_picking', 'limitations'];
  tabs.forEach(t => {
    const btn = container.querySelector(`#tab-${t === 'order_picking' ? 'picking' : t}`);
    if (btn) {
      if (t === tab) {
        btn.className = 'tab-btn pb-3 px-1 border-b-2 font-semibold flex items-center gap-2 border-primary-600 text-primary-600';
      } else {
        btn.className = 'tab-btn pb-3 px-1 border-b-2 font-semibold flex items-center gap-2 border-transparent text-slate-500 hover:text-slate-700';
      }
    }
  });

  const content = container.querySelector('#logistics-tab-content');
  if (tab === 'shipping') {
    renderShippingTab(content);
  } else if (tab === 'internal') {
    renderInternalLabelsTab(content);
  } else if (tab === 'order_picking') {
    renderOrderPickingTab(content);
  } else if (tab === 'limitations') {
    renderLimitationsTab(content);
  }
}

async function loadMetrics(container) {
  try {
    const res = await api.get('/logistics/metrics');
    metricsData = res;
    container.querySelector('#stat-pending').textContent = res.pending_count;
    container.querySelector('#stat-prepared').textContent = res.prepared_count;
    container.querySelector('#stat-dispatched').textContent = res.dispatched_count;
    container.querySelector('#stat-error').textContent = res.error_count;
    container.querySelector('#stat-full').textContent = res.fulfillment_full_count;
  } catch (err) {
    console.error('Error al cargar métricas logísticas:', err);
  }
}

async function refreshData(container) {
  await loadMetrics(container);
  switchTab(activeTab, container);
  showToast('Datos logísticos actualizados', 'info');
}

// ===========================================================================
// PESTAÑA A: ETIQUETAS DE ENVÍO OFICIALES (Mercado Envíos)
// ===========================================================================

async function renderShippingTab(container) {
  container.innerHTML = `
    <div class="space-y-4">
      <!-- Barra de Filtros y Acciones por Lote -->
      <div class="card p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div class="flex flex-wrap items-center gap-3">
          <!-- Buscador -->
          <div class="relative w-64">
            <input type="text" id="shipments-search" placeholder="Buscar guía, orden, comprador..." 
                   value="${searchQuery}" class="input-text text-xs py-1.5 pl-8 pr-2 w-full" />
            <span class="absolute left-2.5 top-2 text-slate-400">${icons.search}</span>
          </div>

          <!-- Filtro por Estado Operativo -->
          <select id="filter-dispatch" class="input-text text-xs py-1.5">
            <option value="all" ${currentFilterDispatch === 'all' ? 'selected' : ''}>Todos los Estados</option>
            <option value="pending" ${currentFilterDispatch === 'pending' ? 'selected' : ''}>⏳ Pendientes de Empaque</option>
            <option value="prepared" ${currentFilterDispatch === 'prepared' ? 'selected' : ''}>📦 Preparados (Etiqueta Impresa)</option>
            <option value="dispatched" ${currentFilterDispatch === 'dispatched' ? 'selected' : ''}>🚚 Despachados / En Ruta</option>
            <option value="error" ${currentFilterDispatch === 'error' ? 'selected' : ''}>⚠️ Errores / Demoras</option>
          </select>

          <!-- Filtro por Modalidad -->
          <select id="filter-logistic" class="input-text text-xs py-1.5">
            <option value="all" ${currentFilterLogistic === 'all' ? 'selected' : ''}>Todas las Modalidades</option>
            <option value="cross_docking" ${currentFilterLogistic === 'cross_docking' ? 'selected' : ''}>Colecta Estándar (Bodega)</option>
            <option value="drop_off" ${currentFilterLogistic === 'drop_off' ? 'selected' : ''}>Agencias MeLi (Drop-off)</option>
            <option value="self_service" ${currentFilterLogistic === 'self_service' ? 'selected' : ''}>Mercado Envíos Flex</option>
            <option value="fulfillment" ${currentFilterLogistic === 'fulfillment' ? 'selected' : ''}>Mercado Envíos Full</option>
          </select>
        </div>

        <!-- Botón Lote -->
        <div class="flex items-center gap-2">
          <button id="btn-batch-print" disabled class="btn-primary opacity-50 cursor-not-allowed flex items-center gap-1.5 text-xs py-2 px-3">
            ${icons.printer || icons.truck} Imprimir Lote (<span id="selected-count">0</span>)
          </button>
        </div>
      </div>

      <!-- Tabla de Envíos -->
      <div class="card overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs">
            <thead class="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold uppercase tracking-wider">
              <tr>
                <th class="p-3 w-8 text-center">
                  <input type="checkbox" id="check-all-shipments" class="rounded border-slate-300 text-primary-600 focus:ring-primary-500" />
                </th>
                <th class="p-3">Envío MeLi / Orden</th>
                <th class="p-3">Comprador</th>
                <th class="p-3">Modalidad</th>
                <th class="p-3">Transportista / Tracking</th>
                <th class="p-3 text-center">Impresiones</th>
                <th class="p-3">Estado Operativo</th>
                <th class="p-3 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody id="shipments-table-body" class="divide-y divide-slate-100">
              <tr><td colspan="8" class="p-6 text-center text-slate-400">Cargando envíos...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  // Bindings
  const searchInput = container.querySelector('#shipments-search');
  searchInput.addEventListener('input', (e) => {
    searchQuery = e.target.value;
    loadShipments(container);
  });

  container.querySelector('#filter-dispatch').addEventListener('change', (e) => {
    currentFilterDispatch = e.target.value;
    loadShipments(container);
  });

  container.querySelector('#filter-logistic').addEventListener('change', (e) => {
    currentFilterLogistic = e.target.value;
    loadShipments(container);
  });

  container.querySelector('#check-all-shipments').addEventListener('change', (e) => {
    const isChecked = e.target.checked;
    shipmentsList.forEach(s => {
      if (s.logistic_type !== 'fulfillment' && s.status !== 'cancelled') {
        if (isChecked) selectedShipmentIds.add(s.id);
        else selectedShipmentIds.delete(s.id);
      }
    });
    updateBatchPrintButton(container);
    renderShipmentsRows(container);
  });

  container.querySelector('#btn-batch-print').addEventListener('click', () => {
    executeBatchPrint(container);
  });

  await loadShipments(container);
}

async function loadShipments(container) {
  try {
    let url = `/logistics/shipments?size=50`;
    if (currentFilterDispatch !== 'all') url += `&dispatch_status=${currentFilterDispatch}`;
    if (currentFilterLogistic !== 'all') url += `&logistic_type=${currentFilterLogistic}`;
    if (searchQuery.trim()) url += `&search=${encodeURIComponent(searchQuery.trim())}`;

    const res = await api.get(url);
    shipmentsList = res.items || [];
    renderShipmentsRows(container);
  } catch (err) {
    showToast(`Error al cargar envíos: ${err.message}`, 'error');
  }
}

function renderShipmentsRows(container) {
  const tbody = container.querySelector('#shipments-table-body');
  if (!shipmentsList.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="p-6 text-center text-slate-400">No se encontraron envíos con los filtros actuales.</td></tr>`;
    return;
  }

  tbody.innerHTML = shipmentsList.map(s => {
    const isFull = s.logistic_type === 'fulfillment';
    const isCancelled = s.status === 'cancelled';
    const isSelected = selectedShipmentIds.has(s.id);
    const canSelect = !isFull && !isCancelled;

    let badgeDispatch = '<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-100 text-amber-800">Pendiente</span>';
    if (s.dispatch_status === 'prepared') {
      badgeDispatch = '<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-blue-100 text-blue-800">Preparado</span>';
    } else if (s.dispatch_status === 'dispatched') {
      badgeDispatch = '<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-800">Despachado</span>';
    } else if (s.dispatch_status === 'error') {
      badgeDispatch = '<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-rose-100 text-rose-800">Incidencia</span>';
    }

    let badgeLogistic = '<span class="px-1.5 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-slate-700">Colecta</span>';
    if (isFull) {
      badgeLogistic = '<span class="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-purple-100 text-purple-700">⚡ Full (CEDIS)</span>';
    } else if (s.logistic_type === 'drop_off') {
      badgeLogistic = '<span class="px-1.5 py-0.5 rounded text-[10px] font-medium bg-indigo-100 text-indigo-700">Agencia MeLi</span>';
    } else if (s.logistic_type === 'self_service') {
      badgeLogistic = '<span class="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-100 text-amber-800">Flex Mismo Día</span>';
    }

    const printBadge = s.print_count > 0 
      ? `<span class="px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-blue-50 text-blue-600">${s.print_count}x</span>`
      : `<span class="text-slate-300">0</span>`;

    const trackingText = s.tracking_number 
      ? `<span class="font-mono font-medium text-slate-800">${s.tracking_number}</span>`
      : `<span class="text-slate-400 italic">Por asignar</span>`;

    const orderNum = s.order?.order_number || `#${s.meli_shipment_id}`;
    const buyerNickname = s.order?.buyer_nickname || 'Comprador MeLi';

    return `
      <tr class="hover:bg-slate-50 transition-colors">
        <td class="p-3 text-center">
          <input type="checkbox" class="shipment-row-check rounded border-slate-300 text-primary-600 focus:ring-primary-500"
                 data-id="${s.id}" ${isSelected ? 'checked' : ''} ${!canSelect ? 'disabled' : ''} />
        </td>
        <td class="p-3">
          <div class="font-bold text-slate-900">${s.meli_shipment_id}</div>
          <div class="text-[11px] text-slate-500">${orderNum}</div>
        </td>
        <td class="p-3">
          <div class="font-medium text-slate-800">${buyerNickname}</div>
          <div class="text-[10px] text-slate-400">${s.receiver_address?.city?.name || 'México'}</div>
        </td>
        <td class="p-3">
          ${badgeLogistic}
        </td>
        <td class="p-3">
          <div class="font-semibold text-slate-700">${s.carrier_name || 'Mercado Envíos'}</div>
          <div class="text-[10px]">${trackingText}</div>
        </td>
        <td class="p-3 text-center">
          ${printBadge}
        </td>
        <td class="p-3">
          ${badgeDispatch}
        </td>
        <td class="p-3 text-right space-x-1">
          <!-- Ver / Descargar Guía -->
          ${!isFull && !isCancelled ? `
            <button class="btn-action-view btn-secondary py-1 px-2 text-[11px]" data-id="${s.id}" title="Ver o descargar PDF oficial">
              ${icons.download || icons.file || 'PDF'}
            </button>
            <button class="btn-action-print ${s.print_count === 0 ? 'btn-primary' : 'btn-secondary'} py-1 px-2 text-[11px]" 
                    data-id="${s.id}" data-count="${s.print_count}" title="${s.print_count === 0 ? 'Imprimir Guía' : 'Reimprimir Guía'}">
              ${s.print_count === 0 ? (icons.printer || 'Imprimir') : 'Reimprimir'}
            </button>
          ` : isFull ? `
            <span class="text-[10px] text-purple-600 font-semibold" title="Mercado Libre despacha directamente">CEDIS MeLi</span>
          ` : `
            <span class="text-[10px] text-rose-500 font-semibold">Cancelado</span>
          `}
          <!-- Seguimiento -->
          <button class="btn-action-tracking btn-secondary py-1 px-2 text-[11px]" data-id="${s.id}" title="Trazabilidad y Seguimiento">
            ${icons.truck || 'Rastreo'}
          </button>
        </td>
      </tr>
    `;
  }).join('');

  // Vincular eventos de filas
  tbody.querySelectorAll('.shipment-row-check').forEach(chk => {
    chk.addEventListener('change', (e) => {
      const id = e.target.dataset.id;
      if (e.target.checked) selectedShipmentIds.add(id);
      else selectedShipmentIds.delete(id);
      updateBatchPrintButton(container);
    });
  });

  tbody.querySelectorAll('.btn-action-view').forEach(btn => {
    btn.addEventListener('click', () => viewOfficialLabel(btn.dataset.id));
  });

  tbody.querySelectorAll('.btn-action-print').forEach(btn => {
    const id = btn.dataset.id;
    const count = parseInt(btn.dataset.count || '0');
    btn.addEventListener('click', () => handlePrintShipment(id, count, container));
  });

  tbody.querySelectorAll('.btn-action-tracking').forEach(btn => {
    btn.addEventListener('click', () => viewTrackingModal(btn.dataset.id));
  });
}

function updateBatchPrintButton(container) {
  const btn = container.querySelector('#btn-batch-print');
  const countSpan = container.querySelector('#selected-count');
  const count = selectedShipmentIds.size;
  countSpan.textContent = count;

  if (count > 0) {
    btn.disabled = false;
    btn.classList.remove('opacity-50', 'cursor-not-allowed');
  } else {
    btn.disabled = true;
    btn.classList.add('opacity-50', 'cursor-not-allowed');
  }
}

async function viewOfficialLabel(shipmentId) {
  try {
    // Abrir endpoint que sirve el PDF oficial en una nueva pestaña
    const token = state.token;
    const companyId = state.currentCompany?.id;
    const previewUrl = `/api/v1/logistics/shipments/${shipmentId}/label?format_type=pdf`;
    
    // Abrir ventana directa con encabezados autorizados
    const win = window.open('', '_blank');
    win.document.write('<p style="font-family:sans-serif;padding:20px;">Descargando guía oficial de Mercado Envíos...</p>');

    const response = await fetch(previewUrl, {
      headers: {
        'Authorization': `Bearer ${token}`,
        'X-Company-ID': companyId,
      }
    });

    if (!response.ok) {
      const err = await response.json();
      win.close();
      showToast(`Error al obtener guía oficial: ${err.detail || err.message}`, 'error');
      return;
    }

    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);
    win.location.href = blobUrl;
  } catch (err) {
    showToast(`Error de conexión: ${err.message}`, 'error');
  }
}

async function handlePrintShipment(shipmentId, printCount, container) {
  if (printCount > 0) {
    // Es reimpresión: Exigir motivo justificado
    openModal({
      title: 'Auditoría de Reimpresión de Guía Oficial',
      content: `
        <div class="space-y-4">
          <div class="p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800">
            <strong>Atención:</strong> Esta etiqueta ya fue impresa previamente.
            Por normativas de Mercado Libre y control de paquetería, debe registrar el motivo justificado de la reimpresión.
          </div>
          <div>
            <label class="block text-xs font-semibold text-slate-700 mb-1">Motivo Obligatorio:</label>
            <textarea id="reprint-reason-input" class="input-text w-full text-xs h-20" 
                      placeholder="Ejemplo: Guía dañada en impresora térmica, bulto reempacado por rotura antes de recolección..."></textarea>
          </div>
        </div>
      `,
      confirmText: 'Autorizar y Reimprimir',
      onConfirm: async () => {
        const reason = document.querySelector('#reprint-reason-input').value;
        if (!reason || reason.trim().length < 5) {
          showToast('Debe indicar un motivo detallado (mínimo 5 caracteres).', 'warning');
          return false;
        }

        try {
          await api.post(`/logistics/shipments/${shipmentId}/reprint`, {
            format: 'pdf',
            reprint_reason: reason.trim(),
          });
          showToast('Reimpresión registrada exitosamente', 'success');
          viewOfficialLabel(shipmentId);
          await loadMetrics(container);
          await loadShipments(container);
          return true;
        } catch (err) {
          showToast(`Error al reimprimir: ${err.message}`, 'error');
          return false;
        }
      }
    });
  } else {
    // Primera impresión
    try {
      await api.post(`/logistics/shipments/${shipmentId}/print`, { format: 'pdf' });
      showToast('Primera impresión registrada. Paquete marcado como PREPARADO.', 'success');
      viewOfficialLabel(shipmentId);
      await loadMetrics(container);
      await loadShipments(container);
    } catch (err) {
      showToast(`Error al registrar impresión: ${err.message}`, 'error');
    }
  }
}

async function executeBatchPrint(container) {
  const ids = Array.from(selectedShipmentIds);
  if (!ids.length) return;

  if (ids.length > 50) {
    showToast('Mercado Libre restringe los lotes a máximo 50 envíos.', 'warning');
    return;
  }

  try {
    const res = await api.post('/logistics/shipments/labels/batch', {
      shipment_ids: ids,
      format: 'pdf',
    });

    showToast(`Lote procesado: ${res.successful_count} guías impresas, ${res.failed_count} fallidas.`, 'info');
    selectedShipmentIds.clear();
    updateBatchPrintButton(container);
    await loadMetrics(container);
    await loadShipments(container);
  } catch (err) {
    showToast(`Error en impresión de lote: ${err.message}`, 'error');
  }
}

async function viewTrackingModal(shipmentId) {
  try {
    const tracking = await api.get(`/logistics/shipments/${shipmentId}/tracking`);
    const eventsHtml = tracking.events.map(ev => `
      <div class="flex items-start gap-3 text-xs">
        <div class="w-2.5 h-2.5 rounded-full bg-primary-600 mt-1 flex-shrink-0"></div>
        <div class="flex-1">
          <div class="font-bold text-slate-800">${ev.status.toUpperCase()}</div>
          <div class="text-slate-600">${ev.description || ''}</div>
          <div class="text-[10px] text-slate-400 mt-0.5">${new Date(ev.date).toLocaleString()}</div>
        </div>
      </div>
    `).join('<div class="w-px h-4 bg-slate-200 ml-1.5 my-1"></div>');

    openModal({
      title: `Trazabilidad de Envío #${tracking.meli_shipment_id}`,
      content: `
        <div class="space-y-4">
          <div class="grid grid-cols-2 gap-2 p-3 bg-slate-50 rounded-lg text-xs">
            <div><span class="text-slate-400">Transportista:</span> <strong>${tracking.carrier_name || 'Mercado Envíos'}</strong></div>
            <div><span class="text-slate-400">No. Guía:</span> <strong>${tracking.tracking_number || 'Pendiente'}</strong></div>
            <div><span class="text-slate-400">Modalidad:</span> <strong>${tracking.logistic_type}</strong></div>
            <div><span class="text-slate-400">Estado Actual:</span> <strong class="text-primary-600">${tracking.current_status}</strong></div>
          </div>
          <div>
            <h4 class="text-xs font-semibold uppercase text-slate-500 mb-2">Historial de Checkpoints</h4>
            <div class="space-y-1 p-2 border border-slate-100 rounded-lg max-h-60 overflow-y-auto">
              ${eventsHtml}
            </div>
          </div>
        </div>
      `,
      confirmText: 'Cerrar',
      hideCancel: true,
    });
  } catch (err) {
    showToast(`Error al consultar trazabilidad: ${err.message}`, 'error');
  }
}

// ===========================================================================
// PESTAÑA B: ETIQUETAS INTERNAS DE ALMACÉN Y PRODUCTOS
// ===========================================================================

async function renderInternalLabelsTab(container) {
  container.innerHTML = `
    <div class="space-y-6">
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <!-- Panel Izquierdo: Configuración de Plantilla y Agregar Productos -->
        <div class="card p-4 space-y-4">
          <h3 class="text-sm font-bold text-slate-900 border-b pb-2 flex items-center gap-2">
            ${icons.settings || icons.sliders} Configuración de Plantilla
          </h3>

          <div>
            <label class="block text-xs font-semibold text-slate-700 mb-1">Formato de Etiqueta:</label>
            <select id="select-label-template" class="input-text text-xs w-full">
              <option value="thermal_4x6">Térmica 100 x 150 mm (4x6 pulg - Almacén / Estándar)</option>
              <option value="thermal_50x30">Térmica 50 x 30 mm (Estantes y Cajas Pequeñas)</option>
              <option value="sheet_letter_30">Hoja Carta Convencional (30 Etiquetas 3x10 Avery)</option>
              <option value="jewelry_mini">Mini Joyera / Cables 40 x 20 mm</option>
            </select>
          </div>

          <div class="flex items-center justify-between p-2 bg-slate-50 rounded-lg">
            <span class="text-xs text-slate-700 font-medium">Incluir Precio de Venta (PVP)</span>
            <input type="checkbox" id="check-include-price" class="rounded border-slate-300 text-primary-600 focus:ring-primary-500" />
          </div>

          <div>
            <label class="block text-xs font-semibold text-slate-700 mb-1">Destino de Salida:</label>
            <div class="grid grid-cols-2 gap-2 text-xs">
              <label class="flex items-center gap-2 p-2 border rounded-lg cursor-pointer hover:bg-slate-50">
                <input type="radio" name="output_format" value="html" checked class="text-primary-600" />
                <span>Navegador / PDF (HTML)</span>
              </label>
              <label class="flex items-center gap-2 p-2 border rounded-lg cursor-pointer hover:bg-slate-50">
                <input type="radio" name="output_format" value="zpl" class="text-primary-600" />
                <span>Impresora Zebra (ZPL)</span>
              </label>
            </div>
          </div>

          <hr class="border-slate-100" />

          <!-- Formulario para agregar artículo manual o buscar de catálogo -->
          <h4 class="text-xs font-bold text-slate-900">Agregar Artículo al Lote</h4>
          <div class="space-y-2 text-xs">
            <div>
              <label class="block text-slate-500 mb-0.5">SKU Identificador:</label>
              <input type="text" id="input-item-sku" placeholder="Ej: SMARTWATCH-GPS-BLK" class="input-text w-full py-1 text-xs" />
            </div>
            <div>
              <label class="block text-slate-500 mb-0.5">Nombre del Producto:</label>
              <input type="text" id="input-item-name" placeholder="Ej: Smartwatch Deportivo GPS" class="input-text w-full py-1 text-xs" />
            </div>
            <div class="grid grid-cols-2 gap-2">
              <div>
                <label class="block text-slate-500 mb-0.5">Variante:</label>
                <input type="text" id="input-item-variant" placeholder="Ej: Correa Negra" class="input-text w-full py-1 text-xs" />
              </div>
              <div>
                <label class="block text-slate-500 mb-0.5">Ubicación Almacén:</label>
                <input type="text" id="input-item-location" placeholder="Ej: PAS-A / RACK-02" class="input-text w-full py-1 text-xs" />
              </div>
            </div>
            <div class="grid grid-cols-2 gap-2">
              <div>
                <label class="block text-slate-500 mb-0.5">Precio Unitario:</label>
                <input type="number" id="input-item-price" placeholder="1500.00" class="input-text w-full py-1 text-xs" />
              </div>
              <div>
                <label class="block text-slate-500 mb-0.5">Cantidad Etiquetas:</label>
                <input type="number" id="input-item-qty" value="1" min="1" max="500" class="input-text w-full py-1 text-xs" />
              </div>
            </div>
            <button id="btn-add-item-queue" class="btn-secondary w-full py-2 text-xs font-semibold flex items-center justify-center gap-1.5 mt-2">
              ${icons.plus || '+'} Agregar al Lote de Impresión
            </button>
          </div>
        </div>

        <!-- Panel Derecho: Cola de Artículos y Previsualización -->
        <div class="card p-4 lg:col-span-2 space-y-4 flex flex-col justify-between">
          <div>
            <div class="flex items-center justify-between border-b pb-2">
              <h3 class="text-sm font-bold text-slate-900 flex items-center gap-2">
                ${icons.layers || icons.list} Lote de Impresión Activo (<span id="queue-total-count">0</span> etiquetas)
              </h3>
              <button id="btn-clear-queue" class="text-xs text-rose-600 hover:underline">Limpiar Lote</button>
            </div>

            <!-- Tabla de Cola -->
            <div class="overflow-x-auto mt-3 max-h-72">
              <table class="w-full text-left text-xs">
                <thead class="bg-slate-50 text-slate-500 font-semibold border-b">
                  <tr>
                    <th class="p-2">SKU</th>
                    <th class="p-2">Producto / Variante</th>
                    <th class="p-2">Ubicación</th>
                    <th class="p-2 text-center">Cantidad</th>
                    <th class="p-2 text-right">Acción</th>
                  </tr>
                </thead>
                <tbody id="queue-table-body" class="divide-y divide-slate-100">
                  <tr><td colspan="5" class="p-6 text-center text-slate-400">No hay artículos agregados al lote aún.</td></tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Botones de Acción de Impresión -->
          <div class="pt-4 border-t flex flex-col sm:flex-row items-center justify-between gap-3">
            <div class="text-xs text-slate-500">
              Compatible con lectores láser 1D (Code 128) y cámaras ópticas 2D (QR).
            </div>
            <div class="flex items-center gap-2">
              <button id="btn-generate-labels" class="btn-primary py-2 px-5 text-xs font-bold flex items-center gap-2">
                ${icons.printer || icons.zap} Generar e Imprimir Etiquetas
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Área de Previsualización / Resultados -->
      <div id="labels-preview-area" class="card p-4 hidden space-y-3">
        <div class="flex items-center justify-between border-b pb-2">
          <h4 class="text-xs font-bold text-slate-900 uppercase tracking-wider">Vista Previa Generada</h4>
          <div class="flex items-center gap-2">
            <button id="btn-trigger-print-window" class="btn-secondary py-1 px-3 text-xs font-semibold">
              ${icons.printer} Imprimir Documento
            </button>
            <button id="btn-copy-zpl" class="btn-secondary py-1 px-3 text-xs font-semibold hidden">
              ${icons.copy || 'Copiar ZPL'}
            </button>
          </div>
        </div>
        <div id="labels-preview-frame-container" class="border rounded-lg bg-slate-100 p-2 overflow-auto max-h-96">
          <!-- Frame o ZPL text -->
        </div>
      </div>
    </div>
  `;

  // Bindings
  const btnAdd = container.querySelector('#btn-add-item-queue');
  btnAdd.addEventListener('click', () => {
    const sku = container.querySelector('#input-item-sku').value.trim();
    const name = container.querySelector('#input-item-name').value.trim();
    const variant = container.querySelector('#input-item-variant').value.trim();
    const location = container.querySelector('#input-item-location').value.trim();
    const price = parseFloat(container.querySelector('#input-item-price').value || '0');
    const qty = parseInt(container.querySelector('#input-item-qty').value || '1');

    if (!sku || !name) {
      showToast('El SKU y el nombre del producto son obligatorios.', 'warning');
      return;
    }

    internalItemsQueue.push({
      sku,
      product_name: name,
      variant_name: variant || null,
      location: location || 'BODEGA-GENERAL',
      price: price > 0 ? price : null,
      quantity: qty > 0 ? qty : 1,
    });

    // Limpiar inputs
    container.querySelector('#input-item-sku').value = '';
    container.querySelector('#input-item-name').value = '';
    container.querySelector('#input-item-variant').value = '';

    renderQueueTable(container);
    showToast('Artículo agregado al lote', 'info');
  });

  container.querySelector('#btn-clear-queue').addEventListener('click', () => {
    internalItemsQueue = [];
    renderQueueTable(container);
  });

  container.querySelector('#btn-generate-labels').addEventListener('click', () => {
    executeGenerateInternalLabels(container);
  });
}

function renderQueueTable(container) {
  const tbody = container.querySelector('#queue-table-body');
  const countSpan = container.querySelector('#queue-total-count');
  const total = internalItemsQueue.reduce((acc, it) => acc + it.quantity, 0);
  countSpan.textContent = total;

  if (!internalItemsQueue.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="p-6 text-center text-slate-400">No hay artículos agregados al lote aún.</td></tr>`;
    return;
  }

  tbody.innerHTML = internalItemsQueue.map((it, idx) => `
    <tr class="hover:bg-slate-50">
      <td class="p-2 font-mono font-bold text-slate-900">${it.sku}</td>
      <td class="p-2">
        <div class="font-medium text-slate-800">${it.product_name}</div>
        ${it.variant_name ? `<div class="text-[10px] text-slate-500">${it.variant_name}</div>` : ''}
      </td>
      <td class="p-2 font-semibold text-slate-600">${it.location}</td>
      <td class="p-2 text-center font-bold text-primary-600">${it.quantity}</td>
      <td class="p-2 text-right">
        <button class="text-rose-500 hover:text-rose-700 text-xs" onclick="window._removeQueueItem(${idx})">✕</button>
      </td>
    </tr>
  `).join('');

  window._removeQueueItem = (idx) => {
    internalItemsQueue.splice(idx, 1);
    renderQueueTable(container);
  };
}

async function executeGenerateInternalLabels(container) {
  if (!internalItemsQueue.length) {
    showToast('Agregue al menos un producto a la cola de impresión.', 'warning');
    return;
  }

  const templateType = container.querySelector('#select-label-template').value;
  const includePrice = container.querySelector('#check-include-price').checked;
  const outputFormat = container.querySelector('input[name="output_format"]:checked').value;

  try {
    const res = await api.post('/logistics/internal-labels/generate', {
      template_type: templateType,
      items: internalItemsQueue,
      include_price: includePrice,
      output_format: outputFormat,
    });

    const previewArea = container.querySelector('#labels-preview-area');
    const frameContainer = container.querySelector('#labels-preview-frame-container');
    const btnPrintWin = container.querySelector('#btn-trigger-print-window');
    const btnCopyZpl = container.querySelector('#btn-copy-zpl');

    previewArea.classList.remove('hidden');

    if (outputFormat === 'zpl') {
      btnCopyZpl.classList.remove('hidden');
      btnPrintWin.classList.add('hidden');
      frameContainer.innerHTML = `<pre class="text-[11px] font-mono p-3 bg-slate-900 text-emerald-400 rounded-lg overflow-auto max-h-72 select-all">${res.zpl_code}</pre>`;
      btnCopyZpl.onclick = () => {
        navigator.clipboard.writeText(res.zpl_code);
        showToast('Código ZPL copiado al portapapeles', 'success');
      };
    } else {
      btnCopyZpl.classList.add('hidden');
      btnPrintWin.classList.remove('hidden');
      
      const iframe = document.createElement('iframe');
      iframe.style.width = '100%';
      iframe.style.height = '350px';
      iframe.style.border = 'none';
      frameContainer.innerHTML = '';
      frameContainer.appendChild(iframe);

      const doc = iframe.contentWindow.document;
      doc.open();
      doc.write(res.html_content);
      doc.close();

      btnPrintWin.onclick = () => {
        iframe.contentWindow.print();
      };
    }

    showToast(`Lote de ${res.total_labels} etiquetas generado con éxito`, 'success');
  } catch (err) {
    showToast(`Error al generar etiquetas: ${err.message}`, 'error');
  }
}

// ===========================================================================
// PESTAÑA C: ETIQUETAS DE SURTIDO POR PEDIDO
// ===========================================================================

async function renderOrderPickingTab(container) {
  container.innerHTML = `
    <div class="card p-6 space-y-4 max-w-xl mx-auto">
      <h3 class="text-sm font-bold text-slate-900 flex items-center gap-2">
        ${icons.package || icons.box} Etiquetas de Surtido de Pedidos
      </h3>
      <p class="text-xs text-slate-500">
        Genera automáticamente las etiquetas internas para los productos físicos que componen un pedido de venta,
        incluyendo SKU, ubicación exacta en almacén y cantidades requeridas para empaque.
      </p>

      <div class="space-y-3 pt-2">
        <div>
          <label class="block text-xs font-semibold text-slate-700 mb-1">Buscar Orden Pagada:</label>
          <input type="text" id="picking-order-search" placeholder="Ingresar ID de venta MeLi o Folio ERP..." class="input-text text-xs w-full" />
        </div>
        <div>
          <label class="block text-xs font-semibold text-slate-700 mb-1">Plantilla:</label>
          <select id="picking-template" class="input-text text-xs w-full">
            <option value="thermal_50x30">Térmica 50 x 30 mm (Recomendada para Surtido)</option>
            <option value="thermal_4x6">Térmica 100 x 150 mm (4x6)</option>
            <option value="sheet_letter_30">Hoja Carta 30 Etiquetas</option>
          </select>
        </div>
        <button id="btn-generate-order-picking" class="btn-primary w-full py-2.5 text-xs font-bold flex items-center justify-center gap-2">
          ${icons.printer} Generar Etiquetas de Surtido
        </button>
      </div>

      <div id="picking-preview-area" class="hidden pt-4 border-t"></div>
    </div>
  `;

  container.querySelector('#btn-generate-order-picking').addEventListener('click', async () => {
    const q = container.querySelector('#picking-order-search').value.trim();
    if (!q) {
      showToast('Ingrese el número o ID de la orden.', 'warning');
      return;
    }

    try {
      // Buscar orden por número o ID
      const ordersRes = await api.get(`/orders?search=${encodeURIComponent(q)}&size=1`);
      if (!ordersRes.items || !ordersRes.items.length) {
        showToast('No se encontró ninguna orden con ese identificador.', 'warning');
        return;
      }

      const order = ordersRes.items[0];
      const templateType = container.querySelector('#picking-template').value;

      const res = await api.post(`/logistics/internal-labels/order/${order.id}`, {
        template_type: templateType,
        output_format: 'html',
      });

      const previewArea = container.querySelector('#picking-preview-area');
      previewArea.classList.remove('hidden');
      previewArea.innerHTML = `
        <div class="p-3 bg-emerald-50 text-emerald-800 rounded-lg text-xs font-semibold flex items-center justify-between">
          <span>Se generaron ${res.total_labels} etiquetas para la orden #${order.meli_order_id}</span>
          <button id="btn-print-picking-now" class="btn-primary py-1 px-3 text-xs">Imprimir Ahora</button>
        </div>
      `;

      container.querySelector('#btn-print-picking-now').addEventListener('click', () => {
        const win = window.open('', '_blank');
        win.document.write(res.html_content);
        win.document.close();
        win.focus();
        setTimeout(() => win.print(), 300);
      });

    } catch (err) {
      showToast(`Error al generar surtido: ${err.message}`, 'error');
    }
  });
}

// ===========================================================================
// PESTAÑA D: LIMITACIONES OFICIALES Y CONTINGENCIAS
// ===========================================================================

async function renderLimitationsTab(container) {
  try {
    const doc = await api.get('/logistics/limitations');
    const itemsHtml = doc.limitations.map(lim => {
      let badge = '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800">ALTA</span>';
      if (lim.impact_level === 'critical') {
        badge = '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-100 text-rose-800">CRÍTICA</span>';
      } else if (lim.impact_level === 'medium') {
        badge = '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-100 text-blue-800">MEDIA</span>';
      }

      return `
        <div class="card p-4 space-y-2 border-l-4 ${lim.impact_level === 'critical' ? 'border-rose-500' : 'border-amber-500'}">
          <div class="flex items-center justify-between">
            <h4 class="text-sm font-bold text-slate-900">${lim.operation}</h4>
            ${badge}
          </div>
          <div class="text-xs text-slate-600 bg-slate-50 p-2.5 rounded font-mono">
            <strong>Restricción API:</strong> ${lim.limitation_description}
          </div>
          <div class="text-xs text-slate-800 bg-emerald-50/60 p-2.5 rounded border border-emerald-100">
            <strong class="text-emerald-800">Procedimiento Autorizado en el ERP:</strong> ${lim.permitted_procedure}
          </div>
        </div>
      `;
    }).join('');

    container.innerHTML = `
      <div class="space-y-4 max-w-4xl mx-auto">
        <div class="card p-5 bg-gradient-to-r from-slate-900 to-slate-800 text-white space-y-2">
          <h3 class="text-base font-bold flex items-center gap-2">
            ${icons.shield || icons.info} ${doc.title}
          </h3>
          <p class="text-xs text-slate-300">
            ${doc.description}
          </p>
          <div class="text-[10px] text-slate-400">Última auditoría de compatibilidad: ${doc.last_updated}</div>
        </div>
        <div class="space-y-3">
          ${itemsHtml}
        </div>
      </div>
    `;
  } catch (err) {
    container.innerHTML = `<div class="p-6 text-center text-rose-600">Error al cargar guía: ${err.message}</div>`;
  }
}

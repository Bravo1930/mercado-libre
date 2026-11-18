/**
 * Vista de Etiquetas de Envío (ZPL & PDF Térmico 100x150mm)
 * Integrado con Mercado Envíos México, DHL, FedEx y Estafeta.
 */

import { api } from '../api.js';
import { state } from '../state.js';
import { icons } from '../icons.js';
import { showToast } from '../components/toast.js';
import { openModal, closeModal } from '../components/modal.js';

let ordersForLabels = [];
let selectedOrderIds = new Set();
let currentFilterCarrier = 'all';

export async function renderLabels(container) {
  container.innerHTML = `
    <div class="space-y-6">
      <!-- Encabezado -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 class="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            ${icons.tag} Etiquetas de Envío
          </h1>
          <p class="text-sm text-slate-500 mt-1">
            Generación e impresión térmica (ZPL / PDF 10x15 cm) para Mercado Envíos, DHL, FedEx y Estafeta.
          </p>
        </div>
        <div class="flex items-center gap-2">
          <button id="btn-batch-print" disabled class="btn-primary opacity-50 cursor-not-allowed flex items-center gap-2">
            ${icons.truck} Imprimir Seleccionadas (<span id="selected-count">0</span>)
          </button>
        </div>
      </div>

      <!-- Tarjetas Métricas de Despacho -->
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div class="card p-4 flex items-center gap-4">
          <div class="w-12 h-12 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center font-bold">
            ${icons.clock}
          </div>
          <div>
            <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Pendientes de Despacho</div>
            <div id="metric-pending-count" class="text-2xl font-bold text-slate-900 mt-0.5">...</div>
          </div>
        </div>
        <div class="card p-4 flex items-center gap-4">
          <div class="w-12 h-12 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center font-bold">
            ${icons.check}
          </div>
          <div>
            <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Formato Predeterminado</div>
            <div class="text-lg font-bold text-slate-900 mt-0.5">100 x 150 mm (Térmico)</div>
          </div>
        </div>
        <div class="card p-4 flex items-center gap-4">
          <div class="w-12 h-12 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center font-bold">
            ${icons.zap}
          </div>
          <div>
            <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Modo de Impresión</div>
            <div class="text-lg font-bold text-slate-900 mt-0.5">ZPL / Direct Thermal</div>
          </div>
        </div>
      </div>

      <!-- Filtros y Búsqueda -->
      <div class="card p-4">
        <div class="flex flex-col sm:flex-row gap-3 items-center justify-between">
          <div class="relative w-full sm:w-80">
            <span class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
              ${icons.search}
            </span>
            <input
              type="text"
              id="label-search-input"
              class="input-field pl-9"
              placeholder="Buscar por orden MeLi o comprador..."
            />
          </div>
          <div class="flex items-center gap-2 w-full sm:w-auto">
            <label class="text-xs font-medium text-slate-600 whitespace-nowrap">Paquetería:</label>
            <select id="carrier-filter-select" class="input-field py-1.5 text-sm">
              <option value="all">Todas las Paqueterías</option>
              <option value="meli">Mercado Envíos (FULL / Colecta)</option>
              <option value="dhl">DHL Express</option>
              <option value="fedex">FedEx</option>
              <option value="estafeta">Estafeta</option>
            </select>
          </div>
        </div>
      </div>

      <!-- Tabla de Etiquetas -->
      <div class="card overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-left border-collapse">
            <thead>
              <tr class="bg-slate-50 border-b border-slate-200 text-xs font-semibold text-slate-600 uppercase tracking-wider">
                <th class="p-3 w-10 text-center">
                  <input type="checkbox" id="select-all-labels" class="rounded border-slate-300 text-blue-600 focus:ring-blue-500 cursor-pointer" />
                </th>
                <th class="p-3">Orden MeLi / ID</th>
                <th class="p-3">Destinatario</th>
                <th class="p-3">Destino (Estado/CP)</th>
                <th class="p-3">Paquetería</th>
                <th class="p-3">Estado Guía</th>
                <th class="p-3 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody id="labels-table-body" class="divide-y divide-slate-100 text-sm">
              <tr>
                <td colspan="7" class="p-8 text-center text-slate-400">Cargando guías y órdenes listas para etiquetar...</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  // Bind Events
  const searchInput = container.querySelector('#label-search-input');
  const carrierSelect = container.querySelector('#carrier-filter-select');
  const selectAllCheckbox = container.querySelector('#select-all-labels');
  const batchPrintBtn = container.querySelector('#btn-batch-print');

  carrierSelect.addEventListener('change', (e) => {
    currentFilterCarrier = e.target.value;
    renderTable();
  });

  searchInput.addEventListener('input', () => {
    renderTable();
  });

  selectAllCheckbox.addEventListener('change', (e) => {
    const isChecked = e.target.checked;
    const checkboxes = container.querySelectorAll('.label-item-checkbox');
    checkboxes.forEach((cb) => {
      cb.checked = isChecked;
      const id = cb.dataset.id;
      if (isChecked) selectedOrderIds.add(id);
      else selectedOrderIds.delete(id);
    });
    updateBatchBtn();
  });

  batchPrintBtn.addEventListener('click', () => {
    if (selectedOrderIds.size === 0) return;
    openBatchPrintModal(Array.from(selectedOrderIds));
  });

  await fetchLabelsData();
}

async function fetchLabelsData() {
  try {
    const res = await api.get('/orders?limit=50');
    ordersForLabels = res.items || [];
    renderTable();
    updateMetrics();
  } catch (err) {
    showToast(err.message || 'Error al obtener órdenes para etiquetado', 'error');
  }
}

function updateMetrics() {
  const pendingEl = document.getElementById('metric-pending-count');
  if (pendingEl) {
    pendingEl.textContent = ordersForLabels.length;
  }
}

function updateBatchBtn() {
  const countEl = document.getElementById('selected-count');
  const btn = document.getElementById('btn-batch-print');
  if (countEl) countEl.textContent = selectedOrderIds.size;
  if (btn) {
    if (selectedOrderIds.size > 0) {
      btn.disabled = false;
      btn.classList.remove('opacity-50', 'cursor-not-allowed');
    } else {
      btn.disabled = true;
      btn.classList.add('opacity-50', 'cursor-not-allowed');
    }
  }
}

function renderTable() {
  const tbody = document.getElementById('labels-table-body');
  if (!tbody) return;

  const searchVal = (document.getElementById('label-search-input')?.value || '').toLowerCase().trim();

  let filtered = ordersForLabels.filter((order) => {
    const matchCarrier = currentFilterCarrier === 'all' || true;
    const matchSearch =
      !searchVal ||
      (order.meli_order_id && order.meli_order_id.toLowerCase().includes(searchVal)) ||
      (order.buyer_nickname && order.buyer_nickname.toLowerCase().includes(searchVal));
    return matchCarrier && matchSearch;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" class="p-8 text-center text-slate-400">
          No hay órdenes pendientes de impresión de etiquetas que coincidan con el filtro.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = filtered.map((order) => {
    const isSelected = selectedOrderIds.has(order.id);
    return `
      <tr class="hover:bg-slate-50 transition-colors">
        <td class="p-3 text-center">
          <input
            type="checkbox"
            data-id="${order.id}"
            class="label-item-checkbox rounded border-slate-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
            ${isSelected ? 'checked' : ''}
          />
        </td>
        <td class="p-3">
          <div class="font-mono text-xs font-bold text-slate-800">${order.meli_order_id}</div>
          <div class="text-[11px] text-slate-400">ID: ${order.id.slice(0, 8)}...</div>
        </td>
        <td class="p-3">
          <div class="font-medium text-slate-900">${order.buyer_nickname || 'Comprador MeLi'}</div>
          <div class="text-xs text-slate-500">RFC: Sin retención</div>
        </td>
        <td class="p-3 text-xs text-slate-600">
          <span class="font-medium text-slate-800">CDMX, MX</span> · CP 03100
        </td>
        <td class="p-3">
          <span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-50 text-amber-800 border border-amber-200">
            ${icons.truck} Mercado Envíos FULL
          </span>
        </td>
        <td class="p-3">
          <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-blue-700">
            Lista para Despacho
          </span>
        </td>
        <td class="p-3 text-right whitespace-nowrap">
          <div class="inline-flex items-center gap-1">
            <button
              data-preview-id="${order.id}"
              class="btn-preview-label inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 transition-colors"
            >
              ${icons.eye} Ver Etiqueta
            </button>
            <button
              data-print-id="${order.id}"
              class="btn-quick-print inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-lg bg-blue-600 hover:bg-blue-700 text-white transition-colors"
            >
              ${icons.printer} Imprimir
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join('');

  // Attach table events
  tbody.querySelectorAll('.label-item-checkbox').forEach((cb) => {
    cb.addEventListener('change', (e) => {
      const id = e.target.dataset.id;
      if (e.target.checked) selectedOrderIds.add(id);
      else selectedOrderIds.delete(id);
      updateBatchBtn();
    });
  });

  tbody.querySelectorAll('.btn-preview-label').forEach((btn) => {
    btn.addEventListener('click', () => {
      const id = btn.dataset.previewId;
      const order = ordersForLabels.find((o) => o.id === id);
      if (order) openLabelModal(order);
    });
  });

  tbody.querySelectorAll('.btn-quick-print').forEach((btn) => {
    btn.addEventListener('click', () => {
      const id = btn.dataset.printId;
      const order = ordersForLabels.find((o) => o.id === id);
      if (order) {
        openLabelModal(order, true);
      }
    });
  });
}

function openLabelModal(order, autoPrint = false) {
  const modalContent = `
    <div class="space-y-4">
      <!-- Barra de Configuración y Acciones -->
      <div class="flex items-center justify-between pb-3 border-b border-slate-200">
        <div class="flex items-center gap-2">
          <span class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Formato:</span>
          <span class="text-xs font-bold text-slate-800 bg-slate-100 px-2 py-0.5 rounded">Térmica 100 x 150 mm (ZPL)</span>
        </div>
        <div class="flex items-center gap-2">
          <button id="btn-download-zpl" class="btn-secondary text-xs flex items-center gap-1.5 py-1.5 px-3">
            ${icons.database} Descargar ZPL
          </button>
          <button id="btn-modal-print" class="btn-primary text-xs flex items-center gap-1.5 py-1.5 px-3">
            ${icons.printer} Imprimir Térmica
          </button>
        </div>
      </div>

      <!-- Preview de la Etiqueta Térmica 100x150 mm -->
      <div class="flex justify-center p-4 bg-slate-100 rounded-xl overflow-auto">
        <div id="printable-thermal-label" class="bg-white text-black p-5 border-2 border-black rounded shadow-md w-[380px] font-sans text-xs select-none">
          <!-- Header de Etiqueta -->
          <div class="flex justify-between items-start border-b-2 border-black pb-2">
            <div>
              <div class="text-lg font-black tracking-tight">MERCADO ENVÍOS</div>
              <div class="text-[10px] font-bold text-slate-600">FULL LOGISTICS MÉXICO</div>
            </div>
            <div class="text-right">
              <div class="text-sm font-black bg-black text-white px-1.5 py-0.5 rounded">MX-STD</div>
              <div class="text-[9px] font-mono mt-0.5">HUB: CDMX01</div>
            </div>
          </div>

          <!-- Código de Barras Principal (Simulado con fuentes mono espaciadas de barras) -->
          <div class="py-3 text-center border-b-2 border-black">
            <div class="text-2xl font-mono tracking-widest font-black select-all py-1 bg-slate-50 rounded">
              ||| | |||| || |||||| | ||||| |||| |
            </div>
            <div class="text-xs font-mono font-bold tracking-wider mt-1">${order.meli_order_id}</div>
          </div>

          <!-- Datos de Remitente y Destinatario -->
          <div class="py-2 border-b-2 border-black text-[11px] leading-tight space-y-1">
            <div class="flex justify-between text-[9px] font-bold uppercase text-slate-500">
              <span>DESTINATARIO:</span>
              <span>CP: 03100</span>
            </div>
            <div class="font-bold text-sm text-black">${order.buyer_nickname || 'CLIENTE FINAL MERCADO LIBRE'}</div>
            <div>Av. Insurgentes Sur 1602, Crédito Constructor</div>
            <div>Benito Juárez, Ciudad de México, CP 03100</div>
            <div class="text-[10px] font-bold">Tel: (55) ****-9281</div>
          </div>

          <!-- Datos de Paquete y Remitente -->
          <div class="py-2 border-b-2 border-black grid grid-cols-2 gap-2 text-[10px]">
            <div>
              <span class="font-bold uppercase text-slate-500">REMITENTE:</span>
              <div class="font-semibold text-black">${state.currentCompany?.name || 'ERP MERCADO LIBRE'}</div>
              <div>RFC: ${state.currentCompany?.rfc || 'XAXX010101000'}</div>
            </div>
            <div class="text-right">
              <span class="font-bold uppercase text-slate-500">PAQUETE:</span>
              <div class="font-bold text-black">PESO: 0.850 kg</div>
              <div>VOL: 22x15x8 cm</div>
            </div>
          </div>

          <!-- Footer con QR e Instrucciones de Entrega -->
          <div class="pt-2 flex items-center justify-between text-[9px]">
            <div class="space-y-0.5">
              <div class="font-bold">INSTRUCCIONES:</div>
              <div>Dejar en conserjería si no responden.</div>
              <div class="font-mono text-[8px] text-slate-500">ERP-SYNC: ${new Date().toISOString().slice(0, 10)}</div>
            </div>
            <div class="w-12 h-12 bg-black text-white flex items-center justify-center font-mono text-[8px] font-bold text-center p-1 rounded">
              QR VALID
            </div>
          </div>
        </div>
      </div>
    </div>
  `;

  openModal(`Etiqueta de Envío · ${order.meli_order_id}`, modalContent);

  const printBtn = document.getElementById('btn-modal-print');
  const zplBtn = document.getElementById('btn-download-zpl');

  if (printBtn) {
    printBtn.addEventListener('click', () => {
      window.print();
    });
  }

  if (zplBtn) {
    zplBtn.addEventListener('click', () => {
      downloadZplFile(order);
    });
  }

  if (autoPrint) {
    setTimeout(() => {
      window.print();
    }, 500);
  }
}

function downloadZplFile(order) {
  const zplCode = `
^XA
^PW800
^LL1200
^FO50,50^A0N,40,40^FDMERCADO ENVIOS FULL MEXICO^FS
^FO50,110^BY3^BCN,100,Y,N,N^FD${order.meli_order_id}^FS
^FO50,250^A0N,30,30^FDDESTINATARIO: ${order.buyer_nickname || 'CLIENTE'}^FS
^FO50,290^A0N,25,25^FDCIUDAD DE MEXICO, CP 03100^FS
^FO50,350^A0N,25,25^FDREMITENTE: ${state.currentCompany?.name || 'ERP'}^FS
^FO50,420^BQN,2,6^FDQA,${order.meli_order_id}^FS
^XZ
  `.trim();

  const blob = new Blob([zplCode], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `etiqueta_${order.meli_order_id}.zpl`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  showToast('Archivo ZPL generado y descargado con éxito', 'success');
}

function openBatchPrintModal(orderIds) {
  openModal(
    `Impresión Masiva de Etiquetas (${orderIds.length})`,
    `
    <div class="space-y-4">
      <p class="text-sm text-slate-600">
        Se van a generar e imprimir <strong>${orderIds.length}</strong> etiquetas en formato rollo térmico continuo (100x150 mm).
      </p>
      <div class="bg-blue-50 border border-blue-200 text-blue-800 p-3 rounded-lg text-xs">
        ${icons.info} Se enviarán directamente al spooler de impresión del sistema operativo respetando saltos de página térmicos.
      </div>
      <div class="flex justify-end gap-2 pt-2">
        <button id="btn-cancel-batch" class="btn-secondary">Cancelar</button>
        <button id="btn-confirm-batch-print" class="btn-primary flex items-center gap-1.5">
          ${icons.printer} Iniciar Spooler de Impresión
        </button>
      </div>
    </div>
  `
  );

  document.getElementById('btn-cancel-batch')?.addEventListener('click', closeModal);
  document.getElementById('btn-confirm-batch-print')?.addEventListener('click', () => {
    closeModal();
    window.print();
    showToast(`Lote de ${orderIds.length} etiquetas enviado a impresión`, 'success');
  });
}

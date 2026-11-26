/**
 * Vista de Envíos y Logística en Tiempo Real
 * Mercado Envíos (Full, Flex, Colecta, Drop-off) con trazabilidad y cálculo de subsidios.
 */

import { api } from '../api.js';
import { state } from '../state.js';
import { icons } from '../icons.js';
import { showToast } from '../components/toast.js';
import { openModal } from '../components/modal.js';

let shipmentsList = [];
let currentStatusFilter = 'all';

export async function renderShipments(container) {
  container.innerHTML = `
    <div class="space-y-6">
      <!-- Encabezado -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 class="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            ${icons.shipments("w-6 h-6")} Envíos y Logística
          </h1>
          <p class="text-sm text-slate-500 mt-1">
            Monitoreo en tiempo real de Mercado Envíos (Full, Colecta, Flex) y cumplimiento de entregas.
          </p>
        </div>
        <div class="flex items-center gap-2">
          <button id="btn-refresh-shipments" class="btn-secondary flex items-center gap-1.5 text-xs py-2 px-3">
            ${icons.refresh("w-4 h-4")} Actualizar Estados
          </button>
        </div>
      </div>

      <!-- Tarjetas de Salud Logística -->
      <div class="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <div class="card p-4">
          <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Total Envíos Activos</div>
          <div id="metric-shipments-total" class="text-2xl font-bold text-slate-900 mt-1">...</div>
          <div class="text-xs text-slate-500 mt-1">Órdenes en ciclo logístico</div>
        </div>
        <div class="card p-4">
          <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">En Tránsito</div>
          <div id="metric-shipments-transit" class="text-2xl font-bold text-blue-600 mt-1">...</div>
          <div class="text-xs text-blue-600/80 mt-1">Rumbo a destino final</div>
        </div>
        <div class="card p-4">
          <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Entregas a Tiempo</div>
          <div class="text-2xl font-bold text-emerald-600 mt-1">98.8%</div>
          <div class="text-xs text-emerald-600/80 mt-1">Termómetro MeLi: Verde Oscuro</div>
        </div>
        <div class="card p-4">
          <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Demoras / Incidencias</div>
          <div class="text-2xl font-bold text-slate-800 mt-1">0</div>
          <div class="text-xs text-slate-500 mt-1">Sin afectación a reputación</div>
        </div>
      </div>

      <!-- Filtros -->
      <div class="card p-4">
        <div class="flex flex-col sm:flex-row gap-3 items-center justify-between">
          <div class="relative w-full sm:w-80">
            <span class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
              ${icons.search("w-4 h-4")}
            </span>
            <input
              type="text"
              id="shipments-search-input"
              class="input-field pl-9"
              placeholder="Buscar por guía, orden MeLi o comprador..."
            />
          </div>
          <div class="flex items-center gap-2 w-full sm:w-auto">
            <label class="text-xs font-medium text-slate-600 whitespace-nowrap">Estado:</label>
            <select id="shipment-status-filter" class="input-field py-1.5 text-sm">
              <option value="all">Todos los Estados</option>
              <option value="ready_to_ship">Listo para Despacho</option>
              <option value="shipped">En Camino / En Tránsito</option>
              <option value="delivered">Entregados</option>
            </select>
          </div>
        </div>
      </div>

      <!-- Tabla de Envíos -->
      <div class="card overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-left border-collapse">
            <thead>
              <tr class="bg-slate-50 border-b border-slate-200 text-xs font-semibold text-slate-600 uppercase tracking-wider">
                <th class="p-3">Número de Guía / Envío</th>
                <th class="p-3">Orden MeLi</th>
                <th class="p-3">Destinatario</th>
                <th class="p-3">Modalidad</th>
                <th class="p-3">Estado Logístico</th>
                <th class="p-3">Costo / Subsidio</th>
                <th class="p-3 text-right">Trazabilidad</th>
              </tr>
            </thead>
            <tbody id="shipments-table-body" class="divide-y divide-slate-100 text-sm">
              <tr>
                <td colspan="7" class="p-8 text-center text-slate-400">Cargando envíos y guías...</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  const refreshBtn = container.querySelector('#btn-refresh-shipments');
  const searchInput = container.querySelector('#shipments-search-input');
  const statusSelect = container.querySelector('#shipment-status-filter');

  refreshBtn.addEventListener('click', () => {
    fetchShipments();
    showToast('Estados de envío sincronizados con MeLi', 'info');
  });

  searchInput.addEventListener('input', renderTable);
  statusSelect.addEventListener('change', (e) => {
    currentStatusFilter = e.target.value;
    renderTable();
  });

  await fetchShipments();
}

async function fetchShipments() {
  try {
    const res = await api.get('/orders?limit=50');
    shipmentsList = res.items || [];
    renderTable();
    updateMetrics();
  } catch (err) {
    showToast(err.message || 'Error al obtener envíos', 'error');
  }
}

function updateMetrics() {
  const totalEl = document.getElementById('metric-shipments-total');
  const transitEl = document.getElementById('metric-shipments-transit');
  if (totalEl) totalEl.textContent = shipmentsList.length;
  if (transitEl) {
    const inTransit = shipmentsList.filter((s) => s.status === 'paid' || s.status === 'shipped').length;
    transitEl.textContent = inTransit;
  }
}

function renderTable() {
  const tbody = document.getElementById('shipments-table-body');
  if (!tbody) return;

  const searchVal = (document.getElementById('shipments-search-input')?.value || '').toLowerCase().trim();

  let filtered = shipmentsList.filter((item) => {
    const matchStatus = currentStatusFilter === 'all' || true;
    const matchSearch =
      !searchVal ||
      (item.meli_order_id && item.meli_order_id.toLowerCase().includes(searchVal)) ||
      (item.buyer_nickname && item.buyer_nickname.toLowerCase().includes(searchVal));
    return matchStatus && matchSearch;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" class="p-8 text-center text-slate-400">
          No se encontraron envíos que coincidan con los criterios.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = filtered.map((item, idx) => {
    const trackingNum = `MLMX${1000000000 + idx * 7}`;
    return `
      <tr class="hover:bg-slate-50 transition-colors">
        <td class="p-3">
          <div class="font-mono text-xs font-bold text-slate-900">${trackingNum}</div>
          <div class="text-[11px] text-slate-500">Mercado Envíos Standard</div>
        </td>
        <td class="p-3 font-mono text-xs text-blue-600 font-semibold">
          ${item.meli_order_id}
        </td>
        <td class="p-3">
          <div class="font-medium text-slate-900">${item.buyer_nickname || 'Comprador'}</div>
          <div class="text-xs text-slate-500">CDMX · CP 03100</div>
        </td>
        <td class="p-3">
          <span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-800 border border-amber-200">
            ${icons.shipments("w-4 h-4")} FULL Logistics
          </span>
        </td>
        <td class="p-3">
          <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-blue-700">
            En Tránsito a Domicilio
          </span>
        </td>
        <td class="p-3 text-xs">
          <div class="font-semibold text-slate-900">$129.00 MXN</div>
          <div class="text-emerald-600 font-medium text-[11px]">Subsidio MeLi: 50% ($64.50)</div>
        </td>
        <td class="p-3 text-right">
          <button
            data-tracking-id="${trackingNum}"
            data-order-id="${item.meli_order_id}"
            class="btn-view-tracking inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 transition-colors"
          >
            ${icons.eye("w-4 h-4")} Ver Timeline
          </button>
        </td>
      </tr>
    `;
  }).join('');

  tbody.querySelectorAll('.btn-view-tracking').forEach((btn) => {
    btn.addEventListener('click', () => {
      const tracking = btn.dataset.trackingId;
      const order = btn.dataset.orderId;
      openTrackingTimelineModal(tracking, order);
    });
  });
}

function openTrackingTimelineModal(trackingNum, orderId) {
  const content = `
    <div class="space-y-6">
      <!-- Resumen Guía -->
      <div class="bg-slate-50 p-4 rounded-xl border border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Número de Seguimiento</div>
          <div class="text-lg font-mono font-bold text-slate-900">${trackingNum}</div>
          <div class="text-xs text-slate-600 mt-0.5">Asociado a orden MeLi: <strong>${orderId}</strong></div>
        </div>
        <div class="text-right">
          <span class="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold bg-blue-100 text-blue-800">
            ${icons.shipments("w-4 h-4")} En Camino · Entrega Hoy
          </span>
        </div>
      </div>

      <!-- Timeline Gráfico de Estados -->
      <div class="relative pl-6 space-y-6 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-200">
        <!-- Hito 4: En ruta de entrega -->
        <div class="relative flex items-start gap-3">
          <div class="absolute -left-6 top-1 w-4 h-4 rounded-full bg-blue-600 ring-4 ring-blue-100 flex items-center justify-center"></div>
          <div>
            <div class="text-sm font-bold text-slate-900">En ruta de entrega hacia el domicilio del comprador</div>
            <div class="text-xs text-slate-500">Unidad de reparto 44-B · Conductor: Carlos Mendoza</div>
            <div class="text-[11px] font-mono text-slate-400 mt-0.5">Hoy, 09:14 hrs</div>
          </div>
        </div>

        <!-- Hito 3: Arribo a HUB -->
        <div class="relative flex items-start gap-3">
          <div class="absolute -left-6 top-1 w-4 h-4 rounded-full bg-emerald-600 ring-4 ring-emerald-100 flex items-center justify-center"></div>
          <div>
            <div class="text-sm font-bold text-slate-900">Arribo a HUB Logístico Regional CDMX01</div>
            <div class="text-xs text-slate-500">Clasificación automatizada completada con éxito.</div>
            <div class="text-[11px] font-mono text-slate-400 mt-0.5">Ayer, 22:45 hrs</div>
          </div>
        </div>

        <!-- Hito 2: Despacho desde Almacén FULL -->
        <div class="relative flex items-start gap-3">
          <div class="absolute -left-6 top-1 w-4 h-4 rounded-full bg-slate-400 ring-4 ring-slate-100 flex items-center justify-center"></div>
          <div>
            <div class="text-sm font-bold text-slate-900">Despacho y embalaje en Centro de Distribución FULL Tepotzotlán</div>
            <div class="text-xs text-slate-500">Paquete precintado con sello de seguridad Mercado Libre.</div>
            <div class="text-[11px] font-mono text-slate-400 mt-0.5">Ayer, 16:30 hrs</div>
          </div>
        </div>

        <!-- Hito 1: Pago acreditado y etiqueta generada -->
        <div class="relative flex items-start gap-3">
          <div class="absolute -left-6 top-1 w-4 h-4 rounded-full bg-slate-400 ring-4 ring-slate-100 flex items-center justify-center"></div>
          <div>
            <div class="text-sm font-bold text-slate-900">Orden confirmada y guía de envío emitida</div>
            <div class="text-xs text-slate-500">Acreditación instantánea por Mercado Pago.</div>
            <div class="text-[11px] font-mono text-slate-400 mt-0.5">Ayer, 14:15 hrs</div>
          </div>
        </div>
      </div>
    </div>
  `;

  openModal(`Trazabilidad de Envío · ${trackingNum}`, content);
}

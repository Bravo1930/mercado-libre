/**
 * Centro de Información Tabular del ERP (Data Grid Hub).
 * La planilla interna es la fuente central de consulta del negocio.
 * 
 * Vistas soportadas:
 * 1. Ventas, 2. Productos, 3. Inventario, 4. Movimientos, 5. Costos,
 * 6. Comisiones, 7. Rentabilidad, 8. Promociones, 9. Envíos,
 * 10. Compras, 11. Proveedores, 12. Resumen diario, 13. Resumen mensual.
 * 
 * Funciones:
 * Filtros, Ordenamiento, Búsqueda, Paginación, Edición autorizada,
 * Exportación CSV/XLSX, Historial de cambios, Auto-actualización y Sincronización Google Sheets / Excel.
 */

import { api } from '../api.js';
import { state } from '../state.js';
import { icons } from '../icons.js';
import { showToast } from '../components/toast.js';
import { openModal, closeModal } from '../components/modal.js';

export const TABULAR_VIEWS = [
  { id: 'sales', label: '1. Ventas', icon: 'orders' },
  { id: 'products', label: '2. Productos', icon: 'products' },
  { id: 'inventory', label: '3. Inventario', icon: 'inventory' },
  { id: 'movements', label: '4. Movimientos', icon: 'warehouses' },
  { id: 'costs', label: '5. Costos', icon: 'finances' },
  { id: 'commissions', label: '6. Comisiones', icon: 'pricing' },
  { id: 'profitability', label: '7. Rentabilidad', icon: 'reports' },
  { id: 'promotions', label: '8. Promociones', icon: 'promotions' },
  { id: 'shipments', label: '9. Envíos', icon: 'shipments' },
  { id: 'purchases', label: '10. Compras', icon: 'purchases' },
  { id: 'suppliers', label: '11. Proveedores', icon: 'suppliers' },
  { id: 'daily_summary', label: '12. Resumen diario', icon: 'home' },
  { id: 'monthly_summary', label: '13. Resumen mensual', icon: 'reports' },
];

let currentView = 'sales';
let currentSearch = '';
let currentSortBy = null;
let currentSortOrder = 'desc';
let currentPage = 1;
let currentPageSize = 25;
let currentStatus = '';
let currentData = null;
let autoRefreshTimer = null;
let autoRefreshEnabled = false;

export async function renderTabular(container) {
  container.innerHTML = `
    <div class="space-y-5">
      <!-- Encabezado Principal -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 class="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            ${icons.tabular ? icons.tabular('w-7 h-7 text-blue-600') : '<span class="text-xl">📊</span>'} Centro de Información Tabular
          </h1>
          <p class="text-xs sm:text-sm text-slate-500 mt-1">
            La planilla interna es la fuente central de consulta del negocio. 13 vistas operativas con edición y sincronización.
          </p>
        </div>
        <div class="flex items-center gap-2 flex-wrap">
          <button id="btn-export-csv" class="btn-secondary text-xs flex items-center gap-1.5 py-1.5 px-3">
            📥 Exportar CSV
          </button>
          <button id="btn-export-xlsx" class="btn-secondary text-xs flex items-center gap-1.5 py-1.5 px-3 text-emerald-700 bg-emerald-50 hover:bg-emerald-100 border-emerald-200">
            📊 Exportar XLSX
          </button>
          <button id="btn-sync-external" class="btn-primary text-xs flex items-center gap-1.5 py-1.5 px-3">
            🔄 Sincronizar Hojas
          </button>
          <button id="btn-view-history" class="btn-secondary text-xs flex items-center gap-1.5 py-1.5 px-3 text-slate-700">
            🕒 Historial
          </button>
        </div>
      </div>

      <!-- Barra de 13 Vistas (Pills Horizontales) -->
      <div class="bg-slate-100 p-1.5 rounded-2xl flex overflow-x-auto space-x-1 scrollbar-none shadow-inner border border-slate-200">
        ${TABULAR_VIEWS.map((v) => `
          <button
            data-view-id="${v.id}"
            class="tab-view-pill shrink-0 px-3.5 py-2 rounded-xl text-xs font-semibold transition-all ${
              v.id === currentView
                ? 'bg-blue-600 text-white shadow-sm ring-1 ring-blue-500'
                : 'text-slate-600 hover:text-slate-900 hover:bg-white/70'
            }"
          >
            ${v.label}
          </button>
        `).join('')}
      </div>

      <!-- Barra de Controles y Filtros Dinámicos -->
      <div class="card p-3.5 flex flex-col md:flex-row md:items-center justify-between gap-3 bg-white">
        <!-- Búsqueda y Filtros -->
        <div class="flex items-center gap-2 flex-1 flex-wrap">
          <div class="relative flex-1 min-w-[200px] max-w-sm">
            <input
              type="text"
              id="tabular-search-input"
              class="input-field text-xs pl-8 pr-3 py-1.5 w-full"
              placeholder="Buscar por SKU, nombre, folio..."
              value="${currentSearch}"
            />
            <span class="absolute left-2.5 top-2 text-slate-400">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
            </span>
          </div>

          <button id="btn-search-exec" class="btn-secondary text-xs py-1.5 px-3">
            Buscar
          </button>
          <button id="btn-clear-search" class="text-xs text-slate-400 hover:text-slate-600 px-2">
            Limpiar
          </button>
        </div>

        <!-- Indicador de Sincronización y Auto-refresh -->
        <div class="flex items-center gap-3 text-xs text-slate-500 justify-end">
          <div class="flex items-center gap-1.5">
            <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            <span id="tabular-sync-timestamp">Sincronizado: Justo ahora</span>
          </div>
          <div class="h-4 w-px bg-slate-200"></div>
          <label class="flex items-center gap-1.5 cursor-pointer select-none text-slate-600">
            <input type="checkbox" id="chk-auto-refresh" class="rounded text-blue-600 text-xs" ${autoRefreshEnabled ? 'checked' : ''} />
            <span>Auto-actualizar (30s)</span>
          </label>
        </div>
      </div>

      <!-- Contenedor de la Planilla -->
      <div class="card overflow-hidden border border-slate-200 shadow-sm">
        <!-- Encabezado de la Vista Activa -->
        <div class="px-4 py-3 bg-slate-50 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h2 id="view-active-title" class="text-sm font-bold text-slate-900">Cargando vista...</h2>
            <p id="view-active-desc" class="text-xs text-slate-500 mt-0.5">La planilla interna es la fuente central de consulta.</p>
          </div>
          <div class="flex items-center gap-2 text-xs text-slate-500">
            <span id="view-row-counter" class="font-mono bg-white px-2.5 py-1 rounded-md border border-slate-200 font-bold text-slate-800">
              0 registros
            </span>
          </div>
        </div>

        <!-- Tabla con Scroll Horizontal y Vertical -->
        <div class="overflow-x-auto max-h-[600px] relative scrollbar-thin">
          <table class="w-full text-left border-collapse text-xs">
            <thead id="tabular-thead" class="sticky top-0 bg-slate-100 z-10 shadow-sm border-b border-slate-200">
              <tr>
                <th class="p-3 text-slate-400">Cargando columnas...</th>
              </tr>
            </thead>
            <tbody id="tabular-tbody" class="divide-y divide-slate-100 font-sans">
              <tr>
                <td class="p-8 text-center text-slate-400">Cargando datos tabulares...</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Barra de Paginación -->
        <div class="p-3 bg-slate-50 border-t border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
          <div class="flex items-center gap-2">
            <span class="text-slate-500">Filas por página:</span>
            <select id="tabular-page-size" class="input-field py-1 px-2 text-xs w-20">
              <option value="25" ${currentPageSize === 25 ? 'selected' : ''}>25</option>
              <option value="50" ${currentPageSize === 50 ? 'selected' : ''}>50</option>
              <option value="100" ${currentPageSize === 100 ? 'selected' : ''}>100</option>
              <option value="250" ${currentPageSize === 250 ? 'selected' : ''}>250</option>
            </select>
            <span id="tabular-page-info" class="text-slate-500 ml-2">Página 1 de 1</span>
          </div>

          <div class="flex items-center gap-1">
            <button id="btn-page-prev" class="btn-secondary py-1 px-2.5 text-xs disabled:opacity-40" disabled>
              ← Anterior
            </button>
            <button id="btn-page-next" class="btn-secondary py-1 px-2.5 text-xs disabled:opacity-40" disabled>
              Siguiente →
            </button>
          </div>
        </div>
      </div>
    </div>
  `;

  // Bind Events
  bindPillEvents(container);
  bindFilterEvents(container);
  bindActionEvents(container);

  // Initial Load
  await loadTabularData();
}

function bindPillEvents(container) {
  container.querySelectorAll('.tab-view-pill').forEach((btn) => {
    btn.addEventListener('click', async () => {
      currentView = btn.dataset.viewId;
      currentPage = 1;
      currentSortBy = null;
      updatePillStyles(container);
      await loadTabularData();
    });
  });
}

function updatePillStyles(container) {
  container.querySelectorAll('.tab-view-pill').forEach((btn) => {
    if (btn.dataset.viewId === currentView) {
      btn.className = 'tab-view-pill shrink-0 px-3.5 py-2 rounded-xl text-xs font-semibold transition-all bg-blue-600 text-white shadow-sm ring-1 ring-blue-500';
    } else {
      btn.className = 'tab-view-pill shrink-0 px-3.5 py-2 rounded-xl text-xs font-semibold transition-all text-slate-600 hover:text-slate-900 hover:bg-white/70';
    }
  });
}

function bindFilterEvents(container) {
  const searchInput = container.querySelector('#tabular-search-input');
  const btnSearch = container.querySelector('#btn-search-exec');
  const btnClear = container.querySelector('#btn-clear-search');
  const pageSizeSelect = container.querySelector('#tabular-page-size');
  const btnPrev = container.querySelector('#btn-page-prev');
  const btnNext = container.querySelector('#btn-page-next');
  const chkAutoRefresh = container.querySelector('#chk-auto-refresh');

  btnSearch?.addEventListener('click', async () => {
    currentSearch = searchInput?.value.trim() || '';
    currentPage = 1;
    await loadTabularData();
  });

  searchInput?.addEventListener('keydown', async (e) => {
    if (e.key === 'Enter') {
      currentSearch = searchInput.value.trim();
      currentPage = 1;
      await loadTabularData();
    }
  });

  btnClear?.addEventListener('click', async () => {
    if (searchInput) searchInput.value = '';
    currentSearch = '';
    currentPage = 1;
    await loadTabularData();
  });

  pageSizeSelect?.addEventListener('change', async (e) => {
    currentPageSize = parseInt(e.target.value) || 25;
    currentPage = 1;
    await loadTabularData();
  });

  btnPrev?.addEventListener('click', async () => {
    if (currentPage > 1) {
      currentPage--;
      await loadTabularData();
    }
  });

  btnNext?.addEventListener('click', async () => {
    if (currentData && currentPage < currentData.total_pages) {
      currentPage++;
      await loadTabularData();
    }
  });

  chkAutoRefresh?.addEventListener('change', (e) => {
    autoRefreshEnabled = e.target.checked;
    if (autoRefreshEnabled) {
      startAutoRefresh();
      showToast('Actualización automática activada cada 30 segundos', 'info');
    } else {
      stopAutoRefresh();
      showToast('Actualización automática desactivada', 'info');
    }
  });
}

function startAutoRefresh() {
  stopAutoRefresh();
  autoRefreshTimer = setInterval(async () => {
    if (autoRefreshEnabled) {
      await loadTabularData(true);
    }
  }, 30000);
}

function stopAutoRefresh() {
  if (autoRefreshTimer) {
    clearInterval(autoRefreshTimer);
    autoRefreshTimer = null;
  }
}

function bindActionEvents(container) {
  // Exportar CSV
  container.querySelector('#btn-export-csv')?.addEventListener('click', async () => {
    try {
      showToast('Generando archivo CSV...', 'info');
      const blob = await api.downloadBlob(`/tabular/${currentView}/export/csv?search=${encodeURIComponent(currentSearch)}`);
      triggerDownload(blob, `${currentView}_export.csv`);
      showToast('Descarga CSV completada', 'success');
    } catch (err) {
      showToast(err.message || 'Error al exportar CSV', 'error');
    }
  });

  // Exportar XLSX
  container.querySelector('#btn-export-xlsx')?.addEventListener('click', async () => {
    try {
      showToast('Generando libro Excel XLSX estilizado...', 'info');
      const blob = await api.downloadBlob(`/tabular/${currentView}/export/xlsx?search=${encodeURIComponent(currentSearch)}`);
      triggerDownload(blob, `${currentView}_export.xlsx`);
      showToast('Descarga XLSX completada', 'success');
    } catch (err) {
      showToast(err.message || 'Error al exportar XLSX', 'error');
    }
  });

  // Modal Sincronización Externa
  container.querySelector('#btn-sync-external')?.addEventListener('click', () => {
    openSyncModal();
  });

  // Modal Historial de Modificaciones
  container.querySelector('#btn-view-history')?.addEventListener('click', () => {
    openHistoryModal();
  });
}

function triggerDownload(blob, filename) {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.style.display = 'none';
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  window.URL.revokeObjectURL(url);
  a.remove();
}

async function loadTabularData(isSilent = false) {
  const thead = document.getElementById('tabular-thead');
  const tbody = document.getElementById('tabular-tbody');
  const titleEl = document.getElementById('view-active-title');
  const descEl = document.getElementById('view-active-desc');
  const counterEl = document.getElementById('view-row-counter');
  const pageInfoEl = document.getElementById('tabular-page-info');
  const syncTimeEl = document.getElementById('tabular-sync-timestamp');
  const btnPrev = document.getElementById('btn-page-prev');
  const btnNext = document.getElementById('btn-page-next');

  if (!isSilent && tbody) {
    tbody.innerHTML = `<tr><td colspan="15" class="p-8 text-center text-slate-400">Cargando datos de la planilla...</td></tr>`;
  }

  try {
    const params = {
      page: currentPage,
      page_size: currentPageSize,
      search: currentSearch || undefined,
      sort_by: currentSortBy || undefined,
      sort_order: currentSortOrder,
    };

    const res = await api.get(`/tabular/${currentView}`, params);
    currentData = res;

    // Actualizar encabezados y títulos
    if (titleEl) titleEl.textContent = res.view_title;
    if (descEl) descEl.textContent = res.description;
    if (counterEl) counterEl.textContent = `${res.total_items.toLocaleString()} registros`;
    if (pageInfoEl) pageInfoEl.textContent = `Página ${res.page} de ${res.total_pages || 1}`;
    if (syncTimeEl) {
      const now = new Date();
      syncTimeEl.textContent = `Última sincronización: ${now.toLocaleTimeString('es-MX')}`;
    }

    if (btnPrev) btnPrev.disabled = !res.has_prev;
    if (btnNext) btnNext.disabled = !res.has_next;

    renderTableHeader(thead, res.columns);
    renderTableBody(tbody, res.columns, res.items);
  } catch (err) {
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="15" class="p-8 text-center text-rose-600 font-semibold">${err.message || 'Error cargando planilla'}</td></tr>`;
    }
  }
}

function renderTableHeader(thead, columns) {
  if (!thead) return;

  thead.innerHTML = `
    <tr class="bg-slate-100 text-slate-700 font-semibold border-b border-slate-200">
      ${columns.map((col) => {
        const isSorted = currentSortBy === col.key;
        const arrow = isSorted ? (currentSortOrder === 'asc' ? ' ▲' : ' ▼') : '';
        const sortClass = col.sortable ? 'cursor-pointer hover:bg-slate-200 select-none transition-colors' : '';
        const editBadge = col.editable ? '<span class="text-[10px] text-blue-600 font-normal ml-1" title="Columna editable">✎</span>' : '';
        return `
          <th
            data-col-key="${col.key}"
            data-sortable="${col.sortable}"
            class="p-3 text-left whitespace-nowrap text-xs ${sortClass}"
            style="${col.width ? `min-width: ${col.width * 8}px;` : ''}"
          >
            ${col.label}${editBadge}${arrow}
          </th>
        `;
      }).join('')}
    </tr>
  `;

  // Click para ordenar
  thead.querySelectorAll('th[data-sortable="true"]').forEach((th) => {
    th.addEventListener('click', async () => {
      const key = th.dataset.colKey;
      if (currentSortBy === key) {
        currentSortOrder = currentSortOrder === 'asc' ? 'desc' : 'asc';
      } else {
        currentSortBy = key;
        currentSortOrder = 'desc';
      }
      await loadTabularData();
    });
  });
}

function renderTableBody(tbody, columns, items) {
  if (!tbody) return;

  if (items.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="${columns.length}" class="p-12 text-center text-slate-400">
          No se encontraron registros para los filtros seleccionados en esta planilla.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = items.map((item, idx) => {
    const rowId = item.row_id || item.id || `row-${idx}`;
    const zebra = idx % 2 === 0 ? 'bg-white' : 'bg-slate-50/50';

    const cellsHtml = columns.map((col) => {
      const rawVal = item[col.key];
      let formattedVal = rawVal;
      let extraClass = '';

      if (rawVal === null || rawVal === undefined || rawVal === '') {
        formattedVal = '<span class="text-slate-300">-</span>';
      } else if (col.data_type === 'currency') {
        const num = parseFloat(rawVal) || 0;
        formattedVal = `$${num.toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} MXN`;
        extraClass = 'font-mono text-right';
      } else if (col.data_type === 'number') {
        formattedVal = rawVal;
        extraClass = 'font-mono text-right';
      } else if (col.data_type === 'boolean') {
        formattedVal = rawVal
          ? '<span class="text-emerald-700 font-bold">✓ SÍ</span>'
          : '<span class="text-slate-400 font-medium">✕ NO</span>';
        extraClass = 'text-center';
      } else if (col.data_type === 'badge') {
        const strVal = String(rawVal).toUpperCase();
        let badgeColor = 'bg-slate-100 text-slate-700';
        if (['PAID', 'DELIVERED', 'ACTIVE', 'SALUDABLE', 'RENTABLE', 'RECEIVED', 'APPROVED', 'SUCCESS'].includes(strVal)) {
          badgeColor = 'bg-emerald-50 text-emerald-700 border border-emerald-200';
        } else if (['PENDING', 'IN_PROCESS', 'SHIPPED', 'ISSUED', 'PARTIALLY_RECEIVED', 'REORDER_POINT'].includes(strVal)) {
          badgeColor = 'bg-amber-50 text-amber-800 border border-amber-200';
        } else if (['CANCELLED', 'RETURNED', 'AGOTADO', 'PÉRDIDA', 'BAJO_STOCK', 'ERROR'].includes(strVal)) {
          badgeColor = 'bg-rose-50 text-rose-700 border border-rose-200';
        }
        formattedVal = `<span class="inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold ${badgeColor}">${strVal}</span>`;
        extraClass = 'text-center';
      }

      const editableAttr = col.editable ? `data-editable="true" data-col-key="${col.key}" data-raw-val="${escapeHtml(String(rawVal ?? ''))}" class="p-2.5 whitespace-nowrap group cursor-pointer hover:bg-blue-50/60 transition-colors ${extraClass}"` : `class="p-2.5 whitespace-nowrap ${extraClass}"`;

      return `
        <td ${editableAttr} title="${col.editable ? 'Haz clic para editar este valor' : ''}">
          <div class="flex items-center justify-between gap-1">
            <span>${formattedVal}</span>
            ${col.editable ? '<span class="opacity-0 group-hover:opacity-100 text-[10px] text-blue-500 font-mono">✎</span>' : ''}
          </div>
        </td>
      `;
    }).join('');

    return `
      <tr data-row-id="${rowId}" class="${zebra} hover:bg-blue-50/40 transition-colors border-b border-slate-100">
        ${cellsHtml}
      </tr>
    `;
  }).join('');

  // Vincular eventos de edición en celdas autorizadas
  tbody.querySelectorAll('td[data-editable="true"]').forEach((td) => {
    td.addEventListener('click', () => {
      const tr = td.closest('tr');
      const rowId = tr.dataset.rowId;
      const colKey = td.dataset.colKey;
      const rawVal = td.dataset.rawVal;
      const colDef = columns.find((c) => c.key === colKey);
      openCellEditModal(rowId, colDef, rawVal);
    });
  });
}

function escapeHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ===========================================================================
// MODAL: EDICIÓN AUTORIZADA DE CELDA
// ===========================================================================

function openCellEditModal(rowId, colDef, currentVal) {
  const inputType = colDef.data_type === 'number' || colDef.data_type === 'currency' ? 'number' : (colDef.data_type === 'boolean' ? 'checkbox' : 'text');
  const stepAttr = colDef.data_type === 'currency' ? 'step="0.01"' : '';

  const content = `
    <form id="tabular-edit-cell-form" class="space-y-4">
      <div class="bg-slate-50 p-3 rounded-xl border border-slate-200 text-xs space-y-1">
        <div><span class="text-slate-500">Planilla Activa:</span> <strong class="text-slate-900">${currentView}</strong></div>
        <div><span class="text-slate-500">Identificador Fila (ID / SKU):</span> <strong class="font-mono text-slate-800">${rowId}</strong></div>
        <div><span class="text-slate-500">Campo a Modificar:</span> <strong class="text-blue-700">${colDef.label} (${colDef.key})</strong></div>
      </div>

      <div>
        <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">
          Nuevo Valor *
        </label>
        ${
          colDef.data_type === 'boolean'
            ? `
              <label class="flex items-center gap-2 cursor-pointer mt-2 text-sm">
                <input type="checkbox" id="cell-new-val" class="rounded text-blue-600" ${currentVal === 'true' || currentVal === 'True' || currentVal === '1' ? 'checked' : ''} />
                <span class="font-semibold text-slate-800">Activo / Habilitado</span>
              </label>
            `
            : `
              <input
                type="${inputType}"
                id="cell-new-val"
                class="input-field text-sm"
                value="${escapeHtml(currentVal)}"
                ${stepAttr}
                required
              />
            `
        }
      </div>

      <div>
        <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">
          Motivo del Cambio (Auditoría Obligatoria) *
        </label>
        <input
          type="text"
          id="cell-change-reason"
          class="input-field text-xs"
          placeholder="e.g. Ajuste autorizado de costo, actualización de stock de seguridad..."
          required
        />
      </div>

      <div class="flex justify-end gap-2 pt-2 border-t border-slate-100">
        <button type="button" id="btn-cancel-cell-edit" class="btn-secondary">Cancelar</button>
        <button type="submit" id="btn-save-cell-edit" class="btn-primary flex items-center gap-1.5">
          ${icons.check ? icons.check('w-4 h-4') : '✓'} Guardar y Auditar
        </button>
      </div>
    </form>
  `;

  openModal(`Edición Autorizada · ${colDef.label}`, content);
  document.getElementById('btn-cancel-cell-edit')?.addEventListener('click', closeModal);

  const form = document.getElementById('tabular-edit-cell-form');
  form?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('btn-save-cell-edit');
    btn.disabled = true;
    btn.textContent = 'Guardando...';

    let newVal;
    if (colDef.data_type === 'boolean') {
      newVal = document.getElementById('cell-new-val').checked;
    } else if (colDef.data_type === 'number' || colDef.data_type === 'currency') {
      newVal = parseFloat(document.getElementById('cell-new-val').value);
    } else {
      newVal = document.getElementById('cell-new-val').value.trim();
    }

    const reason = document.getElementById('cell-change-reason').value.trim();

    try {
      const updates = { [colDef.key]: newVal };
      await api.put(`/tabular/${currentView}/${rowId}`, {
        updates,
        change_reason: reason,
      });

      closeModal();
      showToast(`Celda '${colDef.label}' actualizada exitosamente`, 'success');
      await loadTabularData();
    } catch (err) {
      showToast(err.message || 'Error al actualizar celda', 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Guardar y Auditar';
      }
    }
  });
}

// ===========================================================================
// MODAL: SINCRONIZACIÓN EXTERNA (GOOGLE SHEETS / EXCEL ONLINE)
// ===========================================================================

async function openSyncModal() {
  const content = `
    <div class="space-y-4">
      <div class="bg-blue-50 border border-blue-200 p-3 rounded-xl text-xs text-blue-900 space-y-1">
        <div class="font-bold flex items-center gap-1">
          <span>ℹ️</span> Regla de Sincronización ERP:
        </div>
        <p>
          La planilla interna es la <strong>fuente central de verdad</strong>. Las planillas externas (Google Sheets o Excel Online) se mantienen sincronizadas preservando identificadores únicos. Las planillas externas <em>no pueden sobreescribir directamente el inventario físico</em>.
        </p>
      </div>

      <div class="border border-slate-200 rounded-xl p-4 space-y-3">
        <h4 class="text-xs font-bold text-slate-800 uppercase">Sincronizar Vista Actual: <strong>${currentView}</strong></h4>
        
        <div class="grid grid-cols-2 gap-3">
          <div class="p-3 border border-slate-200 rounded-lg hover:border-blue-400 cursor-pointer bg-slate-50 text-center transition-colors">
            <div class="text-2xl mb-1">📑</div>
            <div class="font-bold text-slate-900 text-xs">Google Sheets</div>
            <div class="text-[10px] text-slate-500 mb-2">OAuth2 + Google Sheets API v4</div>
            <button id="btn-sync-gsheets" class="btn-primary text-xs py-1 px-3 w-full">
              Sincronizar Google Sheets
            </button>
          </div>

          <div class="p-3 border border-slate-200 rounded-lg hover:border-emerald-400 cursor-pointer bg-slate-50 text-center transition-colors">
            <div class="text-2xl mb-1">📊</div>
            <div class="font-bold text-slate-900 text-xs">Microsoft Excel</div>
            <div class="text-[10px] text-slate-500 mb-2">Microsoft Graph API / OneDrive</div>
            <button id="btn-sync-msexcel" class="btn-secondary text-xs py-1 px-3 w-full text-emerald-800 bg-emerald-50 hover:bg-emerald-100">
              Sincronizar Excel Online
            </button>
          </div>
        </div>
      </div>

      <div class="flex justify-end pt-2 border-t border-slate-200">
        <button id="btn-close-sync-modal" class="btn-secondary text-xs">Cerrar</button>
      </div>
    </div>
  `;

  openModal('Sincronización con Planillas Externas', content);
  document.getElementById('btn-close-sync-modal')?.addEventListener('click', closeModal);

  document.getElementById('btn-sync-gsheets')?.addEventListener('click', async () => {
    try {
      showToast('Sincronizando con Google Sheets...', 'info');
      const res = await api.post(`/tabular/${currentView}/sync/google_sheets`, {
        direction: 'push',
      });
      closeModal();
      showToast(res.message, 'success');
      await loadTabularData();
    } catch (err) {
      showToast(err.message || 'Error en sincronización con Google Sheets', 'error');
    }
  });

  document.getElementById('btn-sync-msexcel')?.addEventListener('click', async () => {
    try {
      showToast('Sincronizando con Microsoft Excel...', 'info');
      const res = await api.post(`/tabular/${currentView}/sync/microsoft_excel`, {
        direction: 'push',
      });
      closeModal();
      showToast(res.message, 'success');
      await loadTabularData();
    } catch (err) {
      showToast(err.message || 'Error en sincronización con Excel', 'error');
    }
  });
}

// ===========================================================================
// MODAL: HISTORIAL DE MODIFICACIONES EN PLANILLAS
// ===========================================================================

async function openHistoryModal() {
  const content = `
    <div class="space-y-4">
      <div class="flex items-center justify-between text-xs text-slate-500">
        <span>Auditoría inmutable de celdas modificadas en las 13 planillas.</span>
        <button id="btn-refresh-hist" class="text-blue-600 hover:underline">Refrescar</button>
      </div>

      <div class="overflow-x-auto max-h-[400px] border border-slate-200 rounded-lg">
        <table class="w-full text-left text-xs border-collapse">
          <thead class="bg-slate-100 sticky top-0 border-b border-slate-200">
            <tr>
              <th class="p-2">Fecha</th>
              <th class="p-2">Planilla</th>
              <th class="p-2">Fila (ID/SKU)</th>
              <th class="p-2">Campo</th>
              <th class="p-2">Valor Anterior</th>
              <th class="p-2 font-bold text-blue-700">Nuevo Valor</th>
              <th class="p-2">Usuario</th>
              <th class="p-2">Motivo</th>
            </tr>
          </thead>
          <tbody id="history-modal-tbody" class="divide-y divide-slate-100">
            <tr><td colspan="8" class="p-6 text-center text-slate-400">Cargando historial de auditoría...</td></tr>
          </tbody>
        </table>
      </div>

      <div class="flex justify-end pt-2 border-t border-slate-200">
        <button id="btn-close-hist-modal" class="btn-secondary text-xs">Cerrar</button>
      </div>
    </div>
  `;

  openModal('Historial de Cambios en Planillas ERP', content);
  document.getElementById('btn-close-hist-modal')?.addEventListener('click', closeModal);

  async function loadHistoryRows() {
    const tbody = document.getElementById('history-modal-tbody');
    try {
      const res = await api.get('/tabular/history?limit=50');
      const items = res.items || [];
      if (items.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="p-6 text-center text-slate-400">No hay modificaciones registradas aún.</td></tr>`;
        return;
      }

      tbody.innerHTML = items.map((it) => `
        <tr class="hover:bg-slate-50">
          <td class="p-2 text-slate-500">${new Date(it.created_at).toLocaleString('es-MX')}</td>
          <td class="p-2 font-bold uppercase text-[10px] text-slate-700">${it.view_name}</td>
          <td class="p-2 font-mono">${it.row_id}</td>
          <td class="p-2 font-semibold text-slate-800">${it.column_name}</td>
          <td class="p-2 text-slate-500 line-through">${it.previous_value ?? '-'}</td>
          <td class="p-2 font-bold text-blue-700">${it.new_value ?? '-'}</td>
          <td class="p-2 text-slate-600">${it.user_name}</td>
          <td class="p-2 text-slate-500 italic">${it.change_reason || '-'}</td>
        </tr>
      `).join('');
    } catch (err) {
      if (tbody) tbody.innerHTML = `<tr><td colspan="8" class="p-6 text-center text-rose-600">${err.message || 'Error cargando historial'}</td></tr>`;
    }
  }

  document.getElementById('btn-refresh-hist')?.addEventListener('click', loadHistoryRows);
  await loadHistoryRows();
}

/**
 * Centro de Automatización Empresarial (ECA: Eventos, Condiciones y Acciones)
 * 
 * Incluye:
 * 1. Interruptor General (Global Kill Switch) a nivel empresa.
 * 2. Matriz de Modalidades por Módulo (Manual, Automática, Automática con Aprobación Previa).
 * 3. Catálogo de Reglas ECA con salvaguardas y Circuit Breaker.
 * 4. Bandeja de Aprobaciones Pendientes (Human-in-the-Loop).
 * 5. Bitácora Inmutable de Auditoría y Ejecuciones con Reversión (Rollback/Compensación).
 * 6. Disparo manual de eventos para pruebas de concurrencia e idempotencia.
 */

import { api } from '../api.js';
import { icons } from '../icons.js';
import { showToast } from '../components/toast.js';

let automationConfig = null;
let automationRules = [];
let automationExecutions = [];
let automationStats = null;

export async function renderAutomations(container) {
  container.innerHTML = `
    <div class="space-y-6">
      <!-- Encabezado Principal e Interruptor General -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-200 pb-4">
        <div>
          <h1 class="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2.5">
            <span class="p-2 bg-gradient-to-tr from-amber-500 to-orange-600 text-white rounded-xl shadow-sm">
              ${icons.zap}
            </span>
            Motor de Automatización Empresarial (ECA)
          </h1>
          <p class="text-sm text-slate-500 mt-1">
            Orquestación desatendida basada en Eventos, Condiciones y Acciones con salvaguardas de inventario, precios y reversión auditable.
          </p>
        </div>

        <!-- Interruptor General (Kill Switch) y Botón Nueva Regla -->
        <div class="flex items-center gap-3">
          <div id="kill-switch-container" class="flex items-center gap-2.5 bg-slate-100 px-3.5 py-1.5 rounded-xl border border-slate-200">
            <span class="text-xs font-semibold text-slate-700">Motor Global:</span>
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" id="global-kill-switch" class="sr-only peer" checked>
              <div class="w-10 h-5 bg-slate-300 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-emerald-600"></div>
            </label>
            <span id="kill-switch-status" class="text-xs font-bold text-emerald-700">ACTIVO</span>
          </div>

          <button
            id="btn-new-rule"
            class="px-3.5 py-2 text-xs font-semibold text-white bg-amber-600 rounded-xl hover:bg-amber-700 shadow-sm flex items-center gap-1.5 transition-all"
          >
            + Nueva Regla ECA
          </button>
        </div>
      </div>

      <!-- KPI Summary Cards -->
      <div id="automation-kpi-cards" class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3.5">
        <div class="card p-3.5 text-center animate-pulse bg-slate-50"><span class="text-xs text-slate-400">Cargando métricas...</span></div>
      </div>

      <!-- Modalidades Configurables por Módulo -->
      <div class="card p-5 space-y-4">
        <div class="flex items-center justify-between border-b border-slate-100 pb-3">
          <div>
            <h2 class="text-sm font-bold text-slate-800 uppercase tracking-wider flex items-center gap-2">
              ${icons.settings || '⚙️'} Modalidad de Ejecución por Módulo
            </h2>
            <p class="text-xs text-slate-500 mt-0.5">
              Controla qué módulos operan desatendidos, cuáles requieren autorización humana previa y cuáles son manuales.
            </p>
          </div>
          <button id="btn-save-modes" class="px-3 py-1.5 text-xs font-semibold text-white bg-slate-900 rounded-lg hover:bg-slate-800 transition-all">
            Guardar Modalidades
          </button>
        </div>

        <div id="module-modes-grid" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <!-- Renderizado dinámicamente -->
        </div>
      </div>

      <!-- Pestañas de Navegación: Reglas, Aprobaciones Pendientes y Auditoría -->
      <div class="space-y-4">
        <div class="border-b border-slate-200">
          <nav class="flex space-x-6 text-sm font-medium">
            <button id="tab-rules" class="tab-btn pb-3 px-1 border-b-2 border-amber-600 text-amber-600 font-bold flex items-center gap-2">
              📜 Reglas Activas (<span id="count-rules">0</span>)
            </button>
            <button id="tab-approvals" class="tab-btn pb-3 px-1 border-b-2 border-transparent text-slate-500 hover:text-slate-700 font-bold flex items-center gap-2">
              ⏳ Aprobaciones Pendientes (<span id="count-pending">0</span>)
            </button>
            <button id="tab-executions" class="tab-btn pb-3 px-1 border-b-2 border-transparent text-slate-500 hover:text-slate-700 font-bold flex items-center gap-2">
              📋 Bitácora Inmutable de Ejecuciones
            </button>
          </nav>
        </div>

        <!-- Contenedores de Vistas según Tab -->
        <div id="tab-content-rules" class="tab-content space-y-3">
          <div id="rules-list-container" class="space-y-3">
            <p class="text-xs text-slate-400 py-6 text-center">Cargando catálogo de reglas...</p>
          </div>
        </div>

        <div id="tab-content-approvals" class="tab-content hidden space-y-3">
          <div id="approvals-list-container" class="space-y-3">
            <p class="text-xs text-slate-400 py-6 text-center">No hay ejecuciones pendientes de aprobación.</p>
          </div>
        </div>

        <div id="tab-content-executions" class="tab-content hidden space-y-3">
          <div class="card overflow-hidden">
            <div class="overflow-x-auto">
              <table class="w-full text-left text-xs">
                <thead class="bg-slate-50 border-b border-slate-200 text-slate-600 font-bold uppercase tracking-wider">
                  <tr>
                    <th class="py-3 px-4">Fecha / ID</th>
                    <th class="py-3 px-4">Evento / Activador</th>
                    <th class="py-3 px-4">Acción Ejecutada</th>
                    <th class="py-3 px-4">Estado</th>
                    <th class="py-3 px-4">Latencia</th>
                    <th class="py-3 px-4 text-right">Compensación</th>
                  </tr>
                </thead>
                <tbody id="executions-tbody" class="divide-y divide-slate-100">
                  <tr><td colspan="6" class="text-center py-6 text-slate-400">Cargando historial de ejecuciones...</td></tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal: Crear / Editar Regla ECA -->
    <div id="rule-modal" class="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 hidden flex items-center justify-center p-4">
      <div class="bg-white rounded-2xl max-w-2xl w-full p-6 shadow-xl border border-slate-200 space-y-4 max-h-[90vh] overflow-y-auto">
        <div class="flex items-center justify-between border-b border-slate-100 pb-3">
          <h3 class="text-base font-bold text-slate-900 flex items-center gap-2">
            ${icons.zap} <span id="modal-rule-title">Nueva Regla de Automatización ECA</span>
          </h3>
          <button id="btn-close-modal" class="text-slate-400 hover:text-slate-600 text-xl font-bold">&times;</button>
        </div>

        <form id="form-rule" class="space-y-4 text-xs">
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="block font-semibold text-slate-700 mb-1">Nombre de la Regla *</label>
              <input type="text" id="rule-name" required placeholder="Ej: Reservar stock en venta recibida" class="w-full px-3 py-2 border border-slate-300 rounded-lg">
            </div>
            <div>
              <label class="block font-semibold text-slate-700 mb-1">Módulo del ERP *</label>
              <select id="rule-module" class="w-full px-3 py-2 border border-slate-300 rounded-lg bg-white">
                <option value="inventory">Inventario y Almacenes</option>
                <option value="pricing">Precios y Márgenes</option>
                <option value="promotions">Promociones y Ofertas</option>
                <option value="logistics">Logística y Envíos</option>
                <option value="procurement">Abastecimiento y Proveedores</option>
                <option value="reports">Reportes Ejecutivos</option>
                <option value="spreadsheets">Planillas y Centro Tabular</option>
                <option value="general">General</option>
              </select>
            </div>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="block font-semibold text-slate-700 mb-1">Evento Disparador (Trigger) *</label>
              <select id="rule-trigger-event" class="w-full px-3 py-2 border border-slate-300 rounded-lg bg-white">
                <option value="ORDER_CREATED">Venta Recibida (ORDER_CREATED)</option>
                <option value="ORDER_CONFIRMED">Venta Confirmada / Pagada (ORDER_CONFIRMED)</option>
                <option value="STOCK_LOW">Stock Bajo / Punto de Reorden (STOCK_LOW)</option>
                <option value="STOCK_DEPLETED">Stock Agotado (STOCK_DEPLETED)</option>
                <option value="LABEL_READY">Etiqueta de Envío Disponible (LABEL_READY)</option>
                <option value="PROMOTION_EXPIRING_SOON">Promoción Próxima a Vencer (PROMOTION_EXPIRING_SOON)</option>
                <option value="PRICE_CHANGE_REQUESTED">Cambio de Precio Solicitado (PRICE_CHANGE_REQUESTED)</option>
                <option value="SALE_PROCESSED">Venta Procesada (SALE_PROCESSED)</option>
                <option value="END_OF_DAY">Fin del Día / Cierre Diario (END_OF_DAY)</option>
                <option value="SURGING_DEMAND">Demanda Creciente (SURGING_DEMAND)</option>
              </select>
            </div>
            <div>
              <label class="block font-semibold text-slate-700 mb-1">Modalidad de Ejecución *</label>
              <select id="rule-execution-mode" class="w-full px-3 py-2 border border-slate-300 rounded-lg bg-white">
                <option value="default_by_module">Heredar de la Configuración del Módulo</option>
                <option value="automatic">Automática (Desatendida en tiempo real)</option>
                <option value="approval_required">Automática con Aprobación Previa</option>
                <option value="manual">Manual (Solo bajo demanda)</option>
              </select>
            </div>
          </div>

          <div>
            <label class="block font-semibold text-slate-700 mb-1">Acción a Ejecutar (Action) *</label>
            <select id="rule-action-type" class="w-full px-3 py-2 border border-slate-300 rounded-lg bg-white font-bold text-slate-800">
              <option value="RESERVE_INVENTORY">Reservar Inventario (Protección sobreventa)</option>
              <option value="CONFIRM_INVENTORY_DEDUCTION">Actualizar Existencias (Deducción definitiva con movimiento)</option>
              <option value="CREATE_OPERATIONAL_ALERT">Generar Alerta Operativa / Financiera</option>
              <option value="SYNC_MELI_ITEM_STATUS">Pausar / Actualizar Publicación en Mercado Libre</option>
              <option value="CREATE_LOGISTICS_TASK">Preparar Tarea Logística / Orden de Empaque</option>
              <option value="BLOCK_PRICE_CHANGE">Detener / Bloquear Cambio de Precio (Salvaguarda de Margen)</option>
              <option value="UPDATE_TABULAR_SHEET">Actualizar Planilla Interna y Centro Tabular</option>
              <option value="GENERATE_DAILY_REPORT">Generar Reporte Ejecutivo de Cierre</option>
              <option value="CREATE_RESTOCK_SUGGESTION">Recomendar Reposición (Crear Borrador de Compra)</option>
            </select>
          </div>

          <div class="border-t border-slate-100 pt-3">
            <label class="block font-semibold text-slate-700 mb-1">Salvaguardas de Seguridad (Opcionales)</label>
            <div class="grid grid-cols-3 gap-2">
              <input type="number" id="rule-min-price" step="0.5" placeholder="Precio piso ($)" class="px-2 py-1.5 border border-slate-300 rounded">
              <input type="number" id="rule-min-margin" step="0.5" placeholder="Margen mín. (%)" class="px-2 py-1.5 border border-slate-300 rounded">
              <input type="number" id="rule-cooldown" placeholder="Cooldown (seg.)" value="30" class="px-2 py-1.5 border border-slate-300 rounded">
            </div>
          </div>

          <div class="flex justify-end gap-2 pt-2 border-t border-slate-100">
            <button type="button" id="btn-cancel-rule" class="px-4 py-2 border border-slate-300 rounded-lg text-slate-700 hover:bg-slate-50">Cancelar</button>
            <button type="submit" class="px-4 py-2 bg-amber-600 text-white font-semibold rounded-lg hover:bg-amber-700 shadow-sm">Guardar Regla</button>
          </div>
        </form>
      </div>
    </div>
  `;

  // Cargar datos iniciales
  await loadAutomationData();
  bindEvents(container);
}

async function loadAutomationData() {
  try {
    const [cfg, stats, rules, execs] = await Promise.all([
      api.get('/api/v1/automation/config'),
      api.get('/api/v1/automation/stats'),
      api.get('/api/v1/automation/rules'),
      api.get('/api/v1/automation/executions?limit=30'),
    ]);

    automationConfig = cfg;
    automationStats = stats;
    automationRules = rules;
    automationExecutions = execs;

    renderKPIs();
    renderModuleModes();
    renderRules();
    renderApprovals();
    renderExecutions();
    updateKillSwitchUI();
  } catch (err) {
    console.error('Error al cargar datos del motor de automatización:', err);
    showToast('Error cargando automatizaciones: ' + err.message, 'error');
  }
}

function updateKillSwitchUI() {
  const switchEl = document.getElementById('global-kill-switch');
  const statusEl = document.getElementById('kill-switch-status');
  if (switchEl && statusEl && automationConfig) {
    switchEl.checked = automationConfig.is_engine_active;
    if (automationConfig.is_engine_active) {
      statusEl.textContent = 'ACTIVO';
      statusEl.className = 'text-xs font-bold text-emerald-700';
    } else {
      statusEl.textContent = 'PAUSADO (KILL SWITCH)';
      statusEl.className = 'text-xs font-bold text-rose-700';
    }
  }
}

function renderKPIs() {
  const container = document.getElementById('automation-kpi-cards');
  if (!container || !automationStats) return;

  const s = automationStats;
  container.innerHTML = `
    <div class="card p-3 text-center border-l-4 border-amber-500">
      <div class="text-[10px] uppercase font-bold text-slate-400">Total Reglas</div>
      <div class="text-lg font-black text-slate-900 mt-0.5">${s.total_rules}</div>
      <div class="text-[10px] text-slate-500">${s.active_rules} activas</div>
    </div>
    <div class="card p-3 text-center border-l-4 border-emerald-500">
      <div class="text-[10px] uppercase font-bold text-slate-400">Éxitos Hoy</div>
      <div class="text-lg font-black text-emerald-700 mt-0.5">${s.successful_executions_today}</div>
      <div class="text-[10px] text-slate-500">Ejecutadas</div>
    </div>
    <div class="card p-3 text-center border-l-4 border-indigo-500">
      <div class="text-[10px] uppercase font-bold text-slate-400">Pend. Aprobación</div>
      <div class="text-lg font-black text-indigo-700 mt-0.5">${s.pending_approvals_count}</div>
      <div class="text-[10px] text-slate-500">Human-in-the-loop</div>
    </div>
    <div class="card p-3 text-center border-l-4 border-rose-500">
      <div class="text-[10px] uppercase font-bold text-slate-400">Dead-Letter</div>
      <div class="text-lg font-black text-rose-700 mt-0.5">${s.dead_letter_count_today}</div>
      <div class="text-[10px] text-slate-500">Reintentos agotados</div>
    </div>
    <div class="card p-3 text-center border-l-4 border-purple-500">
      <div class="text-[10px] uppercase font-bold text-slate-400">Circuit Breakers</div>
      <div class="text-lg font-black ${s.circuit_breakers_active > 0 ? 'text-rose-600' : 'text-slate-700'} mt-0.5">
        ${s.circuit_breakers_active}
      </div>
      <div class="text-[10px] text-slate-500">Reglas en pausa</div>
    </div>
    <div class="card p-3 text-center border-l-4 border-blue-500">
      <div class="text-[10px] uppercase font-bold text-slate-400">Cuota Diaria</div>
      <div class="text-lg font-black text-blue-700 mt-0.5">${automationConfig.daily_execution_limit - automationConfig.executions_today}</div>
      <div class="text-[10px] text-slate-500">disponibles</div>
    </div>
  `;

  document.getElementById('count-rules').textContent = automationRules.length;
  document.getElementById('count-pending').textContent = s.pending_approvals_count;
}

function renderModuleModes() {
  const container = document.getElementById('module-modes-grid');
  if (!container || !automationConfig) return;

  const labels = {
    inventory: '📦 Inventario y Almacenes',
    pricing: '💲 Precios y Rentabilidad',
    promotions: '🏷️ Promociones y Ofertas',
    logistics: '🚚 Logística y Envíos',
    procurement: '🛒 Abastecimiento y Compras',
    reports: '📊 Reportes de Cierre',
    spreadsheets: '📑 Centro Tabular',
  };

  container.innerHTML = Object.entries(automationConfig.module_modes)
    .map(([mod, currentMode]) => `
      <div class="p-3 bg-slate-50 border border-slate-200 rounded-xl space-y-1.5">
        <div class="font-bold text-xs text-slate-800">${labels[mod] || mod}</div>
        <select class="module-mode-select w-full text-xs px-2 py-1 border border-slate-300 rounded bg-white font-medium" data-module="${mod}">
          <option value="automatic" ${currentMode === 'automatic' ? 'selected' : ''}>⚡ Automática (Desatendida)</option>
          <option value="approval_required" ${currentMode === 'approval_required' ? 'selected' : ''}>⏳ Aprobación Previa</option>
          <option value="manual" ${currentMode === 'manual' ? 'selected' : ''}>👤 Manual (Solo bajo demanda)</option>
        </select>
      </div>
    `)
    .join('');
}

function renderRules() {
  const container = document.getElementById('rules-list-container');
  if (!container) return;

  if (automationRules.length === 0) {
    container.innerHTML = `
      <div class="card p-8 text-center text-slate-500 space-y-2">
        <p class="text-sm font-semibold">No hay reglas de automatización creadas aún.</p>
        <p class="text-xs text-slate-400">Crea tu primera regla ECA para orquestar reservas de inventario, alertas y precios.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = automationRules
    .map((r) => {
      const isPaused = r.is_paused_by_circuit_breaker;
      return `
        <div class="card p-4 flex flex-col md:flex-row md:items-center justify-between gap-4 border-l-4 ${isPaused ? 'border-rose-500 bg-rose-50/20' : r.is_active ? 'border-emerald-500' : 'border-slate-300'}">
          <div class="space-y-1.5 max-w-2xl">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="font-bold text-sm text-slate-900">${r.name}</span>
              <span class="px-2 py-0.5 rounded text-[10px] font-bold uppercase ${isPaused ? 'bg-rose-100 text-rose-800' : r.is_active ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-200 text-slate-600'}">
                ${isPaused ? '🚨 CIRCUIT BREAKER' : r.is_active ? 'ACTIVA' : 'INACTIVA'}
              </span>
              <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-50 text-amber-800 border border-amber-200">
                ${r.module.toUpperCase()}
              </span>
              <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-50 text-blue-800 border border-blue-200">
                ${r.execution_mode}
              </span>
            </div>
            <div class="text-xs text-slate-600 flex items-center gap-3">
              <span><strong>Activador:</strong> <code class="bg-slate-100 px-1 py-0.5 rounded text-slate-800 font-mono">${r.trigger_event || r.trigger_type}</code></span>
              <span><strong>Acción:</strong> <code class="bg-indigo-50 px-1 py-0.5 rounded text-indigo-800 font-mono">${r.action_type}</code></span>
            </div>
            <div class="text-[11px] text-slate-400">
              Ejecuciones: ${r.total_executions} (${r.successful_executions} exitosas, ${r.failed_executions} fallidas)
            </div>
          </div>

          <div class="flex items-center gap-2 self-end md:self-center">
            ${
              isPaused
                ? `<button class="btn-reset-cb px-3 py-1.5 text-xs font-bold text-white bg-rose-600 rounded-lg hover:bg-rose-700" data-rule-id="${r.id}">Reactivar CB</button>`
                : ''
            }
            <button class="btn-exec-manual px-3 py-1.5 text-xs font-semibold text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50" data-rule-id="${r.id}">
              ▶️ Probar
            </button>
            <button class="btn-delete-rule text-slate-400 hover:text-rose-600 p-1.5 rounded-lg" data-rule-id="${r.id}" title="Eliminar regla">
              🗑️
            </button>
          </div>
        </div>
      `;
    })
    .join('');
}

function renderApprovals() {
  const container = document.getElementById('approvals-list-container');
  if (!container) return;

  const pending = automationExecutions.filter((e) => e.status === 'pending_approval');
  if (pending.length === 0) {
    container.innerHTML = `
      <div class="card p-8 text-center text-slate-400 space-y-1">
        <p class="text-sm font-semibold text-slate-600">No hay acciones pendientes de aprobación</p>
        <p class="text-xs">Las automatizaciones en modalidad 'Aprobación Previa' aparecerán aquí antes de aplicarse.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = pending
    .map((e) => `
      <div class="card p-4 space-y-3 border-l-4 border-indigo-500">
        <div class="flex items-start justify-between gap-4">
          <div class="space-y-1">
            <div class="flex items-center gap-2">
              <span class="font-bold text-xs uppercase px-2 py-0.5 rounded bg-indigo-100 text-indigo-800">Acción Pendiente</span>
              <span class="text-sm font-black text-slate-900">${e.action_executed}</span>
              <span class="text-xs text-slate-400 font-mono">${e.trigger_event || ''}</span>
            </div>
            <p class="text-xs text-slate-600">
              Disparado por evento: <code class="bg-slate-100 px-1 py-0.5 rounded">${e.event_id || 'manual'}</code>
            </p>
            <div class="bg-slate-50 p-2.5 rounded-lg font-mono text-[11px] text-slate-700 overflow-x-auto max-h-24">
              ${JSON.stringify(e.action_parameters, null, 2)}
            </div>
          </div>
          <div class="flex items-center gap-2 shrink-0">
            <button class="btn-approve px-3.5 py-1.5 text-xs font-bold text-white bg-emerald-600 rounded-lg hover:bg-emerald-700 shadow-sm" data-exec-id="${e.id}">
              ✓ Aprobar y Ejecutar
            </button>
            <button class="btn-reject px-3.5 py-1.5 text-xs font-semibold text-rose-700 bg-rose-50 border border-rose-200 rounded-lg hover:bg-rose-100" data-exec-id="${e.id}">
              ✕ Rechazar
            </button>
          </div>
        </div>
      </div>
    `)
    .join('');
}

function renderExecutions() {
  const tbody = document.getElementById('executions-tbody');
  if (!tbody) return;

  if (automationExecutions.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="text-center py-6 text-slate-400">No hay ejecuciones registradas.</td></tr>`;
    return;
  }

  tbody.innerHTML = automationExecutions
    .map((e) => {
      const statusBadge = {
        success: 'bg-emerald-100 text-emerald-800',
        dead_letter: 'bg-rose-100 text-rose-800 font-black',
        failed: 'bg-rose-100 text-rose-800',
        pending_approval: 'bg-indigo-100 text-indigo-800 font-bold',
        reverted: 'bg-amber-100 text-amber-800 font-bold',
        rejected: 'bg-slate-100 text-slate-600',
      }[e.status] || 'bg-slate-100 text-slate-700';

      const dateStr = new Date(e.created_at).toLocaleTimeString();
      const canRollback = e.can_rollback && !e.is_rolled_back && e.status === 'success';

      return `
        <tr class="hover:bg-slate-50/80">
          <td class="py-2.5 px-4 font-mono text-slate-600">
            <div>${dateStr}</div>
            <div class="text-[10px] text-slate-400 truncate max-w-[120px]">${e.event_id || e.id.substring(0, 8)}</div>
          </td>
          <td class="py-2.5 px-4">
            <span class="font-bold text-slate-800">${e.trigger_event || e.trigger_type}</span>
          </td>
          <td class="py-2.5 px-4 font-mono text-slate-700">
            ${e.action_executed}
          </td>
          <td class="py-2.5 px-4">
            <span class="px-2 py-0.5 rounded text-[10px] uppercase font-bold ${statusBadge}">
              ${e.status}
            </span>
          </td>
          <td class="py-2.5 px-4 text-slate-500 font-mono">
            ${e.execution_time_ms}ms
          </td>
          <td class="py-2.5 px-4 text-right">
            ${
              canRollback
                ? `<button class="btn-rollback px-2.5 py-1 text-[11px] font-bold text-amber-700 bg-amber-50 hover:bg-amber-100 border border-amber-200 rounded" data-exec-id="${e.id}">
                     ↩ Revertir
                   </button>`
                : e.is_rolled_back
                ? `<span class="text-[11px] text-slate-400 font-medium">Revertido</span>`
                : `<span class="text-[11px] text-slate-300">-</span>`
            }
          </td>
        </tr>
      `;
    })
    .join('');
}

function bindEvents(container) {
  // Tabs navigation
  const tabs = ['rules', 'approvals', 'executions'];
  tabs.forEach((tab) => {
    const btn = document.getElementById(`tab-${tab}`);
    if (btn) {
      btn.addEventListener('click', () => {
        tabs.forEach((t) => {
          document.getElementById(`tab-${t}`).className =
            'tab-btn pb-3 px-1 border-b-2 border-transparent text-slate-500 hover:text-slate-700 font-bold flex items-center gap-2';
          document.getElementById(`tab-content-${t}`).classList.add('hidden');
        });
        btn.className =
          'tab-btn pb-3 px-1 border-b-2 border-amber-600 text-amber-600 font-bold flex items-center gap-2';
        document.getElementById(`tab-content-${tab}`).classList.remove('hidden');
      });
    }
  });

  // Global Kill Switch
  const killSwitch = document.getElementById('global-kill-switch');
  if (killSwitch) {
    killSwitch.addEventListener('change', async (e) => {
      try {
        const isActive = e.target.checked;
        await api.put('/api/v1/automation/config', { is_engine_active: isActive });
        showToast(isActive ? 'Motor global ACTIVADO' : 'Motor global PAUSADO (Kill Switch)', isActive ? 'success' : 'warning');
        await loadAutomationData();
      } catch (err) {
        showToast('Error al modificar interruptor: ' + err.message, 'error');
      }
    });
  }

  // Guardar modalidades por módulo
  const btnSaveModes = document.getElementById('btn-save-modes');
  if (btnSaveModes) {
    btnSaveModes.addEventListener('click', async () => {
      try {
        const selects = document.querySelectorAll('.module-mode-select');
        const modes = {};
        selects.forEach((sel) => {
          modes[sel.dataset.module] = sel.value;
        });
        await api.put('/api/v1/automation/config', { module_modes: modes });
        showToast('Modalidades de módulos guardadas exitosamente', 'success');
        await loadAutomationData();
      } catch (err) {
        showToast('Error al guardar modalidades: ' + err.message, 'error');
      }
    });
  }

  // Abrir y cerrar modal de regla
  const btnNewRule = document.getElementById('btn-new-rule');
  const modal = document.getElementById('rule-modal');
  const btnCloseModal = document.getElementById('btn-close-modal');
  const btnCancelRule = document.getElementById('btn-cancel-rule');

  if (btnNewRule && modal) {
    btnNewRule.addEventListener('click', () => modal.classList.remove('hidden'));
  }
  if (btnCloseModal && modal) {
    btnCloseModal.addEventListener('click', () => modal.classList.add('hidden'));
  }
  if (btnCancelRule && modal) {
    btnCancelRule.addEventListener('click', () => modal.classList.add('hidden'));
  }

  // Crear regla form submit
  const formRule = document.getElementById('form-rule');
  if (formRule) {
    formRule.addEventListener('submit', async (e) => {
      e.preventDefault();
      try {
        const payload = {
          name: document.getElementById('rule-name').value.trim(),
          module: document.getElementById('rule-module').value,
          trigger_type: 'event',
          trigger_event: document.getElementById('rule-trigger-event').value,
          action_type: document.getElementById('rule-action-type').value,
          execution_mode: document.getElementById('rule-execution-mode').value,
          conditions: [],
          condition_match_type: 'ALL',
          action_parameters: {},
          safety_limits: {
            min_price: parseFloat(document.getElementById('rule-min-price').value) || undefined,
            min_margin_pct: parseFloat(document.getElementById('rule-min-margin').value) || undefined,
            cooldown_seconds: parseInt(document.getElementById('rule-cooldown').value) || 30,
          },
        };

        await api.post('/api/v1/automation/rules', payload);
        showToast('Regla ECA creada exitosamente', 'success');
        modal.classList.add('hidden');
        formRule.reset();
        await loadAutomationData();
      } catch (err) {
        showToast('Error al crear regla: ' + err.message, 'error');
      }
    });
  }

  // Delegación de eventos para botones dinámicos
  container.addEventListener('click', async (e) => {
    // Probar manualmente
    const btnExec = e.target.closest('.btn-exec-manual');
    if (btnExec) {
      const ruleId = btnExec.dataset.ruleId;
      try {
        await api.post(`/api/v1/automation/rules/${ruleId}/execute`, {});
        showToast('Regla ejecutada manualmente con éxito', 'success');
        await loadAutomationData();
      } catch (err) {
        showToast('Fallo al ejecutar regla: ' + err.message, 'error');
      }
      return;
    }

    // Reset Circuit Breaker
    const btnResetCB = e.target.closest('.btn-reset-cb');
    if (btnResetCB) {
      const ruleId = btnResetCB.dataset.ruleId;
      try {
        await api.post(`/api/v1/automation/rules/${ruleId}/reset-circuit-breaker`, {});
        showToast('Circuit Breaker reactivado para la regla', 'success');
        await loadAutomationData();
      } catch (err) {
        showToast('Error al resetear CB: ' + err.message, 'error');
      }
      return;
    }

    // Aprobar ejecución
    const btnApprove = e.target.closest('.btn-approve');
    if (btnApprove) {
      const execId = btnApprove.dataset.execId;
      try {
        await api.post(`/api/v1/automation/executions/${execId}/approve`, { action: 'approve' });
        showToast('Acción autorizada y ejecutada exitosamente', 'success');
        await loadAutomationData();
      } catch (err) {
        showToast('Error al autorizar: ' + err.message, 'error');
      }
      return;
    }

    // Rechazar ejecución
    const btnReject = e.target.closest('.btn-reject');
    if (btnReject) {
      const execId = btnReject.dataset.execId;
      try {
        await api.post(`/api/v1/automation/executions/${execId}/reject`, { action: 'reject', notes: 'Rechazado desde panel' });
        showToast('Acción rechazada y descartada', 'info');
        await loadAutomationData();
      } catch (err) {
        showToast('Error al rechazar: ' + err.message, 'error');
      }
      return;
    }

    // Revertir (Rollback)
    const btnRollback = e.target.closest('.btn-rollback');
    if (btnRollback) {
      const execId = btnRollback.dataset.execId;
      if (!confirm('¿Confirma que desea revertir esta acción compensatoria?')) return;
      try {
        const res = await api.post(`/api/v1/automation/executions/${execId}/rollback`, {});
        showToast(res.message || 'Acción revertida exitosamente', 'success');
        await loadAutomationData();
      } catch (err) {
        showToast('Error al revertir: ' + err.message, 'error');
      }
      return;
    }

    // Eliminar regla
    const btnDelete = e.target.closest('.btn-delete-rule');
    if (btnDelete) {
      const ruleId = btnDelete.dataset.ruleId;
      if (!confirm('¿Está seguro de eliminar esta regla?')) return;
      try {
        await api.delete(`/api/v1/automation/rules/${ruleId}`);
        showToast('Regla eliminada', 'info');
        await loadAutomationData();
      } catch (err) {
        showToast('Error al eliminar: ' + err.message, 'error');
      }
      return;
    }
  });
}

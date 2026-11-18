/**
 * Vista de Integraciones y Conector Oficial de Mercado Libre México.
 * Gestión multi-cuenta OAuth 2.0, diagnóstico en vivo, renovación de tokens,
 * y Monitor de Sincronización en tiempo real con Conciliación Periódica.
 */

import { api } from '../api.js';
import { state } from '../state.js';
import { icons } from '../icons.js';
import { showToast } from '../components/toast.js';
import { openModal, closeModal } from '../components/modal.js';

let meliAccounts = [];
let monitorMetrics = null;
let syncEvents = [];
let reconciliationLogs = [];

export async function renderIntegrations(container) {
  container.innerHTML = `
    <div class="space-y-6 animate-fade-in">
      <!-- Encabezado -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 class="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            ${icons.plug} Conector Oficial Mercado Libre México
          </h1>
          <p class="text-sm text-slate-500 mt-1">
            Módulo independiente <strong>MercadoLibreConnector</strong> con OAuth 2.0, auto-refresh de tokens y motor de sincronización idempotente.
          </p>
        </div>
        <div class="flex items-center gap-2">
          <button id="btn-trigger-reconciliation" class="btn-secondary flex items-center gap-1.5 text-xs font-semibold px-3 py-2">
            ${icons.refresh} Conciliación Periódica
          </button>
          <button id="btn-oauth-connect" class="btn-primary flex items-center gap-2 bg-yellow-400 hover:bg-yellow-500 text-slate-900 border-none font-bold shadow-sm">
            ${icons.plus} Conectar Cuenta vía OAuth
          </button>
          <button id="btn-manual-connect" class="px-3.5 py-2 border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold rounded-xl transition-smooth shadow-sm">
            Ingreso Manual
          </button>
        </div>
      </div>

      <!-- Cuentas de Mercado Libre Vinculadas -->
      <div class="space-y-3">
        <div class="flex items-center justify-between">
          <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
            <span class="w-3 h-3 rounded-full bg-yellow-400"></span> Cuentas de Mercado Libre Vinculadas
          </h2>
          <span class="text-xs text-slate-500">Cifrado de credenciales AES-256 en reposo</span>
        </div>

        <div id="meli-accounts-grid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div class="card p-6 text-center text-slate-400 col-span-full">Cargando cuentas vinculadas...</div>
        </div>
      </div>

      <!-- PANEL: MONITOR DE SINCRONIZACIÓN EN TIEMPO REAL -->
      <div class="card p-5 space-y-5 border-l-4 border-l-blue-600">
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-100 pb-3">
          <div>
            <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
              ${icons.zap} Monitor de Sincronización Oficial MeLi
            </h2>
            <p class="text-xs text-slate-500 mt-0.5">
              Control de webhooks, colas asíncronas, idempotencia y prevención de duplicados de pedidos y movimientos.
            </p>
          </div>
          <div class="flex items-center gap-2">
            <button id="btn-refresh-monitor" class="px-3 py-1.5 text-xs font-semibold text-blue-700 bg-blue-50 hover:bg-blue-100 rounded-lg transition-smooth flex items-center gap-1.5">
              ${icons.refresh} Refrescar Métricas
            </button>
            <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800">
              <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span> Motor Activo
            </span>
          </div>
        </div>

        <!-- Tarjetas KPI del Monitor -->
        <div class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3 text-center" id="monitor-kpis">
          <div class="p-3 bg-slate-50 border border-slate-200 rounded-xl">
            <div class="text-[10px] uppercase font-bold text-slate-400 tracking-wider">Última Sync</div>
            <div id="kpi-last-sync" class="text-xs font-bold text-slate-800 mt-1 truncate">Consultando...</div>
          </div>
          <div class="p-3 bg-slate-50 border border-slate-200 rounded-xl">
            <div class="text-[10px] uppercase font-bold text-slate-400 tracking-wider">Recibidos</div>
            <div id="kpi-received" class="text-lg font-black text-slate-900 mt-0.5">0</div>
          </div>
          <div class="p-3 bg-emerald-50 border border-emerald-200 rounded-xl">
            <div class="text-[10px] uppercase font-bold text-emerald-600 tracking-wider">Procesados</div>
            <div id="kpi-processed" class="text-lg font-black text-emerald-700 mt-0.5">0</div>
          </div>
          <div class="p-3 bg-amber-50 border border-amber-200 rounded-xl">
            <div class="text-[10px] uppercase font-bold text-amber-600 tracking-wider">Pendientes</div>
            <div id="kpi-pending" class="text-lg font-black text-amber-700 mt-0.5">0</div>
          </div>
          <div class="p-3 bg-rose-50 border border-rose-200 rounded-xl">
            <div class="text-[10px] uppercase font-bold text-rose-600 tracking-wider">Fallidos</div>
            <div id="kpi-failed" class="text-lg font-black text-rose-700 mt-0.5">0</div>
          </div>
          <div class="p-3 bg-indigo-50 border border-indigo-200 rounded-xl">
            <div class="text-[10px] uppercase font-bold text-indigo-600 tracking-wider">Reintentos</div>
            <div id="kpi-retried" class="text-lg font-black text-indigo-700 mt-0.5">0</div>
          </div>
          <div class="p-3 bg-purple-50 border border-purple-200 rounded-xl">
            <div class="text-[10px] uppercase font-bold text-purple-600 tracking-wider">Diferencias</div>
            <div id="kpi-discrepancies" class="text-lg font-black text-purple-700 mt-0.5">0</div>
          </div>
        </div>

        <!-- Distribución de los 8 Tópicos Oficiales -->
        <div class="space-y-2">
          <div class="text-xs font-bold text-slate-700 uppercase tracking-wider">
            Tópicos Oficiales de Mercado Libre México
          </div>
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs" id="topics-badges">
            <div class="p-2.5 bg-white border border-slate-200 rounded-lg">
              <div class="flex justify-between items-center">
                <span class="font-bold text-slate-800">orders_v2</span>
                <span id="topic-count-orders_v2" class="badge badge-info">0</span>
              </div>
              <div class="text-[11px] text-slate-500 mt-0.5">Órdenes y reserva de stock</div>
            </div>
            <div class="p-2.5 bg-white border border-slate-200 rounded-lg">
              <div class="flex justify-between items-center">
                <span class="font-bold text-slate-800">payments</span>
                <span id="topic-count-payments" class="badge badge-info">0</span>
              </div>
              <div class="text-[11px] text-slate-500 mt-0.5">Cobros y transacciones</div>
            </div>
            <div class="p-2.5 bg-white border border-slate-200 rounded-lg">
              <div class="flex justify-between items-center">
                <span class="font-bold text-slate-800">items</span>
                <span id="topic-count-items" class="badge badge-info">0</span>
              </div>
              <div class="text-[11px] text-slate-500 mt-0.5">Publicaciones y variaciones</div>
            </div>
            <div class="p-2.5 bg-white border border-slate-200 rounded-lg">
              <div class="flex justify-between items-center">
                <span class="font-bold text-slate-800">shipments</span>
                <span id="topic-count-shipments" class="badge badge-info">0</span>
              </div>
              <div class="text-[11px] text-slate-500 mt-0.5">Guías y rastreo Mercado Envíos</div>
            </div>
            <div class="p-2.5 bg-white border border-slate-200 rounded-lg">
              <div class="flex justify-between items-center">
                <span class="font-bold text-slate-800">claims</span>
                <span id="topic-count-claims" class="badge badge-info">0</span>
              </div>
              <div class="text-[11px] text-slate-500 mt-0.5">Reclamos y disputas post-venta</div>
            </div>
            <div class="p-2.5 bg-white border border-slate-200 rounded-lg">
              <div class="flex justify-between items-center">
                <span class="font-bold text-slate-800">public_candidates</span>
                <span id="topic-count-public_candidates" class="badge badge-info">0</span>
              </div>
              <div class="text-[11px] text-slate-500 mt-0.5">Elegibilidad para promociones</div>
            </div>
            <div class="p-2.5 bg-white border border-slate-200 rounded-lg">
              <div class="flex justify-between items-center">
                <span class="font-bold text-slate-800">public_offers</span>
                <span id="topic-count-public_offers" class="badge badge-info">0</span>
              </div>
              <div class="text-[11px] text-slate-500 mt-0.5">Campañas de ofertas activas</div>
            </div>
            <div class="p-2.5 bg-white border border-slate-200 rounded-lg">
              <div class="flex justify-between items-center">
                <span class="font-bold text-slate-800">items_prices</span>
                <span id="topic-count-items_prices" class="badge badge-info">0</span>
              </div>
              <div class="text-[11px] text-slate-500 mt-0.5">Precios y condiciones comerciales</div>
            </div>
          </div>
        </div>

        <!-- Tabla de Eventos Recientes de Sincronización -->
        <div class="space-y-2 pt-2">
          <div class="flex items-center justify-between">
            <h3 class="text-xs font-bold text-slate-700 uppercase tracking-wider">
              Registro de Eventos y Notificaciones Push
            </h3>
            <span class="text-[11px] text-slate-500">Respuesta oficial &lt; 500 ms</span>
          </div>

          <div class="overflow-x-auto rounded-xl border border-slate-200">
            <table class="w-full text-left text-xs text-slate-700">
              <thead class="bg-slate-50 text-[10px] uppercase font-bold text-slate-500 border-b border-slate-200">
                <tr>
                  <th class="py-2.5 px-3">Tópico</th>
                  <th class="py-2.5 px-3">Recurso MeLi</th>
                  <th class="py-2.5 px-3">Estado</th>
                  <th class="py-2.5 px-3">Reintentos</th>
                  <th class="py-2.5 px-3">Fecha y Hora</th>
                  <th class="py-2.5 px-3 text-right">Acción</th>
                </tr>
              </thead>
              <tbody id="sync-events-tbody" class="divide-y divide-slate-100">
                <tr>
                  <td colspan="6" class="py-4 text-center text-slate-400">Cargando eventos de sincronización...</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Historial de Conciliaciones Periódicas -->
        <div class="space-y-2 pt-2 border-t border-slate-100">
          <div class="flex items-center justify-between">
            <h3 class="text-xs font-bold text-slate-700 uppercase tracking-wider">
              Historial de Conciliaciones Periódicas (Recuperación Activa)
            </h3>
            <span class="text-[11px] text-slate-500">Independiente de Webhooks</span>
          </div>

          <div class="overflow-x-auto rounded-xl border border-slate-200">
            <table class="w-full text-left text-xs text-slate-700">
              <thead class="bg-slate-50 text-[10px] uppercase font-bold text-slate-500 border-b border-slate-200">
                <tr>
                  <th class="py-2 px-3">Tipo</th>
                  <th class="py-2 px-3">Estatus</th>
                  <th class="py-2 px-3">Órdenes Sincronizadas</th>
                  <th class="py-2 px-3">Discrepancias Detectadas</th>
                  <th class="py-2 px-3">Inicio</th>
                  <th class="py-2 px-3">Fin</th>
                </tr>
              </thead>
              <tbody id="reconciliation-logs-tbody" class="divide-y divide-slate-100">
                <tr>
                  <td colspan="6" class="py-3 text-center text-slate-400">No hay registros de conciliación aún.</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Resiliencia y Métricas del Conector -->
      <div class="card p-5 space-y-4">
        <div class="border-b border-slate-100 pb-3">
          <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
            ${icons.database} Políticas de Resiliencia del Conector
          </h2>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
          <div class="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-1">
            <div class="font-bold text-slate-900 flex items-center gap-1.5">
              <span class="w-2.5 h-2.5 rounded-full bg-emerald-500"></span> Control de Rate Limits
            </div>
            <div class="text-slate-500">Inspección de cabeceras x-ratelimit-remaining y x-ratelimit-reset para evitar bloqueos HTTP 429.</div>
            <div class="font-mono text-slate-700 pt-1">Algoritmo: Exponential Backoff con Jitter</div>
          </div>
          <div class="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-1">
            <div class="font-bold text-slate-900 flex items-center gap-1.5">
              <span class="w-2.5 h-2.5 rounded-full bg-emerald-500"></span> Auto-renovación con Mutex
            </div>
            <div class="text-slate-500">Bloqueo asíncrono para prevenir tormentas de refresco en rotación única de refresh tokens.</div>
            <div class="font-mono text-slate-700 pt-1">Umbral preventivo: 300 segundos</div>
          </div>
          <div class="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-1">
            <div class="font-bold text-slate-900 flex items-center gap-1.5">
              <span class="w-2.5 h-2.5 rounded-full bg-emerald-500"></span> Cifrado Criptográfico
            </div>
            <div class="text-slate-500">Protección estricta de Access Tokens y Refresh Tokens en reposo con AES-256.</div>
            <div class="font-mono text-slate-700 pt-1">Estándar: AES-128-CBC / HMAC-SHA256</div>
          </div>
        </div>
      </div>
    </div>
  `;

  const btnOAuth = container.querySelector('#btn-oauth-connect');
  const btnManual = container.querySelector('#btn-manual-connect');
  const btnReconcile = container.querySelector('#btn-trigger-reconciliation');
  const btnRefreshMon = container.querySelector('#btn-refresh-monitor');

  if (btnOAuth) btnOAuth.addEventListener('click', openOAuthFlowModal);
  if (btnManual) btnManual.addEventListener('click', openManualConnectModal);
  if (btnReconcile) btnReconcile.addEventListener('click', openReconcileModal);
  if (btnRefreshMon) btnRefreshMon.addEventListener('click', async () => {
    await loadMonitorData();
    showToast('Métricas del monitor actualizadas', 'info');
  });

  await loadMeliAccounts();
  await loadMonitorData();
}

async function loadMeliAccounts() {
  try {
    const res = await api.get('/meli-accounts?limit=20');
    meliAccounts = res.items || [];
    renderMeliGrid();
  } catch (err) {
    showToast(err.message || 'Error cargando cuentas MeLi', 'error');
  }
}

function renderMeliGrid() {
  const grid = document.getElementById('meli-accounts-grid');
  if (!grid) return;

  if (meliAccounts.length === 0) {
    grid.innerHTML = `
      <div class="card p-8 text-center text-slate-400 col-span-full space-y-2">
        <div class="text-base font-bold text-slate-700">No hay cuentas de Mercado Libre vinculadas para esta empresa.</div>
        <p class="text-xs text-slate-500">
          Haz clic en "Conectar Cuenta vía OAuth" para autorizar la sincronización oficial de inventario, órdenes y publicaciones.
        </p>
      </div>
    `;
    return;
  }

  grid.innerHTML = meliAccounts.map((acc) => {
    const isExpired = new Date(acc.token_expires_at) < new Date();
    let statusBadge = '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700">Conectada</span>';
    if (!acc.is_active) {
      statusBadge = '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-600">Desconectada</span>';
    } else if (isExpired) {
      statusBadge = '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700">Token Expirado</span>';
    }

    return `
      <div class="card p-5 space-y-3 relative border-t-4 border-yellow-400 flex flex-col justify-between">
        <div>
          <div class="flex items-start justify-between">
            <div>
              <div class="text-base font-bold text-slate-900 flex items-center gap-2">
                ${acc.nickname || 'Cuenta Mercado Libre'}
              </div>
              <div class="font-mono text-xs text-slate-500">Seller ID: ${acc.meli_user_id}</div>
            </div>
            ${statusBadge}
          </div>

          <div class="p-2.5 bg-slate-50 rounded-lg text-xs space-y-1 font-mono mt-3">
            <div class="text-slate-500 flex justify-between">
              <span>Sitio:</span>
              <span class="font-bold text-slate-800">${acc.site_id} (México)</span>
            </div>
            <div class="text-slate-500 flex justify-between">
              <span>Expiración Token:</span>
              <span class="font-bold ${isExpired ? 'text-amber-700' : 'text-slate-700'}">
                ${new Date(acc.token_expires_at).toLocaleString('es-MX')}
              </span>
            </div>
            <div class="text-slate-500 flex justify-between">
              <span>Seguridad:</span>
              <span class="text-emerald-700 font-bold">Cifrado AES-256</span>
            </div>
          </div>
        </div>

        <div class="pt-3 border-t border-slate-100 flex flex-wrap items-center justify-between gap-2 text-xs">
          <div class="flex items-center space-x-2">
            <button
              data-acc-id="${acc.id}"
              class="btn-test-conn text-blue-600 hover:text-blue-800 font-bold hover:underline"
            >
              Probar Conexión
            </button>
            <button
              data-acc-id="${acc.id}"
              class="btn-refresh-token text-slate-600 hover:text-slate-900 font-medium hover:underline"
            >
              Renovar Token
            </button>
          </div>

          <div>
            ${acc.is_active ? `
              <button data-acc-id="${acc.id}" class="btn-disconnect text-rose-600 hover:text-rose-800 font-medium hover:underline">
                Desconectar
              </button>
            ` : `
              <button data-acc-id="${acc.id}" class="btn-reconnect text-emerald-600 hover:text-emerald-800 font-bold hover:underline">
                Reconectar
              </button>
            `}
          </div>
        </div>
      </div>
    `;
  }).join('');

  grid.querySelectorAll('.btn-test-conn').forEach((btn) => {
    btn.addEventListener('click', () => runConnectionDiagnostic(btn.dataset.accId));
  });

  grid.querySelectorAll('.btn-refresh-token').forEach((btn) => {
    btn.addEventListener('click', () => forceRefreshToken(btn.dataset.accId));
  });

  grid.querySelectorAll('.btn-disconnect').forEach((btn) => {
    btn.addEventListener('click', () => disconnectAccount(btn.dataset.accId));
  });

  grid.querySelectorAll('.btn-reconnect').forEach((btn) => {
    btn.addEventListener('click', () => openReconnectModal(btn.dataset.accId));
  });
}

async function loadMonitorData() {
  try {
    const [metrics, eventsRes, logsRes] = await Promise.all([
      api.get('/sync/monitor'),
      api.get('/sync/events?limit=15'),
      api.get('/sync/reconciliation-logs?limit=5'),
    ]);

    monitorMetrics = metrics;
    syncEvents = eventsRes.items || [];
    reconciliationLogs = logsRes.items || [];

    renderMonitorKPIs();
    renderTopicBadges();
    renderSyncEventsTable();
    renderReconciliationLogsTable();
  } catch (err) {
    console.warn('Aviso cargando datos del monitor de sincronización:', err);
  }
}

function renderMonitorKPIs() {
  if (!monitorMetrics) return;

  const kpiLastSync = document.getElementById('kpi-last-sync');
  const kpiReceived = document.getElementById('kpi-received');
  const kpiProcessed = document.getElementById('kpi-processed');
  const kpiPending = document.getElementById('kpi-pending');
  const kpiFailed = document.getElementById('kpi-failed');
  const kpiRetried = document.getElementById('kpi-retried');
  const kpiDisc = document.getElementById('kpi-discrepancies');

  if (kpiLastSync) {
    if (monitorMetrics.last_sync_at) {
      kpiLastSync.textContent = new Date(monitorMetrics.last_sync_at).toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      kpiLastSync.title = new Date(monitorMetrics.last_sync_at).toLocaleString('es-MX');
    } else {
      kpiLastSync.textContent = 'Sin eventos';
    }
  }

  if (kpiReceived) kpiReceived.textContent = monitorMetrics.total_received || 0;
  if (kpiProcessed) kpiProcessed.textContent = monitorMetrics.total_processed || 0;
  if (kpiPending) kpiPending.textContent = monitorMetrics.total_pending || 0;
  if (kpiFailed) kpiFailed.textContent = monitorMetrics.total_failed || 0;
  if (kpiRetried) kpiRetried.textContent = monitorMetrics.total_retried || 0;
  if (kpiDisc) kpiDisc.textContent = monitorMetrics.discrepancies_detected || 0;
}

function renderTopicBadges() {
  if (!monitorMetrics || !monitorMetrics.by_topic) return;
  const topics = [
    'orders_v2', 'payments', 'items', 'shipments',
    'claims', 'public_candidates', 'public_offers', 'items_prices'
  ];

  topics.forEach((topic) => {
    const el = document.getElementById(`topic-count-${topic}`);
    if (el) {
      const count = monitorMetrics.by_topic[topic] || 0;
      el.textContent = count;
      if (count > 0) {
        el.className = 'px-2 py-0.5 rounded-full text-[11px] font-bold bg-blue-100 text-blue-800';
      } else {
        el.className = 'px-2 py-0.5 rounded-full text-[11px] font-medium bg-slate-100 text-slate-500';
      }
    }
  });
}

function renderSyncEventsTable() {
  const tbody = document.getElementById('sync-events-tbody');
  if (!tbody) return;

  if (syncEvents.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" class="py-4 text-center text-slate-400">
          No hay eventos de sincronización registrados aún.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = syncEvents.map((evt) => {
    let statusClass = 'bg-slate-100 text-slate-700';
    let statusLabel = evt.status;
    if (evt.status === 'processed') {
      statusClass = 'bg-emerald-100 text-emerald-800';
      statusLabel = 'Procesado';
    } else if (evt.status === 'pending' || evt.status === 'processing') {
      statusClass = 'bg-amber-100 text-amber-800';
      statusLabel = evt.status === 'processing' ? 'Procesando' : 'Pendiente';
    } else if (evt.status === 'failed') {
      statusClass = 'bg-rose-100 text-rose-800';
      statusLabel = 'Fallido';
    } else if (evt.status === 'duplicate') {
      statusClass = 'bg-slate-200 text-slate-600';
      statusLabel = 'Duplicado';
    }

    const canRetry = evt.status === 'failed' || evt.status === 'pending';

    return `
      <tr class="hover:bg-slate-50 transition-smooth">
        <td class="py-2.5 px-3 font-semibold text-slate-900 font-mono text-[11px]">
          ${evt.topic}
        </td>
        <td class="py-2.5 px-3 font-mono text-slate-600 truncate max-w-xs" title="${evt.resource}">
          ${evt.resource}
        </td>
        <td class="py-2.5 px-3">
          <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold ${statusClass}">
            ${statusLabel}
          </span>
        </td>
        <td class="py-2.5 px-3 text-center font-mono">
          ${evt.retry_count} / ${evt.max_retries}
        </td>
        <td class="py-2.5 px-3 text-slate-500 text-[11px]">
          ${new Date(evt.received_at).toLocaleString('es-MX')}
        </td>
        <td class="py-2.5 px-3 text-right">
          ${canRetry ? `
            <button data-event-id="${evt.id}" class="btn-retry-event text-blue-600 hover:text-blue-800 font-bold hover:underline">
              Reintentar
            </button>
          ` : `
            <span class="text-slate-300">-</span>
          `}
        </td>
      </tr>
    `;
  }).join('');

  tbody.querySelectorAll('.btn-retry-event').forEach((btn) => {
    btn.addEventListener('click', () => retrySyncEvent(btn.dataset.eventId));
  });
}

async function retrySyncEvent(eventId) {
  try {
    const res = await api.post(`/sync/events/${eventId}/retry`);
    showToast(`Reintento ejecutado: ${res.event_status}`, 'success');
    await loadMonitorData();
  } catch (err) {
    showToast(err.message || 'Error reintentando evento', 'error');
  }
}

function renderReconciliationLogsTable() {
  const tbody = document.getElementById('reconciliation-logs-tbody');
  if (!tbody) return;

  if (reconciliationLogs.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" class="py-3 text-center text-slate-400">
          No hay registros de conciliación periódica todavía.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = reconciliationLogs.map((log) => `
    <tr class="hover:bg-slate-50">
      <td class="py-2 px-3 font-medium text-slate-800">${log.sync_type}</td>
      <td class="py-2 px-3">
        <span class="inline-flex px-2 py-0.5 rounded text-[10px] font-bold ${log.status === 'completed' ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'}">
          ${log.status === 'completed' ? 'Completado' : 'Fallido'}
        </span>
      </td>
      <td class="py-2 px-3 font-bold text-slate-900">${log.orders_synced}</td>
      <td class="py-2 px-3 font-bold ${log.discrepancies_found > 0 ? 'text-amber-600' : 'text-slate-600'}">${log.discrepancies_found}</td>
      <td class="py-2 px-3 text-slate-500">${new Date(log.started_at).toLocaleTimeString('es-MX')}</td>
      <td class="py-2 px-3 text-slate-500">${new Date(log.finished_at).toLocaleTimeString('es-MX')}</td>
    </tr>
  `).join('');
}

function openReconcileModal() {
  const currentCompany = state.currentCompany;
  if (!currentCompany) {
    showToast('Selecciona una empresa primero', 'error');
    return;
  }

  openModal({
    title: "Ejecutar Conciliación Periódica MeLi",
    size: "md",
    content: `
      <div class="space-y-4 text-xs">
        <p class="text-slate-600">
          Inspecciona activamente en Mercado Libre las órdenes de las últimas horas para recuperar eventos perdidos y sincronizar stock sin duplicar.
        </p>
        <div>
          <label class="block font-bold text-slate-700 mb-1">Ventana de Inspección (Horas hacia atrás) *</label>
          <select id="reconcile-lookback" class="w-full px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-600">
            <option value="12">Últimas 12 horas</option>
            <option value="24" selected>Últimas 24 horas (Recomendado)</option>
            <option value="48">Últimas 48 horas</option>
            <option value="72">Últimas 72 horas</option>
            <option value="168">Últimos 7 días (Completo)</option>
          </select>
        </div>
        <div class="p-3 bg-blue-50 border border-blue-200 rounded-xl text-blue-900">
          ℹ Si se detectan órdenes pagadas o canceladas no registradas, el motor creará el pedido y actualizará las reservas en bodega local automáticamente sin duplicar.
        </div>
      </div>
    `,
    confirmText: "Iniciar Conciliación",
    onConfirm: async () => {
      const lookback = parseInt(document.getElementById("reconcile-lookback").value) || 24;
      showToast("Ejecutando conciliación con Mercado Libre...", "info");
      const res = await api.post("/sync/reconcile", { lookback_hours: lookback });
      const totalOrders = (res || []).reduce((acc, curr) => acc + (curr.orders_synced || 0), 0);
      const totalDisc = (res || []).reduce((acc, curr) => acc + (curr.discrepancies_found || 0), 0);
      showToast(`Conciliación completada: ${totalOrders} órdenes sincronizadas, ${totalDisc} discrepancias corregidas.`, 'success');
      await loadMonitorData();
    },
  });
}

async function runConnectionDiagnostic(accountId) {
  try {
    showToast("Ejecutando diagnóstico oficial con Mercado Libre...", "info");
    const res = await api.post(`/meli-accounts/${accountId}/test-connection`);
    if (res.connected) {
      showToast(
        `Conexión exitosa con MeLi. Seller: ${res.seller_nickname || res.seller_id}. Latencia: ${res.latency_ms} ms.`,
        "success"
      );
    } else {
      showToast(`Diagnóstico fallido: ${res.error_message}`, "error");
    }
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function forceRefreshToken(accountId) {
  try {
    showToast("Renovando Access Token mediante OAuth 2.0...", "info");
    const res = await api.post(`/meli-accounts/${accountId}/refresh-token`);
    showToast(
      `Token renovado. Válido por ${Math.round(res.expires_in / 3600)} horas.`,
      "success"
    );
    await loadMeliAccounts();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function disconnectAccount(accountId) {
  if (!confirm("¿Estás seguro de desconectar esta cuenta de Mercado Libre? Las notificaciones push dejarán de recibirse.")) return;
  try {
    await api.post(`/meli-accounts/${accountId}/disconnect`);
    showToast("Cuenta desconectada exitosamente.", "info");
    await loadMeliAccounts();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function openOAuthFlowModal() {
  const currentCompany = state.currentCompany;
  if (!currentCompany) {
    showToast('Selecciona una empresa primero', 'error');
    return;
  }

  try {
    const res = await api.get(`/meli-accounts/oauth-url?company_id=${currentCompany.id}`);

    openModal({
      title: "Vincular Cuenta Oficial vía OAuth 2.0",
      size: "md",
      content: `
        <div class="space-y-4 text-xs">
          <p class="text-slate-600">
            Mercado Libre requiere autorización explícita para que el ERP sincronice inventario, publicaciones y pedidos:
          </p>
          <div class="p-3 bg-amber-50 border border-amber-200 rounded-xl space-y-2">
            <div class="font-bold text-amber-900">Paso 1: Abrir ventana de autorización</div>
            <p class="text-amber-800">
              Haz clic en el botón para abrir el portal de autenticación oficial de Mercado Libre México.
            </p>
            <a
              href="${res.authorization_url}"
              target="_blank"
              class="inline-flex items-center gap-2 px-3 py-1.5 bg-yellow-400 text-slate-900 font-bold rounded-lg hover:bg-yellow-500 shadow-sm"
            >
              Abrir Mercado Libre OAuth ↗
            </a>
          </div>

          <div class="space-y-2">
            <div class="font-bold text-slate-800">Paso 2: Código de Autorización (TG-code)</div>
            <p class="text-slate-500">
              Tras autorizar en MeLi, serás redirigido a una URL que contiene un parámetro <code class="bg-slate-100 px-1 py-0.5 rounded">code=TG-...</code>. Pega ese código o la URL completa aquí:
            </p>
            <input
              type="text"
              id="oauth-code-input"
              placeholder="TG-65a8... o URL completa"
              class="w-full px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-600 focus:outline-none font-mono text-xs"
            />
          </div>
        </div>
      `,
      confirmText: "Completar Vinculación",
      onConfirm: async () => {
        const codeInput = document.getElementById("oauth-code-input").value.trim();
        if (!codeInput) throw new Error("Debes proporcionar el código de autorización.");

        let cleanCode = codeInput;
        if (codeInput.includes("code=")) {
          const match = codeInput.match(/code=([^&]+)/);
          if (match) cleanCode = match[1];
        }

        await api.post("/meli-accounts/oauth-callback", {
          code: cleanCode,
          state: res.state,
          redirect_uri: res.redirect_uri,
        });

        showToast("Cuenta de Mercado Libre vinculada exitosamente vía OAuth.", "success");
        await loadMeliAccounts();
      },
    });
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function openManualConnectModal() {
  const currentCompany = state.currentCompany;
  if (!currentCompany) {
    showToast('Selecciona una empresa primero', 'error');
    return;
  }

  openModal({
    title: "Vinculación Manual de Credenciales MeLi",
    size: "md",
    content: `
      <div class="space-y-3 text-xs">
        <div>
          <label class="block font-bold text-slate-700 mb-1">Nombre o Apodo de la Cuenta *</label>
          <input id="manual-nickname" type="text" placeholder="e.g. Tienda Oficial MeLi" class="w-full px-3 py-2 border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-600 focus:outline-none" />
        </div>

        <div>
          <label class="block font-bold text-slate-700 mb-1">Seller ID Oficial de MeLi *</label>
          <input id="manual-seller-id" type="number" placeholder="123456789" class="w-full px-3 py-2 border border-slate-200 rounded-xl font-mono focus:ring-2 focus:ring-blue-600 focus:outline-none" />
        </div>

        <div>
          <label class="block font-bold text-slate-700 mb-1">Access Token (Plain) *</label>
          <textarea id="manual-access-token" rows="2" placeholder="APP_USR-..." class="w-full px-3 py-2 border border-slate-200 rounded-xl font-mono text-[11px] focus:ring-2 focus:ring-blue-600 focus:outline-none"></textarea>
        </div>

        <div>
          <label class="block font-bold text-slate-700 mb-1">Refresh Token (Plain) *</label>
          <input id="manual-refresh-token" type="text" placeholder="TG-..." class="w-full px-3 py-2 border border-slate-200 rounded-xl font-mono focus:ring-2 focus:ring-blue-600 focus:outline-none" />
        </div>
      </div>
    `,
    confirmText: "Guardar Credenciales Cifradas",
    onConfirm: async () => {
      const nickname = document.getElementById("manual-nickname").value.trim();
      const sellerId = parseInt(document.getElementById("manual-seller-id").value);
      const accessT = document.getElementById("manual-access-token").value.trim();
      const refreshT = document.getElementById("manual-refresh-token").value.trim();

      if (!nickname || isNaN(sellerId) || !accessT || !refreshT) {
        throw new Error("Todos los campos marcados con * son obligatorios.");
      }

      await api.post("/meli-accounts", {
        company_id: currentCompany.id,
        meli_user_id: sellerId,
        nickname: nickname,
        access_token_plain: accessT,
        refresh_token_plain: refreshT,
        expires_in_seconds: 21600,
      });

      showToast("Cuenta de Mercado Libre guardada exitosamente.", "success");
      await loadMeliAccounts();
    },
  });
}

function openReconnectModal(accountId) {
  openModal({
    title: "Reconectar Cuenta de Mercado Libre",
    size: "md",
    content: `
      <div class="space-y-3 text-xs">
        <p class="text-slate-600">Ingresa los nuevos tokens generados para reactivar la sincronización:</p>
        <div>
          <label class="block font-bold text-slate-700 mb-1">Nuevo Access Token *</label>
          <textarea id="reconn-access-token" rows="2" placeholder="APP_USR-..." class="w-full px-3 py-2 border border-slate-200 rounded-xl font-mono text-[11px]"></textarea>
        </div>
        <div>
          <label class="block font-bold text-slate-700 mb-1">Nuevo Refresh Token *</label>
          <input id="reconn-refresh-token" type="text" placeholder="TG-..." class="w-full px-3 py-2 border border-slate-200 rounded-xl font-mono" />
        </div>
      </div>
    `,
    confirmText: "Reactivar Cuenta",
    onConfirm: async () => {
      const accessT = document.getElementById("reconn-access-token").value.trim();
      const refreshT = document.getElementById("reconn-refresh-token").value.trim();
      if (!accessT || !refreshT) throw new Error("Ambos tokens son requeridos.");

      await api.post(`/meli-accounts/${accountId}/reconnect`, {
        access_token_plain: accessT,
        refresh_token_plain: refreshT,
        expires_in_seconds: 21600,
      });

      showToast("Cuenta reactivada exitosamente.", "success");
      await loadMeliAccounts();
    },
  });
}

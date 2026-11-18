/**
 * Centro de Operaciones de Ciberseguridad (SOC), Respaldos Cifrados y Monitoreo SIEM.
 */

import { api } from '../api.js';
import { showToast } from '../components/toast.js';
import { escapeHtml } from '../security.js';

export async function renderSecurity(container) {
  container.innerHTML = `
    <div class="space-y-6">
      <!-- Encabezado de Ciberseguridad -->
      <div class="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
        <div>
          <div class="flex items-center gap-3">
            <span class="p-2.5 bg-emerald-100 text-emerald-800 rounded-lg">
              <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"/></svg>
            </span>
            <div>
              <h1 class="text-2xl font-bold text-slate-900 tracking-tight">Centro de Ciberseguridad & Resiliencia</h1>
              <p class="text-sm text-slate-500">Monitoreo SIEM, detección de amenazas en tiempo real, respaldos cifrados y recuperación ante desastres.</p>
            </div>
          </div>
        </div>
        <div class="flex items-center gap-3">
          <button id="btn-create-backup" class="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg shadow-sm flex items-center gap-2 text-sm transition-colors">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4"/></svg>
            Generar Respaldo Cifrado
          </button>
          <button id="btn-refresh-security" class="px-3 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-sm font-medium transition-colors">
            Refrescar
          </button>
        </div>
      </div>

      <!-- Tarjetas de Métricas de Seguridad -->
      <div class="grid grid-cols-1 md:grid-cols-4 gap-4" id="security-kpis">
        <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <p class="text-xs font-semibold uppercase text-slate-500 tracking-wider">Estado del Escudo</p>
          <p class="text-2xl font-bold text-emerald-600 mt-2 flex items-center gap-2">
            <span class="w-3 h-3 bg-emerald-500 rounded-full animate-pulse"></span>
            Activo & Blindado
          </p>
          <p class="text-xs text-slate-500 mt-1">10 barreras de defensa activas</p>
        </div>
        <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <p class="text-xs font-semibold uppercase text-slate-500 tracking-wider">Protección de Datos</p>
          <p class="text-2xl font-bold text-slate-900 mt-2">AES-128 / Fernet</p>
          <p class="text-xs text-emerald-600 font-medium mt-1">Cifrado simétrico en reposo</p>
        </div>
        <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <p class="text-xs font-semibold uppercase text-slate-500 tracking-wider">Control de Tasa (Rate Limit)</p>
          <p class="text-2xl font-bold text-blue-600 mt-2">Ventana Deslizante</p>
          <p class="text-xs text-slate-500 mt-1">Anti-fuerza bruta & anti-DoS</p>
        </div>
        <div class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <p class="text-xs font-semibold uppercase text-slate-500 tracking-wider">Aislamiento Multi-Tenant</p>
          <p class="text-2xl font-bold text-purple-600 mt-2">Estricto</p>
          <p class="text-xs text-slate-500 mt-1">Cero acceso horizontal (IDOR)</p>
        </div>
      </div>

      <!-- Sección de Respaldos Cifrados -->
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="p-5 border-b border-slate-200 flex items-center justify-between">
          <div>
            <h2 class="text-lg font-bold text-slate-900">Respaldos Cifrados & Recuperación (Disaster Recovery)</h2>
            <p class="text-xs text-slate-500 mt-0.5">Archivos encriptados con AES y verificados mediante checksums criptográficos SHA-256.</p>
          </div>
          <span class="px-2.5 py-1 bg-blue-50 text-blue-700 text-xs font-medium rounded-full border border-blue-200">
            Retención: Máx 10 versiones
          </span>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-left border-collapse text-sm">
            <thead>
              <tr class="bg-slate-50 text-slate-600 text-xs font-semibold uppercase border-b border-slate-200">
                <th class="py-3 px-4">Identificador</th>
                <th class="py-3 px-4">Archivo Encriptado</th>
                <th class="py-3 px-4">Tamaño Cifrado</th>
                <th class="py-3 px-4">Checksum SHA-256</th>
                <th class="py-3 px-4">Fecha de Creación</th>
                <th class="py-3 px-4 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody id="backups-tbody" class="divide-y divide-slate-100">
              <tr><td colspan="6" class="py-8 text-center text-slate-400">Cargando catálogo de respaldos...</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Sección SIEM: Registro de Incidentes y Amenazas -->
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="p-5 border-b border-slate-200">
          <h2 class="text-lg font-bold text-slate-900">Registro de Incidentes y Postura de Amenazas (SIEM)</h2>
          <p class="text-xs text-slate-500 mt-0.5">Eventos de seguridad correlacionados, bloqueos de IP y detección de anomalías.</p>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-left border-collapse text-sm">
            <thead>
              <tr class="bg-slate-50 text-slate-600 text-xs font-semibold uppercase border-b border-slate-200">
                <th class="py-3 px-4">Fecha</th>
                <th class="py-3 px-4">Tipo de Amenaza</th>
                <th class="py-3 px-4">Severidad</th>
                <th class="py-3 px-4">IP Origen</th>
                <th class="py-3 px-4">Descripción del Bloqueo</th>
              </tr>
            </thead>
            <tbody id="security-events-tbody" class="divide-y divide-slate-100">
              <tr><td colspan="5" class="py-8 text-center text-slate-400">Cargando eventos de seguridad...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  async function loadData() {
    try {
      // 1. Cargar estado de seguridad
      const statusRes = await api.get('/system/security/status');
      renderEvents(statusRes.recent_incidents || []);

      // 2. Cargar respaldos
      const backupsRes = await api.get('/system/backups/list');
      renderBackups(backupsRes || []);
    } catch (err) {
      showToast('Error cargando información de seguridad: ' + err.message, 'error');
    }
  }

  function renderBackups(backups) {
    const tbody = document.getElementById('backups-tbody');
    if (!tbody) return;
    if (backups.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="py-8 text-center text-slate-400">No hay respaldos generados aún. Haz clic en "Generar Respaldo Cifrado".</td></tr>`;
      return;
    }
    tbody.innerHTML = backups.map(b => `
      <tr class="hover:bg-slate-50/80 transition-colors">
        <td class="py-3 px-4 font-mono text-xs text-slate-700 font-semibold">${escapeHtml(b.backup_id.slice(0, 8))}...</td>
        <td class="py-3 px-4 text-xs font-medium text-slate-900">${escapeHtml(b.filename)}</td>
        <td class="py-3 px-4 text-xs text-slate-600">${Math.round(b.encrypted_size_bytes / 1024)} KB</td>
        <td class="py-3 px-4 font-mono text-xs text-slate-500">${escapeHtml((b.encrypted_sha256 || '').slice(0, 16))}...</td>
        <td class="py-3 px-4 text-xs text-slate-500">${new Date(b.created_at).toLocaleString()}</td>
        <td class="py-3 px-4 text-right space-x-2">
          <button data-verify-id="${escapeHtml(b.backup_id)}" class="btn-verify px-2.5 py-1 text-xs font-medium text-blue-700 bg-blue-50 hover:bg-blue-100 rounded border border-blue-200">
            Verificar SHA-256
          </button>
          <button data-dr-id="${escapeHtml(b.backup_id)}" class="btn-dr px-2.5 py-1 text-xs font-medium text-purple-700 bg-purple-50 hover:bg-purple-100 rounded border border-purple-200">
            Simular Recuperación
          </button>
        </td>
      </tr>
    `).join('');

    // Event listeners
    tbody.querySelectorAll('.btn-verify').forEach(btn => {
      btn.addEventListener('click', async () => {
        const id = btn.getAttribute('data-verify-id');
        try {
          btn.textContent = 'Verificando...';
          const res = await api.post(`/system/backups/${id}/verify`);
          if (res.is_valid) {
            showToast(`Respaldo íntegro y verificado: Checksum SHA-256 válido (${res.tables_verified} tablas comprobadas)`, 'success');
          } else {
            showToast(`Fallo de verificación: ${res.error}`, 'error');
          }
        } catch (err) {
          showToast('Error al verificar respaldo: ' + err.message, 'error');
        } finally {
          btn.textContent = 'Verificar SHA-256';
        }
      });
    });

    tbody.querySelectorAll('.btn-dr').forEach(btn => {
      btn.addEventListener('click', async () => {
        const id = btn.getAttribute('data-dr-id');
        try {
          btn.textContent = 'Simulando...';
          const res = await api.post(`/system/backups/${id}/disaster-recovery-test`);
          if (res.dry_run_success) {
            showToast(`Ensayo de recuperación exitoso: ${res.message}`, 'success');
          }
        } catch (err) {
          showToast('Fallo en simulación de recuperación: ' + err.message, 'error');
        } finally {
          btn.textContent = 'Simular Recuperación';
        }
      });
    });
  }

  function renderEvents(events) {
    const tbody = document.getElementById('security-events-tbody');
    if (!tbody) return;
    if (events.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="py-8 text-center text-slate-400">Sin incidentes de seguridad registrados. El sistema se encuentra en estado óptimo.</td></tr>`;
      return;
    }
    tbody.innerHTML = events.map(e => {
      const sevColor = e.severity === 'CRITICAL' ? 'bg-red-100 text-red-800 border-red-200' :
                       e.severity === 'HIGH' ? 'bg-amber-100 text-amber-800 border-amber-200' :
                       'bg-blue-100 text-blue-800 border-blue-200';
      return `
        <tr class="hover:bg-slate-50/80 transition-colors">
          <td class="py-3 px-4 text-xs text-slate-500">${e.created_at ? new Date(e.created_at).toLocaleString() : '-'}</td>
          <td class="py-3 px-4 font-mono text-xs font-semibold text-slate-800">${escapeHtml(e.event_type)}</td>
          <td class="py-3 px-4">
            <span class="px-2 py-0.5 text-xs font-semibold rounded-full border ${sevColor}">
              ${escapeHtml(e.severity)}
            </span>
          </td>
          <td class="py-3 px-4 font-mono text-xs text-slate-600">${escapeHtml(e.ip_address || '127.0.0.1')}</td>
          <td class="py-3 px-4 text-xs text-slate-700">${escapeHtml(e.description)}</td>
        </tr>
      `;
    }).join('');
  }

  document.getElementById('btn-create-backup')?.addEventListener('click', async () => {
    try {
      showToast('Generando respaldo cifrado...', 'info');
      const res = await api.post('/system/backups/create');
      showToast(`Respaldo cifrado generado con éxito (${Math.round(res.encrypted_size_bytes / 1024)} KB)`, 'success');
      loadData();
    } catch (err) {
      showToast('Error al generar respaldo: ' + err.message, 'error');
    }
  });

  document.getElementById('btn-refresh-security')?.addEventListener('click', loadData);

  loadData();
}

/**
 * Vista de Perfil de Usuario y Gestión de Sesiones Activas
 * Conectado con /api/v1/auth/me, /api/v1/auth/sessions, /auth/sessions/{id} y /auth/logout-all.
 */

import { api } from '../api.js';
import { state } from '../state.js';
import { icons } from '../icons.js';
import { showToast } from '../components/toast.js';
import { showConfirmDialog } from '../components/modal.js';

let activeSessions = [];

export async function renderProfile(container) {
  const user = state.user || {};
  const currentCompany = state.currentCompany || {};

  container.innerHTML = `
    <div class="space-y-6 max-w-4xl mx-auto">
      <!-- Encabezado -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 class="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            ${icons.user("w-6 h-6")} Mi Perfil y Seguridad
          </h1>
          <p class="text-sm text-slate-500 mt-1">
            Información de cuenta, membresías empresariales y administración de sesiones concurrentes.
          </p>
        </div>
      </div>

      <!-- Tarjeta de Perfil -->
      <div class="card p-6 space-y-6">
        <div class="flex flex-col sm:flex-row items-start sm:items-center gap-4 border-b border-slate-100 pb-6">
          <div class="w-16 h-16 rounded-2xl bg-gradient-to-tr from-blue-600 to-indigo-600 text-white flex items-center justify-center font-bold text-2xl shadow-md">
            ${(user.full_name || user.email || 'U')[0].toUpperCase()}
          </div>
          <div>
            <h2 class="text-xl font-bold text-slate-900">${user.full_name || 'Usuario del ERP'}</h2>
            <div class="text-sm text-slate-500">${user.email || 'correo@ejemplo.com'}</div>
            <div class="flex items-center gap-2 mt-2">
              <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-blue-50 text-blue-700 border border-blue-200">
                Rol Global: ${user.role || 'viewer'}
              </span>
              <span class="text-xs text-slate-400">·</span>
              <span class="text-xs text-slate-600 font-medium">
                Empresa Activa: <strong class="text-slate-800">${currentCompany.name || 'Sin empresa'}</strong>
              </span>
            </div>
          </div>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
          <div>
            <span class="text-slate-400 font-medium">Identificador de Usuario (UUID):</span>
            <div class="font-mono text-slate-700 font-semibold mt-0.5">${user.id || '-'}</div>
          </div>
          <div>
            <span class="text-slate-400 font-medium">Teléfono / Celular:</span>
            <div class="text-slate-700 font-semibold mt-0.5">${user.phone || 'No registrado'}</div>
          </div>
        </div>
      </div>

      <!-- Gestión de Sesiones Activas -->
      <div class="card overflow-hidden">
        <div class="p-5 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
              ${icons.shield("w-4 h-4")} Sesiones Activas en Dispositivos
            </h2>
            <p class="text-xs text-slate-500 mt-0.5">
              Dispositivos y navegadores que tienen tokens de acceso vigentes a tu cuenta.
            </p>
          </div>
          <button id="btn-logout-all" class="btn-secondary text-xs text-rose-600 hover:text-rose-700 hover:bg-rose-50 border-rose-200 py-1.5 px-3">
            Cerrar Todas las Demás Sesiones
          </button>
        </div>

        <div class="overflow-x-auto">
          <table class="w-full text-left border-collapse">
            <thead>
              <tr class="bg-slate-50 border-b border-slate-200 text-xs font-semibold text-slate-600 uppercase tracking-wider">
                <th class="p-3">Dispositivo / Navegador</th>
                <th class="p-3">Dirección IP</th>
                <th class="p-3">Inicio de Sesión</th>
                <th class="p-3">Última Actividad</th>
                <th class="p-3 text-right">Acción</th>
              </tr>
            </thead>
            <tbody id="sessions-table-body" class="divide-y divide-slate-100 text-sm">
              <tr>
                <td colspan="5" class="p-6 text-center text-slate-400">Cargando sesiones activas...</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  container.querySelector('#btn-logout-all').addEventListener('click', handleLogoutAll);

  await loadSessions();
}

async function loadSessions() {
  try {
    const res = await api.get('/auth/sessions');
    activeSessions = res.sessions || [];
    renderSessionsTable();
  } catch (err) {
    showToast(err.message || 'Error cargando sesiones', 'error');
  }
}

function renderSessionsTable() {
  const tbody = document.getElementById('sessions-table-body');
  if (!tbody) return;

  if (activeSessions.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="5" class="p-6 text-center text-slate-400">
          No se encontraron otras sesiones concurrentes activas.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = activeSessions.map((s, idx) => {
    const isCurrent = idx === 0;
    return `
      <tr class="hover:bg-slate-50 transition-colors">
        <td class="p-3">
          <div class="font-medium text-slate-900 flex items-center gap-2">
            ${icons.products("w-4 h-4")} ${s.user_agent ? s.user_agent.slice(0, 40) + '...' : 'Navegador Web'}
            ${isCurrent ? '<span class="text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800">Esta Sesión</span>' : ''}
          </div>
          <div class="font-mono text-[11px] text-slate-400">ID: ${s.id.slice(0, 8)}...</div>
        </td>
        <td class="p-3 font-mono text-xs text-slate-600">${s.ip_address || '127.0.0.1'}</td>
        <td class="p-3 text-xs text-slate-500">${new Date(s.created_at).toLocaleString('es-MX')}</td>
        <td class="p-3 text-xs text-slate-500">${s.last_used_at ? new Date(s.last_used_at).toLocaleString('es-MX') : 'Reciente'}</td>
        <td class="p-3 text-right">
          ${
            !isCurrent
              ? `
            <button
              data-session-id="${s.id}"
              class="btn-revoke-session text-xs font-semibold text-rose-600 hover:text-rose-800"
            >
              Revocar
            </button>
          `
              : `
            <span class="text-xs text-slate-400">Sesión Actual</span>
          `
          }
        </td>
      </tr>
    `;
  }).join('');

  tbody.querySelectorAll('.btn-revoke-session').forEach((btn) => {
    btn.addEventListener('click', () => {
      const id = btn.dataset.sessionId;
      showConfirmDialog(
        '¿Revocar sesión remota?',
        'El usuario en ese dispositivo será desconectado inmediatamente.',
        async () => {
          try {
            await api.delete(`/auth/sessions/${id}`);
            showToast('Sesión revocada exitosamente', 'success');
            await loadSessions();
          } catch (err) {
            showToast(err.message || 'Error al revocar sesión', 'error');
          }
        }
      );
    });
  });
}

function handleLogoutAll() {
  showConfirmDialog(
    '¿Cerrar todas las demás sesiones?',
    'Se invalidarán todos los tokens en otros dispositivos o navegadores, manteniendo únicamente tu sesión actual.',
    async () => {
      try {
        await api.post('/auth/logout-all');
        showToast('Todas las demás sesiones han sido invalidadas', 'success');
        await loadSessions();
      } catch (err) {
        showToast(err.message || 'Error al cerrar sesiones', 'error');
      }
    }
  );
}


// Adaptador para el encabezado: el perfil es una vista completa del ERP,
// así que el botón "Perfil" navega a la ruta #profile.
export function openProfileModal() {
  state.setRoute("profile");
}

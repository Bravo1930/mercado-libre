/**
 * Vista de Configuración Empresarial, Roles RBAC y Bitácora de Auditoría
 * Conectado con /api/v1/companies/{id}, /companies/{id}/users y /api/v1/audit.
 */

import { api } from '../api.js';
import { state } from '../state.js';
import { icons } from '../icons.js';
import { showToast } from '../components/toast.js';
import { openModal, closeModal, showConfirmDialog } from '../components/modal.js';

let companyUsers = [];
let auditLogs = [];
let activeSettingsTab = 'company';

const ROLES_LIST = [
  { id: 'platform_owner', name: 'Propietario de Plataforma' },
  { id: 'saas_admin', name: 'Administrador SaaS' },
  { id: 'company_admin', name: 'Administrador de Empresa' },
  { id: 'director', name: 'Director' },
  { id: 'operator', name: 'Operador' },
  { id: 'warehouse_manager', name: 'Responsable de Almacén' },
  { id: 'financial_manager', name: 'Responsable Financiero' },
  { id: 'viewer', name: 'Usuario de Consulta' },
];

export async function renderSettings(container) {
  container.innerHTML = `
    <div class="space-y-6">
      <!-- Encabezado -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 class="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            ${icons.settings} Configuración y Administración
          </h1>
          <p class="text-sm text-slate-500 mt-1">
            Gestión fiscal de la empresa, control de accesos RBAC (8 roles) y bitácora de auditoría inmutable.
          </p>
        </div>
      </div>

      <!-- Pestañas de Navegación Interna -->
      <div class="flex border-b border-slate-200 gap-6">
        <button id="tab-btn-company" class="settings-tab-btn pb-3 text-sm font-bold border-b-2 border-blue-600 text-blue-600">
          Datos Fiscales de la Empresa
        </button>
        <button id="tab-btn-users" class="settings-tab-btn pb-3 text-sm font-semibold border-b-2 border-transparent text-slate-500 hover:text-slate-800">
          Usuarios y Permisos RBAC
        </button>
        <button id="tab-btn-audit" class="settings-tab-btn pb-3 text-sm font-semibold border-b-2 border-transparent text-slate-500 hover:text-slate-800">
          Bitácora de Auditoría
        </button>
      </div>

      <!-- Contenedor Dinámico de Pestañas -->
      <div id="settings-tab-content">
        <!-- Rendered based on active tab -->
      </div>
    </div>
  `;

  const btnCompany = container.querySelector('#tab-btn-company');
  const btnUsers = container.querySelector('#tab-btn-users');
  const btnAudit = container.querySelector('#tab-btn-audit');

  function setTab(tab) {
    activeSettingsTab = tab;
    [btnCompany, btnUsers, btnAudit].forEach((b) => {
      b.className = 'settings-tab-btn pb-3 text-sm font-semibold border-b-2 border-transparent text-slate-500 hover:text-slate-800';
    });

    if (tab === 'company') {
      btnCompany.className = 'settings-tab-btn pb-3 text-sm font-bold border-b-2 border-blue-600 text-blue-600';
      renderCompanyTab();
    } else if (tab === 'users') {
      btnUsers.className = 'settings-tab-btn pb-3 text-sm font-bold border-b-2 border-blue-600 text-blue-600';
      renderUsersTab();
    } else if (tab === 'audit') {
      btnAudit.className = 'settings-tab-btn pb-3 text-sm font-bold border-b-2 border-blue-600 text-blue-600';
      renderAuditTab();
    }
  }

  btnCompany.addEventListener('click', () => setTab('company'));
  btnUsers.addEventListener('click', () => setTab('users'));
  btnAudit.addEventListener('click', () => setTab('audit'));

  setTab('company');
}

function renderCompanyTab() {
  const container = document.getElementById('settings-tab-content');
  if (!container) return;

  const currentCompany = state.currentCompany || {};

  container.innerHTML = `
    <div class="card p-6 max-w-3xl space-y-6">
      <div class="border-b border-slate-100 pb-4">
        <h2 class="text-base font-bold text-slate-900">Razón Social y Datos Tributarios</h2>
        <p class="text-xs text-slate-500 mt-1">
          Información registrada ante el Servicio de Administración Tributaria (SAT México).
        </p>
      </div>

      <form id="company-profile-form" class="space-y-4">
        <div>
          <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Nombre Comercial / Razón Social *</label>
          <input
            type="text"
            id="comp-name-input"
            class="input-field text-sm"
            value="${currentCompany.name || ''}"
            required
          />
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">RFC Mexicano *</label>
            <input
              type="text"
              id="comp-rfc-input"
              class="input-field text-sm font-mono uppercase font-bold"
              value="${currentCompany.rfc || ''}"
              maxlength="13"
              required
            />
          </div>
          <div>
            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">UUID Identificador</label>
            <input
              type="text"
              class="input-field text-xs font-mono bg-slate-50"
              value="${currentCompany.id || ''}"
              disabled
            />
          </div>
        </div>

        <div>
          <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Régimen Fiscal SAT</label>
          <select id="comp-regime-select" class="input-field text-sm">
            <option value="601">601 - General de Ley Personas Morales</option>
            <option value="612">612 - Personas Físicas con Actividades Empresariales</option>
            <option value="625" selected>625 - Régimen de Plataformas Tecnológicas (Mercado Libre)</option>
            <option value="626">626 - Régimen Simplificado de Confianza (RESICO)</option>
          </select>
        </div>

        <div class="pt-4 border-t border-slate-100 flex justify-end">
          <button type="submit" id="btn-save-company" class="btn-primary flex items-center gap-2">
            ${icons.check} Actualizar Datos de Empresa
          </button>
        </div>
      </form>
    </div>
  `;

  const form = container.querySelector('#company-profile-form');
  form?.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!currentCompany.id) return;

    const btn = document.getElementById('btn-save-company');
    btn.disabled = true;
    btn.innerHTML = 'Guardando...';

    const name = document.getElementById('comp-name-input').value.trim();
    const rfc = document.getElementById('comp-rfc-input').value.trim().toUpperCase();

    try {
      const updated = await api.put(`/companies/${currentCompany.id}`, { name, rfc });
      showToast('Datos de la empresa actualizados exitosamente', 'success');
      state.currentCompany = { ...state.currentCompany, ...updated };
    } catch (err) {
      showToast(err.message || 'Error al actualizar empresa', 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `${icons.check} Actualizar Datos de Empresa`;
      }
    }
  });
}

async function renderUsersTab() {
  const container = document.getElementById('settings-tab-content');
  if (!container) return;

  const currentCompany = state.currentCompany;
  if (!currentCompany) {
    container.innerHTML = '<div class="card p-6 text-slate-400">Selecciona una empresa primero.</div>';
    return;
  }

  container.innerHTML = `
    <div class="space-y-4">
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 class="text-base font-bold text-slate-900">Usuarios Asignados a ${currentCompany.name}</h2>
          <p class="text-xs text-slate-500">Matriz estricta de 8 roles RBAC con validación en backend.</p>
        </div>
        <button id="btn-assign-user" class="btn-primary flex items-center gap-1.5 text-xs">
          ${icons.plus} Asignar Nuevo Usuario
        </button>
      </div>

      <div class="card overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-left border-collapse">
            <thead>
              <tr class="bg-slate-50 border-b border-slate-200 text-xs font-semibold text-slate-600 uppercase tracking-wider">
                <th class="p-3">ID de Usuario</th>
                <th class="p-3">Rol RBAC</th>
                <th class="p-3">Estado</th>
                <th class="p-3">Fecha de Asignación</th>
                <th class="p-3 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody id="company-users-body" class="divide-y divide-slate-100 text-sm">
              <tr>
                <td colspan="5" class="p-6 text-center text-slate-400">Cargando usuarios...</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  container.querySelector('#btn-assign-user').addEventListener('click', openAssignUserModal);

  await loadCompanyUsers();
}

async function loadCompanyUsers() {
  const currentCompany = state.currentCompany;
  if (!currentCompany) return;

  try {
    const res = await api.get(`/companies/${currentCompany.id}/users?limit=50`);
    companyUsers = res.items || [];
    renderCompanyUsersTable();
  } catch (err) {
    showToast(err.message || 'Error cargando usuarios de la empresa', 'error');
  }
}

function renderCompanyUsersTable() {
  const tbody = document.getElementById('company-users-body');
  if (!tbody) return;

  if (companyUsers.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="5" class="p-6 text-center text-slate-400">
          No hay usuarios asignados a esta empresa.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = companyUsers.map((cu) => {
    const roleObj = ROLES_LIST.find((r) => r.id === cu.role) || { name: cu.role };
    return `
      <tr class="hover:bg-slate-50 transition-colors">
        <td class="p-3 font-mono text-xs font-bold text-slate-900">${cu.user_id}</td>
        <td class="p-3">
          <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-blue-50 text-blue-700 border border-blue-200">
            ${roleObj.name}
          </span>
        </td>
        <td class="p-3">
          <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${cu.is_active ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-600'}">
            ${cu.is_active ? 'Activo' : 'Inactivo'}
          </span>
        </td>
        <td class="p-3 text-xs text-slate-500">${new Date(cu.created_at).toLocaleDateString('es-MX')}</td>
        <td class="p-3 text-right">
          <button
            data-user-id="${cu.user_id}"
            data-current-role="${cu.role}"
            class="btn-edit-user-role text-xs text-blue-600 hover:text-blue-800 font-semibold mr-3"
          >
            Cambiar Rol
          </button>
          <button
            data-user-id="${cu.user_id}"
            class="btn-remove-company-user text-xs text-rose-600 hover:text-rose-800 font-semibold"
          >
            Remover
          </button>
        </td>
      </tr>
    `;
  }).join('');

  tbody.querySelectorAll('.btn-edit-user-role').forEach((btn) => {
    btn.addEventListener('click', () => {
      const userId = btn.dataset.userId;
      const curRole = btn.dataset.currentRole;
      openEditRoleModal(userId, curRole);
    });
  });

  tbody.querySelectorAll('.btn-remove-company-user').forEach((btn) => {
    btn.addEventListener('click', () => {
      const userId = btn.dataset.userId;
      showConfirmDialog(
        '¿Remover usuario de la empresa?',
        'El usuario perderá de inmediato todos los accesos a esta empresa y sus módulos.',
        async () => {
          try {
            await api.delete(`/companies/${state.currentCompany.id}/users/${userId}`);
            showToast('Usuario removido de la empresa', 'success');
            await loadCompanyUsers();
          } catch (err) {
            showToast(err.message || 'Error al remover usuario', 'error');
          }
        }
      );
    });
  });
}

function openAssignUserModal() {
  const currentCompany = state.currentCompany;
  if (!currentCompany) return;

  const roleOptions = ROLES_LIST.map((r) => `<option value="${r.id}">${r.name}</option>`).join('');

  const content = `
    <form id="assign-user-form" class="space-y-4">
      <div>
        <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">UUID del Usuario a Asignar *</label>
        <input
          type="text"
          id="assign-user-id-input"
          class="input-field text-xs font-mono"
          placeholder="00000000-0000-0000-0000-000000000000"
          required
        />
      </div>

      <div>
        <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Rol RBAC para esta Empresa *</label>
        <select id="assign-role-select" class="input-field text-sm" required>
          ${roleOptions}
        </select>
      </div>

      <div class="flex justify-end gap-2 pt-2">
        <button type="button" id="btn-cancel-assign" class="btn-secondary">Cancelar</button>
        <button type="submit" id="btn-submit-assign" class="btn-primary flex items-center gap-1.5">
          ${icons.check} Asignar a Empresa
        </button>
      </div>
    </form>
  `;

  openModal('Asignar Usuario a la Empresa', content);

  document.getElementById('btn-cancel-assign')?.addEventListener('click', closeModal);

  const form = document.getElementById('assign-user-form');
  form?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('btn-submit-assign');
    btn.disabled = true;
    btn.innerHTML = 'Asignando...';

    const userId = document.getElementById('assign-user-id-input').value.trim();
    const role = document.getElementById('assign-role-select').value;

    try {
      await api.post(`/companies/${currentCompany.id}/users`, {
        user_id: userId,
        role: role,
      });
      closeModal();
      showToast('Usuario asignado exitosamente con rol RBAC', 'success');
      await loadCompanyUsers();
    } catch (err) {
      showToast(err.message || 'Error al asignar usuario', 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `${icons.check} Asignar a Empresa`;
      }
    }
  });
}

function openEditRoleModal(userId, currentRole) {
  const currentCompany = state.currentCompany;
  if (!currentCompany) return;

  const roleOptions = ROLES_LIST.map((r) => {
    const isSelected = r.id === currentRole ? 'selected' : '';
    return `<option value="${r.id}" ${isSelected}>${r.name}</option>`;
  }).join('');

  const content = `
    <form id="edit-role-form" class="space-y-4">
      <div class="text-xs text-slate-500">
        Usuario: <span class="font-mono font-bold text-slate-800">${userId}</span>
      </div>

      <div>
        <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Nuevo Rol RBAC *</label>
        <select id="edit-role-select" class="input-field text-sm" required>
          ${roleOptions}
        </select>
      </div>

      <div class="flex justify-end gap-2 pt-2">
        <button type="button" id="btn-cancel-edit-role" class="btn-secondary">Cancelar</button>
        <button type="submit" id="btn-submit-edit-role" class="btn-primary flex items-center gap-1.5">
          ${icons.check} Guardar Cambio de Rol
        </button>
      </div>
    </form>
  `;

  openModal('Modificar Rol de Usuario', content);

  document.getElementById('btn-cancel-edit-role')?.addEventListener('click', closeModal);

  const form = document.getElementById('edit-role-form');
  form?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const newRole = document.getElementById('edit-role-select').value;

    try {
      await api.put(`/companies/${currentCompany.id}/users/${userId}`, {
        role: newRole,
      });
      closeModal();
      showToast('Rol de usuario actualizado exitosamente', 'success');
      await loadCompanyUsers();
    } catch (err) {
      showToast(err.message || 'Error actualizando rol', 'error');
    }
  });
}

async function renderAuditTab() {
  const container = document.getElementById('settings-tab-content');
  if (!container) return;

  container.innerHTML = `
    <div class="card overflow-hidden">
      <div class="p-4 border-b border-slate-200 flex items-center justify-between">
        <div>
          <h2 class="text-base font-bold text-slate-900">Bitácora Inmutable de Auditoría</h2>
          <p class="text-xs text-slate-500">Registro auditable de modificaciones, creaciones y accesos.</p>
        </div>
        <button id="btn-refresh-audit" class="btn-secondary text-xs flex items-center gap-1.5 py-1.5 px-3">
          ${icons.refresh} Refrescar Eventos
        </button>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-left border-collapse">
          <thead>
            <tr class="bg-slate-50 border-b border-slate-200 text-xs font-semibold text-slate-600 uppercase tracking-wider">
              <th class="p-3">Acción</th>
              <th class="p-3">Entidad</th>
              <th class="p-3">Usuario ID</th>
              <th class="p-3">Cambios (JSON)</th>
              <th class="p-3 text-right">Fecha / Hora</th>
            </tr>
          </thead>
          <tbody id="audit-table-body" class="divide-y divide-slate-100 text-sm font-mono">
            <tr>
              <td colspan="5" class="p-6 text-center text-slate-400 font-sans">Cargando registros de auditoría...</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  `;

  container.querySelector('#btn-refresh-audit').addEventListener('click', loadAuditLogs);

  await loadAuditLogs();
}

async function loadAuditLogs() {
  try {
    const res = await api.get('/audit?limit=50');
    auditLogs = res.items || [];
    renderAuditTable();
  } catch (err) {
    showToast(err.message || 'Error cargando bitácora de auditoría', 'error');
  }
}

function renderAuditTable() {
  const tbody = document.getElementById('audit-table-body');
  if (!tbody) return;

  if (auditLogs.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="5" class="p-6 text-center text-slate-400 font-sans">
          No hay eventos de auditoría registrados para esta empresa.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = auditLogs.map((log) => {
    const changesStr = log.changes ? JSON.stringify(log.changes) : '-';
    return `
      <tr class="hover:bg-slate-50 transition-colors">
        <td class="p-3 font-bold text-slate-800">${log.action}</td>
        <td class="p-3 text-xs text-blue-700">${log.entity_name} (${log.entity_id ? log.entity_id.slice(0, 8) + '...' : '-'})</td>
        <td class="p-3 text-xs text-slate-500">${log.user_id ? log.user_id.slice(0, 8) + '...' : 'SISTEMA'}</td>
        <td class="p-3 text-xs text-slate-600 truncate max-w-xs" title="${changesStr}">${changesStr}</td>
        <td class="p-3 text-right text-xs text-slate-400 font-sans">${new Date(log.created_at).toLocaleString('es-MX')}</td>
      </tr>
    `;
  }).join('');
}

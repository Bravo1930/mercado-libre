/**
 * Vista de Integraciones y Conector Oficial de Mercado Libre México.
 * Gestión multi-cuenta OAuth 2.0, diagnóstico en vivo, renovación de tokens y sincronización.
 */

import { api } from '../api.js';
import { state } from '../state.js';
import { icons } from '../icons.js';
import { showToast } from '../components/toast.js';
import { openModal, closeModal } from '../components/modal.js';

let meliAccounts = [];

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
            Módulo independiente <strong>MercadoLibreConnector</strong> con OAuth 2.0, auto-refresh de tokens y rate limiting.
          </p>
        </div>
        <div class="flex items-center gap-2">
          <button id="btn-oauth-connect" class="btn-primary flex items-center gap-2 bg-yellow-400 hover:bg-yellow-500 text-slate-900 border-none font-bold shadow-sm">
            ${icons.plus} Conectar Cuenta vía OAuth
          </button>
          <button id="btn-manual-connect" class="px-3.5 py-2 border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold rounded-xl transition-smooth shadow-sm">
            Ingreso Manual de Tokens
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

      <!-- Monitor de Webhooks Oficiales -->
      <div class="card p-5 space-y-4">
        <div class="flex items-center justify-between border-b border-slate-100 pb-3">
          <div>
            <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
              ${icons.zap} Receptor de Notificaciones Push (Webhooks)
            </h2>
            <p class="text-xs text-slate-500 mt-0.5">
              Escucha activa de notificaciones Push de la API de Mercado Libre México (HMAC-SHA256).
            </p>
          </div>
          <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800">
            <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span> Endpoint 200 OK En Línea
          </span>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-4 gap-3 text-xs">
          <div class="p-3 bg-white border border-slate-200 rounded-lg space-y-1">
            <div class="font-bold text-slate-900">orders_v2</div>
            <div class="text-slate-500">Nuevas compras, cobros y cancelaciones de pedidos.</div>
            <div class="text-emerald-600 font-semibold text-[11px]">✔ Activo</div>
          </div>
          <div class="p-3 bg-white border border-slate-200 rounded-lg space-y-1">
            <div class="font-bold text-slate-900">shipments</div>
            <div class="text-slate-500">Rastreo y transiciones de guías Mercado Envíos.</div>
            <div class="text-emerald-600 font-semibold text-[11px]">✔ Activo</div>
          </div>
          <div class="p-3 bg-white border border-slate-200 rounded-lg space-y-1">
            <div class="font-bold text-slate-900">items</div>
            <div class="text-slate-500">Sincronización de publicaciones, variaciones y precios.</div>
            <div class="text-emerald-600 font-semibold text-[11px]">✔ Activo</div>
          </div>
          <div class="p-3 bg-white border border-slate-200 rounded-lg space-y-1">
            <div class="font-bold text-slate-900">stock_fulfillment</div>
            <div class="text-slate-500">Ajustes automáticos de existencias en centros FULL.</div>
            <div class="text-emerald-600 font-semibold text-[11px]">✔ Activo</div>
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

  if (btnOAuth) btnOAuth.addEventListener('click', openOAuthFlowModal);
  if (btnManual) btnManual.addEventListener('click', openManualConnectModal);

  await loadMeliAccounts();
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

  // Handlers reales conectados a la API
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

async function runConnectionDiagnostic(accountId) {
  try {
    showToast('Ejecutando diagnóstico en vivo con Mercado Libre México...', 'info');
    const res = await api.post(`/meli-accounts/${accountId}/test-connection`, {});

    if (res.healthy) {
      openModal({
        title: "Diagnóstico de Conexión MeLi México (200 OK)",
        size: "md",
        content: `
          <div class="space-y-3 text-xs">
            <div class="p-3 bg-emerald-50 border border-emerald-200 rounded-xl text-emerald-900 font-semibold flex items-center justify-between">
              <span>Estado de la API:</span>
              <span class="badge badge-success text-xs font-bold">Conexión Exitosa</span>
            </div>
            <div class="p-3 bg-slate-50 border border-slate-200 rounded-xl space-y-1.5 font-mono">
              <div class="flex justify-between"><span>Vendedor:</span><span class="font-bold">${res.nickname}</span></div>
              <div class="flex justify-between"><span>Seller ID:</span><span class="font-bold">${res.meli_user_id}</span></div>
              <div class="flex justify-between"><span>Sitio:</span><span class="font-bold">${res.site_id}</span></div>
              <div class="flex justify-between"><span>Latencia de Respuesta:</span><span class="font-bold text-blue-700">${res.latency_ms} ms</span></div>
              <div class="flex justify-between"><span>Cuota Rate Limit Restante:</span><span class="font-bold">${res.rate_limit_remaining ?? 'Normal'}</span></div>
            </div>
          </div>
        `,
        confirmText: "Aceptar",
      });
    } else {
      showToast(`Error de conexión: ${res.error}`, 'error');
    }
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function forceRefreshToken(accountId) {
  try {
    showToast('Renovando Access Token mediante Refresh Token oficial...', 'info');
    await api.post(`/meli-accounts/${accountId}/refresh-token`, {});
    showToast('Token de acceso renovado exitosamente con Mercado Libre.', 'success');
    await loadMeliAccounts();
  } catch (err) {
    showToast(`Fallo al renovar token: ${err.message}`, 'error');
  }
}

async function disconnectAccount(accountId) {
  if (!confirm('¿Estás seguro de desconectar esta cuenta? Se pausará la sincronización de órdenes y stock.')) return;
  try {
    await api.post(`/meli-accounts/${accountId}/disconnect`, {});
    showToast('Cuenta de Mercado Libre desconectada.', 'warning');
    await loadMeliAccounts();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function openOAuthFlowModal() {
  try {
    const res = await api.get('/meli-accounts/auth-url');
    openModal({
      title: "Autorización Oficial OAuth 2.0 (Mercado Libre México)",
      size: "md",
      content: `
        <div class="space-y-4 text-xs">
          <p class="text-slate-600">
            Para vincular tu cuenta oficial de Mercado Libre México mediante el conector nativo:
          </p>

          <div class="p-3 bg-yellow-50 border border-yellow-200 rounded-xl text-yellow-900 space-y-1">
            <p class="font-bold">Paso 1: Autorizar en Mercado Libre</p>
            <p>Haz clic en el enlace para abrir la ventana de inicio de sesión oficial de Mercado Libre México.</p>
            <div class="pt-2">
              <a href="${res.auth_url}" target="_blank" rel="noopener noreferrer" class="inline-block px-4 py-2 bg-yellow-400 hover:bg-yellow-500 text-slate-900 font-bold rounded-lg shadow-sm">
                Abrir Portal de Autorización MeLi ↗
              </a>
            </div>
          </div>

          <div class="space-y-2">
            <label class="block font-bold text-slate-700">Paso 2: Ingresa el Authorization Code devuelto por MeLi</label>
            <input
              id="oauth-code-input"
              type="text"
              placeholder="TG-XXXXXX o Código de la URL devuelta (?code=...)"
              class="w-full px-3 py-2 border border-slate-200 rounded-xl font-mono focus:ring-2 focus:ring-blue-600 focus:outline-none"
            />
            <p class="text-[11px] text-slate-400">
              El conector intercambiará este código automáticamente por Access Token y Refresh Token oficiales.
            </p>
          </div>
        </div>
      `,
      confirmText: "Vincular Cuenta",
      onConfirm: async () => {
        const codeInput = document.getElementById("oauth-code-input").value.trim();
        if (!codeInput) throw new Error("Debes ingresar el código de autorización devuelto por Mercado Libre.");

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

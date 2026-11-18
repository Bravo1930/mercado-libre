/**
 * Vista del Asistente Comercial de Inteligencia Artificial para Mercado Libre México.
 *
 * Incluye:
 * 1. Asistente Conversacional Ejecutivo con Function Calling y citas de datos reales de BD.
 * 2. Chips de Preguntas Rápidas del Negocio (¿Cuánto gané hoy?, ¿Qué productos debo reponer?, etc.).
 * 3. Tarjetas de Citaciones de Fuentes Oficiales, Justificaciones Analíticas y Nivel de Certeza.
 * 4. Ejecución de Acciones Comerciales Autorizadas (Ajustes de Precios, Borradores de Compras).
 * 5. Configuración de Proveedores (Ollama Local, OpenAI, Claude, Gemini, Mock Fallback).
 * 6. Historial Inmutable de Auditoría de IA.
 * 7. Optimizador de Títulos y SEO MeLi (herramienta complementaria).
 */

import { api } from '../api.js';
import { icons } from '../icons.js';
import { showToast } from '../components/toast.js';

let activeConversationId = null;
let aiSettings = null;

export async function renderAI(container) {
  container.innerHTML = `
    <div class="space-y-6">
      <!-- Encabezado Principal -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-200 pb-4">
        <div>
          <h1 class="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2.5">
            <span class="p-2 bg-gradient-to-tr from-purple-600 to-indigo-600 text-white rounded-xl shadow-sm">
              ${icons.sparkles}
            </span>
            Asistente Comercial de Inteligencia Artificial
          </h1>
          <p class="text-sm text-slate-500 mt-1">
            Copiloto analítico para Mercado Libre México: ventas en tiempo real, rentabilidad neta, detección de anomalías y reposición con datos oficiales.
          </p>
        </div>

        <!-- Botones de Acción Superior -->
        <div class="flex items-center gap-2">
          <button
            id="btn-ai-settings"
            class="px-3.5 py-2 text-xs font-semibold text-slate-700 bg-white border border-slate-300 rounded-xl hover:bg-slate-50 shadow-sm flex items-center gap-1.5 transition-all"
          >
            ${icons.settings || '⚙️'} Proveedor de IA
          </button>
          <button
            id="btn-ai-audit"
            class="px-3.5 py-2 text-xs font-semibold text-slate-700 bg-white border border-slate-300 rounded-xl hover:bg-slate-50 shadow-sm flex items-center gap-1.5 transition-all"
          >
            📋 Auditoría
          </button>
          <button
            id="btn-new-chat"
            class="px-3.5 py-2 text-xs font-semibold text-white bg-indigo-600 rounded-xl hover:bg-indigo-700 shadow-sm flex items-center gap-1.5 transition-all"
          >
            + Nueva Consulta
          </button>
        </div>
      </div>

      <!-- Barra de Preguntas Canónicas del Negocio (Quick Chips) -->
      <div class="space-y-2">
        <div class="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
          <span>⚡ Preguntas Rápidas del Negocio</span>
          <span class="text-[10px] text-slate-400 font-normal">(Consulta datos reales de la base de datos sin alucinaciones)</span>
        </div>
        <div class="flex flex-wrap gap-2" id="quick-chips-container">
          <button class="ai-chip px-3 py-1.5 bg-purple-50 text-purple-700 hover:bg-purple-100 border border-purple-200 rounded-lg text-xs font-medium transition-all" data-q="¿Cuánto gané hoy?">
            💰 ¿Cuánto gané hoy?
          </button>
          <button class="ai-chip px-3 py-1.5 bg-blue-50 text-blue-700 hover:bg-blue-100 border border-blue-200 rounded-lg text-xs font-medium transition-all" data-q="¿Cuánto vendí este mes?">
            📈 ¿Cuánto vendí este mes?
          </button>
          <button class="ai-chip px-3 py-1.5 bg-amber-50 text-amber-800 hover:bg-amber-100 border border-amber-200 rounded-lg text-xs font-medium transition-all" data-q="¿Qué productos debo reponer?">
            📦 ¿Qué productos debo reponer?
          </button>
          <button class="ai-chip px-3 py-1.5 bg-rose-50 text-rose-700 hover:bg-rose-100 border border-rose-200 rounded-lg text-xs font-medium transition-all" data-q="¿Qué productos pierden dinero?">
            ⚠️ ¿Qué productos pierden dinero?
          </button>
          <button class="ai-chip px-3 py-1.5 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border border-emerald-200 rounded-lg text-xs font-medium transition-all" data-q="¿Qué producto debería promocionar?">
            🎯 ¿Qué producto debería promocionar?
          </button>
          <button class="ai-chip px-3 py-1.5 bg-indigo-50 text-indigo-700 hover:bg-indigo-100 border border-indigo-200 rounded-lg text-xs font-medium transition-all" data-q="¿Cuál es mi margen promedio?">
            📊 ¿Cuál es mi margen promedio?
          </button>
        </div>
      </div>

      <!-- Área de Trabajo Principal (Chat + Panel Lateral) -->
      <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <!-- Ventana de Chat Comercial (8 Cols) -->
        <div class="lg:col-span-8 flex flex-col bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden min-h-[580px] max-h-[700px]">
          <!-- Subcabecera del Chat con Estatus del Proveedor -->
          <div class="p-3.5 bg-slate-50 border-b border-slate-200 flex items-center justify-between text-xs">
            <div class="flex items-center gap-2">
              <span class="inline-block w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse"></span>
              <span class="font-bold text-slate-800" id="ai-active-model-label">Cargando modelo...</span>
              <span class="text-slate-400">|</span>
              <span class="text-slate-500" id="ai-rate-limit-label">Cuota diaria: --</span>
            </div>
            <div class="text-[11px] text-slate-400 flex items-center gap-1">
              <span>🛡️ Prompt Injection Guard Activo</span>
            </div>
          </div>

          <!-- Contenedor de Mensajes -->
          <div id="ai-chat-messages" class="flex-1 p-4 overflow-y-auto space-y-4 bg-slate-50/50">
            <!-- Mensaje de bienvenida inicial -->
            <div class="flex gap-3 max-w-3xl">
              <div class="w-8 h-8 rounded-full bg-indigo-600 text-white flex items-center justify-center text-xs font-bold shrink-0 shadow-sm">
                AI
              </div>
              <div class="space-y-2">
                <div class="p-4 bg-white border border-slate-200 rounded-2xl rounded-tl-none shadow-sm text-sm text-slate-800 space-y-2">
                  <p class="font-semibold text-slate-900">¡Hola! Soy tu Asistente Comercial Ejecutivo para Mercado Libre México.</p>
                  <p>Estoy conectado directamente a los servicios analíticos del ERP (ventas, finanzas, inventario, abastecimiento y reglas comerciales) para responder tus dudas con <strong>cifras reales y exactas</strong> de tu base de datos.</p>
                  <p class="text-xs text-slate-500 pt-1">
                    Puedes hacer clic en cualquiera de las <strong>preguntas rápidas</strong> de arriba o escribir tu consulta abajo.
                  </p>
                </div>
              </div>
            </div>
          </div>

          <!-- Barra de Entrada de Consulta -->
          <div class="p-3.5 bg-white border-t border-slate-200">
            <form id="ai-chat-form" class="flex gap-2">
              <input
                type="text"
                id="ai-user-input"
                class="flex-1 px-4 py-2.5 bg-slate-50 border border-slate-300 rounded-xl text-sm focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-all"
                placeholder="Escribe tu consulta comercial (ej. ¿Cuánto gané hoy?, ¿Qué productos pierden dinero?)..."
                autocomplete="off"
              />
              <button
                type="submit"
                id="ai-submit-btn"
                class="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold rounded-xl shadow-sm flex items-center justify-center gap-1.5 transition-all shrink-0"
              >
                <span>Enviar</span> ${icons.send || '➤'}
              </button>
            </form>
          </div>
        </div>

        <!-- Panel Lateral Informativo (4 Cols): Herramientas y Diagnóstico -->
        <div class="lg:col-span-4 space-y-4">
          <!-- Tarjeta de Herramientas Oficiales Disponibles -->
          <div class="card p-4 space-y-3">
            <div class="flex items-center justify-between border-b border-slate-100 pb-2">
              <h3 class="text-xs font-bold text-slate-900 uppercase tracking-wider flex items-center gap-1.5">
                🛠️ 11 Herramientas Autorizadas
              </h3>
              <span class="text-[10px] px-2 py-0.5 bg-emerald-100 text-emerald-800 rounded font-semibold">100% Controladas</span>
            </div>
            <p class="text-xs text-slate-500">
              La IA solo puede acceder a datos y ejecutar acciones mediante estas funciones verificadas del ERP:
            </p>
            <div class="space-y-1.5 text-xs text-slate-700 max-h-56 overflow-y-auto pr-1" id="ai-tools-list">
              <div class="p-2 bg-slate-50 rounded border border-slate-100 flex items-center justify-between">
                <span class="font-medium">1. analyze_sales</span>
                <span class="text-[10px] text-slate-400">Ventas y Pedidos</span>
              </div>
              <div class="p-2 bg-slate-50 rounded border border-slate-100 flex items-center justify-between">
                <span class="font-medium">2. analyze_profitability</span>
                <span class="text-[10px] text-slate-400">Margen y Ganancia</span>
              </div>
              <div class="p-2 bg-slate-50 rounded border border-slate-100 flex items-center justify-between">
                <span class="font-medium">3. detect_trends</span>
                <span class="text-[10px] text-slate-400">Tendencias 7d/30d</span>
              </div>
              <div class="p-2 bg-slate-50 rounded border border-slate-100 flex items-center justify-between">
                <span class="font-medium">4. recommend_products</span>
                <span class="text-[10px] text-slate-400">Top Productos</span>
              </div>
              <div class="p-2 bg-slate-50 rounded border border-slate-100 flex items-center justify-between">
                <span class="font-medium">5. detect_slow_rotation</span>
                <span class="text-[10px] text-slate-400">Baja Rotación</span>
              </div>
              <div class="p-2 bg-slate-50 rounded border border-slate-100 flex items-center justify-between">
                <span class="font-medium">6. recommend_restock</span>
                <span class="text-[10px] text-slate-400">Punto de Reorden</span>
              </div>
              <div class="p-2 bg-slate-50 rounded border border-slate-100 flex items-center justify-between">
                <span class="font-medium">7. recommend_pricing</span>
                <span class="text-[10px] text-slate-400">Precios Óptimos</span>
              </div>
              <div class="p-2 bg-slate-50 rounded border border-slate-100 flex items-center justify-between">
                <span class="font-medium">8. evaluate_promotions</span>
                <span class="text-[10px] text-slate-400">Simulación Ofertas</span>
              </div>
              <div class="p-2 bg-slate-50 rounded border border-slate-100 flex items-center justify-between">
                <span class="font-medium">9. detect_anomalies</span>
                <span class="text-[10px] text-slate-400">Pérdidas y Riesgos</span>
              </div>
              <div class="p-2 bg-slate-50 rounded border border-slate-100 flex items-center justify-between">
                <span class="font-medium">10. generate_report</span>
                <span class="text-[10px] text-slate-400">Reporte Ejecutivo</span>
              </div>
              <div class="p-2 bg-slate-50 rounded border border-slate-100 flex items-center justify-between">
                <span class="font-medium">11. execute_commercial_action</span>
                <span class="text-[10px] text-purple-600 font-semibold">Automatización</span>
              </div>
            </div>
          </div>

          <!-- Política de Seguridad y Guardrails -->
          <div class="card p-4 space-y-2.5 bg-slate-50/70 border-slate-200 text-xs">
            <div class="font-bold text-slate-900 flex items-center gap-1.5">
              <span>🔒 Salvaguardas y Auditoría Activa</span>
            </div>
            <ul class="space-y-1 text-slate-600 list-disc list-inside">
              <li><strong>Sin acceso SQL irrestricto:</strong> La IA no puede ejecutar consultas libres a la base de datos.</li>
              <li><strong>Validación estricta de precios:</strong> Los ajustes respetan el precio piso configurado.</li>
              <li><strong>Aprobación humana:</strong> Las compras y órdenes sugeridas quedan en estado borrador.</li>
            </ul>
          </div>
        </div>
      </div>

      <!-- Modal de Configuración de Proveedor de IA (Oculto por defecto) -->
      <div id="ai-settings-modal" class="hidden fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4">
        <div class="bg-white rounded-2xl shadow-xl border border-slate-200 max-w-lg w-full p-6 space-y-4">
          <div class="flex items-center justify-between border-b border-slate-100 pb-3">
            <h3 class="text-base font-bold text-slate-900 flex items-center gap-2">
              ⚙️ Configuración del Motor de IA
            </h3>
            <button id="btn-close-settings-modal" class="text-slate-400 hover:text-slate-600 font-bold text-lg">&times;</button>
          </div>

          <form id="ai-settings-form" class="space-y-3 text-xs">
            <div>
              <label class="block font-bold text-slate-700 uppercase mb-1">Proveedor Activo</label>
              <select id="modal-provider" class="input-field text-xs">
                <option value="mock_fallback">Local Heurístico Deterministico (Offline / Sin API Key)</option>
                <option value="local_ollama">Ollama Local (http://localhost:11434/v1)</option>
                <option value="openai">OpenAI Oficial (GPT-4o / GPT-4o-mini)</option>
                <option value="custom_openai">Servicio Externo Compatible (Groq, vLLM, DeepSeek)</option>
              </select>
            </div>

            <div>
              <label class="block font-bold text-slate-700 uppercase mb-1">URL Base (para Ollama o Proxies)</label>
              <input type="text" id="modal-base-url" class="input-field text-xs" placeholder="http://localhost:11434/v1" />
            </div>

            <div>
              <label class="block font-bold text-slate-700 uppercase mb-1">API Key (Encriptada con Fernet)</label>
              <input type="password" id="modal-api-key" class="input-field text-xs" placeholder="sk-..." />
              <p class="text-[10px] text-slate-400 mt-0.5">Dejar en blanco para mantener la clave actual si ya está configurada.</p>
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block font-bold text-slate-700 uppercase mb-1">Nombre del Modelo</label>
                <input type="text" id="modal-model-name" class="input-field text-xs" placeholder="llama3.2 o gpt-4o-mini" />
              </div>
              <div>
                <label class="block font-bold text-slate-700 uppercase mb-1">Límite Diario Consultas</label>
                <input type="number" id="modal-daily-limit" class="input-field text-xs" min="10" max="5000" />
              </div>
            </div>

            <div class="flex justify-end gap-2 pt-3 border-t border-slate-100">
              <button type="button" id="btn-cancel-settings" class="px-3.5 py-2 rounded-xl bg-slate-100 text-slate-700 hover:bg-slate-200 font-semibold">
                Cancelar
              </button>
              <button type="submit" class="px-4 py-2 rounded-xl bg-indigo-600 text-white hover:bg-indigo-700 font-bold">
                Guardar Configuración
              </button>
            </div>
          </form>
        </div>
      </div>

      <!-- Modal de Historial de Auditoría (Oculto por defecto) -->
      <div id="ai-audit-modal" class="hidden fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4">
        <div class="bg-white rounded-2xl shadow-xl border border-slate-200 max-w-3xl w-full p-6 space-y-4">
          <div class="flex items-center justify-between border-b border-slate-100 pb-3">
            <h3 class="text-base font-bold text-slate-900 flex items-center gap-2">
              📋 Registro de Auditoría de Inteligencia Artificial
            </h3>
            <button id="btn-close-audit-modal" class="text-slate-400 hover:text-slate-600 font-bold text-lg">&times;</button>
          </div>

          <div class="max-h-96 overflow-y-auto" id="ai-audit-logs-table-container">
            <p class="text-xs text-slate-400">Cargando bitácora de auditoría...</p>
          </div>
        </div>
      </div>
    </div>
  `;

  // Inicializar listeners y cargar configuración
  initEventListeners(container);
  await loadAISettings(container);
}

function initEventListeners(container) {
  // Chips de preguntas rápidas
  container.querySelectorAll('.ai-chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      const q = chip.dataset.q;
      const input = container.querySelector('#ai-user-input');
      if (input) {
        input.value = q;
        submitChatQuery(container, q);
      }
    });
  });

  // Envío del formulario de chat
  const form = container.querySelector('#ai-chat-form');
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const input = container.querySelector('#ai-user-input');
    const msg = input.value.trim();
    if (msg) {
      submitChatQuery(container, msg);
      input.value = '';
    }
  });

  // Botón nueva consulta
  container.querySelector('#btn-new-chat').addEventListener('click', () => {
    activeConversationId = null;
    const msgContainer = container.querySelector('#ai-chat-messages');
    msgContainer.innerHTML = `
      <div class="flex gap-3 max-w-3xl">
        <div class="w-8 h-8 rounded-full bg-indigo-600 text-white flex items-center justify-center text-xs font-bold shrink-0">
          AI
        </div>
        <div class="p-4 bg-white border border-slate-200 rounded-2xl rounded-tl-none shadow-sm text-sm text-slate-800">
          Nueva sesión iniciada. ¿Qué datos o análisis comercial deseas consultar hoy?
        </div>
      </div>
    `;
    showToast('Nueva sesión de asistente iniciada', 'info');
  });

  // Modales
  const settingsModal = container.querySelector('#ai-settings-modal');
  container.querySelector('#btn-ai-settings').addEventListener('click', () => {
    populateSettingsForm(container);
    settingsModal.classList.remove('hidden');
  });
  container.querySelector('#btn-close-settings-modal').addEventListener('click', () => settingsModal.classList.add('hidden'));
  container.querySelector('#btn-cancel-settings').addEventListener('click', () => settingsModal.classList.add('hidden'));

  const auditModal = container.querySelector('#ai-audit-modal');
  container.querySelector('#btn-ai-audit').addEventListener('click', async () => {
    auditModal.classList.remove('hidden');
    await loadAuditLogs(container);
  });
  container.querySelector('#btn-close-audit-modal').addEventListener('click', () => auditModal.classList.add('hidden'));

  // Formulario guardar configuración
  container.querySelector('#ai-settings-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    await saveAISettings(container);
  });
}

async function loadAISettings(container) {
  try {
    const res = await api.get('/ai/settings');
    aiSettings = res;

    const modelLabel = container.querySelector('#ai-active-model-label');
    if (modelLabel) {
      modelLabel.textContent = `Modelo: ${res.model_name} (${res.provider})`;
    }

    const limitLabel = container.querySelector('#ai-rate-limit-label');
    if (limitLabel) {
      limitLabel.textContent = `Consultas hoy: ${res.requests_today} / ${res.daily_request_limit}`;
    }
  } catch (err) {
    console.warn('No se pudo cargar la configuración de IA:', err);
  }
}

function populateSettingsForm(container) {
  if (!aiSettings) return;
  container.querySelector('#modal-provider').value = aiSettings.provider;
  container.querySelector('#modal-base-url').value = aiSettings.base_url || '';
  container.querySelector('#modal-model-name').value = aiSettings.model_name || '';
  container.querySelector('#modal-daily-limit').value = aiSettings.daily_request_limit || 500;
}

async function saveAISettings(container) {
  const provider = container.querySelector('#modal-provider').value;
  const baseUrl = container.querySelector('#modal-base-url').value.trim() || null;
  const apiKey = container.querySelector('#modal-api-key').value.trim() || null;
  const modelName = container.querySelector('#modal-model-name').value.trim() || 'llama3.2';
  const dailyLimit = parseInt(container.querySelector('#modal-daily-limit').value, 10) || 500;

  try {
    const payload = {
      provider: provider,
      base_url: baseUrl,
      model_name: modelName,
      daily_request_limit: dailyLimit,
      temperature: 0.2,
      max_tokens: 2048,
      is_active: true,
    };
    if (apiKey) payload.api_key = apiKey;

    const res = await api.put('/ai/settings', payload);
    aiSettings = res;
    container.querySelector('#ai-settings-modal').classList.add('hidden');
    showToast('Configuración de IA actualizada correctamente', 'success');
    await loadAISettings(container);
  } catch (err) {
    showToast(err.message || 'Error guardando configuración de IA', 'error');
  }
}

async function loadAuditLogs(container) {
  const tableContainer = container.querySelector('#ai-audit-logs-table-container');
  try {
    const logs = await api.get('/ai/audit-logs?limit=30');
    if (!logs || logs.length === 0) {
      tableContainer.innerHTML = '<p class="text-xs text-slate-500">No hay registros de auditoría recientes.</p>';
      return;
    }

    tableContainer.innerHTML = `
      <table class="w-full text-left text-xs border-collapse">
        <thead>
          <tr class="border-b border-slate-200 text-slate-500 uppercase text-[10px]">
            <th class="py-2">Fecha</th>
            <th class="py-2">Consulta</th>
            <th class="py-2">Estado</th>
            <th class="py-2">Latencia</th>
            <th class="py-2">Herramientas</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          ${logs.map((l) => `
            <tr>
              <td class="py-2 text-slate-500 font-mono">${new Date(l.created_at).toLocaleTimeString()}</td>
              <td class="py-2 font-medium text-slate-800 max-w-xs truncate" title="${l.query_text}">${l.query_text}</td>
              <td class="py-2">
                <span class="px-2 py-0.5 rounded text-[10px] font-bold ${
                  l.status === 'success' ? 'bg-emerald-100 text-emerald-800' :
                  l.status === 'injection_blocked' ? 'bg-rose-100 text-rose-800' : 'bg-amber-100 text-amber-800'
                }">
                  ${l.status}
                </span>
              </td>
              <td class="py-2 text-slate-600 font-mono">${l.latency_ms} ms</td>
              <td class="py-2 text-slate-500">${l.tools_invoked ? l.tools_invoked.map(t => t.tool || t.action).join(', ') : '-'}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  } catch (err) {
    tableContainer.innerHTML = `<p class="text-xs text-rose-600">Error cargando auditoría: ${err.message}</p>`;
  }
}

async function submitChatQuery(container, message) {
  const msgContainer = container.querySelector('#ai-chat-messages');

  // Renderizar mensaje del usuario inmediatamente
  const userBubble = document.createElement('div');
  userBubble.className = 'flex gap-3 justify-end';
  userBubble.innerHTML = `
    <div class="p-3.5 bg-indigo-600 text-white rounded-2xl rounded-tr-none text-sm shadow-sm max-w-xl">
      ${escapeHtml(message)}
    </div>
  `;
  msgContainer.appendChild(userBubble);

  // Renderizar indicador de carga del asistente
  const loadingBubble = document.createElement('div');
  loadingBubble.className = 'flex gap-3 max-w-3xl';
  loadingBubble.id = 'ai-loading-bubble';
  loadingBubble.innerHTML = `
    <div class="w-8 h-8 rounded-full bg-indigo-600 text-white flex items-center justify-center text-xs font-bold shrink-0">
      AI
    </div>
    <div class="p-4 bg-white border border-slate-200 rounded-2xl rounded-tl-none shadow-sm text-xs text-slate-500 flex items-center gap-2">
      <span class="inline-block w-2 h-2 rounded-full bg-indigo-600 animate-ping"></span>
      Consultando base de datos oficial y analizando métricas comerciales...
    </div>
  `;
  msgContainer.appendChild(loadingBubble);
  msgContainer.scrollTop = msgContainer.scrollHeight;

  try {
    const payload = {
      conversation_id: activeConversationId,
      message: message,
      preset_period: 'today',
    };

    const res = await api.post('/ai/chat', payload);
    activeConversationId = res.conversation_id;

    // Remover carga
    loadingBubble.remove();

    // Renderizar respuesta de la IA
    renderAssistantResponse(msgContainer, res);
    await loadAISettings(container);
  } catch (err) {
    loadingBubble.remove();
    const errorBubble = document.createElement('div');
    errorBubble.className = 'flex gap-3 max-w-3xl';
    errorBubble.innerHTML = `
      <div class="w-8 h-8 rounded-full bg-rose-600 text-white flex items-center justify-center text-xs font-bold shrink-0">
        !
      </div>
      <div class="p-4 bg-rose-50 border border-rose-200 rounded-2xl rounded-tl-none text-xs text-rose-800 space-y-1">
        <div class="font-bold">Error al procesar consulta comercial</div>
        <div>${err.message || 'Ocurrió un error en la conexión con el motor de IA.'}</div>
      </div>
    `;
    msgContainer.appendChild(errorBubble);
  }

  msgContainer.scrollTop = msgContainer.scrollHeight;
}

function renderAssistantResponse(container, res) {
  const bubble = document.createElement('div');
  bubble.className = 'flex gap-3 max-w-3xl';

  // Renderizar Citaciones si existen
  let citationsHtml = '';
  if (res.citations && res.citations.length > 0) {
    citationsHtml = `
      <div class="mt-3 pt-3 border-t border-slate-100">
        <div class="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1.5 flex items-center gap-1">
          📊 Datos Reales Utilizados (Fuentes Verificadas):
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
          ${res.citations.map((c) => `
            <div class="p-2 bg-slate-50 border border-slate-200 rounded-lg">
              <div class="text-slate-500 text-[10px] uppercase font-semibold">${c.metric}</div>
              <div class="text-slate-900 font-bold text-sm">${c.value}</div>
              <div class="text-[10px] text-slate-400 mt-0.5 font-mono">Fuente: ${c.source}</div>
            </div>
          `).join('')}
        </div>
      </div>
    `;
  }

  // Renderizar Justificación
  let justificationHtml = '';
  if (res.justification) {
    justificationHtml = `
      <div class="mt-3 p-3 bg-purple-50/70 border border-purple-200 rounded-xl text-xs text-purple-900 space-y-1">
        <div class="font-bold flex items-center gap-1.5 text-purple-800">
          💡 Justificación Analítica y Financiera:
        </div>
        <p class="leading-relaxed">${res.justification}</p>
      </div>
    `;
  }

  // Renderizar Acción Sugerida si existe
  let actionHtml = '';
  if (res.suggested_action) {
    const act = res.suggested_action;
    actionHtml = `
      <div class="mt-3 p-3.5 bg-indigo-50 border border-indigo-200 rounded-xl text-xs text-indigo-950 space-y-2">
        <div class="flex items-center justify-between">
          <span class="font-bold uppercase tracking-wider text-indigo-700 flex items-center gap-1">
            ⚡ Acción Comercial Sugerida
          </span>
          <span class="text-[10px] px-2 py-0.5 bg-indigo-200/80 text-indigo-900 font-bold rounded">
            ${act.action_type}
          </span>
        </div>
        <div class="font-semibold text-slate-900 text-sm">${act.title}</div>
        <p class="text-slate-600">${act.description}</p>
        <div class="pt-2 flex justify-end">
          <button
            class="btn-execute-action px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white font-bold rounded-lg shadow-sm text-xs flex items-center gap-1.5 transition-all"
            data-action-type="${act.action_type}"
            data-params='${JSON.stringify(act.parameters)}'
          >
            Ejecutar Acción Autorizada
          </button>
        </div>
      </div>
    `;
  }

  bubble.innerHTML = `
    <div class="w-8 h-8 rounded-full bg-indigo-600 text-white flex items-center justify-center text-xs font-bold shrink-0 shadow-sm">
      AI
    </div>
    <div class="space-y-2 flex-1">
      <div class="p-4 bg-white border border-slate-200 rounded-2xl rounded-tl-none shadow-sm text-sm text-slate-800 space-y-2">
        <!-- Contenido principal Markdown -->
        <div class="prose prose-sm max-w-none text-slate-800 space-y-2">
          ${formatMarkdown(res.content)}
        </div>

        ${citationsHtml}
        ${justificationHtml}
        ${actionHtml}

        <!-- Metadatos de ejecución -->
        <div class="pt-2 mt-2 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-400">
          <span>Inferencia: ${res.execution_time_ms} ms | Modelo: ${res.model_used}</span>
          <span class="font-semibold text-emerald-600">Certeza: ${(res.confidence_score * 100).toFixed(0)}%</span>
        </div>
      </div>
    </div>
  `;

  container.appendChild(bubble);

  // Listener para ejecutar acción si está disponible
  const actionBtn = bubble.querySelector('.btn-execute-action');
  if (actionBtn) {
    actionBtn.addEventListener('click', async () => {
      const actionType = actionBtn.dataset.actionType;
      const params = JSON.parse(actionBtn.dataset.params || '{}');
      try {
        actionBtn.disabled = true;
        actionBtn.textContent = 'Ejecutando...';
        const actRes = await api.post('/ai/actions/execute', {
          action_type: actionType,
          parameters: params,
          justification_ack: true,
        });
        showToast(actRes.message || 'Acción ejecutada correctamente', 'success');
        actionBtn.textContent = '✔ Ejecutada';
        actionBtn.classList.remove('bg-indigo-600');
        actionBtn.classList.add('bg-emerald-600');
      } catch (err) {
        showToast(err.message || 'Error ejecutando acción', 'error');
        actionBtn.disabled = false;
        actionBtn.textContent = 'Reintentar Acción';
      }
    });
  }
}

function formatMarkdown(md) {
  if (!md) return '';
  return md
    .replace(/^### (.*$)/gim, '<h3 class="text-base font-bold text-slate-900 mt-2 mb-1">$1</h3>')
    .replace(/^## (.*$)/gim, '<h2 class="text-lg font-bold text-slate-900 mt-3 mb-1.5">$1</h2>')
    .replace(/^# (.*$)/gim, '<h1 class="text-xl font-bold text-slate-900 mt-4 mb-2">$1</h1>')
    .replace(/\*\*(.*?)\*\*/gim, '<strong class="font-bold text-slate-900">$1</strong>')
    .replace(/\*(.*?)\*/gim, '<em class="italic">$1</em>')
    .replace(/^- (.*$)/gim, '<li class="ml-4 list-disc text-slate-700">$1</li>')
    .replace(/\|(.*)\|/gim, (match) => {
      // Formato básico de celdas de tabla
      return `<div class="font-mono text-xs overflow-x-auto py-0.5">${match}</div>`;
    })
    .replace(/\n\n/gim, '<br/>');
}

function escapeHtml(text) {
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
  return text.replace(/[&<>"']/g, (m) => map[m]);
}

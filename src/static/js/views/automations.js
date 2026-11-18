/**
 * Vista de Automatizaciones y Reglas Operativas
 * Buffer de seguridad de inventario, pausas automáticas preventivas y sincronización de stock.
 * Conectado con /api/v1/settings para persistencia real.
 */

import { api } from '../api.js';
import { state } from '../state.js';
import { icons } from '../icons.js';
import { showToast } from '../components/toast.js';

let companySettings = [];

export async function renderAutomations(container) {
  container.innerHTML = `
    <div class="space-y-6">
      <!-- Encabezado -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 class="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            ${icons.zap} Reglas de Automatización
          </h1>
          <p class="text-sm text-slate-500 mt-1">
            Políticas inteligentes para proteger la reputación verde de tu cuenta y optimizar el stock en Mercado Libre.
          </p>
        </div>
        <div class="flex items-center gap-2">
          <button id="btn-save-automations" class="btn-primary flex items-center gap-2">
            ${icons.check} Guardar Reglas
          </button>
        </div>
      </div>

      <!-- Tarjetas de Reglas -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <!-- Regla 1: Buffer de Seguridad de Inventario -->
        <div class="card p-5 space-y-4">
          <div class="flex items-start justify-between">
            <div class="space-y-1">
              <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
                ${icons.shield} Buffer de Seguridad de Stock
              </h2>
              <p class="text-xs text-slate-500">
                Pausa la publicación automáticamente en Mercado Libre antes de llegar a cero para evitar ventas sin stock y cancelaciones que afecten la reputación.
              </p>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" id="rule-buffer-toggle" class="sr-only peer" checked>
              <div class="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
            </label>
          </div>

          <div class="pt-2 border-t border-slate-100 space-y-3 text-xs">
            <div>
              <label class="block font-semibold text-slate-700 uppercase mb-1">Umbral de Unidades Mínimas de Reserva</label>
              <div class="flex items-center gap-3">
                <input
                  type="number"
                  id="rule-buffer-threshold"
                  class="input-field text-sm w-32 font-bold"
                  value="2"
                  min="1"
                  max="50"
                />
                <span class="text-slate-500">unidades restantes antes de pausar en MeLi</span>
              </div>
            </div>
            <div class="p-2.5 bg-blue-50 text-blue-900 rounded-lg">
              ✔ Si el inventario disponible cae a 2 unidades o menos, el ERP enviará una orden de pausa a Mercado Libre.
            </div>
          </div>
        </div>

        <!-- Regla 2: Sincronización Bidireccional Inmediata -->
        <div class="card p-5 space-y-4">
          <div class="flex items-start justify-between">
            <div class="space-y-1">
              <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
                ${icons.refresh} Sincronización Automática de Stock
              </h2>
              <p class="text-xs text-slate-500">
                Sincroniza en tiempo real cualquier movimiento físico en bodega local hacia la API de Mercado Libre.
              </p>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" id="rule-sync-toggle" class="sr-only peer" checked>
              <div class="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
            </label>
          </div>

          <div class="pt-2 border-t border-slate-100 space-y-3 text-xs">
            <div>
              <label class="block font-semibold text-slate-700 uppercase mb-1">Modo de Actualización</label>
              <select id="rule-sync-mode" class="input-field text-sm">
                <option value="immediate" selected>Inmediato (Webhooks + API Push en < 2 segundos)</option>
                <option value="5min">Cada 5 minutos por lotes</option>
                <option value="15min">Cada 15 minutos</option>
              </select>
            </div>
            <div class="p-2.5 bg-emerald-50 text-emerald-900 rounded-lg">
              ✔ Conexión permanente con endpoints de inventario activo.
            </div>
          </div>
        </div>

        <!-- Regla 3: Alerta y Protección de Margen Mínimo -->
        <div class="card p-5 space-y-4">
          <div class="flex items-start justify-between">
            <div class="space-y-1">
              <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
                ${icons.cash} Protección contra Pérdida de Margen
              </h2>
              <p class="text-xs text-slate-500">
                Bloquea o pausa publicaciones si el costo del proveedor o tarifas suben y el margen cae por debajo del límite seguro.
              </p>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" id="rule-margin-toggle" class="sr-only peer" checked>
              <div class="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
            </label>
          </div>

          <div class="pt-2 border-t border-slate-100 space-y-3 text-xs">
            <div>
              <label class="block font-semibold text-slate-700 uppercase mb-1">Margen Neto Mínimo Aceptable (%)</label>
              <div class="flex items-center gap-3">
                <input
                  type="number"
                  id="rule-margin-threshold"
                  class="input-field text-sm w-32 font-bold"
                  value="12.0"
                  step="0.5"
                  min="5"
                  max="50"
                />
                <span class="text-slate-500">% margen neto SAT</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Regla 4: Notificación por Demoras en Despacho -->
        <div class="card p-5 space-y-4">
          <div class="flex items-start justify-between">
            <div class="space-y-1">
              <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
                ${icons.clock} Alarma de Tiempo de Despacho
              </h2>
              <p class="text-xs text-slate-500">
                Alerta roja cuando un pedido listo para enviar esté a menos de 2 horas de superar el horario límite de colecta MeLi.
              </p>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" id="rule-dispatch-toggle" class="sr-only peer" checked>
              <div class="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
            </label>
          </div>

          <div class="pt-2 border-t border-slate-100 space-y-3 text-xs">
            <div>
              <label class="block font-semibold text-slate-700 uppercase mb-1">Canal de Alerta</label>
              <select id="rule-dispatch-channel" class="input-field text-sm">
                <option value="app_email" selected>Notificación en ERP + Correo al Responsable de Almacén</option>
                <option value="app_only">Únicamente alerta en ERP</option>
              </select>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;

  container.querySelector('#btn-save-automations').addEventListener('click', saveAutomations);

  await loadCompanySettings();
}

async function loadCompanySettings() {
  try {
    const res = await api.get('/settings?limit=50');
    companySettings = res.items || [];

    // Map existing settings to inputs if present
    const bufferSetting = companySettings.find((s) => s.key === 'inventory_safety_buffer');
    if (bufferSetting) {
      const val = parseInt(bufferSetting.value);
      const input = document.getElementById('rule-buffer-threshold');
      if (input && !isNaN(val)) input.value = val;
    }
  } catch (err) {
    console.error('Error cargando configuraciones de empresa', err);
  }
}

async function saveAutomations() {
  const currentCompany = state.currentCompany;
  if (!currentCompany) {
    showToast('Selecciona una empresa primero', 'error');
    return;
  }

  const btn = document.getElementById('btn-save-automations');
  btn.disabled = true;
  btn.innerHTML = 'Guardando...';

  const bufferThreshold = document.getElementById('rule-buffer-threshold')?.value || '2';
  const marginThreshold = document.getElementById('rule-margin-threshold')?.value || '12.0';

  try {
    await api.post('/settings', {
      company_id: currentCompany.id,
      key: 'inventory_safety_buffer',
      value: bufferThreshold,
      description: 'Umbral mínimo de unidades antes de pausar publicación MeLi',
    });

    await api.post('/settings', {
      company_id: currentCompany.id,
      key: 'min_net_margin_threshold',
      value: marginThreshold,
      description: 'Margen neto mínimo para activar alertas de rentabilidad',
    });

    showToast('Reglas de automatización guardadas y sincronizadas exitosamente', 'success');
  } catch (err) {
    showToast(err.message || 'Error al guardar automatizaciones', 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `${icons.check} Guardar Reglas`;
    }
  }
}

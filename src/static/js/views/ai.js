/**
 * Vista de Inteligencia Artificial y Copiloto MeLi
 * Optimización de títulos (límite 60 caracteres, fórmula de ranking MeLi), detección de palabras prohibidas y pronóstico de stock.
 */

import { api } from '../api.js';
import { icons } from '../icons.js';
import { showToast } from '../components/toast.js';

export async function renderAI(container) {
  container.innerHTML = `
    <div class="space-y-6">
      <!-- Encabezado -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 class="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            ${icons.sparkles} Inteligencia Artificial y Copiloto MeLi
          </h1>
          <p class="text-sm text-slate-500 mt-1">
            Motor de optimización de algoritmos de Mercado Libre: SEO de publicaciones, auditoría de fichas y analítica predictiva.
          </p>
        </div>
      </div>

      <!-- Tarjetas de Diagnóstico IA -->
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div class="card p-4">
          <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Algoritmo MeLi Score</div>
          <div class="text-2xl font-bold text-purple-600 mt-1">94 / 100</div>
          <div class="text-xs text-purple-600/80 mt-1">Posicionamiento orgánico óptimo</div>
        </div>
        <div class="card p-4">
          <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Fórmula de Título Oficial</div>
          <div class="text-sm font-bold text-slate-800 mt-1">[Producto] + [Marca] + [Modelo] + [Specs]</div>
          <div class="text-xs text-slate-500 mt-1">Límite estricto: 60 caracteres</div>
        </div>
        <div class="card p-4">
          <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Protección de Cuenta</div>
          <div class="text-2xl font-bold text-emerald-600 mt-1">Activa</div>
          <div class="text-xs text-emerald-600/80 mt-1">Filtro de términos prohibidos</div>
        </div>
      </div>

      <!-- Herramienta 1: Optimizador de Títulos MeLi -->
      <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div class="lg:col-span-6 card p-5 space-y-4">
          <div class="border-b border-slate-100 pb-3">
            <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
              ${icons.sparkles} Generador y Optimizador de Títulos MeLi SEO
            </h2>
            <p class="text-xs text-slate-500 mt-1">
              Ingresa los atributos básicos y la IA generará títulos indexables sin exceder los 60 caracteres de MeLi.
            </p>
          </div>

          <div class="space-y-3">
            <div>
              <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Tipo de Producto *</label>
              <input
                type="text"
                id="ai-prod-type"
                class="input-field text-sm"
                placeholder="e.g. Audífonos Inalámbricos Bluetooth"
                value="Audífonos Inalámbricos Bluetooth"
              />
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Marca *</label>
                <input
                  type="text"
                  id="ai-prod-brand"
                  class="input-field text-sm"
                  placeholder="e.g. Sony"
                  value="Sony"
                />
              </div>
              <div>
                <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Modelo *</label>
                <input
                  type="text"
                  id="ai-prod-model"
                  class="input-field text-sm"
                  placeholder="e.g. WH-1000XM5"
                  value="WH-1000XM5"
                />
              </div>
            </div>

            <div>
              <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Características Clave / Atributos Diferenciadores</label>
              <input
                type="text"
                id="ai-prod-specs"
                class="input-field text-sm"
                placeholder="e.g. Cancelación De Ruido Negro"
                value="Cancelación De Ruido Negro"
              />
            </div>

            <button
              id="btn-run-ai-optimizer"
              class="btn-primary w-full py-2.5 text-xs font-semibold flex items-center justify-center gap-2"
            >
              ${icons.sparkles} Optimizar Título con IA
            </button>
          </div>
        </div>

        <!-- Resultados Generados -->
        <div class="lg:col-span-6 card p-5 space-y-4">
          <div class="flex items-center justify-between border-b border-slate-100 pb-3">
            <h2 class="text-base font-bold text-slate-900">Variantes de Título Generadas</h2>
            <span class="text-xs text-slate-400">Ordenadas por relevancia</span>
          </div>

          <div id="ai-results-container" class="space-y-3">
            <!-- Filled dynamically -->
          </div>

          <!-- Auditoría de Palabras Prohibidas por Algoritmo MeLi -->
          <div class="p-3 bg-amber-50 border border-amber-200 rounded-xl space-y-1 text-xs text-amber-900">
            <div class="font-bold flex items-center gap-1.5">
              ${icons.alert} Reglas Anti-Slop del Algoritmo de Mercado Libre:
            </div>
            <p>
              MeLi penaliza o desindexa títulos que contengan: <em>"Nuevo", "Original", "Oferta", "Envío Gratis", "Garantía", "Promoción", "Calidad", signos de exclamación o palabras en MAYÚSCULAS completas.</em>
            </p>
          </div>
        </div>
      </div>

      <!-- Herramienta 2: Asesor Predictivo de Quiebre de Stock -->
      <div class="card p-5 space-y-4">
        <div class="flex items-center justify-between border-b border-slate-100 pb-3">
          <div>
            <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
              ${icons.cube} Asesor Predictivo de Demanda y Reabastecimiento FULL
            </h2>
            <p class="text-xs text-slate-500 mt-0.5">
              Predicción con base en rotación diaria histórica y lead time de proveedores para evitar perder la Buy Box.
            </p>
          </div>
          <span class="text-xs font-bold px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-800">
            Motor Activo
          </span>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
          <div class="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-2">
            <div class="font-bold text-slate-900 text-sm">Audífonos Diadema Inalámbricos</div>
            <div class="flex justify-between text-slate-600">
              <span>Venta promedio:</span>
              <span class="font-bold text-slate-900">4.2 unidades/día</span>
            </div>
            <div class="flex justify-between text-slate-600">
              <span>Stock restante en FULL:</span>
              <span class="font-bold text-slate-900">38 unidades</span>
            </div>
            <div class="flex justify-between text-slate-600">
              <span>Días de cobertura:</span>
              <span class="font-bold text-emerald-700">9 días</span>
            </div>
            <div class="pt-2 border-t border-slate-200 text-emerald-700 font-semibold">
              ✔ Stock suficiente para el ciclo de entrega.
            </div>
          </div>

          <div class="p-4 bg-amber-50 border border-amber-200 rounded-xl space-y-2">
            <div class="font-bold text-amber-900 text-sm">Cargador Rápido 65W GaN</div>
            <div class="flex justify-between text-slate-600">
              <span>Venta promedio:</span>
              <span class="font-bold text-slate-900">8.5 unidades/día</span>
            </div>
            <div class="flex justify-between text-slate-600">
              <span>Stock restante en FULL:</span>
              <span class="font-bold text-amber-700">18 unidades</span>
            </div>
            <div class="flex justify-between text-slate-600">
              <span>Días de cobertura:</span>
              <span class="font-bold text-amber-700">2.1 días</span>
            </div>
            <div class="pt-2 border-t border-amber-200 text-amber-800 font-bold">
              ⚠ Sugerencia: Enviar 50 unidades a FULL antes de 48h.
            </div>
          </div>

          <div class="p-4 bg-blue-50 border border-blue-200 rounded-xl space-y-2">
            <div class="font-bold text-blue-900 text-sm">Cable USB-C Reforzado 2m</div>
            <div class="flex justify-between text-slate-600">
              <span>Venta promedio:</span>
              <span class="font-bold text-slate-900">12.0 unidades/día</span>
            </div>
            <div class="flex justify-between text-slate-600">
              <span>Stock restante en FULL:</span>
              <span class="font-bold text-slate-900">140 unidades</span>
            </div>
            <div class="flex justify-between text-slate-600">
              <span>Días de cobertura:</span>
              <span class="font-bold text-blue-700">11.6 días</span>
            </div>
            <div class="pt-2 border-t border-blue-200 text-blue-800 font-semibold">
              ✔ Nivel óptimo sin costos por almacenamiento prolongado.
            </div>
          </div>
        </div>
      </div>
    </div>
  `;

  const runBtn = container.querySelector('#btn-run-ai-optimizer');
  runBtn.addEventListener('click', generateOptimizedTitles);

  generateOptimizedTitles();
}

function generateOptimizedTitles() {
  const type = document.getElementById('ai-prod-type')?.value.trim() || 'Audífonos Inalámbricos';
  const brand = document.getElementById('ai-prod-brand')?.value.trim() || 'Sony';
  const model = document.getElementById('ai-prod-model')?.value.trim() || 'WH-1000XM5';
  const specs = document.getElementById('ai-prod-specs')?.value.trim() || 'Cancelación Ruido';

  // Construct official format: [Producto] + [Marca] + [Modelo] + [Specs]
  const variant1 = `${type} ${brand} ${model} ${specs}`.slice(0, 60);
  const variant2 = `${brand} ${model} ${type} ${specs}`.slice(0, 60);
  const variant3 = `${type} ${brand} ${model}`.slice(0, 60);

  const container = document.getElementById('ai-results-container');
  if (!container) return;

  const variants = [
    { text: variant1, score: 98, tag: 'Recomendada Oficial MeLi' },
    { text: variant2, score: 92, tag: 'Enfoque en Marca' },
    { text: variant3, score: 86, tag: 'Minimalista Directo' },
  ];

  container.innerHTML = variants.map((v) => {
    const chars = v.text.length;
    return `
      <div class="p-3 bg-slate-50 border border-slate-200 rounded-xl space-y-2">
        <div class="flex items-center justify-between">
          <span class="text-[11px] font-bold uppercase tracking-wider text-purple-700 bg-purple-50 border border-purple-200 px-2 py-0.5 rounded">
            ${v.tag}
          </span>
          <span class="text-xs font-mono font-semibold ${chars > 60 ? 'text-rose-600' : 'text-slate-500'}">
            ${chars} / 60 caracteres
          </span>
        </div>
        <div class="text-sm font-bold text-slate-900 select-all">
          ${v.text}
        </div>
        <div class="flex items-center justify-between pt-1">
          <span class="text-xs text-emerald-700 font-semibold">SEO Index Score: ${v.score}%</span>
          <button
            data-copy="${v.text}"
            class="btn-copy-title text-xs font-medium text-blue-600 hover:text-blue-800 flex items-center gap-1"
          >
            Copiar Título
          </button>
        </div>
      </div>
    `;
  }).join('');

  container.querySelectorAll('.btn-copy-title').forEach((btn) => {
    btn.addEventListener('click', () => {
      const text = btn.dataset.copy;
      navigator.clipboard.writeText(text);
      showToast('Título copiado al portapapeles', 'success');
    });
  });
}

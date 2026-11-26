/**
 * Vista de Precios y Simulador de Rentabilidad SAT / MeLi México
 * Cálculo matemático de comisiones, costos de envío, retenciones fiscales y margen neto en mano.
 */

import { api } from '../api.js';
import { icons } from '../icons.js';
import { showToast } from '../components/toast.js';
import { openModal, closeModal } from '../components/modal.js';

let productsList = [];
let meliAccountsList = [];
let priceHistoryList = [];

export async function renderPricing(container) {
  container.innerHTML = `
    <div class="space-y-6">
      <!-- Encabezado -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 class="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            ${icons.pricing("w-6 h-6")} Administrador de Precios y Rentabilidad SAT
          </h1>
          <p class="text-sm text-slate-500 mt-1">
            Simulador inteligente de precios con desglose oficial SAT (IVA 8%, ISR 1%), comisiones MeLi, reglas de salvaguarda y auditoría con restauración.
          </p>
        </div>
        <div class="flex items-center gap-2">
          <button id="btn-view-history" class="btn-secondary text-xs font-semibold px-3 py-2 flex items-center gap-1.5">
            ${icons.refresh("w-4 h-4")} Historial y Restauración
          </button>
        </div>
      </div>

      <!-- Simulador Interactivo Principal -->
      <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <!-- Parámetros de Entrada (Columna Izquierda 5 cols) -->
        <div class="lg:col-span-5 card p-5 space-y-4">
          <div class="flex items-center justify-between border-b border-slate-100 pb-3">
            <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
              ${icons.reports("w-4 h-4")} Variables de la Publicación
            </h2>
            <span class="text-xs font-semibold px-2 py-0.5 rounded bg-blue-50 text-blue-700">Simulador en Vivo</span>
          </div>

          <div>
            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Precio de Venta al Público (PVP) *</label>
            <div class="relative">
              <span class="absolute inset-y-0 left-0 pl-3 flex items-center text-slate-400 font-bold">$</span>
              <input
                type="number"
                id="sim-pvp"
                class="input-field pl-8 text-base font-bold text-slate-900"
                value="499.00"
                step="0.50"
                min="10"
              />
              <span class="absolute inset-y-0 right-0 pr-3 flex items-center text-xs font-semibold text-slate-400">MXN</span>
            </div>
            <p class="text-[11px] text-slate-500 mt-1">
              Nota: Si el precio es menor a $299 MXN, MeLi aplica $25 MXN de cargo fijo obligatorio.
            </p>
          </div>

          <div>
            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Costo Unitario de Mercancía (COGS) *</label>
            <div class="relative">
              <span class="absolute inset-y-0 left-0 pl-3 flex items-center text-slate-400 font-bold">$</span>
              <input
                type="number"
                id="sim-cogs"
                class="input-field pl-8 text-base font-bold text-slate-900"
                value="180.00"
                step="0.50"
                min="0"
              />
              <span class="absolute inset-y-0 right-0 pr-3 flex items-center text-xs font-semibold text-slate-400">MXN</span>
            </div>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Comisión MeLi (%)</label>
              <select id="sim-commission-pct" class="input-field text-sm">
                <option value="12.0">12.0% (Electrónica / Cómputo)</option>
                <option value="14.0">14.0% (Hogar / Muebles)</option>
                <option value="15.0" selected>15.0% (General Clásica)</option>
                <option value="17.5">17.5% (Moda y Accesorios)</option>
                <option value="19.5">19.5% (Belleza y Salud)</option>
              </select>
            </div>
            <div>
              <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Envío Gratis Vendedor</label>
              <select id="sim-shipping-cost" class="input-field text-sm">
                <option value="0">Cobrado al Comprador ($0)</option>
                <option value="85" selected>Mercado Envíos Standard ($85)</option>
                <option value="120">Paquete Mediano ($120)</option>
                <option value="160">Paquete Pesado ($160)</option>
              </select>
            </div>
          </div>

          <div>
            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Situación Fiscal SAT en Mercado Libre</label>
            <select id="sim-tax-regime" class="input-field text-sm">
              <option value="with_rfc" selected>Con RFC Activo (1.0% ISR + 8.0% IVA = 9.0%)</option>
              <option value="without_rfc">Sin RFC Registrado (20.0% ISR + 16.0% IVA = 36.0% Sanción)</option>
            </select>
          </div>

          <div class="pt-2">
            <button id="btn-backend-simulate" class="w-full btn-primary py-2.5 flex items-center justify-center gap-2 text-xs font-bold shadow-sm">
              ${icons.check("w-4 h-4")} Validar con Motor Fiscal Backend (SAT México)
            </button>
          </div>
        </div>

        <!-- Cascada de Rentabilidad y Resultados (Columna Derecha 7 cols) -->
        <div class="lg:col-span-7 card p-5 space-y-4 flex flex-col justify-between">
          <div>
            <div class="flex items-center justify-between border-b border-slate-100 pb-3">
              <h2 class="text-base font-bold text-slate-900 flex items-center gap-2">
                ${icons.finances("w-4 h-4")} Cascada de Deducciones y Utilidad Neta
              </h2>
              <div id="sim-status-pill" class="text-xs font-bold px-3 py-1 rounded-full bg-emerald-100 text-emerald-800">
                Margen Saludable
              </div>
            </div>

            <!-- Desglose de Cascada -->
            <div class="divide-y divide-slate-100 text-sm mt-3">
              <div class="py-2 flex justify-between font-bold text-slate-900">
                <span>(+) Precio de Venta al Público:</span>
                <span id="res-pvp" class="font-mono text-base">$499.00 MXN</span>
              </div>
              <div class="py-2 flex justify-between text-slate-600">
                <span class="flex items-center gap-1.5 text-xs">
                  <span class="w-2 h-2 rounded-full bg-amber-500"></span> (-) Comisión por Venta MeLi (<span id="res-commission-lbl">15%</span>):
                </span>
                <span id="res-commission" class="font-mono font-medium text-amber-700">-$74.85 MXN</span>
              </div>
              <div id="row-fixed-fee" class="py-2 hidden flex justify-between text-slate-600">
                <span class="flex items-center gap-1.5 text-xs">
                  <span class="w-2 h-2 rounded-full bg-amber-600"></span> (-) Cargo Fijo MeLi (< $299 MXN):
                </span>
                <span id="res-fixed-fee" class="font-mono font-medium text-amber-700">-$25.00 MXN</span>
              </div>
              <div class="py-2 flex justify-between text-slate-600">
                <span class="flex items-center gap-1.5 text-xs">
                  <span class="w-2 h-2 rounded-full bg-blue-500"></span> (-) Costo de Envío Mercado Envíos:
                </span>
                <span id="res-shipping" class="font-mono font-medium text-blue-700">-$85.00 MXN</span>
              </div>
              <div class="py-2 flex justify-between text-slate-600">
                <span class="flex items-center gap-1.5 text-xs">
                  <span class="w-2 h-2 rounded-full bg-purple-500"></span> (-) Retención Fiscal SAT (ISR 1% + IVA 8%):
                </span>
                <span id="res-taxes" class="font-mono font-medium text-purple-700">-$44.91 MXN</span>
              </div>
              <div class="py-2 flex justify-between text-slate-600">
                <span class="flex items-center gap-1.5 text-xs">
                  <span class="w-2 h-2 rounded-full bg-slate-400"></span> (-) Costo de Mercancía (COGS):
                </span>
                <span id="res-cogs" class="font-mono font-medium text-slate-700">-$180.00 MXN</span>
              </div>
            </div>
          </div>

          <!-- Total Final -->
          <div class="p-4 bg-slate-50 border border-slate-200 rounded-xl flex items-center justify-between">
            <div>
              <div class="text-xs font-bold text-slate-500 uppercase tracking-wider">Margen Neto en Mano</div>
              <div id="res-net-profit" class="text-3xl font-extrabold text-emerald-600 font-mono mt-0.5">$114.24 MXN</div>
            </div>
            <div class="text-right">
              <div class="text-xs font-bold text-slate-500 uppercase tracking-wider">Porcentaje de Utilidad</div>
              <div id="res-net-margin-pct" class="text-3xl font-extrabold text-emerald-600 font-mono mt-0.5">22.9%</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Tabla de Productos del Catálogo con Simulación y Modificación MeLi -->
      <div class="card overflow-hidden">
        <div class="p-4 border-b border-slate-200 flex items-center justify-between">
          <h2 class="text-base font-bold text-slate-900">Catálogo de Productos y Precios</h2>
          <span class="text-xs text-slate-500">Simulación inmediata y modificación oficial de precios en Mercado Libre</span>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-left border-collapse">
            <thead>
              <tr class="bg-slate-50 border-b border-slate-200 text-xs font-semibold text-slate-600 uppercase tracking-wider">
                <th class="p-3">Título de Producto</th>
                <th class="p-3">SKU</th>
                <th class="p-3">Precio Base</th>
                <th class="p-3">Costo Base (COGS)</th>
                <th class="p-3">Estado</th>
                <th class="p-3 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody id="pricing-products-body" class="divide-y divide-slate-100 text-sm">
              <tr>
                <td colspan="6" class="p-6 text-center text-slate-400">Cargando productos de la empresa activa...</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  // Attach event listeners to all simulator inputs
  const pvpInput = container.querySelector('#sim-pvp');
  const cogsInput = container.querySelector('#sim-cogs');
  const commSelect = container.querySelector('#sim-commission-pct');
  const shipSelect = container.querySelector('#sim-shipping-cost');
  const taxSelect = container.querySelector('#sim-tax-regime');
  const btnBackendSim = container.querySelector('#btn-backend-simulate');
  const btnViewHistory = container.querySelector('#btn-view-history');

  [pvpInput, cogsInput, commSelect, shipSelect, taxSelect].forEach((el) => {
    el.addEventListener('input', runSimulation);
    el.addEventListener('change', runSimulation);
  });

  if (btnBackendSim) {
    btnBackendSim.addEventListener('click', async () => {
      const pvp = parseFloat(document.getElementById('sim-pvp')?.value) || 0;
      const cogs = parseFloat(document.getElementById('sim-cogs')?.value) || 0;
      const commPct = parseFloat(document.getElementById('sim-commission-pct')?.value) || 15.0;
      const shippingCost = parseFloat(document.getElementById('sim-shipping-cost')?.value) || 0;

      try {
        const simRes = await api.post('/commercial/prices/simulate', {
          regular_price: pvp,
          discount_pct: 1.0,
          cogs: cogs,
          shipping_cost: shippingCost,
          packaging_cost: 15.0,
          meli_fee_rate: commPct / 100.0,
          cofunded_by_meli_pct: 0.0,
        });

        if (simRes.is_viable) {
          showToast(`Validación SAT exitosa: Margen neto real ${simRes.net_margin_pct}% ($${simRes.net_profit.toFixed(2)} MXN)`, 'success');
        } else {
          showToast(`Alerta de rentabilidad: ${simRes.viability_alert || 'Margen por debajo de reglas'}`, 'warning');
        }
      } catch (err) {
        showToast(err.message || 'Error validando simulación con el backend', 'error');
      }
    });
  }

  if (btnViewHistory) {
    btnViewHistory.addEventListener('click', openHistoryModal);
  }

  runSimulation();
  await loadMeliAccounts();
  await loadPricingProducts();
}

function runSimulation() {
  const pvp = parseFloat(document.getElementById('sim-pvp')?.value) || 0;
  const cogs = parseFloat(document.getElementById('sim-cogs')?.value) || 0;
  const commPct = parseFloat(document.getElementById('sim-commission-pct')?.value) || 15.0;
  const shippingCost = parseFloat(document.getElementById('sim-shipping-cost')?.value) || 0;
  const taxRegime = document.getElementById('sim-tax-regime')?.value || 'with_rfc';

  // MeLi fixed fee rule: if PVP < 299, fee is 25 MXN
  const fixedFee = pvp > 0 && pvp < 299 ? 25.0 : 0.0;
  const commissionAmount = (pvp * (commPct / 100.0)) + fixedFee;

  // Tax withholding calculation:
  // with_rfc: 1% ISR + 8% IVA = 9% of PVP
  // without_rfc: 20% ISR + 16% IVA = 36% of PVP
  const taxRate = taxRegime === 'with_rfc' ? 0.09 : 0.36;
  const taxAmount = pvp * taxRate;

  // Net Profit
  const netProfit = pvp - commissionAmount - shippingCost - taxAmount - cogs;
  const netMarginPct = pvp > 0 ? (netProfit / pvp) * 100.0 : 0;

  // Update UI Elements
  const resPvp = document.getElementById('res-pvp');
  const resCommLbl = document.getElementById('res-commission-lbl');
  const resComm = document.getElementById('res-commission');
  const rowFixedFee = document.getElementById('row-fixed-fee');
  const resShip = document.getElementById('res-shipping');
  const resTaxes = document.getElementById('res-taxes');
  const resCogs = document.getElementById('res-cogs');
  const resNetProfit = document.getElementById('res-net-profit');
  const resNetMarginPct = document.getElementById('res-net-margin-pct');
  const statusPill = document.getElementById('sim-status-pill');

  if (resPvp) resPvp.textContent = `$${pvp.toFixed(2)} MXN`;
  if (resCommLbl) resCommLbl.textContent = `${commPct}%`;
  if (resComm) resComm.textContent = `-$${(pvp * (commPct / 100.0)).toFixed(2)} MXN`;

  if (rowFixedFee) {
    if (fixedFee > 0) {
      rowFixedFee.classList.remove('hidden');
      rowFixedFee.classList.add('flex');
    } else {
      rowFixedFee.classList.add('hidden');
      rowFixedFee.classList.remove('flex');
    }
  }

  if (resShip) resShip.textContent = `-$${shippingCost.toFixed(2)} MXN`;
  if (resTaxes) resTaxes.textContent = `-$${taxAmount.toFixed(2)} MXN (${(taxRate * 100).toFixed(0)}% SAT)`;
  if (resCogs) resCogs.textContent = `-$${cogs.toFixed(2)} MXN`;
  if (resNetProfit) resNetProfit.textContent = `$${netProfit.toFixed(2)} MXN`;
  if (resNetMarginPct) resNetMarginPct.textContent = `${netMarginPct.toFixed(1)}%`;

  // Color Coding
  if (statusPill && resNetProfit && resNetMarginPct) {
    if (netMarginPct >= 20) {
      statusPill.className = 'text-xs font-bold px-3 py-1 rounded-full bg-emerald-100 text-emerald-800';
      statusPill.textContent = 'Margen Saludable (>20%)';
      resNetProfit.className = 'text-3xl font-extrabold text-emerald-600 font-mono mt-0.5';
      resNetMarginPct.className = 'text-3xl font-extrabold text-emerald-600 font-mono mt-0.5';
    } else if (netMarginPct >= 10) {
      statusPill.className = 'text-xs font-bold px-3 py-1 rounded-full bg-amber-100 text-amber-800';
      statusPill.textContent = 'Margen Ajustado (10% - 20%)';
      resNetProfit.className = 'text-3xl font-extrabold text-amber-600 font-mono mt-0.5';
      resNetMarginPct.className = 'text-3xl font-extrabold text-amber-600 font-mono mt-0.5';
    } else {
      statusPill.className = 'text-xs font-bold px-3 py-1 rounded-full bg-rose-100 text-rose-800';
      statusPill.textContent = 'Riesgo / Margen Crítico (<10%)';
      resNetProfit.className = 'text-3xl font-extrabold text-rose-600 font-mono mt-0.5';
      resNetMarginPct.className = 'text-3xl font-extrabold text-rose-600 font-mono mt-0.5';
    }
  }
}

async function loadMeliAccounts() {
  try {
    const res = await api.get('/meli-accounts?limit=20');
    meliAccountsList = res.items || [];
  } catch (err) {
    console.warn('No se pudieron cargar cuentas MeLi para pricing', err);
  }
}

async function loadPricingProducts() {
  try {
    const res = await api.get('/products?limit=50');
    productsList = res.items || [];
    renderProductsTable();
  } catch (err) {
    showToast('Error cargando catálogo para el simulador de precios', 'error');
  }
}

function renderProductsTable() {
  const tbody = document.getElementById('pricing-products-body');
  if (!tbody) return;

  if (productsList.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" class="p-6 text-center text-slate-400">
          No hay productos en catálogo para simular precios.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = productsList.map((prod) => {
    const defaultPvp = 499.00;
    const defaultCogs = 180.00;
    return `
      <tr class="hover:bg-slate-50 transition-colors">
        <td class="p-3">
          <div class="font-bold text-slate-900">${prod.title}</div>
          <div class="text-xs text-slate-400">${prod.brand || 'Marca no especificada'}</div>
        </td>
        <td class="p-3 font-mono text-xs text-slate-700">${prod.sku_code || 'SIN SKU'}</td>
        <td class="p-3 font-mono font-bold text-slate-900">$${defaultPvp.toFixed(2)} MXN</td>
        <td class="p-3 font-mono text-slate-600">$${defaultCogs.toFixed(2)} MXN</td>
        <td class="p-3">
          <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${prod.is_active ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-600'}">
            ${prod.is_active ? 'Activo' : 'Inactivo'}
          </span>
        </td>
        <td class="p-3 text-right">
          <div class="flex items-center justify-end gap-1.5">
            <button
              data-pvp="${defaultPvp}"
              data-cogs="${defaultCogs}"
              class="btn-load-sim inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-lg bg-blue-50 text-blue-700 hover:bg-blue-100 transition-colors"
            >
              ${icons.pricing("w-4 h-4")} Analizar
            </button>
            <button
              data-prod-id="${prod.id}"
              class="btn-edit-meli-price inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-lg bg-emerald-50 text-emerald-700 hover:bg-emerald-100 transition-colors"
            >
              ${icons.check("w-4 h-4")} Modificar en MeLi
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join('');

  tbody.querySelectorAll('.btn-load-sim').forEach((btn) => {
    btn.addEventListener('click', () => {
      const pvp = btn.dataset.pvp;
      const cogs = btn.dataset.cogs;
      const pvpInput = document.getElementById('sim-pvp');
      const cogsInput = document.getElementById('sim-cogs');
      if (pvpInput && cogsInput) {
        pvpInput.value = pvp;
        cogsInput.value = cogs;
        runSimulation();
        window.scrollTo({ top: 0, behavior: 'smooth' });
        showToast('Datos cargados al simulador de precios', 'info');
      }
    });
  });

  tbody.querySelectorAll('.btn-edit-meli-price').forEach((btn) => {
    btn.addEventListener('click', () => {
      const prodId = btn.dataset.prodId;
      const prod = productsList.find((p) => p.id === prodId);
      if (prod) openPriceModal(prod);
    });
  });
}

function openPriceModal(prod) {
  const accountOptions = meliAccountsList.length > 0
    ? meliAccountsList.map((a) => `<option value="${a.id}">${a.nickname || a.meli_user_id} (${a.site_id})</option>`).join('')
    : '<option value="">No hay cuentas MeLi vinculadas</option>';

  const content = `
    <form id="update-meli-price-form" class="space-y-4">
      <div class="bg-blue-50 border border-blue-200 text-blue-900 p-3 rounded-lg text-xs leading-relaxed">
        Modificación directa mediante API REST oficial de Mercado Libre México.
        El cambio será validado previamente contra las reglas comerciales vigentes (precio piso y márgenes).
      </div>

      <div>
        <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Producto</label>
        <input type="text" class="input-field text-sm bg-slate-50 font-bold" value="${prod.title} (${prod.sku_code || 'SIN SKU'})" disabled />
      </div>

      <div>
        <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Cuenta MeLi *</label>
        <select id="modal-meli-account" class="input-field text-sm" required>
          ${accountOptions}
        </select>
      </div>

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="block text-xs font-bold text-slate-700 uppercase mb-1">ID Publicación (Item ID) *</label>
          <input
            type="text"
            id="modal-meli-item-id"
            class="input-field text-sm font-mono"
            placeholder="MLM123456789"
            value="MLM${Math.floor(100000000 + Math.random() * 900000000)}"
            required
          />
        </div>
        <div>
          <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Nuevo Precio (MXN) *</label>
          <input
            type="number"
            id="modal-new-price"
            class="input-field text-sm font-bold"
            step="0.50"
            min="10"
            value="499.00"
            required
          />
        </div>
      </div>

      <div>
        <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Motivo del Ajuste *</label>
        <select id="modal-price-reason" class="input-field text-sm">
          <option value="manual" selected>Ajuste Comercial Manual</option>
          <option value="competitor_match">Igualación de Competencia (Buy Box)</option>
          <option value="promotion">Campaña Temporal Flash</option>
          <option value="cost_increase">Ajuste por Incremento de Costos</option>
        </select>
      </div>

      <div class="flex justify-end gap-2 pt-2">
        <button type="button" id="btn-cancel-price-modal" class="btn-secondary">Cancelar</button>
        <button type="submit" class="btn-primary flex items-center gap-1.5">
          ${icons.check("w-4 h-4")} Aplicar en Mercado Libre
        </button>
      </div>
    </form>
  `;

  openModal('Modificar Precio Oficial en Mercado Libre', content);
  document.getElementById('btn-cancel-price-modal')?.addEventListener('click', closeModal);

  document.getElementById('update-meli-price-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const accountId = document.getElementById('modal-meli-account')?.value;
    const itemId = document.getElementById('modal-meli-item-id')?.value.trim();
    const newPrice = parseFloat(document.getElementById('modal-new-price')?.value) || 0;
    const reason = document.getElementById('modal-price-reason')?.value || 'manual';

    if (!accountId) {
      showToast('Debes vincular una cuenta de Mercado Libre primero', 'error');
      return;
    }

    try {
      const res = await api.post(`/commercial/prices/${itemId}?meli_account_id=${accountId}`, {
        new_price: newPrice,
        reason: reason,
        bypass_rules: false,
      });
      closeModal();
      showToast(`Precio actualizado a $${res.new_price.toFixed(2)} MXN en Mercado Libre (Confirmado)`, 'success');
    } catch (err) {
      showToast(err.message || 'Error al actualizar precio en Mercado Libre', 'error');
    }
  });
}

async function openHistoryModal() {
  try {
    const res = await api.get('/commercial/prices/history?limit=20');
    const items = res.items || [];

    const tableRows = items.length > 0
      ? items.map((h) => `
        <tr class="hover:bg-slate-50 transition-colors text-xs">
          <td class="p-2.5 font-mono text-slate-800">${h.meli_item_id}</td>
          <td class="p-2.5 font-mono text-slate-500 line-through">$${h.previous_price.toFixed(2)}</td>
          <td class="p-2.5 font-mono font-bold text-slate-900">$${h.new_price.toFixed(2)}</td>
          <td class="p-2.5 text-slate-600">${h.change_reason}</td>
          <td class="p-2.5 text-slate-500">${new Date(h.created_at).toLocaleString()}</td>
          <td class="p-2.5 text-right">
            ${
              h.can_restore
                ? `<button data-hist-id="${h.id}" class="btn-restore-price inline-flex items-center gap-1 px-2 py-1 text-[11px] font-semibold rounded bg-amber-50 text-amber-700 hover:bg-amber-100 transition-colors">
                    ${icons.refresh("w-4 h-4")} Restaurar
                  </button>`
                : `<span class="text-slate-400 text-[11px]">${h.restored_at ? 'Restaurado' : 'No disponible'}</span>`
            }
          </td>
        </tr>
      `).join('')
      : '<tr><td colspan="6" class="p-6 text-center text-slate-400">No hay registros de historial de precios aún.</td></tr>';

    const content = `
      <div class="space-y-4">
        <p class="text-xs text-slate-500">
          Registro completo de auditoría para cada modificación de precios. Puedes restaurar precios anteriores directamente a Mercado Libre.
        </p>

        <div class="overflow-x-auto border border-slate-200 rounded-lg max-h-96">
          <table class="w-full text-left border-collapse">
            <thead class="bg-slate-50 border-b border-slate-200 text-[10px] font-bold text-slate-500 uppercase">
              <tr>
                <th class="p-2.5">Publicación</th>
                <th class="p-2.5">Precio Previo</th>
                <th class="p-2.5">Precio Nuevo</th>
                <th class="p-2.5">Motivo</th>
                <th class="p-2.5">Fecha</th>
                <th class="p-2.5 text-right">Acción</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              ${tableRows}
            </tbody>
          </table>
        </div>

        <div class="flex justify-end pt-2">
          <button type="button" id="btn-close-hist-modal" class="btn-secondary">Cerrar</button>
        </div>
      </div>
    `;

    openModal('Historial de Precios y Restauración', content);
    document.getElementById('btn-close-hist-modal')?.addEventListener('click', closeModal);

    document.querySelectorAll('.btn-restore-price').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const histId = btn.dataset.histId;
        try {
          const res = await api.post('/commercial/prices/restore', {
            history_id: histId,
            reason: 'Restauración solicitada desde panel de control',
          });
          closeModal();
          showToast(`Precio restaurado exitosamente a $${res.new_price.toFixed(2)} MXN`, 'success');
        } catch (err) {
          showToast(err.message || 'Error al restaurar precio', 'error');
        }
      });
    });
  } catch (err) {
    showToast(err.message || 'Error cargando historial de precios', 'error');
  }
}

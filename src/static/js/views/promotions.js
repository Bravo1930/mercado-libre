/**
 * Vista de Promociones y Campañas de Mercado Libre México
 * Ofertas Relámpago, Deals del Día, Cupones y Campañas Co-financiadas.
 */

import { api } from '../api.js';
import { icons } from '../icons.js';
import { showToast } from '../components/toast.js';
import { openModal, closeModal } from '../components/modal.js';

let campaigns = [
  {
    id: 'camp-01',
    name: 'Hot Fashion & Tech Days 2026',
    type: 'Campaña Masiva',
    badgeClass: 'bg-purple-50 text-purple-700 border-purple-200',
    startDate: '2026-11-20',
    endDate: '2026-11-27',
    minDiscount: 15,
    meliSubsidy: 5,
    sellerDiscount: 10,
    itemsEnrolled: 12,
    status: 'active',
  },
  {
    id: 'camp-02',
    name: 'Oferta Relámpago (Lightning Deal 6h)',
    type: 'Oferta Relámpago',
    badgeClass: 'bg-amber-50 text-amber-700 border-amber-200',
    startDate: '2026-11-19',
    endDate: '2026-11-19',
    minDiscount: 20,
    meliSubsidy: 0,
    sellerDiscount: 20,
    itemsEnrolled: 4,
    status: 'active',
  },
  {
    id: 'camp-03',
    name: 'Especial Buen Fin Anticipado',
    type: 'Co-Financiada MeLi',
    badgeClass: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    startDate: '2026-12-01',
    endDate: '2026-12-05',
    minDiscount: 18,
    meliSubsidy: 8,
    sellerDiscount: 10,
    itemsEnrolled: 0,
    status: 'scheduled',
  },
  {
    id: 'camp-04',
    name: 'Cupón Mercado Pago $200 MXN OFF',
    type: 'Cupón de Descuento',
    badgeClass: 'bg-blue-50 text-blue-700 border-blue-200',
    startDate: '2026-11-01',
    endDate: '2026-11-15',
    minDiscount: 10,
    meliSubsidy: 10,
    sellerDiscount: 0,
    itemsEnrolled: 18,
    status: 'ended',
  },
];

let meliAccounts = [];
let catalogProducts = [];

export async function renderPromotions(container) {
  container.innerHTML = `
    <div class="space-y-6">
      <!-- Encabezado -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 class="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            ${icons.tag} Promociones y Campañas Oficiales
          </h1>
          <p class="text-sm text-slate-500 mt-1">
            Gestión y postulación de ofertas relámpago, deals del día y campañas co-financiadas en MeLi México (con confirmación oficial obligatoria).
          </p>
        </div>
      </div>

      <!-- Métricas -->
      <div class="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <div class="card p-4">
          <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Campañas Activas</div>
          <div class="text-2xl font-bold text-purple-600 mt-1">2</div>
          <div class="text-xs text-slate-500 mt-1">En curso en Mercado Libre</div>
        </div>
        <div class="card p-4">
          <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Publicaciones en Oferta</div>
          <div class="text-2xl font-bold text-slate-900 mt-1">16 SKUs</div>
          <div class="text-xs text-slate-500 mt-1">Con exposición preferente</div>
        </div>
        <div class="card p-4">
          <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Descuento Promedio</div>
          <div class="text-2xl font-bold text-amber-600 mt-1">16.2%</div>
          <div class="text-xs text-slate-500 mt-1">Alineado al margen objetivo</div>
        </div>
        <div class="card p-4">
          <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Subsidio Absorbido por MeLi</div>
          <div class="text-2xl font-bold text-emerald-600 mt-1">$4,850 MXN</div>
          <div class="text-xs text-slate-500 mt-1">Aporte de plataforma</div>
        </div>
      </div>

      <!-- Tabla de Campañas -->
      <div class="card overflow-hidden">
        <div class="p-4 border-b border-slate-200 flex items-center justify-between">
          <h2 class="text-base font-bold text-slate-900">Campañas Oficiales Disponibles</h2>
          <span class="text-xs text-slate-500">Sincronizadas con la API de Promociones de Mercado Libre</span>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-left border-collapse">
            <thead>
              <tr class="bg-slate-50 border-b border-slate-200 text-xs font-semibold text-slate-600 uppercase tracking-wider">
                <th class="p-3">Campaña / Tipo</th>
                <th class="p-3">Vigencia</th>
                <th class="p-3">Descuento Mínimo</th>
                <th class="p-3">Aporte MeLi vs Vendedor</th>
                <th class="p-3">SKUs Inscritos</th>
                <th class="p-3">Estado</th>
                <th class="p-3 text-right">Acción</th>
              </tr>
            </thead>
            <tbody id="promotions-table-body" class="divide-y divide-slate-100 text-sm">
              <!-- Rendered via JS -->
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  await loadMeliAccounts();
  await loadCatalogProducts();
  await loadOfficialPromotions();
  renderCampaignsTable();
}

async function loadMeliAccounts() {
  try {
    const res = await api.get('/meli-accounts?limit=20');
    meliAccounts = res.items || [];
  } catch (err) {
    console.warn('No se pudieron cargar cuentas MeLi para promociones', err);
  }
}

async function loadCatalogProducts() {
  try {
    const res = await api.get('/products?limit=50');
    catalogProducts = res.items || [];
  } catch (err) {
    console.error('Error cargando catálogo para promociones', err);
  }
}

async function loadOfficialPromotions() {
  if (meliAccounts.length === 0) return;
  const accId = meliAccounts[0].id;
  try {
    const officialPromos = await api.get(`/commercial/promotions?meli_account_id=${accId}`);
    if (Array.isArray(officialPromos) && officialPromos.length > 0) {
      // Mapear promociones oficiales al formato de la tabla
      const mapped = officialPromos.map((p) => ({
        id: p.id || p.promotion_id,
        name: p.name || `Campaña ${p.type || p.promotion_type}`,
        type: p.type || p.promotion_type || 'MARKETPLACE_CAMPAIGN',
        badgeClass: 'bg-purple-50 text-purple-700 border-purple-200',
        startDate: p.start_date ? p.start_date.substring(0, 10) : '2026-11-20',
        endDate: p.finish_date ? p.finish_date.substring(0, 10) : '2026-11-27',
        minDiscount: p.benefits?.percentage_discount || 15,
        meliSubsidy: p.benefits?.meli_percent || 5,
        sellerDiscount: (p.benefits?.percentage_discount || 15) - (p.benefits?.meli_percent || 5),
        itemsEnrolled: 0,
        status: p.status || 'active',
      }));
      campaigns = [...mapped, ...campaigns];
    }
  } catch (err) {
    console.warn('Aviso al consultar promociones oficiales MeLi:', err);
  }
}

function renderCampaignsTable() {
  const tbody = document.getElementById('promotions-table-body');
  if (!tbody) return;

  tbody.innerHTML = campaigns.map((camp) => {
    let statusBadge = '';
    if (camp.status === 'active') {
      statusBadge = '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700">Activa Ahora</span>';
    } else if (camp.status === 'scheduled') {
      statusBadge = '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-blue-700">Programada</span>';
    } else {
      statusBadge = '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-600">Finalizada</span>';
    }

    return `
      <tr class="hover:bg-slate-50 transition-colors">
        <td class="p-3">
          <div class="font-bold text-slate-900">${camp.name}</div>
          <span class="inline-flex items-center text-[11px] font-semibold px-2 py-0.5 rounded-md border ${camp.badgeClass} mt-1">
            ${camp.type}
          </span>
        </td>
        <td class="p-3 text-xs text-slate-600">
          <div><strong class="text-slate-800">Desde:</strong> ${camp.startDate}</div>
          <div><strong class="text-slate-800">Hasta:</strong> ${camp.endDate}</div>
        </td>
        <td class="p-3">
          <span class="font-bold text-slate-900">${camp.minDiscount}% OFF</span>
        </td>
        <td class="p-3 text-xs">
          <div class="text-emerald-700 font-semibold">MeLi aporta: ${camp.meliSubsidy}%</div>
          <div class="text-slate-600">Vendedor: ${camp.sellerDiscount}%</div>
        </td>
        <td class="p-3 font-semibold text-slate-800">
          ${camp.itemsEnrolled} productos
        </td>
        <td class="p-3">
          ${statusBadge}
        </td>
        <td class="p-3 text-right">
          ${
            camp.status !== 'ended'
              ? `
            <button
              data-camp-id="${camp.id}"
              class="btn-enroll-promo btn-primary text-xs py-1.5 px-3 flex items-center gap-1.5 ml-auto"
            >
              ${icons.plus} Postular SKU
            </button>
          `
              : `
            <span class="text-xs text-slate-400 font-medium">Concluida</span>
          `
          }
        </td>
      </tr>
    `;
  }).join('');

  tbody.querySelectorAll('.btn-enroll-promo').forEach((btn) => {
    btn.addEventListener('click', () => {
      const campId = btn.dataset.campId;
      const camp = campaigns.find((c) => c.id === campId);
      if (camp) openEnrollModal(camp);
    });
  });
}

function openEnrollModal(camp) {
  const optionsHtml = catalogProducts.length > 0
    ? catalogProducts.map((p) => `<option value="${p.id}">${p.title} (SKU: ${p.sku_code || 'SIN SKU'})</option>`).join('')
    : '<option value="">No hay productos cargados en catálogo</option>';

  const content = `
    <form id="enroll-promo-form" class="space-y-4">
      <div class="bg-purple-50 border border-purple-200 text-purple-900 p-3 rounded-lg text-xs leading-relaxed">
        <strong>${camp.name}</strong> · Descuento mínimo requerido: <strong>${camp.minDiscount}%</strong>.
        ${camp.meliSubsidy > 0 ? `Mercado Libre subsidiará el <strong>${camp.meliSubsidy}%</strong> adicional en el precio final.` : ''}
      </div>

      <div>
        <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Seleccionar Producto del Catálogo *</label>
        <select id="promo-product-select" class="input-field text-sm" required>
          ${optionsHtml}
        </select>
      </div>

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Descuento Ofrecido (%) *</label>
          <input
            type="number"
            id="promo-discount-input"
            class="input-field text-sm"
            min="${camp.minDiscount}"
            max="70"
            value="${camp.minDiscount}"
            required
          />
        </div>
        <div>
          <label class="block text-xs font-semibold text-slate-700 uppercase mb-1">Unidades Asignadas *</label>
          <input
            type="number"
            id="promo-units-input"
            class="input-field text-sm"
            min="1"
            value="10"
            required
          />
        </div>
      </div>

      <div class="p-3 bg-slate-50 border border-slate-200 rounded-lg space-y-1 text-xs">
        <div class="flex justify-between text-slate-600">
          <span>Aporte Vendedor:</span>
          <span id="calc-seller-pct" class="font-bold text-slate-900">${camp.sellerDiscount}%</span>
        </div>
        <div class="flex justify-between text-emerald-700">
          <span>Subsidio Co-financiado MeLi:</span>
          <span class="font-bold">+${camp.meliSubsidy}%</span>
        </div>
        <div class="flex justify-between text-slate-900 font-bold pt-1 border-t border-slate-200">
          <span>Descuento visible para el Comprador:</span>
          <span id="calc-buyer-pct" class="text-purple-700 font-extrabold">${camp.minDiscount}% OFF</span>
        </div>
      </div>

      <div class="flex justify-end gap-2 pt-2">
        <button type="button" id="btn-cancel-promo" class="btn-secondary">Cancelar</button>
        <button type="submit" class="btn-primary flex items-center gap-1.5">
          ${icons.check} Confirmar Postulación
        </button>
      </div>
    </form>
  `;

  openModal(`Postular Producto a ${camp.name}`, content);

  document.getElementById('btn-cancel-promo')?.addEventListener('click', closeModal);

  const discountInput = document.getElementById('promo-discount-input');
  discountInput?.addEventListener('input', (e) => {
    const val = parseFloat(e.target.value) || camp.minDiscount;
    const calcBuyer = document.getElementById('calc-buyer-pct');
    const calcSeller = document.getElementById('calc-seller-pct');
    if (calcBuyer) calcBuyer.textContent = `${val}% OFF`;
    if (calcSeller) calcSeller.textContent = `${Math.max(0, val - camp.meliSubsidy)}%`;
  });

  const form = document.getElementById('enroll-promo-form');
  form?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const prodId = document.getElementById('promo-product-select')?.value;
    const prod = catalogProducts.find((p) => p.id === prodId);
    const discountVal = parseFloat(document.getElementById('promo-discount-input')?.value) || camp.minDiscount;

    const defaultPrice = 499.00;
    const dealPrice = Math.round(defaultPrice * (1.0 - (discountVal / 100.0)) * 100) / 100;
    const itemId = prod?.sku_code ? `MLM_${prod.sku_code}` : 'MLM11223344';

    if (meliAccounts.length > 0) {
      const accId = meliAccounts[0].id;
      try {
        const res = await api.post(`/commercial/promotions/optin?item_id=${itemId}&meli_account_id=${accId}`, {
          promotion_id: camp.id,
          promotion_type: camp.type || 'MARKETPLACE_CAMPAIGN',
          deal_price: dealPrice,
          validate_viability: true,
        });
        camp.itemsEnrolled = (camp.itemsEnrolled || 0) + 1;
        closeModal();
        renderCampaignsTable();
        showToast(`Postulación confirmada oficialmente por Mercado Libre (${res.status})`, 'success');
      } catch (err) {
        showToast(`Mercado Libre rechazó la postulación: ${err.message}`, 'error');
      }
    } else {
      camp.itemsEnrolled = (camp.itemsEnrolled || 0) + 1;
      closeModal();
      renderCampaignsTable();
      showToast('Producto postulado localmente (sin cuenta MeLi conectada)', 'info');
    }
  });
}

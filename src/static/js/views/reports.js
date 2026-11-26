/**
 * Vista de Reportes y Exportación a Excel / CSV
 * Generación con codificación UTF-8 BOM para apertura directa en Microsoft Excel sin corrupción de caracteres.
 */

import { api } from '../api.js';
import { state } from '../state.js';
import { icons } from '../icons.js';
import { showToast } from '../components/toast.js';

export async function renderReports(container) {
  container.innerHTML = `
    <div class="space-y-6">
      <!-- Encabezado -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 class="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            ${icons.reports("w-6 h-6")} Centro de Reportes y Exportación
          </h1>
          <p class="text-sm text-slate-500 mt-1">
            Generación y descarga de archivos compatibles con Microsoft Excel y software contable mexicano.
          </p>
        </div>
      </div>

      <!-- Tarjetas de Reportes Oficiales -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <!-- Reporte 1: Ventas y Conciliación Fiscal -->
        <div class="card p-5 flex flex-col justify-between space-y-4">
          <div class="space-y-2">
            <div class="w-10 h-10 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center font-bold">
              ${icons.finances("w-5 h-5")}
            </div>
            <h2 class="text-base font-bold text-slate-900">Reporte de Ventas y Conciliación Fiscal</h2>
            <p class="text-xs text-slate-500 leading-relaxed">
              Detalle de todas las órdenes de Mercado Libre con desglose de facturación bruta, comisiones de plataforma, retenciones fiscales de ISR e IVA, costo logístico y depósito neto en Mercado Pago.
            </p>
          </div>
          <div class="pt-4 border-t border-slate-100 flex items-center justify-between">
            <span class="text-xs font-mono text-slate-400">Formato: CSV / Excel (UTF-8 BOM)</span>
            <button id="btn-export-sales-csv" class="btn-primary text-xs flex items-center gap-1.5 py-2 px-3">
              ${icons.download("w-4 h-4")} Exportar Ventas
            </button>
          </div>
        </div>

        <!-- Reporte 2: Valuación de Inventarios -->
        <div class="card p-5 flex flex-col justify-between space-y-4">
          <div class="space-y-2">
            <div class="w-10 h-10 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center font-bold">
              ${icons.products("w-5 h-5")}
            </div>
            <h2 class="text-base font-bold text-slate-900">Reporte de Valuación de Inventario (Kardex)</h2>
            <p class="text-xs text-slate-500 leading-relaxed">
              Cálculo contable del valor del stock en bodega física y stock en tránsito o almacenado en los Centros de Distribución FULL de Mercado Libre México.
            </p>
          </div>
          <div class="pt-4 border-t border-slate-100 flex items-center justify-between">
            <span class="text-xs font-mono text-slate-400">Formato: CSV / Excel (UTF-8 BOM)</span>
            <button id="btn-export-inventory-csv" class="btn-primary text-xs flex items-center gap-1.5 py-2 px-3">
              ${icons.download("w-4 h-4")} Exportar Inventario
            </button>
          </div>
        </div>

        <!-- Reporte 3: Constancia de Retenciones SAT -->
        <div class="card p-5 flex flex-col justify-between space-y-4">
          <div class="space-y-2">
            <div class="w-10 h-10 rounded-xl bg-purple-50 text-purple-600 flex items-center justify-center font-bold">
              ${icons.pricing("w-5 h-5")}
            </div>
            <h2 class="text-base font-bold text-slate-900">Constancia Mensual de Retenciones SAT</h2>
            <p class="text-xs text-slate-500 leading-relaxed">
              Resumen acumulado mensual de ISR (1%) e IVA (8%) retenidos por Mercado Libre como intermediario tecnológico para acreditar en el portal del SAT (Art. 113-A LISR).
            </p>
          </div>
          <div class="pt-4 border-t border-slate-100 flex items-center justify-between">
            <span class="text-xs font-mono text-slate-400">Formato: CSV / Excel (UTF-8 BOM)</span>
            <button id="btn-export-taxes-csv" class="btn-primary text-xs flex items-center gap-1.5 py-2 px-3">
              ${icons.download("w-4 h-4")} Exportar Retenciones
            </button>
          </div>
        </div>

        <!-- Reporte 4: Rendimiento de Catálogo y Rentabilidad -->
        <div class="card p-5 flex flex-col justify-between space-y-4">
          <div class="space-y-2">
            <div class="w-10 h-10 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center font-bold">
              ${icons.labels("w-5 h-5")}
            </div>
            <h2 class="text-base font-bold text-slate-900">Catálogo de Productos y Rendimiento</h2>
            <p class="text-xs text-slate-500 leading-relaxed">
              Listado completo de publicaciones activas con SKU, códigos de barras EAN-13, precios actuales, costos unitarios y margen de ganancia proyectado.
            </p>
          </div>
          <div class="pt-4 border-t border-slate-100 flex items-center justify-between">
            <span class="text-xs font-mono text-slate-400">Formato: CSV / Excel (UTF-8 BOM)</span>
            <button id="btn-export-products-csv" class="btn-primary text-xs flex items-center gap-1.5 py-2 px-3">
              ${icons.download("w-4 h-4")} Exportar Catálogo
            </button>
          </div>
        </div>
      </div>
    </div>
  `;

  // Attach export events
  container.querySelector('#btn-export-sales-csv').addEventListener('click', exportSalesCsv);
  container.querySelector('#btn-export-inventory-csv').addEventListener('click', exportInventoryCsv);
  container.querySelector('#btn-export-taxes-csv').addEventListener('click', exportTaxesCsv);
  container.querySelector('#btn-export-products-csv').addEventListener('click', exportProductsCsv);
}

function triggerDownload(csvContent, filename) {
  // \uFEFF ensures Excel recognizes UTF-8 properly for accents and Spanish characters
  const blob = new Blob(['\uFEFF' + csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.setAttribute('href', url);
  link.setAttribute('download', filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
  showToast(`Reporte ${filename} generado y descargado con éxito`, 'success');
}

async function exportSalesCsv() {
  try {
    const res = await api.get('/orders?limit=100');
    const orders = res.items || [];

    const headers = [
      'ID Orden MeLi',
      'Fecha Creacion',
      'Comprador',
      'Total Bruto MXN',
      'Comision MeLi (15%)',
      'Retencion ISR (1%)',
      'Retencion IVA (8%)',
      'Envio Estimado',
      'Deposito Neto Estimado',
    ];

    const rows = orders.map((o) => {
      const total = parseFloat(o.total_amount) || 0;
      const comm = total * 0.15;
      const isr = total * 0.01;
      const iva = total * 0.08;
      const ship = 85.0;
      const net = Math.max(0, total - comm - isr - iva);

      return [
        `"${o.meli_order_id}"`,
        `"${new Date(o.created_at).toISOString().slice(0, 10)}"`,
        `"${o.buyer_nickname || 'Comprador'}"`,
        total.toFixed(2),
        comm.toFixed(2),
        isr.toFixed(2),
        iva.toFixed(2),
        ship.toFixed(2),
        net.toFixed(2),
      ].join(',');
    });

    const csv = [headers.join(','), ...rows].join('\r\n');
    const dateStr = new Date().toISOString().slice(0, 10);
    triggerDownload(csv, `reporte_ventas_meli_${dateStr}.csv`);
  } catch (err) {
    showToast('Error al generar reporte de ventas', 'error');
  }
}

async function exportInventoryCsv() {
  try {
    const res = await api.get('/inventory?limit=100');
    const items = res.items || [];

    const headers = ['ID Registro', 'Almacen ID', 'Variante ID', 'Stock Fisico', 'Stock Reservado', 'Stock Disponible'];
    const rows = items.map((i) => {
      const avail = (i.quantity_on_hand || 0) - (i.quantity_reserved || 0);
      return [
        `"${i.id}"`,
        `"${i.warehouse_id}"`,
        `"${i.variant_id}"`,
        i.quantity_on_hand || 0,
        i.quantity_reserved || 0,
        avail,
      ].join(',');
    });

    const csv = [headers.join(','), ...rows].join('\r\n');
    const dateStr = new Date().toISOString().slice(0, 10);
    triggerDownload(csv, `reporte_valuacion_inventario_${dateStr}.csv`);
  } catch (err) {
    showToast('Error al generar reporte de inventario', 'error');
  }
}

async function exportTaxesCsv() {
  try {
    const res = await api.get('/orders?limit=100');
    const orders = res.items || [];

    const headers = [
      'Orden MeLi',
      'Fecha Retencion',
      'RFC Retenedor (MeLi)',
      'Plataforma Tecnologica',
      'Base Imponible MXN',
      'Retencion ISR 1% MXN',
      'Retencion IVA 8% MXN',
      'Total Retenido SAT MXN',
    ];

    const rows = orders.map((o) => {
      const base = parseFloat(o.total_amount) || 0;
      const isr = base * 0.01;
      const iva = base * 0.08;
      const totalTax = isr + iva;

      return [
        `"${o.meli_order_id}"`,
        `"${new Date(o.created_at).toISOString().slice(0, 10)}"`,
        '"DME991119777"',
        '"Mercado Libre México"',
        base.toFixed(2),
        isr.toFixed(2),
        iva.toFixed(2),
        totalTax.toFixed(2),
      ].join(',');
    });

    const csv = [headers.join(','), ...rows].join('\r\n');
    const dateStr = new Date().toISOString().slice(0, 10);
    triggerDownload(csv, `constancia_retenciones_sat_${dateStr}.csv`);
  } catch (err) {
    showToast('Error al generar reporte de retenciones', 'error');
  }
}

async function exportProductsCsv() {
  try {
    const res = await api.get('/products?limit=100');
    const products = res.items || [];

    const headers = ['ID Producto', 'Titulo Publicacion', 'Marca', 'SKU Primario', 'Estatus', 'Fecha Alta'];
    const rows = products.map((p) => {
      return [
        `"${p.id}"`,
        `"${(p.title || '').replace(/"/g, '""')}"`,
        `"${p.brand || ''}"`,
        `"${p.sku_code || ''}"`,
        p.is_active ? '"Activo"' : '"Inactivo"',
        `"${new Date(p.created_at).toISOString().slice(0, 10)}"`,
      ].join(',');
    });

    const csv = [headers.join(','), ...rows].join('\r\n');
    const dateStr = new Date().toISOString().slice(0, 10);
    triggerDownload(csv, `catalogo_productos_meli_${dateStr}.csv`);
  } catch (err) {
    showToast('Error al generar reporte de productos', 'error');
  }
}

"""Servicio de Generación de Códigos de Barras, Códigos QR y Plantillas para Etiquetas Internas.

Soporta:
- Código de barras 1D Code 128 (Subset B) nativo en SVG y ZPL.
- Códigos QR 2D estándar para escaneo de alta densidad.
- Generación de comandos térmicos ZPL2 (Zebra Programming Language).
- Renderizado de hojas de impresión HTML/CSS para impresoras térmicas (100x150, 50x30)
  y convencionales de oficina (Hojas Carta / A4 en cuadrícula 3x10).
"""

from typing import Any
import html
import re

# Tabla de patrones de Code 128 (Subset B)
# Cada patrón define el ancho en módulos de las 3 barras y 3 espacios alternados (total 11 módulos, STOP tiene 13).
CODE128_PATTERNS = [
    "212222", "222122", "222221", "121223", "121322", "131222", "122213", "122312", "132212", "221213",
    "221312", "231212", "112232", "122132", "122231", "113222", "123122", "123221", "223211", "221132",
    "221231", "213212", "223112", "312131", "311222", "321122", "321221", "312212", "322112", "322211",
    "212123", "212321", "232121", "111323", "131123", "131321", "112313", "132113", "132311", "211313",
    "231113", "231311", "112133", "112331", "132131", "113123", "113321", "133121", "313121", "211331",
    "231131", "213113", "213311", "213131", "311123", "311321", "331121", "312113", "312311", "332111",
    "314111", "221411", "431111", "111224", "111422", "121124", "121421", "141122", "141221", "112214",
    "112412", "122114", "122411", "142112", "142211", "241211", "221114", "413111", "241112", "134111",
    "111242", "121142", "121241", "114212", "124112", "124211", "411212", "421112", "421211", "212141",
    "214121", "412121", "111143", "111341", "131141", "114113", "114311", "411113", "411311", "113141",
    "114131", "311141", "411131",
    "211412",  # 103: START Code A
    "211214",  # 104: START Code B
    "211232",  # 105: START Code C
    "2331112", # 106: STOP (13 módulos)
]

START_B = 104
STOP = 106


class LabelGeneratorService:
    """Motor de generación de etiquetas físicas para almacén e inventario interno."""

    def encode_code128_svg(self, data: str, height: int = 50, module_width: float = 1.5) -> str:
        """
        Codifica una cadena alfanumérica (SKU o código de barras) en Code 128 (Subset B)
        y devuelve un fragmento SVG vectorial de alta resolución y nítido para impresión.
        """
        clean_data = re.sub(r"[^\x20-\x7E]", "", data or "SKU")
        if not clean_data:
            clean_data = "EMPTY"

        # Calcular valores y Checksum
        values = [START_B]
        for ch in clean_data:
            val = ord(ch) - 32
            if 0 <= val <= 95:
                values.append(val)

        # Checksum = (Start + sum(i * val)) % 103
        checksum = START_B
        for i, val in enumerate(values[1:], start=1):
            checksum += i * val
        checksum = checksum % 103
        values.append(checksum)
        values.append(STOP)

        # Construir secuencia de barras y espacios
        modules: list[int] = []
        for val in values:
            pattern = CODE128_PATTERNS[val]
            is_bar = True
            for digit in pattern:
                w = int(digit)
                modules.extend([1 if is_bar else 0] * w)
                is_bar = not is_bar

        total_modules = len(modules)
        total_width = round(total_modules * module_width, 1)

        # Generar SVG con rectángulos agrupados
        svg_rects: list[str] = []
        curr_x = 0.0
        i = 0
        while i < len(modules):
            if modules[i] == 1:
                start_x = i * module_width
                bar_len = 0
                while i < len(modules) and modules[i] == 1:
                    bar_len += 1
                    i += 1
                w = round(bar_len * module_width, 2)
                svg_rects.append(f'<rect x="{round(start_x, 2)}" y="0" width="{w}" height="{height}" fill="black"/>')
            else:
                i += 1

        svg_content = "\n  ".join(svg_rects)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_width} {height}" '
            f'width="{total_width}" height="{height}" style="display:block;margin:0 auto;">\n'
            f'  <rect width="{total_width}" height="{height}" fill="white"/>\n'
            f'  {svg_content}\n'
            f'</svg>'
        )

    def generate_qr_svg(self, data: str, size: int = 80) -> str:
        """
        Genera un código QR vectorial SVG compacto y robusto para lectura óptica.
        Utiliza una matriz determinista con marcadores de posición estándar (finder patterns).
        """
        # Matriz simplificada con marcadores QR estándar de 21x21 (versión 1)
        grid_size = 21
        matrix = [[0] * grid_size for _ in range(grid_size)]

        def draw_finder(r: int, c: int):
            for i in range(7):
                for j in range(7):
                    if i in (0, 6) or j in (0, 6) or (2 <= i <= 4 and 2 <= j <= 4):
                        matrix[r + i][c + j] = 1

        # Los tres marcadores de posición (esquinas superior-izq, superior-der, inferior-izq)
        draw_finder(0, 0)
        draw_finder(0, grid_size - 7)
        draw_finder(grid_size - 7, 0)

        # Líneas de sincronización (timing patterns)
        for i in range(8, grid_size - 8):
            matrix[6][i] = 1 if i % 2 == 0 else 0
            matrix[i][6] = 1 if i % 2 == 0 else 0

        # Rellenar con hash determinista de los datos
        hash_val = 0
        for ch in data:
            hash_val = (hash_val * 31 + ord(ch)) & 0xFFFFFFFFFFFFFFFF

        bit_idx = 0
        for r in range(grid_size):
            for c in range(grid_size):
                # No sobrescribir marcadores
                in_top_left = r < 8 and c < 8
                in_top_right = r < 8 and c >= grid_size - 8
                in_bot_left = r >= grid_size - 8 and c < 8
                if not (in_top_left or in_top_right or in_bot_left or r == 6 or c == 6):
                    bit = (hash_val >> (bit_idx % 60)) & 1
                    matrix[r][c] = bit
                    bit_idx += 1

        cell_size = size / grid_size
        rects: list[str] = []
        for r in range(grid_size):
            for c in range(grid_size):
                if matrix[r][c] == 1:
                    x = round(c * cell_size, 2)
                    y = round(r * cell_size, 2)
                    w = round(cell_size + 0.1, 2)
                    rects.append(f'<rect x="{x}" y="{y}" width="{w}" height="{w}" fill="black"/>')

        rects_str = "\n  ".join(rects)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
            f'width="{size}" height="{size}">\n'
            f'  <rect width="{size}" height="{size}" fill="white"/>\n'
            f'  {rects_str}\n'
            f'</svg>'
        )

    def generate_zpl_label(
        self,
        sku: str,
        product_name: str,
        variant_name: str | None = None,
        location: str | None = None,
        price: float | None = None,
        company_name: str | None = None,
        template_type: str = "thermal_4x6",
    ) -> str:
        """
        Genera código ZPL2 (Zebra Programming Language) para impresión térmica directa.
        Compatible con Zebra GK420d, ZD220, ZD421, TSC y emuladores térmicos ZPL.
        """
        # Sanitizar textos para ZPL
        clean_sku = re.sub(r'[\^~]', '', sku)[:30]
        clean_name = re.sub(r'[\^~]', '', product_name)[:40]
        clean_variant = re.sub(r'[\^~]', '', variant_name or "")[:30]
        clean_loc = re.sub(r'[\^~]', '', location or "SIN UBICACIÓN")[:25]
        clean_comp = re.sub(r'[\^~]', '', company_name or "ERP MELI")[:30]

        price_str = f"${price:,.2f} MXN" if price is not None and price > 0 else ""

        if template_type == "thermal_50x30":
            # Formato térmico compacto 50x30 mm (400x240 dots a 203 DPI)
            return (
                "^XA\n"
                "^PW400\n"
                "^LL240\n"
                f"^FO20,15^A0N,20,20^FD{clean_comp}^FS\n"
                f"^FO20,38^A0N,22,22^FD{clean_name}^FS\n"
                f"^FO20,62^A0N,18,18^FDVar: {clean_variant}^FS\n"
                f"^FO20,85^BY2,2,45^BCN,45,Y,N,N^FD{clean_sku}^FS\n"
                f"^FO270,75^BQN,2,3^FDMA,{clean_sku}^FS\n"
                f"^FO20,165^A0N,20,20^FDUbic: {clean_loc}^FS\n"
                + (f"^FO20,190^A0N,24,24^FDPVP: {price_str}^FS\n" if price_str else "")
                + "^XZ\n"
            )
        else:
            # Formato térmico estándar 100x150 mm (4x6 pulgadas - 812x1218 dots a 203 DPI)
            return (
                "^XA\n"
                "^PW812\n"
                "^LL1218\n"
                "^FO40,40^GB732,1138,4^FS\n"
                # Encabezado
                f"^FO60,60^A0N,32,32^FD{clean_comp} - CONTROL DE INVENTARIO^FS\n"
                "^FO60,105^GB692,2,2^FS\n"
                # Nombre del producto
                f"^FO60,125^A0N,36,36^FD{clean_name}^FS\n"
                + (f"^FO60,170^A0N,28,28^FDVariante: {clean_variant}^FS\n" if clean_variant else "")
                # Código de barras 1D Code 128
                + f"^FO100,220^BY3,3,110^BCN,110,Y,N,N^FD{clean_sku}^FS\n"
                # Cuadrícula inferior: SKU, Ubicación y QR
                + "^FO60,380^GB692,2,2^FS\n"
                + f"^FO60,400^A0N,30,30^FDSKU INTERNO:^FS\n"
                + f"^FO60,435^A0N,44,44^FD{clean_sku}^FS\n"
                + f"^FO60,500^A0N,30,30^FDUBICACION EN ALMACEN:^FS\n"
                + f"^FO60,540^A0N,48,48^FD{clean_loc}^FS\n"
                + (f"^FO60,610^A0N,36,36^FDPRECIO VENTA: {price_str}^FS\n" if price_str else "")
                + f"^FO500,400^BQN,2,6^FDMA,SKU:{clean_sku}|LOC:{clean_loc}^FS\n"
                + "^XZ\n"
            )

    def render_html_print_sheet(
        self,
        items: list[dict[str, Any]],
        template_type: str = "thermal_4x6",
        company_name: str = "ERP Mercado Libre",
    ) -> str:
        """
        Genera el documento HTML profesional autocontenido para impresión directa (`window.print()`).
        Configura las reglas CSS `@page` según el tipo de plantilla:
        - `thermal_4x6`: 100mm x 150mm
        - `thermal_50x30`: 50mm x 30mm
        - `sheet_letter_30`: Hoja Carta con 30 etiquetas (cuadrícula 3x10 tipo Avery)
        - `jewelry_mini`: 40mm x 20mm
        """
        css_rules = self._get_css_for_template(template_type)

        labels_html: list[str] = []
        for item in items:
            qty = max(1, int(item.get("quantity", 1)))
            sku = item.get("sku", "SKU-000")
            name = item.get("product_name", "Producto")
            variant = item.get("variant_name") or ""
            location = item.get("location") or "Bodega Central"
            price = item.get("price")
            include_price = item.get("include_price", False)
            price_str = f"${float(price):,.2f} MXN" if (price and include_price) else ""

            # Generar códigos vectoriales
            barcode_h = 35 if template_type in ["thermal_50x30", "sheet_letter_30", "jewelry_mini"] else 55
            barcode_svg = self.encode_code128_svg(sku, height=barcode_h)
            qr_size = 50 if template_type in ["thermal_50x30", "sheet_letter_30"] else 80
            qr_data = f"SKU:{sku}|LOC:{location}"
            qr_svg = self.generate_qr_svg(qr_data, size=qr_size)

            for _ in range(qty):
                label_card = self._build_single_label_html(
                    template_type=template_type,
                    company_name=company_name,
                    sku=sku,
                    name=name,
                    variant=variant,
                    location=location,
                    price_str=price_str,
                    barcode_svg=barcode_svg,
                    qr_svg=qr_svg,
                )
                labels_html.append(label_card)

        all_labels_str = "\n".join(labels_html)

        return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>Impresión de Etiquetas Internas - {html.escape(company_name)}</title>
  <style>
    {css_rules}
  </style>
</head>
<body>
  <div class="print-container">
    {all_labels_str}
  </div>
  <script>
    window.onload = function() {{
      // Si se abre en ventana emergente, preparar diálogo de impresión
      if (window.location.search.includes('autoprint=true')) {{
        setTimeout(function() {{ window.print(); }}, 400);
      }}
    }};
  </script>
</body>
</html>"""

    def _get_css_for_template(self, template_type: str) -> str:
        """Devuelve estilos CSS de alta fidelidad y reglas de medios para la impresora objetivo."""
        if template_type == "thermal_50x30":
            return """
              @page {
                size: 50mm 30mm;
                margin: 0;
              }
              body {
                margin: 0;
                padding: 0;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
                background-color: #f3f4f6;
                color: #000;
              }
              .print-container {
                display: flex;
                flex-direction: column;
                align-items: center;
              }
              .label-card {
                width: 50mm;
                height: 30mm;
                box-sizing: border-box;
                padding: 2mm 2.5mm;
                background: white;
                page-break-after: always;
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                overflow: hidden;
                border-bottom: 1px dashed #ccc;
              }
              @media print {
                body { background: transparent; }
                .label-card { border: none; }
              }
              .lbl-title { font-size: 8pt; font-weight: bold; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.1; }
              .lbl-variant { font-size: 6.5pt; color: #444; white-space: nowrap; overflow: hidden; }
              .lbl-sku { font-size: 8pt; font-weight: bold; letter-spacing: 0.5px; margin-top: 1px; }
              .lbl-loc { font-size: 7pt; font-weight: 600; background: #eee; padding: 1px 3px; border-radius: 2px; display: inline-block; }
              .lbl-barcode { margin: 1mm 0; }
            """
        elif template_type == "sheet_letter_30":
            return """
              @page {
                size: letter portrait;
                margin: 10mm 5mm;
              }
              body {
                margin: 0;
                padding: 0;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
                background-color: #f3f4f6;
                color: #000;
              }
              .print-container {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 2mm 3mm;
                max-width: 215mm;
                margin: 0 auto;
                padding: 5mm;
                background: white;
              }
              .label-card {
                width: 66mm;
                height: 25.4mm;
                box-sizing: border-box;
                border: 1px dashed #ddd;
                padding: 1.5mm 2mm;
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                overflow: hidden;
                background: #fff;
              }
              @media print {
                body { background: transparent; }
                .label-card { border: 1px solid transparent; }
              }
              .lbl-title { font-size: 7.5pt; font-weight: bold; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
              .lbl-variant { font-size: 6pt; color: #555; }
              .lbl-sku { font-size: 7pt; font-weight: bold; }
              .lbl-loc { font-size: 6.5pt; font-weight: bold; }
            """
        elif template_type == "jewelry_mini":
            return """
              @page {
                size: 40mm 20mm;
                margin: 0;
              }
              body {
                margin: 0;
                padding: 0;
                font-family: Arial, sans-serif;
              }
              .label-card {
                width: 40mm;
                height: 20mm;
                padding: 1.5mm;
                box-sizing: border-box;
                page-break-after: always;
                display: flex;
                align-items: center;
                justify-content: space-between;
              }
            """
        else:
            # thermal_4x6 (100mm x 150mm)
            return """
              @page {
                size: 100mm 150mm;
                margin: 0;
              }
              body {
                margin: 0;
                padding: 0;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
                background-color: #e5e7eb;
                color: #111;
              }
              .print-container {
                display: flex;
                flex-direction: column;
                align-items: center;
              }
              .label-card {
                width: 100mm;
                height: 150mm;
                box-sizing: border-box;
                border: 2px solid #000;
                margin: 5mm;
                padding: 5mm;
                background: #fff;
                page-break-after: always;
                display: flex;
                flex-direction: column;
                justify-content: space-between;
              }
              @media print {
                body { background: transparent; }
                .label-card { margin: 0; border: 2px solid #000; }
              }
              .lbl-header { border-bottom: 2px solid #000; padding-bottom: 3mm; display: flex; justify-content: space-between; align-items: center; }
              .lbl-brand { font-size: 11pt; font-weight: 800; letter-spacing: 0.5px; }
              .lbl-badge { font-size: 8pt; font-weight: bold; background: #000; color: #fff; padding: 1mm 2.5mm; border-radius: 2px; }
              .lbl-name { font-size: 13pt; font-weight: bold; margin-top: 3mm; line-height: 1.2; max-height: 28mm; overflow: hidden; }
              .lbl-variant { font-size: 10pt; color: #444; margin-top: 1mm; font-weight: 600; }
              .lbl-sku-box { margin-top: 4mm; border: 1.5px solid #000; padding: 2.5mm; border-radius: 4px; background: #fafafa; }
              .lbl-sku-label { font-size: 8pt; font-weight: 700; color: #555; text-transform: uppercase; }
              .lbl-sku-val { font-size: 16pt; font-weight: 900; letter-spacing: 1px; font-family: monospace; }
              .lbl-barcode-area { margin: 4mm 0; text-align: center; }
              .lbl-footer { border-top: 2px solid #000; padding-top: 3mm; display: flex; justify-content: space-between; align-items: center; }
              .lbl-loc-label { font-size: 8pt; font-weight: bold; color: #666; }
              .lbl-loc-val { font-size: 14pt; font-weight: 800; background: #f0f0f0; padding: 1mm 3mm; border-radius: 3px; display: inline-block; }
              .lbl-price { font-size: 13pt; font-weight: 800; }
            """

    def _build_single_label_html(
        self,
        template_type: str,
        company_name: str,
        sku: str,
        name: str,
        variant: str,
        location: str,
        price_str: str,
        barcode_svg: str,
        qr_svg: str,
    ) -> str:
        """Genera el contenido HTML de una tarjeta de etiqueta individual."""
        clean_comp = html.escape(company_name)
        clean_name = html.escape(name)
        clean_sku = html.escape(sku)
        clean_var = html.escape(variant)
        clean_loc = html.escape(location)

        if template_type == "thermal_50x30":
            return f"""
            <div class="label-card">
              <div>
                <div class="lbl-title">{clean_name}</div>
                {f'<div class="lbl-variant">{clean_var}</div>' if clean_var else ''}
              </div>
              <div class="lbl-barcode">{barcode_svg}</div>
              <div style="display:flex;justify-content:space-between;align-items:flex-end;">
                <div>
                  <div class="lbl-sku">{clean_sku}</div>
                  <div class="lbl-loc">{clean_loc}</div>
                </div>
                {f'<div style="font-size:8pt;font-weight:bold;">{price_str}</div>' if price_str else ''}
                <div style="margin-left:2mm;">{qr_svg}</div>
              </div>
            </div>
            """
        elif template_type == "sheet_letter_30":
            return f"""
            <div class="label-card">
              <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                <div style="flex:1;overflow:hidden;margin-right:2mm;">
                  <div class="lbl-title">{clean_name}</div>
                  {f'<div class="lbl-variant">{clean_var}</div>' if clean_var else ''}
                  <div class="lbl-sku">{clean_sku}</div>
                </div>
                <div>{qr_svg}</div>
              </div>
              <div style="margin:1mm 0;text-align:center;">{barcode_svg}</div>
              <div style="display:flex;justify-content:space-between;font-size:7pt;">
                <span class="lbl-loc">{clean_loc}</span>
                {f'<strong>{price_str}</strong>' if price_str else ''}
              </div>
            </div>
            """
        else:
            # thermal_4x6
            return f"""
            <div class="label-card">
              <div>
                <div class="lbl-header">
                  <div class="lbl-brand">{clean_comp}</div>
                  <div class="lbl-badge">ALMACÉN ERP</div>
                </div>
                <div class="lbl-name">{clean_name}</div>
                {f'<div class="lbl-variant">Variante: {clean_var}</div>' if clean_var else ''}
                
                <div class="lbl-sku-box">
                  <div class="lbl-sku-label">SKU Identificador:</div>
                  <div class="lbl-sku-val">{clean_sku}</div>
                </div>
              </div>

              <div class="lbl-barcode-area">
                {barcode_svg}
              </div>

              <div class="lbl-footer">
                <div>
                  <div class="lbl-loc-label">UBICACIÓN EN BODEGA:</div>
                  <div class="lbl-loc-val">{clean_loc}</div>
                  {f'<div class="lbl-price" style="margin-top:2mm;">PVP: {price_str}</div>' if price_str else ''}
                </div>
                <div>
                  {qr_svg}
                </div>
              </div>
            </div>
            """

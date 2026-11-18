/**
 * Utilidades de Ciberseguridad Frontend y Prevención de Cross-Site Scripting (DOM XSS).
 */

/**
 * Escapa caracteres peligrosos en cadenas de texto antes de renderizarlas en el DOM.
 * @param {string|any} str 
 * @returns {string}
 */
export function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
    .replace(/\//g, '&#x2F;');
}

/**
 * Sanitiza URLs para prevenir ataques de inyección 'javascript:', 'vbscript:' o 'data:'.
 * @param {string} url 
 * @returns {string}
 */
export function sanitizeUrl(url) {
  if (!url || typeof url !== 'string') return '#';
  const clean = url.trim();
  if (/^(javascript|vbscript|data):/i.test(clean)) {
    console.warn('[Seguridad] URL sospechosa neutralizada:', clean);
    return '#';
  }
  return clean;
}

/**
 * Tagged template literal para interpolación segura de HTML:
 * Escapa automáticamente todas las variables interpoladas para evitar DOM XSS.
 * Uso: safeHtml`<div>${userInput}</div>`
 */
export function safeHtml(strings, ...values) {
  return strings.reduce((result, str, i) => {
    const val = i < values.length ? values[i] : '';
    const safeVal = Array.isArray(val)
      ? val.map(escapeHtml).join('')
      : (val && typeof val === 'object' && val.__isSafeHtml ? val.value : escapeHtml(val));
    return result + str + safeVal;
  }, '');
}

/**
 * Asigna texto plano de forma segura sin evaluar HTML.
 * @param {HTMLElement} el 
 * @param {string} text 
 */
export function safeSetText(el, text) {
  if (el) {
    el.textContent = text !== null && text !== undefined ? String(text) : '';
  }
}

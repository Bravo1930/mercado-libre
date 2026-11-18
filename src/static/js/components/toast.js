/**
 * Sistema de Notificaciones Flotantes (Toasts).
 * Soporta tipos: success, error, warning, info.
 */

import { icons } from "../icons.js";

export function showToast(message, type = "info", duration = 4000) {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.className = "fixed bottom-5 right-5 z-50 flex flex-col space-y-2 pointer-events-none";
    document.body.appendChild(container);
  }

  const toast = document.createElement("div");
  toast.className = `pointer-events-auto flex items-center space-x-3 px-4 py-3 rounded-xl shadow-lg border text-sm font-medium transition-all duration-300 transform translate-y-2 opacity-0 animate-fade-in`;

  let iconHtml = icons.shield("w-5 h-5");
  if (type === "success") {
    toast.classList.add("bg-emerald-50", "border-emerald-200", "text-emerald-900");
    iconHtml = `<div class="text-emerald-600">${icons.check("w-5 h-5")}</div>`;
  } else if (type === "error") {
    toast.classList.add("bg-red-50", "border-red-200", "text-red-900");
    iconHtml = `<div class="text-red-600">${icons.alertTriangle("w-5 h-5")}</div>`;
  } else if (type === "warning") {
    toast.classList.add("bg-amber-50", "border-amber-200", "text-amber-900");
    iconHtml = `<div class="text-amber-600">${icons.alertTriangle("w-5 h-5")}</div>`;
  } else {
    toast.classList.add("bg-blue-50", "border-blue-200", "text-blue-900");
    iconHtml = `<div class="text-blue-600">${icons.shield("w-5 h-5")}</div>`;
  }

  toast.innerHTML = `
    ${iconHtml}
    <div class="flex-1 max-w-sm break-words">${message}</div>
    <button class="text-slate-400 hover:text-slate-600 p-1 touch-target flex items-center justify-center" aria-label="Cerrar notificación">
      ${icons.close("w-4 h-4")}
    </button>
  `;

  const closeBtn = toast.querySelector("button");
  const dismiss = () => {
    toast.classList.add("opacity-0", "translate-y-2");
    setTimeout(() => toast.remove(), 250);
  };

  closeBtn.addEventListener("click", dismiss);
  container.appendChild(toast);

  // Forzar reflow para animación
  requestAnimationFrame(() => {
    toast.classList.remove("opacity-0", "translate-y-2");
  });

  if (duration > 0) {
    setTimeout(dismiss, duration);
  }
}

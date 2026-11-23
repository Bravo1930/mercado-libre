/**
 * Sistema Accesible de Modales y Cuadros de Diálogo de Confirmación.
 * Maneja foco, cierre por ESC y clic fuera del diálogo.
 */

import { icons } from "../icons.js";

let activeModal = null;

export function openModal(titleOrOptions, contentArg = "", optionsArg = {}) {
  // Compatibilidad: las vistas llaman openModal("Título", contenidoHTML)
  // y otras openModal({ title, content, ... }). Se aceptan ambas formas.
  // Antes solo se aceptaba el objeto: con la llamada posicional el título
  // caía en "Ventana Modal" y el contenido quedaba vacío.
  const opts =
    typeof titleOrOptions === "string"
      ? { title: titleOrOptions, content: contentArg, ...optionsArg }
      : titleOrOptions || {};
  const {
    title = "Ventana Modal",
    content = "",
    footer = null,
    size = "md", // sm, md, lg, xl, full
    onConfirm = null,
    confirmText = "Aceptar",
    confirmDanger = false,
    cancelText = "Cancelar",
    onCancel = null,
  } = opts;
  closeModal();

  const widthClass = {
    sm: "max-w-md",
    md: "max-w-lg",
    lg: "max-w-2xl",
    xl: "max-w-4xl",
    full: "max-w-6xl",
  }[size] || "max-w-lg";

  const overlay = document.createElement("div");
  overlay.id = "app-modal-overlay";
  overlay.className = "fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fade-in";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");

  let footerHtml = footer;
  if (!footerHtml) {
    const confirmBtnClass = confirmDanger
      ? "bg-red-600 hover:bg-red-700 text-white"
      : "bg-blue-600 hover:bg-blue-700 text-white";

    footerHtml = `
      <div class="flex items-center justify-end space-x-3 pt-4 border-t border-slate-100">
        <button id="modal-cancel-btn" type="button" class="px-4 py-2.5 text-sm font-semibold text-slate-700 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-smooth">
          ${cancelText}
        </button>
        ${
          onConfirm
            ? `<button id="modal-confirm-btn" type="button" class="px-5 py-2.5 text-sm font-semibold rounded-lg shadow-sm transition-smooth flex items-center space-x-2 ${confirmBtnClass}">
                <span>${confirmText}</span>
              </button>`
            : ""
        }
      </div>
    `;
  }

  overlay.innerHTML = `
    <div class="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full ${widthClass} max-h-[90vh] flex flex-col overflow-hidden animate-fade-in">
      <div class="flex items-center justify-between px-6 py-4 border-b border-slate-100 bg-slate-50/50">
        <h3 class="text-lg font-bold text-slate-900">${title}</h3>
        <button id="modal-close-x" class="text-slate-400 hover:text-slate-600 p-1.5 rounded-lg hover:bg-slate-100 transition-smooth touch-target flex items-center justify-center" aria-label="Cerrar modal">
          ${icons.close("w-5 h-5")}
        </button>
      </div>
      <div class="p-6 overflow-y-auto flex-1 text-slate-700 text-sm">
        ${content}
      </div>
      ${footerHtml ? `<div class="px-6 py-4 bg-slate-50/50">${footerHtml}</div>` : ""}
    </div>
  `;

  document.body.appendChild(overlay);
  activeModal = overlay;
  document.body.style.overflow = "hidden";

  // Eventos de Cierre
  const closeBtn = overlay.querySelector("#modal-close-x");
  const cancelBtn = overlay.querySelector("#modal-cancel-btn");
  const confirmBtn = overlay.querySelector("#modal-confirm-btn");

  const closeHandler = () => {
    if (onCancel) onCancel();
    closeModal();
  };

  if (closeBtn) closeBtn.addEventListener("click", closeHandler);
  if (cancelBtn) cancelBtn.addEventListener("click", closeHandler);

  if (confirmBtn && onConfirm) {
    confirmBtn.addEventListener("click", async () => {
      confirmBtn.disabled = true;
      confirmBtn.innerHTML = `${icons.spinner("w-4 h-4")} <span>Procesando...</span>`;
      try {
        await onConfirm();
        closeModal();
      } catch (err) {
        confirmBtn.disabled = false;
        confirmBtn.innerHTML = `<span>${confirmText}</span>`;
      }
    });
  }

  // Clic en el backdrop
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) closeHandler();
  });

  // Tecla ESC
  const escHandler = (e) => {
    if (e.key === "Escape") {
      closeHandler();
      window.removeEventListener("keydown", escHandler);
    }
  };
  window.addEventListener("keydown", escHandler);

  return overlay;
}

export function closeModal() {
  if (activeModal) {
    activeModal.remove();
    activeModal = null;
    document.body.style.overflow = "";
  }
}

export function showConfirmDialog({
  title = "¿Estás seguro?",
  message = "Esta acción no se puede deshacer.",
  confirmText = "Confirmar",
  cancelText = "Cancelar",
  isDanger = false,
  onConfirm,
}) {
  return openModal({
    title,
    size: "sm",
    confirmText,
    cancelText,
    confirmDanger: isDanger,
    content: `
      <div class="flex items-start space-x-3.5">
        <div class="p-2.5 rounded-full ${isDanger ? 'bg-red-100 text-red-600' : 'bg-blue-100 text-blue-600'}">
          ${icons.alertTriangle("w-6 h-6")}
        </div>
        <div>
          <p class="text-sm text-slate-600 mt-1">${message}</p>
        </div>
      </div>
    `,
    onConfirm,
  });
}

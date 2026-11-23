/**
 * Vista de Inicio de Sesión, Registro de Organización y Recuperación de Contraseña.
 */

import { api } from "../api.js";
import { state } from "../state.js";
import { icons } from "../icons.js";
import { showToast } from "../components/toast.js";
import { openModal } from "../components/modal.js";

export function renderLoginView() {
  const container = document.createElement("div");
  container.className = "min-h-screen flex items-center justify-center p-4 sm:p-6 bg-slate-900";

  let activeTab = "login"; // 'login' | 'register'

  function update() {
    container.innerHTML = `
      <div class="w-full max-w-md bg-white rounded-3xl shadow-2xl border border-slate-800 p-8 sm:p-10 animate-fade-in">
        <!-- Logo y Título -->
        <div class="text-center mb-8">
          <div class="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-[#FFE600] shadow-lg mb-4">
            <svg class="w-8 h-8 text-[#2D3277]" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"></path>
            </svg>
          </div>
          <h1 class="text-2xl font-black text-slate-900 tracking-tight">ERP Mercado Libre México</h1>
          <p class="text-xs font-semibold text-slate-500 mt-1">Plataforma Empresarial Inteligente Multi-Empresa</p>
        </div>

        <!-- Pestañas Login / Registro -->
        <div class="flex p-1 mb-6 bg-slate-100 rounded-xl">
          <button id="tab-login" class="flex-1 py-2 text-xs font-bold rounded-lg transition-smooth ${activeTab === 'login' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-900'}">
            Iniciar Sesión
          </button>
          <button id="tab-register" class="flex-1 py-2 text-xs font-bold rounded-lg transition-smooth ${activeTab === 'register' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-900'}">
            Registrar Organización
          </button>
        </div>

        <div id="form-container"></div>
      </div>
    `;

    const formWrapper = container.querySelector("#form-container");

    if (activeTab === "login") {
      formWrapper.innerHTML = `
        <form id="login-form" class="space-y-4">
          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1">Correo Electrónico</label>
            <input 
              id="login-email" 
              type="email" 
              required 
              placeholder="director@tuempresa.com.mx"
              class="w-full px-4 py-2.5 text-sm bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:ring-2 focus:ring-blue-600 focus:outline-none transition-smooth"
            />
          </div>

          <div>
            <div class="flex items-center justify-between mb-1">
              <label class="block text-xs font-bold text-slate-700">Contraseña</label>
              <button id="btn-forgot-pwd" type="button" class="text-[11px] font-semibold text-blue-600 hover:text-blue-800 transition-smooth">
                ¿Olvidaste tu contraseña?
              </button>
            </div>
            <input 
              id="login-password" 
              type="password" 
              required 
              placeholder="••••••••"
              class="w-full px-4 py-2.5 text-sm bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:ring-2 focus:ring-blue-600 focus:outline-none transition-smooth"
            />
          </div>

          <div id="login-error-banner" class="hidden p-3 rounded-xl bg-red-50 border border-red-200 text-xs font-semibold text-red-700"></div>

          <button 
            id="btn-submit-login" 
            type="submit" 
            class="w-full py-3 px-4 bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold rounded-xl shadow-lg shadow-blue-600/30 transition-smooth flex items-center justify-center space-x-2 touch-target"
          >
            <span>Ingresar al Sistema</span>
          </button>
        </form>
      `;

      bindLoginForm(container);
    } else {
      formWrapper.innerHTML = `
        <form id="register-form" class="space-y-3.5">
          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1">Nombre de la Organización</label>
            <input id="reg-tenant-name" type="text" required placeholder="Grupo Comercial Alfa S.A." class="w-full px-3.5 py-2 text-sm bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:ring-2 focus:ring-blue-600 focus:outline-none" />
          </div>

          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1">Slug URL (Identificador)</label>
            <input id="reg-tenant-slug" type="text" required placeholder="grupo-alfa" class="w-full px-3.5 py-2 text-sm font-mono bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:ring-2 focus:ring-blue-600 focus:outline-none" />
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">Razón Social</label>
              <input id="reg-legal-name" type="text" required placeholder="Alfa de México S.A." class="w-full px-3.5 py-2 text-sm bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:ring-2 focus:ring-blue-600 focus:outline-none" />
            </div>
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1">RFC Mexicano</label>
              <input id="reg-rfc" type="text" required placeholder="AME180512XYZ" maxlength="13" class="w-full px-3.5 py-2 text-sm font-mono uppercase bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:ring-2 focus:ring-blue-600 focus:outline-none" />
            </div>
          </div>

          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1">Nombre Completo del Director</label>
            <input id="reg-admin-name" type="text" required placeholder="Carlos Mendoza" class="w-full px-3.5 py-2 text-sm bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:ring-2 focus:ring-blue-600 focus:outline-none" />
          </div>

          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1">Correo Electrónico Administrador</label>
            <input id="reg-admin-email" type="email" required placeholder="admin@grupoalfa.com" class="w-full px-3.5 py-2 text-sm bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:ring-2 focus:ring-blue-600 focus:outline-none" />
          </div>

          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1">Contraseña Segura (mín. 8 caracteres)</label>
            <input id="reg-admin-pwd" type="password" required minlength="8" placeholder="••••••••" class="w-full px-3.5 py-2 text-sm bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:ring-2 focus:ring-blue-600 focus:outline-none" />
          </div>

          <div id="reg-error-banner" class="hidden p-3 rounded-xl bg-red-50 border border-red-200 text-xs font-semibold text-red-700"></div>

          <button id="btn-submit-reg" type="submit" class="w-full py-3 px-4 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-bold rounded-xl shadow-lg shadow-emerald-600/30 transition-smooth flex items-center justify-center space-x-2 touch-target">
            <span>Crear Organización & Iniciar</span>
          </button>
        </form>
      `;

      bindRegisterForm(container);
    }

    // Tab Listeners
    container.querySelector("#tab-login").addEventListener("click", () => {
      activeTab = "login";
      update();
    });
    container.querySelector("#tab-register").addEventListener("click", () => {
      activeTab = "register";
      update();
    });
  }

  function bindLoginForm(root) {
    const form = root.querySelector("#login-form");
    const errorBanner = root.querySelector("#login-error-banner");
    const submitBtn = root.querySelector("#btn-submit-login");
    const forgotBtn = root.querySelector("#btn-forgot-pwd");

    if (forgotBtn) {
      forgotBtn.addEventListener("click", () => openForgotPasswordModal());
    }

    if (form) {
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        errorBanner.classList.add("hidden");
        submitBtn.disabled = true;
        submitBtn.innerHTML = `${icons.spinner("w-4 h-4")} <span>Autenticando...</span>`;

        const email = root.querySelector("#login-email").value.trim();
        const password = root.querySelector("#login-password").value;

        try {
          const res = await api.post("/auth/login", {
            email,
            password,
            device_info: `${navigator.platform || 'PC'} · ${navigator.userAgent.slice(0, 40)}`,
          });

          showToast(`¡Bienvenido de vuelta, ${res.user.full_name}!`, "success");
          state.setAuth(res.access_token, res.user, res.authorized_companies);
          state.setRoute("dashboard");
        } catch (err) {
          errorBanner.textContent = err.message;
          errorBanner.classList.remove("hidden");
        } finally {
          submitBtn.disabled = false;
          submitBtn.innerHTML = `<span>Ingresar al Sistema</span>`;
        }
      });
    }
  }

  function bindRegisterForm(root) {
    const form = root.querySelector("#register-form");
    const errorBanner = root.querySelector("#reg-error-banner");
    const submitBtn = root.querySelector("#btn-submit-reg");

    if (form) {
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        errorBanner.classList.add("hidden");
        submitBtn.disabled = true;
        submitBtn.innerHTML = `${icons.spinner("w-4 h-4")} <span>Creando Organización...</span>`;

        const payload = {
          tenant_name: root.querySelector("#reg-tenant-name").value.trim(),
          tenant_slug: root.querySelector("#reg-tenant-slug").value.trim().toLowerCase(),
          company_legal_name: root.querySelector("#reg-legal-name").value.trim(),
          company_rfc: root.querySelector("#reg-rfc").value.trim().toUpperCase(),
          admin_full_name: root.querySelector("#reg-admin-name").value.trim(),
          admin_email: root.querySelector("#reg-admin-email").value.trim(),
          admin_password: root.querySelector("#reg-admin-pwd").value,
        };

        try {
          await api.post("/auth/register-tenant", payload);
          showToast("Organización registrada exitosamente. Iniciando sesión...", "success");

          // Auto-login
          const res = await api.post("/auth/login", {
            email: payload.admin_email,
            password: payload.admin_password,
            device_info: "Registro Inicial",
          });

          state.setAuth(res.access_token, res.user, res.authorized_companies);
          state.setRoute("dashboard");
        } catch (err) {
          errorBanner.textContent = err.message;
          errorBanner.classList.remove("hidden");
          submitBtn.disabled = false;
          submitBtn.innerHTML = `<span>Crear Organización & Iniciar</span>`;
        }
      });
    }
  }

  function openForgotPasswordModal() {
    openModal({
      title: "Recuperación de Contraseña",
      size: "sm",
      content: `
        <div class="space-y-4">
          <p class="text-xs text-slate-600">
            Ingresa tu correo electrónico registrado y te enviaremos un token criptográfico de recuperación.
          </p>
          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1">Correo Electrónico</label>
            <input id="forgot-email-input" type="email" placeholder="usuario@empresa.com.mx" class="w-full px-3.5 py-2 text-sm border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-600 focus:outline-none" />
          </div>
          <div id="forgot-token-display" class="hidden p-3 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-900 font-mono break-all"></div>
        </div>
      `,
      confirmText: "Solicitar Token",
      onConfirm: async () => {
        const email = document.getElementById("forgot-email-input").value.trim();
        if (!email) throw new Error("Ingresa tu correo.");

        const res = await api.post("/auth/forgot-password", { email });
        showToast(res.message, "success");

        if (res.reset_token_dev) {
          openResetPasswordModal(res.reset_token_dev);
        }
      },
    });
  }

  function openResetPasswordModal(initialToken = "") {
    openModal({
      title: "Restablecer Contraseña",
      size: "sm",
      content: `
        <div class="space-y-4">
          <p class="text-xs text-slate-600">
            Ingresa el token de recuperación y define tu nueva contraseña segura.
          </p>
          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1">Token de Recuperación</label>
            <input id="reset-token-input" type="text" value="${initialToken}" class="w-full px-3.5 py-2 text-xs font-mono border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-600 focus:outline-none" />
          </div>
          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1">Nueva Contraseña (mín. 8 caracteres)</label>
            <input id="reset-new-pwd-input" type="password" placeholder="••••••••" minlength="8" class="w-full px-3.5 py-2 text-sm border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-600 focus:outline-none" />
          </div>
        </div>
      `,
      confirmText: "Actualizar Contraseña",
      onConfirm: async () => {
        const token = document.getElementById("reset-token-input").value.trim();
        const newPassword = document.getElementById("reset-new-pwd-input").value;
        if (!token || !newPassword) throw new Error("Completa todos los campos.");

        await api.post("/auth/reset-password", { token, new_password: newPassword });
        showToast("Contraseña restablecida exitosamente. Ingresa con tu nueva clave.", "success");
      },
    });
  }

  update();
  return container;
}


// Adaptador para app.js: la app espera renderLogin(contenedor) y descarta el
// valor de retorno; renderLoginView() no recibe argumentos y devuelve el elemento.
export function renderLogin(container) {
  const el = renderLoginView();
  if (container) container.appendChild(el);
  return el;
}

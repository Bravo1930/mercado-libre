/**
 * Cliente HTTP Centralizado para la API REST del ERP.
 * Inyecta tokens JWT, encabezado de aislamiento X-Company-ID y gestiona errores.
 */

import { state } from "./state.js";
import { showToast } from "./components/toast.js";

const BASE_URL = "/api/v1";

class ApiClient {
  async request(endpoint, options = {}) {
    const url = new URL(`${BASE_URL}${endpoint}`, window.location.origin);
    
    // Si hay parámetros query en options.params, agregarlos a la URL
    if (options.params) {
      Object.entries(options.params).forEach(([key, val]) => {
        if (val !== undefined && val !== null && val !== "") {
          url.searchParams.append(key, String(val));
        }
      });
    }

    const headers = {
      "Content-Type": "application/json",
      "Accept": "application/json",
      ...(options.headers || {}),
    };

    // Inyectar JWT si está autenticado
    if (state.token) {
      headers["Authorization"] = `Bearer ${state.token}`;
    }

    // Inyectar contexto de empresa activa
    const compId = state.currentCompany ? (state.currentCompany.id || state.currentCompany.company_id) : null;
    if (compId) {
      headers["X-Company-ID"] = compId;
    }

    try {
      const response = await fetch(url.toString(), {
        ...options,
        headers,
      });

      // Manejo de sesión expirada o token revocado
      if (response.status === 401 && endpoint !== "/auth/login") {
        showToast("Tu sesión ha expirado o ha sido revocada. Por favor ingresa nuevamente.", "warning");
        state.logout();
        throw new Error("UNAUTHORIZED");
      }

      // Si la respuesta no es 2xx, extraer mensaje estructurado de error
      if (!response.ok) {
        let errData;
        try {
          errData = await response.json();
        } catch {
          errData = { error: `Error del servidor HTTP ${response.status}` };
        }
        
        const message = errData.error || errData.message || errData.detail || "Error en la operación";
        throw new Error(message);
      }

      // 204 No Content
      if (response.status === 204) {
        return null;
      }

      return await response.json();
    } catch (err) {
      if (err.message !== "UNAUTHORIZED") {
        console.error(`[API ERROR] ${options.method || "GET"} ${endpoint}:`, err);
      }
      throw err;
    }
  }

  get(endpoint, params = {}, options = {}) {
    return this.request(endpoint, { method: "GET", params, ...options });
  }

  post(endpoint, body = {}, options = {}) {
    return this.request(endpoint, { method: "POST", body: JSON.stringify(body), ...options });
  }

  put(endpoint, body = {}, options = {}) {
    return this.request(endpoint, { method: "PUT", body: JSON.stringify(body), ...options });
  }

  patch(endpoint, body = {}, options = {}) {
    return this.request(endpoint, { method: "PATCH", body: JSON.stringify(body), ...options });
  }

  delete(endpoint, options = {}) {
    return this.request(endpoint, { method: "DELETE", ...options });
  }

  async upload(endpoint, formData, options = {}) {
    const url = new URL(`${BASE_URL}${endpoint}`, window.location.origin);
    const headers = { ...(options.headers || {}) };
    if (state.token) headers["Authorization"] = `Bearer ${state.token}`;
    const compId = state.currentCompany ? (state.currentCompany.id || state.currentCompany.company_id) : null;
    if (compId) headers["X-Company-ID"] = compId;

    try {
      const response = await fetch(url.toString(), {
        method: "POST",
        body: formData,
        headers,
      });

      if (!response.ok) {
        let errData;
        try {
          errData = await response.json();
        } catch {
          errData = { error: `Error HTTP ${response.status}` };
        }
        throw new Error(errData.error || errData.message || "Error al subir archivo");
      }
      return await response.json();
    } catch (err) {
      console.error(`[API UPLOAD ERROR] ${endpoint}:`, err);
      throw err;
    }
  }

  async downloadBlob(endpoint, options = {}) {
    const url = new URL(`${BASE_URL}${endpoint}`, window.location.origin);
    const headers = { ...(options.headers || {}) };
    if (state.token) headers["Authorization"] = `Bearer ${state.token}`;
    const compId = state.currentCompany ? (state.currentCompany.id || state.currentCompany.company_id) : null;
    if (compId) headers["X-Company-ID"] = compId;

    try {
      const response = await fetch(url.toString(), {
        method: "GET",
        headers,
      });

      if (!response.ok) {
        throw new Error(`Error descargando archivo (HTTP ${response.status})`);
      }
      return await response.blob();
    } catch (err) {
      console.error(`[API DOWNLOAD ERROR] ${endpoint}:`, err);
      throw err;
    }
  }
}

export const api = new ApiClient();

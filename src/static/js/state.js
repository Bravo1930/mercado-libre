/**
 * Gestor Central de Estado Reactivo de la Aplicación ERP.
 * Mantiene la sesión, empresa activa, roles, notificaciones y ruta actual.
 */

class AppState {
  constructor() {
    this.token = localStorage.getItem("erp_token") || null;
    this.user = JSON.parse(localStorage.getItem("erp_user") || "null");
    this.companies = JSON.parse(localStorage.getItem("erp_companies") || "[]");
    this.currentCompany = JSON.parse(localStorage.getItem("erp_current_company") || "null");
    this.currentRoute = window.location.hash.replace("#", "") || "dashboard";
    this.sidebarCollapsed = localStorage.getItem("erp_sidebar_collapsed") === "true";
    this.mobileMenuOpen = false;
    this.notifications = [];
    this.listeners = new Set();
  }

  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  notify(event, data) {
    for (const listener of this.listeners) {
      listener(event, data, this);
    }
  }

  setAuth(token, user, companies = []) {
    this.token = token;
    this.user = user;
    this.companies = companies;
    localStorage.setItem("erp_token", token);
    localStorage.setItem("erp_user", JSON.stringify(user));
    localStorage.setItem("erp_companies", JSON.stringify(companies));

    // Si no hay empresa activa seleccionada o la actual no está en la lista, seleccionar la primera
    if (companies.length > 0) {
      const match = companies.find(c => this.currentCompany && c.company_id === this.currentCompany.company_id);
      this.currentCompany = match || companies[0];
      localStorage.setItem("erp_current_company", JSON.stringify(this.currentCompany));
    } else {
      this.currentCompany = null;
      localStorage.removeItem("erp_current_company");
    }

    this.notify("AUTH_CHANGED", { authenticated: true, user: this.user });
  }

  setCompany(company) {
    this.currentCompany = company;
    localStorage.setItem("erp_current_company", JSON.stringify(company));
    this.notify("COMPANY_CHANGED", company);
  }

  setRoute(route) {
    this.currentRoute = route;
    window.location.hash = route;
    this.mobileMenuOpen = false;
    this.notify("ROUTE_CHANGED", route);
  }

  toggleSidebar() {
    this.sidebarCollapsed = !this.sidebarCollapsed;
    localStorage.setItem("erp_sidebar_collapsed", String(this.sidebarCollapsed));
    this.notify("SIDEBAR_TOGGLED", this.sidebarCollapsed);
  }

  toggleMobileMenu() {
    this.mobileMenuOpen = !this.mobileMenuOpen;
    this.notify("MOBILE_MENU_TOGGLED", this.mobileMenuOpen);
  }

  logout() {
    this.token = null;
    this.user = null;
    this.companies = [];
    this.currentCompany = null;
    localStorage.removeItem("erp_token");
    localStorage.removeItem("erp_user");
    localStorage.removeItem("erp_companies");
    localStorage.removeItem("erp_current_company");
    this.setRoute("login");
    this.notify("AUTH_CHANGED", { authenticated: false });
  }

  isAuthenticated() {
    return Boolean(this.token && this.user);
  }

  getActiveRole() {
    if (this.currentCompany && this.currentCompany.role) {
      return this.currentCompany.role;
    }
    return this.user ? this.user.role : "viewer";
  }
}

export const state = new AppState();

"""Rutas centrales de la API REST v1 del ERP."""

from fastapi import APIRouter

from src.api.v1.ai import router as ai_router
from src.api.v1.audit import router as audit_router
from src.api.v1.auth import router as auth_router
from src.api.v1.automation import router as automation_router
from src.api.v1.commercial import router as commercial_router
from src.api.v1.companies import router as companies_router
from src.api.v1.dashboard import router as dashboard_router
from src.api.v1.finances import router as finances_router
from src.api.v1.health import router as health_router
from src.api.v1.inventory import router as inventory_router
from src.api.v1.logistics import router as logistics_router
from src.api.v1.meli_accounts import router as meli_accounts_router
from src.api.v1.orders import router as orders_router
from src.api.v1.products import router as products_router
from src.api.v1.profitability import router as profitability_router
from src.api.v1.saas import router as saas_router
from src.api.v1.settings import router as settings_router
from src.api.v1.suppliers import router as suppliers_router
from src.api.v1.sync import router as sync_router
from src.api.v1.system_security import router as system_security_router
from src.api.v1.tabular import router as tabular_router
from src.api.v1.users import router as users_router
from src.api.v1.warehouses import router as warehouses_router
from src.api.v1.webhooks import router as webhooks_router

api_v1_router = APIRouter(prefix="/api/v1")

# Registro de routers modulares
api_v1_router.include_router(health_router)
api_v1_router.include_router(dashboard_router)
api_v1_router.include_router(ai_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(companies_router)
api_v1_router.include_router(users_router)
api_v1_router.include_router(meli_accounts_router)
api_v1_router.include_router(products_router)
api_v1_router.include_router(warehouses_router)
api_v1_router.include_router(inventory_router)
api_v1_router.include_router(orders_router)
api_v1_router.include_router(commercial_router)
api_v1_router.include_router(automation_router)
api_v1_router.include_router(logistics_router)
api_v1_router.include_router(finances_router)
api_v1_router.include_router(profitability_router)
api_v1_router.include_router(suppliers_router)
api_v1_router.include_router(tabular_router)
api_v1_router.include_router(settings_router)
api_v1_router.include_router(sync_router)
api_v1_router.include_router(audit_router)
api_v1_router.include_router(webhooks_router)
api_v1_router.include_router(system_security_router)
api_v1_router.include_router(saas_router)

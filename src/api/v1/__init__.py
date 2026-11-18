"""Rutas de la versión 1 de la API del ERP."""

from fastapi import APIRouter

from src.api.v1.auth import router as auth_router
from src.api.v1.health import router as health_router
from src.api.v1.webhooks import router as webhooks_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(health_router)
api_v1_router.include_router(webhooks_router)
api_v1_router.include_router(auth_router)

"""Esquemas Pydantic para Cuentas de Mercado Libre México, OAuth y Diagnósticos."""

from datetime import datetime
from typing import Any
import uuid
from pydantic import Field

from src.schemas.common import BaseSchema


class MeliAccountCreate(BaseSchema):
    company_id: uuid.UUID
    meli_user_id: int
    nickname: str
    access_token_plain: str
    refresh_token_plain: str
    expires_in_seconds: int = 21600


class MeliAccountReconnectRequest(BaseSchema):
    access_token_plain: str
    refresh_token_plain: str
    expires_in_seconds: int = 21600


class MeliOAuthUrlResponse(BaseSchema):
    auth_url: str
    app_id: str
    redirect_uri: str
    state: str


class MeliOAuthCallbackRequest(BaseSchema):
    code: str = Field(..., min_length=5, description="Authorization code devuelto por Mercado Libre")
    state: str | None = Field(None, description="Parámetro CSRF state enviado en el inicio del flujo")
    redirect_uri: str | None = Field(None, description="URI de redirección configurada en la App")


class MeliConnectionTestResponse(BaseSchema):
    status: str
    healthy: bool
    latency_ms: float
    meli_user_id: int | None = None
    nickname: str | None = None
    site_id: str | None = None
    token_expires_at: str | None = None
    rate_limit_remaining: int | None = None
    error: str | None = None


class MeliUpdateStockRequest(BaseSchema):
    available_quantity: int = Field(..., ge=0, description="Cantidad disponible a sincronizar en MeLi")
    variation_id: str | int | None = Field(None, description="ID de variante si la publicación tiene variaciones")


class MeliUpdatePriceRequest(BaseSchema):
    price: float = Field(..., gt=0, description="Nuevo precio de venta en MXN")
    variation_id: str | int | None = Field(None, description="ID de variante si la publicación tiene variaciones")


class MeliAccountResponse(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    meli_user_id: int
    nickname: str
    site_id: str
    token_expires_at: datetime
    is_active: bool
    sync_orders: bool
    sync_stock: bool
    sync_prices: bool
    created_at: datetime

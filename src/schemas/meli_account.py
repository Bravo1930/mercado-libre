"""Esquemas para Cuentas de Mercado Libre México."""

import uuid
from datetime import datetime
from pydantic import Field

from src.schemas.common import BaseSchema


class MeliAccountCreate(BaseSchema):
    company_id: uuid.UUID
    meli_user_id: int
    nickname: str
    access_token_plain: str
    refresh_token_plain: str
    expires_in_seconds: int = 21600


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

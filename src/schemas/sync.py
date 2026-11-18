"""Esquemas Pydantic para el Motor de Sincronización, Conciliación y Monitor MeLi."""

from datetime import datetime
from enum import Enum
from typing import Any
import uuid
from pydantic import Field

from src.schemas.common import BaseSchema


class SyncTopicEnum(str, Enum):
    """Tópicos oficiales de notificaciones de Mercado Libre México."""

    ORDERS_V2 = "orders_v2"
    PAYMENTS = "payments"
    ITEMS = "items"
    SHIPMENTS = "shipments"
    CLAIMS = "claims"
    PUBLIC_CANDIDATES = "public_candidates"
    PUBLIC_OFFERS = "public_offers"
    ITEMS_PRICES = "items_prices"


class SyncEventResponse(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID | None = None
    meli_account_id: uuid.UUID | None = None
    meli_event_id: str | None = None
    topic: str
    resource: str
    user_id: int
    attempts: int
    status: str
    retry_count: int
    max_retries: int
    error_message: str | None = None
    discrepancy_details: dict[str, Any] | None = None
    sent_at: datetime | None = None
    received_at: datetime
    processed_at: datetime | None = None


class SyncMonitorResponse(BaseSchema):
    last_sync_at: datetime | None = None
    total_received: int = 0
    total_processed: int = 0
    total_pending: int = 0
    total_failed: int = 0
    total_retried: int = 0
    discrepancies_detected: int = 0
    by_topic: dict[str, int] = Field(default_factory=dict)
    by_status: dict[str, int] = Field(default_factory=dict)


class SyncReconcileRequest(BaseSchema):
    meli_account_id: uuid.UUID | None = Field(None, description="Cuenta específica a conciliar, o None para todas")
    lookback_hours: int = Field(default=24, ge=1, le=168, description="Horas hacia atrás a inspeccionar en MeLi")


class SyncReconcileResponse(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    meli_account_id: uuid.UUID | None = None
    sync_type: str
    status: str
    orders_synced: int
    items_synced: int
    promotions_synced: int
    discrepancies_found: int
    started_at: datetime
    finished_at: datetime
    details: dict[str, Any] | None = None

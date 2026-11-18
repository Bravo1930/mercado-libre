"""Modelos de Eventos de Webhook, Colas de Sincronización y Conciliación Periódica."""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from src.models.base import GUID, Base, TimestampMixin


class SyncEvent(Base, TimestampMixin):
    """
    Registro persistente de eventos de webhooks y notificaciones Push de Mercado Libre.
    Asegura idempotencia, encolamiento, control de duplicados y reintentos.
    """

    __tablename__ = "sync_events"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    meli_account_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("meli_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Identificador único enviado por MeLi en el payload (_id)
    meli_event_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # Tópicos oficiales de Mercado Libre
    # orders_v2, payments, items, shipments, claims, public_candidates, public_offers, items_prices
    topic: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Recurso notificado (e.g. /orders/200000123456, /items/MLM123456)
    resource: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    application_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Payload completo enviado por Mercado Libre
    payload: Mapped[dict[str, Any]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), default=dict)

    # Estado del procesamiento: pending, processing, processed, failed, duplicate, ignored
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False, index=True)

    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Discrepancias o cambios detectados al procesar el recurso
    discrepancy_details: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )

    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_sync_events_company_status", "company_id", "status"),
        Index("ix_sync_events_topic_status", "topic", "status"),
        Index("ix_sync_events_res_user", "resource", "user_id"),
    )


class SyncReconciliationLog(Base, TimestampMixin):
    """
    Pista de auditoría de los ciclos de conciliación periódica.
    Recupera eventos perdidos y detecta discrepancias entre MeLi y el ERP.
    """

    __tablename__ = "sync_reconciliation_logs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meli_account_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("meli_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )

    sync_type: Mapped[str] = mapped_column(
        String(50), default="periodic_reconciliation", nullable=False
    )  # periodic_reconciliation, manual, webhook_recovery

    status: Mapped[str] = mapped_column(String(30), default="completed", nullable=False)  # completed, failed

    orders_synced: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_synced: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    promotions_synced: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    discrepancies_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    details: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )

    __table_args__ = (
        Index("ix_reconciliation_company_date", "company_id", "started_at"),
    )

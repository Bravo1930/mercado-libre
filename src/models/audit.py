"""Modelo de Registro de Auditoría Centralizado (Audit Log)."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import GUID, Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.tenant import Company


class AuditLog(Base, TimestampMixin):
    """Pista inmutable de auditoría para trazabilidad de acciones críticas en el ERP."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=True, index=True)
    action: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # CREATE, UPDATE, DELETE, SYNC_MELI, STOCK_OVERRIDE, PRICE_CHANGE
    entity_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # Product, Order, Inventory
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    changes_json: Mapped[str] = mapped_column(Text, nullable=True)  # Diff de cambios en formato JSON
    ip_address: Mapped[str] = mapped_column(String(50), nullable=True)

    company: Mapped["Company"] = relationship("Company")

    __table_args__ = (
        Index("ix_audit_logs_company_action_date", "company_id", "action", "created_at"),
    )

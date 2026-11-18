"""Modelo de Configuraciones personalizables por Empresa."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import GUID, Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.tenant import Company


class CompanySetting(Base, TimestampMixin):
    """Configuraciones clave-valor y parámetros del sistema por empresa."""

    __tablename__ = "company_settings"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=True)

    company: Mapped["Company"] = relationship("Company", back_populates="settings")

    __table_args__ = (
        Index("ix_company_settings_key", "company_id", "key", unique=True),
    )

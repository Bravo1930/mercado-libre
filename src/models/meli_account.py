"""Modelo de Cuentas de Vendedor oficiales de Mercado Libre México."""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import GUID, Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.order import Order
    from src.models.product import ProductSKU
    from src.models.promotion import Promotion
    from src.models.tenant import Company


class MeliAccount(Base, TimestampMixin):
    """Cuenta de vendedor oficial de Mercado Libre México (Seller Account)."""

    __tablename__ = "meli_accounts"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meli_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    nickname: Mapped[str] = mapped_column(String(100), nullable=False)
    site_id: Mapped[str] = mapped_column(String(10), default="MLM", nullable=False)

    # Tokens encriptados con AES-256 (Fernet)
    access_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_orders: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_prices: Mapped[bool] = mapped_column(Boolean, default=True)

    company: Mapped["Company"] = relationship("Company", back_populates="meli_accounts")
    skus: Mapped[list["ProductSKU"]] = relationship(
        "ProductSKU", back_populates="meli_account", cascade="all, delete-orphan"
    )
    orders: Mapped[list["Order"]] = relationship(
        "Order", back_populates="meli_account", cascade="all, delete-orphan"
    )
    promotions: Mapped[list["Promotion"]] = relationship(
        "Promotion", back_populates="meli_account", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_meli_accounts_company_active", "company_id", "is_active"),
    )

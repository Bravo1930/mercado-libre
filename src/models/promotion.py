"""Modelos de Campañas Promocionales y Descuentos en Mercado Libre."""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import GUID, Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.meli_account import MeliAccount


class Promotion(Base, TimestampMixin):
    """Campaña de descuentos o deal oficial de Mercado Libre México."""

    __tablename__ = "promotions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    meli_account_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("meli_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meli_promotion_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    promotion_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # LIGHTNING (Oferta Relámpago), DEAL, SMART, VOLUME_DISCOUNT
    status: Mapped[str] = mapped_column(String(30), default="started", index=True)  # started, pending, finished
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finish_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    meli_account: Mapped["MeliAccount"] = relationship("MeliAccount", back_populates="promotions")
    items: Mapped[list["PromotionItem"]] = relationship(
        "PromotionItem", back_populates="promotion", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_promotions_account_promo", "meli_account_id", "meli_promotion_id", unique=True),
    )


class PromotionItem(Base, TimestampMixin):
    """Publicación inscrita en una promoción activa con su precio y descuento."""

    __tablename__ = "promotion_items"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    promotion_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("promotions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meli_item_id: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    regular_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    promotional_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    discount_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    cofunded_by_meli_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=0.0)  # Descuento absorbido por MeLi
    max_units_allowed: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    promotion: Mapped["Promotion"] = relationship("Promotion", back_populates="items")

"""Modelos de Organizaciones (Tenants) y Empresas (Companies / Multi-RFC)."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import GUID, Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.meli_account import MeliAccount
    from src.models.product import Product
    from src.models.user import CompanyUser, User
    from src.models.warehouse import Warehouse
    from src.models.supplier import Supplier
    from src.models.setting import CompanySetting


class Tenant(Base, TimestampMixin):
    """Cliente u Organización suscriptora del servicio ERP / SaaS."""

    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    plan_tier: Mapped[str] = mapped_column(String(50), default="standard")  # standard, pro, enterprise
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    companies: Mapped[list["Company"]] = relationship(
        "Company", back_populates="tenant", cascade="all, delete-orphan"
    )
    users: Mapped[list["User"]] = relationship(
        "User", back_populates="tenant", cascade="all, delete-orphan"
    )


class Company(Base, TimestampMixin):
    """Empresa con personalidad jurídica propia y RFC en México."""

    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    rfc: Mapped[str] = mapped_column(String(13), index=True, nullable=False)
    fiscal_regime: Mapped[str] = mapped_column(String(100), nullable=True)  # e.g. 626 RESICO, 601 General
    email: Mapped[str] = mapped_column(String(255), nullable=True)
    phone: Mapped[str] = mapped_column(String(30), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relaciones
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="companies")
    meli_accounts: Mapped[list["MeliAccount"]] = relationship(
        "MeliAccount", back_populates="company", cascade="all, delete-orphan"
    )
    products: Mapped[list["Product"]] = relationship(
        "Product", back_populates="company", cascade="all, delete-orphan"
    )
    warehouses: Mapped[list["Warehouse"]] = relationship(
        "Warehouse", back_populates="company", cascade="all, delete-orphan"
    )
    suppliers: Mapped[list["Supplier"]] = relationship(
        "Supplier", back_populates="company", cascade="all, delete-orphan"
    )
    settings: Mapped[list["CompanySetting"]] = relationship(
        "CompanySetting", back_populates="company", cascade="all, delete-orphan"
    )
    user_access: Mapped[list["CompanyUser"]] = relationship(
        "CompanyUser", back_populates="company", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_companies_tenant_rfc", "tenant_id", "rfc", unique=True),
    )

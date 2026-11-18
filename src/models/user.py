"""Modelos de Usuarios, Roles y Permisos Multi-Empresa."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import GUID, Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.tenant import Tenant


class User(Base, TimestampMixin):
    """Usuario del sistema ERP con control de acceso basado en roles (RBAC)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="operator")  # admin, manager, operator, viewer
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="users")
    company_access: Mapped[list["CompanyUser"]] = relationship(
        "CompanyUser", back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_users_tenant_role", "tenant_id", "role"),
    )


class CompanyUser(Base, TimestampMixin):
    """Tabla de asociación: Asigna usuarios a empresas específicas dentro de su tenant."""

    __tablename__ = "company_users"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_override: Mapped[str] = mapped_column(String(50), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="company_access")

    __table_args__ = (
        Index("ix_company_users_unique", "user_id", "company_id", unique=True),
    )

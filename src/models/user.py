"""Modelos de Usuarios, Roles, Permisos, Sesiones y Recuperación de Contraseña."""

from datetime import datetime, timezone
import json
from typing import TYPE_CHECKING, Any
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import GUID, Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.tenant import Company, Tenant


class User(Base, TimestampMixin):
    """Usuario del sistema ERP con control de acceso basado en roles (RBAC)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    role: Mapped[str] = mapped_column(
        String(50), default="operator", nullable=False
    )  # platform_owner, saas_admin, company_admin, director, operator, warehouse_manager, financial_manager, viewer
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant: Mapped["Tenant | None"] = relationship("Tenant", back_populates="users")
    company_access: Mapped[list["CompanyUser"]] = relationship(
        "CompanyUser", back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["UserSession"]] = relationship(
        "UserSession", back_populates="user", cascade="all, delete-orphan"
    )
    reset_tokens: Mapped[list["PasswordResetToken"]] = relationship(
        "PasswordResetToken", back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_users_tenant_role", "tenant_id", "role"),
    )


class CompanyUser(Base, TimestampMixin):
    """Tabla de asociación: Asigna usuarios a empresas específicas con rol y restricciones modulares."""

    __tablename__ = "company_users"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(
        String(50), default="operator", nullable=False
    )  # company_admin, director, operator, warehouse_manager, financial_manager, viewer
    role_override: Mapped[str | None] = mapped_column(String(50), nullable=True)
    permissions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    restricted_modules_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="company_access")
    company: Mapped["Company"] = relationship("Company", back_populates="user_access")

    @property
    def permissions(self) -> list[str]:
        """Obtiene la lista deserializada de permisos personalizados."""
        if not self.permissions_json:
            return []
        try:
            return json.loads(self.permissions_json)
        except Exception:
            return []

    @permissions.setter
    def permissions(self, val: list[str] | None) -> None:
        self.permissions_json = json.dumps(val) if val else None

    @property
    def restricted_modules(self) -> list[str]:
        """Obtiene la lista deserializada de módulos restringidos para este usuario."""
        if not self.restricted_modules_json:
            return []
        try:
            return json.loads(self.restricted_modules_json)
        except Exception:
            return []

    @restricted_modules.setter
    def restricted_modules(self, val: list[str] | None) -> None:
        self.restricted_modules_json = json.dumps(val) if val else None

    __table_args__ = (
        Index("ix_company_users_unique", "user_id", "company_id", unique=True),
        Index("ix_company_users_lookup", "company_id", "user_id", "is_active"),
    )


class UserSession(Base, TimestampMixin):
    """Gestión de sesiones activas de usuario con trazabilidad de IP, dispositivo y revocación."""

    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_jti: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    device_info: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="sessions")

    __table_args__ = (
        Index("ix_user_sessions_active", "user_id", "is_revoked", "expires_at"),
    )


class PasswordResetToken(Base, TimestampMixin):
    """Tokens criptográficos de un solo uso para recuperación de contraseña."""

    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    user: Mapped["User"] = relationship("User", back_populates="reset_tokens")

    __table_args__ = (
        Index("ix_pwd_reset_active", "token_hash", "is_used", "expires_at"),
    )

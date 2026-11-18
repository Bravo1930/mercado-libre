"""Esquemas de validación para Tenants y Empresas (Multi-RFC)."""

import uuid
from datetime import datetime
from pydantic import Field, field_validator

from src.schemas.common import RFC_REGEX, BaseSchema


class TenantCreate(BaseSchema):
    name: str = Field(..., min_length=3, max_length=200)
    slug: str = Field(..., min_length=3, max_length=100)
    plan_tier: str = Field(default="standard")


class TenantResponse(BaseSchema):
    id: uuid.UUID
    name: str
    slug: str
    plan_tier: str
    is_active: bool
    created_at: datetime


class CompanyCreate(BaseSchema):
    tenant_id: uuid.UUID
    legal_name: str = Field(..., min_length=3, max_length=255)
    rfc: str = Field(..., description="RFC mexicano con homoclave")
    fiscal_regime: str | None = Field(default="626", description="Clave de régimen fiscal SAT")
    email: str | None = Field(default=None)
    phone: str | None = Field(default=None)

    @field_validator("rfc")
    @classmethod
    def validate_rfc_format(cls, v: str) -> str:
        clean_rfc = v.strip().upper()
        if not RFC_REGEX.match(clean_rfc):
            raise ValueError(f"El RFC '{clean_rfc}' no cumple con el formato oficial del SAT (12 o 13 caracteres).")
        return clean_rfc


class CompanyUpdate(BaseSchema):
    legal_name: str | None = None
    fiscal_regime: str | None = None
    email: str | None = None
    phone: str | None = None
    is_active: bool | None = None


class CompanyResponse(BaseSchema):
    id: uuid.UUID
    tenant_id: uuid.UUID
    legal_name: str
    rfc: str
    fiscal_regime: str | None
    email: str | None
    phone: str | None
    is_active: bool
    created_at: datetime

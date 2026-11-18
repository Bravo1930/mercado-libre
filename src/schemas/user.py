"""Esquemas de validación para Usuarios, Autenticación y Tokens JWT."""

import uuid
from datetime import datetime
from pydantic import EmailStr, Field

from src.schemas.common import BaseSchema


class UserCreate(BaseSchema):
    tenant_id: uuid.UUID
    email: EmailStr
    password: str = Field(..., min_length=8, description="Contraseña de mínimo 8 caracteres")
    full_name: str = Field(..., min_length=2, max_length=150)
    role: str = Field(default="operator")  # admin, manager, operator, viewer


class UserLogin(BaseSchema):
    email: EmailStr
    password: str


class TokenResponse(BaseSchema):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user_id: uuid.UUID
    role: str


class UserResponse(BaseSchema):
    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime

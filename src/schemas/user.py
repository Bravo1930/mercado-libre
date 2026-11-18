"""Esquemas de validación para Usuarios, Autenticación, Sesiones y Multi-Empresa."""

from datetime import datetime
from typing import Any
import uuid
from pydantic import EmailStr, Field, field_validator

from src.core.permissions import RoleEnum
from src.schemas.common import RFC_REGEX, BaseSchema


class TenantRegisterRequest(BaseSchema):
    """Solicitud de registro inicial de Tenant, Empresa y Propietario / Administrador."""

    tenant_name: str = Field(..., min_length=2, max_length=200, description="Nombre de la organización o grupo")
    tenant_slug: str = Field(..., min_length=2, max_length=100, pattern=r"^[a-z0-9\-]+$", description="Slug identificador URL")
    company_legal_name: str = Field(..., min_length=3, max_length=255, description="Razón Social o Nombre Legal de la empresa")
    company_rfc: str = Field(..., description="RFC oficial de México")
    admin_email: EmailStr = Field(..., description="Correo de acceso del administrador")
    admin_password: str = Field(..., min_length=8, description="Contraseña segura (mínimo 8 caracteres)")
    admin_full_name: str = Field(..., min_length=2, max_length=150, description="Nombre completo del administrador")

    @field_validator("company_rfc")
    @classmethod
    def validate_rfc_format(cls, v: str) -> str:
        rfc = v.strip().upper()
        if not RFC_REGEX.match(rfc):
            raise ValueError(f"El RFC '{rfc}' no cumple con el formato oficial del SAT (12 o 13 caracteres alfanuméricos).")
        return rfc


class TenantRegisterResponse(BaseSchema):
    """Respuesta de registro exitoso de Tenant."""

    tenant_id: uuid.UUID
    tenant_name: str
    tenant_slug: str
    company_id: uuid.UUID
    company_legal_name: str
    company_rfc: str
    user_id: uuid.UUID
    email: str
    role: str
    created_at: datetime


class UserLoginRequest(BaseSchema):
    """Credenciales de inicio de sesión."""

    email: EmailStr
    password: str = Field(..., min_length=1)
    device_info: str | None = Field(None, max_length=100, description="Identificador del navegador o dispositivo")


class CompanyBriefResponse(BaseSchema):
    """Resumen de empresa asignada a un usuario."""

    company_id: uuid.UUID
    legal_name: str
    rfc: str
    role: str
    permissions: list[str] = Field(default_factory=list)
    restricted_modules: list[str] = Field(default_factory=list)


class UserProfileResponse(BaseSchema):
    """Perfil público del usuario autenticado."""

    id: uuid.UUID
    tenant_id: uuid.UUID | None
    email: str
    full_name: str
    role: str
    is_active: bool
    is_superuser: bool
    last_login_at: datetime | None = None
    created_at: datetime


class LoginResponse(BaseSchema):
    """Respuesta de inicio de sesión con JWT y empresas autorizadas."""

    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user: UserProfileResponse
    authorized_companies: list[CompanyBriefResponse] = Field(default_factory=list)


class ForgotPasswordRequest(BaseSchema):
    """Solicitud de recuperación de contraseña."""

    email: EmailStr


class ForgotPasswordResponse(BaseSchema):
    """Respuesta a solicitud de recuperación."""

    status: str = "success"
    message: str
    reset_token_dev: str | None = None  # Disponible en testing/dev para facilitar pruebas


class ResetPasswordRequest(BaseSchema):
    """Restablecimiento de contraseña con token."""

    token: str = Field(..., min_length=10, description="Token de recuperación recibido")
    new_password: str = Field(..., min_length=8, description="Nueva contraseña segura")


class ResetPasswordResponse(BaseSchema):
    """Confirmación de restablecimiento."""

    status: str = "success"
    message: str


class UserSessionResponse(BaseSchema):
    """Detalle de una sesión activa de usuario."""

    id: uuid.UUID
    ip_address: str | None
    user_agent: str | None
    device_info: str | None
    is_revoked: bool
    is_current: bool = False
    expires_at: datetime
    last_activity_at: datetime
    created_at: datetime


class CompanyUserAssignRequest(BaseSchema):
    """Asignación o vinculación de un usuario a una empresa."""

    user_id: uuid.UUID
    role: RoleEnum = Field(default=RoleEnum.OPERATOR, description="Rol asignado en la empresa")
    permissions: list[str] | None = Field(None, description="Permisos personalizados adicionales")
    restricted_modules: list[str] | None = Field(None, description="Módulos expresamente bloqueados")


class CompanyUserUpdateRequest(BaseSchema):
    """Actualización de membresía o permisos de un usuario en la empresa."""

    role: RoleEnum | None = None
    permissions: list[str] | None = None
    restricted_modules: list[str] | None = None
    is_active: bool | None = None


class CompanyUserResponse(BaseSchema):
    """Respuesta de asociación de usuario a empresa."""

    id: uuid.UUID
    user_id: uuid.UUID
    company_id: uuid.UUID
    email: str | None = None
    full_name: str | None = None
    role: str
    permissions: list[str] = Field(default_factory=list)
    restricted_modules: list[str] = Field(default_factory=list)
    is_active: bool
    created_at: datetime


class UserCreate(BaseSchema):
    """Creación de nuevo usuario dentro de un Tenant."""

    tenant_id: uuid.UUID | None = None
    email: EmailStr
    password: str = Field(..., min_length=8, description="Contraseña de mínimo 8 caracteres")
    full_name: str = Field(..., min_length=2, max_length=150)
    role: RoleEnum = Field(default=RoleEnum.OPERATOR, description="Rol primario del usuario")


class UserUpdate(BaseSchema):
    """Actualización de datos básicos de usuario."""

    full_name: str | None = Field(None, min_length=2, max_length=150)
    role: RoleEnum | None = None
    is_active: bool | None = None


class UserResponse(BaseSchema):
    """Respuesta de usuario."""

    id: uuid.UUID
    tenant_id: uuid.UUID | None
    email: str
    full_name: str
    role: str
    is_active: bool
    is_superuser: bool
    last_login_at: datetime | None = None
    created_at: datetime


# Compatibilidad con esquemas anteriores
UserLogin = UserLoginRequest
TokenResponse = LoginResponse

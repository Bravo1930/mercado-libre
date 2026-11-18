"""API REST para Autenticación, Registro, Sesiones, Recuperación y OAuth 2.0 MeLi."""

from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import Any
from urllib.parse import urlencode
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.audit import record_audit_event
from src.core.auth_context import UserContext, get_current_user
from src.core.config import get_settings
from src.core.database import get_db
from src.core.exceptions import (
    AppException,
    AuthenticationFailedException,
    EntityAlreadyExistsException,
    EntityNotFoundException,
)
from src.core.logging import get_logger
from src.core.permissions import RoleEnum
from src.core.security import create_access_token, encrypt_token, hash_password, verify_password
from src.models.audit import AuditLog
from src.models.tenant import Company, Tenant
from src.models.user import CompanyUser, PasswordResetToken, User, UserSession
from src.schemas.user import (
    CompanyBriefResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    TenantRegisterRequest,
    TenantRegisterResponse,
    UserProfileResponse,
    UserLoginRequest,
    UserSessionResponse,
)

logger = get_logger("auth")
router = APIRouter(prefix="/auth", tags=["Autenticación & Sesiones"])


@router.post("/register-tenant", response_model=TenantRegisterResponse, status_code=status.HTTP_201_CREATED)
async def register_tenant(
    payload: TenantRegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Registra una nueva Organización (Tenant) con su Empresa fiscal y Usuario Administrador inicial.
    Flujo transaccional atómico de onboarding para SaaS.
    """
    # 1. Validar unicidad de slug del tenant y correo del admin
    stmt_slug = select(Tenant).where(Tenant.slug == payload.tenant_slug)
    if (await session.execute(stmt_slug)).scalar_one_or_none():
        raise EntityAlreadyExistsException("Organización", "slug", payload.tenant_slug)

    stmt_email = select(User).where(User.email == payload.admin_email)
    if (await session.execute(stmt_email)).scalar_one_or_none():
        raise EntityAlreadyExistsException("Usuario", "email", payload.admin_email)

    # 2. Crear Tenant
    tenant = Tenant(
        name=payload.tenant_name,
        slug=payload.tenant_slug,
        plan_tier="standard",
        is_active=True,
    )
    session.add(tenant)
    await session.flush()

    # 3. Crear Empresa fiscal asociada
    company = Company(
        tenant_id=tenant.id,
        legal_name=payload.company_legal_name,
        rfc=payload.company_rfc,
        is_active=True,
    )
    session.add(company)
    await session.flush()

    # 4. Crear Usuario Administrador de la empresa
    user = User(
        tenant_id=tenant.id,
        email=payload.admin_email,
        password_hash=hash_password(payload.admin_password),
        full_name=payload.admin_full_name,
        role=RoleEnum.COMPANY_ADMIN.value,
        is_active=True,
        is_superuser=False,
    )
    session.add(user)
    await session.flush()

    # 5. Asignar al usuario como Administrador de la Empresa en CompanyUser
    company_user = CompanyUser(
        user_id=user.id,
        company_id=company.id,
        role=RoleEnum.COMPANY_ADMIN.value,
        is_active=True,
    )
    session.add(company_user)
    await session.flush()

    # 6. Registrar evento de auditoría
    client_ip = request.client.host if request.client else None
    await record_audit_event(
        session=session,
        action="REGISTER_TENANT",
        entity_name="Tenant",
        entity_id=str(tenant.id),
        company_id=company.id,
        user_id=user.id,
        changes={
            "tenant_name": tenant.name,
            "company_rfc": company.rfc,
            "admin_email": user.email,
        },
        ip_address=client_ip,
    )

    return {
        "tenant_id": tenant.id,
        "tenant_name": tenant.name,
        "tenant_slug": tenant.slug,
        "company_id": company.id,
        "company_legal_name": company.legal_name,
        "company_rfc": company.rfc,
        "user_id": user.id,
        "email": user.email,
        "role": user.role,
        "created_at": tenant.created_at,
    }


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: UserLoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Autentica al usuario, genera un identificador de sesión único (jti), registra la sesión
    activa en base de datos y emite el JWT con los claims del usuario y sus empresas autorizadas.
    """
    settings = get_settings()

    # 1. Buscar usuario por email con sus empresas asignadas
    stmt = (
        select(User)
        .where(User.email == payload.email)
        .options(
            selectinload(User.company_access).selectinload(CompanyUser.company)
        )
    )
    user = (await session.execute(stmt)).scalar_one_or_none()

    if not user or not verify_password(payload.password, user.password_hash):
        logger.warning(f"Intento de inicio de sesión fallido para email='{payload.email}'")
        raise AuthenticationFailedException("Correo electrónico o contraseña incorrectos.")

    if not user.is_active:
        logger.warning(f"Intento de inicio de sesión en cuenta inactiva: '{payload.email}'")
        raise AuthenticationFailedException("La cuenta de usuario se encuentra suspendida o inactiva.")

    # 2. Generar JTI único para la sesión
    jti = str(uuid.uuid4())
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    device_info = payload.device_info or (user_agent[:100] if user_agent else "Navegador Web")

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    user_session = UserSession(
        user_id=user.id,
        token_jti=jti,
        ip_address=client_ip,
        user_agent=user_agent[:255] if user_agent else None,
        device_info=device_info,
        is_revoked=False,
        expires_at=expires_at,
        last_activity_at=datetime.now(timezone.utc),
    )
    session.add(user_session)

    # Actualizar última fecha de login
    user.last_login_at = datetime.now(timezone.utc)
    await session.flush()

    # 3. Construir lista de empresas autorizadas
    authorized_companies = []
    for access in user.company_access:
        if access.is_active and access.company and access.company.is_active:
            authorized_companies.append(
                CompanyBriefResponse(
                    company_id=access.company_id,
                    legal_name=access.company.legal_name,
                    rfc=access.company.rfc,
                    role=access.role,
                    permissions=access.permissions,
                    restricted_modules=access.restricted_modules,
                )
            )

    # 4. Crear Token JWT
    token_claims = {
        "sub": str(user.id),
        "jti": jti,
        "email": user.email,
        "role": user.role,
        "tenant_id": str(user.tenant_id) if user.tenant_id else None,
    }
    access_token = create_access_token(
        data=token_claims,
        expires_delta=timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    # 5. Registro de auditoría
    await record_audit_event(
        session=session,
        action="LOGIN_SUCCESS",
        entity_name="UserSession",
        entity_id=jti,
        user_id=user.id,
        changes={"ip": client_ip, "device": device_info},
        ip_address=client_ip,
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in_minutes": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
        "user": user,
        "authorized_companies": authorized_companies,
    }


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    request: Request,
    user_ctx: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Cierra la sesión actual revocando inmediatamente el identificador de sesión (jti) en base de datos.
    Cualquier uso subsecuente del JWT será rechazado de inmediato.
    """
    user_ctx.session.is_revoked = True
    await session.flush()

    client_ip = request.client.host if request.client else None
    await record_audit_event(
        session=session,
        action="LOGOUT",
        entity_name="UserSession",
        entity_id=user_ctx.token_jti,
        user_id=user_ctx.id,
        changes={"revoked_jti": user_ctx.token_jti},
        ip_address=client_ip,
    )
    return {"status": "success", "message": "Sesión finalizada exitosamente."}


@router.post("/logout-all", status_code=status.HTTP_200_OK)
async def logout_all_devices(
    request: Request,
    user_ctx: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Cierra y revoca todas las sesiones activas del usuario en todos los dispositivos.
    """
    stmt = (
        update(UserSession)
        .where(UserSession.user_id == user_ctx.id, UserSession.is_revoked == False)
        .values(is_revoked=True)
    )
    await session.execute(stmt)
    await session.flush()

    client_ip = request.client.host if request.client else None
    await record_audit_event(
        session=session,
        action="LOGOUT_ALL_DEVICES",
        entity_name="UserSession",
        entity_id=str(user_ctx.id),
        user_id=user_ctx.id,
        changes={"user_id": str(user_ctx.id)},
        ip_address=client_ip,
    )
    return {"status": "success", "message": "Todas las sesiones activas han sido revocadas."}


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Genera un token criptográfico seguro de un solo uso para recuperación de contraseña.
    Almacena únicamente el hash SHA-256 del token para prevenir fugas de credenciales.
    """
    settings = get_settings()
    stmt = select(User).where(User.email == payload.email)
    user = (await session.execute(stmt)).scalar_one_or_none()

    generic_msg = "Si el correo electrónico se encuentra registrado, se han generado las instrucciones de recuperación."
    client_ip = request.client.host if request.client else None

    if not user or not user.is_active:
        return {"status": "success", "message": generic_msg, "reset_token_dev": None}

    # Generar token aleatorio criptográficamente seguro
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    reset_token_entry = PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
        is_used=False,
    )
    session.add(reset_token_entry)
    await session.flush()

    await record_audit_event(
        session=session,
        action="PASSWORD_RESET_REQUESTED",
        entity_name="PasswordResetToken",
        entity_id=str(reset_token_entry.id),
        user_id=user.id,
        changes={"email": user.email},
        ip_address=client_ip,
    )

    # En entorno testing o local no productivo, retornamos el token en la respuesta para facilitar pruebas automatizadas
    reset_token_dev = raw_token if settings.ENVIRONMENT in {"development", "testing"} else None

    return {
        "status": "success",
        "message": generic_msg,
        "reset_token_dev": reset_token_dev,
    }


@router.post("/reset-password", response_model=ResetPasswordResponse)
async def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Valida el token de recuperación, actualiza la contraseña con hash bcrypt y
    revoca automáticamente todas las sesiones previas del usuario por seguridad.
    """
    token_hash = hashlib.sha256(payload.token.encode("utf-8")).hexdigest()
    now_utc = datetime.now(timezone.utc)

    stmt = select(PasswordResetToken).where(
        PasswordResetToken.token_hash == token_hash,
        PasswordResetToken.is_used == False,
    )
    reset_token = (await session.execute(stmt)).scalar_one_or_none()

    if not reset_token:
        raise AppException(
            "El token de recuperación es inválido o ya fue utilizado.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_RESET_TOKEN",
        )

    exp = reset_token.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < now_utc:
        raise AppException(
            "El token de recuperación ha expirado.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="EXPIRED_RESET_TOKEN",
        )

    # Cargar usuario y actualizar contraseña
    stmt_user = select(User).where(User.id == reset_token.user_id)
    user = (await session.execute(stmt_user)).scalar_one_or_none()
    if not user:
        raise EntityNotFoundException("Usuario", "id", str(reset_token.user_id))

    user.password_hash = hash_password(payload.new_password)
    reset_token.is_used = True

    # Revocar todas las sesiones existentes de forma preventiva
    stmt_revoke = (
        update(UserSession)
        .where(UserSession.user_id == user.id, UserSession.is_revoked == False)
        .values(is_revoked=True)
    )
    await session.execute(stmt_revoke)
    await session.flush()

    client_ip = request.client.host if request.client else None
    await record_audit_event(
        session=session,
        action="PASSWORD_RESET_COMPLETED",
        entity_name="User",
        entity_id=str(user.id),
        user_id=user.id,
        changes={"sessions_revoked": True},
        ip_address=client_ip,
    )

    return {
        "status": "success",
        "message": "Contraseña actualizada exitosamente. Todas las sesiones activas han sido cerradas por seguridad.",
    }


@router.get("/me", response_model=UserProfileResponse)
async def get_my_profile(
    user_ctx: UserContext = Depends(get_current_user),
) -> User:
    """Retorna el perfil del usuario autenticado."""
    return user_ctx.user


@router.get("/my-companies", response_model=list[CompanyBriefResponse])
async def list_my_companies(
    user_ctx: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[CompanyBriefResponse]:
    """Retorna las empresas a las que el usuario tiene acceso operativo junto con su rol en cada una."""
    stmt = (
        select(CompanyUser)
        .where(CompanyUser.user_id == user_ctx.id, CompanyUser.is_active == True)
        .options(selectinload(CompanyUser.company))
    )
    accesses = (await session.execute(stmt)).scalars().all()

    results = []
    for access in accesses:
        if access.company and access.company.is_active:
            results.append(
                CompanyBriefResponse(
                    company_id=access.company_id,
                    legal_name=access.company.legal_name,
                    rfc=access.company.rfc,
                    role=access.role,
                    permissions=access.permissions,
                    restricted_modules=access.restricted_modules,
                )
            )
    return results


@router.get("/sessions", response_model=list[UserSessionResponse])
async def list_my_sessions(
    user_ctx: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Consulta la lista de sesiones registradas del usuario con indicador de sesión actual."""
    stmt = (
        select(UserSession)
        .where(UserSession.user_id == user_ctx.id)
        .order_by(UserSession.created_at.desc())
    )
    user_sessions = (await session.execute(stmt)).scalars().all()

    results = []
    for s in user_sessions:
        results.append({
            "id": s.id,
            "ip_address": s.ip_address,
            "user_agent": s.user_agent,
            "device_info": s.device_info,
            "is_revoked": s.is_revoked,
            "is_current": (s.token_jti == user_ctx.token_jti),
            "expires_at": s.expires_at,
            "last_activity_at": s.last_activity_at,
            "created_at": s.created_at,
        })
    return results


@router.delete("/sessions/{session_id}", status_code=status.HTTP_200_OK)
async def revoke_session(
    session_id: uuid.UUID,
    user_ctx: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Revoca una sesión específica de un dispositivo."""
    stmt = select(UserSession).where(UserSession.id == session_id, UserSession.user_id == user_ctx.id)
    target_session = (await session.execute(stmt)).scalar_one_or_none()

    if not target_session:
        raise EntityNotFoundException("Sesión", "id", str(session_id))

    target_session.is_revoked = True
    await session.flush()

    return {"status": "success", "message": f"Sesión '{session_id}' revocada exitosamente."}


# =========================================================================
# RUTAS OFICIALES OAUTH 2.0 MERCADO LIBRE MÉXICO
# =========================================================================

@router.get("/meli/authorize-url")
def get_meli_authorization_url(company_id: str = Query(..., description="UUID de la empresa vinculante")) -> dict[str, str]:
    """Genera el enlace oficial de Mercado Libre México para vincular una cuenta de vendedor."""
    settings = get_settings()
    params = {
        "response_type": "code",
        "client_id": settings.MELI_APP_ID,
        "redirect_uri": settings.MELI_REDIRECT_URI,
        "state": company_id,
    }
    url = f"{settings.MELI_AUTH_URL}?{urlencode(params)}"
    return {
        "authorization_url": url,
        "site_id": settings.MELI_SITE_ID,
        "redirect_uri": settings.MELI_REDIRECT_URI,
    }


@router.get("/meli/callback")
async def meli_oauth_callback(
    code: str = Query(..., description="Código temporal de autorización emitido por MeLi"),
    state: str = Query(..., description="Estado / ID de la empresa vinculante"),
) -> dict[str, Any]:
    """Callback oficial que recibe el código de autorización y lo canjea por Access y Refresh Token."""
    settings = get_settings()
    logger.info(f"Procesando callback de autorización para empresa ID='{state}'")

    token_url = f"{settings.MELI_API_BASE_URL}/oauth/token"
    payload = {
        "grant_type": "authorization_code",
        "client_id": settings.MELI_APP_ID,
        "client_secret": settings.MELI_CLIENT_SECRET,
        "code": code,
        "redirect_uri": settings.MELI_REDIRECT_URI,
    }

    if settings.ENVIRONMENT != "production" and settings.MELI_APP_ID == "dev_mock_app_id":
        return {
            "status": "mock_success",
            "message": "Entorno local de desarrollo: flujo OAuth verificado.",
            "company_id": state,
            "mock_user_id": 123456789,
            "expires_in_hours": 6,
        }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(token_url, data=payload)
        if response.status_code != 200:
            logger.error(f"Error al canjear código en Mercado Libre: {response.text}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Fallo en la autenticación con la API de Mercado Libre.",
            )
        data = response.json()

    access_token_enc = encrypt_token(data["access_token"])
    refresh_token_enc = encrypt_token(data["refresh_token"])

    return {
        "status": "success",
        "user_id": data["user_id"],
        "token_type": data.get("token_type", "bearer"),
        "expires_in": data["expires_in"],
        "scope": data.get("scope"),
        "encrypted": True,
    }

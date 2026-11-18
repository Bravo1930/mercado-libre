"""Contexto de Autenticación, Verificación de Sesiones y Protección Multi-Empresa."""

from datetime import datetime, timezone
from typing import Annotated, Any
import uuid

from fastapi import Depends, Header, Path, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.database import get_db
from src.core.exceptions import (
    AppException,
    AuthenticationFailedException,
    EntityNotFoundException,
    PermissionDeniedException,
)
from src.core.logging import get_logger
from src.core.permissions import (
    PRIVATE_COMPANY_MODULES,
    ActionEnum,
    ModuleEnum,
    RoleEnum,
    has_module_permission,
)
from src.core.quota_enforcement import QuotaEnforcementService
from src.core.security import decode_access_token
from src.core.session_security import SessionAnomalyDetector
from src.models.tenant import Company
from src.models.user import CompanyUser, User, UserSession
from src.services.security_monitoring import SecurityEventType, SecurityMonitoringService, SecurityThreatLevel

logger = get_logger("auth_context")
http_bearer = HTTPBearer(auto_error=False)


class UserContext:
    """Información del usuario autenticado y su sesión activa."""

    def __init__(self, user: User, session: UserSession, token_jti: str):
        self.user = user
        self.session = session
        self.token_jti = token_jti

    @property
    def id(self) -> uuid.UUID:
        return self.user.id

    @property
    def email(self) -> str:
        return self.user.email

    @property
    def role(self) -> str:
        return self.user.role

    @property
    def is_superuser(self) -> bool:
        return self.user.is_superuser


class CompanyContext:
    """Contexto operativo validado de la empresa activa para la solicitud en curso."""

    def __init__(
        self,
        user_ctx: UserContext,
        company: Company,
        company_user: CompanyUser | None,
        effective_role: str,
    ):
        self.user_ctx = user_ctx
        self.user = user_ctx.user
        self.company = company
        self.company_user = company_user
        self.effective_role = effective_role

    @property
    def company_id(self) -> uuid.UUID:
        return self.company.id

    @property
    def user_id(self) -> uuid.UUID:
        return self.user.id

    @property
    def tenant_id(self) -> uuid.UUID:
        return self.company.tenant_id


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(http_bearer)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> UserContext:
    """
    Extrae, valida y verifica el JWT y la sesión activa en base de datos.
    Rechaza tokens si la sesión fue cerrada o revocada.
    """
    if not credentials:
        raise AuthenticationFailedException("Token de autenticación no proporcionado.")

    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload:
        raise AuthenticationFailedException("Token de autenticación inválido o expirado.")

    user_id_str = payload.get("sub")
    jti = payload.get("jti")

    if not user_id_str or not jti:
        raise AuthenticationFailedException("Estructura de token JWT inválida (sub o jti ausente).")

    try:
        user_uuid = uuid.UUID(user_id_str)
    except ValueError:
        raise AuthenticationFailedException("Identificador de usuario inválido en token.")

    # 1. Verificar sesión activa en base de datos (revocación y expiración en tiempo real)
    stmt_session = select(UserSession).where(UserSession.token_jti == jti)
    user_session = (await session.execute(stmt_session)).scalar_one_or_none()

    if not user_session:
        raise AuthenticationFailedException("Sesión no encontrada o inválida.")

    if user_session.is_revoked:
        raise AuthenticationFailedException("La sesión ha sido revocada o cerrada.")

    now_utc = datetime.now(timezone.utc)
    exp = user_session.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < now_utc:
        raise AuthenticationFailedException("La sesión ha expirado.")

    # 2. Cargar usuario con sus accesos a empresas
    stmt_user = (
        select(User)
        .where(User.id == user_uuid)
        .options(selectinload(User.company_access))
    )
    user = (await session.execute(stmt_user)).scalar_one_or_none()

    if not user or not user.is_active:
        raise AuthenticationFailedException("Usuario no encontrado o inactivo.")

    # 3. Detección de secuestro de sesión y robo de tokens (Session Anomaly Matching)
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    is_suspicious, anomalies = SessionAnomalyDetector.evaluate_session_consistency(user_session, client_ip, user_agent)
    if is_suspicious:
        await SecurityMonitoringService.record_security_incident(
            session=session,
            event_type=SecurityEventType.SESSION_HIJACK_ALERT,
            severity=SecurityThreatLevel.CRITICAL,
            description=f"Posible secuestro de sesión para usuario {user.email}: {', '.join(anomalies)}",
            source_ip=client_ip,
            user_id=user.id,
            metadata={"jti": jti, "anomalies": anomalies},
        )

    # Actualizar marca de tiempo de última actividad de forma ligera
    user_session.last_activity_at = now_utc

    return UserContext(user=user, session=user_session, token_jti=jti)


def require_company_permission(module: ModuleEnum, action: ActionEnum = ActionEnum.READ):
    """
    Fábrica de dependencias de autorización backend estricta.
    
    REGLAS DE SEGURIDAD ESTRICTAS:
    1. No confía en identificadores del frontend: valida que el usuario pertenezca a la empresa en BD.
    2. Aisla estrictamente los datos entre empresas.
    3. Protege documentos privados (finanzas, pedidos, costos SAT) de administradores globales si no son miembros.
    4. Valida permisos por rol, permisos personalizados y listas de módulos restringidos.
    """

    async def _permission_dependency(
        request: Request,
        user_ctx: Annotated[UserContext, Depends(get_current_user)],
        db_session: Annotated[AsyncSession, Depends(get_db)],
        x_company_id: Annotated[str | None, Header(alias="X-Company-ID")] = None,
        company_id_query: Annotated[uuid.UUID | None, Query(alias="company_id")] = None,
    ) -> CompanyContext:
        target_company_id: uuid.UUID | None = None

        # 1. Determinar el company_id desde Header, Query o Path
        if x_company_id:
            try:
                target_company_id = uuid.UUID(x_company_id)
            except ValueError:
                raise AppException(
                    "El encabezado 'X-Company-ID' debe ser un UUID válido.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                    error_code="INVALID_COMPANY_ID",
                )
        elif company_id_query:
            target_company_id = company_id_query
        elif "company_id" in request.path_params:
            try:
                target_company_id = uuid.UUID(request.path_params["company_id"])
            except ValueError:
                raise AppException(
                    "El parámetro de ruta 'company_id' debe ser un UUID válido.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                    error_code="INVALID_COMPANY_ID",
                )
        else:
            # Si no se envió identificador, intentar resolver si el usuario pertenece a una única empresa
            active_accesses = [a for a in user_ctx.user.company_access if a.is_active]
            if len(active_accesses) == 1:
                target_company_id = active_accesses[0].company_id
            elif len(active_accesses) > 1:
                raise AppException(
                    "El usuario pertenece a múltiples empresas. Debe especificar la empresa activa en el encabezado 'X-Company-ID'.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                    error_code="AMBIGUOUS_COMPANY_CONTEXT",
                )
            elif user_ctx.role not in {RoleEnum.PLATFORM_OWNER.value, RoleEnum.SAAS_ADMIN.value}:
                raise PermissionDeniedException("El usuario no tiene empresas asignadas activas.")

        # 2. Verificar existencia de la empresa en la base de datos
        if not target_company_id:
            raise AppException(
                "Debe proporcionar el identificador de empresa mediante 'X-Company-ID' o parámetro 'company_id'.",
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="MISSING_COMPANY_CONTEXT",
            )

        stmt_company = select(Company).where(Company.id == target_company_id)
        company = (await db_session.execute(stmt_company)).scalar_one_or_none()
        if not company:
            raise EntityNotFoundException("Empresa", "id", str(target_company_id))

        if not company.is_active:
            raise PermissionDeniedException("La empresa solicitada se encuentra inactiva.")

        # 3. Buscar asignación del usuario a esta empresa específica (CompanyUser)
        stmt_cu = select(CompanyUser).where(
            CompanyUser.company_id == target_company_id,
            CompanyUser.user_id == user_ctx.user.id,
            CompanyUser.is_active == True,
        )
        company_user = (await db_session.execute(stmt_cu)).scalar_one_or_none()

        is_platform_admin = user_ctx.role in {RoleEnum.PLATFORM_OWNER.value, RoleEnum.SAAS_ADMIN.value}
        is_private_module = module.value in PRIVATE_COMPANY_MODULES

        # REGLA CRÍTICA DE SEGURIDAD:
        # Los administradores globales NO tienen acceso irrestricto a documentos privados sin membresía
        if is_platform_admin and is_private_module and not company_user:
            logger.warning(
                f"Bloqueado intento de acceso de admin global {user_ctx.email} a documento privado "
                f"en empresa {target_company_id} para módulo {module.value}"
            )
            raise PermissionDeniedException(
                "Acceso restringido: Los administradores de plataforma requieren asignación explícita "
                "para consultar documentos privados, facturación y rentabilidad de la empresa."
            )

        # Si no es admin global y no tiene asignación en la empresa -> DENEGADO (Prevención de Acceso Cruzado)
        if not company_user and not is_platform_admin:
            logger.warning(
                f"Intento de acceso cruzado denegado: Usuario {user_ctx.email} "
                f"intentó acceder a datos de la empresa {target_company_id}"
            )
            await SecurityMonitoringService.record_security_incident(
                session=db_session,
                event_type=SecurityEventType.HORIZONTAL_ACCESS_ATTEMPT,
                severity=SecurityThreatLevel.HIGH,
                description=f"Usuario '{user_ctx.email}' intentó acceder sin autorización a datos de empresa ajena '{target_company_id}'",
                source_ip=request.client.host if request.client else None,
                company_id=target_company_id,
                user_id=user_ctx.id,
            )
            raise PermissionDeniedException("Acceso denegado: No perteneces a la empresa solicitada.")

        # 4. Determinar el rol efectivo y verificar permisos
        effective_role = company_user.role if company_user else user_ctx.role
        custom_perms = company_user.permissions if company_user else None
        restricted_mods = company_user.restricted_modules if company_user else None

        allowed = has_module_permission(
            role=effective_role,
            module=module.value,
            action=action.value,
            custom_permissions=custom_perms,
            restricted_modules=restricted_mods,
        )

        if not allowed:
            logger.warning(
                f"Permiso denegado: Usuario {user_ctx.email} con rol '{effective_role}' "
                f"intentó '{action.value}' en módulo '{module.value}' para empresa {target_company_id}"
            )
            await SecurityMonitoringService.record_security_incident(
                session=db_session,
                event_type=SecurityEventType.PRIVILEGE_ESCALATION,
                severity=SecurityThreatLevel.HIGH,
                description=f"Usuario '{user_ctx.email}' con rol '{effective_role}' intentó acción no permitida '{action.value}' en módulo '{module.value}'",
                source_ip=request.client.host if request.client else None,
                company_id=target_company_id,
                user_id=user_ctx.id,
                metadata={"attempted_action": action.value, "module": module.value, "role": effective_role},
            )
            raise PermissionDeniedException(
                f"Permiso denegado: El rol '{effective_role}' no cuenta con autorización "
                f"para la acción '{action.value}' en el módulo '{module.value}'."
            )

        # 5. Enforzamiento de Suscripción SaaS (bloqueo de escritura en clientes suspendidos o expirados)
        if action in [ActionEnum.CREATE, ActionEnum.UPDATE, ActionEnum.DELETE]:
            await QuotaEnforcementService.check_subscription_status(db_session, company.tenant_id)

        return CompanyContext(
            user_ctx=user_ctx,
            company=company,
            company_user=company_user,
            effective_role=effective_role,
        )

    return _permission_dependency


def require_platform_admin(
    user_ctx: Annotated[UserContext, Depends(get_current_user)],
) -> UserContext:
    """Restringe el acceso exclusivamente a platform_owner o saas_admin."""
    if user_ctx.role not in {RoleEnum.PLATFORM_OWNER.value, RoleEnum.SAAS_ADMIN.value}:
        raise PermissionDeniedException(
            "Acceso denegado: Se requiere rol de Propietario de Plataforma o Administrador SaaS."
        )
    return user_ctx

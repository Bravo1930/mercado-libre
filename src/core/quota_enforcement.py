"""Motor de Control de Cuotas, Enforzamiento de Límites y Feature Flags de Suscripción SaaS."""

from datetime import datetime, timezone
from typing import Any
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AppException
from src.core.logging import get_logger
from src.models.meli_account import MeliAccount
from src.models.saas import SaaSPlan, SaaSSubscription
from src.models.tenant import Company
from src.models.user import User

logger = get_logger("quota_enforcement")


class QuotaExceededException(AppException):
    """Lanzada cuando un cliente intenta exceder los límites operativos autorizados en su plan."""

    def __init__(self, resource_name: str, current_count: int, max_allowed: int, plan_name: str):
        msg = (
            f"Límite de cuota alcanzado para '{resource_name}': Actualmente tiene {current_count} de "
            f"{max_allowed} permitidos en el Plan '{plan_name}'. Actualice su suscripción para ampliar su capacidad."
        )
        super().__init__(
            message=msg,
            status_code=402,  # Payment Required
            code="QUOTA_EXCEEDED",
            details={
                "resource": resource_name,
                "current": current_count,
                "limit": max_allowed,
                "plan": plan_name,
            },
        )


class SubscriptionSuspendedException(AppException):
    """Lanzada cuando un cliente con suscripción suspendida o vencida intenta realizar operaciones de escritura."""

    def __init__(self, status: str, reason: str | None = None):
        msg = (
            f"El acceso a este módulo se encuentra restringido debido a que la suscripción de la organización está '{status}'. "
            f"{f'Motivo: {reason}. ' if reason else ''}Por favor regularice su pago en el portal de suscripciones."
        )
        super().__init__(
            message=msg,
            status_code=402,
            code="SUBSCRIPTION_INACTIVE",
            details={"subscription_status": status, "reason": reason},
        )


class FeatureNotIncludedException(AppException):
    """Lanzada cuando se intenta usar una característica no contemplada en el plan contratado."""

    def __init__(self, feature_name: str, required_plan: str = "Profesional"):
        msg = (
            f"La funcionalidad '{feature_name}' no está incluida en su plan actual. "
            f"Requiere actualizar al Plan {required_plan} o superior."
        )
        super().__init__(
            message=msg,
            status_code=403,
            code="FEATURE_NOT_INCLUDED",
            details={"feature": feature_name, "required_plan": required_plan},
        )


class QuotaEnforcementService:
    """Validador en tiempo real de cuotas, límites de procesamiento y licencias SaaS."""

    @classmethod
    async def get_subscription_with_plan(
        cls, session: AsyncSession, tenant_id: uuid.UUID
    ) -> tuple[SaaSSubscription | None, SaaSPlan | None]:
        """Recupera la suscripción activa y la definición del plan para un Tenant."""
        stmt = (
            select(SaaSSubscription, SaaSPlan)
            .join(SaaSPlan, SaaSSubscription.plan_id == SaaSPlan.id)
            .where(SaaSSubscription.tenant_id == tenant_id)
        )
        res = (await session.execute(stmt)).first()
        if not res:
            return None, None
        return res[0], res[1]

    @classmethod
    async def check_subscription_status(cls, session: AsyncSession, tenant_id: uuid.UUID) -> SaaSSubscription:
        """
        Verifica que la suscripción esté activa o en periodo de prueba vigente.
        Bloquea operaciones de mutación si está suspendida, expirada o cancelada.
        """
        sub, plan = await cls.get_subscription_with_plan(session, tenant_id)
        if not sub:
            # Si no tiene suscripción formal creada (compatibilidad legacy), permitir
            return None

        now_utc = datetime.now(timezone.utc)

        # Si está suspendida
        if sub.status == "suspended":
            raise SubscriptionSuspendedException(sub.status, sub.suspension_reason)

        # Si está cancelada
        if sub.status == "cancelled":
            if sub.current_period_end and sub.current_period_end < now_utc:
                raise SubscriptionSuspendedException("cancelled", "El periodo de servicio cancelado ha expirado.")

        # Si está en trial pero ya expiró
        if sub.status == "trialing" and sub.trial_ends_at:
            t_end = sub.trial_ends_at
            if t_end.tzinfo is None:
                t_end = t_end.replace(tzinfo=timezone.utc)
            if t_end < now_utc:
                sub.status = "expired"
                await session.flush()
                raise SubscriptionSuspendedException("expired", "El periodo de prueba gratuita de 14 días ha concluido.")

        return sub

    @classmethod
    async def check_user_limit(cls, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        """Verifica que el alta de un nuevo usuario no exceda el límite del plan."""
        sub, plan = await cls.get_subscription_with_plan(session, tenant_id)
        if not sub or not plan or plan.max_users == -1:
            return

        stmt_count = select(func.count(User.id)).where(User.tenant_id == tenant_id, User.is_active == True)
        current_users = (await session.execute(stmt_count)).scalar() or 0

        if current_users >= plan.max_users:
            raise QuotaExceededException("Usuarios Permitidos", current_users, plan.max_users, plan.name)

    @classmethod
    async def check_meli_accounts_limit(cls, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        """Verifica que la vinculación de cuentas de Mercado Libre no exceda el límite del plan."""
        sub, plan = await cls.get_subscription_with_plan(session, tenant_id)
        if not sub or not plan or plan.max_meli_accounts == -1:
            return

        stmt_count = (
            select(func.count(MeliAccount.id))
            .join(Company, MeliAccount.company_id == Company.id)
            .where(Company.tenant_id == tenant_id, MeliAccount.is_active == True)
        )
        current_accounts = (await session.execute(stmt_count)).scalar() or 0

        if current_accounts >= plan.max_meli_accounts:
            raise QuotaExceededException("Cuentas de Mercado Libre", current_accounts, plan.max_meli_accounts, plan.name)

    @classmethod
    async def check_feature_permission(
        cls, session: AsyncSession, tenant_id: uuid.UUID, feature_code: str
    ) -> None:
        """
        Verifica si la característica avanzada solicitada está habilitada en el plan del cliente:
        - 'automation_engine': Motor de automatizaciones empresariales (ECA)
        - 'ai_assistant': Asistente de inteligencia artificial comercial
        - 'advanced_logistics': Etiquetas térmicas y trazabilidad avanzada
        """
        sub, plan = await cls.get_subscription_with_plan(session, tenant_id)
        if not sub or not plan:
            return

        if feature_code == "automation_engine" and not plan.has_automation_engine:
            raise FeatureNotIncludedException("Motor de Automatizaciones Empresariales (ECA)", "Profesional")

        if feature_code == "ai_assistant" and not plan.has_ai_assistant:
            raise FeatureNotIncludedException("Asistente Comercial de Inteligencia Artificial", "Profesional")

        if feature_code == "advanced_logistics" and not plan.has_advanced_logistics:
            raise FeatureNotIncludedException("Logística Avanzada y Etiquetas Térmicas", "Básico")

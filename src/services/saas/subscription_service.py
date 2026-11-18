"""Servicio Central de Gestión SaaS, Suscripciones, Planes, Facturación y Métricas."""

from datetime import datetime, timedelta, timezone
import json
from typing import Any
import uuid

from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.audit import record_audit_event
from src.core.exceptions import AppException, EntityAlreadyExistsException, EntityNotFoundException, ValidationException
from src.core.logging import get_logger
from src.core.permissions import RoleEnum
from src.core.security import hash_password
from src.models.meli_account import MeliAccount
from src.models.saas import SaaSInvoice, SaaSPlan, SaaSPayment, SaaSSubscription, SaaSUsageRecord
from src.models.tenant import Company, Tenant
from src.models.user import CompanyUser, User

logger = get_logger("saas_service")


class SaaSSubscriptionService:
    """
    Gestor integral de comercialización SaaS, monetización, ciclo de vida de clientes,
    planes comerciales, cuotas, facturación y panel de control ejecutivo.
    """

    @classmethod
    async def initialize_default_plans(cls, session: AsyncSession) -> list[SaaSPlan]:
        """
        Siembra o actualiza los tres planes canónicos del SaaS:
        1. Básico (Startups y micro-vendedores).
        2. Profesional (Vendedores en crecimiento y pymes).
        3. Empresarial (Grandes marcas, alta escala y cotización personalizada).
        """
        plans_data = [
            {
                "code": "basic",
                "name": "Básico",
                "description": "Ideal para vendedores individuales o emprendimientos en Mercado Libre que inician su profesionalización.",
                "monthly_price_mxn": 499.00,
                "annual_price_mxn": 4990.00,  # 2 meses de descuento
                "is_custom_pricing": False,
                "trial_days": 14,
                "max_users": 3,
                "max_meli_accounts": 1,
                "max_storage_mb": 1024,  # 1 GB
                "max_monthly_orders": 1000,
                "max_monthly_syncs": 5000,
                "has_automation_engine": False,
                "has_ai_assistant": False,
                "has_advanced_logistics": True,
                "has_priority_support": False,
                "features_json": json.dumps([
                    "Hasta 3 usuarios operativos",
                    "1 cuenta de Mercado Libre México",
                    "1,000 pedidos procesados por mes",
                    "1 GB de almacenamiento de etiquetas y reportes",
                    "Generación de etiquetas térmicas PDF y ZPL",
                    "Centro de ventas y control de stock básico",
                    "Soporte por correo electrónico",
                ]),
                "sort_order": 1,
            },
            {
                "code": "pro",
                "name": "Profesional",
                "description": "Para empresas y distribuidores con múltiples cuentas, alto volumen y necesidad de automatización e IA.",
                "monthly_price_mxn": 1499.00,
                "annual_price_mxn": 14990.00,
                "is_custom_pricing": False,
                "trial_days": 14,
                "max_users": 10,
                "max_meli_accounts": 5,
                "max_storage_mb": 10240,  # 10 GB
                "max_monthly_orders": 15000,
                "max_monthly_syncs": 50000,
                "has_automation_engine": True,
                "has_ai_assistant": True,
                "has_advanced_logistics": True,
                "has_priority_support": True,
                "features_json": json.dumps([
                    "Hasta 10 usuarios operativos con roles avanzados",
                    "Hasta 5 cuentas de Mercado Libre vinculadas",
                    "15,000 pedidos procesados por mes",
                    "10 GB de almacenamiento seguro en la nube",
                    "Motor de Automatización Empresarial (ECA)",
                    "Asistente Comercial de Inteligencia Artificial",
                    "Administrador de precios dinámicos y promociones",
                    "Módulo financiero completo y conciliación MeLi",
                    "Soporte prioritario y WhatsApp corporativo",
                ]),
                "sort_order": 2,
            },
            {
                "code": "enterprise",
                "name": "Empresarial",
                "description": "Para grandes marcas, distribuidores oficiales y corporativos con requerimientos a la medida y SLA garantizado.",
                "monthly_price_mxn": 3999.00,
                "annual_price_mxn": 39990.00,
                "is_custom_pricing": True,  # Sujeto a análisis comercial y cotización a medida
                "trial_days": 30,
                "max_users": -1,  # Ilimitado
                "max_meli_accounts": -1,  # Ilimitado
                "max_storage_mb": 102400,  # 100 GB
                "max_monthly_orders": -1,  # Ilimitado
                "max_monthly_syncs": -1,  # Ilimitado
                "has_automation_engine": True,
                "has_ai_assistant": True,
                "has_advanced_logistics": True,
                "has_priority_support": True,
                "features_json": json.dumps([
                    "Usuarios y sucursales ilimitados",
                    "Cuentas de Mercado Libre ilimitadas",
                    "Procesamiento y sincronización sin límites",
                    "100 GB+ de almacenamiento dedicado",
                    "Cotización personalizada según análisis comercial",
                    "Respaldos diarios con retención extendida",
                    "Gerente de cuenta dedicado y SLA 99.9% garantizado",
                    "Desarrollo e integraciones a la medida",
                ]),
                "sort_order": 3,
            },
        ]

        created_plans = []
        for pdata in plans_data:
            stmt = select(SaaSPlan).where(SaaSPlan.code == pdata["code"])
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if not existing:
                plan = SaaSPlan(**pdata)
                session.add(plan)
                created_plans.append(plan)
            else:
                for k, v in pdata.items():
                    setattr(existing, k, v)
                created_plans.append(existing)

        await session.flush()
        return created_plans

    @classmethod
    async def get_plans(cls, session: AsyncSession) -> list[SaaSPlan]:
        """Consulta el catálogo de planes comerciales activos ordenados."""
        stmt = select(SaaSPlan).where(SaaSPlan.is_active == True).order_by(SaaSPlan.sort_order.asc())
        plans = (await session.execute(stmt)).scalars().all()
        if not plans:
            plans = await cls.initialize_default_plans(session)
        return list(plans)

    @classmethod
    async def get_plan_by_code(cls, session: AsyncSession, plan_code: str) -> SaaSPlan:
        """Obtiene un plan específico por su código."""
        stmt = select(SaaSPlan).where(SaaSPlan.code == plan_code)
        plan = (await session.execute(stmt)).scalar_one_or_none()
        if not plan:
            # Si no existe, inicializar y reintentar
            await cls.initialize_default_plans(session)
            plan = (await session.execute(stmt)).scalar_one_or_none()
        if not plan:
            raise EntityNotFoundException("Plan SaaS", "code", plan_code)
        return plan

    @classmethod
    async def register_client(cls, session: AsyncSession, payload: Any) -> dict[str, Any]:
        """
        Alta completa de un nuevo cliente SaaS (Organización, Empresa fiscal, Admin y Suscripción Trial).
        Garantiza aislamiento absoluto entre clientes y asignación de periodo de prueba de 14 días.
        """
        # 1. Validar unicidad de slug del tenant y correo del admin
        stmt_slug = select(Tenant).where(Tenant.slug == payload.tenant_slug)
        if (await session.execute(stmt_slug)).scalar_one_or_none():
            raise EntityAlreadyExistsException("Organización", "slug", payload.tenant_slug)

        stmt_email = select(User).where(User.email == payload.admin_email)
        if (await session.execute(stmt_email)).scalar_one_or_none():
            raise EntityAlreadyExistsException("Usuario", "email", payload.admin_email)

        # 2. Obtener plan solicitado
        plan = await cls.get_plan_by_code(session, payload.plan_code)

        # 3. Crear Tenant
        tenant = Tenant(
            name=payload.tenant_name,
            slug=payload.tenant_slug,
            plan_tier=plan.code,
            is_active=True,
        )
        session.add(tenant)
        await session.flush()

        # 4. Crear Empresa fiscal inicial asociada
        company = Company(
            tenant_id=tenant.id,
            legal_name=payload.company_legal_name,
            rfc=payload.company_rfc.upper().strip(),
            is_active=True,
        )
        session.add(company)
        await session.flush()

        # 5. Crear Usuario Administrador de la Organización
        user = User(
            tenant_id=tenant.id,
            email=payload.admin_email.lower().strip(),
            password_hash=hash_password(payload.admin_password),
            full_name=payload.admin_full_name,
            role=RoleEnum.COMPANY_ADMIN.value,
            is_active=True,
            is_superuser=False,
        )
        session.add(user)
        await session.flush()

        # 6. Asignar usuario como administrador de la empresa en CompanyUser
        company_user = CompanyUser(
            user_id=user.id,
            company_id=company.id,
            role=RoleEnum.COMPANY_ADMIN.value,
            is_active=True,
        )
        session.add(company_user)
        await session.flush()

        # 7. Crear Suscripción SaaS en estado 'trialing'
        now_utc = datetime.now(timezone.utc)
        trial_end = now_utc + timedelta(days=plan.trial_days)

        subscription = SaaSSubscription(
            tenant_id=tenant.id,
            plan_id=plan.id,
            status="trialing",
            billing_cycle=payload.billing_cycle,
            current_period_start=now_utc,
            current_period_end=trial_end,
            trial_ends_at=trial_end,
            auto_renew=True,
            payment_provider="manual",
        )
        session.add(subscription)
        await session.flush()

        # 8. Registro de auditoría
        await record_audit_event(
            session=session,
            action="SAAS_CLIENT_ONBOARDING",
            entity_name="Tenant",
            entity_id=str(tenant.id),
            company_id=company.id,
            user_id=user.id,
            changes={
                "tenant_name": tenant.name,
                "plan": plan.code,
                "trial_days": plan.trial_days,
                "admin_email": user.email,
            },
        )

        return {
            "tenant_id": tenant.id,
            "tenant_name": tenant.name,
            "tenant_slug": tenant.slug,
            "company_id": company.id,
            "company_legal_name": company.legal_name,
            "user_id": user.id,
            "admin_email": user.email,
            "subscription_id": subscription.id,
            "plan_code": plan.code,
            "status": subscription.status,
            "trial_ends_at": subscription.trial_ends_at,
            "message": f"Organización registrada exitosamente. Disfruta de {plan.trial_days} días de prueba gratuita sin compromiso.",
        }

    @classmethod
    async def get_subscription_details(cls, session: AsyncSession, tenant_id: uuid.UUID) -> dict[str, Any]:
        """Obtiene la ficha técnica y de consumo de la suscripción de un tenant."""
        stmt = (
            select(SaaSSubscription)
            .where(SaaSSubscription.tenant_id == tenant_id)
            .options(selectinload(SaaSSubscription.plan))
        )
        sub = (await session.execute(stmt)).scalar_one_or_none()
        if not sub:
            raise EntityNotFoundException("Suscripción SaaS", "tenant_id", str(tenant_id))

        plan = sub.plan
        now_utc = datetime.now(timezone.utc)

        # Contar usuarios activos en el tenant
        stmt_users = select(func.count(User.id)).where(User.tenant_id == tenant_id, User.is_active == True)
        active_users = (await session.execute(stmt_users)).scalar() or 0

        # Contar cuentas MeLi activas en el tenant
        stmt_meli = (
            select(func.count(MeliAccount.id))
            .join(Company, MeliAccount.company_id == Company.id)
            .where(Company.tenant_id == tenant_id, MeliAccount.is_active == True)
        )
        active_meli = (await session.execute(stmt_meli)).scalar() or 0

        # Calcular precio efectivo considerando precios personalizados y descuentos
        base_price = (
            float(sub.custom_price_mxn)
            if sub.custom_price_mxn is not None
            else float(plan.annual_price_mxn if sub.billing_cycle == "annual" else plan.monthly_price_mxn)
        )
        if sub.discount_percent > 0:
            effective_price = round(base_price * (1 - float(sub.discount_percent) / 100), 2)
        else:
            effective_price = base_price

        # Días restantes de prueba
        is_trial = sub.status == "trialing"
        days_left = 0
        if is_trial and sub.trial_ends_at:
            t_end = sub.trial_ends_at
            if t_end.tzinfo is None:
                t_end = t_end.replace(tzinfo=timezone.utc)
            delta = (t_end - now_utc).days
            days_left = max(0, delta)

        return {
            "id": sub.id,
            "tenant_id": sub.tenant_id,
            "plan_code": plan.code,
            "plan_name": plan.name,
            "status": sub.status,
            "billing_cycle": sub.billing_cycle,
            "current_period_start": sub.current_period_start,
            "current_period_end": sub.current_period_end,
            "trial_ends_at": sub.trial_ends_at,
            "is_trial_active": is_trial,
            "days_left_in_trial": days_left,
            "effective_price_mxn": effective_price,
            "discount_percent": float(sub.discount_percent),
            "auto_renew": sub.auto_renew,
            "payment_provider": sub.payment_provider,
            # Consumo vs Límites
            "current_monthly_orders": sub.current_monthly_orders,
            "max_monthly_orders": plan.max_monthly_orders,
            "current_monthly_syncs": sub.current_monthly_syncs,
            "max_monthly_syncs": plan.max_monthly_syncs,
            "current_storage_mb": float(sub.current_storage_mb),
            "max_storage_mb": plan.max_storage_mb,
            "active_users_count": active_users,
            "max_users": plan.max_users,
            "active_meli_accounts_count": active_meli,
            "max_meli_accounts": plan.max_meli_accounts,
            # Features
            "has_automation_engine": plan.has_automation_engine,
            "has_ai_assistant": plan.has_ai_assistant,
            "has_advanced_logistics": plan.has_advanced_logistics,
        }

    @classmethod
    async def change_plan(
        cls, session: AsyncSession, tenant_id: uuid.UUID, new_plan_code: str, billing_cycle: str = "monthly"
    ) -> dict[str, Any]:
        """Cambia el plan de suscripción de un cliente (Upgrade / Downgrade)."""
        stmt = (
            select(SaaSSubscription)
            .where(SaaSSubscription.tenant_id == tenant_id)
            .options(selectinload(SaaSSubscription.plan))
        )
        sub = (await session.execute(stmt)).scalar_one_or_none()
        if not sub:
            raise EntityNotFoundException("Suscripción", "tenant_id", str(tenant_id))

        new_plan = await cls.get_plan_by_code(session, new_plan_code)

        old_plan_name = sub.plan.name
        sub.plan_id = new_plan.id
        sub.billing_cycle = billing_cycle

        # Si el cliente estaba en trial o activo, actualizar tenant.plan_tier
        stmt_t = select(Tenant).where(Tenant.id == tenant_id)
        tenant = (await session.execute(stmt_t)).scalar_one_or_none()
        if tenant:
            tenant.plan_tier = new_plan.code

        await session.flush()
        logger.info(f"Suscripción de tenant {tenant_id} actualizada: de {old_plan_name} a {new_plan.name}")

        return {
            "status": "success",
            "message": f"Plan actualizado exitosamente a '{new_plan.name}' ({billing_cycle}).",
            "plan_code": new_plan.code,
            "plan_name": new_plan.name,
        }

    @classmethod
    async def suspend_tenant(
        cls, session: AsyncSession, tenant_id: uuid.UUID, reason: str, admin_user_id: uuid.UUID | None = None
    ) -> dict[str, Any]:
        """Suspende el acceso de un cliente por falta de pago o incumplimiento de términos."""
        stmt = select(SaaSSubscription).where(SaaSSubscription.tenant_id == tenant_id)
        sub = (await session.execute(stmt)).scalar_one_or_none()
        if not sub:
            raise EntityNotFoundException("Suscripción", "tenant_id", str(tenant_id))

        now_utc = datetime.now(timezone.utc)
        sub.status = "suspended"
        sub.suspended_at = now_utc
        sub.suspension_reason = reason

        await record_audit_event(
            session=session,
            action="SAAS_TENANT_SUSPENDED",
            entity_name="Tenant",
            entity_id=str(tenant_id),
            user_id=admin_user_id,
            changes={"status": "suspended", "reason": reason},
        )
        return {"status": "suspended", "tenant_id": str(tenant_id), "reason": reason, "suspended_at": now_utc}

    @classmethod
    async def reactivate_tenant(
        cls, session: AsyncSession, tenant_id: uuid.UUID, admin_user_id: uuid.UUID | None = None
    ) -> dict[str, Any]:
        """Reactiva una suscripción previamente suspendida tras confirmación de pago."""
        stmt = select(SaaSSubscription).where(SaaSSubscription.tenant_id == tenant_id)
        sub = (await session.execute(stmt)).scalar_one_or_none()
        if not sub:
            raise EntityNotFoundException("Suscripción", "tenant_id", str(tenant_id))

        sub.status = "active"
        sub.suspended_at = None
        sub.suspension_reason = None

        await record_audit_event(
            session=session,
            action="SAAS_TENANT_REACTIVATED",
            entity_name="Tenant",
            entity_id=str(tenant_id),
            user_id=admin_user_id,
            changes={"status": "active"},
        )
        return {"status": "active", "tenant_id": str(tenant_id), "message": "Organización reactivada exitosamente."}

    @classmethod
    async def extend_trial(
        cls, session: AsyncSession, tenant_id: uuid.UUID, extra_days: int, admin_user_id: uuid.UUID | None = None
    ) -> dict[str, Any]:
        """Concede días adicionales de prueba a un cliente potencial."""
        stmt = select(SaaSSubscription).where(SaaSSubscription.tenant_id == tenant_id)
        sub = (await session.execute(stmt)).scalar_one_or_none()
        if not sub:
            raise EntityNotFoundException("Suscripción", "tenant_id", str(tenant_id))

        now_utc = datetime.now(timezone.utc)
        current_trial_end = sub.trial_ends_at or now_utc
        if current_trial_end.tzinfo is None:
            current_trial_end = current_trial_end.replace(tzinfo=timezone.utc)

        base_dt = max(now_utc, current_trial_end)
        new_trial_end = base_dt + timedelta(days=extra_days)

        sub.trial_ends_at = new_trial_end
        sub.current_period_end = new_trial_end
        sub.status = "trialing"

        await session.flush()
        return {
            "status": "trialing",
            "new_trial_ends_at": new_trial_end,
            "message": f"Periodo de prueba extendido en {extra_days} días adicionales.",
        }

    @classmethod
    async def set_custom_pricing(
        cls,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        custom_price: float | None,
        discount_percent: float = 0.0,
        notes: str | None = None,
        admin_user_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """
        Fija una cotización o descuento especial tras análisis comercial individual.
        Cumple la regla: 'No fijar precios definitivos sin análisis comercial'.
        """
        stmt = select(SaaSSubscription).where(SaaSSubscription.tenant_id == tenant_id)
        sub = (await session.execute(stmt)).scalar_one_or_none()
        if not sub:
            raise EntityNotFoundException("Suscripción", "tenant_id", str(tenant_id))

        sub.custom_price_mxn = custom_price
        sub.discount_percent = discount_percent

        await record_audit_event(
            session=session,
            action="SAAS_CUSTOM_PRICING_APPLIED",
            entity_name="SaaSSubscription",
            entity_id=str(sub.id),
            user_id=admin_user_id,
            changes={
                "custom_price_mxn": custom_price,
                "discount_percent": discount_percent,
                "commercial_notes": notes,
            },
        )
        return {
            "status": "success",
            "tenant_id": str(tenant_id),
            "custom_price_mxn": custom_price,
            "discount_percent": discount_percent,
            "message": "Condición comercial personalizada guardada correctamente.",
        }

    @classmethod
    async def create_saas_invoice(
        cls, session: AsyncSession, tenant_id: uuid.UUID, due_days: int = 15
    ) -> SaaSInvoice:
        """
        Genera una factura formal de suscripción emitida por la plataforma SaaS.
        Separada absolutamente de las ventas y facturas SAT de cada cliente.
        """
        stmt = (
            select(SaaSSubscription)
            .where(SaaSSubscription.tenant_id == tenant_id)
            .options(selectinload(SaaSSubscription.plan))
        )
        sub = (await session.execute(stmt)).scalar_one_or_none()
        if not sub:
            raise EntityNotFoundException("Suscripción", "tenant_id", str(tenant_id))

        plan = sub.plan
        base_price = (
            float(sub.custom_price_mxn)
            if sub.custom_price_mxn is not None
            else float(plan.annual_price_mxn if sub.billing_cycle == "annual" else plan.monthly_price_mxn)
        )
        if sub.discount_percent > 0:
            effective_subtotal = round(base_price * (1 - float(sub.discount_percent) / 100), 2)
        else:
            effective_subtotal = base_price

        tax_amount = round(effective_subtotal * 0.16, 2)  # IVA 16% México
        total_amount = round(effective_subtotal + tax_amount, 2)

        now_utc = datetime.now(timezone.utc)
        folio = f"SAAS-{now_utc.strftime('%Y%m')}-{uuid.uuid4().hex[:6].upper()}"

        invoice = SaaSInvoice(
            tenant_id=tenant_id,
            subscription_id=sub.id,
            invoice_number=folio,
            issue_date=now_utc,
            due_date=now_utc + timedelta(days=due_days),
            subtotal=effective_subtotal,
            tax_amount=tax_amount,
            total_amount=total_amount,
            currency="MXN",
            status="issued",
            notes=f"Suscripción ERP Mercado Libre México - Plan {plan.name} ({sub.billing_cycle})",
        )
        session.add(invoice)
        await session.flush()
        return invoice

    @classmethod
    async def record_saas_payment(
        cls,
        session: AsyncSession,
        invoice_id: uuid.UUID,
        amount: float,
        payment_method: str,
        gateway_transaction_id: str | None = None,
        gateway_fee: float = 0.0,
        receipt_url: str | None = None,
    ) -> SaaSPayment:
        """
        Registra la recepción de un pago por suscripción, marca la factura como pagada
        y extiende el periodo de vigencia de la suscripción SaaS.
        """
        stmt_inv = (
            select(SaaSInvoice)
            .where(SaaSInvoice.id == invoice_id)
            .options(selectinload(SaaSInvoice.subscription).selectinload(SaaSSubscription.plan))
        )
        invoice = (await session.execute(stmt_inv)).scalar_one_or_none()
        if not invoice:
            raise EntityNotFoundException("Factura SaaS", "id", str(invoice_id))

        now_utc = datetime.now(timezone.utc)
        payment = SaaSPayment(
            tenant_id=invoice.tenant_id,
            invoice_id=invoice.id,
            payment_method=payment_method,
            amount=amount,
            currency="MXN",
            status="succeeded",
            gateway_transaction_id=gateway_transaction_id or f"TX-{uuid.uuid4().hex[:10].upper()}",
            gateway_fee=gateway_fee,
            paid_at=now_utc,
            receipt_url=receipt_url,
        )
        session.add(payment)

        # Actualizar factura
        invoice.status = "paid"
        invoice.paid_at = now_utc

        # Renovar / Activar suscripción
        sub = invoice.subscription
        sub.status = "active"
        sub.suspended_at = None
        sub.suspension_reason = None

        # Avanzar el ciclo
        period_days = 365 if sub.billing_cycle == "annual" else 30
        sub.current_period_start = now_utc
        sub.current_period_end = now_utc + timedelta(days=period_days)
        # Resetear contadores de consumo para el nuevo ciclo
        sub.current_monthly_orders = 0
        sub.current_monthly_syncs = 0

        await session.flush()
        logger.info(
            f"Pago de suscripción procesado exitosamente: Factura={invoice.invoice_number}, "
            f"Monto=${amount} MXN vía {payment_method}"
        )
        return payment

    @classmethod
    async def get_saas_metrics(cls, session: AsyncSession) -> dict[str, Any]:
        """
        Calcula las métricas financieras y comerciales globales de la plataforma SaaS:
        MRR, ARR, ARPU, Churn Rate, Clientes Activos, en Prueba, Suspendidos y Cancelados.
        """
        # Contar tenants por estado de suscripción
        stmt_subs = (
            select(SaaSSubscription)
            .options(selectinload(SaaSSubscription.plan))
        )
        all_subs = (await session.execute(stmt_subs)).scalars().all()

        total_tenants = len(all_subs)
        active_tenants = 0
        trialing_tenants = 0
        suspended_tenants = 0
        cancelled_tenants = 0
        plan_dist = {"basic": 0, "pro": 0, "enterprise": 0}

        total_monthly_revenue = 0.0

        for s in all_subs:
            p_code = s.plan.code
            plan_dist[p_code] = plan_dist.get(p_code, 0) + 1

            if s.status == "active":
                active_tenants += 1
                base_price = (
                    float(s.custom_price_mxn)
                    if s.custom_price_mxn is not None
                    else float(s.plan.monthly_price_mxn)
                )
                if s.discount_percent > 0:
                    base_price = base_price * (1 - float(s.discount_percent) / 100)
                # Si es anual, convertir a MRR dividiendo entre 12
                if s.billing_cycle == "annual":
                    annual_base = (
                        float(s.custom_price_mxn * 12)
                        if s.custom_price_mxn is not None
                        else float(s.plan.annual_price_mxn)
                    )
                    total_monthly_revenue += (annual_base / 12)
                else:
                    total_monthly_revenue += base_price

            elif s.status == "trialing":
                trialing_tenants += 1
            elif s.status == "suspended":
                suspended_tenants += 1
            elif s.status in ["cancelled", "expired"]:
                cancelled_tenants += 1

        mrr = round(total_monthly_revenue, 2)
        arr = round(mrr * 12, 2)
        arpu = round(mrr / active_tenants, 2) if active_tenants > 0 else 0.0

        # Tasa de cancelación (Churn Rate) = Cancelados / Total
        churn_rate = round((cancelled_tenants / total_tenants * 100), 2) if total_tenants > 0 else 0.0

        return {
            "mrr_mxn": mrr,
            "arr_mxn": arr,
            "arpu_mxn": arpu,
            "total_tenants": total_tenants,
            "active_tenants": active_tenants,
            "trialing_tenants": trialing_tenants,
            "suspended_tenants": suspended_tenants,
            "cancelled_tenants": cancelled_tenants,
            "churn_rate_percent": churn_rate,
            "plan_distribution": plan_dist,
            "evaluated_at": datetime.now(timezone.utc),
        }

    @classmethod
    async def list_tenants_for_admin(cls, session: AsyncSession) -> list[dict[str, Any]]:
        """Listado integral de clientes para el Panel Global SaaS."""
        stmt = (
            select(Tenant)
            .options(
                selectinload(Tenant.companies),
                selectinload(Tenant.users),
            )
            .order_by(Tenant.created_at.desc())
        )
        tenants = (await session.execute(stmt)).scalars().all()

        results = []
        for t in tenants:
            # Buscar suscripción
            stmt_sub = (
                select(SaaSSubscription)
                .where(SaaSSubscription.tenant_id == t.id)
                .options(selectinload(SaaSSubscription.plan))
            )
            sub = (await session.execute(stmt_sub)).scalar_one_or_none()

            admin_user = next((u for u in t.users if u.role in [RoleEnum.COMPANY_ADMIN.value, "company_admin"]), None)
            admin_email = admin_user.email if admin_user else (t.users[0].email if t.users else "Sin admin")

            plan_code = sub.plan.code if sub and sub.plan else t.plan_tier
            plan_name = sub.plan.name if sub and sub.plan else t.plan_tier.capitalize()
            status_str = sub.status if sub else ("active" if t.is_active else "suspended")
            cycle = sub.billing_cycle if sub else "monthly"
            p_end = sub.current_period_end if sub else t.created_at + timedelta(days=30)

            # MRR individual
            eff_mrr = 0.0
            if sub and sub.plan and sub.status == "active":
                eff_mrr = float(sub.custom_price_mxn or sub.plan.monthly_price_mxn)

            results.append({
                "tenant_id": t.id,
                "tenant_name": t.name,
                "tenant_slug": t.slug,
                "companies_count": len(t.companies),
                "admin_email": admin_email,
                "plan_code": plan_code,
                "plan_name": plan_name,
                "status": status_str,
                "billing_cycle": cycle,
                "current_period_end": p_end,
                "trial_ends_at": sub.trial_ends_at if sub else None,
                "effective_mrr_mxn": eff_mrr,
                "active_users": len(t.users),
                "meli_accounts_count": 0,
                "created_at": t.created_at,
            })
        return results

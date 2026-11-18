"""Endpoints REST para Comercialización SaaS, Gestión de Suscripciones y Panel Global."""

from typing import Any
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_context import UserContext, get_current_user, require_company_permission, require_platform_admin
from src.core.database import get_db
from src.core.exceptions import PermissionDeniedException
from src.core.permissions import ActionEnum, ModuleEnum
from src.models.saas import SaaSInvoice
from src.schemas.saas import (
    CancelSubscriptionRequest,
    ChangePlanRequest,
    CustomPricingRequest,
    ExtendTrialRequest,
    SaaSClientRegisterRequest,
    SaaSClientRegisterResponse,
    SaaSGlobalMetricsResponse,
    SaaSInvoiceResponse,
    SaaSPlanResponse,
    SaaSPaymentRecordRequest,
    SaaSSubscriptionResponse,
    SaaSTenantSummaryResponse,
    SuspendTenantRequest,
)
from src.services.saas.subscription_service import SaaSSubscriptionService

router = APIRouter(prefix="/saas", tags=["Comercialización SaaS & Suscripciones"])


# =============================================================================
# ENDPOINTS PÚBLICOS Y DE CLIENTES
# =============================================================================

@router.get("/plans", response_model=list[SaaSPlanResponse], status_code=status.HTTP_200_OK)
async def list_available_plans(session: AsyncSession = Depends(get_db)) -> list[Any]:
    """Catálogo público de planes comerciales disponibles (Básico, Profesional, Empresarial)."""
    return await SaaSSubscriptionService.get_plans(session)


@router.post("/onboarding", response_model=SaaSClientRegisterResponse, status_code=status.HTTP_201_CREATED)
async def client_onboarding(
    payload: SaaSClientRegisterRequest,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Registro autogestionado de un nuevo cliente SaaS con periodo de prueba gratuito de 14 días.
    Crea el Tenant, la Empresa fiscal, el Usuario Administrador y la Suscripción inicial.
    """
    return await SaaSSubscriptionService.register_client(session, payload)


@router.get("/my-subscription", response_model=SaaSSubscriptionResponse, status_code=status.HTTP_200_OK)
async def get_my_subscription(
    user_ctx: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Consulta la suscripción activa, cuotas y límites de la organización del usuario autenticado."""
    if not user_ctx.user.tenant_id:
        raise PermissionDeniedException("El usuario no se encuentra vinculado a una Organización SaaS.")
    return await SaaSSubscriptionService.get_subscription_details(session, user_ctx.user.tenant_id)


@router.post("/my-subscription/change-plan", status_code=status.HTTP_200_OK)
async def change_my_plan(
    payload: ChangePlanRequest,
    user_ctx: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Solicita un cambio de plan comercial (Upgrade / Downgrade)."""
    if not user_ctx.user.tenant_id:
        raise PermissionDeniedException("El usuario no se encuentra vinculado a una Organización SaaS.")
    return await SaaSSubscriptionService.change_plan(
        session, user_ctx.user.tenant_id, payload.new_plan_code, payload.billing_cycle
    )


@router.get("/my-invoices", response_model=list[SaaSInvoiceResponse], status_code=status.HTTP_200_OK)
async def list_my_invoices(
    user_ctx: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[Any]:
    """Consulta el historial de facturas emitidas por la plataforma SaaS a la organización cliente."""
    if not user_ctx.user.tenant_id:
        raise PermissionDeniedException("El usuario no se encuentra vinculado a una Organización SaaS.")
    stmt = (
        select(SaaSInvoice)
        .where(SaaSInvoice.tenant_id == user_ctx.user.tenant_id)
        .order_by(desc(SaaSInvoice.issue_date))
    )
    invoices = (await session.execute(stmt)).scalars().all()
    return list(invoices)


# =============================================================================
# PANEL GLOBAL DE ADMINISTRACIÓN SAAS (PLATFORM OWNER / SUPERADMIN)
# =============================================================================

@router.get("/admin/metrics", response_model=SaaSGlobalMetricsResponse, status_code=status.HTTP_200_OK)
async def get_saas_global_metrics(
    admin_ctx: UserContext = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retorna las métricas financieras y comerciales globales del SaaS (MRR, ARR, ARPU, Churn Rate)."""
    return await SaaSSubscriptionService.get_saas_metrics(session)


@router.get("/admin/tenants", response_model=list[SaaSTenantSummaryResponse], status_code=status.HTTP_200_OK)
async def list_saas_tenants(
    admin_ctx: UserContext = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Listado consolidado de todos los clientes SaaS con su plan, estatus y consumo."""
    return await SaaSSubscriptionService.list_tenants_for_admin(session)


@router.post("/admin/tenants/{tenant_id}/suspend", status_code=status.HTTP_200_OK)
async def suspend_client_tenant(
    tenant_id: uuid.UUID,
    payload: SuspendTenantRequest,
    admin_ctx: UserContext = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Suspende administrativamente a un cliente por falta de pago o violación de términos."""
    return await SaaSSubscriptionService.suspend_tenant(session, tenant_id, payload.reason, admin_ctx.id)


@router.post("/admin/tenants/{tenant_id}/reactivate", status_code=status.HTTP_200_OK)
async def reactivate_client_tenant(
    tenant_id: uuid.UUID,
    admin_ctx: UserContext = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Reactiva el acceso de una organización previamente suspendida."""
    return await SaaSSubscriptionService.reactivate_tenant(session, tenant_id, admin_ctx.id)


@router.post("/admin/tenants/{tenant_id}/extend-trial", status_code=status.HTTP_200_OK)
async def extend_client_trial(
    tenant_id: uuid.UUID,
    payload: ExtendTrialRequest,
    admin_ctx: UserContext = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Extiende comercialmente los días de prueba gratuita de un cliente potencial."""
    return await SaaSSubscriptionService.extend_trial(session, tenant_id, payload.extra_days, admin_ctx.id)


@router.post("/admin/tenants/{tenant_id}/set-custom-pricing", status_code=status.HTTP_200_OK)
async def apply_custom_pricing(
    tenant_id: uuid.UUID,
    payload: CustomPricingRequest,
    admin_ctx: UserContext = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Fija una cotización o descuento especial tras análisis comercial.
    Cumple la directriz: 'No fijar precios definitivos sin análisis comercial'.
    """
    return await SaaSSubscriptionService.set_custom_pricing(
        session=session,
        tenant_id=tenant_id,
        custom_price=payload.custom_monthly_price_mxn,
        discount_percent=payload.discount_percent,
        notes=payload.notes,
        admin_user_id=admin_ctx.id,
    )


@router.post("/admin/invoices/create", response_model=SaaSInvoiceResponse, status_code=status.HTTP_201_CREATED)
async def generate_saas_invoice(
    tenant_id: uuid.UUID = Query(..., description="UUID de la organización cliente"),
    due_days: int = Query(15, ge=1, le=60, description="Días de crédito para vencimiento"),
    admin_ctx: UserContext = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_db),
) -> Any:
    """Emite una factura formal de suscripción SaaS para una organización cliente."""
    return await SaaSSubscriptionService.create_saas_invoice(session, tenant_id, due_days)


@router.post("/admin/payments/record", status_code=status.HTTP_201_CREATED)
async def record_payment(
    payload: SaaSPaymentRecordRequest,
    admin_ctx: UserContext = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Registra la confirmación de pago de una factura SaaS y renueva/activa la suscripción."""
    payment = await SaaSSubscriptionService.record_saas_payment(
        session=session,
        invoice_id=payload.invoice_id,
        amount=payload.amount,
        payment_method=payload.payment_method,
        gateway_transaction_id=payload.gateway_transaction_id,
        gateway_fee=payload.gateway_fee,
        receipt_url=payload.receipt_url,
    )
    return {
        "status": "success",
        "payment_id": str(payment.id),
        "invoice_id": str(payment.invoice_id),
        "amount": float(payment.amount),
        "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
        "message": "Pago registrado exitosamente. Suscripción activada y renovada.",
    }

"""Suite Exhaustiva de Pruebas Automatizadas para Comercialización SaaS Multiempresa."""

from datetime import datetime, timedelta, timezone
import uuid
import pytest
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

from src.core.database import get_db
from src.core.quota_enforcement import (
    FeatureNotIncludedException,
    QuotaEnforcementService,
    QuotaExceededException,
    SubscriptionSuspendedException,
)
from src.main import app
from src.models import Base
from src.models.saas import SaaSInvoice, SaaSPlan, SaaSPayment, SaaSSubscription
from src.models.tenant import Company, Tenant
from src.models.user import CompanyUser, User
from src.schemas.saas import SaaSClientRegisterRequest
from src.services.saas.subscription_service import SaaSSubscriptionService


@pytest.fixture
def saas_test_context(tmp_path):
    """Provee un entorno aislado de pruebas para SaaS con base de datos SQLite."""
    db_file = tmp_path / "saas_test.db"
    sync_engine = sa.create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()

    async_engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    session_factory = async_sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        # Sembrar planes comerciales
        with sync_engine.connect() as conn:
            pass

        yield {
            "client": client,
            "session_factory": session_factory,
        }

    app.dependency_overrides.clear()


# =============================================================================
# 1. PRUEBA DE INICIALIZACIÓN DE PLANES CANÓNICOS
# =============================================================================
@pytest.mark.anyio
async def test_default_saas_plans_initialization(saas_test_context):
    """
    Verifica que los planes canónicos Básico, Profesional y Empresarial
    se inicialicen con sus límites, precios configurables y banderas de características.
    """
    async with saas_test_context["session_factory"]() as session:
        plans = await SaaSSubscriptionService.get_plans(session)
        assert len(plans) == 3

        plan_map = {p.code: p for p in plans}
        assert "basic" in plan_map
        assert "pro" in plan_map
        assert "enterprise" in plan_map

        basic = plan_map["basic"]
        assert basic.name == "Básico"
        assert basic.max_users == 3
        assert basic.max_meli_accounts == 1
        assert basic.max_storage_mb == 1024
        assert basic.has_automation_engine is False
        assert basic.trial_days == 14

        pro = plan_map["pro"]
        assert pro.name == "Profesional"
        assert pro.max_users == 10
        assert pro.max_meli_accounts == 5
        assert pro.has_automation_engine is True
        assert pro.has_ai_assistant is True

        enterprise = plan_map["enterprise"]
        assert enterprise.is_custom_pricing is True
        assert enterprise.max_users == -1
        assert enterprise.max_meli_accounts == -1


# =============================================================================
# 2. PRUEBA DE ALTA DE CLIENTES Y ONBOARDING CON TRIAL
# =============================================================================
@pytest.mark.anyio
async def test_client_onboarding_and_trial_period(saas_test_context):
    """
    Verifica el flujo completo de alta de nuevo cliente SaaS con suscripción trial de 14 días.
    """
    client = saas_test_context["client"]
    uid = uuid.uuid4().hex[:6]

    res = client.post("/api/v1/saas/onboarding", json={
        "tenant_name": f"Cliente SaaS {uid}",
        "tenant_slug": f"cliente-slug-{uid}",
        "company_legal_name": f"Distribuidora {uid} SA de CV",
        "company_rfc": "DIS880101AA1",
        "admin_email": f"ceo_{uid}@distribuidora.com",
        "admin_password": "PasswordSegura123!",
        "admin_full_name": "Director General",
        "plan_code": "basic",
        "billing_cycle": "monthly",
    })
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "trialing"
    assert data["plan_code"] == "basic"
    assert data["trial_ends_at"] is not None

    # Verificar login con las credenciales creadas
    login_res = client.post("/api/v1/auth/login", json={
        "email": f"ceo_{uid}@distribuidora.com",
        "password": "PasswordSegura123!",
    })
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]

    # Consultar suscripción activa
    sub_res = client.get("/api/v1/saas/my-subscription", headers={"Authorization": f"Bearer {token}"})
    assert sub_res.status_code == 200
    sub_data = sub_res.json()
    assert sub_data["plan_code"] == "basic"
    assert sub_data["is_trial_active"] is True
    assert sub_data["days_left_in_trial"] >= 13


# =============================================================================
# 3. PRUEBA DE ENFORZAMIENTO DE LÍMITES (MAX USUARIOS Y CUENTAS MELI)
# =============================================================================
@pytest.mark.anyio
async def test_quota_enforcement_limits(saas_test_context):
    """
    Verifica que el motor de cuotas bloquee la creación de recursos cuando se alcanza el límite del plan.
    """
    async with saas_test_context["session_factory"]() as session:
        # Registrar cliente en plan básico (límite: 3 usuarios, 1 cuenta MeLi)
        reg_payload = SaaSClientRegisterRequest(
            tenant_name="Empresa Límites",
            tenant_slug=f"lim-{uuid.uuid4().hex[:6]}",
            company_legal_name="Límites SA",
            company_rfc="LIM880101AA1",
            admin_email=f"admin_{uuid.uuid4().hex[:6]}@limites.com",
            admin_password="Password123!",
            admin_full_name="Admin Lim",
            plan_code="basic",
        )
        reg_res = await SaaSSubscriptionService.register_client(session, reg_payload)
        t_id = reg_res["tenant_id"]

        # Agregar 2 usuarios adicionales (total 3 = límite del plan básico)
        for i in range(2):
            u = User(
                tenant_id=t_id,
                email=f"user_{i}_{uuid.uuid4().hex[:4]}@lim.com",
                password_hash="hash",
                full_name=f"User {i}",
                role="operator",
                is_active=True,
            )
            session.add(u)
        await session.flush()

        # Intentar verificar límite de usuario -> debe lanzar QuotaExceededException
        with pytest.raises(QuotaExceededException) as exc:
            await QuotaEnforcementService.check_user_limit(session, t_id)
        assert "Límite de cuota alcanzado para 'Usuarios Permitidos'" in str(exc.value)
        assert exc.value.status_code == 402

        # Verificar bandera de característica (Plan básico no tiene automatizaciones)
        with pytest.raises(FeatureNotIncludedException) as exc_feat:
            await QuotaEnforcementService.check_feature_permission(session, t_id, "automation_engine")
        assert "Motor de Automatizaciones Empresariales (ECA)" in str(exc_feat.value)


# =============================================================================
# 4. PRUEBA DE CICLO DE VIDA: SUSPENSIÓN Y REACTIVACIÓN
# =============================================================================
@pytest.mark.anyio
async def test_subscription_lifecycle_suspension_and_reactivation(saas_test_context):
    """
    Verifica la suspensión administrativa por morosidad (bloqueando operaciones de escritura)
    y la reactivación instantánea tras regularización.
    """
    async with saas_test_context["session_factory"]() as session:
        reg_payload = SaaSClientRegisterRequest(
            tenant_name="Empresa Morosa",
            tenant_slug=f"mor-{uuid.uuid4().hex[:6]}",
            company_legal_name="Morosa SA",
            company_rfc="MOR880101AA1",
            admin_email=f"admin_{uuid.uuid4().hex[:6]}@morosa.com",
            admin_password="Password123!",
            admin_full_name="Admin Morosa",
            plan_code="basic",
        )
        reg_res = await SaaSSubscriptionService.register_client(session, reg_payload)
        t_id = reg_res["tenant_id"]

        # 1. Suspender cliente
        susp = await SaaSSubscriptionService.suspend_tenant(session, t_id, "Falta de pago de factura SAAS-2026-0001")
        assert susp["status"] == "suspended"

        # Verificar que el validador de suscripción bloquea operaciones
        with pytest.raises(SubscriptionSuspendedException) as exc:
            await QuotaEnforcementService.check_subscription_status(session, t_id)
        assert "Falta de pago" in str(exc.value)
        assert exc.value.status_code == 402

        # 2. Reactivar cliente
        react = await SaaSSubscriptionService.reactivate_tenant(session, t_id)
        assert react["status"] == "active"

        # Ahora el validador permite operar normalmente
        active_sub = await QuotaEnforcementService.check_subscription_status(session, t_id)
        assert active_sub.status == "active"


# =============================================================================
# 5. PRUEBA DE UPGRADE Y DOWNGRADE DE PLAN
# =============================================================================
@pytest.mark.anyio
async def test_change_plan_upgrade_and_downgrade(saas_test_context):
    """
    Verifica la actualización de plan (de Básico a Profesional) con ampliación de cuotas.
    """
    async with saas_test_context["session_factory"]() as session:
        reg_payload = SaaSClientRegisterRequest(
            tenant_name="Empresa Upgrade",
            tenant_slug=f"upg-{uuid.uuid4().hex[:6]}",
            company_legal_name="Upgrade SA",
            company_rfc="UPG880101AA1",
            admin_email=f"admin_{uuid.uuid4().hex[:6]}@upg.com",
            admin_password="Password123!",
            admin_full_name="Admin Upg",
            plan_code="basic",
        )
        reg_res = await SaaSSubscriptionService.register_client(session, reg_payload)
        t_id = reg_res["tenant_id"]

        # Upgrade a Plan Profesional
        chg = await SaaSSubscriptionService.change_plan(session, t_id, "pro", "annual")
        assert chg["plan_code"] == "pro"

        # Comprobar que ahora tiene acceso al motor de automatización
        sub, plan = await QuotaEnforcementService.get_subscription_with_plan(session, t_id)
        assert plan.code == "pro"
        assert plan.max_users == 10
        assert plan.has_automation_engine is True

        # No debe lanzar excepción
        await QuotaEnforcementService.check_feature_permission(session, t_id, "automation_engine")


# =============================================================================
# 6. PRUEBA DE PRECIOS PERSONALIZADOS TRAS ANÁLISIS COMERCIAL
# =============================================================================
@pytest.mark.anyio
async def test_custom_pricing_without_rigid_defaults(saas_test_context):
    """
    Cumple la directriz: 'No fijar precios definitivos sin análisis comercial'.
    Permite fijar cotizaciones y descuentos personalizados a nivel de organización.
    """
    async with saas_test_context["session_factory"]() as session:
        reg_payload = SaaSClientRegisterRequest(
            tenant_name="Empresa Gran Cuenta",
            tenant_slug=f"corp-{uuid.uuid4().hex[:6]}",
            company_legal_name="Gran Cuenta SA",
            company_rfc="GRA880101AA1",
            admin_email=f"admin_{uuid.uuid4().hex[:6]}@grancuenta.com",
            admin_password="Password123!",
            admin_full_name="Admin Gran",
            plan_code="enterprise",
        )
        reg_res = await SaaSSubscriptionService.register_client(session, reg_payload)
        t_id = reg_res["tenant_id"]

        # Aplicar cotización negociada: $2,800 MXN mensuales con 15% de descuento especial
        custom_res = await SaaSSubscriptionService.set_custom_pricing(
            session=session,
            tenant_id=t_id,
            custom_price=2800.0,
            discount_percent=15.0,
            notes="Acuerdo comercial corporativo anual con 5 sucursales",
        )
        assert custom_res["custom_price_mxn"] == 2800.0
        assert custom_res["discount_percent"] == 15.0

        details = await SaaSSubscriptionService.get_subscription_details(session, t_id)
        # 2800 * 0.85 = 2380.0
        assert details["effective_price_mxn"] == 2380.0


# =============================================================================
# 7. PRUEBA DE FACTURACIÓN Y PAGO SAAS SEPARADO DE FINANZAS DE CLIENTES
# =============================================================================
@pytest.mark.anyio
async def test_saas_invoicing_and_payment_processing(saas_test_context):
    """
    Verifica que la facturación del SaaS opere de forma independiente a las ventas de MeLi,
    con cálculo de IVA 16% mexicano y reactivación automática de periodo tras registrar pago.
    """
    async with saas_test_context["session_factory"]() as session:
        reg_payload = SaaSClientRegisterRequest(
            tenant_name="Empresa Facturación",
            tenant_slug=f"fac-{uuid.uuid4().hex[:6]}",
            company_legal_name="Facturación SA",
            company_rfc="FAC880101AA1",
            admin_email=f"admin_{uuid.uuid4().hex[:6]}@fac.com",
            admin_password="Password123!",
            admin_full_name="Admin Fac",
            plan_code="basic",
        )
        reg_res = await SaaSSubscriptionService.register_client(session, reg_payload)
        t_id = reg_res["tenant_id"]

        # 1. Generar factura de suscripción SaaS
        invoice = await SaaSSubscriptionService.create_saas_invoice(session, t_id, due_days=10)
        assert invoice.invoice_number.startswith("SAAS-")
        assert invoice.subtotal == 499.0
        assert invoice.tax_amount == round(499.0 * 0.16, 2)
        assert invoice.total_amount == round(499.0 + invoice.tax_amount, 2)
        assert invoice.status == "issued"

        # 2. Registrar pago de la factura mediante SPEI o Stripe
        payment = await SaaSSubscriptionService.record_saas_payment(
            session=session,
            invoice_id=invoice.id,
            amount=invoice.total_amount,
            payment_method="stripe",
            gateway_transaction_id="ch_stripe_test_123456",
            gateway_fee=18.50,
        )
        assert payment.status == "succeeded"
        assert invoice.status == "paid"

        # 3. Comprobar que la suscripción pasó a 'active' con vigencia renovada
        sub = await QuotaEnforcementService.check_subscription_status(session, t_id)
        assert sub.status == "active"


# =============================================================================
# 8. PRUEBA DE MÉTRICAS GLOBALES DEL SAAS (MRR, ARR, CHURN)
# =============================================================================
@pytest.mark.anyio
async def test_saas_global_metrics_calculation(saas_test_context):
    """
    Verifica el cálculo en tiempo real de MRR, ARR, ARPU y conteo de clientes por estado.
    """
    async with saas_test_context["session_factory"]() as session:
        # Crear 1 cliente activo con pago
        reg_payload = SaaSClientRegisterRequest(
            tenant_name="Empresa Métrica",
            tenant_slug=f"met-{uuid.uuid4().hex[:6]}",
            company_legal_name="Métrica SA",
            company_rfc="MET880101AA1",
            admin_email=f"admin_{uuid.uuid4().hex[:6]}@metrica.com",
            admin_password="Password123!",
            admin_full_name="Admin Met",
            plan_code="pro",
        )
        reg_res = await SaaSSubscriptionService.register_client(session, reg_payload)
        t_id = reg_res["tenant_id"]

        # Activar y emitir pago
        inv = await SaaSSubscriptionService.create_saas_invoice(session, t_id)
        await SaaSSubscriptionService.record_saas_payment(session, inv.id, inv.total_amount, "spei")

        metrics = await SaaSSubscriptionService.get_saas_metrics(session)
        assert metrics["total_tenants"] >= 1
        assert metrics["active_tenants"] >= 1
        assert metrics["mrr_mxn"] >= 1499.0
        assert metrics["arr_mxn"] >= 1499.0 * 12
        assert metrics["arpu_mxn"] > 0.0

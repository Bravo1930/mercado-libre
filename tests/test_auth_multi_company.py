"""Pruebas exhaustivas del sistema de autenticación, control de sesiones, roles y aislamiento multi-empresa."""

import uuid
from datetime import datetime, timedelta, timezone
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from src.core.auth_context import (
    CompanyContext,
    UserContext,
    has_module_permission,
)
from src.core.database import get_db
from src.core.exceptions import AuthenticationFailedException, PermissionDeniedException
from src.core.permissions import (
    ActionEnum,
    ModuleEnum,
    RoleEnum,
    can_assign_role,
)
from src.core.security import create_access_token, decode_access_token, hash_password, verify_password
from src.main import app
from src.models import (
    AuditLog,
    Base,
    Company,
    CompanyUser,
    PasswordResetToken,
    Tenant,
    User,
    UserSession,
)


@pytest.fixture(scope="module")
def db_session():
    """Crea una base de datos SQLite en memoria con todas las tablas del ERP para pruebas unitarias."""
    engine = sa.create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def api_client(tmp_path):
    """Provee un cliente TestClient con una base de datos SQLite aislada y limpia por prueba."""
    db_file = tmp_path / "integration_test.db"
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
        yield client
    app.dependency_overrides.pop(get_db, None)


def test_rbac_8_roles_matrix_permissions():
    """Valida la matriz de permisos para los 8 roles oficiales del sistema."""
    # 1. Platform Owner (Acceso a nivel SaaS, NO a documentos privados sin membresía)
    assert has_module_permission(RoleEnum.PLATFORM_OWNER.value, "tenants", "create") is True
    assert has_module_permission(RoleEnum.PLATFORM_OWNER.value, "platform", "manage_tenants") is True
    assert has_module_permission(RoleEnum.PLATFORM_OWNER.value, "finance", "audit_sat") is False

    # 2. SaaS Admin
    assert has_module_permission(RoleEnum.SAAS_ADMIN.value, "tenants", "read") is True
    assert has_module_permission(RoleEnum.SAAS_ADMIN.value, "finance", "manage_cogs") is False

    # 3. Company Admin (Control total dentro de la empresa)
    assert has_module_permission(RoleEnum.COMPANY_ADMIN.value, "catalog", "create") is True
    assert has_module_permission(RoleEnum.COMPANY_ADMIN.value, "inventory", "adjust") is True
    assert has_module_permission(RoleEnum.COMPANY_ADMIN.value, "orders", "read") is True
    assert has_module_permission(RoleEnum.COMPANY_ADMIN.value, "finance", "audit_sat") is True
    assert has_module_permission(RoleEnum.COMPANY_ADMIN.value, "users", "manage_roles") is True
    assert has_module_permission(RoleEnum.COMPANY_ADMIN.value, "settings", "update") is True

    # 4. Director (Visualización amplia, finanzas, pero no alterar ajustes ni eliminar usuarios)
    assert has_module_permission(RoleEnum.DIRECTOR.value, "orders", "read") is True
    assert has_module_permission(RoleEnum.DIRECTOR.value, "finance", "read") is True
    assert has_module_permission(RoleEnum.DIRECTOR.value, "catalog", "update") is True
    assert has_module_permission(RoleEnum.DIRECTOR.value, "users", "delete") is False
    assert has_module_permission(RoleEnum.DIRECTOR.value, "settings", "update") is False

    # 5. Operador (Catálogo, pedidos, logística, pero NO finanzas ni configuración)
    assert has_module_permission(RoleEnum.OPERATOR.value, "catalog", "create") is True
    assert has_module_permission(RoleEnum.OPERATOR.value, "orders", "read") is True
    assert has_module_permission(RoleEnum.OPERATOR.value, "logistics", "print_label") is True
    assert has_module_permission(RoleEnum.OPERATOR.value, "finance", "read") is False
    assert has_module_permission(RoleEnum.OPERATOR.value, "settings", "update") is False
    assert has_module_permission(RoleEnum.OPERATOR.value, "users", "manage_roles") is False

    # 6. Responsable de Almacén (Inventarios, Kardex, logística, pero NO finanzas)
    assert has_module_permission(RoleEnum.WAREHOUSE_MANAGER.value, "inventory", "adjust") is True
    assert has_module_permission(RoleEnum.WAREHOUSE_MANAGER.value, "inventory", "kardex") is True
    assert has_module_permission(RoleEnum.WAREHOUSE_MANAGER.value, "logistics", "update") is True
    assert has_module_permission(RoleEnum.WAREHOUSE_MANAGER.value, "finance", "read") is False
    assert has_module_permission(RoleEnum.WAREHOUSE_MANAGER.value, "settings", "update") is False

    # 7. Responsable Financiero (Costos COGS, rentabilidad, auditoría SAT, pero NO ajustes físicos de almacén)
    assert has_module_permission(RoleEnum.FINANCIAL_MANAGER.value, "finance", "audit_sat") is True
    assert has_module_permission(RoleEnum.FINANCIAL_MANAGER.value, "finance", "manage_cogs") is True
    assert has_module_permission(RoleEnum.FINANCIAL_MANAGER.value, "orders", "read") is True
    assert has_module_permission(RoleEnum.FINANCIAL_MANAGER.value, "inventory", "adjust") is False
    assert has_module_permission(RoleEnum.FINANCIAL_MANAGER.value, "settings", "update") is False

    # 8. Usuario de Consulta (Solo lectura no sensible)
    assert has_module_permission(RoleEnum.VIEWER.value, "catalog", "read") is True
    assert has_module_permission(RoleEnum.VIEWER.value, "catalog", "create") is False
    assert has_module_permission(RoleEnum.VIEWER.value, "inventory", "adjust") is False
    assert has_module_permission(RoleEnum.VIEWER.value, "finance", "read") is False


def test_granular_permissions_and_module_restrictions():
    """Valida la precedencia de módulos restringidos y permisos personalizados."""
    # Caso 1: Operador con módulo 'orders' expresamente restringido
    allowed = has_module_permission(
        role=RoleEnum.OPERATOR.value,
        module="orders",
        action="read",
        restricted_modules=["orders"],
    )
    assert allowed is False

    # Caso 2: Operador con permiso personalizado para ver finanzas
    allowed_custom = has_module_permission(
        role=RoleEnum.OPERATOR.value,
        module="finance",
        action="read",
        custom_permissions=["finance:read"],
    )
    assert allowed_custom is True

    # Caso 3: Módulo restringido tiene mayor prioridad que permiso personalizado
    blocked_conflict = has_module_permission(
        role=RoleEnum.OPERATOR.value,
        module="finance",
        action="read",
        custom_permissions=["finance:read"],
        restricted_modules=["finance"],
    )
    assert blocked_conflict is False


def test_privilege_escalation_guard():
    """Verifica la prevención estricta de escalamiento de privilegios entre roles."""
    assert can_assign_role(RoleEnum.OPERATOR.value, RoleEnum.COMPANY_ADMIN.value) is False
    assert can_assign_role(RoleEnum.OPERATOR.value, RoleEnum.OPERATOR.value) is False
    assert can_assign_role(RoleEnum.COMPANY_ADMIN.value, RoleEnum.OPERATOR.value) is True
    assert can_assign_role(RoleEnum.COMPANY_ADMIN.value, RoleEnum.DIRECTOR.value) is True
    assert can_assign_role(RoleEnum.COMPANY_ADMIN.value, RoleEnum.PLATFORM_OWNER.value) is False
    assert can_assign_role(RoleEnum.COMPANY_ADMIN.value, RoleEnum.SAAS_ADMIN.value) is False
    assert can_assign_role(RoleEnum.PLATFORM_OWNER.value, RoleEnum.SAAS_ADMIN.value) is True


def test_session_lifecycle_and_revocation(db_session):
    """Prueba el ciclo de vida de sesiones: inicio, verificación, actividad y revocación (cierre de sesión)."""
    tenant = Tenant(name="Grupo Corporativo Alfa", slug="alfa-group")
    db_session.add(tenant)
    db_session.flush()

    user = User(
        tenant_id=tenant.id,
        email="test_session@empresa.com",
        password_hash=hash_password("SuperSecret2026!"),
        full_name="Usuario Sesiones",
        role=RoleEnum.COMPANY_ADMIN.value,
    )
    db_session.add(user)
    db_session.flush()

    jti = str(uuid.uuid4())
    expires = datetime.now(timezone.utc) + timedelta(minutes=60)
    session_obj = UserSession(
        user_id=user.id,
        token_jti=jti,
        ip_address="192.168.1.100",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        device_info="Chrome Windows",
        is_revoked=False,
        expires_at=expires,
        last_activity_at=datetime.now(timezone.utc),
    )
    db_session.add(session_obj)
    db_session.flush()

    retrieved = db_session.query(UserSession).filter_by(token_jti=jti).one()
    assert retrieved.is_revoked is False
    assert retrieved.user_id == user.id

    retrieved.is_revoked = True
    db_session.flush()

    revoked_session = db_session.query(UserSession).filter_by(token_jti=jti).one()
    assert revoked_session.is_revoked is True


def test_password_reset_cryptographic_token_flow(db_session):
    """Verifica el flujo seguro de recuperación de contraseña con tokens criptográficos de un solo uso."""
    import hashlib
    import secrets

    user = User(
        email="reset_target@empresa.com",
        password_hash=hash_password("ClaveVieja123!"),
        full_name="Target Reset",
        role=RoleEnum.OPERATOR.value,
    )
    db_session.add(user)
    db_session.flush()

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires = datetime.now(timezone.utc) + timedelta(hours=1)

    reset_record = PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires,
        is_used=False,
    )
    db_session.add(reset_record)
    db_session.flush()

    lookup = db_session.query(PasswordResetToken).filter_by(
        token_hash=token_hash,
        is_used=False,
    ).one()
    assert lookup.user_id == user.id

    new_password = "NuevaPasswordSegura2026#"
    user.password_hash = hash_password(new_password)
    lookup.is_used = True
    db_session.flush()

    assert verify_password("ClaveVieja123!", user.password_hash) is False
    assert verify_password(new_password, user.password_hash) is True


def test_api_tenant_registration_and_login_flow(api_client):
    """Prueba completa vía API: Registro de Tenant, Empresa y Admin, seguido de Login."""
    # 1. Registro
    reg_payload = {
        "tenant_name": "Logística y Comercio Global S.A.",
        "tenant_slug": "comercio-global",
        "company_legal_name": "Logística y Comercio Global de México S.A. de C.V.",
        "company_rfc": "LCG190412XYZ",
        "admin_email": "director@comercioglobal.mx",
        "admin_password": "PasswordFuerte2026!",
        "admin_full_name": "Alejandro Morales",
    }
    res_reg = api_client.post("/api/v1/auth/register-tenant", json=reg_payload)
    assert res_reg.status_code == 201
    data_reg = res_reg.json()
    assert data_reg["tenant_slug"] == "comercio-global"
    assert data_reg["company_rfc"] == "LCG190412XYZ"
    company_id = data_reg["company_id"]

    # 2. Login con contraseña correcta
    login_payload = {
        "email": "director@comercioglobal.mx",
        "password": "PasswordFuerte2026!",
        "device_info": "MacBook Pro M3",
    }
    res_login = api_client.post("/api/v1/auth/login", json=login_payload)
    assert res_login.status_code == 200
    data_login = res_login.json()
    assert "access_token" in data_login
    token = data_login["access_token"]
    assert len(data_login["authorized_companies"]) == 1
    assert data_login["authorized_companies"][0]["company_id"] == company_id
    assert data_login["authorized_companies"][0]["role"] == "company_admin"

    # 3. Consulta de perfil con token
    res_me = api_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res_me.status_code == 200
    assert res_me.json()["email"] == "director@comercioglobal.mx"

    # 4. Login con contraseña incorrecta
    res_fail = api_client.post("/api/v1/auth/login", json={
        "email": "director@comercioglobal.mx",
        "password": "WrongPassword!"
    })
    assert res_fail.status_code == 401


def test_api_session_logout_and_revocation(api_client):
    """Verifica que el logout invalide inmediatamente la sesión en backend impidiendo reuso del token."""
    # 1. Registrar y loguear
    api_client.post("/api/v1/auth/register-tenant", json={
        "tenant_name": "Pruebas Logout Tenant",
        "tenant_slug": "logout-tenant",
        "company_legal_name": "Logout Corp S.A.",
        "company_rfc": "LGT200101AA1",
        "admin_email": "admin@logoutcorp.com",
        "admin_password": "PasswordSegura123!",
        "admin_full_name": "Admin Logout",
    })
    res_login = api_client.post("/api/v1/auth/login", json={
        "email": "admin@logoutcorp.com",
        "password": "PasswordSegura123!",
    })
    token = res_login.json()["access_token"]
    auth_header = {"Authorization": f"Bearer {token}"}

    # 2. Verificar acceso funcional
    res_me = api_client.get("/api/v1/auth/me", headers=auth_header)
    assert res_me.status_code == 200

    # 3. Listar sesiones activas
    res_sessions = api_client.get("/api/v1/auth/sessions", headers=auth_header)
    assert res_sessions.status_code == 200
    assert len(res_sessions.json()) == 1
    assert res_sessions.json()[0]["is_current"] is True

    # 4. Cierre de sesión (Logout)
    res_logout = api_client.post("/api/v1/auth/logout", headers=auth_header)
    assert res_logout.status_code == 200

    # 5. Intentar reusar el mismo token (debe fallar con 401 Unauthorized)
    res_blocked = api_client.get("/api/v1/auth/me", headers=auth_header)
    assert res_blocked.status_code == 401
    err_msg = res_blocked.json().get("error", "")
    assert "revocada" in err_msg.lower()


def test_api_forgot_and_reset_password_flow(api_client):
    """Verifica el flujo completo de recuperación y cambio de contraseña por API."""
    api_client.post("/api/v1/auth/register-tenant", json={
        "tenant_name": "Tenant Reset Pwd",
        "tenant_slug": "reset-pwd-tenant",
        "company_legal_name": "Reset Pwd Corp",
        "company_rfc": "RPC180512ABC",
        "admin_email": "user@resetpwd.com",
        "admin_password": "ClaveInicial123!",
        "admin_full_name": "User Reset",
    })

    # Solicitar recuperación
    res_forgot = api_client.post("/api/v1/auth/forgot-password", json={"email": "user@resetpwd.com"})
    assert res_forgot.status_code == 200
    reset_token = res_forgot.json()["reset_token_dev"]
    assert reset_token is not None

    # Restablecer contraseña
    res_reset = api_client.post("/api/v1/auth/reset-password", json={
        "token": reset_token,
        "new_password": "NuevaSuperPassword2026#",
    })
    assert res_reset.status_code == 200

    # Login con clave vieja debe fallar
    res_old = api_client.post("/api/v1/auth/login", json={
        "email": "user@resetpwd.com",
        "password": "ClaveInicial123!",
    })
    assert res_old.status_code == 401

    # Login con clave nueva debe tener éxito
    res_new = api_client.post("/api/v1/auth/login", json={
        "email": "user@resetpwd.com",
        "password": "NuevaSuperPassword2026#",
    })
    assert res_new.status_code == 200


def test_api_cross_company_access_attack_blocked(api_client):
    """
    ATAQUE DE ACCESO CRUZADO (Cross-Tenant / Cross-Company IDOR):
    El usuario de Empresa A intenta enviar 'X-Company-ID' o parámetros de Empresa B.
    El backend DEBE rechazar la petición con 403 Forbidden.
    """
    # 1. Crear Empresa 1
    res_a = api_client.post("/api/v1/auth/register-tenant", json={
        "tenant_name": "Grupo Alpha",
        "tenant_slug": "grupo-alpha",
        "company_legal_name": "Alpha Corp S.A.",
        "company_rfc": "ALP100101AA1",
        "admin_email": "admin@alpha.com",
        "admin_password": "PasswordAlpha1!",
        "admin_full_name": "Admin Alpha",
    })
    company_a_id = res_a.json()["company_id"]

    # 2. Crear Empresa 2
    res_b = api_client.post("/api/v1/auth/register-tenant", json={
        "tenant_name": "Grupo Beta",
        "tenant_slug": "grupo-beta",
        "company_legal_name": "Beta Corp S.A.",
        "company_rfc": "BET200202BB2",
        "admin_email": "admin@beta.com",
        "admin_password": "PasswordBeta1!",
        "admin_full_name": "Admin Beta",
    })
    company_b_id = res_b.json()["company_id"]

    # 3. Loguearse como Admin Alpha
    res_login_a = api_client.post("/api/v1/auth/login", json={
        "email": "admin@alpha.com",
        "password": "PasswordAlpha1!",
    })
    token_a = res_login_a.json()["access_token"]

    # 4. Intento de ataque: Admin Alpha envía X-Company-ID de Empresa Beta para consultar pedidos o finanzas
    attack_headers = {
        "Authorization": f"Bearer {token_a}",
        "X-Company-ID": company_b_id,
    }
    res_attack = api_client.get("/api/v1/orders", headers=attack_headers)
    assert res_attack.status_code == 403
    err_msg = res_attack.json().get("error", "")
    assert "no perteneces a la empresa" in err_msg.lower()

    # 5. Intento de ataque en configuración
    res_attack_settings = api_client.get("/api/v1/settings", headers=attack_headers)
    assert res_attack_settings.status_code == 403


def test_api_privilege_escalation_attack_blocked(api_client):
    """
    ATAQUE DE ESCALAMIENTO DE PRIVILEGIOS:
    Un Operador intenta dar de alta una nueva empresa o asignar roles de administración.
    El backend DEBE rechazar la petición con 403 Forbidden.
    """
    # 1. Registrar empresa y obtener admin
    res_reg = api_client.post("/api/v1/auth/register-tenant", json={
        "tenant_name": "Holding Delta",
        "tenant_slug": "holding-delta",
        "company_legal_name": "Delta Operaciones S.A.",
        "company_rfc": "DEL150315XY1",
        "admin_email": "admin@delta.com",
        "admin_password": "PasswordDelta1!",
        "admin_full_name": "Admin Delta",
    })
    company_id = res_reg.json()["company_id"]
    tenant_id = res_reg.json()["tenant_id"]

    res_login_admin = api_client.post("/api/v1/auth/login", json={
        "email": "admin@delta.com",
        "password": "PasswordDelta1!",
    })
    token_admin = res_login_admin.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {token_admin}", "X-Company-ID": company_id}

    # 2. Admin crea un usuario con rol 'operator'
    res_create_op = api_client.post("/api/v1/users", json={
        "tenant_id": tenant_id,
        "email": "operador@delta.com",
        "password": "PasswordOperador1!",
        "full_name": "Operador Delta",
        "role": "operator",
    })
    operator_user_id = res_create_op.json()["id"]

    # Asignarlo a la empresa como operador
    api_client.post(f"/api/v1/companies/{company_id}/users", headers=admin_headers, json={
        "user_id": operator_user_id,
        "role": "operator",
    })

    # 3. Loguearse como Operador
    res_login_op = api_client.post("/api/v1/auth/login", json={
        "email": "operador@delta.com",
        "password": "PasswordOperador1!",
    })
    token_op = res_login_op.json()["access_token"]
    op_headers = {"Authorization": f"Bearer {token_op}", "X-Company-ID": company_id}

    # 4. Intento 1: Operador intenta crear una empresa -> DEBE FALLAR con 403
    res_op_create_company = api_client.post("/api/v1/companies", headers=op_headers, json={
        "tenant_id": tenant_id,
        "legal_name": "Empresa Clandestina S.A.",
        "rfc": "ECL200101AA1",
    })
    assert res_op_create_company.status_code == 403

    # 5. Intento 2: Operador intenta auto-promoverse o asignar rol de Administrador -> DEBE FALLAR con 403
    res_op_escalate = api_client.post(f"/api/v1/companies/{company_id}/users", headers=op_headers, json={
        "user_id": operator_user_id,
        "role": "company_admin",
    })
    assert res_op_escalate.status_code == 403


def test_api_global_admin_private_docs_protection(api_client, tmp_path):
    """
    PROTECCIÓN DE DOCUMENTOS PRIVADOS ANTE ADMINISTRADOR GLOBAL:
    Un Platform Owner o SaaS Admin NO puede consultar pedidos, finanzas ni retenciones
    de una empresa privada a menos que esté expresamente asignado a ella.
    """
    # 1. Crear empresa privada con su admin
    res_reg = api_client.post("/api/v1/auth/register-tenant", json={
        "tenant_name": "Empresa Privada Tenant",
        "tenant_slug": "empresa-privada",
        "company_legal_name": "Confidencial de México S.A.",
        "company_rfc": "CDM150505ZZ9",
        "admin_email": "dueno@confidencial.mx",
        "admin_password": "PasswordPrivado1!",
        "admin_full_name": "Dueño Confidencial",
    })
    company_id = res_reg.json()["company_id"]

    # 2. Crear usuario con rol 'platform_owner' pero SIN membresía en 'Confidencial de México'
    res_owner = api_client.post("/api/v1/users", json={
        "email": "platform_owner_global@saas.com",
        "password": "SuperPlatformPassword2026!",
        "full_name": "Global Platform Owner",
        "role": "platform_owner",
    })
    assert res_owner.status_code == 201

    # 3. Loguearse como Platform Owner
    res_login_owner = api_client.post("/api/v1/auth/login", json={
        "email": "platform_owner_global@saas.com",
        "password": "SuperPlatformPassword2026!",
    })
    token_owner = res_login_owner.json()["access_token"]
    owner_headers = {
        "Authorization": f"Bearer {token_owner}",
        "X-Company-ID": company_id,
    }

    # 4. Platform Owner intenta ver pedidos privados de la empresa privada -> DEBE SER RECHAZADO con 403
    res_private_orders = api_client.get("/api/v1/orders", headers=owner_headers)
    assert res_private_orders.status_code == 403
    err_owner = res_private_orders.json().get("error", "")
    assert "documentos privados" in err_owner.lower()

    # 5. Platform Owner intenta ver configuraciones privadas -> DEBE SER RECHAZADO con 403
    res_private_settings = api_client.get("/api/v1/settings", headers=owner_headers)
    assert res_private_settings.status_code == 403

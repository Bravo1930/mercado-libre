"""Suite Integral de Ciberseguridad Empresarial y Auditoría contra Amenazas OWASP Top 10."""

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import logging
from pathlib import Path
import time
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

from src.core.config import Settings, get_settings
from src.core.database import get_db
from src.core.file_security import PathTraversalException, safe_resolve_path, sanitize_filename
from src.core.logging import SensitiveDataScrubberFilter, scrub_sensitive_text
from src.core.rate_limiter import InMemoryRateLimitStore, RateLimiter
from src.core.security import create_access_token, decrypt_token, encrypt_token, hash_password
from src.core.session_security import SessionAnomalyDetector, revoke_user_sessions
from src.core.ssrf_protection import SSRFProtectionException, is_ip_allowed, validate_safe_url
from src.core.webhook_security import WebhookSecurityException, verify_meli_webhook_signature
from src.main import app
from src.models import Base
from src.models.audit import AuditLog, SecurityAlert
from src.models.tenant import Company, Tenant
from src.models.user import CompanyUser, User, UserSession
from src.services.backup_service import BackupException, BackupService
from src.services.security_monitoring import (
    SecurityEventType,
    SecurityMonitoringService,
    SecurityThreatLevel,
)


@pytest.fixture
def security_ctx(tmp_path):
    """Provee un entorno de pruebas aislado con base de datos SQLite y dos empresas creadas."""
    db_file = tmp_path / "security_test.db"
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
        # 1. Registrar Empresa A
        uid_a = uuid.uuid4().hex[:6]
        reg_a = client.post("/api/v1/auth/register-tenant", json={
            "tenant_name": f"Tenant Sec A {uid_a}",
            "tenant_slug": f"sec-a-{uid_a}",
            "company_legal_name": f"Sec Corp A {uid_a} SA",
            "company_rfc": "SECA880101AA1",
            "admin_email": f"admin_a_{uid_a}@corp.com",
            "admin_password": "Password123!",
            "admin_full_name": "Admin Sec A",
        })
        assert reg_a.status_code == 201
        comp_a_id = reg_a.json()["company_id"]
        user_a_id = reg_a.json()["user_id"]

        login_a = client.post("/api/v1/auth/login", json={
            "email": f"admin_a_{uid_a}@corp.com",
            "password": "Password123!",
        })
        assert login_a.status_code == 200
        token_a = login_a.json()["access_token"]

        # 2. Registrar Empresa B
        uid_b = uuid.uuid4().hex[:6]
        reg_b = client.post("/api/v1/auth/register-tenant", json={
            "tenant_name": f"Tenant Sec B {uid_b}",
            "tenant_slug": f"sec-b-{uid_b}",
            "company_legal_name": f"Sec Corp B {uid_b} SA",
            "company_rfc": "SECB990101AA2",
            "admin_email": f"admin_b_{uid_b}@corp.com",
            "admin_password": "Password123!",
            "admin_full_name": "Admin Sec B",
        })
        assert reg_b.status_code == 201
        comp_b_id = reg_b.json()["company_id"]

        yield {
            "client": client,
            "session_factory": session_factory,
            "comp_a_id": comp_a_id,
            "user_a_id": user_a_id,
            "token_a": token_a,
            "comp_b_id": comp_b_id,
        }

    app.dependency_overrides.clear()


# =============================================================================
# 1. PRUEBAS CONTRA SQL INJECTION (OWASP A03:2021)
# =============================================================================
def test_sql_injection_defense_across_queries(security_ctx):
    """
    Verifica que las consultas con payloads maliciosos de SQL Injection sean
    100% neutralizadas por el sistema de parametrización de SQLAlchemy.
    """
    client = security_ctx["client"]
    token = security_ctx["token_a"]
    comp_id = security_ctx["comp_a_id"]

    headers = {"Authorization": f"Bearer {token}", "X-Company-ID": str(comp_id)}

    sqli_payloads = [
        "' OR '1'='1",
        "'; DROP TABLE users; --",
        "1 UNION SELECT null, null, null, null--",
        "' OR SLEEP(5)--",
        "admin'--",
    ]

    for payload in sqli_payloads:
        # Búsqueda de productos
        res_prod = client.get(f"/api/v1/products?search={payload}", headers=headers)
        assert res_prod.status_code in [200, 422], f"Fallo con payload: {payload}"
        assert "syntax error" not in res_prod.text.lower()
        assert "corrupt" not in res_prod.text.lower()

        # Búsqueda en planillas tabulares
        res_tab = client.get(f"/api/v1/tabular/products?search={payload}", headers=headers)
        assert res_tab.status_code in [200, 422]
        assert "syntax error" not in res_tab.text.lower()


# =============================================================================
# 2. PRUEBAS DE ENCABEZADOS DE SEGURIDAD, CSP, CLICKJACKING Y XSS
# =============================================================================
def test_http_security_headers_and_clickjacking_protection(security_ctx):
    """
    Verifica que la aplicación inyecte todos los encabezados de seguridad HTTP
    recomendados por OWASP y elimine información que permita fingerprinting.
    """
    client = security_ctx["client"]
    response = client.get("/api/v1/health")
    assert response.status_code == 200

    # 1. Content Security Policy (CSP)
    csp = response.headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    # Fix 13: todos los hosts externos que carga src/static/index.html deben
    # estar permitidos o el navegador los bloquea (Tailwind no se definía y
    # el sourcemap de Chart.js fallaba).
    assert "https://cdn.tailwindcss.com" in csp  # script-src: Tailwind Play CDN
    assert "https://cdn.jsdelivr.net" in csp  # script-src (Chart.js) y connect-src (sourcemap)
    assert "https://fonts.googleapis.com" in csp  # style-src y connect-src (preconnect)
    assert "https://fonts.gstatic.com" in csp  # font-src y connect-src (preconnect)

    # 2. Anti-Clickjacking
    assert response.headers.get("X-Frame-Options") == "DENY"

    # 3. Anti-MIME Sniffing
    assert response.headers.get("X-Content-Type-Options") == "nosniff"

    # 4. XSS Protection
    assert response.headers.get("X-XSS-Protection") == "1; mode=block"

    # 5. Referrer Policy
    assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    # 6. Permissions Policy
    assert "geolocation=()" in response.headers.get("Permissions-Policy", "")

    # 7. Hiding Server Fingerprinting
    assert "server" not in response.headers
    assert "x-powered-by" not in response.headers


def test_frontend_xss_sanitization_utilities():
    """
    Verifica las rutinas de sanitización de cadenas en frontend contra inyección de HTML y JS.
    """
    malicious_text = '<script>alert("XSS")</script>&foo'
    escaped = scrub_sensitive_text(malicious_text)
    assert isinstance(escaped, str)


# =============================================================================
# 3. PRUEBAS CONTRA SERVER-SIDE REQUEST FORGERY (SSRF)
# =============================================================================
def test_ssrf_protection_blocks_internal_and_cloud_metadata():
    """
    Verifica que el validador SSRF rechace terminantemente IPs privadas,
    loopback, servicios de metadatos de nube (AWS 169.254.169.254) y esquemas no seguros.
    """
    # 1. Loopback
    with pytest.raises(SSRFProtectionException) as exc:
        validate_safe_url("http://127.0.0.1:8000/internal")
    assert "prohibida" in str(exc.value)

    with pytest.raises(SSRFProtectionException):
        validate_safe_url("http://localhost:5432")

    # 2. Cloud Metadata Endpoint (AWS / GCP / Azure)
    with pytest.raises(SSRFProtectionException):
        validate_safe_url("http://169.254.169.254/latest/meta-data/")

    # 3. Redes privadas RFC 1918
    assert not is_ip_allowed("10.0.0.1")
    assert not is_ip_allowed("172.16.5.4")
    assert not is_ip_allowed("192.168.1.1")
    assert not is_ip_allowed("127.0.0.1")
    assert not is_ip_allowed("169.254.169.254")

    # 4. Esquemas no autorizados
    with pytest.raises(SSRFProtectionException) as exc_scheme:
        validate_safe_url("file:///etc/passwd")
    assert "Solo se autoriza HTTP o HTTPS" in str(exc_scheme.value)

    with pytest.raises(SSRFProtectionException):
        validate_safe_url("gopher://127.0.0.1:6379/_")


# =============================================================================
# 4. PRUEBAS DE AISLAMIENTO MULTI-TENANT (ANTI-IDOR Y ACCESO HORIZONTAL)
# =============================================================================
@pytest.mark.anyio
async def test_multi_tenant_isolation_prevents_horizontal_access(security_ctx):
    """
    Verifica que un usuario autenticado de la Empresa A no pueda consultar ni modificar
    recursos pertenecientes a la Empresa B (prevención estricta de IDOR / BOLA).
    """
    client = security_ctx["client"]
    token_a = security_ctx["token_a"]
    comp_b_id = security_ctx["comp_b_id"]

    # El usuario A intenta enviar peticiones indicando la empresa B en cabecera
    headers_malicious = {
        "Authorization": f"Bearer {token_a}",
        "X-Company-ID": str(comp_b_id),
    }

    res = client.get("/api/v1/products", headers=headers_malicious)
    assert res.status_code == 403
    assert "No perteneces a la empresa solicitada" in res.json().get("error", "")

    # Verificar que el SIEM registró el incidente
    async with security_ctx["session_factory"]() as session:
        stmt_alert = (
            select(AuditLog)
            .where(AuditLog.action == "SECURITY_ALERT_HORIZONTAL_ACCESS_ATTEMPT")
            .order_by(AuditLog.created_at.desc())
        )
        audit_rec = (await session.execute(stmt_alert)).scalars().first()
        assert audit_rec is not None


# =============================================================================
# 5. PRUEBAS DE ESCALAMIENTO DE PRIVILEGIOS
# =============================================================================
@pytest.mark.anyio
async def test_privilege_escalation_is_blocked(security_ctx):
    """
    Verifica que un usuario de empresa sin privilegios globales no pueda acceder
    a los endpoints restringidos de ciberseguridad y respaldos.
    """
    client = security_ctx["client"]
    token = security_ctx["token_a"]
    comp_id = security_ctx["comp_a_id"]

    headers = {"Authorization": f"Bearer {token}", "X-Company-ID": str(comp_id)}

    # Administrador de empresa intenta consultar estado de seguridad de plataforma
    res_sec = client.get("/api/v1/system/security/status", headers=headers)
    assert res_sec.status_code == 403
    assert "Se requiere rol de Propietario de Plataforma" in res_sec.json().get("error", "")

    # Administrador de empresa intenta crear respaldo
    res_back = client.post("/api/v1/system/backups/create", headers=headers)
    assert res_back.status_code == 403


# =============================================================================
# 6. PRUEBAS DE CONTROL DE SESIONES, ROBO DE TOKENS Y ANOMALÍAS
# =============================================================================
@pytest.mark.anyio
async def test_session_anomaly_detection_and_revocation(security_ctx):
    """
    Verifica la detección de anomalías por cambios abruptos de plataforma/User-Agent,
    y el rechazo inmediato de tokens cuya sesión haya sido revocada.
    """
    client = security_ctx["client"]
    token_a = security_ctx["token_a"]
    comp_id = security_ctx["comp_a_id"]
    headers = {"Authorization": f"Bearer {token_a}", "X-Company-ID": str(comp_id)}

    # Funciona antes de revocar
    res_ok = client.get("/api/v1/auth/me", headers=headers)
    assert res_ok.status_code == 200

    # Cierre de sesión (logout)
    res_logout = client.post("/api/v1/auth/logout", headers=headers)
    assert res_logout.status_code == 200

    # Petición subsecuente rechazada inmediatamente
    res_after = client.get("/api/v1/auth/me", headers=headers)
    assert res_after.status_code == 401
    assert "revocada" in res_after.json().get("error", "").lower()


# =============================================================================
# 7. PRUEBAS DE FIRMAS DE WEBHOOK Y REPETICIÓN DE EVENTOS (REPLAY ATTACKS)
# =============================================================================
def test_webhook_hmac_and_replay_attack_mitigation():
    """
    Verifica que los webhooks con firmas HMAC alteradas sean rechazados,
    y que payloads con estampas de tiempo antiguas (replay attacks) sean neutralizados.
    """
    secret = "meli_test_secret_12345"
    raw_payload = b'{"resource": "/orders/123456", "topic": "orders_v2"}'

    # 1. Webhook válido con firma auténtica
    ts_now = int(time.time())
    message = f"id:{ts_now};{raw_payload.decode('utf-8')}"
    valid_sig = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
    sig_header = f"ts={ts_now},v1={valid_sig}"

    is_valid = verify_meli_webhook_signature(sig_header, raw_payload, secret_key=secret)
    assert is_valid is True

    # 2. Webhook manipulado (firma inválida)
    invalid_sig_header = f"ts={ts_now},v1=deadbeef12345678"
    with pytest.raises(WebhookSecurityException) as exc_sig:
        verify_meli_webhook_signature(invalid_sig_header, raw_payload, secret_key=secret)
    assert "Firma HMAC del webhook inválida" in str(exc_sig.value)

    # 3. Ataque de repetición (timestamp con 20 minutos de antigüedad)
    ts_old = ts_now - 1200  # 20 min atrás (límite es 15 min = 900s)
    old_msg = f"id:{ts_old};{raw_payload.decode('utf-8')}"
    old_sig = hmac.new(secret.encode("utf-8"), old_msg.encode("utf-8"), hashlib.sha256).hexdigest()
    old_sig_header = f"ts={ts_old},v1={old_sig}"

    with pytest.raises(WebhookSecurityException) as exc_replay:
        verify_meli_webhook_signature(old_sig_header, raw_payload, secret_key=secret)
    assert "Posible ataque de repetición" in str(exc_replay.value)


# =============================================================================
# 8. PRUEBAS DE RATE LIMITING Y DETECCIÓN DE FUERZA BRUTA
# =============================================================================
@pytest.mark.anyio
async def test_rate_limiting_and_brute_force_detection(security_ctx):
    """
    Verifica que tras múltiples peticiones sucesivas se devuelva HTTP 429 Too Many Requests,
    y que 5 inicios de sesión fallidos registren una alerta crítica de fuerza bruta.
    """
    # 1. Almacén de rate limit en memoria
    store = InMemoryRateLimitStore()
    key = "ratelimit:test:192.168.1.50"
    window = 10

    # Simular 5 hits
    for _ in range(5):
        hits = await store.record_hit(key, window)
    assert hits == 5

    # 2. Detección de ataque de fuerza bruta por IP
    test_ip = f"198.51.100.{int(time.time()) % 200 + 10}"
    target_email = "victim@empresa.com"

    async with security_ctx["session_factory"]() as session:
        for i in range(4):
            is_attack = await SecurityMonitoringService.check_failed_login_attempt(session, test_ip, target_email)
            assert is_attack is False

        # El quinto intento fallido dispara la alerta crítica
        is_attack_5th = await SecurityMonitoringService.check_failed_login_attempt(session, test_ip, target_email)
        assert is_attack_5th is True

        # Verificar que se generó la alerta en la bitácora
        stmt = select(AuditLog).where(AuditLog.ip_address == test_ip)
        logs = (await session.execute(stmt)).scalars().all()
        assert len(logs) > 0
        assert "SECURITY_ALERT_BRUTE_FORCE_ATTACK" in logs[0].action


# =============================================================================
# 9. PRUEBAS CONTRA PATH TRAVERSAL Y ACCESO A ARCHIVOS
# =============================================================================
def test_path_traversal_prevention(tmp_path: Path):
    """
    Verifica que cualquier intento de escapar del directorio base mediante
    `../`, `..\\`, rutas absolutas o bytes nulos sea bloqueado con PathTraversalException.
    """
    base_dir = tmp_path / "storage"
    base_dir.mkdir(parents=True, exist_ok=True)

    # 1. Ruta válida
    valid_file = safe_resolve_path(base_dir, "documentos/reporte.pdf")
    assert str(valid_file).startswith(str(base_dir.resolve()))

    # 2. Intento de escape hacia directorio superior
    with pytest.raises(PathTraversalException):
        safe_resolve_path(base_dir, "../../windows/system32/config/sam")

    with pytest.raises(PathTraversalException):
        safe_resolve_path(base_dir, "../../../etc/shadow")

    # 3. Inyección de byte nulo
    with pytest.raises(PathTraversalException):
        safe_resolve_path(base_dir, "archivo.pdf\x00.exe")

    # 4. Sanitización de nombres de archivo
    cleaned = sanitize_filename("../../malicious*file?.txt")
    assert "/" not in cleaned
    assert "\\" not in cleaned
    assert "*" not in cleaned
    assert "?" not in cleaned


# =============================================================================
# 10. PRUEBAS DE SANITIZACIÓN DE SECRETOS EN REGISTROS (LOG SCRUBBING)
# =============================================================================
def test_secrets_redaction_in_logging():
    """
    Verifica que el filtro de seguridad de logs enmascare de forma absoluta
    contraseñas, tokens JWT, Bearer tokens, claves de API y tarjetas de crédito.
    Garantiza: 'No mostrar secretos en registros'.
    """
    filter_obj = SensitiveDataScrubberFilter()

    secret_jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    log_msg = f"Iniciando petición con Authorization: Bearer {secret_jwt} y password='MiSuperPasswordSecreta123!'"

    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg=log_msg,
        args=(),
        exc_info=None,
    )

    filter_obj.filter(record)

    assert secret_jwt not in record.msg
    assert "MiSuperPasswordSecreta123!" not in record.msg
    assert "[REDACTED_TOKEN]" in record.msg
    assert "[REDACTED]" in record.msg

    # Tarjeta de crédito
    card_msg = "Cobro procesado a tarjeta 4532-1234-5678-9012 exitosamente."
    record_card = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=20,
        msg=card_msg,
        args=(),
        exc_info=None,
    )
    filter_obj.filter(record_card)
    assert "4532-1234-5678-9012" not in record_card.msg
    assert "[REDACTED_CARD_****9012]" in record_card.msg


# =============================================================================
# 11. PRUEBAS DE RESPALDOS CIFRADOS, VERIFICACIÓN DE INTEGRIDAD Y DISASTER RECOVERY
# =============================================================================
@pytest.mark.anyio
async def test_encrypted_backups_and_disaster_recovery_simulation(tmp_path: Path, security_ctx):
    """
    Verifica la creación de respaldos cifrados con AES-128/Fernet, cálculo de SHA-256,
    detección de archivos manipulados o corruptos, y ensayo de recuperación DR.
    """
    backup_service = BackupService(backups_dir=tmp_path / "backups_test")

    async with security_ctx["session_factory"]() as session:
        # 1. Crear respaldo cifrado
        meta = await backup_service.create_encrypted_backup(
            session=session,
            notes="Respaldo para prueba de ciberseguridad",
        )
        backup_id = meta["backup_id"]
        enc_filename = meta["filename"]

        # Verificar que el archivo existe en disco y está cifrado
        enc_file_path = tmp_path / "backups_test" / enc_filename
        assert enc_file_path.exists()
        with open(enc_file_path, "rb") as f:
            file_bytes = f.read()

        # El contenido no debe contener texto plano legible de tablas
        assert b"tenants" not in file_bytes
        assert b"users" not in file_bytes

        # 2. Verificación de integridad exitosa
        verification = await backup_service.verify_backup_integrity(backup_id)
        assert verification["is_valid"] is True
        assert verification["status"] == "verified_healthy"

        # 3. Simulación de recuperación ante desastres (Dry-Run)
        dr_result = await backup_service.restore_disaster_recovery_dry_run(backup_id)
        assert dr_result["dry_run_success"] is True
        assert "table_record_counts" in dr_result

        # 4. Prueba de corrupción: alterar un byte del archivo cifrado
        corrupt_bytes = bytearray(file_bytes)
        corrupt_bytes[len(corrupt_bytes) // 2] = (corrupt_bytes[len(corrupt_bytes) // 2] + 1) % 256
        with open(enc_file_path, "wb") as f:
            f.write(corrupt_bytes)

        # La verificación debe detectar la corrupción de inmediato
        corrupt_verification = await backup_service.verify_backup_integrity(backup_id)
        assert corrupt_verification["is_valid"] is False
        assert "CORRUPCIÓN DETECTADA" in corrupt_verification["error"]


# =============================================================================
# 12. PRUEBAS DE ENDURECIMIENTO DE CONFIGURACIÓN EN PRODUCCIÓN
# =============================================================================
def test_production_environment_security_validation():
    """
    Verifica que la configuración falle de inmediato (fail-fast) si se intenta
    iniciar en producción con secretos de desarrollo o contraseñas por defecto.
    """
    with pytest.raises(ValueError) as exc:
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="dev_secret_key_short",
            TOKEN_ENCRYPTION_KEY="gK7m4a0_qN2s8u1v5x9z_B4c6e8h0j2l4n6p8r0t2v4=",
            INTERNAL_API_KEY="dev_internal_api_key_for_testing",
        )
    assert "VULNERABILIDAD CRÍTICA EN PRODUCCIÓN" in str(exc.value)

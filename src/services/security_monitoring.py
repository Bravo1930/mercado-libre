"""Servicio de Monitoreo de Seguridad (SIEM), Detección de Amenazas y Alertas de Incidentes."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import time
from typing import Any
import uuid

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.audit import record_audit_event
from src.core.logging import get_logger
from src.models.audit import AuditLog, SecurityAlert

logger = get_logger("security_monitoring")


class SecurityThreatLevel:
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SecurityEventType:
    BRUTE_FORCE_ATTACK = "BRUTE_FORCE_ATTACK"
    SQLI_PROBE = "SQLI_PROBE"
    XSS_PROBE = "XSS_PROBE"
    SSRF_ATTEMPT = "SSRF_ATTEMPT"
    PATH_TRAVERSAL_ATTEMPT = "PATH_TRAVERSAL_ATTEMPT"
    HORIZONTAL_ACCESS_ATTEMPT = "HORIZONTAL_ACCESS_ATTEMPT"
    PRIVILEGE_ESCALATION = "PRIVILEGE_ESCALATION"
    SESSION_HIJACK_ALERT = "SESSION_HIJACK_ALERT"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    REPLAY_ATTACK = "REPLAY_ATTACK"


class SecurityMonitoringService:
    """
    Motor central de detección de incidentes, correlación de eventos y generación de alertas de seguridad.
    """

    # Memoria volátil para correlación rápida de ataques de fuerza bruta por IP
    _failed_login_tracker: dict[str, list[float]] = defaultdict(list)

    @classmethod
    async def record_security_incident(
        cls,
        session: AsyncSession,
        event_type: str,
        severity: str,
        description: str,
        source_ip: str | None = None,
        company_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditLog:
        """
        Registra un incidente de seguridad inmutable y dispara una alerta operativa si la severidad es alta o crítica.
        """
        meta_dict = metadata or {}
        meta_dict.update({
            "event_type": event_type,
            "severity": severity,
            "description": description,
            "detected_at": datetime.now(timezone.utc).isoformat(),
        })

        # 1. Registrar en bitácora inmutable de auditoría
        audit_entry = await record_audit_event(
            session=session,
            action=f"SECURITY_ALERT_{event_type}",
            entity_name="SecurityThreat",
            entity_id=source_ip or str(user_id or uuid.uuid4()),
            company_id=company_id,
            user_id=user_id,
            changes=meta_dict,
            ip_address=source_ip,
        )

        # 2. Si la severidad es HIGH o CRITICAL, generar Alerta de Ciberseguridad para el SOC/Administrador
        if severity in [SecurityThreatLevel.HIGH, SecurityThreatLevel.CRITICAL]:
            alert = SecurityAlert(
                company_id=company_id,
                alert_type=f"SECURITY_{event_type}",
                severity=severity,
                title=f"Alerta de Ciberseguridad: {event_type}",
                description=f"[{severity}] {description} (Origen IP: {source_ip or 'Desconocida'})",
                source_ip=source_ip,
                user_id=user_id,
                status="OPEN",
            )
            session.add(alert)
            await session.flush()

        # Comprometer inmediatamente para que los registros de ciberseguridad sobrevivan a rollbacks
        try:
            await session.commit()
        except Exception:
            pass

        logger.warning(
            f"INCIDENTE DE CIBERSEGURIDAD [{severity}] {event_type} - IP={source_ip}: {description}"
        )
        return audit_entry

    @classmethod
    async def check_failed_login_attempt(
        cls,
        session: AsyncSession,
        source_ip: str,
        email_attempted: str,
    ) -> bool:
        """
        Registra un intento fallido de autenticación.
        Si se superan 5 intentos fallidos en menos de 10 minutos desde la misma IP,
        se clasifica como ataque de fuerza bruta activo (BRUTE_FORCE_ATTACK).
        """
        now = time.time()
        window_seconds = 600  # 10 minutos
        cutoff = now - window_seconds

        hits = [t for t in cls._failed_login_tracker[source_ip] if t > cutoff]
        hits.append(now)
        cls._failed_login_tracker[source_ip] = hits

        if len(hits) >= 5:
            await cls.record_security_incident(
                session=session,
                event_type=SecurityEventType.BRUTE_FORCE_ATTACK,
                severity=SecurityThreatLevel.CRITICAL,
                description=f"Se detectaron {len(hits)} intentos fallidos de autenticación en menos de 10 minutos hacia '{email_attempted}'.",
                source_ip=source_ip,
                metadata={"total_failed_attempts": len(hits), "target_email": email_attempted},
            )
            return True

        return False

    @classmethod
    async def get_security_posture_summary(
        cls,
        session: AsyncSession,
        company_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """
        Retorna el estado de postura de ciberseguridad, incidentes detectados y métricas de amenazas.
        """
        stmt = (
            select(AuditLog)
            .where(AuditLog.action.like("SECURITY_ALERT_%"))
            .order_by(desc(AuditLog.created_at))
            .limit(50)
        )
        if company_id:
            stmt = stmt.where(AuditLog.company_id == company_id)

        incidents = (await session.execute(stmt)).scalars().all()

        breakdown = defaultdict(int)
        severity_counts = defaultdict(int)

        recent_logs = []
        for inc in incidents:
            action = inc.action.replace("SECURITY_ALERT_", "")
            breakdown[action] += 1
            changes = {}
            if inc.changes_json:
                try:
                    changes = json.loads(inc.changes_json)
                except Exception:
                    pass
            sev = changes.get("severity", SecurityThreatLevel.MEDIUM)
            severity_counts[sev] += 1

            recent_logs.append({
                "id": str(inc.id),
                "event_type": action,
                "severity": sev,
                "description": changes.get("description", "Incidente de seguridad registrado"),
                "ip_address": inc.ip_address,
                "created_at": inc.created_at.isoformat() if inc.created_at else None,
            })

        return {
            "status": "monitored",
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "total_incidents_recorded": len(incidents),
            "threat_breakdown": dict(breakdown),
            "severity_counts": dict(severity_counts),
            "recent_incidents": recent_logs[:15],
            "defenses_active": [
                "SQL_INJECTION_PARAMETRIZED_DEFENSE",
                "STRICT_CSP_AND_SECURITY_HEADERS",
                "ENTERPRISE_SLIDING_WINDOW_RATE_LIMITING",
                "OUTBOUND_SSRF_NETWORK_BLOCKING",
                "MULTI_TENANT_IDOR_ISOLATION",
                "PATH_TRAVERSAL_CANONICALIZATION",
                "WEBHOOK_HMAC_AND_ANTI_REPLAY_SHIELD",
                "SESSION_ANOMALY_DETECTOR",
                "AES_256_FERNET_ENCRYPTED_BACKUPS",
                "AUTOMATED_SECRET_REDACTION_IN_LOGS",
            ],
        }

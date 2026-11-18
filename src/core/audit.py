"""Servicio centralizado de auditoría para trazabilidad de eventos."""

import json
import uuid
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit import AuditLog


async def record_audit_event(
    session: AsyncSession,
    company_id: uuid.UUID,
    action: str,
    entity_name: str,
    entity_id: str,
    changes: dict[str, Any] | None = None,
    user_id: uuid.UUID | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """Registra un evento inmutable en el log central de auditoría del ERP."""
    audit_entry = AuditLog(
        company_id=company_id,
        user_id=user_id,
        action=action,
        entity_name=entity_name,
        entity_id=entity_id,
        changes_json=json.dumps(changes, default=str) if changes else None,
        ip_address=ip_address,
    )
    session.add(audit_entry)
    await session.flush()
    return audit_entry

"""API REST para Consulta de Pistas de Auditoría (Audit Logs)."""

import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_context import CompanyContext, require_company_permission
from src.core.database import get_db
from src.core.pagination import Page, PaginationParams
from src.core.permissions import ActionEnum, ModuleEnum
from src.models.audit import AuditLog
from src.repositories.base import BaseRepository
from src.schemas.supplier import AuditLogResponse

router = APIRouter(prefix="/audit", tags=["Auditoría & Trazabilidad"])
audit_repo = BaseRepository[AuditLog](AuditLog)


@router.get("", response_model=Page[AuditLogResponse])
async def list_audit_logs(
    action: str | None = Query(None, description="Filtrar por acción (CREATE, UPDATE, DELETE, etc.)"),
    entity_name: str | None = Query(None, description="Filtrar por nombre de entidad"),
    params: PaginationParams = Depends(),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.AUDIT, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> Page[AuditLog]:
    """Consulta la pista inmutable de eventos y cambios realizados dentro de la empresa activa."""
    filters = [AuditLog.company_id == ctx.company_id]
    if action:
        filters.append(AuditLog.action == action)
    if entity_name:
        filters.append(AuditLog.entity_name == entity_name)

    return await audit_repo.get_paginated(session, params, *filters)

"""API REST para el Motor de Sincronización, Conciliación Periódica y Monitor MeLi."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_context import CompanyContext, require_company_permission
from src.core.database import get_db
from src.core.exceptions import EntityNotFoundException, PermissionDeniedException
from src.core.pagination import Page, PaginationParams, paginate_query
from src.core.permissions import ActionEnum, ModuleEnum
from src.models.meli_account import MeliAccount
from src.models.sync import SyncEvent, SyncReconciliationLog
from src.schemas.sync import (
    SyncEventResponse,
    SyncMonitorResponse,
    SyncReconcileRequest,
    SyncReconcileResponse,
)
from src.services.sync_service import SyncService

router = APIRouter(prefix="/sync", tags=["Motor de Sincronización"])
sync_service = SyncService()


@router.get("/monitor", response_model=SyncMonitorResponse)
async def get_sync_monitor_metrics(
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.MELI_ACCOUNTS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> SyncMonitorResponse:
    """
    Retorna métricas operativas del motor de sincronización para la empresa activa:
    - Última sincronización exitosa.
    - Total de eventos recibidos, procesados, pendientes y fallidos.
    - Conteo de reintentos y discrepancias detectadas por conciliación.
    - Distribución por tópico oficial y por estado.
    """
    metrics = await sync_service.get_monitor_metrics(session, ctx.company_id)
    return SyncMonitorResponse(**metrics)


@router.get("/events", response_model=Page[SyncEventResponse])
async def list_sync_events(
    topic: str | None = Query(None, description="Filtrar por tópico oficial (e.g. orders_v2, items, payments)"),
    event_status: str | None = Query(None, alias="status", description="Filtrar por estado (pending, processed, failed, duplicate)"),
    meli_account_id: uuid.UUID | None = Query(None, description="Filtrar por cuenta de Mercado Libre"),
    params: PaginationParams = Depends(),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.MELI_ACCOUNTS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> Page[SyncEvent]:
    """Lista eventos de sincronización registrados y recibidos para la empresa activa."""
    stmt = select(SyncEvent).where(SyncEvent.company_id == ctx.company_id)

    if topic:
        stmt = stmt.where(SyncEvent.topic == topic)
    if event_status:
        stmt = stmt.where(SyncEvent.status == event_status)
    if meli_account_id:
        stmt = stmt.where(SyncEvent.meli_account_id == meli_account_id)

    stmt = stmt.order_by(SyncEvent.created_at.desc())
    items, total = await paginate_query(stmt, session, params)
    return Page.create(items, total, params)


@router.post("/events/{event_id}/retry", status_code=status.HTTP_200_OK)
async def retry_sync_event(
    event_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.MELI_ACCOUNTS, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Fuerza el reintento de procesamiento de un evento fallido o pendiente."""
    event = await session.get(SyncEvent, event_id)
    if not event or event.company_id != ctx.company_id:
        raise EntityNotFoundException("Evento de Sincronización", "id", str(event_id))

    event.status = "pending"
    await session.flush()

    success = await sync_service.process_sync_event(session, event.id)
    await session.commit()

    return {
        "status": "retried",
        "success": success,
        "event_id": str(event.id),
        "event_status": event.status,
        "error_message": event.error_message,
    }


@router.post("/reconcile", response_model=list[SyncReconcileResponse])
async def trigger_reconciliation(
    payload: SyncReconcileRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.MELI_ACCOUNTS, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> list[SyncReconciliationLog]:
    """
    Ejecuta el ciclo de conciliación periódica activa e independiente de webhooks.
    Inspecciona en MeLi las órdenes y estados para recuperar notificaciones perdidas.
    """
    results: list[SyncReconciliationLog] = []

    if payload.meli_account_id:
        # Conciliar cuenta específica
        acc = await session.get(MeliAccount, payload.meli_account_id)
        if not acc or acc.company_id != ctx.company_id:
            raise EntityNotFoundException("Cuenta Mercado Libre", "id", str(payload.meli_account_id))
        log = await sync_service.reconcile_account(session, acc.id, payload.lookback_hours)
        results.append(log)
    else:
        # Conciliar todas las cuentas activas de la empresa
        stmt = select(MeliAccount).where(
            MeliAccount.company_id == ctx.company_id,
            MeliAccount.is_active == True,
        )
        accounts = (await session.execute(stmt)).scalars().all()
        for acc in accounts:
            log = await sync_service.reconcile_account(session, acc.id, payload.lookback_hours)
            results.append(log)

    await session.commit()
    return results


@router.get("/reconciliation-logs", response_model=Page[SyncReconcileResponse])
async def list_reconciliation_logs(
    meli_account_id: uuid.UUID | None = Query(None, description="Filtrar por cuenta MeLi"),
    params: PaginationParams = Depends(),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.MELI_ACCOUNTS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> Page[SyncReconciliationLog]:
    """Lista historial de ciclos de conciliación periódica y auditoría de discrepancias."""
    stmt = select(SyncReconciliationLog).where(SyncReconciliationLog.company_id == ctx.company_id)
    if meli_account_id:
        stmt = stmt.where(SyncReconciliationLog.meli_account_id == meli_account_id)

    stmt = stmt.order_by(SyncReconciliationLog.started_at.desc())
    items, total = await paginate_query(stmt, session, params)
    return Page.create(items, total, params)

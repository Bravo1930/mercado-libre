"""
Rutas API REST para el Motor de Automatización Empresarial (ECA).
"""

from datetime import datetime, timezone
from typing import Any
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_context import CompanyContext, require_company_permission
from src.core.database import get_db
from src.core.permissions import ActionEnum, ModuleEnum
from src.schemas.automation import (
    AutomationConfigResponse,
    AutomationConfigUpdateRequest,
    AutomationExecutionResponse,
    AutomationRuleCreate,
    AutomationRuleResponse,
    AutomationRuleUpdate,
    AutomationStatsResponse,
    ExecutionApprovalRequest,
    ExecutionRollbackResponse,
    TriggerEventRequest,
    TriggerEventResponse,
)
from src.services.automation.engine import AutomationEngineService

router = APIRouter(prefix="/automation", tags=["Motor de Automatización Empresarial (ECA)"])
engine_service = AutomationEngineService()


# ---------------------------------------------------------------------------
# 1. CONFIGURACIÓN GLOBAL E INTERRUPTOR GENERAL
# ---------------------------------------------------------------------------

@router.get("/config", response_model=AutomationConfigResponse)
async def get_automation_config(
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
):
    """Consulta la configuración del motor, interruptor general y modalidades por módulo."""
    cfg = await engine_service.get_or_create_config(session, ctx.company_id)
    return cfg


@router.put("/config", response_model=AutomationConfigResponse)
async def update_automation_config(
    payload: AutomationConfigUpdateRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
):
    """Modifica el interruptor general (Kill Switch), modos por módulo y umbrales de salvaguarda."""
    cfg = await engine_service.update_config(session, ctx.company_id, payload)
    await session.commit()
    return cfg


# ---------------------------------------------------------------------------
# 2. REGLAS DE AUTOMATIZACIÓN (CRUD)
# ---------------------------------------------------------------------------

@router.get("/rules", response_model=list[AutomationRuleResponse])
async def list_automation_rules(
    module: str | None = Query(None, description="Filtrar por módulo"),
    trigger_event: str | None = Query(None, description="Filtrar por evento"),
    is_active: bool | None = Query(None, description="Filtrar por estatus activo"),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
):
    """Lista las reglas ECA configuradas para la empresa."""
    return await engine_service.list_rules(
        session=session,
        company_id=ctx.company_id,
        module=module,
        trigger_event=trigger_event,
        is_active=is_active,
    )


@router.post("/rules", response_model=AutomationRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_automation_rule(
    payload: AutomationRuleCreate,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.CREATE)),
    session: AsyncSession = Depends(get_db),
):
    """Crea una nueva regla ECA con disparadores, condiciones y acciones controladas."""
    rule = await engine_service.create_rule(session, ctx.company_id, payload)
    await session.commit()
    return rule


@router.get("/rules/{rule_id}", response_model=AutomationRuleResponse)
async def get_automation_rule(
    rule_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
):
    """Obtiene el detalle completo de una regla de automatización."""
    return await engine_service.get_rule(session, ctx.company_id, rule_id)


@router.put("/rules/{rule_id}", response_model=AutomationRuleResponse)
async def update_automation_rule(
    rule_id: uuid.UUID,
    payload: AutomationRuleUpdate,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
):
    """Modifica parámetros, condiciones o límites de una regla."""
    rule = await engine_service.update_rule(session, ctx.company_id, rule_id, payload)
    await session.commit()
    return rule


@router.delete("/rules/{rule_id}", status_code=status.HTTP_200_OK)
async def delete_automation_rule(
    rule_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.DELETE)),
    session: AsyncSession = Depends(get_db),
):
    """Elimina una regla de automatización."""
    await engine_service.delete_rule(session, ctx.company_id, rule_id)
    await session.commit()
    return {"success": True, "message": "Regla eliminada exitosamente."}


@router.post("/rules/{rule_id}/execute", response_model=AutomationExecutionResponse)
async def execute_rule_manually(
    rule_id: uuid.UUID,
    custom_payload: dict[str, Any] | None = None,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
):
    """Fuerza la ejecución manual bajo demanda de una regla ECA."""
    execution = await engine_service.execute_rule_manually(session, ctx.company_id, rule_id, custom_payload)
    await session.commit()
    return execution


@router.post("/rules/{rule_id}/reset-circuit-breaker", response_model=AutomationRuleResponse)
async def reset_rule_circuit_breaker(
    rule_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
):
    """Reactiva una regla que fue pausada por el circuit breaker tras errores consecutivos."""
    rule = await engine_service.reset_circuit_breaker(session, ctx.company_id, rule_id)
    await session.commit()
    return rule


# ---------------------------------------------------------------------------
# 3. DISPARO DE EVENTOS (EVENT DISPATCH & DEDUPLICATION)
# ---------------------------------------------------------------------------

@router.post("/events/trigger", response_model=TriggerEventResponse)
async def trigger_automation_event(
    payload: TriggerEventRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
):
    """
    Emite un evento de dominio en el motor de automatización con deduplicación e idempotencia.
    Ejemplos: ORDER_CREATED, ORDER_CONFIRMED, STOCK_LOW, STOCK_DEPLETED, etc.
    """
    res = await engine_service.trigger_event(
        session=session,
        company_id=ctx.company_id,
        event_name=payload.event_name,
        payload=payload.payload,
        event_id=payload.event_id,
        idempotency_key=payload.idempotency_key,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
    )
    await session.commit()
    return res


# ---------------------------------------------------------------------------
# 4. HISTORIAL DE EJECUCIONES Y AUDITORÍA
# ---------------------------------------------------------------------------

@router.get("/executions", response_model=list[AutomationExecutionResponse])
async def list_automation_executions(
    rule_id: uuid.UUID | None = Query(None, description="Filtrar por regla"),
    status: str | None = Query(None, description="Filtrar por estado (success, pending_approval, dead_letter, etc.)"),
    trigger_event: str | None = Query(None, description="Filtrar por evento"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
):
    """Consulta la bitácora inmutable de ejecuciones del motor."""
    items, _ = await engine_service.list_executions(
        session=session,
        company_id=ctx.company_id,
        rule_id=rule_id,
        status=status,
        trigger_event=trigger_event,
        offset=offset,
        limit=limit,
    )
    return items


@router.get("/executions/{execution_id}", response_model=AutomationExecutionResponse)
async def get_automation_execution(
    execution_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
):
    """Consulta los detalles de una ejecución incluyendo snapshot de condiciones y resultados."""
    return await engine_service.get_execution(session, ctx.company_id, execution_id)


@router.post("/executions/{execution_id}/approve", response_model=AutomationExecutionResponse)
async def approve_automation_execution(
    execution_id: uuid.UUID,
    payload: ExecutionApprovalRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
):
    """Autoriza la ejecución de una acción que estaba en modo 'approval_required'."""
    if payload.action == "reject":
        res = await engine_service.reject_execution(session, ctx.company_id, execution_id, ctx.user_id, payload.notes)
    else:
        res = await engine_service.approve_execution(session, ctx.company_id, execution_id, ctx.user_id, payload.notes)
    await session.commit()
    return res


@router.post("/executions/{execution_id}/reject", response_model=AutomationExecutionResponse)
async def reject_automation_execution(
    execution_id: uuid.UUID,
    payload: ExecutionApprovalRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
):
    """Rechaza una ejecución pendiente de aprobación."""
    res = await engine_service.reject_execution(session, ctx.company_id, execution_id, ctx.user_id, payload.notes)
    await session.commit()
    return res


@router.post("/executions/{execution_id}/rollback", response_model=ExecutionRollbackResponse)
async def rollback_automation_execution(
    execution_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
):
    """
    Revierte y compensa una acción exitosa cuando sea técnicamente posible.
    Ejemplo: anular reserva de stock, reactivar publicación pausada, cancelar tarea logística.
    """
    success, msg, r_result = await engine_service.rollback_execution(session, ctx.company_id, execution_id)
    await session.commit()
    return ExecutionRollbackResponse(
        execution_id=execution_id,
        success=success,
        message=msg,
        rollback_result=r_result,
        executed_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# 5. ESTADÍSTICAS Y SALUD DEL MOTOR
# ---------------------------------------------------------------------------

@router.get("/stats", response_model=AutomationStatsResponse)
async def get_automation_stats(
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
):
    """Retorna métricas consolidadas, estado de circuit breakers y ejecuciones del día."""
    return await engine_service.get_stats(session, ctx.company_id)

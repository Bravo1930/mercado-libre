"""
Esquemas Pydantic para el Motor de Automatización Empresarial (ECA).
"""

from datetime import datetime
from typing import Any, Literal
import uuid

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# CONDICIONES Y SALVAGUARDAS
# ---------------------------------------------------------------------------

class ConditionDefinition(BaseModel):
    """Definición individual de una condición lógica evaluable."""
    field: str = Field(..., description="Ruta del campo en notación punto (e.g. 'order.total_amount', 'variant.stock_available')")
    operator: Literal["eq", "neq", "gt", "gte", "lt", "lte", "in", "nin", "contains", "between", "is_null", "is_not_null"] = Field(
        ..., description="Operador de comparación seguro"
    )
    value: Any = Field(None, description="Valor esperado o lista de valores a comparar")


class SafetyLimits(BaseModel):
    """Límites de salvaguarda y circuit breaker para reglas automáticas."""
    min_price: float | None = Field(None, description="Precio piso absoluto en MXN")
    min_margin_pct: float | None = Field(None, description="Margen neto mínimo exigido (e.g. 15.0)")
    max_discount_pct: float | None = Field(None, description="Descuento máximo tolerado (e.g. 35.0)")
    max_executions_per_hour: int = Field(60, ge=1, le=1000, description="Límite horario para evitar bucles o inundación")
    cooldown_seconds: int = Field(30, ge=0, le=3600, description="Tiempo de espera mínimo entre disparos de la misma entidad")


# ---------------------------------------------------------------------------
# CONFIGURACIÓN GLOBAL E INTERRUPTOR GENERAL
# ---------------------------------------------------------------------------

class AutomationConfigUpdateRequest(BaseModel):
    """Actualización del interruptor general y modos por módulo."""
    is_engine_active: bool | None = Field(None, description="Interruptor general (Global Kill Switch) del motor")
    module_modes: dict[str, Literal["manual", "automatic", "approval_required"]] | None = Field(
        None, description="Modalidad de ejecución por módulo (inventory, pricing, promotions, logistics, procurement, reports, spreadsheets)"
    )
    daily_execution_limit: int | None = Field(None, ge=10, le=50000)
    circuit_breaker_error_threshold: int | None = Field(None, ge=1, le=50)
    cooldown_seconds_default: int | None = Field(None, ge=0, le=3600)
    max_retries_default: int | None = Field(None, ge=0, le=10)


class AutomationConfigResponse(BaseModel):
    """Configuración vigente del motor de automatización."""
    model_config = ConfigDict(from_attributes=True)

    company_id: uuid.UUID
    is_engine_active: bool
    module_modes: dict[str, str]
    daily_execution_limit: int
    executions_today: int
    circuit_breaker_error_threshold: int
    cooldown_seconds_default: int
    max_retries_default: int
    updated_at: datetime


# ---------------------------------------------------------------------------
# REGLAS ECA (EVENT - CONDITION - ACTION)
# ---------------------------------------------------------------------------

class AutomationRuleCreate(BaseModel):
    """Creación de una nueva regla ECA."""
    name: str = Field(..., min_length=3, max_length=120)
    description: str | None = Field(None, max_length=500)
    module: Literal["inventory", "pricing", "promotions", "logistics", "procurement", "reports", "spreadsheets", "finance", "general"] = Field(
        "general", description="Módulo al que pertenece la regla"
    )
    trigger_type: Literal["event", "schedule", "manual"] = Field("event", description="Tipo de activador")
    trigger_event: str | None = Field(
        None,
        description="Nombre oficial del evento disparador (e.g. ORDER_CREATED, STOCK_LOW, PRICE_CHANGE_REQUESTED)",
    )
    cron_expression: str | None = Field(None, max_length=50, description="Expresión cron si trigger_type='schedule'")
    interval_minutes: int | None = Field(None, ge=1, le=1440, description="Intervalo en minutos si trigger_type='schedule'")
    conditions: list[ConditionDefinition] = Field(default_factory=list, description="Lista de condiciones a verificar")
    condition_match_type: Literal["ALL", "ANY"] = Field("ALL", description="ALL para operador AND; ANY para operador OR")
    action_type: Literal[
        "RESERVE_INVENTORY",
        "CONFIRM_INVENTORY_DEDUCTION",
        "CREATE_OPERATIONAL_ALERT",
        "SYNC_MELI_ITEM_STATUS",
        "CREATE_LOGISTICS_TASK",
        "BLOCK_PRICE_CHANGE",
        "UPDATE_TABULAR_SHEET",
        "GENERATE_DAILY_REPORT",
        "CREATE_RESTOCK_SUGGESTION",
        "CUSTOM_ACTION",
    ] = Field(..., description="Tipo oficial de acción a ejecutar")
    action_parameters: dict[str, Any] = Field(default_factory=dict, description="Parámetros específicos requeridos por la acción")
    execution_mode: Literal["default_by_module", "manual", "automatic", "approval_required"] = Field(
        "default_by_module", description="Modalidad de ejecución para esta regla específica"
    )
    safety_limits: dict[str, Any] = Field(default_factory=dict, description="Salvaguardas de precio, margen y límites horarios")
    max_retries: int = Field(3, ge=0, le=10)
    retry_backoff_base_sec: int = Field(2, ge=1, le=10)
    is_active: bool = Field(True)


class AutomationRuleUpdate(BaseModel):
    """Actualización de campos en una regla ECA."""
    name: str | None = Field(None, min_length=3, max_length=120)
    description: str | None = None
    module: Literal["inventory", "pricing", "promotions", "logistics", "procurement", "reports", "spreadsheets", "finance", "general"] | None = None
    trigger_type: Literal["event", "schedule", "manual"] | None = None
    trigger_event: str | None = None
    cron_expression: str | None = None
    interval_minutes: int | None = None
    conditions: list[ConditionDefinition] | None = None
    condition_match_type: Literal["ALL", "ANY"] | None = None
    action_type: str | None = None
    action_parameters: dict[str, Any] | None = None
    execution_mode: Literal["default_by_module", "manual", "automatic", "approval_required"] | None = None
    safety_limits: dict[str, Any] | None = None
    max_retries: int | None = None
    is_active: bool | None = None


class AutomationRuleResponse(BaseModel):
    """Detalle completo de una regla de automatización con métricas."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    description: str | None = None
    module: str
    trigger_type: str
    trigger_event: str | None = None
    cron_expression: str | None = None
    interval_minutes: int | None = None
    conditions: list[dict[str, Any]]
    condition_match_type: str
    action_type: str
    action_parameters: dict[str, Any]
    execution_mode: str
    safety_limits: dict[str, Any]
    max_retries: int
    retry_backoff_base_sec: int
    is_active: bool
    is_paused_by_circuit_breaker: bool
    consecutive_errors: int
    last_triggered_at: datetime | None = None
    total_executions: int
    successful_executions: int
    failed_executions: int
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# DISPARO DE EVENTOS (EVENT DISPATCH)
# ---------------------------------------------------------------------------

class TriggerEventRequest(BaseModel):
    """Solicitud de emisión de evento en el motor de automatización."""
    event_name: str = Field(..., description="Nombre del evento (e.g. ORDER_CREATED, STOCK_LOW, SALE_PROCESSED)")
    event_id: str | None = Field(None, description="Identificador único del evento para control de duplicados e idempotencia")
    idempotency_key: str | None = Field(None, description="Clave de idempotencia única")
    entity_type: str | None = Field(None, description="Tipo de entidad asociada (order, variant, inventory, etc.)")
    entity_id: str | None = Field(None, description="ID de la entidad asociada")
    payload: dict[str, Any] = Field(default_factory=dict, description="Datos contextuales del evento")


class TriggerEventResponse(BaseModel):
    """Resultado del despacho de evento en el motor ECA."""
    event_id: str
    dispatched: bool
    engine_active: bool
    matched_rules_count: int
    executions: list[dict[str, Any]]
    message: str


# ---------------------------------------------------------------------------
# EJECUCIONES Y AUDITORÍA INMUTABLE
# ---------------------------------------------------------------------------

class AutomationExecutionResponse(BaseModel):
    """Detalle completo de una ejecución del motor."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    rule_id: uuid.UUID | None = None
    trigger_type: str
    trigger_event: str | None = None
    event_id: str | None = None
    idempotency_key: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    event_payload: dict[str, Any]
    conditions_snapshot: list[dict[str, Any]]
    conditions_met: bool
    status: str
    approval_status: str
    approved_by_user_id: uuid.UUID | None = None
    approved_at: datetime | None = None
    rejection_reason: str | None = None
    action_executed: str
    action_parameters: dict[str, Any]
    action_result: dict[str, Any] | None = None
    error_message: str | None = None
    retry_count: int
    max_retries: int
    execution_time_ms: int
    can_rollback: bool
    is_rolled_back: bool
    rollback_payload: dict[str, Any] | None = None
    rollback_executed_at: datetime | None = None
    rollback_result: dict[str, Any] | None = None
    created_at: datetime
    completed_at: datetime | None = None


class ExecutionApprovalRequest(BaseModel):
    """Autorización o rechazo humano para ejecuciones en pending_approval."""
    action: Literal["approve", "reject"] = Field(..., description="Aprobar para ejecutar o rechazar para descartar")
    notes: str | None = Field(None, description="Justificación o notas de la decisión")


class ExecutionRollbackResponse(BaseModel):
    """Resultado de la reversión / compensación de una acción."""
    execution_id: uuid.UUID
    success: bool
    message: str
    rollback_result: dict[str, Any] | None = None
    executed_at: datetime


# ---------------------------------------------------------------------------
# ESTADÍSTICAS Y SALUD DEL MOTOR
# ---------------------------------------------------------------------------

class AutomationStatsResponse(BaseModel):
    """Métricas operativas del motor de automatización."""
    is_engine_active: bool
    total_rules: int
    active_rules: int
    circuit_breakers_active: int
    total_executions_today: int
    successful_executions_today: int
    failed_executions_today: int
    dead_letter_count_today: int
    pending_approvals_count: int
    executions_by_module: dict[str, int]

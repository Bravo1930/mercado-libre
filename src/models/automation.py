"""
Modelos del Motor de Automatización Empresarial (ECA: Eventos, Condiciones y Acciones).

Permite la orquestación desatendida y segura de flujos operativos en el ERP:
- Disparadores basados en eventos de dominio y programaciones (Cron/Intervalos).
- Evaluación segura de condiciones y salvaguardas de negocio.
- Acciones transaccionales con compensación y reversión (Rollback).
- Modalidades de ejecución: Manual, Automática y Automática con Aprobación Previa.
- Interruptor general (Global Kill Switch) y modos granulares por módulo.
- Deduplicación de eventos (Idempotencia), reintentos con backoff exponencial y Dead-Letter Queue.
- Circuit breaker ante fallos repetitivos.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
import uuid

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import GUID, Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.tenant import Company
    from src.models.user import User


class AutomationConfig(Base, TimestampMixin):
    """
    Configuración global y políticas de gobernanza del motor de automatización por empresa.
    """

    __tablename__ = "automation_configs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )

    # Interruptor general del motor (Global Kill Switch)
    is_engine_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Modalidades configurables por módulo: "manual", "automatic", "approval_required"
    # Módulos: inventory, pricing, promotions, logistics, procurement, reports, spreadsheets
    module_modes: Mapped[dict[str, str]] = mapped_column(
        JSON,
        default=lambda: {
            "inventory": "automatic",
            "pricing": "approval_required",
            "promotions": "approval_required",
            "logistics": "automatic",
            "procurement": "approval_required",
            "reports": "automatic",
            "spreadsheets": "automatic",
        },
        nullable=False,
    )

    daily_execution_limit: Mapped[int] = mapped_column(Integer, default=5000, nullable=False)
    executions_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_reset_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    circuit_breaker_error_threshold: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    cooldown_seconds_default: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    max_retries_default: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    company: Mapped["Company"] = relationship("Company")


class AutomationRule(Base, TimestampMixin):
    """
    Definición formal de una regla ECA (Event - Condition - Action).
    """

    __tablename__ = "automation_rules"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Módulo de pertenencia: inventory, pricing, promotions, logistics, procurement, reports, spreadsheets, general
    module: Mapped[str] = mapped_column(String(50), default="general", nullable=False, index=True)

    # Tipo de disparador: "event", "schedule", "manual"
    trigger_type: Mapped[str] = mapped_column(String(30), default="event", nullable=False, index=True)

    # Nombre del evento disparador:
    # ORDER_CREATED, ORDER_CONFIRMED, STOCK_LOW, STOCK_DEPLETED, LABEL_READY,
    # PROMOTION_EXPIRING_SOON, PRICE_CHANGE_REQUESTED, SALE_PROCESSED, END_OF_DAY, SURGING_DEMAND
    trigger_event: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)

    # Programación opcional para trigger_type="schedule"
    cron_expression: Mapped[str | None] = mapped_column(String(50), nullable=True)
    interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Condiciones estructuradas en formato JSON:
    # [{"field": "order.total_amount", "operator": "gte", "value": 500.0}, ...]
    conditions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    condition_match_type: Mapped[str] = mapped_column(String(10), default="ALL", nullable=False)  # ALL (AND) o ANY (OR)

    # Tipo de acción oficial:
    # RESERVE_INVENTORY, CONFIRM_INVENTORY_DEDUCTION, CREATE_OPERATIONAL_ALERT,
    # SYNC_MELI_ITEM_STATUS, CREATE_LOGISTICS_TASK, BLOCK_PRICE_CHANGE,
    # UPDATE_TABULAR_SHEET, GENERATE_DAILY_REPORT, CREATE_RESTOCK_SUGGESTION
    action_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    action_parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Modalidad de ejecución específica de la regla:
    # "default_by_module": Hereda la modalidad definida en AutomationConfig para su módulo.
    # "manual", "automatic", "approval_required"
    execution_mode: Mapped[str] = mapped_column(String(30), default="default_by_module", nullable=False)

    # Límites de salvaguarda y circuit breaker:
    # {"min_price": 50.0, "min_margin_pct": 12.0, "max_discount_pct": 30.0, "max_executions_per_hour": 60, "cooldown_seconds": 30}
    safety_limits: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    retry_backoff_base_sec: Mapped[int] = mapped_column(Integer, default=2, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    is_paused_by_circuit_breaker: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    consecutive_errors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_executions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successful_executions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_executions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    company: Mapped["Company"] = relationship("Company")
    executions: Mapped[list["AutomationExecution"]] = relationship("AutomationExecution", back_populates="rule", cascade="all, delete-orphan")


class AutomationExecution(Base, TimestampMixin):
    """
    Registro inmutable de auditoría para cada intento y ciclo de ejecución del motor.
    """

    __tablename__ = "automation_executions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("automation_rules.id", ondelete="SET NULL"), nullable=True, index=True
    )

    trigger_type: Mapped[str] = mapped_column(String(30), default="event", nullable=False)
    trigger_event: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)

    # Identificadores para deduplicación e idempotencia estricta
    event_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)

    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)  # order, product, variant, inventory, price, etc.
    entity_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)

    event_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    conditions_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    conditions_met: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Estado del ciclo de vida:
    # pending, pending_approval, executing, success, failed, dead_letter, rejected, reverted
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False, index=True)

    # Flujo de aprobación previa
    approval_status: Mapped[str] = mapped_column(String(30), default="none", nullable=False, index=True)  # none, pending, approved, rejected
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    action_executed: Mapped[str] = mapped_column(String(80), nullable=False)
    action_parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    action_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    execution_time_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Mecanismo de reversión y compensación (Rollback)
    can_rollback: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_rolled_back: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    rollback_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    rollback_executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rollback_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped["Company"] = relationship("Company")
    rule: Mapped["AutomationRule | None"] = relationship("AutomationRule", back_populates="executions")


# Índices compuestos para alto rendimiento en deduplicación y búsquedas
Index("idx_auto_exec_dedup", AutomationExecution.company_id, AutomationExecution.event_id)
Index("idx_auto_exec_idemp", AutomationExecution.company_id, AutomationExecution.idempotency_key)
Index("idx_auto_exec_status", AutomationExecution.company_id, AutomationExecution.status)

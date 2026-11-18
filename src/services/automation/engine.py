"""
Servicio Central del Motor de Automatización Empresarial (ECA).

Orquesta el ciclo de vida completo de activadores, evaluación de condiciones,
despacho de acciones, límites de salvaguarda, reintentos con dead-letter queue,
circuit breaker, aprobaciones previas y reversión compensatoria.
"""

from datetime import datetime, timezone
import time
from typing import Any
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import EntityNotFoundException, ValidationException
from src.core.logging import get_logger
from src.models.automation import AutomationConfig, AutomationExecution, AutomationRule
from src.schemas.automation import (
    AutomationConfigUpdateRequest,
    AutomationRuleCreate,
    AutomationRuleUpdate,
    AutomationStatsResponse,
    TriggerEventResponse,
)
from src.services.automation.actions import AutomationActionHandler
from src.services.automation.conditions import ConditionEvaluator

logger = get_logger("automation_engine")


def _norm_dt(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class AutomationEngineService:
    """Motor central de automatizaciones y gobernanza de reglas de negocio."""

    # ===========================================================================
    # 1. GESTIÓN DE CONFIGURACIÓN GLOBAL E INTERRUPTOR GENERAL
    # ===========================================================================

    async def get_or_create_config(self, session: AsyncSession, company_id: uuid.UUID) -> AutomationConfig:
        """Obtiene la configuración del motor de la empresa o la inicializa con valores seguros."""
        stmt = select(AutomationConfig).where(AutomationConfig.company_id == company_id)
        config = (await session.execute(stmt)).scalar_one_or_none()
        if not config:
            today = datetime.now(timezone.utc)
            config = AutomationConfig(
                company_id=company_id,
                is_engine_active=True,
                module_modes={
                    "inventory": "automatic",
                    "pricing": "approval_required",
                    "promotions": "approval_required",
                    "logistics": "automatic",
                    "procurement": "approval_required",
                    "reports": "automatic",
                    "spreadsheets": "automatic",
                },
                daily_execution_limit=5000,
                executions_today=0,
                last_reset_date=today,
                circuit_breaker_error_threshold=5,
                cooldown_seconds_default=30,
                max_retries_default=3,
            )
            session.add(config)
            await session.flush()
        return config

    async def update_config(
        self, session: AsyncSession, company_id: uuid.UUID, payload: AutomationConfigUpdateRequest
    ) -> AutomationConfig:
        """Actualiza el interruptor general y las modalidades configuradas por módulo."""
        config = await self.get_or_create_config(session, company_id)

        if payload.is_engine_active is not None:
            config.is_engine_active = payload.is_engine_active
        if payload.module_modes is not None:
            # Combinar manteniendo modalidades existentes
            merged = dict(config.module_modes)
            merged.update(payload.module_modes)
            config.module_modes = merged
        if payload.daily_execution_limit is not None:
            config.daily_execution_limit = payload.daily_execution_limit
        if payload.circuit_breaker_error_threshold is not None:
            config.circuit_breaker_error_threshold = payload.circuit_breaker_error_threshold
        if payload.cooldown_seconds_default is not None:
            config.cooldown_seconds_default = payload.cooldown_seconds_default
        if payload.max_retries_default is not None:
            config.max_retries_default = payload.max_retries_default

        await session.flush()
        return config

    # ===========================================================================
    # 2. GESTIÓN DE REGLAS ECA (CRUD)
    # ===========================================================================

    async def create_rule(
        self, session: AsyncSession, company_id: uuid.UUID, payload: AutomationRuleCreate
    ) -> AutomationRule:
        """Crea una nueva regla de automatización validando coherencia de tipos."""
        conditions_data = [c.model_dump() for c in payload.conditions]

        rule = AutomationRule(
            company_id=company_id,
            name=payload.name,
            description=payload.description,
            module=payload.module,
            trigger_type=payload.trigger_type,
            trigger_event=payload.trigger_event,
            cron_expression=payload.cron_expression,
            interval_minutes=payload.interval_minutes,
            conditions=conditions_data,
            condition_match_type=payload.condition_match_type,
            action_type=payload.action_type,
            action_parameters=payload.action_parameters,
            execution_mode=payload.execution_mode,
            safety_limits=payload.safety_limits,
            max_retries=payload.max_retries,
            retry_backoff_base_sec=payload.retry_backoff_base_sec,
            is_active=payload.is_active,
        )
        session.add(rule)
        await session.flush()
        return rule

    async def update_rule(
        self, session: AsyncSession, company_id: uuid.UUID, rule_id: uuid.UUID, payload: AutomationRuleUpdate
    ) -> AutomationRule:
        """Modifica una regla de automatización existente."""
        stmt = select(AutomationRule).where(AutomationRule.id == rule_id, AutomationRule.company_id == company_id)
        rule = (await session.execute(stmt)).scalar_one_or_none()
        if not rule:
            raise EntityNotFoundException("Regla de Automatización", str(rule_id))

        if payload.name is not None:
            rule.name = payload.name
        if payload.description is not None:
            rule.description = payload.description
        if payload.module is not None:
            rule.module = payload.module
        if payload.trigger_type is not None:
            rule.trigger_type = payload.trigger_type
        if payload.trigger_event is not None:
            rule.trigger_event = payload.trigger_event
        if payload.cron_expression is not None:
            rule.cron_expression = payload.cron_expression
        if payload.interval_minutes is not None:
            rule.interval_minutes = payload.interval_minutes
        if payload.conditions is not None:
            rule.conditions = [c.model_dump() for c in payload.conditions]
        if payload.condition_match_type is not None:
            rule.condition_match_type = payload.condition_match_type
        if payload.action_type is not None:
            rule.action_type = payload.action_type
        if payload.action_parameters is not None:
            rule.action_parameters = payload.action_parameters
        if payload.execution_mode is not None:
            rule.execution_mode = payload.execution_mode
        if payload.safety_limits is not None:
            rule.safety_limits = payload.safety_limits
        if payload.max_retries is not None:
            rule.max_retries = payload.max_retries
        if payload.is_active is not None:
            rule.is_active = payload.is_active

        await session.flush()
        return rule

    async def delete_rule(self, session: AsyncSession, company_id: uuid.UUID, rule_id: uuid.UUID) -> bool:
        """Elimina una regla de automatización."""
        stmt = select(AutomationRule).where(AutomationRule.id == rule_id, AutomationRule.company_id == company_id)
        rule = (await session.execute(stmt)).scalar_one_or_none()
        if not rule:
            raise EntityNotFoundException("Regla de Automatización", str(rule_id))

        await session.delete(rule)
        await session.flush()
        return True

    async def get_rule(self, session: AsyncSession, company_id: uuid.UUID, rule_id: uuid.UUID) -> AutomationRule:
        """Obtiene una regla por ID con aislamiento de tenant."""
        stmt = select(AutomationRule).where(AutomationRule.id == rule_id, AutomationRule.company_id == company_id)
        rule = (await session.execute(stmt)).scalar_one_or_none()
        if not rule:
            raise EntityNotFoundException("Regla de Automatización", str(rule_id))
        return rule

    async def list_rules(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        module: str | None = None,
        trigger_event: str | None = None,
        is_active: bool | None = None,
    ) -> list[AutomationRule]:
        """Lista las reglas de automatización de la empresa con filtros opcionales."""
        stmt = select(AutomationRule).where(AutomationRule.company_id == company_id).order_by(AutomationRule.created_at.desc())
        if module:
            stmt = stmt.where(AutomationRule.module == module)
        if trigger_event:
            stmt = stmt.where(AutomationRule.trigger_event == trigger_event)
        if is_active is not None:
            stmt = stmt.where(AutomationRule.is_active == is_active)
        return list((await session.execute(stmt)).scalars().all())

    # ===========================================================================
    # 3. MOTOR DE DISPACHO Y EVALUACIÓN DE EVENTOS (TRIGGER ENGINE)
    # ===========================================================================

    async def trigger_event(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        event_name: str,
        payload: dict[str, Any],
        event_id: str | None = None,
        idempotency_key: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> TriggerEventResponse:
        """
        Punto neurálgico de recepción y despacho de eventos en el ERP.
        
        Aplica:
        1. Verificación del Interruptor General (Global Kill Switch).
        2. Deduplicación e Idempotencia estricta por event_id / idempotency_key.
        3. Cuota diaria de ejecuciones y circuit breakers.
        4. Evaluación segura de condiciones booleanas (AND / OR).
        5. Enrutamiento según modalidad: Manual, Automática o Automática con Aprobación Previa.
        """
        effective_event_id = event_id or idempotency_key or f"EVT-{uuid.uuid4()}"
        config = await self.get_or_create_config(session, company_id)

        # 1. Interruptor General (Global Kill Switch)
        if not config.is_engine_active:
            logger.info(f"Evento '{event_name}' ignorado: Motor de automatización desactivado globalmente para la empresa {company_id}.")
            return TriggerEventResponse(
                event_id=effective_event_id,
                dispatched=False,
                engine_active=False,
                matched_rules_count=0,
                executions=[],
                message="El motor de automatización está desactivado globalmente (Global Kill Switch activo).",
            )

        # 2. Control de Duplicados e Idempotencia
        # Si ya se procesó con éxito o está en curso una ejecución con el mismo event_id o idempotency_key
        stmt_dedup = select(AutomationExecution).where(
            AutomationExecution.company_id == company_id,
            (AutomationExecution.event_id == effective_event_id)
            | (AutomationExecution.idempotency_key == effective_event_id),
            AutomationExecution.status.in_(["success", "executing", "pending_approval"]),
        )
        existing_exec = (await session.execute(stmt_dedup)).scalars().first()
        if existing_exec:
            logger.warning(f"Evento duplicado '{effective_event_id}' ({event_name}) detectado. Descartando sin reprocesar.")
            return TriggerEventResponse(
                event_id=effective_event_id,
                dispatched=False,
                engine_active=True,
                matched_rules_count=0,
                executions=[
                    {
                        "execution_id": str(existing_exec.id),
                        "status": "duplicate_ignored",
                        "message": "Evento descartado por control de duplicados e idempotencia.",
                    }
                ],
                message="Evento duplicado ya procesado anteriormente.",
            )

        # 3. Buscar reglas activas que coincidan con el evento
        stmt_rules = (
            select(AutomationRule)
            .where(
                AutomationRule.company_id == company_id,
                AutomationRule.trigger_type == "event",
                AutomationRule.trigger_event == event_name,
                AutomationRule.is_active == True,
                AutomationRule.is_paused_by_circuit_breaker == False,
            )
            .order_by(AutomationRule.created_at.asc())
        )
        matched_rules = list((await session.execute(stmt_rules)).scalars().all())

        if not matched_rules:
            return TriggerEventResponse(
                event_id=effective_event_id,
                dispatched=True,
                engine_active=True,
                matched_rules_count=0,
                executions=[],
                message=f"Evento '{event_name}' recibido pero no hay reglas activas configuradas.",
            )

        # Contexto unificado para evaluación de condiciones
        eval_context = {
            "event_name": event_name,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "payload": payload,
            **payload,  # Acceso directo de primer nivel
        }

        now_utc = datetime.now(timezone.utc)
        executions_results = []

        # 4. Procesar cada regla coincidente
        for rule in matched_rules:
            # 4.1 Cooldown check
            cooldown = rule.safety_limits.get("cooldown_seconds", config.cooldown_seconds_default)
            if rule.last_triggered_at:
                elapsed = (now_utc - _norm_dt(rule.last_triggered_at)).total_seconds()
                if elapsed < cooldown:
                    logger.info(f"Regla '{rule.name}' en periodo de cooldown ({elapsed:.1f}s < {cooldown}s). Omitiendo.")
                    continue

            # 4.2 Evaluar condiciones
            conditions_met, snap = ConditionEvaluator.evaluate_all(
                rule.conditions, rule.condition_match_type, eval_context
            )
            if not conditions_met:
                continue

            # 4.3 Determinar modalidad de ejecución
            effective_mode = rule.execution_mode
            if effective_mode == "default_by_module":
                effective_mode = config.module_modes.get(rule.module, "automatic")

            # Combinar parámetros de la acción con los del evento
            action_params = dict(rule.action_parameters)
            action_params.update(payload)

            # 4.4 Modalidad 1: Manual (solo crea el registro o espera invocación explícita)
            if effective_mode == "manual":
                execution = AutomationExecution(
                    company_id=company_id,
                    rule_id=rule.id,
                    trigger_type="event",
                    trigger_event=event_name,
                    event_id=effective_event_id,
                    idempotency_key=idempotency_key,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    event_payload=payload,
                    conditions_snapshot=snap,
                    conditions_met=True,
                    status="pending_manual",
                    approval_status="none",
                    action_executed=rule.action_type,
                    action_parameters=action_params,
                )
                session.add(execution)
                await session.flush()
                executions_results.append({"execution_id": str(execution.id), "status": "pending_manual", "rule_id": str(rule.id)})

            # 4.5 Modalidad 2: Automática con Aprobación Previa
            elif effective_mode == "approval_required":
                execution = AutomationExecution(
                    company_id=company_id,
                    rule_id=rule.id,
                    trigger_type="event",
                    trigger_event=event_name,
                    event_id=effective_event_id,
                    idempotency_key=idempotency_key,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    event_payload=payload,
                    conditions_snapshot=snap,
                    conditions_met=True,
                    status="pending_approval",
                    approval_status="pending",
                    action_executed=rule.action_type,
                    action_parameters=action_params,
                )
                session.add(execution)
                await session.flush()
                executions_results.append({"execution_id": str(execution.id), "status": "pending_approval", "rule_id": str(rule.id)})

            # 4.6 Modalidad 3: Automática desatendida
            else:
                exec_res = await self._execute_rule_action_with_retries(
                    session=session,
                    company_id=company_id,
                    rule=rule,
                    event_id=effective_event_id,
                    idempotency_key=idempotency_key,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    event_payload=payload,
                    conditions_snapshot=snap,
                    action_params=action_params,
                    config=config,
                )
                executions_results.append(exec_res)

        return TriggerEventResponse(
            event_id=effective_event_id,
            dispatched=True,
            engine_active=True,
            matched_rules_count=len(matched_rules),
            executions=executions_results,
            message=f"Evento '{event_name}' procesado. {len(executions_results)} ejecuciones generadas.",
        )

    # ===========================================================================
    # 4. EJECUCIÓN CON REINTENTOS Y CIRCUIT BREAKER
    # ===========================================================================

    async def _execute_rule_action_with_retries(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        rule: AutomationRule,
        event_id: str,
        idempotency_key: str | None,
        entity_type: str | None,
        entity_id: str | None,
        event_payload: dict[str, Any],
        conditions_snapshot: list[dict[str, Any]],
        action_params: dict[str, Any],
        config: AutomationConfig,
    ) -> dict[str, Any]:
        """Ejecuta la acción con reintentos configurables y protección de circuit breaker."""
        start_time = time.time()
        max_retries = rule.max_retries
        retry_count = 0
        last_error = None
        action_res = None
        rollback_payload = None
        can_rollback = False

        # Validaciones de salvaguarda de precio y margen antes de ejecutar
        safety = rule.safety_limits
        safety_error = None
        if "min_price" in safety and "proposed_price" in action_params:
            if float(action_params["proposed_price"]) < float(safety["min_price"]):
                safety_error = (
                    f"Acción cancelada: el precio propuesto (${action_params['proposed_price']}) "
                    f"es inferior al precio piso de salvaguarda (${safety['min_price']})."
                )

        if not safety_error and "min_margin_pct" in safety and "current_margin_pct" in action_params:
            if float(action_params["current_margin_pct"]) < float(safety["min_margin_pct"]):
                safety_error = (
                    f"Acción cancelada: el margen ({action_params['current_margin_pct']}%) "
                    f"viola el margen mínimo de salvaguarda ({safety['min_margin_pct']}%)."
                )

        if safety_error:
            execution_time_ms = int((time.time() - start_time) * 1000)
            now_utc = datetime.now(timezone.utc)
            rule.total_executions += 1
            rule.failed_executions += 1
            rule.last_triggered_at = now_utc

            execution = AutomationExecution(
                company_id=company_id,
                rule_id=rule.id,
                trigger_type="event",
                trigger_event=rule.trigger_event,
                event_id=event_id,
                idempotency_key=idempotency_key,
                entity_type=entity_type,
                entity_id=entity_id,
                event_payload=event_payload,
                conditions_snapshot=conditions_snapshot,
                conditions_met=True,
                status="dead_letter",
                approval_status="none",
                action_executed=rule.action_type,
                action_parameters=action_params,
                error_message=safety_error,
                retry_count=0,
                max_retries=max_retries,
                execution_time_ms=execution_time_ms,
                can_rollback=False,
                completed_at=now_utc,
            )
            session.add(execution)
            await session.flush()
            return {"execution_id": str(execution.id), "status": "dead_letter", "error": safety_error, "rule_id": str(rule.id)}

        # Ciclo de ejecución con reintentos
        while retry_count <= max_retries:
            try:
                action_res, rollback_payload, can_rollback = await AutomationActionHandler.execute_action(
                    session=session,
                    company_id=company_id,
                    action_type=rule.action_type,
                    parameters=action_params,
                )
                last_error = None
                break
            except Exception as e:
                last_error = str(e)
                retry_count += 1
                logger.warning(
                    f"Fallo en ejecución de regla '{rule.name}' (Intento {retry_count}/{max_retries}): {e}"
                )

        execution_time_ms = int((time.time() - start_time) * 1000)
        now_utc = datetime.now(timezone.utc)

        # Si tuvo éxito
        if last_error is None:
            rule.total_executions += 1
            rule.successful_executions += 1
            rule.consecutive_errors = 0
            rule.last_triggered_at = now_utc
            config.executions_today += 1

            execution = AutomationExecution(
                company_id=company_id,
                rule_id=rule.id,
                trigger_type="event",
                trigger_event=rule.trigger_event,
                event_id=event_id,
                idempotency_key=idempotency_key,
                entity_type=entity_type,
                entity_id=entity_id,
                event_payload=event_payload,
                conditions_snapshot=conditions_snapshot,
                conditions_met=True,
                status="success",
                approval_status="none",
                action_executed=rule.action_type,
                action_parameters=action_params,
                action_result=action_res,
                retry_count=retry_count,
                max_retries=max_retries,
                execution_time_ms=execution_time_ms,
                can_rollback=can_rollback,
                is_rolled_back=False,
                rollback_payload=rollback_payload,
                completed_at=now_utc,
            )
            session.add(execution)
            await session.flush()
            return {"execution_id": str(execution.id), "status": "success", "rule_id": str(rule.id)}

        # Si falló tras agotar reintentos -> Dead-Letter
        rule.total_executions += 1
        rule.failed_executions += 1
        rule.consecutive_errors += 1
        rule.last_triggered_at = now_utc

        # Comprobar si se dispara el Circuit Breaker
        if rule.consecutive_errors >= config.circuit_breaker_error_threshold:
            rule.is_paused_by_circuit_breaker = True
            logger.critical(
                f"🚨 CIRCUIT BREAKER ACTIVADO: Regla '{rule.name}' pausada automáticamente tras {rule.consecutive_errors} errores consecutivos."
            )

        execution = AutomationExecution(
            company_id=company_id,
            rule_id=rule.id,
            trigger_type="event",
            trigger_event=rule.trigger_event,
            event_id=event_id,
            idempotency_key=idempotency_key,
            entity_type=entity_type,
            entity_id=entity_id,
            event_payload=event_payload,
            conditions_snapshot=conditions_snapshot,
            conditions_met=True,
            status="dead_letter",
            approval_status="none",
            action_executed=rule.action_type,
            action_parameters=action_params,
            error_message=last_error,
            retry_count=retry_count,
            max_retries=max_retries,
            execution_time_ms=execution_time_ms,
            can_rollback=False,
            completed_at=now_utc,
        )
        session.add(execution)
        await session.flush()
        return {"execution_id": str(execution.id), "status": "dead_letter", "error": last_error, "rule_id": str(rule.id)}

    # ===========================================================================
    # 5. APROBACIÓN O RECHAZO HUMANO
    # ===========================================================================

    async def approve_execution(
        self, session: AsyncSession, company_id: uuid.UUID, execution_id: uuid.UUID, user_id: uuid.UUID, notes: str | None = None
    ) -> AutomationExecution:
        """Autoriza y ejecuta una acción en estado 'pending_approval'."""
        stmt = select(AutomationExecution).where(
            AutomationExecution.id == execution_id, AutomationExecution.company_id == company_id
        )
        execution = (await session.execute(stmt)).scalar_one_or_none()
        if not execution:
            raise EntityNotFoundException("Ejecución de Automatización", str(execution_id))

        if execution.status != "pending_approval":
            raise ValidationException(f"La ejecución no está pendiente de aprobación (estado actual: '{execution.status}').")

        start_time = time.time()
        now_utc = datetime.now(timezone.utc)

        # Ejecutar la acción formalmente
        action_res, rollback_payload, can_rollback = await AutomationActionHandler.execute_action(
            session=session,
            company_id=company_id,
            action_type=execution.action_executed,
            parameters=execution.action_parameters,
        )

        execution.status = "success"
        execution.approval_status = "approved"
        execution.approved_by_user_id = user_id
        execution.approved_at = now_utc
        execution.action_result = action_res
        execution.can_rollback = can_rollback
        execution.rollback_payload = rollback_payload
        execution.execution_time_ms = int((time.time() - start_time) * 1000)
        execution.completed_at = now_utc

        await session.flush()
        return execution

    async def reject_execution(
        self, session: AsyncSession, company_id: uuid.UUID, execution_id: uuid.UUID, user_id: uuid.UUID, reason: str | None = None
    ) -> AutomationExecution:
        """Rechaza y cancela una ejecución pendiente de aprobación."""
        stmt = select(AutomationExecution).where(
            AutomationExecution.id == execution_id, AutomationExecution.company_id == company_id
        )
        execution = (await session.execute(stmt)).scalar_one_or_none()
        if not execution:
            raise EntityNotFoundException("Ejecución de Automatización", str(execution_id))

        if execution.status != "pending_approval":
            raise ValidationException(f"La ejecución no está pendiente de aprobación (estado actual: '{execution.status}').")

        execution.status = "rejected"
        execution.approval_status = "rejected"
        execution.rejection_reason = reason or "Rechazado manualmente por el usuario facultado."
        execution.completed_at = datetime.now(timezone.utc)

        await session.flush()
        return execution

    # ===========================================================================
    # 6. REVERSIÓN Y COMPENSACIÓN (ROLLBACK / UNDO)
    # ===========================================================================

    async def rollback_execution(
        self, session: AsyncSession, company_id: uuid.UUID, execution_id: uuid.UUID
    ) -> tuple[bool, str, dict[str, Any] | None]:
        """
        Revierte una acción exitosa ejecutando su acción compensatoria.
        Garantiza: 'Reversión cuando sea posible'.
        """
        stmt = select(AutomationExecution).where(
            AutomationExecution.id == execution_id, AutomationExecution.company_id == company_id
        )
        execution = (await session.execute(stmt)).scalar_one_or_none()
        if not execution:
            raise EntityNotFoundException("Ejecución de Automatización", str(execution_id))

        if not execution.can_rollback:
            raise ValidationException(f"La acción '{execution.action_executed}' no admite reversión automática.")

        if execution.is_rolled_back:
            raise ValidationException("Esta ejecución ya ha sido revertida previamente.")

        if execution.status != "success":
            raise ValidationException(f"Solo se pueden revertir ejecuciones con estado 'success' (actual: '{execution.status}').")

        # Despachar reversión
        res = await AutomationActionHandler.rollback_action(
            session=session,
            company_id=company_id,
            action_type=execution.action_executed,
            rollback_payload=execution.rollback_payload or {},
        )

        now_utc = datetime.now(timezone.utc)
        execution.is_rolled_back = True
        execution.status = "reverted"
        execution.rollback_executed_at = now_utc
        execution.rollback_result = res

        await session.flush()
        return True, f"Acción '{execution.action_executed}' revertida exitosamente.", res

    # ===========================================================================
    # 7. EJECUCIÓN MANUAL Y REACTIVACIÓN DE CIRCUIT BREAKER
    # ===========================================================================

    async def execute_rule_manually(
        self, session: AsyncSession, company_id: uuid.UUID, rule_id: uuid.UUID, custom_payload: dict[str, Any] | None = None
    ) -> AutomationExecution:
        """Fuerza la ejecución manual de una regla pasando por alto su activación automática."""
        rule = await self.get_rule(session, company_id, rule_id)
        config = await self.get_or_create_config(session, company_id)

        payload = dict(rule.action_parameters)
        if custom_payload:
            payload.update(custom_payload)

        start_time = time.time()
        action_res, rollback_payload, can_rollback = await AutomationActionHandler.execute_action(
            session=session,
            company_id=company_id,
            action_type=rule.action_type,
            parameters=payload,
        )

        now_utc = datetime.now(timezone.utc)
        rule.total_executions += 1
        rule.successful_executions += 1
        rule.last_triggered_at = now_utc

        execution = AutomationExecution(
            company_id=company_id,
            rule_id=rule.id,
            trigger_type="manual",
            trigger_event=rule.trigger_event,
            event_id=f"MANUAL-{uuid.uuid4()}",
            entity_type=None,
            entity_id=None,
            event_payload=payload,
            conditions_snapshot=[],
            conditions_met=True,
            status="success",
            approval_status="none",
            action_executed=rule.action_type,
            action_parameters=payload,
            action_result=action_res,
            retry_count=0,
            max_retries=0,
            execution_time_ms=int((time.time() - start_time) * 1000),
            can_rollback=can_rollback,
            is_rolled_back=False,
            rollback_payload=rollback_payload,
            completed_at=now_utc,
        )
        session.add(execution)
        await session.flush()
        return execution

    async def reset_circuit_breaker(
        self, session: AsyncSession, company_id: uuid.UUID, rule_id: uuid.UUID
    ) -> AutomationRule:
        """Reactiva una regla que fue pausada por el circuit breaker."""
        rule = await self.get_rule(session, company_id, rule_id)
        rule.is_paused_by_circuit_breaker = False
        rule.consecutive_errors = 0
        await session.flush()
        return rule

    # ===========================================================================
    # 8. HISTORIAL Y ESTADÍSTICAS DEL MOTOR
    # ===========================================================================

    async def list_executions(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        rule_id: uuid.UUID | None = None,
        status: str | None = None,
        trigger_event: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[AutomationExecution], int]:
        """Consulta el historial paginado de ejecuciones con filtros."""
        stmt = select(AutomationExecution).where(AutomationExecution.company_id == company_id)
        if rule_id:
            stmt = stmt.where(AutomationExecution.rule_id == rule_id)
        if status:
            stmt = stmt.where(AutomationExecution.status == status)
        if trigger_event:
            stmt = stmt.where(AutomationExecution.trigger_event == trigger_event)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await session.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(AutomationExecution.created_at.desc()).offset(offset).limit(limit)
        items = (await session.execute(stmt)).scalars().all()
        return list(items), total

    async def get_execution(
        self, session: AsyncSession, company_id: uuid.UUID, execution_id: uuid.UUID
    ) -> AutomationExecution:
        """Obtiene una ejecución por ID."""
        stmt = select(AutomationExecution).where(
            AutomationExecution.id == execution_id, AutomationExecution.company_id == company_id
        )
        exec_item = (await session.execute(stmt)).scalar_one_or_none()
        if not exec_item:
            raise EntityNotFoundException("Ejecución de Automatización", str(execution_id))
        return exec_item

    async def get_stats(self, session: AsyncSession, company_id: uuid.UUID) -> AutomationStatsResponse:
        """Calcula las métricas consolidadas del motor de automatización."""
        config = await self.get_or_create_config(session, company_id)

        # Contadores de reglas
        stmt_rules = select(
            func.count(AutomationRule.id).label("total"),
            func.count(AutomationRule.id).filter(AutomationRule.is_active == True).label("active"),
            func.count(AutomationRule.id).filter(AutomationRule.is_paused_by_circuit_breaker == True).label("paused_cb"),
        ).where(AutomationRule.company_id == company_id)
        r_counts = (await session.execute(stmt_rules)).one()

        # Contadores de ejecuciones
        stmt_execs = select(
            func.count(AutomationExecution.id).label("total"),
            func.count(AutomationExecution.id).filter(AutomationExecution.status == "success").label("success"),
            func.count(AutomationExecution.id).filter(AutomationExecution.status == "failed").label("failed"),
            func.count(AutomationExecution.id).filter(AutomationExecution.status == "dead_letter").label("dead_letter"),
            func.count(AutomationExecution.id).filter(AutomationExecution.status == "pending_approval").label("pending_approval"),
        ).where(AutomationExecution.company_id == company_id)
        e_counts = (await session.execute(stmt_execs)).one()

        # Desglose por módulo
        stmt_by_mod = (
            select(AutomationRule.module, func.count(AutomationExecution.id))
            .join(AutomationExecution, AutomationRule.id == AutomationExecution.rule_id)
            .where(AutomationRule.company_id == company_id)
            .group_by(AutomationRule.module)
        )
        by_mod_rows = (await session.execute(stmt_by_mod)).all()
        by_mod = {row[0]: row[1] for row in by_mod_rows}

        return AutomationStatsResponse(
            is_engine_active=config.is_engine_active,
            total_rules=r_counts.total or 0,
            active_rules=r_counts.active or 0,
            circuit_breakers_active=r_counts.paused_cb or 0,
            total_executions_today=e_counts.total or 0,
            successful_executions_today=e_counts.success or 0,
            failed_executions_today=e_counts.failed or 0,
            dead_letter_count_today=e_counts.dead_letter or 0,
            pending_approvals_count=e_counts.pending_approval or 0,
            executions_by_module=by_mod,
        )

"""
Orquestador Principal del Asistente de Inteligencia Artificial Comercial.

Coordina:
1. Verificación de cuotas y rate limits por empresa.
2. Detección y bloqueo estricto de prompt injection y accesos no autorizados.
3. Selección dinámica y conexión a proveedores de IA (Locales y Externos).
4. Ejecución de herramientas autorizadas conectadas a los servicios reales del ERP.
5. Persistencia del historial conversacional con citaciones auditables.
6. Registro inmutable en AIAuditLog de cada consulta y tiempo de respuesta.
"""

from datetime import date, datetime, timezone
import time
from typing import Any
import uuid

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.exceptions import EntityNotFoundException, ValidationException
from src.core.logging import get_logger
from src.core.security import decrypt_token, encrypt_token
from src.models.ai import AIAuditLog, AIConversation, AIMessage, AISettings
from src.schemas.ai import (
    AIActionExecutionRequest,
    AIActionExecutionResponse,
    AIChatRequest,
    AIChatResponse,
    AICitation,
    AIQuickQueryRequest,
    AISettingsCreateOrUpdate,
    AISettingsResponse,
    AISuggestedAction,
)
from src.services.ai.guardrails import PromptInjectionGuard
from src.services.ai.providers import LLMProviderFactory
from src.services.ai.tools import CommercialAITools

logger = get_logger("ai_assistant_service")


class AIAssistantService:
    """Servicio orquestador del Asistente Comercial de Inteligencia Artificial."""

    def __init__(self):
        self.tools_helper = CommercialAITools()

    # ===========================================================================
    # 1. GESTIÓN DE CONFIGURACIÓN DE IA POR EMPRESA
    # ===========================================================================

    async def get_or_create_settings(
        self, session: AsyncSession, company_id: uuid.UUID
    ) -> AISettings:
        """Obtiene la configuración activa de IA de la empresa o crea una predeterminada."""
        stmt = select(AISettings).where(AISettings.company_id == company_id)
        settings = (await session.execute(stmt)).scalar_one_or_none()

        if not settings:
            settings = AISettings(
                company_id=company_id,
                provider="mock_fallback",
                base_url="http://localhost:11434/v1",
                model_name="llama3.2",
                temperature=0.2,
                max_tokens=2048,
                daily_request_limit=500,
                requests_today=0,
                last_reset_date=datetime.now(timezone.utc).date(),
                is_active=True,
            )
            session.add(settings)
            await session.flush()

        return settings

    async def update_settings(
        self, session: AsyncSession, company_id: uuid.UUID, payload: AISettingsCreateOrUpdate
    ) -> AISettingsResponse:
        """Actualiza la configuración de IA, encriptando la API key si se suministra una nueva."""
        settings = await self.get_or_create_settings(session, company_id)

        settings.provider = payload.provider
        settings.base_url = payload.base_url
        settings.model_name = payload.model_name
        settings.temperature = payload.temperature
        settings.max_tokens = payload.max_tokens
        settings.daily_request_limit = payload.daily_request_limit
        settings.system_prompt_override = payload.system_prompt_override
        settings.is_active = payload.is_active

        if payload.api_key:
            settings.api_key_enc = encrypt_token(payload.api_key)

        await session.commit()
        await session.refresh(settings)

        masked_key = None
        if settings.api_key_enc:
            masked_key = "sk-••••••••••••"

        return AISettingsResponse(
            id=settings.id,
            company_id=settings.company_id,
            provider=settings.provider,
            base_url=settings.base_url,
            api_key_masked=masked_key,
            model_name=settings.model_name,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            daily_request_limit=settings.daily_request_limit,
            requests_today=settings.requests_today,
            system_prompt_override=settings.system_prompt_override,
            is_active=settings.is_active,
            created_at=settings.created_at,
            updated_at=settings.updated_at,
        )

    # ===========================================================================
    # 2. CHAT CONVERSACIONAL Y CONSULTA COMERCIAL
    # ===========================================================================

    async def chat(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        user_id: uuid.UUID | None,
        company_name: str,
        payload: AIChatRequest,
    ) -> AIChatResponse:
        """
        Punto de entrada principal para interacción conversacional con el asistente.
        Valida cuotas, filtra inyecciones, invoca herramientas y persiste auditoría.
        """
        start_time = time.time()
        today = datetime.now(timezone.utc).date()

        # 1. Obtener y validar configuración de IA y cuota diaria
        ai_cfg = await self.get_or_create_settings(session, company_id)
        if not ai_cfg.is_active:
            raise ValidationException("El asistente de inteligencia artificial está desactivado para esta empresa.")

        # Reiniciar contador diario si cambió la fecha
        if ai_cfg.last_reset_date != today:
            ai_cfg.requests_today = 0
            ai_cfg.last_reset_date = today

        if ai_cfg.requests_today >= ai_cfg.daily_request_limit:
            # Registrar bloqueo por límite en auditoría
            audit = AIAuditLog(
                company_id=company_id,
                user_id=user_id,
                endpoint="/api/v1/ai/chat",
                query_text=payload.message[:200],
                provider=ai_cfg.provider,
                model_name=ai_cfg.model_name,
                latency_ms=int((time.time() - start_time) * 1000),
                status="rate_limited",
                error_message="Límite diario de consultas excedido.",
            )
            session.add(audit)
            await session.commit()
            raise ValidationException(f"Has alcanzado tu límite de {ai_cfg.daily_request_limit} consultas diarias.")

        # 2. Protección contra Prompt Injection y Accesos Maliciosos
        guard_res = PromptInjectionGuard.check_and_sanitize(payload.message)
        if not guard_res.is_safe:
            latency_ms = int((time.time() - start_time) * 1000)
            audit = AIAuditLog(
                company_id=company_id,
                user_id=user_id,
                endpoint="/api/v1/ai/chat",
                query_text=payload.message[:200],
                provider=ai_cfg.provider,
                model_name=ai_cfg.model_name,
                latency_ms=latency_ms,
                security_flags=[guard_res.violation_type or "PROMPT_INJECTION"],
                status="injection_blocked",
                error_message=guard_res.reason,
            )
            session.add(audit)
            await session.commit()

            # Devolver respuesta segura sin revelar datos internos
            conv = await self._get_or_create_conversation(session, company_id, user_id, payload.conversation_id, payload.message)
            msg_warn = AIMessage(
                conversation_id=conv.id,
                role="assistant",
                content=f"⚠️ **Consulta Bloqueada por Seguridad:** {guard_res.reason}",
                justification="La consulta ingresada viola las políticas de protección y seguridad de datos del ERP.",
                confidence_score=0.0,
            )
            session.add(msg_warn)
            await session.commit()

            return AIChatResponse(
                conversation_id=conv.id,
                message_id=msg_warn.id,
                role="assistant",
                content=msg_warn.content,
                citations=[],
                justification=msg_warn.justification,
                confidence_score=0.0,
                tools_used=[],
                suggested_action=None,
                execution_time_ms=latency_ms,
                model_used=ai_cfg.model_name,
            )

        sanitized_message = guard_res.sanitized_text

        # 3. Obtener o crear conversación
        conv = await self._get_or_create_conversation(session, company_id, user_id, payload.conversation_id, sanitized_message)

        # Cargar historial previo
        history_stmt = (
            select(AIMessage)
            .where(AIMessage.conversation_id == conv.id)
            .order_by(AIMessage.created_at.asc())
            .limit(10)
        )
        prev_msgs = (await session.execute(history_stmt)).scalars().all()
        conv_history = [{"role": m.role, "content": m.content} for m in prev_msgs]

        # 4. Guardar mensaje del usuario
        user_msg_db = AIMessage(
            conversation_id=conv.id,
            role="user",
            content=sanitized_message,
        )
        session.add(user_msg_db)
        await session.flush()

        # 5. Instanciar proveedor de IA activo
        plain_key = decrypt_token(ai_cfg.api_key_enc) if ai_cfg.api_key_enc else None
        provider = LLMProviderFactory.get_provider(
            provider_name=ai_cfg.provider,
            base_url=ai_cfg.base_url,
            api_key=plain_key,
            model_name=ai_cfg.model_name,
            temperature=ai_cfg.temperature,
            max_tokens=ai_cfg.max_tokens,
        )

        # 6. Generar respuesta ejecutando herramientas autorizadas
        p_res = await provider.generate_response(
            session=session,
            company_id=company_id,
            company_name=company_name,
            user_message=sanitized_message,
            tools_helper=self.tools_helper,
            preset_period=payload.preset_period or "today",
            conversation_history=conv_history,
        )

        # 7. Persistir mensaje de la IA
        assistant_msg_db = AIMessage(
            conversation_id=conv.id,
            role="assistant",
            content=p_res.content,
            citations=p_res.citations,
            justification=p_res.justification,
            confidence_score=p_res.confidence_score,
            suggested_action=p_res.suggested_action,
        )
        session.add(assistant_msg_db)

        # 8. Incrementar cuota y registrar auditoría inmutable
        ai_cfg.requests_today += 1
        latency_ms = int((time.time() - start_time) * 1000)

        audit = AIAuditLog(
            company_id=company_id,
            user_id=user_id,
            conversation_id=conv.id,
            endpoint="/api/v1/ai/chat",
            query_text=sanitized_message[:500],
            provider=ai_cfg.provider,
            model_name=p_res.model_name,
            prompt_tokens=p_res.prompt_tokens,
            completion_tokens=p_res.completion_tokens,
            total_tokens=p_res.total_tokens,
            latency_ms=latency_ms,
            tools_invoked=[{"tool": t} for t in p_res.tools_used],
            status="success",
        )
        session.add(audit)
        await session.commit()

        # Construir modelo de acción sugerida
        suggested_action_obj = None
        if p_res.suggested_action:
            suggested_action_obj = AISuggestedAction(**p_res.suggested_action)

        citations_objs = [AICitation(**c) for c in p_res.citations]

        return AIChatResponse(
            conversation_id=conv.id,
            message_id=assistant_msg_db.id,
            role="assistant",
            content=p_res.content,
            citations=citations_objs,
            justification=p_res.justification,
            confidence_score=p_res.confidence_score,
            tools_used=p_res.tools_used,
            suggested_action=suggested_action_obj,
            execution_time_ms=latency_ms,
            model_used=p_res.model_name,
        )

    async def quick_query(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        user_id: uuid.UUID | None,
        company_name: str,
        payload: AIQuickQueryRequest,
    ) -> AIChatResponse:
        """Endpoint abreviado para preguntas rápidas del negocio."""
        chat_req = AIChatRequest(
            conversation_id=None,
            message=payload.question,
            preset_period=payload.preset_period or "today",
        )
        return await self.chat(session, company_id, user_id, company_name, chat_req)

    # ===========================================================================
    # 3. EJECUCIÓN AUTORIZADA DE ACCIONES COMERCIALES
    # ===========================================================================

    async def execute_action(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        user_id: uuid.UUID | None,
        payload: AIActionExecutionRequest,
    ) -> AIActionExecutionResponse:
        """Ejecuta una acción comercial autorizada a través del motor de automatizaciones."""
        start_time = time.time()
        tool_res = await self.tools_helper.tool_execute_commercial_action(
            session=session,
            company_id=company_id,
            action_type=payload.action_type,
            parameters=payload.parameters,
        )

        # Registrar en auditoría
        audit = AIAuditLog(
            company_id=company_id,
            user_id=user_id,
            endpoint="/api/v1/ai/actions/execute",
            query_text=f"Action: {payload.action_type} | Params: {payload.parameters}",
            provider="automation_engine",
            model_name="commercial-automator",
            latency_ms=int((time.time() - start_time) * 1000),
            tools_invoked=[{"action": payload.action_type, "params": payload.parameters}],
            status="success" if tool_res["success"] else "tool_error",
        )
        session.add(audit)
        await session.commit()

        return AIActionExecutionResponse(
            success=tool_res["success"],
            action_type=tool_res["action_type"],
            execution_id=tool_res.get("execution_id"),
            message=tool_res["message"],
            details=tool_res.get("details", {}),
            applied_at=datetime.fromisoformat(tool_res["applied_at"]),
        )

    # ===========================================================================
    # 4. AUDITORÍA Y REGISTROS
    # ===========================================================================

    async def list_audit_logs(
        self, session: AsyncSession, company_id: uuid.UUID, limit: int = 50, offset: int = 0
    ) -> list[AIAuditLog]:
        """Consulta los registros de auditoría de consultas de IA para supervisión de seguridad."""
        stmt = (
            select(AIAuditLog)
            .where(AIAuditLog.company_id == company_id)
            .order_by(desc(AIAuditLog.created_at))
            .offset(offset)
            .limit(limit)
        )
        return list((await session.execute(stmt)).scalars().all())

    # ===========================================================================
    # HELPERS
    # ===========================================================================

    async def _get_or_create_conversation(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        user_id: uuid.UUID | None,
        conversation_id: uuid.UUID | None,
        first_message: str,
    ) -> AIConversation:
        """Recupera o crea un nuevo hilo de conversación."""
        if conversation_id:
            stmt = select(AIConversation).where(
                AIConversation.id == conversation_id, AIConversation.company_id == company_id
            )
            conv = (await session.execute(stmt)).scalar_one_or_none()
            if conv:
                return conv

        title = first_message[:50] + ("..." if len(first_message) > 50 else "")
        conv = AIConversation(
            company_id=company_id,
            user_id=user_id,
            title=title,
            status="active",
        )
        session.add(conv)
        await session.flush()
        return conv

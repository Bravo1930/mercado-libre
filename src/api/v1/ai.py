"""
Endpoints del Asistente Comercial de Inteligencia Artificial para Mercado Libre México.

Ofrece:
- Chat conversacional comercial con citaciones auditables y notas de justificación.
- Consultas analíticas rápidas para preguntas canónicas del negocio.
- Ejecución autorizada de acciones comerciales mediante el motor de automatizaciones.
- Catálogo oficial de las 11 herramientas autorizadas de IA.
- Configuración de proveedores (Ollama, OpenAI, Claude, Gemini, Fallback local).
- Auditoría inmutable de interacciones y detección de amenazas.
"""

from typing import Any
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_context import CompanyContext, require_company_permission
from src.core.database import get_db
from src.core.permissions import ActionEnum, ModuleEnum
from src.schemas.ai import (
    AIActionExecutionRequest,
    AIActionExecutionResponse,
    AIAuditLogItemResponse,
    AIChatRequest,
    AIChatResponse,
    AIQuickQueryRequest,
    AISettingsCreateOrUpdate,
    AISettingsResponse,
    AIToolDefinition,
)
from src.services.ai.assistant_service import AIAssistantService
from src.services.ai.tools import CommercialAITools

router = APIRouter(prefix="/ai", tags=["Asistente Comercial de IA"])
ai_service = AIAssistantService()


@router.post(
    "/chat",
    response_model=AIChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Interacción conversacional con el Asistente Comercial de IA",
)
async def chat_with_assistant(
    payload: AIChatRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> AIChatResponse:
    """
    Envía un mensaje o consulta en lenguaje natural al asistente de IA:
    - Analiza ventas, márgenes, rentabilidad, inventario y tendencias.
    - Accede a datos reales mediante servicios backend autorizados (sin acceso irrestricto a la BD).
    - Protege contra Prompt Injection y ataques de jailbreak.
    - Proporciona justificación económica y citaciones transparentes para cada recomendación.
    """
    company_name = ctx.company.legal_name if ctx.company else "Empresa ERP"
    return await ai_service.chat(
        session=session,
        company_id=ctx.company_id,
        user_id=ctx.user_id,
        company_name=company_name,
        payload=payload,
    )


@router.post(
    "/query",
    response_model=AIChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Consulta directa de preguntas clave del negocio",
)
async def quick_query_assistant(
    payload: AIQuickQueryRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> AIChatResponse:
    """
    Responde directamente a preguntas de negocio con datos reales auditables:
    - ¿Cuánto gané hoy?
    - ¿Qué productos debo reponer?
    - ¿Qué productos pierden dinero?
    - ¿Qué producto debería promocionar?
    - ¿Cuál es mi margen promedio?
    - ¿Cuánto vendí este mes?
    """
    company_name = ctx.company.legal_name if ctx.company else "Empresa ERP"
    return await ai_service.quick_query(
        session=session,
        company_id=ctx.company_id,
        user_id=ctx.user_id,
        company_name=company_name,
        payload=payload,
    )


@router.post(
    "/actions/execute",
    response_model=AIActionExecutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Ejecutar acción comercial propuesta por la IA a través del motor de automatizaciones",
)
async def execute_suggested_action(
    payload: AIActionExecutionRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.CREATE)),
    session: AsyncSession = Depends(get_db),
) -> AIActionExecutionResponse:
    """
    Aplica una recomendación de acción sugerida por el asistente:
    - Ajuste de precios respetando reglas comerciales y márgenes mínimos.
    - Generación de borrador de orden de compra en abastecimiento.
    - Creación o actualización de reglas de salvaguarda.
    """
    return await ai_service.execute_action(
        session=session,
        company_id=ctx.company_id,
        user_id=ctx.user_id,
        payload=payload,
    )


@router.get(
    "/tools",
    response_model=list[AIToolDefinition],
    summary="Listar el catálogo de herramientas autorizadas de IA",
)
async def list_ai_tools(
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.READ)),
) -> list[AIToolDefinition]:
    """Retorna las 11 herramientas comerciales autorizadas y sus parámetros disponibles."""
    return CommercialAITools.get_definitions()


@router.get(
    "/settings",
    response_model=AISettingsResponse,
    summary="Consultar configuración del motor de IA",
)
async def get_ai_settings(
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> AISettingsResponse:
    """Obtiene la configuración activa de IA de la empresa con clave API enmascarada."""
    s = await ai_service.get_or_create_settings(session, ctx.company_id)
    masked = "sk-••••••••••••" if s.api_key_enc else None
    return AISettingsResponse(
        id=s.id,
        company_id=s.company_id,
        provider=s.provider,
        base_url=s.base_url,
        api_key_masked=masked,
        model_name=s.model_name,
        temperature=s.temperature,
        max_tokens=s.max_tokens,
        daily_request_limit=s.daily_request_limit,
        requests_today=s.requests_today,
        system_prompt_override=s.system_prompt_override,
        is_active=s.is_active,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


@router.put(
    "/settings",
    response_model=AISettingsResponse,
    summary="Actualizar configuración del motor de IA",
)
async def update_ai_settings(
    payload: AISettingsCreateOrUpdate,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> AISettingsResponse:
    """Actualiza proveedor (Ollama local, OpenAI, Claude, Gemini, Fallback), modelo y límites."""
    return await ai_service.update_settings(session, ctx.company_id, payload)


@router.get(
    "/audit-logs",
    response_model=list[AIAuditLogItemResponse],
    summary="Consultar registro de auditoría de consultas de IA",
)
async def get_ai_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> list[AIAuditLogItemResponse]:
    """Retorna el historial inmutable de auditoría para supervisar seguridad, latencias y herramientas."""
    logs = await ai_service.list_audit_logs(session, ctx.company_id, limit, offset)
    return [AIAuditLogItemResponse.model_validate(l) for l in logs]

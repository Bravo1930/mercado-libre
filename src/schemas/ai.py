"""
Esquemas Pydantic para el Asistente de Inteligencia Artificial Comercial.
Garantiza tipado estricto, sanitización, citaciones transparentes, justificaciones y auditoría.
"""

from datetime import datetime
from typing import Any, Literal
import uuid

from pydantic import BaseModel, ConfigDict, Field


# ===========================================================================
# CONFIGURACIÓN DEL PROVEEDOR DE IA
# ===========================================================================

class AISettingsCreateOrUpdate(BaseModel):
    """Payload para configurar el motor de IA de la empresa."""
    provider: Literal[
        "mock_fallback",
        "local_ollama",
        "openai",
        "anthropic",
        "gemini",
        "custom_openai",
    ] = Field(
        default="mock_fallback",
        description="Proveedor de IA activo (local u hospedado externamente)",
    )
    base_url: str | None = Field(
        default=None,
        description="URL base para modelos locales (ej. http://localhost:11434/v1) o proxies privados",
    )
    api_key: str | None = Field(
        default=None,
        description="API Key en texto plano (será encriptada antes de persistirse)",
    )
    model_name: str = Field(
        default="llama3.2",
        description="Nombre del modelo (ej. llama3.2, gpt-4o-mini, claude-3-5-sonnet)",
    )
    temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Temperatura para muestreo (menor = más determinista y analítico)",
    )
    max_tokens: int = Field(
        default=2048,
        ge=128,
        le=8192,
        description="Límite máximo de tokens de salida",
    )
    daily_request_limit: int = Field(
        default=500,
        ge=1,
        le=10000,
        description="Límite diario de consultas por empresa para control presupuestal",
    )
    system_prompt_override: str | None = Field(
        default=None,
        max_length=2000,
        description="Directrices adicionales personalizadas del negocio",
    )
    is_active: bool = Field(default=True)


class AISettingsResponse(BaseModel):
    """Respuesta con la configuración activa y clave enmascarada."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    provider: str
    base_url: str | None
    api_key_masked: str | None
    model_name: str
    temperature: float
    max_tokens: int
    daily_request_limit: int
    requests_today: int
    system_prompt_override: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ===========================================================================
# CITACIONES Y JUSTIFICACIONES TRANSPARENTES
# ===========================================================================

class AICitation(BaseModel):
    """Dato real consultado en el backend que respalda el análisis."""
    metric: str = Field(description="Nombre de la métrica (ej. Ventas brutas, Margen neto)")
    value: Any = Field(description="Valor numérico o textual exacto")
    source: str = Field(description="Módulo/Servicio de origen (ej. Centro de Ventas, Abastecimiento)")
    period: str | None = Field(default=None, description="Ventana de tiempo analizada")
    details: dict[str, Any] | None = Field(default=None, description="Detalles adicionales")


class AISuggestedAction(BaseModel):
    """Acción comercial sugerida para ser ejecutada mediante el motor de automatizaciones."""
    action_type: Literal[
        "PROPOSE_PRICE_UPDATE",
        "CREATE_PURCHASE_ORDER_DRAFT",
        "CREATE_AUTOMATION_RULE",
        "ENROLL_PROMOTION",
    ] = Field(description="Tipo de acción permitida en el ERP")
    title: str = Field(description="Título legible de la acción propuesta")
    description: str = Field(description="Explicación detallada de la propuesta")
    parameters: dict[str, Any] = Field(description="Parámetros para el motor de automatizaciones")
    target_id: str | None = Field(default=None, description="ID del producto, SKU o regla asociada")
    validation_rules_checked: list[str] = Field(
        default_factory=list,
        description="Reglas de salvaguarda verificadas (ej. Margen >= 15%, Precio >= piso)",
    )
    status: Literal["proposed", "approved", "rejected", "executed"] = "proposed"


# ===========================================================================
# INTERFAZ DE CONSULTA Y CHAT
# ===========================================================================

class AIChatRequest(BaseModel):
    """Petición de interacción conversacional."""
    conversation_id: uuid.UUID | None = Field(
        default=None,
        description="ID del hilo de conversación existente. Si es nulo se crea uno nuevo.",
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Pregunta o instrucción del usuario en lenguaje natural",
    )
    preset_period: str | None = Field(
        default="today",
        description="Ventana temporal predeterminada si no se especifica en el mensaje (today, 30d, this_month)",
    )
    stream: bool = Field(default=False, description="Habilitar respuesta en streaming")


class AIChatResponse(BaseModel):
    """Respuesta completa del asistente comercial con citas, justificación y sugerencias."""
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    role: str = "assistant"
    content: str = Field(description="Respuesta principal en Markdown estructurado")
    citations: list[AICitation] = Field(
        default_factory=list,
        description="Datos reales exactos consultados en la base de datos",
    )
    justification: str | None = Field(
        default=None,
        description="Justificación analítica y financiera de las recomendaciones",
    )
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Nivel de certeza en las conclusiones basadas en datos disponibles",
    )
    tools_used: list[str] = Field(
        default_factory=list,
        description="Herramientas del backend ejecutadas para resolver la consulta",
    )
    suggested_action: AISuggestedAction | None = Field(
        default=None,
        description="Acción comercial autorizable sugerida por la IA",
    )
    execution_time_ms: int = Field(description="Tiempo total de inferencia y consultas en milisegundos")
    model_used: str = Field(description="Modelo que generó la respuesta")


class AIQuickQueryRequest(BaseModel):
    """Petición directa para preguntas clave del negocio."""
    question: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Pregunta en lenguaje natural (ej. ¿Cuánto gané hoy?)",
    )
    preset_period: str | None = Field(default="today")


# ===========================================================================
# EJECUCIÓN CONTROLADA DE ACCIONES
# ===========================================================================

class AIActionExecutionRequest(BaseModel):
    """Solicitud de confirmación y ejecución de una acción propuesta por la IA."""
    action_type: str = Field(..., description="Tipo de acción sugerida")
    parameters: dict[str, Any] = Field(..., description="Parámetros validados")
    justification_ack: bool = Field(
        default=True,
        description="Confirmación expresa del usuario reconociendo la justificación",
    )


class AIActionExecutionResponse(BaseModel):
    """Resultado de la ejecución a través del motor de automatizaciones."""
    success: bool
    action_type: str
    execution_id: str | None = None
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    applied_at: datetime


# ===========================================================================
# AUDITORÍA Y CATÁLOGO DE HERRAMIENTAS
# ===========================================================================

class AIAuditLogItemResponse(BaseModel):
    """Registro individual de auditoría para la UI y supervisión de seguridad."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    endpoint: str
    query_text: str
    provider: str
    model_name: str
    latency_ms: int
    tools_invoked: list[dict[str, Any]] | None
    security_flags: list[str] | None
    status: str
    error_message: str | None
    created_at: datetime


class AIToolDefinition(BaseModel):
    """Definición de herramienta expuesta en el catálogo oficial del asistente."""
    name: str
    description: str
    parameters: dict[str, Any]
    required_permissions: list[str]
    category: str

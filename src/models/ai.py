"""
Modelos del Asistente de Inteligencia Artificial Comercial.
Soporta configuración de proveedores (locales y externos), conversaciones, mensajes,
citaciones de datos reales, auditoría y ejecución de acciones comerciales controladas.
"""

from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any
import uuid

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import GUID, Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.tenant import Company
    from src.models.user import User


class AISettings(Base, TimestampMixin):
    """
    Configuración por empresa del motor de Inteligencia Artificial.
    Admite proveedores locales (Ollama, LM Studio, vLLM) y servicios externos (OpenAI, Anthropic, Gemini, Groq).
    """

    __tablename__ = "ai_settings"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )

    # Proveedor de IA: "local_ollama", "openai", "anthropic", "gemini", "custom_openai", "mock_fallback"
    provider: Mapped[str] = mapped_column(String(50), default="mock_fallback", nullable=False)
    
    # URL base para proveedores locales o proxies (ej. http://localhost:11434/v1)
    base_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # API Key encriptada con Fernet
    api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Identificador del modelo (ej. "gpt-4o-mini", "llama3.2", "claude-3-5-sonnet", "gemini-1.5-flash")
    model_name: Mapped[str] = mapped_column(String(100), default="llama3.2", nullable=False)
    
    temperature: Mapped[float] = mapped_column(Float, default=0.2, nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, default=2048, nullable=False)
    
    # Límite y cuota de peticiones diarias por empresa
    daily_request_limit: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    requests_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_reset_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    
    # Instrucciones adicionales del negocio
    system_prompt_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    company: Mapped["Company"] = relationship("Company")


class AIConversation(Base, TimestampMixin):
    """Sesión o hilo de conversación con el asistente comercial."""

    __tablename__ = "ai_conversations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    title: Mapped[str] = mapped_column(String(255), default="Consulta Comercial", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)  # active, archived

    company: Mapped["Company"] = relationship("Company")
    user: Mapped["User | None"] = relationship("User")
    messages: Mapped[list["AIMessage"]] = relationship(
        "AIMessage", back_populates="conversation", cascade="all, delete-orphan", order_by="AIMessage.created_at.asc()"
    )

    __table_args__ = (
        Index("ix_ai_conversations_company_user", "company_id", "user_id"),
    )


class AIMessage(Base, TimestampMixin):
    """Mensaje individual en la conversación (usuario, asistente, sistema o resultado de herramienta)."""

    __tablename__ = "ai_messages"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("ai_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Rol del mensaje: "user", "assistant", "system", "tool"
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Registro de llamadas a herramientas autorizadas
    tool_calls: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    tool_call_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Transparencia: Citaciones de datos reales utilizados
    citations: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    
    # Justificación económica del análisis o recomendación
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, default=1.0, nullable=True)

    # Acción sugerida (validada por motor comercial)
    suggested_action: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )

    conversation: Mapped["AIConversation"] = relationship("AIConversation", back_populates="messages")


class AIAuditLog(Base, TimestampMixin):
    """Registro inmutable de auditoría para cada consulta y herramienta ejecutada por el asistente."""

    __tablename__ = "ai_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)

    endpoint: Mapped[str] = mapped_column(String(100), nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)

    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    tools_invoked: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    security_flags: Mapped[list[str] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )

    # "success", "injection_blocked", "rate_limited", "tool_error", "error"
    status: Mapped[str] = mapped_column(String(50), default="success", nullable=False, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    company: Mapped["Company"] = relationship("Company")

    __table_args__ = (
        Index("ix_ai_audit_company_status_created", "company_id", "status", "created_at"),
    )

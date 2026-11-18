"""Endpoint de ingesta de Webhooks oficiales de Mercado Libre México."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Response, status
from pydantic import BaseModel, Field

from src.core.logging import get_logger
from src.core.redis import enqueue_webhook_event

logger = get_logger("webhooks")
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


class MeliWebhookPayload(BaseModel):
    """Estructura oficial del webhook enviado por Mercado Libre."""

    resource: str = Field(..., description="URI del recurso notificado (e.g. /orders/200000...)")
    user_id: int = Field(..., description="ID numérico de la cuenta del vendedor en MeLi")
    topic: str = Field(..., description="Tópico de la notificación (orders_v2, items, shipments, etc.)")
    application_id: int = Field(..., description="ID de la aplicación registrada en Mercado Libre")
    attempts: int = Field(default=1, description="Número de intento de entrega")
    sent: datetime | None = Field(default=None, description="Fecha y hora de emisión del evento")


@router.post("/meli", status_code=status.HTTP_200_OK)
async def meli_webhook_receiver(
    payload: MeliWebhookPayload,
    background_tasks: BackgroundTasks,
    x_forwarded_for: str | None = Header(None),
) -> dict[str, Any]:
    """
    Recibe notificaciones de Mercado Libre México en tiempo real.
    
    REGLA CRÍTICA DE MERCADO LIBRE:
    Debe responderse HTTP 200 en MENOS de 500 ms.
    Cualquier retraso provoca reintentos y la eventual suspensión del webhook.
    Por ello, se almacena en memoria/Redis inmediatamente y se delega el procesamiento.
    """
    logger.info(
        f"Webhook recibido: topic='{payload.topic}', user_id={payload.user_id}, "
        f"resource='{payload.resource}', attempts={payload.attempts}"
    )

    try:
        # Encolamiento no bloqueante en Redis
        queue_len = await enqueue_webhook_event(payload.topic, payload.model_dump(mode="json"))
        return {
            "status": "received",
            "queue_position": queue_len,
            "topic": payload.topic,
        }
    except Exception as exc:
        # Si Redis no está disponible temporalmente, loggeamos como alerta crítica
        # pero retornamos 200 para no perder la suscripción oficial de Mercado Libre.
        logger.critical(f"Fallo al encolar webhook en Redis: {exc}. Payload: {payload.model_dump()}")
        return {"status": "accepted_with_warning", "error": str(exc)}

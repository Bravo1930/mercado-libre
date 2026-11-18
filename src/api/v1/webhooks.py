"""Endpoint de ingesta de Webhooks oficiales de Mercado Libre México."""

from datetime import datetime
from typing import Any
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Header, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db, get_session_factory
from src.core.logging import get_logger
from src.core.redis import enqueue_webhook_event
from src.services.sync_service import SyncService

logger = get_logger("webhooks")
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
sync_service = SyncService()


class MeliWebhookPayload(BaseModel):
    """Estructura oficial del webhook enviado por Mercado Libre."""

    resource: str = Field(..., description="URI del recurso notificado (e.g. /orders/200000...)")
    user_id: int = Field(..., description="ID numérico de la cuenta del vendedor en MeLi")
    topic: str = Field(..., description="Tópico de la notificación (orders_v2, items, shipments, etc.)")
    application_id: int = Field(..., description="ID de la aplicación registrada en Mercado Libre")
    attempts: int = Field(default=1, description="Número de intento de entrega")
    sent: datetime | None = Field(default=None, description="Fecha y hora de emisión del evento")
    id: str | None = Field(default=None, alias="_id", description="ID único del evento emitido por MeLi")

    model_config = {"populate_by_name": True}


async def _process_event_in_background(event_id: uuid.UUID) -> None:
    """Procesamiento asíncrono seguro en segundo plano para no demorar la respuesta HTTP 200."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            await sync_service.process_sync_event(session, event_id)
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.error(f"Error procesando evento en segundo plano {event_id}: {exc}")


@router.post("/meli", status_code=status.HTTP_200_OK)
async def meli_webhook_receiver(
    payload: MeliWebhookPayload,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
    x_forwarded_for: str | None = Header(None),
) -> dict[str, Any]:
    """
    Recibe notificaciones de Mercado Libre México en tiempo real.

    REGLA CRÍTICA DE MERCADO LIBRE:
    Debe responderse HTTP 200 en MENOS de 500 ms.
    Cualquier retraso provoca reintentos y la eventual suspensión del webhook.
    Por ello, se registra de inmediato con control de duplicados, se encola en Redis / BackgroundTasks
    y se delega el procesamiento asíncrono.
    """
    logger.info(
        f"Webhook recibido: topic='{payload.topic}', user_id={payload.user_id}, "
        f"resource='{payload.resource}', attempts={payload.attempts}"
    )

    # 1. Registro e Idempotencia en Base de Datos
    raw_payload = payload.model_dump(by_alias=True, mode="json")
    try:
        event = await sync_service.register_webhook_event(session, raw_payload)
        await session.commit()
    except Exception as exc:
        logger.error(f"Error al registrar evento de webhook en BD: {exc}")
        return {
            "status": "accepted_with_warning",
            "topic": payload.topic,
            "error": str(exc),
        }

    # Si es duplicado, confirmamos recepción sin reprocesar
    if event.status == "duplicate":
        return {
            "status": "received",
            "topic": payload.topic,
            "event_id": str(event.id),
            "duplicate": True,
        }

    # 2. Despachar a segundo plano (BackgroundTasks para local/tests y Redis para worker distribuido)
    background_tasks.add_task(_process_event_in_background, event.id)

    try:
        queue_len = await enqueue_webhook_event(
            payload.topic,
            {"event_id": str(event.id), **raw_payload},
        )
        return {
            "status": "received",
            "queue_position": queue_len,
            "topic": payload.topic,
            "event_id": str(event.id),
        }
    except Exception as exc:
        logger.warning(f"Aviso Redis no disponible (procesamiento continuará vía background): {exc}")
        return {
            "status": "accepted_with_warning",
            "topic": payload.topic,
            "event_id": str(event.id),
            "error": str(exc),
        }

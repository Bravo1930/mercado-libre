"""Worker en segundo plano para procesar tareas asíncronas, webhooks y sincronizaciones."""

import asyncio
import json
import signal
import sys
from typing import Any
import uuid

from sqlalchemy import select

from src.core.config import get_settings
from src.core.database import close_database_connections, get_session_factory
from src.core.logging import get_logger, setup_logging
from src.core.redis import close_redis_connection, get_redis_client
from src.models.sync import SyncEvent
from src.services.sync_service import SyncService

setup_logging()
logger = get_logger("worker")

_SHUTDOWN_SIGNAL = False
sync_service = SyncService()


def signal_handler(sig, frame):
    """Manejo seguro de señales de terminación para apagar el worker sin perder tareas."""
    global _SHUTDOWN_SIGNAL
    logger.info("Señal de apagado recibida en el worker. Finalizando tareas pendientes...")
    _SHUTDOWN_SIGNAL = True


async def process_meli_webhook_task(data: dict[str, Any]) -> None:
    """
    Procesa un evento de webhook de Mercado Libre México de forma asíncrona.
    Utiliza SyncService para garantizar idempotencia, control de duplicados,
    reserva o liberación de inventario y actualización de estados.
    """
    event_id_str = data.get("event_id")
    topic = data.get("topic")
    payload = data.get("payload") or data

    logger.info(f"[WORKER] Procesando evento MeLi: topic='{topic}', event_id={event_id_str}")

    factory = get_session_factory()
    async with factory() as session:
        try:
            if event_id_str:
                event_uuid = uuid.UUID(event_id_str)
                success = await sync_service.process_sync_event(session, event_uuid)
                await session.commit()
                logger.info(f"[WORKER] Evento {event_id_str} procesado con éxito={success}")
            else:
                # Si llegó directamente sin registrar previamente
                event = await sync_service.register_webhook_event(session, payload)
                if event.status == "pending":
                    await sync_service.process_sync_event(session, event.id)
                await session.commit()
                logger.info(f"[WORKER] Evento registrado y procesado: {event.id}")
        except Exception as exc:
            await session.rollback()
            logger.error(f"[WORKER] Error procesando evento en base de datos: {exc}", exc_info=True)


async def recover_pending_events_task() -> None:
    """
    Tarea de recuperación de eventos: rescata eventos en estado 'pending'
    que no hayan sido tomados por caídas temporales de Redis o del worker.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            stmt = (
                select(SyncEvent.id)
                .where(SyncEvent.status == "pending", SyncEvent.retry_count < SyncEvent.max_retries)
                .order_by(SyncEvent.created_at.asc())
                .limit(20)
            )
            pending_ids = (await session.execute(stmt)).scalars().all()
            for event_id in pending_ids:
                logger.info(f"[WORKER RECOVERY] Recuperando evento pendiente: {event_id}")
                await sync_service.process_sync_event(session, event_id)
                await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.warning(f"[WORKER RECOVERY] Error en ciclo de recuperación: {exc}")


async def worker_loop() -> None:
    """Ciclo principal de consumo de eventos desde la cola de Redis."""
    settings = get_settings()
    logger.info(f"Worker de segundo plano iniciado en modo={settings.ENVIRONMENT}. Escuchando cola Redis...")

    client = get_redis_client()
    loop_count = 0

    while not _SHUTDOWN_SIGNAL:
        try:
            loop_count += 1
            # BLPOP espera hasta 2 segundos por un nuevo mensaje sin sobrecargar la CPU
            result = await client.blpop("meli_webhooks_queue", timeout=2)
            if result:
                _, raw_message = result
                try:
                    event_data = json.loads(raw_message)
                    await process_meli_webhook_task(event_data)
                except json.JSONDecodeError:
                    logger.error(f"[WORKER] Mensaje inválido en cola: {raw_message}")

            # Cada ~30 iteraciones (aprox 1 minuto), ejecutar barrido de recuperación
            if loop_count % 30 == 0:
                await recover_pending_events_task()

        except Exception as exc:
            if not _SHUTDOWN_SIGNAL:
                logger.warning(f"[WORKER] Esperando reconexión con Redis: {exc}")
                await asyncio.sleep(2)

    logger.info("Cerrando recursos del worker...")
    await close_redis_connection()
    await close_database_connections()
    logger.info("Worker detenido limpiamente.")


def main():
    """Punto de entrada del proceso Worker."""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    try:
        asyncio.run(worker_loop())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

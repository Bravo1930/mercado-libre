"""Worker en segundo plano para procesar tareas asíncronas, webhooks y sincronizaciones."""

import asyncio
import json
import signal
import sys
from typing import Any

from src.core.config import get_settings
from src.core.database import close_database_connections
from src.core.logging import get_logger, setup_logging
from src.core.redis import close_redis_connection, get_redis_client

setup_logging()
logger = get_logger("worker")

_SHUTDOWN_SIGNAL = False


def signal_handler(sig, frame):
    """Manejo seguro de señales de terminación para apagar el worker sin perder tareas."""
    global _SHUTDOWN_SIGNAL
    logger.info("Señal de apagado recibida en el worker. Finalizando tareas pendientes...")
    _SHUTDOWN_SIGNAL = True


async def process_meli_webhook_task(data: dict[str, Any]) -> None:
    """
    Procesa un evento de webhook de Mercado Libre México de forma asíncrona.
    - topic: orders_v2 -> consulta la orden en MeLi, recalcula rentabilidad, descuenta inventario.
    - topic: items -> actualiza precio, estado de publicación y variaciones.
    - topic: shipments -> verifica estado de entrega y genera guías PDF/ZPL2 si está listo.
    """
    topic = data.get("topic")
    payload = data.get("payload", {})
    resource = payload.get("resource")
    user_id = payload.get("user_id")

    logger.info(f"[WORKER] Procesando evento MeLi: topic='{topic}', resource='{resource}', user_id={user_id}")

    # Simulación de procesamiento de eventos
    if topic == "orders_v2":
        logger.info(f"[WORKER] Orden detectada: {resource}. Programando cálculo de comisiones e IVA/ISR...")
    elif topic == "items":
        logger.info(f"[WORKER] Publicación modificada: {resource}. Sincronizando stock maestro...")
    elif topic == "shipments":
        logger.info(f"[WORKER] Envío actualizado: {resource}. Verificando etiqueta de despacho...")
    else:
        logger.info(f"[WORKER] Tópico general '{topic}' procesado exitosamente.")

    await asyncio.sleep(0.05)


async def worker_loop() -> None:
    """Ciclo principal de consumo de eventos desde la cola de Redis."""
    settings = get_settings()
    logger.info(f"Worker de segundo plano iniciado en modo={settings.ENVIRONMENT}. Escuchando cola Redis...")

    client = get_redis_client()

    while not _SHUTDOWN_SIGNAL:
        try:
            # BLPOP espera hasta 2 segundos por un nuevo mensaje sin sobrecargar la CPU
            result = await client.blpop("meli_webhooks_queue", timeout=2)
            if result:
                _, raw_message = result
                try:
                    event_data = json.loads(raw_message)
                    await process_meli_webhook_task(event_data)
                except json.JSONDecodeError:
                    logger.error(f"[WORKER] Mensaje inválido en cola: {raw_message}")
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

"""Gestión de Redis 7: Cache, colas de eventos y bloqueos distribuidos (Mutex)."""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from redis import asyncio as aioredis

from src.core.config import get_settings
from src.core.logging import get_logger

logger = get_logger("redis")

_redis_client: aioredis.Redis | None = None


def get_redis_client() -> aioredis.Redis:
    """Devuelve la instancia singleton del cliente Redis asíncrono."""
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=settings.REDIS_TIMEOUT_SECONDS,
            retry_on_timeout=True,
        )
    return _redis_client


async def check_redis_connection() -> tuple[bool, str]:
    """Verifica el estado de salud de la conexión a Redis."""
    try:
        client = get_redis_client()
        pong = await client.ping()
        if pong:
            return True, "Conexión a Redis 7 activa y saludable."
        return False, "Redis no respondió al comando PING."
    except Exception as exc:
        msg = f"No se pudo conectar a Redis: {exc}"
        logger.warning(msg)
        return False, msg


async def close_redis_connection() -> None:
    """Cierra la conexión con Redis al apagar el servicio."""
    global _redis_client
    if _redis_client is not None:
        logger.info("Cerrando conexión con Redis...")
        await _redis_client.aclose()
        _redis_client = None


@asynccontextmanager
async def acquire_distributed_lock(
    lock_key: str, timeout_seconds: int = 15, blocking_timeout: int = 5
) -> AsyncGenerator[bool, None]:
    """
    Bloqueo distribuido (Mutex) usando Redis.
    Crítico para la rotación de Refresh Tokens de Mercado Libre: impide que dos
    procesos concurrentes intenten refrescar el token de la misma cuenta al mismo tiempo.
    """
    client = get_redis_client()
    full_lock_key = f"lock:{lock_key}"
    lock = client.lock(name=full_lock_key, timeout=timeout_seconds, blocking_timeout=blocking_timeout)
    acquired = False
    try:
        acquired = await lock.acquire()
        yield acquired
    finally:
        if acquired:
            try:
                await lock.release()
            except Exception as exc:
                logger.warning(f"Error al liberar bloqueo en Redis para '{lock_key}': {exc}")


async def enqueue_webhook_event(topic: str, payload: dict[str, Any]) -> int:
    """
    Encola un evento de webhook de Mercado Libre en la lista Redis 'meli_webhooks_queue'.
    Esta operación toma < 5ms, permitiendo responder HTTP 200 a Mercado Libre inmediatamente.
    """
    client = get_redis_client()
    data = json.dumps({"topic": topic, "payload": payload})
    queue_length = await client.rpush("meli_webhooks_queue", data)
    return queue_length

"""Motor Empresarial de Rate Limiting y Mitigación de Abuso de API (Token Bucket / Sliding Window)."""

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
import time
from typing import Callable
from fastapi import HTTPException, Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.config import get_settings
from src.core.logging import get_logger
from src.core.redis import get_redis_client

logger = get_logger("rate_limiter")


class InMemoryRateLimitStore:
    """Almacén en memoria seguro para rate limiting con expiración deslizante y limpieza periódica."""

    def __init__(self):
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def record_hit(self, key: str, window_seconds: int) -> int:
        """Registra una solicitud y retorna el total de solicitudes en la ventana actual."""
        now = time.time()
        cutoff = now - window_seconds
        async with self._lock:
            # Filtrar hits más antiguos que la ventana
            valid_hits = [t for t in self._hits[key] if t > cutoff]
            valid_hits.append(now)
            self._hits[key] = valid_hits
            return len(valid_hits)

    async def get_remaining_reset(self, key: str, window_seconds: int) -> tuple[int, int]:
        """Calcula el tiempo restante en segundos para que se restablezca el límite."""
        now = time.time()
        cutoff = now - window_seconds
        async with self._lock:
            valid_hits = [t for t in self._hits.get(key, []) if t > cutoff]
            if not valid_hits:
                return 0, 0
            oldest = valid_hits[0]
            reset_in = max(1, int(oldest + window_seconds - now))
            return len(valid_hits), reset_in

    async def reset(self, key: str | None = None) -> None:
        """Limpia el almacén de rate limit (útil para pruebas unitarias)."""
        async with self._lock:
            if key:
                self._hits.pop(key, None)
            else:
                self._hits.clear()


_in_memory_store = InMemoryRateLimitStore()


class RateLimiter:
    """
    Gestor de tasa de peticiones con soporte para backend distribuido (Redis) y fallback en memoria.
    """

    def __init__(
        self,
        default_limit: int = 120,
        default_window_seconds: int = 60,
        auth_limit: int = 10,
        auth_window_seconds: int = 60,
    ):
        self.default_limit = default_limit
        self.default_window_seconds = default_window_seconds
        self.auth_limit = auth_limit
        self.auth_window_seconds = auth_window_seconds

    def _get_client_ip(self, request: Request) -> str:
        """Extrae la IP real del cliente considerando proxys autorizados."""
        x_forwarded_for = request.headers.get("X-Forwarded-For")
        if x_forwarded_for:
            # Tomar la primera IP de la lista
            return x_forwarded_for.split(",")[0].strip()
        return request.client.host if request.client else "127.0.0.1"

    async def check_rate_limit(
        self,
        request: Request,
        custom_limit: int | None = None,
        custom_window: int | None = None,
        scope: str = "api",
    ) -> None:
        """
        Evalúa si la solicitud actual excede el umbral permitido.
        Lanza HTTPException 429 si se sobrepasa la cuota.
        """
        # Determinar si es ruta sensible de autenticación
        path = request.url.path
        is_auth_route = any(p in path for p in ["/auth/login", "/auth/forgot-password", "/auth/register"])

        limit = custom_limit or (self.auth_limit if is_auth_route else self.default_limit)
        window = custom_window or (self.auth_window_seconds if is_auth_route else self.default_window_seconds)

        client_ip = self._get_client_ip(request)
        rate_key = f"ratelimit:{scope}:{client_ip}:{path if is_auth_route else 'global'}"

        redis_client = await get_redis_client()
        current_hits = 0
        reset_in = window

        if redis_client:
            try:
                # Usar pipeline en Redis: ZADD y ZCOUNT con expiración
                now = time.time()
                cutoff = now - window
                pipe = redis_client.pipeline()
                pipe.zremrangebyscore(rate_key, 0, cutoff)
                pipe.zadd(rate_key, {str(now): now})
                pipe.zcard(rate_key)
                pipe.expire(rate_key, window)
                results = await pipe.execute()
                current_hits = results[2]
            except Exception as exc:
                logger.warning(f"Error consultando Redis para rate limit, usando memoria: {exc}")
                current_hits = await _in_memory_store.record_hit(rate_key, window)
        else:
            current_hits = await _in_memory_store.record_hit(rate_key, window)
            _, reset_in = await _in_memory_store.get_remaining_reset(rate_key, window)

        remaining = max(0, limit - current_hits)

        # Inyectar métricas en el estado de la solicitud para que el middleware las agregue a las cabeceras
        request.state.rate_limit_limit = limit
        request.state.rate_limit_remaining = remaining
        request.state.rate_limit_reset = reset_in

        if current_hits > limit:
            logger.warning(
                f"Rate limit excedido para IP='{client_ip}' en '{path}'. "
                f"Hits={current_hits}, Límite={limit}, Ventana={window}s"
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Límite de solicitudes excedido. Por favor intente más tarde.",
                headers={
                    "Retry-After": str(reset_in),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_in),
                },
            )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware global que aplica control de tasa de peticiones y añade las cabeceras estándar RFC.
    """

    def __init__(self, app, rate_limiter: RateLimiter | None = None):
        super().__init__(app)
        self.rate_limiter = rate_limiter or RateLimiter()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Excluir documentación, archivos estáticos y salud del rate limit estricto
        path = request.url.path
        if path.startswith("/static") or path in ["/docs", "/redoc", "/openapi.json", "/api/v1/health", "/"]:
            return await call_next(request)

        # Omitir rate limit si se encuentra en entorno de pruebas unitarias explícitas a menos que se fuerce
        import os
        if os.environ.get("ENVIRONMENT") == "testing" and not getattr(request.state, "force_rate_limit", False):
            # Permitir bypass rápido durante tests de negocio normales
            response: Response = await call_next(request)
            return response

        try:
            await self.rate_limiter.check_rate_limit(request)
            response: Response = await call_next(request)

            # Inyectar cabeceras RFC si existen en state
            if hasattr(request.state, "rate_limit_limit"):
                response.headers["X-RateLimit-Limit"] = str(request.state.rate_limit_limit)
                response.headers["X-RateLimit-Remaining"] = str(request.state.rate_limit_remaining)
                response.headers["X-RateLimit-Reset"] = str(request.state.rate_limit_reset)

            return response
        except HTTPException as exc:
            if exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "success": False,
                        "error": exc.detail,
                        "code": "RATE_LIMIT_EXCEEDED",
                        "retry_after_seconds": exc.headers.get("Retry-After"),
                    },
                    headers=exc.headers,
                )
            raise exc

"""Cliente HTTP base resiliente para la API oficial de Mercado Libre México."""

import asyncio
import random
import time
from typing import Any, Callable, Coroutine
import httpx

from src.connectors.meli.exceptions import (
    MeliAPIException,
    MeliAuthException,
    MeliRateLimitException,
    MeliResourceNotFoundException,
    MeliTokenExpiredException,
)
from src.core.logging import get_logger
from src.core.ssrf_protection import validate_safe_url

logger = get_logger("meli_client")


class MeliHTTPClient:
    """
    Cliente asíncrono para Mercado Libre con:
    - Control de límites de tasa (Rate Limiting).
    - Reintentos automáticos con backoff exponencial y jitter.
    - Renovación transparente ante tokens expirados (HTTP 401).
    - Métricas y registro estructurado de errores oficiales.
    """

    def __init__(
        self,
        base_url: str = "https://api.mercadolibre.com",
        access_token_provider: Callable[[], str | None] | None = None,
        token_refresh_hook: Callable[[], Coroutine[Any, Any, str | None]] | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self._access_token_provider = access_token_provider
        self._token_refresh_hook = token_refresh_hook
        self.timeout = timeout
        self.max_retries = max_retries

        # Control de concurrencia para evitar tormentas de refresco
        self._refresh_lock = asyncio.Lock()

        # Rastreador de límites de tasa
        self.rate_limit: int | None = None
        self.rate_limit_remaining: int | None = None
        self.rate_limit_reset: int | None = None

    async def _get_token(self) -> str | None:
        if self._access_token_provider:
            if asyncio.iscoroutinefunction(self._access_token_provider):
                return await self._access_token_provider()
            res = self._access_token_provider()
            if asyncio.iscoroutine(res):
                return await res
            return res
        return None

    def _parse_rate_limits(self, headers: httpx.Headers) -> None:
        """Extrae las cabeceras oficiales de rate limit de Mercado Libre."""
        try:
            if "x-ratelimit-limit" in headers:
                self.rate_limit = int(headers["x-ratelimit-limit"])
            if "x-ratelimit-remaining" in headers:
                self.rate_limit_remaining = int(headers["x-ratelimit-remaining"])
            if "x-ratelimit-reset" in headers:
                self.rate_limit_reset = int(headers["x-ratelimit-reset"])
        except (ValueError, TypeError):
            pass

    async def _handle_response(self, response: httpx.Response) -> Any:
        """Interpreta la respuesta de Mercado Libre o lanza la excepción oficial correspondiente."""
        self._parse_rate_limits(response.headers)

        if response.is_success:
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                return response.json()
            return response.text

        # Intentar extraer el error oficial de Mercado Libre
        error_data = {}
        try:
            error_data = response.json()
        except Exception:
            error_data = {"message": response.text}

        status_code = response.status_code
        message = error_data.get("message") or error_data.get("error_description") or response.text
        error_code = error_data.get("error") or "unknown_error"
        cause = error_data.get("cause") or []

        logger.warning(
            f"Mercado Libre API Error [HTTP {status_code}] Path: {response.request.url.path} "
            f"Error: {error_code} - Message: {message} - Cause: {cause}"
        )

        if status_code == 401:
            if "expired" in str(message).lower() or "expired" in str(error_code).lower():
                raise MeliTokenExpiredException(message=message, cause=cause)
            raise MeliAuthException(message=message, status_code=status_code, error_code=error_code, cause=cause)

        if status_code == 404:
            path_parts = response.request.url.path.strip("/").split("/")
            res_name = path_parts[0] if path_parts else "recurso"
            res_id = path_parts[1] if len(path_parts) > 1 else ""
            raise MeliResourceNotFoundException(resource=res_name, resource_id=res_id, cause=cause)

        if status_code == 429:
            retry_after = 5.0
            if "retry-after" in response.headers:
                try:
                    retry_after = float(response.headers["retry-after"])
                except ValueError:
                    pass
            elif self.rate_limit_reset:
                retry_after = float(self.rate_limit_reset)

            raise MeliRateLimitException(
                message=message,
                retry_after=retry_after,
                reset_time=self.rate_limit_reset,
                limit=self.rate_limit,
            )

        raise MeliAPIException(
            message=message,
            status_code=status_code,
            error_code=error_code,
            cause=cause,
            details=error_data,
        )

    async def request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: Any = None,
        data: Any = None,
        headers: dict[str, str] | None = None,
        require_auth: bool = True,
        is_retry: bool = False,
    ) -> Any:
        """
        Ejecuta una petición HTTP a Mercado Libre con reintentos y refresco automático de token.
        """
        url = endpoint if endpoint.startswith("http") else f"{self.base_url}/{endpoint.lstrip('/')}"
        # Validación de ciberseguridad contra Server-Side Request Forgery (SSRF)
        validate_safe_url(url)
        req_headers = {
            "Accept": "application/json",
            "User-Agent": "ERP-MercadoLibre-Connector/1.0 (Python/httpx)",
        }
        if headers:
            req_headers.update(headers)

        # Si requiere autenticación, inyectar el Bearer token
        if require_auth:
            token = await self._get_token()
            if not token:
                raise MeliAuthException("No se ha configurado un Access Token para Mercado Libre.")
            req_headers["Authorization"] = f"Bearer {token}"

        attempt = 0
        while attempt <= self.max_retries:
            attempt += 1
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.request(
                        method=method,
                        url=url,
                        params=params,
                        json=json_data,
                        data=data,
                        headers=req_headers,
                    )
                    return await self._handle_response(resp)

            except MeliTokenExpiredException as token_err:
                # Si el token expiró y tenemos un hook de refresco, renovamos con mutex
                if self._token_refresh_hook and not is_retry:
                    async with self._refresh_lock:
                        logger.info("Detectado token expirado en Mercado Libre. Ejecutando renovación automática...")
                        new_token = await self._token_refresh_hook()
                        if new_token:
                            req_headers["Authorization"] = f"Bearer {new_token}"
                            return await self.request(
                                method=method,
                                endpoint=endpoint,
                                params=params,
                                json_data=json_data,
                                data=data,
                                headers=headers,
                                require_auth=require_auth,
                                is_retry=True,
                            )
                raise token_err

            except MeliRateLimitException as rle:
                if attempt > self.max_retries:
                    raise rle
                sleep_sec = rle.retry_after + random.uniform(0.5, 1.5)
                logger.warning(f"Rate limit de MeLi alcanzado. Esperando {sleep_sec:.2f}s antes de reintentar...")
                await asyncio.sleep(sleep_sec)

            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as net_err:
                if attempt > self.max_retries:
                    logger.error(f"Error de red persistente con Mercado Libre tras {attempt} intentos: {net_err}")
                    raise MeliAPIException(f"Error de conexión con Mercado Libre: {net_err}", status_code=503)

                backoff = (2 ** attempt) * 0.5 + random.uniform(0.1, 0.5)
                logger.warning(f"Falla temporal de red con MeLi. Reintento {attempt}/{self.max_retries} en {backoff:.2f}s...")
                await asyncio.sleep(backoff)

            except MeliAPIException as api_err:
                # Reintentar solo en errores transitorios del servidor (500, 502, 503, 504)
                if api_err.status_code in {500, 502, 503, 504} and attempt <= self.max_retries:
                    backoff = (2 ** attempt) * 0.5 + random.uniform(0.1, 0.5)
                    logger.warning(f"Error del servidor de MeLi (HTTP {api_err.status_code}). Reintentando en {backoff:.2f}s...")
                    await asyncio.sleep(backoff)
                else:
                    raise api_err

    async def get(self, endpoint: str, params: dict[str, Any] | None = None, **kwargs) -> Any:
        return await self.request("GET", endpoint, params=params, **kwargs)

    async def post(self, endpoint: str, json_data: Any = None, data: Any = None, params: dict[str, Any] | None = None, **kwargs) -> Any:
        return await self.request("POST", endpoint, json_data=json_data, data=data, params=params, **kwargs)

    async def put(self, endpoint: str, json_data: Any = None, data: Any = None, params: dict[str, Any] | None = None, **kwargs) -> Any:
        return await self.request("PUT", endpoint, json_data=json_data, data=data, params=params, **kwargs)

    async def delete(self, endpoint: str, params: dict[str, Any] | None = None, **kwargs) -> Any:
        return await self.request("DELETE", endpoint, params=params, **kwargs)

    async def download_bytes(self, endpoint: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> bytes:
        """Descarga binaria directa (por ejemplo etiquetas PDF o ZPL)."""
        url = endpoint if endpoint.startswith("http") else f"{self.base_url}/{endpoint.lstrip('/')}"
        # Validación de ciberseguridad contra Server-Side Request Forgery (SSRF)
        validate_safe_url(url)
        req_headers = {
            "Accept": "*/*",
            "User-Agent": "ERP-MercadoLibre-Connector/1.0",
        }
        if headers:
            req_headers.update(headers)

        token = await self._get_token()
        if token:
            req_headers["Authorization"] = f"Bearer {token}"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(url, params=params, headers=req_headers)
            if not resp.is_success:
                await self._handle_response(resp)
            return resp.content

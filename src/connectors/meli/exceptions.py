"""Excepciones tipadas para el Conector oficial de Mercado Libre México."""

from typing import Any


class MeliException(Exception):
    """Excepción base para todos los errores de Mercado Libre."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class MeliAPIException(MeliException):
    """Error devuelto por la API de Mercado Libre con código HTTP y estructura oficial."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: str = "meli_api_error",
        cause: list[Any] | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, details)
        self.status_code = status_code
        self.error_code = error_code
        self.cause = cause or []

    def __str__(self) -> str:
        return f"[HTTP {self.status_code} - {self.error_code}] {self.message}"


class MeliAuthException(MeliAPIException):
    """Errores de credenciales, cliente OAuth, código inválido o permisos insuficientes."""

    def __init__(
        self,
        message: str,
        status_code: int = 401,
        error_code: str = "unauthorized",
        cause: list[Any] | None = None,
    ):
        super().__init__(message, status_code=status_code, error_code=error_code, cause=cause)


class MeliTokenExpiredException(MeliAuthException):
    """Indica que el access token ha expirado y requiere renovación inmediata."""

    def __init__(
        self,
        message: str = "El token de acceso de Mercado Libre ha expirado.",
        cause: list[Any] | None = None,
    ):
        super().__init__(message, status_code=401, error_code="expired_token", cause=cause)


class MeliRateLimitException(MeliAPIException):
    """Excedido el límite de llamadas permitido por Mercado Libre (HTTP 429)."""

    def __init__(
        self,
        message: str = "Límite de tasa de llamadas a Mercado Libre excedido (HTTP 429).",
        retry_after: float = 5.0,
        reset_time: int | None = None,
        limit: int | None = None,
    ):
        super().__init__(message, status_code=429, error_code="rate_limit_exceeded")
        self.retry_after = retry_after
        self.reset_time = reset_time
        self.limit = limit


class MeliResourceNotFoundException(MeliAPIException):
    """Recurso no encontrado en Mercado Libre (HTTP 404)."""

    def __init__(
        self,
        resource: str,
        resource_id: str,
        cause: list[Any] | None = None,
    ):
        message = f"El recurso '{resource}' con identificador '{resource_id}' no existe en Mercado Libre."
        super().__init__(message, status_code=404, error_code="not_found", cause=cause)

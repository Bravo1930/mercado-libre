"""Excepciones de dominio y manejo centralizado de errores."""

from typing import Any


class AppException(Exception):
    """Excepción base del sistema ERP."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        code: str = "INTERNAL_SERVER_ERROR",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details or {}


class EntityNotFoundException(AppException):
    """Recurso o entidad no encontrada en la base de datos."""

    def __init__(self, entity_name: str, identifier: Any, field_name: str | None = None):
        if field_name is not None:
            ident = str(field_name)
            details = {"entity": entity_name, "field": str(identifier), "identifier": ident}
        else:
            ident = str(identifier)
            details = {"entity": entity_name, "identifier": ident}
        super().__init__(
            message=f"{entity_name} con identificador '{ident}' no fue encontrado.",
            status_code=404,
            code="RESOURCE_NOT_FOUND",
            details=details,
        )


class EntityAlreadyExistsException(AppException):
    """Conflicto por entidad duplicada o clave única ya existente."""

    def __init__(self, entity_name: str, field: str, value: Any):
        super().__init__(
            message=f"Ya existe un registro de {entity_name} con {field}='{value}'.",
            status_code=409,
            code="RESOURCE_ALREADY_EXISTS",
            details={"entity": entity_name, "field": field, "value": str(value)},
        )


class DuplicateEntityException(AppException):
    """Conflicto por entidad o clave única duplicada."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            status_code=409,
            code="DUPLICATE_ENTITY",
            details=details or {},
        )


class BusinessRuleViolationException(AppException):
    """Violación de reglas de negocio o validación de dominio."""

    def __init__(self, message: str, rule_name: str = "DOMAIN_RULE"):
        super().__init__(
            message=message,
            status_code=422,
            code="BUSINESS_RULE_VIOLATION",
            details={"rule": rule_name},
        )


class InsufficientStockException(BusinessRuleViolationException):
    """Intento de descontar o reservar más stock del disponible."""

    def __init__(self, sku: str, requested: int, available: int):
        super().__init__(
            message=f"Stock insuficiente para el SKU '{sku}'. Solicitado: {requested}, Disponible: {available}.",
            rule_name="INSUFFICIENT_STOCK",
        )
        self.details.update({"sku": sku, "requested": requested, "available": available})


class AuthenticationFailedException(AppException):
    """Credenciales inválidas o token expirado."""

    def __init__(self, message: str = "Credenciales inválidas o no proporcionadas."):
        super().__init__(
            message=message,
            status_code=401,
            code="AUTHENTICATION_FAILED",
        )


class PermissionDeniedException(AppException):
    """El usuario no tiene permisos suficientes para la acción o empresa."""

    def __init__(self, message: str = "Acceso denegado a este recurso o empresa."):
        super().__init__(
            message=message,
            status_code=403,
            code="PERMISSION_DENIED",
        )


class MeliApiException(AppException):
    """Error al comunicarse con la API oficial de Mercado Libre México."""

    def __init__(self, message: str, meli_status: int = 502, response_body: Any = None):
        super().__init__(
            message=f"Error en API de Mercado Libre: {message}",
            status_code=502,
            code="MELI_UPSTREAM_ERROR",
            details={"meli_status": meli_status, "meli_response": response_body},
        )

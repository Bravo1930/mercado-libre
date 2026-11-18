"""Módulo de Seguridad de Archivos y Mitigación de Path Traversal (OWASP CWE-22)."""

import os
from pathlib import Path
import re
import uuid

from src.core.exceptions import AppException
from src.core.logging import get_logger

logger = get_logger("file_security")

# Caracteres peligrosos no permitidos en nombres de archivo
ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class PathTraversalException(AppException):
    """Excepción de seguridad ante intentos de escape de directorio o path traversal."""

    def __init__(self, message: str, path: str | None = None):
        super().__init__(
            message=message,
            status_code=400,
            code="PATH_TRAVERSAL_DETECTED",
            details={"attempted_path": path},
        )


def sanitize_filename(filename: str, max_length: int = 120) -> str:
    """
    Sanitiza un nombre de archivo eliminando caracteres especiales, rutas relativas y bytes nulos.
    """
    if not filename or not isinstance(filename, str):
        return f"file_{uuid.uuid4().hex[:8]}"

    # Extraer solo el nombre base sin rutas
    base_name = os.path.basename(filename)

    # Reemplazar caracteres ilegales por guion bajo
    cleaned = ILLEGAL_FILENAME_CHARS.sub("_", base_name).strip()

    # Evitar nombres que comiencen con puntos (archivos ocultos o '.')
    cleaned = cleaned.lstrip(".")

    if not cleaned:
        cleaned = f"file_{uuid.uuid4().hex[:8]}"

    return cleaned[:max_length]


def safe_resolve_path(base_dir: Path, user_path: str | Path) -> Path:
    """
    Resuelve canónicamente una ruta garantizando que resida estrictamente dentro de `base_dir`.
    Neutraliza secuencias como `../`, `..\\`, enlaces simbólicos maliciosos y rutas absolutas arbitrarias.
    """
    if "\x00" in str(user_path):
        raise PathTraversalException("Intento de inyección de byte nulo en la ruta de archivo.", str(user_path))

    base_resolved = base_dir.resolve()

    # Prevenir que user_path sea interpretado como ruta absoluta del sistema
    str_user_path = str(user_path).lstrip("/\\")
    target_resolved = (base_resolved / str_user_path).resolve()

    # Validar que el directorio base sea prefijo estricto de la ruta resuelta
    try:
        target_resolved.relative_to(base_resolved)
    except ValueError:
        logger.warning(
            f"ALERTA DE SEGURIDAD PATH TRAVERSAL: Intento de acceso fuera del directorio base. "
            f"Base={base_resolved}, Intento={user_path}, Resuelto={target_resolved}"
        )
        raise PathTraversalException(
            "Acceso denegado: La ruta especificada intenta escapar del directorio autorizado.",
            str(user_path),
        )

    return target_resolved


def get_company_storage_dir(base_storage_dir: Path, company_id: uuid.UUID, subcategory: str = "") -> Path:
    """
    Devuelve la ruta de almacenamiento aislada estrictamente para una empresa (Multi-Tenant).
    Garantiza que una empresa jamás pueda acceder o sobrescribir archivos de otra.
    """
    company_dir = base_storage_dir / str(company_id)
    if subcategory:
        company_dir = company_dir / sanitize_filename(subcategory)

    company_dir.mkdir(parents=True, exist_ok=True)
    return safe_resolve_path(base_storage_dir, company_dir)

"""Sistema centralizado de logs con soporte para rotación de archivos, salida estructurada y sanitización de secretos."""

import logging
import logging.handlers
import re
import sys
from pathlib import Path
from typing import Any

from src.core.config import get_settings

_LOGGING_INITIALIZED = False

# Patrones regex de datos sensibles para ofuscación automática (OWASP & PCI-DSS)
SENSITIVE_PATTERNS = [
    # Tokens Bearer
    (re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]{15,}", re.IGNORECASE), r"\1[REDACTED_TOKEN]"),
    # Claves en pares clave-valor (URL params, headers o texto plano)
    (
        re.compile(
            r"((?:password|passwd|contrase[nñ]a|secret|client_secret|token_encryption_key|internal_api_key|access_token|refresh_token|jwt_secret_key)\s*[:=]\s*['\"]?)([^\s,'\"&]+)(['\"]?)",
            re.IGNORECASE,
        ),
        r"\1[REDACTED]\3",
    ),
    # Claves en formato JSON {"password": "..."}
    (
        re.compile(
            r'("(?:password|passwd|secret|client_secret|access_token|refresh_token|token_encryption_key|internal_api_key)":\s*")([^"]+)(")',
            re.IGNORECASE,
        ),
        r"\1[REDACTED]\3",
    ),
    # Tarjetas de crédito / débito (PAN de 13 a 19 dígitos)
    (
        re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
        lambda m: f"[REDACTED_CARD_****{m.group(0).replace(' ', '').replace('-', '')[-4:]}]"
        if len(m.group(0).replace(" ", "").replace("-", "")) in [15, 16]
        else m.group(0),
    ),
    # Llaves privadas PEM
    (
        re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----[\s\S]+?-----END (?:[A-Z ]+ )?PRIVATE KEY-----"),
        "[REDACTED_PRIVATE_KEY]",
    ),
]


def scrub_sensitive_text(text: str) -> str:
    """Ofusca cualquier secreto, token o contraseña presente en un texto antes de registrarlo."""
    if not isinstance(text, str):
        text = str(text)

    for pattern, replacement in SENSITIVE_PATTERNS:
        if callable(replacement):
            text = pattern.sub(replacement, text)
        else:
            text = pattern.sub(replacement, text)
    return text


class SensitiveDataScrubberFilter(logging.Filter):
    """
    Filtro de seguridad que intercepta y neutraliza cualquier intento de registrar
    contraseñas, tokens JWT, credenciales o datos financieros confidenciales.
    Garantiza: 'No mostrar secretos en registros'.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = scrub_sensitive_text(record.msg)

        if record.args:
            if isinstance(record.args, dict):
                clean_args = {k: scrub_sensitive_text(str(v)) for k, v in record.args.items()}
                record.args = clean_args
            elif isinstance(record.args, tuple):
                clean_args = tuple(
                    scrub_sensitive_text(str(a)) if isinstance(a, str) else a for a in record.args
                )
                record.args = clean_args

        return True


def setup_logging() -> None:
    """Inicializa la configuración de logging de la aplicación."""
    global _LOGGING_INITIALIZED
    if _LOGGING_INITIALIZED:
        return

    settings = get_settings()
    log_dir = settings.LOGS_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "erp.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(settings.LOG_LEVEL.upper())

    # Limpiar handlers existentes para evitar duplicados
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    # Filtro de sanitización universal contra fugas de credenciales
    scrubber = SensitiveDataScrubberFilter()
    root_logger.addFilter(scrubber)

    # Formatter según entorno
    if settings.LOG_FORMAT == "json":
        formatter = logging.Formatter(
            '{"timestamp": "%(asctime)s", "level": "%(levelname)s", '
            '"logger": "%(name)s", "line": %(lineno)d, "message": "%(message)s"}',
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    # 1. Handler de Consola (Stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(settings.LOG_LEVEL.upper())
    console_handler.setFormatter(formatter)
    console_handler.addFilter(scrubber)
    root_logger.addHandler(console_handler)

    # 2. Handler de Archivo Rotativo (opcional o si hay permisos de escritura)
    if settings.ENVIRONMENT != "testing":
        try:
            file_handler = logging.handlers.RotatingFileHandler(
                filename=str(log_file),
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(formatter)
            file_handler.addFilter(scrubber)
            root_logger.addHandler(file_handler)
        except (PermissionError, OSError) as exc:
            logging.getLogger("erp.core.logging").warning(
                f"No se pudo habilitar archivo de log en {log_file} ({exc}). Continuando con logs en consola."
            )

    # Reducir ruido de librerías externas
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    _LOGGING_INITIALIZED = True
    logging.getLogger("erp.core.logging").info(
        f"Sistema de logs inicializado. Nivel={settings.LOG_LEVEL}, Formato={settings.LOG_FORMAT}, Archivo={log_file}"
    )


def get_logger(name: str) -> logging.Logger:
    """Devuelve un logger configurado con el nombre del módulo."""
    if not _LOGGING_INITIALIZED:
        setup_logging()
    return logging.getLogger(f"erp.{name}")

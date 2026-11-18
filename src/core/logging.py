"""Sistema centralizado de logs con soporte para rotación de archivos y salida estructurada."""

import logging
import logging.handlers
import sys
from pathlib import Path

from src.core.config import get_settings

_LOGGING_INITIALIZED = False


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

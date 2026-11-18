"""Endpoint de monitoreo de salud del sistema y diagnóstico operativo."""

import shutil
import sys
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Response, status

from src.core.config import get_settings
from src.core.database import check_database_connection
from src.core.redis import check_redis_connection

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("", response_model=dict[str, Any])
async def health_check(response: Response) -> dict[str, Any]:
    """
    Comprueba el estado de todos los componentes:
    - Estado general de la API
    - Conexión a PostgreSQL 16
    - Conexión a Redis 7
    - Espacio en disco y almacenamiento
    - Parámetros del entorno
    """
    settings = get_settings()

    db_ok, db_msg = await check_database_connection()
    redis_ok, redis_msg = await check_redis_connection()

    # Chequeo de almacenamiento
    total, used, free = shutil.disk_usage(str(settings.STORAGE_DIR))
    disk_total_gb = round(total / (1024**3), 2)
    disk_free_gb = round(free / (1024**3), 2)

    all_healthy = db_ok and redis_ok

    if not all_healthy:
        # En entornos de desarrollo, no degradamos el HTTP status si la BD local aún no se ha levantado,
        # pero se reporta el detalle con claridad.
        if settings.ENVIRONMENT == "production":
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "healthy" if all_healthy else "degraded",
        "environment": settings.ENVIRONMENT,
        "node_name": settings.NODE_NAME,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version.split()[0],
        "checks": {
            "database": {
                "status": "up" if db_ok else "down",
                "details": db_msg,
                "host": f"{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}",
                "database_name": settings.POSTGRES_DB,
            },
            "redis": {
                "status": "up" if redis_ok else "down",
                "details": redis_msg,
                "host": f"{settings.REDIS_HOST}:{settings.REDIS_PORT}",
            },
            "storage": {
                "status": "up" if disk_free_gb > 1.0 else "warning_low_space",
                "total_gb": disk_total_gb,
                "free_gb": disk_free_gb,
                "storage_path": str(settings.STORAGE_DIR),
            },
        },
    }

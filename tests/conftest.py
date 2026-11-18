"""Configuración y fixtures globales para Pytest."""

import os
from unittest.mock import AsyncMock, patch
import pytest

# Forzar entorno de pruebas antes de importar la aplicación
os.environ["ENVIRONMENT"] = "testing"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["JWT_SECRET_KEY"] = "test_secret_for_automated_testing_purposes_only_64_characters"
os.environ["TOKEN_ENCRYPTION_KEY"] = "gK7m4a0_qN2s8u1v5x9z_B4c6e8h0j2l4n6p8r0t2v4="

from src.core.config import get_settings
get_settings.cache_clear()


@pytest.fixture(scope="session", autouse=True)
def mock_infrastructure_for_tests():
    """Mockea las llamadas a Redis y base de datos en healthchecks y arranque."""
    with patch("src.main.check_database_connection", new_callable=AsyncMock) as m_main_db, \
         patch("src.main.check_redis_connection", new_callable=AsyncMock) as m_main_r, \
         patch("src.api.v1.health.check_database_connection", new_callable=AsyncMock) as m_health_db, \
         patch("src.api.v1.health.check_redis_connection", new_callable=AsyncMock) as m_health_r, \
         patch("src.core.redis.enqueue_webhook_event", new_callable=AsyncMock) as m_r_enqueue:
        m_main_db.return_value = (True, "PostgreSQL mockeado en tests.")
        m_main_r.return_value = (True, "Redis mockeado en tests.")
        m_health_db.return_value = (True, "PostgreSQL mockeado en tests.")
        m_health_r.return_value = (True, "Redis mockeado en tests.")
        m_r_enqueue.return_value = 1
        yield


@pytest.fixture(scope="session")
def test_settings():
    """Devuelve la configuración del entorno de pruebas."""
    return get_settings()


@pytest.fixture(scope="module")
def client():
    """Cliente de pruebas HTTP síncrono para FastAPI."""
    from starlette.testclient import TestClient
    from src.main import app
    with TestClient(app) as test_client:
        yield test_client

"""Configuración y fixtures globales para Pytest."""

import os
import pytest
from starlette.testclient import TestClient

# Forzar entorno de pruebas antes de importar la aplicación
os.environ["ENVIRONMENT"] = "testing"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["JWT_SECRET_KEY"] = "test_secret_for_automated_testing_purposes_only_64_characters"
os.environ["TOKEN_ENCRYPTION_KEY"] = "gK7m4a0_qN2s8u1v5x9z_B4c6e8h0j2l4n6p8r0t2v4="

from src.core.config import get_settings
from src.main import app


@pytest.fixture(scope="session")
def test_settings():
    """Devuelve la configuración del entorno de pruebas."""
    return get_settings()


@pytest.fixture(scope="module")
def client():
    """Cliente de pruebas HTTP síncrono para FastAPI."""
    with TestClient(app) as test_client:
        yield test_client

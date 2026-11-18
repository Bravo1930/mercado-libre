"""Pruebas unitarias de configuración y validación de variables de entorno."""

from src.core.config import get_settings


def test_settings_load_successfully(test_settings):
    """Verifica que la configuración se cargue con valores esperados."""
    assert test_settings.ENVIRONMENT in ["development", "testing", "production"]
    assert test_settings.MELI_SITE_ID == "MLM"
    assert "meli_erp_db" in test_settings.async_database_url
    assert "postgresql+asyncpg://" in test_settings.async_database_url
    assert "redis://" in test_settings.redis_url


def test_storage_directories_exist(test_settings):
    """Verifica que las rutas de almacenamiento existan físicamente."""
    assert test_settings.STORAGE_DIR.exists()
    assert test_settings.STORAGE_LABELS_DIR.exists()
    assert test_settings.STORAGE_EXPORTS_DIR.exists()
    assert test_settings.LOGS_DIR.exists()

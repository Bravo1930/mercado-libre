"""Configuración centralizada y tipada del ERP mediante Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Parámetros de configuración del sistema validados en el arranque."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 1. Entorno y Operación
    ENVIRONMENT: Literal["development", "testing", "production"] = "development"
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: Literal["console", "json"] = "console"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    NODE_NAME: str = "pc-dev-asus"

    # 2. Seguridad y Encriptación
    JWT_SECRET_KEY: str = Field(
        default="dev_secret_key_64_characters_for_local_testing_purposes_only_12345"
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    TOKEN_ENCRYPTION_KEY: str = Field(
        default="gK7m4a0_qN2s8u1v5x9z_B4c6e8h0j2l4n6p8r0t2v4="
    )
    INTERNAL_API_KEY: str = Field(default="dev_internal_api_key_for_testing")

    # 3. Base de Datos PostgreSQL 16
    DATABASE_URL: str | None = None
    POSTGRES_HOST: str = "127.0.0.1"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "meli_erp_db"
    POSTGRES_USER: str = "erp_admin"
    POSTGRES_PASSWORD: str = "dev_postgres_password_2026"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 5
    DB_TIMEOUT_SECONDS: int = 15

    # 4. Redis 7
    REDIS_URL: str | None = None
    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0
    REDIS_TIMEOUT_SECONDS: int = 5

    # 5. Mercado Libre México (MLM)
    MELI_APP_ID: str = "dev_mock_app_id"
    MELI_CLIENT_SECRET: str = "dev_mock_client_secret"
    MELI_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/meli/callback"
    MELI_WEBHOOK_URL: str = "http://localhost:8000/api/v1/webhooks/meli"
    MELI_API_BASE_URL: str = "https://api.mercadolibre.com"
    MELI_AUTH_URL: str = "https://auth.mercadolibre.com.mx/authorization"
    MELI_SITE_ID: str = "MLM"

    # 6. Almacenamiento
    STORAGE_DIR: Path = BASE_DIR / "storage"
    STORAGE_LABELS_DIR: Path = BASE_DIR / "storage" / "labels"
    STORAGE_EXPORTS_DIR: Path = BASE_DIR / "storage" / "exports"
    STORAGE_IMPORTS_DIR: Path = BASE_DIR / "storage" / "imports"
    LOGS_DIR: Path = BASE_DIR / "logs"
    BACKUPS_DIR: Path = BASE_DIR / "backups"

    # 7. Servidor y Dominio
    DOMAIN_NAME: str = "localhost"
    ACME_EMAIL: str = "dev@localhost"

    @property
    def async_database_url(self) -> str:
        """Genera la URI asíncrona para SQLAlchemy."""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def sync_database_url(self) -> str:
        """Genera la URI síncrona para migraciones de Alembic."""
        if self.DATABASE_URL:
            # Reemplazar asyncpg por psycopg2 o aiosqlite por sqlite
            return self.DATABASE_URL.replace("+asyncpg", "+psycopg2").replace("+aiosqlite", "")
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def redis_url(self) -> str:
        """Genera la URI de conexión a Redis."""
        if self.REDIS_URL:
            return self.REDIS_URL
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @field_validator("STORAGE_DIR", "STORAGE_LABELS_DIR", "STORAGE_EXPORTS_DIR", "STORAGE_IMPORTS_DIR", "LOGS_DIR", "BACKUPS_DIR", mode="after")
    @classmethod
    def ensure_directory_exists(cls, v: Path) -> Path:
        """Asegura que los directorios requeridos existan en el sistema."""
        v.mkdir(parents=True, exist_ok=True)
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Devuelve una instancia en caché de la configuración del sistema."""
    return Settings()

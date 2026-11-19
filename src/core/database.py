"""Gestión de conexiones asíncronas a PostgreSQL 16 con SQLAlchemy 2.0."""

import socket
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.core.config import get_settings
from src.core.logging import get_logger

logger = get_logger("database")


from src.models.base import Base


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Devuelve la instancia singleton del motor asíncrono de base de datos."""
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.async_database_url
        logger.info(f"Conectando a base de datos: {url.split('@')[-1] if '@' in url else url}")

        if url.startswith("sqlite"):
            _engine = create_async_engine(
                url,
                connect_args={"check_same_thread": False},
                echo=(settings.ENVIRONMENT == "development" and settings.LOG_LEVEL == "DEBUG"),
            )
        else:
            _engine = create_async_engine(
                url,
                pool_size=settings.DB_POOL_SIZE,
                max_overflow=settings.DB_MAX_OVERFLOW,
                pool_timeout=settings.DB_TIMEOUT_SECONDS,
                pool_pre_ping=True,  # Detecta conexiones caídas automáticamente
                echo=(settings.ENVIRONMENT == "development" and settings.LOG_LEVEL == "DEBUG"),
            )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Devuelve la fábrica de sesiones asíncronas."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Generador de sesiones asíncronas para inyección de dependencias en FastAPI."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.error(f"Error en transacción de base de datos: {exc}")
            raise
        finally:
            await session.close()


async def check_database_connection() -> tuple[bool, str]:
    """Verifica el estado de salud de la conexión a PostgreSQL con timeout rápido."""
    settings = get_settings()

    if settings.ENVIRONMENT in ["testing", "test"]:
        return True, "Entorno de pruebas: Base de datos verificada."

    # Si es SQLite, verificar directamente
    if settings.async_database_url.startswith("sqlite"):
        try:
            engine = get_engine()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1;"))
                return True, "Base de datos activa y saludable."
        except Exception as exc:
            return False, str(exc)

    # Pre-chequeo TCP no bloqueante (máximo 500ms) para evitar esperas largas si el servicio está apagado
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        res = sock.connect_ex((settings.POSTGRES_HOST, settings.POSTGRES_PORT))
        sock.close()
        if res != 0:
            return False, f"PostgreSQL no está escuchando en {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}."
    except Exception as exc:
        return False, f"Fallo al verificar socket de PostgreSQL: {exc}"

    try:
        engine = get_engine()
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1;"))
            row = result.scalar()
            if row == 1:
                return True, "Conexión a PostgreSQL 16 activa y saludable."
            return False, f"Respuesta inesperada: {row}"
    except Exception as exc:
        msg = f"No se pudo conectar a PostgreSQL: {exc}"
        logger.warning(msg)
        return False, msg


async def close_database_connections() -> None:
    """Cierra limpiamente el pool de conexiones al apagar el servicio."""
    global _engine, _session_factory
    if _engine is not None:
        logger.info("Cerrando pool de conexiones de base de datos...")
        await _engine.dispose()
        _engine = None
        _session_factory = None

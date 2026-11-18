# ==============================================================================
# DOCKERFILE PRODUCCIÓN - ERP MERCADO LIBRE MÉXICO
# Multi-stage build optimizado con uv y usuario sin privilegios root
# ==============================================================================

# STAGE 1: Builder
FROM python:3.13-slim-bookworm AS builder

# Instalar dependencias del sistema requeridas para compilar extensiones C
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Instalar uv directamente desde el binario oficial
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /build

# Copiar archivos de definición de dependencias
COPY pyproject.toml README.md ./

# Instalar dependencias en un entorno virtual aislado
ENV UV_PROJECT_ENVIRONMENT="/opt/venv"
RUN uv venv /opt/venv && uv pip install --no-cache -r pyproject.toml

# STAGE 2: Runtime
FROM python:3.13-slim-bookworm AS runtime

# Variables de entorno de ejecución
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    TZ="America/Mexico_City"

# Instalar librerías mínimas de runtime (libpq para postgres, tzdata, curl para healthchecks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    tzdata \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Crear usuario y grupo de sistema sin privilegios
RUN groupadd -g 1001 erpgroup && \
    useradd -u 1001 -g erpgroup -s /bin/bash -m erpuser

WORKDIR /app

# Copiar el entorno virtual compilado desde el builder
COPY --from=builder --chown=erpuser:erpgroup /opt/venv /opt/venv

# Crear directorios de almacenamiento y logs con permisos adecuados
RUN mkdir -p /app/storage/labels /app/storage/exports /app/storage/imports /app/logs /app/backups \
    && chown -R erpuser:erpgroup /app

# Copiar el código fuente y scripts
COPY --chown=erpuser:erpgroup src/ /app/src/
COPY --chown=erpuser:erpgroup scripts/ /app/scripts/
COPY --chown=erpuser:erpgroup pyproject.toml README.md /app/

# Cambiar a usuario no root
USER erpuser

# Exponer el puerto del API
EXPOSE 8000

# Health check nativo de Docker
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Comando por defecto: Uvicorn con ASGI FastAPI
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--log-config", "config/logging.conf"]

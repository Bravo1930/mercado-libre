#!/usr/bin/env bash
# ==============================================================================
# SCRIPT DE DESPLIEGUE REPRODUCIBLE - ENTORNO STAGING (PRE-PRODUCCIÓN)
# ==============================================================================
set -euo pipefail

echo "=========================================================="
echo "  INICIANDO DESPLIEGUE ENTORNO STAGING - ERP MERCADO LIBRE"
echo "=========================================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

if [ ! -f ".env.staging" ]; then
    echo "[ERROR] El archivo .env.staging no existe."
    echo "[AYUDA] Copie .env.staging.example a .env.staging y configure las credenciales."
    exit 1
fi

echo "[1/5] Construyendo imágenes Docker para Staging..."
docker compose -f docker-compose.staging.yml build --pull

echo "[2/5] Levantando infraestructura base de Staging (PostgreSQL y Redis)..."
docker compose -f docker-compose.staging.yml up -d postgres_staging redis_staging

echo "[3/5] Esperando a que PostgreSQL Staging responda con healthcheck..."
until docker compose -f docker-compose.staging.yml exec -T postgres_staging pg_isready -U erp_staging_admin -d meli_erp_staging_db; do
    echo "Esperando a postgres_staging..."
    sleep 3
done

echo "[4/5] Aplicando migraciones de base de datos con Alembic en Staging..."
docker compose -f docker-compose.staging.yml run --rm --no-deps api_staging alembic upgrade head

echo "[5/5] Levantando servicios completos de Staging..."
docker compose -f docker-compose.staging.yml up -d

echo "Esperando 10 segundos para verificar salud de los servicios..."
sleep 10

HEALTH_URL="http://localhost:8080/api/v1/health"
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_URL" || echo "000")

if [ "$HTTP_STATUS" -eq 200 ]; then
    echo "=========================================================="
    echo "  DESPLIEGUE EN STAGING COMPLETADO CON ÉXITO [HTTP 200]"
    echo "  Acceso: http://localhost:8080/app"
    echo "  Métricas: http://localhost:8080/metrics"
    echo "  Prometheus: http://localhost:9091"
    echo "=========================================================="
else
    echo "[ALERTA] El endpoint de salud devolvió estado $HTTP_STATUS"
    docker compose -f docker-compose.staging.yml logs --tail=50 api_staging
    exit 1
fi

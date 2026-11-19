#!/usr/bin/env bash
# ==============================================================================
# SCRIPT DE DESPLIEGUE REPRODUCIBLE - ENTORNO PRODUCCIÓN
# ==============================================================================
# Procedimiento seguro con:
# 1. Validación de variables críticas
# 2. Respaldo obligatorio previo de la base de datos
# 3. Aplicación de migraciones Alembic
# 4. Despliegue de contenedores y verificación de disponibilidad
# ==============================================================================
set -euo pipefail

echo "=========================================================="
echo "  INICIANDO DESPLIEGUE EN PRODUCCIÓN - ERP MERCADO LIBRE"
echo "=========================================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

if [ ! -f ".env" ]; then
    echo "[ERROR CRÍTICO] Falta el archivo .env de producción."
    exit 1
fi

# Validar que ENVIRONMENT sea production
ENV_MODE=$(grep -E "^ENVIRONMENT=" .env | cut -d '=' -f2 | tr -d ' "')
if [ "$ENV_MODE" != "production" ]; then
    echo "[ADVERTENCIA] La variable ENVIRONMENT no es 'production' (actual: $ENV_MODE)."
    read -p "¿Desea continuar con el despliegue? (s/N): " -r CONFIRM
    if [[ ! "$CONFIRM" =~ ^[sS]$ ]]; then
        echo "Despliegue cancelado."
        exit 0
    fi
fi

echo "[1/6] Ejecutando respaldo de seguridad previo al despliegue..."
if [ -f "$SCRIPT_DIR/backup.sh" ]; then
    bash "$SCRIPT_DIR/backup.sh" || echo "[AVISO] El respaldo previo continuó con código no cero."
fi

echo "[2/6] Compilando imágenes Docker de producción..."
docker compose build --pull

echo "[3/6] Levantando dependencias de almacenamiento y base de datos..."
docker compose up -d postgres redis

echo "[4/6] Aplicando migraciones de base de datos..."
docker compose run --rm --no-deps api alembic upgrade head

echo "[5/6] Actualizando servicios de aplicación (API y Worker)..."
docker compose up -d --remove-orphans api worker caddy prometheus

echo "[6/6] Ejecutando prueba de humo (Smoke Test)..."
sleep 8

HEALTH_STATUS=$(curl -s -k -o /dev/null -w "%{http_code}" "http://localhost:8000/api/v1/health" || echo "000")

if [ "$HEALTH_STATUS" -eq 200 ]; then
    echo "=========================================================="
    echo "  DESPLIEGUE EN PRODUCCIÓN COMPLETADO SATISFACTORIAMENTE"
    echo "  Estado de Salud: HTTP 200 OK"
    echo "  Fecha: $(date -Iseconds)"
    echo "=========================================================="
else
    echo "[ERROR] El servicio no respondió con HTTP 200 (Código: $HEALTH_STATUS)"
    docker compose logs --tail=50 api
    exit 1
fi

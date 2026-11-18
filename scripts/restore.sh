#!/usr/bin/env bash
# ==============================================================================
# SCRIPT DE RESTAURACIÓN DE BASE DE DATOS - POSTGRESQL 16
# Uso: ./scripts/restore.sh /backups/meli_erp_backup_YYYYMMDD_HHMMSS.sql.gz
# ==============================================================================
set -euo pipefail

if [ "$#" -ne 1 ]; then
    echo "Uso: $0 <archivo_respaldo.sql.gz>"
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "${BACKUP_FILE}" ]; then
    echo "Error: El archivo '${BACKUP_FILE}' no existe."
    exit 1
fi

echo "ADVERTENCIA: Esta operación sobrescribirá los datos existentes en '${POSTGRES_DB:-meli_erp_db}'."
read -p "¿Deseas continuar? (escribe 'si' para confirmar): " CONFIRMATION

if [ "${CONFIRMATION}" != "si" ]; then
    echo "Restauración cancelada."
    exit 0
fi

echo "[$(date -Iseconds)] Descomprimiendo y restaurando base de datos..."
PGPASSWORD="${POSTGRES_PASSWORD:-dev_postgres_password_2026}" gunzip -c "${BACKUP_FILE}" | psql \
    -h "${POSTGRES_HOST:-postgres}" \
    -p "${POSTGRES_PORT:-5432}" \
    -U "${POSTGRES_USER:-erp_admin}" \
    -d "${POSTGRES_DB:-meli_erp_db}"

echo "[$(date -Iseconds)] Restauración completada exitosamente."

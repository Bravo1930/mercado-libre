#!/usr/bin/env bash
# ==============================================================================
# SCRIPT DE COPIAS DE SEGURIDAD AUTOMATIZADAS - POSTGRESQL 16
# Genera respaldos comprimidos con gzip, fecha y hora, y retención de 14 días.
# ==============================================================================
set -euo pipefail

BACKUP_DIR="${BACKUPS_DIR:-/backups}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/meli_erp_backup_${TIMESTAMP}.sql.gz"
RETENTION_DAYS=14

mkdir -p "${BACKUP_DIR}"

echo "[$(date -Iseconds)] Iniciando respaldo de la base de datos PostgreSQL: ${POSTGRES_DB:-meli_erp_db}..."

PGPASSWORD="${POSTGRES_PASSWORD:-dev_postgres_password_2026}" pg_dump \
    -h "${POSTGRES_HOST:-postgres}" \
    -p "${POSTGRES_PORT:-5432}" \
    -U "${POSTGRES_USER:-erp_admin}" \
    -d "${POSTGRES_DB:-meli_erp_db}" \
    --format=plain \
    --no-owner \
    --no-privileges \
    | gzip -9 > "${BACKUP_FILE}"

FILE_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
echo "[$(date -Iseconds)] Respaldo completado exitosamente: ${BACKUP_FILE} (Tamaño: ${FILE_SIZE})"

# Limpieza de respaldos antiguos (> RETENTION_DAYS días)
echo "[$(date -Iseconds)] Purgando respaldos mayores a ${RETENTION_DAYS} días..."
find "${BACKUP_DIR}" -type f -name "meli_erp_backup_*.sql.gz" -mtime +"${RETENTION_DAYS}" -delete

echo "[$(date -Iseconds)] Proceso de respaldo finalizado."

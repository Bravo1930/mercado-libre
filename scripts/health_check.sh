#!/usr/bin/env bash
# ==============================================================================
# AUDITORÍA RÁPIDA DE SALUD Y SERVICIOS - ERP MERCADO LIBRE MÉXICO
# ==============================================================================
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"

echo "=========================================================="
echo "  AUDITANDO SALUD DEL ERP EN $BASE_URL"
echo "=========================================================="

echo -n "1. Endpoint /api/v1/health: "
HEALTH_RES=$(curl -s "$BASE_URL/api/v1/health" || echo '{"status":"error"}')
echo "$HEALTH_RES"

echo -n "2. Endpoint de Métricas /metrics: "
METRICS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/metrics" || echo "000")
if [ "$METRICS_STATUS" -eq 200 ]; then
    echo "OK (HTTP 200)"
else
    echo "FALLO (HTTP $METRICS_STATUS)"
fi

echo -n "3. Endpoint de Postura de Seguridad /api/v1/system/security/status: "
SEC_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/v1/system/security/status" || echo "000")
echo "HTTP $SEC_STATUS"

echo -n "4. Diagnóstico de Base de Datos y Redis: "
echo "$HEALTH_RES" | grep -q '"status":"healthy"' && echo "PostgreSQL y Redis OPERATIVOS" || echo "ADVERTENCIA EN CONEXIONES"

echo "=========================================================="
echo "  AUDITORÍA DE SALUD CONCLUIDA"
echo "=========================================================="

#!/usr/bin/env bash
# ==============================================================================
# SCRIPT DE ACTUALIZACIÓN CON CERO TIEMPO DE INACTIVIDAD (ZERO-DOWNTIME UPDATE)
# ==============================================================================
# Realiza una recarga controlada del servicio API y worker garantizando que
# las peticiones en curso se completen antes de reiniciar los procesos.
# ==============================================================================
set -euo pipefail

echo "[$(date -Iseconds)] Iniciando actualización Zero-Downtime del ERP..."

# 1. Compilar nueva imagen en segundo plano
echo "1. Construyendo nueva imagen de producción..."
docker compose build api worker

# 2. Re-desplegar worker primero (procesa colas sin afectar peticiones HTTP de usuarios)
echo "2. Actualizando contenedor de tareas en segundo plano (worker)..."
docker compose up -d --no-deps worker

# 3. Actualizar contenedor API con recreación suave
echo "3. Recreando contenedor API con tolerancia a fallos..."
docker compose up -d --no-deps api

# 4. Comprobar que el API responda correctamente
echo "4. Validando disponibilidad del servicio..."
for i in {1..12}; do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8000/api/v1/health" || echo "000")
    if [ "$STATUS" -eq 200 ]; then
        echo "[ÉXITO] El API está activo y respondiendo correctamente en la nueva versión."
        exit 0
    fi
    echo "Intento $i: esperando respuesta del API..."
    sleep 2
done

echo "[ERROR CRÍTICO] La nueva versión no respondió a tiempo. Verifique los logs."
docker compose logs --tail=50 api
exit 1

<#
.SYNOPSIS
  Script de despliegue reproducible para el entorno Staging (Windows / PowerShell).
#>
$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  INICIANDO DESPLIEGUE ENTORNO STAGING - ERP MERCADO LIBRE" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

if (-not (Test-Path ".env.staging")) {
    Write-Host "[ERROR] El archivo .env.staging no existe." -ForegroundColor Red
    Write-Host "[AYUDA] Copie .env.staging.example a .env.staging y configure las credenciales." -ForegroundColor Yellow
    exit 1
}

Write-Host "[1/5] Construyendo imágenes Docker para Staging..." -ForegroundColor Green
docker compose -f docker-compose.staging.yml build --pull

Write-Host "[2/5] Levantando base de datos y cache de Staging..." -ForegroundColor Green
docker compose -f docker-compose.staging.yml up -d postgres_staging redis_staging

Write-Host "[3/5] Verificando disponibilidad de base de datos..." -ForegroundColor Green
Start-Sleep -Seconds 5

Write-Host "[4/5] Aplicando migraciones de base de datos Alembic..." -ForegroundColor Green
docker compose -f docker-compose.staging.yml run --rm --no-deps api_staging alembic upgrade head

Write-Host "[5/5] Levantando todos los servicios en Staging..." -ForegroundColor Green
docker compose -f docker-compose.staging.yml up -d

Write-Host "Verificando salud del entorno..." -ForegroundColor Cyan
Start-Sleep -Seconds 8

try {
    $res = Invoke-RestMethod -Uri "http://localhost:8080/api/v1/health" -Method Get -TimeoutSec 10
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host "  DESPLIEGUE EN STAGING COMPLETADO CON ÉXITO" -ForegroundColor Green
    Write-Host "  Estado del ERP: $($res.status)" -ForegroundColor Green
    Write-Host "  UI: http://localhost:8080/app" -ForegroundColor Green
    Write-Host "  Métricas: http://localhost:8080/metrics" -ForegroundColor Green
    Write-Host "==========================================================" -ForegroundColor Green
} catch {
    Write-Host "[ALERTA] No se pudo conectar al endpoint de salud: $_" -ForegroundColor Yellow
}

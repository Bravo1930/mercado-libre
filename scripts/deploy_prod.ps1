<#
.SYNOPSIS
  Script de despliegue en Producción (Windows / PowerShell).
#>
$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  INICIANDO DESPLIEGUE EN PRODUCCIÓN - ERP MERCADO LIBRE" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

if (-not (Test-Path ".env")) {
    Write-Host "[ERROR] El archivo .env de producción no existe." -ForegroundColor Red
    exit 1
}

Write-Host "[1/5] Compilando imágenes Docker de producción..." -ForegroundColor Green
docker compose build --pull

Write-Host "[2/5] Levantando dependencias de infraestructura..." -ForegroundColor Green
docker compose up -d postgres redis

Start-Sleep -Seconds 4

Write-Host "[3/5] Aplicando migraciones de base de datos..." -ForegroundColor Green
docker compose run --rm --no-deps api alembic upgrade head

Write-Host "[4/5] Desplegando servicios de aplicación..." -ForegroundColor Green
docker compose up -d --remove-orphans api worker caddy prometheus

Write-Host "[5/5] Verificando salud en producción..." -ForegroundColor Green
Start-Sleep -Seconds 8

try {
    $res = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health" -Method Get -TimeoutSec 10
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host "  DESPLIEGUE EN PRODUCCIÓN EXITOSO" -ForegroundColor Green
    Write-Host "  Estado del ERP: $($res.status)" -ForegroundColor Green
    Write-Host "==========================================================" -ForegroundColor Green
} catch {
    Write-Host "[ALERTA] No se pudo conectar al endpoint de salud: $_" -ForegroundColor Yellow
}

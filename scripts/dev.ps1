# ==============================================================================
# SCRIPT DE INICIO RÁPIDO PARA DESARROLLO LOCAL EN WINDOWS (POWERSHELL)
# ==============================================================================
param (
    [switch]$Docker,
    [switch]$Test,
    [switch]$Worker
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  ERP Mercado Libre México - Entorno Local de Desarrollo  " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# Comprobar uv
$uvPath = "C:\Users\Asus\.local\bin\uv.exe"
if (-not (Test-Path $uvPath)) {
    $uvCmd = Get-Command "uv" -ErrorAction SilentlyContinue
    if ($uvCmd) { $uvPath = $uvCmd.Source }
}

if ($Docker) {
    Write-Host "[Docker] Iniciando servicios con docker-compose.dev.yml..." -ForegroundColor Yellow
    docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
    exit 0
}

if ($Test) {
    Write-Host "[Tests] Ejecutando suite de pruebas unitarias y de integración..." -ForegroundColor Green
    & $uvPath run pytest -v --cov=src
    exit 0
}

if ($Worker) {
    Write-Host "[Worker] Iniciando worker de segundo plano..." -ForegroundColor Magenta
    & $uvPath run python -m src.workers.tasks
    exit 0
}

Write-Host "[API] Levantando servidor local FastAPI con Uvicorn (Hot-Reload)..." -ForegroundColor Green
Write-Host "URL: http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "Documentación Swagger: http://127.0.0.1:8000/docs" -ForegroundColor Cyan
Write-Host "Health Check: http://127.0.0.1:8000/api/v1/health" -ForegroundColor Cyan

& $uvPath run uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload

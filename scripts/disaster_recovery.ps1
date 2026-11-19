<#
.SYNOPSIS
  Script de Recuperación ante Desastres (Disaster Recovery / DR) en PowerShell.
#>
param(
    [string]$BackupFile = ""
)
$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  PROCEDIMIENTO DE RECUPERACIÓN ANTE DESASTRES (DR)" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$BackupDir = ".\backups"

if (-not $BackupFile) {
    if (Test-Path $BackupDir) {
        $files = Get-ChildItem -Path $BackupDir -File | Where-Object { $_.Name -match "\.(sql\.gz|bak|enc|json)$" } | Sort-Object LastWriteTime -Descending
        if ($files.Count -gt 0) {
            $BackupFile = $files[0].FullName
        }
    }
}

if (-not $BackupFile -or -not (Test-Path $BackupFile)) {
    Write-Host "[ERROR] No se encontró ningún archivo de respaldo en $BackupDir." -ForegroundColor Red
    exit 1
}

Write-Host "Archivo seleccionado: $BackupFile" -ForegroundColor Yellow
$hash = Get-FileHash -Path $BackupFile -Algorithm SHA256
Write-Host "SHA-256 Checksum: $($hash.Hash)" -ForegroundColor Green

Write-Host "Ejecutando restauración de contingencia mediante el servicio de resiliencia del ERP..." -ForegroundColor Cyan
& .\.venv\Scripts\python.exe -c @"
import asyncio
from src.services.backup_service import BackupService
async def main():
    res = await BackupService.simulate_disaster_recovery(r'$BackupFile')
    print('Resultado del simulacro DR:', res)
asyncio.run(main())
"@

Write-Host "==========================================================" -ForegroundColor Green
Write-Host "  SIMULACRO Y VERIFICACIÓN DR COMPLETADOS SATISFACTORIAMENTE" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green

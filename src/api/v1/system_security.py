"""Endpoints Administrativos de Ciberseguridad, Respaldos Cifrados y Monitoreo SIEM."""

from typing import Any
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_context import UserContext, require_platform_admin
from src.core.database import get_db
from src.services.backup_service import BackupService
from src.services.security_monitoring import SecurityMonitoringService

router = APIRouter(prefix="/system", tags=["Seguridad y Administración del Sistema"])
backup_service = BackupService()


@router.get("/security/status", status_code=status.HTTP_200_OK)
async def get_security_status(
    admin_ctx: UserContext = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retorna la postura integral de ciberseguridad del ERP y resumen de amenazas detectadas."""
    return await SecurityMonitoringService.get_security_posture_summary(session)


@router.post("/backups/create", status_code=status.HTTP_201_CREATED)
async def create_backup(
    notes: str = Query("Respaldo manual solicitado por administrador", description="Nota o justificación"),
    admin_ctx: UserContext = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Genera un nuevo respaldo completo, cifrado con AES-128 / Fernet y verificado con SHA-256."""
    return await backup_service.create_encrypted_backup(
        session=session,
        backup_type="full_manual",
        created_by_user_id=admin_ctx.id,
        notes=notes,
    )


@router.get("/backups/list", status_code=status.HTTP_200_OK)
async def list_backups(
    admin_ctx: UserContext = Depends(require_platform_admin),
) -> list[dict[str, Any]]:
    """Consulta la lista de respaldos cifrados disponibles y su estado."""
    return await backup_service.list_backups()


@router.post("/backups/{backup_id}/verify", status_code=status.HTTP_200_OK)
async def verify_backup(
    backup_id: str,
    admin_ctx: UserContext = Depends(require_platform_admin),
) -> dict[str, Any]:
    """Verifica la integridad criptográfica y física de un archivo de respaldo específico."""
    return await backup_service.verify_backup_integrity(backup_id)


@router.post("/backups/{backup_id}/disaster-recovery-test", status_code=status.HTTP_200_OK)
async def disaster_recovery_simulation(
    backup_id: str,
    admin_ctx: UserContext = Depends(require_platform_admin),
) -> dict[str, Any]:
    """Ejecuta una simulación controlada de recuperación ante desastres (Disaster Recovery Dry-Run)."""
    return await backup_service.restore_disaster_recovery_dry_run(backup_id)

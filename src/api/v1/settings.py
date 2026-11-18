"""API REST para Parámetros y Configuraciones de Empresa."""

import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_context import CompanyContext, require_company_permission
from src.core.database import get_db
from src.core.pagination import Page, PaginationParams
from src.core.permissions import ActionEnum, ModuleEnum
from src.models.setting import CompanySetting
from src.repositories.base import BaseRepository
from src.schemas.supplier import CompanySettingCreate, CompanySettingResponse

router = APIRouter(prefix="/settings", tags=["Configuraciones"])
setting_repo = BaseRepository[CompanySetting](CompanySetting)


@router.post("", response_model=CompanySettingResponse, status_code=status.HTTP_200_OK)
async def set_company_setting(
    payload: CompanySettingCreate,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SETTINGS, ActionEnum.MANAGE)),
    session: AsyncSession = Depends(get_db),
) -> CompanySetting:
    """Crea o actualiza una configuración clave-valor para la empresa activa (Upsert)."""
    stmt = select(CompanySetting).where(
        CompanySetting.company_id == ctx.company_id,
        CompanySetting.key == payload.key,
    )
    setting = (await session.execute(stmt)).scalar_one_or_none()

    if setting:
        setting.value = payload.value
        setting.description = payload.description or setting.description
    else:
        setting = CompanySetting(
            company_id=ctx.company_id,
            key=payload.key,
            value=payload.value,
            description=payload.description,
        )
        session.add(setting)

    await session.flush()
    return setting


@router.get("", response_model=Page[CompanySettingResponse])
async def list_company_settings(
    params: PaginationParams = Depends(),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SETTINGS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> Page[CompanySetting]:
    """Lista las configuraciones activas de la empresa del solicitante."""
    return await setting_repo.get_paginated(session, params, CompanySetting.company_id == ctx.company_id)

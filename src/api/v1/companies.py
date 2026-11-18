"""API REST para Gestión de Empresas y Razones Sociales (Multi-RFC)."""

import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.audit import record_audit_event
from src.core.database import get_db
from src.core.exceptions import EntityAlreadyExistsException
from src.core.pagination import Page, PaginationParams
from src.models.tenant import Company
from src.repositories.base import BaseRepository
from src.schemas.tenant import CompanyCreate, CompanyResponse, CompanyUpdate

router = APIRouter(prefix="/companies", tags=["Empresas"])
company_repo = BaseRepository[Company](Company)


@router.post("", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
async def create_company(
    payload: CompanyCreate,
    session: AsyncSession = Depends(get_db),
) -> Company:
    """Crea una nueva empresa con validación estricta de RFC oficial de México."""
    # Verificar unicidad de RFC dentro del tenant
    stmt = select(Company).where(Company.tenant_id == payload.tenant_id, Company.rfc == payload.rfc)
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing:
        raise EntityAlreadyExistsException("Empresa", "RFC", payload.rfc)

    company = await company_repo.create(session, payload.model_dump())
    await record_audit_event(
        session=session,
        company_id=company.id,
        action="CREATE",
        entity_name="Company",
        entity_id=str(company.id),
        changes={"legal_name": company.legal_name, "rfc": company.rfc},
    )
    return company


@router.get("", response_model=Page[CompanyResponse])
async def list_companies(
    tenant_id: uuid.UUID | None = Query(None, description="Filtrar por Tenant ID"),
    is_active: bool | None = Query(None, description="Filtrar por estatus"),
    params: PaginationParams = Depends(),
    session: AsyncSession = Depends(get_db),
) -> Page[Company]:
    """Lista empresas con paginación y filtros opcionales."""
    filters = []
    if tenant_id:
        filters.append(Company.tenant_id == tenant_id)
    if is_active is not None:
        filters.append(Company.is_active == is_active)

    return await company_repo.get_paginated(session, params, *filters)


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> Company:
    """Obtiene los datos detallados de una empresa por su UUID."""
    return await company_repo.get_or_fail(session, company_id)


@router.put("/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: uuid.UUID,
    payload: CompanyUpdate,
    session: AsyncSession = Depends(get_db),
) -> Company:
    """Actualiza la información fiscal o de contacto de una empresa."""
    company = await company_repo.get_or_fail(session, company_id)
    update_data = payload.model_dump(exclude_unset=True)
    updated = await company_repo.update(session, company, update_data)

    await record_audit_event(
        session=session,
        company_id=company.id,
        action="UPDATE",
        entity_name="Company",
        entity_id=str(company.id),
        changes=update_data,
    )
    return updated

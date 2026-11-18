"""API REST para Gestión de Empresas, Razones Sociales y Asignación de Usuarios (Multi-Empresa)."""

import uuid
from typing import Any
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.audit import record_audit_event
from src.core.auth_context import (
    CompanyContext,
    UserContext,
    get_current_user,
    require_company_permission,
)
from src.core.database import get_db
from src.core.exceptions import (
    AppException,
    EntityAlreadyExistsException,
    EntityNotFoundException,
    PermissionDeniedException,
)
from src.core.pagination import Page, PaginationParams
from src.core.permissions import ActionEnum, ModuleEnum, RoleEnum, can_assign_role
from src.models.tenant import Company
from src.models.user import CompanyUser, User
from src.repositories.base import BaseRepository
from src.schemas.tenant import CompanyCreate, CompanyResponse, CompanyUpdate
from src.schemas.user import (
    CompanyUserAssignRequest,
    CompanyUserResponse,
    CompanyUserUpdateRequest,
)

router = APIRouter(prefix="/companies", tags=["Empresas & Multi-Empresa"])
company_repo = BaseRepository[Company](Company)


@router.post("", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
async def create_company(
    payload: CompanyCreate,
    user_ctx: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Company:
    """
    Crea una nueva empresa con validación estricta de RFC oficial de México.
    Previene escalamiento de privilegios y vincula automáticamente al creador como Administrador.
    """
    # 1. Validación de privilegios: Operadores y usuarios de consulta no pueden crear empresas
    allowed_creators = {
        RoleEnum.PLATFORM_OWNER.value,
        RoleEnum.SAAS_ADMIN.value,
        RoleEnum.COMPANY_ADMIN.value,
    }
    if user_ctx.role not in allowed_creators:
        raise PermissionDeniedException(
            f"El rol '{user_ctx.role}' no cuenta con privilegios para dar de alta nuevas empresas."
        )

    # Si el usuario es de nivel tenant, garantizar que no cree empresas para otro tenant ajeno
    if user_ctx.user.tenant_id and payload.tenant_id != user_ctx.user.tenant_id and user_ctx.role not in {
        RoleEnum.PLATFORM_OWNER.value, RoleEnum.SAAS_ADMIN.value
    }:
        raise PermissionDeniedException("No está autorizado a crear empresas en una organización ajena.")

    # 2. Verificar unicidad de RFC dentro del tenant
    stmt = select(Company).where(Company.tenant_id == payload.tenant_id, Company.rfc == payload.rfc)
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing:
        raise EntityAlreadyExistsException("Empresa", "RFC", payload.rfc)

    company = await company_repo.create(session, payload.model_dump())

    # 3. Asignar automáticamente al creador como Administrador de la nueva empresa
    cu = CompanyUser(
        user_id=user_ctx.id,
        company_id=company.id,
        role=RoleEnum.COMPANY_ADMIN.value,
        is_active=True,
    )
    session.add(cu)
    await session.flush()

    await record_audit_event(
        session=session,
        action="CREATE",
        entity_name="Company",
        entity_id=str(company.id),
        company_id=company.id,
        user_id=user_ctx.id,
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
    """Lista empresas registradas con paginación y filtros."""
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
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMPANIES, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> Company:
    """Actualiza la información fiscal o de contacto de una empresa."""
    company = await company_repo.get_or_fail(session, company_id)
    update_data = payload.model_dump(exclude_unset=True)
    updated = await company_repo.update(session, company, update_data)

    await record_audit_event(
        session=session,
        action="UPDATE",
        entity_name="Company",
        entity_id=str(company.id),
        company_id=company.id,
        user_id=ctx.user.id,
        changes=update_data,
    )
    return updated


# =========================================================================
# GESTIÓN Y ASIGNACIÓN DE USUARIOS A LA EMPRESA (RBAC & RESTRICCIONES)
# =========================================================================

@router.post(
    "/{company_id}/users",
    response_model=CompanyUserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assign_user_to_company(
    company_id: uuid.UUID,
    payload: CompanyUserAssignRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMPANIES, ActionEnum.MANAGE)),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Asigna un usuario a la empresa con un rol específico, permisos granulares opcionales
    y restricciones modulares. Valida contra escalamiento de privilegios.
    """
    # 1. Validar escalamiento de privilegios
    if not can_assign_role(ctx.effective_role, payload.role.value):
        raise PermissionDeniedException(
            f"Escalamiento denegado: El rol '{ctx.effective_role}' no puede otorgar el rol '{payload.role.value}'."
        )

    # 2. Verificar existencia del usuario
    stmt_user = select(User).where(User.id == payload.user_id)
    user = (await session.execute(stmt_user)).scalar_one_or_none()
    if not user:
        raise EntityNotFoundException("Usuario", "id", str(payload.user_id))

    # 3. Buscar si ya existe la membresía
    stmt_existing = select(CompanyUser).where(
        CompanyUser.company_id == company_id,
        CompanyUser.user_id == payload.user_id,
    )
    existing_cu = (await session.execute(stmt_existing)).scalar_one_or_none()

    if existing_cu:
        existing_cu.role = payload.role.value
        existing_cu.permissions = payload.permissions
        existing_cu.restricted_modules = payload.restricted_modules
        existing_cu.is_active = True
        cu = existing_cu
    else:
        cu = CompanyUser(
            user_id=payload.user_id,
            company_id=company_id,
            role=payload.role.value,
            is_active=True,
        )
        cu.permissions = payload.permissions
        cu.restricted_modules = payload.restricted_modules
        session.add(cu)

    await session.flush()

    await record_audit_event(
        session=session,
        action="ASSIGN_USER_TO_COMPANY",
        entity_name="CompanyUser",
        entity_id=str(cu.id),
        company_id=company_id,
        user_id=ctx.user.id,
        changes={
            "assigned_user_email": user.email,
            "role": payload.role.value,
            "restricted_modules": payload.restricted_modules,
        },
    )

    return {
        "id": cu.id,
        "user_id": cu.user_id,
        "company_id": cu.company_id,
        "email": user.email,
        "full_name": user.full_name,
        "role": cu.role,
        "permissions": cu.permissions,
        "restricted_modules": cu.restricted_modules,
        "is_active": cu.is_active,
        "created_at": cu.created_at,
    }


@router.get(
    "/{company_id}/users",
    response_model=list[CompanyUserResponse],
)
async def list_company_users(
    company_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMPANIES, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Consulta los usuarios asignados a la empresa con sus respectivos roles y restricciones."""
    stmt = (
        select(CompanyUser)
        .where(CompanyUser.company_id == company_id)
        .options(selectinload(CompanyUser.user))
    )
    members = (await session.execute(stmt)).scalars().all()

    results = []
    for m in members:
        results.append({
            "id": m.id,
            "user_id": m.user_id,
            "company_id": m.company_id,
            "email": m.user.email if m.user else None,
            "full_name": m.user.full_name if m.user else None,
            "role": m.role,
            "permissions": m.permissions,
            "restricted_modules": m.restricted_modules,
            "is_active": m.is_active,
            "created_at": m.created_at,
        })
    return results


@router.put(
    "/{company_id}/users/{target_user_id}",
    response_model=CompanyUserResponse,
)
async def update_company_user(
    company_id: uuid.UUID,
    target_user_id: uuid.UUID,
    payload: CompanyUserUpdateRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMPANIES, ActionEnum.MANAGE)),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Actualiza el rol, permisos o módulos restringidos de un usuario asignado a la empresa."""
    stmt = (
        select(CompanyUser)
        .where(CompanyUser.company_id == company_id, CompanyUser.user_id == target_user_id)
        .options(selectinload(CompanyUser.user))
    )
    cu = (await session.execute(stmt)).scalar_one_or_none()

    if not cu:
        raise EntityNotFoundException("Membresía de Usuario en Empresa", "user_id", str(target_user_id))

    if payload.role is not None:
        if not can_assign_role(ctx.effective_role, payload.role.value):
            raise PermissionDeniedException(
                f"Escalamiento denegado: El rol '{ctx.effective_role}' no puede otorgar '{payload.role.value}'."
            )
        cu.role = payload.role.value

    if payload.permissions is not None:
        cu.permissions = payload.permissions

    if payload.restricted_modules is not None:
        cu.restricted_modules = payload.restricted_modules

    if payload.is_active is not None:
        cu.is_active = payload.is_active

    await session.flush()

    await record_audit_event(
        session=session,
        action="UPDATE_COMPANY_USER_PERMISSIONS",
        entity_name="CompanyUser",
        entity_id=str(cu.id),
        company_id=company_id,
        user_id=ctx.user.id,
        changes=payload.model_dump(exclude_unset=True),
    )

    return {
        "id": cu.id,
        "user_id": cu.user_id,
        "company_id": cu.company_id,
        "email": cu.user.email if cu.user else None,
        "full_name": cu.user.full_name if cu.user else None,
        "role": cu.role,
        "permissions": cu.permissions,
        "restricted_modules": cu.restricted_modules,
        "is_active": cu.is_active,
        "created_at": cu.created_at,
    }


@router.delete(
    "/{company_id}/users/{target_user_id}",
    status_code=status.HTTP_200_OK,
)
async def remove_user_from_company(
    company_id: uuid.UUID,
    target_user_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMPANIES, ActionEnum.MANAGE)),
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Revoca el acceso de un usuario a la empresa."""
    # Prevenir auto-eliminación si es el único administrador
    if ctx.user.id == target_user_id and ctx.effective_role == RoleEnum.COMPANY_ADMIN.value:
        # Verificar si hay otros administradores activos
        stmt_admins = select(CompanyUser).where(
            CompanyUser.company_id == company_id,
            CompanyUser.role == RoleEnum.COMPANY_ADMIN.value,
            CompanyUser.is_active == True,
            CompanyUser.user_id != target_user_id,
        )
        other_admins = (await session.execute(stmt_admins)).scalars().all()
        if not other_admins:
            raise AppException(
                "No puedes revocar tu propio acceso siendo el único Administrador de la empresa.",
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="SOLE_ADMIN_REMOVAL_PREVENTED",
            )

    stmt = select(CompanyUser).where(
        CompanyUser.company_id == company_id,
        CompanyUser.user_id == target_user_id,
    )
    cu = (await session.execute(stmt)).scalar_one_or_none()

    if not cu:
        raise EntityNotFoundException("Membresía de Usuario en Empresa", "user_id", str(target_user_id))

    await session.delete(cu)
    await session.flush()

    await record_audit_event(
        session=session,
        action="REMOVE_USER_FROM_COMPANY",
        entity_name="CompanyUser",
        entity_id=str(target_user_id),
        company_id=company_id,
        user_id=ctx.user.id,
        changes={"removed_user_id": str(target_user_id)},
    )

    return {"status": "success", "message": "Acceso a la empresa revocado exitosamente."}

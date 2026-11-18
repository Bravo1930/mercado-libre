"""Router del Dashboard Ejecutivo del ERP Mercado Libre México."""

from datetime import date, datetime
from typing import Any, Literal
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_context import CompanyContext, require_company_permission
from src.core.database import get_db
from src.core.permissions import ActionEnum, ModuleEnum
from src.schemas.dashboard import (
    CompareToType,
    DashboardFilterParams,
    DashboardPresetType,
    ExecutiveDashboardResponse,
)
from src.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["Dashboard Ejecutivo"])
dashboard_service = DashboardService()


@router.get(
    "/executive",
    response_model=ExecutiveDashboardResponse,
    summary="Consultar Dashboard Ejecutivo con 15 KPIs, 9 Gráficas y Comparación de Periodos",
)
async def get_executive_dashboard(
    preset: DashboardPresetType = Query("30d", description="Rango de fecha preconfigurado"),
    date_from: datetime | date | None = Query(None, description="Fecha inicial periodo personalizado"),
    date_to: datetime | date | None = Query(None, description="Fecha final periodo personalizado"),
    meli_account_id: uuid.UUID | None = Query(None, description="Filtrar por cuenta Mercado Libre"),
    product_id: uuid.UUID | None = Query(None, description="Filtrar por producto maestro"),
    sku: str | None = Query(None, description="Filtrar por SKU o código parcial"),
    category: str | None = Query(None, description="Filtrar por categoría"),
    status: str | None = Query(None, description="Filtrar por estado del pedido (paid, confirmed, etc.)"),
    compare: bool = Query(True, description="Calcular variación respecto al periodo previo"),
    compare_to: CompareToType = Query("previous_period", description="Base comparativa: previous_period o previous_year"),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMPANIES, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> ExecutiveDashboardResponse:
    """
    Retorna la analítica ejecutiva del negocio para Mercado Libre México:
    - 15 Indicadores y KPIs en tiempo real con datos de BD.
    - Cifras confirmadas vs estimadas.
    - Comparativa porcentual vs periodo anterior o año anterior.
    - 9 Gráficas analíticas completas listas para Chart.js.
    """
    params = DashboardFilterParams(
        preset=preset,
        date_from=date_from,
        date_to=date_to,
        meli_account_id=meli_account_id,
        product_id=product_id,
        sku=sku,
        category=category,
        status=status,
        compare=compare,
        compare_to=compare_to,
    )

    company_name = ctx.company.legal_name if ctx.company else "Empresa ERP"
    data = await dashboard_service.get_executive_dashboard(
        session=session,
        company_id=ctx.company_id,
        company_name=company_name,
        params=params,
    )
    return data


@router.get(
    "/filters",
    summary="Obtener opciones y catálogos disponibles para los filtros del Dashboard",
)
async def get_dashboard_filters(
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMPANIES, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retorna las cuentas conectadas, categorías en catálogo y almacenes de la empresa."""
    return await dashboard_service.get_filter_options(session=session, company_id=ctx.company_id)

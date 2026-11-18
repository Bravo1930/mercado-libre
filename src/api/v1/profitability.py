"""API REST para el Motor Financiero de Rentabilidad, Historial de Costos, Alertas y Fiscalidad SAT."""

from datetime import datetime
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_context import CompanyContext, require_company_permission
from src.core.database import get_db
from src.core.permissions import ActionEnum, ModuleEnum
from src.models.profitability import (
    CostHistory,
    FiscalIntegrationConfig,
    FiscalInvoice,
    ProfitabilityAlert,
    ProfitabilityConfig,
)
from src.schemas.profitability import (
    CostHistoryCreateRequest,
    CostHistoryResponse,
    FiscalIntegrationConfigCreateRequest,
    FiscalIntegrationConfigResponse,
    FiscalInvoiceGenerateRequest,
    FiscalInvoiceResponse,
    ProfitabilityAlertResolveRequest,
    ProfitabilityAlertResponse,
    ProfitabilityConfigResponse,
    ProfitabilityConfigUpdateRequest,
    ProfitabilityReportResponse,
    TargetMarginSimulationRequest,
    TargetMarginSimulationResponse,
)
from src.services.profitability_service import ProfitabilityService

router = APIRouter(prefix="/profitability", tags=["Motor Financiero de Rentabilidad"])
profitability_service = ProfitabilityService()


# ---------------------------------------------------------------------------
# 1. FÓRMULAS Y CONFIGURACIÓN DE RENTABILIDAD
# ---------------------------------------------------------------------------

@router.get("/config", response_model=ProfitabilityConfigResponse)
async def get_profitability_config(
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.FINANCE, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> ProfitabilityConfig:
    """Obtiene las fórmulas y parámetros vigentes de rentabilidad configurados para la empresa."""
    return await profitability_service.get_or_create_config(session, ctx.company_id)


@router.put("/config", response_model=ProfitabilityConfigResponse)
async def update_profitability_config(
    payload: ProfitabilityConfigUpdateRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.FINANCE, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> ProfitabilityConfig:
    """Actualiza las fórmulas matemáticas, costos operativos base y umbrales de alerta."""
    config = await profitability_service.update_config(session, ctx.company_id, payload)
    await session.commit()
    return config


# ---------------------------------------------------------------------------
# 2. REPORTES DE RENTABILIDAD MULTIDIMENSIONAL (8 DIMENSIONES)
# ---------------------------------------------------------------------------

@router.get("/reports", response_model=ProfitabilityReportResponse)
async def get_multidimensional_profitability_report(
    dimension: Literal["product", "sku", "item", "order", "account", "daily", "weekly", "monthly"] = Query(
        "product", description="Eje dimensional de análisis contable"
    ),
    date_from: datetime | None = Query(None, description="Fecha inicial del periodo"),
    date_to: datetime | None = Query(None, description="Fecha final del periodo"),
    meli_account_id: uuid.UUID | None = Query(None, description="Filtrar por cuenta MeLi específica"),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.FINANCE, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> ProfitabilityReportResponse:
    """
    Genera el desglose contable y financiero completo para la dimensión seleccionada:
    - Precio de venta unitario promedio
    - Ingreso bruto e ingresos efectivos (después de descuentos)
    - Comisiones y cargos fijos MeLi (< $299 MXN)
    - Fletes Mercado Envíos a cargo del vendedor
    - Costo del producto (COGS histórico vigente)
    - Gastos operativos (empaque, manipulación y externos)
    - Impuestos aplicables (Retenciones SAT México: IVA 8% e ISR 1%)
    - Reembolsos por cancelaciones y devoluciones
    - Ganancia bruta, ganancia neta y margen neto porcentual
    - Diferenciación explícita de costos reales, estimados y pendientes.
    """
    return await profitability_service.generate_profitability_report(
        session=session,
        company_id=ctx.company_id,
        dimension=dimension,
        date_from=date_from,
        date_to=date_to,
        meli_account_id=meli_account_id,
    )


# ---------------------------------------------------------------------------
# 3. ALERTAS DE PRODUCTOS EN PÉRDIDA Y MARGEN CRÍTICO
# ---------------------------------------------------------------------------

@router.get("/alerts", response_model=list[ProfitabilityAlertResponse])
async def list_loss_alerts(
    status_filter: str | None = Query("active", description="Filtrar por estatus (active, acknowledged, resolved)"),
    severity_filter: str | None = Query(None, description="Filtrar por severidad (critical, high, medium)"),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.FINANCE, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> list[ProfitabilityAlert]:
    """Lista las alertas financieras de productos, SKUs o publicaciones con pérdidas o margen crítico."""
    return await profitability_service.list_alerts(session, ctx.company_id, status_filter, severity_filter)


@router.post("/alerts/sync", response_model=list[ProfitabilityAlertResponse])
async def sync_loss_alerts(
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.FINANCE, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> list[ProfitabilityAlert]:
    """
    Ejecuta el motor de diagnóstico sobre el catálogo y ventas recientes.
    Detecta automáticamente publicaciones en pérdida, analiza la causa raíz y calcula precios sugeridos.
    """
    alerts = await profitability_service.detect_and_sync_loss_alerts(session, ctx.company_id)
    await session.commit()
    return alerts


@router.post("/alerts/{alert_id}/resolve", response_model=ProfitabilityAlertResponse)
async def resolve_loss_alert(
    alert_id: uuid.UUID,
    payload: ProfitabilityAlertResolveRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.FINANCE, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> ProfitabilityAlert:
    """Registra la acción correctiva tomada para solucionar una alerta de pérdida."""
    alert = await profitability_service.resolve_alert(session, ctx.company_id, alert_id, payload)
    await session.commit()
    return alert


# ---------------------------------------------------------------------------
# 4. SIMULADOR INVERSO DE PRECIOS PARA MARGEN OBJETIVO
# ---------------------------------------------------------------------------

@router.post("/simulator/target-margin", response_model=TargetMarginSimulationResponse)
async def simulate_target_margin(
    payload: TargetMarginSimulationRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.FINANCE, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> TargetMarginSimulationResponse:
    """
    Calcula mediante álgebra matemática inversa el precio de venta exacto requerido
    para alcanzar un margen neto objetivo deseado.
    Considera comisiones de categoría, flete vendedor, gastos de empaque,
    retenciones oficiales SAT (9% con RFC vs 36% sin RFC) y el cargo fijo de $25 MXN si PVP < $299 MXN.
    """
    config = await profitability_service.get_or_create_config(session, ctx.company_id)
    return profitability_service.simulate_price_for_target_margin(payload, config)


# ---------------------------------------------------------------------------
# 5. HISTORIAL INMUTABLE DE COSTOS (COGS)
# ---------------------------------------------------------------------------

@router.post("/costs/history", response_model=CostHistoryResponse, status_code=status.HTTP_201_CREATED)
async def record_cost_history(
    payload: CostHistoryCreateRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.FINANCE, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> CostHistory:
    """
    Registra un ajuste de costo de adquisición para una variante o producto.
    Conserva la trazabilidad histórica obligatoria con motivo y fecha de vigencia.
    """
    record = await profitability_service.record_cost_change(session, ctx.company_id, payload, ctx.user_id)
    await session.commit()
    return record


@router.get("/costs/history", response_model=list[CostHistoryResponse])
async def get_cost_history(
    sku: str | None = Query(None, description="Filtrar por SKU específico"),
    product_id: uuid.UUID | None = Query(None, description="Filtrar por producto"),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.FINANCE, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> list[CostHistory]:
    """Consulta el historial inmutable de costos ordenado cronológicamente descendente."""
    return await profitability_service.list_cost_history(session, ctx.company_id, sku, product_id)


# ---------------------------------------------------------------------------
# 6. INTEGRACIÓN FISCAL MEXICANA (PAC / CFDI 4.0 / SAT)
# ---------------------------------------------------------------------------

@router.get("/fiscal/config", response_model=FiscalIntegrationConfigResponse)
async def get_fiscal_integration_config(
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.FINANCE, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> FiscalIntegrationConfig:
    """Consulta la configuración del Proveedor Autorizado de Certificación (PAC) del SAT."""
    return await profitability_service.get_or_create_fiscal_config(session, ctx.company_id)


@router.post("/fiscal/config", response_model=FiscalIntegrationConfigResponse)
async def update_fiscal_integration_config(
    payload: FiscalIntegrationConfigCreateRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.FINANCE, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> FiscalIntegrationConfig:
    """Configura o actualiza las credenciales y parámetros de timbrado del PAC."""
    config = await profitability_service.get_or_create_fiscal_config(session, ctx.company_id, payload)
    await session.commit()
    return config


@router.post("/fiscal/invoices", response_model=FiscalInvoiceResponse, status_code=status.HTTP_201_CREATED)
async def generate_fiscal_invoice(
    payload: FiscalInvoiceGenerateRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.FINANCE, ActionEnum.CREATE)),
    session: AsyncSession = Depends(get_db),
) -> FiscalInvoice:
    """
    Genera y timbra un CFDI 4.0 con el PAC autorizado a partir de una orden de venta.
    Desglosa Subtotal, IVA 16% trasladado, Retención IVA 8% y Retención ISR 1%.
    """
    invoice = await profitability_service.generate_fiscal_invoice_for_order(session, ctx.company_id, payload)
    await session.commit()
    return invoice


@router.get("/fiscal/invoices", response_model=list[FiscalInvoiceResponse])
async def list_fiscal_invoices(
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.FINANCE, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> list[FiscalInvoice]:
    """Lista las facturas electrónicas y constancias de retención timbradas."""
    return await profitability_service.list_fiscal_invoices(session, ctx.company_id)

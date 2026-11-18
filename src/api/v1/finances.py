"""API REST para el Módulo Financiero, Transacciones, Liquidaciones, Gastos y Conciliación."""

from datetime import datetime, timezone
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.auth_context import CompanyContext, require_company_permission
from src.core.database import get_db
from src.core.exceptions import EntityNotFoundException
from src.core.pagination import Page, PaginationParams, paginate_query
from src.core.permissions import ActionEnum, ModuleEnum
from src.models.finance import ExternalExpense, FinancialDiscrepancy, FinancialTransaction, Settlement
from src.schemas.finance import (
    AccountFinancialReportResponse,
    DiscrepancyResolveRequest,
    ExternalExpenseCreateRequest,
    ExternalExpenseResponse,
    FinancialDiscrepancyResponse,
    FinancialKPIsResponse,
    FinancialTransactionResponse,
    OrderFinancialReportResponse,
    PeriodFinancialReportResponse,
    ProductFinancialReportResponse,
    ReconciliationRunResponse,
    SettlementCreateRequest,
    SettlementResponse,
)
from src.services.finance_service import FinanceService

router = APIRouter(prefix="/finances", tags=["Finanzas & Conciliación"])
finance_service = FinanceService()


# ---------------------------------------------------------------------------
# KPIS Y LAS 7 MÉTRICAS OBLIGATORIAS
# ---------------------------------------------------------------------------

@router.get("/kpis", response_model=FinancialKPIsResponse)
async def get_financial_kpis_endpoint(
    meli_account_id: uuid.UUID | None = Query(None, description="Filtrar por cuenta MeLi específica"),
    date_from: datetime | None = Query(None, description="Fecha de inicio"),
    date_to: datetime | None = Query(None, description="Fecha de fin"),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.FINANCE, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> FinancialKPIsResponse:
    """
    Retorna las 7 métricas financieras diferenciadas de Mercado Libre:
    1. Importe bruto (Facturación total sin descuentos)
    2. Importe neto estimado (Bruto - comisiones - fletes - retenciones SAT - empaques)
    3. Dinero acreditado (Pagos aprobados en MP pendientes de liberación)
    4. Dinero disponible (Saldo líquido liberado listo para retiro)
    5. Dinero retirado (Fondos transferidos a banco vía SPEI)
    6. Reembolsos (Montos devueltos por cancelaciones/devoluciones)
    7. Cargos definitivos (Comisiones MeLi + fletes vendedor + retenciones SAT cobradas)
    """
    return await finance_service.get_financial_kpis(
        session=session,
        company_id=ctx.company_id,
        meli_account_id=meli_account_id,
        date_from=date_from,
        date_to=date_to,
    )


# ---------------------------------------------------------------------------
# REPORTES FINANCIEROS (Rutas estáticas antes de rutas dinámicas /{id})
# ---------------------------------------------------------------------------

@router.get("/reports/accounts", response_model=AccountFinancialReportResponse)
async def get_accounts_report(
    date_from: datetime | None = Query(None, description="Fecha de inicio"),
    date_to: datetime | None = Query(None, description="Fecha de fin"),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.FINANCE, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> AccountFinancialReportResponse:
    """Reporte comparativo financiero auditando cada cuenta de Mercado Libre conectada."""
    return await finance_service.generate_account_financial_report(
        session=session,
        company_id=ctx.company_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/reports/products", response_model=ProductFinancialReportResponse)
async def get_products_report(
    date_from: datetime | None = Query(None, description="Fecha de inicio"),
    date_to: datetime | None = Query(None, description="Fecha de fin"),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.FINANCE, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> ProductFinancialReportResponse:
    """Reporte de rentabilidad real por producto y SKU (ventas, COGS, comisiones, fletes, utilidad)."""
    return await finance_service.generate_product_financial_report(
        session=session,
        company_id=ctx.company_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/reports/orders/{order_id}", response_model=OrderFinancialReportResponse)
async def get_order_financial_report(
    order_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.FINANCE, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> OrderFinancialReportResponse:
    """Auditoría granular de una orden: pagos, comisiones, fletes, retenciones SAT y conciliación."""
    return await finance_service.generate_order_financial_report(
        session=session,
        company_id=ctx.company_id,
        order_id=order_id,
    )


@router.get("/reports/period", response_model=PeriodFinancialReportResponse)
async def get_period_report(
    period: Literal["daily", "weekly", "monthly", "yearly"] = Query("daily", description="Tipo de periodo"),
    reference_date: datetime | None = Query(None, description="Fecha de referencia"),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.FINANCE, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> PeriodFinancialReportResponse:
    """Reporte financiero consolidado por periodo temporal con desglose."""
    ref_dt = reference_date or datetime.now(timezone.utc)
    return await finance_service.generate_period_financial_report(
        session=session,
        company_id=ctx.company_id,
        period_type=period,
        reference_date=ref_dt,
    )


# ---------------------------------------------------------------------------
# TRANSACCIONES FINANCIERAS
# ---------------------------------------------------------------------------

@router.get("/transactions", response_model=Page[FinancialTransactionResponse])
async def list_financial_transactions(
    transaction_type: str | None = Query(None, description="Filtrar por tipo (sale, marketplace_fee, shipping_fee, refund, payout, etc.)"),
    status: str | None = Query(None, description="Filtrar por estatus (pending, accredited, available, settled, withdrawn, refunded)"),
    meli_account_id: uuid.UUID | None = Query(None, description="Filtrar por cuenta MeLi"),
    order_id: uuid.UUID | None = Query(None, description="Filtrar por orden específica"),
    search: str | None = Query(None, description="Buscar por concepto o referencia externa"),
    date_from: datetime | None = Query(None, description="Fecha desde"),
    date_to: datetime | None = Query(None, description="Fecha hasta"),
    params: PaginationParams = Depends(),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.FINANCE, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> Page[FinancialTransaction]:
    """Lista las partidas contables con fechas de origen, importes brutos, comisiones y retenciones."""
    stmt = (
        select(FinancialTransaction)
        .where(FinancialTransaction.company_id == ctx.company_id)
        .order_by(FinancialTransaction.date_created.desc())
    )

    if transaction_type:
        stmt = stmt.where(FinancialTransaction.transaction_type == transaction_type)
    if status:
        stmt = stmt.where(FinancialTransaction.status == status)
    if meli_account_id:
        stmt = stmt.where(FinancialTransaction.meli_account_id == meli_account_id)
    if order_id:
        stmt = stmt.where(FinancialTransaction.order_id == order_id)
    if date_from:
        stmt = stmt.where(FinancialTransaction.date_created >= date_from)
    if date_to:
        stmt = stmt.where(FinancialTransaction.date_created <= date_to)
    if search:
        search_pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                FinancialTransaction.concept.ilike(search_pattern),
                FinancialTransaction.external_reference.ilike(search_pattern),
            )
        )

    items, total = await paginate_query(stmt, session, params)
    return Page.create(items, total, params)


# ---------------------------------------------------------------------------
# LIQUIDACIONES Y RETIROS BANCARIOS
# ---------------------------------------------------------------------------

@router.get("/settlements", response_model=Page[SettlementResponse])
async def list_settlements(
    meli_account_id: uuid.UUID | None = Query(None, description="Filtrar por cuenta MeLi"),
    status: str | None = Query(None, description="Filtrar por estatus"),
    params: PaginationParams = Depends(),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.FINANCE, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> Page[Settlement]:
    """Historial de liquidaciones y transferencias de dinero hacia cuentas bancarias CLABE."""
    stmt = select(Settlement).where(Settlement.company_id == ctx.company_id).order_by(Settlement.period_end.desc())
    if meli_account_id:
        stmt = stmt.where(Settlement.meli_account_id == meli_account_id)
    if status:
        stmt = stmt.where(Settlement.status == status)

    items, total = await paginate_query(stmt, session, params)
    return Page.create(items, total, params)


@router.post("/settlements", response_model=SettlementResponse, status_code=status.HTTP_201_CREATED)
async def create_settlement(
    payload: SettlementCreateRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.FINANCE, ActionEnum.CREATE)),
    session: AsyncSession = Depends(get_db),
) -> Settlement:
    """Registra una liquidación o transferencia bancaria y genera la partida de retiro (payout)."""
    settlement = await finance_service.record_settlement(session, ctx.company_id, payload)
    await session.commit()
    return settlement


# ---------------------------------------------------------------------------
# GASTOS OPERATIVOS EXTERNOS MANUALES
# ---------------------------------------------------------------------------

@router.get("/expenses", response_model=Page[ExternalExpenseResponse])
async def list_external_expenses(
    category: str | None = Query(None, description="Filtrar por categoría"),
    meli_account_id: uuid.UUID | None = Query(None, description="Filtrar por cuenta"),
    order_id: uuid.UUID | None = Query(None, description="Filtrar por orden"),
    search: str | None = Query(None, description="Buscar por concepto o proveedor"),
    params: PaginationParams = Depends(),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.FINANCE, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> Page[ExternalExpense]:
    """Lista de gastos operativos externos ingresados manualmente."""
    stmt = (
        select(ExternalExpense)
        .where(ExternalExpense.company_id == ctx.company_id)
        .order_by(ExternalExpense.expense_date.desc())
    )
    if category:
        stmt = stmt.where(ExternalExpense.category == category)
    if meli_account_id:
        stmt = stmt.where(ExternalExpense.meli_account_id == meli_account_id)
    if order_id:
        stmt = stmt.where(ExternalExpense.order_id == order_id)
    if search:
        search_pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                ExternalExpense.concept.ilike(search_pattern),
                ExternalExpense.vendor_name.ilike(search_pattern),
                ExternalExpense.invoice_folio.ilike(search_pattern),
            )
        )

    items, total = await paginate_query(stmt, session, params)
    return Page.create(items, total, params)


@router.post("/expenses", response_model=ExternalExpenseResponse, status_code=status.HTTP_201_CREATED)
async def create_external_expense(
    payload: ExternalExpenseCreateRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.FINANCE, ActionEnum.CREATE)),
    session: AsyncSession = Depends(get_db),
) -> ExternalExpense:
    """Permite registrar un gasto externo manual (publicidad externa, empaques, fletes privados)."""
    expense = await finance_service.register_external_expense(
        session=session,
        company_id=ctx.company_id,
        payload=payload,
        created_by_user_id=ctx.user_id,
    )
    await session.commit()
    return expense


# ---------------------------------------------------------------------------
# CONCILIACIÓN AUTOMÁTICA Y DISCREPANCIAS
# ---------------------------------------------------------------------------

@router.post("/reconciliation/run", response_model=ReconciliationRunResponse)
async def run_reconciliation(
    meli_account_id: uuid.UUID | None = Query(None, description="Ejecutar para una cuenta específica o todas"),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.FINANCE, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> ReconciliationRunResponse:
    """
    Ejecuta el motor de conciliación automática entre órdenes, pagos y liquidaciones.
    Detecta diferencias de montos, cobros inesperados y desajustes en comisiones e impuestos.
    """
    res = await finance_service.run_automatic_reconciliation(
        session=session,
        company_id=ctx.company_id,
        meli_account_id=meli_account_id,
    )
    await session.commit()
    return res


@router.get("/discrepancies", response_model=Page[FinancialDiscrepancyResponse])
async def list_discrepancies(
    status_filter: str | None = Query(None, alias="status", description="Filtrar por estatus (unresolved, investigating, resolved, ignored)"),
    severity: str | None = Query(None, description="Filtrar por severidad (low, medium, high, critical)"),
    discrepancy_type: str | None = Query(None, description="Filtrar por tipo"),
    meli_account_id: uuid.UUID | None = Query(None, description="Filtrar por cuenta MeLi"),
    params: PaginationParams = Depends(),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.FINANCE, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> Page[FinancialDiscrepancy]:
    """Lista las discrepancias financieras detectadas entre ventas, pagos y liquidaciones."""
    stmt = (
        select(FinancialDiscrepancy)
        .where(FinancialDiscrepancy.company_id == ctx.company_id)
        .order_by(FinancialDiscrepancy.detection_date.desc())
    )
    if status_filter:
        stmt = stmt.where(FinancialDiscrepancy.status == status_filter)
    if severity:
        stmt = stmt.where(FinancialDiscrepancy.severity == severity)
    if discrepancy_type:
        stmt = stmt.where(FinancialDiscrepancy.discrepancy_type == discrepancy_type)
    if meli_account_id:
        stmt = stmt.where(FinancialDiscrepancy.meli_account_id == meli_account_id)

    items, total = await paginate_query(stmt, session, params)
    return Page.create(items, total, params)


@router.post("/discrepancies/{discrepancy_id}/resolve", response_model=FinancialDiscrepancyResponse)
async def resolve_discrepancy(
    discrepancy_id: uuid.UUID,
    payload: DiscrepancyResolveRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.FINANCE, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> FinancialDiscrepancy:
    """Marca una discrepancia financiera como resuelta, investigada o ignorada."""
    disc = await session.get(FinancialDiscrepancy, discrepancy_id)
    if not disc or disc.company_id != ctx.company_id:
        raise EntityNotFoundException("Discrepancia Financiera", str(discrepancy_id))

    disc.status = payload.status
    disc.resolution_notes = payload.resolution_notes
    disc.resolved_at = datetime.now(timezone.utc)
    await session.commit()
    return disc

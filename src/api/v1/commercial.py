"""API REST para el Administrador Comercial: Reglas, Precios, Promociones, Simulación, Competencia y Recomendaciones."""

from typing import Any, Literal
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_context import CompanyContext, require_company_permission
from src.core.database import get_db
from src.core.exceptions import EntityNotFoundException, ValidationException
from src.core.pagination import Page, PaginationParams, paginate_query
from src.core.permissions import ActionEnum, ModuleEnum
from src.models.commercial import CommercialRecommendation, CommercialRule, PriceHistory, ScheduledPriceChange
from src.schemas.commercial import (
    CommercialRecommendationResponse,
    CommercialRuleCreateRequest,
    CommercialRuleResponse,
    CommercialRuleUpdateRequest,
    CompetitorBenchmarkResponse,
    PriceHistoryResponse,
    PriceRestoreRequest,
    PriceUpdateRequest,
    PriceUpdateResponse,
    PromotionOptinRequest,
    PromotionOptinResponse,
    PromotionSimulationRequest,
    PromotionSimulationResponse,
    ScheduledPriceChangeCreateRequest,
    ScheduledPriceChangeResponse,
)
from src.services.commercial_service import CommercialService

router = APIRouter(prefix="/commercial", tags=["Administrador Comercial & Precios"])
commercial_service = CommercialService()


# ---------------------------------------------------------------------------
# REGLAS COMERCIALES CONFIGURABLES
# ---------------------------------------------------------------------------

@router.get("/rules", response_model=list[CommercialRuleResponse])
async def list_commercial_rules(
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> list[CommercialRule]:
    """Lista todas las reglas comerciales de precios, márgenes mínimos y techos de descuento."""
    return await commercial_service.list_rules(session, ctx.company_id)


@router.post("/rules", response_model=CommercialRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_commercial_rule(
    payload: CommercialRuleCreateRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.CREATE)),
    session: AsyncSession = Depends(get_db),
) -> CommercialRule:
    """Crea una regla comercial para proteger la rentabilidad y automatizar ajustes autorizados."""
    rule = await commercial_service.create_rule(session, ctx.company_id, payload)
    await session.commit()
    return rule


@router.put("/rules/{rule_id}", response_model=CommercialRuleResponse)
async def update_commercial_rule(
    rule_id: uuid.UUID,
    payload: CommercialRuleUpdateRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> CommercialRule:
    """Modifica parámetros de una regla comercial (precios piso, horarios, SKUs excluidos)."""
    rule = await commercial_service.update_rule(session, rule_id, ctx.company_id, payload)
    await session.commit()
    return rule


# ---------------------------------------------------------------------------
# SIMULACIÓN DE RENTABILIDAD ANTES DE APLICAR DESCUENTOS
# ---------------------------------------------------------------------------

@router.post("/prices/simulate", response_model=PromotionSimulationResponse)
async def simulate_promotion(
    payload: PromotionSimulationRequest,
    meli_account_id: uuid.UUID | None = Query(None, description="Cuenta MeLi para aplicar regla específica"),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> PromotionSimulationResponse:
    """
    Simula con estricto rigor financiero el resultado de una oferta antes de aplicarla.
    Desglosa comisiones MeLi, flete vendedor, empaque y retenciones SAT México (IVA 8% e ISR 1%).
    Evalúa viabilidad frente al margen y precio mínimo configurados.
    """
    rule = await commercial_service.get_effective_rule(session, ctx.company_id, meli_account_id)
    return commercial_service.simulate_promotion_profitability(payload, rule)


# ---------------------------------------------------------------------------
# MODIFICACIÓN, AUDITORÍA Y RESTAURACIÓN DE PRECIOS
# ---------------------------------------------------------------------------

@router.post("/prices/restore", response_model=PriceUpdateResponse)
async def restore_previous_price(
    payload: PriceRestoreRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> PriceUpdateResponse:
    """
    Restaura el precio original previo a una modificación técnica,
    re-aplicándolo directamente a Mercado Libre y actualizando el historial.
    """
    res = await commercial_service.restore_previous_price(
        session=session,
        company_id=ctx.company_id,
        user_id=ctx.user_id,
        history_id=payload.history_id,
    )
    await session.commit()
    return res


@router.get("/prices/history", response_model=Page[PriceHistoryResponse])
async def list_price_history(
    meli_item_id: str | None = Query(None, description="Filtrar por publicación específica"),
    params: PaginationParams = Depends(),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> Page[PriceHistory]:
    """Consulta el historial de auditoría de modificaciones de precios."""
    stmt = await commercial_service.list_price_history(session, ctx.company_id, meli_item_id)
    items, total = await paginate_query(stmt, session, params)
    return Page.create(items, total, params)


@router.post("/prices/schedule", response_model=ScheduledPriceChangeResponse, status_code=status.HTTP_201_CREATED)
async def schedule_price_change(
    payload: ScheduledPriceChangeCreateRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> ScheduledPriceChange:
    """Programa una modificación de precio a futuro con opción de reversión automática."""
    scheduled = await commercial_service.schedule_price_change(
        session=session,
        company_id=ctx.company_id,
        user_id=ctx.user_id,
        meli_item_id=payload.meli_item_id,
        target_price=payload.target_price,
        scheduled_at=payload.scheduled_at,
        revert_at=payload.revert_at,
    )
    await session.commit()
    return scheduled


@router.post("/prices/schedule/process")
async def trigger_process_scheduled_prices(
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
):
    """Procesa y aplica las modificaciones de precios programadas cuya fecha ha llegado."""
    count = await commercial_service.process_due_scheduled_prices(session)
    await session.commit()
    return {"status": "success", "applied_count": count}


@router.post("/prices/{item_id}", response_model=PriceUpdateResponse)
async def update_item_price(
    item_id: str,
    payload: PriceUpdateRequest,
    meli_account_id: uuid.UUID = Query(..., description="Cuenta MeLi a la que pertenece la publicación"),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> PriceUpdateResponse:
    """
    Modifica oficialmente el precio en Mercado Libre mediante la API REST oficial.
    Valida previamente precios piso, descuentos máximos y límite de cambios diarios.
    Registra auditoría completa en el historial de precios.
    """
    res = await commercial_service.update_item_price(
        session=session,
        company_id=ctx.company_id,
        meli_account_id=meli_account_id,
        user_id=ctx.user_id,
        meli_item_id=item_id,
        new_price=payload.new_price,
        variation_id=payload.variation_id,
        reason=payload.reason,
        bypass_rules=payload.bypass_rules,
    )
    await session.commit()
    return res


# ---------------------------------------------------------------------------
# PROMOCIONES, CAMPAÑAS Y OFERTAS OFICIALES
# ---------------------------------------------------------------------------

@router.get("/promotions")
async def get_seller_promotions(
    meli_account_id: uuid.UUID = Query(..., description="Cuenta MeLi a consultar"),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
):
    """Consulta las campañas promocionales oficiales disponibles en MeLi para la cuenta."""
    return await commercial_service.get_seller_promotions(session, ctx.company_id, meli_account_id)


@router.get("/promotions/{promotion_id}/candidates")
async def get_promotion_candidates(
    promotion_id: str,
    meli_account_id: uuid.UUID = Query(..., description="Cuenta MeLi a consultar"),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
):
    """Consulta las publicaciones elegibles como candidatas para una campaña oficial."""
    return await commercial_service.get_promotion_candidates(session, ctx.company_id, meli_account_id, promotion_id)


@router.post("/promotions/optin", response_model=PromotionOptinResponse)
async def optin_promotion(
    item_id: str = Query(..., description="ID de la publicación (e.g. MLM123456)"),
    meli_account_id: uuid.UUID = Query(..., description="Cuenta MeLi propietaria"),
    payload: PromotionOptinRequest = ...,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> PromotionOptinResponse:
    """
    Postula formalmente un artículo a una campaña oficial.
    REGLA: No afirma que la promoción se activó sin confirmación oficial de Mercado Libre.
    """
    res = await commercial_service.optin_promotion_item(
        session=session,
        company_id=ctx.company_id,
        meli_account_id=meli_account_id,
        item_id=item_id,
        promotion_id=payload.promotion_id,
        promotion_type=payload.promotion_type,
        deal_price=payload.deal_price,
        validate_viability=payload.validate_viability,
    )
    await session.commit()
    return res


# ---------------------------------------------------------------------------
# ANÁLISIS DE COMPETENCIA Y RECOMENDACIONES COMERCIALES
# ---------------------------------------------------------------------------

@router.get("/competitor/{item_id}", response_model=CompetitorBenchmarkResponse)
async def benchmark_competitor(
    item_id: str,
    meli_account_id: uuid.UUID = Query(..., description="Cuenta MeLi propietaria"),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> CompetitorBenchmarkResponse:
    """
    Analiza la competencia mediante datos autorizados de catálogo en Mercado Libre.
    Evalúa precio del Buy Box y calcula sugerencias para ganar la publicación.
    """
    bench = await commercial_service.benchmark_competitor_item(session, ctx.company_id, meli_account_id, item_id)
    await session.commit()
    return bench


@router.get("/recommendations", response_model=list[CommercialRecommendationResponse])
async def list_recommendations(
    status_filter: str = Query("pending", description="Filtrar por estatus (pending, applied, dismissed)"),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.COMMERCIAL, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> list[CommercialRecommendation]:
    """Lista las oportunidades comerciales y recomendaciones de rentabilidad generadas."""
    return await commercial_service.list_recommendations(session, ctx.company_id, status_filter)

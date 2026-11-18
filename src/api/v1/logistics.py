"""API REST para el Centro de Logística, Despacho, Seguimiento y Sistema Dual de Etiquetas (Envíos & Internas)."""

from typing import Literal
import uuid

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_context import CompanyContext, require_company_permission
from src.core.database import get_db
from src.core.pagination import Page, PaginationParams, paginate_query
from src.core.permissions import ActionEnum, ModuleEnum
from src.models.internal_label import InternalLabelTemplate
from src.models.shipment import Shipment, ShipmentPrintLog
from src.schemas.logistics import (
    InternalLabelGenerateRequest,
    InternalLabelOrderRequest,
    InternalLabelResponse,
    InternalLabelTemplateResponse,
    LogisticsDashboardMetricsResponse,
    LogisticsLimitationsDocResponse,
    ShipmentBatchPrintRequest,
    ShipmentBatchPrintResponse,
    ShipmentPrintLogResponse,
    ShipmentPrintRequest,
    ShipmentReprintRequest,
    ShipmentResponse,
    ShipmentTrackingResponse,
)
from src.services.logistics_service import LogisticsService

router = APIRouter(prefix="/logistics", tags=["Centro de Logística & Etiquetas"])
logistics_service = LogisticsService()


# ---------------------------------------------------------------------------
# MÉTRICAS Y TABLERO OPERATIVO DE LOGÍSTICA
# ---------------------------------------------------------------------------

@router.get("/metrics", response_model=LogisticsDashboardMetricsResponse)
async def get_logistics_metrics(
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.LOGISTICS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> LogisticsDashboardMetricsResponse:
    """Retorna los conteos operativos: pedidos pendientes, preparados, despachados, errores y modalidades."""
    return await logistics_service.get_dashboard_metrics(session, ctx.company_id)


@router.get("/limitations", response_model=LogisticsLimitationsDocResponse)
async def get_logistics_limitations(
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.LOGISTICS, ActionEnum.READ)),
) -> LogisticsLimitationsDocResponse:
    """Documentación oficial de las limitaciones técnicas de la API de Mercado Envíos y contingencias permitidas."""
    return logistics_service.get_logistics_limitations_doc()


# ---------------------------------------------------------------------------
# MÓDULO A: ENVÍOS, DESPACHO Y ETIQUETAS OFICIALES (Mercado Envíos)
# ---------------------------------------------------------------------------

@router.get("/shipments", response_model=Page[ShipmentResponse])
async def list_shipments(
    dispatch_status: str | None = Query(None, description="Filtrar por estado operativo: pending, prepared, dispatched, error"),
    logistic_type: str | None = Query(None, description="Filtrar por modalidad: fulfillment, cross_docking, drop_off, self_service"),
    carrier_name: str | None = Query(None, description="Filtrar por paquetería (DHL, FedEx, Estafeta, etc.)"),
    search: str | None = Query(None, description="Buscar por número de guía, tracking, orden o comprador"),
    params: PaginationParams = Depends(),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.LOGISTICS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> Page[Shipment]:
    """Lista los envíos de la empresa con clasificación operativa y filtros avanzados."""
    stmt = await logistics_service.list_shipments(
        session=session,
        company_id=ctx.company_id,
        dispatch_status=dispatch_status,
        logistic_type=logistic_type,
        carrier_name=carrier_name,
        search=search,
    )
    items, total = await paginate_query(stmt, session, params)
    return Page.create(items, total, params)


@router.get("/shipments/{shipment_id}", response_model=ShipmentResponse)
async def get_shipment_detail(
    shipment_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.LOGISTICS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> Shipment:
    """Detalle completo del envío, domicilios de entrega y desglose de flete."""
    return await logistics_service.get_shipment_by_id(session, shipment_id, ctx.company_id)


@router.get("/shipments/{shipment_id}/tracking", response_model=ShipmentTrackingResponse)
async def get_shipment_tracking(
    shipment_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.LOGISTICS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> ShipmentTrackingResponse:
    """Trazabilidad completa, checkpoints y seguimiento en tiempo real del transportista."""
    tracking = await logistics_service.get_shipment_tracking(session, shipment_id, ctx.company_id)
    await session.commit()
    return tracking


@router.get("/shipments/{shipment_id}/label")
async def download_shipment_label(
    shipment_id: uuid.UUID,
    format_type: Literal["pdf", "zpl2"] = Query("pdf", description="Formato de la guía oficial"),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.LOGISTICS, ActionEnum.PRINT_LABEL)),
    session: AsyncSession = Depends(get_db),
):
    """
    Descarga o previsualiza la guía oficial de Mercado Envíos directamente en PDF o ZPL.
    REGLA: No genera etiquetas falsas. Si es Full o está cancelado, informa la limitación oficial.
    """
    label_bytes, content_type = await logistics_service.download_official_shipment_label(
        session=session,
        shipment_id=shipment_id,
        company_id=ctx.company_id,
        format_type=format_type,
    )
    
    filename = f"guia_oficial_{shipment_id}.{format_type}"
    return Response(
        content=label_bytes,
        media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.post("/shipments/{shipment_id}/print", response_model=ShipmentPrintLogResponse, status_code=status.HTTP_201_CREATED)
async def record_shipment_print(
    shipment_id: uuid.UUID,
    payload: ShipmentPrintRequest,
    request: Request,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.LOGISTICS, ActionEnum.PRINT_LABEL)),
    session: AsyncSession = Depends(get_db),
) -> ShipmentPrintLog:
    """
    Registra la primera impresión de la guía oficial.
    Actualiza el estado operativo a 'prepared' e incrementa el contador de impresiones.
    """
    client_ip = request.client.host if request.client else None
    log_entry = await logistics_service.record_shipment_print(
        session=session,
        shipment_id=shipment_id,
        company_id=ctx.company_id,
        user_id=ctx.user_id,
        format_type=payload.format,
        is_reprint=False,
        ip_address=client_ip,
    )
    await session.commit()
    return log_entry


@router.post("/shipments/{shipment_id}/reprint", response_model=ShipmentPrintLogResponse, status_code=status.HTTP_201_CREATED)
async def record_shipment_reprint(
    shipment_id: uuid.UUID,
    payload: ShipmentReprintRequest,
    request: Request,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.LOGISTICS, ActionEnum.PRINT_LABEL)),
    session: AsyncSession = Depends(get_db),
) -> ShipmentPrintLog:
    """
    Registra una reimpresión de guía oficial auditando obligatoriamente el motivo justificado.
    Bloquea reimpresiones si el paquete ya fue despachado o entregado.
    """
    client_ip = request.client.host if request.client else None
    log_entry = await logistics_service.record_shipment_print(
        session=session,
        shipment_id=shipment_id,
        company_id=ctx.company_id,
        user_id=ctx.user_id,
        format_type=payload.format,
        is_reprint=True,
        reprint_reason=payload.reprint_reason,
        ip_address=client_ip,
    )
    await session.commit()
    return log_entry


@router.post("/shipments/labels/batch", response_model=ShipmentBatchPrintResponse)
async def batch_print_shipments(
    payload: ShipmentBatchPrintRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.LOGISTICS, ActionEnum.PRINT_LABEL)),
    session: AsyncSession = Depends(get_db),
) -> ShipmentBatchPrintResponse:
    """
    Descarga e imprime guías oficiales en lote (hasta 50 por bloque permitido por MeLi).
    Agrupa por cuenta de Mercado Libre, valida elegibilidad y genera el log de auditoría.
    """
    _, summary = await logistics_service.batch_print_shipments(
        session=session,
        company_id=ctx.company_id,
        user_id=ctx.user_id,
        shipment_ids=payload.shipment_ids,
        format_type=payload.format,
    )
    await session.commit()
    return summary


# ---------------------------------------------------------------------------
# MÓDULO B: ETIQUETAS INTERNAS DE ALMACÉN, PRODUCTOS Y SURTIDO
# ---------------------------------------------------------------------------

@router.get("/internal-labels/templates", response_model=list[InternalLabelTemplateResponse])
async def list_internal_label_templates(
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.LOGISTICS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> list[InternalLabelTemplate]:
    """Lista las plantillas disponibles (Térmica 100x150, 50x30, Hoja Carta 30 etiquetas, Joyera)."""
    templates = await logistics_service.get_or_create_default_internal_templates(session, ctx.company_id)
    await session.commit()
    return templates


@router.post("/internal-labels/generate", response_model=InternalLabelResponse)
async def generate_internal_labels(
    payload: InternalLabelGenerateRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.LOGISTICS, ActionEnum.PRINT_LABEL)),
    session: AsyncSession = Depends(get_db),
) -> InternalLabelResponse:
    """
    Genera etiquetas internas masivas con SKU, Code 128, QR, ubicación y precio opcional.
    Devuelve HTML listo para imprimir (`window.print()`) o código ZPL para impresoras Zebra.
    """
    result = await logistics_service.generate_internal_labels_for_items(
        session=session,
        company_id=ctx.company_id,
        user_id=ctx.user_id,
        items=payload.items,
        template_type=payload.template_type,
        include_price=payload.include_price,
        output_format=payload.output_format,
    )
    await session.commit()
    return result


@router.post("/internal-labels/order/{order_id}", response_model=InternalLabelResponse)
async def generate_internal_labels_for_order(
    order_id: uuid.UUID,
    payload: InternalLabelOrderRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.LOGISTICS, ActionEnum.PRINT_LABEL)),
    session: AsyncSession = Depends(get_db),
) -> InternalLabelResponse:
    """Genera las etiquetas internas de surtido de almacén para todos los productos de un pedido específico."""
    result = await logistics_service.generate_internal_labels_for_order(
        session=session,
        company_id=ctx.company_id,
        user_id=ctx.user_id,
        order_id=order_id,
        template_type=payload.template_type,
        include_price=payload.include_price,
        output_format=payload.output_format,
    )
    await session.commit()
    return result

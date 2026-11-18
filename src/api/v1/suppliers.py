"""
Rutas API REST v1 para Abastecimiento:
Proveedores, Catálogo de Suministro, Evaluación de Desempeño,
Órdenes de Compra con Autorización Previa, Recepciones Parciales,
Facturas de Compra, Gastos Asociados (Landed Cost) y Motor de Reposición Inteligente.
"""

import uuid
from typing import Literal
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_context import CompanyContext, require_company_permission
from src.core.database import get_db
from src.core.exceptions import PermissionDeniedException, ValidationException
from src.core.pagination import Page, PaginationParams
from src.core.permissions import ActionEnum, ModuleEnum
from src.schemas.supplier import (
    CreatePOFromSuggestionsRequest,
    GoodsReceiptCreate,
    GoodsReceiptResponse,
    LandedCostSummaryResponse,
    PurchaseExpenseCreate,
    PurchaseExpenseResponse,
    PurchaseInvoiceCreate,
    PurchaseInvoiceResponse,
    PurchaseOrderApproveRequest,
    PurchaseOrderAuthorizePaymentRequest,
    PurchaseOrderCancelRequest,
    PurchaseOrderCreate,
    PurchaseOrderResponse,
    PurchaseOrderUpdate,
    ReplenishmentReportResponse,
    SupplierCreate,
    SupplierEvaluationCreate,
    SupplierEvaluationResponse,
    SupplierProductCreate,
    SupplierProductResponse,
    SupplierProductUpdate,
    SupplierResponse,
    SupplierUpdate,
)
from src.services.procurement_service import ProcurementService

router = APIRouter(prefix="/suppliers", tags=["Abastecimiento & Proveedores"])
procurement_service = ProcurementService()


# ===========================================================================
# 1. MOTOR DE REPOSICIÓN INTELIGENTE Y ALERTAS (Rutas estáticas prioritarias)
# ===========================================================================

@router.get(
    "/replenishment/suggestions",
    response_model=ReplenishmentReportResponse,
    summary="Analiza y genera sugerencias de reposición de inventario",
)
async def get_replenishment_suggestions(
    days_history: int = Query(30, ge=7, le=180, description="Días de historial de ventas analizados"),
    target_days_coverage: int = Query(30, ge=7, le=120, description="Días objetivo de inventario a cubrir"),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SUPPLIERS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> ReplenishmentReportResponse:
    """
    Ejecuta el motor de reposición inteligente considerando:
    - Ventas históricas
    - Velocidad de rotación
    - Stock disponible, reservado y en tránsito
    - Tiempo de entrega (lead time)
    - Stock de seguridad
    - Demanda estimada y Punto de Reorden (ROP)
    - Alertas de agotados, críticos, reorden y sobre-inventario
    """
    return await procurement_service.analyze_replenishment(
        session=session,
        company_id=ctx.company_id,
        days_history=days_history,
        target_days_coverage=target_days_coverage,
    )


@router.post(
    "/replenishment/generate-po",
    response_model=PurchaseOrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Genera una orden de compra en borrador a partir de sugerencias de reposición",
)
async def create_po_from_suggestions(
    payload: CreatePOFromSuggestionsRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SUPPLIERS, ActionEnum.CREATE)),
    session: AsyncSession = Depends(get_db),
) -> PurchaseOrderResponse:
    """Genera un borrador de OC a partir de sugerencias seleccionadas."""
    po = await procurement_service.create_po_from_suggestions(
        session=session,
        company_id=ctx.company_id,
        payload=payload,
        user_id=ctx.user.id,
    )
    return await procurement_service.get_purchase_order(session, ctx.company_id, po.id)  # type: ignore


# ===========================================================================
# 2. ÓRDENES DE COMPRA (Rutas estáticas y dinámicas)
# ===========================================================================

@router.post(
    "/purchase-orders",
    response_model=PurchaseOrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crea una nueva orden de compra en borrador (requiere autorización)",
)
async def create_purchase_order(
    payload: PurchaseOrderCreate,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SUPPLIERS, ActionEnum.CREATE)),
    session: AsyncSession = Depends(get_db),
) -> PurchaseOrderResponse:
    """
    Crea una orden de compra en estado borrador (draft).
    No genera compras ni pagos reales sin previa autorización.
    """
    if payload.company_id != ctx.company_id:
        raise PermissionDeniedException("No se puede generar una orden para otra empresa.")

    po = await procurement_service.create_purchase_order(
        session=session,
        company_id=ctx.company_id,
        payload=payload,
        user_id=ctx.user.id,
    )
    return await procurement_service.get_purchase_order(session, ctx.company_id, po.id)  # type: ignore


@router.get(
    "/purchase-orders",
    response_model=Page[PurchaseOrderResponse],
    summary="Lista órdenes de compra con filtros por proveedor y estado",
)
async def list_purchase_orders(
    supplier_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SUPPLIERS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> Page[PurchaseOrderResponse]:
    """Lista órdenes de compra de la empresa activa."""
    offset = (page - 1) * limit
    items, total = await procurement_service.list_purchase_orders(
        session=session,
        company_id=ctx.company_id,
        supplier_id=supplier_id,
        status=status,
        offset=offset,
        limit=limit,
    )
    return Page.create(items=items, total_items=total, params=PaginationParams(page=page, page_size=limit))  # type: ignore


@router.get(
    "/purchase-orders/{po_id}",
    response_model=PurchaseOrderResponse,
    summary="Obtiene el detalle completo de una orden de compra",
)
async def get_purchase_order(
    po_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SUPPLIERS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> PurchaseOrderResponse:
    """Obtiene el detalle de una OC con partidas, recepciones y facturas."""
    return await procurement_service.get_purchase_order(session, ctx.company_id, po_id)  # type: ignore


@router.post(
    "/purchase-orders/{po_id}/approve",
    response_model=PurchaseOrderResponse,
    summary="Autoriza formalmente una orden de compra",
)
async def approve_purchase_order(
    po_id: uuid.UUID,
    payload: PurchaseOrderApproveRequest = PurchaseOrderApproveRequest(),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SUPPLIERS, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> PurchaseOrderResponse:
    """
    Autorización de compra por parte de un usuario facultado.
    Garantiza: 'No generar compras ni pagos reales sin autorización'.
    """
    po = await procurement_service.approve_purchase_order(
        session=session,
        company_id=ctx.company_id,
        po_id=po_id,
        user_id=ctx.user.id,
        notes=payload.notes,
    )
    return await procurement_service.get_purchase_order(session, ctx.company_id, po.id)  # type: ignore


@router.post(
    "/purchase-orders/{po_id}/issue",
    response_model=PurchaseOrderResponse,
    summary="Emite formalmente la orden autorizada al proveedor",
)
async def issue_purchase_order(
    po_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SUPPLIERS, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> PurchaseOrderResponse:
    """Emite la orden de compra una vez aprobada."""
    po = await procurement_service.issue_purchase_order(
        session=session,
        company_id=ctx.company_id,
        po_id=po_id,
        user_id=ctx.user.id,
    )
    return await procurement_service.get_purchase_order(session, ctx.company_id, po.id)  # type: ignore


@router.post(
    "/purchase-orders/{po_id}/cancel",
    response_model=PurchaseOrderResponse,
    summary="Cancela una orden de compra con motivo auditado",
)
async def cancel_purchase_order(
    po_id: uuid.UUID,
    payload: PurchaseOrderCancelRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SUPPLIERS, ActionEnum.DELETE)),
    session: AsyncSession = Depends(get_db),
) -> PurchaseOrderResponse:
    """Cancela una orden de compra no completada."""
    po = await procurement_service.cancel_purchase_order(
        session=session,
        company_id=ctx.company_id,
        po_id=po_id,
        reason=payload.reason,
        user_id=ctx.user.id,
    )
    return await procurement_service.get_purchase_order(session, ctx.company_id, po.id)  # type: ignore


@router.post(
    "/purchase-orders/{po_id}/authorize-payment",
    response_model=PurchaseOrderResponse,
    summary="Autoriza formalmente el pago/desembolso a proveedor",
)
async def authorize_purchase_payment(
    po_id: uuid.UUID,
    payload: PurchaseOrderAuthorizePaymentRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SUPPLIERS, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> PurchaseOrderResponse:
    """
    Autoriza el pago formal a proveedor.
    Garantiza: 'No generar pagos reales sin autorización'.
    """
    po = await procurement_service.authorize_payment(
        session=session,
        company_id=ctx.company_id,
        po_id=po_id,
        user_id=ctx.user.id,
        notes=payload.notes,
    )
    return await procurement_service.get_purchase_order(session, ctx.company_id, po.id)  # type: ignore


# ===========================================================================
# 3. RECEPCIONES DE MERCANCÍA (PARCIALES Y TOTALES)
# ===========================================================================

@router.post(
    "/purchase-orders/{po_id}/receipts",
    response_model=GoodsReceiptResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registra una recepción física de mercancía (parcial o total) y actualiza inventario",
)
async def create_goods_receipt(
    po_id: uuid.UUID,
    payload: GoodsReceiptCreate,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SUPPLIERS, ActionEnum.CREATE)),
    session: AsyncSession = Depends(get_db),
) -> GoodsReceiptResponse:
    """
    Registra recepción física de mercancía:
    - Permite recepciones parciales.
    - Actualiza el inventario transaccionalmente creando movimientos auditables INBOUND.
    - Actualiza el costo COGS en el catálogo maestro y en el historial inmutable.
    """
    return await procurement_service.create_goods_receipt(
        session=session,
        company_id=ctx.company_id,
        po_id=po_id,
        payload=payload,
        user_id=ctx.user.id,
        user_name=ctx.user.full_name or "Encargado Almacén",
    )  # type: ignore


@router.get(
    "/purchase-orders/{po_id}/receipts",
    response_model=list[GoodsReceiptResponse],
    summary="Consulta las recepciones físicas asociadas a una orden de compra",
)
async def list_po_receipts(
    po_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SUPPLIERS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> list[GoodsReceiptResponse]:
    """Lista las recepciones de una OC."""
    return await procurement_service.list_goods_receipts(session, ctx.company_id, po_id=po_id)  # type: ignore


@router.get(
    "/receipts",
    response_model=list[GoodsReceiptResponse],
    summary="Consulta todas las recepciones de mercancía de la empresa",
)
async def list_all_receipts(
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SUPPLIERS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> list[GoodsReceiptResponse]:
    """Lista todas las recepciones registradas en los almacenes."""
    return await procurement_service.list_goods_receipts(session, ctx.company_id)  # type: ignore


# ===========================================================================
# 4. FACTURAS DE PROVEEDOR Y GASTOS ASOCIADOS (LANDED COST)
# ===========================================================================

@router.post(
    "/purchase-orders/{po_id}/invoices",
    response_model=PurchaseInvoiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registra una factura comercial o CFDI 4.0 de proveedor",
)
async def register_purchase_invoice(
    po_id: uuid.UUID,
    payload: PurchaseInvoiceCreate,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SUPPLIERS, ActionEnum.CREATE)),
    session: AsyncSession = Depends(get_db),
) -> PurchaseInvoiceResponse:
    """Registra la factura formal de compra."""
    return await procurement_service.register_invoice(session, ctx.company_id, po_id, payload)  # type: ignore


@router.get(
    "/purchase-orders/{po_id}/invoices",
    response_model=list[PurchaseInvoiceResponse],
    summary="Lista las facturas asociadas a una orden de compra",
)
async def list_po_invoices(
    po_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SUPPLIERS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> list[PurchaseInvoiceResponse]:
    """Lista facturas de compra."""
    return await procurement_service.list_invoices(session, ctx.company_id, po_id=po_id)  # type: ignore


@router.post(
    "/purchase-orders/{po_id}/expenses",
    response_model=PurchaseExpenseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registra un gasto adicional de abastecimiento (flete, aduana, maniobras, seguro)",
)
async def register_purchase_expense(
    po_id: uuid.UUID,
    payload: PurchaseExpenseCreate,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SUPPLIERS, ActionEnum.CREATE)),
    session: AsyncSession = Depends(get_db),
) -> PurchaseExpenseResponse:
    """Registra gastos asociados al embarque para prorrateo en landed cost."""
    return await procurement_service.register_expense(session, ctx.company_id, po_id, payload)  # type: ignore


@router.get(
    "/purchase-orders/{po_id}/expenses",
    response_model=list[PurchaseExpenseResponse],
    summary="Lista gastos adicionales de abastecimiento",
)
async def list_po_expenses(
    po_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SUPPLIERS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> list[PurchaseExpenseResponse]:
    """Consulta gastos asociados."""
    return await procurement_service.list_expenses(session, ctx.company_id, po_id)  # type: ignore


@router.get(
    "/purchase-orders/{po_id}/landed-cost",
    response_model=LandedCostSummaryResponse,
    summary="Calcula el costo puesto en almacén (Landed Cost) por partida",
)
async def get_po_landed_cost(
    po_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SUPPLIERS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> LandedCostSummaryResponse:
    """Prorratea fletes, seguros y gastos sobre las partidas para obtener el costo landed exacto."""
    return await procurement_service.calculate_landed_cost(session, ctx.company_id, po_id)


# ===========================================================================
# 5. CATÁLOGO DE SUMINISTRO Y EVALUACIÓN DE PROVEEDORES
# ===========================================================================

@router.get(
    "/{supplier_id}/products",
    response_model=list[SupplierProductResponse],
    summary="Lista los productos y variantes suministrados por el proveedor",
)
async def list_supplier_products(
    supplier_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SUPPLIERS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> list[SupplierProductResponse]:
    """Consulta catálogo suministrado por un proveedor."""
    return await procurement_service.list_supplier_products(session, ctx.company_id, supplier_id)  # type: ignore


@router.post(
    "/{supplier_id}/products",
    response_model=SupplierProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Asocia un producto o variante al catálogo del proveedor",
)
async def link_supplier_product(
    supplier_id: uuid.UUID,
    payload: SupplierProductCreate,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SUPPLIERS, ActionEnum.CREATE)),
    session: AsyncSession = Depends(get_db),
) -> SupplierProductResponse:
    """Registra costo pactado, MOQ y plazo de entrega específico del SKU."""
    return await procurement_service.link_supplier_product(session, ctx.company_id, supplier_id, payload)  # type: ignore


@router.delete(
    "/{supplier_id}/products/{variant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Desasocia un producto del catálogo del proveedor",
)
async def remove_supplier_product(
    supplier_id: uuid.UUID,
    variant_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SUPPLIERS, ActionEnum.DELETE)),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Elimina una asociación de producto."""
    await procurement_service.remove_supplier_product(session, ctx.company_id, supplier_id, variant_id)


@router.get(
    "/{supplier_id}/evaluations",
    response_model=list[SupplierEvaluationResponse],
    summary="Consulta el historial de evaluaciones de desempeño de un proveedor",
)
async def list_supplier_evaluations(
    supplier_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SUPPLIERS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> list[SupplierEvaluationResponse]:
    """Lista evaluaciones del proveedor."""
    return await procurement_service.list_evaluations(session, ctx.company_id, supplier_id)  # type: ignore


@router.post(
    "/{supplier_id}/evaluations",
    response_model=SupplierEvaluationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registra una evaluación de desempeño y recalcula la calificación del proveedor",
)
async def create_supplier_evaluation(
    supplier_id: uuid.UUID,
    payload: SupplierEvaluationCreate,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SUPPLIERS, ActionEnum.CREATE)),
    session: AsyncSession = Depends(get_db),
) -> SupplierEvaluationResponse:
    """Registra evaluación en puntualidad, calidad, precio y servicio."""
    return await procurement_service.create_evaluation(
        session=session,
        company_id=ctx.company_id,
        supplier_id=supplier_id,
        payload=payload,
        user_id=ctx.user.id,
        evaluator_name=ctx.user.full_name or "Auditor Compras",
    )  # type: ignore


# ===========================================================================
# 6. CRUD DE PROVEEDORES (DIRECTORIO Y DATOS DE CONTACTO)
# ===========================================================================

@router.post(
    "",
    response_model=SupplierResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registra un nuevo proveedor de mercancía",
)
async def create_supplier(
    payload: SupplierCreate,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SUPPLIERS, ActionEnum.CREATE)),
    session: AsyncSession = Depends(get_db),
) -> SupplierResponse:
    """Registra un nuevo proveedor con datos de contacto y condiciones comerciales."""
    if payload.company_id != ctx.company_id:
        raise PermissionDeniedException("No se puede registrar un proveedor para otra empresa.")

    return await procurement_service.create_supplier(session, ctx.company_id, payload, user_id=ctx.user.id)  # type: ignore


@router.get(
    "",
    response_model=Page[SupplierResponse],
    summary="Lista proveedores registrados con filtros",
)
async def list_suppliers(
    search: str | None = Query(None),
    is_active: bool | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SUPPLIERS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> Page[SupplierResponse]:
    """Lista proveedores de la empresa activa."""
    offset = (page - 1) * limit
    items, total = await procurement_service.list_suppliers(
        session=session,
        company_id=ctx.company_id,
        search=search,
        is_active=is_active,
        offset=offset,
        limit=limit,
    )
    return Page.create(items=items, total_items=total, params=PaginationParams(page=page, page_size=limit))  # type: ignore


@router.get(
    "/{supplier_id}",
    response_model=SupplierResponse,
    summary="Obtiene la información de un proveedor por ID",
)
async def get_supplier(
    supplier_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SUPPLIERS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
) -> SupplierResponse:
    """Obtiene un proveedor específico."""
    return await procurement_service.get_supplier(session, ctx.company_id, supplier_id)  # type: ignore


@router.put(
    "/{supplier_id}",
    response_model=SupplierResponse,
    summary="Actualiza los datos de un proveedor",
)
async def update_supplier(
    supplier_id: uuid.UUID,
    payload: SupplierUpdate,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SUPPLIERS, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
) -> SupplierResponse:
    """Actualiza la ficha del proveedor."""
    return await procurement_service.update_supplier(
        session, ctx.company_id, supplier_id, payload, user_id=ctx.user.id
    )  # type: ignore


@router.delete(
    "/{supplier_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Desactiva un proveedor",
)
async def delete_supplier(
    supplier_id: uuid.UUID,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SUPPLIERS, ActionEnum.DELETE)),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Desactiva un proveedor."""
    await procurement_service.delete_supplier(session, ctx.company_id, supplier_id)

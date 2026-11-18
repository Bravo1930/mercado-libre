"""
Rutas API REST v1 para el Centro de Información Tabular del ERP.
Gestión de 13 vistas de consulta central, filtros, ordenamiento dinámico,
búsqueda, paginación, edición autorizada, exportación a CSV/XLSX,
historial inmutable y sincronización con Google Sheets / Microsoft Excel.
"""

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_context import CompanyContext, require_company_permission
from src.core.database import get_db
from src.core.exceptions import ValidationException
from src.core.pagination import Page, PaginationParams
from src.core.permissions import ActionEnum, ModuleEnum
from src.schemas.tabular import (
    TabularEditHistoryResponse,
    TabularRowUpdateRequest,
    TabularRowUpdateResponse,
    TabularSyncConfigCreate,
    TabularSyncConfigResponse,
    TabularSyncExecuteRequest,
    TabularSyncResultResponse,
    TabularViewResponse,
    TabularViewType,
)
from src.services.tabular_service import TabularService

router = APIRouter(prefix="/tabular", tags=["Centro de Información Tabular"])
tabular_service = TabularService()


@router.get(
    "/views",
    summary="Listar las 13 vistas de información tabular del ERP",
)
async def list_available_tabular_views():
    """Retorna el catálogo de las 13 vistas disponibles y sus metadatos de columnas."""
    views_info = []
    view_names = [
        ("sales", "Ventas", "Registro consolidado de pedidos, pagos, comisiones y rentabilidad neta."),
        ("products", "Productos", "Catálogo unificado de variantes, SKUs, costos COGS y PVP."),
        ("inventory", "Inventario", "Existencias físicas, reservadas, bloqueadas y disponible."),
        ("movements", "Movimientos", "Kardex de entradas, salidas, transferencias y mermas."),
        ("costs", "Costos", "Historial inmutable de costos de adquisición y variaciones."),
        ("commissions", "Comisiones", "Desglose de retenciones, tarifas marketplace y cargos fijos."),
        ("profitability", "Rentabilidad", "Ingresos, deducciones logísticas, impuestos SAT y margen."),
        ("promotions", "Promociones", "Monitoreo de descuentos activos y precios de oferta."),
        ("shipments", "Envíos", "Seguimiento logístico, guías de rastreo y costos de flete."),
        ("purchases", "Compras", "Órdenes de compra a proveedores y estado de autorización."),
        ("suppliers", "Proveedores", "Directorio, condiciones de crédito y tiempos de entrega."),
        ("daily_summary", "Resumen diario", "Consolidado por fecha de ventas, costos y utilidades."),
        ("monthly_summary", "Resumen mensual", "Agregación contable mensual de facturación y márgenes."),
    ]
    for key, title, desc in view_names:
        cols = tabular_service.get_columns_for_view(key)  # type: ignore
        views_info.append(
            {
                "view_name": key,
                "title": title,
                "description": desc,
                "columns_count": len(cols),
                "columns": [c.model_dump() for c in cols],
            }
        )
    return {"views": views_info, "total_views": len(views_info)}


@router.get(
    "/history",
    response_model=Page[TabularEditHistoryResponse],
    summary="Consultar historial inmutable de modificaciones en planillas",
)
async def get_tabular_edit_history(
    view_name: TabularViewType | None = Query(None, description="Filtrar por vista"),
    row_id: str | None = Query(None, description="Filtrar por identificador de fila / SKU"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.AUDIT, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
):
    """Consulta la trazabilidad de celdas modificadas en las planillas internas o sincronizadas."""
    offset = (page - 1) * page_size
    items, total = await tabular_service.list_edit_history(
        session=session,
        company_id=ctx.company_id,
        view_name=view_name,
        row_id=row_id,
        offset=offset,
        limit=page_size,
    )
    return Page.create(
        items=[TabularEditHistoryResponse.model_validate(it) for it in items],
        total_items=total,
        params=PaginationParams(page=page, page_size=page_size),
    )


@router.get(
    "/sync-configs",
    response_model=list[TabularSyncConfigResponse],
    summary="Listar configuraciones de sincronización con Google Sheets / Excel",
)
async def list_tabular_sync_configs(
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SETTINGS, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
):
    """Consulta las sincronizaciones externas activas configuradas para la empresa."""
    configs = await tabular_service.list_sync_configs(session=session, company_id=ctx.company_id)
    return [TabularSyncConfigResponse.model_validate(c) for c in configs]


@router.post(
    "/sync-configs",
    response_model=TabularSyncConfigResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Configurar enlace con Google Sheets o Microsoft Excel",
)
async def configure_tabular_sync(
    payload: TabularSyncConfigCreate,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SETTINGS, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
):
    """
    Registra o actualiza la integración con una hoja de cálculo externa.
    Garantiza que la planilla externa no suplante la verdad del inventario interno.
    """
    config = await tabular_service.configure_sync(
        session=session, company_id=ctx.company_id, payload=payload
    )
    return TabularSyncConfigResponse.model_validate(config)


@router.post(
    "/{view_name}/sync/{provider}",
    response_model=TabularSyncResultResponse,
    summary="Ejecutar sincronización recuperable con Google Sheets o Excel",
)
async def trigger_sheet_sync(
    view_name: TabularViewType,
    provider: Literal["google_sheets", "microsoft_excel"],
    payload: TabularSyncExecuteRequest = TabularSyncExecuteRequest(),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.SETTINGS, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
):
    """
    Ejecuta la sincronización hacia/desde Google Sheets o Microsoft Excel.
    - Preserva identificadores únicos de fila para evitar duplicados.
    - Cumple la regla estricta: Las planillas externas no son la fuente principal de inventario.
    - Maneja y audita conflictos según la política configurada.
    """
    result = await tabular_service.execute_sheet_sync(
        session=session,
        company_id=ctx.company_id,
        view_name=view_name,
        provider=provider,
        direction=payload.direction,
        user_id=ctx.user.id,
        user_name=ctx.user.full_name or "Operador",
    )
    return result


@router.get(
    "/{view_name}/export/csv",
    summary="Exportar vista tabular a CSV compatible con Microsoft Excel (UTF-8 con BOM)",
)
async def export_tabular_csv(
    view_name: TabularViewType,
    search: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    status: str | None = Query(None),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.CATALOG, ActionEnum.EXPORT)),
    session: AsyncSession = Depends(get_db),
):
    """Genera y descarga un archivo CSV con encoding UTF-8 BOM para apertura perfecta de caracteres."""
    csv_bytes, filename = await tabular_service.export_to_csv(
        session=session,
        company_id=ctx.company_id,
        view_name=view_name,
        search=search,
        date_from=date_from,
        date_to=date_to,
        status=status,
    )
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/{view_name}/export/xlsx",
    summary="Exportar vista tabular a Microsoft Excel XLSX estilizado con openpyxl",
)
async def export_tabular_xlsx(
    view_name: TabularViewType,
    search: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    status: str | None = Query(None),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.CATALOG, ActionEnum.EXPORT)),
    session: AsyncSession = Depends(get_db),
):
    """Genera y descarga un libro nativo XLSX con estilos corporativos, autofit y formatos numéricos."""
    xlsx_bytes, filename = await tabular_service.export_to_xlsx(
        session=session,
        company_id=ctx.company_id,
        view_name=view_name,
        search=search,
        date_from=date_from,
        date_to=date_to,
        status=status,
    )
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.put(
    "/{view_name}/{row_id}",
    response_model=TabularRowUpdateResponse,
    summary="Edición autorizada de celdas en una fila de la planilla",
)
async def update_tabular_cell_or_row(
    view_name: TabularViewType,
    row_id: str,
    payload: TabularRowUpdateRequest,
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.CATALOG, ActionEnum.UPDATE)),
    session: AsyncSession = Depends(get_db),
):
    """
    Aplica modificaciones autorizadas en celdas de la fila identificada.
    Genera trazabilidad inmutable en TabularEditHistory y auditoría del sistema.
    """
    res = await tabular_service.update_tabular_row(
        session=session,
        company_id=ctx.company_id,
        view_name=view_name,
        row_id=row_id,
        updates=payload.updates,
        user_id=ctx.user.id,
        user_name=ctx.user.full_name or "Operador",
        change_reason=payload.change_reason,
        source="internal_grid",
    )
    return res


@router.get(
    "/{view_name}",
    response_model=TabularViewResponse,
    summary="Consultar datos tabulares con búsqueda, filtros, ordenamiento y paginación",
)
async def get_tabular_view_data(
    view_name: TabularViewType,
    search: str | None = Query(None, description="Búsqueda general por texto (SKU, nombre, folio, etc.)"),
    sort_by: str | None = Query(None, description="Clave de columna por la cual ordenar"),
    sort_order: Literal["asc", "desc"] = Query("desc", description="Dirección del ordenamiento"),
    date_from: datetime | None = Query(None, description="Fecha inicial de filtrado"),
    date_to: datetime | None = Query(None, description="Fecha final de filtrado"),
    status: str | None = Query(None, description="Filtro por estado de negocio"),
    warehouse_id: uuid.UUID | None = Query(None, description="Filtro opcional por almacén"),
    page: int = Query(1, ge=1, description="Número de página"),
    page_size: int = Query(25, ge=1, le=500, description="Filas por página"),
    ctx: CompanyContext = Depends(require_company_permission(ModuleEnum.CATALOG, ActionEnum.READ)),
    session: AsyncSession = Depends(get_db),
):
    """
    Consulta la planilla interna para cualquiera de las 13 vistas de negocio.
    La planilla interna es la fuente central de consulta del ERP.
    """
    offset = (page - 1) * page_size
    view_res = await tabular_service.get_tabular_view(
        session=session,
        company_id=ctx.company_id,
        view_name=view_name,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        date_from=date_from,
        date_to=date_to,
        status=status,
        warehouse_id=warehouse_id,
        offset=offset,
        limit=page_size,
    )
    return view_res

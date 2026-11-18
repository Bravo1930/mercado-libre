"""
Esquemas Pydantic v2 para el Centro de Información Tabular del ERP.
Soporte para 13 vistas de negocio, filtros avanzados, ordenamiento,
edición autorizada, exportación CSV/XLSX y sincronización con Google Sheets / Excel.
"""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

TabularViewType = Literal[
    "sales",
    "products",
    "inventory",
    "movements",
    "costs",
    "commissions",
    "profitability",
    "promotions",
    "shipments",
    "purchases",
    "suppliers",
    "daily_summary",
    "monthly_summary",
]

ProviderType = Literal["google_sheets", "microsoft_excel"]
SyncDirectionType = Literal["push_to_sheet", "bidirectional"]
ConflictResolutionType = Literal["server_wins", "external_wins", "manual_review"]


class TabularColumnDef(BaseModel):
    """Metadatos de cada columna de la planilla para renderizado e inspección."""

    key: str = Field(..., description="Clave única de la columna en el registro JSON")
    label: str = Field(..., description="Encabezado visible en la planilla")
    data_type: Literal["string", "number", "currency", "date", "datetime", "boolean", "badge"] = "string"
    sortable: bool = True
    filterable: bool = True
    editable: bool = False
    width: int | None = Field(None, description="Ancho recomendado en píxeles o caracteres")
    description: str | None = None


class TabularViewResponse(BaseModel):
    """Respuesta paginada y estructurada para una vista tabular del ERP."""

    view_name: TabularViewType
    view_title: str
    description: str
    columns: list[TabularColumnDef]
    items: list[dict[str, Any]]
    total_items: int = Field(..., description="Total de filas que coinciden con los filtros")
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1)
    total_pages: int
    has_next: bool
    has_prev: bool
    last_synced_at: datetime
    server_timestamp: datetime
    sync_config: dict[str, Any] | None = None


class TabularRowUpdateRequest(BaseModel):
    """Solicitud de modificación autorizada de una o varias celdas de una fila."""

    updates: dict[str, Any] = Field(..., min_length=1, description="Pares campo:nuevo_valor permitidos")
    change_reason: str | None = Field(None, max_length=255, description="Motivo obligatorio o auditoría")


class TabularRowUpdateResponse(BaseModel):
    """Resultado de la edición autorizada de una fila."""

    success: bool
    view_name: str
    row_id: str
    updated_fields: dict[str, Any]
    previous_values: dict[str, Any]
    message: str
    updated_at: datetime


class TabularEditHistoryResponse(BaseModel):
    """Registro inmutable de trazabilidad de cambios en celdas de la planilla."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    view_name: str
    row_id: str
    column_name: str
    previous_value: str | None = None
    new_value: str | None = None
    change_reason: str | None = None
    source: str
    status: str
    conflict_details: str | None = None
    user_name: str
    created_at: datetime


class TabularSyncConfigCreate(BaseModel):
    """Configuración de sincronización con hoja externa (Google Sheets o Microsoft Excel)."""

    view_name: TabularViewType
    provider: ProviderType
    spreadsheet_id: str = Field(..., min_length=3, max_length=255, description="ID de hoja o archivo en la nube")
    sheet_name: str = Field("Datos_ERP", min_length=1, max_length=100)
    sync_direction: SyncDirectionType = "push_to_sheet"
    conflict_resolution: ConflictResolutionType = "server_wins"
    auto_sync_interval_minutes: int = Field(0, ge=0, le=1440, description="0 = sólo manual")
    oauth_credentials: str | None = Field(None, description="Tokens JSON o credenciales OAuth oficiales")
    external_url: str | None = Field(None, description="Enlace web directo a la hoja para visualización")


class TabularSyncConfigUpdate(BaseModel):
    """Actualización de parámetros de sincronización."""

    sheet_name: str | None = None
    sync_direction: SyncDirectionType | None = None
    conflict_resolution: ConflictResolutionType | None = None
    auto_sync_interval_minutes: int | None = None
    is_active: bool | None = None
    oauth_credentials: str | None = None
    external_url: str | None = None


class TabularSyncConfigResponse(BaseModel):
    """Respuesta con la configuración activa de sincronización."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    view_name: str
    provider: str
    spreadsheet_id: str
    sheet_name: str
    sync_direction: str
    conflict_resolution: str
    auto_sync_interval_minutes: int
    is_active: bool
    last_synced_at: datetime | None = None
    last_sync_status: str
    last_sync_error: str | None = None
    external_url: str | None = None
    total_rows_synced: int
    created_at: datetime


class TabularSyncExecuteRequest(BaseModel):
    """Parámetros de ejecución manual de sincronización."""

    direction: Literal["push", "pull", "bidirectional"] = "push"
    force_override: bool = False
    notes: str | None = None


class TabularSyncResultResponse(BaseModel):
    """Resultado detallado de la sincronización con planillas externas."""

    success: bool
    message: str
    provider: str
    view_name: str
    sync_direction: str
    synced_rows_count: int
    conflicts_detected: int
    conflicts_resolved: int
    primary_source_rule_applied: str = (
        "Regla verificada: La planilla interna es la fuente central de verdad; el inventario externo es informativo."
    )
    external_sheet_url: str | None = None
    sync_timestamp: datetime

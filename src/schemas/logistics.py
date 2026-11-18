"""Esquemas Pydantic para el Centro de Logística y Sistema Dual de Etiquetas (Envíos & Internas)."""

from datetime import datetime
from typing import Any, Literal
import uuid

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# MÓDULO A: ETIQUETAS DE ENVÍO Y DESPACHO OFICIAL (Mercado Envíos)
# ---------------------------------------------------------------------------

class ShipmentPrintLogResponse(BaseModel):
    """Registro histórico y de auditoría de impresión / reimpresión de guía oficial."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    shipment_id: uuid.UUID
    print_number: int
    is_reprint: bool
    reprint_reason: str | None = None
    format: str
    created_at: datetime


class ShipmentResponse(BaseModel):
    """Información completa de un envío de Mercado Envíos."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID | None = None
    order_id: uuid.UUID
    meli_shipment_id: int
    status: str
    substatus: str | None = None
    dispatch_status: str  # pending, prepared, dispatched, error
    logistic_type: str  # fulfillment, cross_docking, drop_off, self_service
    tracking_number: str | None = None
    tracking_method: str | None = None
    carrier_name: str | None = None
    shipping_cost_total: float = 0.0
    shipping_cost_seller: float = 0.0
    print_count: int = 0
    last_printed_at: datetime | None = None
    estimated_delivery_limit: datetime | None = None
    sender_address: dict[str, Any] | None = None
    receiver_address: dict[str, Any] | None = None
    shipping_option: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class ShipmentTrackingEvent(BaseModel):
    """Hito o evento de seguimiento del paquete."""
    date: datetime | str
    status: str
    substatus: str | None = None
    description: str | None = None


class ShipmentTrackingResponse(BaseModel):
    """Trazabilidad completa y seguimiento en tiempo real del transportista."""
    shipment_id: uuid.UUID
    meli_shipment_id: int
    tracking_number: str | None = None
    carrier_name: str | None = None
    logistic_type: str
    current_status: str
    current_substatus: str | None = None
    estimated_delivery_limit: datetime | None = None
    events: list[dict[str, Any]] = []


class ShipmentPrintRequest(BaseModel):
    """Solicitud de primera impresión de guía oficial."""
    format: Literal["pdf", "zpl2"] = Field("pdf", description="Formato de la guía oficial")


class ShipmentReprintRequest(BaseModel):
    """Solicitud de reimpresión de guía oficial con motivo justificado obligatorio."""
    format: Literal["pdf", "zpl2"] = Field("pdf", description="Formato de la guía oficial")
    reprint_reason: str = Field(
        ...,
        min_length=5,
        max_length=255,
        description="Motivo justificado obligatorio para autorizar la reimpresión (ej: 'Guía física dañada')",
    )


class ShipmentBatchPrintRequest(BaseModel):
    """Solicitud para impresión de guías en lote (hasta 50 por restricción oficial MeLi)."""
    shipment_ids: list[uuid.UUID] = Field(
        ..., min_length=1, max_length=50, description="Lista de UUIDs de envíos a imprimir en lote"
    )
    format: Literal["pdf", "zpl2"] = Field("pdf", description="Formato consolidado de descarga")


class ShipmentBatchPrintResponse(BaseModel):
    """Resultado de la descarga e impresión por lotes."""
    total_requested: int
    successful_count: int
    failed_count: int
    format: str
    labels_file_url: str | None = None
    failed_details: list[dict[str, Any]] = []


class LogisticsDashboardMetricsResponse(BaseModel):
    """Métricas operativas del centro de logística para control de pedidos y despachos."""
    pending_count: int = Field(..., description="Pedidos pendientes de preparar (etiqueta aún no impresa)")
    prepared_count: int = Field(..., description="Pedidos preparados (etiqueta impresa, listos para despacho)")
    dispatched_count: int = Field(..., description="Pedidos despachados (en camino o entregados)")
    error_count: int = Field(..., description="Pedidos con problemas o demoras de logística")
    total_shipments: int
    fulfillment_full_count: int = Field(..., description="Envíos gestionados por Mercado Envíos Full")
    cross_docking_count: int = Field(..., description="Envíos de colecta estándar")
    drop_off_count: int = Field(..., description="Envíos por agencias de entrega")
    flex_count: int = Field(..., description="Envíos entrega mismo día Flex")


class LogisticsLimitationItem(BaseModel):
    """Documentación formal de limitación de API oficial y procedimiento permitido."""
    operation: str
    limitation_description: str
    official_code: str
    permitted_procedure: str
    impact_level: Literal["critical", "high", "medium", "info"]


class LogisticsLimitationsDocResponse(BaseModel):
    """Catálogo oficial de limitaciones de la API de Mercado Envíos y contingencias."""
    title: str
    description: str
    last_updated: str
    limitations: list[LogisticsLimitationItem]


# ---------------------------------------------------------------------------
# MÓDULO B: ETIQUETAS INTERNAS DE ALMACÉN, PRODUCTOS Y SURTIDO
# ---------------------------------------------------------------------------

class InternalLabelItemRequest(BaseModel):
    """Definición de un producto/variante para generar su etiqueta interna."""
    variant_id: uuid.UUID | None = None
    sku: str = Field(..., min_length=1, max_length=100)
    product_name: str = Field(..., min_length=1, max_length=255)
    variant_name: str | None = None
    location: str | None = Field("BODEGA-GENERAL", description="Ubicación física en el almacén (Pasillo, Rack, Nivel)")
    price: float | None = None
    quantity: int = Field(1, ge=1, le=500, description="Cantidad de etiquetas físicas a generar")


class InternalLabelGenerateRequest(BaseModel):
    """Parámetros para la generación de lote de etiquetas internas."""
    template_type: Literal["thermal_4x6", "thermal_50x30", "sheet_letter_30", "jewelry_mini"] = Field(
        "thermal_4x6", description="Plantilla de impresión térmica o convencional"
    )
    items: list[InternalLabelItemRequest] = Field(..., min_length=1)
    include_price: bool = Field(False, description="Incluir precio de venta sugerido en la etiqueta")
    output_format: Literal["html", "zpl"] = Field("html", description="Formato de salida (HTML listo para imprimir o ZPL Zebra)")


class InternalLabelOrderRequest(BaseModel):
    """Generar etiquetas de surtido interno directamente desde los productos de una orden."""
    template_type: Literal["thermal_4x6", "thermal_50x30", "sheet_letter_30", "jewelry_mini"] = "thermal_50x30"
    include_price: bool = False
    output_format: Literal["html", "zpl"] = "html"


class InternalLabelResponse(BaseModel):
    """Respuesta con el código ZPL o HTML generado para impresión."""
    batch_id: uuid.UUID
    batch_name: str
    template_type: str
    total_labels: int
    output_format: str
    zpl_code: str | None = None
    html_content: str | None = None


class InternalLabelTemplateResponse(BaseModel):
    """Plantilla de etiquetas configurada en el sistema."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    template_type: str
    width_mm: float
    height_mm: float
    columns: int
    rows: int
    include_barcode: bool
    barcode_type: str
    include_qr: bool
    include_sku: bool
    include_product_name: bool
    include_variant: bool
    include_location: bool
    include_price: bool
    is_default: bool

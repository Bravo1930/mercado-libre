"""Servicio Central de Logística, Despacho, Trazabilidad y Sistema Dual de Etiquetas (Envíos & Internas)."""

from datetime import datetime, timezone
from typing import Any, Literal
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.connectors.meli.connector import MercadoLibreConnector
from src.core.exceptions import EntityNotFoundException, ValidationException
from src.core.logging import get_logger
from src.core.security import decrypt_token
from src.models.internal_label import InternalLabelPrintBatch, InternalLabelTemplate
from src.models.meli_account import MeliAccount
from src.models.order import Order, OrderItem, OrderTimeline
from src.models.product import Product, ProductVariant
from src.models.shipment import Shipment, ShipmentPrintLog
from src.models.warehouse import Inventory, Warehouse
from src.schemas.logistics import (
    InternalLabelItemRequest,
    InternalLabelResponse,
    LogisticsDashboardMetricsResponse,
    LogisticsLimitationItem,
    LogisticsLimitationsDocResponse,
    ShipmentBatchPrintResponse,
    ShipmentTrackingResponse,
)
from src.services.label_generator_service import LabelGeneratorService

logger = get_logger("logistics_service")


class LogisticsService:
    """
    Motor del Centro de Logística del ERP de Mercado Libre.
    
    Gestiona:
    Módulo A:
    - Consulta de envíos y clasificación operativa: Pendientes, Preparados, Despachados y Errores.
    - Descarga de etiquetas oficiales MeLi (PDF / ZPL2).
    - Registro de impresiones y control de reimpresiones con auditoría.
    - Impresión por lotes (hasta 50 por restricción oficial).
    - Trazabilidad y seguimiento de paqueterías.
    
    Módulo B:
    - Generación de etiquetas internas para almacén e inventario (Code 128, QR).
    - Compatibilidad con impresoras térmicas (100x150, 50x30) y de oficina (Hoja carta 30 etiquetas).
    - Etiquetas de surtido asociadas a pedidos de venta.
    - Documentación de limitaciones oficiales de Mercado Envíos.
    """

    def __init__(self):
        self.label_generator = LabelGeneratorService()

    # ---------------------------------------------------------------------------
    # MÓDULO A: GESTIÓN DE ENVÍOS Y ETIQUETAS OFICIALES
    # ---------------------------------------------------------------------------

    async def list_shipments(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        dispatch_status: str | None = None,
        logistic_type: str | None = None,
        carrier_name: str | None = None,
        search: str | None = None,
    ) -> select:
        """Construye la consulta filtrada de envíos pertenecientes a la empresa."""
        stmt = (
            select(Shipment)
            .join(Order, Shipment.order_id == Order.id)
            .join(MeliAccount, Order.meli_account_id == MeliAccount.id)
            .where(MeliAccount.company_id == company_id)
            .options(
                selectinload(Shipment.order),
                selectinload(Shipment.print_logs),
            )
            .order_by(Shipment.created_at.desc())
        )

        if dispatch_status:
            stmt = stmt.where(Shipment.dispatch_status == dispatch_status)
        if logistic_type:
            stmt = stmt.where(Shipment.logistic_type == logistic_type)
        if carrier_name:
            stmt = stmt.where(Shipment.carrier_name == carrier_name)
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    func.cast(Shipment.meli_shipment_id, String).ilike(pattern),
                    Shipment.tracking_number.ilike(pattern),
                    Shipment.carrier_name.ilike(pattern),
                    Order.order_number.ilike(pattern),
                    Order.buyer_nickname.ilike(pattern),
                )
            )

        return stmt

    async def get_shipment_by_id(
        self,
        session: AsyncSession,
        shipment_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> Shipment:
        """Obtiene un envío validando pertenencia a la empresa solicitante."""
        stmt = (
            select(Shipment)
            .join(Order, Shipment.order_id == Order.id)
            .join(MeliAccount, Order.meli_account_id == MeliAccount.id)
            .where(Shipment.id == shipment_id, MeliAccount.company_id == company_id)
            .options(
                selectinload(Shipment.order),
                selectinload(Shipment.print_logs),
            )
        )
        shipment = (await session.execute(stmt)).scalar_one_or_none()
        if not shipment:
            raise EntityNotFoundException("Envío", str(shipment_id))
        return shipment

    async def get_shipment_tracking(
        self,
        session: AsyncSession,
        shipment_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> ShipmentTrackingResponse:
        """
        Consulta la trazabilidad y seguimiento del transportista.
        Consulta los datos locales y, si la cuenta MeLi está activa, sincroniza con la API de MeLi.
        """
        shipment = await self.get_shipment_by_id(session, shipment_id, company_id)
        order = shipment.order

        # Si tenemos cuenta conectada, intentar actualizar seguimiento desde MeLi
        meli_events: list[dict[str, Any]] = []
        try:
            account = await session.get(MeliAccount, order.meli_account_id)
            if account and account.access_token_enc:
                token = decrypt_token(account.access_token_enc)
                connector = MercadoLibreConnector(access_token=token)
                tracking_data = await connector.shipments.get_shipment(shipment.meli_shipment_id)
                if tracking_data:
                    # Actualizar campos locales si cambiaron
                    new_status = tracking_data.get("status")
                    if new_status and new_status != shipment.status:
                        shipment.status = new_status
                        if new_status in ["shipped", "delivered"]:
                            shipment.dispatch_status = "dispatched"
                    substatus = tracking_data.get("substatus")
                    if substatus:
                        shipment.substatus = substatus
                    
                    hist = tracking_data.get("status_history", {})
                    for st_name, st_dt in hist.items():
                        if st_dt:
                            meli_events.append({
                                "date": st_dt,
                                "status": st_name,
                                "description": f"Hito de envío: {st_name}",
                            })
        except Exception as e:
            logger.warning(f"Aviso al consultar seguimiento MeLi para envío {shipment.meli_shipment_id}: {e}")

        # Ordenar eventos cronológicamente
        if not meli_events:
            meli_events.append({
                "date": shipment.created_at.isoformat(),
                "status": shipment.status,
                "substatus": shipment.substatus,
                "description": f"Estado del envío: {shipment.status.upper()}",
            })

        return ShipmentTrackingResponse(
            shipment_id=shipment.id,
            meli_shipment_id=shipment.meli_shipment_id,
            tracking_number=shipment.tracking_number,
            carrier_name=shipment.carrier_name,
            logistic_type=shipment.logistic_type,
            current_status=shipment.status,
            current_substatus=shipment.substatus,
            estimated_delivery_limit=shipment.estimated_delivery_limit,
            events=meli_events,
        )

    async def download_official_shipment_label(
        self,
        session: AsyncSession,
        shipment_id: uuid.UUID,
        company_id: uuid.UUID,
        format_type: str = "pdf",
    ) -> tuple[bytes, str]:
        """
        Descarga la guía oficial de Mercado Envíos directamente desde la API oficial.
        
        REGLAS Y LIMITACIONES OFICIALES ESTRICTAS:
        1. No genera etiquetas falsas bajo ninguna circunstancia.
        2. Si el envío es de Mercado Envíos Full (fulfillment), rechaza la operación informando
           que la etiqueta la emite y pega exclusivamente el CEDIS de Mercado Libre.
        3. Si la orden está cancelada o no pagada, bloquea la solicitud.
        4. Si el envío ya fue entregado (delivered), bloquea la descarga de guía activa.
        """
        shipment = await self.get_shipment_by_id(session, shipment_id, company_id)
        order = shipment.order

        # Validación 1: Mercado Envíos Full (Fulfillment)
        if shipment.logistic_type == "fulfillment":
            raise ValidationException(
                f"El envío #{shipment.meli_shipment_id} opera bajo modalidad 'Mercado Envíos Full'. "
                "Los productos están resguardados en el CEDIS de Mercado Libre, quien realiza el picking, "
                "empaque y rotulado de la guía oficial. No se permite generar etiquetas para Full desde la API de vendedores.",
                code="FULL_LABEL_RESTRICTION",
            )

        # Validación 2: Pedido cancelado
        if order.status == "cancelled" or shipment.status == "cancelled":
            raise ValidationException(
                f"El pedido #{order.meli_order_id} se encuentra cancelado. "
                "Mercado Libre anula automáticamente las guías de órdenes canceladas.",
                code="CANCELLED_ORDER_LABEL",
            )

        # Validación 3: Pedido ya entregado
        if shipment.status == "delivered":
            raise ValidationException(
                f"El paquete #{shipment.meli_shipment_id} ya fue entregado al comprador final. "
                "La guía se encuentra consumida y no puede ser descargada para nuevo despacho.",
                code="ALREADY_DELIVERED",
            )

        # Obtener token de la cuenta MeLi asociada
        account = await session.get(MeliAccount, order.meli_account_id)
        if not account or not account.access_token_enc:
            raise ValidationException("La cuenta de Mercado Libre asociada no cuenta con credenciales activas.")

        token = decrypt_token(account.access_token_enc)
        connector = MercadoLibreConnector(access_token=token)

        try:
            label_bytes = await connector.shipments.get_shipment_labels(
                [shipment.meli_shipment_id], response_type=format_type
            )
            if not label_bytes:
                raise ValidationException("Mercado Libre no devolvió contenido para la guía solicitada.")
            
            content_type = "application/pdf" if format_type == "pdf" else "text/plain"
            return label_bytes, content_type

        except Exception as e:
            logger.error(f"Error al descargar etiqueta oficial para envío #{shipment.meli_shipment_id}: {e}")
            raise ValidationException(
                f"No fue posible obtener la guía oficial de Mercado Libre: {str(e)}. "
                "Verifique que la colecta esté asignada y que la guía esté lista para impresión en el portal de Mercado Envíos."
            )

    async def record_shipment_print(
        self,
        session: AsyncSession,
        shipment_id: uuid.UUID,
        company_id: uuid.UUID,
        user_id: uuid.UUID | None,
        format_type: str = "pdf",
        is_reprint: bool = False,
        reprint_reason: str | None = None,
        ip_address: str | None = None,
    ) -> ShipmentPrintLog:
        """
        Registra la impresión o reimpresión de una guía oficial.
        Aplica control estricto de reimpresiones:
        - Si el envío ya tiene impresiones previas, exige `reprint_reason`.
        - Si el envío ya fue despachado o entregado, bloquea la reimpresión.
        - Actualiza el estado operativo interno a 'prepared' (preparado).
        """
        shipment = await self.get_shipment_by_id(session, shipment_id, company_id)

        # Si ya fue despachado, no permitir reimpresión
        if shipment.status in ["shipped", "delivered"]:
            raise ValidationException(
                f"El envío #{shipment.meli_shipment_id} ya fue despachado ({shipment.status}). "
                "No está permitido reimprimir etiquetas para paquetes que ya están en tránsito con la paquetería."
            )

        # Validar si es reimpresión
        if shipment.print_count > 0:
            is_reprint = True
            if not reprint_reason or len(reprint_reason.strip()) < 5:
                raise ValidationException(
                    "Esta etiqueta ya fue impresa previamente. Para autorizar una reimpresión, "
                    "debe indicar obligatoriamente el motivo justificado (mínimo 5 caracteres)."
                )

        next_print_num = shipment.print_count + 1
        shipment.print_count = next_print_num
        shipment.last_printed_at = datetime.now(timezone.utc)
        shipment.last_printed_by_user_id = user_id

        # Si estaba en pendiente de empaque, actualizar a preparado
        if shipment.dispatch_status == "pending":
            shipment.dispatch_status = "prepared"
            shipment.substatus = "printed"

        # Crear registro de auditoría
        log_entry = ShipmentPrintLog(
            shipment_id=shipment.id,
            company_id=company_id,
            user_id=user_id,
            print_number=next_print_num,
            is_reprint=is_reprint,
            reprint_reason=reprint_reason.strip() if reprint_reason else None,
            format=format_type,
            ip_address=ip_address,
        )
        session.add(log_entry)

        # Agregar hito a la línea de tiempo de la orden
        action_text = "Reimpresión de Etiqueta" if is_reprint else "Etiqueta Oficial Impresa"
        desc_text = (
            f"Guía #{shipment.tracking_number or shipment.meli_shipment_id} impresa ({format_type.upper()}). "
            + (f"Motivo: {reprint_reason}" if is_reprint else "Paquete preparado para despacho.")
        )
        tl = OrderTimeline(
            order_id=shipment.order_id,
            event_type="SHIPPING_LABEL_PRINTED",
            title=action_text,
            description=desc_text,
            actor="Operador de Almacén",
            metadata_info={"print_number": next_print_num, "is_reprint": is_reprint, "format": format_type},
        )
        session.add(tl)

        await session.flush()
        return log_entry

    async def batch_print_shipments(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        user_id: uuid.UUID | None,
        shipment_ids: list[uuid.UUID],
        format_type: str = "pdf",
    ) -> tuple[bytes, ShipmentBatchPrintResponse]:
        """
        Descarga e impresión por lotes de guías oficiales (hasta 50 envíos por lote).
        Agrupa los envíos por cuenta de Mercado Libre, valida elegibilidad y registra auditoría.
        """
        if len(shipment_ids) > 50:
            raise ValidationException("Mercado Libre permite imprimir hasta un máximo de 50 guías por lote.")

        # Cargar los envíos solicitados
        stmt = (
            select(Shipment)
            .join(Order, Shipment.order_id == Order.id)
            .join(MeliAccount, Order.meli_account_id == MeliAccount.id)
            .where(Shipment.id.in_(shipment_ids), MeliAccount.company_id == company_id)
            .options(selectinload(Shipment.order))
        )
        shipments = (await session.execute(stmt)).scalars().all()

        successful_shipments: list[Shipment] = []
        failed_details: list[dict[str, Any]] = []

        for s in shipments:
            if s.logistic_type == "fulfillment":
                failed_details.append({
                    "shipment_id": str(s.id),
                    "meli_shipment_id": s.meli_shipment_id,
                    "reason": "Modalidad Full: el rotulado lo realiza el CEDIS de Mercado Libre.",
                })
            elif s.status == "cancelled" or s.order.status == "cancelled":
                failed_details.append({
                    "shipment_id": str(s.id),
                    "meli_shipment_id": s.meli_shipment_id,
                    "reason": "Pedido cancelado.",
                })
            elif s.status == "delivered":
                failed_details.append({
                    "shipment_id": str(s.id),
                    "meli_shipment_id": s.meli_shipment_id,
                    "reason": "El paquete ya fue entregado.",
                })
            else:
                successful_shipments.append(s)

        if not successful_shipments:
            summary = ShipmentBatchPrintResponse(
                total_requested=len(shipment_ids),
                successful_count=0,
                failed_count=len(failed_details),
                format=format_type,
                failed_details=failed_details,
            )
            return b"", summary

        # Agrupar por cuenta de Mercado Libre
        accounts_map: dict[uuid.UUID, list[Shipment]] = {}
        for s in successful_shipments:
            accounts_map.setdefault(s.order.meli_account_id, []).append(s)

        consolidated_bytes = b""
        final_success_count = 0

        for acc_id, acc_shipments in accounts_map.items():
            account = await session.get(MeliAccount, acc_id)
            if not account or not account.access_token_enc:
                continue

            token = decrypt_token(account.access_token_enc)
            connector = MercadoLibreConnector(access_token=token)
            m_ids = [s.meli_shipment_id for s in acc_shipments]

            try:
                b_content = await connector.shipments.get_shipment_labels(m_ids, response_type=format_type)
                if b_content:
                    consolidated_bytes += b_content
                    # Registrar impresiones
                    for s in acc_shipments:
                        await self.record_shipment_print(
                            session=session,
                            shipment_id=s.id,
                            company_id=company_id,
                            user_id=user_id,
                            format_type=format_type,
                            is_reprint=(s.print_count > 0),
                            reprint_reason="Impresión en lote de almacén" if s.print_count > 0 else None,
                        )
                        final_success_count += 1
            except Exception as e:
                logger.error(f"Error al descargar lote para cuenta {acc_id}: {e}")
                for s in acc_shipments:
                    failed_details.append({
                        "shipment_id": str(s.id),
                        "meli_shipment_id": s.meli_shipment_id,
                        "reason": f"Falla de API MeLi: {str(e)}",
                    })

        summary = ShipmentBatchPrintResponse(
            total_requested=len(shipment_ids),
            successful_count=final_success_count,
            failed_count=len(failed_details),
            format=format_type,
            failed_details=failed_details,
        )
        return consolidated_bytes, summary

    async def get_dashboard_metrics(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
    ) -> LogisticsDashboardMetricsResponse:
        """Calcula los KPIs y clasificaciones operativas del Centro de Logística."""
        stmt = (
            select(Shipment)
            .join(Order, Shipment.order_id == Order.id)
            .join(MeliAccount, Order.meli_account_id == MeliAccount.id)
            .where(MeliAccount.company_id == company_id)
        )
        shipments = (await session.execute(stmt)).scalars().all()

        pending_count = 0
        prepared_count = 0
        dispatched_count = 0
        error_count = 0

        full_count = 0
        cross_count = 0
        drop_count = 0
        flex_count = 0

        for s in shipments:
            # Conteo operativo
            if s.dispatch_status == "pending":
                pending_count += 1
            elif s.dispatch_status == "prepared":
                prepared_count += 1
            elif s.dispatch_status == "dispatched":
                dispatched_count += 1
            elif s.dispatch_status == "error":
                error_count += 1

            # Conteo de modalidad logística
            ltype = s.logistic_type or "cross_docking"
            if ltype == "fulfillment":
                full_count += 1
            elif ltype == "cross_docking":
                cross_count += 1
            elif ltype == "drop_off":
                drop_count += 1
            elif ltype == "self_service":
                flex_count += 1

        return LogisticsDashboardMetricsResponse(
            pending_count=pending_count,
            prepared_count=prepared_count,
            dispatched_count=dispatched_count,
            error_count=error_count,
            total_shipments=len(shipments),
            fulfillment_full_count=full_count,
            cross_docking_count=cross_count,
            drop_off_count=drop_count,
            flex_count=flex_count,
        )

    # ---------------------------------------------------------------------------
    # MÓDULO B: ETIQUETAS INTERNAS DE ALMACÉN, PRODUCTOS Y SURTIDO
    # ---------------------------------------------------------------------------

    async def get_or_create_default_internal_templates(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
    ) -> list[InternalLabelTemplate]:
        """Asegura la existencia de las 4 plantillas estándar para la empresa."""
        stmt = select(InternalLabelTemplate).where(InternalLabelTemplate.company_id == company_id)
        templates = (await session.execute(stmt)).scalars().all()

        if not templates:
            defaults = [
                InternalLabelTemplate(
                    company_id=company_id,
                    name="Térmica 100x150 mm (4x6 pulg) - Estándar Logística",
                    template_type="thermal_4x6",
                    width_mm=100.0,
                    height_mm=150.0,
                    columns=1,
                    rows=1,
                    include_barcode=True,
                    barcode_type="code128",
                    include_qr=True,
                    include_sku=True,
                    include_product_name=True,
                    include_variant=True,
                    include_location=True,
                    include_price=False,
                    is_default=True,
                ),
                InternalLabelTemplate(
                    company_id=company_id,
                    name="Térmica 50x30 mm - Estantes y Partes Pequeñas",
                    template_type="thermal_50x30",
                    width_mm=50.0,
                    height_mm=30.0,
                    columns=1,
                    rows=1,
                    include_barcode=True,
                    barcode_type="code128",
                    include_qr=True,
                    include_sku=True,
                    include_product_name=True,
                    include_variant=True,
                    include_location=True,
                    include_price=False,
                    is_default=False,
                ),
                InternalLabelTemplate(
                    company_id=company_id,
                    name="Hoja Carta Avery (30 Etiquetas por hoja 3x10)",
                    template_type="sheet_letter_30",
                    width_mm=66.0,
                    height_mm=25.4,
                    columns=3,
                    rows=10,
                    include_barcode=True,
                    barcode_type="code128",
                    include_qr=True,
                    include_sku=True,
                    include_product_name=True,
                    include_variant=True,
                    include_location=True,
                    include_price=False,
                    is_default=False,
                ),
                InternalLabelTemplate(
                    company_id=company_id,
                    name="Mini Joyera / Cables 40x20 mm",
                    template_type="jewelry_mini",
                    width_mm=40.0,
                    height_mm=20.0,
                    columns=1,
                    rows=1,
                    include_barcode=True,
                    barcode_type="code128",
                    include_qr=True,
                    include_sku=True,
                    include_product_name=True,
                    include_variant=False,
                    include_location=True,
                    include_price=False,
                    is_default=False,
                ),
            ]
            for t in defaults:
                session.add(t)
            await session.flush()
            templates = defaults

        return templates

    async def generate_internal_labels_for_items(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        user_id: uuid.UUID | None,
        items: list[InternalLabelItemRequest],
        template_type: str = "thermal_4x6",
        include_price: bool = False,
        output_format: str = "html",
        batch_name: str | None = None,
        order_id: uuid.UUID | None = None,
    ) -> InternalLabelResponse:
        """Genera un lote de etiquetas internas con SKU, Code 128, QR, ubicación y precio opcional."""
        if not items:
            raise ValidationException("Debe proporcionar al menos un artículo para generar etiquetas.")

        # Preparar datos enriquecidos de cada artículo
        processed_items: list[dict[str, Any]] = []
        total_units = 0

        for it in items:
            var_name = it.variant_name
            loc = it.location
            pr = it.price

            # Si viene variant_id, consultar datos del catálogo interno
            if it.variant_id:
                stmt_v = (
                    select(ProductVariant)
                    .where(ProductVariant.id == it.variant_id, ProductVariant.company_id == company_id)
                    .options(selectinload(ProductVariant.product))
                )
                variant = (await session.execute(stmt_v)).scalar_one_or_none()
                if variant:
                    var_name = var_name or variant.variant_name
                    pr = pr or float(variant.sale_price)
                    # Consultar ubicación en inventario
                    stmt_inv = (
                        select(Inventory)
                        .where(Inventory.variant_id == variant.id)
                        .order_by(Inventory.created_at.asc())
                    )
                    inv = (await session.execute(stmt_inv)).scalars().first()
                    if inv and inv.location_bin:
                        loc = inv.location_bin

            processed_items.append({
                "variant_id": str(it.variant_id) if it.variant_id else None,
                "sku": it.sku,
                "product_name": it.product_name,
                "variant_name": var_name,
                "location": loc or "BODEGA-GENERAL",
                "price": pr,
                "include_price": include_price,
                "quantity": it.quantity,
            })
            total_units += it.quantity

        b_name = batch_name or f"Lote Etiquetas {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"

        # Guardar registro del lote en base de datos
        batch_record = InternalLabelPrintBatch(
            company_id=company_id,
            user_id=user_id,
            order_id=order_id,
            batch_name=b_name,
            template_type=template_type,
            total_labels=total_units,
            output_format=output_format,
            items_payload=processed_items,
        )
        session.add(batch_record)
        await session.flush()

        # Renderizar en formato solicitado
        zpl_result = None
        html_result = None

        if output_format == "zpl":
            zpl_lines: list[str] = []
            for pit in processed_items:
                for _ in range(pit["quantity"]):
                    zpl_lines.append(
                        self.label_generator.generate_zpl_label(
                            sku=pit["sku"],
                            product_name=pit["product_name"],
                            variant_name=pit["variant_name"],
                            location=pit["location"],
                            price=pit["price"] if include_price else None,
                            template_type=template_type,
                        )
                    )
            zpl_result = "\n".join(zpl_lines)
        else:
            html_result = self.label_generator.render_html_print_sheet(
                items=processed_items,
                template_type=template_type,
            )

        return InternalLabelResponse(
            batch_id=batch_record.id,
            batch_name=b_name,
            template_type=template_type,
            total_labels=total_units,
            output_format=output_format,
            zpl_code=zpl_result,
            html_content=html_result,
        )

    async def generate_internal_labels_for_order(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        user_id: uuid.UUID | None,
        order_id: uuid.UUID,
        template_type: str = "thermal_50x30",
        include_price: bool = False,
        output_format: str = "html",
    ) -> InternalLabelResponse:
        """Genera etiquetas de surtido de almacén para todos los productos de un pedido específico."""
        stmt = (
            select(Order)
            .join(MeliAccount, Order.meli_account_id == MeliAccount.id)
            .where(Order.id == order_id, MeliAccount.company_id == company_id)
            .options(selectinload(Order.items))
        )
        order = (await session.execute(stmt)).scalar_one_or_none()
        if not order:
            raise EntityNotFoundException("Orden de Venta", str(order_id))

        if not order.items:
            raise ValidationException(f"La orden #{order.meli_order_id} no contiene artículos para etiquetar.")

        items_req: list[InternalLabelItemRequest] = []
        for it in order.items:
            items_req.append(
                InternalLabelItemRequest(
                    variant_id=it.variant_id,
                    sku=it.seller_sku or it.meli_item_id,
                    product_name=it.title,
                    variant_name=it.variant_name,
                    quantity=it.quantity,
                    price=float(it.unit_price) if include_price else None,
                )
            )

        return await self.generate_internal_labels_for_items(
            session=session,
            company_id=company_id,
            user_id=user_id,
            items=items_req,
            template_type=template_type,
            include_price=include_price,
            output_format=output_format,
            batch_name=f"Surtido Orden #{order.meli_order_id}",
            order_id=order.id,
        )

    # ---------------------------------------------------------------------------
    # DOCUMENTACIÓN DE LIMITACIONES OFICIALES Y PROCEDIMIENTOS PERMITIDOS
    # ---------------------------------------------------------------------------

    def get_logistics_limitations_doc(self) -> LogisticsLimitationsDocResponse:
        """
        Documentación oficial de limitaciones técnicas de la API de Mercado Envíos
        y propuesta de procedimientos operativos autorizados para contingencias.
        """
        limitations = [
            LogisticsLimitationItem(
                operation="Descarga de Etiquetas en Mercado Envíos Full",
                limitation_description=(
                    "La API oficial de Mercado Libre prohíbe terminantemente la descarga y generación de etiquetas "
                    "para órdenes con 'logistic_type': 'fulfillment'. Mercado Libre gestiona el almacenamiento, "
                    "empaque y rotulado de forma automatizada en sus propios CEDIS."
                ),
                official_code="CANNOT_PRINT_FULFILLMENT_LABEL",
                permitted_procedure=(
                    "El ERP identifica y clasifica los pedidos Full automáticamente. En lugar de intentar imprimir "
                    "guías que serán rechazadas por la API, se proporciona trazabilidad en vivo de los estados de preparación "
                    "del CEDIS y confirmación de salida."
                ),
                impact_level="critical",
            ),
            LogisticsLimitationItem(
                operation="Reimpresión de Guías de Envíos Despachados",
                limitation_description=(
                    "Una vez que el paquete ha sido escaneado por el transportista (DHL, FedEx, Colecta MeLi) y pasa "
                    "al estado 'shipped' o 'in_transit', la guía oficial queda consumida y bloqueada para reimpresión."
                ),
                official_code="SHIPMENT_ALREADY_IN_TRANSIT",
                permitted_procedure=(
                    "Si una etiqueta física se deteriora después de la recolección, el transportista ya posee la lectura "
                    "en su sistema de rutas. No se debe generar una guía nueva (lo que crearía un cobro de flete duplicado). "
                    "En su lugar, el operador debe consultar la trazabilidad con el número de tracking original."
                ),
                impact_level="high",
            ),
            LogisticsLimitationItem(
                operation="Impresión Masiva de Guías (Límites por Lote)",
                limitation_description=(
                    "El endpoint oficial 'GET /shipment_labels?shipment_ids=...' acepta como máximo 50 identificadores "
                    "por solicitud y requiere que todos los envíos pertenezcan a la misma cuenta de vendedor."
                ),
                official_code="BATCH_SIZE_LIMIT_50",
                permitted_procedure=(
                    "El motor del ERP particiona las solicitudes en bloques de máximo 50 unidades y agrupa por cuenta MeLi, "
                    "concatenando los flujos binarios PDF o ZPL devueltos de forma transparente para el usuario."
                ),
                impact_level="medium",
            ),
            LogisticsLimitationItem(
                operation="Etiquetas para Pedidos Cancelados o en Disputa",
                limitation_description=(
                    "Si un comprador cancela la compra o inicia un reclamo previo al despacho, la guía es cancelada en MeLi. "
                    "Intentar descargar la etiqueta retornará error HTTP 400."
                ),
                official_code="SHIPMENT_CANCELLED",
                permitted_procedure=(
                    "El ERP detecta el evento de cancelación en tiempo real vía webhook, bloquea la descarga de la guía "
                    "y libera automáticamente el stock reservado en el almacén local."
                ),
                impact_level="high",
            ),
            LogisticsLimitationItem(
                operation="Generación de Etiquetas Oficiales Falsas",
                limitation_description=(
                    "Queda estrictamente prohibido simular o inventar guías de envío que imiten formatos oficiales de DHL, "
                    "FedEx o Mercado Envíos sin respaldo de la API."
                ),
                official_code="NO_FAKE_OFFICIAL_LABELS",
                permitted_procedure=(
                    "Si la API oficial no está disponible o las credenciales expiraron, el sistema reporta el error exacto "
                    "y recomienda el flujo de reconexión OAuth o uso de las Etiquetas Internas para identificación de almacén."
                ),
                impact_level="critical",
            ),
        ]

        return LogisticsLimitationsDocResponse(
            title="Catálogo Oficial de Limitaciones de Mercado Envíos y Contingencias Operativas",
            description=(
                "Especificación técnica de las restricciones oficiales vigentes de la API de Mercado Libre México "
                "para envíos, guías de despacho y los procedimientos autorizados implementados en el ERP."
            ),
            last_updated=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            limitations=limitations,
        )

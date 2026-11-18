"""Servicio empresarial de Inventario, Kardex, Transferencias, Conteos y Sincronización con Mercado Libre."""

from datetime import datetime, timezone
import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.exceptions import AppException, EntityNotFoundException, InsufficientStockException
from src.core.logging import get_logger
from src.models.product import Product, ProductVariant
from src.models.warehouse import (
    Inventory,
    InventoryMovement,
    PhysicalCount,
    PhysicalCountItem,
    StockTransfer,
    StockTransferItem,
    Warehouse,
)
from src.repositories.inventory import InventoryRepository

logger = get_logger("inventory_service")


class InventoryService:
    def __init__(self):
        self.repo = InventoryRepository()

    async def get_or_create_inventory(
        self, session: AsyncSession, warehouse_id: uuid.UUID, variant_id: uuid.UUID
    ) -> Inventory:
        """Obtiene o crea una fila de inventario con bloqueo pesimista."""
        return await self.repo.get_or_create(session, warehouse_id, variant_id)

    async def adjust_stock(
        self,
        session: AsyncSession,
        warehouse_id: uuid.UUID,
        variant_id: uuid.UUID,
        quantity_delta: int,
        movement_type: str = "ADJUSTMENT",
        reference_id: str | None = None,
        reference_type: str | None = "manual",
        condition: str | None = "good",
        user_id: uuid.UUID | None = None,
        notes: str | None = None,
    ) -> tuple[Inventory, InventoryMovement]:
        """Ajuste transaccional general con cálculo automático de Stock Disponible."""
        return await self.repo.adjust_stock(
            session=session,
            warehouse_id=warehouse_id,
            variant_id=variant_id,
            quantity_delta=quantity_delta,
            movement_type=movement_type,
            reference_id=reference_id,
            reference_type=reference_type,
            condition=condition,
            user_id=user_id,
            notes=notes,
        )

    async def block_stock(
        self,
        session: AsyncSession,
        warehouse_id: uuid.UUID,
        variant_id: uuid.UUID,
        quantity: int,
        reason: str,
        user_id: uuid.UUID | None = None,
        notes: str | None = None,
    ) -> tuple[Inventory, InventoryMovement]:
        """
        Traslada existencias de Disponible a Bloqueado (cuarentena o control de calidad).
        Fórmula: Stock disponible = físico - reservado - bloqueado.
        """
        if quantity <= 0:
            raise AppException("La cantidad a bloquear debe ser mayor a 0", 400, "INVALID_QUANTITY")

        inventory = await self.repo.get_or_create(session, warehouse_id, variant_id)

        if inventory.available_stock < quantity:
            variant = await session.get(ProductVariant, variant_id)
            sku = variant.sku if variant else str(variant_id)
            raise InsufficientStockException(
                sku=sku, requested=quantity, available=inventory.available_stock
            )

        quantity_before = inventory.quantity_blocked
        inventory.quantity_blocked += quantity
        inventory.sync_available()

        full_notes = f"Bloqueo por motivo: {reason}. {notes or ''}".strip()
        movement = InventoryMovement(
            inventory_id=inventory.id,
            movement_type="BLOCK",
            quantity_delta=quantity,
            quantity_before=quantity_before,
            quantity_after=inventory.quantity_blocked,
            reference_id=str(user_id) if user_id else None,
            reference_type="manual",
            user_id=user_id,
            notes=full_notes,
        )
        session.add(movement)
        await session.flush()
        return inventory, movement

    async def unblock_stock(
        self,
        session: AsyncSession,
        warehouse_id: uuid.UUID,
        variant_id: uuid.UUID,
        quantity: int,
        reason: str,
        user_id: uuid.UUID | None = None,
        notes: str | None = None,
    ) -> tuple[Inventory, InventoryMovement]:
        """Libera existencias bloqueadas y las devuelve al stock disponible."""
        if quantity <= 0:
            raise AppException("La cantidad a desbloquear debe ser mayor a 0", 400, "INVALID_QUANTITY")

        inventory = await self.repo.get_or_create(session, warehouse_id, variant_id)

        if inventory.quantity_blocked < quantity:
            raise AppException(
                f"No se pueden desbloquear {quantity} unidades. Solo hay {inventory.quantity_blocked} bloqueadas.",
                400,
                "EXCESSIVE_UNBLOCK",
            )

        quantity_before = inventory.quantity_blocked
        inventory.quantity_blocked -= quantity
        inventory.sync_available()

        full_notes = f"Desbloqueo por motivo: {reason}. {notes or ''}".strip()
        movement = InventoryMovement(
            inventory_id=inventory.id,
            movement_type="UNBLOCK",
            quantity_delta=-quantity,
            quantity_before=quantity_before,
            quantity_after=inventory.quantity_blocked,
            reference_id=str(user_id) if user_id else None,
            reference_type="manual",
            user_id=user_id,
            notes=full_notes,
        )
        session.add(movement)
        await session.flush()
        return inventory, movement

    async def update_location_and_limits(
        self,
        session: AsyncSession,
        warehouse_id: uuid.UUID,
        variant_id: uuid.UUID,
        location_bin: str | None = None,
        safety_stock: int | None = None,
        max_stock: int | None = None,
    ) -> Inventory:
        """Actualiza ubicación en estante (pasillo/rack/bin) y umbrales mínimo/máximo."""
        inventory = await self.repo.get_or_create(session, warehouse_id, variant_id)
        if location_bin is not None:
            inventory.location_bin = location_bin
        if safety_stock is not None:
            inventory.safety_stock = safety_stock
            inventory.min_stock = safety_stock
        if max_stock is not None:
            inventory.max_stock = max_stock
        await session.flush()
        return inventory

    async def reserve_stock_for_order(
        self,
        session: AsyncSession,
        warehouse_id: uuid.UUID,
        variant_id: uuid.UUID,
        quantity: int,
        order_id: str,
        user_id: uuid.UUID | None = None,
        notes: str | None = None,
    ) -> tuple[Inventory, InventoryMovement]:
        """
        Reserva existencias al confirmarse un pedido de venta.
        Verifica disponibilidad e idempotencia: no duplica la reserva si ya existe.
        """
        if quantity <= 0:
            raise AppException("La cantidad a reservar debe ser mayor a 0", 400, "INVALID_QUANTITY")

        inventory = await self.repo.get_or_create(session, warehouse_id, variant_id)

        # Idempotencia: Verificar si ya existe movimiento RESERVATION para esta orden y variante
        stmt_dup = select(InventoryMovement).where(
            InventoryMovement.inventory_id == inventory.id,
            InventoryMovement.movement_type == "RESERVATION",
            InventoryMovement.reference_id == str(order_id),
            InventoryMovement.reference_type == "order",
        )
        existing_res = (await session.execute(stmt_dup)).scalar_one_or_none()
        if existing_res:
            logger.info(f"Reserva para orden {order_id} y variante {variant_id} ya aplicada previamente.")
            return inventory, existing_res

        # Validar disponibilidad estricta
        if inventory.available_stock < quantity:
            variant = await session.get(ProductVariant, variant_id)
            sku = variant.sku if variant else str(variant_id)
            raise InsufficientStockException(
                sku=sku, requested=quantity, available=inventory.available_stock
            )

        quantity_before = inventory.quantity_reserved
        inventory.quantity_reserved += quantity
        inventory.sync_available()

        movement = InventoryMovement(
            inventory_id=inventory.id,
            movement_type="RESERVATION",
            quantity_delta=quantity,
            quantity_before=quantity_before,
            quantity_after=inventory.quantity_reserved,
            reference_id=str(order_id),
            reference_type="order",
            user_id=user_id,
            notes=notes or f"Reserva por pedido #{order_id}",
        )
        session.add(movement)
        await session.flush()
        return inventory, movement

    async def release_order_reservation(
        self,
        session: AsyncSession,
        warehouse_id: uuid.UUID,
        variant_id: uuid.UUID,
        quantity: int,
        order_id: str,
        user_id: uuid.UUID | None = None,
        notes: str | None = None,
    ) -> tuple[Inventory, InventoryMovement]:
        """Libera la reserva de unidades cuando un pedido es cancelado antes de su envío."""
        inventory = await self.repo.get_or_create(session, warehouse_id, variant_id)

        # Idempotencia: Verificar si ya se liberó la reserva
        stmt_dup = select(InventoryMovement).where(
            InventoryMovement.inventory_id == inventory.id,
            InventoryMovement.movement_type == "RESERVATION_RELEASE",
            InventoryMovement.reference_id == str(order_id),
            InventoryMovement.reference_type == "order",
        )
        existing_rel = (await session.execute(stmt_dup)).scalar_one_or_none()
        if existing_rel:
            return inventory, existing_rel

        quantity_before = inventory.quantity_reserved
        qty_to_release = min(quantity, inventory.quantity_reserved)
        inventory.quantity_reserved -= qty_to_release
        inventory.sync_available()

        movement = InventoryMovement(
            inventory_id=inventory.id,
            movement_type="RESERVATION_RELEASE",
            quantity_delta=-qty_to_release,
            quantity_before=quantity_before,
            quantity_after=inventory.quantity_reserved,
            reference_id=str(order_id),
            reference_type="order",
            user_id=user_id,
            notes=notes or f"Liberación de reserva por cancelación de pedido #{order_id}",
        )
        session.add(movement)
        await session.flush()
        return inventory, movement

    async def commit_order_dispatch(
        self,
        session: AsyncSession,
        warehouse_id: uuid.UUID,
        variant_id: uuid.UUID,
        quantity: int,
        order_id: str,
        user_id: uuid.UUID | None = None,
        notes: str | None = None,
    ) -> tuple[Inventory, InventoryMovement]:
        """
        Despacha un pedido de venta, reduciendo stock físico y liberando la reserva.
        CONTROL ESTRICTO DE IDEMPOTENCIA:
        Evita descontar dos veces la misma venta verificando si ya existe un movimiento OUTBOUND para esa orden.
        """
        inventory = await self.repo.get_or_create(session, warehouse_id, variant_id)

        # 1. Comprobación de idempotencia: ¿ya fue despachada esta orden?
        stmt_dup = select(InventoryMovement).where(
            InventoryMovement.inventory_id == inventory.id,
            InventoryMovement.movement_type == "OUTBOUND",
            InventoryMovement.reference_id == str(order_id),
            InventoryMovement.reference_type == "order",
        )
        existing_disp = (await session.execute(stmt_dup)).scalar_one_or_none()
        if existing_disp:
            logger.warning(f"Intento de despacho duplicado bloqueado para orden {order_id}. Idempotencia garantizada.")
            return inventory, existing_disp

        # 2. Descuento de stock físico y ajuste de reserva
        if inventory.quantity_on_hand < quantity:
            variant = await session.get(ProductVariant, variant_id)
            sku = variant.sku if variant else str(variant_id)
            raise InsufficientStockException(
                sku=sku, requested=quantity, available=inventory.quantity_on_hand
            )

        quantity_before = inventory.quantity_on_hand
        inventory.quantity_on_hand -= quantity
        inventory.quantity_reserved = max(0, inventory.quantity_reserved - quantity)
        inventory.sync_available()

        movement = InventoryMovement(
            inventory_id=inventory.id,
            movement_type="OUTBOUND",
            quantity_delta=-quantity,
            quantity_before=quantity_before,
            quantity_after=inventory.quantity_on_hand,
            reference_id=str(order_id),
            reference_type="order",
            user_id=user_id,
            notes=notes or f"Despacho oficial de pedido #{order_id}",
        )
        session.add(movement)
        await session.flush()
        return inventory, movement

    async def process_order_return(
        self,
        session: AsyncSession,
        warehouse_id: uuid.UUID,
        variant_id: uuid.UUID,
        quantity: int,
        order_id: str,
        condition: str = "good",
        user_id: uuid.UUID | None = None,
        notes: str | None = None,
    ) -> tuple[Inventory, InventoryMovement]:
        """
        Procesa la devolución de una venta.
        - Condición 'good': reingresa al stock físico y queda DISPONIBLE para reventa.
        - Condición 'damaged': reingresa al stock físico pero se suma a BLOQUEADO/MERMA,
          impidiendo que se oferte en Mercado Libre como producto nuevo.
        """
        if quantity <= 0:
            raise AppException("La cantidad devuelta debe ser mayor a 0", 400, "INVALID_QUANTITY")

        inventory = await self.repo.get_or_create(session, warehouse_id, variant_id)

        quantity_before = inventory.quantity_on_hand
        inventory.quantity_on_hand += quantity

        if condition.lower() == "damaged":
            inventory.quantity_blocked += quantity
            movement_type = "DAMAGE"
            default_notes = f"Devolución con daño/merma de pedido #{order_id} - Bloqueado para inspección/baja"
        else:
            movement_type = "RETURN"
            default_notes = f"Devolución en buen estado de pedido #{order_id} - Reincorporado a existencias vendibles"

        inventory.sync_available()

        movement = InventoryMovement(
            inventory_id=inventory.id,
            movement_type=movement_type,
            quantity_delta=quantity,
            quantity_before=quantity_before,
            quantity_after=inventory.quantity_on_hand,
            reference_id=str(order_id),
            reference_type="order",
            user_id=user_id,
            notes=notes or default_notes,
        )
        session.add(movement)
        await session.flush()
        return inventory, movement

    async def create_stock_transfer(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        source_warehouse_id: uuid.UUID,
        target_warehouse_id: uuid.UUID,
        items_payload: list[dict],
        user_id: uuid.UUID | None = None,
        notes: str | None = None,
    ) -> StockTransfer:
        """Crea y despacha una transferencia entre almacenes (ej. Almacén Central -> MeLi Full)."""
        if source_warehouse_id == target_warehouse_id:
            raise AppException(
                "El almacén de origen y destino no pueden ser el mismo", 400, "INVALID_TRANSFER_DESTINATION"
            )

        # Generar número consecutivo
        count_stmt = select(func.count(StockTransfer.id)).where(StockTransfer.company_id == company_id)
        current_count = (await session.execute(count_stmt)).scalar() or 0
        transfer_number = f"TRF-{datetime.now(timezone.utc).strftime('%Y%m')}-{current_count + 1:04d}"

        transfer = StockTransfer(
            company_id=company_id,
            source_warehouse_id=source_warehouse_id,
            target_warehouse_id=target_warehouse_id,
            transfer_number=transfer_number,
            status="in_transit",
            notes=notes,
            created_by=user_id,
            shipped_at=datetime.now(timezone.utc),
        )
        session.add(transfer)
        await session.flush()

        # Descontar del almacén de origen
        for item in items_payload:
            variant_id = item["variant_id"]
            qty = item["quantity_sent"]
            if qty <= 0:
                continue

            inv_src = await self.repo.get_or_create(session, source_warehouse_id, variant_id)
            if inv_src.available_stock < qty:
                variant = await session.get(ProductVariant, variant_id)
                sku = variant.sku if variant else str(variant_id)
                raise InsufficientStockException(
                    sku=sku, requested=qty, available=inv_src.available_stock
                )

            inv_src.quantity_on_hand -= qty
            inv_src.sync_available()

            mov = InventoryMovement(
                inventory_id=inv_src.id,
                movement_type="TRANSFER_OUT",
                quantity_delta=-qty,
                quantity_before=inv_src.quantity_on_hand + qty,
                quantity_after=inv_src.quantity_on_hand,
                reference_id=str(transfer.id),
                reference_type="transfer",
                user_id=user_id,
                notes=f"Envío de transferencia #{transfer_number}",
            )
            session.add(mov)

            trf_item = StockTransferItem(
                transfer_id=transfer.id,
                variant_id=variant_id,
                quantity_sent=qty,
                quantity_received=0,
            )
            session.add(trf_item)

        await session.flush()
        return transfer

    async def receive_stock_transfer(
        self,
        session: AsyncSession,
        transfer_id: uuid.UUID,
        received_items: list[dict],
        user_id: uuid.UUID | None = None,
        notes: str | None = None,
    ) -> StockTransfer:
        """Confirma la recepción física en el almacén de destino (ej. reporte de ingreso a MeLi Full)."""
        stmt = (
            select(StockTransfer)
            .where(StockTransfer.id == transfer_id)
            .options(selectinload(StockTransfer.items))
            .with_for_update()
        )
        transfer = (await session.execute(stmt)).scalar_one_or_none()
        if not transfer:
            raise EntityNotFoundException("Transferencia", "id", str(transfer_id))

        if transfer.status == "received":
            raise AppException("Esta transferencia ya ha sido recibida previamente", 400, "ALREADY_RECEIVED")

        items_map = {item.variant_id: item for item in transfer.items}

        for rec in received_items:
            var_id = rec["variant_id"]
            qty_rec = rec["quantity_received"]
            if var_id not in items_map:
                continue

            trf_item = items_map[var_id]
            trf_item.quantity_received = qty_rec

            # Aumentar stock físico en el almacén de destino
            inv_tgt = await self.repo.get_or_create(session, transfer.target_warehouse_id, var_id)
            quantity_before = inv_tgt.quantity_on_hand
            inv_tgt.quantity_on_hand += qty_rec
            inv_tgt.sync_available()

            mov = InventoryMovement(
                inventory_id=inv_tgt.id,
                movement_type="TRANSFER_IN",
                quantity_delta=qty_rec,
                quantity_before=quantity_before,
                quantity_after=inv_tgt.quantity_on_hand,
                reference_id=str(transfer.id),
                reference_type="transfer",
                user_id=user_id,
                notes=f"Recepción de transferencia #{transfer.transfer_number}",
            )
            session.add(mov)

        transfer.status = "received"
        transfer.received_at = datetime.now(timezone.utc)
        if notes:
            transfer.notes = f"{transfer.notes or ''}\n{notes}".strip()

        await session.flush()
        return transfer

    async def create_physical_count(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        items_payload: list[dict],
        user_id: uuid.UUID | None = None,
        notes: str | None = None,
    ) -> PhysicalCount:
        """Registra un conteo físico cíclico para conciliar diferencias."""
        count_stmt = select(func.count(PhysicalCount.id)).where(PhysicalCount.company_id == company_id)
        current_count = (await session.execute(count_stmt)).scalar() or 0
        count_number = f"CNT-{datetime.now(timezone.utc).strftime('%Y%m')}-{current_count + 1:04d}"

        count_obj = PhysicalCount(
            company_id=company_id,
            warehouse_id=warehouse_id,
            count_number=count_number,
            status="in_progress",
            notes=notes,
            counted_by=user_id,
        )
        session.add(count_obj)
        await session.flush()

        for item in items_payload:
            variant_id = item["variant_id"]
            counted_qty = item["counted_quantity"]
            loc_bin = item.get("location_bin")

            inv = await self.repo.get_or_create(session, warehouse_id, variant_id)
            system_qty = inv.quantity_on_hand
            diff = counted_qty - system_qty

            count_item = PhysicalCountItem(
                count_id=count_obj.id,
                variant_id=variant_id,
                system_quantity=system_qty,
                counted_quantity=counted_qty,
                difference=diff,
                location_bin=loc_bin or inv.location_bin,
            )
            session.add(count_item)

        await session.flush()
        return count_obj

    async def apply_physical_count(
        self,
        session: AsyncSession,
        count_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> PhysicalCount:
        """Aplica formalmente los ajustes derivados del conteo físico al inventario."""
        stmt = (
            select(PhysicalCount)
            .where(PhysicalCount.id == count_id)
            .options(selectinload(PhysicalCount.items))
            .with_for_update()
        )
        count_obj = (await session.execute(stmt)).scalar_one_or_none()
        if not count_obj:
            raise EntityNotFoundException("Conteo Físico", "id", str(count_id))

        if count_obj.status == "applied":
            raise AppException("Este conteo físico ya fue aplicado", 400, "ALREADY_APPLIED")

        for item in count_obj.items:
            if item.difference != 0:
                inv = await self.repo.get_or_create(session, count_obj.warehouse_id, item.variant_id)
                quantity_before = inv.quantity_on_hand
                inv.quantity_on_hand = item.counted_quantity
                if item.location_bin:
                    inv.location_bin = item.location_bin
                inv.sync_available()

                movement = InventoryMovement(
                    inventory_id=inv.id,
                    movement_type="CYCLE_COUNT",
                    quantity_delta=item.difference,
                    quantity_before=quantity_before,
                    quantity_after=inv.quantity_on_hand,
                    reference_id=str(count_obj.id),
                    reference_type="cycle_count",
                    user_id=user_id,
                    notes=f"Ajuste por conteo físico cíclico #{count_obj.count_number}",
                )
                session.add(movement)

        count_obj.status = "applied"
        count_obj.applied_at = datetime.now(timezone.utc)
        await session.flush()
        return count_obj

    async def get_inventory_alerts(
        self, session: AsyncSession, company_id: uuid.UUID, warehouse_id: uuid.UUID | None = None
    ) -> list[dict]:
        """
        Recupera las alertas preventivas de existencias:
        - Agotados (OUT_OF_STOCK)
        - Bajo Stock (LOW_STOCK <= safety_stock)
        - Sobre-inventario (OVER_STOCK > max_stock)
        """
        stmt = (
            select(Inventory, Warehouse, ProductVariant, Product)
            .join(Warehouse, Inventory.warehouse_id == Warehouse.id)
            .join(ProductVariant, Inventory.variant_id == ProductVariant.id)
            .join(Product, ProductVariant.product_id == Product.id)
            .where(Warehouse.company_id == company_id)
        )
        if warehouse_id:
            stmt = stmt.where(Warehouse.id == warehouse_id)

        rows = (await session.execute(stmt)).all()
        alerts = []

        for inv, wh, variant, prod in rows:
            alert_st = inv.alert_status
            if alert_st in {"OUT_OF_STOCK", "LOW_STOCK", "OVER_STOCK"}:
                alerts.append(
                    {
                        "variant_id": inv.variant_id,
                        "warehouse_id": inv.warehouse_id,
                        "warehouse_name": wh.name,
                        "is_fulfillment": wh.is_fulfillment,
                        "sku": variant.sku,
                        "product_title": prod.name,
                        "quantity_on_hand": inv.quantity_on_hand,
                        "quantity_reserved": inv.quantity_reserved,
                        "quantity_blocked": inv.quantity_blocked,
                        "quantity_available": inv.quantity_available,
                        "safety_stock": inv.safety_stock,
                        "max_stock": inv.max_stock,
                        "location_bin": inv.location_bin,
                        "alert_status": alert_st,
                    }
                )

        return alerts

    async def get_syncable_stock_for_meli(
        self, session: AsyncSession, company_id: uuid.UUID, variant_id: uuid.UUID, safety_buffer: int = 0
    ) -> dict:
        """
        Calcula el stock sincronizable con Mercado Libre garantizando discriminación estricta de MeLi FULL.
        
        REGLA DE NEGOCIO CRÍTICA (MERCADO ENVÍOS FULL):
        - Las bodegas FULL de Mercado Libre reportan y gestionan su propio stock físico de forma autónoma.
        - Para las publicaciones locales (Flex, Colecta, Drop-off), el ERP solo sincroniza la suma del
          Stock Disponible de los almacenes LOCALES/INTERNOS (is_fulfillment=False).
        - Se evita sobreescribir o colisionar con el inventario administrado por Mercado Libre en FULL.
        """
        variant = await session.get(ProductVariant, variant_id)
        if not variant:
            raise EntityNotFoundException("Variante", "id", str(variant_id))

        stmt = (
            select(Inventory, Warehouse)
            .join(Warehouse, Inventory.warehouse_id == Warehouse.id)
            .where(Warehouse.company_id == company_id, Inventory.variant_id == variant_id)
        )
        results = (await session.execute(stmt)).all()

        local_available = 0
        meli_full_stock = 0

        for inv, wh in results:
            if wh.is_fulfillment or wh.warehouse_type == "meli_fulfillment":
                meli_full_stock += inv.quantity_on_hand
            else:
                # Almacén local propio: se toma el stock disponible
                local_available += inv.quantity_available

        syncable_for_meli = max(0, local_available - safety_buffer)

        return {
            "variant_id": variant_id,
            "sku": variant.sku,
            "local_available_stock": local_available,
            "meli_full_stock": meli_full_stock,
            "syncable_stock_for_meli": syncable_for_meli,
            "safety_buffer": safety_buffer,
        }

"""Repositorio transaccional de Inventarios con bloqueo pesimista y Kardex."""

import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import InsufficientStockException
from src.models.product import ProductVariant
from src.models.warehouse import Inventory, InventoryMovement
from src.repositories.base import BaseRepository


class InventoryRepository(BaseRepository[Inventory]):
    def __init__(self):
        super().__init__(Inventory)

    async def get_or_create(
        self, session: AsyncSession, warehouse_id: uuid.UUID, variant_id: uuid.UUID
    ) -> Inventory:
        """Obtiene el registro de inventario o lo inicializa en cero si no existe."""
        stmt = (
            select(Inventory)
            .where(Inventory.warehouse_id == warehouse_id, Inventory.variant_id == variant_id)
            .with_for_update()  # Bloqueo pesimista en PostgreSQL para evitar condiciones de carrera
        )
        result = await session.execute(stmt)
        inventory = result.scalar_one_or_none()

        if not inventory:
            inventory = Inventory(
                warehouse_id=warehouse_id,
                variant_id=variant_id,
                quantity_available=0,
                quantity_reserved=0,
                safety_stock=5,
            )
            session.add(inventory)
            await session.flush()

        return inventory

    async def adjust_stock(
        self,
        session: AsyncSession,
        warehouse_id: uuid.UUID,
        variant_id: uuid.UUID,
        quantity_delta: int,
        movement_type: str = "ADJUSTMENT",
        reference_id: str | None = None,
        user_id: uuid.UUID | None = None,
        notes: str | None = None,
    ) -> tuple[Inventory, InventoryMovement]:
        """
        Ajuste transaccional y atómico de inventario.
        Verifica que el stock resultante no sea negativo e inserta el movimiento en el Kardex.
        """
        inventory = await self.get_or_create(session, warehouse_id, variant_id)

        quantity_before = inventory.quantity_available
        quantity_after = quantity_before + quantity_delta

        if quantity_after < 0:
            variant = await session.get(ProductVariant, variant_id)
            sku = variant.sku if variant else str(variant_id)
            raise InsufficientStockException(sku=sku, requested=abs(quantity_delta), available=quantity_before)

        inventory.quantity_available = quantity_after

        # Registrar movimiento inmutable en el Kardex
        movement = InventoryMovement(
            inventory_id=inventory.id,
            movement_type=movement_type,
            quantity_delta=quantity_delta,
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            reference_id=reference_id,
            user_id=user_id,
            notes=notes,
        )
        session.add(movement)
        await session.flush()

        return inventory, movement

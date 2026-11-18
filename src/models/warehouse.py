"""Modelos de Almacenes, Niveles de Inventario y Movimientos (Kardex)."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import GUID, Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.product import ProductVariant
    from src.models.tenant import Company


class Warehouse(Base, TimestampMixin):
    """Almacén o ubicación física/virtual de inventario."""

    __tablename__ = "warehouses"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "BOD-CENTRAL", "MELI-FULL-01"
    warehouse_type: Mapped[str] = mapped_column(String(50), default="internal")  # internal, meli_fulfillment, dropship
    address: Mapped[str] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    company: Mapped["Company"] = relationship("Company", back_populates="warehouses")
    inventories: Mapped[list["Inventory"]] = relationship(
        "Inventory", back_populates="warehouse", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_warehouses_company_code", "company_id", "code", unique=True),
    )


class Inventory(Base, TimestampMixin):
    """Existencias actuales de una variante en un almacén específico."""

    __tablename__ = "inventories"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    variant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quantity_available: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quantity_reserved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # Reservado por pedidos en proceso
    safety_stock: Mapped[int] = mapped_column(Integer, default=5, nullable=False)  # Punto mínimo de alerta

    warehouse: Mapped["Warehouse"] = relationship("Warehouse", back_populates="inventories")
    variant: Mapped["ProductVariant"] = relationship("ProductVariant", back_populates="inventories")
    movements: Mapped[list["InventoryMovement"]] = relationship(
        "InventoryMovement", back_populates="inventory", cascade="all, delete-orphan"
    )

    @property
    def total_stock(self) -> int:
        return self.quantity_available + self.quantity_reserved

    __table_args__ = (
        Index("ix_inventories_warehouse_variant", "warehouse_id", "variant_id", unique=True),
    )


class InventoryMovement(Base, TimestampMixin):
    """Registro inmutable de movimientos de inventario (Kardex de auditoría)."""

    __tablename__ = "inventory_movements"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    inventory_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("inventories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    movement_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # PURCHASE_RECEIPT, SALE_SHIPMENT, ADJUSTMENT, TRANSFER_IN, TRANSFER_OUT, RETURN
    quantity_delta: Mapped[int] = mapped_column(Integer, nullable=False)  # +10 o -2
    quantity_before: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_id: Mapped[str] = mapped_column(String(100), nullable=True)  # Order ID, Purchase Order ID
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=True)  # Usuario que autorizó el ajuste
    notes: Mapped[str] = mapped_column(Text, nullable=True)

    inventory: Mapped["Inventory"] = relationship("Inventory", back_populates="movements")

    __table_args__ = (
        Index("ix_inventory_movements_type_date", "movement_type", "created_at"),
    )

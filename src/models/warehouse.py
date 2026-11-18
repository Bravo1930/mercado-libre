"""Modelos de Almacenes, Niveles de Inventario, Movimientos (Kardex), Transferencias y Conteos Físicos."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import GUID, Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.product import ProductVariant
    from src.models.tenant import Company


class Warehouse(Base, TimestampMixin):
    """Almacén o centro de distribución físico/virtual de inventario."""

    __tablename__ = "warehouses"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "BOD-CENTRAL", "MELI-FULL-MX01"
    warehouse_type: Mapped[str] = mapped_column(
        String(50), default="internal"
    )  # internal, meli_fulfillment, store, dropship
    is_fulfillment: Mapped[bool] = mapped_column(
        Boolean, default=False
    )  # Si es True, es bodega administrada por Mercado Libre Full
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    company: Mapped["Company"] = relationship("Company", back_populates="warehouses")
    inventories: Mapped[list["Inventory"]] = relationship(
        "Inventory", back_populates="warehouse", cascade="all, delete-orphan"
    )
    transfers_as_source: Mapped[list["StockTransfer"]] = relationship(
        "StockTransfer",
        foreign_keys="StockTransfer.source_warehouse_id",
        back_populates="source_warehouse",
    )
    transfers_as_target: Mapped[list["StockTransfer"]] = relationship(
        "StockTransfer",
        foreign_keys="StockTransfer.target_warehouse_id",
        back_populates="target_warehouse",
    )
    physical_counts: Mapped[list["PhysicalCount"]] = relationship(
        "PhysicalCount", back_populates="warehouse", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_warehouses_company_code", "company_id", "code", unique=True),
        Index("ix_warehouses_type_fulfillment", "company_id", "warehouse_type", "is_fulfillment"),
    )


class Inventory(Base, TimestampMixin):
    """
    Existencias actuales de una variante en un almacén específico.
    
    FÓRMULA ESTRICTA DE INVENTARIO:
    Stock disponible = Stock físico - Stock reservado - Stock bloqueado.
    """

    __tablename__ = "inventories"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    variant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quantity_on_hand: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )  # Stock físico total presente en almacén
    quantity_reserved: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )  # Stock reservado por pedidos confirmados/pagados
    quantity_blocked: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )  # Stock bloqueado por inspección de calidad, cuarentena o daño
    quantity_available: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )  # Stock disponible calculado: físico - reservado - bloqueado
    safety_stock: Mapped[int] = mapped_column(
        Integer, default=5, nullable=False
    )  # Stock mínimo de alerta preventiva
    min_stock: Mapped[int] = mapped_column(
        Integer, default=5, nullable=False
    )  # Umbral mínimo deseable
    max_stock: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # Umbral máximo o capacidad de sobre-inventario
    location_bin: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # Ubicación interna (e.g. Pasillo A, Rack 02, Nivel 3)

    warehouse: Mapped["Warehouse"] = relationship("Warehouse", back_populates="inventories")
    variant: Mapped["ProductVariant"] = relationship("ProductVariant", back_populates="inventories")
    movements: Mapped[list["InventoryMovement"]] = relationship(
        "InventoryMovement", back_populates="inventory", cascade="all, delete-orphan"
    )

    def calculate_available(self) -> int:
        """Calcula el stock disponible respetando la fórmula oficial."""
        return max(0, self.quantity_on_hand - self.quantity_reserved - self.quantity_blocked)

    def sync_available(self) -> None:
        """Sincroniza el campo persistente quantity_available con la fórmula oficial."""
        self.quantity_available = self.calculate_available()

    @property
    def physical_stock(self) -> int:
        return self.quantity_on_hand

    @property
    def reserved_stock(self) -> int:
        return self.quantity_reserved

    @property
    def blocked_stock(self) -> int:
        return self.quantity_blocked

    @property
    def available_stock(self) -> int:
        return self.calculate_available()

    @property
    def total_stock(self) -> int:
        """Alias para mantener compatibilidad con lecturas previas de stock total físico."""
        return self.quantity_on_hand

    @property
    def alert_status(self) -> str:
        """
        Retorna la condición de alerta de existencias:
        - OUT_OF_STOCK: agotado (disponible <= 0 o físico <= 0).
        - LOW_STOCK: bajo stock (disponible <= safety_stock).
        - OVER_STOCK: sobre-inventario (físico > max_stock).
        - NORMAL: niveles saludables.
        """
        if self.quantity_on_hand <= 0 or self.quantity_available <= 0:
            return "OUT_OF_STOCK"
        if self.quantity_available <= self.safety_stock:
            return "LOW_STOCK"
        if self.max_stock is not None and self.quantity_on_hand > self.max_stock:
            return "OVER_STOCK"
        return "NORMAL"

    __table_args__ = (
        Index("ix_inventories_warehouse_variant", "warehouse_id", "variant_id", unique=True),
        Index("ix_inventories_available", "quantity_available"),
    )


class InventoryMovement(Base, TimestampMixin):
    """
    Registro inmutable de movimientos de inventario (Kardex de auditoría transaccional).
    Garantiza trazabilidad de entradas, salidas, reservas, ajustes, devoluciones y transferencias.
    """

    __tablename__ = "inventory_movements"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    inventory_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("inventories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    movement_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # INBOUND, OUTBOUND, ADJUSTMENT, RESERVATION, RESERVATION_RELEASE, RETURN, DAMAGE, TRANSFER_IN, TRANSFER_OUT, CYCLE_COUNT, BLOCK, UNBLOCK
    quantity_delta: Mapped[int] = mapped_column(Integer, nullable=False)  # +10 o -2
    quantity_before: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )  # e.g. ID de Orden de MeLi, ID de Conteo, ID de Transferencia
    reference_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True
    )  # order, purchase_order, transfer, cycle_count, manual
    user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)  # Usuario operador responsable
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    inventory: Mapped["Inventory"] = relationship("Inventory", back_populates="movements")

    __table_args__ = (
        Index("ix_inventory_movements_type_date", "movement_type", "created_at"),
        Index("ix_inventory_movements_ref_id_type", "reference_id", "reference_type"),
    )


class StockTransfer(Base, TimestampMixin):
    """Transferencia formal de mercancía entre almacenes internos y bodegas de Mercado Envíos Full."""

    __tablename__ = "stock_transfers"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_warehouse_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    target_warehouse_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    transfer_number: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "TRF-2026-0001"
    status: Mapped[str] = mapped_column(
        String(30), default="draft", nullable=False
    )  # draft, in_transit, received, cancelled
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped["Company"] = relationship("Company")
    source_warehouse: Mapped["Warehouse"] = relationship(
        "Warehouse", foreign_keys=[source_warehouse_id], back_populates="transfers_as_source"
    )
    target_warehouse: Mapped["Warehouse"] = relationship(
        "Warehouse", foreign_keys=[target_warehouse_id], back_populates="transfers_as_target"
    )
    items: Mapped[list["StockTransferItem"]] = relationship(
        "StockTransferItem", back_populates="transfer", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_transfers_company_number", "company_id", "transfer_number", unique=True),
        Index("ix_transfers_company_status", "company_id", "status"),
    )


class StockTransferItem(Base, TimestampMixin):
    """Partida individual de una transferencia de inventario."""

    __tablename__ = "stock_transfer_items"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    transfer_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("stock_transfers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    variant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quantity_sent: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    transfer: Mapped["StockTransfer"] = relationship("StockTransfer", back_populates="items")
    variant: Mapped["ProductVariant"] = relationship("ProductVariant")


class PhysicalCount(Base, TimestampMixin):
    """Auditoría de inventario físico y conteo cíclico periódico."""

    __tablename__ = "physical_counts"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    count_number: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "CNT-2026-0001"
    status: Mapped[str] = mapped_column(
        String(30), default="draft", nullable=False
    )  # draft, in_progress, applied, cancelled
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    counted_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped["Company"] = relationship("Company")
    warehouse: Mapped["Warehouse"] = relationship("Warehouse", back_populates="physical_counts")
    items: Mapped[list["PhysicalCountItem"]] = relationship(
        "PhysicalCountItem", back_populates="count", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_physical_counts_company_number", "company_id", "count_number", unique=True),
        Index("ix_physical_counts_company_status", "company_id", "status"),
    )


class PhysicalCountItem(Base, TimestampMixin):
    """Partida de auditoría comparando existencias teóricas en sistema vs conteo físico real."""

    __tablename__ = "physical_count_items"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    count_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("physical_counts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    variant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    system_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    counted_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    difference: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # counted - system
    location_bin: Mapped[str | None] = mapped_column(String(50), nullable=True)

    count: Mapped["PhysicalCount"] = relationship("PhysicalCount", back_populates="items")
    variant: Mapped["ProductVariant"] = relationship("ProductVariant")

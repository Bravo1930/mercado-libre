"""
Modelos para el Centro de Información Tabular del ERP.
Gestión de auditoría de ediciones en planillas internas,
configuración de sincronización con Google Sheets y Microsoft Excel,
preservación de identificadores únicos y control de conflictos.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import GUID, Base, TimestampMixin


class TabularSyncConfig(Base, TimestampMixin):
    """
    Configuración de integración con planillas externas (Google Sheets / Microsoft Excel).
    Las planillas externas no son la fuente principal de inventario.
    """

    __tablename__ = "tabular_sync_configs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Vista oficial sincronizada: sales, products, inventory, movements, costs, commissions,
    # profitability, promotions, shipments, purchases, suppliers, daily_summary, monthly_summary
    view_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # Proveedor: google_sheets, microsoft_excel
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # ID de Spreadsheet en Google Drive o Item ID en OneDrive / MS Graph
    spreadsheet_id: Mapped[str] = mapped_column(String(255), nullable=False)
    # Nombre de la pestaña u hoja de cálculo (e.g. "ERP_Ventas", "ERP_Inventario")
    sheet_name: Mapped[str] = mapped_column(String(100), default="Datos_ERP", nullable=False)

    # Dirección: push_to_sheet (ERP -> Hoja), bidirectional (con resolución de conflictos)
    sync_direction: Mapped[str] = mapped_column(String(50), default="push_to_sheet", nullable=False)
    # Resolución de conflictos: server_wins (ERP manda), external_wins (con validación), manual_review
    conflict_resolution: Mapped[str] = mapped_column(String(50), default="server_wins", nullable=False)

    # Intervalo de sincronización periódica en minutos (0 = sólo manual)
    auto_sync_interval_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Estados: idle, in_progress, success, error, conflict_detected
    last_sync_status: Mapped[str] = mapped_column(String(50), default="idle", nullable=False)
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Credenciales OAuth cifradas (AES-256 Fernet)
    oauth_credentials_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    total_rows_synced: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("ix_tabular_sync_company_view_provider", "company_id", "view_name", "provider", unique=True),
    )


class TabularEditHistory(Base):
    """
    Historial inmutable de auditoría para modificaciones realizadas en la planilla tabular
    o sincronizadas desde hojas externas autorizadas.
    """

    __tablename__ = "tabular_edit_history"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    view_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # Identificador único de la fila modificada (e.g. SKU, Order ID, Variant UUID)
    row_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    column_name: Mapped[str] = mapped_column(String(100), nullable=False)

    previous_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    change_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Origen: internal_grid, google_sheets, microsoft_excel, api_import
    source: Mapped[str] = mapped_column(String(50), default="internal_grid", nullable=False)
    # Estatus: applied, conflict_rejected, reverted
    status: Mapped[str] = mapped_column(String(50), default="applied", nullable=False)
    conflict_details: Mapped[str | None] = mapped_column(Text, nullable=True)

    user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    user_name: Mapped[str] = mapped_column(String(150), default="Usuario Autorizado", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )

    __table_args__ = (
        Index("ix_tabular_history_company_view_created", "company_id", "view_name", "created_at"),
        Index("ix_tabular_history_row", "company_id", "row_id"),
    )

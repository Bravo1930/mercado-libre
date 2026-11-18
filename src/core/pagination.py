"""Utilidades genéricas de Paginación y Filtrado para la API REST."""

import math
from typing import Generic, Literal, TypeVar

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

T = TypeVar("T")


class PaginationParams:
    """Parámetros de consulta para paginación y ordenamiento estándar."""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="Número de página (inicia en 1)"),
        page_size: int = Query(20, ge=1, le=100, description="Elementos por página (máx. 100)"),
        sort_by: str | None = Query(None, description="Campo por el cual ordenar"),
        sort_order: Literal["asc", "desc"] = Query("desc", description="Dirección del orden"),
    ):
        self.page = page
        self.page_size = page_size
        self.sort_by = sort_by
        self.sort_order = sort_order

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class Page(BaseModel, Generic[T]):
    """Estructura estandarizada de respuesta paginada."""

    model_config = ConfigDict(arbitrary_types_allowed=True, from_attributes=True)

    items: list[T]
    total_items: int = Field(..., description="Total de registros que coinciden con los filtros")
    page: int = Field(..., description="Página actual")
    page_size: int = Field(..., description="Tamaño de la página")
    total_pages: int = Field(..., description="Total de páginas calculadas")
    has_next: bool = Field(..., description="Indica si existe una página siguiente")
    has_prev: bool = Field(..., description="Indica si existe una página anterior")

    @classmethod
    def create(cls, items: list[T], total_items: int, params: PaginationParams) -> "Page[T]":
        total_pages = math.ceil(total_items / params.page_size) if total_items > 0 else 1
        return cls(
            items=items,
            total_items=total_items,
            page=params.page,
            page_size=params.page_size,
            total_pages=total_pages,
            has_next=params.page < total_pages,
            has_prev=params.page > 1,
        )


async def paginate_query(
    stmt: Select,
    session: AsyncSession,
    params: PaginationParams,
) -> tuple[list, int]:
    """
    Ejecuta una consulta SQL con conteo total exacto y paginación LIMIT/OFFSET eficiente.
    """
    # 1. Contar total de registros
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await session.execute(count_stmt)
    total_items = total_result.scalar_one()

    # 2. Aplicar paginación
    paginated_stmt = stmt.offset(params.offset).limit(params.page_size)
    items_result = await session.execute(paginated_stmt)
    items = list(items_result.scalars().all())

    return items, total_items

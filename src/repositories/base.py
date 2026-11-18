"""Repositorio base genérico con soporte transaccional, paginación y filtros."""

from typing import Any, Generic, Type, TypeVar
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import Base
from src.core.exceptions import EntityNotFoundException
from src.core.pagination import Page, PaginationParams, paginate_query

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Patrón Repositorio genérico para operaciones CRUD seguras en PostgreSQL."""

    def __init__(self, model: Type[ModelType]):
        self.model = model

    async def get(self, session: AsyncSession, id: uuid.UUID) -> ModelType | None:
        """Obtiene una entidad por su clave primaria UUID."""
        stmt = select(self.model).where(self.model.id == id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_fail(self, session: AsyncSession, id: uuid.UUID) -> ModelType:
        """Obtiene una entidad por ID o lanza EntityNotFoundException si no existe."""
        entity = await self.get(session, id)
        if not entity:
            raise EntityNotFoundException(self.model.__name__, id)
        return entity

    async def get_paginated(
        self,
        session: AsyncSession,
        params: PaginationParams,
        *filters: Any,
    ) -> Page[ModelType]:
        """Consulta entidades con filtros dinámicos y paginación LIMIT/OFFSET."""
        stmt = select(self.model)
        for f in filters:
            if f is not None:
                stmt = stmt.where(f)

        if params.sort_by and hasattr(self.model, params.sort_by):
            column = getattr(self.model, params.sort_by)
            stmt = stmt.order_by(column.desc() if params.sort_order == "desc" else column.asc())
        elif hasattr(self.model, "created_at"):
            stmt = stmt.order_by(self.model.created_at.desc())

        items, total = await paginate_query(stmt, session, params)
        return Page.create(items, total, params)

    async def create(self, session: AsyncSession, obj_in: dict[str, Any] | ModelType) -> ModelType:
        """Crea y persiste una nueva entidad dentro de la sesión."""
        if isinstance(obj_in, dict):
            db_obj = self.model(**obj_in)
        else:
            db_obj = obj_in
        session.add(db_obj)
        await session.flush()
        return db_obj

    async def update(
        self, session: AsyncSession, db_obj: ModelType, update_data: dict[str, Any]
    ) -> ModelType:
        """Actualiza atributos de una entidad existente."""
        for field, value in update_data.items():
            if hasattr(db_obj, field) and value is not None:
                setattr(db_obj, field, value)
        session.add(db_obj)
        await session.flush()
        return db_obj

    async def delete(self, session: AsyncSession, id: uuid.UUID) -> bool:
        """Elimina una entidad por su ID."""
        entity = await self.get(session, id)
        if entity:
            await session.delete(entity)
            await session.flush()
            return True
        return False

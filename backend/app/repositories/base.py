"""Generic async repository base class."""
from typing import Any, Generic, Optional, Sequence, Type, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """CRUD helpers shared by all repositories.

    `pk_column` lets subclasses specify a primary key column name other
    than `id` (several SentinelAI tables use domain-specific primary key
    names such as `device_id`, `incident_id`, etc., per the architecture
    document's table definitions).
    """

    model: Type[ModelType]
    pk_column: str = "id"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, pk: Any) -> Optional[ModelType]:
        return await self.session.get(self.model, pk)

    async def list_all(self, limit: int = 100, offset: int = 0) -> Sequence[ModelType]:
        stmt = select(self.model).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def add(self, instance: ModelType) -> ModelType:
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def delete(self, instance: ModelType) -> None:
        await self.session.delete(instance)
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()

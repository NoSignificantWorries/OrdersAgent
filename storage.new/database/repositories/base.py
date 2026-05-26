from typing import Any, Dict, Generic, List, Optional, Type, TypeVar
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

ModelType = TypeVar("ModelType")


class BaseRepository(Generic[ModelType]):
    def __init__(self, model: Type[ModelType], session: AsyncSession) -> None:
        self.model = model
        self.session = session

    async def create(self, **kwargs) -> ModelType:
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def get_by_id(self, id: UUID | int) -> Optional[ModelType]:
        return await self.session.get(self.model, id)

    async def get_all(
        self, skip: int = 0, limit: int = 100, order_by: Optional[str] = None
    ) -> List[ModelType]:
        query = select(self.model).offset(skip).limit(limit)
        if order_by:
            query.order_by(order_by)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def find_by(self, **filters) -> List[ModelType]:
        query = select(self.model).filter_by(**filters)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def find_one_by(self, **filters) -> ModelType:
        query = select(self.model).filter_by(**filters).limit(1)
        result = await self.session.execute(query)
        return result.scalars().first()

    async def update(self, id: UUID | int, **values) -> Optional[ModelType]:
        query = (
            update(self.model)
            .where(self.model.id == id)
            .values(**values)
            .returning(self.model)
        )
        result = await self.session.execute(query)
        await self.session.flush()
        return result.scalars().all()

    async def delete(self, id: UUID | int) -> bool:
        query = delete(self.model).where(self.model.id == id)
        result = await self.session.execute(query)
        await self.session.flush()
        return result.rowcount > 0

    async def bulk_create(self, objects: List[Dict[str, Any]]) -> List[ModelType]:
        instances = [self.model(**obj) for obj in objects]
        self.session.add_all(instances)
        await self.session.flush()
        return instances

    async def bulk_update(self, updates: Dict[UUID | int, Dict[str, Any]]) -> int:
        count = 0
        for id, values in updates.items():
            result = await self.update(id, **values)
            if result:
                count += 1
        return count

    async def delete_all(self, **filters) -> int:
        query = delete(self.model).filter_by(**filters)
        result = await self.session.execute(query)
        await self.session.flush()
        return result.rowcount

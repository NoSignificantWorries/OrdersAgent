from typing import List

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Files, FilesQueue
from .base import BaseRepository


class FilesRepository(BaseRepository[Files]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Files, session)

    async def add_file(self, **file) -> Files:
        result = await self.create(**file)
        return result

    async def add_many(self, email_id: int, files: List[str]) -> List[Files]:
        query = (
            pg_insert(self.model)
            .values([dict(email_id=email_id, origin_minio_key=file) for file in files])
            .returning(self.model)
        )
        results = await self.session.execute(query)
        await self.session.flush()
        return results.scalars().all()

    async def get_files_by_email_id(self, email_id: int) -> List[Files]:
        result = await self.find_by(email_id=email_id)
        return result


class FilesQueueRepository(BaseRepository[FilesQueue]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(FilesQueue, session)

    async def add_file_task(self, **task) -> Files:
        result = await self.create(**task)
        return result

    async def add_many(
        self, email_task_id: int, files_indexes: List[int]
    ) -> List[FilesQueue]:
        query = (
            pg_insert(self.model)
            .values(
                [
                    dict(email_task_id=email_task_id, file_id=file_idx)
                    for file_idx in files_indexes
                ]
            )
            .returning(self.model)
        )
        results = await self.session.execute(query)
        await self.session.flush()
        return results.scalars().all()

    async def update_by_email_task_id(
        self, email_task_id: int, **updates
    ) -> List[FilesQueue]:
        tasks = await self.find_by(email_task_id=email_task_id)
        updates = {task.id: updates for task in tasks}
        results = await self.bulk_update(updates)
        return results

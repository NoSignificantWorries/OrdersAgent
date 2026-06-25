from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Emails, EmailsQueue, EmailType
from .base import BaseRepository


class EmailsRepository(BaseRepository[Emails]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Emails, session)

    async def add_user(self, **email) -> Emails:
        result = await self.create(**email)
        return result

    async def mark_archived(self, id: int) -> Emails:
        result = await self.update(id=id, archived=True, archived_at=datetime.now())
        return result


class EmailsQueueRepository(BaseRepository[EmailsQueue]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(EmailsQueue, session)

    async def add_task(self, **email) -> EmailsQueue:
        result = await self.create(**email)
        return result

    async def get_by_email_id(self, email_id: int) -> EmailsQueue:
        result = await self.find_one_by(email_id=email_id)
        return result

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Emails, EmailsQueue, EmailType
from .base import BaseRepository


class EmailsRepository(BaseRepository[Emails]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Emails, session)


class EmailsQueueRepository(BaseRepository[EmailsQueue]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(EmailsQueue, session)

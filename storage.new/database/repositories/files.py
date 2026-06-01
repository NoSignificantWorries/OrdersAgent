from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Files, FilesQueue
from .base import BaseRepository


class FilesRepository(BaseRepository[Files]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Files, session)


class FilesQueueRepository(BaseRepository[FilesQueue]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(FilesQueue, session)

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Materials
from .base import BaseRepository


class MaterialsRepository(BaseRepository[Materials]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Materials, session)

    async def get_by_source(self, source: str) -> Optional[Materials]:
        return await self.find_one_by(source=source)

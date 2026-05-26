from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Users, UserStatus
from .base import BaseRepository


class UsersRepository(BaseRepository[Users]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Users, session)

    async def get_all_users(self) -> List[Users]:
        return await self.get_all()

    async def get_users_by_status(self, status: UserStatus) -> List[Users]:
        return await self.find_by(status=status)

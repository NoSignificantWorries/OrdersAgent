from typing import Any, Dict, List

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Users, UserStatus
from .base import BaseRepository


class UsersRepository(BaseRepository[Users]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Users, session)

    async def add_user(self, user: Dict[str, Any]) -> Users:
        return await self.create(**user)

    async def change_role(self, email: str, role: UserStatus) -> Users:
        query = (
            update(self.model)
            .where(self.model.email == email)
            .values(status=role)
            .returning(self.model)
        )
        result = await self.session.execute(query)
        await self.session.commit()
        return result.scalar_one()

    async def get_all_users(self) -> List[Users]:
        return await self.get_all()

    async def get_users_by_status(self, status: UserStatus) -> List[Users]:
        return await self.find_by(status=status)

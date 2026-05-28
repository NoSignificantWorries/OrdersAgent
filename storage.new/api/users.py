from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from database import UsersRepository, UserStatus, get_db_session

router = APIRouter(prefix="/users", tags=["users"])


class NewUserItem(BaseModel):
    email: str = Field(..., description="User's email")
    status: UserStatus = Field(UserStatus.STANDART, description="User's role")


class UserItem(BaseModel):
    id: int = Field(...)
    email: str = Field(..., description="User's email")
    status: UserStatus = Field(..., description="User's role")


class UserResponse(BaseModel):
    ok: bool
    user: UserItem


class UsersResponse(BaseModel):
    ok: bool
    count: int
    users: List[UserItem]


@router.post("/add", response_model=UserResponse)
async def add_user(body: NewUserItem, session: AsyncSession = Depends(get_db_session)):
    repo = UsersRepository(session)
    result = await repo.add_user(body.model_dump())
    return UserResponse(
        ok=True, user=UserItem(id=result.id, email=result.email, status=result.status)
    )


@router.get("/change-role", response_model=UserResponse)
async def change_user_role(
    email: str = Query(..., description="User's email"),
    role: UserStatus = Query(..., description="New user's role"),
    session: AsyncSession = Depends(get_db_session),
):
    repo = UsersRepository(session)
    result = await repo.change_role(email, role)
    return UserResponse(
        ok=True, user=UserItem(id=result.id, email=result.email, status=result.status)
    )


@router.get("/get-all", response_model=UsersResponse)
async def get_all_users(session: AsyncSession = Depends(get_db_session)):
    repo = UsersRepository(session)
    results = await repo.get_all()
    return UsersResponse(
        ok=True,
        count=len(results),
        users=[UserItem(id=u.id, email=u.email, status=u.status) for u in results],
    )


@router.get("/get-many-by-role")
async def get_users_by_role(
    role: UserStatus = Query(..., description="User's role"),
    session: AsyncSession = Depends(get_db_session),
):
    repo = UsersRepository(session)
    results = await repo.get_users_by_status(role)
    return UsersResponse(
        ok=True,
        count=len(results),
        users=[UserItem(id=u.id, email=u.email, status=u.status) for u in results],
    )

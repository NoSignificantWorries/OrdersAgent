import re
from datetime import datetime

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response
from pydantic import BaseModel, Field, field_validator

from app.routers import auth
from app.services.favorite_senders import (
    FavoriteSenderAlreadyExistsError,
    create_favorite_sender,
    delete_favorite_sender,
    list_favorite_senders,
    update_favorite_sender,
)


router = APIRouter(prefix="/api", tags=["favorite-senders"])


EMAIL_RE = re.compile(
    r"[a-z0-9!#$%&'*+/=?^_`{|}~-]+"
    r"(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
    r"@"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
)


def _normalize_email(value: str) -> str:
    normalized = value.strip().lower()

    if not normalized:
        raise ValueError("Укажите почтовый адрес")

    if (
        len(normalized) > 255
        or EMAIL_RE.fullmatch(normalized) is None
        or len(normalized.split("@", 1)[0]) > 64
    ):
        raise ValueError(
            "Укажите один адрес вида client@example.com без имени отправителя"
        )

    return normalized


def _normalize_comment(value: str | None) -> str | None:
    if value is None:
        return None

    return value.strip() or None


def _require_user(request: Request) -> None:
    if not auth.get_current_user(request):
        raise HTTPException(status_code=401, detail="Unauthorized")


class FavoriteSenderItem(BaseModel):
    id: int
    email: str
    comment: str | None = None
    created_at: datetime


class FavoriteSendersListResponse(BaseModel):
    items: list[FavoriteSenderItem]
    next_cursor: int | None = None
    has_more: bool


class CreateFavoriteSenderPayload(BaseModel):
    email: str = Field(..., max_length=255)
    comment: str | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _normalize_email(value)

    @field_validator("comment")
    @classmethod
    def validate_comment(cls, value: str | None) -> str | None:
        return _normalize_comment(value)


class UpdateFavoriteSenderPayload(BaseModel):
    email: str | None = Field(default=None, max_length=255)
    comment: str | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Почтовый адрес не может быть null")

        return _normalize_email(value)

    @field_validator("comment")
    @classmethod
    def validate_comment(cls, value: str | None) -> str | None:
        return _normalize_comment(value)


@router.get(
    "/favorite-senders",
    response_model=FavoriteSendersListResponse,
)
async def get_favorite_senders(
    request: Request,
    response: Response,
    cursor: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    search: str = Query(default="", max_length=255),
):
    _require_user(request)
    response.headers["Cache-Control"] = "no-store"

    return await list_favorite_senders(
        cursor=cursor,
        limit=limit,
        search=search.strip(),
    )


@router.post(
    "/favorite-senders",
    response_model=FavoriteSenderItem,
    status_code=201,
)
async def create_favorite_sender_endpoint(
    payload: CreateFavoriteSenderPayload,
    request: Request,
):
    _require_user(request)

    try:
        return await create_favorite_sender(
            email=payload.email,
            comment=payload.comment,
        )
    except FavoriteSenderAlreadyExistsError:
        raise HTTPException(
            status_code=409,
            detail="Этот адрес уже есть в списке избранных",
        )


@router.patch(
    "/favorite-senders/{sender_id}",
    response_model=FavoriteSenderItem,
)
async def update_favorite_sender_endpoint(
    payload: UpdateFavoriteSenderPayload,
    request: Request,
    sender_id: int = Path(..., ge=1),
):
    _require_user(request)

    changes = payload.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(status_code=400, detail="Нечего обновлять")

    try:
        updated_sender = await update_favorite_sender(
            sender_id=sender_id,
            changes=changes,
        )
    except FavoriteSenderAlreadyExistsError:
        raise HTTPException(
            status_code=409,
            detail="Этот адрес уже есть в списке избранных",
        )

    if updated_sender is None:
        raise HTTPException(
            status_code=404,
            detail="Запись избранного отправителя не найдена",
        )

    return updated_sender


@router.delete(
    "/favorite-senders/{sender_id}",
    status_code=204,
)
async def delete_favorite_sender_endpoint(
    request: Request,
    sender_id: int = Path(..., ge=1),
):
    _require_user(request)

    deleted = await delete_favorite_sender(sender_id=sender_id)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Запись избранного отправителя не найдена",
        )

    return Response(status_code=204)
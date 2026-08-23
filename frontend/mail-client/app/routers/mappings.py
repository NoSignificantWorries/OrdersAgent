from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, field_validator

from app.routers import auth
from app.services.mappings import (
    MappingSourceAlreadyExistsError,
    create_mapping,
    list_mappings,
    update_mapping,
)


router = APIRouter(prefix="/api", tags=["mappings"])


class MappingItem(BaseModel):
    source: str
    target: str
    article: str


class MappingsListResponse(BaseModel):
    items: list[MappingItem]
    next_cursor: str | None = None
    has_more: bool


class CreateMappingPayload(BaseModel):
    source: str = Field(..., max_length=255)
    target: str = Field(..., max_length=255)
    article: str = Field(..., max_length=255)

    @field_validator("source", "target", "article")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        normalized_value = value.strip()

        if not normalized_value:
            raise ValueError("Поле не может быть пустым")

        return normalized_value


class UpdateMappingPayload(BaseModel):
    source: str = Field(..., max_length=255)
    target: str = Field(..., max_length=255)
    article: str = Field(..., max_length=255)

    @field_validator("source", "target", "article")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        normalized_value = value.strip()

        if not normalized_value:
            raise ValueError("Поле не может быть пустым")

        return normalized_value


@router.get("/mappings", response_model=MappingsListResponse)
async def get_mappings(
    request: Request,
    response: Response,
    cursor: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=50, ge=1, le=100),
    search: str = Query(default="", max_length=255),
):
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    response.headers["Cache-Control"] = "no-store"

    normalized_cursor = cursor.strip() if cursor else None
    normalized_search = search.strip()

    return await list_mappings(
        cursor=normalized_cursor,
        limit=limit,
        search=normalized_search,
    )


@router.post("/mappings", response_model=MappingItem, status_code=201)
async def create_mapping_endpoint(
    payload: CreateMappingPayload,
    request: Request,
):
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        return await create_mapping(
            source=payload.source,
            target=payload.target,
            article=payload.article,
        )
    except MappingSourceAlreadyExistsError:
        raise HTTPException(
            status_code=409,
            detail=f"Материал «{payload.source}» уже существует",
        )


@router.patch("/mappings", response_model=MappingItem)
async def update_mapping_endpoint(
    payload: UpdateMappingPayload,
    request: Request,
):
    user = auth.get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    updated_mapping = await update_mapping(
        source=payload.source,
        target=payload.target,
        article=payload.article,
    )

    if not updated_mapping:
        raise HTTPException(
            status_code=404,
            detail=f"Материал «{payload.source}» не найден",
        )

    return updated_mapping
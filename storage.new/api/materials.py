from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from database import MaterialsRepository, get_db_session

router = APIRouter(prefix="/materials", tags=["materials"])


class MaterialItem(BaseModel):
    source: str = Field(..., description="Original material")
    target: Optional[str] = Field(None, description="Target value for request emails")
    article: Optional[str] = Field(
        None, description="Target value for callculation emails"
    )
    black_list: bool = Field(False, description="Blacklisted")


class BulkUpsertRequest(BaseModel):
    materials: List[MaterialItem] = Field(..., min_length=1, max_length=10000)


class BulkResponse(BaseModel):
    ok: bool
    count: int
    items: List[MaterialItem]


class BulkGetMaterialsRequest(BaseModel):
    sources: List[str] = Field(..., min_length=1, max_length=10000)


@router.post("/add-many", response_model=BulkResponse)
async def bulk_upsert_materials(
    body: BulkUpsertRequest, session: AsyncSession = Depends(get_db_session)
):
    repo = MaterialsRepository(session)

    material_dict = [m.model_dump() for m in body.materials]
    result = await repo.bulk_upsert_materials(material_dict)

    await repo.session.commit()

    return BulkResponse(
        ok=True,
        count=len(result),
        items=[
            MaterialItem(
                source=m.source,
                target=m.target,
                article=m.article,
                black_list=m.black_list,
            )
            for m in result
        ],
    )


@router.get("/get-all", response_model=BulkResponse)
async def get_all_users(session: AsyncSession = Depends(get_db_session)):
    repo = MaterialsRepository(session)
    results = await repo.get_all()
    return BulkResponse(
        ok=True,
        count=len(results),
        items=[
            MaterialItem(
                source=m.source,
                target=m.target,
                article=m.article,
                black_list=m.black_list,
            )
            for m in results
        ],
    )


@router.get("/get-by-sources", response_model=BulkResponse)
async def bulk_get_materials(
    body: BulkGetMaterialsRequest, session: AsyncSession = Depends(get_db_session)
):
    repo = MaterialsRepository(session)

    result = await repo.bulk_get_by_sources(body.sources)

    return BulkResponse(
        ok=True,
        count=len(result),
        items=[
            MaterialItem(
                source=m.source,
                target=m.target,
                article=m.article,
                black_list=m.black_list,
            )
            for m in result
        ],
    )

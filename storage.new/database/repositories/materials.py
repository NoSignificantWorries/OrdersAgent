from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import any_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.functions import coalesce

from ..models import Materials
from .base import BaseRepository


class MaterialsRepository(BaseRepository[Materials]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Materials, session)

    async def get_by_source(self, source: str) -> Optional[Materials]:
        return await self.find_one_by(source=source)

    async def bulk_get_by_sources(self, sources: List[str]) -> List[Materials]:
        query = select(Materials).where(Materials.source == any_(sources))
        result = await self.session.execute(query)
        return result.scalars().all()

    async def upsert_material(
        self,
        source: str,
        target: Optional[str] = None,
        article: Optional[str] = None,
        black_list: bool = False,
    ) -> Materials:
        stmt = pg_insert(Materials).values(
            source=source, target=target, article=article, black_list=black_list
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["source"],
            set_=dict(
                target=coalesce(stmt.excluded.target, Materials.target),
                article=coalesce(stmt.excluded.article, Materials.article),
                black_list=stmt.excluded.black_list,
            ),
        ).returning(Materials)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.scalar_one()

    async def bulk_upsert_materials(
        self, materials: List[Dict[str, Any]]
    ) -> Sequence[Materials]:
        all_keys = {"source", "target", "article", "black_list"}
        normalized = [{k: m.get(k) for k in all_keys} for m in materials]
        stmt = pg_insert(Materials).values(normalized)
        stmt = stmt.on_conflict_do_update(
            index_elements=["source"],
            set_=dict(
                target=coalesce(stmt.excluded.target, Materials.target),
                article=coalesce(stmt.excluded.article, Materials.article),
                black_list=stmt.excluded.black_list,
            ),
        ).returning(Materials)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.scalars().all()

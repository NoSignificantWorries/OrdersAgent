import asyncpg

from app.db import get_db_pool


class MappingSourceAlreadyExistsError(Exception):
    """Материал с таким source уже существует."""


def _escape_like(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def _mapping_record_to_dict(record: asyncpg.Record) -> dict:
    return {
        "source": str(record["source"] or ""),
        "target": str(record["target"] or ""),
        "article": str(record["article"] or ""),
    }


async def list_mappings(
    *,
    cursor: str | None,
    limit: int,
    search: str,
) -> dict:
    pool = await get_db_pool()

    normalized_search = _escape_like(search.strip())
    fetch_limit = limit + 1

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                source,
                target,
                article
            FROM mappings
            WHERE ($1 = ''
                OR source ILIKE '%' || $1 || '%' ESCAPE E'\\\\'
                OR target ILIKE '%' || $1 || '%' ESCAPE E'\\\\'
                OR article ILIKE '%' || $1 || '%' ESCAPE E'\\\\'
            )
            AND ($2::VARCHAR IS NULL OR source > $2)
            ORDER BY source ASC
            LIMIT $3
            """,
            normalized_search,
            cursor,
            fetch_limit,
        )

    has_more = len(rows) > limit
    page_rows = rows[:limit]

    items = [_mapping_record_to_dict(row) for row in page_rows]
    next_cursor = items[-1]["source"] if has_more and items else None

    return {
        "items": items,
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


async def create_mapping(
    *,
    source: str,
    target: str,
    article: str,
) -> dict:
    pool = await get_db_pool()

    try:
        async with pool.acquire() as conn:
            record = await conn.fetchrow(
                """
                INSERT INTO mappings (
                    source,
                    target,
                    article
                )
                VALUES ($1, $2, $3)
                RETURNING
                    source,
                    target,
                    article
                """,
                source,
                target,
                article,
            )
    except asyncpg.UniqueViolationError as error:
        raise MappingSourceAlreadyExistsError from error

    return _mapping_record_to_dict(record)


async def update_mapping(
    *,
    source: str,
    target: str,
    article: str,
) -> dict | None:
    pool = await get_db_pool()

    async with pool.acquire() as conn:
        record = await conn.fetchrow(
            """
            UPDATE mappings
            SET
                target = $2,
                article = $3
            WHERE source = $1
            RETURNING
                source,
                target,
                article
            """,
            source,
            target,
            article,
        )

    if not record:
        return None

    return _mapping_record_to_dict(record)
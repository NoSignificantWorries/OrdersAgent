import asyncpg

from app.db import get_db_pool


class FavoriteSenderAlreadyExistsError(Exception):
    """Адрес уже есть в общем списке избранных."""


def _escape_like(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def _favorite_sender_record_to_dict(record: asyncpg.Record) -> dict:
    return {
        "id": record["id"],
        "email": record["email"],
        "comment": record["comment"],
        "created_at": record["created_at"],
    }


async def list_favorite_senders(
    *,
    cursor: int | None,
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
                id,
                email,
                comment,
                created_at
            FROM favorite_senders
            WHERE (
                $1::text = ''
                OR email ILIKE '%' || $1 || '%' ESCAPE E'\\\\'
                OR comment ILIKE '%' || $1 || '%' ESCAPE E'\\\\'
            )
            AND ($2::bigint IS NULL OR id > $2)
            ORDER BY id ASC
            LIMIT $3
            """,
            normalized_search,
            cursor,
            fetch_limit,
        )

    has_more = len(rows) > limit
    page_rows = rows[:limit]
    items = [_favorite_sender_record_to_dict(row) for row in page_rows]

    return {
        "items": items,
        "next_cursor": items[-1]["id"] if has_more and items else None,
        "has_more": has_more,
    }


async def create_favorite_sender(
    *,
    email: str,
    comment: str | None,
) -> dict:
    pool = await get_db_pool()

    try:
        async with pool.acquire() as conn:
            record = await conn.fetchrow(
                """
                INSERT INTO favorite_senders (
                    email,
                    comment
                )
                VALUES ($1, $2)
                RETURNING
                    id,
                    email,
                    comment,
                    created_at
                """,
                email,
                comment,
            )
    except asyncpg.UniqueViolationError as error:
        if error.constraint_name != "uq_favorite_senders_email_lower":
            raise
        raise FavoriteSenderAlreadyExistsError from error

    return _favorite_sender_record_to_dict(record)


async def update_favorite_sender(
    *,
    sender_id: int,
    changes: dict,
) -> dict | None:
    pool = await get_db_pool()

    # Имена столбцов берём только из фиксированного списка.
    set_clauses: list[str] = []
    params: list[object] = [sender_id]

    for field in ("email", "comment"):
        if field in changes:
            params.append(changes[field])
            set_clauses.append(f"{field} = ${len(params)}")

    if not set_clauses:
        raise ValueError("Нечего обновлять")

    query = f"""
        UPDATE favorite_senders
        SET {", ".join(set_clauses)}
        WHERE id = $1
        RETURNING
            id,
            email,
            comment,
            created_at
    """

    try:
        async with pool.acquire() as conn:
            record = await conn.fetchrow(query, *params)
    except asyncpg.UniqueViolationError as error:
        if error.constraint_name != "uq_favorite_senders_email_lower":
            raise
        raise FavoriteSenderAlreadyExistsError from error

    if record is None:
        return None

    return _favorite_sender_record_to_dict(record)


async def delete_favorite_sender(*, sender_id: int) -> bool:
    pool = await get_db_pool()

    async with pool.acquire() as conn:
        deleted_id = await conn.fetchval(
            """
            DELETE FROM favorite_senders
            WHERE id = $1
            RETURNING id
            """,
            sender_id,
        )

    return deleted_id is not None
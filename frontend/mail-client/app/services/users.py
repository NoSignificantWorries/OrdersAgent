from datetime import datetime
from typing import Optional

import asyncpg

from app.db import get_db_pool


async def get_or_create_user_by_email(
    email: str,
    login: str,
    name: Optional[str] = None,
) -> dict:
    """
    Возвращает пользователя из таблицы users по email.
    Если нет — создаёт, а роль выставляет БД по DEFAULT.
    """

    pool = await get_db_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, login, email, role
            FROM users
            WHERE email = $1
            """,
            email,
        )
        if row:
            return {
                "id": row["id"],
                "login": row["login"],
                "email": row["email"],
                "role": row["role"],
            }

        fake_password = "oauth_yandex"
        row = await conn.fetchrow(
            """
            INSERT INTO users (login, email, pass_hash)
            VALUES ($1, $2, crypt($3, gen_salt('bf')))
            RETURNING id, login, email, role
            """,
            login or email,
            email,
            fake_password,
        )

        return {
            "id": row["id"],
            "login": row["login"],
            "email": row["email"],
            "role": row["role"],
        }


async def update_user_mail_tokens(
    user_id: int,
    access_token: str,
    refresh_token: Optional[str],
    access_expires_at: datetime,
) -> dict:
    """
    Обновляет OAuth-токены Яндекс Почты у пользователя в таблице users.

    Требует, чтобы в users были поля:
    - mail_access_token TEXT
    - mail_refresh_token TEXT
    - mail_access_expires_at TIMESTAMPTZ
    """

    pool = await get_db_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE users
            SET
                mail_access_token = $1,
                mail_refresh_token = $2,
                mail_access_expires_at = $3
            WHERE id = $4
            RETURNING id, email, mail_access_expires_at
            """,
            access_token,
            refresh_token,
            access_expires_at,
            user_id,
        )

        if not row:
            raise ValueError(f"user not found: id={user_id}")

        return {
            "id": row["id"],
            "email": row["email"],
            "mail_access_expires_at": row["mail_access_expires_at"],
        }
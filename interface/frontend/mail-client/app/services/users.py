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
    Если нет — создаёт с role='manager'.
    """

    pool = await get_db_pool()

    async with pool.acquire() as conn:
        # 1. Пытаемся найти
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

        # 2. Если нет — создаём
        # pass_hash сейчас заглушка, так как авторизация идёт через Яндекс
        fake_password = "oauth_yandex"  # можно сгенерировать случайно
        # crypt(...) вызывается в твоей sql-функции, здесь можно хранить просто заглушку,
        # либо вызвать create_admin_user для админа, но для менеджера INSERT обычный.
        row = await conn.fetchrow(
            """
            INSERT INTO users (login, email, pass_hash, role)
            VALUES ($1, $2, crypt($3, gen_salt('bf')), 'manager')
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
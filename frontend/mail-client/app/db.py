import asyncpg
from app.config import settings  # где уже лежат данные соединения

_db_pool: asyncpg.Pool | None = None


async def get_db_pool() -> asyncpg.Pool:
    global _db_pool
    if _db_pool is None:
        _db_pool = await asyncpg.create_pool(
            host=settings.db_host,
            port=settings.db_port,
            user=settings.db_user,
            password=settings.db_password,
            database=settings.db_name,
            min_size=1,
            max_size=5,
        )
    return _db_pool
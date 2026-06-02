import asyncio

import database as db
from config import DatabaseConfig


async def main():
    db.DatabaseManager.init(
        DatabaseConfig.from_env().async_dsn, pool_size=1, echo=False
    )
    await db.DatabaseManager.create_tables(checkfirst=True)
    await db.DatabaseManager.close()


if __name__ == "__main__":
    asyncio.run(main())

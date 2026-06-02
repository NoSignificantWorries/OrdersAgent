from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

import cloud
import config as conf
import database as db


class DataService:
    def __init__(self) -> None:
        self.db_config = conf.DatabaseConfig.from_env()
        self.cloud_config = conf.MinIOConfig.from_env()
        self.session: Optional[AsyncSession] = None
        self.cloud: cloud.AsyncMinIOClient

    async def init_database(
        self,
        pool_size: int = 5,
        echo: bool = False,
    ) -> None:
        db.DatabaseManager.init(
            self.db_config.async_dsn, pool_size=pool_size, echo=echo
        )
        self.session = db.get_db_session()

    async def close_database(self) -> None:
        await db.DatabaseManager.close()

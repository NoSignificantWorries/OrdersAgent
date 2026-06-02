from contextlib import asynccontextmanager
from typing import AsyncGenerator, ClassVar, Optional

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class DatabaseManager:
    _instance: ClassVar[Optional["DatabaseManager"]] = None
    _engine: ClassVar[Optional[AsyncEngine]] = None
    _session_factory: ClassVar[Optional[async_sessionmaker[AsyncSession]]] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def init(
        cls, database_url: str, pool_size: int = 5, echo: bool = False
    ) -> "DatabaseManager":
        instance = cls()

        if cls._engine is not None:
            return instance

        cls._engine = create_async_engine(
            database_url,
            pool_size=pool_size,
            max_overflow=2,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=echo,
        )

        cls._session_factory = async_sessionmaker(
            cls._engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )

        return instance

    @classmethod
    async def create_tables(cls, checkfirst: bool = True) -> None:
        if cls._engine is None:
            raise RuntimeError(
                "Database not initialized. Call DatabaseManager.init() first"
            )

        if checkfirst:
            async with cls._engine.connect() as conn:

                def get_table_names(connection):
                    inspector = inspect(connection)
                    return inspector.get_table_names()

                existing_tables = await conn.run_sync(get_table_names)
                if existing_tables:
                    logger.info(f"Tables already exists: {existing_tables}")

        # async with cls._engine.connect() as conn:
        #     await conn.run_sync(
        #         Base.metadata.create_all(cls._engine, checkfirst=checkfirst)
        #     )
        async with cls._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @classmethod
    async def health_check(cls) -> bool:
        try:
            async with cls._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                await conn.commit()
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    @classmethod
    def get_engine(cls) -> AsyncEngine:
        if cls._engine is None:
            raise RuntimeError(
                "Database not initialized. Call DatabaseManager.init() first"
            )
        return cls._engine

    @classmethod
    def get_session(cls) -> AsyncSession:
        if cls._session_factory is None:
            raise RuntimeError(
                "Database not initialized. Call DatabaseManager.init() first"
            )
        return cls._session_factory()

    @classmethod
    @asynccontextmanager
    async def session_scope(cls) -> AsyncGenerator[AsyncSession, None]:
        session = cls.get_session()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    @classmethod
    async def close(cls):
        if cls._engine:
            await cls._engine.dispose()
            cls._engine = None
            cls._session_factory = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with DatabaseManager.session_scope() as session:
        yield session


def get_db_session() -> AsyncSession:
    return DatabaseManager.get_session()

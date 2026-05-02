import os
import asyncio
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from sqlalchemy import Column, String, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base


@dataclass
class DatabaseConfig:
    host: str = "localhost"
    port: int = 5432
    database: str = "materials_db"
    user: str = "user"
    password: str = "pass"

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        return cls(
            database=os.getenv("POSTGRES_DB", "materials_db"),
            user=os.getenv("POSTGRES_USER", "user"),
            password=os.getenv("POSTGRES_PASSWORD", "pass")
        )

    @property
    def dsn(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


Base = declarative_base()


class Mapping(Base):
    __tablename__ = 'mappings'
    
    source = Column(String, primary_key=True, index=True)
    target = Column(String, nullable=False)


class DatabaseManager:
    _instance = None
    _engine = None
    _session_factory = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    async def init(cls, database_url: str, pool_size: int = 20, max_overflow: int = 1):
        if cls._engine is not None:
            return

        async_url = database_url.replace('postgresql://', 'postgresql+asyncpg://')
        cls._engine = create_async_engine(
            async_url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False
        )

        cls._session_factory = async_sessionmaker(
            cls._engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

        async with cls._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @classmethod
    def get_session(cls) -> AsyncSession:
        if cls._session_factory is None:
            raise RuntimeError("Database not initialized. Call DatabaseManager.init() first")
        return cls._session_factory()

    @classmethod
    async def close(cls):
        if cls._engine:
            await cls._engine.dispose()
            cls._engine = None
            cls._session_factory = None


class MaterialMatcherORM:
    def __init__(self) -> None:
        pass
    
    async def find_target(self, source: str) -> Optional[str]:
        async with DatabaseManager.get_session() as session:
            result = await session.get(Mapping, source)
            if result:
                return result.target
            return None
    
    async def add_source(self, source: str, target: str) -> None:
        async with DatabaseManager.get_session() as session:
            mapping = Mapping(source=source, target=target)
            session.add(mapping)
            try:
                await session.commit()
            except Exception:
                await session.rollback()
                pass

    async def batch_find(self, sources: List[str]) -> Dict[str, Optional[str]]:
        if not sources:
            return {}
    
        async with DatabaseManager.get_session() as session:
            query = select(Mapping).where(Mapping.source.in_(sources))
            result = await session.execute(query)
            mappings = result.scalars().all()
            
            result_dict = {m.source: m.target for m in mappings}
            
            for source in sources:
                if source not in result_dict:
                    result_dict[source] = None
        
        return result_dict

    async def batch_add(self, mappings: List[Tuple[str, str]]) -> None:
        async with DatabaseManager.get_session() as session:
            for source, target in mappings:
                mapping = Mapping(source=source, target=target)
                session.add(mapping)
            try:
                await session.commit()
            except Exception:
                await session.rollback()


async def initialize_app(pool_size: int = 20, max_overflow: int = 1):
    config = DatabaseConfig().from_env()
    await DatabaseManager.init(
        config.dsn,
        pool_size=pool_size,
        max_overflow=max_overflow
    )


def development() -> None:
    lib = MaterialMatcherORM()

    async def run():
        await initialize_app()

        await lib.batch_add([("4top", "test"), ("4", "4GO"), ("6", "6MTP")])
        res = await lib.batch_find(["4top", "6", "12", "4"])
        print(res)

        await DatabaseManager.close()

    asyncio.run(run())


if __name__ == "__main__":
    development()


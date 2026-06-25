import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Generator, Optional

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker


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
            host=os.getenv("POSTGRES_HOST", "localhost"),
            database=os.getenv("POSTGRES_DB", "materials_db"),
            user=os.getenv("POSTGRES_USER", "user"),
            password=os.getenv("POSTGRES_PASSWORD", "pass"),
        )

    @property
    def dsn(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


Base = declarative_base()


class DatabaseManager:
    _instance = None
    _engine: Optional[Engine] = None
    _session_factory: Optional[sessionmaker] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def init(cls, database_url: str, pool_size: int = 5, echo: bool = False) -> None:
        if cls._instance is not None:
            return

        cls._engine = create_engine(
            database_url,
            pool_size=pool_size,
            max_overflow=2,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=echo,
        )

        cls._session_factory = sessionmaker(
            cls._engine, class_=Session, expire_on_commit=False
        )

        Base.metadata.create_all(cls._engine)

    @classmethod
    def get_session(cls) -> Session:
        if cls._session_factory is None:
            raise RuntimeError(
                "Database not initialized. Call DatabaseManager.init() first"
            )
        return cls._session_factory()

    @classmethod
    @contextmanager
    def session_scope(cls) -> Generator[Session, None, None]:
        session = cls.get_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @classmethod
    def close(cls):
        if cls._engine:
            cls._engine.dispose()
            cls._engine = None
            cls._session_factory = None


def init_database(pool_size: int = 5, echo: bool = False):
    config = DatabaseConfig.from_env()
    DatabaseManager.init(config.dsn, pool_size=pool_size, echo=echo)

import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import ClassVar, Generator, Optional

from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.orm import Session, declarative_base, sessionmaker

formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("materials_app")
logger.setLevel(logging.DEBUG)


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

    @property
    def async_dsn(self) -> str:
        return self.dsn.replace("postgresql", "postgresql+asyncpg")


Base = declarative_base()


class DatabaseManager:
    _instance: ClassVar[Optional["DatabaseManager"]] = None
    _engine: ClassVar[Optional[Engine]] = None
    _session_factory: ClassVar[Optional[sessionmaker]] = None

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

        cls._engine = create_engine(
            database_url,
            pool_size=pool_size,
            max_overflow=2,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=echo,
        )

        cls._session_factory = sessionmaker(
            cls._engine, class_=Session, expire_on_commit=False, autoflush=False
        )

        return instance

    @classmethod
    def create_tables(cls, checkfirst: bool = True) -> None:
        if cls._engine is None:
            raise RuntimeError(
                "Database not initialized. Call DatabaseManager.init() first"
            )

        if checkfirst:
            inspector = inspect(cls._engine)
            existing_tables = inspector.get_table_names()
            if existing_tables:
                logger.info(f"Tables already exists: {existing_tables}")

        Base.metadata.create_all(cls._engine, checkfirst=checkfirst)

    @classmethod
    def health_check(cls) -> bool:
        try:
            with cls._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    @classmethod
    def get_engine(cls) -> Engine:
        if cls._engine is None:
            raise RuntimeError(
                "Database not initialized. Call DatabaseManager.init() first"
            )
        return cls._engine

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


def get_db() -> Generator[Session, None, None]:
    with DatabaseManager.session_scope() as session:
        yield session


def get_db_session() -> Session:
    return DatabaseManager.get_session()


def init_database(
    pool_size: int = 5,
    echo: bool = False,
    create_tables: bool = True,
    checkfirst: bool = True,
):
    config = DatabaseConfig.from_env()
    DatabaseManager.init(config.dsn, pool_size=pool_size, echo=echo)
    if create_tables:
        DatabaseManager.create_tables(checkfirst=checkfirst)
        logger.info("Database tables created/verified")

import logging
import os

from pydantic import BaseModel, Field

formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("materials_app")
logger.setLevel(logging.DEBUG)


class DatabaseConfig(BaseModel):
    host: str = Field("localhost", description="Postgresql host")
    port: int = Field(5432, description="Postgresql port")
    database: str = Field("mails_data", description="Database name")
    user: str = Field("dmitry", description="Posgres user")
    password: str = Field("pass", description="Postgres password")

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        return cls(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=os.getenv("POSTGRES_DB", "mails_data"),
            user=os.getenv("POSTGRES_USER", "dmitry"),
            password=os.getenv("POSTGRES_PASSWORD", "pass"),
        )

    @property
    def dsn(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

    @property
    def async_dsn(self) -> str:
        return self.dsn.replace("postgresql", "postgresql+asyncpg")


class MinIOConfig(BaseModel):
    endpoint: str = Field("localhost:9000", description="MinIO server endpoint")
    access_key: str = Field("minioadmin", description="MinIO user")
    secret_key: str = Field("minioadmin", description="MinIO password")

    @classmethod
    def from_env(cls) -> "MinIOConfig":
        return cls(
            endpoint=os.getenv("MINIO_ENDPOINT", "localhost:9000"),
            access_key=os.getenv("MINIO_ROOT_USER", "minioadmin"),
            secret_key=os.getenv("MINIO_ROOT_PASSWORD", "minioadmin"),
        )


class YandexConfig(BaseModel):
    redirect_uri: str = Field(
        "http://localhost:8000/callback", description="Redirect link for service"
    )
    client_id: str = Field(..., description="Client id")
    client_secret: str = Field(..., description="Client secret")
    token_url: str = Field(
        "https://oauth.yandex.ru/token", description="Yandex access token"
    )

    @classmethod
    def from_env(cls) -> "YandexConfig":
        return cls(
            redirect_uri=os.getenv(
                "YANDEX_REDIRECT_URI", "http://localhost:8000/callback"
            ),
            client_id=os.getenv("YANDEX_CLIENT_ID", ""),
            client_secret=os.getenv("YANDEX_CLIENT_SECRET", ""),
            token_url=os.getenv("YANDEX_TOKEN_URL", "https://oauth.yandex.ru/token"),
        )

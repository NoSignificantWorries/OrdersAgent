# app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv
import os


load_dotenv()


class Settings(BaseSettings):
    # Настройки приложения
    app_name: str = os.getenv("APP_NAME", "Почта менеджера")
    debug: bool = os.getenv("DEBUG", "True").lower() == "true"

    # Настройки сервера
    host: str = "127.0.0.1"
    port: int = 8000

    # Яндекс OAuth
    yandex_client_id: str = os.getenv("YANDEX_CLIENT_ID", "")
    yandex_client_secret: str = os.getenv("YANDEX_CLIENT_SECRET", "")
    yandex_redirect_uri: str = os.getenv(
        "YANDEX_REDIRECT_URI",
        "http://localhost:8000/callback",
    )

    # URL Яндекса
    yandex_auth_url: str = "https://oauth.yandex.ru/authorize"
    yandex_token_url: str = "https://oauth.yandex.ru/token"
    yandex_user_info_url: str = "https://login.yandex.ru/info"

    # Подключение к Postgres
    # 1) пробуем DB_*, если их нет — используем POSTGRES_*
    db_host: str = os.getenv("DB_HOST", os.getenv("POSTGRES_HOST", "localhost"))
    db_port: int = int(os.getenv("DB_PORT", os.getenv("POSTGRES_PORT", "5432")))
    db_user: str = os.getenv("DB_USER", os.getenv("POSTGRES_USER", ""))
    db_password: str = os.getenv("DB_PASSWORD", os.getenv("POSTGRES_PASSWORD", ""))
    db_name: str = os.getenv("DB_NAME", os.getenv("POSTGRES_DB", ""))

    # Безопасность
    secret_key: str = os.getenv("SECRET_KEY", "dev-secret-key-123")

    # ВАЖНО: игнорируем лишние переменные из .env (POSTGRES_*)
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
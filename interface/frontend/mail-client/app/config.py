# app/config.py
from pydantic_settings import BaseSettings
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
    yandex_redirect_uri: str = os.getenv("YANDEX_REDIRECT_URI", "http://localhost:8000/callback")
    
    # URL Яндекса
    yandex_auth_url: str = "https://oauth.yandex.ru/authorize"
    yandex_token_url: str = "https://oauth.yandex.ru/token"
    yandex_user_info_url: str = "https://login.yandex.ru/info"
    
    # Безопасность
    secret_key: str = os.getenv("SECRET_KEY", "dev-secret-key-123")
    
    class Config:
        env_file = ".env"

settings = Settings()
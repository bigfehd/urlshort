"""Application configuration using Pydantic Settings."""
import logging
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    # App
    APP_NAME: str = "URL Shortener"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENV: Literal["development", "staging", "production"] = "development"

    # Database
    DATABASE_URL: str = (
        "postgresql+asyncpg://urlshort:urlshort@localhost:5432/urlshort"
    )
    DATABASE_ECHO: bool = False

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_TTL: int = 86400  # 24 hours

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # ShortURL Config
    BASE_URL: str = "http://localhost:8000"
    SHORT_CODE_LENGTH: int = 6
    MAX_URL_LENGTH: int = 2048

    # API
    API_TITLE: str = "URL Shortener API"
    API_VERSION: str = "1.0.0"
    API_DESCRIPTION: str = "A production-grade distributed URL shortener with analytics"

    # Security
    MAX_REQUESTS_PER_MINUTE: int = 100

    # Logging
    LOG_LEVEL: str = "INFO"

    @property
    def database_dsn(self) -> str:
        """Get database DSN."""
        return self.DATABASE_URL

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.ENV == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.ENV == "production"


@lru_cache
def get_settings() -> Settings:
    """Get settings singleton."""
    return Settings()


def setup_logging(log_level: str = "INFO") -> None:
    """Configure logging."""
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

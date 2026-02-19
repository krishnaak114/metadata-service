"""
Centralized configuration management using Pydantic BaseSettings.

All settings are environment-driven via .env file or environment variables.
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables or .env file.

    Follows the project-wide pattern of optional services with graceful degradation.
    The database is the only required external dependency.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────
    app_name: str = "Metadata Service"
    environment: str = "development"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"

    # ── Database (required) ───────────────────────────────────────────
    database_url: str = Field(
        default="mysql+pymysql://metadata_user:metadata_pass@localhost:3306/metadata_db",
        description="SQLAlchemy connection string for MySQL",
    )

    # DB pool settings
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_pre_ping: bool = True

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v.startswith(("mysql+pymysql://", "mysql+mysqlconnector://")):
            raise ValueError("Only MySQL is supported. Use 'mysql+pymysql://' scheme.")
        return v

    # ── Pagination ────────────────────────────────────────────────────
    default_page_size: int = 50
    max_page_size: int = 200

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in ("production", "prod")


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance (singleton pattern)."""
    return Settings()


# Module-level convenience alias — mirrors SuperClaims / Kairos pattern
settings = get_settings()

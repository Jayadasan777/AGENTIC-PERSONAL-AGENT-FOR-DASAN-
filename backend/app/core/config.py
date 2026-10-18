"""Application configuration and typed environment settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings validated via Pydantic.

    All sensitive fields use SecretStr to prevent accidental leakage in logs.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Core Application Settings
    ENVIRONMENT: Literal["development", "testing", "production"] = "development"
    APP_NAME: str = "AURA"
    DEBUG: bool = False
    API_V1_STR: str = "/api/v1"

    # Security Configuration
    # Uses SecretStr to prevent printing credentials in __repr__ or error logs
    SECRET_KEY: SecretStr = Field(
        default=SecretStr("insecure_dev_key_must_be_changed_in_prod_32chars"),
        description="Cryptographic secret key for signing tokens",
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Database Configuration (PostgreSQL + pgvector)
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "aura_user"
    POSTGRES_PASSWORD: SecretStr = Field(
        default=SecretStr("aura_password_placeholder"),
        description="Database user password",
    )
    POSTGRES_DB: str = "aura_db"

    # Model Provider Configuration
    MODEL_PROVIDER: Literal["mock", "ollama", "llamacpp"] = "mock"
    MODEL_BASE_URL: str = "http://localhost:11434"
    MODEL_NAME: str = "qwen2.5:3b-instruct-q4_K_M"

    # Embedding Configuration
    EMBEDDING_PROVIDER: Literal["mock", "ollama"] = "mock"
    EMBEDDING_MODEL: str = "nomic-embed-text"
    EMBEDDING_DIM: int = 384

    # Storage Settings
    STORAGE_LOCAL_DIR: str = "./data/storage"
    MAX_UPLOAD_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB

    @property
    def async_database_uri(self) -> str:
        """Constructs an asyncpg PostgreSQL connection string."""
        password = self.POSTGRES_PASSWORD.get_secret_value()
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{password}@"
            f"{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key_length(cls, v: SecretStr) -> SecretStr:
        """Ensure secret key is at least 32 characters long for cryptographic security."""
        raw = v.get_secret_value()
        if len(raw) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")
        return v


@lru_cache
def get_settings() -> Settings:
    """Returns a cached instance of Settings to avoid re-reading files on every call."""
    return Settings()


settings = get_settings()

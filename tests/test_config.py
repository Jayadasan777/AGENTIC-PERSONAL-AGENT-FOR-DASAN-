"""Unit tests for typed application configuration."""

import pytest
from pydantic import ValidationError

from backend.app.core.config import Settings


def test_settings_default_values() -> None:
    """Verify that default settings instantiate with expected defaults."""
    settings = Settings()
    assert settings.APP_NAME == "AURA"
    assert settings.ENVIRONMENT == "development"
    assert settings.API_V1_STR == "/api/v1"
    assert settings.MODEL_PROVIDER == "mock"


def test_secret_str_redaction() -> None:
    """Verify that SecretStr prevents plain-text exposure in string representations."""
    settings = Settings()
    # str(settings.SECRET_KEY) must show '**********', never the raw string
    assert "insecure_dev_key" not in str(settings.SECRET_KEY)
    assert "**********" in str(settings.SECRET_KEY)
    expected_key = "insecure_dev_key_must_be_changed_in_prod_32chars"
    assert settings.SECRET_KEY.get_secret_value() == expected_key


def test_secret_key_minimum_length_validation() -> None:
    """Verify that a secret key shorter than 32 characters raises a validation error."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(SECRET_KEY="too_short_key")  # type: ignore[arg-type]

    assert "at least 32 characters long" in str(exc_info.value)


def test_async_database_uri_builder() -> None:
    """Verify that the database URI is formatted properly for asyncpg."""
    settings = Settings(
        POSTGRES_SERVER="db.internal",
        POSTGRES_PORT=5433,
        POSTGRES_USER="test_user",
        POSTGRES_PASSWORD="test_password_placeholder",  # type: ignore[arg-type]
        POSTGRES_DB="test_db",
    )
    expected_uri = (
        "postgresql+asyncpg://test_user:test_password_placeholder@db.internal:5433/test_db"
    )
    assert settings.async_database_uri == expected_uri

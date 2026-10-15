"""Health and readiness check endpoints."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter

from backend.app import __version__
from backend.app.core.config import get_settings
from backend.app.core.logging import get_request_id

router = APIRouter()


@router.get("/health", response_model=dict[str, Any])
async def api_health() -> dict[str, Any]:
    """Return API v1 subsystem status, current timestamp, and active environment."""
    settings = get_settings()
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "version": __version__,
        "timestamp": datetime.now(UTC).isoformat(),
        "request_id": get_request_id(),
    }

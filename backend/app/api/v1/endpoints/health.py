"""Health and readiness check endpoints."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from backend.app import __version__
from backend.app.core.config import get_settings
from backend.app.core.logging import get_request_id
from backend.app.db.session import async_session_factory

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


@router.get("/health/live", response_model=dict[str, str])
async def liveness_probe() -> dict[str, str]:
    """Kubernetes/Docker liveness probe: verifies the ASGI worker is running."""
    return {"status": "alive"}


@router.get("/health/ready", response_model=dict[str, Any])
async def readiness_probe(response: Response) -> dict[str, Any]:
    """Readiness probe: validates connectivity to critical dependencies (PostgreSQL)."""
    db_connected = False
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
            db_connected = True
    except Exception:
        db_connected = False

    is_ready = db_connected
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if is_ready else "not_ready",
        "database": "connected" if db_connected else "disconnected",
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/health/deployment", response_model=dict[str, Any])
async def deployment_status() -> dict[str, Any]:
    """Deployment metadata probe for production orchestrators."""
    settings = get_settings()
    return {
        "status": "operational",
        "app_name": settings.APP_NAME,
        "version": __version__,
        "environment": settings.ENVIRONMENT,
        "proxy_compatible": True,
        "features": {
            "rag": True,
            "agent_harness": True,
            "sandbox": True,
            "automation": True,
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }

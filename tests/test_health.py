"""Integration tests for FastAPI health endpoints, correlation middleware, and error handling."""

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app


@pytest.mark.asyncio
async def test_root_health_endpoint() -> None:
    """Verify GET /health returns 200 with basic liveness payload and request ID header."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app"] == "AURA"
    assert "version" in data
    assert "X-Request-ID" in response.headers
    assert response.headers["X-Request-ID"].startswith("req-")


@pytest.mark.asyncio
async def test_api_v1_health_endpoint() -> None:
    """Verify GET /api/v1/health returns detailed readiness schema."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app"] == "AURA"
    assert data["environment"] == "development"
    assert "timestamp" in data
    assert "request_id" in data
    assert data["request_id"] == response.headers["X-Request-ID"]


@pytest.mark.asyncio
async def test_custom_request_id_header_propagation() -> None:
    """Verify that an incoming X-Request-ID header is honored and preserved in the response."""
    custom_id = "client-trace-777888"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health", headers={"X-Request-ID": custom_id})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == custom_id
    assert response.json()["request_id"] == custom_id

"""FastAPI application factory and main entry point for AURA."""

import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from backend.app import __version__
from backend.app.api.v1.router import api_v1_router
from backend.app.core.config import get_settings
from backend.app.core.logging import get_request_id, set_request_id, setup_logging

logger = logging.getLogger("aura.server")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan context manager for startup and shutdown tasks."""
    setup_logging()
    settings = get_settings()
    logger.info("AURA backend starting up in %s environment", settings.ENVIRONMENT)
    yield
    logger.info("AURA backend shutting down cleanly")


def create_application() -> FastAPI:
    """Factory function initializing the configured FastAPI application instance."""
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version=__version__,
        description="AURA - Adaptive Unified Reasoning Assistant API",
        docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
        redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
        openapi_url="/openapi.json" if settings.ENVIRONMENT != "production" else None,
        lifespan=lifespan,
    )

    # --------------------------------------------------------------------------
    # Middleware: Request ID Propagation & Latency Tracking
    # --------------------------------------------------------------------------
    @app.middleware("http")
    async def request_id_and_logging_middleware(
        request: Request, call_next: Any
    ) -> Response:
        incoming_id = request.headers.get("X-Request-ID")
        request_id = incoming_id if incoming_id else f"req-{uuid.uuid4().hex[:12]}"
        set_request_id(request_id)

        start_time = time.perf_counter()
        response: Response = await call_next(request)
        process_time_ms = (time.perf_counter() - start_time) * 1000

        response.headers["X-Request-ID"] = request_id
        logger.info(
            "%s %s -> %d (%.2f ms)",
            request.method,
            request.url.path,
            response.status_code,
            process_time_ms,
        )
        return response

    # --------------------------------------------------------------------------
    # Global Safe Exception Handler
    # --------------------------------------------------------------------------
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("Unhandled server exception processing %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "request_id": get_request_id(),
            },
            headers={"X-Request-ID": get_request_id()},
        )

    # --------------------------------------------------------------------------
    # Root Health Check (Liveness Probe)
    # --------------------------------------------------------------------------
    @app.get("/health", tags=["Liveness"])
    async def root_health() -> dict[str, str]:
        return {
            "status": "healthy",
            "app": settings.APP_NAME,
            "version": __version__,
        }

    # --------------------------------------------------------------------------
    # Include Versioned API Routes
    # --------------------------------------------------------------------------
    app.include_router(api_v1_router, prefix=settings.API_V1_STR)

    return app


app = create_application()

"""Structured JSON logging and request correlation ID management."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from backend.app.core.config import get_settings

# Context variable storing the correlation/request ID for the active async task
request_id_var: ContextVar[str] = ContextVar("request_id", default="system")


def get_request_id() -> str:
    """Return the current request ID from context."""
    return request_id_var.get()


def set_request_id(request_id: str) -> None:
    """Set the request ID for the active async execution context."""
    request_id_var.set(request_id)


class JSONFormatter(logging.Formatter):
    """Custom formatter outputting log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        settings = get_settings()
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
            "environment": settings.ENVIRONMENT,
        }

        # Include exception traceback if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def setup_logging() -> None:
    """Configure root logger to output structured JSON to standard output."""
    settings = get_settings()
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove default handlers to prevent duplicate lines
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root_logger.addHandler(handler)

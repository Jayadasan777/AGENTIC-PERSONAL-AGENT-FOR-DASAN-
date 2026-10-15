"""Unit tests for structured JSON logging and request ID context tracking."""

import json
import logging

from backend.app.core.logging import JSONFormatter, get_request_id, set_request_id


def test_request_id_context_var() -> None:
    """Verify get and set functions for async request ID context variable."""
    assert get_request_id() == "system"
    set_request_id("req-abc-123")
    assert get_request_id() == "req-abc-123"
    set_request_id("system")


def test_json_formatter_structure() -> None:
    """Verify that JSONFormatter outputs a valid JSON string with required schema fields."""
    formatter = JSONFormatter()
    set_request_id("req-trace-999")

    record = logging.LogRecord(
        name="aura.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=25,
        msg="Test event %s",
        args=("occurred",),
        exc_info=None,
    )

    output = formatter.format(record)
    data = json.loads(output)

    assert data["level"] == "INFO"
    assert data["logger"] == "aura.test"
    assert data["message"] == "Test event occurred"
    assert data["request_id"] == "req-trace-999"
    assert "timestamp" in data
    assert "environment" in data

    set_request_id("system")


def test_json_formatter_with_exception() -> None:
    """Verify that exception tracebacks are captured in the exception JSON field."""
    formatter = JSONFormatter()

    try:
        raise ValueError("Simulated failure")
    except ValueError:
        import sys

        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="aura.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=55,
        msg="Error executing operation",
        args=(),
        exc_info=exc_info,
    )

    output = formatter.format(record)
    data = json.loads(output)

    assert data["level"] == "ERROR"
    assert "exception" in data
    assert "ValueError: Simulated failure" in data["exception"]

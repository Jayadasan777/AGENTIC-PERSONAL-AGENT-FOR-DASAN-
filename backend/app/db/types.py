"""Database custom types supporting cross-engine portability.

PostgreSQL uses native ``pgvector.sqlalchemy.Vector`` for vector similarity operations.
SQLite (used in fast in-memory unit tests) falls back to storing vectors as JSON arrays.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import TypeDecorator
from sqlalchemy.types import JSON, Text

try:
    from pgvector.sqlalchemy import Vector as PgVector

    _HAS_PGVECTOR = True
except ImportError:
    _HAS_PGVECTOR = False
    PgVector = None  # type: ignore[assignment, misc]


class PortableVector(TypeDecorator):
    """Platform-independent Vector type.

    Uses pgvector.sqlalchemy.Vector(dim) when running on PostgreSQL,
    and falls back to JSON-serialized floats when running on SQLite.
    """

    impl = Text
    cache_ok = True

    def __init__(self, dim: int = 384, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.dim = dim

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql" and _HAS_PGVECTOR:
            return dialect.type_descriptor(PgVector(self.dim))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if dialect.name == "postgresql" and _HAS_PGVECTOR:
            return value
        # For SQLite / JSON storage
        if isinstance(value, (list, tuple)):
            return list(value)
        return value

    def process_result_value(self, value: Any, dialect: Any) -> list[float] | None:
        if value is None:
            return None
        if isinstance(value, str):
            try:
                return [float(x) for x in json.loads(value)]
            except Exception:
                return None
        if isinstance(value, (list, tuple)):
            return [float(x) for x in value]
        # In case pgvector returns numpy or custom array
        return list(value)

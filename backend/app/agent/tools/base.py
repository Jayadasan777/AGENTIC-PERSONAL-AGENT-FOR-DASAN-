"""Base contracts, context, and risk classifications for Agent Tools."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession


class RiskTier(StrEnum):
    """Three-tier risk rating for agent tools."""

    READ_ONLY = "READ_ONLY"  # Safe, no side effects, auto-allowed
    MUTATING = "MUTATING"  # Modifies state, creates entities, requires user consent
    DANGEROUS = "DANGEROUS"  # Shell, filesystem wipe, external network; strictly gated


@dataclass
class ToolContext:
    """Execution context injected into every tool call."""

    user_id: uuid.UUID
    session: AsyncSession
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))


class ToolResult(BaseModel):
    """Standardized output structure returned by all tools."""

    success: bool
    data: Any = None
    error: str | None = None
    artifacts: dict[str, Any] = field(default_factory=dict)  # type: ignore[assignment]


class AgentTool(ABC):
    """Abstract contract for an agent tool."""

    name: str
    description: str
    risk_tier: RiskTier
    args_schema: type[BaseModel]

    @abstractmethod
    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        """Run the tool logic within the caller's authorized context."""

    def to_schema(self) -> dict[str, Any]:
        """Export JSON Schema for LLM tool calling."""
        return {
            "name": self.name,
            "description": self.description,
            "risk_tier": self.risk_tier.value,
            "parameters": self.args_schema.model_json_schema(),
        }

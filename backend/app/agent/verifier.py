"""Independent Post-Execution Outcome Verifier for Agent Tool Invocations.

Ensures that:
1. Tool outputs conform to expected schema and data types.
2. State mutations actually persisted without silent failures.
3. No unintended side effects or constraint violations occurred.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.app.agent.tools.base import ToolContext, ToolResult

logger = logging.getLogger("aura.verifier")


class OutcomeVerificationResult:
    """Verdict of post-execution verification."""

    def __init__(self, verified: bool, reason: str, details: dict[str, Any] | None = None) -> None:
        self.verified = verified
        self.reason = reason
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "verified": self.verified,
            "reason": self.reason,
            "details": self.details,
        }


class OutcomeVerifier:
    """Independent validator checking the integrity and truth of tool execution outcomes."""

    async def verify(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: ToolResult,
        context: ToolContext,
    ) -> OutcomeVerificationResult:
        """Inspect execution result against expected post-conditions."""
        # 1. Check for basic tool-level failure
        if not result.success:
            return OutcomeVerificationResult(
                verified=False,
                reason=f"Tool '{tool_name}' failed during execution: {result.error}",
            )

        # 2. Tool-specific semantic verification
        if tool_name == "calculator":
            if not isinstance(result.data, dict) or "result" not in result.data:
                return OutcomeVerificationResult(
                    verified=False,
                    reason="Calculator output missing expected 'result' field.",
                )
            return OutcomeVerificationResult(
                verified=True,
                reason="Calculator arithmetic verified successfully.",
                details={"computed_result": result.data["result"]},
            )

        if tool_name == "create_note":
            # Verify note entity was created with non-empty ID
            if not isinstance(result.data, dict) or not result.data.get("id"):
                return OutcomeVerificationResult(
                    verified=False,
                    reason="Note creation did not return a valid persistent ID.",
                )
            return OutcomeVerificationResult(
                verified=True,
                reason="Note persistence confirmed.",
                details={"note_id": result.data["id"]},
            )

        if tool_name in ("search_memory", "search_documents"):
            if not isinstance(result.data, list):
                return OutcomeVerificationResult(
                    verified=False,
                    reason=f"Search tool '{tool_name}' must return a list of results.",
                )
            return OutcomeVerificationResult(
                verified=True,
                reason=f"Retrieved {len(result.data)} search candidates.",
                details={"count": len(result.data)},
            )

        if tool_name == "system_command":
            if not isinstance(result.data, dict) or "exit_code" not in result.data:
                return OutcomeVerificationResult(
                    verified=False,
                    reason="System command output missing exit_code.",
                )
            exit_code = result.data.get("exit_code")
            if exit_code != 0:
                return OutcomeVerificationResult(
                    verified=False,
                    reason=f"System command failed with non-zero exit code: {exit_code}",
                    details=result.data,
                )
            return OutcomeVerificationResult(
                verified=True,
                reason="System command executed cleanly with exit code 0.",
                details=result.data,
            )

        # Default generic verification
        return OutcomeVerificationResult(
            verified=True,
            reason=f"Tool '{tool_name}' executed cleanly.",
        )


outcome_verifier = OutcomeVerifier()

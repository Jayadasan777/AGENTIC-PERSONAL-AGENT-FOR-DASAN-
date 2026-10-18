"""Server-side Three-Tier Policy Engine for Agent Tool Invocations.

Decisions:
- ALLOW: Safe operations (RiskTier.READ_ONLY) proceed without human intervention.
- REQUIRE_APPROVAL: Sensitive actions (RiskTier.MUTATING or RiskTier.DANGEROUS) generate
  a cryptographically signed, expiration-bounded approval token and block until user approval.
- DENY: Blocked actions (Emergency Kill Switch active, unknown tool, schema violation, or rejected).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from backend.app.agent.kill_switch import kill_switch
from backend.app.agent.tools.base import RiskTier
from backend.app.agent.tools.registry import ToolRegistry, get_tool_registry
from backend.app.core.config import settings

logger = logging.getLogger("aura.policy")


class PolicyDecision(StrEnum):
    """Result of policy evaluation for a proposed tool action."""

    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"


class PolicyEvaluationResult:
    """Detailed verdict returned by the policy engine."""

    def __init__(
        self,
        decision: PolicyDecision,
        reason: str,
        risk_tier: RiskTier | None = None,
        approval_token: str | None = None,
        approval_id: str | None = None,
        expires_at: datetime | None = None,
    ) -> None:
        self.decision = decision
        self.reason = reason
        self.risk_tier = risk_tier
        self.approval_token = approval_token
        self.approval_id = approval_id
        self.expires_at = expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "reason": self.reason,
            "risk_tier": self.risk_tier.value if self.risk_tier else None,
            "approval_token": self.approval_token,
            "approval_id": self.approval_id,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


def canonical_json_hash(data: dict[str, Any]) -> str:
    """Create a deterministic SHA-256 hash of tool arguments."""
    serialized = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class PolicyEngine:
    """Enforces execution boundaries, approval tokens, and risk controls."""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        secret_key: str | None = None,
    ) -> None:
        self.registry = registry or get_tool_registry()
        self.secret_key = (secret_key or settings.SECRET_KEY.get_secret_value()).encode("utf-8")
        self._consumed_nonces: set[str] = set()

    def generate_approval_token(
        self,
        user_id: uuid.UUID,
        tool_name: str,
        args: dict[str, Any],
        expire_minutes: int = 5,
    ) -> tuple[str, str, datetime]:
        """Generate a cryptographically signed, expiration-bounded approval token.

        Returns:
            (approval_token, approval_id, expires_at)
        """
        approval_id = str(uuid.uuid4())
        nonce = str(uuid.uuid4())
        expires_at = datetime.now(UTC) + timedelta(minutes=expire_minutes)
        args_hash = canonical_json_hash(args)

        payload = {
            "aid": approval_id,
            "uid": str(user_id),
            "tool": tool_name,
            "hash": args_hash,
            "nonce": nonce,
            "exp": int(expires_at.timestamp()),
        }
        serialized = json.dumps(payload, sort_keys=True)
        signature = hmac.new(
            self.secret_key, serialized.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        token = f"{serialized}.{signature}"
        return token, approval_id, expires_at

    def verify_approval_token(
        self,
        token: str,
        user_id: uuid.UUID,
        tool_name: str,
        args: dict[str, Any],
        consume: bool = True,
    ) -> bool:
        """Validate HMAC signature, expiration, target tool, user match, and replay prevention."""
        try:
            parts = token.rsplit(".", 1)
            if len(parts) != 2:
                logger.warning("Malformed approval token structure")
                return False

            serialized, expected_sig = parts
            actual_sig = hmac.new(
                self.secret_key, serialized.encode("utf-8"), hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(actual_sig, expected_sig):
                logger.warning("Approval token HMAC signature mismatch")
                return False

            payload = json.loads(serialized)
            nonce = payload.get("nonce")
            if not nonce or nonce in self._consumed_nonces:
                logger.warning("Approval token replay detected: nonce already consumed")
                return False

            if payload.get("uid") != str(user_id):
                logger.warning("Approval token user mismatch")
                return False

            if payload.get("tool") != tool_name:
                logger.warning("Approval token tool mismatch")
                return False

            args_hash = canonical_json_hash(args)
            if payload.get("hash") != args_hash:
                logger.warning("Approval token arguments hash mismatch (parameters tampered)")
                return False

            exp = payload.get("exp", 0)
            now_ts = int(datetime.now(UTC).timestamp())
            if now_ts > exp:
                logger.warning("Approval token has expired (now=%d, exp=%d)", now_ts, exp)
                return False

            if consume:
                self._consumed_nonces.add(nonce)

            return True

        except Exception as err:
            logger.exception("Error verifying approval token: %s", err)
            return False

    def evaluate(
        self,
        user_id: uuid.UUID,
        tool_name: str,
        args: dict[str, Any],
        approval_token: str | None = None,
    ) -> PolicyEvaluationResult:
        """Evaluate a tool invocation request against safety policies."""
        # 1. Global emergency kill switch check
        if kill_switch.is_engaged:
            logger.critical("Policy DENY: Kill switch is active")
            return PolicyEvaluationResult(
                decision=PolicyDecision.DENY,
                reason="Global emergency kill switch is currently engaged.",
            )

        # 2. Tool registry lookup
        tool = self.registry.get(tool_name)
        if tool is None:
            logger.warning("Policy DENY: Unknown tool '%s'", tool_name)
            return PolicyEvaluationResult(
                decision=PolicyDecision.DENY,
                reason=f"Tool '{tool_name}' is not registered or allowed.",
            )

        # 3. Input validation against tool's Pydantic args_schema
        try:
            tool.args_schema.model_validate(args)
        except Exception as err:
            logger.warning("Policy DENY: Argument validation failed for '%s': %s", tool_name, err)
            return PolicyEvaluationResult(
                decision=PolicyDecision.DENY,
                reason=f"Invalid arguments for tool '{tool_name}': {err}",
                risk_tier=tool.risk_tier,
            )

        # 4. Safe READ_ONLY operations are permitted automatically
        if tool.risk_tier == RiskTier.READ_ONLY:
            return PolicyEvaluationResult(
                decision=PolicyDecision.ALLOW,
                reason="Read-only operation is authorized without approval.",
                risk_tier=tool.risk_tier,
            )

        # 5. Sensitive MUTATING and DANGEROUS operations require human approval
        if approval_token:
            is_valid = self.verify_approval_token(
                token=approval_token,
                user_id=user_id,
                tool_name=tool_name,
                args=args,
                consume=True,
            )
            if is_valid:
                return PolicyEvaluationResult(
                    decision=PolicyDecision.ALLOW,
                    reason="Signed approval token verified successfully.",
                    risk_tier=tool.risk_tier,
                )
            return PolicyEvaluationResult(
                decision=PolicyDecision.DENY,
                reason="Invalid or expired approval token provided.",
                risk_tier=tool.risk_tier,
            )

        # Require approval: generate signed token for the client to confirm
        token, approval_id, expires_at = self.generate_approval_token(
            user_id=user_id,
            tool_name=tool_name,
            args=args,
        )
        return PolicyEvaluationResult(
            decision=PolicyDecision.REQUIRE_APPROVAL,
            reason=(
                f"Action involves sensitive operation with risk tier {tool.risk_tier.value}. "
                "Human approval is required."
            ),
            risk_tier=tool.risk_tier,
            approval_token=token,
            approval_id=approval_id,
            expires_at=expires_at,
        )

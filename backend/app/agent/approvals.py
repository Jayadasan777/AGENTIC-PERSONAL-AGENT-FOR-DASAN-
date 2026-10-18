"""Approval Manager for tracking, inspecting, and deciding pending tool actions."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from backend.app.agent.policy import PolicyEngine


class ApprovalStatus(StrEnum):
    """Lifecycle states of an approval request."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass
class PendingApproval:
    """Record of an action suspended awaiting user confirmation."""

    approval_id: str
    user_id: uuid.UUID
    tool_name: str
    args: dict[str, Any]
    risk_tier: str
    reason: str
    approval_token: str
    expires_at: datetime
    status: ApprovalStatus = ApprovalStatus.PENDING
    decision_reason: str | None = None
    decided_at: datetime | None = None


class ApprovalManager:
    """Stores and resolves human-in-the-loop tool approvals."""

    def __init__(self, policy_engine: PolicyEngine | None = None) -> None:
        self.policy_engine = policy_engine or PolicyEngine()
        self._pending: dict[str, PendingApproval] = {}

    def create_request(
        self,
        approval_id: str,
        user_id: uuid.UUID,
        tool_name: str,
        args: dict[str, Any],
        risk_tier: str,
        reason: str,
        approval_token: str,
        expires_at: datetime,
    ) -> PendingApproval:
        """Record a newly generated approval request."""
        record = PendingApproval(
            approval_id=approval_id,
            user_id=user_id,
            tool_name=tool_name,
            args=args,
            risk_tier=risk_tier,
            reason=reason,
            approval_token=approval_token,
            expires_at=expires_at,
        )
        self._pending[approval_id] = record
        return record

    def get_request(self, approval_id: str, user_id: uuid.UUID) -> PendingApproval | None:
        """Fetch approval request strictly isolated to caller's user_id."""
        req = self._pending.get(approval_id)
        if req and req.user_id == user_id:
            # Check expiration
            if req.status == ApprovalStatus.PENDING and datetime.now(UTC) > req.expires_at:
                req.status = ApprovalStatus.EXPIRED
            return req
        return None

    def list_pending(self, user_id: uuid.UUID) -> list[PendingApproval]:
        """List active pending approvals for the authenticated user."""
        now = datetime.now(UTC)
        results: list[PendingApproval] = []
        for req in self._pending.values():
            if req.user_id == user_id:
                if req.status == ApprovalStatus.PENDING and now > req.expires_at:
                    req.status = ApprovalStatus.EXPIRED
                if req.status == ApprovalStatus.PENDING:
                    results.append(req)
        return results

    def decide(
        self,
        approval_id: str,
        user_id: uuid.UUID,
        approved: bool,
        reason: str | None = None,
    ) -> PendingApproval:
        """Record user's decision (Approve or Reject)."""
        req = self.get_request(approval_id, user_id)
        if req is None:
            raise KeyError(f"Approval request '{approval_id}' not found.")

        if req.status != ApprovalStatus.PENDING:
            raise ValueError(f"Approval request is already in status '{req.status.value}'.")

        req.decided_at = datetime.now(UTC)
        req.decision_reason = reason
        req.status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        return req


# Global singleton
approval_manager = ApprovalManager()

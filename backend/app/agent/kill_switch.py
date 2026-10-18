"""Global Emergency Kill Switch for AURA Agent Harness.

Provides an immediate, unconditional halt for all autonomous agent execution loops,
tool invocations, and pending background tasks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

logger = logging.getLogger("aura.kill_switch")


class KillSwitchActiveError(Exception):
    """Raised when an operation is attempted while the emergency kill switch is engaged."""


@dataclass
class KillSwitchState:
    """Status record of the emergency kill switch."""

    is_engaged: bool
    engaged_at: datetime | None = None
    reason: str | None = None
    actor_id: str | None = None


class EmergencyKillSwitch:
    """Thread-safe and process-wide emergency halt switch."""

    _instance: EmergencyKillSwitch | None = None

    def __new__(cls) -> EmergencyKillSwitch:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._state = KillSwitchState(is_engaged=False)
        return cls._instance

    @property
    def is_engaged(self) -> bool:
        """Return True if the agent system is currently halted."""
        return self._state.is_engaged

    @property
    def state(self) -> KillSwitchState:
        """Return current status record."""
        return self._state

    def engage(self, reason: str = "Manual emergency stop", actor_id: str | None = None) -> None:
        """Immediately halt all agent actions."""
        self._state = KillSwitchState(
            is_engaged=True,
            engaged_at=datetime.now(UTC),
            reason=reason,
            actor_id=actor_id,
        )
        logger.critical(
            "EMERGENCY KILL SWITCH ENGAGED! Reason: '%s' by actor: %s", reason, actor_id
        )

    def disengage(self, actor_id: str | None = None) -> None:
        """Disengage the kill switch and restore normal agent operations."""
        logger.warning("Emergency kill switch disengaged by actor: %s", actor_id)
        self._state = KillSwitchState(is_engaged=False)

    def check(self) -> None:
        """Verify the kill switch is clear. Raises KillSwitchActiveError if engaged."""
        if self.is_engaged:
            msg = (
                f"Operation blocked: Emergency kill switch is ACTIVE. "
                f"Reason: '{self._state.reason}' (engaged at {self._state.engaged_at})"
            )
            logger.warning(msg)
            raise KillSwitchActiveError(msg)


# Process-wide singleton
kill_switch = EmergencyKillSwitch()

"""WhatsApp Autonomous Agent Tool for AURA.

Enables AURA to compose, format, and dispatch WhatsApp messages directly to contacts
or phone numbers with native mobile application deep-linking and Human-in-the-Loop security review.
"""

from __future__ import annotations

import logging
import re
import urllib.parse
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.app.agent.tools.base import AgentTool, RiskTier, ToolContext, ToolResult

logger = logging.getLogger("aura.tools.whatsapp")


class WhatsAppMessageArgs(BaseModel):
    """Input parameters for sending a WhatsApp message."""

    recipient_name: str = Field(
        ...,
        description="Name or contact label of the recipient (e.g., 'Arun', 'Mom', 'Doctor').",
    )
    phone_number: str | None = Field(
        default=None,
        description="Target phone number with country code (e.g., '+919876543210' or '9876543210').",
    )
    message: str = Field(
        ...,
        description="The exact message content to send via WhatsApp.",
    )
    action: Literal["prepare_message", "send_direct"] = Field(
        default="prepare_message",
        description="Whether to prepare the message for human confirmation or dispatch it.",
    )


class WhatsAppTool(AgentTool):
    """Autonomous tool for sending WhatsApp messages with native mobile app deep-linking."""

    name = "send_whatsapp_message"
    description = (
        "Compose and dispatch WhatsApp messages to a contact or phone number. "
        "Generates direct phone WhatsApp application links and enforces Human-in-the-Loop authorization."
    )
    risk_tier = RiskTier.MUTATING
    args_schema = WhatsAppMessageArgs

    def _normalize_phone(self, phone: str | None) -> str:
        if not phone:
            return ""
        # Remove all non-digit characters except leading plus
        cleaned = re.sub(r"[^\d+]", "", phone.strip())
        if cleaned.startswith("+"):
            cleaned = cleaned[1:]
        # If 10 digits starting with 6-9, assume India (+91)
        if len(cleaned) == 10 and cleaned[0] in "6789":
            cleaned = f"91{cleaned}"
        return cleaned

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        recipient_name = kwargs.get("recipient_name", "Unknown Contact").strip()
        raw_phone = kwargs.get("phone_number")
        message = kwargs.get("message", "").strip()
        action = kwargs.get("action", "prepare_message")

        phone = self._normalize_phone(raw_phone)
        encoded_msg = urllib.parse.quote(message)

        # Generate direct native app URI (opens official WhatsApp phone app)
        native_app_url = f"whatsapp://send?phone={phone}&text={encoded_msg}" if phone else f"whatsapp://send?text={encoded_msg}"
        # Universal web/mobile fallback link
        universal_url = f"https://api.whatsapp.com/send?phone={phone}&text={encoded_msg}" if phone else f"https://api.whatsapp.com/send?text={encoded_msg}"

        logger.info(
            "WhatsApp Tool: Composed message for %s (phone=%s, action=%s)",
            recipient_name, phone, action,
        )

        return ToolResult(
            success=True,
            data={
                "status": "ready_to_send",
                "recipient_name": recipient_name,
                "phone_number": phone or "Not specified (will prompt in WhatsApp)",
                "message": message,
                "whatsapp_app_url": native_app_url,
                "whatsapp_universal_url": universal_url,
                "note": (
                    f"WhatsApp message ready for {recipient_name}. "
                    "Tap 'Open in WhatsApp App' on your phone to send it instantly via the native WhatsApp application."
                ),
            },
        )

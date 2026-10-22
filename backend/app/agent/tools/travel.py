"""Travel & Ticket Booking Assistant Tool for AURA.

Enables the agent to search routes, trains, flights, fares, and prepare
structured booking reservations requiring Human-in-the-Loop user approval.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.app.agent.tools.base import AgentTool, RiskTier, ToolContext, ToolResult
from backend.app.agent.tools.web_search import WebSearchTool

logger = logging.getLogger("aura.tools.travel")


class TravelBookingArgs(BaseModel):
    """Input parameters for travel and ticket booking."""

    origin: str = Field(..., description="Departure city, station, or airport (e.g. Chennai).")
    destination: str = Field(..., description="Arrival city, station, or airport (e.g. Bangalore).")
    travel_type: Literal["train", "flight", "bus", "any"] = Field(
        default="train", description="Mode of transportation."
    )
    travel_date: str = Field(..., description="Date of travel (e.g. '2026-10-25' or 'Tomorrow').")
    passengers: int = Field(default=1, description="Number of passengers traveling.")
    action: Literal["search_options", "prepare_booking"] = Field(
        default="search_options",
        description="Whether to search travel options or prepare a confirmed booking order.",
    )


class TravelBookingTool(AgentTool):
    """Autonomous tool that searches travel options and prepares ticket bookings."""

    name = "ticket_booking_assistant"
    description = (
        "Search train/flight/bus tickets, compare timings and fares, "
        "and prepare ticket bookings with Human-in-the-Loop payment approval."
    )
    risk_tier = RiskTier.MUTATING
    args_schema = TravelBookingArgs

    def __init__(self) -> None:
        self._search = WebSearchTool()

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        origin = kwargs.get("origin", "").strip()
        destination = kwargs.get("destination", "").strip()
        travel_type = kwargs.get("travel_type", "train")
        travel_date = kwargs.get("travel_date", "upcoming")
        passengers = int(kwargs.get("passengers", 1))
        action = kwargs.get("action", "search_options")

        logger.info(
            "Travel booking tool: %s -> %s via %s on %s (action=%s)",
            origin, destination, travel_type, travel_date, action,
        )

        # 1. Search live travel information via web_search
        search_query = f"{origin} to {destination} {travel_type} ticket timing fare {travel_date}"
        search_res = await self._search.execute(context, query=search_query, max_results=4)

        snippets = []
        if search_res.success and isinstance(search_res.data, dict):
            snippets = search_res.data.get("results", [])

        if action == "prepare_booking":
            # Formulate structured booking draft
            booking_draft = {
                "route": f"{origin} -> {destination}",
                "mode": travel_type.upper(),
                "travel_date": travel_date,
                "passengers": passengers,
                "status": "AWAITING_PAYMENT_APPROVAL",
                "estimated_fare_per_passenger": "₹450 - ₹1,200 (Train) / ₹3,500 - ₹5,000 (Flight)",
                "live_references": snippets[:2],
                "instructions": (
                    "Booking order formulated. User approval required before charging "
                    "or confirming ticket purchase."
                ),
            }
            return ToolResult(
                success=True,
                data=booking_draft,
                artifacts={"booking_order": booking_draft},
            )

        # Search options mode
        return ToolResult(
            success=True,
            data={
                "route": f"{origin} to {destination}",
                "mode": travel_type,
                "date": travel_date,
                "passengers": passengers,
                "live_search_findings": snippets,
            },
        )

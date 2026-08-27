"""
Itinerary output schemas — strict Pydantic models for the Planning Agent.

Design rules:
  - All decisions reference IDs only (never copy factual data from context).
  - All numeric facts (distance, fare, duration) stay in TripContext.
  - The LLM fills decision fields; backend code computes derived totals later.
  - Every field that may be absent uses Optional with a clear description.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


# ── Activity decision ─────────────────────────────────────────────────────────

class Activity(BaseModel):
    """
    A single attraction visit within a day.

    attraction_name is included so the response is human-readable without
    a secondary lookup, but the authoritative reference is attraction_name
    matched against AttractionContext.name (attractions have no ID field).
    start_time and duration_minutes are the LLM's scheduling decisions.
    """
    attraction_name: str = Field(
        ...,
        description="Must exactly match an AttractionContext.name from TripContext.",
    )
    start_time: Optional[str] = Field(
        default=None,
        description="Suggested visit start time in HH:MM (24h). Null if unknown.",
    )
    duration_minutes: Optional[int] = Field(
        default=None,
        description="Suggested visit duration in minutes. Null if unknown.",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Optional visit tip or reasoning. Must not contain invented facts.",
    )


# ── Transport decision ────────────────────────────────────────────────────────

class TransportDecision(BaseModel):
    """
    The LLM's complete transport choice for one journey leg.

    ALL factual fields (times, fares, seats) must be copied EXACTLY from
    the pre-filtered TripContext payload — never invented.

    Format contract (how this renders in the itinerary):
        {train_number} - {train_name}
        Departs {origin} on {departure_date} @ {departure_time}
        Arrives {destination} on {arrival_date} @ {arrival_time}
        Class: {travel_class} | Seats: {seats_available} {seat_status} | Rs.{fare_per_person}/person
    """
    # ── Journey leg ───────────────────────────────────────────────────────────
    leg: str = Field(
        ...,
        description="Human-readable route, e.g. 'Chennai → Coimbatore'.",
    )
    mode: str = Field(
        ...,
        description="Chosen mode: 'train' or 'bus'.",
    )

    # ── Train fields (null for bus legs) ─────────────────────────────────────
    train_number: Optional[str] = Field(
        default=None,
        description="Exact train_number from TripContext outbound_trains / return_trains.",
    )
    train_name: Optional[str] = Field(
        default=None,
        description="Exact train_name from TripContext. Do not invent or abbreviate.",
    )

    # ── Bus fields (null for train legs) ─────────────────────────────────────
    operator_name: Optional[str] = Field(
        default=None,
        description="Exact operator_name from TripContext outbound_buses / return_buses.",
    )
    bus_type: Optional[str] = Field(
        default=None,
        description="Exact bus_type from TripContext, e.g. 'AC Sleeper (2+1)'.",
    )

    # ── Schedule (copy from pre-filtered payload — do NOT compute) ────────────
    departure_date: Optional[str] = Field(
        default=None,
        description="Departure date YYYY-MM-DD. Copy from payload. May be day-1 for overnight trains.",
    )
    departure_time: Optional[str] = Field(
        default=None,
        description="Departure time HH:MM (24h). Copy exactly from payload.",
    )
    arrival_date: Optional[str] = Field(
        default=None,
        description="Arrival date YYYY-MM-DD. Copy from payload.",
    )
    arrival_time: Optional[str] = Field(
        default=None,
        description="Arrival time HH:MM (24h). Copy exactly from payload.",
    )

    # ── Class & availability (copy from pre-filtered payload) ─────────────────
    travel_class: Optional[str] = Field(
        default=None,
        description="Chosen class code: '1A','2A','3A','CC','SL','2S','GN' or bus seat type.",
    )
    seat_status: Optional[str] = Field(
        default=None,
        description="'AVL' (confirmed) or 'RAC' (reservation against cancellation).",
    )
    seats_available: Optional[int] = Field(
        default=None,
        description="Live seat count from payload. Copy exactly — do not guess.",
    )
    fare_per_person: Optional[int] = Field(
        default=None,
        description="Fare in INR per person for the chosen class. Copy from payload.",
    )

    # ── Agent reasoning ───────────────────────────────────────────────────────
    reasoning: Optional[str] = Field(
        default=None,
        description="Why this option was selected (class fit, timing, availability).",
    )


# ── Hotel decision ────────────────────────────────────────────────────────────

class HotelDecision(BaseModel):
    """
    The LLM's hotel selection — references a HotelContext.id from TripContext.
    """
    hotel_id: str = Field(
        ...,
        description="Must match a HotelContext.id from TripContext.hotels.",
    )
    hotel_name: str = Field(
        ...,
        description="Must match the corresponding HotelContext.name. Included for readability.",
    )
    reasoning: Optional[str] = Field(
        default=None,
        description="Why this hotel was selected (budget fit, rating, etc.).",
    )


# ── Day plan ──────────────────────────────────────────────────────────────────

class DayPlan(BaseModel):
    """Activities and transport legs for a single trip day."""
    day: int = Field(..., description="Day number, starting from 1.", ge=1)
    date: Optional[str] = Field(
        default=None,
        description="Calendar date for this day in YYYY-MM-DD format.",
    )
    theme: Optional[str] = Field(
        default=None,
        description="Optional thematic label, e.g. 'Arrival & City Centre'.",
    )
    activities: list[Activity] = Field(
        default_factory=list,
        description="Ordered list of attraction visits for this day.",
    )
    transport: list[TransportDecision] = Field(
        default_factory=list,
        description="Transport legs for this day (origin travel, inter-attraction, etc.).",
    )


# ── Trip summary ──────────────────────────────────────────────────────────────

class ItinerarySummary(BaseModel):
    destination: str
    origin: str
    days: int
    travelers: int
    pace: str = Field(description="relaxed | moderate | intensive")
    budget_level: str = Field(description="low | medium | high")


# ── Top-level itinerary ───────────────────────────────────────────────────────

class Itinerary(BaseModel):
    """
    The complete structured trip plan produced by the Planning Agent.

    GROUNDING CONTRACT:
      - hotel.hotel_id must match a TripContext.hotels[*].id.
      - outbound_transport / return_transport reference TripContext options.
      - All attraction_name values must match TripContext.attractions[*].name.
      - The agent must not invent any value not present in TripContext.
    """
    summary: ItinerarySummary
    hotel: Optional[HotelDecision] = Field(
        default=None,
        description="Chosen hotel. Null if no hotels were available in context.",
    )
    outbound_transport: Optional[TransportDecision] = Field(
        default=None,
        description="How the traveler gets from origin to destination.",
    )
    return_transport: Optional[TransportDecision] = Field(
        default=None,
        description="How the traveler returns from destination to origin.",
    )
    days: list[DayPlan] = Field(
        default_factory=list,
        description="Day-by-day activity plans.",
    )
    planning_notes: Optional[str] = Field(
        default=None,
        description="Optional high-level planning notes from the agent.",
    )

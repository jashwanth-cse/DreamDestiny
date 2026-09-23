"""
PlanningAgent — the AI decision-maker for trip itineraries.

Responsibilities:
  - Accept ONLY a TripContext.
  - Pre-filter trains/buses/hotels with deterministic Python logic before the
    LLM sees ANY data (berth preference, seat availability, budget, rating).
  - Build a minimal, grounded JSON payload for the LLM.
  - Validate the model response with Pydantic Itinerary schema.
  - Return a typed Itinerary object.
  - NEVER import or call service clients.
  - NEVER calculate distances, costs, or durations in LLM prompts.

Architecture note:
  Pre-filtering is deterministic Python (fast, zero tokens).
  The LLM only makes the final SELECTION from the curated shortlist.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Optional

from pydantic import ValidationError

from app.agents.base import BaseAgent, AgentError
from app.schemas.context import TripContext, TrainContext, BusContext, HotelContext, FlightContext
from app.schemas.itinerary import Itinerary
from app.services.llm.gemini_client import GeminiClient, GeminiError
from app.services.llm.prompts import PLANNING_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


# ── Class groupings ───────────────────────────────────────────────────────────

AC_CLASSES     = {"1A", "2A", "3A", "CC"}
NON_AC_CLASSES = {"SL", "2S", "GN"}
ALL_CLASSES    = AC_CLASSES | NON_AC_CLASSES

# Fallback order within AC / Non-AC if exact class unavailable
AC_FALLBACK_ORDER     = ["2A", "3A", "1A", "CC"]
NON_AC_FALLBACK_ORDER = ["SL", "2S", "GN"]

# Price bands for hotel filtering
HOTEL_PRICE_BANDS: dict[str, tuple[float, float]] = {
    "low":    (0,     1_500),
    "medium": (1_500, 5_000),
    "high":   (5_000, float("inf")),
}


# ── Availability parsing ──────────────────────────────────────────────────────

def _parse_avail(avail_str: str) -> tuple[str, int]:
    """
    Parse IRCTC availability strings.
    Examples:
        "AVL 45"  → ("AVL", 45)
        "RAC 3"   → ("RAC", 3)
        "WL 12"   → ("WL", 12)
        "REGRET"  → ("REGRET", 0)
    """
    if not avail_str:
        return "UNKNOWN", 0
    parts = avail_str.strip().upper().split()
    status = parts[0] if parts else "UNKNOWN"
    count = 0
    if len(parts) > 1:
        try:
            count = int(parts[1])
        except ValueError:
            count = 0
    return status, count


# ── Allowed class resolution ──────────────────────────────────────────────────

def _get_allowed_classes(berth_pref: str | None) -> list[str]:
    """
    Return the ordered list of allowed travel class codes for a given preference.

    Specific class (e.g. "3A"):
        Try exact class first, then fallback within same AC/Non-AC group.

    "any" or None:
        All classes allowed, AC preferred over Non-AC.
    """
    if not berth_pref or berth_pref == "any":
        # All classes, AC first
        return AC_FALLBACK_ORDER + NON_AC_FALLBACK_ORDER

    if berth_pref in AC_CLASSES:
        # Exact AC class first, then rest of AC group
        return [berth_pref] + [c for c in AC_FALLBACK_ORDER if c != berth_pref]

    if berth_pref in NON_AC_CLASSES:
        # Exact Non-AC class first, then rest of Non-AC group
        return [berth_pref] + [c for c in NON_AC_FALLBACK_ORDER if c != berth_pref]

    return AC_FALLBACK_ORDER + NON_AC_FALLBACK_ORDER


# ── Train pre-filter ──────────────────────────────────────────────────────────

def _best_class_for_train(
    classes: list,
    ordered_allowed: list[str],
) -> dict | None:
    """
    Walk the ordered_allowed list and pick the FIRST class that has AVL or RAC seats.
    Returns a dict with class details, or None if nothing bookable.
    """
    # Build a quick lookup: class_code → TravelClassContext
    class_map: dict[str, object] = {c.travel_class: c for c in classes}

    # First pass: look for AVL in preferred order
    for code in ordered_allowed:
        cls = class_map.get(code)
        if cls is None:
            continue
        status, count = _parse_avail(cls.availability)
        if status == "AVL":
            return {
                "travel_class": cls.travel_class,
                "fare": cls.fare,
                "seat_status": "AVL",
                "seats_available": count,
            }

    # Second pass: accept RAC if no AVL found
    for code in ordered_allowed:
        cls = class_map.get(code)
        if cls is None:
            continue
        status, count = _parse_avail(cls.availability)
        if status == "RAC":
            return {
                "travel_class": cls.travel_class,
                "fare": cls.fare,
                "seat_status": "RAC",
                "seats_available": count,
            }

    return None  # Only WL or unavailable


def _compute_train_dates(
    journey_date: date,
    departure_time_str: str,
    duration_minutes: int,
) -> tuple[str, str]:
    """
    Compute actual departure_date and arrival_date for a train.

    Departure date = journey_date (service returns trains running on this date).
    Arrival date   = journey_date + how many full days the journey spans.

    Example: departs 22:00, duration 480min → arrives 06:00 next day.
    """
    try:
        dep_h, dep_m = map(int, departure_time_str.strip().split(":"))
    except (ValueError, AttributeError):
        return journey_date.isoformat(), journey_date.isoformat()

    dep_minutes_from_midnight = dep_h * 60 + dep_m
    arr_minutes_from_midnight = dep_minutes_from_midnight + (duration_minutes or 0)
    arrival_day_offset = arr_minutes_from_midnight // (24 * 60)

    dep_date = journey_date
    arr_date = journey_date + timedelta(days=arrival_day_offset)
    return dep_date.isoformat(), arr_date.isoformat()


def _filter_trains(
    trains: list[TrainContext],
    journey_date: date,
    berth_pref: str | None,
    top_n: int = 5,
) -> list[dict]:
    """
    Pre-filter trains for the LLM payload:

    1. Running day check — only trains whose running_days includes journey weekday.
    2. Class & availability — only trains with AVL or RAC in the preferred class
       (or its fallback within same AC/Non-AC group).
    3. Sort — AVL-first, then rating DESC.
    4. Enrich — add departure_date, arrival_date, seat_status, seats_available,
       travel_class, fare_per_person for the chosen class.
    5. Return top_n.
    """
    weekday = journey_date.strftime("%a")  # "Mon", "Tue", etc.
    ordered_allowed = _get_allowed_classes(berth_pref)

    candidates: list[tuple[dict, tuple]] = []  # (enriched_dict, sort_key)

    for t in trains:
        # 1. Running day check
        if weekday not in (t.running_days or []):
            continue

        # 2. Find best available class
        best_cls = _best_class_for_train(t.classes, ordered_allowed)
        if best_cls is None:
            continue  # All preferred classes are WL or unavailable

        # 3. Compute dates
        dep_date, arr_date = _compute_train_dates(
            journey_date, t.departure_time, t.duration_minutes
        )

        enriched = {
            "train_number":    t.train_number,
            "train_name":      t.train_name,
            "departure_date":  dep_date,
            "departure_time":  t.departure_time,
            "arrival_date":    arr_date,
            "arrival_time":    t.arrival_time,
            "duration":        t.duration,
            "distance_km":     t.distance_km,
            "has_pantry":      t.has_pantry,
            "rating":          t.rating,
            "travel_class":    best_cls["travel_class"],
            "fare_per_person": best_cls["fare"],
            "seat_status":     best_cls["seat_status"],
            "seats_available": best_cls["seats_available"],
        }
        # Sort: AVL first (0 < 1), then rating DESC (negate)
        sort_key = (0 if best_cls["seat_status"] == "AVL" else 1, -t.rating)
        candidates.append((enriched, sort_key))

    candidates.sort(key=lambda x: x[1])
    return [item[0] for item in candidates[:top_n]]


# ── Hotel pre-filter ──────────────────────────────────────────────────────────

def _filter_hotels(
    hotels: list[HotelContext],
    budget_level: str,
    top_n: int = 5,
) -> list[dict]:
    """
    Pre-filter hotels to the user's budget band, sorted by rating.
    Relaxes the band if fewer than 3 hotels match (avoids empty list).
    """
    min_price, max_price = HOTEL_PRICE_BANDS.get(budget_level, (0, float("inf")))

    in_band = [
        h for h in hotels
        if h.price.per_night is None
        or (min_price <= h.price.per_night <= max_price)
    ]

    # Relax if too few results
    if len(in_band) < 3:
        in_band = list(hotels)

    in_band.sort(key=lambda h: h.rating or 0, reverse=True)

    return [
        {
            "id":             h.id,
            "name":           h.name,
            "rating":         h.rating,
            "hotel_class":    h.hotel_class,
            "price_per_night": h.price.per_night,
            "price_total":    h.price.total,
            "currency":       h.price.currency,
            # Cap amenities to avoid token bloat
            "amenities":      h.amenities[:5],
        }
        for h in in_band[:top_n]
    ]


# ── Bus pre-filter ────────────────────────────────────────────────────────────

def _parse_bus_time(raw_time: str | None) -> str:
    """
    Extract HH:MM from bus service datetime strings.
    Bus service format: "YYYY-MM-DD HH:MM:SS"  or already "HH:MM".
    """
    if not raw_time:
        return ""
    if " " in raw_time:
        time_part = raw_time.split(" ")[1]
        return time_part[:5]  # "HH:MM"
    return raw_time[:5]


def _filter_buses(
    buses: list[BusContext],
    berth_pref: str | None,
    top_n: int = 5,
) -> list[dict]:
    """
    Pre-filter buses:
    1. Only buses with available_seats > 0.
    2. AC/Non-AC preference via bus_type string match.
    3. Sort by rating DESC, then minimum_fare ASC.
    4. Return top_n enriched dicts with parsed departure/arrival times.
    """
    # Resolve AC preference from berth_pref
    want_ac: Optional[bool] = None  # None = no preference
    if berth_pref in AC_CLASSES or berth_pref == "any":
        want_ac = None  # AC classes on trains don't restrict bus AC pref when "any"
    if berth_pref in AC_CLASSES:
        want_ac = True   # AC train class → prefer AC bus
    elif berth_pref in NON_AC_CLASSES:
        want_ac = False  # Non-AC train class → prefer Non-AC bus

    # Step 1: Only buses with seats
    candidates = [b for b in buses if (b.available_seats or 0) > 0]

    # Step 2: Apply AC/Non-AC preference if set
    if want_ac is not None:
        ac_filtered = []
        for b in candidates:
            bus_type_lower = (b.bus_type or "").lower()
            is_non_ac = (
                "non a/c" in bus_type_lower
                or "non-ac"  in bus_type_lower
                or "non ac"  in bus_type_lower
            )
            if want_ac and not is_non_ac:
                ac_filtered.append(b)
            elif not want_ac and is_non_ac:
                ac_filtered.append(b)
        # Only apply filter if we get at least 2 buses; else use all
        if len(ac_filtered) >= 2:
            candidates = ac_filtered

    # Step 3: Sort
    candidates.sort(key=lambda b: (-(b.rating or 0), b.minimum_fare or 0))

    # Step 4: Enrich and return
    return [
        {
            "operator_name":  b.operator_name,
            "bus_type":       b.bus_type,
            "departure_time": _parse_bus_time(b.departure_time),
            "arrival_time":   _parse_bus_time(b.arrival_time),
            "duration":       b.duration,
            "minimum_fare":   b.minimum_fare,
            "available_seats": b.available_seats,
            "rating":         b.rating,
        }
        for b in candidates[:top_n]
    ]


# ── Flight pre-filter ──────────────────────────────────────────────────────────

def _filter_flights(
    flights: list[FlightContext],
    budget_level: str = "medium",
    top_n: int = 5,
) -> list[dict]:
    """
    Pre-filter flights:
    1. Sort by: is_best_flight DESC, stops ASC, price ASC.
    2. Return top_n normalized dicts.
    """
    if not flights:
        return []

    sorted_flights = sorted(
        flights,
        key=lambda f: (
            0 if f.is_best_flight else 1,
            f.stops,
            f.price if f.price is not None else float("inf"),
        )
    )

    return [
        {
            "flight_id":         f.flight_id,
            "airline":           f.airline,
            "flight_number":     f.flight_number,
            "departure_airport": f.departure_airport_code,
            "arrival_airport":   f.arrival_airport_code,
            "departure_time":    f.departure_time,
            "arrival_time":      f.arrival_time,
            "duration":          f.duration,
            "stops":             f.stops,
            "price":             f.price,
            "currency":          f.currency,
            "travel_class":      f.travel_class,
            "is_best_flight":    f.is_best_flight,
        }
        for f in sorted_flights[:top_n]
    ]


# ── Payload builder ───────────────────────────────────────────────────────────

def _build_context_payload(context: TripContext) -> dict:
    """
    Build a minimal, pre-filtered JSON payload for the LLM.

    All heavy lifting (filtering, sorting, date computation) is done here
    in deterministic Python — the LLM receives a curated shortlist only.

    Token budget (approx):
      trip block      :   ~80
      attractions     :  ~480  (12 items, no change)
      5 hotels        :  ~225  (was ~910 for 20)
      5 outb trains   :  ~310  (was ~994 for 16)
      5 ret  trains   :  ~310  (was ~1201 for 21)
      5 outb buses    :  ~215  (was ~430 for 10)
      5 ret  buses    :  ~215  (was ~430 for 10)
      route           :   ~31
      ─────────────────────────────────────────
      TOTAL           : ~1,866  (was ~4,555)
    """
    trip  = context.trip
    prefs = trip.preferences

    # Resolve berth preference string (enum value like "3A", "SL", or "any")
    berth_pref: str | None = (
        prefs.transport.berth_preference.value
        if prefs.transport.berth_preference else None
    )
    budget_level = prefs.budget.level.value
    trip_days    = (trip.end_date - trip.start_date).days

    return {
        "trip": {
            "origin":      trip.origin,
            "destination": trip.destination,
            "start_date":  trip.start_date.isoformat(),
            "end_date":    trip.end_date.isoformat(),
            "days":        trip_days,
            "travelers":   trip.travelers,
            "preferences": {
                "budget":            budget_level,
                "transport_mode":    prefs.transport.mode.value,
                "berth_preference":  berth_pref or "any",
                "hotel_category":    prefs.hotel.category.value,
                "pace":              prefs.activities.pace.value,
                "interests":         prefs.activities.interests,
                "family_friendly":   prefs.activities.family_friendly,
                "food": (
                    {
                        "dietary_restrictions": prefs.food.dietary_restrictions.value,
                        "cuisines":             prefs.food.cuisines,
                    }
                    if prefs.food else None
                ),
            },
        },

        # Attractions — all sent (LLM needs them all to plan days)
        "attractions": [
            {
                "name":         a.name,
                "address":      a.address,
                "rating":       a.rating,
                "review_count": a.review_count,
                "latitude":     a.latitude,
                "longitude":    a.longitude,
                "types":        a.types,
            }
            for a in context.attractions
        ],

        # Hotels — top 5 matching budget band, sorted by rating
        "hotels": _filter_hotels(context.hotels, budget_level, top_n=5),

        # Outbound trains — top 5: running on start_date weekday,
        #   AVL/RAC in preferred class, AVL-first, then rating DESC
        "outbound_trains": _filter_trains(
            context.outbound_trains,
            journey_date=trip.start_date,
            berth_pref=berth_pref,
            top_n=5,
        ),

        # Return trains — same logic for end_date
        "return_trains": _filter_trains(
            context.return_trains,
            journey_date=trip.end_date,
            berth_pref=berth_pref,
            top_n=5,
        ),

        # Outbound buses — top 5: AC/Non-AC matched, rating DESC, fare ASC
        "outbound_buses": _filter_buses(
            context.outbound_buses,
            berth_pref=berth_pref,
            top_n=5,
        ),

        # Return buses — same logic
        "return_buses": _filter_buses(
            context.return_buses,
            berth_pref=berth_pref,
            top_n=5,
        ),

        # Outbound flights — top 5: best flights, non-stop, lowest price
        "outbound_flights": _filter_flights(
            context.outbound_flights,
            budget_level=budget_level,
            top_n=5,
        ),

        # Return flights — same logic
        "return_flights": _filter_flights(
            context.return_flights,
            budget_level=budget_level,
            top_n=5,
        ),

        "route": (
            {
                "distance_km": context.route.distance_km,
                "modes": [
                    {"mode": r.mode, "duration_minutes": r.duration_minutes}
                    for r in context.route.routes
                ],
            }
            if context.route else None
        ),
    }


# ── Planning Agent ────────────────────────────────────────────────────────────

def _itinerary_json_schema() -> dict:
    return Itinerary.model_json_schema()


class PlanningAgent(BaseAgent[Itinerary]):
    """
    Uses Gemini to produce a grounded, structured Itinerary from TripContext.
    Constructor-injected with a GeminiClient so the LLM backend is swappable.
    """

    def __init__(self, llm: GeminiClient) -> None:
        self._llm = llm

    async def plan(self, context: TripContext) -> Itinerary:
        """
        Produce an Itinerary for the given TripContext.

        Flow:
          1. Pre-filter TripContext into a minimal, grounded payload.
          2. Send system prompt + payload to GeminiClient.
          3. Validate raw JSON response with Pydantic Itinerary.
          4. Return typed Itinerary.
        """
        payload = _build_context_payload(context)
        schema  = _itinerary_json_schema()

        logger.info(
            "PlanningAgent.plan: %s → %s | %d attractions | %d hotels | "
            "%d outbound trains | %d outbound buses | %d outbound flights",
            context.trip.origin,
            context.trip.destination,
            len(payload["attractions"]),
            len(payload["hotels"]),
            len(payload["outbound_trains"]),
            len(payload["outbound_buses"]),
            len(payload["outbound_flights"]),
        )

        try:
            raw = await self._llm.generate_json(
                system_prompt=PLANNING_SYSTEM_PROMPT,
                user_data=payload,
                json_schema=schema,
            )
        except GeminiError as exc:
            raise AgentError(str(exc), cause=exc)

        try:
            itinerary = Itinerary.model_validate(raw)
        except ValidationError as exc:
            logger.error(
                "PlanningAgent: Itinerary validation failed.\n"
                "Raw (truncated): %s\nErrors: %s",
                json.dumps(raw, indent=2)[:1500],
                exc,
            )
            raise AgentError(
                "The planning model returned a response that did not match "
                "the expected Itinerary structure. Please try again.",
                cause=exc,
            )

        logger.info(
            "PlanningAgent.plan complete: %d days | hotel=%s | outbound=%s",
            len(itinerary.days),
            itinerary.hotel.hotel_id if itinerary.hotel else "none",
            (
                itinerary.outbound_transport.train_number
                or itinerary.outbound_transport.operator_name
                if itinerary.outbound_transport else "none"
            ),
        )
        return itinerary

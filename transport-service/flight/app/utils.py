"""
Utility functions for Flight Service:
- Date normalization (to YYYY-MM-DD)
- Travel class mapping (text/int to SerpApi code)
- Duration formatting
- Unique flight ID generation
"""

import re
import hashlib
from typing import Optional, Union


def normalize_flight_date(date_str: str) -> str:
    """
    Normalizes any date string (YYYY-MM-DD, DD-MM-YYYY, DD/MM/YYYY, YYYY/MM/DD)
    into the ISO YYYY-MM-DD format required by Google Flights.
    """
    raw = str(date_str).strip()
    if not raw:
        return ""

    # YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw

    # DD-MM-YYYY -> YYYY-MM-DD
    if re.match(r"^\d{2}-\d{2}-\d{4}$", raw):
        parts = raw.split("-")
        return f"{parts[2]}-{parts[1]}-{parts[0]}"

    # DD/MM/YYYY -> YYYY-MM-DD
    if re.match(r"^\d{2}/\d{2}/\d{4}$", raw):
        parts = raw.split("/")
        return f"{parts[2]}-{parts[1]}-{parts[0]}"

    # YYYY/MM/DD -> YYYY-MM-DD
    if re.match(r"^\d{4}/\d{2}/\d{2}$", raw):
        parts = raw.split("/")
        return f"{parts[0]}-{parts[1]}-{parts[2]}"

    return raw


def map_travel_class(travel_class: Optional[Union[str, int]]) -> int:
    """
    Maps travel class string or integer to SerpApi travel_class integer:
    1 = Economy (default)
    2 = Premium Economy
    3 = Business
    4 = First
    """
    if travel_class is None:
        return 1

    if isinstance(travel_class, int):
        return travel_class if 1 <= travel_class <= 4 else 1

    tc_lower = str(travel_class).lower().strip()
    if "first" in tc_lower:
        return 4
    if "business" in tc_lower:
        return 3
    if "premium" in tc_lower:
        return 2
    return 1


def minutes_to_duration(minutes: Optional[int]) -> Optional[str]:
    """Converts duration in minutes to human readable string (e.g. 75 -> '1h 15m')."""
    if minutes is None:
        return None
    hrs = minutes // 60
    mins = minutes % 60
    if hrs > 0 and mins > 0:
        return f"{hrs}h {mins}m"
    if hrs > 0:
        return f"{hrs}h"
    return f"{mins}m"


def generate_flight_id(
    booking_token: Optional[str] = None,
    flight_number: Optional[str] = None,
    departure_time: Optional[str] = None,
    arrival_time: Optional[str] = None,
    airline: Optional[str] = None
) -> str:
    """
    Generates a deterministic unique ID for a flight.
    Prefers booking_token; otherwise generates an MD5 hash of flight key fields.
    """
    if booking_token:
        # Generate stable short hash from booking token
        return f"fl_{hashlib.md5(booking_token.encode('utf-8')).hexdigest()[:16]}"

    seed = f"{airline or ''}_{flight_number or ''}_{departure_time or ''}_{arrival_time or ''}"
    return f"fl_{hashlib.md5(seed.encode('utf-8')).hexdigest()[:16]}"

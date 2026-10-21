"""
Payload Factory for TrainWatch Availability Load-Test Service.

Generates realistic and deterministic test payloads for Train 06030
(Tirunelveli -> Mettupalayam) across all 23 stations, valid upcoming Sundays,
and travel classes.
"""

from datetime import datetime, timedelta
import random
from typing import List, Tuple, Optional

from app.models.schemas import ScenarioType, TrainQueryPayload

TRAIN_NO = "06030"

# All 23 sequential stations along the Train 06030 route
ROUTE_STATIONS = [
    "TEN",   # Tirunelveli (Origin)
    "SMD",   # Cheranmahadevi
    "KIC",   # Kallidaikurichi
    "ASD",   # Ambasamudram
    "KKY",   # Kilakadaiyam
    "PCM",   # Pavurchatram
    "TSI",   # Tenkasi Junction
    "KDNL",  # Kadayanallur
    "SNKL",  # Sankarankovil
    "RJPM",  # Rajapalayam
    "SVPR",  # Srivilliputtur
    "SVKS",  # Sivakasi
    "VPT",   # Virudhunagar Junction
    "MDU",   # Madurai Junction
    "DG",    # Dindigul Junction
    "ODC",   # Oddanchatram
    "PLNI",  # Palani
    "UDT",   # Udumalaipettai
    "POY",   # Pollachi Junction
    "KKN",   # Kinathukadavu
    "PTJ",   # Podanur Junction
    "CBE",   # Coimbatore Junction
    "MTP",   # Mettupalayam (Destination)
]

TRAVEL_CLASSES = ["SL", "3A", "2A"]


def get_upcoming_sundays(count: int = 5) -> List[str]:
    """
    Computes the upcoming Sundays starting from today in DD-MM-YYYY format.
    Guarantees that test requests are always within the active 120-day IRCTC window.
    """
    today = datetime.now()
    # Sunday is weekday() == 6
    days_until_sunday = (6 - today.weekday()) % 7
    if days_until_sunday == 0:
        # If today is Sunday, include today if early, or start from next Sunday
        days_until_sunday = 7

    first_sunday = today + timedelta(days=days_until_sunday)
    sundays = []
    for i in range(count):
        s = first_sunday + timedelta(days=i * 7)
        sundays.append(s.strftime("%d-%m-%Y"))
    return sundays


def get_random_forward_pair() -> Tuple[str, str]:
    """Returns a valid station pair where source appears strictly before destination."""
    i = random.randint(0, len(ROUTE_STATIONS) - 2)
    j = random.randint(i + 1, len(ROUTE_STATIONS) - 1)
    return ROUTE_STATIONS[i], ROUTE_STATIONS[j]


def build_payload(
    train_no: str,
    source: str,
    destination: str,
    travel_class: str,
    date: str,
    quota: str = "GN",
) -> TrainQueryPayload:
    """Helper to construct a validated TrainQueryPayload."""
    return TrainQueryPayload(
        trainNo=train_no,
        source=source,
        destination=destination,
        travelClass=travel_class,
        date=date,
        quota=quota,
    )


def generate_payloads(
    scenario: ScenarioType,
    total_requests: int,
    custom_payloads: Optional[List[TrainQueryPayload]] = None,
) -> List[TrainQueryPayload]:
    """
    Generates the list of TrainQueryPayload items for the specified load scenario.
    """
    if scenario == ScenarioType.CUSTOM:
        if not custom_payloads:
            raise ValueError("custom_payloads required for custom scenario")
        # Cycle through custom payloads until total_requests is reached
        out = []
        for i in range(total_requests):
            out.append(custom_payloads[i % len(custom_payloads)])
        return out

    sundays = get_upcoming_sundays(5)
    hot_sunday = sundays[0]

    # Baseline hot query: TEN -> MTP on the immediate next Sunday in SL class
    hot_payload = build_payload(
        train_no=TRAIN_NO,
        source="TEN",
        destination="MTP",
        travel_class="SL",
        date=hot_sunday,
        quota="GN",
    )

    if scenario == ScenarioType.BURST_IDENTICAL:
        # 100% identical canonical key to stress-test Singleflight deduplication
        return [hot_payload for _ in range(total_requests)]

    if scenario == ScenarioType.DIVERSE_MATRIX:
        # 100% diverse queries across 253 station pairs, 5 Sundays, 3 travel classes
        payloads = []
        for _ in range(total_requests):
            src, dst = get_random_forward_pair()
            cls = random.choice(TRAVEL_CLASSES)
            date = random.choice(sundays)
            payloads.append(build_payload(TRAIN_NO, src, dst, cls, date))
        return payloads

    # ScenarioType.BALANCED (default):
    # 50% identical hot query, 50% diverse queries
    payloads = []
    identical_count = total_requests // 2
    diverse_count = total_requests - identical_count

    for _ in range(identical_count):
        payloads.append(hot_payload)

    for _ in range(diverse_count):
        src, dst = get_random_forward_pair()
        cls = random.choice(TRAVEL_CLASSES)
        date = random.choice(sundays)
        payloads.append(build_payload(TRAIN_NO, src, dst, cls, date))

    # Shuffle so identical requests are interspersed concurrently with diverse queries
    random.shuffle(payloads)
    return payloads

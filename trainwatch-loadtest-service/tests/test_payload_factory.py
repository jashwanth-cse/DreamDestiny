"""
Tests for Payload Factory.
"""

from datetime import datetime
from app.models.schemas import ScenarioType, TrainQueryPayload
from app.services.payload_factory import (
    get_upcoming_sundays,
    get_random_forward_pair,
    generate_payloads,
    ROUTE_STATIONS,
    TRAIN_NO,
)


def test_get_upcoming_sundays():
    sundays = get_upcoming_sundays(count=4)
    assert len(sundays) == 4
    for s in sundays:
        dt = datetime.strptime(s, "%d-%m-%Y")
        assert dt.weekday() == 6  # 6 is Sunday
        assert dt.date() >= datetime.now().date()


def test_get_random_forward_pair():
    for _ in range(50):
        src, dst = get_random_forward_pair()
        assert src in ROUTE_STATIONS
        assert dst in ROUTE_STATIONS
        assert ROUTE_STATIONS.index(src) < ROUTE_STATIONS.index(dst)


def test_generate_payloads_burst_identical():
    payloads = generate_payloads(ScenarioType.BURST_IDENTICAL, total_requests=25)
    assert len(payloads) == 25
    keys = {p.canonical_key for p in payloads}
    assert len(keys) == 1  # Exactly 1 canonical key
    first_key = list(keys)[0]
    assert first_key.startswith(f"{TRAIN_NO}:TEN:MTP:")


def test_generate_payloads_diverse_matrix():
    payloads = generate_payloads(ScenarioType.DIVERSE_MATRIX, total_requests=30)
    assert len(payloads) == 30
    keys = {p.canonical_key for p in payloads}
    # In 30 random requests across 253 pairs * 5 dates * 3 classes, almost all should be distinct
    assert len(keys) > 10


def test_generate_payloads_balanced():
    payloads = generate_payloads(ScenarioType.BALANCED, total_requests=20)
    assert len(payloads) == 20
    keys = [p.canonical_key for p in payloads]
    hot_key_count = sum(1 for k in keys if ":TEN:MTP:" in k and ":SL:GN" in k)
    assert hot_key_count == 10  # 50% identical


def test_generate_payloads_custom():
    custom = [
        TrainQueryPayload(
            trainNo="06030",
            source="RJPM",
            destination="CBE",
            travelClass="3A",
            date="25-10-2026",
            quota="GN",
        )
    ]
    payloads = generate_payloads(ScenarioType.CUSTOM, total_requests=5, custom_payloads=custom)
    assert len(payloads) == 5
    assert all(p.canonical_key == custom[0].canonical_key for p in payloads)

"""
Verification test script for Flight Service.
Tests AirportResolver, SerpApi provider, and normalized response fields with real data.
"""

import asyncio
import sys
import os

# Add service directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.resolver.airport_resolver import AirportResolver
from app.services.flight_service import FlightService
from app.models.request_models import FlightSearchRequest


async def main():
    print("=" * 70)
    print("  FLIGHT SERVICE TEST SUITE")
    print("=" * 70)

    # ── Test 1: Airport Resolver ──────────────────────────────────────────────
    print("\n[1] Testing AirportResolver...")
    resolver = AirportResolver()

    cases = [
        ("Chennai", "MAA"),
        ("Coimbatore", "CJB"),
        ("Delhi", "DEL"),
        ("mumbai", "BOM"),
        ("BLR", "BLR"),
        ("Dubai", "DXB"),
    ]

    for query, expected_code in cases:
        code, name = resolver.resolve(query)
        assert code == expected_code, f"Expected {expected_code}, got {code}"
        print(f"  [OK] '{query}' -> {code} ({name})")

    # ── Test 2: Live Flight Search with Real SerpApi ──────────────────────────
    print("\n[2] Testing Live Flight Search via FlightService...")
    service = FlightService()

    # Search Chennai -> Coimbatore
    req = FlightSearchRequest(
        origin="Chennai",
        destination="Coimbatore",
        outbound_date="2026-10-15",
        travelers=2,
        travel_class="economy",
        currency="INR"
    )

    print(f"  Executing search: {req.origin} -> {req.destination} on {req.outbound_date}...")
    response = await service.search(req)

    assert response.success is True, f"Expected success=True, got {response.success}"
    assert response.data is not None, "Expected response.data to be present"
    data = response.data

    print(f"  [OK] Status: SUCCESS")
    print(f"  [OK] Origin: {data.origin} ({data.origin_name})")
    print(f"  [OK] Destination: {data.destination} ({data.destination_name})")
    print(f"  [OK] Total Flights Combined: {data.total_flights} "
          f"({data.best_flights_count} best, {data.other_flights_count} other)")

    assert data.total_flights > 0, "Expected at least 1 flight result"

    # ── Test 3: Verify Normalized Field Schemas ──────────────────────────────
    print("\n[3] Verifying Normalized Flight Schema...")
    sample_flight = data.flights[0]

    print(f"  Sample Flight Details:")
    print(f"    - flight_id        : {sample_flight.flight_id}")
    print(f"    - airline          : {sample_flight.airline}")
    print(f"    - flight_number    : {sample_flight.flight_number}")
    print(f"    - departure_airport: {sample_flight.departure_airport.id} ({sample_flight.departure_airport.name})")
    print(f"    - arrival_airport  : {sample_flight.arrival_airport.id} ({sample_flight.arrival_airport.name})")
    print(f"    - departure_time   : {sample_flight.departure_time}")
    print(f"    - arrival_time     : {sample_flight.arrival_time}")
    print(f"    - duration_minutes : {sample_flight.duration_minutes} ({sample_flight.duration})")
    print(f"    - stops            : {sample_flight.stops}")
    print(f"    - price            : {sample_flight.price} {sample_flight.currency}")
    print(f"    - travel_class     : {sample_flight.travel_class}")
    print(f"    - is_best_flight   : {sample_flight.is_best_flight}")
    print(f"    - booking_token    : {sample_flight.booking_token[:30] if sample_flight.booking_token else None}...")
    print(f"    - airline_logo     : {sample_flight.airline_logo}")

    # Assertions on required normalized fields
    assert sample_flight.flight_id is not None and len(sample_flight.flight_id) > 0
    assert sample_flight.departure_airport.id == "MAA"
    assert sample_flight.arrival_airport.id == "CJB"
    assert sample_flight.price is not None and sample_flight.price > 0
    assert sample_flight.currency == "INR"
    assert sample_flight.duration_minutes is not None and sample_flight.duration_minutes > 0

    print("\n" + "=" * 70)
    print("  ALL FLIGHT SERVICE VERIFICATION CHECKS PASSED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())

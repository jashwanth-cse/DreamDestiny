"""
Unit tests for AirportResolver using preprocessed data/airports.json.
"""

import pytest
from app.exceptions import AirportNotFoundError
from app.resolver.airport_resolver import AirportResolver


def test_resolve_iata_direct():
    code, name = AirportResolver.resolve("MAA")
    assert code == "MAA"
    assert "Chennai" in name

    code, name = AirportResolver.resolve("JFK")
    assert code == "JFK"
    assert "Kennedy" in name

    code, name = AirportResolver.resolve("LHR")
    assert code == "LHR"
    assert "Heathrow" in name


def test_resolve_canonical_cities():
    code, name = AirportResolver.resolve("Chennai")
    assert code == "MAA"

    code, name = AirportResolver.resolve("Coimbatore")
    assert code == "CJB"

    code, name = AirportResolver.resolve("Paris")
    assert code in ("CDG", "ORY")

    code, name = AirportResolver.resolve("London")
    assert code in ("LHR", "LGW")


def test_resolve_aliases():
    code, name = AirportResolver.resolve("Madras")
    assert code == "MAA"

    code, name = AirportResolver.resolve("Bombay")
    assert code == "BOM"

    code, name = AirportResolver.resolve("Bangalore")
    assert code == "BLR"

    code, name = AirportResolver.resolve("Calcutta")
    assert code == "CCU"

    code, name = AirportResolver.resolve("Peking")
    assert code in ("PEK", "PKX")


def test_country_and_region_indexes():
    in_airports = AirportResolver.find_by_country("IN")
    assert len(in_airports) > 50
    iatas = [a["iata"] for a in in_airports]
    assert "MAA" in iatas
    assert "DEL" in iatas
    assert "BOM" in iatas

    tn_airports = AirportResolver.find_by_region("IN-TN")
    assert len(tn_airports) >= 5
    tn_iatas = [a["iata"] for a in tn_airports]
    assert "MAA" in tn_iatas
    assert "CJB" in tn_iatas


def test_invalid_query_raises():
    with pytest.raises(AirportNotFoundError):
        AirportResolver.resolve("")

    with pytest.raises(AirportNotFoundError):
        AirportResolver.resolve("   ")

    with pytest.raises(AirportNotFoundError):
        AirportResolver.resolve("NonExistentCityXYZ12345")

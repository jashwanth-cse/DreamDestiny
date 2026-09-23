"""
Tests for the Airport Dataset Preprocessor & Generated Dataset
"""

import json
from pathlib import Path
import pytest

from scripts.preprocess_airports import preprocess_airports, IATA_PATTERN


@pytest.fixture(scope="module")
def dataset():
    json_path = Path("data/airports.json")
    assert json_path.exists(), "data/airports.json must exist"
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_dataset_structure(dataset):
    assert "metadata" in dataset
    assert "airports" in dataset
    assert "indexes" in dataset

    meta = dataset["metadata"]
    assert meta["total_airports"] > 3500
    assert meta["total_countries"] > 180
    assert meta["total_cities_indexed"] > 3000

    indexes = dataset["indexes"]
    assert "by_city" in indexes
    assert "by_country" in indexes
    assert "by_region" in indexes


def test_airport_records_validity(dataset):
    airports = dataset["airports"]
    assert len(airports) >= 4000

    for iata, apt in airports.items():
        assert IATA_PATTERN.match(iata), f"Invalid IATA key: {iata}"
        assert apt["iata"] == iata
        assert apt["name"], f"Missing name for {iata}"
        assert apt["city"], f"Missing city for {iata}"
        assert apt["country"], f"Missing country for {iata}"
        assert apt["iso_country"], f"Missing iso_country for {iata}"
        assert apt["iso_region"], f"Missing iso_region for {iata}"
        assert apt["type"] != "closed", f"Closed airport retained: {iata}"
        assert -90.0 <= apt["latitude"] <= 90.0
        assert -180.0 <= apt["longitude"] <= 180.0


def test_global_coverage(dataset):
    by_country = dataset["indexes"]["by_country"]
    major_countries = ["US", "IN", "GB", "FR", "DE", "JP", "AU", "AE", "CA", "CN", "BR"]
    for country in major_countries:
        assert country in by_country, f"Missing country in index: {country}"
        assert len(by_country[country]) > 0, f"No airports in country {country}"

    # Verify key global hubs
    airports = dataset["airports"]
    for hub in ["JFK", "LHR", "HND", "DXB", "CDG", "SIN", "FRA", "SYD", "DEL", "BOM", "MAA"]:
        assert hub in airports, f"Key global airport {hub} missing from dataset"


def test_city_and_alias_lookups(dataset):
    by_city = dataset["indexes"]["by_city"]
    airports = dataset["airports"]

    # Direct city
    assert "chennai" in by_city
    assert "MAA" in by_city["chennai"]

    assert "coimbatore" in by_city
    assert "CJB" in by_city["coimbatore"]

    # Historical aliases
    assert "madras" in by_city
    assert "MAA" in by_city["madras"]

    assert "bombay" in by_city
    assert "BOM" in by_city["bombay"]

    assert "calcutta" in by_city
    assert "CCU" in by_city["calcutta"]

    assert "bangalore" in by_city
    assert "BLR" in by_city["bangalore"]

    # Global multi-airport city
    assert "london" in by_city
    london_codes = by_city["london"]
    assert "LHR" in london_codes
    # LHR is a large_airport and should be first or among the top
    assert airports[london_codes[0]]["type"] == "large_airport"


def test_region_lookups(dataset):
    by_region = dataset["indexes"]["by_region"]

    assert "IN-TN" in by_region
    tn_airports = by_region["IN-TN"]
    assert "MAA" in tn_airports
    assert "CJB" in tn_airports

    assert "US-NY" in by_region
    assert "JFK" in by_region["US-NY"]


def test_preprocessor_error_on_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        preprocess_airports(
            csv_path=tmp_path / "non_existent.csv",
            output_path=tmp_path / "out.json",
        )


def test_preprocessor_error_on_invalid_csv_headers(tmp_path):
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("id,some_col\n1,val\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing required columns"):
        preprocess_airports(
            csv_path=bad_csv,
            output_path=tmp_path / "out.json",
        )

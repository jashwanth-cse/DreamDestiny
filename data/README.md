# Airport Dataset & Preprocessing Pipeline

This directory contains the production-ready, preprocessed global airport dataset (`airports.json`) and configurable alias mappings (`aliases.json`) used by the Flight Service.

---

## 1. Overview

The raw OurAirports dataset contains ~86,000+ facilities globally, including closed airfields, private heliports, and grass strips. To maximize runtime search speed, reduce memory footprint, and prevent invalid flight searches, the raw CSV is preprocessed into a compact, indexed JSON dataset:

- **Source**: `airports.csv` (86,119 rows, ~12.7 MB)
- **Output**: `data/airports.json` (4,133 active scheduled airports, ~1.2 MB)
- **Runtime Performance**: Sub-millisecond $O(1)$ lookups for IATA codes, cities, countries, and aliases with zero CSV parsing at runtime.

---

## 2. Dataset Regeneration

Whenever `airports.csv` is updated (e.g. from OurAirports releases), regenerate `data/airports.json` by running:

```bash
python scripts/preprocess_airports.py
```

This will automatically:
1. Validate headers, coordinates, and IATA codes.
2. Filter for active commercial airports (`scheduled_service=yes`, valid IATA code, `type!=closed`).
3. Deduplicate and normalize airport names, cities, countries, and coordinates.
4. Build runtime indexes (`by_city`, `by_country`, `by_region`).
5. Output `data/airports.json` and sync it to `transport-service/flight/data/airports.json`.
6. Print a comprehensive statistics summary.

### CLI Options

| Flag | Default | Description |
|---|---|---|
| `--csv` | `airports.csv` | Path to the source raw CSV file |
| `--output` | `data/airports.json` | Destination path for the generated JSON |
| `--aliases` | `data/aliases.json` | Path to the configurable city/IATA alias file |
| `--copy-to` | `transport-service/flight/data/airports.json` | Secondary destination path(s) to sync the dataset to |
| `--strict` | `False` | Fail and abort execution on any invalid row instead of skipping |
| `--pretty` | `False` | Formats output JSON with indentation (default is compact) |

#### Example Commands

```bash
# Standard regeneration and sync
python scripts/preprocess_airports.py

# Strict validation mode (fails if any scheduled airport has malformed data)
python scripts/preprocess_airports.py --strict

# Custom paths
python scripts/preprocess_airports.py --csv /path/to/custom_airports.csv --output data/airports.json
```

---

## 3. Preprocessing & Filtering Rules

A record is retained in `airports.json` **only** if it satisfies all of the following:

1. **Scheduled Service**: `scheduled_service == "yes"` (filters out private strips and abandoned fields).
2. **Valid IATA Code**: Must match the standard 3-letter uppercase ASCII format `^[A-Z]{3}$`.
3. **Open Status**: `type != "closed"`.
4. **Valid Coordinates**: Latitude within $[-90.0, 90.0]$, longitude within $[-180.0, 180.0]$.
5. **Required Metadata**: Non-empty airport name, ISO 3166-1 country code, and ISO 3166-2 region code.

### Deduplication Priority
If duplicate IATA codes occur, the preprocessor deterministically resolves the conflict based on facility type hierarchy:
$$\text{large\_airport} > \text{medium\_airport} > \text{small\_airport} > \text{seaplane\_base} > \text{heliport}$$

---

## 4. Configurable City Aliases (`aliases.json`)

`data/aliases.json` allows configuring custom city name mappings to:
1. **Canonical city names** (e.g. `"bombay": "mumbai"`, `"peking": "beijing"`, `"saigon": "ho chi minh city"`).
2. **Direct IATA codes** (e.g. `"goa": "GOI"`, `"rajapalayam": "IXM"`, `"ooty": "CJB"`).

To add new aliases, simply edit `data/aliases.json` and re-run `python scripts/preprocess_airports.py`.

---

## 5. Dataset Schema (`airports.json`)

```json
{
  "metadata": {
    "version": "1.0.0",
    "generated_at": "2026-09-23T12:40:48.477569+00:00",
    "source_file": "airports.csv",
    "total_airports": 4133,
    "total_countries": 234,
    "total_regions": 1643,
    "total_cities_indexed": 6894
  },
  "airports": {
    "MAA": {
      "iata": "MAA",
      "name": "Chennai International Airport",
      "city": "Chennai",
      "normalized_city": "chennai",
      "country": "India",
      "iso_country": "IN",
      "region": "Tamil Nadu",
      "iso_region": "IN-TN",
      "latitude": 12.990005,
      "longitude": 80.169296,
      "type": "large_airport"
    }
  },
  "indexes": {
    "by_city": {
      "chennai": ["MAA"],
      "madras": ["MAA"],
      "london": ["LGW", "LHR", "LCY", "STN", "LTN", "SEN"]
    },
    "by_country": {
      "IN": ["MAA", "BOM", "DEL", "..."],
      "US": ["JFK", "LAX", "ORD", "..."]
    },
    "by_region": {
      "IN-TN": ["MAA", "CJB", "TRZ", "IXM", "SXV", "TCR"],
      "US-NY": ["JFK", "LGA", "..."]
    }
  }
}
```

---

## 6. Runtime Integration

`AirportResolver` (`transport-service/flight/app/resolver/airport_resolver.py`) loads `data/airports.json` directly into memory at startup. Lookups are executed in sub-millisecond time:

- **IATA Code Lookup**: `airports[code]` $\to O(1)$
- **City & Alias Lookup**: `indexes.by_city[normalized_city]` $\to O(1)$
- **Country Filter**: `indexes.by_country[iso_country]` $\to O(1)$
- **Region Filter**: `indexes.by_region[iso_region]` $\to O(1)$

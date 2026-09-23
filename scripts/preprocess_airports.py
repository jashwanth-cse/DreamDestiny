#!/usr/bin/env python3
"""
Airport Dataset Preprocessor
============================
Reads the raw OurAirports CSV dataset (airports.csv), filters, validates,
normalizes, and outputs a high-performance, compact JSON dataset for runtime lookup.

Key Requirements:
  - Global coverage (all countries, not India-specific)
  - Retain only scheduled_service=yes, valid 3-letter IATA code, type!=closed
  - Robust deduplication and normalization
  - Pre-computed indexes: by_city, by_country, by_region
  - Configurable alias support (e.g. Madras -> Chennai, Bombay -> Mumbai)
  - Clear summary report and strict validation

Usage:
  python scripts/preprocess_airports.py [--csv airports.csv] [--output data/airports.json] [--strict]
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import shutil
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Required CSV Columns ──────────────────────────────────────────────────────
REQUIRED_COLUMNS = {
    "name",
    "type",
    "latitude_deg",
    "longitude_deg",
    "iso_country",
    "iso_region",
    "scheduled_service",
    "iata_code",
}

# ── Airport Type Priority (Higher is preferred in deduplication) ─────────────
AIRPORT_TYPE_PRIORITY = {
    "large_airport": 5,
    "medium_airport": 4,
    "small_airport": 3,
    "seaplane_base": 2,
    "heliport": 1,
    "balloonport": 0,
}

# ── ISO 3166-1 alpha-2 Standard Country Code to Name Mapping ─────────────────
ISO_3166_COUNTRIES: Dict[str, str] = {
    "AD": "Andorra", "AE": "United Arab Emirates", "AF": "Afghanistan", "AG": "Antigua and Barbuda",
    "AI": "Anguilla", "AL": "Albania", "AM": "Armenia", "AO": "Angola", "AQ": "Antarctica",
    "AR": "Argentina", "AS": "American Samoa", "AT": "Austria", "AU": "Australia", "AW": "Aruba",
    "AX": "Aland Islands", "AZ": "Azerbaijan", "BA": "Bosnia and Herzegovina", "BB": "Barbados",
    "BD": "Bangladesh", "BE": "Belgium", "BF": "Burkina Faso", "BG": "Bulgaria", "BH": "Bahrain",
    "BI": "Burundi", "BJ": "Benin", "BL": "Saint Barthelemy", "BM": "Bermuda", "BN": "Brunei",
    "BO": "Bolivia", "BQ": "Bonaire, Sint Eustatius and Saba", "BR": "Brazil", "BS": "Bahamas",
    "BT": "Bhutan", "BV": "Bouvet Island", "BW": "Botswana", "BY": "Belarus", "BZ": "Belize",
    "CA": "Canada", "CC": "Cocos Islands", "CD": "Democratic Republic of the Congo",
    "CF": "Central African Republic", "CG": "Republic of the Congo", "CH": "Switzerland",
    "CI": "Cote d'Ivoire", "CK": "Cook Islands", "CL": "Chile", "CM": "Cameroon", "CN": "China",
    "CO": "Colombia", "CR": "Costa Rica", "CU": "Cuba", "CV": "Cape Verde", "CW": "Curacao",
    "CX": "Christmas Island", "CY": "Cyprus", "CZ": "Czech Republic", "DE": "Germany",
    "DJ": "Djibouti", "DK": "Denmark", "DM": "Dominica", "DO": "Dominican Republic", "DZ": "Algeria",
    "EC": "Ecuador", "EE": "Estonia", "EG": "Egypt", "EH": "Western Sahara", "ER": "Eritrea",
    "ES": "Spain", "ET": "Ethiopia", "FI": "Finland", "FJ": "Fiji", "FK": "Falkland Islands",
    "FM": "Micronesia", "FO": "Faroe Islands", "FR": "France", "GA": "Gabon", "GB": "United Kingdom",
    "GD": "Grenada", "GE": "Georgia", "GF": "French Guiana", "GG": "Guernsey", "GH": "Ghana",
    "GI": "Gibraltar", "GL": "Greenland", "GM": "Gambia", "GN": "Guinea", "GP": "Guadeloupe",
    "GQ": "Equatorial Guinea", "GR": "Greece", "GS": "South Georgia and South Sandwich Islands",
    "GT": "Guatemala", "GU": "Guam", "GW": "Guinea-Bissau", "GY": "Guyana", "HK": "Hong Kong",
    "HM": "Heard Island and McDonald Islands", "HN": "Honduras", "HR": "Croatia", "HT": "Haiti",
    "HU": "Hungary", "ID": "Indonesia", "IE": "Ireland", "IL": "Israel", "IM": "Isle of Man",
    "IN": "India", "IO": "British Indian Ocean Territory", "IQ": "Iraq", "IR": "Iran",
    "IS": "Iceland", "IT": "Italy", "JE": "Jersey", "JM": "Jamaica", "JO": "Jordan",
    "JP": "Japan", "KE": "Kenya", "KG": "Kyrgyzstan", "KH": "Cambodia", "KI": "Kiribati",
    "KM": "Comoros", "KN": "Saint Kitts and Nevis", "KP": "North Korea", "KR": "South Korea",
    "KW": "Kuwait", "KY": "Cayman Islands", "KZ": "Kazakhstan", "LA": "Laos", "LB": "Lebanon",
    "LC": "Saint Lucia", "LI": "Liechtenstein", "LK": "Sri Lanka", "LR": "Liberia", "LS": "Lesotho",
    "LT": "Lithuania", "LU": "Luxembourg", "LV": "Latvia", "LY": "Libya", "MA": "Morocco",
    "MC": "Monaco", "MD": "Moldova", "ME": "Montenegro", "MF": "Saint Martin", "MG": "Madagascar",
    "MH": "Marshall Islands", "MK": "North Macedonia", "ML": "Mali", "MM": "Myanmar",
    "MN": "Mongolia", "MO": "Macao", "MP": "Northern Mariana Islands", "MQ": "Martinique",
    "MR": "Mauritania", "MS": "Montserrat", "MT": "Malta", "MU": "Mauritius", "MV": "Maldives",
    "MW": "Malawi", "MX": "Mexico", "MY": "Malaysia", "MZ": "Mozambique", "NA": "Namibia",
    "NC": "New Caledonia", "NE": "Niger", "NF": "Norfolk Island", "NG": "Nigeria",
    "NI": "Nicaragua", "NL": "Netherlands", "NO": "Norway", "NP": "Nepal", "NR": "Nauru",
    "NU": "Niue", "NZ": "New Zealand", "OM": "Oman", "PA": "Panama", "PE": "Peru",
    "PF": "French Polynesia", "PG": "Papua New Guinea", "PH": "Philippines", "PK": "Pakistan",
    "PL": "Poland", "PM": "Saint Pierre and Miquelon", "PN": "Pitcairn", "PR": "Puerto Rico",
    "PS": "Palestine", "PT": "Portugal", "PW": "Palau", "PY": "Paraguay", "QA": "Qatar",
    "RE": "Reunion", "RO": "Romania", "RS": "Serbia", "RU": "Russia", "RW": "Rwanda",
    "SA": "Saudi Arabia", "SB": "Solomon Islands", "SC": "Seychelles", "SD": "Sudan",
    "SE": "Sweden", "SG": "Singapore", "SH": "Saint Helena", "SI": "Slovenia",
    "SJ": "Svalbard and Jan Mayen", "SK": "Slovakia", "SL": "Sierra Leone", "SM": "San Marino",
    "SN": "Senegal", "SO": "Somalia", "SR": "Suriname", "SS": "South Sudan",
    "ST": "Sao Tome and Principe", "SV": "El Salvador", "SX": "Sint Maarten", "SY": "Syria",
    "SZ": "Eswatini", "TC": "Turks and Caicos Islands", "TD": "Chad", "TF": "French Southern Territories",
    "TG": "Togo", "TH": "Thailand", "TJ": "Tajikistan", "TK": "Tokelau", "TL": "Timor-Leste",
    "TM": "Turkmenistan", "TN": "Tunisia", "TO": "Tonga", "TR": "Turkey", "TT": "Trinidad and Tobago",
    "TV": "Tuvalu", "TW": "Taiwan", "TZ": "Tanzania", "UA": "Ukraine", "UG": "Uganda",
    "UM": "United States Minor Outlying Islands", "US": "United States", "UY": "Uruguay",
    "UZ": "Uzbekistan", "VA": "Vatican City", "VC": "Saint Vincent and the Grenadines",
    "VE": "Venezuela", "VG": "British Virgin Islands", "VI": "U.S. Virgin Islands",
    "VN": "Vietnam", "VU": "Vanuatu", "WF": "Wallis and Futuna", "WS": "Samoa",
    "XK": "Kosovo", "YE": "Yemen", "YT": "Mayotte", "ZA": "South Africa", "ZM": "Zambia",
    "ZW": "Zimbabwe",
}

IATA_PATTERN = re.compile(r"^[A-Z]{3}$")


def strip_accents(s: str) -> str:
    """Normalize unicode string by removing diacritical marks."""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def clean_text(s: Optional[str]) -> str:
    """Trim and collapse consecutive whitespaces."""
    if not s:
        return ""
    return re.sub(r"\s+", " ", s.strip())


def normalize_city_name(municipality: Optional[str], airport_name: str) -> str:
    """
    Returns clean city name.
    If municipality is empty, derives reasonable city name from airport name.
    """
    m = clean_text(municipality)
    if m:
        return m

    # Fallback: Strip common airport suffixes from name
    fallback = re.sub(
        r"(?i)\s+(international\s+)?(airport|airfield|aerodrome|seaplane\s+base|heliport|army\s+aviation\s+centre)$",
        "",
        clean_text(airport_name),
    ).strip()

    return fallback or clean_text(airport_name)


def load_aliases(alias_path: Optional[Path]) -> Dict[str, str]:
    """Load configurable city aliases from JSON file."""
    if not alias_path or not alias_path.exists():
        return {}
    try:
        with open(alias_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            aliases = data.get("aliases", data)
            return {
                strip_accents(k).strip().lower(): clean_text(v).lower()
                for k, v in aliases.items()
                if isinstance(k, str) and isinstance(v, str)
            }
    except Exception as exc:
        logger.warning("Could not load alias file %s: %s", alias_path, exc)
        return {}


class PreprocessSummary:
    """Accumulates and prints statistics for the preprocessing run."""

    def __init__(self) -> None:
        self.total_input_rows: int = 0
        self.excluded_not_scheduled: int = 0
        self.excluded_closed: int = 0
        self.excluded_missing_iata: int = 0
        self.excluded_invalid_iata: int = 0
        self.excluded_invalid_coordinates: int = 0
        self.excluded_missing_required_fields: int = 0
        self.duplicates_removed: int = 0
        self.retained_airports: int = 0
        self.countries_count: int = 0
        self.regions_count: int = 0
        self.cities_count: int = 0
        self.output_file_size_bytes: int = 0
        self.output_path: str = ""

    def print_report(self) -> None:
        print("\n" + "=" * 65)
        print("         AIRPORT DATASET PREPROCESSING SUMMARY")
        print("=" * 65)
        print(f"  Input CSV Total Rows        : {self.total_input_rows:,}")
        print(f"  Excluded (Not Scheduled)    : {self.excluded_not_scheduled:,}")
        print(f"  Excluded (Closed Type)      : {self.excluded_closed:,}")
        print(f"  Excluded (Missing IATA)     : {self.excluded_missing_iata:,}")
        print(f"  Excluded (Invalid IATA)     : {self.excluded_invalid_iata:,}")
        print(f"  Excluded (Invalid Coords)   : {self.excluded_invalid_coordinates:,}")
        print(f"  Excluded (Missing Fields)   : {self.excluded_missing_required_fields:,}")
        print(f"  Duplicate IATAs Resolved    : {self.duplicates_removed:,}")
        print("-" * 65)
        print(f"  RETAINED AIRPORTS           : {self.retained_airports:,}")
        print(f"  Unique Countries Covered    : {self.countries_count:,}")
        print(f"  Unique Regions Covered      : {self.regions_count:,}")
        print(f"  Unique Cities Indexed       : {self.cities_count:,}")
        if self.output_file_size_bytes > 0:
            kb = self.output_file_size_bytes / 1024
            mb = kb / 1024
            size_str = f"{mb:.2f} MB ({kb:.1f} KB)"
            print(f"  Output File Size            : {size_str}")
            print(f"  Destination                 : {self.output_path}")
        print("=" * 65 + "\n")


def preprocess_airports(
    csv_path: Path,
    output_path: Path,
    alias_path: Optional[Path] = None,
    copy_to: Optional[List[Path]] = None,
    strict: bool = False,
    pretty: bool = False,
) -> PreprocessSummary:
    """
    Main preprocessing pipeline.
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"Source airport CSV not found: {csv_path.resolve()}")

    summary = PreprocessSummary()
    summary.output_path = str(output_path.resolve())

    aliases = load_aliases(alias_path)
    logger.info("Loaded %d city alias mappings", len(aliases))

    # Read CSV
    retained_map: Dict[str, Dict[str, Any]] = {}
    row_number = 1  # 1-indexed (header is 1)

    with open(csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"CSV file '{csv_path}' is empty or unreadable.")

        # Validate headers
        missing_cols = REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing_cols:
            raise ValueError(f"CSV is missing required columns: {sorted(missing_cols)}")

        for row in reader:
            row_number += 1
            summary.total_input_rows += 1

            # 1. Scheduled service check
            sched = clean_text(row.get("scheduled_service")).lower()
            if sched != "yes":
                summary.excluded_not_scheduled += 1
                continue

            # 2. Airport type check
            airport_type = clean_text(row.get("type")).lower()
            if airport_type == "closed" or not airport_type:
                summary.excluded_closed += 1
                continue

            # 3. IATA code validation
            iata = clean_text(row.get("iata_code")).upper()
            if not iata:
                summary.excluded_missing_iata += 1
                continue

            if not IATA_PATTERN.match(iata):
                msg = f"Row {row_number}: Invalid IATA code format '{iata}'"
                if strict:
                    raise ValueError(msg)
                logger.warning(msg)
                summary.excluded_invalid_iata += 1
                continue

            # 4. Required fields check
            name = clean_text(row.get("name"))
            iso_country = clean_text(row.get("iso_country")).upper()
            iso_region = clean_text(row.get("iso_region")).upper()

            if not name or not iso_country or not iso_region:
                msg = f"Row {row_number} (IATA: {iata}): Missing required field (name/iso_country/iso_region)"
                if strict:
                    raise ValueError(msg)
                logger.warning(msg)
                summary.excluded_missing_required_fields += 1
                continue

            # 5. Coordinate validation
            lat_raw = clean_text(row.get("latitude_deg"))
            lon_raw = clean_text(row.get("longitude_deg"))
            try:
                lat = float(lat_raw)
                lon = float(lon_raw)
                if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
                    raise ValueError(f"Coordinates out of bounds: lat={lat}, lon={lon}")
            except Exception as exc:
                msg = f"Row {row_number} (IATA: {iata}): Invalid coordinates ('{lat_raw}', '{lon_raw}'): {exc}"
                if strict:
                    raise ValueError(msg)
                logger.warning(msg)
                summary.excluded_invalid_coordinates += 1
                continue

            # 6. Normalization
            city = normalize_city_name(row.get("municipality"), name)
            normalized_city = strip_accents(city).lower()
            country_name = ISO_3166_COUNTRIES.get(iso_country, iso_country)

            # Optional keywords for additional aliases
            raw_keywords = clean_text(row.get("keywords"))
            keywords = [
                strip_accents(k).lower()
                for k in raw_keywords.split(",")
                if clean_text(k)
            ] if raw_keywords else []

            airport_entry = {
                "iata": iata,
                "name": name,
                "city": city,
                "normalized_city": normalized_city,
                "country": country_name,
                "iso_country": iso_country,
                "iso_region": iso_region,
                "latitude": round(lat, 6),
                "longitude": round(lon, 6),
                "type": airport_type,
                "keywords": keywords,
            }

            # 7. Deduplication
            if iata in retained_map:
                existing = retained_map[iata]
                existing_priority = AIRPORT_TYPE_PRIORITY.get(existing["type"], 0)
                new_priority = AIRPORT_TYPE_PRIORITY.get(airport_type, 0)
                summary.duplicates_removed += 1
                logger.warning(
                    "Duplicate IATA '%s' found. Comparing '%s' (%s) vs '%s' (%s)",
                    iata,
                    existing["name"],
                    existing["type"],
                    name,
                    airport_type,
                )
                if new_priority > existing_priority:
                    retained_map[iata] = airport_entry
            else:
                retained_map[iata] = airport_entry

    # ── 8. Build Indexes ──────────────────────────────────────────────────────
    by_city: Dict[str, List[str]] = {}
    by_country: Dict[str, List[str]] = {}
    by_region: Dict[str, List[str]] = {}

    unique_countries: Set[str] = set()
    unique_regions: Set[str] = set()

    # Sort airports deterministically by IATA
    sorted_airports = dict(sorted(retained_map.items()))

    for iata, apt in sorted_airports.items():
        city_key = apt["normalized_city"]
        c_code = apt["iso_country"]
        r_code = apt["iso_region"]

        unique_countries.add(c_code)
        unique_regions.add(r_code)

        # by_country index
        by_country.setdefault(c_code, []).append(iata)

        # by_region index
        by_region.setdefault(r_code, []).append(iata)

        # by_city index (canonical city name)
        if city_key not in by_city:
            by_city[city_key] = []
        if iata not in by_city[city_key]:
            by_city[city_key].append(iata)

        # Keywords / alternative names from CSV
        for kw in apt.get("keywords", []):
            if kw and kw != city_key:
                if kw not in by_city:
                    by_city[kw] = []
                if iata not in by_city[kw]:
                    by_city[kw].append(iata)

    # Apply external alias mappings
    for alias_name, target in aliases.items():
        alias_clean = strip_accents(alias_name).lower()
        upper_target = target.strip().upper()
        target_lower = strip_accents(target).lower()

        # Check if target is directly an IATA code (e.g. "GOI", "IXM")
        if IATA_PATTERN.match(upper_target) and upper_target in sorted_airports:
            if alias_clean not in by_city:
                by_city[alias_clean] = []
            if upper_target not in by_city[alias_clean]:
                by_city[alias_clean].insert(0, upper_target)
        # Check if target matches an existing city key
        elif target_lower in by_city:
            target_airports = by_city[target_lower]
            if alias_clean not in by_city:
                by_city[alias_clean] = []
            for a in target_airports:
                if a not in by_city[alias_clean]:
                    by_city[alias_clean].append(a)

    # Sort each city's airport list by airport priority (largest first)
    for city_k, iata_list in by_city.items():
        iata_list.sort(
            key=lambda code: AIRPORT_TYPE_PRIORITY.get(
                sorted_airports.get(code, {}).get("type", ""), 0
            ),
            reverse=True,
        )

    # Clean internal helper fields from airports dict
    for apt in sorted_airports.values():
        if "keywords" in apt and not apt["keywords"]:
            del apt["keywords"]

    # ── 9. Final Payload Construction ─────────────────────────────────────────
    dataset = {
        "metadata": {
            "version": "1.0.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_file": str(csv_path.name),
            "total_airports": len(sorted_airports),
            "total_countries": len(unique_countries),
            "total_regions": len(unique_regions),
            "total_cities_indexed": len(by_city),
        },
        "airports": sorted_airports,
        "indexes": {
            "by_city": by_city,
            "by_country": by_country,
            "by_region": by_region,
        },
    }

    # ── 10. Write Output ──────────────────────────────────────────────────────
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as out_f:
        if pretty:
            json.dump(dataset, out_f, indent=2, ensure_ascii=False)
        else:
            json.dump(dataset, out_f, separators=(",", ":"), ensure_ascii=False)

    summary.output_file_size_bytes = output_path.stat().st_size
    summary.retained_airports = len(sorted_airports)
    summary.countries_count = len(unique_countries)
    summary.regions_count = len(unique_regions)
    summary.cities_count = len(by_city)

    # Optional copy to secondary targets
    if copy_to:
        for dest in copy_to:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(output_path, dest)
            logger.info("Copied dataset to: %s", dest.resolve())

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Production Airport Dataset Preprocessor"
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("airports.csv"),
        help="Path to source airports.csv (default: airports.csv)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/airports.json"),
        help="Path to output JSON dataset (default: data/airports.json)",
    )
    parser.add_argument(
        "--aliases",
        type=Path,
        default=Path("data/aliases.json"),
        help="Path to aliases JSON (default: data/aliases.json)",
    )
    parser.add_argument(
        "--copy-to",
        type=Path,
        nargs="*",
        default=[Path("transport-service/flight/data/airports.json")],
        help="Optional additional file paths to copy the generated JSON to",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Abort on any invalid or malformed scheduled airport record",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Output pretty-printed JSON (default: compact)",
    )

    args = parser.parse_args()

    try:
        summary = preprocess_airports(
            csv_path=args.csv,
            output_path=args.output,
            alias_path=args.aliases if args.aliases.exists() else None,
            copy_to=args.copy_to,
            strict=args.strict,
            pretty=args.pretty,
        )
        summary.print_report()
    except Exception as exc:
        logger.error("Preprocessing failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()

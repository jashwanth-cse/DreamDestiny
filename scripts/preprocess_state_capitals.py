#!/usr/bin/env python3
"""
State Capitals Preprocessor & Validator
=======================================
Generates and validates data/state_capitals.json using data/railway_stations.json.

Maps every Indian state and union territory to its official capital city and
primary railway station code.

Usage:
    python scripts/preprocess_state_capitals.py [--stations PATH] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATIONS_PATH = _ROOT / "data" / "railway_stations.json"
DEFAULT_OUTPUT_PATH   = _ROOT / "data" / "state_capitals.json"

# Fallback codes present in PRESEEDED_STATIONS if not directly in railway_stations.json
PRESEEDED_VALID_CODES = {"TVC", "MAO", "ERS", "CBE"}

# Canonical mapping of Indian States & Union Territories to capital and station code
# All 28 States and 8 Union Territories
CAPITAL_MAPPINGS: Dict[str, Dict[str, str]] = {
    # ── States ───────────────────────────────────────────────────────────────
    "ANDHRA PRADESH": {
        "capital": "Amaravati",
        "station_code": "BZA",
        "station_name": "Vijayawada Jn"
    },
    "ARUNACHAL PRADESH": {
        "capital": "Itanagar",
        "station_code": "NHLN",
        "station_name": "Naharlagun"
    },
    "ASSAM": {
        "capital": "Dispur",
        "station_code": "GHY",
        "station_name": "Guwahati"
    },
    "BIHAR": {
        "capital": "Patna",
        "station_code": "PNBE",
        "station_name": "Patna Jn"
    },
    "CHHATTISGARH": {
        "capital": "Raipur",
        "station_code": "R",
        "station_name": "Raipur Jn"
    },
    "GOA": {
        "capital": "Panaji",
        "station_code": "MAO",
        "station_name": "Madgaon Jn"
    },
    "GUJARAT": {
        "capital": "Gandhinagar",
        "station_code": "GNC",
        "station_name": "Gandhinagar Capital"
    },
    "HARYANA": {
        "capital": "Chandigarh",
        "station_code": "CDG",
        "station_name": "Chandigarh"
    },
    "HIMACHAL PRADESH": {
        "capital": "Shimla",
        "station_code": "SML",
        "station_name": "Shimla"
    },
    "JHARKHAND": {
        "capital": "Ranchi",
        "station_code": "RNC",
        "station_name": "Ranchi Jn"
    },
    "KARNATAKA": {
        "capital": "Bengaluru",
        "station_code": "SBC",
        "station_name": "KSR Bengaluru"
    },
    "KERALA": {
        "capital": "Thiruvananthapuram",
        "station_code": "TVC",
        "station_name": "Thiruvananthapuram Central"
    },
    "MADHYA PRADESH": {
        "capital": "Bhopal",
        "station_code": "BPL",
        "station_name": "Bhopal Jn"
    },
    "MAHARASHTRA": {
        "capital": "Mumbai",
        "station_code": "CSMT",
        "station_name": "Chhatrapati Shivaji Maharaj Terminus"
    },
    "MANIPUR": {
        "capital": "Imphal",
        "station_code": "JRBM",
        "station_name": "Jiribam"
    },
    "MEGHALAYA": {
        "capital": "Shillong",
        "station_code": "MNDP",
        "station_name": "Mendipathar"
    },
    "MIZORAM": {
        "capital": "Aizawl",
        "station_code": "BHRB",
        "station_name": "Bhairabi"
    },
    "NAGALAND": {
        "capital": "Kohima",
        "station_code": "DMV",
        "station_name": "Dimapur"
    },
    "ODISHA": {
        "capital": "Bhubaneswar",
        "station_code": "BBS",
        "station_name": "Bhubaneswar"
    },
    "PUNJAB": {
        "capital": "Chandigarh",
        "station_code": "CDG",
        "station_name": "Chandigarh"
    },
    "RAJASTHAN": {
        "capital": "Jaipur",
        "station_code": "JP",
        "station_name": "Jaipur Jn"
    },
    "SIKKIM": {
        "capital": "Gangtok",
        "station_code": "NJP",
        "station_name": "New Jalpaiguri"
    },
    "TAMIL NADU": {
        "capital": "Chennai",
        "station_code": "MAS",
        "station_name": "MGR Chennai Central"
    },
    "TELANGANA": {
        "capital": "Hyderabad",
        "station_code": "SC",
        "station_name": "Secunderabad Jn"
    },
    "TRIPURA": {
        "capital": "Agartala",
        "station_code": "AGTL",
        "station_name": "Agartala"
    },
    "UTTAR PRADESH": {
        "capital": "Lucknow",
        "station_code": "LKO",
        "station_name": "Lucknow Charbagh"
    },
    "UTTARAKHAND": {
        "capital": "Dehradun",
        "station_code": "DDN",
        "station_name": "Dehradun"
    },
    "WEST BENGAL": {
        "capital": "Kolkata",
        "station_code": "HWH",
        "station_name": "Howrah Jn"
    },

    # ── Union Territories ────────────────────────────────────────────────────
    "DELHI": {
        "capital": "New Delhi",
        "station_code": "NDLS",
        "station_name": "New Delhi"
    },
    "CHANDIGARH": {
        "capital": "Chandigarh",
        "station_code": "CDG",
        "station_name": "Chandigarh"
    },
    "JAMMU AND KASHMIR": {
        "capital": "Srinagar / Jammu",
        "station_code": "JAT",
        "station_name": "Jammu Tawi"
    },
    "LADAKH": {
        "capital": "Leh",
        "station_code": "JAT",
        "station_name": "Jammu Tawi"
    },
    "PUDUCHERRY": {
        "capital": "Puducherry",
        "station_code": "PDY",
        "station_name": "Puducherry"
    },
    "ANDAMAN AND NICOBAR ISLANDS": {
        "capital": "Port Blair",
        "station_code": "MAS",
        "station_name": "Chennai Central (Sea/Air Port Link)"
    },
    "DADRA AND NAGAR HAVELI AND DAMAN AND DIU": {
        "capital": "Daman",
        "station_code": "VAPI",
        "station_name": "Vapi"
    },
    "LAKSHADWEEP": {
        "capital": "Kavaratti",
        "station_code": "ERS",
        "station_name": "Ernakulam Jn (Port Link)"
    }
}


def build_and_validate_capitals(stations_path: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    with open(stations_path, "r", encoding="utf-8") as f:
        stations_data = json.load(f)

    stations = stations_data.get("stations", {})

    output_capitals: Dict[str, Dict[str, str]] = {}
    verified_in_dataset = 0
    verified_in_preseeded = 0
    invalid_codes = []

    for state, info in CAPITAL_MAPPINGS.items():
        code = info["station_code"]
        if code in stations:
            verified_in_dataset += 1
            stn_name = stations[code].get("station_name", info["station_name"])
        elif code in PRESEEDED_VALID_CODES:
            verified_in_preseeded += 1
            stn_name = info["station_name"]
        else:
            invalid_codes.append((state, code))
            stn_name = info["station_name"]

        output_capitals[state] = {
            "capital": info["capital"],
            "station_code": code,
            "station_name": stn_name
        }

    report = {
        "total_mappings": len(CAPITAL_MAPPINGS),
        "verified_in_dataset": verified_in_dataset,
        "verified_in_preseeded": verified_in_preseeded,
        "invalid_codes": invalid_codes,
        "generated_at": datetime.now(timezone.utc).isoformat()
    }

    return output_capitals, report


def main():
    parser = argparse.ArgumentParser(description="Preprocess and validate state capitals mapping")
    parser.add_argument("--stations", default=str(DEFAULT_STATIONS_PATH), help="Path to railway_stations.json")
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT_PATH), help="Path to state_capitals.json")
    args = parser.parse_args()

    stations_path = Path(args.stations)
    out_path = Path(args.out)

    if not stations_path.exists():
        sys.exit(f"ERROR: {stations_path} not found.")

    output_capitals, report = build_and_validate_capitals(stations_path)

    print("\n" + "=" * 60)
    print("  STATE CAPITALS VALIDATION REPORT")
    print("=" * 60)
    print(f"  Total States/UTs mapped : {report['total_mappings']}")
    print(f"  Verified in JSON dataset: {report['verified_in_dataset']}")
    print(f"  Verified in Pre-seeded  : {report['verified_in_preseeded']}")
    print(f"  Invalid / Missing codes : {len(report['invalid_codes'])}")
    if report["invalid_codes"]:
        for state, code in report["invalid_codes"]:
            print(f"    WARNING: {state} -> {code} not in dataset or preseeded")
    print("=" * 60 + "\n")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output_capitals, f, indent=2, ensure_ascii=False)

    log.info("Saved state capitals dataset to %s", out_path)


if __name__ == "__main__":
    main()

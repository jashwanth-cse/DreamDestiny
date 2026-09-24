#!/usr/bin/env python3
"""
Division Hubs Preprocessor & Validator
======================================
Generates and validates data/division_hubs.json using data/railway_stations.json.

Maps every Indian Railways division to its designated primary hub station code.

Usage:
    python scripts/preprocess_division_hubs.py [--stations PATH] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATIONS_PATH = _ROOT / "data" / "railway_stations.json"
DEFAULT_OUTPUT_PATH   = _ROOT / "data" / "division_hubs.json"

# All 66 railway divisions identified from the station dataset
DIVISION_HUB_MAPPINGS: Dict[str, Dict[str, str]] = {
    "ADI":  {"hub_code": "ADI",  "hub_name": "Ahmedabad Jn", "zone": "WR"},
    "ADRA": {"hub_code": "ADRA", "hub_name": "Adra Jn", "zone": "SER"},
    "AGRA": {"hub_code": "AGC",  "hub_name": "Agra Cantt", "zone": "NCR"},
    "AII":  {"hub_code": "AII",  "hub_name": "Ajmer Jn", "zone": "NWR"},
    "APDJ": {"hub_code": "APDJ", "hub_name": "Alipur Duar Jn", "zone": "NFR"},
    "ASN":  {"hub_code": "ASN",  "hub_name": "Asansol Jn", "zone": "ER"},
    "BCT":  {"hub_code": "MMCT", "hub_name": "Mumbai Central", "zone": "WR"},
    "BKN":  {"hub_code": "BKN",  "hub_name": "Bikaner Jn", "zone": "NWR"},
    "BPL":  {"hub_code": "BPL",  "hub_name": "Bhopal Jn", "zone": "WCR"},
    "BRC":  {"hub_code": "BRC",  "hub_name": "Vadodara Jn", "zone": "WR"},
    "BSB":  {"hub_code": "BSB",  "hub_name": "Varanasi Jn", "zone": "NER"},
    "BSL":  {"hub_code": "BSL",  "hub_name": "Bhusaval Jn", "zone": "CR"},
    "BSP":  {"hub_code": "BSP",  "hub_name": "Bilaspur Jn", "zone": "SECR"},
    "BVP":  {"hub_code": "BVC",  "hub_name": "Bhavnagar Terminus", "zone": "WR"},
    "BZA":  {"hub_code": "BZA",  "hub_name": "Vijayawada Jn", "zone": "SCR"},
    "CKP":  {"hub_code": "CKP",  "hub_name": "Chakradharpur", "zone": "SER"},
    "CSTM": {"hub_code": "CSMT", "hub_name": "Chhatrapati Shivaji Maharaj Terminus", "zone": "CR"},
    "DDU":  {"hub_code": "DDU",  "hub_name": "Pt. Deen Dayal Upadhyaya Jn", "zone": "ECR"},
    "DHN":  {"hub_code": "DHN",  "hub_name": "Dhanbad Jn", "zone": "ECR"},
    "DLI":  {"hub_code": "NDLS", "hub_name": "New Delhi", "zone": "NR"},
    "DNR":  {"hub_code": "PNBE", "hub_name": "Patna Jn", "zone": "ECR"},
    "FZR":  {"hub_code": "FZR",  "hub_name": "Firozpur Cantt", "zone": "NR"},
    "GNT":  {"hub_code": "GNT",  "hub_name": "Guntur Jn", "zone": "SCR"},
    "GTL":  {"hub_code": "GTL",  "hub_name": "Guntakal Jn", "zone": "SCR"},
    "HWH":  {"hub_code": "HWH",  "hub_name": "Howrah Jn", "zone": "ER"},
    "HYB":  {"hub_code": "HYB",  "hub_name": "Hyderabad Deccan", "zone": "SCR"},
    "IZN":  {"hub_code": "IZN",  "hub_name": "Izzatnagar", "zone": "NER"},
    "JBP":  {"hub_code": "JBP",  "hub_name": "Jabalpur", "zone": "WCR"},
    "JHS":  {"hub_code": "GWL",  "hub_name": "Gwalior Jn", "zone": "NCR"},
    "JP":   {"hub_code": "JP",   "hub_name": "Jaipur Jn", "zone": "NWR"},
    "JU":   {"hub_code": "JU",   "hub_name": "Jodhpur Jn", "zone": "NWR"},
    "KGP":  {"hub_code": "KGP",  "hub_name": "Kharagpur Jn", "zone": "SER"},
    "KIR":  {"hub_code": "KIR",  "hub_name": "Katihar Jn", "zone": "NFR"},
    "KOTA": {"hub_code": "KOTA", "hub_name": "Kota Jn", "zone": "WCR"},
    "KUR":  {"hub_code": "BBS",  "hub_name": "Bhubaneswar", "zone": "ECoR"},
    "LJN":  {"hub_code": "LJN",  "hub_name": "Lucknow Jn NER", "zone": "NER"},
    "LKO":  {"hub_code": "LKO",  "hub_name": "Lucknow Charbagh NR", "zone": "NR"},
    "LMG":  {"hub_code": "LMG",  "hub_name": "Lumding Jn", "zone": "NFR"},
    "MAS":  {"hub_code": "MAS",  "hub_name": "MGR Chennai Central", "zone": "SR"},
    "MB":   {"hub_code": "MB",   "hub_name": "Moradabad", "zone": "NR"},
    "MDU":  {"hub_code": "MDU",  "hub_name": "Madurai Jn", "zone": "SR"},
    "MLDT": {"hub_code": "MLDT", "hub_name": "Malda Town", "zone": "ER"},
    "MYS":  {"hub_code": "MYS",  "hub_name": "Mysuru Jn", "zone": "SWR"},
    "NAG":  {"hub_code": "NGP",  "hub_name": "Nagpur Jn", "zone": "SECR"},
    "NED":  {"hub_code": "NED",  "hub_name": "Hazur Sahib Nanded", "zone": "SCR"},
    "NGP":  {"hub_code": "NGP",  "hub_name": "Nagpur Jn", "zone": "CR"},
    "PGT":  {"hub_code": "PGT",  "hub_name": "Palakkad Jn", "zone": "SR"},
    "PRYJ": {"hub_code": "PRYJ", "hub_name": "Prayagraj Jn", "zone": "NCR"},
    "PUNE": {"hub_code": "PUNE", "hub_name": "Pune Jn", "zone": "CR"},
    "R":    {"hub_code": "R",    "hub_name": "Raipur Jn", "zone": "SECR"},
    "RJT":  {"hub_code": "RJT",  "hub_name": "Rajkot Jn", "zone": "WR"},
    "RNC":  {"hub_code": "RNC",  "hub_name": "Ranchi", "zone": "SER"},
    "RNY":  {"hub_code": "RNY",  "hub_name": "Rangiya Jn", "zone": "NFR"},
    "RTM":  {"hub_code": "RTM",  "hub_name": "Ratlam Jn", "zone": "WR"},
    "SBC":  {"hub_code": "SBC",  "hub_name": "KSR Bengaluru", "zone": "SWR"},
    "SBP":  {"hub_code": "SBP",  "hub_name": "Sambalpur", "zone": "ECoR"},
    "SC":   {"hub_code": "SC",   "hub_name": "Secunderabad Jn", "zone": "SCR"},
    "SDAH": {"hub_code": "SDAH", "hub_name": "Sealdah", "zone": "ER"},
    "SEE":  {"hub_code": "SEE",  "hub_name": "Sonpur Jn", "zone": "ECR"},
    "SPJ":  {"hub_code": "SPJ",  "hub_name": "Samastipur Jn", "zone": "ECR"},
    "SUR":  {"hub_code": "SUR",  "hub_name": "Solapur", "zone": "CR"},
    "TPJ":  {"hub_code": "TPJ",  "hub_name": "Tiruchchirappalli Jn", "zone": "SR"},
    "TSK":  {"hub_code": "TSK",  "hub_name": "Tinsukia Jn", "zone": "NFR"},
    "UBL":  {"hub_code": "UBL",  "hub_name": "SSS Hubballi Jn", "zone": "SWR"},
    "UMB":  {"hub_code": "UMB",  "hub_name": "Ambala Cantt", "zone": "NR"},
    "WAT":  {"hub_code": "VSKP", "hub_name": "Visakhapatnam", "zone": "ECoR"},
}


def build_and_validate_division_hubs(stations_path: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    with open(stations_path, "r", encoding="utf-8") as f:
        stations_data = json.load(f)

    stations = stations_data.get("stations", {})

    output_hubs: Dict[str, Dict[str, str]] = {}
    verified = 0
    missing = []

    for div, info in DIVISION_HUB_MAPPINGS.items():
        code = info["hub_code"]
        if code in stations:
            verified += 1
            stn_name = stations[code].get("station_name", info["hub_name"])
            zone = stations[code].get("zone", info.get("zone", ""))
        else:
            missing.append((div, code))
            stn_name = info["hub_name"]
            zone = info.get("zone", "")

        output_hubs[div] = {
            "division": div,
            "hub_code": code,
            "hub_name": stn_name,
            "zone": zone
        }

    report = {
        "total_divisions": len(DIVISION_HUB_MAPPINGS),
        "verified_in_dataset": verified,
        "missing_codes": missing,
        "generated_at": datetime.now(timezone.utc).isoformat()
    }

    return output_hubs, report


def main():
    parser = argparse.ArgumentParser(description="Preprocess and validate division hubs mapping")
    parser.add_argument("--stations", default=str(DEFAULT_STATIONS_PATH), help="Path to railway_stations.json")
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT_PATH), help="Path to division_hubs.json")
    args = parser.parse_args()

    stations_path = Path(args.stations)
    out_path = Path(args.out)

    if not stations_path.exists():
        sys.exit(f"ERROR: {stations_path} not found.")

    output_hubs, report = build_and_validate_division_hubs(stations_path)

    print("\n" + "=" * 60)
    print("  DIVISION HUBS VALIDATION REPORT")
    print("=" * 60)
    print(f"  Total Divisions mapped : {report['total_divisions']}")
    print(f"  Verified in JSON dataset: {report['verified_in_dataset']}")
    print(f"  Missing / Invalid codes: {len(report['missing_codes'])}")
    if report["missing_codes"]:
        for div, code in report["missing_codes"]:
            print(f"    WARNING: Division {div} -> {code} not in dataset")
    print("=" * 60 + "\n")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output_hubs, f, indent=2, ensure_ascii=False)

    log.info("Saved division hubs dataset to %s", out_path)


if __name__ == "__main__":
    main()

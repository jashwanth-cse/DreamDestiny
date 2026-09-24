#!/usr/bin/env python3
"""
Railway Station Preprocessor
==============================
One-time script that parses station_list.pdf (578 pages, Indian Railways) and
produces data/railway_stations.json for fast runtime lookups.

Usage:
    python scripts/preprocess_stations.py [--pdf PATH] [--out PATH] [--aliases PATH]

Output JSON structure:
    {
        "meta": {
            "total_pdf_rows": int,
            "valid_stations": int,
            "invalid_rows": int,
            "duplicate_codes": int,
            "duplicate_normalized_names": int,
            "ambiguous_names": int,
            "generated_at": "ISO8601 timestamp"
        },
        "stations": {
            "STATION_CODE": {
                "station_code": str,
                "station_name": str,
                "division": str,
                "zone": str,
                "district": str,
                "state": str
            },
            ...
        },
        "index": {
            "by_normalized_name": {
                "normalized station name": ["IATA_CODE", ...],
                ...
            },
            "by_code": {
                "CODE": "IATA_CODE",
                ...
            }
        }
    }

How to regenerate:
    1. Drop the new PDF at the project root as station_list.pdf (or pass --pdf path).
    2. Run: python scripts/preprocess_stations.py
    3. Commit data/railway_stations.json.
    4. Restart the train-service container (the JSON is loaded once at startup).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# PDF parsing — installed in scripts venv / host
try:
    import pdfplumber
except ImportError:
    sys.exit("ERROR: pdfplumber is not installed. Run: pip install pdfplumber")

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Defaults ──────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent          # scripts/
_ROOT = _HERE.parent                              # project root
DEFAULT_PDF_PATH    = _ROOT / "station_list.pdf"
DEFAULT_OUTPUT_PATH = _ROOT / "data" / "railway_stations.json"
DEFAULT_ALIASES_PATH = _ROOT / "data" / "station_aliases.json"

# ── PDF column indices (0-based after S No) ───────────────────────────────────
# Row layout: [S_No, Station_Name, Stn_Code, Old_Cat, New_Cat, Division, Zone, District, State]
COL_SNUM     = 0
COL_NAME     = 1
COL_CODE     = 2
COL_OLD_CAT  = 3
COL_NEW_CAT  = 4
COL_DIVISION = 5
COL_ZONE     = 6
COL_DISTRICT = 7
COL_STATE    = 8
EXPECTED_COLS = 9

# ── Station code validation ───────────────────────────────────────────────────
_CODE_RE = re.compile(r"^[A-Z][A-Z0-9]{0,6}$")   # 1-7 uppercase alphanum, starts alpha

# ── Text normalization ────────────────────────────────────────────────────────

# Railway name suffixes to strip when normalizing lookup keys.
# Order matters — strip longest first.
_SUFFIXES = [
    "railway station",
    "rly stn",
    "rly station",
    "railway stn",
    "junction",
    " jn.",
    " jn",
    " road",
    " halt",
    " p.h.",
    " ph",
]

def _strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize(text: str) -> str:
    """
    Produce a deterministic lookup key for a station name:
        - decode accents
        - lowercase
        - strip harmless punctuation (keep alphanum + space + hyphen)
        - collapse whitespace
        - strip common railway suffixes
    """
    if not text:
        return ""
    s = _strip_accents(text)
    s = s.lower()
    # Keep letters, digits, spaces, hyphens
    s = re.sub(r"[^a-z0-9 \-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # Strip known suffixes (trailing)
    for suffix in _SUFFIXES:
        if s.endswith(suffix):
            s = s[: -len(suffix)].rstrip()
            break
    return s


# ── PDF parsing ───────────────────────────────────────────────────────────────

def _is_header_row(row: List[Optional[str]]) -> bool:
    """Skip header rows that appear at the top of each page."""
    if not row:
        return True
    first = (row[0] or "").strip()
    return first in ("S No", "S NO", "S.No", "") or not first.replace(".", "").isdigit()


def parse_pdf(pdf_path: Path) -> Tuple[List[Dict[str, str]], int, List[str]]:
    """
    Extracts raw station records from the PDF.

    Returns:
        (records, total_rows_seen, error_log)
        Each record: {station_name, station_code, division, zone, district, state}
    """
    records: List[Dict[str, str]] = []
    total_rows = 0
    errors: List[str] = []

    log.info("Opening %s …", pdf_path)
    t0 = time.time()

    with pdfplumber.open(str(pdf_path)) as pdf:
        n_pages = len(pdf.pages)
        log.info("PDF has %d pages. Extracting tables …", n_pages)

        for page_num, page in enumerate(pdf.pages, start=1):
            if page_num % 50 == 0:
                elapsed = time.time() - t0
                log.info("  Page %d / %d  (%.0fs elapsed)", page_num, n_pages, elapsed)

            tables = page.extract_tables()
            if not tables:
                continue

            for row in tables[0]:
                if _is_header_row(row):
                    continue

                total_rows += 1

                # Pad / trim to expected width
                row = list(row) + [None] * EXPECTED_COLS
                row = row[:EXPECTED_COLS]

                def cell(idx: int) -> str:
                    v = row[idx]
                    return (v or "").strip().replace("\n", " ")

                name = cell(COL_NAME)
                code = cell(COL_CODE).upper()
                division = cell(COL_DIVISION)
                zone = cell(COL_ZONE)
                district = cell(COL_DISTRICT)
                state = cell(COL_STATE)

                # Validate required fields
                if not name:
                    errors.append(f"Row {total_rows} (p{page_num}): empty station name — skipped")
                    continue
                if not code or not _CODE_RE.match(code):
                    errors.append(
                        f"Row {total_rows} (p{page_num}): invalid code '{code}' for '{name}' — skipped"
                    )
                    continue

                records.append({
                    "station_name": name,
                    "station_code": code,
                    "division": division,
                    "zone": zone,
                    "district": district,
                    "state": state,
                })

    log.info("Extraction done: %d rows seen, %d valid records, %d errors (%.0fs)",
             total_rows, len(records), len(errors), time.time() - t0)
    return records, total_rows, errors


# ── Deduplication & indexing ──────────────────────────────────────────────────

def build_dataset(
    records: List[Dict[str, str]],
    aliases: Dict[str, str],
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """
    Returns:
        (stations_dict, index, report)

    stations_dict:  { CODE: full record }
    index: {
        by_normalized_name: { normalized_name: [CODE, ...] },
        by_code: { CODE: CODE }   (identity — fast validation)
    }
    report: validation summary
    """
    stations: Dict[str, Dict[str, str]] = {}
    duplicate_codes: List[str] = []
    by_name: Dict[str, List[str]] = defaultdict(list)   # normalized_name → [codes]

    for rec in records:
        code = rec["station_code"]
        if code in stations:
            duplicate_codes.append(code)
            # Keep first occurrence; continue to index second occurrence too
            # so ambiguity is detected correctly.
        else:
            stations[code] = rec

        norm = normalize(rec["station_name"])
        if code not in by_name[norm]:
            by_name[norm].append(code)

    # Inject aliases into the name index (alias → code)
    # aliases.json format: { "alias_name": "STATION_CODE" }
    alias_injected = 0
    for alias_raw, target_code in aliases.items():
        norm_alias = normalize(alias_raw)
        if target_code not in stations:
            log.warning("Alias '%s' → '%s': code not in dataset, skipping", alias_raw, target_code)
            continue
        if norm_alias not in by_name:
            by_name[norm_alias] = [target_code]
            alias_injected += 1
        elif target_code not in by_name[norm_alias]:
            by_name[norm_alias].append(target_code)

    # Classify duplicates
    duplicate_normalized: List[str] = []
    ambiguous_names: List[str] = []
    for norm_name, codes in by_name.items():
        if len(codes) > 1:
            duplicate_normalized.append(norm_name)
            ambiguous_names.append(norm_name)

    report = {
        "duplicate_codes": len(duplicate_codes),
        "duplicate_code_list": sorted(set(duplicate_codes))[:20],
        "duplicate_normalized_names": len(duplicate_normalized),
        "ambiguous_names": len(ambiguous_names),
        "ambiguous_name_sample": sorted(ambiguous_names)[:10],
        "alias_injected": alias_injected,
    }

    index = {
        "by_normalized_name": dict(by_name),
        "by_code": {code: code for code in stations},
    }

    return stations, index, report


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Preprocess station_list.pdf → railway_stations.json")
    parser.add_argument("--pdf",     default=str(DEFAULT_PDF_PATH),    help="Path to station_list.pdf")
    parser.add_argument("--out",     default=str(DEFAULT_OUTPUT_PATH), help="Path to output JSON")
    parser.add_argument("--aliases", default=str(DEFAULT_ALIASES_PATH),help="Path to aliases JSON (optional)")
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    out_path = Path(args.out)
    aliases_path = Path(args.aliases)

    if not pdf_path.exists():
        sys.exit(f"ERROR: PDF not found at {pdf_path}")

    # Load optional aliases
    aliases: Dict[str, str] = {}
    if aliases_path.exists():
        with open(aliases_path, "r", encoding="utf-8") as f:
            aliases = json.load(f)
        log.info("Loaded %d aliases from %s", len(aliases), aliases_path)
    else:
        log.info("No aliases file at %s — creating default", aliases_path)
        # Create a starter file with common railway aliases
        default_aliases: Dict[str, str] = {
            "chennai": "MAS",
            "madras": "MAS",
            "chennai central": "MAS",
            "chennai egmore": "MS",
            "delhi": "NDLS",
            "new delhi": "NDLS",
            "old delhi": "DLI",
            "mumbai": "CSMT",
            "mumbai csmt": "CSMT",
            "bombay": "CSMT",
            "bangalore": "SBC",
            "bengaluru": "SBC",
            "calcutta": "HWH",
            "kolkata": "HWH",
            "hyderabad": "SC",
            "madurai": "MDU",
            "coimbatore": "CBE",
            "trivandrum": "TVC",
            "goa": "MAO",
        }
        aliases_path.parent.mkdir(parents=True, exist_ok=True)
        with open(aliases_path, "w", encoding="utf-8") as f:
            json.dump(default_aliases, f, indent=2, ensure_ascii=False)
        aliases = default_aliases
        log.info("Created default aliases at %s", aliases_path)

    # Parse PDF
    records, total_rows, errors = parse_pdf(pdf_path)

    # Build dataset
    stations, index, report = build_dataset(records, aliases)

    # Print validation report
    print("\n" + "=" * 60)
    print("  PREPROCESSING VALIDATION REPORT")
    print("=" * 60)
    print(f"  Total PDF rows parsed  : {total_rows:,}")
    print(f"  Valid station records  : {len(records):,}")
    print(f"  Invalid / skipped rows : {total_rows - len(records):,}")
    print(f"  Unique station codes   : {len(stations):,}")
    print(f"  Duplicate codes        : {report['duplicate_codes']:,}")
    print(f"  Unique normalized names: {len(index['by_normalized_name']):,}")
    print(f"  Ambiguous names        : {report['ambiguous_names']:,}")
    print(f"  Aliases injected       : {report['alias_injected']:,}")
    if report["ambiguous_name_sample"]:
        print(f"\n  Ambiguous name samples :")
        for nm in report["ambiguous_name_sample"]:
            codes = index["by_normalized_name"][nm]
            print(f"    '{nm}' -> {codes}")
    if errors:
        print(f"\n  Sample parse errors (first 5):")
        for e in errors[:5]:
            print(f"    {e}")
    print("=" * 60 + "\n")

    # Assemble output
    output: Dict[str, Any] = {
        "meta": {
            "total_pdf_rows": total_rows,
            "valid_stations": len(stations),
            "invalid_rows": total_rows - len(records),
            "duplicate_codes": report["duplicate_codes"],
            "duplicate_normalized_names": report["duplicate_normalized_names"],
            "ambiguous_names": report["ambiguous_names"],
            "alias_injected": report["alias_injected"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_pdf": pdf_path.name,
        },
        "stations": stations,
        "index": index,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = out_path.stat().st_size / 1024
    log.info("Written to %s  (%.0f KB)", out_path, size_kb)
    log.info("Done.")


if __name__ == "__main__":
    main()

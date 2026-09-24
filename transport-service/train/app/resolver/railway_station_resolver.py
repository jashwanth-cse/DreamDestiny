"""
Railway Station Resolver
=========================
Fast local lookup of Indian railway station names → station codes using the
preprocessed data/railway_stations.json dataset.

Resolution priority (lowest index = highest priority):
  1. Direct station code passthrough (e.g. "MAS", "NDLS")
  2. Exact normalized name match (from index.by_normalized_name)
  3. Alias match (injected into the same index at preprocessing time)
  4. Deterministic fuzzy match — only when exactly ONE candidate scores above
     the confidence threshold (no arbitrary selection between equals)
  5. NOT_FOUND / AMBIGUOUS — caller must fall through to the API

Design principles:
  - Zero network I/O.
  - Index loaded ONCE at module import / explicit load_dataset() call.
  - Thread-safe reads (index is immutable after load).
  - Never guesses between equally plausible candidates.
  - Provider-agnostic: returns a StationMatch dataclass, not provider-specific dict.

Lookup metrics are logged at INFO level:
  - local_hit      exact or alias match resolved locally
  - local_miss     name not in dataset at all
  - ambiguous      name matched multiple stations with equal confidence
  - fuzzy_hit      deterministic fuzzy match with high confidence
  - api_fallback   caller must use external API (miss or ambiguous)
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# ── Dataset path discovery ────────────────────────────────────────────────────

def _find_dataset_path() -> Optional[Path]:
    """Locate railway_stations.json relative to common project layouts."""
    env = os.environ.get("RAILWAY_STATIONS_DATA_PATH")
    if env and Path(env).exists():
        return Path(env)

    candidates = [
        Path(__file__).resolve().parent.parent.parent / "data" / "railway_stations.json",
        Path("data/railway_stations.json"),
        Path("../data/railway_stations.json"),
        Path("../../data/railway_stations.json"),
        Path("/app/data/railway_stations.json"),
    ]
    for p in candidates:
        if p.exists():
            return p.resolve()
    return None


# ── Text normalization (must match preprocess_stations.py) ─────────────────

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

# Valid station code pattern: 1-7 uppercase alphanumeric, starts with letter
_CODE_RE = re.compile(r"^[A-Z][A-Z0-9]{0,6}$")


def _strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_name(text: str) -> str:
    """
    Produce a deterministic lookup key for a station name.
    Must stay byte-for-byte identical to the normalizer in preprocess_stations.py.
    """
    if not text:
        return ""
    s = _strip_accents(text)
    s = s.lower()
    s = re.sub(r"[^a-z0-9 \-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    for suffix in _SUFFIXES:
        if s.endswith(suffix):
            s = s[: -len(suffix)].rstrip()
            break
    return s


# ── Fuzzy matching (no LLM, no ML, pure token/character overlap) ─────────────

# Minimum Jaccard similarity of character bigrams to accept a fuzzy match.
# Only applied when exactly ONE candidate exceeds this threshold.
FUZZY_CONFIDENCE_THRESHOLD = 0.82


def _bigrams(s: str) -> set:
    """Character bigrams of a string (for Jaccard similarity)."""
    return {s[i : i + 2] for i in range(len(s) - 1)} if len(s) >= 2 else {s}


def _jaccard(a: str, b: str) -> float:
    """Jaccard similarity of character bigrams."""
    ba, bb = _bigrams(a), _bigrams(b)
    if not ba and not bb:
        return 1.0
    intersection = len(ba & bb)
    union = len(ba | bb)
    return intersection / union if union else 0.0


# ── Result types ──────────────────────────────────────────────────────────────

class ResolveStatus(str, Enum):
    EXACT       = "exact"        # exact normalized match or alias
    CODE        = "code"         # input was already a valid station code
    FUZZY       = "fuzzy"        # deterministic high-confidence fuzzy match
    AMBIGUOUS   = "ambiguous"    # multiple equally plausible candidates
    NOT_FOUND   = "not_found"    # no local match; must fall back to API


@dataclass
class StationMatch:
    """Result of a local resolver lookup."""
    status:       ResolveStatus
    station_code: Optional[str]   = None
    station_name: Optional[str]   = None
    division:     Optional[str]   = None
    zone:         Optional[str]   = None
    district:     Optional[str]   = None
    state:        Optional[str]   = None
    confidence:   float           = 1.0   # 1.0 for exact/code; Jaccard for fuzzy
    candidates:   List[str]       = field(default_factory=list)   # for AMBIGUOUS
    latency_ms:   float           = 0.0

    @property
    def needs_api_fallback(self) -> bool:
        return self.status in (ResolveStatus.NOT_FOUND, ResolveStatus.AMBIGUOUS)

    def to_station_dict(self) -> Optional[Dict[str, Any]]:
        """Convert to the legacy station dict format used by StationService."""
        if self.station_code is None:
            return None
        return {
            "station_name": self.station_name or self.station_code,
            "station_code": self.station_code,
            "division":     self.division or "",
            "zone":         self.zone or "",
            "district":     self.district or "",
            "state":        self.state or "",
            "latitude":     0.0,   # not in PDF; will be filled by API fallback if needed
            "longitude":    0.0,
        }


# ── Resolver ──────────────────────────────────────────────────────────────────

class RailwayStationResolver:
    """
    In-memory railway station resolver backed by railway_stations.json.

    Load once at startup:
        resolver = RailwayStationResolver()
        resolver.load()

    Resolve at request time (zero-network, sub-millisecond for exact matches):
        match = resolver.resolve("Sivakasi")
        if match.needs_api_fallback:
            # call external station API
    """

    def __init__(self, dataset_path: Optional[Path] = None) -> None:
        self._path: Optional[Path] = dataset_path
        self._stations:  Dict[str, Dict[str, Any]] = {}
        self._by_name:   Dict[str, List[str]] = {}    # normalized_name → [codes]
        self._by_code:   Dict[str, str] = {}           # CODE → CODE
        self._loaded:    bool = False
        self._meta:      Dict[str, Any] = {}

    # ── Dataset loading ──────────────────────────────────────────────────────

    def load(self, dataset_path: Optional[Path] = None) -> None:
        """
        Load railway_stations.json into memory.
        Safe to call multiple times; only loads once.
        """
        if self._loaded:
            return

        target = dataset_path or self._path or _find_dataset_path()
        if target is None or not Path(target).exists():
            log.warning(
                "RailwayStationResolver: railway_stations.json not found. "
                "Run scripts/preprocess_stations.py to generate it. "
                "Resolver will always return NOT_FOUND (API fallback will handle)."
            )
            self._loaded = True   # mark loaded to avoid repeated warnings
            return

        t0 = time.perf_counter()
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)

        self._stations = data.get("stations", {})
        idx = data.get("index", {})
        self._by_name  = idx.get("by_normalized_name", {})
        self._by_code  = idx.get("by_code", {})
        self._meta     = data.get("meta", {})
        self._loaded   = True

        elapsed_ms = (time.perf_counter() - t0) * 1000
        log.info(
            "RailwayStationResolver loaded %d stations, %d normalized names "
            "(%.1f ms) from %s",
            len(self._stations),
            len(self._by_name),
            elapsed_ms,
            Path(target).name,
        )

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    # ── Resolution ───────────────────────────────────────────────────────────

    def resolve(self, query: str) -> StationMatch:
        """
        Resolve a city/station name or code to a StationMatch.

        Priority:
          1. Input is a valid station code  → CODE result
          2. Exact normalized name match    → EXACT result
          3. High-confidence fuzzy match    → FUZZY result (single candidate only)
          4. Multiple fuzzy candidates      → AMBIGUOUS
          5. No match                       → NOT_FOUND
        """
        self._ensure_loaded()
        t0 = time.perf_counter()

        raw = (query or "").strip()
        if not raw:
            return StationMatch(status=ResolveStatus.NOT_FOUND, latency_ms=0.0)

        # ── Step 1: Direct station code passthrough ──────────────────────────
        upper = raw.upper()
        if _CODE_RE.match(upper) and upper in self._by_code:
            rec = self._stations.get(upper)
            match = self._build_match(
                ResolveStatus.CODE, upper, rec, 1.0, latency_start=t0
            )
            log.info("local_hit (code) '%s' → %s [%.3f ms]", raw, upper, match.latency_ms)
            return match

        # ── Step 2: Exact normalized name match ──────────────────────────────
        norm = normalize_name(raw)
        if norm in self._by_name:
            codes = self._by_name[norm]
            if len(codes) == 1:
                code = codes[0]
                rec  = self._stations.get(code)
                match = self._build_match(
                    ResolveStatus.EXACT, code, rec, 1.0, latency_start=t0
                )
                log.info(
                    "local_hit (exact) '%s' → %s (%s) [%.3f ms]",
                    raw, code, rec.get("station_name") if rec else "?", match.latency_ms
                )
                return match
            else:
                # Exact match but multiple stations share the same normalized name
                match = StationMatch(
                    status=ResolveStatus.AMBIGUOUS,
                    candidates=codes,
                    latency_ms=(time.perf_counter() - t0) * 1000,
                )
                log.info(
                    "ambiguous '%s' → candidates %s [%.3f ms]",
                    raw, codes, match.latency_ms
                )
                return match

        # ── Step 3: Fuzzy match ──────────────────────────────────────────────
        best_code:  Optional[str]  = None
        best_score: float          = 0.0
        second_best: float         = 0.0
        above_threshold: List[str] = []

        for cand_norm, cand_codes in self._by_name.items():
            score = _jaccard(norm, cand_norm)
            if score >= FUZZY_CONFIDENCE_THRESHOLD:
                above_threshold.extend(cand_codes)
                if score > best_score:
                    second_best = best_score
                    best_score  = score
                    best_code   = cand_codes[0]  # take first if normalized name maps to one
                elif score > second_best:
                    second_best = score

        if above_threshold:
            # Only accept fuzzy if exactly one candidate clears threshold
            unique_above = list(dict.fromkeys(above_threshold))   # preserve order
            if len(unique_above) == 1:
                code = unique_above[0]
                rec  = self._stations.get(code)
                match = self._build_match(
                    ResolveStatus.FUZZY, code, rec, best_score, latency_start=t0
                )
                log.info(
                    "fuzzy_hit '%s' → %s (score=%.3f) [%.3f ms]",
                    raw, code, best_score, match.latency_ms
                )
                return match
            else:
                match = StationMatch(
                    status=ResolveStatus.AMBIGUOUS,
                    candidates=unique_above,
                    confidence=best_score,
                    latency_ms=(time.perf_counter() - t0) * 1000,
                )
                log.info(
                    "ambiguous (fuzzy) '%s' → candidates %s [%.3f ms]",
                    raw, unique_above[:5], match.latency_ms
                )
                return match

        # ── Step 4: Not found ────────────────────────────────────────────────
        latency = (time.perf_counter() - t0) * 1000
        log.info("local_miss '%s' [%.3f ms]", raw, latency)
        return StationMatch(
            status=ResolveStatus.NOT_FOUND,
            latency_ms=latency,
        )

    def _build_match(
        self,
        status: ResolveStatus,
        code: str,
        rec: Optional[Dict[str, Any]],
        confidence: float,
        latency_start: float,
    ) -> StationMatch:
        latency = (time.perf_counter() - latency_start) * 1000
        return StationMatch(
            status=status,
            station_code=code,
            station_name=rec.get("station_name") if rec else None,
            division=rec.get("division") if rec else None,
            zone=rec.get("zone") if rec else None,
            district=rec.get("district") if rec else None,
            state=rec.get("state") if rec else None,
            confidence=confidence,
            candidates=[code],
            latency_ms=latency,
        )

    # ── Bulk utilities ────────────────────────────────────────────────────────

    def get_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Retrieve a full station record by exact station code."""
        self._ensure_loaded()
        return self._stations.get(code.upper())

    @property
    def total_stations(self) -> int:
        self._ensure_loaded()
        return len(self._stations)

    @property
    def meta(self) -> Dict[str, Any]:
        self._ensure_loaded()
        return self._meta

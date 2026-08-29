"""
Persistent SQLite-backed cache for hotel search results.

Cache key format:
    hotel:{city_lower}:{check_in}:{check_out}:{adults}:{children}

Example:
    hotel:coimbatore:2026-08-20:2026-08-22:2:0

Cached entries expire after HOTEL_CACHE_TTL_HOURS (default 24 h).
The SQLite file lives next to this module so it survives service restarts.
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

from app.config import settings

# Path to the SQLite file
if settings.hotel_db_path:
    _DB_PATH = Path(settings.hotel_db_path)
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
else:
    _DB_PATH = Path(__file__).parent / "hotel_cache.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    """Create the cache table if it doesn't exist yet."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hotel_cache (
                cache_key   TEXT PRIMARY KEY,
                payload     TEXT NOT NULL,
                created_at  REAL NOT NULL
            )
            """
        )
        conn.commit()


# Initialise on import
_init_db()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def make_cache_key(
    city: str,
    check_in: str,
    check_out: str,
    adults: int,
    children: int,
) -> str:
    return f"hotel:{city.lower().strip()}:{check_in}:{check_out}:{adults}:{children}"


def get_cached(cache_key: str) -> Optional[dict]:
    """
    Return the cached payload dict if it exists and has not expired.
    Returns None on a cache miss or expired entry.
    """
    ttl_seconds = settings.hotel_cache_ttl_hours * 3600
    cutoff = time.time() - ttl_seconds

    with _connect() as conn:
        row = conn.execute(
            "SELECT payload, created_at FROM hotel_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()

    if row is None:
        return None  # miss

    if row["created_at"] < cutoff:
        # Expired — delete it so future requests fetch fresh data
        _delete(cache_key)
        return None

    return json.loads(row["payload"])


def set_cached(cache_key: str, payload: dict) -> None:
    """Upsert a cache entry with the current timestamp."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO hotel_cache (cache_key, payload, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                payload    = excluded.payload,
                created_at = excluded.created_at
            """,
            (cache_key, json.dumps(payload, ensure_ascii=False), time.time()),
        )
        conn.commit()


def _delete(cache_key: str) -> None:
    with _connect() as conn:
        conn.execute(
            "DELETE FROM hotel_cache WHERE cache_key = ?", (cache_key,)
        )
        conn.commit()

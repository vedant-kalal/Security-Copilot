"""
SQLite verdict cache — the router's fast path (spec section 2).

Stores one row per URL with the verdict as JSON and a timestamp; a read
older than CACHE_TTL_HOURS is treated as a miss. Deliberately plain
`sqlite3` (stdlib, synchronous) rather than an ORM or async driver —
this table has one job, and a full async/ORM stack would be more code
to navigate for no real benefit at this scale.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

from config import get_settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS verdict_cache (
    url TEXT PRIMARY KEY,
    verdict_json TEXT NOT NULL,
    cached_at REAL NOT NULL
)
"""


def _connect() -> sqlite3.Connection:
    settings = get_settings()
    db_path = Path(settings.CACHE_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(_SCHEMA)
    return conn


def get_cached_verdict(url: str) -> Optional[dict]:
    """Return the cached verdict for `url` if one exists and is still fresh, else None."""
    settings = get_settings()
    with _connect() as conn:
        row = conn.execute("SELECT verdict_json, cached_at FROM verdict_cache WHERE url = ?", (url,)).fetchone()

    if row is None:
        return None

    verdict_json, cached_at = row
    age_hours = (time.time() - cached_at) / 3600
    if age_hours > settings.CACHE_TTL_HOURS:
        return None

    return json.loads(verdict_json)


def set_cached_verdict(url: str, verdict: dict) -> None:
    """Write/overwrite the cached verdict for `url`."""
    with _connect() as conn:
        conn.execute(
            "INSERT INTO verdict_cache (url, verdict_json, cached_at) VALUES (?, ?, ?) "
            "ON CONFLICT(url) DO UPDATE SET verdict_json = excluded.verdict_json, cached_at = excluded.cached_at",
            (url, json.dumps(verdict), time.time()),
        )
        conn.commit()

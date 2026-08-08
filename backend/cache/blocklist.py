"""
Static blocklist — the router's first, cheapest check (spec section 2).

Plain text file at `data/blocklist.txt`, one domain or full URL per
line, `#`-comments allowed. Loaded once and cached in memory; call
`reload_blocklist()` if the file changes while the process is running.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from config import get_settings
from logger import get_logger
from utils.validators import extract_domain

logger = get_logger(__name__)


@lru_cache
def _load_blocklist() -> frozenset[str]:
    settings = get_settings()
    path = Path(settings.BLOCKLIST_PATH)
    if not path.exists():
        logger.info("No blocklist file at %s — starting with an empty blocklist", path)
        return frozenset()

    entries = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        entries.add(line.lower())
    return frozenset(entries)


def is_blocklisted(url: str) -> bool:
    """True if the URL or its domain appears in the static blocklist."""
    blocklist = _load_blocklist()
    if not blocklist:
        return False
    domain = extract_domain(url).lower()
    return url.lower() in blocklist or domain in blocklist


def reload_blocklist() -> None:
    _load_blocklist.cache_clear()

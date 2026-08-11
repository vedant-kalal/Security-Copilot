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


def list_blocklist() -> list[str]:
    """Every entry currently on the blocklist (domains and/or full URLs, whatever was added) — the extension polls this to build its own local block-on-navigation list."""
    return sorted(_load_blocklist())


def add_to_blocklist(domain: str) -> bool:
    """Append a domain to the blocklist file and make it take effect
    immediately (reloads the in-memory cache). Returns False if the
    domain was already on the list (nothing written, not an error —
    reporting the same site twice is a normal, expected user action)."""
    domain = domain.lower().strip()
    if domain in _load_blocklist():
        return False

    settings = get_settings()
    path = Path(settings.BLOCKLIST_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{domain}\n")
    reload_blocklist()
    return True

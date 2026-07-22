"""Small validation/normalization helpers shared across services."""
from __future__ import annotations

import re
from urllib.parse import urlparse

_IP_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def extract_domain(url: str) -> str:
    """Extract the registrable hostname from a URL, defaulting to the raw
    input if it cannot be parsed as a URL."""
    parsed = urlparse(url if "://" in url else f"http://{url}")
    return parsed.hostname or url


def is_ip_address(value: str) -> bool:
    return bool(_IP_RE.match(value))


def normalize_email(email: str) -> str:
    return email.strip().lower()

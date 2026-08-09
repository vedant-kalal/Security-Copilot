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


def same_registrable_domain(a: str, b: str) -> bool:
    """Approximates "same site" by comparing the last two dot-separated
    labels (e.g. "login.example.com" and "www.example.com" both reduce to
    "example.com"). Not a real public-suffix-list lookup, so it's wrong for
    multi-part suffixes like "co.uk" (treats "foo.co.uk" and "bar.co.uk" as
    the same site) — an acceptable false negative here (it just means we
    fail to flag a cross-site form on a ccTLD), never a false positive on a
    real same-site case, which is the direction that matters for this
    codebase's phishing checks."""
    a_labels = a.lower().rstrip(".").split(".")
    b_labels = b.lower().rstrip(".").split(".")
    return a_labels[-2:] == b_labels[-2:]


def normalize_email(email: str) -> str:
    return email.strip().lower()

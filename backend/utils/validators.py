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


_URL_RE = re.compile(r"https?://[^\s<>\"']+")
_TRAILING_PUNCT = ".,;:!?)]}\"'"


def extract_urls_from_text(text: str) -> list[str]:
    """Pull plausible URLs out of free-form text (an email body, a pasted
    page's text) via a permissive regex — good enough to catch what a
    human eye would call "a link in this text," not a strict RFC 3986
    parser. Trailing punctuation a sentence would naturally end a URL
    with (".", ")", etc.) is stripped, since it's almost always prose
    punctuation rather than part of the URL itself."""
    if not text:
        return []
    return [cleaned for match in _URL_RE.findall(text) if (cleaned := match.rstrip(_TRAILING_PUNCT))]


def dedupe_links_by_domain(urls: list[str], limit: int) -> list[str]:
    """First-seen URL per registrable domain, capped at `limit` — keeps a
    multi-link email's investigation workload bounded (each link costs a
    real inspect_website + domain_reputation round trip) regardless of how
    many raw links were found in the email."""
    seen: set[str] = set()
    picked: list[str] = []
    for url in urls:
        domain = extract_domain(url).lower()
        if domain in seen:
            continue
        seen.add(domain)
        picked.append(url)
        if len(picked) >= limit:
            break
    return picked

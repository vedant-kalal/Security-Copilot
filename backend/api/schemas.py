"""Pydantic request/response models for the API (spec section 10)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class CheckLinksRequest(BaseModel):
    urls: list[str]


class CheckLinksResponse(BaseModel):
    results: dict[str, dict]


class CheckEmailRequest(BaseModel):
    text: str
    # Real anchor hrefs the caller already has DOM access to (the
    # extension popup) — catches "Click here"-style links where the
    # visible text has no URL in it at all, which a regex over `text`
    # alone can never find. Optional and additive: routes_check_email.py
    # always also regex-extracts URLs from `text` itself (see
    # utils.validators.extract_urls_from_text), so a plain pasted email
    # (dashboard's Email scanner, no DOM available) still gets its
    # visible links investigated even with `links` empty.
    links: list[str] = []


class QuickCheckEmailRequest(BaseModel):
    text: str


class QuickCheckRequest(BaseModel):
    url: str
    # Set by the extension's content script when it finds a password field
    # inside a <form> whose action posts to a different hostname than the
    # page itself — a strong, well-established phishing tell (a fake login
    # page harvesting credentials to an attacker-controlled server) that a
    # URL-only model has no way to see. Only meaningful together.
    cross_domain_password_form: bool = False
    action_domain: Optional[str] = None


class ReportFlowRequest(BaseModel):
    """Sent by the native host when Isolation Forest/TranAD flags a flow (spec sections 9/10)."""

    destination: str
    port: Optional[int] = None
    protocol: Optional[str] = None
    process_name: Optional[str] = None
    anomaly_score: Optional[float] = None
    context: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    service: str


class ReportRequest(BaseModel):
    url: str


class VirusTotalReportResult(BaseModel):
    reported: bool
    detail: str


class ReportResponse(BaseModel):
    domain: str
    added_to_blocklist: bool
    virustotal: VirusTotalReportResult


class BlocklistResponse(BaseModel):
    domains: list[str]

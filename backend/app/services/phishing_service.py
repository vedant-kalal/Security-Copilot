"""
Phishing detection service.

Combines the DistilBERT classifier (`app.ml.phishing_model`) with
threat-intelligence reputation lookups to produce a single phishing
verdict. This is step 5-6 of the core workflow: "Threat intelligence
lookup" then "Phishing detection".
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.ml.phishing_model import get_phishing_classifier
from app.services.threat_intel_service import ThreatIntelService
from app.utils.validators import extract_domain, is_ip_address

logger = get_logger(__name__)


class URLHeuristicsAnalyzer:
    """Analyzes structural and semantic properties of a URL for phishing indicators."""
    
    SUSPICIOUS_KEYWORDS = {"login", "verify", "update", "secure", "account", "banking", "wallet", "support", "auth"}
    TARGET_BRANDS = {"paypal", "amazon", "apple", "microsoft", "google", "netflix", "facebook", "chase", "boa"}
    SUSPICIOUS_TLDS = {".tk", ".ml", ".ga", ".cf", ".gq", ".xyz", ".top", ".club"}

    @classmethod
    def analyze(cls, url: str) -> tuple[float, list[str]]:
        reasons = []
        score_boost = 0.0
        parsed_url = url.lower()
        domain = extract_domain(url).lower()

        # 1. IP Address instead of Domain
        if is_ip_address(domain):
            score_boost += 0.4
            reasons.append("Heuristic: Uses a raw IP address instead of a domain name")

        # 2. Suspicious TLDs
        if any(domain.endswith(tld) for tld in cls.SUSPICIOUS_TLDS):
            score_boost += 0.3
            reasons.append("Heuristic: Uses a high-risk or commonly abused Top Level Domain (TLD)")

        # 3. Brand Spoofing mixed with Urgency/Action keywords
        brands_found = [b for b in cls.TARGET_BRANDS if b in parsed_url]
        keywords_found = [k for k in cls.SUSPICIOUS_KEYWORDS if k in parsed_url]
        
        if brands_found and keywords_found:
            score_boost += 0.6
            reasons.append(f"Heuristic: Deceptive combination of targeted brand ({brands_found[0]}) and urgency keyword ({keywords_found[0]})")
        elif brands_found and domain != f"{brands_found[0]}.com":
            # Brand name is in the URL, but the domain isn't the primary brand.com
            score_boost += 0.4
            reasons.append(f"Heuristic: Trusted brand ({brands_found[0]}) found outside of its primary domain")

        # 4. Excessive Subdomains or Length
        if domain.count(".") >= 4:
            score_boost += 0.3
            reasons.append("Heuristic: Excessive use of subdomains to obfuscate the true destination")

        return min(0.9, score_boost), reasons


@dataclass
class PhishingVerdict:
    url: str
    is_phishing: bool
    confidence: float
    reasons: List[str] = field(default_factory=list)
    threat_intel_hit: bool = False


class PhishingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.threat_intel = ThreatIntelService(session)
        self.classifier = get_phishing_classifier()

    async def evaluate(self, url: str, page_title: str | None = None, page_text: str | None = None) -> PhishingVerdict:
        parsed_url = url.lower()
        
        # 1. Avoid flagging local development environments (e.g. localhost, 127.0.0.1)
        if "localhost" in parsed_url or "127.0.0.1" in parsed_url or "0.0.0.0" in parsed_url:
            return PhishingVerdict(
                url=url,
                is_phishing=False,
                confidence=0.0,
                reasons=["Local development environment bypassed"],
                threat_intel_hit=False,
            )

        text_for_model = " ".join(filter(None, [url, page_title, page_text]))
        model_prediction = await asyncio.to_thread(self.classifier.predict, text_for_model)

        intel_results = await self.threat_intel.check_url(url)
        intel_hit = any(r.queried and r.reputation >= 0.5 for r in intel_results)
        intel_reputation = max((r.reputation for r in intel_results if r.queried), default=0.0)

        heuristic_score, heuristic_reasons = URLHeuristicsAnalyzer.analyze(url)

        # Weighted fusion: threat intel is a stronger, ground-truth signal
        # when available; the model score dominates otherwise. We then dynamically
        # add the heuristic bonus to catch zero-day structure abuse.
        if any(r.queried for r in intel_results):
            base_confidence = 0.6 * intel_reputation + 0.4 * model_prediction.confidence
        else:
            base_confidence = model_prediction.confidence
            
        combined_confidence = round(min(1.0, base_confidence + heuristic_score), 4)

        reasons = list(model_prediction.reasons) + heuristic_reasons
        for result in intel_results:
            if result.queried:
                reasons.append(f"{result.source.value}: {result.detail}")

        return PhishingVerdict(
            url=url,
            is_phishing=combined_confidence >= 0.5 or intel_hit,
            confidence=combined_confidence,
            reasons=reasons,
            threat_intel_hit=intel_hit,
        )

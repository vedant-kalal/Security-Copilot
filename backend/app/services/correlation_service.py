"""
Threat Correlation Engine.

"This is the heart of the product." (architecture doc, section 12)

Input:  Signals derived from Browser Events, Threat Intelligence,
        Isolation Forest, Phishing Detection, and Uploaded Logs.
Output: ONE Incident (existing incidents are enriched with new evidence
        instead of spawning duplicate alerts — "Less alert fatigue").

The engine does three things:
  1. Scores and names each incoming `Signal`.
  2. Decides whether the signal(s) belong to an existing open incident
     within the correlation time window, or should start a new one.
  3. Persists the Incident + Evidence rows and computes the MITRE
     mapping for the resulting incident.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.evidence import Evidence
from app.models.incident import Incident, IncidentSeverity, IncidentStatus
from app.repositories.evidence_repository import EvidenceRepository
from app.repositories.incident_repository import IncidentRepository
from app.services.mitre_service import MitreService

logger = get_logger(__name__)


@dataclass(frozen=True)
class Signal:
    """A single normalized finding to be fed into the correlation engine.

    `name` must be one of the keys in `app.utils.mitre_mappings.SIGNAL_TO_TECHNIQUES`
    for MITRE mapping to work; unknown names are still accepted (they simply
    contribute no MITRE techniques).
    """

    name: str
    event_id: UUID
    score: float  # 0.0 .. 1.0 contribution to overall incident confidence
    reason: str


@dataclass
class CorrelationResult:
    incident: Incident
    created: bool
    signals: List[Signal] = field(default_factory=list)


# Known signal combinations mapped to a human-readable incident title,
# mirroring the worked example in the architecture document:
# "Visited suspicious domain + Downloaded executable + VirusTotal hit +
#  High anomaly score -> Credential Theft Attempt"
_TITLE_RULES: List[tuple[frozenset, str]] = [
    (
        frozenset({"phishing_url_detected", "credential_form_on_suspicious_site"}),
        "Credential Theft Attempt",
    ),
    (
        frozenset({"phishing_url_detected", "suspicious_file_download"}),
        "Malicious Download via Phishing Link",
    ),
    (
        frozenset({"malicious_domain_reputation", "suspicious_file_download"}),
        "Malware Delivery from Known-Bad Domain",
    ),
    (frozenset({"phishing_url_detected", "malicious_domain_reputation"}), "Confirmed Phishing Site Visit"),
    (frozenset({"network_anomaly_beaconing"}), "Possible Command-and-Control Beaconing"),
    (frozenset({"network_anomaly_port_scan"}), "Network Reconnaissance / Port Scan Detected"),
    (frozenset({"network_anomaly_high_volume"}), "Abnormal Network Traffic Volume"),
    (frozenset({"repeated_login_attempts"}), "Possible Brute-Force Login Activity"),
    (frozenset({"malicious_ip_reputation"}), "Traffic to Known-Malicious IP Address"),
    (frozenset({"phishing_url_detected"}), "Suspicious Phishing Link Visited"),
]


def derive_incident_title(signal_names: Sequence[str]) -> str:
    signal_set = frozenset(signal_names)
    for rule_set, title in _TITLE_RULES:
        if rule_set.issubset(signal_set):
            return title
    return "Suspicious Activity Detected"


def derive_severity(confidence: float) -> IncidentSeverity:
    if confidence >= 0.85:
        return IncidentSeverity.CRITICAL
    if confidence >= 0.70:
        return IncidentSeverity.HIGH
    if confidence >= 0.50:
        return IncidentSeverity.MEDIUM
    return IncidentSeverity.LOW


def _aggregate_confidence(existing: Optional[float], new_scores: Sequence[float]) -> float:
    """Combine multiple signal scores into a single confidence value using
    a noisy-OR fusion (each independent signal reduces the probability the
    activity is benign), then folds in any prior confidence for enrichment."""
    combined_benign_probability = 1.0
    for score in new_scores:
        combined_benign_probability *= (1.0 - min(max(score, 0.0), 0.999))
    new_confidence = 1.0 - combined_benign_probability

    if existing is None:
        return round(new_confidence, 4)

    # Enrichment: fold the new evidence in without letting confidence fall.
    combined = 1.0 - (1.0 - existing) * (1.0 - new_confidence)
    return round(min(combined, 0.99), 4)


class ThreatCorrelationEngine:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.incidents = IncidentRepository(session)
        self.evidence = EvidenceRepository(session)
        self.mitre = MitreService()
        self.settings = get_settings()

    async def process_signals(self, user_id: UUID, signals: List[Signal]) -> Optional[CorrelationResult]:
        """Correlate a batch of signals (typically produced from a single
        ingested event) into an Incident. Returns None if no signal met the
        minimum contribution threshold to warrant an incident."""
        significant = [s for s in signals if s.score > 0.0]
        if not significant:
            return None

        aggregate_score = _aggregate_confidence(None, [s.score for s in significant])
        if aggregate_score < self.settings.CORRELATION_MIN_SCORE_FOR_INCIDENT:
            logger.info(
                "Signals for user %s scored %.2f, below incident threshold %.2f — no incident created",
                user_id,
                aggregate_score,
                self.settings.CORRELATION_MIN_SCORE_FOR_INCIDENT,
            )
            return None

        existing_incident = await self._find_correlated_incident(user_id)
        signal_names = [s.name for s in significant]
        mitre_techniques = self.mitre.map_signals(signal_names)

        if existing_incident:
            incident = await self._enrich_incident(existing_incident, significant, mitre_techniques)
            created = False
        else:
            incident = await self._create_incident(user_id, significant, mitre_techniques, aggregate_score)
            created = True

        await self.incidents.commit()
        logger.info(
            "Correlation result for user %s: incident=%s created=%s severity=%s confidence=%.2f",
            user_id,
            incident.incident_id,
            created,
            incident.severity,
            incident.confidence,
        )
        return CorrelationResult(incident=incident, created=created, signals=significant)

    async def _find_correlated_incident(self, user_id: UUID) -> Optional[Incident]:
        window_start = datetime.now(timezone.utc) - timedelta(minutes=self.settings.CORRELATION_WINDOW_MINUTES)
        candidates = await self.incidents.find_correlation_candidates(
            user_id, window_start, [IncidentStatus.OPEN, IncidentStatus.INVESTIGATING]
        )
        return candidates[0] if candidates else None

    async def _create_incident(
        self, user_id: UUID, signals: List[Signal], mitre_techniques: List[str], confidence: float
    ) -> Incident:
        title = derive_incident_title([s.name for s in signals])
        severity = derive_severity(confidence)
        reasons_summary = "; ".join(sorted({s.reason for s in signals}))

        incident = Incident(
            user_id=user_id,
            title=title,
            severity=severity,
            confidence=confidence,
            mitre=mitre_techniques,
            status=IncidentStatus.OPEN,
            summary=f"{title}. Triggered by: {reasons_summary}",
        )
        await self.incidents.add(incident)
        await self._attach_evidence(incident.incident_id, signals)
        return incident

    async def _enrich_incident(
        self, incident: Incident, signals: List[Signal], mitre_techniques: List[str]
    ) -> Incident:
        incident.confidence = _aggregate_confidence(incident.confidence, [s.score for s in signals])
        incident.severity = derive_severity(incident.confidence)
        incident.mitre = sorted(set(incident.mitre) | set(mitre_techniques))
        if incident.status == IncidentStatus.RESOLVED:
            incident.status = IncidentStatus.INVESTIGATING
        await self._attach_evidence(incident.incident_id, signals)
        return incident

    async def _attach_evidence(self, incident_id: UUID, signals: List[Signal]) -> None:
        for signal in signals:
            evidence = Evidence(
                incident_id=incident_id,
                event_id=signal.event_id,
                reason=signal.reason,
                score=signal.score,
            )
            await self.evidence.add(evidence)

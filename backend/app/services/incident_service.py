"""
Incident service.

Two responsibilities:

  1. Pipeline orchestration — `ingest_and_correlate()` runs the full
     "Incident Lifecycle" from the architecture document (section 13):
     Raw Event -> Feature Extraction -> Threat Intelligence -> Model
     Inference -> Threat Correlation -> Incident -> MITRE Mapping -> RAG
     -> Gemini -> (Dashboard reads it from here on).

  2. CRUD — listing, retrieving, and updating incidents for the
     dashboard's Investigation / Security Operations views.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models.ai_response import AIResponse
from app.models.event import Event, EventType
from app.models.incident import Incident, IncidentStatus
from app.repositories.ai_response_repository import AIResponseRepository
from app.repositories.event_repository import EventRepository
from app.repositories.incident_repository import IncidentRepository
from app.services.anomaly_service import AnomalyService, classify_anomaly_subtype
from app.services.correlation_service import CorrelationResult, Signal, ThreatCorrelationEngine
from app.services.llm_service import LLMService
from app.services.phishing_service import PhishingService
from app.services.rag_service import RAGService

logger = get_logger(__name__)

_NETWORK_EVENT_TYPES = {
    EventType.NETWORK_FLOW,
    EventType.NETWORK_FLOW_REPLAY,
    EventType.NETWORK_FLOW_UPLOAD,
}
_URL_EVENT_TYPES = {EventType.PAGE_NAVIGATION, EventType.URL_VISIT}
_EXECUTABLE_EXTENSIONS = (".exe", ".scr", ".bat", ".cmd", ".msi", ".jar", ".js", ".vbs", ".ps1", ".dll")


class IncidentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.incidents = IncidentRepository(session)
        self.events = EventRepository(session)
        self.ai_responses = AIResponseRepository(session)
        self.correlation_engine = ThreatCorrelationEngine(session)
        self.phishing_service = PhishingService(session)
        self.anomaly_service = AnomalyService()
        self.llm_service = LLMService()
        self.rag_service = RAGService(session, llm_service=self.llm_service)

    # ------------------------------------------------------------------
    # Pipeline orchestration
    # ------------------------------------------------------------------
    async def ingest_and_correlate(self, user_id: UUID, event: Event) -> Optional[CorrelationResult]:
        """Run detection + correlation for a single newly-persisted event.
        Returns the correlation result (with the incident it created or
        enriched), or None if the event produced no actionable signal."""
        signals = await self._build_signals(user_id, event)
        if not signals:
            return None

        result = await self.correlation_engine.process_signals(user_id, signals)
        if result is None:
            return None

        await self._generate_ai_explanation(result.incident)
        return result

    async def _build_signals(self, user_id: UUID, event: Event) -> List[Signal]:
        signals: List[Signal] = []

        if event.event_type in _URL_EVENT_TYPES:
            signals.extend(await self._signals_from_url_event(event))
        elif event.event_type == EventType.FILE_DOWNLOAD:
            signals.extend(await self._signals_from_download_event(event))
        elif event.event_type == EventType.FORM_SUBMISSION:
            signals.extend(await self._signals_from_form_event(event))
        elif event.event_type == EventType.LOGIN_ATTEMPT:
            signals.extend(await self._signals_from_login_event(event))
        elif event.event_type in _NETWORK_EVENT_TYPES:
            signals.extend(self._signals_from_network_event(event))

        return signals

    async def _signals_from_url_event(self, event: Event) -> List[Signal]:
        url = event.payload_json.get("url")
        if not url:
            return []

        verdict = await self.phishing_service.evaluate(
            url,
            page_title=event.payload_json.get("page_title"),
            page_text=event.payload_json.get("page_text_snippet"),
        )

        signals: List[Signal] = []
        if verdict.is_phishing:
            signals.append(
                Signal(
                    name="phishing_url_detected",
                    event_id=event.event_id,
                    score=verdict.confidence,
                    reason=f"Phishing model flagged {url} ({verdict.confidence:.0%} confidence)",
                )
            )
        if verdict.threat_intel_hit:
            signals.append(
                Signal(
                    name="malicious_domain_reputation",
                    event_id=event.event_id,
                    score=0.9,
                    reason=f"Threat intelligence providers flagged {url} as malicious",
                )
            )
        return signals

    async def _signals_from_download_event(self, event: Event) -> List[Signal]:
        filename = str(event.payload_json.get("filename", "")).lower()
        source_url = event.payload_json.get("source_url")
        signals: List[Signal] = []

        if filename.endswith(_EXECUTABLE_EXTENSIONS):
            score = 0.5
            reason = f"Executable file downloaded: {filename}"
            if source_url:
                verdict = await self.phishing_service.evaluate(source_url)
                if verdict.is_phishing or verdict.threat_intel_hit:
                    score = 0.85
                    reason += f" from a flagged source ({source_url})"
            signals.append(
                Signal(name="suspicious_file_download", event_id=event.event_id, score=score, reason=reason)
            )
        return signals

    async def _signals_from_form_event(self, event: Event) -> List[Signal]:
        has_password_field = bool(event.payload_json.get("has_password_field"))
        url = event.payload_json.get("url")
        if not (has_password_field and url):
            return []

        verdict = await self.phishing_service.evaluate(url)
        if verdict.is_phishing or verdict.threat_intel_hit:
            return [
                Signal(
                    name="credential_form_on_suspicious_site",
                    event_id=event.event_id,
                    score=max(verdict.confidence, 0.7),
                    reason=f"Credential form submitted on flagged site {url}",
                )
            ]
        return []

    async def _signals_from_login_event(self, event: Event) -> List[Signal]:
        if event.payload_json.get("success", True):
            return []

        window_start = datetime.now(timezone.utc) - timedelta(minutes=10)
        recent = await self.events.list_for_device_since(event.device_id, window_start)
        failed_attempts = [
            e for e in recent if e.event_type == EventType.LOGIN_ATTEMPT and not e.payload_json.get("success", True)
        ]
        if len(failed_attempts) >= 5:
            return [
                Signal(
                    name="repeated_login_attempts",
                    event_id=event.event_id,
                    score=min(0.4 + 0.05 * len(failed_attempts), 0.9),
                    reason=f"{len(failed_attempts)} failed login attempts in the last 10 minutes",
                )
            ]
        return []

    def _signals_from_network_event(self, event: Event) -> List[Signal]:
        prediction = self.anomaly_service.evaluate(event.payload_json)
        if not prediction.is_anomaly:
            return []

        subtype = classify_anomaly_subtype(event.payload_json, prediction)
        return [
            Signal(
                name=subtype,
                event_id=event.event_id,
                score=prediction.anomaly_score,
                reason=(
                    f"Isolation Forest flagged this network flow as anomalous "
                    f"(score {prediction.anomaly_score:.0%}); top factors: "
                    f"{', '.join(prediction.top_contributing_features)}"
                ),
            )
        ]

    async def _generate_ai_explanation(self, incident: Incident) -> AIResponse:
        playbooks = await self.rag_service.retrieve_playbooks(incident.title, incident.mitre)
        evidence_reasons = [e.reason for e in incident.evidence_entries][-5:]

        explanation = await self.llm_service.generate_incident_explanation(
            incident_title=incident.title,
            severity=incident.severity.value,
            mitre_techniques=incident.mitre,
            evidence_reasons=evidence_reasons,
            playbook_excerpts=[p.content for p in playbooks],
        )

        ai_response = AIResponse(
            incident_id=incident.incident_id,
            summary=explanation.summary,
            recommendation=explanation.recommendation,
        )
        await self.ai_responses.add(ai_response)
        await self.ai_responses.commit()
        return ai_response

    # ------------------------------------------------------------------
    # CRUD / read paths
    # ------------------------------------------------------------------
    async def list_for_user(
        self, user_id: UUID, status: Optional[IncidentStatus] = None, page: int = 1, page_size: int = 20
    ) -> tuple[Sequence[Incident], int]:
        offset = (page - 1) * page_size
        items = await self.incidents.list_for_user(user_id, status=status, limit=page_size, offset=offset)
        total = await self.incidents.count_for_user(user_id, status=status)
        return items, total

    async def get_owned_incident(self, incident_id: UUID, user_id: UUID) -> Incident:
        incident = await self.incidents.get(incident_id)
        if not incident or incident.user_id != user_id:
            raise NotFoundError(f"Incident {incident_id} not found")
        return incident

    async def update_status(self, incident_id: UUID, user_id: UUID, status: IncidentStatus) -> Incident:
        incident = await self.get_owned_incident(incident_id, user_id)
        incident.status = status
        await self.incidents.commit()
        return incident

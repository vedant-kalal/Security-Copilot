"""
Real-time phishing check endpoint — POST /phishing/check.

Called by the extension's background service worker on every
navigation (architecture doc section 8, "Popup Behaviour"): a fast
synchronous verdict is returned for the popup UI, while the same
navigation is recorded as an Event and run through the correlation
engine so a matching Incident is available if the user clicks
"View Details".
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.event import EventType
from app.models.user import User
from app.schemas.phishing import PhishingCheckRequest, PhishingCheckResponse
from app.services.event_service import EventService
from app.services.incident_service import IncidentService
from app.services.phishing_service import PhishingService

router = APIRouter(prefix="/phishing", tags=["Phishing Detection"])


@router.post("/check", response_model=PhishingCheckResponse)
async def check_url(
    payload: PhishingCheckRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PhishingCheckResponse:
    """Classify a URL as phishing or legitimate, and correlate it into an incident if warranted."""
    phishing_service = PhishingService(db)
    verdict = await phishing_service.evaluate(payload.url, payload.page_title, payload.page_text_snippet)

    incident_id = None
    if payload.device_id is not None:
        event_service = EventService(db)
        event = await event_service.record_event(
            device_id=payload.device_id,
            event_type=EventType.URL_VISIT,
            payload={
                "url": payload.url,
                "page_title": payload.page_title,
                "page_text_snippet": payload.page_text_snippet,
            },
        )
        incident_service = IncidentService(db)
        result = await incident_service.ingest_and_correlate(current_user.id, event)
        if result is not None:
            incident_id = result.incident.incident_id

    risk_label = "high" if verdict.confidence >= 0.75 else "medium" if verdict.confidence >= 0.5 else "low"

    return PhishingCheckResponse(
        url=verdict.url,
        is_phishing=verdict.is_phishing,
        confidence=verdict.confidence,
        risk_label=risk_label,
        reasons=verdict.reasons,
        threat_intel_hit=verdict.threat_intel_hit,
        incident_id=incident_id,
    )

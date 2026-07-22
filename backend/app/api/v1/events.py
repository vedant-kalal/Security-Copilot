"""
Event ingestion endpoint — POST /events.

This is the entry point for the extension's telemetry (core workflow
steps 3-4: "Extension monitors browser events" -> "Events sent to
FastAPI"). Every accepted event is run through the full detection +
correlation pipeline synchronously, so the response can report whether
an incident was created.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import ForbiddenError, ValidationError
from app.models.user import User
from app.schemas.event import EventBatchCreateRequest, EventCreateRequest, EventIngestResponse
from app.services.device_service import DeviceService
from app.services.event_service import EventService
from app.services.incident_service import IncidentService

router = APIRouter(prefix="/events", tags=["Events"])


async def _ingest_single(
    payload: EventCreateRequest, current_user: User, db: AsyncSession
) -> EventIngestResponse:
    device_service = DeviceService(db)
    await device_service.get_owned_device(payload.device_id, current_user.id)

    event_service = EventService(db)
    event = await event_service.record_event(
        device_id=payload.device_id,
        event_type=payload.event_type,
        payload=payload.payload,
        timestamp=payload.timestamp,
    )

    incident_service = IncidentService(db)
    result = await incident_service.ingest_and_correlate(current_user.id, event)

    if result is None:
        return EventIngestResponse(accepted=1, incident_created=False)

    return EventIngestResponse(accepted=1, incident_id=result.incident.incident_id, incident_created=result.created)


@router.post("", response_model=EventIngestResponse, status_code=201)
async def ingest_event(
    payload: EventCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EventIngestResponse:
    """Ingest a single browser telemetry event and run the detection pipeline."""
    return await _ingest_single(payload, current_user, db)


@router.post("/batch", response_model=EventIngestResponse, status_code=201)
async def ingest_event_batch(
    payload: EventBatchCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EventIngestResponse:
    """Ingest multiple events in one request (used by the extension when
    flushing a buffer of events collected while offline)."""
    if not payload.events:
        return EventIngestResponse(accepted=0, incident_created=False)

    if len(payload.events) > 100:
        raise ValidationError("Batch size cannot exceed 100 events")

    device_ids = {e.device_id for e in payload.events}
    if len(device_ids) != 1:
        raise ForbiddenError("All events in a batch must belong to the same device")

    device_service = DeviceService(db)
    await device_service.get_owned_device(next(iter(device_ids)), current_user.id)

    last_incident_id = None
    last_created = False
    accepted = 0

    event_service = EventService(db)
    incident_service = IncidentService(db)

    for event_payload in payload.events:
        event = await event_service.record_event(
            device_id=event_payload.device_id,
            event_type=event_payload.event_type,
            payload=event_payload.payload,
            timestamp=event_payload.timestamp,
        )
        accepted += 1
        result = await incident_service.ingest_and_correlate(current_user.id, event)
        if result is not None:
            last_incident_id = result.incident.incident_id
            last_created = result.created

    return EventIngestResponse(accepted=accepted, incident_id=last_incident_id, incident_created=last_created)

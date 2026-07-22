"""Incident management endpoints — GET /incidents, GET /incidents/{id}, PATCH /incidents/{id}."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.incident import IncidentStatus
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.incident import IncidentDetailRead, IncidentRead, IncidentUpdateRequest
from app.services.incident_service import IncidentService

router = APIRouter(prefix="/incidents", tags=["Incidents"])


@router.get("", response_model=PaginatedResponse[IncidentRead])
async def list_incidents(
    status_filter: Optional[IncidentStatus] = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[IncidentRead]:
    """List incidents for the current user, optionally filtered by status.

    Powers the dashboard's 'Security Operations' (active incidents) view.
    """
    service = IncidentService(db)
    items, total = await service.list_for_user(current_user.id, status=status_filter, page=page, page_size=page_size)
    return PaginatedResponse(
        items=[IncidentRead.model_validate(i) for i in items], total=total, page=page, page_size=page_size
    )


@router.get("/{incident_id}", response_model=IncidentDetailRead)
async def get_incident(
    incident_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> IncidentDetailRead:
    """Full incident detail: evidence timeline + AI-generated explanation
    (architecture doc section 5, "Investigation" area: Timeline, Evidence,
    AI explanation, Playbooks)."""
    service = IncidentService(db)
    incident = await service.get_owned_incident(incident_id, current_user.id)
    return IncidentDetailRead.model_validate(incident)


@router.patch("/{incident_id}", response_model=IncidentDetailRead)
async def update_incident(
    incident_id: UUID,
    payload: IncidentUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> IncidentDetailRead:
    """Update an incident's status (e.g. analyst marks it Investigating / Resolved)."""
    service = IncidentService(db)
    if payload.status is not None:
        await service.update_status(incident_id, current_user.id, payload.status)
    incident = await service.get_owned_incident(incident_id, current_user.id)
    return IncidentDetailRead.model_validate(incident)

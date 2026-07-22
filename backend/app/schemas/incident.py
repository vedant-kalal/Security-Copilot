"""Incident + evidence + AI response schemas."""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel

from app.models.incident import IncidentSeverity, IncidentStatus
from app.schemas.common import ORMBaseModel
from app.schemas.event import EventRead


class EvidenceRead(ORMBaseModel):
    evidence_id: UUID
    incident_id: UUID
    event_id: UUID
    reason: str
    score: float
    event: Optional[EventRead] = None


class AIResponseRead(ORMBaseModel):
    response_id: UUID
    incident_id: UUID
    summary: str
    recommendation: str
    generated_at: datetime


class IncidentRead(ORMBaseModel):
    incident_id: UUID
    user_id: UUID
    title: str
    severity: IncidentSeverity
    confidence: float
    mitre: List[str]
    status: IncidentStatus
    summary: str
    created_at: datetime


class IncidentDetailRead(IncidentRead):
    evidence_entries: List[EvidenceRead] = []
    ai_responses: List[AIResponseRead] = []


class IncidentUpdateRequest(BaseModel):
    status: Optional[IncidentStatus] = None

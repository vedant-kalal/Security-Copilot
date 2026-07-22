"""Playbook retrieval endpoint — GET /playbooks/{incident}."""
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.playbook import PlaybookRead
from app.services.incident_service import IncidentService
from app.services.rag_service import RAGService

router = APIRouter(prefix="/playbooks", tags=["Playbooks"])


@router.get("/{incident_id}", response_model=list[PlaybookRead])
async def get_playbooks_for_incident(
    incident_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[PlaybookRead]:
    """Return the guided-response playbook(s) retrieved via RAG for a given incident."""
    incident_service = IncidentService(db)
    incident = await incident_service.get_owned_incident(incident_id, current_user.id)

    rag_service = RAGService(db)
    playbooks = await rag_service.retrieve_playbooks(incident.title, incident.mitre)
    return [PlaybookRead.model_validate(p) for p in playbooks]

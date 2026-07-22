"""Playbook schemas (RAG retrieval results)."""
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import ORMBaseModel


class PlaybookRead(ORMBaseModel):
    id: UUID
    title: str
    mitre_techniques: list[str]
    content: str


class PlaybookRetrievalResult(BaseModel):
    playbook: PlaybookRead
    similarity: float

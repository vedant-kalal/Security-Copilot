"""
SQLAlchemy ORM models.

Table design follows the SentinelAI Solution Architecture document
(section 17, "Database Design") exactly. One additional table,
`playbooks`, is introduced beyond the original spec to support the RAG
pipeline (section 11 / "RAG retrieves playbooks" in the core workflow) —
pgvector needs somewhere to store playbook embeddings, and the
architecture document does not define that table explicitly, so it is
added here as the most production-ready, spec-consistent choice.
"""
from app.models.ai_response import AIResponse
from app.models.device import Device
from app.models.event import Event
from app.models.evidence import Evidence
from app.models.incident import Incident, IncidentStatus, IncidentSeverity
from app.models.playbook import Playbook
from app.models.session import Session
from app.models.threat_cache import ThreatCache
from app.models.user import User

__all__ = [
    "AIResponse",
    "Device",
    "Event",
    "Evidence",
    "Incident",
    "IncidentStatus",
    "IncidentSeverity",
    "Playbook",
    "Session",
    "ThreatCache",
    "User",
]

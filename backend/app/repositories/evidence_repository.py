"""Evidence repository."""
from uuid import UUID

from app.models.evidence import Evidence
from app.repositories.base import BaseRepository


class EvidenceRepository(BaseRepository[Evidence]):
    model = Evidence
    pk_column = "evidence_id"

    async def get(self, pk: UUID) -> Evidence | None:
        return await self.session.get(Evidence, pk)

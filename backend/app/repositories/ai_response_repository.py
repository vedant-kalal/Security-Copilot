"""AI response repository."""
from uuid import UUID

from app.models.ai_response import AIResponse
from app.repositories.base import BaseRepository


class AIResponseRepository(BaseRepository[AIResponse]):
    model = AIResponse
    pk_column = "response_id"

    async def get(self, pk: UUID) -> AIResponse | None:
        return await self.session.get(AIResponse, pk)

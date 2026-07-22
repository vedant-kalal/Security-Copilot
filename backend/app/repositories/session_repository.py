"""Login-session repository."""
from uuid import UUID

from app.models.session import Session as LoginSession
from app.repositories.base import BaseRepository


class SessionRepository(BaseRepository[LoginSession]):
    model = LoginSession
    pk_column = "session_id"

    async def get(self, pk: UUID) -> LoginSession | None:
        return await self.session.get(LoginSession, pk)

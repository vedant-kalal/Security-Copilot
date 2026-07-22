"""Device repository."""
from typing import Sequence
from uuid import UUID

from sqlalchemy import select

from app.models.device import Device
from app.repositories.base import BaseRepository


class DeviceRepository(BaseRepository[Device]):
    model = Device
    pk_column = "device_id"

    async def get(self, pk: UUID) -> Device | None:
        return await self.session.get(Device, pk)

    async def list_for_user(self, user_id: UUID) -> Sequence[Device]:
        stmt = select(Device).where(Device.user_id == user_id).order_by(Device.last_seen.desc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_for_user(self, user_id: UUID) -> int:
        stmt = select(Device).where(Device.user_id == user_id)
        result = await self.session.execute(stmt)
        return len(result.scalars().all())

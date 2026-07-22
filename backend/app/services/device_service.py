"""Device registration and lookup service."""
from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.device import Device
from app.repositories.device_repository import DeviceRepository


class DeviceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.devices = DeviceRepository(session)

    async def register_device(self, user_id: UUID, browser: str, os: str) -> Device:
        device = Device(user_id=user_id, browser=browser, os=os)
        await self.devices.add(device)
        await self.devices.commit()
        return device

    async def touch_last_seen(self, device_id: UUID) -> Device:
        from datetime import datetime, timezone

        device = await self.devices.get(device_id)
        if not device:
            raise NotFoundError(f"Device {device_id} not found")
        device.last_seen = datetime.now(timezone.utc)
        await self.devices.commit()
        return device

    async def list_for_user(self, user_id: UUID) -> Sequence[Device]:
        return await self.devices.list_for_user(user_id)

    async def get_owned_device(self, device_id: UUID, user_id: UUID) -> Device:
        device = await self.devices.get(device_id)
        if not device or device.user_id != user_id:
            raise NotFoundError(f"Device {device_id} not found")
        return device

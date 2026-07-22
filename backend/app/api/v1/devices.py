"""Device management endpoints."""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.device import DeviceRead, DeviceRegisterRequest
from app.services.device_service import DeviceService

router = APIRouter(prefix="/devices", tags=["Devices"])


@router.post("", response_model=DeviceRead, status_code=201)
async def register_device(
    payload: DeviceRegisterRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DeviceRead:
    """Register a new device (browser/OS pair) for the current user.

    Called once by the extension's background service worker after the
    user signs in — architecture doc section 3: 'Backend registers a
    Device.'
    """
    service = DeviceService(db)
    device = await service.register_device(current_user.id, payload.browser, payload.os)
    return DeviceRead.model_validate(device)


@router.get("", response_model=List[DeviceRead])
async def list_devices(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> List[DeviceRead]:
    """List every device registered to the current user."""
    service = DeviceService(db)
    devices = await service.list_for_user(current_user.id)
    return [DeviceRead.model_validate(d) for d in devices]


@router.post("/{device_id}/heartbeat", response_model=DeviceRead)
async def device_heartbeat(
    device_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> DeviceRead:
    """Update a device's `last_seen` timestamp. Called periodically by the
    extension's background service worker while monitoring is active."""
    service = DeviceService(db)
    await service.get_owned_device(device_id, current_user.id)
    device = await service.touch_last_seen(device_id)
    return DeviceRead.model_validate(device)

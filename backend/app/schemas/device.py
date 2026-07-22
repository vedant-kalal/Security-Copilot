"""Device schemas."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMBaseModel


class DeviceRegisterRequest(BaseModel):
    browser: str = Field(min_length=1, max_length=100)
    os: str = Field(min_length=1, max_length=100)


class DeviceRead(ORMBaseModel):
    device_id: UUID
    user_id: UUID
    browser: str
    os: str
    last_seen: datetime

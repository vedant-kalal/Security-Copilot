"""User schemas."""
from datetime import datetime
from uuid import UUID

from pydantic import EmailStr

from app.schemas.common import ORMBaseModel


class UserRead(ORMBaseModel):
    id: UUID
    email: EmailStr
    created_at: datetime

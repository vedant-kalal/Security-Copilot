"""Shared/base schema types used across multiple modules."""
from datetime import datetime
from typing import Generic, List, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ORMBaseModel(BaseModel):
    """Base for schemas that are built directly from SQLAlchemy ORM instances."""

    model_config = ConfigDict(from_attributes=True)


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated list envelope."""

    items: List[T]
    total: int
    page: int
    page_size: int


class MessageResponse(BaseModel):
    """Simple acknowledgement response."""

    message: str


class TimestampedModel(ORMBaseModel):
    created_at: datetime

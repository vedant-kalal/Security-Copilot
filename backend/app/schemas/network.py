"""Network telemetry schemas: CSV upload + dataset replay (architecture doc section 10)."""
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class NetworkUploadResponse(BaseModel):
    rows_ingested: int
    anomalies_detected: int
    incidents_created: int
    incident_ids: list[UUID]


class ReplayStartRequest(BaseModel):
    dataset: str = Field(description="One of: cicids2017, unsw-nb15")
    device_id: Optional[UUID] = None
    max_rows: int = Field(default=200, ge=1, le=5000)
    speed: float = Field(default=10.0, gt=0, description="Rows replayed per second")


class ReplayStartResponse(BaseModel):
    replay_id: UUID
    dataset: str
    rows_scheduled: int
    status: str

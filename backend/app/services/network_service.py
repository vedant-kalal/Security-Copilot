"""
Network telemetry service.

Implements the two non-extension telemetry sources described in the
architecture document, section 10 ("Network Anomaly Demonstration"):

  B. CSV Upload    — user uploads network logs; analysed immediately.
  C. Dataset Replay — replay CICIDS2017 / UNSW-NB15 traffic as if it
                       were live telemetry, so Isolation Forest can
                       analyse it and incidents appear in the dashboard.
"""
from __future__ import annotations

import asyncio
import csv
import io
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import session_scope
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.models.event import EventType
from app.services.event_service import EventService
from app.services.incident_service import IncidentService

logger = get_logger(__name__)

_DATASETS_DIR = Path(__file__).resolve().parent.parent / "data" / "network_datasets"
_DATASET_FILES = {
    "cicids2017": _DATASETS_DIR / "cicids2017_sample.csv",
    "unsw-nb15": _DATASETS_DIR / "unsw_nb15_sample.csv",
}


class NetworkService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.event_service = EventService(session)
        self.incident_service = IncidentService(session)

    async def process_csv_upload(self, user_id: UUID, device_id: UUID, file_bytes: bytes) -> dict:
        """Parse an uploaded network-log CSV and run every row through the
        anomaly-detection + correlation pipeline immediately."""
        try:
            text = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValidationError("Uploaded file is not valid UTF-8 text") from exc

        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise ValidationError("CSV file has no header row")

        rows_ingested = 0
        anomalies_detected = 0
        incident_ids: set[UUID] = set()

        for row in reader:
            payload = {k: v for k, v in row.items() if k is not None}
            event = await self.event_service.record_event(
                device_id=device_id, event_type=EventType.NETWORK_FLOW_UPLOAD, payload=payload
            )
            rows_ingested += 1

            prediction = self.incident_service.anomaly_service.evaluate(payload)
            if prediction.is_anomaly:
                anomalies_detected += 1

            result = await self.incident_service.ingest_and_correlate(user_id, event)
            if result is not None:
                incident_ids.add(result.incident.incident_id)

        return {
            "rows_ingested": rows_ingested,
            "anomalies_detected": anomalies_detected,
            "incidents_created": len(incident_ids),
            "incident_ids": list(incident_ids),
        }

    async def start_replay(
        self, user_id: UUID, device_id: UUID, dataset: str, max_rows: int, speed: float
    ) -> dict:
        """Schedule a background replay of a bundled sample dataset. The
        replay runs in its own database session (independent of the
        request's session, which closes when the HTTP response returns)."""
        dataset_key = dataset.lower().strip()
        dataset_path = _DATASET_FILES.get(dataset_key)
        if dataset_path is None or not dataset_path.exists():
            raise ValidationError(
                f"Unknown dataset '{dataset}'. Supported datasets: {', '.join(_DATASET_FILES)}"
            )

        replay_id = uuid4()
        rows = self._load_dataset_rows(dataset_path, max_rows)

        asyncio.create_task(
            self._run_replay(replay_id, user_id, device_id, dataset_key, rows, speed)
        )

        logger.info(
            "Scheduled replay %s for user %s: dataset=%s rows=%d speed=%.1f rows/s",
            replay_id,
            user_id,
            dataset_key,
            len(rows),
            speed,
        )

        return {
            "replay_id": replay_id,
            "dataset": dataset_key,
            "rows_scheduled": len(rows),
            "status": "started",
        }

    @staticmethod
    def _load_dataset_rows(path: Path, max_rows: int) -> list[dict]:
        with path.open("r", newline="") as f:
            reader = csv.DictReader(f)
            rows = []
            for i, row in enumerate(reader):
                if i >= max_rows:
                    break
                rows.append(dict(row))
        return rows

    @staticmethod
    async def _run_replay(
        replay_id: UUID, user_id: UUID, device_id: UUID, dataset: str, rows: list[dict], speed: float
    ) -> None:
        delay = 1.0 / speed if speed > 0 else 0.1
        incidents_created = 0

        for row in rows:
            await asyncio.sleep(delay)
            try:
                async with session_scope() as session:
                    event_service = EventService(session)
                    incident_service = IncidentService(session)

                    event = await event_service.record_event(
                        device_id=device_id, event_type=EventType.NETWORK_FLOW_REPLAY, payload=row
                    )
                    result = await incident_service.ingest_and_correlate(user_id, event)
                    if result is not None and result.created:
                        incidents_created += 1
            except Exception:  # noqa: BLE001 - a single bad row must not kill the replay
                logger.exception("Replay %s: failed to process a row", replay_id)

        logger.info(
            "Replay %s (%s) finished: %d rows processed, %d new incidents created",
            replay_id,
            dataset,
            len(rows),
            incidents_created,
        )

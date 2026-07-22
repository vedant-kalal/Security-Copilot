"""Network anomaly endpoints — POST /network/upload, POST /network/replay/start."""
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import ValidationError
from app.models.user import User
from app.schemas.network import NetworkUploadResponse, ReplayStartRequest, ReplayStartResponse
from app.services.device_service import DeviceService
from app.services.network_service import NetworkService

router = APIRouter(prefix="/network", tags=["Network Anomaly Detection"])


@router.post("/upload", response_model=NetworkUploadResponse, status_code=201)
async def upload_network_log(
    device_id: UUID = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NetworkUploadResponse:
    """Upload a CSV of network flow logs for immediate Isolation Forest analysis
    (architecture doc section 10.B)."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise ValidationError("Only .csv files are supported")

    device_service = DeviceService(db)
    await device_service.get_owned_device(device_id, current_user.id)

    contents = await file.read()
    network_service = NetworkService(db)
    result = await network_service.process_csv_upload(current_user.id, device_id, contents)
    return NetworkUploadResponse(**result)


@router.post("/replay/start", response_model=ReplayStartResponse, status_code=202)
async def start_replay(
    payload: ReplayStartRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReplayStartResponse:
    """Start replaying a bundled CICIDS2017/UNSW-NB15 sample dataset as live
    telemetry (architecture doc section 10.C)."""
    device_service = DeviceService(db)

    if payload.device_id is not None:
        device = await device_service.get_owned_device(payload.device_id, current_user.id)
    else:
        devices = await device_service.list_for_user(current_user.id)
        if not devices:
            raise ValidationError("Register a device before starting a replay, or pass device_id explicitly")
        device = devices[0]

    network_service = NetworkService(db)
    result = await network_service.start_replay(
        current_user.id, device.device_id, payload.dataset, payload.max_rows, payload.speed
    )
    return ReplayStartResponse(**result)

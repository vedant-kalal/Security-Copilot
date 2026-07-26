"""
POST /report-flow (spec section 10).

Called by the native host when Isolation Forest/TranAD flags a flow.
MITRE mapping (spec section 6, `mitre/lookup.py`) isn't built yet, so
this runs the shared agent without technique context for now — once
`mitre/lookup.py` is real, call `find_technique()` here and pass its
result as `run_case`'s `mitre_technique` argument.
"""
from __future__ import annotations

from fastapi import APIRouter

from agent.graph import run_case_traced
from api.schemas import ReportFlowRequest

router = APIRouter()


@router.post("/report-flow", tags=["Network"])
async def report_flow(payload: ReportFlowRequest) -> dict:
    description = f"Destination: {payload.destination}"
    if payload.port:
        description += f", port {payload.port}"
    if payload.protocol:
        description += f", protocol {payload.protocol}"
    if payload.process_name:
        description += f", process {payload.process_name}"
    if payload.anomaly_score is not None:
        description += f", anomaly score {payload.anomaly_score:.2f}"
    if payload.context:
        description += f". {payload.context}"

    result = await run_case_traced("network_flow", description)
    return {**result["verdict"], "run_id": result["run_id"]}

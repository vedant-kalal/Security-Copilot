"""
POST /report-flow (spec section 10).

Called by the native host when Isolation Forest/TranAD flags a flow. The
flow's description is mapped to the nearest MITRE ATT&CK technique
(mitre/lookup.py) and that match is threaded into the agent as
`run_case`'s `mitre_technique` argument, so the verdict/report can name a
technique and attach its mitigation text, not just a bare anomaly score.
"""
from __future__ import annotations

from fastapi import APIRouter

from agent.graph import run_case_traced
from api.schemas import ReportFlowRequest
from logger import get_logger
from mitre.lookup import find_technique

router = APIRouter()
logger = get_logger(__name__)


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

    # Map the flow to the nearest ATT&CK technique. Returns None if the index
    # hasn't been built yet (python -m mitre.build_index) — the agent then runs
    # without technique context rather than failing the request.
    mitre_technique = find_technique(payload.context or description)
    if mitre_technique:
        logger.info(
            "Flow mapped to MITRE %s (%s), similarity %.2f",
            mitre_technique["technique_id"],
            mitre_technique["technique_name"],
            mitre_technique["similarity"],
        )

    result = await run_case_traced("network_flow", description, mitre_technique=mitre_technique)
    return {**result["verdict"], "run_id": result["run_id"]}

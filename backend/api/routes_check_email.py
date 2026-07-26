"""POST /check-email (spec section 10)."""
from __future__ import annotations

from fastapi import APIRouter

from agent.graph import run_case_traced
from api.schemas import CheckEmailRequest

router = APIRouter()


@router.post("/check-email", tags=["Email"])
async def check_email(payload: CheckEmailRequest) -> dict:
    """No URL to look up, so this skips the router's blocklist/cache step
    entirely (spec section 10). Recorded to history.py like every other case."""
    result = await run_case_traced("email", payload.text)
    return {**result["verdict"], "run_id": result["run_id"]}

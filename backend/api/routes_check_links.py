"""POST /check-links (spec section 10)."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter

from agent.graph import run_case_traced
from api.schemas import CheckLinksRequest, CheckLinksResponse

router = APIRouter()


@router.post("/check-links", response_model=CheckLinksResponse, tags=["Links"])
async def check_links(payload: CheckLinksRequest) -> CheckLinksResponse:
    """Each URL runs the router's fast path first (blocklist/cache), then the
    agent for whatever's unresolved — concurrently across URLs. Every check is
    recorded to history.py, browsable via GET /runs and the UI."""
    results = await asyncio.gather(*(run_case_traced("link", url) for url in payload.urls))
    return CheckLinksResponse(
        results={url: {**r["verdict"], "run_id": r["run_id"]} for url, r in zip(payload.urls, results)}
    )

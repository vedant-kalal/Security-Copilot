"""
POST /check-links-stream — same investigation as /check-links, but as a
Server-Sent Events stream instead of one blocking JSON response, so the
extension's "Full report" flow can show what the agent is actually doing
(exploring the page, checking VirusTotal, searching for the real site,
...) instead of a static "Investigating..." spinner for however long the
real thing takes (confirmed up to ~40s for a real case).

Single-URL only — this exists specifically for the extension's one-URL-
at-a-time "Full report" button. /check-links (unchanged) is still what
the CLI and any batch/multi-URL caller uses; both ultimately run the same
agent/graph.py code (stream_case_traced), so results are identical
either way — this route only changes how progress is surfaced.
"""
from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from agent.graph import stream_case_traced
from api.schemas import CheckLinksRequest

router = APIRouter()


async def _event_stream(url: str):
    async for event in stream_case_traced("link", url):
        yield f"data: {json.dumps(event)}\n\n"


@router.post("/check-links-stream", tags=["Links"])
async def check_links_stream(payload: CheckLinksRequest) -> StreamingResponse:
    url = payload.urls[0]
    return StreamingResponse(
        _event_stream(url),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

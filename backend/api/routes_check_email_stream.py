"""
POST /check-email-stream — same investigation as /check-email, but as a
Server-Sent Events stream instead of one blocking JSON response.

Same motivation as routes_check_links_stream.py, sharper here: an email
with several links now costs one inspect_website + domain_reputation
round trip *per link* (see routes_check_email.py's _extract_links and
config.py's EMAIL_LINK_RECURSION_BUDGET), so a multi-link email can
easily run past a minute — comfortably long enough to hit MV3's ~30s
service-worker idle teardown if the extension is left awaiting one
blocking call the way the popup used to. Streaming progress keeps the
service worker's keepalive interval fed (background.ts's startKeepAlive)
the same way the link flow already relies on.
"""
from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from agent.graph import stream_case_traced
from api.routes_check_email import _extract_links
from api.schemas import CheckEmailRequest

router = APIRouter()


async def _event_stream(payload: CheckEmailRequest):
    links = _extract_links(payload)
    async for event in stream_case_traced("email", payload.text, email_links=links):
        yield f"data: {json.dumps(event)}\n\n"


@router.post("/check-email-stream", tags=["Email"])
async def check_email_stream(payload: CheckEmailRequest) -> StreamingResponse:
    return StreamingResponse(
        _event_stream(payload),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

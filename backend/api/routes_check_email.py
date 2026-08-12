"""POST /check-email (spec section 10)."""
from __future__ import annotations

from fastapi import APIRouter

from agent.graph import run_case_traced
from api.schemas import CheckEmailRequest
from utils.validators import dedupe_links_by_domain, extract_urls_from_text

router = APIRouter()

# How many distinct links a single email investigation will actually chase
# down — each one costs a real inspect_website + domain_reputation round
# trip (see config.py's EMAIL_LINK_RECURSION_BUDGET), so this is a hard
# ceiling regardless of how many raw links the email contains.
_MAX_LINKS_PER_EMAIL = 5


def _extract_links(payload: CheckEmailRequest) -> list[str]:
    """Union of two sources: URLs visible in the raw text itself (catches
    a plain pasted email with no DOM behind it — the dashboard's Email
    scanner), and real anchor hrefs the caller already had DOM access to
    (catches "Click here"-style links the text alone would miss — see
    CheckEmailRequest.links). Deduped to one URL per domain and capped."""
    combined = extract_urls_from_text(payload.text) + list(payload.links)
    return dedupe_links_by_domain(combined, _MAX_LINKS_PER_EMAIL)


@router.post("/check-email", tags=["Email"])
async def check_email(payload: CheckEmailRequest) -> dict:
    """No URL to look up, so this skips the router's blocklist/cache step
    entirely (spec section 10). Recorded to history.py like every other case."""
    links = _extract_links(payload)
    result = await run_case_traced("email", payload.text, email_links=links)
    return {**result["verdict"], "run_id": result["run_id"]}

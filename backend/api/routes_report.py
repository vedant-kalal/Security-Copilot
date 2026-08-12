"""
POST /report, GET /blocklist — the "Report & Block" action (run page /
extension popup) for a confirmed-bad URL. See reporting.py's module
docstring for why this reports outward instead of attacking the site.

GET /blocklist exists for the extension: it keeps its own local copy
(synced periodically, and refreshed right after a successful /report)
so it can block a matching navigation immediately, before ever making a
network round trip to ask the backend "is this one blocked?"
"""
from __future__ import annotations

from fastapi import APIRouter

from api.schemas import BlocklistResponse, ReportRequest, ReportResponse
from cache.blocklist import add_to_blocklist, list_blocklist
from reporting import report_url_to_virustotal
from utils.validators import extract_domain

router = APIRouter()


@router.post("/report", response_model=ReportResponse, tags=["Report"])
async def report_url(payload: ReportRequest) -> ReportResponse:
    domain = extract_domain(payload.url)
    added = add_to_blocklist(domain)
    vt_result = await report_url_to_virustotal(payload.url)
    return ReportResponse(domain=domain, added_to_blocklist=added, virustotal=vt_result)


@router.get("/blocklist", response_model=BlocklistResponse, tags=["Report"])
async def get_blocklist() -> BlocklistResponse:
    return BlocklistResponse(domains=list_blocklist())

"""
`web_search` tool — NEW, not one of the original spec's 3 tools (spec
section 4 names only inspect_website/domain_reputation/content_classifier).
Added at the user's request 2026-07-25: when the agent suspects a page
is impersonating a real company, it can search for that company's name
and hand back its actual official site(s) — so the verdict isn't just
"this is dangerous," it's "and here's where you probably meant to go."

Uses `ddgs` (DuckDuckGo search) — keyless, free, no signup. Deliberately
not a paid/API-key search provider (Tavily, Google Custom Search, Bing):
this project already requires OPENROUTER_API_KEYS and optionally accepts
VT_API_KEY; a third mandatory key for a "nice to have" feature isn't a
good trade. Same graceful-degrade shape as every other tool here if the
lookup fails for any reason.
"""
from __future__ import annotations

import asyncio

from langchain_core.tools import tool

from config import get_settings
from logger import get_logger

logger = get_logger(__name__)


def _search_sync(query: str, max_results: int) -> list[dict]:
    from ddgs import DDGS

    with DDGS() as ddgs:
        results = ddgs.text(query, max_results=max_results)
    return [{"title": r.get("title"), "url": r.get("href"), "snippet": r.get("body")} for r in results]


@tool
async def web_search(query: str) -> dict:
    """Searches the web and returns real results — use this when a page appears to impersonate a known company or brand, to find that brand's actual official website(s) so they can be shown to the user as the real, legitimate alternative to the suspicious link. Search for the company/brand name itself (e.g. "Instagram official website"), not the suspicious URL."""
    settings = get_settings()
    try:
        results = await asyncio.to_thread(_search_sync, query, settings.WEB_SEARCH_MAX_RESULTS)
        return {"available": True, "query": query, "results": results}
    except Exception as exc:  # noqa: BLE001 - a search hiccup should degrade, not crash the agent loop
        logger.warning("web_search failed for %r: %s", query, exc)
        return {"available": False, "query": query, "results": [], "detail": str(exc)}

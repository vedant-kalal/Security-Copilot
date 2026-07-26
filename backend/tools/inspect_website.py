"""
`inspect_website` tool (spec section 4.1).

Opens a URL in an isolated sandbox browser (Playwright, headless
Chromium, `--no-sandbox`) and reports what the page actually does. A
fresh browser context is created per call and torn down in `finally` —
never reused between checks, never authenticates against or submits
real credentials to any real service (spec section 14).

Also extracts every on-page link (`links`, deduped, flagged same-origin
vs cross-origin) so the agent can *choose* to call this tool again on a
link it finds suspicious — e.g. a secondary "login" link on a page that
otherwise looked clean. That's the whole mechanism for multi-page
investigation: no separate "crawl" or "click" capability, no automatic
form submission, no automatic permission-granting — just handing the
agent enough information to decide whether investigating further is
warranted, exactly the same way it already decides which tools to call
at all. See agent/agent_node.py's system prompt for how deep it's
told to go.

Uses LangChain's `content_and_artifact` response format: the base64
screenshot is real evidence spec 4.1 asks for, but it's tens of
thousands of tokens as text — sending it back through the LLM's context
blows through free-tier token-per-minute limits for no benefit (a
non-vision chat call can't "see" it anyway). So the screenshot travels
as the ToolMessage's `artifact` (available to any caller that wants the
raw bytes later, e.g. a future dashboard) while `content` — what the
LLM actually reads — only says a screenshot was captured and how big it is.

Two things were added after a real ngrok-tunneled phishing page (a fake
Instagram login) turned up "safe" because the tool never actually saw
it — it only ever inspected ngrok's own neutral anti-abuse warning
interstitial, which every free ngrok link shows before the real
destination and which was still mid-render at `domcontentloaded`:
  1. `ngrok-skip-browser-warning` is sent on every request. It's a
     header ngrok itself documents for exactly this purpose; harmless
     and ignored by every other site, but it stops that interstitial
     from swallowing the real content of any ngrok-hosted phishing page.
  2. `wait_until="networkidle"` instead of `"domcontentloaded"`, so
     JS-rendered content (that interstitial, and plenty of legitimate
     SPAs) has actually painted before the screenshot/text are taken —
     still bounded by the same overall timeout, so a page that never
     goes idle just times out gracefully like any other slow page.
"""
from __future__ import annotations

import base64
from urllib.parse import urlparse

from langchain_core.tools import tool

from config import get_settings
from logger import get_logger

logger = get_logger(__name__)

_FORM_EXTRACT_JS = """
(forms) => forms.map((f) => ({
    action: f.action || null,
    has_password_field: !!f.querySelector('input[type="password"]'),
}))
"""

_LINK_EXTRACT_JS = """
(anchors) => anchors
    .map((a) => ({ href: a.href || null, text: (a.textContent || '').trim().slice(0, 80) }))
    .filter((l) => l.href && l.href.startsWith('http'))
"""


def _dedupe_links(links: list[dict], final_url: str, limit: int) -> list[dict]:
    """De-dupe by href, flag same-origin vs cross-origin (a link to a
    different domain is more informative for deciding whether to explore
    further than yet another internal nav link), cap at `limit`."""
    origin = urlparse(final_url).netloc
    seen: set[str] = set()
    deduped: list[dict] = []
    for link in links:
        href = link["href"]
        if href in seen:
            continue
        seen.add(href)
        deduped.append({**link, "same_origin": urlparse(href).netloc == origin})
        if len(deduped) >= limit:
            break
    return deduped


async def _get_redirect_chain(response) -> list[dict]:
    """Walk Playwright's `request.redirected_from` chain backward from the
    final response to reconstruct every hop — original URL through any
    30x redirects to `final_url` — each with its own status code."""
    chain_requests = []
    req = response.request
    while req is not None:
        chain_requests.insert(0, req)
        req = req.redirected_from

    chain = []
    for req in chain_requests:
        resp = await req.response()
        chain.append({"url": req.url, "status": resp.status if resp else None})
    return chain


def _for_llm(full: dict) -> dict:
    """Everything the model should see — same as `full` but with the
    (potentially huge) base64 screenshot swapped for a short marker."""
    screenshot = full.get("screenshot_base64")
    llm_view = {k: v for k, v in full.items() if k != "screenshot_base64"}
    llm_view["screenshot"] = f"captured, {len(screenshot)} base64 chars" if screenshot else "not captured"
    return llm_view


@tool(response_format="content_and_artifact")
async def inspect_website(url: str) -> tuple[dict, dict]:
    """Opens a URL in an isolated sandbox browser and reports what the page actually does — final destination after redirects, a screenshot, visible page text, any forms and where they submit to, and every outbound network request. Use this first for almost any unknown link."""
    settings = get_settings()

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        error = {"error": "Playwright is not installed. Run: pip install playwright && playwright install chromium"}
        return error, error

    network_requests: list[dict[str, str]] = []

    def _record_request(request) -> None:
        if len(network_requests) < settings.SANDBOX_MAX_NETWORK_REQUESTS:
            network_requests.append({"url": request.url, "method": request.method})

    browser = None
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            context = await browser.new_context(
                ignore_https_errors=True,
                extra_http_headers={"ngrok-skip-browser-warning": "true"},
            )
            page = await context.new_page()
            page.on("request", _record_request)

            try:
                response = await page.goto(
                    url, timeout=settings.SANDBOX_TIMEOUT_SECONDS * 1000, wait_until="networkidle"
                )
            except Exception as exc:  # noqa: BLE001 - a page that won't load is itself evidence, not a tool crash
                full = {
                    "final_url": url,
                    "navigation_error": str(exc),
                    "redirect_chain": [],
                    "screenshot_base64": None,
                    "page_text": "",
                    "forms": [],
                    "links": [],
                    "network_requests": network_requests,
                }
                return _for_llm(full), full

            screenshot_bytes = await page.screenshot(type="png")
            page_text = await page.inner_text("body")
            forms = await page.eval_on_selector_all("form", _FORM_EXTRACT_JS)
            raw_links = await page.eval_on_selector_all("a", _LINK_EXTRACT_JS)
            links = _dedupe_links(raw_links, page.url, settings.SANDBOX_MAX_LINKS)
            redirect_chain = await _get_redirect_chain(response) if response else [{"url": url, "status": None}]

            full = {
                "final_url": page.url,
                "status_code": response.status if response else None,
                "redirect_chain": redirect_chain,
                "screenshot_base64": base64.b64encode(screenshot_bytes).decode("ascii"),
                "page_text": page_text[: settings.SANDBOX_MAX_PAGE_TEXT_CHARS],
                "forms": forms,
                "links": links,
                "network_requests": network_requests,
            }
            return _for_llm(full), full
    except Exception as exc:  # noqa: BLE001 - never let a sandbox crash take down the agent loop
        logger.warning("inspect_website failed for %s: %s", url, exc)
        full = {
            "error": str(exc),
            "final_url": url,
            "redirect_chain": [],
            "screenshot_base64": None,
            "page_text": "",
            "forms": [],
            "links": [],
            "network_requests": network_requests,
        }
        return _for_llm(full), full
    finally:
        if browser is not None:
            await browser.close()

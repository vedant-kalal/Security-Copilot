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

Two more signal categories beyond page content, added because neither a
URL string nor a WHOIS/VirusTotal domain lookup can see them:
  - DOM/asset structure (`_summarize_assets`): whether the page's own
    scripts/images/stylesheets are served from its own domain or hotlinked
    from somewhere else. A cloned phishing kit very commonly skips copying
    the real brand's assets and just references them live from the real
    site — same visual result, dead giveaway once you look at where the
    bytes actually come from.
  - Deployment (`_get_deployment_info`): the responding server's raw HTTP
    headers and resolved IP address — the IP specifically is worth handing
    back to `domain_reputation`, which already accepts a bare IP (network-
    flow cases report one directly), so the agent can check this exact
    hosting IP's own reputation independent of the domain name.

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
(forms) => forms.map((f) => {
    // A named form control (e.g. <input name="action">) shadows the form
    // element's own .action property with that control's element instead
    // of the resolved URL string — a real HTML/DOM quirk. Falls back to
    // resolving the raw attribute by hand when that happens, so this never
    // sends back a DOM node Playwright can't serialize across the bridge
    // (verified 2026-08 on a real Google sign-in page, whose form has an
    // input named "action" — this broke every consumer of the field,
    // silently, until the extension/dashboard actually rendered forms).
    let action = null;
    if (typeof f.action === 'string' && f.action) {
        action = f.action;
    } else {
        const raw = f.getAttribute('action');
        if (raw) {
            try { action = new URL(raw, location.href).href; } catch { action = raw; }
        }
    }
    return { action, has_password_field: !!f.querySelector('input[type="password"]') };
})
"""

_LINK_EXTRACT_JS = """
(anchors) => anchors
    .map((a) => ({ href: a.href || null, text: (a.textContent || '').trim().slice(0, 80) }))
    .filter((l) => l.href && l.href.startsWith('http'))
"""

# DOM structure signal: which domains the page's own assets actually load
# from. A cloned phishing kit typically either hosts a full copy of the
# real site's logo/CSS/JS (same-origin, indistinguishable by this signal
# alone) or — very commonly, because it's less work — just hotlinks them
# straight from the real site. That second pattern (this page's HTML, but
# most of its assets pulled live from one specific other domain) is a
# strong, cheap tell that a URL-only or WHOIS/VirusTotal-only check has no
# way to see at all.
_ASSET_EXTRACT_JS = """
() => ({
    title: document.title || null,
    scripts: Array.from(document.querySelectorAll('script[src]')).map((s) => s.src).filter(Boolean),
    images: Array.from(document.querySelectorAll('img[src]')).map((i) => i.src).filter(Boolean),
    stylesheets: Array.from(document.querySelectorAll('link[rel="stylesheet"]')).map((l) => l.href).filter(Boolean),
})
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


def _summarize_assets(assets: dict, final_url: str) -> dict:
    """Turn the raw script/image/stylesheet URLs into origin-comparison
    facts — the actual list of asset URLs is noisy and rarely useful to
    the agent directly; whether they're same-origin vs. cross-origin, and
    especially whether most of them funnel through one specific foreign
    domain, is the signal that matters."""
    origin = urlparse(final_url).netloc
    all_urls = [*assets.get("scripts", []), *assets.get("images", []), *assets.get("stylesheets", [])]
    origins = [urlparse(u).netloc for u in all_urls if u]
    cross = [o for o in origins if o and o != origin]

    dominant_foreign = None
    if cross:
        from collections import Counter

        top_domain, top_count = Counter(cross).most_common(1)[0]
        # Require both a minimum count and a majority share — one stray
        # cross-origin analytics script shouldn't read the same as a page
        # whose logo/CSS/JS all come from somewhere else.
        if top_count >= 2 and top_count / len(cross) >= 0.5:
            dominant_foreign = {"domain": top_domain, "asset_count": top_count}

    return {
        "page_title": assets.get("title"),
        "asset_same_origin_count": len(origins) - len(cross),
        "asset_cross_origin_count": len(cross),
        "asset_dominant_foreign_origin": dominant_foreign,
    }


async def _get_deployment_info(response) -> dict:
    """Where and on what this page is actually served from — headers and
    the resolved server IP, neither of which a URL string or a WHOIS/
    VirusTotal domain lookup can show. The IP specifically is worth the
    agent's attention on its own: `domain_reputation` also accepts a raw
    IP (spec: network_flow cases already report bare destination IPs), so
    the agent can look up this exact hosting IP's own reputation the same
    way it would a domain."""
    try:
        headers = await response.all_headers()
    except Exception:  # noqa: BLE001 — headers are a bonus signal, never worth failing the whole tool over
        headers = {}
    try:
        server = await response.server_addr()
    except Exception:  # noqa: BLE001
        server = None
    return {
        "response_headers": headers,
        "server_ip": server.get("ipAddress") if server else None,
    }


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
    """Opens a URL in an isolated sandbox browser and reports what the page actually does — final destination after redirects, a screenshot, visible page text, any forms and where they submit to, every outbound network request, whether its scripts/images/stylesheets are hosted on this same domain or hotlinked from somewhere else (a page that visually matches a real brand but loads that brand's own assets live is a strong tell), and the responding server's HTTP headers and IP address. Use this first for almost any unknown link."""
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
                    "page_title": None,
                    "asset_same_origin_count": 0,
                    "asset_cross_origin_count": 0,
                    "asset_dominant_foreign_origin": None,
                    "response_headers": {},
                    "server_ip": None,
                }
                return _for_llm(full), full

            screenshot_bytes = await page.screenshot(type="png")
            page_text = await page.inner_text("body")
            forms = await page.eval_on_selector_all("form", _FORM_EXTRACT_JS)
            raw_links = await page.eval_on_selector_all("a", _LINK_EXTRACT_JS)
            links = _dedupe_links(raw_links, page.url, settings.SANDBOX_MAX_LINKS)
            redirect_chain = await _get_redirect_chain(response) if response else [{"url": url, "status": None}]
            raw_assets = await page.evaluate(_ASSET_EXTRACT_JS)
            asset_summary = _summarize_assets(raw_assets, page.url)
            deployment = await _get_deployment_info(response) if response else {"response_headers": {}, "server_ip": None}

            full = {
                "final_url": page.url,
                "status_code": response.status if response else None,
                "redirect_chain": redirect_chain,
                "screenshot_base64": base64.b64encode(screenshot_bytes).decode("ascii"),
                "page_text": page_text[: settings.SANDBOX_MAX_PAGE_TEXT_CHARS],
                "forms": forms,
                "links": links,
                "network_requests": network_requests,
                **asset_summary,
                **deployment,
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
            "page_title": None,
            "asset_same_origin_count": 0,
            "asset_cross_origin_count": 0,
            "asset_dominant_foreign_origin": None,
            "response_headers": {},
            "server_ip": None,
        }
        return _for_llm(full), full
    finally:
        if browser is not None:
            await browser.close()

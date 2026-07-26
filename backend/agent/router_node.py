"""
Router node — spec section 2's deterministic fast path.

For `case_type == "link"`, checks a static blocklist then a SQLite
cache keyed by URL (24h TTL) before ever calling the LLM. Email and
network_flow cases always fall through to the agent — there's no URL
to look up for an email, and a network case only reaches here after
Isolation Forest/TranAD already flagged it, so nothing to short-circuit.
"""
from __future__ import annotations

from agent.state import AgentState, Verdict
from cache.blocklist import is_blocklisted
from cache.sqlite_cache import get_cached_verdict
from logger import get_logger

logger = get_logger(__name__)


def router_node(state: AgentState) -> dict:
    if state["case_type"] != "link":
        return {}

    url = state["raw_input"]

    if is_blocklisted(url):
        logger.info("Router: %s matched the static blocklist", url)
        return {
            "verdict": Verdict(
                label="dangerous", confidence=1.0, reason="URL matches the static blocklist", mitigation=None
            )
        }

    cached = get_cached_verdict(url)
    if cached is not None:
        logger.info("Router: %s served from cache", url)
        return {"verdict": cached}

    return {}


def route_after_router(state: AgentState) -> str:
    """Conditional edge: straight to Output if the router already resolved the case, else on to the Agent."""
    return "output" if state.get("verdict") else "agent"

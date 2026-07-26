"""
Output node — spec section 2's deterministic finish line.

Parses the agent's final message into a `Verdict`, writes it to the
SQLite cache (link cases only — there's no stable key to cache an
email or network-flow verdict under), and attaches MITRE mitigation
text when `mitre_technique` is set (mitre/lookup.py — not yet built,
see that module for the current stub).
"""
from __future__ import annotations

import re

from agent.state import AgentState, Verdict
from cache.sqlite_cache import set_cached_verdict
from logger import get_logger

logger = get_logger(__name__)

_VERDICT_RE = re.compile(r"VERDICT:\s*(dangerous|suspicious|safe)", re.IGNORECASE)
_CONFIDENCE_RE = re.compile(r"CONFIDENCE:\s*([0-9.]+)")
# REASON stops right before ALTERNATIVES (if present) instead of running
# to the end of the message — the two fields are a matched pair with
# agent_node.py's prompt format; if REASON went to end-of-string it would
# swallow ALTERNATIVES whole.
_REASON_RE = re.compile(r"REASON:\s*(.+?)(?=\n\s*ALTERNATIVES:|\Z)", re.IGNORECASE | re.DOTALL)
_ALTERNATIVES_RE = re.compile(r"ALTERNATIVES:\s*(.+)", re.IGNORECASE | re.DOTALL)


def _parse_alternatives(text: str) -> list[dict]:
    match = _ALTERNATIVES_RE.search(text)
    if not match:
        return []

    raw = match.group(1).strip()
    if not raw or raw.lower().startswith("none"):
        return []

    alternatives = []
    for entry in raw.split("|"):
        entry = entry.strip()
        if not entry:
            continue
        # The prompt asks for "Title — URL"; fall back to a plain hyphen,
        # and to using the whole entry as both if the model didn't split it.
        for sep in ("—", " - "):
            if sep in entry:
                title, _, url = entry.partition(sep)
                break
        else:
            title, url = entry, entry
        title, url = title.strip(), url.strip()
        if url.startswith("http"):
            alternatives.append({"title": title or url, "url": url})
    return alternatives[:4]


def _parse_verdict(text: str) -> Verdict:
    label_match = _VERDICT_RE.search(text)
    confidence_match = _CONFIDENCE_RE.search(text)
    reason_match = _REASON_RE.search(text)
    alternatives = _parse_alternatives(text)

    if not label_match:
        logger.warning("Agent's final message didn't match the expected VERDICT format: %r", text[:200])
        return Verdict(
            label="suspicious",
            confidence=0.5,
            reason=text.strip() or "Agent gave no parsable verdict",
            mitigation=None,
            legitimate_alternatives=alternatives,
        )

    confidence = float(confidence_match.group(1)) if confidence_match else 0.5
    reason = reason_match.group(1).strip() if reason_match else text.strip()

    return Verdict(
        label=label_match.group(1).lower(),
        confidence=round(min(max(confidence, 0.0), 1.0), 4),
        reason=reason,
        mitigation=None,
        legitimate_alternatives=alternatives,
    )


def output_node(state: AgentState) -> dict:
    if state.get("verdict"):
        # Router already resolved this one (blocklist/cache hit) — nothing to parse.
        verdict = state["verdict"]
    else:
        last_message = state["messages"][-1]
        content = last_message.content if isinstance(last_message.content, str) else str(last_message.content)
        verdict = _parse_verdict(content)

        if state["case_type"] == "link":
            set_cached_verdict(state["raw_input"], verdict)

    mitre = state.get("mitre_technique")
    if mitre:
        from mitre.lookup import get_mitigation_text

        mitigation = get_mitigation_text(mitre["technique_id"])
        if mitigation:
            verdict = {**verdict, "mitigation": mitigation}

    return {"verdict": verdict}

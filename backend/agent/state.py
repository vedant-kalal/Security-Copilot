"""
Agent state shape (spec section 2).

This is the single object threaded through every node in the graph —
router -> agent -> tools -> output. Add a new field here (and nowhere
else) if a future node needs to carry new information through the loop.
"""
from __future__ import annotations

from typing import Annotated, Literal, Optional, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

CaseType = Literal["link", "email", "network_flow"]


class LegitimateAlternative(TypedDict):
    title: str
    url: str


class Verdict(TypedDict, total=False):
    label: Literal["dangerous", "suspicious", "safe"]
    confidence: float
    reason: str
    mitigation: Optional[str]
    # Populated via web_search when the agent suspects brand impersonation —
    # the real company's actual site(s), so the verdict can say "and here's
    # where you probably meant to go," not just "this is dangerous."
    legitimate_alternatives: list[LegitimateAlternative]


class AgentState(TypedDict):
    case_type: CaseType
    raw_input: str
    messages: Annotated[list[BaseMessage], add_messages]
    mitre_technique: Optional[dict]
    verdict: Optional[Verdict]
    # case_type == "email" only — links found in the email (regex-extracted
    # from the body text, plus real anchor hrefs when the caller has DOM
    # access, e.g. the extension popup), already deduped to one URL per
    # domain and capped (see utils.validators.dedupe_links_by_domain) so
    # the agent's per-link investigation work stays bounded. None/empty for
    # every other case type.
    email_links: Optional[list[str]]

"""
Groq chat model factory (spec sections 12/13, rescoped by the
security-copilot-poc-scope memory: Groq instead of Claude for this POC).

Kept as its own file so swapping the LLM provider later means editing
only this one file — nothing else in agent/ imports langchain_groq
directly.
"""
from __future__ import annotations

from functools import lru_cache


@lru_cache
def get_llm():
    """Return a process-wide singleton chat model, not yet bound to any tools (agent_node.py does that)."""
    from langchain_groq import ChatGroq

    from config import get_settings

    settings = get_settings()
    if not settings.GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Get a free key at https://console.groq.com/keys and add it to backend/.env"
        )
    return ChatGroq(model=settings.GROQ_MODEL, api_key=settings.GROQ_API_KEY, temperature=0)

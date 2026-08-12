"""
`recall_similar_cases` tool — searches past investigations for ones that
resemble the current case, by meaning rather than exact text match (see
memory/case_index.py). This is the tool that lets the agent generalize:
a brand-new domain using a trick structurally identical to one seen
before ("brand name folded into a longer domain on a cheap TLD," "assets
hotlinked from the real site," "form posts to an unrelated domain") can
still be recognized even though nothing about the literal URL or wording
matches anything on a blocklist or in VirusTotal's database yet.
"""
from __future__ import annotations

import asyncio

from langchain_core.tools import tool

# Aliased on import — the @tool-decorated function below has the same
# name (deliberately, it's the public tool name the agent sees), which
# would otherwise shadow this import at module scope and make the call
# inside the function body recurse into the tool wrapper instead of the
# real implementation.
from memory.case_index import recall_similar_cases as _recall_similar_cases


@tool
async def recall_similar_cases(description: str) -> dict:
    """Searches past investigations for cases that resemble this one in substance — a similar brand-impersonation pattern, similar page structure, similar hosting, similar evasion trick — even when the exact domain or wording has never been seen before. Describe what's notable about the current case (the domain, what the page does, any suspicious pattern you've noticed) as the input. Most useful when something feels like a variation on a known trick but doesn't cleanly match blocklist or reputation data on its own."""
    matches = await asyncio.to_thread(_recall_similar_cases, description)
    if not matches:
        return {"matches": [], "detail": "No sufficiently similar past investigations found."}
    return {"matches": matches}

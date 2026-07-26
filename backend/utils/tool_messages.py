"""
Extracts the full result dict from a ToolMessage, regardless of which
response format the tool used.

`inspect_website` uses `content_and_artifact` (its screenshot is too
large to put in `content` — see tools/inspect_website.py), so its full
result lives in `.artifact`. `domain_reputation` and `content_classifier`
are plain `@tool`-decorated functions with no artifact at all — their
full result is whatever they returned, JSON-serialized into `.content`
by LangChain. Recording/reporting code (cli.py, agent/graph.py) needs
the full result either way, so this is the one place that knows the
difference instead of guessing at each call site.
"""
from __future__ import annotations

import json
from typing import Any


def extract_full_result(msg: Any) -> dict:
    artifact = getattr(msg, "artifact", None)
    if isinstance(artifact, dict):
        return artifact

    content = getattr(msg, "content", None)
    if isinstance(content, dict):
        return content
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        return {"raw": content}

    return {}

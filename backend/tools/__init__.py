"""
The tools the agent binds and can call (spec section 4, plus
`web_search` added afterward — see that file's docstring).

Each tool is a plain async function decorated with `@tool` from
langchain_core — the decorator turns the function's docstring into the
description the LLM sees when deciding whether to call it, so those
docstrings are part of the agent's prompt, not just documentation.
Keep the original 3 worded per spec section 4 unless you have a good
reason to change them.

Add another tool by writing its own file here and adding it to
ALL_TOOLS below — nothing else needs to change.
"""
from tools.content_classifier import content_classifier
from tools.domain_reputation import domain_reputation
from tools.inspect_website import inspect_website
from tools.web_search import web_search

ALL_TOOLS = [inspect_website, domain_reputation, content_classifier, web_search]

__all__ = ["ALL_TOOLS", "inspect_website", "domain_reputation", "content_classifier", "web_search"]

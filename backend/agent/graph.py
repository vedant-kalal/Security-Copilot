"""
The LangGraph graph itself (spec section 2) — wires router, agent,
tools, and output into one state machine and compiles it. This is the
only file that should change if the graph's *shape* changes; every
node's actual logic lives in its own file (router_node.py,
agent_node.py, output_node.py) so this file stays a pure wiring diagram.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from langgraph.errors import GraphRecursionError
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from agent.agent_node import agent_node
from agent.output_node import output_node
from agent.router_node import route_after_router, router_node
from agent.state import AgentState, CaseType, Verdict
from config import get_settings
from exceptions import LLMRateLimitedError
from history import record_run
from logger import get_logger
from report import generate_report
from tools import ALL_TOOLS
from utils.screenshots import save_screenshot
from utils.tool_messages import extract_full_result

logger = get_logger(__name__)

INCONCLUSIVE_VERDICT = Verdict(
    label="suspicious",
    confidence=0.3,
    reason=(
        "The agent could not reach a confident verdict within its allowed number of "
        "investigation steps. Treat this as unresolved rather than cleared."
    ),
    mitigation=None,
)

# OpenRouter rate-limited the API key mid-investigation. Fail safe to a
# low-confidence "suspicious" verdict (never "safe") that names the reason,
# rather than propagating a raw exception to the caller.
RATE_LIMITED_VERDICT = Verdict(
    label="suspicious",
    confidence=0.3,
    reason=(
        "The investigation could not run because the LLM provider (OpenRouter) is temporarily "
        "rate-limiting this API key. This is a service limitation, not a judgment about the "
        "target — treat it as unresolved and re-run in a few moments."
    ),
    mitigation=None,
)


@lru_cache
def build_graph():
    """Compile and return a process-wide singleton graph app."""
    workflow = StateGraph(AgentState)
    workflow.add_node("router", router_node)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", ToolNode(ALL_TOOLS))
    workflow.add_node("output", output_node)

    workflow.set_entry_point("router")
    workflow.add_conditional_edges("router", route_after_router, {"output": "output", "agent": "agent"})
    workflow.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: "output"})
    workflow.add_edge("tools", "agent")  # the one unconditional edge in the graph (spec section 2)
    workflow.add_edge("output", END)

    return workflow.compile()


async def run_case(case_type: CaseType, raw_input: str, mitre_technique: Optional[dict] = None) -> dict:
    """Run one case through the graph end to end. Returns the final state's `verdict`.

    "Fails safely instead of looping forever" (spec section 2) means exactly
    that — a case that blows through AGENT_RECURSION_LIMIT without concluding
    comes back as a low-confidence "suspicious" verdict, not an unhandled
    exception. GraphRecursionError is the only exception caught here on
    purpose; anything else is a real bug and should still propagate.
    """
    graph = build_graph()
    settings = get_settings()

    try:
        result = await graph.ainvoke(
            {
                "case_type": case_type,
                "raw_input": raw_input,
                "messages": [],
                "mitre_technique": mitre_technique,
                "verdict": None,
            },
            config={"recursion_limit": settings.AGENT_RECURSION_LIMIT},
        )
        return result["verdict"]
    except GraphRecursionError:
        logger.warning("Case hit the recursion limit (%d) without concluding: %r", settings.AGENT_RECURSION_LIMIT, raw_input)
        return dict(INCONCLUSIVE_VERDICT)
    except LLMRateLimitedError:
        logger.warning("Case could not run — OpenRouter rate-limited: %r", raw_input)
        return dict(RATE_LIMITED_VERDICT)


# Friendly, human-readable labels for what the agent is actually doing —
# shown live in the extension's banner/popup while a full check runs
# (spec: users watching a 10-40s investigation should see *what* it's
# doing, not just a static "Investigating..." spinner). Keyed by tool
# name; inspect_website gets a different label on repeat calls since a
# second call means the agent chose to follow a link it found suspicious
# on the first page (spec section 4.1 / inspect_website.py's docstring).
_TOOL_LABELS = {
    "domain_reputation": "Checking VirusTotal & domain registration history...",
    "content_classifier": "Analyzing the page for phishing patterns...",
    "web_search": "Searching the web for the real, legitimate site...",
}


def _friendly_step(tool_name: str, call_number: int) -> str:
    if tool_name == "inspect_website":
        return (
            "Opening the page in a sandboxed browser & taking a screenshot..."
            if call_number == 1
            else "Exploring another page found on the site..."
        )
    return _TOOL_LABELS.get(tool_name, f"Running {tool_name}...")


async def stream_case_traced(case_type: CaseType, raw_input: str, mitre_technique: Optional[dict] = None):
    """Same investigation as `run_case_traced` below, but as an async
    generator that yields a `{"type": "progress", "label": ...}` event
    after every step instead of only returning once at the very end —
    what api/routes_check_links_stream.py's SSE endpoint forwards to the
    extension so its "Full report" flow can show live progress instead of
    a static spinner for however long the real investigation takes.

    This *is* the implementation now — `run_case_traced` just consumes it
    and returns the final `{"type": "done", ...}` event's payload, so the
    two can never drift out of sync with each other.

    Ends with exactly one `{"type": "done", "verdict": ..., "run_id": ...,
    "report_path": ...}` event.
    """
    graph = build_graph()
    settings = get_settings()

    initial_state = {
        "case_type": case_type,
        "raw_input": raw_input,
        "messages": [],
        "mitre_technique": mitre_technique,
        "verdict": None,
    }

    tool_call_records: list[dict] = []
    pending_calls: list[dict] = []
    verdict: Optional[dict] = None
    call_counts: dict[str, int] = {}

    yield {"type": "progress", "label": "Starting investigation..."}

    try:
        async for step in graph.astream(
            initial_state, config={"recursion_limit": settings.AGENT_RECURSION_LIMIT}, stream_mode="updates"
        ):
            for node_name, update in step.items():
                update = update or {}

                if node_name == "agent":
                    last = update["messages"][-1]
                    tool_calls = getattr(last, "tool_calls", None)
                    pending_calls = tool_calls if tool_calls else []
                    # Announced as soon as the agent decides to call them —
                    # before the (possibly slow) call actually finishes —
                    # so the label reflects what's happening *right now*.
                    for call in pending_calls:
                        call_counts[call["name"]] = call_counts.get(call["name"], 0) + 1
                        yield {"type": "progress", "label": _friendly_step(call["name"], call_counts[call["name"]])}

                elif node_name == "tools":
                    for i, msg in enumerate(update["messages"]):
                        full_result = extract_full_result(msg)
                        screenshot_path = save_screenshot(full_result)
                        call_info = (
                            pending_calls[i] if i < len(pending_calls) else {"name": getattr(msg, "name", "?"), "args": {}}
                        )
                        tool_call_records.append(
                            {
                                "tool": call_info["name"],
                                "args": call_info["args"],
                                "artifact": full_result,
                                "screenshot_path": screenshot_path,
                            }
                        )
                    pending_calls = []

                elif node_name == "output":
                    verdict = update["verdict"]
    except GraphRecursionError:
        logger.warning("Case hit the recursion limit (%d) without concluding: %r", settings.AGENT_RECURSION_LIMIT, raw_input)
        verdict = dict(INCONCLUSIVE_VERDICT)
    except LLMRateLimitedError:
        logger.warning("Case could not run — OpenRouter rate-limited: %r", raw_input)
        verdict = dict(RATE_LIMITED_VERDICT)

    yield {"type": "progress", "label": "Finalizing the verdict & saving the report..."}
    report_path = generate_report(case_type, raw_input, tool_call_records, verdict)
    run_id = record_run(case_type, raw_input, tool_call_records, verdict, report_path)

    yield {"type": "done", "verdict": verdict, "run_id": run_id, "report_path": report_path}


async def run_case_traced(case_type: CaseType, raw_input: str, mitre_technique: Optional[dict] = None) -> dict:
    """Same as `run_case`, but captures every tool call along the way (not
    just the final verdict) and records the whole thing as one entry in
    history.py + report.py — this is what the API and cli.py both use so
    every run, from either path, shows up in the UI's history list.

    Returns {"verdict": ..., "run_id": ..., "report_path": ...}. See
    `stream_case_traced` above for the actual step-by-step implementation
    — this just drains it and keeps the final result.
    """
    async for event in stream_case_traced(case_type, raw_input, mitre_technique):
        if event["type"] == "done":
            return {"verdict": event["verdict"], "run_id": event["run_id"], "report_path": event["report_path"]}
    raise RuntimeError("stream_case_traced ended without a 'done' event")  # unreachable

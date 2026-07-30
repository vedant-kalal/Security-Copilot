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
from exceptions import AllKeysRateLimitedError
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

# When every OpenRouter key is throttled, an in-flight case can't be investigated
# at all. Fail safe to a low-confidence "suspicious" verdict (never "safe") that
# names the reason, rather than propagating a raw exception to the caller.
RATE_LIMITED_VERDICT = Verdict(
    label="suspicious",
    confidence=0.3,
    reason=(
        "The investigation could not run because all of the LLM provider's API keys are "
        "temporarily rate-limited. This is a service limitation, not a judgment about the "
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
    except AllKeysRateLimitedError:
        logger.warning("Case could not run — all LLM API keys rate-limited: %r", raw_input)
        return dict(RATE_LIMITED_VERDICT)


async def run_case_traced(case_type: CaseType, raw_input: str, mitre_technique: Optional[dict] = None) -> dict:
    """Same as `run_case`, but captures every tool call along the way (not
    just the final verdict) and records the whole thing as one entry in
    history.py + report.py — this is what the API and cli.py both use so
    every run, from either path, shows up in the UI's history list.

    Returns {"verdict": ..., "run_id": ..., "report_path": ...}.
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
    except AllKeysRateLimitedError:
        logger.warning("Case could not run — all LLM API keys rate-limited: %r", raw_input)
        verdict = dict(RATE_LIMITED_VERDICT)

    report_path = generate_report(case_type, raw_input, tool_call_records, verdict)
    run_id = record_run(case_type, raw_input, tool_call_records, verdict, report_path)

    return {"verdict": verdict, "run_id": run_id, "report_path": report_path}

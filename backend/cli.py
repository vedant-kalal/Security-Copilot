"""
Terminal harness — run a link or email case through the agent and
watch every tool call and the final verdict print live, no API server
or Chrome extension required (see security-copilot-poc-scope memory:
terminal-first for the POC).

Every run also writes a full markdown report (verdict + every tool call,
screenshot, redirect chain — see report.py) so the evidence survives
after the terminal scrolls past it.

Usage:
    python cli.py link https://example.com/login
    python cli.py email
        (then paste the email/page text, end with Ctrl-D / Ctrl-Z+Enter on Windows)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from langgraph.errors import GraphRecursionError

from agent.graph import build_graph
from config import get_settings
from history import record_run
from logger import configure_logging
from report import generate_report
from utils.screenshots import save_screenshot
from utils.tool_messages import extract_full_result


async def _run(case_type: str, raw_input: str) -> None:
    configure_logging()
    graph = build_graph()
    settings = get_settings()

    initial_state = {
        "case_type": case_type,
        "raw_input": raw_input,
        "messages": [],
        "mitre_technique": None,
        "verdict": None,
    }

    tool_call_records: list[dict] = []
    pending_calls: list[dict] = []
    verdict: dict | None = None

    try:
        async for step in graph.astream(
            initial_state, config={"recursion_limit": settings.AGENT_RECURSION_LIMIT}, stream_mode="updates"
        ):
            for node_name, update in step.items():
                # In "updates" stream mode, LangGraph reports a node that
                # returned an empty dict (no state change — e.g. the router
                # finding no fast-path match) as None rather than {}.
                update = update or {}
                print(f"\n--- {node_name} ---")

                if node_name == "router":
                    if update.get("verdict"):
                        print(f"  resolved by fast path (blocklist/cache): {update['verdict']}")
                    else:
                        print("  no fast-path match — escalating to the agent")

                elif node_name == "agent":
                    last = update["messages"][-1]
                    tool_calls = getattr(last, "tool_calls", None)
                    if tool_calls:
                        pending_calls = tool_calls
                        for call in tool_calls:
                            print(f"  -> calling tool: {call['name']}({call['args']})")
                    else:
                        pending_calls = []
                        print(f"  final response:\n{last.content}")

                elif node_name == "tools":
                    for i, msg in enumerate(update["messages"]):
                        content = str(msg.content)
                        preview = content if len(content) < 500 else content[:500] + "... (truncated)"
                        print(f"  <- tool result ({getattr(msg, 'name', '?')}): {preview}")

                        full_result = extract_full_result(msg)
                        screenshot_path = save_screenshot(full_result)
                        if screenshot_path:
                            print(f"     screenshot saved: {screenshot_path}")

                        call_info = pending_calls[i] if i < len(pending_calls) else {"name": getattr(msg, "name", "?"), "args": {}}
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
                    print(f"  VERDICT:\n{json.dumps(verdict, indent=2)}")
    except GraphRecursionError:
        print(f"\n--- inconclusive ---\n  Hit the recursion limit ({settings.AGENT_RECURSION_LIMIT} steps) without the agent reaching a final verdict.")

    report_path = generate_report(case_type, raw_input, tool_call_records, verdict)
    record_run(case_type, raw_input, tool_call_records, verdict, report_path)
    print(f"\nFull report saved: {report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a case through the security-copilot agent from the terminal.")
    parser.add_argument("case_type", choices=["link", "email"], help="What kind of case to investigate")
    parser.add_argument("input", nargs="?", help="The URL to check (for 'link'). Omit for 'email' to read from stdin.")
    args = parser.parse_args()

    if args.case_type == "link":
        if not args.input:
            parser.error("'link' requires a URL argument")
        raw_input = args.input
    else:
        print("Paste the email/page text, then press Ctrl-D (Ctrl-Z+Enter on Windows) when done:")
        raw_input = sys.stdin.read()

    asyncio.run(_run(args.case_type, raw_input))


if __name__ == "__main__":
    main()

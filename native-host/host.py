"""
Native messaging host (spec section 9) — NOT YET BUILT.

Chrome extensions cannot read OS-level network connections directly;
this is the separate native process that bridges that gap. Plan:

  1. Run `network.flow_collector.collect_flows()` and
     `network.isolation_forest`'s scorer (later also `network.tranad`)
     in a background loop.
  2. Speak Chrome's native messaging protocol (length-prefixed JSON
     over stdin/stdout) to push anomaly events to the extension's
     background script as they're escalated and resolved by the agent
     (i.e. after a POST to the backend's /report-flow, spec section 10).

Deferred per security-copilot-poc-scope memory (terminal-first for the
POC) and spec section 15, build order step 9 — comes after the network
anomaly pipeline (step 8) is working.
"""
from __future__ import annotations


def main() -> None:
    raise NotImplementedError(
        "The native messaging host is not yet implemented — see this file's module docstring for the plan "
        "(spec section 9)."
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Phase 9 — staged network-anomaly trigger.

Generates an anomalous-looking flow on cue so the network path can be
demoed live without waiting for real traffic to do something interesting.
Two modes:

  live  (default) — rapidly opens a burst of short-lived outbound TCP
                    connections to many ports on a target host. Most ports
                    are closed, so the connections fail/reset — producing a
                    window with high connection_count, unique_port_count and
                    failed_reset_ratio. Run the native helper
                    (`python native-host/host.py`) at the same time; its
                    collector will pick this burst up, score it anomalous,
                    and POST it to /report-flow.

  post           — skips traffic generation and POSTs one hand-crafted
                    anomalous flow straight to /report-flow. A guaranteed,
                    zero-timing-risk trigger for the demo.

Examples:
    python scripts/staged_flow_trigger.py live --target 198.51.100.10 --ports 200
    python scripts/staged_flow_trigger.py post --backend-url http://127.0.0.1:8010
"""
from __future__ import annotations

import argparse
import socket
import sys
import time


def run_live(target: str, base_port: int, ports: int, connect_timeout: float) -> None:
    print(f"Opening a burst of {ports} outbound connections to {target}:{base_port}..{base_port + ports - 1} …")
    opened = 0
    for offset in range(ports):
        port = base_port + offset
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setblocking(False)
        try:
            # Non-blocking connect: fires the SYN and moves on, so the collector
            # sees many simultaneous half-open/failed connections in one window.
            sock.connect_ex((target, port))
            opened += 1
        except OSError:
            pass
        # Keep the sockets briefly alive so a poll catches them, then move on.
        if offset % 50 == 0:
            time.sleep(0.05)
    print(f"Fired {opened} connection attempts. Give the collector one window (~60s) to aggregate and score them.")
    # Hold the process a moment so the sockets linger into a collector poll.
    time.sleep(connect_timeout)


def run_post(backend_url: str) -> None:
    import httpx

    payload = {
        "destination": "198.51.100.10",  # TEST-NET-2, guaranteed non-routable
        "port": 4444,
        "protocol": "tcp",
        "process_name": "staged_trigger_demo",
        "anomaly_score": 0.82,
        "context": (
            "Staged demo anomaly: 480 connections to 190 destinations across 150 ports in one 60s window, "
            "failed/reset ratio 0.55, repeated short connections to an unfamiliar host on port 4444 — "
            "resembles command-and-control beaconing / scanning."
        ),
    }
    url = f"{backend_url.rstrip('/')}/report-flow"
    print(f"POSTing staged anomalous flow to {url} …")
    response = httpx.post(url, json=payload, timeout=120.0)
    response.raise_for_status()
    verdict = response.json()
    print("Verdict:")
    for key in ("label", "confidence", "reason", "mitigation", "run_id"):
        if verdict.get(key):
            print(f"  {key}: {verdict[key]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Staged network-anomaly trigger for demos (Phase 9).")
    sub = parser.add_subparsers(dest="mode")

    live = sub.add_parser("live", help="Generate a real burst of failed outbound connections.")
    live.add_argument("--target", default="198.51.100.10", help="Target host (default TEST-NET, non-routable).")
    live.add_argument("--base-port", type=int, default=20000)
    live.add_argument("--ports", type=int, default=200, help="Number of consecutive ports to hit.")
    live.add_argument("--linger", type=float, default=3.0, help="Seconds to keep sockets open after firing.")

    post = sub.add_parser("post", help="POST one hand-crafted anomalous flow to /report-flow.")
    post.add_argument("--backend-url", default="http://127.0.0.1:8010")

    args = parser.parse_args()
    mode = args.mode or "live"

    if mode == "live":
        run_live(args.target, args.base_port, args.ports, args.linger)
    elif mode == "post":
        run_post(args.backend_url)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

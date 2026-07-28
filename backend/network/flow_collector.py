"""
psutil-based network flow capture (spec section 5.1).

Polls `psutil.net_connections(kind='inet')` on a short timer (default 2s),
diffs each snapshot against the previous one to find newly-appeared
connections, and attributes each to its owning process via
`psutil.Process(pid).name()`. Connections are accumulated over a rolling
60-second window; when the window closes the collector emits one feature
vector describing that window's traffic.

Emitted per window (see `network/feature_engineering.py`'s
`extract_window_features` for the canonical order the model reads):
  - connection_count        — distinct connections observed in the window
  - unique_destination_count
  - unique_port_count
  - failed_reset_ratio      — share of connections left in a failed/reset-ish
                              TCP state (SYN_SENT that never established, CLOSE,
                              CLOSE_WAIT, …) — psutil can't see RST directly, so
                              this is the closest metadata-only proxy
  - hour_sin, hour_cos      — cyclical time-of-day encoding of the window
  - proto_tcp, proto_udp    — share of connections per L4 protocol (soft one-hot)

Alongside the features, each window carries a `meta` block (window bounds,
the most-active destination/port/protocol/process) so downstream callers
(native-host/host.py) have something concrete to report to `/report-flow`
without ever needing packet contents.

CONNECTION METADATA ONLY — never packet payloads/content (spec section 14,
non-negotiable). psutil surfaces addresses, ports, states and owning PIDs;
this module never reads a single byte of any payload.
"""
from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, Iterator, Optional

from config import get_settings
from logger import get_logger

logger = get_logger(__name__)

# TCP states that indicate a connection that failed to establish, was reset, or
# is tearing down abnormally. Used as the numerator of failed_reset_ratio. A
# healthy established connection sits in ESTABLISHED; anything stuck mid-handshake
# (SYN_SENT/SYN_RECV) or closing is treated as a "failed/reset-ish" observation.
_FAILED_STATUSES = frozenset(
    {"SYN_SENT", "SYN_RECV", "FIN_WAIT1", "FIN_WAIT2", "CLOSE_WAIT", "CLOSING", "LAST_ACK", "CLOSE"}
)


def _process_name(pid: Optional[int], cache: Dict[int, str]) -> str:
    """Resolve a PID to a process name, tolerating races where it already exited."""
    if not pid:
        return "unknown"
    if pid in cache:
        return cache[pid]
    import psutil

    try:
        name = psutil.Process(pid).name() or "unknown"
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        name = "unknown"
    except Exception:  # noqa: BLE001 — never let a name lookup crash the collector
        name = "unknown"
    cache[pid] = name
    return name


def _conn_key(conn) -> tuple:
    """Stable identity for a connection so we can diff snapshots poll-to-poll."""
    laddr = (conn.laddr.ip, conn.laddr.port) if conn.laddr else ("", 0)
    raddr = (conn.raddr.ip, conn.raddr.port) if conn.raddr else ("", 0)
    return (conn.pid, conn.type, laddr, raddr)


def _protocol_name(conn) -> str:
    import socket

    if conn.type == socket.SOCK_STREAM:
        return "tcp"
    if conn.type == socket.SOCK_DGRAM:
        return "udp"
    return "other"


class _WindowAccumulator:
    """Collects per-connection observations across polls within one window."""

    def __init__(self) -> None:
        # conn_key -> last observed record for that connection this window
        self.records: Dict[tuple, dict] = {}
        self.new_connection_count = 0

    def observe(self, conn, process_name: str, is_new: bool) -> None:
        key = _conn_key(conn)
        if is_new:
            self.new_connection_count += 1
        self.records[key] = {
            "dest_ip": conn.raddr.ip if conn.raddr else "",
            "dest_port": conn.raddr.port if conn.raddr else 0,
            "protocol": _protocol_name(conn),
            "process": process_name,
            "status": conn.status,
        }

    def is_empty(self) -> bool:
        return not self.records

    def to_feature_vector(self, window_start: datetime, window_end: datetime) -> dict:
        records = list(self.records.values())
        total = len(records)

        dest_ips = [r["dest_ip"] for r in records if r["dest_ip"]]
        dest_ports = [r["dest_port"] for r in records if r["dest_port"]]
        protocols = [r["protocol"] for r in records]
        processes = [r["process"] for r in records]

        failed = sum(1 for r in records if r["status"] in _FAILED_STATUSES)
        tcp = sum(1 for p in protocols if p == "tcp")
        udp = sum(1 for p in protocols if p == "udp")

        # Cyclical hour-of-day encoding of the window's midpoint.
        mid = window_start + (window_end - window_start) / 2
        hour = mid.hour + mid.minute / 60.0
        angle = 2.0 * math.pi * hour / 24.0

        def _most_common(items, default):
            return Counter(items).most_common(1)[0][0] if items else default

        top_dest = _most_common(dest_ips, "")
        # Report the port/protocol/process most associated with the top destination.
        for_dest = [r for r in records if r["dest_ip"] == top_dest] or records
        top_port = _most_common([r["dest_port"] for r in for_dest if r["dest_port"]], 0)
        top_proto = _most_common([r["protocol"] for r in for_dest], "tcp")
        top_process = _most_common([r["process"] for r in for_dest], "unknown")

        return {
            # --- feature vector (see feature_engineering.extract_window_features) ---
            "connection_count": total,
            "unique_destination_count": len(set(dest_ips)),
            "unique_port_count": len(set(dest_ports)),
            "failed_reset_ratio": round(failed / total, 4) if total else 0.0,
            "hour_sin": round(math.sin(angle), 6),
            "hour_cos": round(math.cos(angle), 6),
            "proto_tcp": round(tcp / total, 4) if total else 0.0,
            "proto_udp": round(udp / total, 4) if total else 0.0,
            # --- metadata for reporting / the agent (never payloads) ---
            "meta": {
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "new_connection_count": self.new_connection_count,
                "destination": top_dest or "unknown",
                "port": top_port,
                "protocol": top_proto,
                "process_name": top_process,
                "unique_processes": sorted(set(processes)),
            },
        }


def collect_flows(
    poll_interval: Optional[float] = None,
    window_seconds: Optional[float] = None,
    max_windows: Optional[int] = None,
) -> Iterator[dict]:
    """Yield one windowed feature-vector dict per `window_seconds` of live traffic.

    Runs forever by default; pass `max_windows` to stop after N windows (useful
    for standalone testing). Poll interval and window length default to
    `config.py`'s FLOW_POLL_INTERVAL_SECONDS / FLOW_WINDOW_SECONDS.
    """
    import time

    import psutil

    settings = get_settings()
    poll_interval = poll_interval if poll_interval is not None else settings.FLOW_POLL_INTERVAL_SECONDS
    window_seconds = window_seconds if window_seconds is not None else settings.FLOW_WINDOW_SECONDS

    prev_keys: set[tuple] = set()
    pid_name_cache: Dict[int, str] = {}
    accumulator = _WindowAccumulator()
    window_start = datetime.now(timezone.utc)
    windows_emitted = 0

    logger.info(
        "Flow collector started (poll=%.1fs, window=%.0fs, metadata only, no payloads)",
        poll_interval,
        window_seconds,
    )

    while True:
        try:
            conns = psutil.net_connections(kind="inet")
        except (psutil.AccessDenied, PermissionError):
            # On some OSes net_connections needs elevation for other users' sockets;
            # keep going with whatever we can see rather than crashing the loop.
            logger.warning("net_connections access denied — some sockets may be invisible without elevation")
            conns = []

        # Only connections with a remote address are outbound "flows" worth modeling;
        # bare LISTENers have no destination.
        current_keys: set[tuple] = set()
        for conn in conns:
            if not conn.raddr:
                continue
            key = _conn_key(conn)
            current_keys.add(key)
            accumulator.observe(conn, _process_name(conn.pid, pid_name_cache), is_new=key not in prev_keys)

        prev_keys = current_keys

        now = datetime.now(timezone.utc)
        if (now - window_start).total_seconds() >= window_seconds:
            if not accumulator.is_empty():
                yield accumulator.to_feature_vector(window_start, now)
                windows_emitted += 1
            else:
                logger.debug("Window closed with no outbound connections observed; skipping emit")
            accumulator = _WindowAccumulator()
            window_start = now
            pid_name_cache.clear()  # let long-lived pids refresh occasionally

            if max_windows is not None and windows_emitted >= max_windows:
                return

        time.sleep(poll_interval)


if __name__ == "__main__":  # pragma: no cover — standalone smoke test (Phase 2 "Done when")
    import argparse
    import json

    from logger import configure_logging

    configure_logging()

    parser = argparse.ArgumentParser(description="Run the flow collector standalone and print feature windows.")
    parser.add_argument("--window", type=float, default=10.0, help="Window length in seconds (default 10 for testing)")
    parser.add_argument("--poll", type=float, default=1.0, help="Poll interval in seconds")
    parser.add_argument("--count", type=int, default=5, help="Number of windows to emit before exiting")
    args = parser.parse_args()

    for window in collect_flows(poll_interval=args.poll, window_seconds=args.window, max_windows=args.count):
        print(json.dumps(window, indent=2))

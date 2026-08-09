#!/usr/bin/env python3
"""
Aggregate a CICIDS2017-style per-flow CSV into 60-second windowed features —
the same shape `network/flow_collector.py` emits from live traffic, so a
labeled dataset can be used to train/evaluate the *windowed* models
(Isolation Forest --feature-set window, and TranAD), not just the per-row
Isolation Forest.

Per-flow datasets have no direct equivalent of "connections observed on this
host in this 60s window" — this script reconstructs it by bucketing flows
into fixed windows by their start Timestamp and computing the same
aggregates `_WindowAccumulator.to_feature_vector` computes live:
  - connection_count        = flows starting in the window
  - unique_destination_count = distinct Destination IP
  - unique_port_count        = distinct Destination Port
  - failed_reset_ratio       = share of flows with RST Flag Count > 0
                                (a direct signal here, vs. the live collector's
                                TCP-state proxy — flow exports carry the flag
                                counts psutil can't see)
  - hour_sin, hour_cos       = cyclical encoding of the window's midpoint
  - proto_tcp, proto_udp     = share of flows on protocol 6 / 17

Also emits an `attack` column (1 if any flow in the window is non-BENIGN) so
the output can be used both to train (feed only benign-day output) and to
evaluate (feed an attack-day output and check recall against this column).

Usage:
    python scripts/aggregate_flows_to_windows.py --input day.csv --output windows.csv
    python scripts/aggregate_flows_to_windows.py --input day.csv --output windows.csv --window 60
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime, timedelta
from math import cos, pi, sin
from pathlib import Path


_TIMESTAMP_FORMATS = (
    "%d/%m/%Y %H:%M:%S",  # Monday: "03/07/2017 08:55:58"
    "%d/%m/%Y %H:%M",     # Other days: "7/7/2017 3:30" (no seconds)
)


def _parse_timestamp(raw: str) -> datetime:
    raw = raw.strip()
    for fmt in _TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unrecognized timestamp format: {raw!r}")


def _coerce_int(value: str, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def aggregate(input_path: Path, window_seconds: float) -> list[dict]:
    buckets: dict[int, list[dict]] = defaultdict(list)
    with input_path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames:
            reader.fieldnames = [name.strip() for name in reader.fieldnames]
        for row in reader:
            ts_raw = row.get("Timestamp")
            if not ts_raw:
                continue
            try:
                ts = _parse_timestamp(ts_raw)
            except ValueError:
                continue
            bucket_key = int(ts.timestamp() // window_seconds)
            buckets[bucket_key].append(row)

    windows = []
    for bucket_key in sorted(buckets):
        rows = buckets[bucket_key]
        total = len(rows)
        window_start = datetime.fromtimestamp(bucket_key * window_seconds)
        window_end = window_start + timedelta(seconds=window_seconds)
        mid = window_start + (window_end - window_start) / 2
        hour = mid.hour + mid.minute / 60.0
        angle = 2.0 * pi * hour / 24.0

        dest_ips = {r.get("Destination IP", "") for r in rows if r.get("Destination IP")}
        dest_ports = {r.get("Destination Port", "") for r in rows if r.get("Destination Port")}
        failed = sum(1 for r in rows if _coerce_int(r.get("RST Flag Count", "0")) > 0)
        tcp = sum(1 for r in rows if r.get("Protocol") == "6")
        udp = sum(1 for r in rows if r.get("Protocol") == "17")
        attack = any(r.get("Label", "BENIGN") not in ("BENIGN", "") for r in rows)
        n_attack_flows = sum(1 for r in rows if r.get("Label", "BENIGN") not in ("BENIGN", ""))

        windows.append({
            "window_start": window_start.isoformat(),
            "connection_count": total,
            "unique_destination_count": len(dest_ips),
            "unique_port_count": len(dest_ports),
            "failed_reset_ratio": round(failed / total, 4) if total else 0.0,
            "hour_sin": round(sin(angle), 6),
            "hour_cos": round(cos(angle), 6),
            "proto_tcp": round(tcp / total, 4) if total else 0.0,
            "proto_udp": round(udp / total, 4) if total else 0.0,
            "attack": int(attack),
            "n_flows": total,
            "n_attack_flows": n_attack_flows,
        })
    return windows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="CICIDS2017-style per-flow CSV")
    parser.add_argument("--output", type=Path, required=True, help="Output windowed-features CSV")
    parser.add_argument("--window", type=float, default=60.0, help="Window length in seconds (default 60, matches FLOW_WINDOW_SECONDS)")
    args = parser.parse_args()

    windows = aggregate(args.input, args.window)
    if not windows:
        raise SystemExit(f"No windows produced from {args.input} — check the Timestamp column exists and parses.")

    fieldnames = list(windows[0].keys())
    with args.output.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(windows)

    n_attack_windows = sum(w["attack"] for w in windows)
    print(f"Wrote {len(windows)} windows ({args.window:g}s each) -> {args.output}")
    print(f"  {n_attack_windows} windows contain at least one attack-labeled flow ({100*n_attack_windows/len(windows):.1f}%)")


if __name__ == "__main__":
    main()

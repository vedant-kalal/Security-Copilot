#!/usr/bin/env python3
"""
Phase 9 — replay fallback.

Feeds a couple of pre-recorded CICIDS2017 attack flows through the live
pipeline, so the network-anomaly demo has a zero-risk backup if the staged
live trigger has any timing hiccup. Each selected attack row is scored with
the (csv) Isolation Forest for a real anomaly score, then POSTed to the
backend's /report-flow endpoint exactly as the native helper would — the
agent investigates it and returns a verdict that lands in the UI history.

Examples:
    python scripts/replay_attack_flow.py
    python scripts/replay_attack_flow.py --label DDoS --count 1 --backend-url http://127.0.0.1:8010
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

DEFAULT_CSV = BACKEND_DIR / "data" / "network_datasets" / "cicids2017_sample.csv"


def _label_col(fieldnames) -> str:
    return next((c for c in fieldnames or [] if c.lower() in ("label", "attack_cat")), "Label")


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay pre-recorded CICIDS2017 attack flows through /report-flow.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--label", default=None, help="Only replay rows with this attack label (default: any non-benign).")
    parser.add_argument("--count", type=int, default=2, help="How many attack rows to replay.")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8010")
    parser.add_argument("--score-only", action="store_true", help="Score locally and print; do not POST.")
    args = parser.parse_args()

    # Import after sys.path is set; run from backend so model paths resolve.
    import os

    os.chdir(BACKEND_DIR)
    from network.isolation_forest import get_anomaly_detector

    detector = get_anomaly_detector("csv")
    benign = {"BENIGN", "benign", "0"}

    with args.csv.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        label_col = _label_col(reader.fieldnames)
        rows = [r for r in reader if r.get(label_col, "").strip() not in benign]

    if args.label:
        rows = [r for r in rows if r.get(label_col, "").strip() == args.label]
    rows = rows[: args.count]

    if not rows:
        print("No matching attack rows found to replay.")
        sys.exit(1)

    for row in rows:
        label = row.get(label_col, "attack").strip()
        prediction = detector.predict(row)
        port = int(float(row.get("Destination Port", 0) or 0))
        payload = {
            "destination": f"replayed-{label.lower()}-flow.test",
            "port": port or None,
            "protocol": "tcp",
            "process_name": "cicids2017_replay",
            "anomaly_score": prediction.anomaly_score,
            "context": (
                f"Replayed CICIDS2017 '{label}' flow. Isolation Forest anomaly score "
                f"{prediction.anomaly_score} vs threshold {prediction.threshold} "
                f"(top features: {', '.join(prediction.top_contributing_features)})."
            ),
        }

        if args.score_only:
            print(f"[{label}] score={prediction.anomaly_score} flagged={prediction.is_anomaly} -> {payload['context']}")
            continue

        import httpx

        url = f"{args.backend_url.rstrip('/')}/report-flow"
        print(f"[{label}] POSTing to {url} (score {prediction.anomaly_score}) …")
        response = httpx.post(url, json=payload, timeout=120.0)
        response.raise_for_status()
        verdict = response.json()
        print(f"  verdict={verdict.get('label')} confidence={verdict.get('confidence')} run_id={verdict.get('run_id')}")


if __name__ == "__main__":
    main()

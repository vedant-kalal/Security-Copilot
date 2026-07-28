"""
Native helper (Phase 4) — a standalone, long-running Python process that
watches this machine's network flows and escalates anomalies to the
backend over plain HTTP.

This deliberately does NOT use Chrome's native-messaging protocol (no
length-prefixed stdin/stdout, no manifest/registry registration). It talks
to the backend exactly the way the extension does — an ordinary POST — so
there is no OS-specific installer to maintain. The old native-messaging
files (`com.securitycopilot.host.json`, `install.sh`, `install.ps1`)
describe the abandoned approach and are not used here.

Loop:
  1. `network.flow_collector.collect_flows()` yields one feature vector per
     60-second window (connection metadata only — never payloads).
  2. Score each window with the "window" Isolation Forest
     (`network.isolation_forest`), which loads its persisted percentile
     threshold.
  3. If the anomaly score crosses that threshold, POST the flow's
     destination/port/protocol/process to the backend's `/report-flow`
     endpoint and log the returned verdict. Below threshold: log locally,
     no network call.

Run it alongside the backend:
    python native-host/host.py
The extension never talks to this process directly.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# This script lives outside backend/, but reuses the backend's collector and
# model. Put backend/ on the path so those imports resolve when run directly.
REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from logger import configure_logging, get_logger  # noqa: E402
from network.feature_engineering import extract_window_features  # noqa: E402
from network.flow_collector import collect_flows  # noqa: E402
from network.isolation_forest import get_anomaly_detector  # noqa: E402
from network.tranad import get_tranad_detector  # noqa: E402

logger = get_logger("native_host")

DEFAULT_BACKEND_URL = os.environ.get("NATIVE_HOST_BACKEND_URL", "http://127.0.0.1:8000")
REPORT_TIMEOUT_SECONDS = 60.0  # the agent investigation behind /report-flow can take a while


def _report_flow(backend_url: str, window: dict, if_pred, tad_pred, flagged_by: list) -> None:
    """POST one escalated window to the backend and log the resulting verdict."""
    import httpx

    meta = window.get("meta", {})
    detail = (
        f"Isolation Forest score {if_pred.anomaly_score} vs threshold {if_pred.threshold} "
        f"(top features: {', '.join(if_pred.top_contributing_features)}); "
        f"TranAD temporal score {tad_pred.anomaly_score} vs threshold {tad_pred.threshold}."
    )
    payload = {
        "destination": meta.get("destination", "unknown"),
        "port": meta.get("port") or None,
        "protocol": meta.get("protocol"),
        "process_name": meta.get("process_name"),
        "anomaly_score": if_pred.anomaly_score,
        "context": (
            f"Windowed anomaly flagged by {', '.join(flagged_by)}: "
            f"{window.get('connection_count')} connections to "
            f"{window.get('unique_destination_count')} destinations across "
            f"{window.get('unique_port_count')} ports, "
            f"failed/reset ratio {window.get('failed_reset_ratio')}. {detail}"
        ),
    }

    url = f"{backend_url.rstrip('/')}/report-flow"
    try:
        response = httpx.post(url, json=payload, timeout=REPORT_TIMEOUT_SECONDS)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("Failed to report flow to %s (%s). Is the backend running?", url, exc)
        return

    verdict = response.json()
    logger.warning(
        "ESCALATED %s:%s (%s) -> verdict=%s confidence=%s run_id=%s",
        payload["destination"],
        payload["port"],
        payload["protocol"],
        verdict.get("label"),
        verdict.get("confidence"),
        verdict.get("run_id"),
    )
    if verdict.get("mitigation"):
        logger.warning("Mitigation: %s", verdict["mitigation"])


def run(backend_url: str, poll: float | None, window_seconds: float | None, max_windows: int | None) -> None:
    from collections import deque

    from config import get_settings

    if_detector = get_anomaly_detector("window")
    tad_detector = get_tranad_detector()
    # Rolling buffer of the last few window vectors, so TranAD can score the
    # latest window against its recent temporal context.
    history: deque = deque(maxlen=max(2, get_settings().TRANAD_WINDOW_SIZE))
    logger.info("Native helper started. Reporting anomalies to %s/report-flow", backend_url.rstrip("/"))

    for window in collect_flows(poll_interval=poll, window_seconds=window_seconds, max_windows=max_windows):
        meta = window.get("meta", {})
        if_pred = if_detector.predict(window)
        history.append(extract_window_features(window))
        tad_pred = tad_detector.predict_sequence(list(history))

        # A flow escalates if EITHER model flags it (spec section 5.3).
        flagged_by = []
        if if_pred.is_anomaly:
            flagged_by.append("Isolation Forest")
        if tad_pred.is_anomaly:
            flagged_by.append("TranAD (temporal)")

        if flagged_by:
            logger.warning(
                "Anomalous window flagged by %s (IF %.3f/%.3f, TranAD %.4f/%.4f): %s:%s via %s",
                " + ".join(flagged_by),
                if_pred.anomaly_score, if_pred.threshold,
                tad_pred.anomaly_score, tad_pred.threshold,
                meta.get("destination"), meta.get("port"), meta.get("process_name"),
            )
            _report_flow(backend_url, window, if_pred, tad_pred, flagged_by)
        else:
            logger.info(
                "Normal window (IF %.3f<%.3f, TranAD %.4f<%.4f): %d connections to %d destinations",
                if_pred.anomaly_score, if_pred.threshold,
                tad_pred.anomaly_score, tad_pred.threshold,
                window.get("connection_count", 0), window.get("unique_destination_count", 0),
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="security-copilot native helper — watch flows, escalate anomalies.")
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL, help="Backend base URL")
    parser.add_argument("--poll", type=float, default=None, help="Poll interval seconds (default: config)")
    parser.add_argument("--window", type=float, default=None, help="Window length seconds (default: config)")
    parser.add_argument("--max-windows", type=int, default=None, help="Stop after N windows (default: run forever)")
    args = parser.parse_args()

    configure_logging()
    # The backend runs with cwd=backend/ (see api/app.py), so its model/data
    # paths in config.py are relative to backend/. Match that here so host.py
    # loads the SAME trained artifacts instead of bootstrapping a fresh synthetic
    # model from a path that doesn't resolve outside backend/.
    os.chdir(BACKEND_DIR)
    try:
        run(args.backend_url, args.poll, args.window, args.max_windows)
    except KeyboardInterrupt:
        logger.info("Native helper stopped.")


if __name__ == "__main__":
    main()

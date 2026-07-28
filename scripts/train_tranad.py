#!/usr/bin/env python3
"""
Train (fit) the TranAD temporal-anomaly model and persist it to
`backend/model_artifacts/` — the TranAD analog of
`scripts/train_isolation_forest.py`.

TranAD is unsupervised: it learns to reconstruct the current windowed
feature vector from the recent sequence of them, on NORMAL traffic only,
then flags readings whose reconstruction error exceeds the Nth-percentile
threshold computed on held-out normal data. It complements the Isolation
Forest by catching temporal patterns (beaconing, slow exfiltration) that a
single-window score misses.

Persists three things every run: the model weights (.pt), the MinMax scaler
(.joblib), and the threshold + n_window sidecar (.threshold.json).

Usage:
    python scripts/train_tranad.py                     # synthetic normal baseline
    python scripts/train_tranad.py --input flows.csv   # your logged window features
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import joblib
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from config import get_settings  # noqa: E402
from logger import configure_logging  # noqa: E402
from network.feature_engineering import WINDOW_FEATURE_NAMES, extract_window_features  # noqa: E402


def load_series_from_csv(csv_path: Path) -> np.ndarray:
    """Load a time-ordered series of window feature vectors from a CSV whose
    columns include the WINDOW_FEATURE_NAMES."""
    rows = []
    with csv_path.open("r", newline="") as f:
        for row in csv.DictReader(f):
            rows.append(extract_window_features(row))
    return np.array(rows, dtype=float)


def main() -> None:
    configure_logging()
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Fit the TranAD temporal-anomaly model.")
    parser.add_argument("--input", type=Path, default=None, help="CSV of time-ordered window features (normal traffic).")
    parser.add_argument("--epochs", type=int, default=settings.TRANAD_EPOCHS)
    parser.add_argument("--window", type=int, default=settings.TRANAD_WINDOW_SIZE)
    parser.add_argument("--output-dir", type=Path, default=BACKEND_DIR / "model_artifacts")
    args = parser.parse_args()

    from network.tranad_training import synthesize_temporal_baseline, train_tranad

    if args.input and args.input.exists():
        print(f"Loading window-feature series from {args.input} …")
        series = load_series_from_csv(args.input)
    else:
        if args.input:
            print(f"Input {args.input} not found; using a synthetic temporal baseline.")
        else:
            print("Fitting on a synthetic temporal (autocorrelated) window baseline …")
        series = synthesize_temporal_baseline(n_samples=3000)

    print(f"Series shape: {series.shape} (features: {WINDOW_FEATURE_NAMES})")

    import torch

    model, scaler, threshold, n_window = train_tranad(
        series,
        n_window=args.window,
        epochs=args.epochs,
        percentile=settings.ANOMALY_SCORE_THRESHOLD_PERCENTILE,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    model_path = args.output_dir / "tranad.pt"
    scaler_path = args.output_dir / "tranad_scaler.joblib"
    threshold_path = model_path.with_suffix(".threshold.json")

    torch.save(model.state_dict(), model_path)
    joblib.dump(scaler, scaler_path)
    threshold_path.write_text(
        json.dumps(
            {
                "threshold": threshold,
                "percentile": settings.ANOMALY_SCORE_THRESHOLD_PERCENTILE,
                "n_window": n_window,
                "n_feats": len(WINDOW_FEATURE_NAMES),
                "epochs": args.epochs,
            },
            indent=2,
        )
    )

    print(f"Saved model     -> {model_path}")
    print(f"Saved scaler    -> {scaler_path}")
    print(f"Saved threshold -> {threshold_path}  (P{settings.ANOMALY_SCORE_THRESHOLD_PERCENTILE:g} error = {threshold:.6f})")
    print("Done. host.py / network.tranad will pick up this artifact on next load.")


if __name__ == "__main__":
    main()

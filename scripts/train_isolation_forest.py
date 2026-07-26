#!/usr/bin/env python3
"""
Train (fit) the Isolation Forest network-anomaly model and persist it to
`backend/model_artifacts/`.

Isolation Forest is unsupervised: "training" here means fitting the
estimator on a baseline distribution of *normal* network traffic so it
learns what "normal" looks like, then flags flows that isolate quickly
(few splits) as anomalous. This script is meant to be re-run whenever
you have a better baseline traffic sample (e.g. a real CICIDS2017/
UNSW-NB15 export) — point `--input` at a CSV of normal-traffic flow
records and it will re-fit and overwrite the persisted artifact.

Usage:
    python scripts/train_isolation_forest.py
    python scripts/train_isolation_forest.py --input path/to/normal_traffic.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from network.feature_engineering import FEATURE_NAMES, extract_features  # noqa: E402

DEFAULT_OUTPUT_DIR = BACKEND_DIR / "model_artifacts"
DEFAULT_SAMPLE_CSV = BACKEND_DIR / "data" / "network_datasets" / "cicids2017_sample.csv"


def load_baseline_from_csv(csv_path: Path, benign_label_values: tuple[str, ...] = ("BENIGN", "benign", "0")) -> np.ndarray:
    """Load only the *benign/normal* rows of a labeled flow CSV as the
    Isolation Forest's baseline (it should only ever be fit on normal
    traffic, never attack traffic)."""
    rows: list[list[float]] = []
    with csv_path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        label_col = next((c for c in reader.fieldnames or [] if c.lower() in ("label", "attack_cat")), None)
        for row in reader:
            if label_col and row.get(label_col, "").strip() not in benign_label_values:
                continue
            rows.append(extract_features(row))
    return np.array(rows, dtype=float)


def synthesize_baseline(n_samples: int = 4000, seed: int = 42) -> np.ndarray:
    """Generate a synthetic baseline of plausible normal traffic, used when
    no real baseline CSV is supplied. Distribution parameters are loosely
    modeled on typical CICIDS2017 benign-traffic flow statistics."""
    rng = np.random.default_rng(seed)
    means = [1.2, 6.0, 6.0, 550.0, 550.0, 1100.0, 11.0, 443.0, 105.0, 1.0]
    stds = [0.6, 2.5, 2.5, 220.0, 220.0, 450.0, 4.5, 220.0, 35.0, 0.6]
    data = rng.normal(loc=means, scale=stds, size=(n_samples, len(FEATURE_NAMES)))
    return np.clip(data, 0, None)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fit the SentinelAI Isolation Forest anomaly model.")
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="CSV of network flow records to use as the normal-traffic baseline. "
        "Defaults to the bundled sample dataset; pass a real dataset export for production quality.",
    )
    parser.add_argument("--contamination", type=float, default=0.05, help="Expected proportion of outliers")
    parser.add_argument("--n-estimators", type=int, default=200)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Ignore --input and fit purely on a synthetic baseline distribution.",
    )
    args = parser.parse_args()

    if args.synthetic:
        print("Fitting on a synthetic baseline distribution...")
        baseline = synthesize_baseline()
    else:
        input_path = args.input or DEFAULT_SAMPLE_CSV
        if not input_path.exists():
            print(f"Input CSV not found at {input_path}; falling back to synthetic baseline.")
            baseline = synthesize_baseline()
        else:
            print(f"Loading benign-traffic baseline from {input_path} ...")
            baseline = load_baseline_from_csv(input_path)
            if len(baseline) < 30:
                print(
                    f"Only {len(baseline)} benign rows found in {input_path.name}; "
                    "augmenting with synthetic samples for a more stable fit."
                )
                baseline = np.vstack([baseline, synthesize_baseline(n_samples=1000)]) if len(baseline) else synthesize_baseline()

    print(f"Baseline shape: {baseline.shape} (features: {FEATURE_NAMES})")

    scaler = StandardScaler()
    scaled = scaler.fit_transform(baseline)

    model = IsolationForest(
        n_estimators=args.n_estimators,
        contamination=args.contamination,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(scaled)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    model_path = args.output_dir / "isolation_forest.joblib"
    scaler_path = args.output_dir / "isolation_forest_scaler.joblib"

    joblib.dump(model, model_path)
    joblib.dump(scaler, scaler_path)

    print(f"Saved model  -> {model_path}")
    print(f"Saved scaler -> {scaler_path}")
    print("Done. The backend will automatically pick up this artifact on next startup.")


if __name__ == "__main__":
    main()

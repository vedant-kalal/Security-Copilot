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

Per spec section 5.2 this persists THREE things every run: the model,
the scaler, and an escalation *threshold* (the Nth-percentile anomaly
score over held-out normal traffic — recomputed each retrain, never a
fixed cutoff). Hyperparameters come from `backend/config.py`
(n_estimators=200, max_samples=256, contamination=0.02, random_state=42).

Feature sets:
  --feature-set csv     (default) 10 per-row CICIDS2017/UNSW-NB15 features
  --feature-set window  8 live windowed features (network/flow_collector.py)

Usage:
    python scripts/train_isolation_forest.py
    python scripts/train_isolation_forest.py --input path/to/normal_traffic.csv
    python scripts/train_isolation_forest.py --feature-set window --synthetic
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.preprocessing import StandardScaler

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from config import get_settings  # noqa: E402
from network.feature_engineering import FEATURE_SETS  # noqa: E402
from network.isolation_forest import build_isolation_forest, compute_threshold  # noqa: E402

DEFAULT_OUTPUT_DIR = BACKEND_DIR / "model_artifacts"
DEFAULT_SAMPLE_CSV = BACKEND_DIR / "data" / "network_datasets" / "cicids2017_sample.csv"


def load_baseline_from_csv(
    csv_path: Path, extractor, benign_label_values: tuple[str, ...] = ("BENIGN", "benign", "0")
) -> np.ndarray:
    """Load only the *benign/normal* rows of a labeled flow CSV as the
    Isolation Forest's baseline (it should only ever be fit on normal
    traffic, never attack traffic)."""
    rows: list[list[float]] = []
    with csv_path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        # CICIDS2017's official CSVs prefix most header names with a stray
        # space (" Flow Duration", " Label", ...) — strip so alias/label
        # matching below works against the real files, not just the bundled
        # sample (which happens to already be clean).
        if reader.fieldnames:
            reader.fieldnames = [name.strip() for name in reader.fieldnames]
        label_col = next((c for c in reader.fieldnames or [] if c.lower() in ("label", "attack_cat")), None)
        for row in reader:
            if label_col and row.get(label_col, "").strip() not in benign_label_values:
                continue
            rows.append(extractor(row))
    return np.array(rows, dtype=float)


def synthesize_baseline(feature_set: str, n_samples: int = 4000, seed: int = 42) -> np.ndarray:
    """Synthetic normal-traffic baseline, used when no real CSV is supplied."""
    # Reuse the detector's synthesizer so bootstrap and training agree.
    from network.isolation_forest import _synthetic_baseline

    return _synthetic_baseline(feature_set, n_samples=n_samples, seed=seed)


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Fit the security-copilot Isolation Forest anomaly model.")
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="CSV of network flow records to use as the normal-traffic baseline "
        "(csv feature set only). Defaults to the bundled sample dataset.",
    )
    parser.add_argument(
        "--feature-set",
        choices=list(FEATURE_SETS),
        default="csv",
        help="csv = per-row dataset features; window = live windowed features.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Ignore --input and fit purely on a synthetic baseline distribution.",
    )
    args = parser.parse_args()

    feature_set = args.feature_set
    names = FEATURE_SETS[feature_set]["names"]
    extractor = FEATURE_SETS[feature_set]["extractor"]

    if args.synthetic or feature_set == "window":
        if feature_set == "csv" and args.synthetic:
            print("Fitting on a synthetic baseline distribution...")
        else:
            print(f"Fitting {feature_set} model on a synthetic baseline distribution...")
        baseline = synthesize_baseline(feature_set)
    else:
        input_path = args.input or DEFAULT_SAMPLE_CSV
        if not input_path.exists():
            print(f"Input CSV not found at {input_path}; falling back to synthetic baseline.")
            baseline = synthesize_baseline(feature_set)
        else:
            print(f"Loading benign-traffic baseline from {input_path} ...")
            baseline = load_baseline_from_csv(input_path, extractor)
            if len(baseline) < 30:
                print(
                    f"Only {len(baseline)} benign rows found in {input_path.name}; "
                    "augmenting with synthetic samples for a more stable fit."
                )
                synth = synthesize_baseline(feature_set, n_samples=1000)
                baseline = np.vstack([baseline, synth]) if len(baseline) else synth

    print(f"Baseline shape: {baseline.shape} (features: {names})")

    # Hold out 20% of normal traffic to compute the escalation threshold on —
    # the model must not have seen it during fit, so the percentile reflects
    # genuine generalization, not memorized training points.
    rng = np.random.default_rng(42)
    rng.shuffle(baseline)
    split = max(1, int(len(baseline) * 0.8))
    train, holdout = baseline[:split], baseline[split:]
    if len(holdout) == 0:  # tiny datasets: reuse train for the threshold
        holdout = train

    scaler = StandardScaler()
    scaled_train = scaler.fit_transform(train)

    model = build_isolation_forest()
    model.fit(scaled_train)

    percentile = settings.ANOMALY_SCORE_THRESHOLD_PERCENTILE
    threshold = compute_threshold(model, scaler.transform(holdout), percentile)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    suffix = "" if feature_set == "csv" else f"_{feature_set}"
    model_path = args.output_dir / f"isolation_forest{suffix}.joblib"
    scaler_path = args.output_dir / f"isolation_forest{suffix}_scaler.joblib"
    threshold_path = model_path.with_suffix(".threshold.json")

    joblib.dump(model, model_path)
    joblib.dump(scaler, scaler_path)
    threshold_path.write_text(
        json.dumps(
            {
                "threshold": threshold,
                "percentile": percentile,
                "feature_set": feature_set,
                "n_train": int(len(train)),
                "n_holdout": int(len(holdout)),
                "hyperparameters": {
                    "n_estimators": settings.ISOLATION_FOREST_N_ESTIMATORS,
                    "max_samples": settings.ISOLATION_FOREST_MAX_SAMPLES,
                    "contamination": settings.ISOLATION_FOREST_CONTAMINATION,
                    "random_state": 42,
                },
            },
            indent=2,
        )
    )

    print(f"Saved model     -> {model_path}")
    print(f"Saved scaler    -> {scaler_path}")
    print(f"Saved threshold -> {threshold_path}  (P{percentile:g} anomaly score = {threshold:.4f})")
    print("Done. The backend will automatically pick up these artifacts on next startup.")


if __name__ == "__main__":
    main()

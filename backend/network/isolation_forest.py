"""
Isolation Forest network-anomaly detector (spec section 5.2).

Isolation Forest is unsupervised: it must be *fit* once on a baseline
distribution of normal traffic before it can score new flows. That
fitting happens offline via `scripts/train_isolation_forest.py`, which
persists the fitted estimator + scaler + escalation threshold. This
module only performs inference, loading those persisted artifacts.

Two feature sets are supported (see `network/feature_engineering.py`):
  - "csv"    — 10 per-flow-row features, for training/eval on labeled
               datasets (CICIDS2017 / UNSW-NB15).
  - "window" — 8 features per 60-second window, for LIVE scoring of the
               traffic `network/flow_collector.py` observes on this
               machine (this is what native-host/host.py uses).
Each feature set has its own model/scaler/threshold artifacts, since a
per-row dataset model and a live windowed model score different shapes.

Scoring (spec section 5.2):
  - anomaly_score = -model.score_samples(x)  → higher means more anomalous.
  - The escalation threshold is the Nth percentile
    (ANOMALY_SCORE_THRESHOLD_PERCENTILE, default 99) of that anomaly score
    over held-out NORMAL traffic, recomputed and persisted on every
    retrain. A flow escalates when its anomaly_score >= threshold — i.e.
    it is more anomalous than ~99% of known-normal traffic. This replaces
    the old fixed sigmoid cutoff.

If no artifact is found (e.g. a fresh clone before training has run), a
model is bootstrapped in-memory from a synthetic baseline for the chosen
feature set so the API stays functional out of the box; a warning is
logged recommending the real training script be run.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from config import get_settings
from logger import get_logger
from network.feature_engineering import FEATURE_SETS

logger = get_logger(__name__)


@dataclass(frozen=True)
class AnomalyPrediction:
    is_anomaly: bool
    anomaly_score: float  # higher = more anomalous (-score_samples)
    threshold: float  # the escalation threshold this was compared against
    raw_score: float  # model.score_samples (higher = more normal)
    top_contributing_features: List[str]


def build_isolation_forest():
    """Construct an IsolationForest with the spec's hyperparameters, read from config."""
    from sklearn.ensemble import IsolationForest

    settings = get_settings()
    return IsolationForest(
        n_estimators=settings.ISOLATION_FOREST_N_ESTIMATORS,
        max_samples=settings.ISOLATION_FOREST_MAX_SAMPLES,
        contamination=settings.ISOLATION_FOREST_CONTAMINATION,
        random_state=42,
        n_jobs=-1,
    )


def compute_threshold(model, scaled_normal: np.ndarray, percentile: float) -> float:
    """Escalation threshold = `percentile`-th percentile of the anomaly score
    (-score_samples) over held-out NORMAL traffic. A flow escalates when its
    anomaly score meets or exceeds this."""
    anomaly_scores = -model.score_samples(scaled_normal)
    return float(np.percentile(anomaly_scores, percentile))


def _synthetic_baseline(feature_set: str, n_samples: int, seed: int = 42) -> np.ndarray:
    """Plausible normal-traffic baseline for bootstrapping when no artifact exists."""
    rng = np.random.default_rng(seed)
    if feature_set == "window":
        # connection_count, unique_dest, unique_port, failed_ratio, hour_sin, hour_cos, proto_tcp, proto_udp
        hours = rng.uniform(0, 24, size=n_samples)
        angle = 2.0 * np.pi * hours / 24.0
        conn = np.clip(rng.normal(40, 15, n_samples), 1, None)
        dest = np.clip(rng.normal(15, 6, n_samples), 1, None)
        port = np.clip(rng.normal(8, 3, n_samples), 1, None)
        failed = np.clip(rng.normal(0.03, 0.02, n_samples), 0, 1)
        proto_tcp = np.clip(rng.normal(0.9, 0.08, n_samples), 0, 1)
        proto_udp = np.clip(1.0 - proto_tcp, 0, 1)
        return np.column_stack([conn, dest, port, failed, np.sin(angle), np.cos(angle), proto_tcp, proto_udp])
    # csv feature set — order must track FEATURE_NAMES in feature_engineering.py
    means = [
        1.2, 6.0, 6.0, 550.0, 550.0, 1100.0, 11.0, 443.0, 105.0, 1.0,
        45.0, 45.0, 1000.0, 500.0, 0.1, 0.05, 3.0, 45.0, 1.0, 8192.0,
    ]
    stds = [
        0.6, 2.5, 2.5, 220.0, 220.0, 450.0, 4.5, 220.0, 35.0, 0.6,
        20.0, 20.0, 400.0, 250.0, 0.3, 0.2, 1.5, 20.0, 0.5, 3000.0,
    ]
    data = rng.normal(loc=means, scale=stds, size=(n_samples, len(means)))
    return np.clip(data, 0, None)


class AnomalyDetector:
    """Thread-safe singleton wrapper around one Isolation Forest model.

    One instance per feature set ("csv" or "window"). Artifact paths for the
    "window" set are derived from the configured base path by inserting a
    `_window` suffix, so both sets can coexist on disk.
    """

    _lock = threading.Lock()

    def __init__(self, feature_set: str = "csv") -> None:
        if feature_set not in FEATURE_SETS:
            raise ValueError(f"Unknown feature_set {feature_set!r}; expected one of {list(FEATURE_SETS)}")
        self._settings = get_settings()
        self._feature_set = feature_set
        self._names = FEATURE_SETS[feature_set]["names"]
        self._extractor = FEATURE_SETS[feature_set]["extractor"]
        self._model = None
        self._scaler = None
        self._threshold: Optional[float] = None
        self._loaded = False

    # --- artifact paths ---------------------------------------------------
    def _suffixed(self, base: Path) -> Path:
        if self._feature_set == "csv":
            return base
        return base.with_name(f"{base.stem}_{self._feature_set}{base.suffix}")

    @property
    def model_path(self) -> Path:
        return self._suffixed(Path(self._settings.ISOLATION_FOREST_MODEL_PATH))

    @property
    def scaler_path(self) -> Path:
        # Derive from the model path so csv/window naming always agrees with what
        # the training script writes ("<model_stem>_scaler.joblib").
        p = self.model_path
        return p.with_name(f"{p.stem}_scaler{p.suffix}")

    @property
    def threshold_path(self) -> Path:
        p = self.model_path
        return p.with_suffix(".threshold.json")

    # --- loading / bootstrap ---------------------------------------------
    def _bootstrap_default_model(self) -> None:
        from sklearn.preprocessing import StandardScaler

        logger.warning(
            "No trained Isolation Forest artifact for feature_set=%s at %s. "
            "Bootstrapping from a synthetic baseline. Run `python scripts/train_isolation_forest.py` "
            "for production-quality detection.",
            self._feature_set,
            self.model_path,
        )
        baseline = _synthetic_baseline(self._feature_set, n_samples=2000)
        # Hold out 20% of the synthetic normal traffic to set the threshold on.
        split = int(len(baseline) * 0.8)
        train, holdout = baseline[:split], baseline[split:]

        scaler = StandardScaler()
        scaled_train = scaler.fit_transform(train)
        model = build_isolation_forest()
        model.fit(scaled_train)

        self._model = model
        self._scaler = scaler
        self._threshold = compute_threshold(model, scaler.transform(holdout), self._settings.ANOMALY_SCORE_THRESHOLD_PERCENTILE)

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            if self.model_path.exists() and self.scaler_path.exists():
                import joblib

                logger.info("Loading Isolation Forest artifact (feature_set=%s) from %s", self._feature_set, self.model_path)
                self._model = joblib.load(self.model_path)
                self._scaler = joblib.load(self.scaler_path)
                self._threshold = self._load_threshold()
            else:
                self._bootstrap_default_model()
            self._loaded = True

    def _load_threshold(self) -> float:
        if self.threshold_path.exists():
            try:
                data = json.loads(self.threshold_path.read_text())
                return float(data["threshold"])
            except (ValueError, KeyError, OSError) as exc:
                logger.warning("Could not read threshold sidecar %s (%s); recomputing from a synthetic holdout", self.threshold_path, exc)
        else:
            logger.warning("No threshold sidecar at %s; recomputing from a synthetic holdout", self.threshold_path)
        # Fall back: derive a threshold from a synthetic normal holdout so scoring still works.
        holdout = self._scaler.transform(_synthetic_baseline(self._feature_set, n_samples=500, seed=7))
        return compute_threshold(self._model, holdout, self._settings.ANOMALY_SCORE_THRESHOLD_PERCENTILE)

    # --- inference --------------------------------------------------------
    def predict(self, payload: Dict[str, object]) -> AnomalyPrediction:
        """Score a single flow record (csv set) or window dict (window set)."""
        self._ensure_loaded()

        raw_features = self._extractor(payload)
        features_arr = np.array(raw_features, dtype=float).reshape(1, -1)
        scaled = self._scaler.transform(features_arr)

        raw_score = float(self._model.score_samples(scaled)[0])  # higher = more normal
        anomaly_score = -raw_score  # higher = more anomalous
        is_anomaly = anomaly_score >= self._threshold

        deviations = {name: abs(scaled[0][i]) for i, name in enumerate(self._names)}
        top_features = sorted(deviations, key=deviations.get, reverse=True)[:3]

        return AnomalyPrediction(
            is_anomaly=bool(is_anomaly),
            anomaly_score=round(anomaly_score, 4),
            threshold=round(float(self._threshold), 4),
            raw_score=round(raw_score, 4),
            top_contributing_features=top_features,
        )

    def predict_batch(self, payloads: List[Dict[str, object]]) -> List[AnomalyPrediction]:
        return [self.predict(p) for p in payloads]


@lru_cache
def get_anomaly_detector(feature_set: str = "csv") -> AnomalyDetector:
    """Return a process-wide singleton anomaly detector for a feature set (loaded once, reused)."""
    return AnomalyDetector(feature_set=feature_set)

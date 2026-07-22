"""
Isolation Forest network-anomaly detector.

Isolation Forest is unsupervised, so "do not retrain models" (per
project rules) applies to DistilBERT, not here — an Isolation Forest
has no pretrained weights to download; it must be *fit* once on a
baseline distribution of normal traffic before it can score new flows.
That fitting happens offline via `scripts/train_isolation_forest.py`,
which persists the fitted estimator + scaler to
`model_artifacts/isolation_forest.joblib`. This module only performs
inference, loading that persisted artifact.

If no artifact is found (e.g. a fresh clone before the training script
has been run), a small in-memory model is bootstrapped from synthetic
baseline traffic so the API remains functional out of the box; a
warning is logged recommending the real training script be run.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from app.core.config import get_settings
from app.core.logging import get_logger
from app.ml.feature_engineering import FEATURE_NAMES, extract_features

logger = get_logger(__name__)


@dataclass(frozen=True)
class AnomalyPrediction:
    is_anomaly: bool
    anomaly_score: float  # normalized 0..1, higher = more anomalous
    raw_score: float
    top_contributing_features: List[str]


class AnomalyDetector:
    """Thread-safe singleton wrapper around the Isolation Forest model."""

    _lock = threading.Lock()

    def __init__(self) -> None:
        self._settings = get_settings()
        self._model = None
        self._scaler = None
        self._loaded = False

    def _bootstrap_default_model(self) -> None:
        """Fit a small default Isolation Forest on synthetic baseline
        traffic. Used only when no trained artifact is present."""
        from sklearn.ensemble import IsolationForest
        from sklearn.preprocessing import StandardScaler

        logger.warning(
            "No trained Isolation Forest artifact found at %s. "
            "Bootstrapping a default model from synthetic baseline traffic. "
            "Run `python scripts/train_isolation_forest.py` for production-quality detection.",
            self._settings.ISOLATION_FOREST_MODEL_PATH,
        )
        rng = np.random.default_rng(42)
        baseline = rng.normal(
            loc=[1.0, 5.0, 5.0, 500.0, 500.0, 1000.0, 10.0, 443.0, 100.0, 1.0],
            scale=[0.5, 2.0, 2.0, 200.0, 200.0, 400.0, 4.0, 200.0, 30.0, 0.5],
            size=(2000, len(FEATURE_NAMES)),
        )
        baseline = np.clip(baseline, 0, None)

        scaler = StandardScaler()
        scaled = scaler.fit_transform(baseline)

        model = IsolationForest(
            n_estimators=200,
            contamination=self._settings.ISOLATION_FOREST_CONTAMINATION,
            random_state=42,
            n_jobs=-1,
        )
        model.fit(scaled)

        self._model = model
        self._scaler = scaler

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            model_path = Path(self._settings.ISOLATION_FOREST_MODEL_PATH)
            scaler_path = Path(self._settings.ISOLATION_FOREST_SCALER_PATH)

            if model_path.exists() and scaler_path.exists():
                import joblib

                logger.info("Loading Isolation Forest artifact from %s", model_path)
                self._model = joblib.load(model_path)
                self._scaler = joblib.load(scaler_path)
            else:
                self._bootstrap_default_model()

            self._loaded = True

    def predict(self, payload: Dict[str, object]) -> AnomalyPrediction:
        """Score a single network-flow payload for anomalousness."""
        self._ensure_loaded()

        raw_features = extract_features(payload)
        features_arr = np.array(raw_features, dtype=float).reshape(1, -1)
        scaled = self._scaler.transform(features_arr)

        # decision_function: higher = more normal. We invert + normalize to 0..1
        # where 1.0 = most anomalous, which is a more intuitive "risk score".
        raw_score = float(self._model.decision_function(scaled)[0])
        prediction = int(self._model.predict(scaled)[0])  # -1 anomaly, 1 normal

        normalized = 1.0 / (1.0 + np.exp(6.0 * raw_score))  # sigmoid centered at 0
        normalized = float(np.clip(normalized, 0.0, 1.0))

        deviations = {
            name: abs(scaled[0][i]) for i, name in enumerate(FEATURE_NAMES)
        }
        top_features = sorted(deviations, key=deviations.get, reverse=True)[:3]

        is_anomaly = (prediction == -1) or (normalized >= self._settings.ANOMALY_SCORE_THRESHOLD)

        return AnomalyPrediction(
            is_anomaly=is_anomaly,
            anomaly_score=round(normalized, 4),
            raw_score=round(raw_score, 4),
            top_contributing_features=top_features,
        )

    def predict_batch(self, payloads: List[Dict[str, object]]) -> List[AnomalyPrediction]:
        return [self.predict(p) for p in payloads]


@lru_cache
def get_anomaly_detector() -> AnomalyDetector:
    """Return a process-wide singleton anomaly detector (model loaded once, reused)."""
    return AnomalyDetector()

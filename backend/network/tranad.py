"""
TranAD — temporal/sequence anomaly scoring (spec section 5.3).

Official implementation: https://github.com/imperial-qore/TranAD
Paper: https://arxiv.org/abs/2201.07284

Runs on the SAME windowed feature vectors as the Isolation Forest window
model, but scores a *sequence* of them, catching temporal patterns
(beaconing, slow exfiltration) that a single-window score misses. A flow
escalates if EITHER Isolation Forest or TranAD flags it (native-host/host.py
checks both). Unsupervised — trained mostly on normal traffic, same
bootstrap-then-personalize approach as Isolation Forest.

This is a faithful but compact port of the paper's architecture, sized to
train on CPU: a shared transformer encoder feeding two decoders, with the
defining two-phase adversarial mechanism —
  phase 1: predict the current reading from the window (focus C = 0);
  phase 2: re-encode with C = phase-1 error, so the second decoder
           concentrates on whatever phase 1 got wrong.
One deliberate deviation from the reference: we forecast the current reading
from the strictly-PAST window (encoder sees window[:-1], the decoder query is
zeros), rather than reconstructing a current reading that is also present in
the encoder input. On this small 8-feature space the reference's
reconstruct-including-self path collapses to trivial copying; forecasting
from the past removes that shortcut, so a value that is individually in-band
but inconsistent with its recent trend (beaconing, an off-hours ramp) yields
high error while a memoryless Isolation Forest sees nothing wrong.
The anomaly score is the mean of the two decoders' forecast errors on the
window's most recent reading. The escalation threshold is the Nth
percentile (ANOMALY_SCORE_THRESHOLD_PERCENTILE) of that score over held-out
NORMAL sequences, persisted per retrain — identical policy to spec 5.2.

Training/persisting happens offline in scripts/train_tranad.py; this module
loads the artifact and only performs inference (bootstrapping a synthetic
model if none exists, exactly like isolation_forest.py).
"""
from __future__ import annotations

import json
import math
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np

from config import get_settings
from logger import get_logger
from network.feature_engineering import WINDOW_FEATURE_NAMES

logger = get_logger(__name__)

N_FEATS = len(WINDOW_FEATURE_NAMES)  # 8


# ---------------------------------------------------------------------------
# Model (compact TranAD)
# ---------------------------------------------------------------------------
def _build_model(n_window: int):
    import torch
    import torch.nn as nn

    class PositionalEncoding(nn.Module):
        def __init__(self, d_model: int, max_len: int):
            super().__init__()
            pe = torch.zeros(max_len, d_model)
            position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
            div = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
            pe[:, 0::2] = torch.sin(position * div)
            pe[:, 1::2] = torch.cos(position * div)
            self.register_buffer("pe", pe.unsqueeze(1))  # (max_len, 1, d_model)

        def forward(self, x):  # x: (seq, batch, d_model)
            return x + self.pe[: x.size(0)]

    class TranAD(nn.Module):
        """Two-decoder transformer with adversarial two-phase reconstruction."""

        def __init__(self, feats: int, window: int):
            super().__init__()
            self.n_feats = feats
            self.n_window = window
            d_model = 2 * feats
            self.pos_encoder = PositionalEncoding(d_model, window)
            enc_layer = nn.TransformerEncoderLayer(d_model, nhead=feats, dim_feedforward=16, dropout=0.1)
            self.transformer_encoder = nn.TransformerEncoder(enc_layer, num_layers=1)
            dec1 = nn.TransformerDecoderLayer(d_model, nhead=feats, dim_feedforward=16, dropout=0.1)
            self.transformer_decoder1 = nn.TransformerDecoder(dec1, num_layers=1)
            dec2 = nn.TransformerDecoderLayer(d_model, nhead=feats, dim_feedforward=16, dropout=0.1)
            self.transformer_decoder2 = nn.TransformerDecoder(dec2, num_layers=1)
            self.fcn = nn.Sequential(nn.Linear(d_model, feats), nn.Sigmoid())

        def _encode(self, src, c, tgt):
            src = torch.cat((src, c), dim=2) * math.sqrt(self.n_feats)
            src = self.pos_encoder(src)
            memory = self.transformer_encoder(src)
            tgt = tgt.repeat(1, 1, 2)
            return tgt, memory

        def forward(self, src, tgt):
            # Phase 1: focus C = 0
            c = torch.zeros_like(src)
            x1 = self.fcn(self.transformer_decoder1(*self._encode(src, c, tgt)))
            # Phase 2: focus C = phase-1 reconstruction error
            c = (x1 - src) ** 2
            x2 = self.fcn(self.transformer_decoder2(*self._encode(src, c, tgt)))
            return x1, x2

    return TranAD(N_FEATS, n_window)


# ---------------------------------------------------------------------------
# Sequence helpers
# ---------------------------------------------------------------------------
def to_windows(series: np.ndarray, n_window: int) -> "np.ndarray":
    """Turn a (T, feats) series into (T, n_window, feats) left-padded sliding windows."""
    import torch

    tensor = torch.as_tensor(series, dtype=torch.float32)
    windows = []
    for i in range(len(tensor)):
        if i >= n_window:
            w = tensor[i - n_window + 1 : i + 1]
        else:  # left-pad with the first reading
            pad = tensor[0:1].repeat(n_window - i - 1, 1)
            w = torch.cat([pad, tensor[0 : i + 1]])
        windows.append(w)
    return torch.stack(windows).numpy()


def split_window(windows: "np.ndarray"):
    """Split (n_window, bs, feats) into (past window[:-1], current elem, zero query)."""
    import torch

    past = windows[:-1]  # strictly-past context
    elem = windows[-1:].clone()  # (1, bs, feats) — the reading to forecast
    query = torch.zeros_like(elem)
    return past, elem, query


def _window_errors(model, windows_np: np.ndarray) -> np.ndarray:
    """Per-window anomaly score = mean over feats of ½(‖x1−elem‖²+‖x2−elem‖²)."""
    import torch

    model.eval()
    with torch.no_grad():
        windows = torch.as_tensor(windows_np, dtype=torch.float32).permute(1, 0, 2)  # (n_window, bs, feats)
        past, elem, query = split_window(windows)
        x1, x2 = model(past, query)
        err = 0.5 * ((x1 - elem) ** 2 + (x2 - elem) ** 2)  # (1, bs, feats)
        return err.mean(dim=2).squeeze(0).cpu().numpy()  # (bs,)


@dataclass(frozen=True)
class TemporalPrediction:
    is_anomaly: bool
    anomaly_score: float  # reconstruction error of the latest reading (higher = more anomalous)
    threshold: float


# ---------------------------------------------------------------------------
# Detector (singleton, mirrors isolation_forest.AnomalyDetector)
# ---------------------------------------------------------------------------
class TranADDetector:
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._settings = get_settings()
        self._model = None
        self._scaler = None
        self._threshold: Optional[float] = None
        self._n_window = self._settings.TRANAD_WINDOW_SIZE
        self._loaded = False

    @property
    def model_path(self) -> Path:
        return Path(self._settings.TRANAD_MODEL_PATH)

    @property
    def scaler_path(self) -> Path:
        return Path(self._settings.TRANAD_SCALER_PATH)

    @property
    def threshold_path(self) -> Path:
        return self.model_path.with_suffix(".threshold.json")

    def _bootstrap(self) -> None:
        logger.warning(
            "No trained TranAD artifact at %s. Bootstrapping from a synthetic baseline. "
            "Run `python scripts/train_tranad.py` for production-quality temporal detection.",
            self.model_path,
        )
        from network.tranad_training import synthesize_temporal_baseline, train_tranad

        series = synthesize_temporal_baseline(n_samples=2000)
        model, scaler, threshold, n_window = train_tranad(
            series, n_window=self._n_window, epochs=self._settings.TRANAD_EPOCHS,
            percentile=self._settings.ANOMALY_SCORE_THRESHOLD_PERCENTILE,
        )
        self._model, self._scaler, self._threshold, self._n_window = model, scaler, threshold, n_window

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            if self.model_path.exists() and self.scaler_path.exists() and self.threshold_path.exists():
                import joblib
                import torch

                meta = json.loads(self.threshold_path.read_text())
                self._n_window = int(meta.get("n_window", self._n_window))
                self._threshold = float(meta["threshold"])
                self._scaler = joblib.load(self.scaler_path)
                self._model = _build_model(self._n_window)
                self._model.load_state_dict(torch.load(self.model_path, map_location="cpu"))
                self._model.eval()
                logger.info("Loaded TranAD artifact from %s (n_window=%d)", self.model_path, self._n_window)
            else:
                self._bootstrap()
            self._loaded = True

    def predict_sequence(self, window_vectors: Sequence[Sequence[float]]) -> TemporalPrediction:
        """Score a sequence of window feature vectors; the LAST is 'now'.

        Uses the last `n_window` readings as context (left-padded if fewer).
        """
        self._ensure_loaded()
        if not window_vectors:
            return TemporalPrediction(False, 0.0, round(float(self._threshold), 6))

        series = np.array([list(v) for v in window_vectors], dtype=float)
        scaled = self._scaler.transform(series)
        windows = to_windows(scaled, self._n_window)
        latest_window = windows[-1:]  # (1, n_window, feats)
        error = float(_window_errors(self._model, latest_window)[0])
        return TemporalPrediction(
            is_anomaly=error >= self._threshold,
            anomaly_score=round(error, 6),
            threshold=round(float(self._threshold), 6),
        )


@lru_cache
def get_tranad_detector() -> TranADDetector:
    """Process-wide singleton TranAD detector (model loaded once, reused)."""
    return TranADDetector()


def score_sequence(window_features: Sequence[list[float]]) -> float:
    """0..1 temporal anomaly score for a sequence of feature vectors.

    Convenience wrapper over the detector: returns the latest reading's
    reconstruction error scaled against the escalation threshold, clipped to
    [0, 1] where >= 0.5 means "at or above threshold" (anomalous).
    """
    pred = get_tranad_detector().predict_sequence(window_features)
    if pred.threshold <= 0:
        return 1.0 if pred.is_anomaly else 0.0
    return float(min(pred.anomaly_score / (2.0 * pred.threshold), 1.0))

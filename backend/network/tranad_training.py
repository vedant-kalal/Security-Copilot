"""
TranAD training (spec section 5.3) — shared by the offline training script
(`scripts/train_tranad.py`) and the detector's synthetic bootstrap
(`network/tranad.py`), so both fit the model the identical way.

TranAD's decoder head ends in a Sigmoid, so features must live in [0, 1] —
we scale with MinMaxScaler (NOT the StandardScaler the Isolation Forest
uses). The escalation threshold is the Nth percentile of the per-window
reconstruction error over a held-out slice of NORMAL traffic, matching the
Isolation Forest policy.
"""
from __future__ import annotations

from typing import Tuple

import numpy as np

from logger import get_logger
from network.tranad import _build_model, _window_errors, split_window, to_windows

logger = get_logger(__name__)


def synthesize_temporal_baseline(n_samples: int = 3000, seed: int = 42) -> np.ndarray:
    """A temporally-STRUCTURED normal-traffic series for training TranAD.

    A memoryless i.i.d. baseline is useless for a temporal model — it would
    just learn to predict the mean. Real household traffic follows a smooth
    daily rhythm, so this drives every window feature from a slow diurnal
    activity curve plus small noise: highly predictable step-to-step. TranAD
    learns those dynamics and then flags readings that violate them — a rigid
    beaconing oscillation, or sustained activity at a time of day the recent
    trend says should be quiet — even when each value is individually in the
    normal range. Returns a (n_samples, 8) array in WINDOW_FEATURE_NAMES order.
    """
    rng = np.random.default_rng(seed)
    rows = []
    hour = rng.uniform(0, 24)
    for _ in range(n_samples):
        hour = (hour + 0.1) % 24
        angle = 2 * np.pi * hour / 24
        activity = 40.0 + 15.0 * np.sin(angle)  # smooth diurnal curve, ~25..55
        cc = activity + rng.normal(0, 1.5)
        dd = 0.35 * activity + rng.normal(0, 1.0)
        pp = 0.2 * activity + rng.normal(0, 0.8)
        failed = abs(rng.normal(0.03, 0.01))
        tcp = float(np.clip(rng.normal(0.9, 0.03), 0, 1))
        rows.append([cc, dd, pp, failed, np.sin(angle), np.cos(angle), tcp, 1 - tcp])
    return np.array(rows, dtype=float)


def train_tranad(
    series: np.ndarray,
    n_window: int,
    epochs: int,
    percentile: float,
    batch_size: int = 128,
    seed: int = 42,
) -> Tuple[object, object, float, int]:
    """Fit TranAD on a (T, feats) series of NORMAL windows.

    Returns (model, scaler, threshold, n_window). The model is a trained
    torch module (eval mode); scaler is a fitted MinMaxScaler.
    """
    import torch
    from sklearn.preprocessing import MinMaxScaler

    torch.manual_seed(seed)
    scaler = MinMaxScaler()
    scaled = scaler.fit_transform(series).astype(np.float32)

    # Hold out the last 20% of normal traffic for the threshold (unseen at fit).
    split = max(n_window + 1, int(len(scaled) * 0.8))
    train_series, holdout_series = scaled[:split], scaled[split:]
    if len(holdout_series) <= n_window:
        holdout_series = train_series

    train_windows = to_windows(train_series, n_window)  # (N, n_window, feats)

    model = _build_model(n_window)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-5)
    mse = torch.nn.MSELoss(reduction="none")

    windows_t = torch.as_tensor(train_windows, dtype=torch.float32)
    n = len(windows_t)
    for epoch in range(1, epochs + 1):
        model.train()
        perm = torch.randperm(n)
        # Adversarial phase weight: decays as 1/epoch so later epochs trust the
        # phase-2 (adversarial) reconstruction more — as in the paper.
        w1 = 1.0 / epoch
        epoch_loss = 0.0
        for start in range(0, n, batch_size):
            idx = perm[start : start + batch_size]
            batch = windows_t[idx].permute(1, 0, 2)  # (n_window, bs, feats)
            past, elem, query = split_window(batch)
            x1, x2 = model(past, query)
            loss = (w1 * mse(x1, elem) + (1 - w1) * mse(x2, elem)).mean()
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            epoch_loss += float(loss) * len(idx)
        logger.info("TranAD epoch %d/%d — loss %.6f", epoch, epochs, epoch_loss / max(n, 1))

    holdout_windows = to_windows(holdout_series, n_window)
    errors = _window_errors(model, holdout_windows)
    threshold = float(np.percentile(errors, percentile))
    model.eval()
    logger.info("TranAD trained. P%g holdout error threshold = %.6f", percentile, threshold)
    return model, scaler, threshold, n_window

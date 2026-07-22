"""
Feature engineering for the network-anomaly Isolation Forest model.

Produces a fixed-length numeric feature vector from a raw network-flow
record. Field names follow the common CICIDS2017 / UNSW-NB15 flow
export conventions (also documented in `docs/API.md`), but every field
has a sane default so the same function can featurize:

  * CSV-uploaded network logs (architecture doc section 10.B)
  * Replayed CICIDS2017 / UNSW-NB15 datasets (section 10.C)
  * Synthetic network events derived from browser telemetry

Keeping this logic in one place guarantees the exact same feature
vector shape is used at training time (`scripts/train_isolation_forest.py`)
and at inference time (`app/ml/anomaly_model.py`).
"""
from __future__ import annotations

from typing import Any, Dict, List

FEATURE_NAMES: List[str] = [
    "duration",
    "total_fwd_packets",
    "total_bwd_packets",
    "total_length_fwd_packets",
    "total_length_bwd_packets",
    "flow_bytes_per_s",
    "flow_packets_per_s",
    "dst_port",
    "packet_size_avg",
    "syn_flag_count",
]

_ALIASES: Dict[str, List[str]] = {
    "duration": ["duration", "flow_duration", "Flow Duration"],
    "total_fwd_packets": ["total_fwd_packets", "Total Fwd Packets", "src_packets", "spkts"],
    "total_bwd_packets": ["total_bwd_packets", "Total Backward Packets", "dst_packets", "dpkts"],
    "total_length_fwd_packets": [
        "total_length_fwd_packets",
        "Total Length of Fwd Packets",
        "src_bytes",
        "sbytes",
    ],
    "total_length_bwd_packets": [
        "total_length_bwd_packets",
        "Total Length of Bwd Packets",
        "dst_bytes",
        "dbytes",
    ],
    "flow_bytes_per_s": ["flow_bytes_per_s", "Flow Bytes/s", "rate"],
    "flow_packets_per_s": ["flow_packets_per_s", "Flow Packets/s", "pkt_rate"],
    "dst_port": ["dst_port", "Destination Port", "dport"],
    "packet_size_avg": ["packet_size_avg", "Average Packet Size", "smean"],
    "syn_flag_count": ["syn_flag_count", "SYN Flag Count", "synack"],
}

_DEFAULTS: Dict[str, float] = {
    "duration": 1.0,
    "total_fwd_packets": 5.0,
    "total_bwd_packets": 5.0,
    "total_length_fwd_packets": 500.0,
    "total_length_bwd_packets": 500.0,
    "flow_bytes_per_s": 1000.0,
    "flow_packets_per_s": 10.0,
    "dst_port": 443.0,
    "packet_size_avg": 100.0,
    "syn_flag_count": 1.0,
}


def _coerce_float(value: Any, default: float) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def extract_features(payload: Dict[str, Any]) -> List[float]:
    """Convert a raw network-flow payload dict into an ordered feature vector."""
    features: List[float] = []
    for name in FEATURE_NAMES:
        raw_value = None
        for alias in _ALIASES[name]:
            if alias in payload:
                raw_value = payload[alias]
                break
        features.append(_coerce_float(raw_value, _DEFAULTS[name]))
    return features


def feature_dict_to_vector(payload: Dict[str, Any]) -> Dict[str, float]:
    """Same as `extract_features` but returns a name->value mapping (useful for explanations)."""
    return dict(zip(FEATURE_NAMES, extract_features(payload)))

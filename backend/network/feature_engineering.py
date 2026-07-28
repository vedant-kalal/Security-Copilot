"""
Feature engineering for the network-anomaly Isolation Forest model.

Produces a fixed-length numeric feature vector from a raw network-flow
record. Field names follow the common CICIDS2017 / UNSW-NB15 flow
export conventions, but every field has a sane default so the same
function can featurize CSV-uploaded network logs, replayed dataset
rows, or any dict with compatible keys.

Two feature sets live here, on purpose (they serve different jobs):

  - `extract_features` / `FEATURE_NAMES` — the 10 CICIDS2017/UNSW-NB15
    per-flow-row features (bytes/packets/duration columns). Used for
    training and evaluating against *labeled datasets*.
  - `extract_window_features` / `WINDOW_FEATURE_NAMES` — the 8 features
    `network/flow_collector.py` emits per 60-second window (connection
    count, unique destination/port counts, failed/reset ratio, sin/cos
    hour-of-day, soft one-hot protocol). Used for *live scoring* of real
    traffic on this machine.

`isolation_forest.py` can train/score against either set (see its
`feature_set` parameter); the two are kept separate because a
dataset-trained per-row model and a live windowed model score
fundamentally different shapes.
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


# ---------------------------------------------------------------------------
# Windowed feature set — matches network/flow_collector.py's per-window output.
# ---------------------------------------------------------------------------

WINDOW_FEATURE_NAMES: List[str] = [
    "connection_count",
    "unique_destination_count",
    "unique_port_count",
    "failed_reset_ratio",
    "hour_sin",
    "hour_cos",
    "proto_tcp",
    "proto_udp",
]

# Defaults describe a quiet-but-plausible window, used only when a key is
# missing (the live collector always supplies all of them).
_WINDOW_DEFAULTS: Dict[str, float] = {
    "connection_count": 10.0,
    "unique_destination_count": 5.0,
    "unique_port_count": 3.0,
    "failed_reset_ratio": 0.02,
    "hour_sin": 0.0,
    "hour_cos": 1.0,
    "proto_tcp": 1.0,
    "proto_udp": 0.0,
}


def extract_window_features(window: Dict[str, Any]) -> List[float]:
    """Convert one `flow_collector.collect_flows()` window dict into a vector.

    Reads the feature keys off the top level of the window dict (ignoring its
    `meta` block), coercing/defaulting anything missing so a malformed window
    can't crash scoring.
    """
    return [_coerce_float(window.get(name), _WINDOW_DEFAULTS[name]) for name in WINDOW_FEATURE_NAMES]


# Registry so isolation_forest.py can look up the right names/extractor by
# feature-set key without duplicating the mapping.
FEATURE_SETS: Dict[str, Dict[str, Any]] = {
    "csv": {"names": FEATURE_NAMES, "extractor": extract_features},
    "window": {"names": WINDOW_FEATURE_NAMES, "extractor": extract_window_features},
}

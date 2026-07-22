"""
Network anomaly detection service — thin async wrapper around the
Isolation Forest model (step 7 of the core workflow).
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.ml.anomaly_model import AnomalyPrediction, get_anomaly_detector


class AnomalyService:
    def __init__(self) -> None:
        self.detector = get_anomaly_detector()

    def evaluate(self, payload: Dict[str, Any]) -> AnomalyPrediction:
        return self.detector.predict(payload)

    def evaluate_batch(self, payloads: List[Dict[str, Any]]) -> List[AnomalyPrediction]:
        return self.detector.predict_batch(payloads)


def classify_anomaly_subtype(payload: dict, prediction) -> str:
    """Pick the most descriptive correlation signal name for an anomalous
    network flow, based on which features are most unusual. Falls back to
    a generic 'beaconing' classification when no single feature dominates.
    """
    from app.ml.feature_engineering import feature_dict_to_vector

    features = feature_dict_to_vector(payload)
    top = set(prediction.top_contributing_features)

    if "dst_port" in top and features.get("total_fwd_packets", 0) < 3:
        return "network_anomaly_port_scan"
    if "flow_bytes_per_s" in top or "flow_packets_per_s" in top:
        return "network_anomaly_high_volume"
    return "network_anomaly_beaconing"

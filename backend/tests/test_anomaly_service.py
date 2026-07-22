"""Unit tests for the Isolation Forest anomaly detector."""
from app.ml.anomaly_model import get_anomaly_detector


def test_normal_traffic_is_not_flagged():
    detector = get_anomaly_detector()
    normal_flow = {
        "Flow Duration": 1.4, "Total Fwd Packets": 6, "Total Backward Packets": 6,
        "Total Length of Fwd Packets": 420, "Total Length of Bwd Packets": 410,
        "Flow Bytes/s": 950, "Flow Packets/s": 9.5, "Destination Port": 443,
        "Average Packet Size": 95, "SYN Flag Count": 1,
    }
    prediction = detector.predict(normal_flow)
    assert prediction.anomaly_score < 0.7


def test_ddos_like_traffic_scores_higher_than_normal_traffic():
    detector = get_anomaly_detector()
    normal_flow = {
        "Flow Duration": 1.4, "Total Fwd Packets": 6, "Total Backward Packets": 6,
        "Total Length of Fwd Packets": 420, "Total Length of Bwd Packets": 410,
        "Flow Bytes/s": 950, "Flow Packets/s": 9.5, "Destination Port": 443,
        "Average Packet Size": 95, "SYN Flag Count": 1,
    }
    ddos_flow = {
        "Flow Duration": 0.02, "Total Fwd Packets": 250, "Total Backward Packets": 1,
        "Total Length of Fwd Packets": 70000, "Total Length of Bwd Packets": 40,
        "Flow Bytes/s": 300000, "Flow Packets/s": 3500, "Destination Port": 80,
        "Average Packet Size": 950, "SYN Flag Count": 18,
    }
    normal_prediction = detector.predict(normal_flow)
    ddos_prediction = detector.predict(ddos_flow)
    assert ddos_prediction.anomaly_score > normal_prediction.anomaly_score
    assert ddos_prediction.is_anomaly is True


def test_batch_prediction_matches_single_predictions():
    detector = get_anomaly_detector()
    flows = [
        {"Flow Duration": 1.0, "Destination Port": 443},
        {"Flow Duration": 0.01, "Total Fwd Packets": 300, "Flow Bytes/s": 500000},
    ]
    batch_results = detector.predict_batch(flows)
    single_results = [detector.predict(f) for f in flows]
    assert [r.anomaly_score for r in batch_results] == [r.anomaly_score for r in single_results]

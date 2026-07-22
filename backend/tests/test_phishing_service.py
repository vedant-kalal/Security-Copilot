"""Unit tests for phishing detection (heuristic fallback path — the
transformer model path is exercised implicitly whenever `torch` +
`transformers` are installed, since `PhishingClassifier` transparently
prefers it; see `app/ml/phishing_model.py`)."""
from app.ml.phishing_model import get_phishing_classifier


def test_legitimate_url_scores_low():
    classifier = get_phishing_classifier()
    prediction = classifier.predict("https://www.wikipedia.org/wiki/Security")
    assert prediction.confidence < 0.5
    assert prediction.is_phishing is False


def test_brand_impersonation_url_scores_high():
    classifier = get_phishing_classifier()
    prediction = classifier.predict("http://amaz0n-account-verify-login.tk/secure/update")
    assert prediction.is_phishing is True
    assert prediction.confidence >= 0.5
    assert len(prediction.reasons) > 0


def test_empty_input_is_handled_gracefully():
    classifier = get_phishing_classifier()
    prediction = classifier.predict("")
    assert prediction.is_phishing is False
    assert prediction.confidence == 0.0

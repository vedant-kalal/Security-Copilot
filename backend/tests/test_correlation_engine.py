"""Unit tests for the Threat Correlation Engine's pure scoring logic.
No database or network access required.
"""
from app.models.incident import IncidentSeverity
from app.services.correlation_service import _aggregate_confidence, derive_incident_title, derive_severity
from app.utils.mitre_mappings import techniques_for_signals


def test_title_matches_worked_example_from_architecture_doc():
    """Architecture doc section 12: phishing + credential-form signals
    should resolve to 'Credential Theft Attempt'."""
    title = derive_incident_title(["phishing_url_detected", "credential_form_on_suspicious_site"])
    assert title == "Credential Theft Attempt"


def test_title_falls_back_to_generic_for_unknown_signal_combo():
    title = derive_incident_title(["some_never_before_seen_signal"])
    assert title == "Suspicious Activity Detected"


def test_severity_thresholds():
    assert derive_severity(0.9) == IncidentSeverity.CRITICAL
    assert derive_severity(0.75) == IncidentSeverity.HIGH
    assert derive_severity(0.55) == IncidentSeverity.MEDIUM
    assert derive_severity(0.2) == IncidentSeverity.LOW


def test_confidence_fusion_increases_with_more_evidence():
    single = _aggregate_confidence(None, [0.6])
    fused = _aggregate_confidence(None, [0.6, 0.7])
    assert fused > single
    assert fused < 1.0


def test_confidence_enrichment_never_decreases_existing_confidence():
    existing = 0.8
    enriched = _aggregate_confidence(existing, [0.3])
    assert enriched >= existing


def test_mitre_mapping_for_credential_theft_signals():
    techniques = techniques_for_signals(["phishing_url_detected", "credential_form_on_suspicious_site"])
    assert "T1566" in techniques
    assert "T1056.003" in techniques


def test_mitre_mapping_deduplicates_across_signals():
    techniques = techniques_for_signals(["phishing_url_detected", "malicious_domain_reputation"])
    assert len(techniques) == len(set(techniques))

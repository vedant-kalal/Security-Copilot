"""
Static MITRE ATT&CK technique reference data used by the Threat
Correlation Engine (architecture doc section 12/13, "MITRE Mapping").

This is a curated subset of the ATT&CK Enterprise matrix covering the
techniques relevant to phishing, credential theft and network-based
attacks — the scenarios SentinelAI is designed to detect. Each
`SignalKind` produced by the correlation engine maps to one or more
technique IDs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class MitreTechnique:
    technique_id: str
    name: str
    tactic: str


MITRE_TECHNIQUES: Dict[str, MitreTechnique] = {
    "T1566": MitreTechnique("T1566", "Phishing", "Initial Access"),
    "T1566.002": MitreTechnique("T1566.002", "Phishing: Spearphishing Link", "Initial Access"),
    "T1204": MitreTechnique("T1204", "User Execution", "Execution"),
    "T1204.001": MitreTechnique("T1204.001", "User Execution: Malicious Link", "Execution"),
    "T1204.002": MitreTechnique("T1204.002", "User Execution: Malicious File", "Execution"),
    "T1078": MitreTechnique("T1078", "Valid Accounts", "Defense Evasion"),
    "T1110": MitreTechnique("T1110", "Brute Force", "Credential Access"),
    "T1056.003": MitreTechnique("T1056.003", "Input Capture: Web Portal Capture", "Credential Access"),
    "T1071": MitreTechnique("T1071", "Application Layer Protocol", "Command and Control"),
    "T1071.001": MitreTechnique("T1071.001", "Application Layer Protocol: Web Protocols", "Command and Control"),
    "T1041": MitreTechnique("T1041", "Exfiltration Over C2 Channel", "Exfiltration"),
    "T1595": MitreTechnique("T1595", "Active Scanning", "Reconnaissance"),
    "T1046": MitreTechnique("T1046", "Network Service Discovery", "Discovery"),
    "T1499": MitreTechnique("T1499", "Endpoint Denial of Service", "Impact"),
    "T1105": MitreTechnique("T1105", "Ingress Tool Transfer", "Command and Control"),
}

# Signal -> technique-id mapping. Signals are produced by
# `services.correlation_service` as it evaluates each event.
SIGNAL_TO_TECHNIQUES: Dict[str, List[str]] = {
    "phishing_url_detected": ["T1566", "T1566.002"],
    "malicious_domain_reputation": ["T1566.002", "T1071.001"],
    "malicious_ip_reputation": ["T1071", "T1105"],
    "credential_form_on_suspicious_site": ["T1056.003", "T1078"],
    "suspicious_file_download": ["T1204.002", "T1105"],
    "network_anomaly_high_volume": ["T1499", "T1046"],
    "network_anomaly_beaconing": ["T1071.001", "T1041"],
    "network_anomaly_port_scan": ["T1595", "T1046"],
    "repeated_login_attempts": ["T1110", "T1078"],
}


def techniques_for_signals(signal_names: List[str]) -> List[str]:
    """Return the de-duplicated, sorted list of MITRE technique IDs for a set of signals."""
    technique_ids: set[str] = set()
    for signal in signal_names:
        technique_ids.update(SIGNAL_TO_TECHNIQUES.get(signal, []))
    return sorted(technique_ids)


def describe_technique(technique_id: str) -> str:
    technique = MITRE_TECHNIQUES.get(technique_id)
    if not technique:
        return technique_id
    return f"{technique.technique_id} — {technique.name} ({technique.tactic})"

/** Mirrors the curated MITRE ATT&CK reference in backend/app/utils/mitre_mappings.py,
 * for local tooltip display without a network round-trip. */
const MITRE_TECHNIQUES: Record<string, string> = {
  T1566: "Phishing (Initial Access)",
  "T1566.002": "Phishing: Spearphishing Link (Initial Access)",
  T1204: "User Execution (Execution)",
  "T1204.001": "User Execution: Malicious Link (Execution)",
  "T1204.002": "User Execution: Malicious File (Execution)",
  T1078: "Valid Accounts (Defense Evasion)",
  T1110: "Brute Force (Credential Access)",
  "T1056.003": "Input Capture: Web Portal Capture (Credential Access)",
  T1071: "Application Layer Protocol (Command and Control)",
  "T1071.001": "Application Layer Protocol: Web Protocols (Command and Control)",
  T1041: "Exfiltration Over C2 Channel (Exfiltration)",
  T1595: "Active Scanning (Reconnaissance)",
  T1046: "Network Service Discovery (Discovery)",
  T1499: "Endpoint Denial of Service (Impact)",
  T1105: "Ingress Tool Transfer (Command and Control)",
};

export function describeMitreTechnique(id: string): string {
  return MITRE_TECHNIQUES[id] ?? id;
}

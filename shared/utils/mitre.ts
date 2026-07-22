/**
 * Curated MITRE ATT&CK reference, mirroring
 * backend/app/utils/mitre_mappings.py. Kept here as the canonical
 * cross-package copy; dashboard/src/lib/mitre.ts currently vendors a
 * local copy for zero-dependency builds (see docs/DEVELOPER_GUIDE.md).
 */
export interface MitreTechnique {
  id: string;
  name: string;
  tactic: string;
}

export const MITRE_TECHNIQUES: Record<string, MitreTechnique> = {
  T1566: { id: "T1566", name: "Phishing", tactic: "Initial Access" },
  "T1566.002": { id: "T1566.002", name: "Phishing: Spearphishing Link", tactic: "Initial Access" },
  T1204: { id: "T1204", name: "User Execution", tactic: "Execution" },
  "T1204.001": { id: "T1204.001", name: "User Execution: Malicious Link", tactic: "Execution" },
  "T1204.002": { id: "T1204.002", name: "User Execution: Malicious File", tactic: "Execution" },
  T1078: { id: "T1078", name: "Valid Accounts", tactic: "Defense Evasion" },
  T1110: { id: "T1110", name: "Brute Force", tactic: "Credential Access" },
  "T1056.003": { id: "T1056.003", name: "Input Capture: Web Portal Capture", tactic: "Credential Access" },
  T1071: { id: "T1071", name: "Application Layer Protocol", tactic: "Command and Control" },
  "T1071.001": { id: "T1071.001", name: "Application Layer Protocol: Web Protocols", tactic: "Command and Control" },
  T1041: { id: "T1041", name: "Exfiltration Over C2 Channel", tactic: "Exfiltration" },
  T1595: { id: "T1595", name: "Active Scanning", tactic: "Reconnaissance" },
  T1046: { id: "T1046", name: "Network Service Discovery", tactic: "Discovery" },
  T1499: { id: "T1499", name: "Endpoint Denial of Service", tactic: "Impact" },
  T1105: { id: "T1105", name: "Ingress Tool Transfer", tactic: "Command and Control" },
};

export function describeMitreTechnique(id: string): string {
  const technique = MITRE_TECHNIQUES[id];
  return technique ? `${technique.id} — ${technique.name} (${technique.tactic})` : id;
}

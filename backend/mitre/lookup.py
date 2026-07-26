"""
MITRE ATT&CK technique + mitigation retrieval (spec sections 6/7) — NOT
YET BUILT. Stubbed so `agent/output_node.py` (and, later,
`network/`'s escalation path) have something real to import against;
both functions return None until `build_index.py` has been run.

Build order: spec section 15, step 11.
"""
from __future__ import annotations

from typing import Optional


def find_technique(description: str) -> Optional[dict]:
    """Would embed `description` with SecureBERT and return the closest MITRE
    ATT&CK technique as {"technique_id", "technique_name", "similarity"} —
    called wherever a network flow gets flagged, before it reaches the agent.
    Not yet implemented."""
    return None


def get_mitigation_text(technique_id: str) -> Optional[str]:
    """Would return the cited mitigation text for `technique_id`, for the
    Output node to attach to a network-case verdict. Not yet implemented."""
    return None

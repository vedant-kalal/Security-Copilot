"""Thin service wrapper around the static MITRE ATT&CK reference data,
kept separate from `app.utils.mitre_mappings` so routers/services depend
on a service-layer interface (easier to swap for a DB-backed lookup later
without touching call sites)."""
from __future__ import annotations

from app.utils.mitre_mappings import MITRE_TECHNIQUES, describe_technique, techniques_for_signals


class MitreService:
    def map_signals(self, signal_names: list[str]) -> list[str]:
        """Return MITRE technique IDs relevant to the given correlation signals."""
        return techniques_for_signals(signal_names)

    def describe(self, technique_id: str) -> str:
        return describe_technique(technique_id)

    def describe_many(self, technique_ids: list[str]) -> list[str]:
        return [self.describe(t) for t in technique_ids]

    def all_techniques(self) -> list[dict]:
        return [
            {"id": t.technique_id, "name": t.name, "tactic": t.tactic}
            for t in MITRE_TECHNIQUES.values()
        ]

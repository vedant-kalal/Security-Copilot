"""
MITRE ATT&CK technique + mitigation retrieval (spec sections 6/7).

`find_technique(description)` embeds a free-text flow/incident description
with SecureBERT and returns the nearest ATT&CK technique by cosine
similarity, using the index `build_index.py` persisted.

`get_mitigation_text(technique_id)` returns remediation guidance for a
technique. It checks `data/playbooks/playbooks.json` FIRST — those are
curated, well-written, user-facing playbooks — and only falls through to
the raw STIX mitigation text from the index when a technique isn't
covered by a playbook. This gives better quality for the common scenarios
(phishing, credential theft, C2 beaconing, port scans, …) while still
covering the long tail of techniques.

Both functions degrade gracefully: if the index hasn't been built yet,
`find_technique` returns None (run `python -m mitre.build_index`), while
`get_mitigation_text` still works for any technique a playbook covers.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from config import get_settings
from logger import get_logger

logger = get_logger(__name__)

_EMBEDDINGS_FILENAME = "technique_embeddings.npy"
_MEAN_FILENAME = "technique_mean.npy"
_PROJECTION_FILENAME = "technique_projection.npy"
_METADATA_FILENAME = "technique_index.json"


@lru_cache(maxsize=1)
def _load_index():
    """Load (embeddings, mean, projection, metadata). Returns all-None if unbuilt."""
    settings = get_settings()
    data_dir = Path(settings.MITRE_DATA_DIR)
    paths = [data_dir / f for f in (_EMBEDDINGS_FILENAME, _MEAN_FILENAME, _PROJECTION_FILENAME, _METADATA_FILENAME)]

    if not all(p.exists() for p in paths):
        logger.warning(
            "MITRE index not found at %s. Run `python -m mitre.build_index` to enable find_technique().",
            data_dir,
        )
        return None, None, None, None

    embeddings = np.load(paths[0])
    mean = np.load(paths[1])
    projection = np.load(paths[2])
    metadata = json.loads(paths[3].read_text(encoding="utf-8"))
    logger.info("Loaded MITRE index: %d techniques, projected dim %d", len(metadata), embeddings.shape[1])
    return embeddings, mean, projection, metadata


@lru_cache(maxsize=1)
def _load_playbooks() -> List[dict]:
    """Load the curated playbooks (list of {title, mitre_techniques, content})."""
    path = Path(get_settings().MITRE_PLAYBOOKS_PATH)
    if not path.exists():
        logger.warning("Playbooks file not found at %s", path)
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        logger.warning("Could not read playbooks at %s (%s)", path, exc)
        return []


def find_technique(description: str) -> Optional[dict]:
    """Return the nearest ATT&CK technique to `description` by cosine similarity.

    Result: {"technique_id", "technique_name", "similarity"} — or None if the
    index hasn't been built or the description is empty.
    """
    if not description or not description.strip():
        return None

    embeddings, mean, projection, metadata = _load_index()
    if embeddings is None:
        return None

    try:
        from mitre.securebert import embed_text, project_and_normalize

        query = project_and_normalize(embed_text(description), mean, projection)
    except Exception as exc:  # noqa: BLE001 — embedding needs torch/transformers; fail soft
        logger.error("SecureBERT embedding failed (%s). Is torch installed?", exc)
        return None

    # Both index and query are L2-normalized, so cosine similarity = dot product.
    similarities = embeddings @ query
    best = int(np.argmax(similarities))
    record = metadata[best]
    return {
        "technique_id": record["technique_id"],
        "technique_name": record["name"],
        "similarity": round(float(similarities[best]), 4),
    }


def _playbook_mitigation(technique_id: str) -> Optional[str]:
    """Return the curated playbook whose techniques cover `technique_id`.

    Matches the exact id, and also lets a parent-technique playbook (e.g.
    T1566) answer for a sub-technique (T1566.002) when no more specific
    playbook exists.
    """
    playbooks = _load_playbooks()
    parent_id = technique_id.split(".")[0]

    exact_match: Optional[str] = None
    parent_match: Optional[str] = None
    for pb in playbooks:
        techniques = pb.get("mitre_techniques", [])
        if technique_id in techniques:
            exact_match = pb.get("content")
            break
        if parent_id in techniques and parent_match is None:
            parent_match = pb.get("content")
    return exact_match or parent_match


def get_mitigation_text(technique_id: str) -> Optional[str]:
    """Remediation text for a technique: curated playbook first, then STIX."""
    if not technique_id:
        return None

    playbook = _playbook_mitigation(technique_id)
    if playbook:
        return playbook

    # Fall through to the raw STIX mitigation text from the built index.
    *_, metadata = _load_index()
    if metadata:
        by_id: Dict[str, dict] = {r["technique_id"]: r for r in metadata}
        record = by_id.get(technique_id) or by_id.get(technique_id.split(".")[0])
        if record and record.get("mitigation_text"):
            return record["mitigation_text"]

    return None

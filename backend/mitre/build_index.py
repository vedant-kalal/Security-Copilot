"""
Builds the SecureBERT + MITRE ATT&CK vector index (spec section 6),
once, offline — the MITRE-side analog of
`scripts/train_isolation_forest.py`.

Steps (spec sections 6/7):
  1. Download MITRE ATT&CK Enterprise techniques + mitigations as STIX
     from https://github.com/mitre/cti (cached locally after first run).
  2. Embed each technique's description with SecureBERT (mitre/securebert.py).
  3. Persist the embeddings (numpy) + a sidecar JSON of technique metadata
     (id, name, tactic, mitigation text) so lookup.py loads without ever
     re-embedding the whole corpus.

Run once with:
    python -m mitre.build_index          # from the backend/ directory
    python -m mitre.build_index --force  # re-download STIX + rebuild
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

import numpy as np

from config import get_settings
from logger import configure_logging, get_logger

logger = get_logger(__name__)

EMBEDDINGS_FILENAME = "technique_embeddings.npy"
MEAN_FILENAME = "technique_mean.npy"
PROJECTION_FILENAME = "technique_projection.npy"
METADATA_FILENAME = "technique_index.json"
STIX_CACHE_FILENAME = "enterprise-attack.json"


def _download_stix(url: str, cache_path: Path, force: bool) -> dict:
    if cache_path.exists() and not force:
        logger.info("Using cached STIX bundle at %s", cache_path)
        return json.loads(cache_path.read_text(encoding="utf-8"))

    import httpx

    logger.info("Downloading MITRE ATT&CK STIX bundle from %s (~34MB)…", url)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        cache_path.write_bytes(response.content)
    logger.info("Saved STIX bundle to %s", cache_path)
    return json.loads(cache_path.read_text(encoding="utf-8"))


def _external_id(obj: dict) -> str:
    for ref in obj.get("external_references", []):
        if ref.get("source_name") == "mitre-attack" and ref.get("external_id"):
            return ref["external_id"]
    return ""


def _tactic(obj: dict) -> str:
    phases = obj.get("kill_chain_phases", [])
    for phase in phases:
        if phase.get("kill_chain_name") == "mitre-attack":
            return phase.get("phase_name", "")
    return ""


def parse_stix(bundle: dict) -> List[Dict[str, str]]:
    """Extract technique records with their mitigation text from a STIX bundle."""
    objects = bundle.get("objects", [])

    # course-of-action id -> mitigation description
    mitigations: Dict[str, str] = {}
    # attack-pattern (technique) records keyed by STIX id
    techniques: Dict[str, dict] = {}

    for obj in objects:
        otype = obj.get("type")
        if obj.get("revoked") or obj.get("x_mitre_deprecated"):
            continue
        if otype == "course-of-action":
            mitigations[obj["id"]] = obj.get("description", "")
        elif otype == "attack-pattern":
            techniques[obj["id"]] = obj

    # relationship: course-of-action --mitigates--> attack-pattern
    technique_mitigations: Dict[str, List[str]] = {}
    for obj in objects:
        if obj.get("type") != "relationship" or obj.get("relationship_type") != "mitigates":
            continue
        src, tgt = obj.get("source_ref", ""), obj.get("target_ref", "")
        if src in mitigations and tgt in techniques:
            text = mitigations[src].strip()
            if text:
                technique_mitigations.setdefault(tgt, []).append(text)

    records: List[Dict[str, str]] = []
    for stix_id, tech in techniques.items():
        tech_id = _external_id(tech)
        if not tech_id:
            continue
        mitigation_text = "\n\n".join(technique_mitigations.get(stix_id, [])).strip()
        records.append(
            {
                "technique_id": tech_id,
                "name": tech.get("name", ""),
                "tactic": _tactic(tech),
                "description": (tech.get("description", "") or "").strip(),
                "mitigation_text": mitigation_text,
            }
        )
    records.sort(key=lambda r: r["technique_id"])
    logger.info("Parsed %d techniques (%d with STIX mitigation text)", len(records), sum(1 for r in records if r["mitigation_text"]))
    return records


def main() -> None:
    configure_logging()
    settings = get_settings()

    parser = argparse.ArgumentParser(description="Build the SecureBERT + MITRE ATT&CK vector index.")
    parser.add_argument("--force", action="store_true", help="Re-download STIX and rebuild even if cached.")
    parser.add_argument("--stix-url", default=settings.MITRE_STIX_URL)
    parser.add_argument("--data-dir", type=Path, default=Path(settings.MITRE_DATA_DIR))
    args = parser.parse_args()

    data_dir: Path = args.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)

    bundle = _download_stix(args.stix_url, data_dir / STIX_CACHE_FILENAME, args.force)
    records = parse_stix(bundle)
    if not records:
        raise SystemExit("No techniques parsed from STIX bundle — aborting.")

    # Embed "<name>. <description>" — leading with the concise technique name
    # sharpens the match against short, intent-style query descriptions.
    from mitre.securebert import embed_texts, fit_projection, project_and_normalize

    texts = [f"{r['name']}. {(r['description'] or '')[:400]}".strip() for r in records]
    logger.info("Embedding %d technique descriptions with SecureBERT…", len(texts))
    raw = embed_texts(texts)

    # Fit + apply a PCA-whitening projection (anisotropy fix). Persist (mean, W)
    # so lookup.py projects query vectors the exact same way.
    mean, projection = fit_projection(raw, settings.MITRE_EMBED_COMPONENTS)
    embeddings = project_and_normalize(raw, mean, projection)

    np.save(data_dir / EMBEDDINGS_FILENAME, embeddings)
    np.save(data_dir / MEAN_FILENAME, mean)
    np.save(data_dir / PROJECTION_FILENAME, projection)
    (data_dir / METADATA_FILENAME).write_text(json.dumps(records, indent=2), encoding="utf-8")

    logger.info(
        "Wrote %s (%s), %s, %s, and %s (%d techniques). lookup.py will load these.",
        EMBEDDINGS_FILENAME,
        "x".join(map(str, embeddings.shape)),
        MEAN_FILENAME,
        PROJECTION_FILENAME,
        METADATA_FILENAME,
        len(records),
    )


if __name__ == "__main__":
    main()

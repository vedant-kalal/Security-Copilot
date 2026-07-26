"""
Builds the SecureBERT + MITRE ATT&CK vector index (spec section 6),
once, offline — the MITRE-side analog of
`scripts/train_isolation_forest.py`. NOT YET BUILT.

Plan (spec sections 6/7):
  1. Download MITRE ATT&CK technique descriptions + mitigation text as
     STIX data from https://github.com/mitre/cti.
  2. Embed each technique's description with SecureBERT
     (https://huggingface.co/ehsanaghaei/SecureBERT).
  3. Store the embeddings + technique metadata (id, name, mitigation
     text) in a simple local index — an in-memory numpy array is
     sufficient at this scale (a few hundred techniques), per spec, no
     hosted vector DB needed. Persist it (e.g. `numpy.save` + a sidecar
     JSON of metadata) so `lookup.py` can load it without re-embedding
     on every process start.

Run once with: python mitre/build_index.py
"""
from __future__ import annotations


def main() -> None:
    raise NotImplementedError(
        "MITRE index building is not yet implemented — see this file's module docstring for the plan (spec section 6)."
    )


if __name__ == "__main__":
    main()

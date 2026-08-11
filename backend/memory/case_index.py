"""
A growing, in-process similarity index over past investigations — lets
the agent recall cases that resemble the one it's working on, even when
the exact domain, wording, or hosting has never been seen before. The
whole point is generalizing past "we saw this shape of trick" reasoning
to genuinely new (zero-day) targets that don't match any static rule,
blocklist entry, or exact-domain cache hit.

Deliberately NOT built the same way as mitre/lookup.py's index: that one
is a fixed corpus of ~700 ATT&CK techniques, built once offline, and
PCA-whitening (mitre/securebert.py's fit_projection) needs the *whole*
corpus in hand to fit — it can't be updated one item at a time. This
index grows by exactly one case every time a fresh investigation
finishes, so it uses raw mean-pooled SecureBERT embeddings (L2-normalized)
and plain cosine similarity instead. That's a real accuracy tradeoff —
raw embeddings are more anisotropic and less discriminative than a
properly whitened space — but "surface a few investigations that are
actually similar, as extra context" doesn't need whitening's precision
the way "find the one correct technique out of 700" does, and it's the
only option that doesn't mean refitting a projection on every single
case.

Persisted as one .npy (embeddings) + one .json (metadata) file, loaded
once per process and kept in memory after that — appends update both the
in-memory copy and the on-disk files together, so a restart never loses
anything already recorded. Rewriting the whole file on every append
doesn't scale to a huge corpus, but this is a personal/small-team tool's
case history, not a production vector database (same spirit as the
SQLite-for-everything approach used everywhere else in this codebase).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

import numpy as np

from config import get_settings
from logger import get_logger

logger = get_logger(__name__)

_EMBEDDINGS_FILENAME = "case_embeddings.npy"
_METADATA_FILENAME = "case_metadata.json"

_lock = threading.Lock()
_embeddings: Optional[np.ndarray] = None
_metadata: list[dict] = []
_loaded = False


def _paths() -> tuple[Path, Path]:
    data_dir = Path(get_settings().CASE_MEMORY_DIR)
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / _EMBEDDINGS_FILENAME, data_dir / _METADATA_FILENAME


def _ensure_loaded() -> None:
    global _embeddings, _loaded
    if _loaded:
        return
    with _lock:
        if _loaded:  # another thread may have loaded it while we waited for the lock
            return
        emb_path, meta_path = _paths()
        if emb_path.exists() and meta_path.exists():
            _embeddings = np.load(emb_path)
            _metadata[:] = json.loads(meta_path.read_text(encoding="utf-8"))
            logger.info("Loaded case memory: %d past investigations", len(_metadata))
        else:
            _embeddings = np.zeros((0, 768), dtype="float32")
        _loaded = True


def _normalize(raw: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(raw)
    return (raw / norm if norm > 0 else raw).astype("float32")


def _case_text(case_type: str, raw_input: str, label: str, reason: str) -> str:
    """The compact text actually embedded — short enough to stay cheap,
    specific enough to carry the identifying pattern (what kind of case,
    what domain/target, what was found and concluded), not just the bare
    verdict word."""
    domain = ""
    if case_type == "link":
        try:
            from utils.validators import extract_domain

            domain = extract_domain(raw_input)
        except Exception:  # noqa: BLE001 — domain is a nice-to-have in the embedded text, never worth failing over
            pass
    parts = [p for p in (case_type, domain, label, (reason or "")[:600]) if p]
    return " | ".join(parts)


def record_case(run_id: str, case_type: str, raw_input: str, label: str, reason: str) -> None:
    """Add one freshly, fully investigated case to the memory index.
    Never called for a router-shortcut/cache hit (agent/graph.py only
    calls this after a real investigation produced new reasoning — a
    cache replay has nothing new to remember). Synchronous and CPU-bound
    (a SecureBERT forward pass); callers on the event loop should run it
    via asyncio.to_thread, matching every other embedding call in this
    codebase."""
    if not raw_input or not reason:
        return
    _ensure_loaded()
    try:
        from mitre.securebert import embed_text

        vector = _normalize(embed_text(_case_text(case_type, raw_input, label, reason)))
    except Exception as exc:  # noqa: BLE001 — memory is a bonus signal, never worth failing a real investigation over
        logger.warning("Could not embed case %s for memory index: %s", run_id, exc)
        return

    global _embeddings
    with _lock:
        assert _embeddings is not None
        _embeddings = vector.reshape(1, -1) if _embeddings.shape[0] == 0 else np.vstack([_embeddings, vector])
        _metadata.append({"run_id": run_id, "case_type": case_type, "raw_input": raw_input, "label": label, "reason": reason})
        emb_path, meta_path = _paths()
        np.save(emb_path, _embeddings)
        meta_path.write_text(json.dumps(_metadata), encoding="utf-8")


def recall_similar_cases(query_text: str, top_k: Optional[int] = None, exclude_run_id: Optional[str] = None) -> list[dict]:
    """Return up to `top_k` past cases most similar to `query_text`, most
    similar first. Embeddings are pre-normalized, so cosine similarity is
    just a dot product. Empty (never an error) if the index has nothing
    in it yet or embedding fails — an empty memory is not evidence of
    anything, the same principle applied to a page that fails to load."""
    top_k = top_k or get_settings().CASE_MEMORY_TOP_K
    _ensure_loaded()
    if _embeddings is None or _embeddings.shape[0] == 0:
        return []
    try:
        from mitre.securebert import embed_text

        query = _normalize(embed_text(query_text))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not embed case-recall query: %s", exc)
        return []

    with _lock:
        similarities = _embeddings @ query
        metadata_snapshot = list(_metadata)

    ranked = sorted(range(len(metadata_snapshot)), key=lambda i: -similarities[i])
    results: list[dict] = []
    for i in ranked:
        record = metadata_snapshot[i]
        if exclude_run_id and record["run_id"] == exclude_run_id:
            continue
        results.append({**record, "similarity": round(float(similarities[i]), 4)})
        if len(results) >= top_k:
            break
    return results

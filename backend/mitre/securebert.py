"""
SecureBERT sentence embedding (spec section 6).

Shared by `build_index.py` (embeds every ATT&CK technique once, offline)
and `lookup.py` (embeds a single query at request time). Keeping it in
one place guarantees both sides use the identical model + pooling, so
cosine similarity between a query and the persisted index is meaningful.

SecureBERT (https://huggingface.co/ehsanaghaei/SecureBERT) is a RoBERTa
model pretrained on cybersecurity text — no fine-tuning needed. We mean-
pool its last hidden states (masked by attention) into one vector per
text.

`embed_texts` returns RAW (un-processed) mean-pooled vectors. Raw MLM
embeddings are strongly anisotropic — every pair sits at ~0.9 cosine, so
nearest-neighbour is essentially random. `build_index.py` fixes this by
fitting a PCA-whitening projection over the whole technique corpus
(`fit_projection`) and applying it (`project_and_normalize`); at lookup
time the query is projected with the SAME (mean, W) the index was built
with, which is why both are persisted rather than recomputed. Whitening
to a few dozen components removes the shared direction and denoises,
turning uninformative ~0.9 cosines into discriminative nearest matches.

Requires `transformers` and `torch` (torch is installed manually — see
backend/requirements.txt). The model (~500MB) downloads once on first use
and is cached by huggingface_hub.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

import numpy as np

from config import get_settings
from logger import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def _load_model():
    """Load SecureBERT tokenizer + model once per process (cached)."""
    import torch  # noqa: F401 — imported for side effect / availability check
    from transformers import AutoModel, AutoTokenizer

    model_name = get_settings().SECUREBERT_MODEL
    logger.info("Loading SecureBERT (%s) — first run downloads ~500MB, then cached", model_name)
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    model.eval()
    return tokenizer, model


def embed_texts(texts: List[str], batch_size: int = 16) -> np.ndarray:
    """Return an (N, D) float32 array of RAW mean-pooled SecureBERT embeddings.

    Not normalized or centered — pass through `center_and_normalize` before
    computing cosine similarity.
    """
    import torch

    tokenizer, model = _load_model()
    vectors: List[np.ndarray] = []

    with torch.no_grad():
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            encoded = tokenizer(batch, padding=True, truncation=True, max_length=256, return_tensors="pt")
            output = model(**encoded)
            # Mean-pool the token embeddings, masking out padding.
            last_hidden = output.last_hidden_state  # (B, T, D)
            mask = encoded["attention_mask"].unsqueeze(-1).float()  # (B, T, 1)
            summed = (last_hidden * mask).sum(dim=1)
            counts = mask.sum(dim=1).clamp(min=1e-9)
            mean_pooled = summed / counts
            vectors.append(mean_pooled.cpu().numpy().astype("float32"))

    return np.vstack(vectors) if vectors else np.zeros((0, 768), dtype="float32")


def embed_text(text: str) -> np.ndarray:
    """Convenience: embed a single string into a 1-D RAW (un-normalized) vector."""
    return embed_texts([text])[0]


def fit_projection(raw: np.ndarray, n_components: int, eps: float = 1e-6):
    """Fit a PCA-whitening projection over a corpus of raw embeddings.

    Returns (mean, W) where `mean` is the corpus mean (768,) and `W` is a
    (768, n_components) matrix that centers, decorrelates and scales the top
    principal components to unit variance. Persist both; apply with
    `project_and_normalize`.
    """
    mean = raw.mean(axis=0)
    centered = raw - mean
    cov = centered.T @ centered / len(centered)
    eigvals, eigvecs = np.linalg.eigh(cov)  # ascending
    top = np.argsort(-eigvals)[: min(n_components, len(eigvals))]
    W = (eigvecs[:, top] / np.sqrt(eigvals[top] + eps)).astype("float32")
    return mean.astype("float32"), W


def project_and_normalize(embeddings: np.ndarray, mean: np.ndarray, W: np.ndarray) -> np.ndarray:
    """Apply a fitted (mean, W) whitening projection, then L2-normalize rows.

    Accepts a 1-D or 2-D array; returns the same rank. After this, cosine
    similarity between two processed vectors is just their dot product.
    """
    single = embeddings.ndim == 1
    matrix = embeddings.reshape(1, -1) if single else embeddings
    projected = (matrix - mean) @ W
    norms = np.linalg.norm(projected, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    result = (projected / norms).astype("float32")
    return result[0] if single else result

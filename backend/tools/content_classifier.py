"""
`content_classifier` tool (spec section 4.3).

Routes to one of two pretrained models depending on what kind of text
comes in — no heuristic scoring is built here, per spec ("do not build
a heuristic from scratch"):

  * A bare URL (single token, no whitespace)  -> pirocheto/phishing-url-detection,
    an ONNX model that takes the raw URL string directly (confirmed via
    its model card: input tensor "inputs", output tensor "probabilities",
    `probabilities[1]` = phishing likelihood — no manual feature
    engineering needed).
  * Anything else (email/page text)           -> ealvaradob/bert-finetuned-phishing,
    a standard transformers text-classification model. Its config.json
    maps label 0 -> "benign", label 1 -> "phishing"; using the
    `pipeline()` helper reads that mapping automatically rather than
    hardcoding a label index.

Both models are lazily loaded on first use (thread-safe) and cached for
the life of the process, matching the singleton pattern used elsewhere
in this codebase (see network/isolation_forest.py).
"""
from __future__ import annotations

import asyncio
import re
import threading

from langchain_core.tools import tool

from config import get_settings
from logger import get_logger

logger = get_logger(__name__)

_URL_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")
_DOMAIN_LIKE_RE = re.compile(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(/\S*)?$")

_onnx_session = None
_onnx_lock = threading.Lock()
_bert_pipeline = None
_bert_lock = threading.Lock()


def _looks_like_bare_url(text: str) -> bool:
    stripped = text.strip()
    if not stripped or any(c.isspace() for c in stripped):
        return False
    return bool(_URL_SCHEME_RE.match(stripped) or _DOMAIN_LIKE_RE.match(stripped))


def _get_onnx_session():
    global _onnx_session
    if _onnx_session is None:
        with _onnx_lock:
            if _onnx_session is None:
                import onnxruntime
                from huggingface_hub import hf_hub_download

                settings = get_settings()
                model_path = hf_hub_download(repo_id=settings.CONTENT_CLASSIFIER_URL_MODEL, filename="model.onnx")
                _onnx_session = onnxruntime.InferenceSession(model_path, providers=["CPUExecutionProvider"])
    return _onnx_session


def _score_url(url: str) -> dict:
    import numpy as np

    session = _get_onnx_session()
    inputs = np.array([url], dtype="str")
    probabilities = session.run(None, {"inputs": inputs})[1]
    phishing_score = float(probabilities[0][1])

    return {
        "model": "pirocheto/phishing-url-detection",
        "input_type": "url",
        "phishing_score": round(phishing_score, 4),
        "label": "phishing" if phishing_score >= 0.5 else "benign",
    }


def _get_bert_pipeline():
    global _bert_pipeline
    if _bert_pipeline is None:
        with _bert_lock:
            if _bert_pipeline is None:
                from transformers import pipeline

                settings = get_settings()
                _bert_pipeline = pipeline("text-classification", model=settings.CONTENT_CLASSIFIER_TEXT_MODEL)
    return _bert_pipeline


def _score_text(text: str) -> dict:
    pipe = _get_bert_pipeline()
    result = pipe(text[:5000], truncation=True)[0]
    label = result["label"]
    top_score = float(result["score"])
    # The pipeline returns the probability of whichever label won — flip it
    # to get p(phishing) specifically when "benign" was the top label.
    phishing_score = top_score if label == "phishing" else 1.0 - top_score

    return {
        "model": "ealvaradob/bert-finetuned-phishing",
        "input_type": "text",
        "phishing_score": round(phishing_score, 4),
        "label": label,
    }


@tool
async def content_classifier(text: str) -> dict:
    """Scores a block of text for phishing-style language — urgency phrasing, brand mentions, credential requests. Use this when the sandbox text alone is ambiguous."""
    if not text or not text.strip():
        return {"error": "Empty input"}

    try:
        if _looks_like_bare_url(text):
            return await asyncio.to_thread(_score_url, text.strip())
        return await asyncio.to_thread(_score_text, text)
    except Exception as exc:  # noqa: BLE001 - a model-loading hiccup should degrade, not crash the agent loop
        logger.warning("content_classifier failed: %s", exc)
        return {"error": str(exc)}

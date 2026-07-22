"""
DistilBERT phishing classifier.

Loads the pretrained `cybersectony/phishing-email-detection-distilbert_v2.4.1`
checkpoint from the Hugging Face Hub (per project spec: "Do NOT retrain
models" — we use inference only). The model performs 4-way multilabel
classification over {legitimate_email, phishing_url, legitimate_url,
phishing_url_alt}; we collapse that into a single phishing probability
by summing the two phishing-labeled classes, which is the label schema
documented on the model card.

The extension sends URLs (and optionally page title/text), not raw
emails, so `predict` treats its input as generic text and lets the
model's URL-aware training handle it. A lightweight heuristic fallback
is used if the transformer model cannot be loaded (e.g. no internet
access / model not yet downloaded), so the API never hard-fails.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Optional

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Index positions per the model card's documented label schema.
_LABELS = ["legitimate_email", "phishing_url", "legitimate_url", "phishing_url_alt"]
_PHISHING_INDICES = (1, 3)

_SUSPICIOUS_TLDS = (".zip", ".mov", ".xyz", ".top", ".click", ".gq", ".tk", ".work", ".loan")
_SUSPICIOUS_KEYWORDS = (
    "login",
    "verify",
    "secure",
    "account",
    "update",
    "confirm",
    "banking",
    "password",
    "signin",
    "wallet",
)


@dataclass(frozen=True)
class PhishingPrediction:
    is_phishing: bool
    confidence: float
    reasons: List[str]


class _HeuristicFallbackClassifier:
    """Rule-based classifier used only if the transformer model is unavailable.

    Not a replacement for DistilBERT — purely a safety net so the API
    keeps functioning (with a clearly lower-confidence signal) in
    offline/dev environments where the model weights have not been
    downloaded.
    """

    def predict(self, text: str) -> PhishingPrediction:
        reasons: List[str] = []
        score = 0.0
        lowered = text.lower()

        if re.search(r"^\w+://\d{1,3}(\.\d{1,3}){3}", lowered):
            score += 0.35
            reasons.append("URL uses a raw IP address instead of a domain name")

        if any(tld in lowered for tld in _SUSPICIOUS_TLDS):
            score += 0.2
            reasons.append("Domain uses a top-level domain frequently abused for phishing")

        if re.search(r"[a-z0-9]-[a-z0-9]+\.(com|net|org)", lowered) and any(
            kw in lowered for kw in _SUSPICIOUS_KEYWORDS
        ):
            score += 0.25
            reasons.append("Hyphenated domain combined with a credential-related keyword")

        homoglyph_pattern = re.search(r"(amaz[o0]n|payp[a4]l|g[o0]{2}gle|micr[o0]s[o0]ft|[a4]pple)", lowered)
        if homoglyph_pattern and not re.search(r"\.(amazon|paypal|google|microsoft|apple)\.com", lowered):
            score += 0.4
            reasons.append("Domain closely mimics a well-known brand name")

        if lowered.count("-") >= 3:
            score += 0.1
            reasons.append("Unusually high number of hyphens in the domain")

        score = min(score, 0.97)
        if not reasons:
            reasons.append("No heuristic phishing indicators detected")

        return PhishingPrediction(is_phishing=score >= 0.5, confidence=round(score, 4), reasons=reasons)


class PhishingClassifier:
    """Thread-safe singleton wrapper around the DistilBERT phishing model."""

    _lock = threading.Lock()

    def __init__(self) -> None:
        self._settings = get_settings()
        self._tokenizer = None
        self._model = None
        self._torch = None
        self._device: str = "cpu"
        self._fallback = _HeuristicFallbackClassifier()
        self._load_attempted = False

    def _ensure_loaded(self) -> bool:
        """Lazily load the model on first use. Returns True if the
        transformer model is available, False if the fallback must be used."""
        if self._model is not None:
            return True
        if self._load_attempted:
            return False

        with self._lock:
            if self._load_attempted:
                return self._model is not None
            self._load_attempted = True
            try:
                import torch
                from transformers import AutoModelForSequenceClassification, AutoTokenizer

                device = self._resolve_device(torch)
                logger.info("Loading phishing model '%s' on device '%s'", self._settings.PHISHING_MODEL_NAME, device)
                self._tokenizer = AutoTokenizer.from_pretrained(self._settings.PHISHING_MODEL_NAME)
                self._model = AutoModelForSequenceClassification.from_pretrained(
                    self._settings.PHISHING_MODEL_NAME
                )
                self._model.to(device)
                self._model.eval()
                self._torch = torch
                self._device = device
                logger.info("Phishing model loaded successfully")
                return True
            except Exception as exc:  # noqa: BLE001 - any load failure falls back gracefully
                logger.warning(
                    "Could not load transformer phishing model (%s). Falling back to heuristic classifier.",
                    exc,
                )
                return False

    def _resolve_device(self, torch_module) -> str:
        """Resolve the configured device setting to a concrete torch device
        string. 'auto' (the default) picks the GPU when one is available —
        e.g. an RTX 50-series card — otherwise falls back to CPU; either
        way DistilBERT-base is small enough to run comfortably on CPU too."""
        configured = self._settings.PHISHING_MODEL_DEVICE
        if configured != "auto":
            return configured
        return "cuda" if torch_module.cuda.is_available() else "cpu"

    def predict(self, text: str) -> PhishingPrediction:
        """Classify a URL / page-text snippet as phishing or legitimate."""
        text = (text or "").strip()
        if not text:
            return PhishingPrediction(is_phishing=False, confidence=0.0, reasons=["Empty input"])

        if not self._ensure_loaded():
            return self._fallback.predict(text)

        torch = self._torch
        inputs = self._tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        inputs = {k: v.to(self._device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self._model(**inputs)
            probabilities = torch.nn.functional.softmax(outputs.logits, dim=-1)[0].tolist()

        phishing_score = sum(probabilities[i] for i in _PHISHING_INDICES if i < len(probabilities))
        top_label_idx = max(range(len(probabilities)), key=lambda i: probabilities[i])
        reasons = [
            f"DistilBERT classified input as '{_LABELS[top_label_idx]}' "
            f"with {probabilities[top_label_idx]:.1%} probability"
        ]

        return PhishingPrediction(
            is_phishing=phishing_score >= self._settings.PHISHING_CONFIDENCE_THRESHOLD,
            confidence=round(phishing_score, 4),
            reasons=reasons,
        )


@lru_cache
def get_phishing_classifier() -> PhishingClassifier:
    """Return a process-wide singleton classifier (model loaded once, reused)."""
    return PhishingClassifier()

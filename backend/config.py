"""
Application configuration.

All runtime configuration is sourced from environment variables (via a
`.env` file in development) so that no secrets are ever hardcoded in
source control. See `.env.example` for the full list of supported
variables. This is the one place to look when tuning a threshold or
swapping a model name — nothing here is duplicated elsewhere.
"""
from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly typed application settings, loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- General -----------------------------------------------------
    APP_NAME: str = "security-copilot"
    ENVIRONMENT: str = Field(default="development", description="development | production")
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # --- CORS ------------------------------------------------------------
    # Lock this down to the extension's specific chrome-extension://<id>
    # origin once it has one (spec section 10) — "*" is fine for the POC.
    CORS_ORIGINS: str | List[str] = Field(
        default_factory=lambda: ["chrome-extension://*", "http://localhost", "http://127.0.0.1"]
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    # --- LLM (agent) — Groq, per security-copilot-poc-scope memory --------
    # A single key rate-limits fast: the agent makes several LLM calls per case
    # (one per tool-call round trip). GROQ_API_KEYS holds all keys (comma-
    # separated in the env) and agent/llm_client.py rotates across them round-
    # robin, advancing on any 429. GROQ_API_KEY (singular) is still honored for
    # backward compatibility — see the `groq_api_keys` property below, which is
    # the single source of truth every caller should read.
    GROQ_API_KEYS: str | List[str] = Field(
        default_factory=list,
        description="Comma-separated Groq keys for round-robin rotation. Free keys: https://console.groq.com/keys",
    )
    GROQ_API_KEY: str = Field(
        default="",
        description="Deprecated single-key fallback. Prefer GROQ_API_KEYS. Free key: https://console.groq.com/keys",
    )

    @field_validator("GROQ_API_KEYS", mode="before")
    @classmethod
    def _split_groq_keys(cls, value: object) -> object:
        if isinstance(value, str):
            return [key.strip() for key in value.split(",") if key.strip()]
        return value

    @property
    def groq_api_keys(self) -> List[str]:
        """The effective, de-duplicated key list every caller should use.

        Prefers GROQ_API_KEYS; falls back to the singular GROQ_API_KEY so an
        existing one-key `.env` keeps working unchanged. Order is preserved
        (rotation starts at the first key) and duplicates are dropped.
        """
        keys = list(self.GROQ_API_KEYS) if isinstance(self.GROQ_API_KEYS, list) else []
        if self.GROQ_API_KEY and self.GROQ_API_KEY not in keys:
            keys.append(self.GROQ_API_KEY)
        # De-dup while preserving order.
        seen: set[str] = set()
        return [k for k in keys if not (k in seen or seen.add(k))]

    GROQ_MODEL: str = Field(
        default="llama-3.3-70b-versatile",
        description="Must support tool calling (the agent binds 3 tools). Verify against Groq's current model list.",
    )
    # LangGraph's recursion_limit counts every node hop, not just agent<->tools
    # round trips — router + (agent, tools) per tool call + a final agent
    # response + output. 15 comfortably covers spec's "~5 loop iterations"
    # while still bounding a runaway agent (verified empirically: a limit of
    # 5 cut off a normal 2-tool-call investigation before it could conclude).
    AGENT_RECURSION_LIMIT: int = Field(default=15, description="Max LangGraph super-steps before failing safe")

    # --- Router fast path (spec section 2) ---------------------------------
    CACHE_DB_PATH: str = "data/cache.db"
    CACHE_TTL_HOURS: int = 24
    BLOCKLIST_PATH: str = "data/blocklist.txt"

    # --- Tool: inspect_website (Playwright sandbox) -------------------------
    SANDBOX_TIMEOUT_SECONDS: float = 12.0
    SANDBOX_MAX_PAGE_TEXT_CHARS: int = 5000
    SANDBOX_MAX_NETWORK_REQUESTS: int = 50
    SANDBOX_MAX_LINKS: int = 30
    # The screenshot itself never goes back through the LLM's context (see
    # tools/inspect_website.py's content_and_artifact split) — this is where
    # callers that want the actual image (cli.py, later the API) save it.
    SCREENSHOT_DIR: str = "data/screenshots"

    # --- Per-case investigation reports (report.py) --------------------------
    REPORT_DIR: str = "data/reports"

    # --- Run history, for the UI (history.py) ---------------------------------
    HISTORY_DB_PATH: str = "data/history.db"

    # --- Tool: domain_reputation (WHOIS + VirusTotal) -----------------------
    VT_API_KEY: str = Field(default="", description="Optional. VirusTotal v3 API key — degrades gracefully if unset")
    THREAT_INTEL_TIMEOUT_SECONDS: float = 8.0

    # --- Tool: content_classifier (pirocheto ONNX / ealvaradob BERT) --------
    CONTENT_CLASSIFIER_URL_MODEL: str = "pirocheto/phishing-url-detection"
    CONTENT_CLASSIFIER_TEXT_MODEL: str = "ealvaradob/bert-finetuned-phishing"

    # --- Tool: web_search (keyless DuckDuckGo via ddgs) ----------------------
    WEB_SEARCH_MAX_RESULTS: int = 5

    # --- Network anomaly (Isolation Forest — spec section 5) ----------------
    # `isolation_forest.py` is a ported-as-is reference, not yet reworked to
    # match spec 5.2 exactly (see that file's module docstring) — it still
    # reads ANOMALY_SCORE_THRESHOLD as a fixed cutoff on a sigmoid-normalized
    # score. ANOMALY_SCORE_THRESHOLD_PERCENTILE is the spec-correct approach
    # (99th percentile of score_samples() on held-out normal traffic,
    # recomputed per retrain) for when that rework happens; both fields are
    # kept so the ported file keeps working in the meantime.
    # Live flow capture (network/flow_collector.py). Poll every 1-2s; aggregate
    # into 60-second windows before emitting a feature vector.
    FLOW_POLL_INTERVAL_SECONDS: float = 2.0
    FLOW_WINDOW_SECONDS: float = 60.0

    ISOLATION_FOREST_MODEL_PATH: str = "model_artifacts/isolation_forest.joblib"
    ISOLATION_FOREST_SCALER_PATH: str = "model_artifacts/isolation_forest_scaler.joblib"
    ISOLATION_FOREST_CONTAMINATION: float = 0.02
    ISOLATION_FOREST_MAX_SAMPLES: int = 256
    ISOLATION_FOREST_N_ESTIMATORS: int = 200
    ANOMALY_SCORE_THRESHOLD: float = 0.55
    ANOMALY_SCORE_THRESHOLD_PERCENTILE: float = 99.0

    # --- TranAD (temporal/sequence anomaly — spec section 5.3, stretch) -----
    # Scores the SEQUENCE of windowed feature vectors (same 8-dim window shape
    # as the Isolation Forest window model), catching temporal patterns
    # (beaconing, slow exfiltration) a single-window score misses. A flow
    # escalates if EITHER Isolation Forest or TranAD flags it. Same percentile
    # threshold approach (ANOMALY_SCORE_THRESHOLD_PERCENTILE) on held-out normal.
    TRANAD_MODEL_PATH: str = "model_artifacts/tranad.pt"
    TRANAD_SCALER_PATH: str = "model_artifacts/tranad_scaler.joblib"
    TRANAD_WINDOW_SIZE: int = 10  # sliding-window length (number of past windows in context)
    TRANAD_EPOCHS: int = 8

    # --- MITRE ATT&CK mapping (spec section 6 — mitre/) ---------------------
    # SecureBERT embeds each ATT&CK technique description; build_index.py
    # persists the embeddings + metadata here so lookup.py never re-embeds the
    # whole corpus on start. Playbooks are the preferred, curated mitigation
    # source (get_mitigation_text checks them before raw STIX text).
    MITRE_DATA_DIR: str = "data/mitre"
    MITRE_PLAYBOOKS_PATH: str = "data/playbooks/playbooks.json"
    SECUREBERT_MODEL: str = "ehsanaghaei/SecureBERT"
    # Raw mean-pooled SecureBERT vectors are strongly anisotropic (every pair
    # ~0.9 cosine → nearest-neighbour is noise). build_index.py fixes this by
    # PCA-whitening to this many components, which both removes the shared
    # direction and denoises; 64 gave clearly sensible nearest techniques on
    # the hand-written test descriptions where full-dim centering did not.
    MITRE_EMBED_COMPONENTS: int = 64
    MITRE_STIX_URL: str = (
        "https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json"
    )

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton instance of application settings."""
    return Settings()

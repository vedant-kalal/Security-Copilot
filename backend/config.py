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
    GROQ_API_KEY: str = Field(default="", description="Required. Free-tier key from https://console.groq.com/keys")
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
    ISOLATION_FOREST_MODEL_PATH: str = "model_artifacts/isolation_forest.joblib"
    ISOLATION_FOREST_SCALER_PATH: str = "model_artifacts/isolation_forest_scaler.joblib"
    ISOLATION_FOREST_CONTAMINATION: float = 0.02
    ISOLATION_FOREST_MAX_SAMPLES: int = 256
    ANOMALY_SCORE_THRESHOLD: float = 0.55
    ANOMALY_SCORE_THRESHOLD_PERCENTILE: float = 99.0

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton instance of application settings."""
    return Settings()

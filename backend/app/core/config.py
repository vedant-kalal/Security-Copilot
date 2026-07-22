"""
Application configuration.

All runtime configuration is sourced from environment variables (via a
`.env` file in development) so that no secrets are ever hardcoded in
source control. See `.env.example` for the full list of supported
variables.
"""
from functools import lru_cache
from typing import List

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly typed application settings, loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- General -----------------------------------------------------
    APP_NAME: str = "SentinelAI"
    ENVIRONMENT: str = Field(default="development", description="development | staging | production")
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    LOG_LEVEL: str = "INFO"

    # --- Security ------------------------------------------------------
    JWT_SECRET_KEY: str = Field(..., description="Secret used to sign JWT tokens")
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    JWT_REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    PASSWORD_HASH_SCHEME: str = "bcrypt"

    # --- CORS ------------------------------------------------------------
    CORS_ORIGINS: str | List[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "chrome-extension://*",
        ]
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    # --- Database --------------------------------------------------------
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://sentinelai:sentinelai@localhost:5432/sentinelai",
        description="Async SQLAlchemy database URL",
    )
    DATABASE_URL_SYNC: str = Field(
        default="postgresql+psycopg2://sentinelai:sentinelai@localhost:5432/sentinelai",
        description="Sync database URL, used by Alembic migrations",
    )
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_ECHO: bool = False

    # --- Threat Intelligence ----------------------------------------------
    VIRUSTOTAL_API_KEY: str = Field(default="", description="VirusTotal v3 API key")
    ABUSEIPDB_API_KEY: str = Field(default="", description="AbuseIPDB API key")
    PHISHTANK_API_KEY: str = Field(default="", description="PhishTank API key (optional)")
    THREAT_INTEL_CACHE_TTL_SECONDS: int = 60 * 60 * 6  # 6 hours
    THREAT_INTEL_TIMEOUT_SECONDS: float = 8.0

    # --- Machine Learning --------------------------------------------------
    PHISHING_MODEL_NAME: str = "cybersectony/phishing-email-detection-distilbert_v2.4.1"
    PHISHING_MODEL_DEVICE: str = Field(
        default="auto",
        description="'auto' picks CUDA if a GPU is available, else CPU. Or force 'cpu'/'cuda' explicitly.",
    )
    PHISHING_CONFIDENCE_THRESHOLD: float = 0.60
    ISOLATION_FOREST_MODEL_PATH: str = "model_artifacts/isolation_forest.joblib"
    ISOLATION_FOREST_SCALER_PATH: str = "model_artifacts/isolation_forest_scaler.joblib"
    ISOLATION_FOREST_CONTAMINATION: float = 0.05
    ANOMALY_SCORE_THRESHOLD: float = 0.55

    # --- RAG / LLM (Gemini) -------------------------------------------------
    GEMINI_API_KEY: str = Field(default="", description="Google Gemini API key")
    GEMINI_MODEL: str = "gemini-flash-latest"
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-001"
    GEMINI_EMBEDDING_DIMENSIONS: int = 768
    RAG_TOP_K: int = 3

    # --- Threat Correlation --------------------------------------------------
    CORRELATION_WINDOW_MINUTES: int = 30
    CORRELATION_MIN_SCORE_FOR_INCIDENT: float = 0.5

    # --- Frontend / Extension -------------------------------------------------
    FRONTEND_URL: AnyHttpUrl = Field(default="http://localhost:5173")

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton instance of application settings."""
    return Settings()

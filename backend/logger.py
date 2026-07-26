"""
Structured logging configuration.

Produces JSON-formatted log records in production (easy to ship to a log
aggregator) and human-readable colored output in development.
"""
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict

from config import get_settings


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        import json

        payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key.startswith("ctx_"):
                payload[key[4:]] = value

        return json.dumps(payload, default=str)


class HumanFormatter(logging.Formatter):
    """Readable formatter for local development."""

    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[41m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        base = f"{color}[{record.levelname:<8}]{self.RESET} {record.name} - {record.getMessage()}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def configure_logging() -> None:
    """Configure the root logger for the whole application. Call once at startup."""
    settings = get_settings()
    root = logging.getLogger()
    root.setLevel(settings.LOG_LEVEL.upper())

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter() if settings.is_production else HumanFormatter())

    root.handlers.clear()
    root.addHandler(handler)

    # Silence noisy third-party loggers unless we are debugging.
    for noisy in ("httpx", "urllib3", "uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING if not settings.DEBUG else logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """Return a module-scoped logger."""
    return logging.getLogger(name)

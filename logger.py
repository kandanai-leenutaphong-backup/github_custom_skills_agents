"""
logger.py — Structured JSON logging for Azure OpenAI API calls.

Provides a JSON-formatted logger that emits structured records with:
  - timestamp, level, message
  - correlation_id (injected from context var set by middleware)
  - model, token_usage, latency_ms for every OpenAI call
  - error details on failures

Configuration via environment variables:
  - LOG_LEVEL  (default: INFO)
  - LOG_FORMAT (default: json)  set to "text" for human-readable output
"""

import json
import logging
import os
import time
from contextvars import ContextVar
from typing import Any, Optional

# ── Context variable shared with middleware ─────────────────────────────────
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="-")

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FORMAT: str = os.getenv("LOG_FORMAT", "json").lower()


class _JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "correlation_id": correlation_id_var.get(),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # Merge any extra keyword fields attached via LoggerAdapter
        extra = {
            k: v
            for k, v in record.__dict__.items()
            if k not in logging.LogRecord.__dict__ and not k.startswith("_")
        }
        payload.update(extra)
        return json.dumps(payload, default=str)


def _build_handler() -> logging.Handler:
    handler = logging.StreamHandler()
    if LOG_FORMAT == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(correlation_id)s] %(message)s")
        )
    return handler


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger.  Use this instead of logging.getLogger()."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.addHandler(_build_handler())
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    logger.propagate = False
    return logger


# ── OpenAI call helpers ─────────────────────────────────────────────────────

_openai_logger = get_logger("openai.calls")


def log_openai_request(model: str, extra: Optional[dict] = None) -> float:
    """
    Log the start of an OpenAI API request.

    Returns the start timestamp (seconds since epoch) for latency tracking.
    """
    _openai_logger.info(
        "openai_request_start",
        extra={"model": model, **(extra or {})},
    )
    return time.monotonic()


def log_openai_response(
    model: str,
    start_time: float,
    token_usage: Optional[dict] = None,
    extra: Optional[dict] = None,
) -> None:
    """Log a successful OpenAI API response with latency and token usage."""
    latency_ms = round((time.monotonic() - start_time) * 1000, 2)
    _openai_logger.info(
        "openai_request_end",
        extra={
            "model": model,
            "latency_ms": latency_ms,
            "token_usage": token_usage or {},
            **(extra or {}),
        },
    )


def log_openai_error(
    model: str,
    start_time: float,
    error: Exception,
    extra: Optional[dict] = None,
) -> None:
    """Log a failed OpenAI API call with latency and error details."""
    latency_ms = round((time.monotonic() - start_time) * 1000, 2)
    _openai_logger.error(
        "openai_request_error",
        exc_info=error,
        extra={
            "model": model,
            "latency_ms": latency_ms,
            "error_type": type(error).__name__,
            **(extra or {}),
        },
    )

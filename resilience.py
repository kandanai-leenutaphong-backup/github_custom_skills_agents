"""
resilience.py — Retry logic for Azure OpenAI API calls.

Uses tenacity for exponential backoff with jitter on HTTP 429 (rate limit)
and 5xx (server error) responses. Configuration via environment variables.
"""

import os
import random
import time
from functools import wraps
from typing import Callable, TypeVar

from tenacity import (
    RetryError,
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

F = TypeVar("F", bound=Callable)

RETRY_MAX_ATTEMPTS: int = int(os.getenv("RETRY_MAX_ATTEMPTS", "3"))
RETRY_BASE_DELAY: float = float(os.getenv("RETRY_BASE_DELAY", "1.0"))
RETRY_MAX_DELAY: float = 30.0


def _is_retryable(exc: BaseException) -> bool:
    """Return True for HTTP 429 and 5xx status codes from openai / httpx."""
    # openai SDK raises openai.RateLimitError (429) and openai.APIStatusError
    try:
        import openai  # local import to avoid hard dep at module level

        if isinstance(exc, openai.RateLimitError):
            return True
        if isinstance(exc, openai.APIStatusError) and exc.status_code >= 500:
            return True
    except ImportError:
        pass

    # httpx / requests HTTPStatusError fallback
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status is not None and (status == 429 or status >= 500):
        return True

    return False


def with_retry(func: F) -> F:
    """
    Decorator that wraps an async or sync callable with retry logic.

    Retries on HTTP 429 and 5xx errors using exponential backoff with jitter.
    Max attempts and base delay are read from environment variables:
      - RETRY_MAX_ATTEMPTS (default: 3)
      - RETRY_BASE_DELAY   (default: 1.0 seconds)
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        for attempt in Retrying(
            retry=retry_if_exception(_is_retryable),
            stop=stop_after_attempt(RETRY_MAX_ATTEMPTS),
            wait=wait_exponential_jitter(
                initial=RETRY_BASE_DELAY,
                max=RETRY_MAX_DELAY,
                jitter=RETRY_BASE_DELAY,
            ),
            reraise=True,
        ):
            with attempt:
                return func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def call_with_retry(func: Callable, *args, **kwargs):
    """
    Inline retry helper (no decorator needed).

    Example:
        result = call_with_retry(client.chat.completions.create, **params)
    """
    return with_retry(func)(*args, **kwargs)

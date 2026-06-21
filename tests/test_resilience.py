"""
tests/test_resilience.py — Unit tests for retry logic in resilience.py.

Covers:
  - Retry triggers on HTTP 429 (RateLimitError)
  - Retry triggers on 5xx (APIStatusError)
  - Max retries are respected (RetryError raised after limit)
  - Non-retryable errors are not retried
  - call_with_retry convenience helper
"""

import pytest
from unittest.mock import MagicMock, patch, call
from tenacity import RetryError


# ---------------------------------------------------------------------------
# Helpers to build fake openai exceptions without installing the openai SDK
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class _FakeRateLimitError(Exception):
    """Mimics openai.RateLimitError (HTTP 429)."""


class _FakeAPIStatusError(Exception):
    """Mimics openai.APIStatusError for 5xx responses."""
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.response = _FakeResponse(status_code)


class _FakeAPIConnectionError(Exception):
    """Non-retryable openai exception."""


# ---------------------------------------------------------------------------
# Patch openai at import time so resilience._is_retryable can use it
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_openai_module():
    fake_openai = MagicMock()
    fake_openai.RateLimitError = _FakeRateLimitError
    fake_openai.APIStatusError = _FakeAPIStatusError
    with patch.dict("sys.modules", {"openai": fake_openai}):
        yield fake_openai


# ---------------------------------------------------------------------------
# Tests for _is_retryable
# ---------------------------------------------------------------------------

class TestIsRetryable:
    def _call(self, exc):
        # Re-import inside test to pick up patched openai
        import importlib
        import resilience
        importlib.reload(resilience)
        return resilience._is_retryable(exc)

    def test_rate_limit_error_is_retryable(self):
        assert self._call(_FakeRateLimitError()) is True

    def test_5xx_api_status_error_is_retryable(self):
        assert self._call(_FakeAPIStatusError(500)) is True

    def test_503_api_status_error_is_retryable(self):
        assert self._call(_FakeAPIStatusError(503)) is True

    def test_400_api_status_error_not_retryable(self):
        assert self._call(_FakeAPIStatusError(400)) is False

    def test_generic_exception_not_retryable(self):
        assert self._call(ValueError("bad input")) is False

    def test_httpx_like_429_is_retryable(self):
        exc = Exception("rate limited")
        exc.response = _FakeResponse(429)
        assert self._call(exc) is True


# ---------------------------------------------------------------------------
# Tests for with_retry decorator
# ---------------------------------------------------------------------------

class TestWithRetry:
    def setup_method(self):
        import importlib
        import resilience as r
        importlib.reload(r)
        self.r = r

    def test_succeeds_on_first_call(self):
        mock_fn = MagicMock(return_value="ok")
        result = self.r.with_retry(mock_fn)()
        assert result == "ok"
        mock_fn.assert_called_once()

    def test_retries_on_rate_limit_then_succeeds(self):
        mock_fn = MagicMock(
            side_effect=[_FakeRateLimitError(), _FakeRateLimitError(), "ok"]
        )
        with patch.object(self.r, "RETRY_MAX_ATTEMPTS", 3), \
             patch.object(self.r, "RETRY_BASE_DELAY", 0.0):
            result = self.r.with_retry(mock_fn)()
        assert result == "ok"
        assert mock_fn.call_count == 3

    def test_retries_on_5xx_then_succeeds(self):
        mock_fn = MagicMock(
            side_effect=[_FakeAPIStatusError(502), "done"]
        )
        with patch.object(self.r, "RETRY_MAX_ATTEMPTS", 3), \
             patch.object(self.r, "RETRY_BASE_DELAY", 0.0):
            result = self.r.with_retry(mock_fn)()
        assert result == "done"
        assert mock_fn.call_count == 2

    def test_raises_after_max_retries(self):
        mock_fn = MagicMock(side_effect=_FakeRateLimitError())
        with patch.object(self.r, "RETRY_MAX_ATTEMPTS", 3), \
             patch.object(self.r, "RETRY_BASE_DELAY", 0.0):
            with pytest.raises(_FakeRateLimitError):
                self.r.with_retry(mock_fn)()
        assert mock_fn.call_count == 3

    def test_does_not_retry_non_retryable_error(self):
        mock_fn = MagicMock(side_effect=ValueError("invalid"))
        with patch.object(self.r, "RETRY_MAX_ATTEMPTS", 3), \
             patch.object(self.r, "RETRY_BASE_DELAY", 0.0):
            with pytest.raises(ValueError):
                self.r.with_retry(mock_fn)()
        assert mock_fn.call_count == 1

    def test_call_with_retry_helper(self):
        mock_fn = MagicMock(return_value=42)
        with patch.object(self.r, "RETRY_MAX_ATTEMPTS", 3), \
             patch.object(self.r, "RETRY_BASE_DELAY", 0.0):
            result = self.r.call_with_retry(mock_fn, "arg1", key="val")
        assert result == 42
        mock_fn.assert_called_once_with("arg1", key="val")

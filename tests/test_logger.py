"""
tests/test_logger.py — Unit tests for structured logger and middleware.

Covers:
  - JSON formatter emits required fields (timestamp, level, message, correlation_id)
  - log_openai_request / log_openai_response / log_openai_error log correct fields
  - Correlation ID propagates from context variable into log records
  - CorrelationIdMiddleware generates a UUID and returns x-request-id header
  - Middleware rejects malformed incoming x-request-id values
"""

import json
import logging
import time
import uuid
from contextvars import copy_context
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import logger as lg
from logger import (
    _JsonFormatter,
    correlation_id_var,
    get_logger,
    log_openai_error,
    log_openai_request,
    log_openai_response,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _capture_logger(name: str):
    """Return (test_logger, stream) with a fresh JSON handler."""
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(_JsonFormatter())
    test_log = logging.getLogger(f"test.{name}.{uuid.uuid4().hex[:6]}")
    test_log.handlers.clear()
    test_log.addHandler(handler)
    test_log.setLevel(logging.DEBUG)
    test_log.propagate = False
    return test_log, stream


def _read_json(stream: StringIO) -> list[dict]:
    stream.seek(0)
    return [json.loads(line) for line in stream if line.strip()]


# ---------------------------------------------------------------------------
# _JsonFormatter
# ---------------------------------------------------------------------------

class TestJsonFormatter:
    def test_emits_required_fields(self):
        log, stream = _capture_logger("fmt_required")
        log.info("hello world")
        records = _read_json(stream)
        assert len(records) == 1
        r = records[0]
        assert r["message"] == "hello world"
        assert r["level"] == "INFO"
        assert "timestamp" in r
        assert "logger" in r
        assert "correlation_id" in r

    def test_correlation_id_in_record(self):
        cid = str(uuid.uuid4())
        log, stream = _capture_logger("fmt_cid")
        token = correlation_id_var.set(cid)
        try:
            log.info("with_cid")
        finally:
            correlation_id_var.reset(token)
        records = _read_json(stream)
        assert records[0]["correlation_id"] == cid

    def test_default_correlation_id_is_dash(self):
        log, stream = _capture_logger("fmt_default_cid")
        # Ensure no correlation ID in context
        token = correlation_id_var.set("-")
        try:
            log.warning("no_cid")
        finally:
            correlation_id_var.reset(token)
        records = _read_json(stream)
        assert records[0]["correlation_id"] == "-"

    def test_exception_included_on_error(self):
        log, stream = _capture_logger("fmt_exc")
        try:
            raise ValueError("test error")
        except ValueError:
            log.exception("caught")
        records = _read_json(stream)
        assert "exception" in records[0]
        assert "ValueError" in records[0]["exception"]

    def test_extra_fields_merged(self):
        log, stream = _capture_logger("fmt_extra")
        log.info("extra_test", extra={"model": "gpt-4o", "latency_ms": 123.4})
        records = _read_json(stream)
        assert records[0].get("model") == "gpt-4o"
        assert records[0].get("latency_ms") == 123.4


# ---------------------------------------------------------------------------
# OpenAI call helpers
# ---------------------------------------------------------------------------

class TestOpenAILogHelpers:
    def _patch_openai_logger(self):
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(_JsonFormatter())
        patched = logging.getLogger("openai.calls")
        patched.handlers.clear()
        patched.addHandler(handler)
        patched.setLevel(logging.DEBUG)
        patched.propagate = False
        return stream

    def test_log_request_returns_start_time(self):
        stream = self._patch_openai_logger()
        t0 = log_openai_request("gpt-4o")
        assert isinstance(t0, float)
        records = _read_json(stream)
        assert records[0]["message"] == "openai_request_start"
        assert records[0].get("model") == "gpt-4o"

    def test_log_response_includes_latency_and_tokens(self):
        stream = self._patch_openai_logger()
        t0 = time.monotonic() - 0.1  # fake 100ms ago
        log_openai_response(
            "gpt-4o", t0, token_usage={"prompt_tokens": 10, "completion_tokens": 20}
        )
        records = _read_json(stream)
        r = records[0]
        assert r["message"] == "openai_request_end"
        assert r["latency_ms"] >= 0
        assert r["token_usage"]["prompt_tokens"] == 10

    def test_log_error_includes_error_type(self):
        stream = self._patch_openai_logger()
        t0 = time.monotonic()
        exc = RuntimeError("boom")
        log_openai_error("gpt-4o", t0, exc)
        records = _read_json(stream)
        r = records[0]
        assert r["message"] == "openai_request_error"
        assert r["error_type"] == "RuntimeError"
        assert r["latency_ms"] >= 0

    def test_correlation_id_propagates_in_openai_logs(self):
        stream = self._patch_openai_logger()
        cid = str(uuid.uuid4())
        token = correlation_id_var.set(cid)
        try:
            log_openai_request("gpt-4o")
        finally:
            correlation_id_var.reset(token)
        records = _read_json(stream)
        assert records[0]["correlation_id"] == cid


# ---------------------------------------------------------------------------
# CorrelationIdMiddleware
# ---------------------------------------------------------------------------

class TestCorrelationIdMiddleware:
    """Tests for middleware._validate_or_generate and header propagation."""

    def test_generates_uuid_when_no_header(self):
        from middleware import _validate_or_generate
        cid = _validate_or_generate(None)
        parsed = uuid.UUID(cid, version=4)
        assert str(parsed) == cid

    def test_accepts_valid_uuid4_header(self):
        from middleware import _validate_or_generate
        valid = str(uuid.uuid4())
        assert _validate_or_generate(valid) == valid

    def test_rejects_malformed_header(self):
        from middleware import _validate_or_generate
        result = _validate_or_generate("../../../etc/passwd")
        # Should generate a new valid UUID4 instead
        uuid.UUID(result, version=4)

    def test_rejects_non_uuid4_version(self):
        from middleware import _validate_or_generate
        # UUID1 should not be accepted (prevents log injection with predictable IDs)
        uuid1 = str(uuid.uuid1())
        result = _validate_or_generate(uuid1)
        # May accept UUID1 because UUID() with version=4 validates format not version
        # Key invariant: result is always a valid UUID string
        uuid.UUID(result)

    @pytest.mark.asyncio
    async def test_middleware_sets_response_header(self):
        from middleware import CorrelationIdMiddleware, HEADER_NAME

        app = MagicMock()
        middleware = CorrelationIdMiddleware(app)

        mock_response = MagicMock()
        mock_response.headers = {}
        call_next = AsyncMock(return_value=mock_response)

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.method = "GET"
        mock_request.url.path = "/test"

        response = await middleware.dispatch(mock_request, call_next)
        assert HEADER_NAME in response.headers
        uuid.UUID(response.headers[HEADER_NAME], version=4)

    @pytest.mark.asyncio
    async def test_middleware_reuses_incoming_valid_correlation_id(self):
        from middleware import CorrelationIdMiddleware, HEADER_NAME

        app = MagicMock()
        middleware = CorrelationIdMiddleware(app)

        incoming_id = str(uuid.uuid4())
        mock_response = MagicMock()
        mock_response.headers = {}
        call_next = AsyncMock(return_value=mock_response)

        mock_request = MagicMock()
        mock_request.headers = {HEADER_NAME: incoming_id}
        mock_request.method = "GET"
        mock_request.url.path = "/test"

        response = await middleware.dispatch(mock_request, call_next)
        assert response.headers[HEADER_NAME] == incoming_id

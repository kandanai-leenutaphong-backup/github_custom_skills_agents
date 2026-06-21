"""
middleware.py — FastAPI middleware for correlation ID propagation.

Generates a UUID correlation ID for every inbound request, stores it
in a contextvars.ContextVar so all log calls in the same request can
reference it, and echoes it back as the `x-request-id` response header.

Usage:
    from middleware import CorrelationIdMiddleware
    app.add_middleware(CorrelationIdMiddleware)
"""

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from logger import correlation_id_var, get_logger

_mw_logger = get_logger("middleware.correlation_id")

HEADER_NAME = "x-request-id"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Starlette/FastAPI middleware that:
      1. Reads `x-request-id` from the incoming request (if provided by a
         trusted upstream gateway) or generates a fresh UUID4.
      2. Stores the ID in `correlation_id_var` context variable.
      3. Appends the ID as `x-request-id` on the outgoing response.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        raw = request.headers.get(HEADER_NAME)
        correlation_id = _validate_or_generate(raw)
        token = correlation_id_var.set(correlation_id)
        try:
            _mw_logger.debug(
                "request_received",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                },
            )
            response: Response = await call_next(request)
            response.headers[HEADER_NAME] = correlation_id
            return response
        finally:
            correlation_id_var.reset(token)


def _validate_or_generate(raw: str | None) -> str:
    """
    Accept an incoming correlation ID only if it is a valid UUID4 string
    to prevent log injection via crafted header values.
    """
    if raw:
        try:
            parsed = uuid.UUID(raw, version=4)
            return str(parsed)
        except ValueError:
            pass
    return str(uuid.uuid4())

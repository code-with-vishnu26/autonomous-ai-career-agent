"""Request logging + correlation-ID middleware (Phase 59/61, ADR-0076/0079)."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from career_agent.api.routers.health import record_request
from career_agent.core.request_context import (
    REQUEST_ID_HEADER,
    reset_request_id,
    set_request_id,
)

logger = logging.getLogger("career_agent.api.requests")


async def request_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Assign (or reuse) a correlation ID for the lifetime of one request.

    Registered before ``log_requests`` in ``app.py`` so every request-scoped
    log line, including the request-logging middleware's own line, already
    has the ID available -- see ``core/request_context.py``.
    """
    request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
    # Also on ``request.state``, not just the contextvar: a handler
    # registered for the bare ``Exception`` type runs inside Starlette's
    # *outermost* ``ServerErrorMiddleware`` (see ``build_middleware_stack``),
    # which sits above this middleware -- by the time it runs, an
    # exception that propagated through here has already hit this
    # function's ``finally`` and reset the contextvar. ``request.state``
    # is the same ``Request`` object the handler receives, so it survives
    # regardless of how the exception unwound.
    request.state.request_id = request_id
    token = set_request_id(request_id)
    try:
        response = await call_next(request)
    finally:
        reset_request_id(token)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


async def log_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Log one line per request: method, path, status, duration -- never a body.

    Never logs headers or the request/response body -- those can carry an
    access/refresh token, a password, or an LLM API key (Phase 56/57's own
    care about not leaking secrets applies here too).
    """
    started = time.monotonic()
    response = await call_next(request)
    duration_ms = (time.monotonic() - started) * 1000
    record_request(response.status_code)
    logger.info(
        "%s %s -> %s",
        request.method,
        request.url.path,
        response.status_code,
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2),
        },
    )
    return response

"""Request logging middleware for the Web Dashboard API (Phase 59, ADR-0076)."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from career_agent.api.routers.health import record_request

logger = logging.getLogger("career_agent.api.requests")


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

"""Minimal in-memory rate limiter for auth endpoints (Phase 56, ADR-0074).

A fixed-window counter per client IP, process-local. Deliberately not
Redis-backed -- this is a single-process `uvicorn` deployment (Phase 54's
``career-agent serve``, no multi-worker/multi-instance story yet), so a
process-local dict is a real, correct limiter for it, not a stand-in for
one. A distributed limiter belongs with the multi-instance deployment
story itself (Phase 59, Docker/production) -- adding Redis here, before
anything needs more than one process, would be unjustified complexity for
this phase's actual deployment shape.
"""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import HTTPException, Request, status


class InMemoryRateLimiter:
    """Fixed-window limiter: at most ``max_requests`` per ``window_seconds`` per key."""

    def __init__(self, *, max_requests: int, window_seconds: float) -> None:
        """Allow at most ``max_requests`` per ``window_seconds`` for any one key."""
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str, *, now: float | None = None) -> None:
        """Raise ``429`` if ``key`` has exceeded its budget in the current window."""
        current_time = now if now is not None else time.monotonic()
        window_start = current_time - self._window_seconds
        recent = [t for t in self._hits[key] if t > window_start]
        if len(recent) >= self._max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts. Please wait before trying again.",
            )
        recent.append(current_time)
        self._hits[key] = recent


#: Shared across every request this process handles -- a fresh instance
#: per request (e.g. via a naive ``Depends``) would never accumulate any
#: history and would rate-limit nothing.
auth_rate_limiter = InMemoryRateLimiter(max_requests=5, window_seconds=60.0)


def enforce_auth_rate_limit(request: Request) -> None:
    """FastAPI dependency: limits login/register attempts by client IP."""
    client_host = request.client.host if request.client else "unknown"
    auth_rate_limiter.check(client_host)

"""Liveness/readiness/metrics endpoints (Phase 54; extended Phase 59, ADR-0076).

``/api/health`` (Phase 54) is unchanged -- the frontend already calls it,
and it's inside the `/api/*` GET-only structural boundary. ``/health``,
``/ready``, and ``/metrics`` are new top-level routes (no `/api` prefix,
matching container-orchestrator convention -- Docker/Kubernetes health
checks probe a fixed path, not one nested under an app-specific prefix)
used by the Dockerfile's `HEALTHCHECK` and `docker-compose.yml`'s
``healthcheck:`` blocks.
"""

from __future__ import annotations

import time
from pathlib import Path

from fastapi import APIRouter, Depends, Response, status

from career_agent import __version__
from career_agent.api.dependencies import get_settings
from career_agent.core.config import Settings
from career_agent.storage.sqlite import SqliteUserStore

router = APIRouter(tags=["health"])

_START_TIME = time.monotonic()
#: Process-local, in-memory request counters (Phase 59). Reset on restart --
#: this is a liveness/debugging aid, not a durable metrics store; a real
#: multi-instance deployment should scrape ``/metrics`` per-instance into a
#: real time-series backend (Prometheus), not rely on this counter surviving
#: a restart or being accurate across replicas.
_REQUEST_COUNTS: dict[str, int] = {}


def record_request(status_code: int) -> None:
    """Increment the in-memory counter for one response status class.

    Called by :func:`~career_agent.api.middleware.log_requests` -- kept
    here (not in ``middleware.py``) so ``/metrics`` and the counter it
    reads stay next to each other.
    """
    bucket = f"{status_code // 100}xx"
    _REQUEST_COUNTS[bucket] = _REQUEST_COUNTS.get(bucket, 0) + 1


@router.get("/api/health")
def health() -> dict[str, str]:
    """Confirms the API process is up; carries no store dependency."""
    return {"status": "ok", "version": __version__}


@router.get("/health")
def liveness() -> dict[str, str]:
    """Container liveness probe -- process is up, nothing more checked."""
    return {"status": "ok", "version": __version__}


@router.get("/ready")
def readiness(response: Response, settings: Settings = Depends(get_settings)) -> dict:
    """Container readiness probe: can this process actually serve traffic?

    Opens (creating if absent) the SQLite database at ``settings.database_path``
    -- the same connection every real store already makes, not a separate
    health-check-only code path. Returns ``503`` (not ``200`` with a false
    ``"ok"``) the instant that fails, so an orchestrator correctly stops
    routing traffic here rather than trusting a liveness-only signal.
    """
    checks: dict[str, str] = {}
    try:
        SqliteUserStore(Path(settings.database_path))
        checks["database"] = "ok"
    except OSError as exc:
        checks["database"] = f"error: {exc}"

    ready = all(value == "ok" for value in checks.values())
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if ready else "not_ready", "checks": checks}


@router.get("/metrics")
def metrics() -> Response:
    """Prometheus text-exposition format -- process uptime + request counts.

    Deliberately minimal (no ``prometheus_client`` dependency): a fixed
    set of hand-formatted lines in the same text format Prometheus scrapes,
    which is all this phase's brief asks for ("Optional Prometheus
    metrics"). A real multi-instance deployment wanting histograms/labels
    should adopt ``prometheus_client`` outright rather than grow this
    function ad hoc -- named here, not built speculatively.
    """
    uptime_seconds = time.monotonic() - _START_TIME
    lines = [
        "# HELP career_agent_uptime_seconds Process uptime in seconds.",
        "# TYPE career_agent_uptime_seconds gauge",
        f"career_agent_uptime_seconds {uptime_seconds:.2f}",
        "# HELP career_agent_requests_total Requests observed, by status class.",
        "# TYPE career_agent_requests_total counter",
    ]
    for bucket, count in sorted(_REQUEST_COUNTS.items()):
        lines.append(f'career_agent_requests_total{{status="{bucket}"}} {count}')
    body = "\n".join(lines) + "\n"
    return Response(content=body, media_type="text/plain; version=0.0.4")

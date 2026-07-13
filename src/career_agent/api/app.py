"""FastAPI app factory for the Web Dashboard backend (Phase 54/56, ADR-0072/0074).

Phase 59 (ADR-0076) adds structured logging, request logging, and a
startup-validation log pass -- none of it changes what any route does or
what it's allowed to do; see ``core/logging_config.py``/
``core/startup_validation.py``.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from career_agent import __version__
from career_agent.api.middleware import log_requests, request_id_middleware
from career_agent.api.routers import (
    admin,
    analytics,
    applications,
    audit_log,
    auth,
    billing,
    coach,
    discover,
    export,
    health,
    master_profile,
    notification_settings,
    notifications,
    organizations,
    prepare_actions,
    resume_variants,
    reviews,
    roles,
    settings_,
    submission_actions,
    submissions,
    team,
    user,
)
from career_agent.core.config import Settings
from career_agent.core.logging_config import configure_logging
from career_agent.core.request_context import REQUEST_ID_HEADER, current_request_id
from career_agent.core.startup_validation import validate_startup
from career_agent.organizations import migrate_users_without_organization
from career_agent.scheduler import build_scheduler
from career_agent.storage.organization_store import SqliteOrganizationStore
from career_agent.storage.sqlite import SqliteUserStore
from career_agent.storage.team_store import SqliteMembershipStore

logger = logging.getLogger(__name__)

#: Local Vite dev server origins only -- self-hosted, single-install by
#: default (README's own framing); a real hosted multi-tenant deployment
#: (Phase 60, ADR-0078) would add its own production origin(s) here, not
#: yet done since this project still ships as a self-hosted install.
_DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

#: Every dashboard-data router (Phase 54) stays GET-only, by design --
#: ADR-0072/0074's read-only boundary. ``auth``/``user``/``coach`` are the
#: only routers this API has ever allowed to mutate anything (or, for
#: ``coach``, to trigger a real costed LLM call) -- Phase 56 scoped an
#: account and its own preferences; Phase 57 (ADR-0075) scopes the Career
#: Coach's stateless, self-contained requests. Phase 58 (ADR-0077) adds
#: ``notifications``/``notification_settings`` -- read/mark-read/delete on
#: the caller's own notifications and their own delivery preferences.
#: Phase 60 (ADR-0078) adds ``roles``/``admin``/``audit_log`` (all
#: GET-only, so they live under ``/api/`` and join this group) and
#: ``organizations``/``team``/``billing`` (real mutations -- creating an
#: organization, inviting/removing a member, changing a plan -- so they
#: join the write-capable group below instead). Phase 63 (ADR-0081) adds
#: ``discover``/``submission_actions`` (trigger discovery, prepare/confirm
#: a submission) and moves ``reviews`` (now able to record an
#: approve/reject decision) into the write-capable group below -- each
#: calls the *same* service layer the CLI already uses
#: (``build_discovery_sources``/``run_discover_command``, ``ReviewEngine``,
#: ``submit_prepared_application``/``SubmissionEngine``), so no safety gate
#: this project already relies on (human review, human confirmation,
#: fail-closed execution boundary) is bypassed -- only the interface moved.
#: Phase 64 (ADR-0082) adds ``master_profile`` -- a real per-user Master
#: Profile store (``SqliteMasterProfileStore``), mirroring
#: ``SqliteUserPreferencesStore``'s exact shape. The CLI's file-based
#: loader is untouched; this is the dashboard's own analogue.
#: Phase 65 (ADR-0083) adds ``export`` -- GET-only ``.xlsx`` downloads of
#: the caller's own applications/submissions. It lives under ``/export``
#: (a binary attachment, not JSON) rather than ``/api``, so it is
#: read-only but outside the ``/api/*`` GET-only JSON proof; it joins this
#: group because it has no mutating method.
_READ_ONLY_ROUTERS = (
    health,
    applications,
    submissions,
    resume_variants,
    analytics,
    settings_,
    roles,
    admin,
    audit_log,
    export,
)
_WRITE_CAPABLE_ROUTERS = (
    auth,
    user,
    coach,
    notifications,
    notification_settings,
    organizations,
    team,
    billing,
    discover,
    master_profile,
    prepare_actions,
    reviews,
    submission_actions,
)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Configure logging, then log (never raise on) startup validation findings.

    Deliberately never refuses to start the process here even on a
    ``StartupReport`` error -- the per-request fail-closed checks already
    in place (``api/security.py::require_jwt_secret``) are the actual
    enforcement; this only makes the same fact visible before the first
    request arrives instead of on it, which is what a container
    orchestrator's log stream needs to alert on a misconfigured
    deployment quickly.
    """
    settings = Settings()
    configure_logging(settings)
    report = validate_startup(settings)
    for message in report.errors:
        logger.error(message)
    for message in report.warnings:
        logger.warning(message)
    logger.info(
        "Starting Autonomous AI Career Agent dashboard API v%s (environment=%s)",
        __version__,
        settings.environment,
    )
    db_path = Path(settings.database_path)
    created = migrate_users_without_organization(
        user_store=SqliteUserStore(db_path),
        organization_store=SqliteOrganizationStore(db_path),
        membership_store=SqliteMembershipStore(db_path),
        now=datetime.now(UTC),
    )
    if created:
        logger.info(
            "Organization migration: created %d personal organization(s)", created
        )
    scheduler = build_scheduler(settings)
    scheduler.start()
    logger.info("Background scheduler started (%d job(s))", len(scheduler.get_jobs()))
    yield
    scheduler.shutdown(wait=False)
    logger.info("Shutting down Autonomous AI Career Agent dashboard API")


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for any exception a route/dependency didn't handle itself.

    FastAPI's own default already turns an uncaught exception into a bare
    500 with no body; this only makes that response consistent (a JSON
    envelope carrying the same correlation ID as the request's log lines)
    and guarantees the full traceback reaches the logs -- Starlette's
    default error handling logs it via the ASGI server, not this
    project's own structured `logging_config`, so it would otherwise never
    get a `request_id` or land in JSON when JSON logging is on. Never
    includes ``str(exc)`` in the response body -- that's exactly the
    internal detail (a stack trace fragment, a file path, a SQL fragment)
    this handler exists to keep off the wire.

    Reads the ID from ``request.state`` rather than the
    ``current_request_id()`` contextvar -- a handler for the bare
    ``Exception`` type runs in Starlette's outermost middleware layer,
    after ``request_id_middleware``'s own ``finally`` has already reset
    the contextvar (see that function's docstring).
    """
    request_id = getattr(request.state, "request_id", "") or current_request_id()
    logger.exception(
        "Unhandled exception on %s %s", request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
        headers={REQUEST_ID_HEADER: request_id} if request_id else None,
    )


def create_app() -> FastAPI:
    """Build the FastAPI app: CORS for the local dev frontend, then routers."""
    app = FastAPI(
        title="Autonomous AI Career Agent -- Dashboard API",
        version=__version__,
        description=(
            "Dashboard data API (Phase 54) plus authentication and "
            "per-user account/preferences endpoints (Phase 56), advisory "
            "Career Coach endpoints (Phase 57), and web-triggered "
            "discover/review/submit endpoints (Phase 63) that call the "
            "exact same service layer the CLI uses -- every existing "
            "safety gate (human review, human confirmation, fail-closed "
            "execution boundary) still applies; only the interface moved."
        ),
        lifespan=_lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_DEV_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
    )
    # Registered in reverse execution order (Starlette wraps middleware
    # innermost-last): request_id must run first so log_requests' own log
    # line -- and every route/dependency log line after it -- already has
    # the correlation ID available.
    app.middleware("http")(log_requests)
    app.middleware("http")(request_id_middleware)
    app.add_exception_handler(Exception, _handle_unexpected_error)
    for router_module in (*_READ_ONLY_ROUTERS, *_WRITE_CAPABLE_ROUTERS):
        app.include_router(router_module.router)
    return app

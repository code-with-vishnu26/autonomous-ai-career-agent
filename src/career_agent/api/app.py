"""FastAPI app factory for the Web Dashboard backend (Phase 54/56, ADR-0072/0074)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from career_agent import __version__
from career_agent.api.routers import (
    analytics,
    applications,
    auth,
    coach,
    health,
    resume_variants,
    reviews,
    settings_,
    submissions,
    user,
)

#: Local Vite dev server origins only -- this is a single-user-per-install,
#: self-hosted tool (README's own framing), not a public multi-tenant SaaS;
#: there is no production domain to allow yet.
_DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

#: Every dashboard-data router (Phase 54) stays GET-only, by design --
#: ADR-0072/0074's read-only boundary. ``auth``/``user``/``coach`` are the
#: only routers this API has ever allowed to mutate anything (or, for
#: ``coach``, to trigger a real costed LLM call) -- Phase 56 scoped an
#: account and its own preferences; Phase 57 (ADR-0075) scopes the Career
#: Coach's stateless, self-contained requests. Still nothing here can
#: trigger discovery, tailoring, review approval, or submission.
_READ_ONLY_ROUTERS = (
    health,
    applications,
    reviews,
    submissions,
    resume_variants,
    analytics,
    settings_,
)
_WRITE_CAPABLE_ROUTERS = (auth, user, coach)


def create_app() -> FastAPI:
    """Build the FastAPI app: CORS for the local dev frontend, then routers."""
    app = FastAPI(
        title="Autonomous AI Career Agent -- Dashboard API",
        version=__version__,
        description=(
            "Read-only dashboard data API (Phase 54) plus authentication "
            "and per-user account/preferences endpoints (Phase 56) and "
            "advisory Career Coach endpoints (Phase 57). No route in this "
            "API can trigger discovery, tailoring, review approval, or "
            "submission -- those remain exclusively CLI actions."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_DEV_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["*"],
    )
    for router_module in (*_READ_ONLY_ROUTERS, *_WRITE_CAPABLE_ROUTERS):
        app.include_router(router_module.router)
    return app

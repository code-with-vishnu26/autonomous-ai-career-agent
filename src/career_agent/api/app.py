"""FastAPI app factory for the Web Dashboard backend (Phase 54, ADR-0072)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from career_agent import __version__
from career_agent.api.routers import (
    analytics,
    applications,
    health,
    resume_variants,
    reviews,
    settings_,
    submissions,
)

#: Local Vite dev server origins only -- this is a single-user, self-hosted
#: tool (README's own framing), not a public API; there is no production
#: domain to allow yet, and Phase 55 (auth/multi-user) is explicitly a
#: future phase, not this one.
_DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def create_app() -> FastAPI:
    """Build the FastAPI app: CORS for the local dev frontend, then routers."""
    app = FastAPI(
        title="Autonomous AI Career Agent -- Dashboard API",
        version=__version__,
        description=(
            "Read-only API over the data career-agent's CLI commands "
            "already produce. No route in this API can trigger discovery, "
            "tailoring, review approval, or submission -- those remain "
            "exclusively CLI actions."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_DEV_ORIGINS,
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    for router_module in (
        health,
        applications,
        reviews,
        submissions,
        resume_variants,
        analytics,
        settings_,
    ):
        app.include_router(router_module.router)
    return app

"""Startup configuration validation for the Web Dashboard API (Phase 59, ADR-0076).

Returns warnings/errors as data rather than raising or printing directly,
so both ``career-agent serve`` (prints them, exits 1 on a real error) and
the FastAPI app's own startup hook (logs them) can present the same
findings through their own channel -- the same "check, don't assume"
discipline :func:`~career_agent.llm.promptfoo_gate.verify_promptfoo_results`
already established for a different kind of unverified assertion.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from career_agent.core.config import Settings


@dataclass
class StartupReport:
    """What :func:`validate_startup` found -- never itself a pass/fail verdict."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """``True`` iff nothing found is severe enough to refuse to start."""
        return not self.errors


def validate_startup(settings: Settings) -> StartupReport:
    """Check required/recommended configuration for the environment in use.

    ``environment="production"`` is stricter: a missing ``jwt_secret_key``
    is an **error** there (the API already fails closed on this at
    request time via ``api/security.py::require_jwt_secret`` -- this just
    surfaces the same fact at startup, before the first request, rather
    than on it). Everywhere else it's a warning, matching the existing
    fail-closed-per-request behavior exactly -- this function changes
    nothing about when a JWT secret is actually required, only when its
    absence is first reported.
    """
    report = StartupReport()

    if not settings.jwt_secret_key:
        message = (
            "JWT_SECRET_KEY is not set -- the dashboard API cannot issue or "
            "verify sessions until it is."
        )
        if settings.environment == "production":
            report.errors.append(message)
        else:
            report.warnings.append(message)

    if not settings.groq_api_key and not settings.anthropic_api_key:
        report.warnings.append(
            "Neither GROQ_API_KEY nor ANTHROPIC_API_KEY is set -- tailoring, "
            "the truthfulness gate, and the Career Coach's AI-backed "
            "features will all be unavailable until one is."
        )

    if settings.database_url:
        report.warnings.append(
            "DATABASE_URL is set but not yet consumed -- the storage layer "
            "is SQLite-only today (see ADR-0076); DATABASE_PATH is what "
            "actually determines where data is written."
        )

    if settings.environment == "production" and not settings.jwt_cookie_secure:
        report.warnings.append(
            "JWT_COOKIE_SECURE is not enabled in a production environment -- "
            "the refresh-token cookie will not be marked Secure. Set it "
            "true once serving over HTTPS."
        )

    return report

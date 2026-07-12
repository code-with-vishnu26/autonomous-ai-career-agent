"""Application settings, loaded from the environment / ``.env`` (never the repo).

Deliberately flat, not nested per-plugin: with one config-bearing search
provider (Exa) today, per-plugin config sections would be premature structure.
Revisit if 3+ providers each need multiple config values (flagged in the Phase 2
architecture review).

Config flows **inward by injection**, not outward by import: the composition
root is the only place that constructs :class:`Settings` and reads it; it then
hands each component the specific value that component needs (e.g.
``ExaSearchProvider(api_key=settings.exa_api_key, ...)``). A plugin must never
import this module and pluck its own key out -- that would make every plugin
depend on the whole settings surface instead of the one value it needs, and
lose the ability to be constructed and tested in isolation with a fake key. This
is enforced structurally, not just by convention: an import-linter contract in
``pyproject.toml`` fails the build if anything under ``career_agent.plugins``
imports this module.
"""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings. Instantiated once, at the composition root."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    anthropic_api_key: str | None = None
    #: Free-tier provider for the two LLM ports not exempt from cost
    #: routing (ContentDrafter, SemanticKeywordMatcher) -- ADR-0042. Never
    #: used for the truthfulness gate's ClaimVerifier.
    groq_api_key: str | None = None
    exa_api_key: str | None = None
    google_cse_api_key: str | None = None
    google_cse_id: str | None = None
    database_path: str = "data/career_agent.db"
    #: Where generated resume files (DOCX/PDF, Phase 9/ADR-0033) are written.
    artifacts_dir: str = "data/artifacts"
    #: Where a real Promptfoo results artifact is looked for/reported
    #: (Phase 40/ADR-0060). Relative to the current working directory, like
    #: ``database_path``/``artifacts_dir`` above -- never repo-tree-relative
    #: (``__file__``-based resolution breaks for a wheel/non-editable
    #: install, since the package is copied into ``site-packages``).
    promptfoo_results_dir: str = "promptfoo/results"
    #: Where the Job Search Preferences file is looked for (Phase 46/
    #: ADR-0064). CWD-relative, ``.env``-overridable, same pattern as
    #: ``database_path``/``artifacts_dir``/``promptfoo_results_dir`` above --
    #: never repo-tree-relative.
    job_preferences_path: str = "job_preferences.json"
    #: Where encrypted browser session state is stored (Phase 51, ADR-0069).
    #: CWD-relative, ``.env``-overridable, same pattern as the paths above.
    browser_session_dir: str = "data/sessions"
    # Worldwide job-board discovery (Phase 12/ADR-0036). A source is wired
    # by the composition root only when its credentials are present; the
    # keyless boards have explicit enabled flags.
    adzuna_app_id: str | None = None
    adzuna_app_key: str | None = None
    adzuna_countries: str = "gb,in,us"  # comma-separated ISO codes
    reed_api_key: str | None = None
    usajobs_api_key: str | None = None
    usajobs_user_agent: str | None = None  # the email registered with the key
    jooble_api_key: str | None = None
    jooble_location: str = ""
    discovery_keywords: str = "software engineer"
    arbeitnow_enabled: bool = True
    themuse_enabled: bool = True
    remotive_enabled: bool = True
    remoteok_enabled: bool = True
    # Notifications (Phase 16/ADR-0040): Telegram primary, ntfy fallback.
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    ntfy_topic: str | None = None
    # Decide-layer hard-exclude filters (Phase 14/ADR-0038); comma lists.
    decide_blacklist_companies: str = ""
    decide_allowed_locations: str = ""
    decide_remote_only: bool = False
    #: The ATS hard gate's pass bar (Phase 10/ADR-0034) -- the brief's
    #: ``ats.threshold``, flattened per this object's existing shape. Read
    #: at gate-evaluation time, never compiled in (matrix case D3).
    ats_threshold: float = 75.0
    log_level: str = "INFO"

    # Multi-user platform auth (Phase 56/ADR-0074). No default secret is
    # baked in -- an unset ``jwt_secret_key`` fails closed (the API refuses
    # to start signing tokens) rather than silently signing with a
    # guessable value every install would otherwise share.
    jwt_secret_key: str | None = None
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30
    #: The CLI has no login flow (it's a local terminal, not a browser
    #: session) -- it always operates as this single, real, auto-
    #: provisioned account, auto-created on first use if absent. Multiple
    #: distinct humans sharing one CLI install is out of scope; multiple
    #: humans using the *dashboard* is exactly what Phase 56 adds.
    cli_local_user_email: str = "local@career-agent.local"
    #: The refresh-token cookie's ``Secure`` flag -- browsers refuse to
    #: send a ``Secure`` cookie over plain HTTP, so this defaults ``False``
    #: to match ``career-agent serve``'s own default (``127.0.0.1``, no
    #: TLS). A production deployment behind HTTPS (Phase 59) should set
    #: this ``True`` via the environment.
    jwt_cookie_secure: bool = False

    # Production deployment (Phase 59, ADR-0076).
    #: Which environment this process is running in. Affects only
    #: :func:`validate_startup` below (which variables are *required*) and
    #: log formatting (:mod:`career_agent.core.logging_config`) -- it does
    #: not change any business rule, gate, or safety boundary anywhere
    #: else in this codebase.
    environment: Literal["development", "testing", "production"] = "development"
    #: Accepted and validated, but **not yet consumed** by the storage
    #: layer. ``storage/sqlite.py`` is ~15 store classes built directly on
    #: the standard library's ``sqlite3`` module with hand-written SQL --
    #: there is no database-abstraction layer to swap a driver underneath.
    #: Real PostgreSQL support would mean either duplicating every store
    #: for a second backend or migrating the whole storage layer onto
    #: something like SQLAlchemy; both are out of scope for an
    #: infrastructure phase and were explicitly deferred (ADR-0076) rather
    #: than faked. Set this and :func:`validate_startup` will only warn
    #: that it is not yet honored -- ``database_path`` (SQLite) remains
    #: the only backend actually used.
    database_url: str | None = None
    #: Emit structured (JSON) logs instead of default stdlib formatting --
    #: on by default in ``production`` (see :func:`effective_json_logs`),
    #: overridable either way via the environment for local debugging.
    json_logs: bool | None = None

    # Notifications & Background Processing (Phase 58, ADR-0077).
    #: SMTP transport for real email delivery -- unset means email
    #: notifications are recorded (in-app) but never sent (delivery
    #: status ``SKIPPED``, never fabricated ``SENT``). No default host:
    #: there is no shared, safe-to-assume SMTP relay for a self-hosted
    #: single-install tool.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    #: The ``From`` address on every outbound email -- distinct from
    #: ``smtp_username`` since some providers authenticate under a
    #: different address than the one mail should appear to come from.
    smtp_from_address: str | None = None
    #: Reminders/digests are computed on a scheduled pass, not per
    #: request -- how often the background scheduler checks (minutes).
    reminder_interval_minutes: int = 60
    #: How long an already-read notification survives before the
    #: cleanup job deletes it (days).
    notification_retention_days: int = 30

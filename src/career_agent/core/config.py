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

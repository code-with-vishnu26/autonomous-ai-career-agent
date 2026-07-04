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
    exa_api_key: str | None = None
    google_cse_api_key: str | None = None
    google_cse_id: str | None = None
    database_path: str = "data/career_agent.db"
    #: Where generated resume files (DOCX/PDF, Phase 9/ADR-0033) are written.
    artifacts_dir: str = "data/artifacts"
    log_level: str = "INFO"

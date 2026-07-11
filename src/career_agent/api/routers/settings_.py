"""Read-only, redacted view of ``Settings`` for the dashboard's Settings page.

Named ``settings_`` (trailing underscore) to avoid shadowing
:mod:`career_agent.core.config`'s ``Settings`` import inside this same
package when both are imported together.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from career_agent.api.dependencies import get_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])

#: Field names never sent to the client -- API keys/tokens/credentials.
#: Everything else in ``Settings`` is a path, a flag, or a non-secret
#: preference already safe to display.
_SECRET_FIELDS = {
    "anthropic_api_key",
    "groq_api_key",
    "exa_api_key",
    "google_cse_api_key",
    "google_cse_id",
    "adzuna_app_id",
    "adzuna_app_key",
    "reed_api_key",
    "usajobs_api_key",
    "jooble_api_key",
    "telegram_bot_token",
    "telegram_chat_id",
    "ntfy_topic",
}


class RedactedSettings(BaseModel):
    """Non-secret settings plus a flag per secret naming whether it's set."""

    values: dict[str, object]
    configured_secrets: dict[str, bool]


@router.get("")
def read_settings() -> RedactedSettings:
    """Every non-secret setting, plus which secrets are configured (not values)."""
    dumped = get_settings().model_dump()
    values = {k: v for k, v in dumped.items() if k not in _SECRET_FIELDS}
    configured_secrets = {k: bool(dumped.get(k)) for k in _SECRET_FIELDS}
    return RedactedSettings(values=values, configured_secrets=configured_secrets)

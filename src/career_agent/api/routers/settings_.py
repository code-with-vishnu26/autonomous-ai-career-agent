"""Read-only, redacted view of ``Settings`` for the dashboard's Settings page.

Named ``settings_`` (trailing underscore) to avoid shadowing
:mod:`career_agent.core.config`'s ``Settings`` import inside this same
package when both are imported together.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from career_agent.api.dependencies import get_settings
from career_agent.api.security import get_current_user
from career_agent.domain.user import User

router = APIRouter(prefix="/api/settings", tags=["settings"])

#: Field names never sent to the client -- API keys/tokens/credentials.
#: Everything else in ``Settings`` is a path, a flag, or a non-secret
#: preference already safe to display. ``jwt_secret_key`` (Phase 56) is
#: the single most safety-critical value in this list -- leaking it would
#: let a caller forge an access token for any user id.
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
    "jwt_secret_key",
}


class RedactedSettings(BaseModel):
    """Non-secret settings plus a flag per secret naming whether it's set."""

    values: dict[str, object]
    configured_secrets: dict[str, bool]


@router.get("")
def read_settings(current_user: User = Depends(get_current_user)) -> RedactedSettings:
    """Every non-secret setting, plus which secrets are configured (not values).

    Requires authentication (Phase 56) -- this was anonymous-readable in
    Phase 54, when the API had no concept of a caller at all; now that one
    exists, an unauthenticated request has no business seeing even the
    redacted deployment configuration.
    """
    dumped = get_settings().model_dump()
    values = {k: v for k, v in dumped.items() if k not in _SECRET_FIELDS}
    configured_secrets = {k: bool(dumped.get(k)) for k in _SECRET_FIELDS}
    return RedactedSettings(values=values, configured_secrets=configured_secrets)

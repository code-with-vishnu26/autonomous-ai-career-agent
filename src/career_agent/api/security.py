"""Auth wiring for the dashboard API (Phase 56, ADR-0074).

Bridges :mod:`career_agent.core.security`'s pure functions to FastAPI: reads
the JWT secret from ``Settings`` (fail-closed if unset), extracts and
verifies the bearer access token on every protected route, and loads the
:class:`~career_agent.domain.user.User` it names.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from career_agent.api.dependencies import get_settings, get_user_store
from career_agent.core.config import Settings
from career_agent.core.security import InvalidTokenError, decode_access_token
from career_agent.domain.user import User

_bearer_scheme = HTTPBearer(auto_error=False)


class JwtNotConfiguredError(RuntimeError):
    """``Settings.jwt_secret_key`` is unset.

    The API refuses to sign or verify tokens rather than fall back to a
    shared, guessable default.
    """


def require_jwt_secret(settings: Settings = Depends(get_settings)) -> str:
    """The configured JWT secret, or a fail-closed 500 if none is set.

    A 500 (not a more specific 401/403) is deliberate: an unconfigured
    secret is a deployment misconfiguration, not something the caller did
    wrong -- every request would fail identically regardless of
    credentials, which is exactly what should surface as a server error.
    """
    if not settings.jwt_secret_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "JWT_SECRET_KEY is not configured -- the dashboard API "
                "cannot issue or verify sessions until it is set."
            ),
        )
    return settings.jwt_secret_key


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    secret_key: str = Depends(require_jwt_secret),
    user_store=Depends(get_user_store),
) -> User:
    """The authenticated caller, or a 401 if the bearer token is missing/invalid.

    Deliberately does not distinguish "no token" from "bad token" from
    "expired token" in the response -- all three are the same
    ``401 Unauthorized`` with the same generic message, so a client can't
    use the error shape to probe which case applied.
    """
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        claims = decode_access_token(credentials.credentials, secret_key=secret_key)
    except InvalidTokenError as exc:
        raise unauthorized from exc
    user = user_store.by_id(claims.user_id)
    if user is None:
        raise unauthorized
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """The authenticated caller, or a 403 if they aren't an admin.

    Declared for forward compatibility (``User.role`` already exists) --
    nothing in this phase actually grants a route admin-only access yet.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required."
        )
    return current_user

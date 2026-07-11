"""Password hashing and JWT encode/decode (Phase 56, ADR-0074).

Pure functions -- no storage, no HTTP, no ``Settings`` import (the secret/
expiry values are passed in by the caller, the same "config flows inward
by injection" discipline ``core/config.py``'s own docstring already
states as a hard rule elsewhere in this project). This keeps every
function here trivially unit-testable with a throwaway secret.

Lives in ``core/``, not ``domain/``: ``tests/domain/test_purity.py``
enforces that every ``domain/`` module imports only the standard library
or Pydantic (``bcrypt``/``jwt`` would trip it, and rightly so -- password
hashing and token signing are exactly the kind of external, replaceable
mechanism ``domain/`` is supposed to stay ignorant of, the same reasoning
that already keeps LLM clients and browser automation out of ``domain/``).
``User`` itself (id/email/hashed_password/role) is still a pure
``domain/user.py`` model; only the hashing/signing *mechanism* lives here.

Two token kinds, deliberately not interchangeable:

- **Access token**: short-lived (default 15 min), a signed JWT carrying
  ``sub`` (user id) and ``role``. Sent as ``Authorization: Bearer <token>``
  on every protected request; never persisted server-side, so it cannot be
  revoked early -- its short expiry is the only mitigation, which is why
  it stays short.
- **Refresh token**: long-lived (default 30 days), an opaque random
  string (**not** a JWT -- there is nothing to decode, only a hash to
  look up), persisted server-side as a hash
  (:class:`~career_agent.storage.sqlite.SqliteRefreshTokenStore`) so it
  *can* be revoked (logout, rotation-on-use, or an admin action). Never
  sent as a header; delivered only via an httpOnly cookie (ADR-0074).
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import bcrypt
import jwt

from career_agent.domain.user import UserRole

_JWT_ALGORITHM = "HS256"
TokenType = Literal["access"]


class InvalidTokenError(Exception):
    """An access token is malformed, expired, or signed with the wrong secret."""


def hash_password(plain_password: str) -> str:
    """Bcrypt hash, safe to store. Never reversible, never logged by callers."""
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode(
        "ascii"
    )


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """``True`` iff ``plain_password`` hashes to ``hashed_password``.

    Constant-time by construction (``bcrypt.checkpw``) -- never implemented
    as "hash and ``==``", which would leak timing information.
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except ValueError:
        # A corrupt/foreign hash format -- fail closed, never raise past
        # the caller as a 500 that might hint at why.
        return False


@dataclass(frozen=True)
class AccessTokenClaims:
    """What a decoded, verified access token actually asserts."""

    user_id: str
    role: UserRole
    expires_at: datetime


def create_access_token(
    *,
    user_id: str,
    role: UserRole,
    secret_key: str,
    expires_in_minutes: int,
    now: datetime | None = None,
) -> str:
    """A signed JWT asserting ``user_id``/``role``.

    Expires after ``expires_in_minutes`` minutes.
    """
    issued_at = now or datetime.now(UTC)
    expires_at = issued_at + timedelta(minutes=expires_in_minutes)
    payload = {
        "sub": user_id,
        "role": role,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, secret_key, algorithm=_JWT_ALGORITHM)


def decode_access_token(token: str, *, secret_key: str) -> AccessTokenClaims:
    """Verify signature + expiry and return the claims, or raise ``InvalidTokenError``.

    Never returns claims from an unverified or expired token -- ``jwt.decode``
    raises on both, and both are collapsed into the same
    :class:`InvalidTokenError` so callers can't accidentally branch on
    "expired vs. tampered" in a way that would help an attacker probe the
    difference.
    """
    try:
        payload = jwt.decode(token, secret_key, algorithms=[_JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
    try:
        return AccessTokenClaims(
            user_id=payload["sub"],
            role=payload["role"],
            expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
        )
    except (KeyError, TypeError) as exc:
        raise InvalidTokenError("access token missing required claims") from exc


def generate_refresh_token_value() -> str:
    """A cryptographically random opaque string -- never a JWT, nothing to decode."""
    return secrets.token_urlsafe(48)


def hash_opaque_token(raw_value: str) -> str:
    """SHA-256 over an opaque random token, stored instead of the token itself.

    Used for both refresh tokens and password-reset tokens -- not bcrypt:
    each is already 256+ bits of real entropy (unlike a human password),
    so a slow KDF buys nothing extra against brute force and would only
    slow down the login-refresh hot path. This mirrors the same reasoning
    ``domain.execution.confirmed_artifact_digest`` already used for a
    different "compare without storing the raw value" case.
    """
    return hashlib.sha256(raw_value.encode("utf-8")).hexdigest()


def generate_password_reset_token_value() -> str:
    """A cryptographically random opaque string for a password-reset link."""
    return secrets.token_urlsafe(32)

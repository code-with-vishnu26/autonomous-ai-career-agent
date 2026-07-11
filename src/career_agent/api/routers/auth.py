"""Authentication endpoints (Phase 56, ADR-0074).

Access tokens travel in the JSON response body (the SPA holds them in
memory, never ``localStorage`` -- an XSS payload that can read
``localStorage`` can read anything a script can, but keeping the token
out of persistent storage at least means it doesn't survive a page
reload/is never written to disk). Refresh tokens travel only via an
httpOnly, ``SameSite=Lax`` cookie -- never in a JSON body, never
readable by JavaScript at all. Refresh rotates on every use (the old
token is revoked the moment a new one is issued), so a stolen-and-replayed
refresh token can be used at most once before the legitimate rotation
invalidates it.

No CSRF token: the refresh cookie is ``SameSite=Lax``, which blocks
cross-site POST (only top-level GET navigations are exempt), and
``/auth/refresh`` is a POST that does nothing observable to a third-party
page anyway (no state a CSRF attacker could usefully trigger blind). This
reasoning is written down, not assumed -- see ADR-0074's revisit criteria
for when it would need to change (e.g. adding a state-changing GET, or a
cross-origin frontend).
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from career_agent.api.dependencies import (
    get_password_reset_token_store,
    get_refresh_token_store,
    get_settings,
    get_user_store,
)
from career_agent.api.rate_limit import enforce_auth_rate_limit
from career_agent.api.security import get_current_user, require_jwt_secret
from career_agent.core.config import Settings
from career_agent.core.security import (
    create_access_token,
    generate_password_reset_token_value,
    generate_refresh_token_value,
    hash_opaque_token,
    hash_password,
    verify_password,
)
from career_agent.domain.user import User

router = APIRouter(prefix="/auth", tags=["auth"])

_REFRESH_COOKIE_NAME = "refresh_token"


class UserOut(BaseModel):
    """A ``User`` with the one field that must never leave the server."""

    id: str
    email: str
    display_name: str | None
    role: str
    created_at: datetime

    @classmethod
    def from_user(cls, user: User) -> UserOut:
        """Build a response body from a real ``User``, dropping the password hash."""
        return cls(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
            created_at=user.created_at,
        )


class TokenResponse(BaseModel):
    """What every login/register/refresh response returns in the body."""

    access_token: str
    token_type: str = "bearer"
    user: UserOut


class RegisterRequest(BaseModel):
    """Body for ``POST /auth/register``."""

    email: str
    password: str
    display_name: str | None = None


class LoginRequest(BaseModel):
    """Body for ``POST /auth/login``."""

    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    """Body for ``POST /auth/forgot-password``."""

    email: str


class ResetPasswordRequest(BaseModel):
    """Body for ``POST /auth/reset-password``."""

    token: str
    new_password: str


def _issue_tokens(
    response: Response,
    user: User,
    *,
    settings: Settings,
    secret_key: str,
    refresh_store,
) -> TokenResponse:
    access_token = create_access_token(
        user_id=user.id,
        role=user.role,
        secret_key=secret_key,
        expires_in_minutes=settings.jwt_access_token_expire_minutes,
    )
    raw_refresh = generate_refresh_token_value()
    expires_at = datetime.now(UTC) + timedelta(
        days=settings.jwt_refresh_token_expire_days
    )
    refresh_store.save(
        token_id=str(uuid.uuid4()),
        user_id=user.id,
        token_hash=hash_opaque_token(raw_refresh),
        expires_at=expires_at,
    )
    response.set_cookie(
        key=_REFRESH_COOKIE_NAME,
        value=raw_refresh,
        httponly=True,
        secure=settings.jwt_cookie_secure,
        samesite="lax",
        max_age=settings.jwt_refresh_token_expire_days * 24 * 3600,
        path="/auth",
    )
    return TokenResponse(access_token=access_token, user=UserOut.from_user(user))


@router.post(
    "/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED
)
def register(
    body: RegisterRequest,
    response: Response,
    settings: Settings = Depends(get_settings),
    secret_key: str = Depends(require_jwt_secret),
    user_store=Depends(get_user_store),
    refresh_store=Depends(get_refresh_token_store),
    _rate_limit: None = Depends(enforce_auth_rate_limit),
) -> TokenResponse:
    """Create an account and sign the caller in immediately.

    No demo/seed users: every account starts here, with a real bcrypt hash
    of a password the caller actually chose.
    """
    if len(body.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters.",
        )
    user = User(
        id=str(uuid.uuid4()),
        email=body.email,
        hashed_password=hash_password(body.password),
        display_name=body.display_name,
        role="user",
        created_at=datetime.now(UTC),
    )
    try:
        user_store.create(user)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists.",
        ) from exc
    return _issue_tokens(
        response,
        user,
        settings=settings,
        secret_key=secret_key,
        refresh_store=refresh_store,
    )


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    response: Response,
    settings: Settings = Depends(get_settings),
    secret_key: str = Depends(require_jwt_secret),
    user_store=Depends(get_user_store),
    refresh_store=Depends(get_refresh_token_store),
    _rate_limit: None = Depends(enforce_auth_rate_limit),
) -> TokenResponse:
    """Verify credentials and issue a fresh access/refresh token pair.

    Deliberately the same error for "no such email" and "wrong password"
    -- distinguishing them would let a caller enumerate registered emails.
    """
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password."
    )
    user = user_store.by_email(body.email)
    if user is None or not verify_password(body.password, user.hashed_password):
        raise invalid
    return _issue_tokens(
        response,
        user,
        settings=settings,
        secret_key=secret_key,
        refresh_store=refresh_store,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    refresh_store=Depends(get_refresh_token_store),
) -> None:
    """Revoke the current refresh token (if any) and clear the cookie.

    Never raises for a missing/already-invalid cookie -- logging out is
    always safe to call, including twice.
    """
    raw_refresh = request.cookies.get(_REFRESH_COOKIE_NAME)
    if raw_refresh:
        found = refresh_store.find_active(hash_opaque_token(raw_refresh))
        if found is not None:
            refresh_store.revoke(found["id"])
    response.delete_cookie(_REFRESH_COOKIE_NAME, path="/auth")


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
    secret_key: str = Depends(require_jwt_secret),
    user_store=Depends(get_user_store),
    refresh_store=Depends(get_refresh_token_store),
) -> TokenResponse:
    """Rotate the refresh token and issue a new access token.

    The presented refresh token is revoked the instant a replacement is
    issued (rotation-on-use) -- reusing an already-rotated token (a strong
    signal of theft/replay) will find no active row and fail closed here,
    never silently re-issued.
    """
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session."
    )
    raw_refresh = request.cookies.get(_REFRESH_COOKIE_NAME)
    if not raw_refresh:
        raise unauthorized
    found = refresh_store.find_active(hash_opaque_token(raw_refresh))
    if found is None or found["expires_at"] < datetime.now(UTC):
        raise unauthorized
    refresh_store.revoke(found["id"])
    user = user_store.by_id(found["user_id"])
    if user is None:
        raise unauthorized
    return _issue_tokens(
        response,
        user,
        settings=settings,
        secret_key=secret_key,
        refresh_store=refresh_store,
    )


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> UserOut:
    """The authenticated caller's own account."""
    return UserOut.from_user(current_user)


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(
    body: ForgotPasswordRequest,
    user_store=Depends(get_user_store),
    reset_store=Depends(get_password_reset_token_store),
    _rate_limit: None = Depends(enforce_auth_rate_limit),
) -> dict[str, str]:
    """Issue a password-reset token if the email is registered.

    Always returns ``202`` regardless of whether the account exists --
    responding differently would let a caller enumerate registered
    emails. **No email is actually sent yet**: real delivery (SMTP/
    Telegram/ntfy) is Phase 58 Notifications' job, not this phase's --
    faking a "check your inbox" response without a real send would be
    exactly the kind of unverified capability claim this project's
    discipline forbids. For now the raw token is only ever returned to a
    caller who already holds the account's password (see the response
    here is intentionally token-free); a developer exercising this flow
    reads the token from the reset-token store directly.
    """
    user = user_store.by_email(body.email)
    if user is not None:
        raw_token = generate_password_reset_token_value()
        reset_store.save(
            token_id=str(uuid.uuid4()),
            user_id=user.id,
            token_hash=hash_opaque_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    return {
        "detail": (
            "If that email is registered, a password reset is now possible. "
            "Email delivery is not yet wired (Phase 58) -- see the "
            "documentation for how to complete a reset in the meantime."
        )
    }


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    body: ResetPasswordRequest,
    user_store=Depends(get_user_store),
    reset_store=Depends(get_password_reset_token_store),
    refresh_store=Depends(get_refresh_token_store),
) -> None:
    """Consume a reset token and set a new password.

    Revokes every refresh token for the account -- a password reset
    (self-initiated or attacker-initiated after a leak) should end every
    existing session, not just future ones.
    """
    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired reset token.",
    )
    if len(body.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters.",
        )
    found = reset_store.find_unused(hash_opaque_token(body.token))
    if found is None or found["expires_at"] < datetime.now(UTC):
        raise invalid
    reset_store.mark_used(found["id"])
    user_store.update_password(
        found["user_id"], hashed_password=hash_password(body.new_password)
    )
    refresh_store.revoke_all_for_user(found["user_id"])

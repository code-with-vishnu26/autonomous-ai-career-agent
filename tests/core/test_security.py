"""Phase 56 (ADR-0074): password hashing and JWT encode/decode."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from career_agent.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    generate_password_reset_token_value,
    generate_refresh_token_value,
    hash_opaque_token,
    hash_password,
    verify_password,
)


def test_hash_password_is_never_the_plaintext() -> None:
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"


def test_verify_password_accepts_the_right_password() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed) is True


def test_verify_password_rejects_the_wrong_password() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password("wrong password", hashed) is False


def test_verify_password_fails_closed_on_a_corrupt_hash() -> None:
    assert verify_password("anything", "not-a-real-bcrypt-hash") is False


def test_hash_password_is_salted_differently_each_time() -> None:
    a = hash_password("same password")
    b = hash_password("same password")
    assert a != b
    assert verify_password("same password", a)
    assert verify_password("same password", b)


def test_create_and_decode_access_token_round_trips() -> None:
    token = create_access_token(
        user_id="user-1", role="user", secret_key="s3cret", expires_in_minutes=15
    )
    claims = decode_access_token(token, secret_key="s3cret")
    assert claims.user_id == "user-1"
    assert claims.role == "user"


def test_decode_access_token_rejects_the_wrong_secret() -> None:
    token = create_access_token(
        user_id="user-1", role="user", secret_key="s3cret", expires_in_minutes=15
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, secret_key="wrong-secret")


def test_decode_access_token_rejects_an_expired_token() -> None:
    issued_at = datetime.now(UTC) - timedelta(minutes=30)
    token = create_access_token(
        user_id="user-1",
        role="user",
        secret_key="s3cret",
        expires_in_minutes=15,
        now=issued_at,
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, secret_key="s3cret")


def test_decode_access_token_rejects_garbage() -> None:
    with pytest.raises(InvalidTokenError):
        decode_access_token("not-a-jwt-at-all", secret_key="s3cret")


def test_refresh_token_values_are_unique_and_never_a_jwt() -> None:
    a = generate_refresh_token_value()
    b = generate_refresh_token_value()
    assert a != b
    assert a.count(".") != 2  # a JWT always has exactly two dots; this must not


def test_hash_opaque_token_is_deterministic_but_not_reversible() -> None:
    raw = generate_refresh_token_value()
    assert hash_opaque_token(raw) == hash_opaque_token(raw)
    assert hash_opaque_token(raw) != raw


def test_password_reset_token_values_are_unique() -> None:
    a = generate_password_reset_token_value()
    b = generate_password_reset_token_value()
    assert a != b

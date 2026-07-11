"""Phase 56 (ADR-0074): ``User`` is pure data with a real email check."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from career_agent.domain.user import User


def _user(**overrides: object) -> User:
    fields = {
        "id": "user-1",
        "email": "person@example.com",
        "hashed_password": "$2b$fake-hash",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    fields.update(overrides)
    return User(**fields)


def test_defaults_are_role_user_and_no_display_name() -> None:
    user = _user()
    assert user.role == "user"
    assert user.display_name is None


def test_email_is_normalized_to_lowercase() -> None:
    user = _user(email="Person@EXAMPLE.com")
    assert user.email == "person@example.com"


def test_email_is_stripped_of_surrounding_whitespace() -> None:
    user = _user(email="  person@example.com  ")
    assert user.email == "person@example.com"


@pytest.mark.parametrize(
    "bad_email", ["not-an-email", "missing-domain@", "@missing-local.com", ""]
)
def test_invalid_email_is_rejected(bad_email: str) -> None:
    with pytest.raises(ValidationError):
        _user(email=bad_email)


def test_round_trips_through_json() -> None:
    user = _user(display_name="Ada Lovelace", role="admin")
    restored = User.model_validate_json(user.model_dump_json())
    assert restored == user

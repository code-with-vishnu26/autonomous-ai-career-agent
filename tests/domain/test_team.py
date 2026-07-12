"""Phase 60 (ADR-0078): Membership + Invitation domain models."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from career_agent.domain.team import Invitation, Membership


def _invitation(**overrides: object) -> Invitation:
    now = datetime.now(UTC)
    fields: dict[object, object] = {
        "id": "i1",
        "organization_id": "o1",
        "email": "a@example.com",
        "role": "member",
        "invited_by_user_id": "u1",
        "token_hash": "hash",
        "created_at": now,
        "expires_at": now + timedelta(days=7),
    }
    fields.update(overrides)
    return Invitation(**fields)


def test_membership_carries_organization_and_user_id():
    membership = Membership(
        id="m1",
        organization_id="o1",
        user_id="u1",
        role="owner",
        joined_at=datetime.now(UTC),
    )
    assert membership.organization_id == "o1"
    assert membership.user_id == "u1"


def test_invitation_status_pending_by_default():
    invitation = _invitation()
    assert invitation.status(now=datetime.now(UTC)) == "PENDING"


def test_invitation_status_expired_after_expires_at():
    invitation = _invitation()
    future = invitation.expires_at + timedelta(seconds=1)
    assert invitation.status(now=future) == "EXPIRED"


def test_invitation_status_accepted_takes_priority_over_expired():
    now = datetime.now(UTC)
    invitation = _invitation(accepted_at=now, expires_at=now - timedelta(days=1))
    assert invitation.status(now=now) == "ACCEPTED"


def test_invitation_status_revoked_takes_priority_over_accepted():
    now = datetime.now(UTC)
    invitation = _invitation(accepted_at=now, revoked_at=now)
    assert invitation.status(now=now) == "REVOKED"

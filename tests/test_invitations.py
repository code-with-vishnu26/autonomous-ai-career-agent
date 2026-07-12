"""Phase 60 (ADR-0078): invitations.py composition helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from career_agent.core.security import hash_opaque_token
from career_agent.domain.organization import Organization
from career_agent.domain.user import User
from career_agent.integrations.email import EmailSendError
from career_agent.invitations import (
    InvitationError,
    accept_invitation,
    create_invitation,
    send_invitation,
)
from career_agent.storage.sqlite import (
    SqliteDeliveryAttemptStore,
    SqliteNotificationPreferencesStore,
    SqliteNotificationStore,
    SqliteUserStore,
    SqliteWebhookSubscriptionStore,
)
from career_agent.storage.team_store import SqliteInvitationStore, SqliteMembershipStore

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


class _FakeEmailSender:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[tuple[str, str, str]] = []

    async def send(self, *, to: str, subject: str, body: str) -> None:
        if self.fail:
            raise EmailSendError("SMTP down")
        self.sent.append((to, subject, body))


def _organization(**overrides: object) -> Organization:
    fields: dict[object, object] = {
        "id": "o1",
        "name": "Acme",
        "slug": "acme",
        "created_by_user_id": "u1",
        "created_at": _NOW,
    }
    fields.update(overrides)
    return Organization(**fields)


def test_create_invitation_stores_only_the_hash_not_the_raw_token(
    tmp_path: Path,
) -> None:
    invitation_store = SqliteInvitationStore(tmp_path / "db.sqlite")
    invitation, raw_token = create_invitation(
        organization_id="o1",
        invited_by_user_id="u1",
        email="Someone@Example.com",
        role="member",
        invitation_store=invitation_store,
        now=_NOW,
    )
    assert invitation.email == "someone@example.com"
    assert invitation.token_hash == hash_opaque_token(raw_token)
    assert raw_token not in invitation.model_dump_json()


def test_create_invitation_expires_after_default_window(tmp_path: Path) -> None:
    invitation_store = SqliteInvitationStore(tmp_path / "db.sqlite")
    invitation, _token = create_invitation(
        organization_id="o1",
        invited_by_user_id="u1",
        email="a@example.com",
        role="member",
        invitation_store=invitation_store,
        now=_NOW,
    )
    assert invitation.expires_at > _NOW


def test_accept_invitation_creates_membership_with_the_invited_role(
    tmp_path: Path,
) -> None:
    db = tmp_path / "db.sqlite"
    invitation_store = SqliteInvitationStore(db)
    membership_store = SqliteMembershipStore(db)
    invitation, raw_token = create_invitation(
        organization_id="o1",
        invited_by_user_id="u1",
        email="new@example.com",
        role="recruiter",
        invitation_store=invitation_store,
        now=_NOW,
    )

    membership = accept_invitation(
        token=raw_token,
        user_id="u2",
        user_email="new@example.com",
        invitation_store=invitation_store,
        membership_store=membership_store,
        now=_NOW,
    )

    assert membership.role == "recruiter"
    assert membership.organization_id == "o1"
    assert invitation_store.get(invitation.id).accepted_at == _NOW


def test_accept_invitation_unknown_token_raises_not_found(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    invitation_store = SqliteInvitationStore(db)
    membership_store = SqliteMembershipStore(db)

    with pytest.raises(InvitationError) as excinfo:
        accept_invitation(
            token="not-a-real-token",
            user_id="u2",
            user_email="new@example.com",
            invitation_store=invitation_store,
            membership_store=membership_store,
            now=_NOW,
        )
    assert excinfo.value.reason == "not_found"


def test_accept_invitation_email_mismatch_raises(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    invitation_store = SqliteInvitationStore(db)
    membership_store = SqliteMembershipStore(db)
    _invitation, raw_token = create_invitation(
        organization_id="o1",
        invited_by_user_id="u1",
        email="expected@example.com",
        role="member",
        invitation_store=invitation_store,
        now=_NOW,
    )

    with pytest.raises(InvitationError) as excinfo:
        accept_invitation(
            token=raw_token,
            user_id="u2",
            user_email="different@example.com",
            invitation_store=invitation_store,
            membership_store=membership_store,
            now=_NOW,
        )
    assert excinfo.value.reason == "email_mismatch"


def test_accept_invitation_already_revoked_raises_not_pending(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    invitation_store = SqliteInvitationStore(db)
    membership_store = SqliteMembershipStore(db)
    invitation, raw_token = create_invitation(
        organization_id="o1",
        invited_by_user_id="u1",
        email="a@example.com",
        role="member",
        invitation_store=invitation_store,
        now=_NOW,
    )
    invitation_store.revoke(invitation.id, revoked_at=_NOW)

    with pytest.raises(InvitationError) as excinfo:
        accept_invitation(
            token=raw_token,
            user_id="u2",
            user_email="a@example.com",
            invitation_store=invitation_store,
            membership_store=membership_store,
            now=_NOW,
        )
    assert excinfo.value.reason == "not_pending"


def test_accept_invitation_already_member_raises(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    invitation_store = SqliteInvitationStore(db)
    membership_store = SqliteMembershipStore(db)
    invitation, raw_token = create_invitation(
        organization_id="o1",
        invited_by_user_id="u1",
        email="a@example.com",
        role="member",
        invitation_store=invitation_store,
        now=_NOW,
    )
    accept_invitation(
        token=raw_token,
        user_id="u2",
        user_email="a@example.com",
        invitation_store=invitation_store,
        membership_store=membership_store,
        now=_NOW,
    )
    invitation2, raw_token2 = create_invitation(
        organization_id="o1",
        invited_by_user_id="u1",
        email="a@example.com",
        role="member",
        invitation_store=invitation_store,
        now=_NOW,
    )

    with pytest.raises(InvitationError) as excinfo:
        accept_invitation(
            token=raw_token2,
            user_id="u2",
            user_email="a@example.com",
            invitation_store=invitation_store,
            membership_store=membership_store,
            now=_NOW,
        )
    assert excinfo.value.reason == "already_member"
    assert invitation2.id != invitation.id


async def test_send_invitation_emails_a_brand_new_invitee_directly(
    tmp_path: Path,
) -> None:
    db = tmp_path / "db.sqlite"
    invitation_store = SqliteInvitationStore(db)
    user_store = SqliteUserStore(db)
    sender = _FakeEmailSender()
    invitation, raw_token = create_invitation(
        organization_id="o1",
        invited_by_user_id="u1",
        email="brandnew@example.com",
        role="member",
        invitation_store=invitation_store,
        now=_NOW,
    )

    await send_invitation(
        invitation=invitation,
        raw_token=raw_token,
        organization=_organization(),
        invite_base_url="https://app.invalid/accept-invite",
        email_sender=sender,
        user_store=user_store,
        notification_store=SqliteNotificationStore(db),
        notification_preferences_store=SqliteNotificationPreferencesStore(db),
        delivery_store=SqliteDeliveryAttemptStore(db),
        webhook_store=SqliteWebhookSubscriptionStore(db),
        now=_NOW,
    )

    assert len(sender.sent) == 1
    assert sender.sent[0][0] == "brandnew@example.com"
    assert raw_token in sender.sent[0][2]


async def test_send_invitation_creates_in_app_notification_for_existing_user(
    tmp_path: Path,
) -> None:
    db = tmp_path / "db.sqlite"
    invitation_store = SqliteInvitationStore(db)
    user_store = SqliteUserStore(db)
    existing_user = User(
        id="u2", email="existing@example.com", hashed_password="x", created_at=_NOW
    )
    user_store.create(existing_user)
    notification_store = SqliteNotificationStore(db)
    invitation, raw_token = create_invitation(
        organization_id="o1",
        invited_by_user_id="u1",
        email="existing@example.com",
        role="member",
        invitation_store=invitation_store,
        now=_NOW,
    )

    await send_invitation(
        invitation=invitation,
        raw_token=raw_token,
        organization=_organization(),
        invite_base_url="https://app.invalid/accept-invite",
        email_sender=None,
        user_store=user_store,
        notification_store=notification_store,
        notification_preferences_store=SqliteNotificationPreferencesStore(db),
        delivery_store=SqliteDeliveryAttemptStore(db),
        webhook_store=SqliteWebhookSubscriptionStore(db),
        now=_NOW,
    )

    notifications = notification_store.by_user(existing_user.id)
    assert any(n.category == "invitation_received" for n in notifications)


async def test_send_invitation_never_raises_when_email_delivery_fails(
    tmp_path: Path,
) -> None:
    db = tmp_path / "db.sqlite"
    invitation_store = SqliteInvitationStore(db)
    user_store = SqliteUserStore(db)
    invitation, raw_token = create_invitation(
        organization_id="o1",
        invited_by_user_id="u1",
        email="brandnew@example.com",
        role="member",
        invitation_store=invitation_store,
        now=_NOW,
    )

    await send_invitation(
        invitation=invitation,
        raw_token=raw_token,
        organization=_organization(),
        invite_base_url="https://app.invalid/accept-invite",
        email_sender=_FakeEmailSender(fail=True),
        user_store=user_store,
        notification_store=SqliteNotificationStore(db),
        notification_preferences_store=SqliteNotificationPreferencesStore(db),
        delivery_store=SqliteDeliveryAttemptStore(db),
        webhook_store=SqliteWebhookSubscriptionStore(db),
        now=_NOW,
    )
    # Reaching here (no exception) is the assertion: "notify, never gate".

"""Invitation composition helpers (Phase 60, ADR-0078).

Top-level, same reasoning as ``organizations.py``/``scheduler.py``: this
composes domain object construction (a real random token, hashed before
storage -- the same "store a hash, never the token"
:class:`~career_agent.storage.sqlite.SqlitePasswordResetTokenStore`
discipline) with delivery. **Never duplicates email logic**: delivery
always goes through the exact same
:func:`~career_agent.scheduler.build_email_sender`/
:class:`~career_agent.integrations.email.EmailSender` Phase 58 already
built, and -- when the invited email already has an account -- the exact
same :class:`~career_agent.agents.notifications.engine.NotificationEngine`
/:class:`~career_agent.agents.notifications.dispatcher.NotificationDispatcher`
every other real trigger event already uses. A brand-new invitee (no
account yet) has no ``user_id`` for an in-app row to attach to -- that
case falls back to a direct :class:`EmailSender` call, named here as
exactly that, not silently skipped.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta
from typing import Literal

from career_agent.agents.notifications.dispatcher import NotificationDispatcher
from career_agent.agents.notifications.engine import NotificationEngine
from career_agent.agents.notifications.templates import invitation_email
from career_agent.core.security import hash_opaque_token
from career_agent.domain.organization import Organization
from career_agent.domain.roles import Role
from career_agent.domain.team import Invitation, Membership
from career_agent.integrations.email import EmailSender, EmailSendError
from career_agent.storage.sqlite import (
    SqliteDeliveryAttemptStore,
    SqliteNotificationPreferencesStore,
    SqliteNotificationStore,
    SqliteUserStore,
    SqliteWebhookSubscriptionStore,
)
from career_agent.storage.team_store import SqliteInvitationStore, SqliteMembershipStore

_DEFAULT_EXPIRY_DAYS = 7

InvitationErrorReason = Literal[
    "not_found", "not_pending", "email_mismatch", "already_member"
]


class InvitationError(Exception):
    """Accepting an invitation failed -- ``reason`` names exactly why."""

    def __init__(self, reason: InvitationErrorReason) -> None:
        """Carry the specific, callers-can-branch-on failure reason."""
        self.reason = reason
        super().__init__(reason)


def create_invitation(
    *,
    organization_id: str,
    invited_by_user_id: str,
    email: str,
    role: Role,
    invitation_store: SqliteInvitationStore,
    now: datetime,
    expires_in_days: int = _DEFAULT_EXPIRY_DAYS,
) -> tuple[Invitation, str]:
    """Create a real, hashed-token invitation. Returns ``(invitation, raw_token)``.

    ``raw_token`` is the only time the real value is ever available --
    only the hash is persisted.
    """
    raw_token = secrets.token_urlsafe(32)
    invitation = Invitation(
        id=str(uuid.uuid4()),
        organization_id=organization_id,
        email=email.strip().lower(),
        role=role,
        invited_by_user_id=invited_by_user_id,
        token_hash=hash_opaque_token(raw_token),
        created_at=now,
        expires_at=now + timedelta(days=expires_in_days),
    )
    invitation_store.create(invitation)
    return invitation, raw_token


async def send_invitation(
    *,
    invitation: Invitation,
    raw_token: str,
    organization: Organization,
    invite_base_url: str,
    email_sender: EmailSender | None,
    user_store: SqliteUserStore,
    notification_store: SqliteNotificationStore,
    notification_preferences_store: SqliteNotificationPreferencesStore,
    delivery_store: SqliteDeliveryAttemptStore,
    webhook_store: SqliteWebhookSubscriptionStore,
    now: datetime,
) -> None:
    """Deliver an invitation. Never blocks/raises past creation -- "notify, never gate".

    If the invited email already has an account, this is a real trigger
    event exactly like every other one in ``agents/notifications/`` --
    the full ``NotificationEngine``/``NotificationDispatcher`` path runs
    (in-app + the account's own email/webhook preferences). Otherwise
    (no account yet), only a direct email send is attempted, since there
    is no ``user_id`` an in-app row could ever belong to.
    """
    invite_link = f"{invite_base_url}?token={raw_token}"
    subject, body = invitation_email(
        organization_name=organization.name,
        role=invitation.role,
        invite_link=invite_link,
    )
    existing_user = user_store.by_email(invitation.email)
    if existing_user is not None:
        notification = NotificationEngine(notification_store).create(
            user_id=existing_user.id,
            type="INFO",
            category="invitation_received",
            title=subject,
            message=body,
            now=now,
        )
        dispatcher = NotificationDispatcher(
            delivery_store=delivery_store,
            email_sender=email_sender,
            webhook_sender=None,
        )
        preferences = notification_preferences_store.get_or_default(existing_user.id)
        try:
            await dispatcher.dispatch(
                notification,
                user_id=existing_user.id,
                preferences=preferences,
                email_address=existing_user.email,
                webhook_url=webhook_store.get(existing_user.id),
                now=now,
            )
        except Exception:  # noqa: BLE001 -- notify, never gate (ADR-0005)
            pass
        return
    if email_sender is None:
        return
    try:
        await email_sender.send(to=invitation.email, subject=subject, body=body)
    except EmailSendError:
        pass


def accept_invitation(
    *,
    token: str,
    user_id: str,
    user_email: str,
    invitation_store: SqliteInvitationStore,
    membership_store: SqliteMembershipStore,
    now: datetime,
) -> Membership:
    """Redeem a real invitation token into a real ``Membership``.

    Raises :class:`InvitationError` with a specific ``reason`` for every
    failure mode -- never a generic exception a caller has to string-match.
    """
    invitation = invitation_store.get_by_token_hash(hash_opaque_token(token))
    if invitation is None:
        raise InvitationError("not_found")
    if invitation.status(now=now) != "PENDING":
        raise InvitationError("not_pending")
    if invitation.email != user_email.strip().lower():
        raise InvitationError("email_mismatch")
    existing_membership = membership_store.get(
        organization_id=invitation.organization_id, user_id=user_id
    )
    if existing_membership is not None:
        raise InvitationError("already_member")
    membership = Membership(
        id=str(uuid.uuid4()),
        organization_id=invitation.organization_id,
        user_id=user_id,
        role=invitation.role,
        joined_at=now,
    )
    membership_store.create(membership)
    invitation_store.mark_accepted(invitation.id, accepted_at=now)
    return membership

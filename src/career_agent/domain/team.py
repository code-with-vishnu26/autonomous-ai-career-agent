"""Membership + Invitation: who belongs to an Organization, and how they join.

Phase 60, ADR-0078. Both models carry ``organization_id`` *and* the
relevant identity field explicitly (``user_id`` on ``Membership``,
``email`` on ``Invitation``) rather than denormalizing anything further
-- the same "organization_id + user_id, never user_id alone" discipline
this phase's brief asks for, applied to the two models that are
genuinely new data (as opposed to the nine pre-existing personal-resource
tables, which stay user_id-scoped; see ADR-0078's explicit scoping
section for why those are not retrofitted in this phase).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from .roles import Role

#: - ``PENDING``: sent, not yet acted on.
#: - ``ACCEPTED``: the invited email registered/logged in and accepted --
#:   a real ``Membership`` row now exists for them.
#: - ``REVOKED``: an admin/owner cancelled it before it was accepted.
#: - ``EXPIRED``: never acted on before ``expires_at`` -- computed from
#:   ``expires_at``/``accepted_at``/``revoked_at``, not its own persisted
#:   state (nothing to keep in sync).
InvitationStatus = Literal["PENDING", "ACCEPTED", "REVOKED", "EXPIRED"]


class Membership(BaseModel):
    """One user's role within one organization. Exactly one row per pair."""

    id: str
    organization_id: str
    user_id: str
    role: Role
    joined_at: datetime


class Invitation(BaseModel):
    """One pending (or resolved) invite to join an organization by email.

    ``token_hash`` follows the exact "store a hash, not the token"
    discipline :class:`~career_agent.storage.sqlite.SqlitePasswordResetTokenStore`
    already established -- the raw token is only ever handed to the
    invited email's link, never persisted.
    """

    id: str
    organization_id: str
    email: str
    role: Role
    invited_by_user_id: str
    token_hash: str
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None = None
    revoked_at: datetime | None = None

    def status(self, *, now: datetime) -> InvitationStatus:
        """Derive the invitation's status -- never persisted redundantly."""
        if self.revoked_at is not None:
            return "REVOKED"
        if self.accepted_at is not None:
            return "ACCEPTED"
        if now >= self.expires_at:
            return "EXPIRED"
        return "PENDING"

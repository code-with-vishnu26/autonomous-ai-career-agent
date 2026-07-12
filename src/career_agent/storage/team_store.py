"""SqliteMembershipStore + SqliteInvitationStore (Phase 60, ADR-0078).

Same shared-file, split-for-readability shape as ``organization_store.py``.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from career_agent.domain.roles import Role
from career_agent.domain.team import Invitation, Membership
from career_agent.storage.sqlite import _connect

_MEMBERSHIP_SCHEMA = """
CREATE TABLE IF NOT EXISTS memberships (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    UNIQUE(organization_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_memberships_organization
    ON memberships(organization_id);
CREATE INDEX IF NOT EXISTS idx_memberships_user ON memberships(user_id);
"""

_INVITATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS invitations (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    token_hash TEXT UNIQUE NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_invitations_organization
    ON invitations(organization_id);
"""


class SqliteMembershipStore:
    """Who belongs to which organization, and with what role."""

    def __init__(self, path: Path) -> None:
        """Open (creating if needed) the SQLite database at ``path``."""
        self._path = path
        with _connect(path) as connection:
            connection.executescript(_MEMBERSHIP_SCHEMA)

    def create(self, membership: Membership) -> None:
        """Insert a new membership.

        Raises ``sqlite3.IntegrityError`` if already a member.
        """
        with _connect(self._path) as connection:
            connection.execute(
                "INSERT INTO memberships (id, organization_id, user_id, payload)"
                " VALUES (?, ?, ?, ?)",
                (
                    membership.id,
                    membership.organization_id,
                    membership.user_id,
                    membership.model_dump_json(),
                ),
            )

    def get(self, *, organization_id: str, user_id: str) -> Membership | None:
        """One user's membership in one organization, or ``None`` if not a member."""
        with _connect(self._path) as connection:
            row = connection.execute(
                "SELECT payload FROM memberships"
                " WHERE organization_id = ? AND user_id = ?",
                (organization_id, user_id),
            ).fetchone()
        return Membership.model_validate(json.loads(row["payload"])) if row else None

    def by_organization(self, organization_id: str) -> list[Membership]:
        """Every member of one organization."""
        with _connect(self._path) as connection:
            rows = connection.execute(
                "SELECT payload FROM memberships WHERE organization_id = ?",
                (organization_id,),
            ).fetchall()
        return [Membership.model_validate(json.loads(row["payload"])) for row in rows]

    def by_user(self, user_id: str) -> list[Membership]:
        """Every organization one user belongs to."""
        with _connect(self._path) as connection:
            rows = connection.execute(
                "SELECT payload FROM memberships WHERE user_id = ?", (user_id,)
            ).fetchall()
        return [Membership.model_validate(json.loads(row["payload"])) for row in rows]

    def update_role(self, *, organization_id: str, user_id: str, role: Role) -> bool:
        """Change a member's role; returns whether a row was actually updated."""
        membership = self.get(organization_id=organization_id, user_id=user_id)
        if membership is None:
            return False
        updated = membership.model_copy(update={"role": role})
        with _connect(self._path) as connection:
            connection.execute(
                "UPDATE memberships SET payload = ?"
                " WHERE organization_id = ? AND user_id = ?",
                (updated.model_dump_json(), organization_id, user_id),
            )
        return True

    def remove(self, *, organization_id: str, user_id: str) -> bool:
        """Remove (suspend) a member; returns whether a row was actually removed."""
        with _connect(self._path) as connection:
            cursor = connection.execute(
                "DELETE FROM memberships WHERE organization_id = ? AND user_id = ?",
                (organization_id, user_id),
            )
            return cursor.rowcount > 0


class SqliteInvitationStore:
    """Pending/resolved invitations to join an organization."""

    def __init__(self, path: Path) -> None:
        """Open (creating if needed) the SQLite database at ``path``."""
        self._path = path
        with _connect(path) as connection:
            connection.executescript(_INVITATION_SCHEMA)

    def create(self, invitation: Invitation) -> None:
        """Insert a new invitation.

        Raises ``sqlite3.IntegrityError`` on a token-hash clash.
        """
        with _connect(self._path) as connection:
            connection.execute(
                "INSERT INTO invitations (id, organization_id, token_hash, payload)"
                " VALUES (?, ?, ?, ?)",
                (
                    invitation.id,
                    invitation.organization_id,
                    invitation.token_hash,
                    invitation.model_dump_json(),
                ),
            )

    def get(self, invitation_id: str) -> Invitation | None:
        """One invitation by id, or ``None``."""
        with _connect(self._path) as connection:
            row = connection.execute(
                "SELECT payload FROM invitations WHERE id = ?", (invitation_id,)
            ).fetchone()
        return Invitation.model_validate(json.loads(row["payload"])) if row else None

    def get_by_token_hash(self, token_hash: str) -> Invitation | None:
        """The invitation whose token hashes to ``token_hash``, or ``None``."""
        with _connect(self._path) as connection:
            row = connection.execute(
                "SELECT payload FROM invitations WHERE token_hash = ?", (token_hash,)
            ).fetchone()
        return Invitation.model_validate(json.loads(row["payload"])) if row else None

    def by_organization(self, organization_id: str) -> list[Invitation]:
        """Every invitation ever sent for one organization, newest first."""
        with _connect(self._path) as connection:
            rows = connection.execute(
                "SELECT payload FROM invitations WHERE organization_id = ?",
                (organization_id,),
            ).fetchall()
        invitations = [
            Invitation.model_validate(json.loads(row["payload"])) for row in rows
        ]
        return sorted(
            invitations, key=lambda invitation: invitation.created_at, reverse=True
        )

    def _save(self, invitation: Invitation) -> None:
        with _connect(self._path) as connection:
            connection.execute(
                "UPDATE invitations SET payload = ? WHERE id = ?",
                (invitation.model_dump_json(), invitation.id),
            )

    def mark_accepted(self, invitation_id: str, *, accepted_at: datetime) -> bool:
        """Mark an invitation accepted; returns whether it existed and was pending."""
        invitation = self.get(invitation_id)
        if invitation is None:
            return False
        self._save(invitation.model_copy(update={"accepted_at": accepted_at}))
        return True

    def revoke(self, invitation_id: str, *, revoked_at: datetime) -> bool:
        """Revoke an invitation; returns whether it existed."""
        invitation = self.get(invitation_id)
        if invitation is None:
            return False
        self._save(invitation.model_copy(update={"revoked_at": revoked_at}))
        return True

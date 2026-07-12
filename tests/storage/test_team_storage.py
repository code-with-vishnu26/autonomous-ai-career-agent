"""Phase 60 (ADR-0078): SqliteMembershipStore + SqliteInvitationStore."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from career_agent.domain.team import Invitation, Membership
from career_agent.storage.team_store import SqliteInvitationStore, SqliteMembershipStore

_FIXED_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _membership(**overrides: object) -> Membership:
    fields: dict[object, object] = {
        "id": "m1",
        "organization_id": "o1",
        "user_id": "u1",
        "role": "owner",
        "joined_at": _FIXED_NOW,
    }
    fields.update(overrides)
    return Membership(**fields)


def _invitation(**overrides: object) -> Invitation:
    fields: dict[object, object] = {
        "id": "i1",
        "organization_id": "o1",
        "email": "a@example.com",
        "role": "member",
        "invited_by_user_id": "u1",
        "token_hash": "hash1",
        "created_at": _FIXED_NOW,
        "expires_at": _FIXED_NOW + timedelta(days=7),
    }
    fields.update(overrides)
    return Invitation(**fields)


def test_membership_create_and_get(tmp_path: Path) -> None:
    store = SqliteMembershipStore(tmp_path / "db.sqlite")
    store.create(_membership())
    assert store.get(organization_id="o1", user_id="u1") == _membership()


def test_membership_get_returns_none_when_not_a_member(tmp_path: Path) -> None:
    store = SqliteMembershipStore(tmp_path / "db.sqlite")
    assert store.get(organization_id="o1", user_id="u1") is None


def test_membership_by_organization(tmp_path: Path) -> None:
    store = SqliteMembershipStore(tmp_path / "db.sqlite")
    store.create(_membership(id="m1", user_id="u1"))
    store.create(_membership(id="m2", user_id="u2", role="member"))
    members = store.by_organization("o1")
    assert {m.user_id for m in members} == {"u1", "u2"}


def test_membership_by_user(tmp_path: Path) -> None:
    store = SqliteMembershipStore(tmp_path / "db.sqlite")
    store.create(_membership(id="m1", organization_id="o1"))
    store.create(_membership(id="m2", organization_id="o2"))
    memberships = store.by_user("u1")
    assert {m.organization_id for m in memberships} == {"o1", "o2"}


def test_update_role(tmp_path: Path) -> None:
    store = SqliteMembershipStore(tmp_path / "db.sqlite")
    store.create(_membership(role="member"))
    updated = store.update_role(organization_id="o1", user_id="u1", role="admin")
    assert updated is True
    assert store.get(organization_id="o1", user_id="u1").role == "admin"


def test_update_role_unknown_member_returns_false(tmp_path: Path) -> None:
    store = SqliteMembershipStore(tmp_path / "db.sqlite")
    assert store.update_role(organization_id="o1", user_id="u1", role="admin") is False


def test_remove_member(tmp_path: Path) -> None:
    store = SqliteMembershipStore(tmp_path / "db.sqlite")
    store.create(_membership())
    assert store.remove(organization_id="o1", user_id="u1") is True
    assert store.get(organization_id="o1", user_id="u1") is None


def test_remove_unknown_member_returns_false(tmp_path: Path) -> None:
    store = SqliteMembershipStore(tmp_path / "db.sqlite")
    assert store.remove(organization_id="o1", user_id="u1") is False


def test_invitation_create_and_get(tmp_path: Path) -> None:
    store = SqliteInvitationStore(tmp_path / "db.sqlite")
    store.create(_invitation())
    assert store.get("i1") == _invitation()


def test_invitation_get_by_token_hash(tmp_path: Path) -> None:
    store = SqliteInvitationStore(tmp_path / "db.sqlite")
    store.create(_invitation())
    assert store.get_by_token_hash("hash1") == _invitation()
    assert store.get_by_token_hash("unknown") is None


def test_invitation_by_organization_newest_first(tmp_path: Path) -> None:
    store = SqliteInvitationStore(tmp_path / "db.sqlite")
    older = datetime(2020, 1, 1, tzinfo=UTC)
    newer = datetime(2026, 1, 1, tzinfo=UTC)
    store.create(
        _invitation(
            id="old",
            token_hash="h-old",
            created_at=older,
            expires_at=older + timedelta(days=7),
        )
    )
    store.create(
        _invitation(
            id="new",
            token_hash="h-new",
            created_at=newer,
            expires_at=newer + timedelta(days=7),
        )
    )
    invitations = store.by_organization("o1")
    assert [i.id for i in invitations] == ["new", "old"]


def test_mark_accepted(tmp_path: Path) -> None:
    store = SqliteInvitationStore(tmp_path / "db.sqlite")
    store.create(_invitation())
    now = datetime.now(UTC)
    assert store.mark_accepted("i1", accepted_at=now) is True
    assert store.get("i1").accepted_at == now


def test_mark_accepted_unknown_returns_false(tmp_path: Path) -> None:
    store = SqliteInvitationStore(tmp_path / "db.sqlite")
    assert store.mark_accepted("missing", accepted_at=datetime.now(UTC)) is False


def test_revoke(tmp_path: Path) -> None:
    store = SqliteInvitationStore(tmp_path / "db.sqlite")
    store.create(_invitation())
    now = datetime.now(UTC)
    assert store.revoke("i1", revoked_at=now) is True
    assert store.get("i1").revoked_at == now

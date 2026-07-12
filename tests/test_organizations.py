"""Phase 60 (ADR-0078): organizations.py composition helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from career_agent.domain.user import User
from career_agent.organizations import (
    create_personal_organization,
    migrate_users_without_organization,
    slugify,
    unique_slug,
)
from career_agent.storage.organization_store import SqliteOrganizationStore
from career_agent.storage.sqlite import SqliteUserStore
from career_agent.storage.team_store import SqliteMembershipStore

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _user(**overrides: object) -> User:
    fields: dict[object, object] = {
        "id": str(uuid.uuid4()),
        "email": "ada@example.com",
        "hashed_password": "x",
        "created_at": _NOW,
    }
    fields.update(overrides)
    return User(**fields)


def test_slugify_lowercases_and_hyphenates():
    assert slugify("Ada Lovelace") == "ada-lovelace"


def test_slugify_falls_back_to_org_when_nothing_left():
    assert slugify("!!!") == "org"


def test_unique_slug_appends_suffix_on_collision(tmp_path: Path) -> None:
    from career_agent.domain.organization import Organization

    org_store = SqliteOrganizationStore(tmp_path / "db.sqlite")
    org_store.create(
        Organization(
            id="o1", name="Acme", slug="acme", created_by_user_id="u1", created_at=_NOW
        )
    )
    assert unique_slug("acme", organization_store=org_store) == "acme-2"


def test_create_personal_organization_makes_the_user_owner(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    org_store = SqliteOrganizationStore(db)
    member_store = SqliteMembershipStore(db)
    user = _user()

    organization = create_personal_organization(
        user=user, organization_store=org_store, membership_store=member_store, now=_NOW
    )

    assert organization.created_by_user_id == user.id
    membership = member_store.get(organization_id=organization.id, user_id=user.id)
    assert membership is not None
    assert membership.role == "owner"


def test_create_personal_organization_slug_from_email_local_part(
    tmp_path: Path,
) -> None:
    db = tmp_path / "db.sqlite"
    org_store = SqliteOrganizationStore(db)
    member_store = SqliteMembershipStore(db)
    user = _user(email="grace.hopper@example.com")

    organization = create_personal_organization(
        user=user, organization_store=org_store, membership_store=member_store, now=_NOW
    )

    assert organization.slug == "grace-hopper"


def test_migrate_users_without_organization_backfills_every_orphan(
    tmp_path: Path,
) -> None:
    db = tmp_path / "db.sqlite"
    user_store = SqliteUserStore(db)
    org_store = SqliteOrganizationStore(db)
    member_store = SqliteMembershipStore(db)
    user1, user2 = _user(email="a@example.com"), _user(email="b@example.com")
    user_store.create(user1)
    user_store.create(user2)

    created = migrate_users_without_organization(
        user_store=user_store,
        organization_store=org_store,
        membership_store=member_store,
        now=_NOW,
    )

    assert created == 2
    assert len(member_store.by_user(user1.id)) == 1
    assert len(member_store.by_user(user2.id)) == 1


def test_migrate_users_without_organization_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    user_store = SqliteUserStore(db)
    org_store = SqliteOrganizationStore(db)
    member_store = SqliteMembershipStore(db)
    user_store.create(_user())

    migrate_users_without_organization(
        user_store=user_store,
        organization_store=org_store,
        membership_store=member_store,
        now=_NOW,
    )
    second_pass = migrate_users_without_organization(
        user_store=user_store,
        organization_store=org_store,
        membership_store=member_store,
        now=_NOW,
    )

    assert second_pass == 0


def test_migrate_users_without_organization_skips_users_who_already_have_one(
    tmp_path: Path,
) -> None:
    db = tmp_path / "db.sqlite"
    user_store = SqliteUserStore(db)
    org_store = SqliteOrganizationStore(db)
    member_store = SqliteMembershipStore(db)
    user = _user()
    user_store.create(user)
    create_personal_organization(
        user=user, organization_store=org_store, membership_store=member_store, now=_NOW
    )

    created = migrate_users_without_organization(
        user_store=user_store,
        organization_store=org_store,
        membership_store=member_store,
        now=_NOW,
    )

    assert created == 0
    assert len(member_store.by_user(user.id)) == 1

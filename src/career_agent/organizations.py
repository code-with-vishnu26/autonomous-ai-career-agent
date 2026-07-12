"""Organization composition helpers (Phase 60, ADR-0078).

Top-level, sibling to ``cli.py``/``scheduler.py`` -- not under ``core/``
or ``agents/``. It composes domain object construction (a real ``uuid``,
a real slug) with two stores (``SqliteOrganizationStore``,
``SqliteMembershipStore``), the same "needs to be a real composition root,
not a pure layer" reasoning that already moved ``scheduler.py`` out of
``core/`` in Phase 58 -- and it is not an AI/LLM-driven pipeline, so
``agents/`` would be the wrong layer semantically even if it were
otherwise unconstrained.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from career_agent.domain.organization import Organization
from career_agent.domain.team import Membership
from career_agent.domain.user import User
from career_agent.storage.organization_store import SqliteOrganizationStore
from career_agent.storage.sqlite import SqliteUserStore
from career_agent.storage.team_store import SqliteMembershipStore

_SLUG_SANITIZE = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """A URL-safe, hyphenated slug from ``value`` (usually an email local-part)."""
    cleaned = _SLUG_SANITIZE.sub("-", value.strip().lower()).strip("-")
    return cleaned or "org"


def unique_slug(base: str, *, organization_store: SqliteOrganizationStore) -> str:
    """``base``, or ``base-2``/``base-3``/... if the slug is already taken."""
    slug = base
    suffix = 1
    while organization_store.get_by_slug(slug) is not None:
        suffix += 1
        slug = f"{base}-{suffix}"
    return slug


def create_personal_organization(
    *,
    user: User,
    organization_store: SqliteOrganizationStore,
    membership_store: SqliteMembershipStore,
    now: datetime,
) -> Organization:
    """A new organization owned solely by ``user`` -- "every user belongs to one".

    Never called for a user who already has a membership somewhere
    (callers check first); this always creates a brand new organization.
    """
    local_part = user.email.split("@", 1)[0]
    slug = unique_slug(slugify(local_part), organization_store=organization_store)
    organization = Organization(
        id=str(uuid.uuid4()),
        name=user.display_name or local_part,
        slug=slug,
        created_by_user_id=user.id,
        created_at=now,
    )
    organization_store.create(organization)
    membership_store.create(
        Membership(
            id=str(uuid.uuid4()),
            organization_id=organization.id,
            user_id=user.id,
            role="owner",
            joined_at=now,
        )
    )
    return organization


def migrate_users_without_organization(
    *,
    user_store: SqliteUserStore,
    organization_store: SqliteOrganizationStore,
    membership_store: SqliteMembershipStore,
    now: datetime,
) -> int:
    """Backfill a personal organization for every pre-Phase-60 account.

    Idempotent -- a user with any existing membership is left untouched.
    Mirrors ``storage.sqlite.migrate_to_multi_user``'s own "never orphan
    historical data, safe to call on every startup" discipline. Returns
    how many organizations were newly created.
    """
    created = 0
    for user in user_store.all_users():
        if membership_store.by_user(user.id):
            continue
        create_personal_organization(
            user=user,
            organization_store=organization_store,
            membership_store=membership_store,
            now=now,
        )
        created += 1
    return created

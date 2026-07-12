"""SqliteOrganizationStore (Phase 60, ADR-0078).

Reuses :func:`career_agent.storage.sqlite._connect` -- the same one
SQLite file, same ``sqlite3.Row`` row factory every other store already
uses -- split into its own module purely for readability (``sqlite.py``
was already large before this phase). Not a second database.
"""

from __future__ import annotations

import json
from pathlib import Path

from career_agent.domain.organization import Organization
from career_agent.storage.sqlite import _connect

_ORGANIZATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS organizations (
    id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL
);
"""


class SqliteOrganizationStore:
    """Every tenant this dashboard knows about."""

    def __init__(self, path: Path) -> None:
        """Open (creating if needed) the SQLite database at ``path``."""
        self._path = path
        with _connect(path) as connection:
            connection.executescript(_ORGANIZATION_SCHEMA)

    def create(self, organization: Organization) -> None:
        """Insert a new organization.

        Raises ``sqlite3.IntegrityError`` on a duplicate slug.
        """
        with _connect(self._path) as connection:
            connection.execute(
                "INSERT INTO organizations (id, payload, slug, created_at)"
                " VALUES (?, ?, ?, ?)",
                (
                    organization.id,
                    organization.model_dump_json(),
                    organization.slug,
                    organization.created_at.isoformat(),
                ),
            )

    def get(self, organization_id: str) -> Organization | None:
        """One organization by id, or ``None`` if it doesn't exist."""
        with _connect(self._path) as connection:
            row = connection.execute(
                "SELECT payload FROM organizations WHERE id = ?", (organization_id,)
            ).fetchone()
        return (
            Organization.model_validate(json.loads(row["payload"])) if row else None
        )

    def get_by_slug(self, slug: str) -> Organization | None:
        """One organization by its unique slug, or ``None``."""
        with _connect(self._path) as connection:
            row = connection.execute(
                "SELECT payload FROM organizations WHERE slug = ?", (slug,)
            ).fetchone()
        return (
            Organization.model_validate(json.loads(row["payload"])) if row else None
        )

    def all_organizations(self) -> list[Organization]:
        """Every organization on the platform -- the admin surface's own read."""
        with _connect(self._path) as connection:
            rows = connection.execute("SELECT payload FROM organizations").fetchall()
        return [Organization.model_validate(json.loads(row["payload"])) for row in rows]

    def rename(self, organization_id: str, *, name: str) -> Organization | None:
        """Update an organization's name; returns the updated row, or ``None``."""
        organization = self.get(organization_id)
        if organization is None:
            return None
        updated = organization.model_copy(update={"name": name})
        with _connect(self._path) as connection:
            connection.execute(
                "UPDATE organizations SET payload = ? WHERE id = ?",
                (updated.model_dump_json(), organization_id),
            )
        return updated

    def delete(self, organization_id: str) -> None:
        """Delete an organization outright -- the ``delete_organization`` action.

        Membership/invitation/audit rows referencing it are left as
        historical record (the same "never silently orphan or delete
        history" discipline ``migrate_to_multi_user`` already holds
        itself to) -- callers needing full cascade cleanup do it
        explicitly, this method only removes the organization row itself.
        """
        with _connect(self._path) as connection:
            connection.execute(
                "DELETE FROM organizations WHERE id = ?", (organization_id,)
            )

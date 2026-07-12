"""SqliteAuditLogStore (Phase 60, ADR-0078). Append-only, never mutated."""

from __future__ import annotations

import json
from pathlib import Path

from career_agent.domain.audit import AuditLogEntry
from career_agent.storage.sqlite import _connect

_AUDIT_LOG_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_log_organization ON audit_log(organization_id);
"""


class SqliteAuditLogStore:
    """Every real mutation, recorded -- never updated once written."""

    def __init__(self, path: Path) -> None:
        """Open (creating if needed) the SQLite database at ``path``."""
        self._path = path
        with _connect(path) as connection:
            connection.executescript(_AUDIT_LOG_SCHEMA)

    def record(self, entry: AuditLogEntry) -> None:
        """Persist one audit-log entry. Never called for a hypothetical action."""
        with _connect(self._path) as connection:
            connection.execute(
                "INSERT INTO audit_log (id, organization_id, created_at, payload)"
                " VALUES (?, ?, ?, ?)",
                (
                    entry.id,
                    entry.organization_id,
                    entry.created_at.isoformat(),
                    entry.model_dump_json(),
                ),
            )

    def by_organization(
        self, organization_id: str, *, limit: int = 200
    ) -> list[AuditLogEntry]:
        """The most recent entries for one organization, newest first."""
        with _connect(self._path) as connection:
            rows = connection.execute(
                "SELECT payload FROM audit_log WHERE organization_id = ?"
                " ORDER BY created_at DESC LIMIT ?",
                (organization_id, limit),
            ).fetchall()
        return [
            AuditLogEntry.model_validate(json.loads(row["payload"])) for row in rows
        ]

"""SQLite persistence (Phase 13, ADR-0037).

``SqliteOpportunityRepository`` satisfies the exact
:class:`~career_agent.core.interfaces.OpportunityRepository` contract --
``add`` and ``get``, nothing more -- with byte-for-byte the same two-key
dedup semantics as the in-memory implementation (ADR-0014): duplicate id
is always a duplicate; a *non-authoritative* opportunity (``ats_ref is
None``) whose fingerprint matches a known job is a cross-source
duplicate; two authoritative opportunities sharing a fingerprint stay
separate. The fidelity suite runs the same scenarios against both
implementations, so the swap is proven drop-in, not assumed.

``SqliteApplicationStore`` is the audit trail behind the Excel export and
the Learn pillar: one row per tailoring/submission attempt, recorded at
the composition root after the pipeline runs. It is append-only by
design -- ``record`` never updates an existing row's content; outcome
recording (Phase 15) appends to its own table rather than mutating the
application row, the same never-mutate-history discipline as
``MasterProfile.version``.

Plain stdlib ``sqlite3``, synchronous under the async methods: this is a
single-user, local, personal-scale store -- an async driver would add a
dependency for contention that cannot occur here. Documented, not hidden.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from career_agent.domain.identity import canonical_fingerprint
from career_agent.domain.models import Application, Opportunity

_OPPORTUNITY_SCHEMA = """
CREATE TABLE IF NOT EXISTS opportunities (
    id TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    authoritative INTEGER NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_opportunities_fingerprint
    ON opportunities (fingerprint);
"""

_APPLICATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    id TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    truthfulness_approved INTEGER NOT NULL,
    ats_total REAL,
    tier_used TEXT,
    profile_version TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    artifact_paths TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outcomes (
    application_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    stage TEXT,
    recorded_at TEXT NOT NULL
);
"""


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


class SqliteOpportunityRepository:
    """Deduplicating persistent opportunity store -- same contract, same rules."""

    def __init__(self, path: Path) -> None:
        """Open (creating if needed) the SQLite database at ``path``."""
        self._path = path
        with _connect(path) as connection:
            connection.executescript(_OPPORTUNITY_SCHEMA)

    async def add(self, opportunity: Opportunity) -> bool:
        """Store ``opportunity`` if new (two-key dedup, ADR-0014)."""
        fingerprint = canonical_fingerprint(
            opportunity.canonical_company, opportunity.title, opportunity.location
        )
        authoritative = opportunity.ats_ref is not None
        with _connect(self._path) as connection:
            existing = connection.execute(
                "SELECT 1 FROM opportunities WHERE id = ?", (opportunity.id,)
            ).fetchone()
            if existing is not None:
                return False
            if not authoritative:
                collision = connection.execute(
                    "SELECT 1 FROM opportunities WHERE fingerprint = ?",
                    (fingerprint,),
                ).fetchone()
                if collision is not None:
                    return False
            connection.execute(
                "INSERT INTO opportunities (id, fingerprint, authoritative, payload)"
                " VALUES (?, ?, ?, ?)",
                (
                    opportunity.id,
                    fingerprint,
                    int(authoritative),
                    opportunity.model_dump_json(),
                ),
            )
        return True

    async def get(self, opportunity_id: str) -> Opportunity | None:
        """Return the stored opportunity with ``opportunity_id``, or ``None``."""
        with _connect(self._path) as connection:
            row = connection.execute(
                "SELECT payload FROM opportunities WHERE id = ?", (opportunity_id,)
            ).fetchone()
        if row is None:
            return None
        return Opportunity.model_validate(json.loads(row["payload"]))


class SqliteApplicationStore:
    """Append-only application audit trail feeding the Excel export."""

    def __init__(self, path: Path) -> None:
        """Open (creating if needed) the SQLite database at ``path``."""
        self._path = path
        with _connect(path) as connection:
            connection.executescript(_APPLICATION_SCHEMA)

    def record(
        self,
        application: Application,
        *,
        company: str,
        source: str,
        ats_total: float | None,
    ) -> None:
        """Record one attempt. Never overwrites an existing row (append-only)."""
        with _connect(self._path) as connection:
            connection.execute(
                "INSERT OR IGNORE INTO applications (id, opportunity_id, company,"
                " title, source, status, truthfulness_approved, ats_total,"
                " tier_used, profile_version, prompt_version, artifact_paths,"
                " recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    application.id,
                    application.opportunity_id,
                    company,
                    application.resume.content.summary[:80],
                    source,
                    application.status,
                    int(application.resume.truthfulness.approved),
                    ats_total,
                    application.tier_used,
                    application.resume.profile_version,
                    application.resume.truthfulness.prompt_version,
                    json.dumps(
                        [artifact.path for artifact in application.resume.artifacts]
                    ),
                    datetime.now(UTC).isoformat(),
                ),
            )

    def record_outcome(
        self, application_id: str, kind: str, stage: str | None
    ) -> None:
        """Append one real-world outcome for an application (Phase 15)."""
        with _connect(self._path) as connection:
            connection.execute(
                "INSERT INTO outcomes (application_id, kind, stage, recorded_at)"
                " VALUES (?, ?, ?, ?)",
                (application_id, kind, stage, datetime.now(UTC).isoformat()),
            )

    def all_rows(self) -> list[dict[str, object]]:
        """Every application row joined with its latest outcome, for export."""
        with _connect(self._path) as connection:
            rows = connection.execute(
                "SELECT a.*, ("
                "  SELECT o.kind || COALESCE(':' || o.stage, '')"
                "  FROM outcomes o WHERE o.application_id = a.id"
                "  ORDER BY o.recorded_at DESC LIMIT 1"
                ") AS latest_outcome FROM applications a ORDER BY a.recorded_at"
            ).fetchall()
        return [dict(row) for row in rows]

    def outcome_rows(self) -> list[dict[str, object]]:
        """The FULL outcome history (Phase 15 reads every stage, not the last)."""
        with _connect(self._path) as connection:
            rows = connection.execute(
                "SELECT application_id, kind, stage, recorded_at FROM outcomes"
                " ORDER BY recorded_at"
            ).fetchall()
        return [dict(row) for row in rows]

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
single-*install*, local, personal-scale store -- an async driver would add
a dependency for contention that cannot occur here. Documented, not
hidden. Phase 56 (ADR-0074) adds multi-*user* data ownership within that
one install (a ``user_id`` column on every user-owned table, plus
``users``/``refresh_tokens``/``password_reset_tokens``/``user_preferences``)
without changing this: still one SQLite file, still synchronous, still no
concurrent-writer contention problem to solve.

``SqliteRunJournal`` (Phase 23, ADR-0049) is an append-only execution
journal: one row per stage-transition event for one ``run_id``, used to
reconstruct what a ``career-agent apply``/``auto`` invocation actually did
-- for auditability and crash forensics, not as a safety gate (see
``domain/journal.py`` and ADR-0049 for why a full transition-validated
state machine is not justified yet).
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from career_agent.core.security import hash_password
from career_agent.domain.application_session import ApplicationSession
from career_agent.domain.identity import canonical_fingerprint
from career_agent.domain.job_preferences import JobPreferences
from career_agent.domain.journal import RunEvent
from career_agent.domain.models import Application, Opportunity
from career_agent.domain.resume_variants import ResumeVariant
from career_agent.domain.review import ReviewSession
from career_agent.domain.submission import SubmissionResult
from career_agent.domain.user import User

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


_JOURNAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS run_journal (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    sequence_no INTEGER NOT NULL,
    stage TEXT NOT NULL,
    event_type TEXT NOT NULL,
    outcome TEXT,
    attempt_no INTEGER NOT NULL,
    occurred_at TEXT NOT NULL,
    metadata TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_run_journal_run_seq
    ON run_journal (run_id, sequence_no);
"""


_RESUME_VARIANT_SCHEMA = """
CREATE TABLE IF NOT EXISTS resume_variants (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    user_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_resume_variants_category
    ON resume_variants (category);
CREATE INDEX IF NOT EXISTS idx_resume_variants_user
    ON resume_variants (user_id);
"""

_APPLICATION_SESSION_SCHEMA = """
CREATE TABLE IF NOT EXISTS application_sessions (
    id TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL,
    status TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    user_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_application_sessions_opportunity
    ON application_sessions (opportunity_id);
CREATE INDEX IF NOT EXISTS idx_application_sessions_user
    ON application_sessions (user_id);
"""

_REVIEW_SESSION_SCHEMA = """
CREATE TABLE IF NOT EXISTS review_sessions (
    id TEXT PRIMARY KEY,
    application_session_id TEXT NOT NULL,
    approval_status TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    user_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_review_sessions_application_session
    ON review_sessions (application_session_id);
CREATE INDEX IF NOT EXISTS idx_review_sessions_user
    ON review_sessions (user_id);
"""

_SUBMISSION_RESULT_SCHEMA = """
CREATE TABLE IF NOT EXISTS submission_results (
    id TEXT PRIMARY KEY,
    application_session_id TEXT NOT NULL,
    opportunity_id TEXT NOT NULL,
    status TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    user_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_submission_results_opportunity
    ON submission_results (opportunity_id);
CREATE INDEX IF NOT EXISTS idx_submission_results_user
    ON submission_results (user_id);
"""

_USER_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    hashed_password TEXT NOT NULL,
    display_name TEXT,
    role TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

_REFRESH_TOKEN_SCHEMA = """
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user
    ON refresh_tokens (user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_hash
    ON refresh_tokens (token_hash);
"""

_PASSWORD_RESET_TOKEN_SCHEMA = """
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user
    ON password_reset_tokens (user_id);
"""

_USER_PREFERENCES_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    updated_at TEXT NOT NULL
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

    def prior_attempt_status(self, opportunity_id: str) -> str | None:
        """Most recent blocking-status attempt for this opportunity.

        Returns ``None`` when no such attempt exists. ``"rejected"`` (the
        truthfulness gate blocked the draft, ADR-0003) and ``"declined"``
        (the human confirmation step said no, ADR-0050/Phase 36) are both
        excluded, for the same reason: neither produced any external side
        effect -- confirmation was either never reached or was explicitly
        refused, and in this build no executor is ever reachable regardless
        (ADR-0050) -- so a fresh attempt after fixing the profile/JD
        understanding is legitimate and must not be blocked. Every other
        recorded status (``"pending"``, ``"paused_for_human"``,
        ``"submitted"``, ``"failed"``) means a prior attempt at least
        reached or passed the confirmation boundary, and possibly a real
        submission attempt -- a second attempt risks a duplicate real-world
        side effect, so it must be a human's explicit decision, never
        automatic (Phase 22, ADR-0048).
        """
        with _connect(self._path) as connection:
            row = connection.execute(
                "SELECT status FROM applications WHERE opportunity_id = ?"
                " AND status NOT IN ('rejected', 'declined')"
                " ORDER BY recorded_at DESC LIMIT 1",
                (opportunity_id,),
            ).fetchone()
        return row["status"] if row is not None else None

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


class SqliteRunJournal:
    """Append-only execution journal: one row per run's stage transitions.

    Only ``append``/``history`` are public -- there is no update or delete
    method, so a prior event cannot be mutated through this class's own
    API (append-only by construction, not just convention). Sequence
    numbers are assigned per ``run_id``, monotonically, by this class
    alone (never supplied by the caller): ``MAX(sequence_no) + 1`` is read
    and the new row inserted inside the same connection, matching the
    single-process, single-writer concurrency assumption every other
    store in this module already documents.
    """

    def __init__(self, path: Path) -> None:
        """Open (creating if needed) the SQLite database at ``path``."""
        self._path = path
        with _connect(path) as connection:
            connection.executescript(_JOURNAL_SCHEMA)

    def append(
        self,
        run_id: str,
        stage: str,
        event_type: str,
        *,
        outcome: str | None = None,
        attempt_no: int = 1,
        metadata: dict[str, str] | None = None,
    ) -> RunEvent:
        """Append one immutable event for ``run_id``; returns it as recorded."""
        event_id = str(uuid.uuid4())
        occurred_at = datetime.now(UTC)
        recorded_metadata = metadata or {}
        with _connect(self._path) as connection:
            row = connection.execute(
                "SELECT MAX(sequence_no) AS m FROM run_journal WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            sequence_no = (row["m"] or 0) + 1
            connection.execute(
                "INSERT INTO run_journal (event_id, run_id, sequence_no, stage,"
                " event_type, outcome, attempt_no, occurred_at, metadata)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    run_id,
                    sequence_no,
                    stage,
                    event_type,
                    outcome,
                    attempt_no,
                    occurred_at.isoformat(),
                    json.dumps(recorded_metadata),
                ),
            )
        return RunEvent(
            event_id=event_id,
            run_id=run_id,
            sequence_no=sequence_no,
            stage=stage,
            event_type=event_type,
            outcome=outcome,
            attempt_no=attempt_no,
            occurred_at=occurred_at,
            metadata=recorded_metadata,
        )

    def history(self, run_id: str) -> list[RunEvent]:
        """Every event for ``run_id``, in sequence order (empty if unknown)."""
        with _connect(self._path) as connection:
            rows = connection.execute(
                "SELECT * FROM run_journal WHERE run_id = ? ORDER BY sequence_no",
                (run_id,),
            ).fetchall()
        return [
            RunEvent(
                event_id=row["event_id"],
                run_id=row["run_id"],
                sequence_no=row["sequence_no"],
                stage=row["stage"],
                event_type=row["event_type"],
                outcome=row["outcome"],
                attempt_no=row["attempt_no"],
                occurred_at=datetime.fromisoformat(row["occurred_at"]),
                metadata=json.loads(row["metadata"]),
            )
            for row in rows
        ]


class SqliteResumeVariantStore:
    """Persistent store of approved resume variants, one row per category snapshot.

    Append-only, same discipline as :class:`SqliteApplicationStore`: ``save``
    never updates an existing row, and there is no update/delete method on
    this class at all (Phase 50, ADR-0068). ``by_category`` returns every
    stored variant for a category (newest first) so
    :func:`~career_agent.domain.resume_variants.select_closest_variant` has
    real candidates to rank, never just one silently-assumed row.
    """

    def __init__(self, path: Path) -> None:
        """Open (creating if needed) the SQLite database at ``path``."""
        self._path = path
        with _connect(path) as connection:
            connection.executescript(_RESUME_VARIANT_SCHEMA)

    def save(self, variant: ResumeVariant, *, user_id: str) -> None:
        """Persist ``variant`` for ``user_id``. Never overwrites (append-only).

        ``user_id`` is a required keyword-only argument, deliberately with
        no default (Phase 56, ADR-0074) -- a missing owner is a
        ``TypeError`` at every call site, not a silent cross-user leak.
        Stored as a plain query column, the same "denormalize identity
        fields, not full content" precedent ``company``/``category``
        already follow here; ``ResumeVariant`` itself stays a pure,
        owner-agnostic domain object.
        """
        with _connect(self._path) as connection:
            connection.execute(
                "INSERT OR IGNORE INTO resume_variants"
                " (id, category, payload, created_at, user_id) VALUES (?, ?, ?, ?, ?)",
                (
                    variant.id,
                    variant.category,
                    variant.model_dump_json(),
                    variant.created_at,
                    user_id,
                ),
            )

    def by_category(self, category: str) -> list[ResumeVariant]:
        """Every stored variant for ``category``, newest first."""
        with _connect(self._path) as connection:
            rows = connection.execute(
                "SELECT payload FROM resume_variants WHERE category = ?"
                " ORDER BY created_at DESC",
                (category,),
            ).fetchall()
        return [
            ResumeVariant.model_validate(json.loads(row["payload"])) for row in rows
        ]

    def by_user(self, user_id: str) -> list[ResumeVariant]:
        """Every stored variant owned by ``user_id``, newest first."""
        with _connect(self._path) as connection:
            rows = connection.execute(
                "SELECT payload FROM resume_variants WHERE user_id = ?"
                " ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        return [
            ResumeVariant.model_validate(json.loads(row["payload"])) for row in rows
        ]

    def all_variants(self) -> list[ResumeVariant]:
        """Every stored variant, newest first, across all categories."""
        with _connect(self._path) as connection:
            rows = connection.execute(
                "SELECT payload FROM resume_variants ORDER BY created_at DESC"
            ).fetchall()
        return [
            ResumeVariant.model_validate(json.loads(row["payload"])) for row in rows
        ]

    def get(self, variant_id: str) -> ResumeVariant | None:
        """The stored variant with ``variant_id``, or ``None`` (Phase 53).

        Added for the Submission Engine's artifact-integrity check
        (ADR-0071): it must load one specific variant by the id an
        ``ApplicationSession`` names, not the category it belongs to.
        """
        with _connect(self._path) as connection:
            row = connection.execute(
                "SELECT payload FROM resume_variants WHERE id = ?", (variant_id,)
            ).fetchone()
        return ResumeVariant.model_validate(json.loads(row["payload"])) if row else None


class SqliteApplicationSessionStore:
    """Append-only store of prepared-but-unsubmitted application sessions.

    Same discipline as :class:`SqliteApplicationStore`/
    :class:`SqliteResumeVariantStore` (Phase 51, ADR-0069): ``save`` never
    updates an existing row, and there is no update/delete method on this
    class at all. This is the record Phase 52's Human Review Center reads
    from -- never anything a submission step writes to, since no
    submission step exists anywhere in this codebase yet.
    """

    def __init__(self, path: Path) -> None:
        """Open (creating if needed) the SQLite database at ``path``."""
        self._path = path
        with _connect(path) as connection:
            connection.executescript(_APPLICATION_SESSION_SCHEMA)

    def save(self, session: ApplicationSession, *, user_id: str) -> None:
        """Persist ``session`` for ``user_id``. Never overwrites (append-only).

        ``user_id`` required, no default (Phase 56, ADR-0074) -- see
        :meth:`SqliteResumeVariantStore.save` for why.
        """
        with _connect(self._path) as connection:
            connection.execute(
                "INSERT OR IGNORE INTO application_sessions"
                " (id, opportunity_id, status, payload, created_at, user_id)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    session.id,
                    session.opportunity_id,
                    session.status,
                    session.model_dump_json(),
                    session.created_at.isoformat(),
                    user_id,
                ),
            )

    def by_opportunity(self, opportunity_id: str) -> list[ApplicationSession]:
        """Every stored session for ``opportunity_id``, newest first."""
        with _connect(self._path) as connection:
            rows = connection.execute(
                "SELECT payload FROM application_sessions WHERE opportunity_id = ?"
                " ORDER BY created_at DESC",
                (opportunity_id,),
            ).fetchall()
        return [
            ApplicationSession.model_validate(json.loads(row["payload"]))
            for row in rows
        ]

    def all_sessions(self) -> list[ApplicationSession]:
        """Every stored session, newest first, across all opportunities."""
        with _connect(self._path) as connection:
            rows = connection.execute(
                "SELECT payload FROM application_sessions ORDER BY created_at DESC"
            ).fetchall()
        return [
            ApplicationSession.model_validate(json.loads(row["payload"]))
            for row in rows
        ]

    def by_user(self, user_id: str) -> list[ApplicationSession]:
        """Every stored session owned by ``user_id``, newest first."""
        with _connect(self._path) as connection:
            rows = connection.execute(
                "SELECT payload FROM application_sessions WHERE user_id = ?"
                " ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        return [
            ApplicationSession.model_validate(json.loads(row["payload"]))
            for row in rows
        ]


class SqliteReviewSessionStore:
    """Append-only human-review-decision audit trail (Phase 52, ADR-0070).

    Same discipline as every other store in this file: ``save`` never
    updates an existing row, and there is no update/delete method on this
    class at all -- a review decision, once recorded, is permanent
    history, the same never-mutate-history discipline
    ``SqliteApplicationStore``/``SqliteResumeVariantStore`` already apply.
    """

    def __init__(self, path: Path) -> None:
        """Open (creating if needed) the SQLite database at ``path``."""
        self._path = path
        with _connect(path) as connection:
            connection.executescript(_REVIEW_SESSION_SCHEMA)

    def save(self, review: ReviewSession, *, user_id: str) -> None:
        """Persist ``review`` for ``user_id``. Never overwrites (append-only).

        ``user_id`` required, no default (Phase 56, ADR-0074) -- see
        :meth:`SqliteResumeVariantStore.save` for why.
        """
        with _connect(self._path) as connection:
            connection.execute(
                "INSERT OR IGNORE INTO review_sessions"
                " (id, application_session_id, approval_status, payload, created_at,"
                " user_id) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    review.id,
                    review.application_session_id,
                    review.approval_status,
                    review.model_dump_json(),
                    review.created_at.isoformat(),
                    user_id,
                ),
            )

    def by_application_session(
        self, application_session_id: str
    ) -> list[ReviewSession]:
        """Every stored review for ``application_session_id``, newest first."""
        with _connect(self._path) as connection:
            rows = connection.execute(
                "SELECT payload FROM review_sessions"
                " WHERE application_session_id = ? ORDER BY created_at DESC",
                (application_session_id,),
            ).fetchall()
        return [
            ReviewSession.model_validate(json.loads(row["payload"])) for row in rows
        ]

    def all_reviews(self) -> list[ReviewSession]:
        """Every stored review, newest first, across all application sessions."""
        with _connect(self._path) as connection:
            rows = connection.execute(
                "SELECT payload FROM review_sessions ORDER BY created_at DESC"
            ).fetchall()
        return [
            ReviewSession.model_validate(json.loads(row["payload"])) for row in rows
        ]

    def by_user(self, user_id: str) -> list[ReviewSession]:
        """Every stored review owned by ``user_id``, newest first."""
        with _connect(self._path) as connection:
            rows = connection.execute(
                "SELECT payload FROM review_sessions WHERE user_id = ?"
                " ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        return [
            ReviewSession.model_validate(json.loads(row["payload"])) for row in rows
        ]


class SqliteSubmissionResultStore:
    """Append-only submission-attempt audit trail (Phase 53, ADR-0071).

    Same discipline as every other store in this file: ``save`` never
    updates an existing row, and there is no update/delete method at all
    -- a submission attempt's outcome, once recorded, is permanent
    history, the load-bearing property the execution-safety boundary
    (``domain/execution.py``) relies on to refuse an unsafe retry after a
    ``DEFINITELY_SUBMITTED``/``OUTCOME_UNCERTAIN`` prior result.
    """

    def __init__(self, path: Path) -> None:
        """Open (creating if needed) the SQLite database at ``path``."""
        self._path = path
        with _connect(path) as connection:
            connection.executescript(_SUBMISSION_RESULT_SCHEMA)

    def save(self, result: SubmissionResult, *, user_id: str) -> None:
        """Persist ``result`` for ``user_id``. Never overwrites (append-only).

        ``user_id`` required, no default (Phase 56, ADR-0074) -- see
        :meth:`SqliteResumeVariantStore.save` for why.
        """
        with _connect(self._path) as connection:
            connection.execute(
                "INSERT OR IGNORE INTO submission_results"
                " (id, application_session_id, opportunity_id, status, payload,"
                " created_at, user_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    result.id,
                    result.application_session_id,
                    result.opportunity_id,
                    result.status,
                    result.model_dump_json(),
                    (result.submitted_at or datetime.now(UTC)).isoformat(),
                    user_id,
                ),
            )

    def by_opportunity(self, opportunity_id: str) -> list[SubmissionResult]:
        """Every stored result for ``opportunity_id``, newest first."""
        with _connect(self._path) as connection:
            rows = connection.execute(
                "SELECT payload FROM submission_results WHERE opportunity_id = ?"
                " ORDER BY created_at DESC",
                (opportunity_id,),
            ).fetchall()
        return [
            SubmissionResult.model_validate(json.loads(row["payload"]))
            for row in rows
        ]

    def all_results(self) -> list[SubmissionResult]:
        """Every stored result, newest first, across all opportunities."""
        with _connect(self._path) as connection:
            rows = connection.execute(
                "SELECT payload FROM submission_results ORDER BY created_at DESC"
            ).fetchall()
        return [
            SubmissionResult.model_validate(json.loads(row["payload"]))
            for row in rows
        ]

    def by_user(self, user_id: str) -> list[SubmissionResult]:
        """Every stored result owned by ``user_id``, newest first."""
        with _connect(self._path) as connection:
            rows = connection.execute(
                "SELECT payload FROM submission_results WHERE user_id = ?"
                " ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        return [
            SubmissionResult.model_validate(json.loads(row["payload"]))
            for row in rows
        ]


class SqliteUserStore:
    """Account store (Phase 56, ADR-0074).

    ``email`` is unique, enforced by the schema's own ``UNIQUE`` constraint,
    not just application-level checking -- a race between two concurrent
    registrations with the same email can never both succeed.
    """

    def __init__(self, path: Path) -> None:
        """Open (creating if needed) the SQLite database at ``path``."""
        self._path = path
        with _connect(path) as connection:
            connection.executescript(_USER_SCHEMA)

    def create(self, user: User) -> None:
        """Insert a new account.

        Raises ``sqlite3.IntegrityError`` for a duplicate email.
        """
        with _connect(self._path) as connection:
            connection.execute(
                "INSERT INTO users"
                " (id, email, hashed_password, display_name, role, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    user.id,
                    user.email,
                    user.hashed_password,
                    user.display_name,
                    user.role,
                    user.created_at.isoformat(),
                ),
            )

    def by_email(self, email: str) -> User | None:
        """The account with ``email`` (case/whitespace-normalized), or ``None``."""
        with _connect(self._path) as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE email = ?", (email.strip().lower(),)
            ).fetchone()
        return _user_from_row(row) if row else None

    def by_id(self, user_id: str) -> User | None:
        """The account with ``user_id``, or ``None``."""
        with _connect(self._path) as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return _user_from_row(row) if row else None

    def update_profile(self, user_id: str, *, display_name: str | None) -> None:
        """Update the mutable account-profile fields.

        Email/password/role are never changed here -- password changes go
        through the auth flow (verify-old-password), and there is no
        role-elevation endpoint at all yet (Phase 56 wires no admin
        capability).
        """
        with _connect(self._path) as connection:
            connection.execute(
                "UPDATE users SET display_name = ? WHERE id = ?",
                (display_name, user_id),
            )

    def update_password(self, user_id: str, *, hashed_password: str) -> None:
        """Replace the stored password hash.

        Used by both the change-password and reset-password flows.
        """
        with _connect(self._path) as connection:
            connection.execute(
                "UPDATE users SET hashed_password = ? WHERE id = ?",
                (hashed_password, user_id),
            )


def _user_from_row(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        email=row["email"],
        hashed_password=row["hashed_password"],
        display_name=row["display_name"],
        role=row["role"],
        created_at=row["created_at"],
    )


class SqliteRefreshTokenStore:
    """Refresh-token store (Phase 56, ADR-0074).

    Only a *hash* of each token is ever stored -- see
    :func:`~career_agent.core.security.hash_opaque_token` -- so a database
    read (backup, leak, `sqlite3` CLI on the file) can never itself be
    used to authenticate as anyone. ``revoked`` is a real column, not a
    delete, so a revoked-token-reuse attempt is still observable in the
    data rather than silently vanishing.
    """

    def __init__(self, path: Path) -> None:
        """Open (creating if needed) the SQLite database at ``path``."""
        self._path = path
        with _connect(path) as connection:
            connection.executescript(_REFRESH_TOKEN_SCHEMA)

    def save(
        self, *, token_id: str, user_id: str, token_hash: str, expires_at: datetime
    ) -> None:
        """Persist a newly issued refresh token (hash only)."""
        with _connect(self._path) as connection:
            connection.execute(
                "INSERT INTO refresh_tokens"
                " (id, user_id, token_hash, expires_at, revoked, created_at)"
                " VALUES (?, ?, ?, ?, 0, ?)",
                (
                    token_id,
                    user_id,
                    token_hash,
                    expires_at.isoformat(),
                    datetime.now(UTC).isoformat(),
                ),
            )

    def find_active(self, token_hash: str) -> dict | None:
        """The row for ``token_hash`` iff it exists and is not revoked.

        Returns a plain dict (not a domain model -- this is an internal
        lookup table, not something the API ever serializes to a client)
        with ``id``/``user_id``/``expires_at``, or ``None`` if the hash is
        unknown or the token was revoked.
        """
        with _connect(self._path) as connection:
            row = connection.execute(
                "SELECT id, user_id, expires_at FROM refresh_tokens"
                " WHERE token_hash = ? AND revoked = 0",
                (token_hash,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "expires_at": datetime.fromisoformat(row["expires_at"]),
        }

    def revoke(self, token_id: str) -> None:
        """Mark one refresh token revoked (used on logout and on rotation-on-use)."""
        with _connect(self._path) as connection:
            connection.execute(
                "UPDATE refresh_tokens SET revoked = 1 WHERE id = ?", (token_id,)
            )

    def revoke_all_for_user(self, user_id: str) -> None:
        """Revoke every refresh token for ``user_id`` (on password change/reset)."""
        with _connect(self._path) as connection:
            connection.execute(
                "UPDATE refresh_tokens SET revoked = 1 WHERE user_id = ?", (user_id,)
            )


class SqlitePasswordResetTokenStore:
    """Password-reset-token store (Phase 56, ADR-0074).

    Same "store a hash, not the token" discipline as
    :class:`SqliteRefreshTokenStore`. ``used`` is a real column (not a
    delete) so a used-token-reuse attempt is provably rejected rather than
    coincidentally absent.
    """

    def __init__(self, path: Path) -> None:
        """Open (creating if needed) the SQLite database at ``path``."""
        self._path = path
        with _connect(path) as connection:
            connection.executescript(_PASSWORD_RESET_TOKEN_SCHEMA)

    def save(
        self, *, token_id: str, user_id: str, token_hash: str, expires_at: datetime
    ) -> None:
        """Persist a newly issued password-reset token (hash only)."""
        with _connect(self._path) as connection:
            connection.execute(
                "INSERT INTO password_reset_tokens"
                " (id, user_id, token_hash, expires_at, used, created_at)"
                " VALUES (?, ?, ?, ?, 0, ?)",
                (
                    token_id,
                    user_id,
                    token_hash,
                    expires_at.isoformat(),
                    datetime.now(UTC).isoformat(),
                ),
            )

    def find_unused(self, token_hash: str) -> dict | None:
        """The row for ``token_hash`` iff it exists and hasn't been used yet."""
        with _connect(self._path) as connection:
            row = connection.execute(
                "SELECT id, user_id, expires_at FROM password_reset_tokens"
                " WHERE token_hash = ? AND used = 0",
                (token_hash,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "expires_at": datetime.fromisoformat(row["expires_at"]),
        }

    def mark_used(self, token_id: str) -> None:
        """Mark one reset token consumed -- it can never be replayed."""
        with _connect(self._path) as connection:
            connection.execute(
                "UPDATE password_reset_tokens SET used = 1 WHERE id = ?", (token_id,)
            )


class SqliteUserPreferencesStore:
    """Per-user Job Search Preferences (Phase 56, ADR-0074).

    Extends :class:`~career_agent.domain.job_preferences.JobPreferences`
    (Phase 46, ADR-0064) -- unmodified -- from a single CWD-relative
    ``job_preferences.json`` file to one row per user, keyed by
    ``user_id``. The CLI's file-based store
    (:mod:`career_agent.storage.job_preferences`) is untouched and still
    exactly what ``career-agent preferences``/``discover`` use for the
    local operator; this is the dashboard's per-dashboard-user analogue,
    not a replacement.
    """

    def __init__(self, path: Path) -> None:
        """Open (creating if needed) the SQLite database at ``path``."""
        self._path = path
        with _connect(path) as connection:
            connection.executescript(_USER_PREFERENCES_SCHEMA)

    def save(self, user_id: str, preferences: JobPreferences) -> None:
        """Upsert ``user_id``'s preferences.

        A real update, unlike the append-only stores above -- there is
        exactly one preferences row per user, and it should reflect their
        latest choice, not a history of every edit.
        """
        with _connect(self._path) as connection:
            connection.execute(
                "INSERT INTO user_preferences (user_id, payload, updated_at)"
                " VALUES (?, ?, ?)"
                " ON CONFLICT(user_id) DO UPDATE SET payload = excluded.payload,"
                " updated_at = excluded.updated_at",
                (
                    user_id,
                    preferences.model_dump_json(),
                    datetime.now(UTC).isoformat(),
                ),
            )

    def get(self, user_id: str) -> JobPreferences | None:
        """``user_id``'s stored preferences, or ``None`` if never saved."""
        with _connect(self._path) as connection:
            row = connection.execute(
                "SELECT payload FROM user_preferences WHERE user_id = ?", (user_id,)
            ).fetchone()
        if row is None:
            return None
        return JobPreferences.model_validate(json.loads(row["payload"]))


def migrate_to_multi_user(path: Path, *, default_operator_email: str) -> str:
    """One-time, idempotent migration for a database predating multi-user support.

    Phase 56, ADR-0074. Every user-owned table (``resume_variants``/
    ``application_sessions``/``review_sessions``/``submission_results``)
    gets a ``user_id`` column
    added if it's missing (a pre-Phase-56 database's tables predate the
    column entirely -- ``CREATE TABLE IF NOT EXISTS`` is a no-op against
    an existing table, so the column has to be added explicitly via
    ``ALTER TABLE``). Every row with ``user_id IS NULL`` -- i.e. every row
    that existed before this migration ever ran -- is then backfilled to
    one real, auto-created "default operator" account
    (``default_operator_email``), so no historical data is silently
    orphaned or deleted.

    Returns the default operator's user id. Safe to call on every
    process startup (idempotent): a database that already has the
    ``user_id`` column and no ``NULL`` rows left does nothing beyond the
    one cheap existence check per table.
    """
    user_store = SqliteUserStore(path)
    default_user = user_store.by_email(default_operator_email)
    if default_user is None:
        default_user = User(
            id=str(uuid.uuid4()),
            email=default_operator_email,
            # No real password: this account is never logged into via the
            # API (nothing hands out its credentials) -- it exists solely
            # as the CLI's fixed local-operator identity and as the owner
            # of record for pre-migration rows. A random, never-recorded
            # value keeps `hashed_password` a real bcrypt hash (so nothing
            # downstream has to special-case "no password") without ever
            # being a guessable or reused value.
            hashed_password=hash_password(secrets.token_urlsafe(32)),
            role="user",
            created_at=datetime.now(UTC),
        )
        user_store.create(default_user)

    for table, schema in (
        ("resume_variants", _RESUME_VARIANT_SCHEMA),
        ("application_sessions", _APPLICATION_SESSION_SCHEMA),
        ("review_sessions", _REVIEW_SESSION_SCHEMA),
        ("submission_results", _SUBMISSION_RESULT_SCHEMA),
    ):
        with _connect(path) as connection:
            # The column must exist *before* the schema script runs --
            # that script's own CREATE INDEX on user_id would otherwise
            # fail against a pre-Phase-56 table that predates the column,
            # since CREATE TABLE IF NOT EXISTS is a no-op here.
            columns = {
                row["name"]
                for row in connection.execute(f"PRAGMA table_info({table})")
            }
            if columns and "user_id" not in columns:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN user_id TEXT")
            connection.executescript(schema)
            connection.execute(
                f"UPDATE {table} SET user_id = ? WHERE user_id IS NULL",
                (default_user.id,),
            )

    return default_user.id

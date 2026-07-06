"""Execution-journal domain types and deterministic reconstruction.

Phase 23 / ADR-0049. Pure domain layer: no I/O, no storage dependency,
nothing project-specific beyond stdlib (domain purity, import-linter
contract -- "Domain depends on nothing else in the project"). Reading and
writing this data is :class:`~career_agent.storage.sqlite.SqliteRunJournal`'s
job; this module only defines what a journal event *is* and how to fold
an ordered history into a :class:`RunState`.

``stage``/``event_type`` are free-form, informational strings, not a
validated transition table. Phase 23's repository audit found no evidence
a formal state machine is justified: no composition-root command
(``career-agent apply``/``auto``) wires any concrete ``Applicator`` at
all yet (confirmed by grep -- ``TieredApplicator``/``BrowserApplicator``/
``EmailApplicator``/``SubmissionPipeline`` are never imported by
``cli.py``), so the one class of operation a transition-gated state
machine would primarily protect -- an irreversible external submission --
is structurally unreachable from any real, runnable command today. This
journal therefore records history for reconstruction and auditability,
not as a safety gate; see ADR-0049 for the full reasoning and the named,
deferred trigger for revisiting this once submission is actually wired in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class RunEvent:
    """One immutable, append-only execution-journal entry.

    ``metadata`` must never carry secrets, API keys, or resume/profile
    content -- only plain identifiers, counts, and status strings. This is
    enforced by call-site discipline (verified by test), not by any
    code-level redaction in this module.
    """

    event_id: str
    run_id: str
    sequence_no: int
    stage: str
    event_type: str
    outcome: str | None
    attempt_no: int
    occurred_at: datetime
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RunState:
    """The reconstructed state of one run, folded from its ordered history.

    Deliberately minimal (ADR-0049): the *last* event's stage/event_type/
    outcome is the run's current position. There is no validated
    transition table to fold through step by step, since nothing in this
    codebase today gates behavior on this reconstruction -- it exists for
    auditability and crash-forensics, not as a resume-decision authority.
    """

    run_id: str
    event_count: int
    last_stage: str | None
    last_event_type: str | None
    last_outcome: str | None
    completed: bool
    events: tuple[RunEvent, ...]


#: The one event_type this module treats specially: it marks a run as
#: finished. Everything else is opaque, informational history.
_RUN_COMPLETED = "RUN_COMPLETED"


def reconstruct_run(run_id: str, history: list[RunEvent]) -> RunState:
    """Fold an ordered event history into a ``RunState`` -- pure, deterministic.

    ``history`` must already be in ``sequence_no`` order (the journal's own
    ``history()`` method guarantees this via its own ``ORDER BY``); this
    function does not re-sort. Calling it twice on the same input always
    returns an equal result (reconstruction is deterministic and
    repeat-read-invariant), and reading history is never itself a side
    effect, so replaying it for reconstruction is always safe regardless
    of what the underlying events describe.
    """
    if not history:
        return RunState(
            run_id=run_id,
            event_count=0,
            last_stage=None,
            last_event_type=None,
            last_outcome=None,
            completed=False,
            events=(),
        )
    last = history[-1]
    return RunState(
        run_id=run_id,
        event_count=len(history),
        last_stage=last.stage,
        last_event_type=last.event_type,
        last_outcome=last.outcome,
        completed=last.event_type == _RUN_COMPLETED,
        events=tuple(history),
    )

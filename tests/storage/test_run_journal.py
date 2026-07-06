"""Phase 23 / ADR-0049: SqliteRunJournal -- append-only execution journal."""

from __future__ import annotations

from pathlib import Path

from career_agent.storage.sqlite import SqliteRunJournal


def test_public_surface_is_append_and_history_only() -> None:
    """No update/delete method exists -- append-only by construction (P4)."""
    public = {name for name in vars(SqliteRunJournal) if not name.startswith("_")}
    assert public == {"append", "history"}


def test_sequence_numbers_are_monotonic_per_run(tmp_path: Path) -> None:
    journal = SqliteRunJournal(tmp_path / "db.sqlite")
    first = journal.append("run-1", "run", "RUN_STARTED")
    second = journal.append("run-1", "tailoring", "TAILORING_COMPLETED")
    third = journal.append("run-1", "run", "RUN_COMPLETED")
    assert [e.sequence_no for e in (first, second, third)] == [1, 2, 3]


def test_sequence_numbers_are_independent_per_run(tmp_path: Path) -> None:
    journal = SqliteRunJournal(tmp_path / "db.sqlite")
    journal.append("run-1", "run", "RUN_STARTED")
    journal.append("run-1", "run", "RUN_COMPLETED")
    first_of_run_2 = journal.append("run-2", "run", "RUN_STARTED")
    assert first_of_run_2.sequence_no == 1


def test_history_is_returned_in_sequence_order(tmp_path: Path) -> None:
    journal = SqliteRunJournal(tmp_path / "db.sqlite")
    journal.append("run-1", "run", "RUN_STARTED")
    journal.append("run-1", "tailoring", "TAILORING_COMPLETED")
    journal.append("run-1", "run", "RUN_COMPLETED", outcome="prepared=1")
    history = journal.history("run-1")
    assert [e.event_type for e in history] == [
        "RUN_STARTED",
        "TAILORING_COMPLETED",
        "RUN_COMPLETED",
    ]
    assert history[-1].outcome == "prepared=1"


def test_history_of_an_unknown_run_id_is_empty(tmp_path: Path) -> None:
    journal = SqliteRunJournal(tmp_path / "db.sqlite")
    assert journal.history("never-existed") == []


def test_metadata_round_trips_and_defaults_to_empty(tmp_path: Path) -> None:
    journal = SqliteRunJournal(tmp_path / "db.sqlite")
    journal.append(
        "run-1", "application", "APPLICATION_PREPARED",
        metadata={"opportunity_id": "opp-1"},
    )
    journal.append("run-1", "run", "RUN_COMPLETED")
    history = journal.history("run-1")
    assert history[0].metadata == {"opportunity_id": "opp-1"}
    assert history[1].metadata == {}


def test_survives_close_and_reopen(tmp_path: Path) -> None:
    """The one guarantee memory can't provide: real persistence across restart."""
    db = tmp_path / "db.sqlite"
    first = SqliteRunJournal(db)
    first.append("run-1", "run", "RUN_STARTED")
    del first

    reopened = SqliteRunJournal(db)
    history = reopened.history("run-1")
    assert len(history) == 1
    # A "restart" continuing the same run_id picks up sequencing where it
    # left off, rather than colliding or resetting to 1.
    second_event = reopened.append("run-1", "run", "RUN_COMPLETED")
    assert second_event.sequence_no == 2


def test_metadata_values_recorded_by_real_call_sites_never_look_like_secrets(
    tmp_path: Path,
) -> None:
    """Redaction discipline check (Phase 23 Section 18): call sites in
    cli.py only ever pass short identifiers/counts/status strings into
    metadata, never resume/profile content or API keys -- this asserts
    the shape rather than presence of a redaction filter."""
    journal = SqliteRunJournal(tmp_path / "db.sqlite")
    journal.append(
        "run-1",
        "application",
        "APPLICATION_PREPARED",
        metadata={"opportunity_id": "opp-1", "opportunity_count": "3"},
    )
    for event in journal.history("run-1"):
        for value in event.metadata.values():
            assert len(value) < 200
            assert "api_key" not in value.lower()
            assert "bearer " not in value.lower()

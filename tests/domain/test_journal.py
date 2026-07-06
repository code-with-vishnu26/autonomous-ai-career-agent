"""Phase 23 / ADR-0049: pure reconstruction logic, no I/O."""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.domain.journal import RunEvent, reconstruct_run


def _event(
    sequence_no: int, event_type: str, *, outcome: str | None = None
) -> RunEvent:
    return RunEvent(
        event_id=f"evt-{sequence_no}",
        run_id="run-1",
        sequence_no=sequence_no,
        stage="stage",
        event_type=event_type,
        outcome=outcome,
        attempt_no=1,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_empty_history_reconstructs_to_an_unknown_unstarted_run() -> None:
    state = reconstruct_run("run-1", [])
    assert state.event_count == 0
    assert state.last_stage is None
    assert state.completed is False


def test_last_event_wins_and_run_completed_marks_completion() -> None:
    history = [_event(1, "RUN_STARTED"), _event(2, "RUN_COMPLETED", outcome="ok")]
    state = reconstruct_run("run-1", history)
    assert state.event_count == 2
    assert state.last_event_type == "RUN_COMPLETED"
    assert state.last_outcome == "ok"
    assert state.completed is True


def test_incomplete_history_is_not_completed() -> None:
    history = [_event(1, "RUN_STARTED"), _event(2, "TAILORING_STARTED")]
    state = reconstruct_run("run-1", history)
    assert state.completed is False


def test_reconstruction_is_deterministic_and_repeat_read_invariant() -> None:
    """P2/P3: reading the same history twice always yields an equal state."""
    history = [_event(1, "RUN_STARTED"), _event(2, "RUN_COMPLETED")]
    assert reconstruct_run("run-1", history) == reconstruct_run("run-1", history)


def test_an_unrecognized_event_type_does_not_raise_and_is_reported_as_is() -> None:
    """Corrupted/unknown event types are informational only -- no validation gate."""
    history = [_event(1, "SOME_FUTURE_EVENT_TYPE_NOT_YET_INVENTED")]
    state = reconstruct_run("run-1", history)
    assert state.last_event_type == "SOME_FUTURE_EVENT_TYPE_NOT_YET_INVENTED"
    assert state.completed is False

"""Phase 63 (ADR-0081): DiscoveryRun is pure data."""

from __future__ import annotations

from datetime import UTC, datetime

from career_agent.domain.discovery_run import DiscoveryRun


def _run(**overrides: object) -> DiscoveryRun:
    fields = {
        "id": "run-1",
        "user_id": "u1",
        "status": "PENDING",
        "started_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    fields.update(overrides)
    return DiscoveryRun(**fields)


def test_defaults_are_empty_not_none() -> None:
    run = _run()
    assert run.completed_at is None
    assert run.new_count == 0
    assert run.source_labels == []
    assert run.errors == []


def test_round_trips_through_json() -> None:
    run = _run(
        status="COMPLETED",
        completed_at=datetime(2026, 1, 1, 0, 5, tzinfo=UTC),
        new_count=4,
        source_labels=["adzuna", "remotive"],
        errors=["reed: timeout"],
    )
    restored = DiscoveryRun.model_validate_json(run.model_dump_json())
    assert restored == run


def test_every_status_value_is_constructible() -> None:
    for status in ("PENDING", "RUNNING", "COMPLETED", "FAILED"):
        run = _run(status=status)
        assert run.status == status

"""Phase 49 (ADR-0067): search budget allocation and truncation."""

from __future__ import annotations

from career_agent.agents.planner.budget import allocate_limits, apply_budget
from career_agent.agents.planner.execution_plan import SearchTask


def _task(priority: int, provider: str = "greenhouse") -> SearchTask:
    return SearchTask(
        provider=provider, query=f"query-{priority}", limit=0, priority=priority
    )


def test_allocate_limits_splits_evenly_with_remainder_to_earliest() -> None:
    assert allocate_limits(3, 10) == [4, 3, 3]


def test_allocate_limits_returns_empty_for_zero_tasks() -> None:
    assert allocate_limits(0, 100) == []


def test_allocate_limits_never_gives_less_than_one() -> None:
    assert allocate_limits(5, 2) == [1, 1, 1, 1, 1]


def test_apply_budget_with_no_tasks_returns_empty_and_no_stop_reason() -> None:
    tasks, stop_reason = apply_budget([], 100)
    assert tasks == []
    assert stop_reason is None


def test_apply_budget_fits_every_task_sets_real_limits_no_truncation() -> None:
    tasks = [_task(1), _task(2), _task(3)]
    result, stop_reason = apply_budget(tasks, 30)
    assert len(result) == 3
    assert stop_reason is None
    assert sum(t.limit for t in result) == 30


def test_apply_budget_truncates_lowest_priority_tasks_when_over_budget() -> None:
    tasks = [_task(i) for i in range(1, 11)]  # 10 tasks
    result, stop_reason = apply_budget(tasks, 3)
    assert len(result) == 3
    assert [t.priority for t in result] == [1, 2, 3]
    assert stop_reason == "budget_exhausted"


def test_apply_budget_zero_budget_drops_every_task() -> None:
    tasks = [_task(1), _task(2)]
    result, stop_reason = apply_budget(tasks, 0)
    assert result == []
    assert stop_reason == "budget_exhausted"


def test_apply_budget_never_leaves_a_task_with_a_zero_limit() -> None:
    """A present task must always have a real, non-zero limit -- otherwise
    it would be indistinguishable from 'searched and found nothing.'"""
    tasks = [_task(i) for i in range(1, 6)]
    result, _ = apply_budget(tasks, 2)
    assert all(t.limit > 0 for t in result)

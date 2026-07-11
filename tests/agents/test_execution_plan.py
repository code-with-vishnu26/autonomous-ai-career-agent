"""Phase 49 (ADR-0067): ExecutionPlan/SearchTask -- pure data, no I/O."""

from __future__ import annotations

from career_agent.agents.planner.execution_plan import ExecutionPlan, SearchTask


def test_search_task_max_retries_defaults_to_zero_and_unenforced() -> None:
    task = SearchTask(
        provider="greenhouse", query="Backend Engineer", limit=10, priority=1
    )
    assert task.max_retries == 0


def test_execution_plan_stop_reason_defaults_to_none() -> None:
    plan = ExecutionPlan(tasks=[], total_budget=100)
    assert plan.stop_reason is None


def test_execution_plan_generated_at_is_set_automatically() -> None:
    plan = ExecutionPlan(tasks=[], total_budget=100)
    assert plan.generated_at is not None

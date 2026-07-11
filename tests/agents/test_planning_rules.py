"""Phase 49 (ADR-0067): task-level dedup rules."""

from __future__ import annotations

from career_agent.agents.planner.execution_plan import SearchTask
from career_agent.agents.planner.planning_rules import deduplicate_tasks


def _task(provider: str, priority: int, query: str = "Backend Engineer") -> SearchTask:
    return SearchTask(provider=provider, query=query, limit=10, priority=priority)


def test_exact_provider_query_duplicates_are_dropped() -> None:
    tasks = [_task("greenhouse", 1), _task("greenhouse", 2)]
    result = deduplicate_tasks(tasks)
    assert len(result) == 1
    assert result[0].priority == 1  # first occurrence kept


def test_same_query_different_provider_is_not_a_duplicate() -> None:
    tasks = [_task("greenhouse", 1), _task("lever", 2)]
    assert deduplicate_tasks(tasks) == tasks


def test_original_order_is_preserved() -> None:
    tasks = [
        SearchTask(provider="a", query="x", limit=1, priority=1),
        SearchTask(provider="b", query="y", limit=1, priority=2),
        SearchTask(provider="a", query="x", limit=1, priority=3),
        SearchTask(provider="c", query="z", limit=1, priority=4),
    ]
    result = deduplicate_tasks(tasks)
    assert [t.priority for t in result] == [1, 2, 4]


def test_empty_input_returns_empty() -> None:
    assert deduplicate_tasks([]) == []

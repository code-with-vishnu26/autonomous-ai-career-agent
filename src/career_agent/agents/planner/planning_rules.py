"""Deterministic plan-shaping rules: dedup (Phase 49, ADR-0067).

**Scope note:** this deduplicates *planned tasks* (the same provider asked
the same query twice), never *discovered opportunities* -- that dedup
already exists, unchanged, at
:meth:`~career_agent.storage.sqlite.SqliteOpportunityRepository.add`
(ADR-0014's two-key identity), and stays entirely out of this phase's
scope (no I/O happens here at all).
"""

from __future__ import annotations

from career_agent.agents.planner.execution_plan import SearchTask


def deduplicate_tasks(tasks: list[SearchTask]) -> list[SearchTask]:
    """Drop exact ``(provider, query)`` duplicates.

    Keeps the first occurrence (highest priority, since callers pass
    already-ordered tasks) and its original position -- order-preserving,
    not merely "unique but reshuffled."
    """
    seen: set[tuple[str, str]] = set()
    result: list[SearchTask] = []
    for task in tasks:
        key = (task.provider, task.query)
        if key in seen:
            continue
        seen.add(key)
        result.append(task)
    return result

"""Search budget: target job count and truncation (Phase 49, ADR-0067).

**Deliberately distinct from ``JobPreferences.max_applications_per_day``**
(Phase 46) -- that field governs real applications submitted per day (not
yet enforced anywhere); this budget governs how many job postings one
*discovery planning cycle* targets fetching. Conflating the two would
misapply an application-rate limit to a search-volume decision they have
no necessary relationship to (a user could easily want to discover 200
jobs to review while only applying to 3 a day). No I/O, no adapter calls.
"""

from __future__ import annotations

from career_agent.agents.planner.execution_plan import SearchTask

#: Fallback per-task limit when a task's fair share would round to zero
#: (more tasks than budget) -- every task still gets at least one slot
#: rather than being silently starved to zero, which would make it
#: indistinguishable from a task that was intentionally dropped.
_MIN_TASK_LIMIT = 1


def allocate_limits(task_count: int, total_budget: int) -> list[int]:
    """Split ``total_budget`` roughly evenly across ``task_count`` tasks.

    Ceiling division for the first tasks, floor for the rest, so the sum
    never exceeds ``total_budget`` by more than ``task_count - 1`` in the
    worst case and every task gets at least :data:`_MIN_TASK_LIMIT`.
    Returns an empty list for zero tasks.
    """
    if task_count <= 0:
        return []
    base, remainder = divmod(total_budget, task_count)
    limits = [base + 1 if i < remainder else base for i in range(task_count)]
    return [max(limit, _MIN_TASK_LIMIT) for limit in limits]


def apply_budget(
    tasks: list[SearchTask], total_budget: int
) -> tuple[list[SearchTask], str | None]:
    """Fit ``tasks`` (already priority-ordered) within ``total_budget``.

    If every task fits at :data:`_MIN_TASK_LIMIT` or more, every task's
    ``limit`` is set from an even allocation and ``stop_reason`` is
    ``None``. If there are more tasks than the budget can give even one
    slot each, the lowest-priority (trailing) tasks are dropped entirely
    and ``stop_reason`` is ``"budget_exhausted"`` -- never a task silently
    present with a zero limit, which downstream code could mistake for "no
    results" rather than "never attempted."
    """
    if not tasks:
        return [], None
    if total_budget < len(tasks):
        kept = tasks[:total_budget] if total_budget > 0 else []
        limits = allocate_limits(len(kept), total_budget) if kept else []
        truncated = [
            task.model_copy(update={"limit": limit})
            for task, limit in zip(kept, limits, strict=True)
        ]
        return truncated, "budget_exhausted" if len(kept) < len(tasks) else None
    limits = allocate_limits(len(tasks), total_budget)
    return [
        task.model_copy(update={"limit": limit})
        for task, limit in zip(tasks, limits, strict=True)
    ], None
